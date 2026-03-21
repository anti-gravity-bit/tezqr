from __future__ import annotations

import pytest

from tezqr.infrastructure.container import AppContainer
from tezqr.shared.config import Settings


class FakeTelegramClient:
    def __init__(self) -> None:
        self.webhooks: list[str] = []

    async def set_webhook(self, url: str) -> None:
        self.webhooks.append(url)

    async def aclose(self) -> None:
        return None


class FakeEngine:
    async def dispose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_startup_skips_webhook_registration_in_production() -> None:
    settings = Settings(
        app_env="production",
        auto_register_webhook=True,
        app_domain="https://tez.goholic.in",
        telegram_webhook_secret="secret",
    )
    telegram_client = FakeTelegramClient()
    container = AppContainer(
        settings=settings,
        engine=FakeEngine(),
        session_factory=None,
        telegram_client=telegram_client,
        bot_service=None,
    )

    await container.startup()

    assert telegram_client.webhooks == []


@pytest.mark.asyncio
async def test_startup_registers_webhook_outside_production() -> None:
    settings = Settings(
        app_env="local",
        auto_register_webhook=True,
        app_domain="https://tez.goholic.in",
        telegram_webhook_secret="secret",
    )
    telegram_client = FakeTelegramClient()
    container = AppContainer(
        settings=settings,
        engine=FakeEngine(),
        session_factory=None,
        telegram_client=telegram_client,
        bot_service=None,
    )

    await container.startup()

    assert telegram_client.webhooks == ["https://tez.goholic.in/webhooks/telegram/secret"]
