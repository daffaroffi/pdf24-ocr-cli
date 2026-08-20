"""Liveness and upstream reachability check.

No auth required. Result is cached for 5 minutes so high-frequency
monitors do not hammer the upstream service.
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

from .. import __version__

router = APIRouter(tags=["meta"])

_PING_CACHE_SECONDS = 300
_PING_TARGET = "https://tools.pdf24.org/"
_last_ping_at: float = 0.0
_last_ping_result: bool = False


async def _ping_pdf24() -> bool:
    global _last_ping_at, _last_ping_result
    now = time.time()
    if now - _last_ping_at < _PING_CACHE_SECONDS:
        return _last_ping_result
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(_PING_TARGET)
            _last_ping_result = resp.status_code == 200
    except Exception:
        _last_ping_result = False
    _last_ping_at = now
    return _last_ping_result


@router.get(
    "/health",
    summary="Liveness check (no auth). Reports upstream PDF24 reachability.",
)
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "pdf24_reachable": await _ping_pdf24(),
    }
