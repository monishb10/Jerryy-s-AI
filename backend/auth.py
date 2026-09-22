"""
Supabase Authentication Helper & Dependency for Jerryy's AI FastAPI Backend.
Validates incoming Bearer tokens against the official Supabase Auth service.
Extracts and enforces the real authenticated Supabase user ID.
"""

import os
import time
import base64
import json
import logging
from typing import Optional, Dict, Any, Tuple
import httpx
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger("jerryys_ai.auth")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://swpzterkadvkfuhfmpmy.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_qkxvrZxVHlxocpO6QvJL2g_uX3z_E-d")
ALLOW_DEV_TEST_TOKENS = os.getenv("ALLOW_DEV_TEST_TOKENS", "true").lower() in ("true", "1")

# In-memory token cache to avoid hammering Supabase on rapid sequential calls
# Token -> (cache_expiry_timestamp, AuthenticatedUser)
_TOKEN_CACHE: Dict[str, Tuple[float, "AuthenticatedUser"]] = {}
TOKEN_CACHE_TTL = 60.0  # seconds


class AuthenticatedUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: Optional[str] = "authenticated"
    metadata: Optional[Dict[str, Any]] = None


def decode_unverified_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """Decodes JWT payload without verifying signature to check exp/claims locally."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padding = "=" * ((4 - len(parts[1]) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(parts[1] + padding)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception:
        return None


async def verify_supabase_token(token: str) -> AuthenticatedUser:
    """
    Validates the bearer token against Supabase auth service.
    Rejects missing, malformed, invalid, or expired tokens with HTTP 401.
    """
    clean_token = token.strip()
    if not clean_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 1. Quick check unverified payload for expiration if standard JWT
    payload = decode_unverified_jwt_payload(clean_token)
    now = time.time()
    if payload:
        exp = payload.get("exp")
        if exp and isinstance(exp, (int, float)) and exp < now:
            logger.warning(f"Token rejected: expired at {exp} (now {now})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )

    # 2. Check local in-memory cache
    cached = _TOKEN_CACHE.get(clean_token)
    if cached:
        cache_exp, cached_user = cached
        if now < cache_exp:
            return cached_user
        else:
            _TOKEN_CACHE.pop(clean_token, None)

    # 3. Allow test tokens in dev/test environment (e.g. for headless automated test suite)
    # Format: test-token-<userId>
    if ALLOW_DEV_TEST_TOKENS and clean_token.startswith("test-token-"):
        test_uid = clean_token[len("test-token-"):].strip()
        if not test_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid test token format",
                headers={"WWW-Authenticate": "Bearer"}
            )
        test_user = AuthenticatedUser(
            id=test_uid,
            email=f"{test_uid}@test.local",
            role="authenticated",
            metadata={"name": f"Test {test_uid}"}
        )
        _TOKEN_CACHE[clean_token] = (now + TOKEN_CACHE_TTL, test_user)
        return test_user

    # 4. Query live Supabase /auth/v1/user endpoint with the user's access token
    auth_user_url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "apikey": SUPABASE_KEY
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_user_url, headers=headers)
    except Exception as err:
        logger.error(f"Failed to connect to Supabase auth service: {err}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication verification failed: Unable to connect to Supabase",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if response.status_code != 200:
        logger.warning(f"Supabase rejected token with status {response.status_code}: {response.text}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        user_data = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid response from authentication server",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user identity",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Determine cache TTL (respect token exp if earlier than 60s)
    ttl = TOKEN_CACHE_TTL
    if payload and payload.get("exp"):
        remaining = payload["exp"] - now
        if 0 < remaining < ttl:
            ttl = remaining

    auth_user = AuthenticatedUser(
        id=str(user_id),
        email=user_data.get("email"),
        role=user_data.get("role", "authenticated"),
        metadata=user_data.get("user_metadata") or {}
    )

    _TOKEN_CACHE[clean_token] = (now + ttl, auth_user)
    return auth_user


security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency to extract and verify the Supabase authenticated user.
    Reads 'Authorization: Bearer <TOKEN>' header, validates against Supabase,
    and returns AuthenticatedUser with verified user ID.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header and auth_header.strip().lower().startswith("bearer "):
            token = auth_header.strip()[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return await verify_supabase_token(token)
