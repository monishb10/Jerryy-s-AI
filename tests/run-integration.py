"""Start local test doubles and the real app together; always stop child servers."""
import os,subprocess,sys,socket,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower()};env.update(SUPABASE_URL='http://127.0.0.1:8766',SUPABASE_KEY='fixture-public',SUPABASE_SERVICE_ROLE_KEY='fixture-service',OLLAMA_URL='http://127.0.0.1:8766',OLLAMA_MODEL='jerryys-ai',JAI_INTEGRATION='1');processes=[]
def ready(port):
 for _ in range(150):
  try:
   with socket.create_connection(('127.0.0.1',port),.2):return
  except OSError:time.sleep(.1)
 raise RuntimeError('Test server failed to start')
try:
 with (root/'tests/server.log').open('w') as log:
  processes.append(subprocess.Popen(['node','tests/fixture.mjs'],cwd=root,env=env,stdout=log,stderr=log));ready(8766)
  processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--app-dir','backend','--host','127.0.0.1','--port','8765','--no-access-log'],cwd=root,env=env,stdout=log,stderr=log));ready(8765)
  command=['node','tests/browser.test.mjs'] if '--browser' in sys.argv else [sys.executable,'-m','pytest','-q','backend/tests']
  result=subprocess.run(command,cwd=root,env=env,timeout=240);sys.exit(result.returncode)
finally:
 for p in reversed(processes):p.terminate()
 for p in reversed(processes):
  try:p.wait(8)
  except subprocess.TimeoutExpired:p.kill();p.wait()
