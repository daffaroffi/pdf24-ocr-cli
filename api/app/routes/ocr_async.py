"""Asynchronous OCR endpoints.

- ``POST /api/v1/ocr/async``: queue a job, returns 202 with ``job_id``
- ``GET /api/v1/ocr/async/{job_id}``: poll status
- ``GET /api/v1/ocr/async/{job_id}/result``: download the result PDF

Background tasks are spawned with ``asyncio.create_task`` and kept in
a module-level set so the GC does not collect them mid-run.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from ..auth import verify_bearer_token
from ..config import get_settings
from ..services.input_handlers import from_base64, from_multipart, from_url
from ..services.job_store import JobStatus, get_job_store
from ..services.pdf24_client import OCRProgress, run_ocr_with_retry
from ..utils.errors import (
    InvalidFileError,
    JobNotFoundError,
    JobNotReadyError,
)

logger = logging.getLogger(__name__)

# Strong references to running background tasks. Without this the GC
# could collect a long-running OCR task before it finishes.
_bg_tasks: set[asyncio.Task] = set()

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


async def _read_input(request: Request, max_size: int) -> tuple[Path, str]:
    """Dispatch on Content-Type, returning (temp_pdf_path, lang)."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        return await from_multipart(form, max_size)
    if "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise InvalidFileError("JSON body must be an object")
        if "file_b64" in body:
            return await from_base64(body, max_size)
        if "url" in body:
            return await from_url(body, max_size)
        raise InvalidFileError("JSON body must include 'file_b64' or 'url'")
    raise InvalidFileError("Unsupported Content-Type. Use multipart/form-data or application/json")


async def _process_job(job_id: str, input_path: Path, lang: str) -> None:
    """Run OCR for a queued job and update its state as it progresses."""
    settings = get_settings()
    store = get_job_store()

    async def on_progress(progress: OCRProgress) -> None:
        # Map progress.stage to job status. "done" means upload+process+download
        # all succeeded; the actual result is written below.
        status = JobStatus.DONE if progress.stage == "done" else progress.stage
        await store.update(job_id, status=status, progress=progress)

    try:
        result = await run_ocr_with_retry(
            input_path,
            lang=lang,
            poll_interval=settings.async_poll_interval_seconds,
            on_progress=on_progress,
        )

        settings.tmp_dir.mkdir(parents=True, exist_ok=True)
        result_path = settings.tmp_dir / f"ocr_result_{job_id}.pdf"
        result_path.write_bytes(result)

        await store.update(
            job_id,
            status=JobStatus.DONE,
            progress=OCRProgress(stage=JobStatus.DONE, message="Complete"),
            result_path=result_path,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info("Job %s completed (%d bytes)", job_id, len(result))
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        await store.update(
            job_id,
            status=JobStatus.ERROR,
            error=str(e),
            progress=OCRProgress(stage=JobStatus.ERROR, message=str(e)),
            completed_at=datetime.now(timezone.utc),
        )
    finally:
        if input_path.exists():
            input_path.unlink(missing_ok=True)


@router.post(
    "/async",
    status_code=202,
    summary="Queue an OCR job and return immediately with a job_id",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"oneOf": [
                        {"$ref": "#/components/schemas/Base64OCRRequest"},
                        {"$ref": "#/components/schemas/URLOCRRequest"},
                    ]},
                    "examples": {
                        "base64": {
                            "summary": "Base64 input",
                            "value": {"file_b64": "JVBERi0xLjQK...", "lang": "id"},
                        },
                        "url": {
                            "summary": "URL input",
                            "value": {"url": "https://example.com/large.pdf", "lang": "en"},
                        },
                    },
                }
            }
        }
    },
)
async def ocr_async_create(
    request: Request,
    _token: str = Depends(verify_bearer_token),
) -> JSONResponse:
    settings = get_settings()
    max_size = settings.max_file_size_async_bytes
    input_path, lang = await _read_input(request, max_size)

    job = await get_job_store().create()
    await get_job_store().update(job.id, input_path=input_path)

    _spawn(_process_job(job.id, input_path, lang))

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "status": JobStatus.QUEUED,
            "status_url": f"/api/v1/ocr/async/{job.id}",
            "result_url": f"/api/v1/ocr/async/{job.id}/result",
        },
    )


@router.get(
    "/async/{job_id}",
    summary="Get the current status of an async OCR job",
)
async def ocr_async_status(
    job_id: str,
    _token: str = Depends(verify_bearer_token),
) -> dict[str, Any]:
    job = await get_job_store().get(job_id)
    if job is None:
        raise JobNotFoundError(f"Job {job_id} not found (may have been cleaned up)")
    return job.to_dict()


@router.get(
    "/async/{job_id}/result",
    summary="Download the OCR'd PDF for a completed job",
    responses={
        200: {"description": "OCR'd PDF binary", "content": {"application/pdf": {}}},
        404: {"description": "Job not found"},
        425: {"description": "Job is not yet complete"},
    },
)
async def ocr_async_result(
    job_id: str,
    _token: str = Depends(verify_bearer_token),
) -> FileResponse:
    job = await get_job_store().get(job_id)
    if job is None:
        raise JobNotFoundError(f"Job {job_id} not found (may have been cleaned up)")
    if job.status != JobStatus.DONE:
        raise JobNotReadyError(
            f"Job {job_id} status is '{job.status}', not 'done'"
        )
    if job.result_path is None or not job.result_path.exists():
        raise JobNotReadyError(
            f"Result file for job {job_id} is no longer available"
        )
    if job.is_batch:
        return FileResponse(
            path=job.result_path,
            media_type="application/zip",
            filename="ocr_results.zip",
        )
    return FileResponse(
        path=job.result_path,
        media_type="application/pdf",
        filename="ocr_result.pdf",
    )
