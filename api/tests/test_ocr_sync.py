"""Tests for the synchronous OCR endpoint.

All upstream PDF24 calls are intercepted with respx so no real
network traffic happens.
"""
from __future__ import annotations

import base64
import re

import httpx
import respx

URL_PATTERN = re.compile(r"^https://filetools\d+\.pdf24\.org/.*$")
SAMPLE_RESULT_PDF = b"%PDF-1.4\n% fake OCR result\n%%EOF\n"


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


def test_sync_requires_auth(client, sample_pdf):
    r = client.post(
        "/api/v1/ocr/sync",
        files={"file": ("in.pdf", sample_pdf, "application/pdf")},
        data={"lang": "en"},
    )
    assert r.status_code == 401


def test_sync_multipart_happy_path(client, auth_headers, sample_pdf):
    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=_pdf24_side_effect)
        router.get(URL_PATTERN).mock(side_effect=_pdf24_side_effect)

        r = client.post(
            "/api/v1/ocr/sync",
            headers=auth_headers,
            files={"file": ("in.pdf", sample_pdf, "application/pdf")},
            data={"lang": "id"},
        )

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == SAMPLE_RESULT_PDF


def test_sync_base64_happy_path(client, auth_headers, sample_pdf):
    encoded = base64.b64encode(sample_pdf).decode()
    body = {"file_b64": encoded, "lang": "en"}

    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(side_effect=_pdf24_side_effect)
        router.get(URL_PATTERN).mock(side_effect=_pdf24_side_effect)

        r = client.post(
            "/api/v1/ocr/sync",
            headers=auth_headers,
            json=body,
        )

    assert r.status_code == 200
    assert r.content == SAMPLE_RESULT_PDF


def test_sync_rejects_invalid_pdf_magic(client, auth_headers):
    bad = b"not a pdf, just some text"
    r = client.post(
        "/api/v1/ocr/sync",
        headers=auth_headers,
        files={"file": ("bad.pdf", bad, "application/pdf")},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_file"


def test_sync_rejects_missing_body_field(client, auth_headers):
    r = client.post(
        "/api/v1/ocr/sync",
        headers=auth_headers,
        json={"lang": "en"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_file"


def test_sync_rejects_unsupported_content_type(client, auth_headers):
    r = client.post(
        "/api/v1/ocr/sync",
        headers={**auth_headers, "Content-Type": "text/plain"},
        content=b"hello",
    )
    assert r.status_code == 422


def test_sync_maps_pdf24_failure_to_502(client, auth_headers, sample_pdf):
    with respx.mock(assert_all_called=False) as router:
        router.post(URL_PATTERN).mock(return_value=httpx.Response(500, text="boom"))

        r = client.post(
            "/api/v1/ocr/sync",
            headers=auth_headers,
            files={"file": ("in.pdf", sample_pdf, "application/pdf")},
        )
    # After max_retries we expect a 502.
    assert r.status_code == 502
