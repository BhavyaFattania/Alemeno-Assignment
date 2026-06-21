from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Transaction Processing Pipeline"
    app_env: str = "development"
    database_url: str = "sqlite:///./dev.db"
    test_database_url: str = "sqlite:///./test.db"
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: Path = Path("uploads")
    openrouter_api_key: str | None = None
    openrouter_model: str = "google/gemini-2.0-flash-exp:free"
    llm_timeout_seconds: int = Field(default=30, ge=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
