"""Asynchronous batch OCR endpoint.

``POST /api/v1/ocr/batch-async`` accepts multiple PDF files in a
single multipart request, runs OCR for each in parallel with bounded
concurrency, and returns a job_id. The result is downloaded as a ZIP
from the existing ``/async/{job_id}/result`` endpoint, which detects
``is_batch`` and switches the media type to ``application/zip``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..auth import verify_bearer_token
from ..config import get_settings
from ..services.batch_processor import (
    package_zip,
    process_batch,
    save_upload_to_temp,
)
from ..services.job_store import JobStatus, get_job_store
from ..services.pdf24_client import OCRProgress
from ..utils.errors import FileTooLargeError, InvalidFileError

logger = logging.getLogger(__name__)

# Strong references to running batch background tasks. Without this the
# GC could collect a long-running task before it finishes.
_bg_tasks: set[asyncio.Task] = set()

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


async def _read_uploads(files: list[UploadFile]) -> list[tuple[Path, str, int]]:
    """Save each upload to a temp file. Validates count, size, and PDF magic.

    On any validation failure the already-saved temp files are cleaned
    up before the exception propagates.
    """
    settings = get_settings()
    if not files:
        raise InvalidFileError("No files provided; expected multipart 'file' fields")
    if len(files) > settings.batch_max_files:
        raise FileTooLargeError(
            f"Batch has {len(files)} files; maximum is {settings.batch_max_files}"
        )

    saved: list[tuple[Path, str, int]] = []
    try:
        total = 0
        for upload in files:
            path, filename, size = await save_upload_to_temp(
                upload, settings.max_file_size_async_bytes
            )
            total += size
            if total > settings.batch_max_total_size_bytes:
                path.unlink(missing_ok=True)
                raise FileTooLargeError(
                    f"Batch total size exceeds {settings.batch_max_total_size_bytes} bytes"
                )
            saved.append((path, filename, size))
    except Exception:
        for p, _, _ in saved:
            p.unlink(missing_ok=True)
        raise

    return saved


async def _process_batch_job(
    job_id: str,
    files: list[tuple[Path, str, int]],
    lang: str,
) -> None:
    """Background task: run OCR for each file, package ZIP, update job state."""
    settings = get_settings()
    store = get_job_store()

    async def on_progress(
        completed: int, total: int, current: str, message: str
    ) -> None:
        # files_failed is updated when each file finishes (in the
        # post-batch loop below); here we only update completion count.
        await store.update(
            job_id,
            status=JobStatus.PROCESSING,
            files_completed=completed,
            current_file=current,
            progress=OCRProgress(stage=JobStatus.PROCESSING, message=message),
        )

    try:
        outcomes = await process_batch(files, lang=lang, on_file_done=on_progress)
    except Exception as e:
        logger.exception("Batch job %s failed", job_id)
        await store.update(
            job_id,
            status=JobStatus.ERROR,
            error=str(e),
            completed_at=datetime.now(timezone.utc),
        )
        return

    # Record per-file results before packaging.
    file_results = [
        {
            "filename": o.filename,
            "status": o.status,
            "output_filename": o.output_filename,
            "error": o.error,
            "size_bytes": o.size_bytes,
        }
        for o in outcomes
    ]
    files_failed = sum(1 for o in outcomes if o.status == "failed")
    await store.update(job_id, file_results=file_results, files_failed=files_failed)

    # Package the ZIP.
    await store.update(
        job_id,
        status=JobStatus.PACKAGING,
        progress=OCRProgress(
            stage=JobStatus.PACKAGING, message="Packaging results into ZIP"
        ),
    )
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    result_path = settings.tmp_dir / f"batch_result_{job_id}.zip"
    try:
        package_zip(outcomes, result_path)
    except Exception as e:
        logger.exception("Batch job %s: failed to package ZIP", job_id)
        await store.update(
            job_id,
            status=JobStatus.ERROR,
            error=f"Failed to package ZIP: {e}",
            completed_at=datetime.now(timezone.utc),
        )
        return

    await store.update(
        job_id,
        status=JobStatus.DONE,
        result_path=result_path,
        progress=OCRProgress(stage=JobStatus.DONE, message="Complete"),
        completed_at=datetime.now(timezone.utc),
    )
    logger.info(
        "Batch job %s done: %d success, %d failed",
        job_id,
        len(outcomes) - files_failed,
        files_failed,
    )


@router.post(
    "/batch-async",
    status_code=202,
    summary="Queue a batch of PDFs for OCR. Returns 202 + job_id immediately.",
)
async def ocr_batch_create(
    files: list[UploadFile] = File(
        ..., description="Multiple PDF files (multipart 'file' fields)"
    ),
    lang: str = Form(default="en"),
    _token: str = Depends(verify_bearer_token),
) -> JSONResponse:
    saved = await _read_uploads(files)

    job = await get_job_store().create()
    await get_job_store().update(
        job.id,
        is_batch=True,
        total_files=len(saved),
        progress=OCRProgress(
            stage=JobStatus.QUEUED,
            message=f"Queued {len(saved)} files",
        ),
    )

    _spawn(_process_batch_job(job.id, saved, lang))

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "status": JobStatus.QUEUED,
            "total_files": len(saved),
            "status_url": f"/api/v1/ocr/async/{job.id}",
            "result_url": f"/api/v1/ocr/async/{job.id}/result",
        },
    )
