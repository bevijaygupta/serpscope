"""Environment-driven application configuration."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SERPScope"
    environment: str = "development"
    secret_key: str = "dev-only-secret-change-before-deployment"
    database_url: str = "sqlite:///./data/serpscope.db"
    upload_dir: str = "./data/uploads"
    export_dir: str = "./data/exports"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    job_poll_seconds: float = 0.5
    run_jobs_in_api: bool = True
    max_upload_mb: int = 50
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalise_database_url(cls, value: str) -> str:
        """Render emits postgres://; SQLAlchemy needs an explicit psycopg2 driver."""
        if value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value[len("postgres://"):]
        return value

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
