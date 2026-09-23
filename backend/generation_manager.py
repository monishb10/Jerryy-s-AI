"""
Jerryy's AI Generation Manager
Decouples AI generation from frontend HTTP connections into tracked backend jobs.
Maintains state, streaming accumulation, task cancellation, and user privacy isolation.
"""

import asyncio
import time
import uuid
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("jerryys_ai.generations")


@dataclass
class GenerationJob:
    id: str
    user_id: str
    chat_id: str
    prompt: str
    status: str = "generating"  # generating | complete | stopped | failed
    partial_content: str = ""
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    asyncio_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_id": self.id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "status": self.status,
            "content": self.partial_content,
            "partial_content": self.partial_content,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class GenerationManager:
    def __init__(self):
        self._jobs: Dict[str, GenerationJob] = {}
        self._lock = asyncio.Lock()
        # Concurrency guard: Only 1 active Ollama inference on local CPU/RAM at a time
        self.ollama_semaphore = asyncio.Semaphore(1)

    async def create_job(self, user_id: str, chat_id: str, prompt: str) -> GenerationJob:
        async with self._lock:
            # Concurrency & deduplication: check if this chat already has a generation running
            for job in self._jobs.values():
                if job.user_id == user_id and job.chat_id == chat_id and job.status == "generating":
                    logger.info(f"[JOB] Chat {chat_id} already has active generation {job.id}. Reusing existing job.")
                    return job

            job_id = str(uuid.uuid4())
            now = time.time()
            job = GenerationJob(
                id=job_id,
                user_id=user_id,
                chat_id=chat_id,
                prompt=prompt,
                status="generating",
                partial_content="",
                created_at=now,
                updated_at=now
            )
            self._jobs[job_id] = job
            logger.info(f"[JOB] Created generation job {job_id} for chat {chat_id}, user {user_id}")
            return job

    def get_job(self, generation_id: str, user_id: Optional[str] = None) -> Optional[GenerationJob]:
        job = self._jobs.get(generation_id)
        if not job:
            return None
        # Strict user isolation: never expose a generation belonging to another user
        if user_id and job.user_id != user_id:
            logger.warning(f"[SECURITY] User {user_id} attempted to access job {generation_id} belonging to {job.user_id}")
            return None
        return job

    def get_active_job_for_chat(self, chat_id: str, user_id: str) -> Optional[GenerationJob]:
        # Return currently active generation for this specific user & chat
        for job in self._jobs.values():
            if job.user_id == user_id and job.chat_id == chat_id and job.status == "generating":
                return job
        return None

    def append_content(self, generation_id: str, chunk: str) -> None:
        job = self._jobs.get(generation_id)
        if job and job.status == "generating":
            job.partial_content += chunk
            job.updated_at = time.time()

    def finish_job(self, generation_id: str, status: str = "complete", error: Optional[str] = None) -> None:
        job = self._jobs.get(generation_id)
        if job and job.status == "generating":
            job.status = status
            job.error = error
            job.updated_at = time.time()
            logger.info(f"[JOB] Generation {generation_id} marked as {status} (content len: {len(job.partial_content)})")

    def cancel_job(self, generation_id: str, user_id: str) -> Tuple[bool, Optional[GenerationJob]]:
        job = self.get_job(generation_id, user_id=user_id)
        if not job:
            return False, None

        if job.status == "generating":
            job.status = "stopped"
            job.updated_at = time.time()
            if job.asyncio_task and not job.asyncio_task.done():
                job.asyncio_task.cancel()
                logger.info(f"[JOB] Cancelled background asyncio task for generation {generation_id}")
            return True, job

        return False, job


# Global singleton instance
generation_manager = GenerationManager()
