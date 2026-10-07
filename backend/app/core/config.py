"""Application settings loaded from environment variables / the repo-level .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels up from this file's parent.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    postgres_user: str = "bist"
    postgres_password: str = Field(default="", repr=False)
    postgres_db: str = "bist_news"
    postgres_test_db: str = "bist_test"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:4b-q4_K_M"
    ollama_num_ctx: int = 4096
    ollama_timeout_seconds: float = 120.0

    # Collectors (kept deliberately slow: CLAUDE.md §2.4)
    http_user_agent: str = "bist-news-personal/0.1"
    http_min_interval_seconds: float = 3.0
    http_cache_ttl_seconds: float = 1800.0
    http_cache_dir: Path = REPO_ROOT / "backend" / ".cache" / "http"
    rss_interval_minutes: int = 120
    rss_lookback_days: int = 7

    log_level: str = "INFO"

    def database_url(self, *, test: bool = False) -> str:
        db = self.postgres_test_db if test else self.postgres_db
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
