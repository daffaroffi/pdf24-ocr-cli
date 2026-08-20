"""Custom exception classes mapped to HTTP responses in main.py."""
from typing import Any


class APIError(Exception):
    """Base class for all expected, user-facing errors."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.error_code, "message": self.message}
        if self.detail is not None:
            body["detail"] = self.detail
        return body


class FileTooLargeError(APIError):
    status_code = 413
    error_code = "file_too_large"


class InvalidFileError(APIError):
    status_code = 422
    error_code = "invalid_file"


class PDF24Error(APIError):
    """Generic failure from the upstream PDF24 service."""
    status_code = 502
    error_code = "pdf24_error"


class PDF24TimeoutError(APIError):
    status_code = 504
    error_code = "pdf24_timeout"


class JobNotFoundError(APIError):
    status_code = 404
    error_code = "job_not_found"


class JobNotReadyError(APIError):
    status_code = 425
    error_code = "job_not_ready"
