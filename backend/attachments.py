"""Private storage, bounded extraction, and retryable cleanup."""
import asyncio,io,multiprocessing,os,re,time
from datetime import datetime,timedelta,timezone
from pathlib import PurePath
from urllib.parse import quote
from uuid import UUID,uuid4
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request,UploadFile,File,Response
from auth import get_current_user
from config import SUPABASE_URL,BUCKET,MAX_FILE_BYTES,MAX_TEXT_CHARS
router=APIRouter(prefix='/api')
IMAGES={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}
TEXT={'.txt','.md','.csv','.tsv','.log','.py','.java','.js','.jsx','.ts','.tsx','.sql','.html','.htm','.css','.scss','.c','.h','.cpp','.hpp','.cc','.cs','.json','.jsonl','.sh','.bash','.ps1','.yaml','.yml','.xml','.toml','.ini','.cfg','.rs','.go','.rb','.php','.swift','.kt','.r','.vue','.svelte','.ipynb'}
def file_kind(name,mime):
    if not name or len(name)>180 or any(x in name for x in ('/','\\','..')) or any(ord(c)<32 for c in name):raise HTTPException(400,'Invalid file name.')
    ext=PurePath(name).suffix.lower();mime=(mime or '').lower().split(';')[0]
    if ext in IMAGES and mime in (IMAGES[ext],'application/octet-stream',''):return ext,IMAGES[ext]
    if ext=='.pdf' and mime in ('application/pdf','application/octet-stream',''):return ext,'application/pdf'
    allowed={'','application/octet-stream','application/json','application/javascript','application/typescript','application/xml','application/x-sh','application/x-python-code','application/sql','application/yaml','application/x-powershell'}
    if ext in TEXT and (mime.startswith('text/') or mime in allowed):return ext,'text/plain'
    raise HTTPException(400,'Unsupported file type or MIME type. Select an image, PDF, text, or source-code file.')
def _extract_child(conn,data,kind):
    try:
        if os.name=='posix':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(12,12))
        text=''
        if kind.startswith('image/'):
            from PIL import Image
            Image.MAX_IMAGE_PIXELS=12000000
            im=Image.open(io.BytesIO(data))
            actual={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp','GIF':'image/gif'}.get(im.format)
            if actual!=kind or im.width*im.height>12000000:raise ValueError('Invalid image or image exceeds 12 megapixels.')
            im.verify()
        elif kind=='application/pdf':
            from pypdf import PdfReader
            if not data.startswith(b'%PDF-'):raise ValueError('Invalid PDF file.')
            reader=PdfReader(io.BytesIO(data),strict=True)
            if reader.is_encrypted:raise ValueError('Encrypted PDFs are not supported. Upload an unlocked copy.')
            if len(reader.pages)>80:raise ValueError('PDF exceeds 80 pages. Upload a smaller excerpt.')
            for page in reader.pages:
                content=page.get_contents()
                if content and len(content.get_data())>2000000:raise ValueError('PDF page is too complex. Upload a smaller excerpt.')
                text+=(page.extract_text() or '')+'\n'
                if len(text)>MAX_TEXT_CHARS:raise ValueError('PDF text exceeds 12,000 characters. Upload a smaller excerpt.')
            if not text.strip():raise ValueError('This PDF has no readable text. Scanned PDFs require OCR before upload.')
        else:
            try:text=data.decode('utf-8-sig')
            except UnicodeDecodeError:raise ValueError('Text files must use UTF-8 encoding.')
            if '\x00' in text or any(ord(c)<32 and c not in '\n\r\t' for c in text):raise ValueError('The file contains binary data.')
            if len(text)>MAX_TEXT_CHARS:raise ValueError('Text exceeds 12,000 characters. Upload a smaller excerpt.')
        conn.send({'text':text})
    except ValueError as e:conn.send({'error':str(e)})
    except Exception:conn.send({'error':'The file could not be safely read. Try another file.'})
    finally:conn.close()
async def extract(data,kind):
    ctx=multiprocessing.get_context('spawn');parent,child=ctx.Pipe(duplex=False);process=ctx.Process(target=_extract_child,args=(child,data,kind),daemon=True);process.start();child.close();deadline=time.monotonic()+15
    try:
        while not parent.poll():
            if not process.is_alive() or time.monotonic()>deadline:raise HTTPException(400,'File processing exceeded its limit. Use a smaller or simpler file.')
            await asyncio.sleep(.05)
        try:result=parent.recv()
        except EOFError:raise HTTPException(400,'File could not be processed safely.')
        if result.get('error'):raise HTTPException(400,result['error'])
        return result['text']
    finally:
        if process.is_alive():process.terminate()
        await asyncio.to_thread(process.join,2);parent.close()
class Storage:
    def __init__(self,db):self.db=db
    async def call(self,method,path,**kwargs):
        try:r=await self.db.client.request(method,SUPABASE_URL+'/storage/v1/'+path,headers={**self.db.headers(),**kwargs.pop('headers',{})},**kwargs)
        except httpx.HTTPError:raise HTTPException(503,'Private file storage is unavailable.')
        if r.status_code>=400:raise HTTPException(503,'Private file storage operation failed. Check the bucket setup and retry.')
        return r
    async def upload(self,path,data,kind):await self.call('POST','object/'+BUCKET+'/'+quote(path,safe='/'),content=data,headers={'Content-Type':kind,'x-upsert':'false'})
    async def read(self,path):return (await self.call('GET','object/authenticated/'+BUCKET+'/'+quote(path,safe='/'))).content
    async def remove(self,paths):
        if paths:await self.call('DELETE','object/'+BUCKET,json={'prefixes':paths})
    async def cleanup(self):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
        await self.db.request('DELETE','message_attachments',params={'message_id':'is.null','created_at':'lt.'+cutoff})
        rows=await self.db.request('GET','attachment_cleanup',params={'select':'*','limit':100})
        for r in rows:
            await self.remove([r['storage_path']]);await self.db.request('DELETE','attachment_cleanup',params={'storage_path':'eq.'+r['storage_path']})
def public_attachment(a):return {k:a[k] for k in ('id','chat_id','message_id','file_name','file_type','file_size','created_at')}
@router.post('/chats/{chat_id}/attachments')
async def upload(chat_id:UUID,request:Request,file:UploadFile=File(...),user=Depends(get_current_user)):
    db=request.app.state.db;await db.one('chats',user.id,chat_id,token=user.token)
    ext,kind=file_kind(file.filename,file.content_type);data=await file.read(MAX_FILE_BYTES+1);await file.close()
    if not data:raise HTTPException(400,'The selected file is empty.')
    if len(data)>MAX_FILE_BYTES:raise HTTPException(413,'Files must be 10 MB or smaller.')
    async with request.app.state.extraction_lock:text=await extract(data,kind)
    aid=str(uuid4());path=f'{user.id}/{chat_id}/{aid}{ext}';storage=request.app.state.storage
    await storage.upload(path,data,kind)
    try:
        rows=await db.request('POST','message_attachments',data={'id':aid,'user_id':user.id,'chat_id':str(chat_id),'file_name':file.filename,'file_type':kind,'file_size':len(data),'storage_path':path,'extracted_text':text},headers={'Prefer':'return=representation'})
    except Exception:
        try:
            await db.request('POST','attachment_cleanup',data={'storage_path':path},headers={'Prefer':'resolution=ignore-duplicates'});await storage.remove([path])
        except Exception:pass
        raise
    out=public_attachment(rows[0])
    if kind.startswith('image/'):
        from ollama_client import model_capabilities
        if (await model_capabilities()).get('vision') is not True:out['warning']='Image saved privately. Understanding this image requires confirmed vision support in your installed local model.'
    return out
@router.delete('/attachments/{attachment_id}')
async def delete(attachment_id:UUID,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;a=await db.one('message_attachments',user.id,attachment_id,token=user.token)
    if a['message_id']:raise HTTPException(409,'Sent attachments are removed with their chat or message.')
    await db.request('DELETE','message_attachments',params={'id':'eq.'+str(attachment_id),'user_id':'eq.'+user.id,'message_id':'is.null'})
    return {'ok':True}
@router.get('/attachments/{attachment_id}/content')
async def content(attachment_id:UUID,request:Request,user=Depends(get_current_user)):
    a=await request.app.state.db.one('message_attachments',user.id,attachment_id,token=user.token);data=await request.app.state.storage.read(a['storage_path'])
    disposition='inline' if a['file_type'].startswith('image/') else 'attachment'
    return Response(data,media_type=a['file_type'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Disposition':disposition+"; filename*=UTF-8''"+quote(a['file_name'],safe='')})
