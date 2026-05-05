from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_API_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "Agent MCP API"
    api_version: str = "3.0.0"
    database_url: str = "sqlite:///./agent.db"

    # Ollama
    ollama_host: str = "http://127.0.0.1:11434"
    default_model: str = "qwen2.5-coder:7b"

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
