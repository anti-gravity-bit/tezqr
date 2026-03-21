from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from tezqr.application.ports import QrCodeGenerator, TelegramGateway
from tezqr.application.services import BotService
from tezqr.infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from tezqr.presentation.app import create_app
from tezqr.shared.config import Settings


class SpyTelegramGateway(TelegramGateway):
    def __init__(self) -> None:
        self.text_messages: list[dict] = []
        self.photo_messages: list[dict] = []
        self.photo_reference_messages: list[dict] = []

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> None:
        self.text_messages.append(
            {"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id}
        )

    async def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        *,
        filename: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        self.photo_messages.append(
            {
                "chat_id": chat_id,
                "filename": filename,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
                "photo_bytes": photo_bytes,
            }
        )

    async def send_photo_reference(
        self,
        chat_id: int,
        photo_reference: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        self.photo_reference_messages.append(
            {
                "chat_id": chat_id,
                "photo_reference": photo_reference,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            }
        )

    async def copy_message(self, chat_id: int, from_chat_id: int, message_id: int) -> None:
        return None

    async def set_webhook(self, url: str) -> None:
        return None


class SpyQrGenerator(QrCodeGenerator):
    async def generate_png(self, data: str) -> bytes:
        return f"qr:{data}".encode()


class AppTestContainer:
    def __init__(self, settings: Settings, bot_service: BotService) -> None:
        self.settings = settings
        self.bot_service = bot_service

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


@pytest.mark.asyncio
async def test_webhook_processes_setupi_and_pay_commands(db_session_factory) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )
    gateway = SpyTelegramGateway()
    service = BotService(
        uow_factory=lambda: SQLAlchemyUnitOfWork(db_session_factory),
        telegram_gateway=gateway,
        qr_generator=SpyQrGenerator(),
        settings=settings,
        now_provider=lambda: datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
    )
    app = create_app(settings=settings, container=AppTestContainer(settings, service))

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            setup_response = await client.post(
                "/webhooks/telegram/secret",
                json={
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "from": {"id": 4001, "first_name": "Kiran", "username": "kiran"},
                        "chat": {"id": 4001},
                        "text": "/setupi kiran@okaxis",
                    },
                },
            )
            pay_response = await client.post(
                "/webhooks/telegram/secret",
                json={
                    "update_id": 2,
                    "message": {
                        "message_id": 11,
                        "from": {"id": 4001, "first_name": "Kiran", "username": "kiran"},
                        "chat": {"id": 4001},
                        "text": "/pay 150 Repair work",
                    },
                },
            )

    assert setup_response.status_code == 200
    assert pay_response.status_code == 200
    assert gateway.text_messages[0]["text"].startswith("UPI ID saved successfully.")
    assert len(gateway.photo_messages) == 1
    assert "Powered by TezQR on Telegram." in gateway.photo_messages[0]["caption"]
    assert "upi://pay?" in gateway.photo_messages[0]["caption"]
