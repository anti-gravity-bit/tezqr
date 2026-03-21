from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TezQR"
    app_env: Literal["local", "production", "test"] = "local"
    database_url: str = "postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr"
    telegram_bot_token: str = Field(default="replace-me")
    admin_telegram_id: int = Field(default=123456789)
    admin_upi_id: str = Field(default="owner@upi")
    subscription_price_inr: int = 99
    subscription_payment_upi_id: str | None = None
    subscription_payment_link: str | None = None
    subscription_payment_qr: str | None = None
    app_domain: str | None = None
    telegram_webhook_secret: str = Field(default="change-me")
    auto_register_webhook: bool = False
    tz: str = "Asia/Kolkata"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def telegram_api_base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.telegram_bot_token}"

    @property
    def effective_subscription_upi_id(self) -> str:
        return self.subscription_payment_upi_id or self.admin_upi_id

    @property
    def has_subscription_payment_qr(self) -> bool:
        return bool(self.subscription_payment_qr)

    @property
    def webhook_path(self) -> str:
        return f"/webhooks/telegram/{self.telegram_webhook_secret}"

    @property
    def webhook_url(self) -> str | None:
        if not self.app_domain:
            return None
        return f"{self.app_domain.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
