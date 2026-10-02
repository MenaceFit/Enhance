"""Application settings (environment variables, ``.env`` supported)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore")

    # --- general -----------------------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "Vinted AI"
    public_app_url: str = "http://localhost:3000"
    api_prefix: str = "/api/v1"
    secret_key: str = Field(default="dev-insecure-change-me-please-0123456789", min_length=32)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    log_level: str = "INFO"

    # --- database ----------------------------------------------------------------------
    database_url: str = f"sqlite:///{API_ROOT / 'var' / 'dev.db'}"
    db_echo: bool = False
    auto_create_schema: bool = True  # dev/test convenience; production runs Alembic migrations

    # --- storage -----------------------------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: Path = API_ROOT / "var" / "storage"
    s3_bucket: str = "vinted-ai"
    s3_endpoint_url: str | None = None  # e.g. https://<account>.r2.cloudflarestorage.com or MinIO
    s3_public_endpoint_url: str | None = None  # host used in presigned URLs when it differs (Docker/MinIO)
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_server_side_encryption: str | None = "AES256"  # None for R2 (always encrypted at rest)
    signed_url_ttl_seconds: int = 3600

    # --- queue -------------------------------------------------------------------------
    job_backend: Literal["inline", "celery", "sync"] = "inline"
    redis_url: str = "redis://localhost:6379/0"
    inline_workers: int = 2

    # --- auth & security ---------------------------------------------------------------
    session_cookie_name: str = "vai_session"
    session_ttl_days: int = 30
    cookie_secure: bool = False
    admin_emails: Annotated[list[str], NoDecode] = []
    rate_limit_auth_per_minute: int = 20
    rate_limit_uploads_per_minute: int = 30

    # --- product limits ----------------------------------------------------------------
    max_upload_mb: int = 25
    max_photos_per_upload: int = 12
    max_photos_per_project: int = 12
    preview_long_side: int = 1280
    thumbnail_long_side: int = 480
    working_long_side: int = 3072
    export_sizes: dict[str, int] = {"standard": 1600, "high": 2400, "max": 3072}
    export_jpeg_quality: dict[str, int] = {"standard": 86, "high": 92, "max": 97}
    minutes_saved_per_photo: float = 4.0

    # --- credits & plans (editable at runtime by admins; these seed the DB) -------------
    guest_credits: int = 3
    credit_cost_enhance: int = 1
    plans: list[dict] = [
        {"code": "free", "name": "Free", "monthly_credits": 5, "price_cents": 0, "sort_order": 0},
        {"code": "starter", "name": "Starter", "monthly_credits": 100, "price_cents": 599, "sort_order": 1},
        {"code": "pro", "name": "Pro", "monthly_credits": 500, "price_cents": 1499, "sort_order": 2},
        {"code": "business", "name": "Business", "monthly_credits": 2000, "price_cents": 3999, "sort_order": 3},
    ]

    # --- privacy / GDPR ----------------------------------------------------------------
    default_retention_days: int = 30
    guest_retention_days: int = 2
    max_retention_days: int = 365
    privacy_policy_version: str = "2026-10-01"

    # --- billing -----------------------------------------------------------------------
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_ids: dict[str, str] = {}  # plan code → Stripe price id

    # --- AI providers ------------------------------------------------------------------
    ai_routing: str = "{}"  # JSON: {"segmentation": "rembg", "clothing_detection": "anthropic", "*": "local"}
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    replicate_api_token: str | None = None
    replicate_upscale_version: str | None = None
    rembg_model: str = "isnet-general-use"

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_emails(cls, v):
        if isinstance(v, str):
            return [e.strip().lower() for e in v.split(",") if e.strip()]
        return [e.lower() for e in v]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json

                return json.loads(v)
            return [o.strip().rstrip("/") for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key.startswith(("dev-insecure", "change-me")):
        raise RuntimeError("SECRET_KEY must be set to a random value in production")
    return s
