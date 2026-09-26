"""Authenticated chat, generation, and account memory API."""
from uuid import UUID
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from auth import get_current_user
from attachments import public_attachment
from generation_manager import public_job
from context import title_for
from memory import instant_memories,forget_intent
router=APIRouter(prefix='/api')
class Input(BaseModel):model_config=ConfigDict(extra='forbid')
class NewChat(Input):id:UUID
class Rename(Input):title:str=Field(min_length=1,max_length=80)
class Generate(Input):
    chat_id:UUID
    request_id:UUID
    action:Literal['send','retry','regenerate','continue','edit']='send'
    message:str=Field(default='',max_length=4000)
    target_id:UUID|None=None
    attachment_ids:list[UUID]=Field(default_factory=list,max_length=4)
@router.get('/chats')
async def chats(request:Request,q:str=Query('',max_length=120),offset:int=Query(0,ge=0,le=100000),user=Depends(get_current_user)):
    return await request.app.state.db.rpc('search',p_user=user.id,p_query=q.strip(),p_offset=offset)
@router.post('/chats')
async def create(body:NewChat,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db
    await db.request('POST','chats',data={'id':str(body.id),'user_id':user.id,'title':'New Chat'},headers={'Prefer':'resolution=ignore-duplicates,return=minimal'})
    return await db.one('chats',user.id,body.id,token=user.token)
async def all_rows(db,table,uid,token,**params):
    result=[]
    while True:
        part=await db.rows(table,uid,token=token,limit=500,offset=len(result),**params);result+=part
        if len(part)<500:return result
@router.get('/chats/{chat_id}')
async def load(chat_id:UUID,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;chat=await db.one('chats',user.id,chat_id,token=user.token)
    # Read status before messages: a concurrent completion is either visible now,
    # or the returned active job causes another fetch. No completed answer is lost.
    jobs=await db.rows('generation_jobs',user.id,token=user.token,chat_id='eq.'+str(chat_id),invalidated='eq.false',order='created_at.desc,id.desc',limit=1)
    messages=await all_rows(db,'messages',user.id,user.token,chat_id='eq.'+str(chat_id),order='sequence_no.asc')
    attachments=await all_rows(db,'message_attachments',user.id,user.token,chat_id='eq.'+str(chat_id),order='created_at.asc')
    for m in messages:m['attachments']=[public_attachment(a) for a in attachments if a['message_id']==m['id']]
    return {'chat':chat,'messages':messages,'generation':public_job(jobs[0]) if jobs else None}
@router.post('/chats/{chat_id}/touch')
async def touch(chat_id:UUID,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;await db.one('chats',user.id,chat_id,token=user.token)
    await db.request('PATCH','chats',params={'id':'eq.'+str(chat_id),'user_id':'eq.'+user.id},data={'updated_at':datetime.now(timezone.utc).isoformat()})
    return {'ok':True}
@router.patch('/chats/{chat_id}')
async def rename(chat_id:UUID,body:Rename,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;await db.one('chats',user.id,chat_id,token=user.token)
    if not body.title.strip():raise HTTPException(400,'Enter a chat title.')
    rows=await db.request('PATCH','chats',params={'id':'eq.'+str(chat_id),'user_id':'eq.'+user.id},data={'title':body.title.strip(),'updated_at':datetime.now(timezone.utc).isoformat()},headers={'Prefer':'return=representation'})
    return rows[0]
@router.delete('/chats/{chat_id}')
async def delete(chat_id:UUID,request:Request,user=Depends(get_current_user)):
    await request.app.state.db.rpc('delete_chat',p_user=user.id,p_chat=str(chat_id));return {'ok':True}
@router.post('/generations')
async def generate(body:Generate,request:Request,user=Depends(get_current_user)):
    if body.action!='send' and body.target_id is None:raise HTTPException(400,'Select the message or response to change.')
    if body.action!='send' and body.attachment_ids:raise HTTPException(400,'Attachments can only be added to a new message.')
    db=request.app.state.db
    await db.one('chats',user.id,body.chat_id,token=user.token)
    j=await db.rpc('prepare',p_user=user.id,p_chat=str(body.chat_id),p_request=str(body.request_id),p_action=body.action,p_message=body.message.strip(),p_target=str(body.target_id) if body.target_id else None,p_attachments=[str(a) for a in body.attachment_ids],p_title=title_for(body.message),p_user_limit=3,p_total_limit=30)
    return public_job(j)
@router.get('/generations/{generation_id}')
async def status(generation_id:UUID,request:Request,user=Depends(get_current_user)):
    return public_job(await request.app.state.db.one('generation_jobs',user.id,generation_id,token=user.token))
@router.get('/chats/{chat_id}/generation')
async def active(chat_id:UUID,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;await db.one('chats',user.id,chat_id,token=user.token)
    rows=await db.rows('generation_jobs',user.id,token=user.token,chat_id='eq.'+str(chat_id),status='in.(queued,generating)',limit=1)
    return public_job(rows[0]) if rows else None
@router.post('/generations/{generation_id}/stop')
async def stop(generation_id:UUID,request:Request,user=Depends(get_current_user)):
    return public_job(await request.app.state.db.rpc('stop',p_user=user.id,p_job=str(generation_id)))
@router.get('/memories')
async def memories(request:Request,user=Depends(get_current_user)):
    return await request.app.state.db.rows('user_memories',user.id,token=user.token,order='updated_at.desc',limit=500)
@router.delete('/memories')
async def clear(request:Request,user=Depends(get_current_user)):
    await request.app.state.db.rpc('forget',p_user=user.id,p_key=None);return {'ok':True}
@router.delete('/memories/{memory_id}')
async def forget(memory_id:UUID,request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;m=await db.one('user_memories',user.id,memory_id,token=user.token)
    await db.rpc('forget',p_user=user.id,p_key=m['memory_key']);return {'ok':True}
@router.post('/memories/rescan')
async def rescan(request:Request,user=Depends(get_current_user)):
    db=request.app.state.db;rows=await db.rows('messages',user.id,token=user.token,role='eq.user',order='sequence_no.desc',limit=80);facts={}
    for row in reversed(rows):
        forget=forget_intent(row['content'])
        if '__all__' in forget:facts.clear()
        else:
            for key in forget:facts.pop(key,None)
        if not forget:
            for f in instant_memories(row['content']):facts[f['key']]={**f,'source':row['id']}
    for f in facts.values():
        await db.request('POST','user_memories',params={'on_conflict':'user_id,memory_key'},data={'user_id':user.id,'memory_key':f['key'],'memory_value':f['value'],'category':f['category'],'source_message_id':f['source']},headers={'Prefer':'resolution=merge-duplicates'})
    return {'ok':True,'count':len(facts)}
