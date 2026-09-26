import sys,asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,httpx
from fastapi import HTTPException
from context import title_for,build_context,join_continuation
from memory import instant_memories,forget_intent
from attachments import file_kind,extract
from generation_manager import public_job
from ollama_client import payload

def test_title():assert title_for('Explain binary search with an example')=='Binary Search Explanation'
def test_context_is_bounded():
    rows=[{'id':str(i),'role':'user' if i%2==0 else 'assistant','content':'x'*1000} for i in range(100)]
    context=build_context(rows,[],[]);assert sum(len(x['content']) for x in context)<=18000;assert len(context)<=25;assert context[-1]['content']==rows[-1]['content']
def test_continue_overlap():
    assert join_continuation('This is a sufficiently long sentence.','This is a sufficiently long sentence. And more')=='This is a sufficiently long sentence. And more'
    assert join_continuation('Hello ','world')=='Hello world'
def test_memory():
    assert instant_memories('My name is Monish.')[0]['value']=='Monish';assert instant_memories('I study AI & Data Science.')[0]['value']=='AI & Data Science';assert forget_intent('Forget everything about me.')==['__all__']
def test_job_hides_partial():
    j={'id':'x','status':'generating','partial_content':'private partial'};assert public_job(j)['content']=='';j['status']='stopped';assert public_job(j)['content']=='private partial'
def test_ollama_settings():
    p=payload([]);assert p['model']=='jerryys-ai' and p['think'] is False and p['keep_alive']=='30m'
@pytest.mark.parametrize('name,mime',[('../a.txt','text/plain'),('a.exe','application/octet-stream'),('a.png','text/plain')])
def test_file_rejected(name,mime):
    with pytest.raises(HTTPException):file_kind(name,mime)
@pytest.mark.asyncio
async def test_extraction():
    assert await extract(b'hello\nworld','text/plain')=='hello\nworld'
    with pytest.raises(HTTPException):await extract(b'bad\x00','text/plain')
    with pytest.raises(HTTPException):await extract(b'x'*12001,'text/plain')
    with pytest.raises(HTTPException):await extract(b'not png','image/png')

@pytest.mark.asyncio
async def test_image_and_pdf_validation():
    import io
    from PIL import Image
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    image=io.BytesIO();Image.new('RGB',(3,3)).save(image,format='PNG')
    assert await extract(image.getvalue(),'image/png')==''
    pdf=PdfWriter();page=pdf.add_blank_page(200,200);font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):pdf._add_object(font)})});stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 100 Td (Hello PDF) Tj ET');page[NameObject('/Contents')]=pdf._add_object(stream);output=io.BytesIO();pdf.write(output)
    assert 'Hello PDF' in await extract(output.getvalue(),'application/pdf')
    with pytest.raises(HTTPException):await extract(b'not a pdf','application/pdf')

@pytest.mark.asyncio
async def test_private_config_is_never_exposed(monkeypatch):
    import main
    monkeypatch.setattr(main,'SUPABASE_KEY','sb_secret_do_not_return')
    with pytest.raises(HTTPException):await main.config()
