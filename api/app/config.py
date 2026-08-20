"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values come from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Auth
    api_bearer_token: str = Field(..., description="Bearer token required for all non-health endpoints")

    # File size limits (in MB)
    max_file_size_sync_mb: int = Field(default=5, ge=1, le=100)
    max_file_size_async_mb: int = Field(default=100, ge=1, le=500)

    # Timeouts
    sync_timeout_seconds: int = Field(default=120, ge=10, le=600)
    async_poll_interval_seconds: int = Field(default=2, ge=1, le=10)
    pdf24_request_timeout_seconds: int = Field(default=300, ge=30, le=600)

    # Job lifecycle
    job_ttl_seconds: int = Field(default=7200, ge=60, le=86400)
    job_cleanup_interval_seconds: int = Field(default=1800, ge=60, le=3600)

    # CORS
    cors_origins: str = Field(default="*")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="text", description="text or json")

    # Storage
    tmp_dir: Path = Field(default=Path("./tmp"))

    # PDF24 client
    pdf24_max_retries: int = Field(default=3, ge=1, le=10)
    pdf24_server_count: int = Field(default=30, ge=1, le=50)

    # Batch processing
    batch_max_files: int = Field(default=50, ge=1, le=500)
    batch_max_total_size_mb: int = Field(default=500, ge=10, le=5000)
    batch_concurrency: int = Field(default=3, ge=1, le=10)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_file_size_sync_bytes(self) -> int:
        return self.max_file_size_sync_mb * 1024 * 1024

    @property
    def max_file_size_async_bytes(self) -> int:
        return self.max_file_size_async_mb * 1024 * 1024

    @property
    def batch_max_total_size_bytes(self) -> int:
        return self.batch_max_total_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Call this from app code, not Settings() directly."""
    return Settings()  # type: ignore[call-arg]
