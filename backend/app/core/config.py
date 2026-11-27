"""Environment-driven application configuration."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SERPScope"
    environment: str = "development"
    secret_key: str = "dev-only-secret-change-before-deployment"
    # Optional independent keys. Empty values fall back to SECRET_KEY so an
    # existing deployment keeps working; set them separately to allow rotation.
    token_signing_key: str = ""
    credential_encryption_key: str = ""
    demo_email: str = "demo@serpscope.local"
    database_url: str = "sqlite:///./data/serpscope.db"
    upload_dir: str = "./data/uploads"
    export_dir: str = "./data/exports"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    job_poll_seconds: float = 0.5
    run_jobs_in_api: bool = True
    rate_limit_enabled: bool = True
    allow_self_registration: bool | None = None
    max_upload_mb: int = 50
    log_level: str = "INFO"

    # Dormant live vendor connectors. Every value is empty/off by default; no
    # provider request can be made until an operator opts in and supplies real
    # credentials through the deployment environment (never through the repo).
    live_connectors_enabled: bool = False
    gsc_client_id: str = ""
    gsc_client_secret: str = ""
    gsc_redirect_uri: str = ""
    gsc_site_url: str = ""
    ga4_client_id: str = ""
    ga4_client_secret: str = ""
    ga4_redirect_uri: str = ""
    ga4_property_id: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    vendor_request_timeout_seconds: float = 15.0
    vendor_max_rows: int = 1000

    @field_validator("database_url")
    @classmethod
    def normalise_database_url(cls, value: str) -> str:
        """Render emits postgres://; SQLAlchemy needs an explicit psycopg2 driver."""
        if value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value[len("postgres://"):]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Fail fast on unsafe settings instead of silently serving a weak deploy."""
        if self.environment.strip().lower() not in {"prod", "production"}:
            return self
        problems: list[str] = []
        if len(self.secret_key.strip()) < 32 or "change-before-deployment" in self.secret_key:
            problems.append("SECRET_KEY must be a unique deployment secret of at least 32 characters")
        for name, value in (
            ("TOKEN_SIGNING_KEY", self.token_signing_key),
            ("CREDENTIAL_ENCRYPTION_KEY", self.credential_encryption_key),
        ):
            if value and len(value.strip()) < 32:
                problems.append(f"{name} must be at least 32 characters when set")
        origins = self.cors_origin_list
        if not origins or "*" in origins or any(
            "localhost" in origin or "127.0.0.1" in origin for origin in origins
        ):
            problems.append("CORS_ORIGINS must list explicit public origins in production")
        if self.database_url.startswith("sqlite:"):
            problems.append("DATABASE_URL must use a managed database in production")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self

    @property
    def self_registration_enabled(self) -> bool:
        """Explicit opt-in wins; otherwise registration is dev/local only."""
        if self.allow_self_registration is not None:
            return self.allow_self_registration
        return self.environment.strip().lower() not in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def export_path(self) -> Path:
        return Path(self.export_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
