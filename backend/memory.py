import re
from ollama_client import extract_memories_with_ollama

COMMON_WORDS = {
    'a', 'an', 'the', 'not', 'here', 'there', 'fine', 'good', 'happy', 'sad',
    'sorry', 'busy', 'ready', 'tired', 'sick', 'just', 'asking', 'wondering',
    'testing', 'trying', 'back', 'going', 'doing', 'looking', 'learning',
    'saying', 'telling', 'thinking', 'helping'
}

def clean_name_value(val):
    if not val:
        return None
    val = val.strip().strip('"\'')
    # strip trailing punctuation
    val = re.sub(r'[\s.,!?;:]+$', '', val)
    # strip trailing conversational phrases
    val = re.sub(
        r'(?i)\s+(?:please|ok|okay|now|thanks|thank you|remember it|save it|got it|bro|dude)$',
        '',
        val
    )
    val = val.strip()
    if not val or len(val) > 40:
        return None
    lower = val.lower()
    # Reject assistant identity or generic non-names (allow 'nobodyy' with double-y as test user name)
    if lower in ('jerryy', "jerryy's ai", "jerryys ai", "jerryy's", 'assistant', 'ai', 'bot', 'nobody', 'someone', 'what', 'who', 'unknown'):
        if lower != 'nobodyy':
            return None
    if lower.startswith('not '):
        return None
    # Capitalize if all lowercase
    if val.islower():
        val = val.capitalize()
    return val

NAME_PATTERNS = [
    # "remember (that) my name is X", "save my name as X", "please save my name as X", "just save my name as X"
    r"(?i)\b(?:please\s+|just\s+)?(?:remember\s+(?:that\s+)?|save\s+)(?:my\s+name\s+(?:is|as)\s+)([\w'\- ]+)",
    # "actually my name is X", "my name is actually X"
    r"(?i)\b(?:actually,?\s+my\s+name\s+is|my\s+name\s+is\s+actually)\s+([\w'\- ]+)",
    # "my name is X", "my name's X"
    r"(?i)\bmy\s+name(?:'s|\s+is)\s+([\w'\- ]+)",
    # "you can call me X", "call me X"
    r"(?i)\b(?:you\s+can\s+)?call\s+me\s+([\w'\- ]+)",
    # "I'm X", "I am X"
    r"(?i)\b(?:i'm|i\s+am)\s+([A-Za-z][\w'\- ]+)",
]

def extract_user_name(text):
    clean = text.strip()
    # If the text is a question asking about identity, skip
    if re.search(r"(?i)\b(?:what|who|is|do you know|tell me)\b.*\b(?:name|who am i)\b", clean):
        return None
    for pat in NAME_PATTERNS:
        m = re.search(pat, clean)
        if m:
            raw = m.group(1).split('\n')[0]
            cand = clean_name_value(raw)
            if cand:
                first_word = cand.lower().split()[0]
                if pat == NAME_PATTERNS[-1] and first_word in COMMON_WORDS:
                    continue
                return cand
    return None

def instant_memories(text):
    facts = []
    # 1. Deterministic Name Extraction
    name = extract_user_name(text)
    if name:
        facts.append({'key': 'user_name', 'value': name, 'category': 'personal'})

    # 2. Other deterministic personal facts
    other_patterns = [
        ('education', r"(?:i study|i am studying|i'm studying|my branch is|my major is|my course is)\s+([^.!?\n]{2,100})", 'education'),
        ('college', r"(?:my college is|i study at|i attend)\s+([^.!?\n]{3,100})", 'education'),
        ('location', r"(?:i live in|i'm from|i am from|my hometown is|i reside in)\s+([^.!?\n]{2,80})", 'location'),
        ('favorite_language', r"my favorite (?:programming )?language is\s+([^.!?\n]{2,50})", 'skills'),
        ('favorite_color', r"my favorite colou?r is\s+([^.!?\n]{2,30})", 'personal'),
        ('girlfriend_name', r"my girlfriend(?:'s name)? is\s+([^.!?\n]{2,50})", 'personal'),
        ('address', r"my address is\s+([^.!?\n]{2,100})", 'location')
    ]
    for key, pat, category in other_patterns:
        m = re.search(pat, text, re.I)
        if m:
            val = m.group(1).strip().rstrip('.,!?')
            if val and len(val) <= 100:
                facts.append({'key': key, 'value': val, 'category': category})
    return facts

def forget_intent(text):
    clean = text.strip().lower().rstrip('.!?')
    if re.fullmatch(r'(?:please )?(?:forget|clear|erase|delete) (?:everything|all|all memories|my memory|my memories)(?: about me)?', clean):
        return ['__all__']
    m = re.fullmatch(r"(?:please )?(?:forget|don't remember|stop remembering|remove|delete|clear|erase) (?:my )?([\w '’]{2,50})", clean)
    if m:
        key = re.sub(r"['’]s\b|['’]", '', m.group(1)).replace(' ', '_')
        if key in ('name', 'user_name'):
            return ['user_name', 'name']
        return [key] if key not in ('it', 'this', 'that') else []
    return []

def should_skip_llm_extraction(text):
    clean = text.strip()
    if len(clean) < 8:
        return True
    # Questions about identity, assistant, or general knowledge
    if re.search(r"(?i)\b(?:what|who|where|when|why|how|is|are|can|could|do|does|will|would)\b.*\?", clean):
        return True
    if re.search(r"(?i)\b(?:what is my name|who am i|tell me my name|do you know my name|what is your name|who are you)\b", clean):
        return True
    # Pure conversational greetings
    if re.fullmatch(r"(?i)(?:hi|hello|hey|good morning|good evening|good afternoon|howdy|sup|yo)[.!? ]*", clean):
        return True
    return False

async def process_memory(db, uid, message):
    if message.get('memory_processed'):
        return
    text = message.get('content', '')
    forget = forget_intent(text)
    facts = [] if forget else instant_memories(text)

    # If user_name is being set, delete any legacy 'name' key
    if any(f.get('key') == 'user_name' for f in facts):
        if 'name' not in forget:
            forget.append('name')

    # LLM extraction only as fallback for complex non-trivial messages
    if not facts and not forget and not should_skip_llm_extraction(text):
        try:
            result = await extract_memories_with_ollama(text)
            extracted = result.get('memories', [])
            forget = result.get('forget_keys', [])
            for item in extracted:
                k = item.get('key')
                v = item.get('value')
                if not k or not v:
                    continue
                # Normalize 'name' to 'user_name'
                if k in ('name', 'user_name'):
                    clean_v = clean_name_value(str(v))
                    if clean_v:
                        facts.append({'key': 'user_name', 'value': clean_v, 'category': 'personal'})
                        if 'name' not in forget:
                            forget.append('name')
                else:
                    facts.append(item)
        except Exception:
            pass

    facts = [f for f in facts if 0 < len(str(f.get('key', ''))) <= 50 and 0 < len(str(f.get('value', ''))) <= 500][:12]
    await db.rpc(
        'memory_apply',
        p_user=uid,
        p_message=message['id'],
        p_revision=message['revision'],
        p_memories=facts,
        p_forget=forget
    )
