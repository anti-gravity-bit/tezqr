from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tezqr.application.dto import IncomingAttachment, IncomingMessage
from tezqr.application.ports import AbstractUnitOfWork, QrCodeGenerator, TelegramGateway
from tezqr.application.services import BotService
from tezqr.domain.entities import PREMIUM_GENERATION_LIMIT, Merchant, PaymentRequest, UpgradeRequest
from tezqr.domain.enums import MerchantTier
from tezqr.domain.value_objects import Money, TelegramUser, UpiVpa
from tezqr.shared.config import Settings


class FakeMerchantRepository:
    def __init__(self) -> None:
        self.records: dict[int, Merchant] = {}

    async def get_by_telegram_id(self, telegram_id: int) -> Merchant | None:
        return self.records.get(telegram_id)

    async def add(self, merchant: Merchant) -> None:
        self.records[merchant.telegram_user.telegram_id] = merchant

    async def save(self, merchant: Merchant) -> None:
        self.records[merchant.telegram_user.telegram_id] = merchant

    async def count_active_between(
        self,
        start,
        end,
        *,
        exclude_telegram_id: int | None = None,
    ) -> int:
        return sum(
            1
            for merchant in self.records.values()
            if merchant.last_command_at
            and start <= merchant.last_command_at < end
            and merchant.telegram_user.telegram_id != exclude_telegram_id
        )


class FakePaymentRequestRepository:
    def __init__(self) -> None:
        self.records: list[PaymentRequest] = []

    async def add(self, payment_request: PaymentRequest) -> None:
        self.records.append(payment_request)

    async def count_total(self) -> int:
        return len(self.records)


class FakeUpgradeRequestRepository:
    def __init__(self) -> None:
        self.records: list[UpgradeRequest] = []

    async def add(self, upgrade_request: UpgradeRequest) -> None:
        self.records.append(upgrade_request)

    async def mark_pending_as_approved(self, merchant_id: str) -> None:
        for request in self.records:
            if str(request.merchant_id) == merchant_id and request.status == "pending":
                request.status = "approved"


class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self) -> None:
        self.merchants = FakeMerchantRepository()
        self.payment_requests = FakePaymentRequestRepository()
        self.upgrade_requests = FakeUpgradeRequestRepository()
        self.commits = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeTelegramGateway(TelegramGateway):
    def __init__(self) -> None:
        self.text_messages: list[dict] = []
        self.photo_messages: list[dict] = []
        self.photo_reference_messages: list[dict] = []
        self.copied_messages: list[dict] = []
        self.webhooks: list[str] = []

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
                "photo_bytes": photo_bytes,
                "filename": filename,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
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
        self.copied_messages.append(
            {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
        )

    async def set_webhook(self, url: str) -> None:
        self.webhooks.append(url)


class FakeQrCodeGenerator(QrCodeGenerator):
    async def generate_png(self, data: str) -> bytes:
        return f"png:{data}".encode()


def make_message(
    *,
    telegram_id: int = 2001,
    first_name: str = "Neha",
    text: str | None = None,
    attachment: IncomingAttachment | None = None,
    message_id: int = 1,
) -> IncomingMessage:
    return IncomingMessage(
        message_id=message_id,
        chat_id=telegram_id,
        from_user=TelegramUser(telegram_id=telegram_id, first_name=first_name, username="merchant"),
        text=text,
        attachment=attachment,
    )


def make_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        subscription_price_inr=99,
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 3, 21, 9, 30, tzinfo=UTC)


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def fake_gateway() -> FakeTelegramGateway:
    return FakeTelegramGateway()


@pytest.fixture
def service(
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
    fixed_now: datetime,
) -> BotService:
    return BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=fake_gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        now_provider=lambda: fixed_now,
    )


@pytest.mark.asyncio
async def test_setupi_updates_existing_merchant_without_resetting_quota(
    service: BotService,
    fake_uow: FakeUnitOfWork,
) -> None:
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("old@okaxis"))
    merchant.generation_count = 7
    await fake_uow.merchants.add(merchant)

    await service.handle_message(make_message(text="/setupi new@okaxis"))

    updated = await fake_uow.merchants.get_by_telegram_id(2001)
    assert updated is not None
    assert updated.vpa is not None
    assert updated.vpa.value == "new@okaxis"
    assert updated.generation_count == 7


@pytest.mark.asyncio
async def test_pay_generates_twentieth_free_qr_then_blocks_next_request(
    service: BotService,
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
) -> None:
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("merchant@okaxis"))
    merchant.generation_count = 19
    await fake_uow.merchants.add(merchant)

    await service.handle_message(make_message(text="/pay 125.50 Website order"))
    updated = await fake_uow.merchants.get_by_telegram_id(2001)
    assert updated is not None
    assert updated.generation_count == 20
    assert len(fake_uow.payment_requests.records) == 1
    assert len(fake_gateway.photo_messages) == 1
    assert "Create your own payment QR: https://t.me/TezNudgeBot" in (
        fake_gateway.photo_messages[0]["caption"]
    )

    await service.handle_message(make_message(text="/pay 99 Another order", message_id=2))
    assert len(fake_uow.payment_requests.records) == 1
    assert len(fake_gateway.photo_messages) == 2
    assert fake_gateway.photo_messages[-1]["filename"] == "tezqr-premium-pack.png"
    assert "1000 QR generations" in fake_gateway.photo_messages[-1]["caption"]
    assert "UPI ID: owner@upi" in fake_gateway.photo_messages[-1]["caption"]
    assert "Payment link:" in fake_gateway.photo_messages[-1]["caption"]


@pytest.mark.asyncio
async def test_paywall_screenshot_creates_upgrade_request_and_notifies_admin(
    service: BotService,
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
) -> None:
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("merchant@okaxis"))
    merchant.generation_count = 20
    await fake_uow.merchants.add(merchant)

    await service.handle_message(
        make_message(
            attachment=IncomingAttachment(
                kind="photo",
                file_id="file-123",
                file_unique_id="unique-123",
            ),
            message_id=10,
        )
    )

    assert len(fake_uow.upgrade_requests.records) == 1
    assert fake_uow.upgrade_requests.records[0].telegram_file_id == "file-123"
    assert fake_gateway.copied_messages == [
        {"chat_id": 9999, "from_chat_id": 2001, "message_id": 10}
    ]
    assert fake_gateway.text_messages[0]["chat_id"] == 2001
    assert fake_gateway.text_messages[-1]["chat_id"] == 9999
    assert "Payment screenshot received." in fake_gateway.text_messages[0]["text"]


@pytest.mark.asyncio
async def test_admin_stats_and_upgrade_flow(
    service: BotService,
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
    fixed_now: datetime,
) -> None:
    active = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"), now=fixed_now)
    active.setup_vpa(UpiVpa("merchant@okaxis"), fixed_now)
    active.register_command(fixed_now)
    await fake_uow.merchants.add(active)

    payment_request = PaymentRequest.create(active, Money(Decimal("50")), "Snack", fixed_now)
    await fake_uow.payment_requests.add(payment_request)

    await service.handle_message(make_message(telegram_id=9999, first_name="Admin", text="/stats"))
    assert "Active merchants: 1" in fake_gateway.text_messages[-1]["text"]
    assert "Total QR generations: 1" in fake_gateway.text_messages[-1]["text"]

    await service.handle_message(
        make_message(telegram_id=9999, first_name="Admin", text="/upgrade 2001")
    )
    upgraded = await fake_uow.merchants.get_by_telegram_id(2001)
    assert upgraded is not None
    assert upgraded.tier == MerchantTier.PREMIUM
    assert upgraded.generation_count == 0
    assert (
        fake_gateway.text_messages[-2]["text"]
        == "Merchant 2001 has been upgraded to TezQR Premium with a fresh 1000 QR pack."
    )
    assert "1000 QR generations in this pack" in fake_gateway.text_messages[-1]["text"]


@pytest.mark.asyncio
async def test_non_admin_stats_request_gets_permission_message(
    service: BotService,
    fake_gateway: FakeTelegramGateway,
) -> None:
    await service.handle_message(make_message(text="/stats"))
    assert fake_gateway.text_messages[-1]["text"] == (
        "This command is available only to the TezQR owner account."
    )


@pytest.mark.asyncio
async def test_paywall_can_send_owner_configured_subscription_qr() -> None:
    fake_uow = FakeUnitOfWork()
    fake_gateway = FakeTelegramGateway()
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=fake_gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=Settings(
            app_env="test",
            database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
            telegram_bot_token="test-token",
            admin_telegram_id=9999,
            admin_upi_id="owner@upi",
            subscription_price_inr=149,
            subscription_payment_upi_id="premium@upi",
            subscription_payment_link="https://pay.example.com/tezqr",
            subscription_payment_qr="https://cdn.example.com/premium-qr.png",
            telegram_webhook_secret="secret",
            auto_register_webhook=False,
        ),
        now_provider=lambda: datetime(2026, 3, 21, 9, 30, tzinfo=UTC),
    )
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("merchant@okaxis"))
    merchant.generation_count = 20
    await fake_uow.merchants.add(merchant)

    await service.handle_message(make_message(text="/pay 50 Renewal"))

    assert len(fake_gateway.photo_reference_messages) == 1
    assert fake_gateway.photo_reference_messages[0]["photo_reference"] == (
        "https://cdn.example.com/premium-qr.png"
    )
    assert "UPI ID: premium@upi" in fake_gateway.photo_reference_messages[0]["caption"]
    assert "https://pay.example.com/tezqr" in fake_gateway.photo_reference_messages[0]["caption"]
    assert "1000 QR generations" in fake_gateway.photo_reference_messages[0]["caption"]


@pytest.mark.asyncio
async def test_premium_pack_allows_thousandth_qr_then_requires_renewal(
    service: BotService,
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
) -> None:
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("merchant@okaxis"))
    merchant.upgrade()
    merchant.generation_count = PREMIUM_GENERATION_LIMIT - 1
    await fake_uow.merchants.add(merchant)

    await service.handle_message(make_message(text="/pay 51 Final premium QR"))
    updated = await fake_uow.merchants.get_by_telegram_id(2001)
    assert updated is not None
    assert updated.generation_count == PREMIUM_GENERATION_LIMIT
    assert len(fake_uow.payment_requests.records) == 1

    await service.handle_message(make_message(text="/pay 52 Renewal needed", message_id=2))
    assert len(fake_uow.payment_requests.records) == 1
    assert len(fake_gateway.photo_messages) == 2
    assert fake_gateway.photo_messages[-1]["filename"] == "tezqr-premium-pack.png"
    assert "another 1000 QR generations" in fake_gateway.photo_messages[-1]["caption"]
    assert "Payment link:" in fake_gateway.photo_messages[-1]["caption"]


@pytest.mark.asyncio
async def test_premium_quota_screenshot_creates_upgrade_request_for_renewal(
    service: BotService,
    fake_uow: FakeUnitOfWork,
    fake_gateway: FakeTelegramGateway,
) -> None:
    merchant = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant.setup_vpa(UpiVpa("merchant@okaxis"))
    merchant.upgrade()
    merchant.generation_count = PREMIUM_GENERATION_LIMIT
    await fake_uow.merchants.add(merchant)

    await service.handle_message(
        make_message(
            attachment=IncomingAttachment(
                kind="photo",
                file_id="renewal-file-123",
                file_unique_id="renewal-unique-123",
            ),
            message_id=11,
        )
    )

    assert len(fake_uow.upgrade_requests.records) == 1
    assert fake_uow.upgrade_requests.records[0].telegram_file_id == "renewal-file-123"
    assert "activate your 1000 QR pack" in fake_gateway.text_messages[0]["text"]
