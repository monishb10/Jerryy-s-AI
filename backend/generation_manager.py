"""Database-backed single-model FIFO worker; browser lifetimes never own jobs."""
import asyncio,base64,logging,time
from datetime import datetime,timezone
from uuid import uuid4
from fastapi import HTTPException
from ollama_client import stream_chat_with_ollama,warmup_ollama,model_capabilities,OllamaConnectionError,OllamaResponseError,OllamaModelNotFoundError
from context import build_context,join_continuation
from memory import process_memory
log=logging.getLogger('jerryys_ai.jobs')
def public_job(j):
    if not j:return None
    return {'generation_id':j['id'],**{k:j.get(k) for k in ('chat_id','status','user_message_id','response_id','stop_requested','error','warning','created_at','updated_at')},'content':j.get('partial_content','') if j['status'] in ('complete','stopped') else ''}
class GenerationManager:
    def __init__(self,db,storage):self.db=db;self.storage=storage;self.worker=str(uuid4());self.task=None;self.current=None;self.heartbeat=None;self.lost=False
    def start(self):self.task=asyncio.create_task(self.run())
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        try:await self.db.rpc('release',p_worker=self.worker)
        except Exception:pass
    async def beat(self):
        while True:
            await asyncio.sleep(5)
            try:
                if not await self.db.rpc('lease',p_worker=self.worker):raise RuntimeError()
            except Exception:
                self.lost=True
                if self.current:self.current.cancel()
                return
    async def run(self):
        warmed=False;last_cleanup=0
        try:
            while True:
                try:
                    if self.lost:
                        if self.heartbeat:self.heartbeat.cancel();await asyncio.gather(self.heartbeat,return_exceptions=True)
                        self.worker=str(uuid4());self.lost=False;self.heartbeat=None
                    if not await self.db.rpc('lease',p_worker=self.worker):await asyncio.sleep(2);continue
                    if not self.heartbeat or self.heartbeat.done():self.heartbeat=asyncio.create_task(self.beat())
                    if not warmed:
                        self.current=asyncio.create_task(warmup_ollama());await self.current;warmed=True;self.current=None
                    j=await self.db.rpc('claim',p_worker=self.worker)
                    if j:
                        self.current=asyncio.create_task(self.run_job(j));await self.current;self.current=None
                    elif time.monotonic()-last_cleanup>30:
                        last_cleanup=time.monotonic();await self.storage.cleanup()
                    else:await asyncio.sleep(.5)
                except asyncio.CancelledError:
                    if self.lost:continue
                    raise
                except Exception as e:
                    if isinstance(e, HTTPException):
                        detail = str(e.detail)
                        if 'not configured' in detail.lower():
                            info = 'missing environment variable (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_URL)'
                        elif e.status_code in (401, 403):
                            info = f'permission error (HTTP {e.status_code}: {detail})'
                        elif e.status_code == 404:
                            info = f'missing RPC (HTTP {e.status_code}: {detail})'
                        else:
                            info = f'HTTP status {e.status_code} ({detail})'
                    elif isinstance(e, httpx.HTTPError):
                        info = f'HTTP transport error: {type(e).__name__}'
                    else:
                        info = f'{type(e).__name__}: {str(e)}'
                    log.warning('queue_unavailable: %s', info)
                    await asyncio.sleep(2)
        finally:
            if self.current:self.current.cancel();await asyncio.gather(self.current,return_exceptions=True)
            if self.heartbeat:self.heartbeat.cancel();await asyncio.gather(self.heartbeat,return_exceptions=True)
    async def run_job(self,j):
        uid=j['user_id'];buffer='';warning=None;error=None;status='failed';generation=None;start=time.perf_counter()
        try:
            queued=(datetime.now(timezone.utc)-datetime.fromisoformat(j['created_at'].replace('Z','+00:00'))).total_seconds();log.info('queue_wait_ms=%.1f',queued*1000)
            async def produce():
                nonlocal buffer,warning
                user=await self.db.one('messages',uid,j['user_message_id']);t=time.perf_counter()
                try:await process_memory(self.db,uid,user)
                except Exception:warning='Account memory could not be updated for this response.'
                try:memories=await self.db.rows('user_memories',uid,limit=20,order='updated_at.desc')
                except Exception:memories=[];warning='Account memory is temporarily unavailable.'
                log.info('memory_load_ms=%.1f',(time.perf_counter()-t)*1000)
                rows=await self.db.rows('messages',uid,chat_id='eq.'+j['chat_id'],sequence_no='lte.'+str(user['sequence_no']),order='sequence_no.desc',limit=24);rows.reverse()
                ids=[m['id'] for m in rows];attachments=await self.db.rows('message_attachments',uid,chat_id='eq.'+j['chat_id'],message_id='in.('+','.join(ids)+')',limit=96)
                images=[a for a in attachments if a['message_id']==user['id'] and a['file_type'].startswith('image/')]
                if images:
                    if (await model_capabilities()).get('vision') is True:
                        for a in images:a['image_base64']=base64.b64encode(await self.storage.read(a['storage_path'])).decode()
                    else:warning='Images are saved privately; your installed local model has not confirmed vision support.'
                context=build_context(rows,memories,attachments,base=j['base_content']);t=time.perf_counter()
                try:
                    async for chunk in stream_chat_with_ollama(context):
                        buffer+=chunk
                        if len(buffer)+len(j['base_content'])>100000:raise OllamaResponseError('Response exceeded its size limit. Ask for a shorter response.')
                finally:log.info('ollama_generation_ms=%.1f',(time.perf_counter()-t)*1000)
            generation=asyncio.create_task(produce())
            while True:
                done,_=await asyncio.wait([generation],timeout=.7)
                stopped=await self.db.rpc('checkpoint',p_worker=self.worker,p_job=j['id'],p_content=join_continuation(j['base_content'],buffer))
                if stopped:
                    generation.cancel();await asyncio.gather(generation,return_exceptions=True);status='stopped';break
                if done:
                    await generation
                    if not buffer.strip():raise OllamaResponseError('The local model returned an empty response. Use Retry.')
                    status='complete';break
        except (OllamaConnectionError,OllamaResponseError,OllamaModelNotFoundError) as e:error=str(e)
        except HTTPException as e:error=str(e.detail)
        except asyncio.CancelledError:
            error='The backend stopped during generation. Use Retry.'
            raise
        except Exception:error='Generation could not finish. Please use Retry.';log.warning('generation_failed')
        finally:
            if generation and not generation.done():generation.cancel();await asyncio.gather(generation,return_exceptions=True)
            if not self.lost:
                for attempt in range(4):
                    try:
                        await self.db.rpc('finish',p_worker=self.worker,p_job=j['id'],p_status=status,p_content=join_continuation(j['base_content'],buffer),p_error=error,p_warning=warning);break
                    except Exception:
                        if attempt==3:self.lost=True;log.warning('generation_save_failed')
                        else:await asyncio.sleep(.5*(attempt+1))
            log.info('job_total_ms=%.1f',(time.perf_counter()-start)*1000)
