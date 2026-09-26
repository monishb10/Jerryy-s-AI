import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(env_path, override=True)

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'jerryys-ai')
OLLAMA_TIMEOUT = float(os.getenv('OLLAMA_TIMEOUT', '600'))
KEEP_ALIVE = os.getenv('OLLAMA_KEEP_ALIVE', '30m')
MAX_FILE_BYTES = 10485760
MAX_TEXT_CHARS = 12000
MAX_CONTEXT_CHARS = 18000
BUCKET = 'chat-attachments'
