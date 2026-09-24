"""
Jerryy's AI FastAPI Backend
Connects the web frontend to local Ollama (jerryys-ai) model with chat profile support.
"""

import os
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

import httpx
from auth import get_current_user, AuthenticatedUser, SUPABASE_URL, SUPABASE_KEY
from generation_manager import generation_manager, GenerationJob

from ollama_client import (
    chat_with_ollama,
    stream_chat_with_ollama,
    extract_memories_with_ollama,
    extract_batch_memories_with_ollama,
    check_ollama_health,
    warmup_ollama,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OLLAMA_MODEL
)
from chat_profiles import get_chat_profile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jerryys_ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run Ollama model warm-up as a background startup task without blocking FastAPI startup
    asyncio.create_task(warmup_ollama())
    yield


app = FastAPI(
    title="Jerryy's AI — Local Learning & Exam Preparation Model",
    description="FastAPI service connecting to local Ollama instance running jerryys-ai model.",
    version="2.1.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified System Prompt: Jerryy's AI behaves as a versatile general-purpose assistant
UNIFIED_SYSTEM_PROMPT = (
    "You are Jerryy's AI, a general-purpose conversational AI assistant.\n"
    "Answer the user's actual question directly, accurately, and naturally in clear English.\n"
    "For simple greetings (e.g. 'hi', 'hello', 'hey'), respond briefly and warmly (e.g. 'Hi! How can I help?' or 'Hello! What can I help you with?') without reciting capabilities or giving long introductions.\n"
    "If asked 'Who are you?', answer naturally as a general-purpose AI assistant without calling yourself primarily an exam or study tutor.\n"
    "Provide simple direct answers for simple questions, detailed answers for complex requests, clean code for programming, and study/exam help only when the user explicitly asks for it.\n"
    "Do not include unnecessary self-promotions or capability lists."
)


def build_memory_context(memories: List[Dict[str, Any]]) -> str:
    """
    Constructs a concise, structured memory context block for Ollama.
    Scoped strictly to the currently authenticated user.
    """
    if not memories:
        return ""

    dedup = {}
    for mem in memories:
        k = mem.get("key") or mem.get("memory_key")
        v = mem.get("value") or mem.get("memory_value")
        if k and v:
            clean_k = str(k).replace("_", " ").strip().lower()
            dedup[clean_k] = str(v).strip()

    if not dedup:
        return ""

    lines = ["USER MEMORY (Account-level facts belonging only to the currently authenticated user):"]
    for clean_k, v in dedup.items():
        lines.append(f"- {clean_k.capitalize()}: {v}")

    lines.append("")
    lines.append("Memory Usage Instructions:")
    lines.append("- These memories belong only to the currently authenticated user.")
    lines.append("- Use them naturally and seamlessly when relevant.")
    lines.append("- Do not mention that they came from a database or memory table.")
    lines.append("- Do not repeat them unnecessarily if not relevant to the user's question.")
    lines.append("- If the current user explicitly corrects a memory, prefer the newest information.")
    lines.append("- Do not pretend to know personal information that is not listed here.")

    return "\n".join(lines)


# Pydantic Models
class HistoryItem(BaseModel):
    role: str
    content: str

    @field_validator("role")
    def validate_role(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in ("user", "assistant"):
            raise ValueError("Role must be 'user' or 'assistant'")
        return v_clean


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000, description="User message (max 4000 chars)")
    history: Optional[List[HistoryItem]] = Field(default_factory=list, description="Recent conversation history")
    memories: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="User personal memories")
    profile: Optional[str] = Field(default="default", description="Legacy chat profile (for backward compatibility)")


class ChatResponse(BaseModel):
    reply: str
    model: str
    profile: str


class ExtractMemoryRequest(BaseModel):
    message: str = Field(..., max_length=4000, description="User message to analyze for memory extraction")


class ExtractMemoryResponse(BaseModel):
    memories: List[Dict[str, Any]]
    forget_keys: Optional[List[str]] = []


class StartGenerationRequest(BaseModel):
    chat_id: str = Field(..., description="ID of the chat")
    message: str = Field(..., max_length=4000, description="User prompt text")
    history: Optional[List[HistoryItem]] = Field(default_factory=list, description="Recent conversation history")
    memories: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="User personal memories")


class StartGenerationResponse(BaseModel):
    generation_id: str
    chat_id: str
    status: str


class BackfillMemoryRequest(BaseModel):
    messages: List[str] = Field(..., max_length=100, description="List of historical user messages to extract memories from")


class BackfillMemoryResponse(BaseModel):
    memories: List[Dict[str, Any]]


# Exception Handlers
@app.exception_handler(OllamaConnectionError)
async def handle_connection_error(request: Request, exc: OllamaConnectionError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "error": "connection_error"}
    )


@app.exception_handler(OllamaModelNotFoundError)
async def handle_model_not_found(request: Request, exc: OllamaModelNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error": "model_not_found"}
    )


@app.exception_handler(OllamaResponseError)
async def handle_response_error(request: Request, exc: OllamaResponseError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc), "error": "model_error"}
    )


# 1. Health Check Endpoint
@app.get("/api/health")
async def health_check():
    health = await check_ollama_health()
    ollama_status = "online" if health.get("online") else "offline"
    
    return {
        "status": "ok",
        "service": "Jerryy's AI",
        "engine": "Ollama",
        "model": OLLAMA_MODEL,
        "ollama": ollama_status,
        "model_available": health.get("model_found", False)
    }


# 2. Chat Endpoint (Unified Mode + Cross-Chat Account Memory Injection)
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    t_req_start = time.perf_counter()
    logger.info("[PERF] request started")

    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    t_mem_start = time.perf_counter()
    # 1. Build unified system prompt
    system_content = UNIFIED_SYSTEM_PROMPT

    # 2. Filter memories strictly to current_user.id (Never trust unauthenticated user_id)
    safe_memories = []
    for m in (payload.memories or []):
        m_uid = m.get("user_id")
        if not m_uid or str(m_uid) == current_user.id:
            safe_memories.append(m)

    # 3. Inject account-level memory context block if available
    memory_context = build_memory_context(safe_memories)
    if memory_context:
        system_content += f"\n\n{memory_context}"

    mem_load_ms = (time.perf_counter() - t_mem_start) * 1000.0
    logger.info(f"[PERF] memory database load: {mem_load_ms:.2f} ms")

    # 4. Filter and validate history: limit to last 12
    valid_history = []
    if payload.history:
        for item in payload.history[-12:]:
            r = item.role.lower()
            if r in ("user", "assistant"):
                valid_history.append({"role": r, "content": item.content})

    # 5. Construct Ollama message sequence
    messages = [
        {"role": "system", "content": system_content},
        *valid_history,
        {"role": "user", "content": user_msg}
    ]

    # Memory extraction does not run inside chat request
    logger.info("[PERF] memory extraction Ollama call: 0.00 ms (non-blocking / decoupled from chat response)")

    # 6. Query Ollama
    t_ollama_start = time.perf_counter()
    reply = await chat_with_ollama(messages)
    ollama_gen_ms = (time.perf_counter() - t_ollama_start) * 1000.0
    logger.info(f"[PERF] main Ollama generation: {ollama_gen_ms:.2f} ms")

    # Database writes occur asynchronously client-side
    logger.info("[PERF] database writes: 0.00 ms (handled client-side asynchronously)")

    t_total_ms = (time.perf_counter() - t_req_start) * 1000.0
    logger.info(f"[PERF] total request: {t_total_ms:.2f} ms")
    logger.info("[PERF] Ollama calls for this chat request: 1")

    return {
        "reply": reply,
        "model": OLLAMA_MODEL,
        "profile": "unified"
    }


# 3. Streaming Chat Endpoint (Progressive plain-text response)
@app.post("/api/chat/stream")
async def chat_stream_endpoint(
    payload: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    t_req_start = time.perf_counter()
    logger.info("[PERF] streaming request started")

    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    t_mem_start = time.perf_counter()
    # 1. Build unified system prompt
    system_content = UNIFIED_SYSTEM_PROMPT

    # 2. Filter memories strictly to current_user.id (Never trust unauthenticated user_id)
    safe_memories = []
    for m in (payload.memories or []):
        m_uid = m.get("user_id")
        if not m_uid or str(m_uid) == current_user.id:
            safe_memories.append(m)

    # 3. Inject account-level memory context block if available
    memory_context = build_memory_context(safe_memories)
    if memory_context:
        system_content += f"\n\n{memory_context}"

    mem_load_ms = (time.perf_counter() - t_mem_start) * 1000.0
    logger.info(f"[PERF] memory database load: {mem_load_ms:.2f} ms")

    # 4. Filter and validate history: limit to last 12
    valid_history = []
    if payload.history:
        for item in payload.history[-12:]:
            r = item.role.lower()
            if r in ("user", "assistant"):
                valid_history.append({"role": r, "content": item.content})

    # 5. Construct Ollama message sequence
    messages = [
        {"role": "system", "content": system_content},
        *valid_history,
        {"role": "user", "content": user_msg}
    ]

    logger.info("[PERF] memory extraction Ollama call: 0.00 ms (non-blocking / decoupled from chat response)")

    # 6. Stream from Ollama
    chunk_iterator = await stream_chat_with_ollama(messages)

    return StreamingResponse(
        chunk_iterator,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no"
        }
    )


# -----------------------------------------------------------------------------
# 4. Decoupled Backend AI Generation Job System (Persistent across page reloads & chat switches)
# -----------------------------------------------------------------------------
async def insert_supabase_message(user_id: str, chat_id: str, role: str, content: str, token: Optional[str] = None):
    """
    Saves a single message row to Supabase messages table via PostgREST.
    Ensures user-scoped security and error resilience.
    """
    if not token or not SUPABASE_URL or token.startswith("test-token-"):
        return
    url = f"{SUPABASE_URL}/rest/v1/messages"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "role": role,
        "content": content
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"[DB] Inserted {role} message into Supabase for chat {chat_id}")
            else:
                logger.warning(f"[DB] Supabase insert {role} returned HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"[DB] Supabase insert message failed: {e}")


async def run_background_generation(
    generation_id: str,
    messages: list,
    user_id: str,
    chat_id: str,
    token: Optional[str]
):
    """
    Background worker task: streams from Ollama independently of frontend connection.
    Accumulates partial_content, handles Stop Generation, and saves complete response to Supabase once.
    """
    async with generation_manager.ollama_semaphore:
        job = generation_manager.get_job(generation_id, user_id=user_id)
        if not job or job.status != "generating":
            return

        logger.info(f"[JOB] Starting background Ollama streaming for generation {generation_id} in chat {chat_id}")
        t_start = time.perf_counter()
        try:
            chunk_iterator = await stream_chat_with_ollama(messages)
            async for chunk in chunk_iterator:
                # Check if job was stopped mid-stream
                job = generation_manager.get_job(generation_id, user_id=user_id)
                if not job or job.status != "generating":
                    logger.info(f"[JOB] Generation {generation_id} stopped mid-stream, breaking out")
                    break
                generation_manager.append_content(generation_id, chunk)

            # If generation completed normally (not stopped), finish and save to Supabase
            job = generation_manager.get_job(generation_id, user_id=user_id)
            if job and job.status == "generating":
                generation_manager.finish_job(generation_id, status="complete")
                if job.partial_content.strip():
                    await insert_supabase_message(user_id, chat_id, "assistant", job.partial_content, token)

            elapsed = (time.perf_counter() - t_start) * 1000.0
            logger.info(f"[JOB] Background generation {generation_id} completed in {elapsed:.2f} ms")

        except asyncio.CancelledError:
            logger.info(f"[JOB] Generation {generation_id} task cancelled")
            job = generation_manager.get_job(generation_id, user_id=user_id)
            if job and job.status == "generating":
                generation_manager.finish_job(generation_id, status="stopped")
                if job.partial_content.strip():
                    await insert_supabase_message(user_id, chat_id, "assistant", job.partial_content, token)
        except Exception as e:
            logger.error(f"[JOB] Generation {generation_id} failed: {e}")
            generation_manager.finish_job(generation_id, status="failed", error=str(e))


@app.post("/api/generations", response_model=StartGenerationResponse)
async def start_generation_endpoint(
    payload: StartGenerationRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    chat_id = payload.chat_id.strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="Chat ID cannot be empty.")

    # 1. Deduplication / Concurrency check: If already generating for this chat, return active job
    existing_job = generation_manager.get_active_job_for_chat(chat_id, current_user.id)
    if existing_job:
        logger.info(f"[JOB] Reusing active generation {existing_job.id} for chat {chat_id}")
        return {
            "generation_id": existing_job.id,
            "chat_id": chat_id,
            "status": existing_job.status
        }

    # Extract Bearer token for Supabase operations
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Save user message to Supabase asynchronously (non-blocking)
    if token:
        asyncio.create_task(insert_supabase_message(current_user.id, chat_id, "user", user_msg, token))

    # 3. Build unified system prompt with strictly filtered account memories
    system_content = UNIFIED_SYSTEM_PROMPT
    safe_memories = []
    for m in (payload.memories or []):
        m_uid = m.get("user_id")
        if not m_uid or str(m_uid) == current_user.id:
            safe_memories.append(m)

    memory_context = build_memory_context(safe_memories)
    if memory_context:
        system_content += f"\n\n{memory_context}"

    # 4. Filter history (last 12)
    valid_history = []
    if payload.history:
        for item in payload.history[-12:]:
            r = item.role.lower()
            if r in ("user", "assistant"):
                valid_history.append({"role": r, "content": item.content})

    # 5. Construct Ollama message sequence
    messages = [
        {"role": "system", "content": system_content},
        *valid_history,
        {"role": "user", "content": user_msg}
    ]

    # 6. Create Generation Job
    job = await generation_manager.create_job(current_user.id, chat_id, user_msg)

    # 7. Start background streaming task
    task = asyncio.create_task(
        run_background_generation(job.id, messages, current_user.id, chat_id, token)
    )
    job.asyncio_task = task

    return {
        "generation_id": job.id,
        "chat_id": chat_id,
        "status": job.status
    }


@app.get("/api/generations/{generation_id}")
async def get_generation_status_endpoint(
    generation_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    job = generation_manager.get_job(generation_id, user_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found or access denied.")

    return job.to_dict()


@app.get("/api/chats/{chat_id}/active-generation")
async def get_active_chat_generation_endpoint(
    chat_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    job = generation_manager.get_active_job_for_chat(chat_id, current_user.id)
    if not job:
        return {"active": False, "has_active": False}

    return {
        "active": True,
        "has_active": True,
        **job.to_dict()
    }


@app.post("/api/generations/{generation_id}/stop")
async def stop_generation_endpoint(
    generation_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    job = generation_manager.get_job(generation_id, user_id=current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found or access denied.")

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    was_cancelled, stopped_job = generation_manager.cancel_job(generation_id, current_user.id)
    if stopped_job and stopped_job.partial_content.strip():
        # Save partial content to Supabase once as assistant response
        await insert_supabase_message(current_user.id, stopped_job.chat_id, "assistant", stopped_job.partial_content, token)

    return {
        "generation_id": generation_id,
        "status": "stopped",
        "content": stopped_job.partial_content if stopped_job else ""
    }


# 4. Memory Extraction Endpoint (Runs in background, non-blocking for chat)
@app.post("/api/extract-memories", response_model=ExtractMemoryResponse)
async def extract_memories_endpoint(
    payload: ExtractMemoryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    t_start = time.perf_counter()
    logger.info("[PERF] Background memory extraction endpoint invoked")
    result = await extract_memories_with_ollama(payload.message)
    t_ms = (time.perf_counter() - t_start) * 1000.0
    logger.info(f"[PERF] memory extraction call completed: {t_ms:.2f} ms")
    return result


# 4. Batch Memory Backfill Endpoint (One-time extraction across past user messages)
@app.post("/api/backfill-memories", response_model=BackfillMemoryResponse)
async def backfill_memories_endpoint(
    payload: BackfillMemoryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    t_start = time.perf_counter()
    logger.info("[PERF] Batch memory backfill endpoint invoked")
    result = await extract_batch_memories_with_ollama(payload.messages)
    t_ms = (time.perf_counter() - t_start) * 1000.0
    logger.info(f"[PERF] backfill call completed: {t_ms:.2f} ms")
    return result



# Static Frontend Routing
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/")
async def serve_root():
    # Priority: frontend/index.html, then root index.html
    fe_index = FRONTEND_DIR / "index.html"
    if fe_index.exists() and fe_index.is_file():
        return FileResponse(fe_index)
    root_index = BASE_DIR / "index.html"
    if root_index.exists() and root_index.is_file():
        return FileResponse(root_index)
    raise HTTPException(status_code=404, detail="index.html not found")


@app.get("/chat")
async def serve_chat():
    fe_chat = FRONTEND_DIR / "chat.html"
    if fe_chat.exists() and fe_chat.is_file():
        return FileResponse(fe_chat)
    root_chat = BASE_DIR / "chat.html"
    if root_chat.exists() and root_chat.is_file():
        return FileResponse(root_chat)
    raise HTTPException(status_code=404, detail="chat.html not found")


@app.get("/{filename}.html")
async def serve_html_file(filename: str):
    fe_file = FRONTEND_DIR / f"{filename}.html"
    if fe_file.exists() and fe_file.is_file():
        return FileResponse(fe_file)
    root_file = BASE_DIR / f"{filename}.html"
    if root_file.exists() and root_file.is_file():
        return FileResponse(root_file)
    raise HTTPException(status_code=404, detail=f"{filename}.html not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
