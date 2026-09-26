-- Run this complete file in the Supabase SQL Editor. No live changes have been applied by this package.
BEGIN;
-- =========================================================
-- Jerryy's AI: Supabase Database Schema
-- Per-User Chat History with Row Level Security (RLS)
-- =========================================================

-- 1. Create Chats Table
CREATE TABLE IF NOT EXISTS public.chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    profile TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backwards compatibility table/view for 'conversations'
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    profile TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create Messages Table (with chat_id and conversation_id support)
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID REFERENCES public.chats(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Create High-Performance Indexes
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON public.chats(user_id);
CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON public.chats(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON public.messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON public.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON public.messages(created_at ASC);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

-- 5. Chats RLS Policies
DROP POLICY IF EXISTS "Users can view their own chats" ON public.chats;
CREATE POLICY "Users can view their own chats"
    ON public.chats
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own chats" ON public.chats;
CREATE POLICY "Users can insert their own chats"
    ON public.chats
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own chats" ON public.chats;
CREATE POLICY "Users can update their own chats"
    ON public.chats
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own chats" ON public.chats;
CREATE POLICY "Users can delete their own chats"
    ON public.chats
    FOR DELETE
    USING (auth.uid() = user_id);

-- 6. Conversations RLS Policies (Compatibility)
DROP POLICY IF EXISTS "Users can view their own conversations" ON public.conversations;
CREATE POLICY "Users can view their own conversations"
    ON public.conversations
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own conversations" ON public.conversations;
CREATE POLICY "Users can insert their own conversations"
    ON public.conversations
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own conversations" ON public.conversations;
CREATE POLICY "Users can update their own conversations"
    ON public.conversations
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own conversations" ON public.conversations;
CREATE POLICY "Users can delete their own conversations"
    ON public.conversations
    FOR DELETE
    USING (auth.uid() = user_id);

-- 7. Messages RLS Policies
DROP POLICY IF EXISTS "Users can view their own messages" ON public.messages;
CREATE POLICY "Users can view their own messages"
    ON public.messages
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own messages" ON public.messages;
CREATE POLICY "Users can insert their own messages"
    ON public.messages
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own messages" ON public.messages;
CREATE POLICY "Users can update their own messages"
    ON public.messages
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own messages" ON public.messages;
CREATE POLICY "Users can delete their own messages"
    ON public.messages
    FOR DELETE
    USING (auth.uid() = user_id);

-- 8. User Memories Table (Cross-Chat Per-Account Memory)
CREATE TABLE IF NOT EXISTS public.user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    memory_key TEXT NOT NULL,
    memory_value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, memory_key)
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON public.user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_updated_at ON public.user_memories(updated_at DESC);

ALTER TABLE public.user_memories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own memories" ON public.user_memories;
CREATE POLICY "Users can view their own memories"
    ON public.user_memories
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own memories" ON public.user_memories;
CREATE POLICY "Users can insert their own memories"
    ON public.user_memories
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own memories" ON public.user_memories;
CREATE POLICY "Users can update their own memories"
    ON public.user_memories
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own memories" ON public.user_memories;
CREATE POLICY "Users can delete their own memories"
    ON public.user_memories
    FOR DELETE
    USING (auth.uid() = user_id);


-- =========================================================
-- Jerryy's AI: Create generation_jobs Table with Row Level Security (RLS)
-- Asynchronous backend generation tracking and resilience
-- =========================================================

-- 1. Create generation_jobs Table
CREATE TABLE IF NOT EXISTS public.generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chat_id UUID NOT NULL REFERENCES public.chats(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('generating', 'complete', 'stopped', 'failed')),
    partial_content TEXT NOT NULL DEFAULT '',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create High-Performance Indexes
CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON public.generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_chat_id ON public.generation_jobs(chat_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON public.generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_updated_at ON public.generation_jobs(updated_at DESC);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.generation_jobs ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies: Authenticated users can ONLY interact with their own jobs
DROP POLICY IF EXISTS "Users can view their own generation jobs" ON public.generation_jobs;
CREATE POLICY "Users can view their own generation jobs"
    ON public.generation_jobs
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own generation jobs" ON public.generation_jobs;
CREATE POLICY "Users can insert their own generation jobs"
    ON public.generation_jobs
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own generation jobs" ON public.generation_jobs;
CREATE POLICY "Users can update their own generation jobs"
    ON public.generation_jobs
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own generation jobs" ON public.generation_jobs;
CREATE POLICY "Users can delete their own generation jobs"
    ON public.generation_jobs
    FOR DELETE
    USING (auth.uid() = user_id);

-- Extend the supplied schema without deleting existing chat history.
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS sequence_no BIGINT GENERATED BY DEFAULT AS IDENTITY;
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'complete';
-- Legacy messages already passed through the previous memory system. Do not
-- extract them again on regeneration; explicit Rescan remains available.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='messages' AND column_name='memory_processed') THEN
  ALTER TABLE public.messages ADD COLUMN memory_processed BOOLEAN NOT NULL DEFAULT false;
  UPDATE public.messages SET memory_processed=true;
 END IF;
END $$;
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname='jai_message_order') THEN
  WITH ordered AS(SELECT id,row_number() OVER(ORDER BY created_at,id) n FROM public.messages)
  UPDATE public.messages m SET sequence_no=o.n FROM ordered o WHERE m.id=o.id;
  PERFORM setval(pg_get_serial_sequence('public.messages','sequence_no'),greatest(coalesce((SELECT max(sequence_no) FROM public.messages),0)+1,1),false);
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS jai_message_order ON public.messages(sequence_no);
CREATE INDEX IF NOT EXISTS jai_messages_chat_order ON public.messages(chat_id,sequence_no);
CREATE INDEX IF NOT EXISTS jai_chats_user_recent ON public.chats(user_id,updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS jai_chat_owner ON public.chats(id,user_id);
CREATE UNIQUE INDEX IF NOT EXISTS jai_message_owner ON public.messages(id,chat_id,user_id);
ALTER TABLE public.user_memories ADD COLUMN IF NOT EXISTS source_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL;
ALTER TABLE public.generation_jobs DROP CONSTRAINT IF EXISTS generation_jobs_status_check;
ALTER TABLE public.generation_jobs ADD CONSTRAINT generation_jobs_status_check CHECK(status IN('queued','generating','complete','stopped','failed'));
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS request_id UUID;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS request_body JSONB;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS user_message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS response_id UUID;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'send';
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS base_content TEXT NOT NULL DEFAULT '';
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS invalidated BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS worker_id UUID;
ALTER TABLE public.generation_jobs ADD COLUMN IF NOT EXISTS warning TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS jai_generation_request ON public.generation_jobs(user_id,request_id) WHERE request_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS jai_one_active_per_chat ON public.generation_jobs(chat_id) WHERE status IN('queued','generating');
CREATE INDEX IF NOT EXISTS jai_queue_order ON public.generation_jobs(created_at) WHERE status='queued';
CREATE TABLE IF NOT EXISTS public.message_attachments(
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 chat_id UUID NOT NULL,message_id UUID,file_name TEXT NOT NULL CHECK(length(file_name)<=180),
 file_type TEXT NOT NULL,file_size BIGINT NOT NULL CHECK(file_size BETWEEN 1 AND 10485760),
 storage_path TEXT NOT NULL UNIQUE,extracted_text TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(chat_id,user_id) REFERENCES public.chats(id,user_id) ON DELETE CASCADE,
 FOREIGN KEY(message_id,chat_id,user_id) REFERENCES public.messages(id,chat_id,user_id) ON DELETE CASCADE,
 CHECK(storage_path LIKE user_id::text||'/'||chat_id::text||'/%')
);
CREATE INDEX IF NOT EXISTS jai_attachments_chat ON public.message_attachments(chat_id);
CREATE INDEX IF NOT EXISTS jai_attachments_message ON public.message_attachments(message_id);
CREATE INDEX IF NOT EXISTS jai_attachments_user ON public.message_attachments(user_id);
CREATE TABLE IF NOT EXISTS public.attachment_cleanup(storage_path TEXT PRIMARY KEY,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE OR REPLACE FUNCTION public.jai_queue_file_cleanup() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN INSERT INTO public.attachment_cleanup(storage_path) VALUES(OLD.storage_path) ON CONFLICT DO NOTHING;RETURN OLD;END $$;
DROP TRIGGER IF EXISTS jai_attachment_cleanup ON public.message_attachments;
CREATE TRIGGER jai_attachment_cleanup AFTER DELETE ON public.message_attachments FOR EACH ROW EXECUTE FUNCTION public.jai_queue_file_cleanup();
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='jai_messages_owned_chat') THEN
  ALTER TABLE public.messages ADD CONSTRAINT jai_messages_owned_chat FOREIGN KEY(chat_id,user_id) REFERENCES public.chats(id,user_id) ON DELETE CASCADE NOT VALID;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='jai_jobs_owned_chat') THEN
  ALTER TABLE public.generation_jobs ADD CONSTRAINT jai_jobs_owned_chat FOREIGN KEY(chat_id,user_id) REFERENCES public.chats(id,user_id) ON DELETE CASCADE NOT VALID;
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.generation_worker_lease(id BOOLEAN PRIMARY KEY DEFAULT true CHECK(id),worker_id UUID,expires_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO public.generation_worker_lease(id) VALUES(true) ON CONFLICT DO NOTHING;
ALTER TABLE public.generation_worker_lease ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attachment_cleanup ENABLE ROW LEVEL SECURITY;
-- One server writer preserves message/job invariants; authenticated clients can
-- SELECT only their own rows, and cannot invoke service-only mutation functions.
DO $$ DECLARE t TEXT;p RECORD;BEGIN
 FOREACH t IN ARRAY ARRAY['chats','conversations','messages','generation_jobs','user_memories','message_attachments'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  FOR p IN SELECT policyname FROM pg_policies WHERE schemaname='public' AND tablename=t LOOP EXECUTE format('DROP POLICY %I ON public.%I',p.policyname,t);END LOOP;
  EXECUTE format('CREATE POLICY jai_owner_read ON public.%I FOR SELECT TO authenticated USING((SELECT auth.uid())=user_id)',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM anon,authenticated',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('GRANT ALL ON public.%I TO service_role',t);
 END LOOP;
END $$;
CREATE POLICY jai_parent_read ON public.messages AS RESTRICTIVE FOR SELECT TO authenticated USING(
 (chat_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.chats c WHERE c.id=chat_id AND c.user_id=auth.uid())) OR
 (chat_id IS NULL AND conversation_id IS NOT NULL AND EXISTS(SELECT 1 FROM public.conversations c WHERE c.id=conversation_id AND c.user_id=auth.uid())));
CREATE POLICY jai_parent_read ON public.generation_jobs AS RESTRICTIVE FOR SELECT TO authenticated USING(EXISTS(SELECT 1 FROM public.chats c WHERE c.id=chat_id AND c.user_id=auth.uid()));
REVOKE ALL ON public.generation_worker_lease,public.attachment_cleanup FROM anon,authenticated;
GRANT ALL ON public.generation_worker_lease,public.attachment_cleanup TO service_role;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

CREATE OR REPLACE FUNCTION public.jai_prepare(p_user UUID,p_chat UUID,p_request UUID,p_action TEXT,p_message TEXT,p_target UUID,p_attachments UUID[],p_title TEXT,p_user_limit INTEGER,p_total_limit INTEGER)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE c public.chats;j public.generation_jobs;u public.messages;a public.messages;body JSONB;response UUID;base TEXT:='';n INTEGER;chars INTEGER;
BEGIN
 body:=jsonb_build_object('chat',p_chat,'action',p_action,'message',p_message,'target',p_target,'attachments',p_attachments);
 PERFORM pg_advisory_xact_lock(742191);
 SELECT * INTO j FROM public.generation_jobs WHERE user_id=p_user AND request_id=p_request;
 IF FOUND THEN
  IF j.request_body<>body THEN RAISE EXCEPTION 'request_conflict';END IF;
  IF j.invalidated THEN RAISE EXCEPTION 'stale';END IF;
  RETURN to_jsonb(j);
 END IF;
 SELECT * INTO c FROM public.chats WHERE id=p_chat AND user_id=p_user FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'not_found';END IF;
 IF EXISTS(SELECT 1 FROM public.generation_jobs WHERE chat_id=p_chat AND status IN('queued','generating')) THEN RAISE EXCEPTION 'busy';END IF;
 IF (SELECT count(*) FROM public.generation_jobs WHERE status IN('queued','generating'))>=p_total_limit OR
 (SELECT count(*) FROM public.generation_jobs WHERE user_id=p_user AND status IN('queued','generating'))>=p_user_limit THEN RAISE EXCEPTION 'queue_full';END IF;
 IF p_action='send' THEN
  IF length(btrim(p_message))=0 AND coalesce(array_length(p_attachments,1),0)=0 THEN RAISE EXCEPTION 'invalid_action';END IF;
  IF coalesce(array_length(p_attachments,1),0)>4 THEN RAISE EXCEPTION 'attachments';END IF;
  SELECT count(*),coalesce(sum(length(extracted_text)+CASE WHEN file_type LIKE 'image/%' THEN 1500 ELSE 0 END),0) INTO n,chars FROM public.message_attachments WHERE id=ANY(p_attachments) AND user_id=p_user AND chat_id=p_chat AND message_id IS NULL;
  IF n<>coalesce(array_length(p_attachments,1),0) OR chars+length(p_message)>12000 THEN RAISE EXCEPTION 'attachments';END IF;
  INSERT INTO public.messages(chat_id,user_id,role,content) VALUES(p_chat,p_user,'user',p_message) RETURNING * INTO u;
  UPDATE public.message_attachments SET message_id=u.id WHERE id=ANY(p_attachments) AND user_id=p_user;
  response:=gen_random_uuid();
 ELSIF p_action='edit' THEN
  SELECT * INTO u FROM public.messages WHERE id=p_target AND chat_id=p_chat AND user_id=p_user AND role='user' FOR UPDATE;
  IF NOT FOUND OR length(btrim(p_message))=0 THEN RAISE EXCEPTION 'invalid_action';END IF;
  UPDATE public.generation_jobs SET invalidated=true WHERE chat_id=p_chat AND user_id=p_user AND user_message_id IN(SELECT id FROM public.messages WHERE chat_id=p_chat AND sequence_no>=u.sequence_no);
  DELETE FROM public.user_memories WHERE user_id=p_user AND source_message_id IN(SELECT id FROM public.messages WHERE chat_id=p_chat AND sequence_no>=u.sequence_no);
  DELETE FROM public.messages WHERE chat_id=p_chat AND user_id=p_user AND sequence_no>u.sequence_no;
  UPDATE public.messages SET content=p_message,revision=revision+1,memory_processed=false WHERE id=u.id RETURNING * INTO u;
  response:=gen_random_uuid();
 ELSIF p_action IN('retry','regenerate','continue') THEN
  SELECT * INTO u FROM public.messages WHERE chat_id=p_chat AND user_id=p_user AND role='user' ORDER BY sequence_no DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'invalid_action';END IF;
  SELECT * INTO j FROM public.generation_jobs WHERE chat_id=p_chat AND user_id=p_user AND NOT invalidated ORDER BY created_at DESC,id DESC LIMIT 1;
  SELECT * INTO a FROM public.messages WHERE chat_id=p_chat AND user_id=p_user AND role='assistant' AND sequence_no>u.sequence_no ORDER BY sequence_no DESC LIMIT 1;
  IF p_action='retry' THEN
   IF j.id IS NULL OR j.id<>p_target OR j.status NOT IN('failed','stopped') THEN RAISE EXCEPTION 'invalid_action';END IF;
  ELSE
   IF a.id IS NULL OR a.id<>p_target THEN RAISE EXCEPTION 'stale';END IF;
   IF p_action='continue' AND a.state<>'stopped' THEN RAISE EXCEPTION 'invalid_action';END IF;
  END IF;
  response:=coalesce(a.id,j.response_id,gen_random_uuid());
  IF p_action='continue' THEN base:=a.content;END IF;
  IF p_action='retry' AND j.action='continue' THEN base:=j.base_content;END IF;
 ELSE RAISE EXCEPTION 'invalid_action';END IF;
 INSERT INTO public.generation_jobs(user_id,chat_id,prompt,status,request_id,request_body,user_message_id,response_id,action,base_content)
 VALUES(p_user,p_chat,u.content,'queued',p_request,body,u.id,response,p_action,base) RETURNING * INTO j;
 UPDATE public.chats SET updated_at=now(),title=CASE WHEN title='New Chat' THEN p_title ELSE title END WHERE id=p_chat;
 RETURN to_jsonb(j);
END $$;
CREATE OR REPLACE FUNCTION public.jai_lease(p_worker UUID) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE l public.generation_worker_lease;BEGIN
 SELECT * INTO l FROM public.generation_worker_lease WHERE id FOR UPDATE;
 IF l.worker_id=p_worker OR l.expires_at<now() THEN
  IF l.worker_id IS DISTINCT FROM p_worker THEN
   UPDATE public.generation_jobs SET status='failed',error='The backend restarted during generation. Use Retry.',updated_at=now() WHERE status='generating';
  END IF;
  UPDATE public.generation_worker_lease SET worker_id=p_worker,expires_at=now()+interval '30 seconds' WHERE id;RETURN true;
 END IF;RETURN false;
END $$;
CREATE OR REPLACE FUNCTION public.jai_release(p_worker UUID) RETURNS VOID LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 UPDATE public.generation_worker_lease SET expires_at=now()-interval '1 second' WHERE worker_id=p_worker;
$$;
CREATE OR REPLACE FUNCTION public.jai_claim(p_worker UUID) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE j public.generation_jobs;BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.generation_worker_lease WHERE id AND worker_id=p_worker AND expires_at>now()) THEN RETURN NULL;END IF;
 SELECT * INTO j FROM public.generation_jobs WHERE status='queued' AND NOT invalidated ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 UPDATE public.generation_jobs SET status='generating',worker_id=p_worker,updated_at=now() WHERE id=j.id RETURNING * INTO j;RETURN to_jsonb(j);
END $$;
CREATE OR REPLACE FUNCTION public.jai_checkpoint(p_worker UUID,p_job UUID,p_content TEXT) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE stopped BOOLEAN;BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.generation_worker_lease WHERE id AND worker_id=p_worker AND expires_at>now()) THEN RETURN true;END IF;
 UPDATE public.generation_jobs SET partial_content=p_content,updated_at=now() WHERE id=p_job AND worker_id=p_worker AND status='generating' RETURNING stop_requested INTO stopped;
 RETURN coalesce(stopped,true);
END $$;
CREATE OR REPLACE FUNCTION public.jai_finish(p_worker UUID,p_job UUID,p_status TEXT,p_content TEXT,p_error TEXT,p_warning TEXT) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE j public.generation_jobs;final TEXT;BEGIN
 IF p_status NOT IN('complete','stopped','failed') THEN RAISE EXCEPTION 'invalid_action';END IF;
 SELECT * INTO j FROM public.generation_jobs WHERE id=p_job FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL;END IF;
 IF j.status NOT IN('generating','queued') THEN RETURN to_jsonb(j);END IF;
 IF j.worker_id IS DISTINCT FROM p_worker OR NOT EXISTS(SELECT 1 FROM public.generation_worker_lease WHERE id AND worker_id=p_worker AND expires_at>now()) THEN RAISE EXCEPTION 'stale';END IF;
 final:=CASE WHEN j.stop_requested AND p_status<>'failed' THEN 'stopped' ELSE p_status END;
 IF final IN('complete','stopped') AND length(btrim(p_content))>0 THEN
  INSERT INTO public.messages(id,user_id,chat_id,role,content,state,memory_processed) VALUES(j.response_id,j.user_id,j.chat_id,'assistant',p_content,final,true)
  ON CONFLICT(id) DO UPDATE SET content=excluded.content,state=excluded.state;
 END IF;
 UPDATE public.generation_jobs SET status=final,partial_content=p_content,error=p_error,warning=p_warning,updated_at=now() WHERE id=p_job RETURNING * INTO j;
 UPDATE public.chats SET updated_at=now() WHERE id=j.chat_id;RETURN to_jsonb(j);
END $$;
CREATE OR REPLACE FUNCTION public.jai_stop(p_user UUID,p_job UUID) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE j public.generation_jobs;BEGIN
 UPDATE public.generation_jobs SET stop_requested=true,status=CASE WHEN status='queued' THEN 'stopped' ELSE status END,updated_at=now() WHERE id=p_job AND user_id=p_user AND status IN('queued','generating') RETURNING * INTO j;
 IF NOT FOUND THEN SELECT * INTO j FROM public.generation_jobs WHERE id=p_job AND user_id=p_user;END IF;
 IF j.id IS NULL THEN RAISE EXCEPTION 'not_found';END IF;RETURN to_jsonb(j);
END $$;
CREATE OR REPLACE FUNCTION public.jai_memory_apply(p_user UUID,p_message UUID,p_revision INTEGER,p_memories JSONB,p_forget TEXT[]) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE m public.messages;fact JSONB;BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_user::text,1));
 SELECT * INTO m FROM public.messages WHERE id=p_message AND user_id=p_user AND role='user' FOR UPDATE;
 IF NOT FOUND OR m.memory_processed OR m.revision<>p_revision THEN RETURN false;END IF;
 IF '__all__'=ANY(p_forget) THEN DELETE FROM public.user_memories WHERE user_id=p_user;ELSE DELETE FROM public.user_memories WHERE user_id=p_user AND memory_key=ANY(p_forget);END IF;
 FOR fact IN SELECT * FROM jsonb_array_elements(p_memories) LOOP
  INSERT INTO public.user_memories(user_id,memory_key,memory_value,category,source_message_id) VALUES(p_user,fact->>'key',fact->>'value',coalesce(fact->>'category','general'),p_message)
  ON CONFLICT(user_id,memory_key) DO UPDATE SET memory_value=excluded.memory_value,category=excluded.category,source_message_id=excluded.source_message_id,updated_at=now();
 END LOOP;
 UPDATE public.messages SET memory_processed=true WHERE id=p_message;RETURN true;
END $$;
CREATE OR REPLACE FUNCTION public.jai_forget(p_user UUID,p_key TEXT) RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_user::text,1));
 DELETE FROM public.user_memories WHERE user_id=p_user AND(p_key IS NULL OR memory_key=p_key);
 UPDATE public.messages SET memory_processed=true WHERE user_id=p_user AND NOT memory_processed;
END $$;
CREATE OR REPLACE FUNCTION public.jai_search(p_user UUID,p_query TEXT,p_offset INTEGER DEFAULT 0) RETURNS SETOF public.chats LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT c.* FROM public.chats c WHERE c.user_id=p_user AND(p_query='' OR strpos(lower(c.title),lower(p_query))>0 OR EXISTS(SELECT 1 FROM public.messages m WHERE m.chat_id=c.id AND m.user_id=p_user AND strpos(lower(m.content),lower(p_query))>0)) ORDER BY c.updated_at DESC,c.id LIMIT 100 OFFSET greatest(p_offset,0);
$$;
CREATE OR REPLACE FUNCTION public.jai_delete_chat(p_user UUID,p_chat UUID) RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 PERFORM 1 FROM public.chats WHERE id=p_chat AND user_id=p_user FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'not_found';END IF;
 DELETE FROM public.chats WHERE id=p_chat AND user_id=p_user;
END $$;
DO $$ DECLARE r RECORD;BEGIN
 FOR r IN SELECT p.oid::regprocedure sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'jai_%' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',r.sig);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',r.sig);
 END LOOP;
END $$;
INSERT INTO storage.buckets(id,name,public,file_size_limit) VALUES('chat-attachments','chat-attachments',false,10485760) ON CONFLICT(id) DO UPDATE SET public=false,file_size_limit=10485760;
DROP POLICY IF EXISTS jai_private_attachment_read ON storage.objects;
CREATE POLICY jai_private_attachment_read ON storage.objects FOR SELECT TO authenticated USING(bucket_id='chat-attachments' AND(storage.foldername(name))[1]=(SELECT auth.uid())::text AND EXISTS(SELECT 1 FROM public.message_attachments a WHERE a.storage_path=name AND a.user_id=auth.uid()));
DROP POLICY IF EXISTS jai_attachment_guard ON storage.objects;
CREATE POLICY jai_attachment_guard ON storage.objects AS RESTRICTIVE FOR SELECT TO authenticated USING(bucket_id<>'chat-attachments' OR((storage.foldername(name))[1]=(SELECT auth.uid())::text AND EXISTS(SELECT 1 FROM public.message_attachments a WHERE a.storage_path=name AND a.user_id=auth.uid())));
DROP POLICY IF EXISTS jai_attachment_insert_guard ON storage.objects;
CREATE POLICY jai_attachment_insert_guard ON storage.objects AS RESTRICTIVE FOR INSERT TO authenticated WITH CHECK(bucket_id<>'chat-attachments');
DROP POLICY IF EXISTS jai_attachment_update_guard ON storage.objects;
CREATE POLICY jai_attachment_update_guard ON storage.objects AS RESTRICTIVE FOR UPDATE TO authenticated USING(bucket_id<>'chat-attachments') WITH CHECK(bucket_id<>'chat-attachments');
DROP POLICY IF EXISTS jai_attachment_delete_guard ON storage.objects;
CREATE POLICY jai_attachment_delete_guard ON storage.objects AS RESTRICTIVE FOR DELETE TO authenticated USING(bucket_id<>'chat-attachments');
DROP POLICY IF EXISTS jai_attachment_anon_guard ON storage.objects;
CREATE POLICY jai_attachment_anon_guard ON storage.objects AS RESTRICTIVE FOR ALL TO anon USING(bucket_id<>'chat-attachments') WITH CHECK(bucket_id<>'chat-attachments');
NOTIFY pgrst,'reload schema';

COMMIT;
