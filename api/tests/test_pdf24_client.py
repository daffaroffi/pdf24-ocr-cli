"""Unit tests for the PDF24 client.

These do not go through the HTTP layer; they exercise the client
class directly. ``respx`` mocks the upstream PDF24 server.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.services.pdf24_client import (
    run_ocr_with_retry,
    tesseract_lang,
)
from app.utils.errors import PDF24Error

URL_PATTERN = __import__("re").compile(r"^https://filetools\d+\.pdf24\.org/.*$")


def test_tesseract_lang_maps_known_codes():
    assert tesseract_lang("id") == "ind"
    assert tesseract_lang("en") == "eng"
    assert tesseract_lang("ar") == "ara"


def test_tesseract_lang_passes_through_unknown():
    # 3-letter Tesseract codes are passed through unchanged.
    assert tesseract_lang("fra") == "fra"
    assert tesseract_lang("jpn") == "jpn"


@pytest.mark.asyncio
async def test_run_ocr_happy_path(tmp_path: Path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")

    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=lambda req: _handler(req, "ok"))
        router.get(URL_PATTERN).mock(side_effect=lambda req: _handler(req, "ok"))

        result = await run_ocr_with_retry(pdf, lang="id", poll_interval=0.0)
        assert result.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_run_ocr_retries_then_succeeds(tmp_path: Path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")

    call_count = {"n": 0}

    def flaky(request):
        call_count["n"] += 1
        # First call returns 500; subsequent calls succeed.
        if call_count["n"] == 1:
            return httpx.Response(500, text="boom")
        return _handler(request, "ok")

    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=flaky)
        router.get(URL_PATTERN).mock(side_effect=flaky)

        result = await run_ocr_with_retry(
            pdf, lang="en", poll_interval=0.0, max_retries=2
        )
        assert result.startswith(b"%PDF-")
        # First attempt failed, second attempt succeeded.
        assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_run_ocr_raises_after_max_retries(tmp_path: Path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")

    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(return_value=httpx.Response(500, text="nope"))

        with pytest.raises(PDF24Error) as exc_info:
            await run_ocr_with_retry(pdf, lang="en", poll_interval=0.0, max_retries=2)
        assert "All 2 OCR attempts failed" in str(exc_info.value)


def _handler(request, mode: str):
    """Standalone handler for respx side_effect that does not capture module state."""
    url = str(request.url)
    if "action=upload" in url:
        return httpx.Response(200, json=[{"file": "fid"}])
    if "action=ocrPdf" in url:
        return httpx.Response(200, json={"jobId": "jid"})
    if "action=getStatus" in url:
        return httpx.Response(200, json={"status": "done"})
    if "action=downloadJobResult" in url:
        return httpx.Response(200, content=b"%PDF-1.4\nresult\n%%EOF")
    return httpx.Response(404)
