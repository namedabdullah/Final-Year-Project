"""SAMpai application settings.

Kept deliberately separate from the LightRAG server's argparse/``global_args`` config.
Reads ``APP_*`` / ``R2_*`` env vars from the same ``.env`` the server already loads at
import time. The server ignores these vars; we own them here.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SampaiSettings(BaseSettings):
    """Environment-driven settings for the SAMpai layer.

    Field ``app_database_url`` reads env var ``APP_DATABASE_URL`` (case-insensitive),
    ``r2_endpoint`` reads ``R2_ENDPOINT``, etc.
    """

    # env_file lets standalone tools (alembic, smoke scripts) pick up the repo-root
    # .env even when the LightRAG server's load_dotenv() hasn't run. OS env vars
    # (incl. those the server loads) still take precedence over the file.
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ── App / auth ──────────────────────────────────────────────────────────
    app_database_url: str = "postgresql+asyncpg://sampai:sampai@localhost:5432/sampai"
    app_jwt_secret: str = "change-me-in-env"
    app_jwt_expire_min: int = 1440
    app_cors_origins: str = "http://localhost:5173"
    app_upload_max_mb: int = 100

    # ── Engine registry ─────────────────────────────────────────────────────
    app_engine_idle_ttl: int = 1800
    app_max_resident_engines: int = 8

    # ── Cloudflare R2 (object storage) ──────────────────────────────────────
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "sampai-files"
    r2_presign_ttl: int = 3600

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @classmethod
    def load(cls) -> "SampaiSettings":
        return cls()
