"""
Ollama Client for Jerryy's AI
Handles asynchronous communication with local Ollama instance.
"""

import os
import logging
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
    - timeout: 180s (local CPU execution)
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False
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


async def extract_memories_with_ollama(user_message: str) -> Dict[str, Any]:
    """
    Extracts stable, long-term personal facts from the user's latest message using local Ollama.
    Also identifies explicit 'forget' requests (e.g., 'Forget my address').
    Executes with low temperature (0.1) and strict JSON format.
    Never throws unhandled exceptions; returns empty memory structure on any failure.
    """
    import json
    import re

    clean_msg = (user_message or "").strip()
    if not clean_msg:
        return {"memories": [], "forget_keys": []}

    # 1. Fast regex detection for conversational 'forget' commands
    forget_patterns = [
        r"(?:please\s+)?(?:forget|don'?t\s+remember|stop\s+remembering|remove|delete)\s+(?:my\s+)?([a-zA-Z0-9_'’\s]{2,40})",
        r"(?:clear|erase)\s+(?:my\s+)?([a-zA-Z0-9_'’\s]{2,40})\s+memory"
    ]
    detected_forget_keys = []
    for pat in forget_patterns:
        match = re.search(pat, clean_msg, re.IGNORECASE)
        if match:
            raw_target = match.group(1).strip().lower()
            # Normalize target key e.g. "girlfriend's name" -> "girlfriend_name" without stripping words ending in 's'
            clean_target = re.sub(r"['’]s\b|['’]", "", raw_target).strip()
            clean_target = re.sub(r"\s+", "_", clean_target)
            if clean_target and clean_target not in ("everything", "all", "memory"):
                detected_forget_keys.append(clean_target)
            elif clean_target in ("everything", "all"):
                detected_forget_keys.append("__all__")

    if detected_forget_keys:
        logger.info(f"Detected conversational forget intent for keys: {detected_forget_keys}")
        return {"memories": [], "forget_keys": detected_forget_keys}

    # 2. Extract stable personal facts with Ollama
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
        }
    }

    url = f"{OLLAMA_URL}/api/chat"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(url, json=payload)

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

