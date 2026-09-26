import re
from ollama_client import extract_memories_with_ollama

def instant_memories(text):
    facts=[]
    for key,pat,category in [
      ('name',r"(?:my name is|my name's|call me)\s+([^.!?\n,]{2,50})",'personal'),
      ('education',r"(?:i study|i am studying|i'm studying|my branch is|my major is|my course is)\s+([^.!?\n]{2,100})",'education'),
      ('college',r"(?:my college is|i study at|i attend)\s+([^.!?\n]{3,100})",'education'),
      ('location',r"(?:i live in|i'm from|i am from|my hometown is)\s+([^.!?\n]{2,80})",'location'),
      ('favorite_language',r"my favorite (?:programming )?language is\s+([^.!?\n]{2,50})",'skills'),
      ('girlfriend_name',r"my girlfriend(?:'s name)? is\s+([^.!?\n]{2,50})",'personal'),
      ('address',r"my address is\s+([^.!?\n]{2,100})",'location')]:
        m=re.search(pat,text,re.I)
        if m:facts.append({'key':key,'value':m.group(1).strip(),'category':category})
    return facts

def forget_intent(text):
    clean=text.strip().lower().rstrip('.!?')
    if re.fullmatch(r'(?:please )?(?:forget|clear|erase|delete) (?:everything|all|all memories|my memory|my memories)(?: about me)?',clean):return ['__all__']
    m=re.fullmatch(r"(?:please )?(?:forget|don't remember|stop remembering|remove|delete|clear|erase) (?:my )?([\w '’]{2,50})",clean)
    if m:
        key=re.sub(r"['’]s\b|['’]",'',m.group(1)).replace(' ','_')
        return [key] if key not in ('it','this','that') else []
    return []
async def process_memory(db,uid,message):
    if message.get('memory_processed'):return
    forget=forget_intent(message['content']);facts=[] if forget else instant_memories(message['content'])
    if not facts and not forget:
        result=await extract_memories_with_ollama(message['content']);facts=result.get('memories',[]);forget=result.get('forget_keys',[])
    facts=[f for f in facts if 0<len(str(f.get('key','')))<=50 and 0<len(str(f.get('value','')))<=500][:12]
    await db.rpc('memory_apply',p_user=uid,p_message=message['id'],p_revision=message['revision'],p_memories=facts,p_forget=forget)
