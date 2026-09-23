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
