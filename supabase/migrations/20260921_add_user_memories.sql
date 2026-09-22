-- =========================================================
-- Jerryy's AI: Add user_memories Table with Row Level Security (RLS)
-- Cross-chat per-account memory persistence
-- =========================================================

-- 1. Create user_memories Table
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

-- 2. Create Index for Fast Lookups
CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON public.user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_updated_at ON public.user_memories(updated_at DESC);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.user_memories ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies: Authenticated users can ONLY interact with their own memories
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
