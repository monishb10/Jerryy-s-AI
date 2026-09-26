"""Supabase REST. Privileged RPCs are service-role-only and require verified ownership."""
import time, logging
import httpx
from fastapi import HTTPException
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY

log = logging.getLogger('jerryys_ai.database')

class Database:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=25)

    def headers(self, token=None):
        if not SUPABASE_URL:
            raise HTTPException(503, 'Database is not configured.')
        if token:
            if not SUPABASE_KEY:
                raise HTTPException(503, 'Database is not configured.')
            return {
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {token}'
            }
        if not SUPABASE_SERVICE_ROLE_KEY:
            raise HTTPException(503, 'Database is not configured.')
        h = {'apikey': SUPABASE_SERVICE_ROLE_KEY}
        if SUPABASE_SERVICE_ROLE_KEY.startswith('eyJ'):
            h['Authorization'] = f'Bearer {SUPABASE_SERVICE_ROLE_KEY}'
        return h

    async def request(self, method, path, *, token=None, params=None, data=None, headers=None):
        start = time.perf_counter()
        try:
            r = await self.client.request(
                method,
                SUPABASE_URL + '/rest/v1/' + path,
                headers={**self.headers(token), **(headers or {})},
                params=params,
                json=data
            )
        except httpx.HTTPError:
            raise HTTPException(503, 'Database unavailable. Please retry.')
        finally:
            if method != 'GET':
                log.info('database_write_ms=%.1f', (time.perf_counter() - start) * 1000)
        if r.status_code >= 400:
            try:
                err = r.json()
            except ValueError:
                err = {}
            errors = {
                'not_found': (404, 'Item not found.'),
                'busy': (409, 'This chat already has an active response.'),
                'stale': (409, 'This conversation changed. Reload it.'),
                'invalid_action': (409, 'This action is unavailable.'),
                'attachments': (400, 'Attachments are unavailable or too large.'),
                'queue_full': (429, 'The queue is full. Please try again shortly.'),
                'request_conflict': (409, 'This request ID was already used.')
            }
            if err.get('message') in errors:
                raise HTTPException(*errors[err['message']])
            if token and r.status_code in (401, 403):
                raise HTTPException(r.status_code, 'Session or permission denied.')
            log.warning('database_error status=%s code=%s', r.status_code, err.get('code', 'unknown'))
            if r.status_code in (401, 403):
                raise HTTPException(r.status_code, f'Permission denied (status {r.status_code}, code {err.get("code", "unknown")})')
            if r.status_code == 404:
                raise HTTPException(404, f'Not found or missing RPC (status 404, code {err.get("code", "unknown")})')
            raise HTTPException(503, 'Database operation failed. Check the required migration, then retry.')
        return r.json() if r.content else None

    async def rows(self, table, uid, *, token=None, **filters):
        return await self.request('GET', table, token=token, params={'select': '*', 'user_id': 'eq.' + uid, **filters})

    async def one(self, table, uid, rid, *, token=None):
        rows = await self.rows(table, uid, token=token, id='eq.' + str(rid), limit=1)
        if not rows:
            raise HTTPException(404, 'Item not found.')
        return rows[0]

    async def rpc(self, name, **data):
        return await self.request('POST', 'rpc/jai_' + name, data=data)

    async def close(self):
        await self.client.aclose()
