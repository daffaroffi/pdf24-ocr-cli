"""Tests for the asynchronous OCR endpoint and the job store."""
from __future__ import annotations

import asyncio
import re
import time

import httpx
import respx

from app.services.job_store import JobStatus

URL_PATTERN = re.compile(r"^https://filetools\d+\.pdf24\.org/.*$")
SAMPLE_RESULT_PDF = b"%PDF-1.4\n% async result\n%%EOF\n"


def _pdf24_side_effect(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "action=upload" in url:
        return httpx.Response(200, json=[{"file": "fid"}])
    if "action=ocrPdf" in url:
        return httpx.Response(200, json={"jobId": "jid"})
    if "action=getStatus" in url:
        return httpx.Response(200, json={"status": "done"})
    if "action=downloadJobResult" in url:
        return httpx.Response(200, content=SAMPLE_RESULT_PDF)
    return httpx.Response(404)


def test_async_create_requires_auth(client, sample_pdf):
    r = client.post(
        "/api/v1/ocr/async",
        files={"file": ("in.pdf", sample_pdf, "application/pdf")},
    )
    assert r.status_code == 401


def test_async_full_lifecycle(client, auth_headers, sample_pdf):
    """The respx mock must stay active for the entire test, including
    while the background task makes its HTTP calls. Keeping the
    ``with respx.mock()`` block open for the whole test ensures that.
    """
    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=_pdf24_side_effect)
        router.get(URL_PATTERN).mock(side_effect=_pdf24_side_effect)

        r = client.post(
            "/api/v1/ocr/async",
            headers=auth_headers,
            files={"file": ("in.pdf", sample_pdf, "application/pdf")},
            data={"lang": "id"},
        )
        assert r.status_code == 202
        body = r.json()
        job_id = body["job_id"]
        assert body["status"] == JobStatus.QUEUED

        # Wait for the background task to finish.
        deadline = time.time() + 5
        final_status = None
        while time.time() < deadline:
            sr = client.get(
                f"/api/v1/ocr/async/{job_id}", headers=auth_headers
            )
            assert sr.status_code == 200
            final_status = sr.json()["status"]
            if final_status in (JobStatus.DONE, JobStatus.ERROR):
                break
            time.sleep(0.05)

        assert final_status == JobStatus.DONE

        rr = client.get(
            f"/api/v1/ocr/async/{job_id}/result", headers=auth_headers
        )
        assert rr.status_code == 200
        assert rr.content == SAMPLE_RESULT_PDF


def test_async_status_404_for_unknown_job(client, auth_headers):
    r = client.get(
        "/api/v1/ocr/async/does-not-exist", headers=auth_headers
    )
    assert r.status_code == 404
    assert r.json()["error"] == "job_not_found"


def test_async_result_before_done_returns_425(client, auth_headers, sample_pdf):
    """If the job is still running, /result must report not ready."""
    with respx.mock(assert_all_called=False) as router:
        # All POSTs (upload, ocrPdf, getStatus) and GETs (download) go
        # through the same handler. getStatus is a POST in PDF24, so the
        # handler must return 'processing' for it to keep the job alive.
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "action=upload" in url:
                return httpx.Response(200, json=[{"file": "fid"}])
            if "action=ocrPdf" in url:
                return httpx.Response(200, json={"jobId": "jid"})
            if "action=getStatus" in url:
                return httpx.Response(200, json={"status": "processing"})
            if "action=downloadJobResult" in url:
                return httpx.Response(200, content=SAMPLE_RESULT_PDF)
            return httpx.Response(404)

        router.post(URL_PATTERN).mock(side_effect=handler)
        router.get(URL_PATTERN).mock(side_effect=handler)

        r = client.post(
            "/api/v1/ocr/async",
            headers=auth_headers,
            files={"file": ("in.pdf", sample_pdf, "application/pdf")},
        )
        job_id = r.json()["job_id"]

        # Give the background task a moment to start polling.
        time.sleep(0.2)

        rr = client.get(
            f"/api/v1/ocr/async/{job_id}/result", headers=auth_headers
        )
        assert rr.status_code == 425
        assert rr.json()["error"] == "job_not_ready"


def test_job_store_create_and_get():
    """Direct unit test of the job store (no HTTP layer)."""
    from app.services.job_store import JobStore

    store = JobStore(ttl_seconds=60, cleanup_interval_seconds=60)
    job = asyncio.run(store.create())
    assert job.status == JobStatus.QUEUED
    fetched = asyncio.run(store.get(job.id))
    assert fetched is not None
    assert fetched.id == job.id
