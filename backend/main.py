"""FastAPI entry point. Private data is served only through authenticated routes."""
import asyncio,logging,os,base64,json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from config import SUPABASE_URL,SUPABASE_KEY,SUPABASE_SERVICE_ROLE_KEY,OLLAMA_MODEL,MAX_FILE_BYTES
from database import Database
from attachments import Storage,router as attachment_router
from chat import router as chat_router
from generation_manager import GenerationManager
from ollama_client import check_ollama_health
logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
ROOT=Path(__file__).resolve().parent.parent
@asynccontextmanager
async def lifespan(app):
    app.state.db=Database();app.state.storage=Storage(app.state.db);app.state.extraction_lock=asyncio.Semaphore(1);app.state.jobs=GenerationManager(app.state.db,app.state.storage);app.state.jobs.start()
    yield
    await app.state.jobs.close();await app.state.db.close()
app=FastAPI(title="Jerryy's AI",lifespan=lifespan)
class UploadLimit:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH'):return await self.app(scope,receive,send)
        limit=MAX_FILE_BYTES+1024*1024 if scope['path'].endswith('/attachments') else 128*1024
        headers=dict(scope.get('headers',[]));length=headers.get(b'content-length',b'0')
        try:too_large=int(length)>limit
        except ValueError:too_large=True
        if too_large:return await JSONResponse({'detail':'Request is too large. Files must be 10 MB or smaller.'},status_code=413)(scope,receive,send)
        total=0
        async def bounded():
            nonlocal total
            message=await receive();total+=len(message.get('body',b''))
            if total>limit:raise HTTPException(413,'Request is too large.')
            return message
        await self.app(scope,bounded,send)
app.add_middleware(UploadLimit)
app.add_middleware(CORSMiddleware,allow_origins=[s.strip() for s in os.getenv('CORS_ORIGINS','http://localhost:8000,http://127.0.0.1:8000').split(',') if s.strip()],allow_credentials=False,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Authorization','Content-Type'])
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request);response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response
@app.exception_handler(Exception)
async def unexpected(request,exc):
    logging.getLogger('jerryys_ai').warning('request_failed type=%s',type(exc).__name__)
    return JSONResponse({'detail':'The service could not complete this request. Please retry.'},status_code=500)
app.include_router(chat_router);app.include_router(attachment_router)
@app.get('/api/config')
async def config():
    private=SUPABASE_KEY.startswith('sb_secret_') or bool(SUPABASE_KEY and SUPABASE_KEY==SUPABASE_SERVICE_ROLE_KEY)
    try:
        part=SUPABASE_KEY.split('.')[1];private=private or json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4))).get('role')=='service_role'
    except (IndexError,ValueError,TypeError):pass
    if private:raise HTTPException(503,'Use a publishable or anon key for SUPABASE_KEY. Keep the service-role key server-only.')
    return {'supabase_url':SUPABASE_URL,'supabase_key':SUPABASE_KEY}
@app.get('/api/health')
async def health(request:Request):
    capabilities=await check_ollama_health();available=False
    try:await request.app.state.db.request('GET','chats',params={'select':'id','limit':1});available=True
    except Exception:pass
    return {'service':'Jerryy\'s AI','model':OLLAMA_MODEL,'ollama':capabilities,'database_available':available}
@app.get('/')
@app.get('/index.html')
async def index():return FileResponse(ROOT/'index.html')
@app.get('/chat')
@app.get('/chat.html')
async def page():return FileResponse(ROOT/'chat.html')
@app.get('/loopstack.html')
async def legacy():return RedirectResponse('/#loopstack')
app.mount('/assets',StaticFiles(directory=ROOT/'frontend'/'assets',check_dir=False),name='assets')
