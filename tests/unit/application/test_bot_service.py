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

    async def get_by_id(self, merchant_id: object) -> Merchant | None:
        for merchant in self.records.values():
            if merchant.id == merchant_id:
                return merchant
        return None

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

    async def list_telegram_ids(self, *, exclude_telegram_id: int | None = None) -> list[int]:
        return sorted(
            telegram_id for telegram_id in self.records if telegram_id != exclude_telegram_id
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

    async def get_pending_by_approval_code(self, approval_code: str) -> UpgradeRequest | None:
        normalized = approval_code.strip().upper()
        for request in self.records:
            if request.approval_code.value == normalized and request.status == "pending":
                return request
        return None

    async def mark_as_approved(self, approval_code: str) -> None:
        normalized = approval_code.strip().upper()
        for request in self.records:
            if request.approval_code.value == normalized and request.status == "pending":
                request.status = "approved"

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
    def __init__(self, *, failing_chat_ids: set[int] | None = None) -> None:
        self.failing_chat_ids = failing_chat_ids or set()
        self.text_messages: list[dict] = []
        self.photo_messages: list[dict] = []
        self.photo_reference_messages: list[dict] = []
        self.copied_messages: list[dict] = []
        self.webhooks: list[str] = []
        self.command_sets: list[dict] = []

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> None:
        if chat_id in self.failing_chat_ids:
            raise RuntimeError(f"delivery failed for {chat_id}")
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

    async def set_my_commands(
        self,
        commands: list[dict[str, str]],
        *,
        scope: dict[str, object] | None = None,
    ) -> None:
        self.command_sets.append({"commands": commands, "scope": scope})

    async def delete_my_commands(
        self,
        *,
        scope: dict[str, object] | None = None,
    ) -> None:
        return None


class FakeQrCodeGenerator(QrCodeGenerator):
    async def generate_png(self, data: str) -> bytes:
        return f"png:{data}".encode()


class FakeControlPlaneService:
    def __init__(self) -> None:
        self.provider_register_calls: list[dict] = []
        self.provider_bot_calls: list[dict] = []
        self.provider_destination_calls: list[dict] = []
        self.workspaces: list[dict] = []
        self.providers_for_admin: list[dict] = []
        self.provider_overview: dict | None = None
        self.provider_members: list[dict] = []
        self.provider_bots: list[dict] = []
        self.provider_clients: list[dict] = []
        self.provider_payments: list[dict] = []

    async def create_provider_from_telegram(
        self,
        *,
        slug: str,
        name: str,
        owner_telegram_id: int,
        owner_display_name: str,
        owner_telegram_username: str | None = None,
    ) -> dict:
        self.provider_register_calls.append(
            {
                "slug": slug,
                "name": name,
                "owner_telegram_id": owner_telegram_id,
                "owner_display_name": owner_display_name,
                "owner_telegram_username": owner_telegram_username,
            }
        )
        return {
            "slug": slug,
            "name": name,
            "api_key": "provider-key-123",
            "owner_actor_code": "OWNER1",
        }

    async def create_bot_instance_from_telegram_owner(
        self,
        *,
        provider_slug: str,
        owner_telegram_id: int,
        bot_token: str,
        public_handle: str | None = None,
    ) -> dict:
        self.provider_bot_calls.append(
            {
                "provider_slug": provider_slug,
                "owner_telegram_id": owner_telegram_id,
                "bot_token": bot_token,
                "public_handle": public_handle,
            }
        )
        return {
            "code": "BOT-123",
            "public_handle": public_handle or "https://t.me/orbitpaybot",
            "webhook_url": "https://tez.goholic.in/webhooks/provider-bots/secret/telegram",
            "webhook_registration": "configured",
        }

    async def create_payment_destination_from_telegram_member(
        self,
        *,
        provider_slug: str,
        telegram_id: int,
        code: str,
        vpa: str,
        payee_name: str,
        is_default: bool = True,
    ) -> dict:
        self.provider_destination_calls.append(
            {
                "provider_slug": provider_slug,
                "telegram_id": telegram_id,
                "code": code,
                "vpa": vpa,
                "payee_name": payee_name,
                "is_default": is_default,
            }
        )
        return {
            "code": code,
            "vpa": vpa,
            "payee_name": payee_name,
            "is_default": is_default,
        }

    async def list_member_workspaces_by_telegram(self, telegram_id: int) -> list[dict]:
        return self.workspaces

    async def list_all_providers_for_admin(self) -> list[dict]:
        return self.providers_for_admin

    async def get_provider_overview_for_admin(self, provider_slug: str) -> dict:
        assert self.provider_overview is not None
        return self.provider_overview

    async def list_provider_members_for_admin(self, provider_slug: str) -> list[dict]:
        return self.provider_members

    async def list_provider_bots_for_admin(self, provider_slug: str) -> list[dict]:
        return self.provider_bots

    async def list_provider_clients_for_admin(self, provider_slug: str) -> list[dict]:
        return self.provider_clients

    async def list_provider_payments_for_admin(
        self,
        provider_slug: str,
        *,
        client_code: str | None = None,
    ) -> list[dict]:
        return self.provider_payments


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
async def test_random_text_gets_full_menu_reply(
    service: BotService,
    fake_gateway: FakeTelegramGateway,
) -> None:
    await service.handle_message(make_message(text="hello bot"))

    assert "I did not recognise that message" in fake_gateway.text_messages[-1]["text"]
    assert "/setupi <vpa_id>" in fake_gateway.text_messages[-1]["text"]
    assert "/pay <amount> <description>" in fake_gateway.text_messages[-1]["text"]


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
    assert "TezQR Payment Pass" in fake_gateway.photo_messages[0]["caption"]
    assert (
        "Fast checkout. Clean records. Zero confusion." in fake_gateway.photo_messages[0]["caption"]
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
    upgrade_request = fake_uow.upgrade_requests.records[0]
    assert upgrade_request.telegram_file_id == "file-123"
    assert upgrade_request.approval_code.value.startswith("TZR-2001-")
    assert fake_gateway.copied_messages == [
        {"chat_id": 9999, "from_chat_id": 2001, "message_id": 10}
    ]
    assert fake_gateway.text_messages[0]["chat_id"] == 2001
    assert "Request code:" in fake_gateway.text_messages[0]["text"]
    assert fake_gateway.text_messages[-1]["chat_id"] == 9999
    assert (
        f"/approve {upgrade_request.approval_code.value}" in fake_gateway.text_messages[-1]["text"]
    )


@pytest.mark.asyncio
async def test_admin_stats_and_legacy_upgrade_flow(
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
    assert "Approval code: MANUAL-UPGRADE" in fake_gateway.text_messages[-1]["text"]


@pytest.mark.asyncio
async def test_admin_can_approve_paid_pack_by_human_readable_code(
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
                file_id="approval-file",
                file_unique_id="approval-unique",
            ),
            message_id=10,
        )
    )
    approval_code = fake_uow.upgrade_requests.records[0].approval_code.value

    await service.handle_message(
        make_message(telegram_id=9999, first_name="Admin", text=f"/approve {approval_code}")
    )

    upgraded = await fake_uow.merchants.get_by_telegram_id(2001)
    assert upgraded is not None
    assert upgraded.tier == MerchantTier.PREMIUM
    assert upgraded.generation_count == 0
    assert fake_uow.upgrade_requests.records[0].status == "approved"
    assert fake_gateway.text_messages[-2]["text"].startswith(f"Approved {approval_code}")
    assert f"Approval code: {approval_code}" in fake_gateway.text_messages[-1]["text"]


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
    assert "Request code:" in fake_gateway.text_messages[0]["text"]


@pytest.mark.asyncio
async def test_admin_broadcast_sends_offer_to_all_merchants_and_reports_counts(
    fake_uow: FakeUnitOfWork,
    fixed_now: datetime,
) -> None:
    gateway = FakeTelegramGateway()
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        now_provider=lambda: fixed_now,
    )
    merchant_one = Merchant.onboard(TelegramUser(telegram_id=2001, first_name="Neha"))
    merchant_two = Merchant.onboard(TelegramUser(telegram_id=2002, first_name="Arjun"))
    await fake_uow.merchants.add(merchant_one)
    await fake_uow.merchants.add(merchant_two)

    await service.handle_message(
        make_message(
            telegram_id=9999,
            first_name="Admin",
            text="/broadcast Today only: pay Rs 99 and unlock 1000 more QRs.",
        )
    )

    merchant_messages = [message for message in gateway.text_messages if message["chat_id"] != 9999]
    assert len(merchant_messages) == 2
    assert all("TezQR update" in message["text"] for message in merchant_messages)
    assert all("https://t.me/TezNudgeBot" in message["text"] for message in merchant_messages)
    assert gateway.text_messages[-1]["chat_id"] == 9999
    assert "Target merchants: 2" in gateway.text_messages[-1]["text"]
    assert "Delivered: 2" in gateway.text_messages[-1]["text"]


@pytest.mark.asyncio
async def test_provider_register_creates_workspace_and_shows_next_steps(
    fake_uow: FakeUnitOfWork,
    fixed_now: datetime,
) -> None:
    gateway = FakeTelegramGateway()
    control_plane = FakeControlPlaneService()
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        control_plane_service=control_plane,
        now_provider=lambda: fixed_now,
    )

    await service.handle_message(make_message(text="/provider_register orbit-pay Orbit Pay"))

    assert control_plane.provider_register_calls[0]["slug"] == "orbit-pay"
    assert "Provider workspace created" in gateway.text_messages[-1]["text"]
    assert "API key: provider-key-123" in gateway.text_messages[-1]["text"]
    assert "/provider_bot orbit-pay <bot_token> [public_handle]" in gateway.text_messages[-1][
        "text"
    ]


@pytest.mark.asyncio
async def test_provider_bot_and_destination_commands_use_linked_owner_flow(
    fake_uow: FakeUnitOfWork,
    fixed_now: datetime,
) -> None:
    gateway = FakeTelegramGateway()
    control_plane = FakeControlPlaneService()
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        control_plane_service=control_plane,
        now_provider=lambda: fixed_now,
    )

    await service.handle_message(
        make_message(text="/provider_bot orbit-pay 123456:ABCDEF https://t.me/orbitpaybot")
    )
    await service.handle_message(
        make_message(text="/provider_destination orbit-pay MAIN orbit@okaxis Orbit Pay")
    )

    assert control_plane.provider_bot_calls[0]["provider_slug"] == "orbit-pay"
    assert control_plane.provider_destination_calls[0]["code"] == "MAIN"
    assert "Webhook: configured" in gateway.text_messages[-2]["text"]
    assert "Provider destination saved" in gateway.text_messages[-1]["text"]


@pytest.mark.asyncio
async def test_provider_me_lists_linked_workspaces(
    fake_uow: FakeUnitOfWork,
    fixed_now: datetime,
) -> None:
    gateway = FakeTelegramGateway()
    control_plane = FakeControlPlaneService()
    control_plane.workspaces = [
        {
            "provider": {"slug": "orbit-pay", "name": "Orbit Pay"},
            "api_key": "provider-key-123",
            "member": {"role": "owner", "actor_code": "OWNER1"},
            "default_destination": {"code": "MAIN", "vpa": "orbit@okaxis"},
            "bot_count": 1,
            "client_count": 4,
        }
    ]
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        control_plane_service=control_plane,
        now_provider=lambda: fixed_now,
    )

    await service.handle_message(make_message(text="/provider_me"))

    assert "Your provider workspaces" in gateway.text_messages[-1]["text"]
    assert "Orbit Pay (orbit-pay)" in gateway.text_messages[-1]["text"]
    assert "Default destination: MAIN -> orbit@okaxis" in gateway.text_messages[-1]["text"]


@pytest.mark.asyncio
async def test_admin_can_list_providers_from_main_bot(
    fake_uow: FakeUnitOfWork,
    fixed_now: datetime,
) -> None:
    gateway = FakeTelegramGateway()
    control_plane = FakeControlPlaneService()
    control_plane.providers_for_admin = [
        {
            "provider": {"slug": "orbit-pay", "name": "Orbit Pay", "api_key": "provider-key-123"},
            "member_count": 2,
            "bot_count": 1,
            "client_count": 4,
            "pending_payments": 3,
            "paid_payments": 7,
            "overdue_payments": 1,
            "scheduled_reminders": 2,
        }
    ]
    service = BotService(
        uow_factory=lambda: fake_uow,
        telegram_gateway=gateway,
        qr_generator=FakeQrCodeGenerator(),
        settings=make_settings(),
        control_plane_service=control_plane,
        now_provider=lambda: fixed_now,
    )

    await service.handle_message(
        make_message(telegram_id=9999, first_name="Admin", text="/providers")
    )

    assert "Provider workspaces" in gateway.text_messages[-1]["text"]
    assert "Orbit Pay (orbit-pay)" in gateway.text_messages[-1]["text"]
    assert "Pending/Paid/Overdue: 3/7/1" in gateway.text_messages[-1]["text"]
