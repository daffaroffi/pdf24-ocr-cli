"""Bearer token authentication for protected endpoints.

Uses FastAPI's ``HTTPBearer`` security scheme so the OpenAPI docs at
``/docs`` show the lock icon and a token field. Comparison is
constant-time to avoid timing leaks of the configured token.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer token from API_BEARER_TOKEN env var")


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the ``Authorization: Bearer <token>`` header.

    Returns the verified token string on success. Raises 401 when the
    header is missing or malformed, and 403 when the token does not
    match the configured value.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "missing_authorization",
                "message": "Authorization header with Bearer token is required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(credentials.credentials, settings.api_bearer_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "invalid_token",
                "message": "The provided bearer token is invalid",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
