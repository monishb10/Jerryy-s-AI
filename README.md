# Jerryy's AI

General-purpose local AI chat using the supplied custom HTML/CSS/JavaScript design, FastAPI, Supabase Google authentication/PostgreSQL/private Storage, and Ollama `jerryys-ai` based on `qwen3.5:4b`. No cloud AI API is used.

## Required setup

Use Python **3.11 or newer**. Run the frontend through FastAPI, not `file://` or a separate static server.

**RUN THIS FILE IN SUPABASE SQL EDITOR:**

`supabase/SETUP.sql`

This is the consolidated, transactional setup for new or existing installations of the supplied schema. It includes the original tables and the new `20260924_functional_chat.sql` migration. It does not delete existing chat history. The SQL has **not** been applied to your live Supabase project. Do not run the old standalone schema after this setup: its older policies allow direct client mutations.

The setup creates the **private** `chat-attachments` bucket with a 10 MB limit, owner-only read policies, attachment metadata, cascades, cleanup outbox, job queue and service-only transactional functions. Check Storage → `chat-attachments` → Settings: Public must be OFF. Do not add public access policies. No separate bucket creation is needed if the complete SQL succeeds. Existing incompatible/duplicate data can cause a transaction to roll back; inspect and resolve such data before retrying, without deleting history indiscriminately.

In your existing Supabase project:

1. Enable Google in Authentication → Providers, using your existing Google OAuth client.
2. Configure the Google OAuth redirect URI with your Supabase Auth callback (`https://YOUR-PROJECT.supabase.co/auth/v1/callback`).
3. Set Supabase Authentication → URL Configuration Site URL and allowed redirect URLs to your frontend origin, such as `http://localhost:8000` and `http://localhost:8000/`. Add the HTTPS origin when deployed.
4. Put your project URL, publishable/anon key, and **server-only service-role key** in `backend/.env`. The service-role key lets background jobs finish after a browser session expires. Never put it in HTML, a frontend environment variable, or Git.

## Run on Windows PowerShell

From the extracted `Jerryy-AI` folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
notepad backend/.env
```

Fill in the three Supabase values, preserving your existing project. The Ollama settings already default to your required model. Do not overwrite an existing configured `.env`.

If Ollama is not already running, start it in a separate terminal:

```powershell
ollama serve
```

Keep your existing installed `jerryys-ai` model. **Only if it is missing**, create it from the preserved Modelfile:

```powershell
ollama pull qwen3.5:4b
ollama create jerryys-ai -f Modelfile
```

Start the application:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. Keep FastAPI and Ollama running. Avoid `--reload` while generating: a backend restart interrupts the model request.

## Run on macOS/Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# Edit backend/.env with your existing Supabase project credentials.
# Run ollama serve separately if Ollama is not already running.
.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The optional missing-model commands above work on all platforms. For deployment, use HTTPS and a reverse proxy with an upload body limit of 11 MB. Restrict CORS to your actual frontend origin. Do not serve the project folder as a static root; the supplied server exposes only the selected HTML pages and `/assets`.

## Behavior and limits

- Replies are displayed in full after generation completes. Internal partial text is checkpointed, but never progressively printed in the browser.
- One local model job runs at a time. A database lease coordinates multiple FastAPI processes sharing this Supabase project. The queue allows at most 3 active jobs per account and 30 overall.
- Closing a page, switching chats, refreshing, and logging out do not cancel generation. Stop targets only its owned job and closes that job's Ollama HTTP request. Stop checks run roughly every 0.7 seconds plus database latency.
- Queued jobs survive backend restarts. Interrupted running jobs become failed with Retry after lease recovery (up to 30 seconds). This is not a resumable Ollama compute checkpoint.
- Retry retains the user message. Regenerate replaces the latest assistant row atomically when successful. The previous answer remains visible if regeneration fails. Continue updates the same row and removes exact repeated-prefix overlaps. Model paraphrases can still repeat ideas.
- Edit retains the edited user row, increments its revision, and transactionally removes later messages/attachment records in that chat. Memories sourced from the removed/edited part are removed; other account memory remains. Later attachments are deleted through the cleanup outbox.
- Up to four files/message; each file ≤10 MB. UTF-8 text/code and text PDFs: ≤12,000 extracted characters; PDFs ≤80 pages and bounded processing time/memory. Combined uploaded text/images and message must fit the message context budget. No OCR, vector database or RAG was added.
- PNG/JPEG/WebP/GIF images are validated, stored privately, and capped at 12 megapixels. Runtime `/api/show` capability detection must explicitly report `vision` before image bytes are sent to Ollama. If unsupported or unknown, a clear warning appears and the file remains private. **The actual model installed on your machine was not accessible for verification here.** No primary-model substitution was made. A compatible local vision model would require a separately approved model choice if your installed model lacks vision.
- Model context contains compact account memory plus up to 24 recent messages within an 18,000-character budget. Database history is retained. Character limits are an approximation, not an exact tokenizer budget; Ollama uses `num_ctx=8192`, `num_predict=2048`.
- Draft uploads expire after 24 hours. Storage cleanup runs in the queue worker about every 30 idle seconds; long queues delay physical deletion. Ownership checks/metadata deletion revoke access immediately. If Storage is unavailable, cleanup remains queued for retry. An upload can theoretically orphan a file if both metadata/outbox writes and immediate rollback deletion fail; periodically audit storage on persistently failing infrastructure.
- Memory uses the existing deterministic extraction and local-model fallback, once per user message revision. Clear/delete memory never deletes chats. Explicit Rescan inspects the latest 80 user messages and can restore previously deleted facts; it asks first.
- Search covers only the verified user's titles/message text, paginated 100 chats at a time. Very large histories may need a future full-text index.
- Original externally hosted fonts, Three.js, photos and video remain unchanged. They need network access. Auth and chat functionality are separate from the animation module. Markdown/auth/highlighter dependencies are vendored, with versions/licenses recorded.

To inspect your actual local image capability in PowerShell:

```powershell
(Invoke-RestMethod -Method Post -Uri http://127.0.0.1:11434/api/show -ContentType 'application/json' -Body '{"model":"jerryys-ai"}').capabilities
```

`vision` must be present. `/api/health` also reports the non-sensitive capability result.

## Tests

Backend unit tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q backend/tests
```

The integration test is deliberately skipped by that command. To run real PostgreSQL-compatible SQL/RLS and end-to-end tests with local Supabase/Ollama doubles, install Node.js 20+ and run:

```powershell
npm install --prefix tests
node tests/sql.test.mjs
.\.venv\Scripts\python.exe tests/run-integration.py
npx --prefix tests playwright install chromium
.\.venv\Scripts\python.exe tests/run-integration.py --browser
```

On macOS/Linux use `.venv/bin/python` instead. Test credentials exist only in the isolated fixture, not in production authentication. The fixture runs local ports 8765/8766. SQL checks execute against PGlite PostgreSQL, including real RLS, constraints, functions and cascades. Live Google OAuth, your Supabase deployment and your installed Ollama/hardware still need the setup smoke check in `IMPLEMENTATION_REPORT.md`.
