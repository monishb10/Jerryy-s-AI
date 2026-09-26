"""Only Supabase-verified identity. No production test tokens."""
import time,hashlib,base64,json
from uuid import UUID
import httpx
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel
from config import SUPABASE_URL,SUPABASE_KEY
class AuthenticatedUser(BaseModel):
    id:str
    token:str
security=HTTPBearer(auto_error=False)
_cache={}
async def verify_supabase_token(token):
    if not SUPABASE_URL or not SUPABASE_KEY:raise HTTPException(503,'Authentication is not configured.')
    if not token or len(token)>16384 or token.startswith('test-token-'):raise HTTPException(401,'Invalid session.')
    expiry=time.time()+15
    try:
        p=token.split('.')[1];claim=json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4)))
        if isinstance(claim.get('exp'),(int,float)):expiry=min(expiry,claim['exp'])
    except (ValueError,IndexError,TypeError):pass
    if expiry<=time.time():raise HTTPException(401,'Session expired. Please sign in again.')
    key=hashlib.sha256(token.encode()).hexdigest();cached=_cache.get(key)
    if cached and cached[0]>time.time():return AuthenticatedUser(id=cached[1],token=token)
    try:
        async with httpx.AsyncClient(timeout=10) as c:r=await c.get(SUPABASE_URL+'/auth/v1/user',headers={'apikey':SUPABASE_KEY,'Authorization':'Bearer '+token})
    except httpx.HTTPError:raise HTTPException(503,'Sign-in verification is temporarily unavailable.')
    if r.status_code in (401,403):raise HTTPException(401,'Session expired. Please sign in again.')
    if r.status_code!=200:raise HTTPException(503,'Sign-in verification is temporarily unavailable.')
    try:uid=str(UUID(r.json()['id']))
    except (ValueError,KeyError,TypeError):raise HTTPException(401,'Invalid identity.')
    if len(_cache)>=512:_cache.clear()
    _cache[key]=(expiry,uid)
    return AuthenticatedUser(id=uid,token=token)
async def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(security)):
    if not credentials or credentials.scheme.lower()!='bearer':raise HTTPException(401,'Please sign in.',headers={'WWW-Authenticate':'Bearer'})
    return await verify_supabase_token(credentials.credentials)
