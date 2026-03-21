from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tezqr.application.ports import AbstractUnitOfWork
from tezqr.application.services import BotService
from tezqr.infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from tezqr.infrastructure.qr.generator import QRCodeGeneratorService
from tezqr.infrastructure.telegram.client import TelegramBotClient
from tezqr.shared.config import Settings
from tezqr.shared.db import build_async_session_factory, build_engine


@dataclass
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    telegram_client: TelegramBotClient
    bot_service: BotService

    async def startup(self) -> None:
        if self.settings.auto_register_webhook and self.settings.webhook_url:
            await self.telegram_client.set_webhook(self.settings.webhook_url)

    async def shutdown(self) -> None:
        await self.telegram_client.aclose()
        await self.engine.dispose()


def build_container(settings: Settings) -> AppContainer:
    engine = build_engine(settings.database_url)
    session_factory = build_async_session_factory(engine)
    http_client = httpx.AsyncClient(timeout=20.0)
    telegram_client = TelegramBotClient(settings=settings, http_client=http_client)

    def uow_factory() -> AbstractUnitOfWork:
        return SQLAlchemyUnitOfWork(session_factory)

    bot_service = BotService(
        uow_factory=uow_factory,
        telegram_gateway=telegram_client,
        qr_generator=QRCodeGeneratorService(),
        settings=settings,
    )
    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        telegram_client=telegram_client,
        bot_service=bot_service,
    )
