from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tezqr.application.control_plane import ControlPlaneService
from tezqr.application.ports import AbstractUnitOfWork
from tezqr.application.services import BotService
from tezqr.application.telegram_menu_commands import (
    legacy_admin_commands,
    legacy_public_commands,
    to_telegram_menu_payload,
)
from tezqr.infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from tezqr.infrastructure.qr.generator import QRCodeGeneratorService
from tezqr.infrastructure.telegram.client import TelegramBotClient
from tezqr.shared.config import Settings
from tezqr.shared.db import build_async_session_factory, build_engine

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    telegram_client: TelegramBotClient | None
    bot_service: BotService | None
    http_client: httpx.AsyncClient | None = None
    control_plane_service: ControlPlaneService | None = None

    async def startup(self) -> None:
        if self.telegram_client is not None:
            try:
                await self.telegram_client.set_my_commands(
                    to_telegram_menu_payload(legacy_public_commands())
                )
                await self.telegram_client.set_my_commands(
                    to_telegram_menu_payload(legacy_admin_commands()),
                    scope={"type": "chat", "chat_id": self.settings.admin_telegram_id},
                )
            except Exception:
                logger.warning(
                    "Legacy Telegram command registration skipped after failure.",
                    exc_info=True,
                )
        if (
            self.settings.app_env != "production"
            and self.settings.auto_register_webhook
            and self.settings.webhook_url
            and self.telegram_client is not None
        ):
            try:
                await self.telegram_client.set_webhook(self.settings.webhook_url)
            except Exception:
                logger.warning(
                    "Telegram webhook auto-registration skipped after failure.",
                    exc_info=True,
                )
        if self.control_plane_service is not None:
            try:
                await self.control_plane_service.sync_provider_telegram_bot_commands()
            except Exception:
                logger.warning(
                    "Provider Telegram command registration skipped after failure.",
                    exc_info=True,
                )

    async def shutdown(self) -> None:
        if self.telegram_client is not None:
            await self.telegram_client.aclose()
        elif self.http_client is not None:
            await self.http_client.aclose()
        await self.engine.dispose()


def build_container(settings: Settings) -> AppContainer:
    engine = build_engine(settings.database_url)
    session_factory = build_async_session_factory(engine)
    http_client = httpx.AsyncClient(timeout=20.0)
    telegram_client = TelegramBotClient(settings=settings, http_client=http_client)
    qr_generator = QRCodeGeneratorService()

    def uow_factory() -> AbstractUnitOfWork:
        return SQLAlchemyUnitOfWork(session_factory)

    bot_service = BotService(
        uow_factory=uow_factory,
        telegram_gateway=telegram_client,
        qr_generator=qr_generator,
        settings=settings,
    )
    control_plane_service = ControlPlaneService(
        session_factory=session_factory,
        qr_generator=qr_generator,
        http_client=http_client,
        settings=settings,
    )
    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        telegram_client=telegram_client,
        bot_service=bot_service,
        http_client=http_client,
        control_plane_service=control_plane_service,
    )
