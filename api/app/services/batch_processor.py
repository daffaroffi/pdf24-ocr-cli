"""Batch OCR processing.

Reads a list of (filename, temp_path) tuples, runs OCR for each file
with bounded concurrency via an asyncio.Semaphore, and packages the
results into a ZIP that contains the OCR'd PDFs and a ``results.json``
summarizing per-file status.

Per-file failures do NOT abort the batch: the failure is recorded in
``results.json`` and processing continues with the remaining files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..utils.errors import FileTooLargeError, InvalidFileError
from .pdf24_client import run_ocr_with_retry

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
_SAFE_NAME_RE = re.compile(r"[^\w.\-]")


@dataclass
class FileOutcome:
    """Outcome of OCR for a single file in the batch."""

    filename: str  # original filename as uploaded
    output_filename: str | None  # name inside the output zip
    status: str  # "success" | "failed"
    error: str | None
    bytes: bytes | None  # None when failed
    size_bytes: int  # input size, recorded for results.json


# Signature for the per-file progress callback.
BatchProgress = Callable[[int, int, str, str], Awaitable[None]]


def safe_output_name(name: str) -> str:
    """Sanitize a filename for inclusion in the output ZIP.

    Strips directory components and replaces characters that are
    unsafe in filenames or that some ZIP tools dislike.
    """
    base = Path(name).name or "file.pdf"
    safe = _SAFE_NAME_RE.sub("_", base)
    return f"ocr_{safe}"


async def save_upload_to_temp(upload, max_size: int) -> tuple[Path, str, int]:
    """Stream an ``UploadFile`` to a temp PDF, validating magic + size.

    Returns ``(path, original_filename, size_bytes)``. Raises
    ``FileTooLargeError`` or ``InvalidFileError`` on bad input. The
    caller is responsible for deleting the returned temp file.
    """
    filename = upload.filename or "file.pdf"
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, path_str = tempfile.mkstemp(
        suffix=".pdf", prefix=f"batch_in_{uuid.uuid4().hex}_", dir=str(settings.tmp_dir)
    )
    os.close(fd)
    path = Path(path_str)

    total = 0
    try:
        with open(path, "wb") as f:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise FileTooLargeError(
                        f"File '{filename}' exceeds maximum size of {max_size} bytes"
                    )
                f.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    if total == 0:
        path.unlink(missing_ok=True)
        raise InvalidFileError(f"File '{filename}' is empty")

    with open(path, "rb") as f:
        head = f.read(8)
    if not head.startswith(PDF_MAGIC):
        path.unlink(missing_ok=True)
        raise InvalidFileError(
            f"File '{filename}' is not a valid PDF (missing %PDF- header)"
        )

    return path, filename, total


async def process_batch(
    files: list[tuple[Path, str, int]],
    lang: str,
    on_file_done: BatchProgress | None = None,
) -> list[FileOutcome]:
    """Run OCR for each file with bounded concurrency.

    ``files`` is a list of ``(temp_path, original_filename, size_bytes)``
    tuples. Per-file failures are caught and recorded; they do not
    abort the batch. Returns outcomes in the same order as the input.
    """
    settings = get_settings()
    sem = asyncio.Semaphore(settings.batch_concurrency)

    outcomes: list[FileOutcome | None] = [None] * len(files)
    completed = 0
    completed_lock = asyncio.Lock()

    async def run_one(idx: int, file_path: Path, filename: str, size: int) -> None:
        nonlocal completed
        async with sem:
            try:
                result_bytes = await run_ocr_with_retry(
                    file_path,
                    lang=lang,
                    poll_interval=settings.async_poll_interval_seconds,
                )
                outcomes[idx] = FileOutcome(
                    filename=filename,
                    output_filename=safe_output_name(filename),
                    status="success",
                    error=None,
                    bytes=result_bytes,
                    size_bytes=size,
                )
            except Exception as e:
                logger.exception("Batch: failed to OCR '%s'", filename)
                outcomes[idx] = FileOutcome(
                    filename=filename,
                    output_filename=None,
                    status="failed",
                    error=str(e),
                    bytes=None,
                    size_bytes=size,
                )
            finally:
                file_path.unlink(missing_ok=True)

        async with completed_lock:
            completed += 1
            if on_file_done is not None:
                await on_file_done(
                    completed,
                    len(files),
                    filename,
                    f"Processed {filename} ({completed}/{len(files)})",
                )

    tasks = [run_one(i, p, fn, sz) for i, (p, fn, sz) in enumerate(files)]
    await asyncio.gather(*tasks)

    # All entries must be filled by now; assert for the type checker.
    assert all(o is not None for o in outcomes)
    return [o for o in outcomes if o is not None]


def package_zip(outcomes: list[FileOutcome], output_path: Path) -> Path:
    """Write OCR'd PDFs and a ``results.json`` summary into a ZIP.

    The ZIP contains:
    - one ``ocr_<original_name>.pdf`` per successful file
    - a ``results.json`` with per-file status, sizes, and any errors
    """
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)

    file_entries: list[dict] = []
    for o in outcomes:
        file_entries.append(
            {
                "filename": o.filename,
                "status": o.status,
                "output_filename": o.output_filename,
                "error": o.error,
                "size_bytes_input": o.size_bytes,
                "size_bytes_output": len(o.bytes) if o.bytes else 0,
            }
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(outcomes),
        "successful": sum(1 for o in outcomes if o.status == "success"),
        "failed": sum(1 for o in outcomes if o.status == "failed"),
        "files": file_entries,
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for o in outcomes:
            if o.status == "success" and o.bytes and o.output_filename:
                zf.writestr(o.output_filename, o.bytes)
        zf.writestr("results.json", json.dumps(summary, indent=2))

    return output_path
