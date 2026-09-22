"""
Ollama Client for Jerryy's AI
Handles asynchronous communication with local Ollama instance.
"""

import os
import time
import logging
import re
import json
from typing import List, Dict, Any, Optional
import httpx
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("jerryys_ai.ollama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "jerryys-ai")
TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT", "600.0"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

_OLLAMA_CALL_COUNT = 0

def get_ollama_call_count() -> int:
    return _OLLAMA_CALL_COUNT

def reset_ollama_call_count():
    global _OLLAMA_CALL_COUNT
    _OLLAMA_CALL_COUNT = 0


class OllamaConnectionError(Exception):
    """Raised when cannot connect to local Ollama server."""
    pass


class OllamaModelNotFoundError(Exception):
    """Raised when the specified model is not available in Ollama."""
    pass


class OllamaResponseError(Exception):
    """Raised when Ollama returns an invalid or empty response."""
    pass


async def check_ollama_health() -> Dict[str, Any]:
    """
    Checks if Ollama is running and verifies model availability.
    Returns status dict with connectivity and model presence.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check for either 'jerryys-ai', 'jerryys-ai:latest', or matching model name
                model_found = any(
                    OLLAMA_MODEL == m or m.startswith(f"{OLLAMA_MODEL}:") or m == f"{OLLAMA_MODEL}:latest"
                    for m in models
                )
                return {
                    "online": True,
                    "model_found": model_found,
                    "available_models": models
                }
            return {
                "online": False,
                "model_found": False,
                "error": f"Ollama HTTP {resp.status_code}"
            }
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
        return {
            "online": False,
            "model_found": False,
            "error": str(e)
        }


async def chat_with_ollama(messages: List[Dict[str, str]]) -> str:
    """
    Sends conversation messages to Ollama /api/chat endpoint.
    - model: jerryys-ai
    - stream: false
    - think: false (never expose internal reasoning)
    - keep_alive: 30m
    - timeout: 180s (local CPU execution)
    """
    global _OLLAMA_CALL_COUNT
    _OLLAMA_CALL_COUNT += 1
    call_num = _OLLAMA_CALL_COUNT

    t_start = time.perf_counter()
    logger.info(f"[PERF] Ollama call #{call_num} started: main chat")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE
    }

    url = f"{OLLAMA_URL}/api/chat"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to Ollama at {url}: {e}")
        raise OllamaConnectionError(
            "Jerryy's AI could not connect to the local model. Make sure Ollama is running."
        ) from e
    except httpx.TimeoutException as e:
        logger.error(f"Ollama request timed out after {TIMEOUT_SECONDS}s: {e}")
        raise OllamaResponseError(
            "The model response timed out. Please try again with a shorter prompt."
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error communicating with Ollama: {e}")
        raise OllamaConnectionError(
            f"Error communicating with local Ollama: {e}"
        ) from e

    t_elapsed = (time.perf_counter() - t_start) * 1000.0
    logger.info(f"[PERF] Ollama call #{call_num} completed in {t_elapsed:.2f} ms")

    if response.status_code == 404:
        logger.error(f"Model '{OLLAMA_MODEL}' not found in Ollama.")
        raise OllamaModelNotFoundError(
            f"The {OLLAMA_MODEL} model is not available in Ollama."
        )

    if response.status_code != 200:
        logger.error(f"Ollama returned HTTP {response.status_code}: {response.text}")
        raise OllamaResponseError(
            f"Ollama returned error status {response.status_code}."
        )

    try:
        data = response.json()
    except Exception as e:
        logger.error(f"Failed to parse Ollama JSON response: {e}")
        raise OllamaResponseError("Invalid JSON received from Ollama.") from e

    # Extract message content
    message_obj = data.get("message", {})
    content = message_obj.get("content", "")

    if not content or not content.strip():
        logger.warning("Ollama returned an empty response content.")
        raise OllamaResponseError("The model returned an empty response.")

    return content.strip()


async def stream_chat_with_ollama(messages: List[Dict[str, str]]):
    """
    Streams conversation messages from Ollama /api/chat endpoint.
    - model: jerryys-ai
    - stream: true
    - think: false (never expose internal reasoning)
    - keep_alive: 30m
    - timeout: 600s
    Yields plain-text token content chunks progressively as generated.
    """
    global _OLLAMA_CALL_COUNT
    _OLLAMA_CALL_COUNT += 1
    call_num = _OLLAMA_CALL_COUNT

    t_start = time.perf_counter()
    logger.info(f"[PERF] Ollama call #{call_num} started: streaming chat")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE
    }

    url = f"{OLLAMA_URL}/api/chat"

    client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        req = client.build_request("POST", url, json=payload)
        response = await client.send(req, stream=True)
    except httpx.ConnectError as e:
        await client.aclose()
        logger.error(f"Cannot connect to Ollama at {url}: {e}")
        raise OllamaConnectionError(
            "Jerryy's AI could not connect to the local model. Make sure Ollama is running."
        ) from e
    except httpx.TimeoutException as e:
        await client.aclose()
        logger.error(f"Ollama request timed out after {TIMEOUT_SECONDS}s: {e}")
        raise OllamaResponseError(
            "The model response timed out. Please try again with a shorter prompt."
        ) from e
    except Exception as e:
        await client.aclose()
        logger.error(f"Unexpected error communicating with Ollama: {e}")
        raise OllamaConnectionError(
            f"Error communicating with local Ollama: {e}"
        ) from e

    if response.status_code == 404:
        await response.aclose()
        await client.aclose()
        logger.error(f"Model '{OLLAMA_MODEL}' not found in Ollama.")
        raise OllamaModelNotFoundError(
            f"The {OLLAMA_MODEL} model is not available in Ollama."
        )

    if response.status_code != 200:
        err_bytes = await response.aread()
        await response.aclose()
        await client.aclose()
        logger.error(f"Ollama returned HTTP {response.status_code}: {err_bytes.decode('utf-8', 'ignore')}")
        raise OllamaResponseError(
            f"Ollama returned error status {response.status_code}."
        )

    async def chunk_generator():
        try:
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    msg_obj = chunk.get("message", {})
                    content = msg_obj.get("content", "")
                    if content:
                        yield content
                except Exception:
                    continue
        finally:
            await response.aclose()
            await client.aclose()
            t_elapsed = (time.perf_counter() - t_start) * 1000.0
            logger.info(f"[PERF] Ollama call #{call_num} (streaming chat) finalized in {t_elapsed:.2f} ms")

    return chunk_generator()


async def extract_memories_with_ollama(user_message: str) -> Dict[str, Any]:
    """
    Extracts stable, long-term personal facts from the user's latest message.
    Uses fast deterministic extraction for common patterns (name, education, location)
    and conversational forget intents in 0ms without invoking Ollama.
    Skips Ollama entirely if message has no personal self-referential cues.
    """
    t_start = time.perf_counter()

    clean_msg = (user_message or "").strip()
    if not clean_msg:
        return {"memories": [], "forget_keys": []}

    # 1. Fast regex detection for conversational 'forget' commands (0ms)
    forget_patterns = [
        r"(?:please\s+)?(?:forget|don'?t\s+remember|stop\s+remembering|remove|delete)\s+(?:my\s+)?([a-zA-Z0-9_'’\s]{2,40})",
        r"(?:clear|erase)\s+(?:my\s+)?([a-zA-Z0-9_'’\s]{2,40})\s+memory"
    ]
    detected_forget_keys = []
    for pat in forget_patterns:
        match = re.search(pat, clean_msg, re.IGNORECASE)
        if match:
            raw_target = match.group(1).strip().lower()
            clean_target = re.sub(r"['’]s\b|['’]", "", raw_target).strip()
            clean_target = re.sub(r"\s+", "_", clean_target)
            if clean_target and clean_target not in ("everything", "all", "memory"):
                detected_forget_keys.append(clean_target)
            elif clean_target in ("everything", "all"):
                detected_forget_keys.append("__all__")

    if detected_forget_keys:
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        logger.info(f"[PERF] Conversational forget intent handled deterministically in {t_elapsed:.2f} ms: {detected_forget_keys}")
        return {"memories": [], "forget_keys": detected_forget_keys}

    # 2. Check if message contains ANY personal self-referential cues
    has_personal_cues = bool(re.search(
        r"\b(i am|i'm|my|i live|i study|i work|i like|i love|i prefer|i have|call me|remember that|forget)\b",
        clean_msg,
        re.IGNORECASE
    ))
    if not has_personal_cues:
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        logger.info(f"[PERF] Memory extraction skipped in {t_elapsed:.2f} ms: no personal memory cues detected")
        return {"memories": [], "forget_keys": []}

    # 3. Deterministic extraction for standard personal statements (0ms)
    deterministic_memories = []
    name_m = re.search(r"(?:my name is|my name's|call me)\s+([A-Za-z0-9_]{2,30})", clean_msg, re.IGNORECASE)
    if name_m:
        raw_name = name_m.group(1).strip()
        if raw_name.lower() not in ("a", "an", "the", "not", "here", "what", "who"):
            deterministic_memories.append({"key": "name", "value": raw_name.capitalize(), "category": "personal"})

    year_m = re.search(r"(?:i study in|i'm studying in|i study|i am in|i'm in)\s+((?:first|second|third|fourth|final|1st|2nd|3rd|4th|\d+(?:st|nd|rd|th)?)\s+year)", clean_msg, re.IGNORECASE)
    if year_m:
        raw_yr = year_m.group(1).strip()
        deterministic_memories.append({"key": "study_year", "value": raw_yr.capitalize(), "category": "education"})

    loc_m = re.search(r"(?:i live in|i'm from|i am from|my hometown is|my address is)\s+([A-Za-z0-9\s]{2,40})", clean_msg, re.IGNORECASE)
    if loc_m:
        raw_loc = loc_m.group(1).strip().rstrip(".,")
        if raw_loc.lower() not in ("here", "there", "fear", "pain"):
            deterministic_memories.append({"key": "location", "value": raw_loc.capitalize(), "category": "location"})

    if deterministic_memories:
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        logger.info(f"[PERF] Memory extraction handled deterministically ({len(deterministic_memories)} facts) in {t_elapsed:.2f} ms, skipping Ollama call")
        return {"memories": deterministic_memories, "forget_keys": []}

    # 4. Fallback to Ollama for complex, nuanced facts only
    global _OLLAMA_CALL_COUNT
    _OLLAMA_CALL_COUNT += 1
    call_num = _OLLAMA_CALL_COUNT
    logger.info(f"[PERF] Ollama call #{call_num} started: complex memory extraction")

    system_instruction = (
        "You are a memory extraction component for a personal AI assistant.\n"
        "Analyze ONLY the user's latest message.\n"
        "Extract stable, long-term personal facts that would genuinely help future conversations, such as:\n"
        "- user's preferred name\n"
        "- education / class / year / course / college\n"
        "- occupation / career goals\n"
        "- family or relationship information voluntarily given\n"
        "- address / location / city\n"
        "- important long-term preferences\n\n"
        "Do NOT store:\n"
        "- ordinary questions or queries\n"
        "- temporary calculations or tasks\n"
        "- one-time examples or conversation topics\n"
        "- opinions or fleeting feelings\n\n"
        "Return STRICT JSON only, with no markdown fences, matching this schema:\n"
        "{\n"
        '  "memories": [\n'
        '    {"key": "name", "value": "Kannan", "category": "personal"}\n'
        "  ]\n"
        "}\n"
        "If there is nothing worth remembering:\n"
        '{"memories": []}'
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": clean_msg}
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0.1
        },
        "keep_alive": OLLAMA_KEEP_ALIVE
    }

    url = f"{OLLAMA_URL}/api/chat"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(url, json=payload)

        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        logger.info(f"[PERF] Ollama call #{call_num} (complex memory extraction) completed in {t_elapsed:.2f} ms")

        if response.status_code != 200:
            logger.warning(f"Ollama memory extraction returned status {response.status_code}")
            return {"memories": [], "forget_keys": []}

        data = response.json()
        raw_content = data.get("message", {}).get("content", "").strip()

        # Parse JSON content
        parsed = json.loads(raw_content)
        raw_memories = parsed.get("memories", [])
        if not isinstance(raw_memories, list):
            return {"memories": [], "forget_keys": []}

        valid_memories = []
        for item in raw_memories:
            if not isinstance(item, dict):
                continue
            k = str(item.get("key", "")).strip().lower()
            v = str(item.get("value", "")).strip()
            cat = str(item.get("category", "general")).strip().lower()

            # Clean and normalize key
            k_clean = re.sub(r"[^\w\s-]", "", k).replace("-", "_").replace(" ", "_").strip("_")
            if k_clean and v and len(k_clean) <= 50 and len(v) <= 500:
                valid_memories.append({
                    "key": k_clean,
                    "value": v,
                    "category": cat or "general"
                })

        return {"memories": valid_memories, "forget_keys": []}

    except Exception as err:
        logger.warning(f"Memory extraction skipped or failed: {err}")
        return {"memories": [], "forget_keys": []}


async def extract_batch_memories_with_ollama(user_messages: List[str]) -> Dict[str, Any]:
    """
    Extracts stable, long-term personal facts from a list of historical user messages.
    Used for safe, one-time backfilling of existing conversations for an authenticated user.
    """
    import json
    import re

    clean_msgs = [m.strip() for m in user_messages if m and m.strip()]
    if not clean_msgs:
        return {"memories": []}

    # Format historical user messages into bullet points
    formatted_messages = "\n".join(f"- {msg}" for msg in clean_msgs[:40])

    system_instruction = (
        "You are a memory backfill extraction component for a personal learning assistant.\n"
        "Analyze the following list of historical messages sent by ONE user across previous chats.\n"
        "Extract stable, long-term personal facts that should be remembered, such as:\n"
        "- user's preferred name (key: 'name')\n"
        "- education / study year / class / course / college (key: 'education' or 'study_year')\n"
        "- location / city / address (key: 'location' or 'address')\n"
        "- favorite programming language / skills (key: 'favorite_language')\n"
        "- occupation / career goals\n"
        "- family or voluntary relationship info\n\n"
        "If multiple messages state the same fact, keep the newest or clearest one.\n"
        "Do NOT store questions, quiz answers, calculations, or greetings.\n\n"
        "Return STRICT JSON only, matching this schema:\n"
        "{\n"
        '  "memories": [\n'
        '    {"key": "name", "value": "Nobody", "category": "personal"},\n'
        '    {"key": "study_year", "value": "Second year", "category": "education"}\n'
        "  ]\n"
        "}\n"
        "If nothing worth remembering exists:\n"
        '{"memories": []}'
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Here are the user's past messages:\n{formatted_messages}"}
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0.1
        },
        "keep_alive": OLLAMA_KEEP_ALIVE
    }

    url = f"{OLLAMA_URL}/api/chat"

    global _OLLAMA_CALL_COUNT
    _OLLAMA_CALL_COUNT += 1
    call_num = _OLLAMA_CALL_COUNT

    t_start = time.perf_counter()
    logger.info(f"[PERF] Ollama call #{call_num} started: batch memory backfill")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)

        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        logger.info(f"[PERF] Ollama call #{call_num} (batch memory backfill) completed in {t_elapsed:.2f} ms")

        if response.status_code != 200:
            logger.warning(f"Ollama batch memory extraction returned status {response.status_code}")
            return {"memories": []}

        data = response.json()
        raw_content = data.get("message", {}).get("content", "").strip()

        parsed = json.loads(raw_content)
        raw_memories = parsed.get("memories", [])
        if not isinstance(raw_memories, list):
            return {"memories": []}

        valid_memories = []
        for item in raw_memories:
            if not isinstance(item, dict):
                continue
            k = str(item.get("key", "")).strip().lower()
            v = str(item.get("value", "")).strip()
            cat = str(item.get("category", "general")).strip().lower()

            k_clean = re.sub(r"[^\w\s-]", "", k).replace("-", "_").replace(" ", "_").strip("_")
            if k_clean and v and len(k_clean) <= 50 and len(v) <= 500:
                valid_memories.append({
                    "key": k_clean,
                    "value": v,
                    "category": cat or "general"
                })

        return {"memories": valid_memories}

    except Exception as err:
        logger.warning(f"Batch memory extraction skipped or failed: {err}")
        return {"memories": []}


