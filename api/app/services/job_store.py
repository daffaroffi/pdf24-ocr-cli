"""In-memory job tracking with TTL-based cleanup.

Async OCR jobs are stored here while they run. The store runs a
background task that deletes jobs older than ``job_ttl_seconds`` and
removes their temp files.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from .pdf24_client import OCRProgress

logger = logging.getLogger(__name__)


class JobStatus:
    QUEUED = "queued"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    PACKAGING = "packaging"
    DONE = "done"
    ERROR = "error"


@dataclass
class JobInfo:
    id: str
    status: str
    progress: OCRProgress
    input_path: Path | None = None
    result_path: Path | None = None
    pdf24_server: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    # Batch fields. All default to "no batch" so single-file jobs keep
    # working unchanged.
    is_batch: bool = False
    total_files: int = 0
    files_completed: int = 0
    files_failed: int = 0
    current_file: str | None = None
    file_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        body: dict = {
            "job_id": self.id,
            "status": self.status,
            "progress": {
                "stage": self.progress.stage,
                "current_page": self.progress.current_page,
                "total_page": self.progress.total_pages,
                "message": self.progress.message,
            },
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
        if self.is_batch:
            body["batch"] = {
                "total_files": self.total_files,
                "files_completed": self.files_completed,
                "files_failed": self.files_failed,
                "current_file": self.current_file,
                "file_results": list(self.file_results),
            }
        return body


class JobStore:
    """Thread-safe in-memory job store with a periodic cleanup loop."""

    def __init__(self, ttl_seconds: int, cleanup_interval_seconds: int) -> None:
        self._jobs: dict[str, JobInfo] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Job store cleanup loop started")

    async def stop(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def create(self) -> JobInfo:
        job = JobInfo(
            id=str(uuid.uuid4()),
            status=JobStatus.QUEUED,
            progress=OCRProgress(stage=JobStatus.QUEUED, message="Queued"),
        )
        async with self._lock:
            self._jobs[job.id] = job
        logger.info("Job %s created", job.id)
        return job

    async def get(self, job_id: str) -> JobInfo | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields) -> JobInfo | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for k, v in fields.items():
                setattr(job, k, v)
            return job

    async def delete(self, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        if job.input_path and job.input_path.exists():
            job.input_path.unlink(missing_ok=True)
        if job.result_path and job.result_path.exists():
            job.result_path.unlink(missing_ok=True)
        return True

    async def _cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [
                jid for jid, j in self._jobs.items()
                if (now - j.created_at).total_seconds() > self._ttl
            ]
        deleted = 0
        for jid in expired:
            if await self.delete(jid):
                deleted += 1
                logger.info("Cleaned up expired job %s", jid)
        return deleted

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Job store cleanup error")


_job_store: JobStore | None = None


def init_job_store() -> JobStore:
    """Create and start the singleton job store. Called from lifespan."""
    global _job_store
    settings = get_settings()
    _job_store = JobStore(
        ttl_seconds=settings.job_ttl_seconds,
        cleanup_interval_seconds=settings.job_cleanup_interval_seconds,
    )
    return _job_store


def get_job_store() -> JobStore:
    """Return the singleton job store. Raises if init_job_store was not called."""
    if _job_store is None:
        raise RuntimeError("Job store not initialized; call init_job_store() first")
    return _job_store


async def shutdown_job_store() -> None:
    """Stop the singleton job store. Called from lifespan shutdown."""
    global _job_store
    if _job_store is not None:
        await _job_store.stop()
        _job_store = None
