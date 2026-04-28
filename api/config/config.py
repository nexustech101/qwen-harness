from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="USER_API_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "User Account API"
    database_url: str = "sqlite:///./qwen_coder.db"
    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    api_version: str = "1.1.0"

    global_rate_limit: str = "100/minute"
    health_rate_limit: str = "30/minute"
    register_rate_limit: str = "10/minute"
    login_rate_limit: str = "5/minute"
    firebase_exchange_rate_limit: str = "10/minute"
    refresh_rate_limit: str = "20/minute"
    change_password_rate_limit: str = "10/hour"
    list_users_rate_limit: str = "30/minute"
    billing_checkout_rate_limit: str = "20/minute"
    billing_portal_rate_limit: str = "20/minute"
    billing_webhook_rate_limit: str = "120/minute"

    firebase_enabled: bool = False
    firebase_credentials_path: str | None = None
    firebase_project_id: str | None = None
    firebase_require_verified_email: bool = True
    firebase_check_revoked: bool = True

    stripe_enabled: bool = False
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_default_price_id: str | None = None
    stripe_success_url: str = "http://localhost:3000/billing/success?session_id={CHECKOUT_SESSION_ID}"
    stripe_cancel_url: str = "http://localhost:3000/billing/cancel"
    stripe_portal_return_url: str = "http://localhost:3000/settings/billing"

    log_level: str = "INFO"
    log_json: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()  # Global instance
