"""Normalize incoming requests (multipart, base64, URL) to a temp PDF file.

Every handler returns a ``(path, lang)`` tuple. The caller is
responsible for deleting ``path`` after the job finishes.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..utils.errors import FileTooLargeError, InvalidFileError

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
MAX_URL_FETCH_BYTES = 200 * 1024 * 1024  # 200MB cap for URL downloads
_DATA_URI_RE = re.compile(r"^data:[\w./+-]+;base64,(.+)$", re.IGNORECASE)


def _validate_pdf_magic(path: Path) -> None:
    """Check that the file starts with the PDF magic bytes."""
    with open(path, "rb") as f:
        head = f.read(8)
    if not head.startswith(PDF_MAGIC):
        raise InvalidFileError("File does not appear to be a valid PDF (missing %PDF- header)")


def _write_chunks(tmp_path: Path, chunks, max_size: int) -> None:
    """Write an iterator of bytes-like chunks to ``tmp_path``, enforcing size limit."""
    total = 0
    try:
        with open(tmp_path, "wb") as f:
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_size:
                    raise FileTooLargeError(
                        f"Input exceeds maximum size of {max_size} bytes"
                    )
                f.write(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise InvalidFileError("Empty file received")
    _validate_pdf_magic(tmp_path)


def _new_temp_pdf() -> Path:
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(
        suffix=".pdf", prefix="ocr_input_", dir=str(settings.tmp_dir)
    )
    os.close(fd)
    return Path(path)


async def from_multipart(form, max_size: int) -> tuple[Path, str]:
    """Handle a ``multipart/form-data`` upload with a ``file`` field and a ``lang`` field."""
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise InvalidFileError("Multipart request must include a 'file' field with a PDF")
    lang_raw = form.get("lang")
    lang = str(lang_raw) if lang_raw is not None else "en"

    tmp = _new_temp_pdf()
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    _write_chunks(tmp, chunks, max_size)
    return tmp, lang


async def from_base64(body: dict[str, Any], max_size: int) -> tuple[Path, str]:
    """Handle a JSON body with ``file_b64`` and ``lang`` fields."""
    raw = body.get("file_b64")
    if not isinstance(raw, str) or not raw:
        raise InvalidFileError("JSON body must include a non-empty 'file_b64' string")

    # Accept data URIs: data:application/pdf;base64,XXXX
    m = _DATA_URI_RE.match(raw)
    payload = m.group(1) if m else raw

    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise InvalidFileError(f"file_b64 is not valid base64: {e}") from e

    if len(data) > max_size:
        raise FileTooLargeError(
            f"Decoded base64 exceeds maximum size of {max_size} bytes"
        )
    if not data:
        raise InvalidFileError("Decoded base64 is empty")

    lang = str(body.get("lang") or "en")
    tmp = _new_temp_pdf()
    try:
        tmp.write_bytes(data)
        _validate_pdf_magic(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, lang


async def from_url(body: dict[str, Any], max_size: int) -> tuple[Path, str]:
    """Handle a JSON body with ``url`` and ``lang`` fields. Downloads the PDF."""
    url = body.get("url")
    if not isinstance(url, str) or not url:
        raise InvalidFileError("JSON body must include a non-empty 'url' string")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise InvalidFileError("url must start with http:// or https://")

    fetch_limit = min(max_size, MAX_URL_FETCH_BYTES)
    lang = str(body.get("lang") or "en")
    tmp = _new_temp_pdf()

    try:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers={"User-Agent": "pdf24-ocr-api/0.1"}
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise InvalidFileError(
                        f"URL fetch returned HTTP {resp.status_code}"
                    )
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > fetch_limit:
                    raise FileTooLargeError(
                        f"Remote file is larger than the {fetch_limit} byte limit"
                    )
                chunks: list[bytes] = []
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    chunks.append(chunk)
                _write_chunks(tmp, chunks, fetch_limit)
    except (FileTooLargeError, InvalidFileError):
        raise
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise InvalidFileError(f"Failed to download URL: {e}") from e

    return tmp, lang
