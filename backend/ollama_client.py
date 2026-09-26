"""Local-only Ollama; cancellation always closes the corresponding HTTP stream."""
import asyncio,json,logging,re,time
from typing import Dict,Any
import httpx
from config import OLLAMA_URL,OLLAMA_MODEL,OLLAMA_TIMEOUT,KEEP_ALIVE
TIMEOUT_SECONDS=OLLAMA_TIMEOUT
OLLAMA_KEEP_ALIVE=KEEP_ALIVE
_OLLAMA_CALL_COUNT=0
logger=logging.getLogger('jerryys_ai.ollama')
class OllamaConnectionError(Exception):pass
class OllamaResponseError(Exception):pass
class OllamaModelNotFoundError(Exception):pass
async def model_capabilities():
    try:
        async with httpx.AsyncClient(timeout=5,trust_env=False) as c:r=await c.post(OLLAMA_URL+'/api/show',json={'model':OLLAMA_MODEL})
        if r.status_code==404:return {'online':True,'model_found':False,'vision':False}
        if r.status_code!=200:raise ValueError()
        caps=r.json().get('capabilities')
        return {'online':True,'model_found':True,'vision':('vision' in caps) if isinstance(caps,list) else None}
    except (httpx.HTTPError,ValueError):return {'online':False,'model_found':False,'vision':None}
async def check_ollama_health():return await model_capabilities()
def payload(messages,stream=True):return {'model':OLLAMA_MODEL,'messages':messages,'stream':stream,'think':False,'keep_alive':KEEP_ALIVE,'options':{'num_ctx':8192,'num_predict':2048}}
async def warmup_ollama():
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT,trust_env=False) as c:r=await c.post(OLLAMA_URL+'/api/chat',json=payload([{'role':'user','content':'Reply only with: OK'}],False))
        logger.info('warmup_status=%s',r.status_code)
    except httpx.HTTPError:logger.warning('warmup_unavailable')
async def stream_chat_with_ollama(messages):
    try:
        async with asyncio.timeout(OLLAMA_TIMEOUT):
            async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT,connect=10),trust_env=False) as c:
                async with c.stream('POST',OLLAMA_URL+'/api/chat',json=payload(messages)) as r:
                    if r.status_code==404:raise OllamaModelNotFoundError('The configured local model is not installed.')
                    if r.status_code!=200:raise OllamaResponseError('The local model could not process this request.')
                    done=False
                    async for line in r.aiter_lines():
                        if not line:continue
                        try:part=json.loads(line)
                        except ValueError:raise OllamaResponseError('Invalid response from the local model.')
                        if part.get('error'):raise OllamaResponseError('The local model reported an error. Try a shorter request.')
                        text=part.get('message',{}).get('content','')
                        if text:yield text
                        if part.get('done'):done=True
                    if not done:raise OllamaResponseError('The connection ended before the answer completed. Use Retry.')
    except (httpx.TimeoutException,TimeoutError):raise OllamaResponseError('The local model timed out. Use Retry.')
    except httpx.HTTPError:raise OllamaConnectionError('Ollama is unavailable. Start Ollama, then use Retry.')
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
        logger.info("memory_forget_ms=%.1f",t_elapsed)
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
        async with httpx.AsyncClient(trust_env=False,timeout=25.0) as client:
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
        logger.warning("memory_extraction_unavailable")
        return {"memories": [], "forget_keys": []}


