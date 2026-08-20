"""Tests for the batch OCR endpoint."""
from __future__ import annotations

import io
import json
import os
import re
import time
import zipfile

import httpx
import pytest
import respx

from app.config import get_settings
from app.services.job_store import JobStatus

URL_PATTERN = re.compile(r"^https://filetools\d+\.pdf24\.org/.*$")
SAMPLE_RESULT_PDF = b"%PDF-1.4\n% batch result\n%%EOF\n"


def _ok_handler(request: httpx.Request) -> httpx.Response:
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


@pytest.fixture
def low_retries():
    """Force PDF24_MAX_RETRIES=1 so failure tests don't take 3x longer."""
    old = os.environ.get("PDF24_MAX_RETRIES")
    os.environ["PDF24_MAX_RETRIES"] = "1"
    get_settings.cache_clear()
    yield
    if old is None:
        os.environ.pop("PDF24_MAX_RETRIES", None)
    else:
        os.environ["PDF24_MAX_RETRIES"] = old
    get_settings.cache_clear()


def test_batch_create_requires_auth(client, sample_pdf):
    r = client.post(
        "/api/v1/ocr/batch-async",
        files=[("files", ("a.pdf", sample_pdf, "application/pdf"))],
    )
    assert r.status_code == 401


def test_batch_rejects_empty_file_list(client, auth_headers):
    r = client.post(
        "/api/v1/ocr/batch-async",
        headers=auth_headers,
        files=[],
    )
    assert r.status_code == 422
    assert r.json()["error"] in ("invalid_file", "validation_error")


def test_batch_rejects_non_pdf_file(client, auth_headers):
    r = client.post(
        "/api/v1/ocr/batch-async",
        headers=auth_headers,
        files=[("files", ("bad.txt", b"not a pdf", "text/plain"))],
    )
    assert r.status_code == 422
    assert r.json()["error"] in ("invalid_file", "validation_error")


def test_batch_full_lifecycle(client, auth_headers, sample_pdf):
    """Three files, all succeed, ZIP returned with all PDFs + results.json."""
    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=_ok_handler)
        router.get(URL_PATTERN).mock(side_effect=_ok_handler)

        r = client.post(
            "/api/v1/ocr/batch-async",
            headers=auth_headers,
            files=[
                ("files", ("doc1.pdf", sample_pdf, "application/pdf")),
                ("files", ("doc2.pdf", sample_pdf, "application/pdf")),
                ("files", ("doc3.pdf", sample_pdf, "application/pdf")),
            ],
            data={"lang": "id"},
        )
        assert r.status_code == 202
        body = r.json()
        job_id = body["job_id"]
        assert body["total_files"] == 3
        assert body["status"] == JobStatus.QUEUED

        # Wait for completion. The respx mock must stay active for the
        # entire test (background task makes HTTP calls here).
        deadline = time.time() + 10
        final_status = None
        while time.time() < deadline:
            sr = client.get(
                f"/api/v1/ocr/async/{job_id}", headers=auth_headers
            )
            assert sr.status_code == 200
            final_status = sr.json()["status"]
            if final_status in (JobStatus.DONE, JobStatus.ERROR):
                break
            time.sleep(0.1)

        assert final_status == JobStatus.DONE

        # Status contains batch fields.
        status_body = client.get(
            f"/api/v1/ocr/async/{job_id}", headers=auth_headers
        ).json()
        assert "batch" in status_body
        batch = status_body["batch"]
        assert batch["total_files"] == 3
        assert batch["files_completed"] == 3
        assert batch["files_failed"] == 0

        # Download the result ZIP.
        rr = client.get(
            f"/api/v1/ocr/async/{job_id}/result", headers=auth_headers
        )
        assert rr.status_code == 200
        assert rr.headers["content-type"] == "application/zip"

        # Verify ZIP contents.
        zf = zipfile.ZipFile(io.BytesIO(rr.content))
        names = zf.namelist()
        assert "results.json" in names
        assert "ocr_doc1.pdf" in names
        assert "ocr_doc2.pdf" in names
        assert "ocr_doc3.pdf" in names

        summary = json.loads(zf.read("results.json"))
        assert summary["total_files"] == 3
        assert summary["successful"] == 3
        assert summary["failed"] == 0


def test_batch_partial_failure(client, auth_headers, sample_pdf, low_retries):
    """When one file fails, the batch continues and records the failure.

    The handler forces a 500 on the second upload attempt. With
    PDF24_MAX_RETRIES=1 (set by the ``low_retries`` fixture) that
    failure sticks within the test deadline.
    """
    state = {"uploads": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "action=upload" in str(request.url):
            state["uploads"] += 1
            if state["uploads"] == 2:
                return httpx.Response(500, text="permadown")
        return _ok_handler(request)

    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=handler)
        router.get(URL_PATTERN).mock(side_effect=_ok_handler)

        r = client.post(
            "/api/v1/ocr/batch-async",
            headers=auth_headers,
            files=[
                ("files", (f"file_{i}.pdf", sample_pdf, "application/pdf"))
                for i in range(5)
            ],
            data={"lang": "en"},
        )
        assert r.status_code == 202
        job_id = r.json()["job_id"]

        deadline = time.time() + 20
        while time.time() < deadline:
            sr = client.get(
                f"/api/v1/ocr/async/{job_id}", headers=auth_headers
            )
            if sr.json()["status"] == JobStatus.DONE:
                break
            time.sleep(0.1)

        sr = client.get(
            f"/api/v1/ocr/async/{job_id}", headers=auth_headers
        )
        assert sr.json()["status"] == JobStatus.DONE
        # At least one file should have failed. Exact count depends on
        # retry timing; we just verify the mixed outcome.
        assert sr.json()["batch"]["files_failed"] >= 1
        assert sr.json()["batch"]["files_completed"] >= 1

        rr = client.get(
            f"/api/v1/ocr/async/{job_id}/result", headers=auth_headers
        )
        assert rr.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(rr.content))
        summary = json.loads(zf.read("results.json"))
        assert summary["total_files"] == 5
        assert summary["failed"] >= 1
        assert summary["successful"] >= 1
        assert summary["successful"] + summary["failed"] == 5
        # The failed entries have an error message.
        failed = [f for f in summary["files"] if f["status"] == "failed"]
        assert all(f["error"] for f in failed)
