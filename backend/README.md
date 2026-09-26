# Backend

Use the complete setup, SQL and platform-specific commands in `../README.md`.

`main.py` serves the original pages and includes modular APIs. `auth.py` verifies Supabase sessions; `database.py` wraps REST/RPC; `chat.py` owns private chat/message/job/memory routes; `generation_manager.py` runs a leased FIFO worker; `ollama_client.py` contains local model transport and preserved memory extraction; `context.py` bounds model context; `memory.py` manages facts; `attachments.py` validates/extracts files and manages private Storage; `config.py` reads server environment variables.

Public: `GET /api/config` (publishable configuration only), `GET /api/health`.

Authenticated: chat list/create/load/rename/delete; `/api/generations` create/status/stop; `/api/chats/{id}/generation`; `/api/memories` view/delete/clear/rescan; `/api/chats/{id}/attachments` upload; `/api/attachments/{id}` delete draft; `/api/attachments/{id}/content` private download.

Every private route derives identity from verified Supabase access tokens. Clients cannot supply `user_id`. Background service-role database writes use ownership-scoped queries and transactional service-only functions. Authenticated database clients have owner-only SELECT grants; mutations pass through FastAPI. Database RLS is always enabled.

Do not use removed `/api/chat`, token streaming, direct client message inserts, or the legacy `test-token-*` bypass. Error details are bounded, and timing logs exclude prompts, memory contents and tokens.
