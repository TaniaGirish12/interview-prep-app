"""Settings loaded from the root .env file. The API key never leaves the backend."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "backend" / ".env"), extra="ignore"
    )

    # "api": Anthropic API with ANTHROPIC_API_KEY (billed per token).
    # "claude-code": the `claude` CLI in headless mode, on your Claude subscription login.
    llm_backend: Literal["api", "claude-code"] = "api"
    claude_cli: str = "claude"
    cli_timeout_s: float = 900.0

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    refusal_fallback: bool = True
    db_path: Path = ROOT / "backend" / "data" / "app.db"

    # Effort per pipeline step (thinking cannot be disabled on this model).
    effort_extract: str = "medium"
    effort_rank: str = "medium"
    effort_match: str = "medium"
    effort_topic: str = "high"
    effort_gaps: str = "medium"

    # USD per million tokens (claude-sonnet-5-5). Cache writes use the 5-minute TTL price.
    price_input: float = 2.00
    price_output: float = 10.00
    price_cache_read: float = 0.20
    price_cache_write: float = 2.50

    jd_min_chars: int = 600
    fetch_timeout_s: float = 20.0
    code_run_timeout_s: float = 5.0
    topic_workers: int = 2
    # How many top study-next topics (tier 1–2) to pre-generate in the background; 0 turns it off.
    prefetch_topics: int = Field(default=5, ge=0)

    def effort(self, step: str) -> str:
        return getattr(self, f"effort_{step}", "medium")


@lru_cache
def get_settings() -> Settings:
    return Settings()
