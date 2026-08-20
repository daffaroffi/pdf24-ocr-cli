"""Pydantic models for request/response bodies.

Used primarily for OpenAPI documentation. The sync and async routes
read the request as a raw ``Request`` to dispatch on Content-Type
(multipart vs JSON), so the actual validation is done in
``services.input_handlers``. These schemas still appear in the docs
so consumers can see the expected JSON shape.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class Base64OCRRequest(BaseModel):
    """OCR request with a base64-encoded PDF body."""

    file_b64: str = Field(
        ...,
        description="Base64-encoded PDF content. Data URIs ('data:application/pdf;base64,...') are also accepted.",
    )
    lang: str = Field(
        default="en",
        description="Language code. Supports ISO 2-letter (id, en, ar) or Tesseract 3-letter (ind, eng, ara).",
    )


class URLOCRRequest(BaseModel):
    """OCR request with a URL pointing to a PDF file."""

    url: HttpUrl = Field(..., description="HTTP or HTTPS URL to a PDF file (max 200MB).")
    lang: str = Field(
        default="en",
        description="Language code. Supports ISO 2-letter (id, en, ar) or Tesseract 3-letter (ind, eng, ara).",
    )
