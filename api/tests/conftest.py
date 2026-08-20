"""Shared pytest fixtures.

Sets the bearer token env var before any app imports happen, then
provides the FastAPI test client, a valid auth header, a sample PDF,
and a respx mock for the PDF24 server cluster.
"""
from __future__ import annotations

import os
import re

# Must be set before importing the app, since pydantic-settings reads
# env at construction time.
os.environ.setdefault("API_BEARER_TOKEN", "test-token-12345")
os.environ.setdefault("TMP_DIR", "./tmp_test")

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

URL_PATTERN = re.compile(r"^https://filetools\d+\.pdf24\.org/.*$")
SAMPLE_PDF = b"%PDF-1.4\n% fake pdf for testing\n%%EOF\n"


def _pdf24_handler(request):
    """Dispatch mocked PDF24 responses based on the action query param."""
    from httpx import Response

    url = str(request.url)
    if "action=upload" in url:
        return Response(200, json=[{"file": "test-file-id"}])
    if "action=ocrPdf" in url:
        return Response(200, json={"jobId": "test-job-id"})
    if "action=getStatus" in url:
        return Response(
            200,
            json={
                "status": "done",
                "job": {"progress.msg": "Recognizing text, page 3 of 10"},
            },
        )
    if "action=downloadJobResult" in url:
        return Response(200, content=SAMPLE_PDF, headers={"content-type": "application/pdf"})
    return Response(404, json={"error": "unknown action"})


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Settings are cached; clear before and after each test for isolation."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token-12345"}


@pytest.fixture
def sample_pdf() -> bytes:
    return SAMPLE_PDF
