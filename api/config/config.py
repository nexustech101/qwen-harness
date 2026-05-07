from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.paths import data_dir as _data_dir, ensure_data_dir as _ensure_data_dir

# Resolve and create the centralized data directory at import time so that the
# SQLite database URL always points to a directory that exists.
_dd: Path = _data_dir()
_dd.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_API_",
        # Load from the centralized data dir first, then from CWD for dev overrides.
        # pydantic-settings silently ignores missing files.
        env_file=[str(_dd / ".env"), ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agent MCP API"
    api_version: str = "3.0.0"
    # Database lives in the centralized data directory — never in CWD.
    database_url: str = f"sqlite:///{_dd / 'agent.db'}"

    # LLM provider ("ollama" | "openai" | "anthropic")
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"

    # Ollama
    ollama_host: str = "http://127.0.0.1:11434"
    default_model: str = "qwen2.5-coder:7b"

    # OpenAI
    openai_api_key: SecretStr | None = None
    openai_default_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: SecretStr | None = None
    anthropic_default_model: str = "claude-3-5-haiku-20241022"

    # MCP
    mcp_server_name: str = "Local Agent"

    # Rate limits
    global_rate_limit: str = "200/minute"

    # Logging
    log_level: str = "INFO"
    log_json: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
