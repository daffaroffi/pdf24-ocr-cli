"""Async client wrapping PDF24's public OCR service.

Each PDF24Client instance owns its own httpx.AsyncClient and cookie
store, so concurrent jobs do not share session state. The high-level
``run_ocr_with_retry`` helper creates a fresh client (and therefore a
fresh server from the cluster) on each retry attempt.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import get_settings
from ..utils.errors import PDF24Error

logger = logging.getLogger(__name__)

# Headers required to mimic browser requests to tools.pdf24.org.
DEFAULT_HEADERS = {
    "Origin": "https://tools.pdf24.org",
    "Referer": "https://tools.pdf24.org/en/ocr-pdf",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Map common 2-letter ISO codes to Tesseract 3-letter codes.
LANG_MAP: dict[str, str] = {
    "id": "ind",
    "en": "eng",
    "ar": "ara",
}


@dataclass
class OCRProgress:
    """Snapshot of progress for a running OCR job."""

    stage: str  # "uploading" | "processing" | "downloading" | "done" | "error"
    current_page: int = 0
    total_pages: int = 0
    message: str = ""


ProgressCallback = Callable[[OCRProgress], Awaitable[None]]

_PAGE_RE = re.compile(r"page (\d+) of (\d+)")


def tesseract_lang(lang: str) -> str:
    """Translate a 2-letter ISO code to Tesseract's 3-letter code when known."""
    return LANG_MAP.get(lang.lower(), lang)


def _pick_server(server_count: int) -> str:
    n = random.randint(0, server_count - 1)
    return f"https://filetools{n}.pdf24.org/client.php"


class PDF24Client:
    """Async client for a single PDF24 server.

    Use as an async context manager so the underlying httpx client is
    properly opened and closed. The 4-step flow (upload, start, poll,
    download) is exposed as separate methods, plus a ``run_ocr`` helper
    that wires them together.
    """

    def __init__(
        self,
        server_count: int | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._server_count = server_count or settings.pdf24_server_count
        self._timeout = timeout or settings.pdf24_request_timeout_seconds
        self._base_url = _pick_server(self._server_count)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PDF24Client:
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def base_url(self) -> str:
        return self._base_url

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PDF24Client must be used as an async context manager")
        return self._client

    async def upload(self, file_path: Path) -> str:
        """Upload a PDF file. Returns the file_id assigned by the server."""
        client = self._require_client()
        url = f"{self._base_url}?action=upload"
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/pdf")}
                resp = await client.post(url, files=files)
        except httpx.HTTPError as e:
            raise PDF24Error(f"Upload failed: {e}") from e

        if resp.status_code != 200:
            raise PDF24Error(
                f"Upload failed: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        if not isinstance(data, list) or not data:
            raise PDF24Error(f"Unexpected upload response: {resp.text[:200]}")
        file_id = data[0].get("file")
        if not file_id:
            raise PDF24Error(f"No file id in upload response: {resp.text[:200]}")
        return file_id

    async def start_ocr(self, file_id: str, lang: str = "en") -> str:
        """Start an OCR job for an uploaded file. Returns the job_id."""
        client = self._require_client()
        payload = {
            "files": [{"file": file_id}],
            "langCode": tesseract_lang(lang),
            "outputType": "pdf",
            "removeBackground": False,
            "rotatePages": False,
            "deskew": False,
            "clean": False,
            "forceOcr": True,
            "joinFiles": False,
        }
        url = f"{self._base_url}?action=ocrPdf"
        try:
            resp = await client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise PDF24Error(f"OCR job start failed: {e}") from e

        if resp.status_code != 200:
            raise PDF24Error(
                f"OCR job start failed: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        job_id = data.get("jobId")
        if not job_id:
            raise PDF24Error(f"No jobId in start response: {resp.text[:200]}")
        return job_id

    async def poll_status(self, job_id: str) -> tuple[str, OCRProgress]:
        """Poll the job status once. Returns ``(status, progress)``.

        ``status`` is ``"done"``, ``"error"``, or ``"processing"``. When
        ``"error"`` a ``PDF24Error`` is raised with the server's message.
        """
        client = self._require_client()
        url = f"{self._base_url}?action=getStatus"
        try:
            resp = await client.post(url, json={"jobId": job_id})
        except httpx.HTTPError as e:
            raise PDF24Error(f"Status poll failed: {e}") from e

        if resp.status_code != 200:
            raise PDF24Error(
                f"Status poll failed: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        status = data.get("status", "")

        if status == "error":
            err = data.get("error", "Unknown error")
            raise PDF24Error(f"OCR failed on server: {err}")

        progress = OCRProgress(stage="processing")
        job = data.get("job") or {}
        msg = job.get("progress.msg") or job.get("description") or "Processing..."
        progress.message = msg
        m = _PAGE_RE.search(msg)
        if m:
            progress.current_page = int(m.group(1))
            progress.total_pages = int(m.group(2))

        return status, progress

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Poll until the job is done. Raises ``PDF24Error`` on failure."""
        while True:
            status, progress = await self.poll_status(job_id)
            if status == "done":
                if on_progress:
                    await on_progress(OCRProgress(stage="done", message="Complete"))
                return
            if on_progress:
                await on_progress(progress)
            await asyncio.sleep(poll_interval)

    async def download(self, job_id: str) -> bytes:
        """Download the OCR'd PDF. Returns the binary content."""
        client = self._require_client()
        url = f"{self._base_url}?action=downloadJobResult&jobId={job_id}"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            raise PDF24Error(f"Download failed: {e}") from e

        if resp.status_code != 200:
            raise PDF24Error(
                f"Download failed: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        return resp.content

    async def run_ocr(
        self,
        file_path: Path,
        lang: str = "en",
        poll_interval: float = 2.0,
        on_progress: ProgressCallback | None = None,
    ) -> bytes:
        """High-level helper: upload -> start -> poll -> download.

        Raises ``PDF24Error`` on any failure. Use ``run_ocr_with_retry``
        for automatic server fallback on failure.
        """
        if on_progress:
            await on_progress(OCRProgress(stage="uploading", message="Uploading"))
        file_id = await self.upload(file_path)

        if on_progress:
            await on_progress(OCRProgress(stage="processing", message="Starting OCR"))
        job_id = await self.start_ocr(file_id, lang)

        await self.wait_for_completion(
            job_id, poll_interval=poll_interval, on_progress=on_progress
        )

        if on_progress:
            await on_progress(OCRProgress(stage="downloading", message="Downloading result"))
        return await self.download(job_id)


async def run_ocr_with_retry(
    file_path: Path,
    lang: str = "en",
    poll_interval: float = 2.0,
    on_progress: ProgressCallback | None = None,
    max_retries: int | None = None,
) -> bytes:
    """Run OCR with server fallback.

    On failure, picks a new random server and retries up to
    ``pdf24_max_retries`` times (from settings). Sleeps 2s between
    attempts to avoid hammering the cluster.
    """
    settings = get_settings()
    retries = max_retries or settings.pdf24_max_retries
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with PDF24Client() as client:
                logger.info("OCR attempt %d/%d using %s", attempt, retries, client.base_url)
                return await client.run_ocr(
                    file_path,
                    lang,
                    poll_interval=poll_interval,
                    on_progress=on_progress,
                )
        except PDF24Error as e:
            last_error = e
            logger.warning("OCR attempt %d/%d failed: %s", attempt, retries, e)
            if attempt < retries:
                await asyncio.sleep(2)

    raise PDF24Error(
        f"All {retries} OCR attempts failed; last error: {last_error}"
    )
