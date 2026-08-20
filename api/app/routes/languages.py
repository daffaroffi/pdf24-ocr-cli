"""Static list of supported OCR languages.

The three entries here are mapped 1:1 in
``services.pdf24_client.LANG_MAP`` from a 2-letter ISO code to the
3-letter Tesseract code. Any other value passed by the user is
forwarded to PDF24 as-is, so additional Tesseract languages can be
used without code changes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import verify_bearer_token

router = APIRouter(prefix="/api/v1", tags=["meta"])

_LANGUAGES = [
    {"code": "id", "name": "Indonesian", "tesseract_code": "ind"},
    {"code": "en", "name": "English", "tesseract_code": "eng"},
    {"code": "ar", "name": "Arabic", "tesseract_code": "ara"},
]


@router.get(
    "/languages",
    summary="List the languages that have a 2-letter ISO shortcut",
)
async def list_languages(_token: str = Depends(verify_bearer_token)) -> dict:
    return {
        "languages": _LANGUAGES,
        "note": (
            "Any Tesseract 3-letter language code is also accepted as "
            "the 'lang' parameter and forwarded to PDF24 unchanged."
        ),
    }
