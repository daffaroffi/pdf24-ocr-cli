"""Synchronous OCR endpoint.

Accepts a PDF via multipart, base64, or URL and returns the OCR'd
PDF as binary. Blocks until completion or ``sync_timeout_seconds``
(default 120s). For larger files or longer jobs, use the async
endpoint at ``POST /api/v1/ocr/async``.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..auth import verify_bearer_token
from ..config import get_settings
from ..services.input_handlers import from_base64, from_multipart, from_url
from ..services.pdf24_client import run_ocr_with_retry
from ..utils.errors import InvalidFileError, PDF24TimeoutError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])


_OPENAPI_EXAMPLES = {
    "application/json": {
        "schema": {"oneOf": [
            {"$ref": "#/components/schemas/Base64OCRRequest"},
            {"$ref": "#/components/schemas/URLOCRRequest"},
        ]},
        "examples": {
            "base64": {
                "summary": "Base64 input",
                "value": {
                    "file_b64": "JVBERi0xLjQKJcKlwrHDqwoxIDAgb2JqCjw8IC9UaXRsZSAoU2FtcGxlKSAvQXV0aG9yICg... (truncated)",
                    "lang": "id",
                },
            },
            "url": {
                "summary": "URL input",
                "value": {
                    "url": "https://example.com/sample.pdf",
                    "lang": "en",
                },
            },
        },
    }
}


@router.post(
    "/sync",
    response_class=Response,
    responses={
        200: {
            "description": "OCR'd PDF as binary",
            "content": {"application/pdf": {}},
        },
        413: {"description": "Input file too large"},
        422: {"description": "Invalid PDF or bad request"},
        502: {"description": "Upstream PDF24 service failed"},
        504: {"description": "OCR did not complete within sync_timeout_seconds"},
    },
    openapi_extra={"requestBody": {"content": _OPENAPI_EXAMPLES}},
    summary="OCR a PDF and return the result inline",
)
async def ocr_sync(
    request: Request,
    _token: str = Depends(verify_bearer_token),
) -> Response:
    settings = get_settings()
    max_size = settings.max_file_size_sync_bytes
    content_type = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in content_type:
        form = await request.form()
        path, lang = await from_multipart(form, max_size)
    elif "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise InvalidFileError("JSON body must be an object")
        if "file_b64" in body:
            path, lang = await from_base64(body, max_size)
        elif "url" in body:
            path, lang = await from_url(body, max_size)
        else:
            raise InvalidFileError(
                "JSON body must include either 'file_b64' or 'url'"
            )
    else:
        raise InvalidFileError(
            "Unsupported Content-Type. Use multipart/form-data or application/json"
        )

    try:
        try:
            result = await asyncio.wait_for(
                run_ocr_with_retry(
                    path,
                    lang=lang,
                    poll_interval=settings.async_poll_interval_seconds,
                ),
                timeout=settings.sync_timeout_seconds,
            )
        except asyncio.TimeoutError as e:
            raise PDF24TimeoutError(
                f"OCR did not complete within {settings.sync_timeout_seconds} seconds"
            ) from e
    finally:
        path.unlink(missing_ok=True)

    return Response(
        content=result,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ocr_result.pdf"'},
    )
