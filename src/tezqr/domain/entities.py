from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tezqr.domain.enums import (
    BotPlatform,
    DeliveryState,
    MerchantTier,
    MessageChannel,
    PaymentStatus,
    ProviderMemberRole,
    QrAssetType,
    ReminderStatus,
    ReminderType,
)
from tezqr.domain.exceptions import (
    DomainValidationError,
    FreeQuotaExceededError,
    MerchantSetupRequiredError,
)
from tezqr.domain.value_objects import (
    ItemCode,
    Money,
    PaymentReference,
    PhoneNumber,
    ProviderSlug,
    TelegramUser,
    UpgradeRequestCode,
    UpiPaymentLink,
    UpiVpa,
)
from tezqr.shared.time import utc_now

FREE_GENERATION_LIMIT = 20
PREMIUM_GENERATION_LIMIT = 1000


def _clean_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field_name} is required.")
    return normalized


@dataclass(slots=True)
class Merchant:
    id: UUID
    telegram_user: TelegramUser
    tier: MerchantTier = MerchantTier.FREE
    generation_count: int = 0
    vpa: UpiVpa | None = None
    last_command_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.generation_count < 0:
            raise DomainValidationError("Generation count cannot be negative.")

    @classmethod
    def onboard(cls, telegram_user: TelegramUser, now: datetime | None = None) -> Merchant:
        timestamp = now or utc_now()
        return cls(
            id=uuid4(),
            telegram_user=telegram_user,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def refresh_profile(self, telegram_user: TelegramUser, now: datetime | None = None) -> None:
        self.telegram_user = telegram_user
        self.updated_at = now or utc_now()

    def register_command(self, now: datetime | None = None) -> None:
        timestamp = now or utc_now()
        self.last_command_at = timestamp
        self.updated_at = timestamp

    def setup_vpa(self, vpa: UpiVpa, now: datetime | None = None) -> None:
        self.vpa = vpa
        self.updated_at = now or utc_now()

    def upgrade(self, now: datetime | None = None) -> None:
        self.tier = MerchantTier.PREMIUM
        self.generation_count = 0
        self.updated_at = now or utc_now()

    @property
    def is_upi_configured(self) -> bool:
        return self.vpa is not None

    @property
    def quota_reached(self) -> bool:
        if self.tier == MerchantTier.PREMIUM:
            return self.generation_count >= PREMIUM_GENERATION_LIMIT
        return self.generation_count >= FREE_GENERATION_LIMIT

    def ensure_ready_for_generation(self) -> None:
        if not self.vpa:
            raise MerchantSetupRequiredError(
                "Merchant must register a UPI VPA before generating QR codes."
            )
        if self.quota_reached:
            raise FreeQuotaExceededError("Generation quota has been exhausted for this merchant.")

    def record_generation(self, now: datetime | None = None) -> None:
        self.ensure_ready_for_generation()
        self.generation_count += 1
        self.updated_at = now or utc_now()


@dataclass(slots=True)
class Provider:
    id: UUID
    slug: ProviderSlug
    name: str
    api_key: str
    branding: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.name = _clean_text(self.name, field_name="Provider name")
        self.api_key = _clean_text(self.api_key, field_name="Provider API key")


@dataclass(slots=True)
class ProviderMember:
    id: UUID
    provider_id: UUID
    actor_code: str
    display_name: str
    role: ProviderMemberRole
    telegram_id: int | None = None
    telegram_username: str | None = None
    whatsapp_number: PhoneNumber | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.actor_code = _clean_text(self.actor_code, field_name="Actor code").upper()
        self.display_name = _clean_text(self.display_name, field_name="Display name")
        if self.telegram_id is not None and self.telegram_id <= 0:
            raise DomainValidationError("Telegram id must be positive when provided.")


@dataclass(slots=True)
class ProviderBotInstance:
    id: UUID
    provider_id: UUID
    code: str
    platform: BotPlatform
    display_name: str
    webhook_secret: str
    bot_token: str | None = None
    public_handle: str | None = None
    branding_override: dict[str, str] = field(default_factory=dict)
    configuration: dict[str, str] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="Bot code").upper()
        self.display_name = _clean_text(self.display_name, field_name="Bot display name")
        self.webhook_secret = _clean_text(self.webhook_secret, field_name="Webhook secret")


@dataclass(slots=True)
class PaymentDestination:
    id: UUID
    provider_id: UUID
    code: str
    label: str
    vpa: UpiVpa
    payee_name: str
    is_default: bool = False
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="Payment destination code").upper()
        self.label = _clean_text(self.label, field_name="Payment destination label")
        self.payee_name = _clean_text(self.payee_name, field_name="Payee name")


@dataclass(slots=True)
class Client:
    id: UUID
    provider_id: UUID
    code: str
    full_name: str
    telegram_id: int | None = None
    telegram_username: str | None = None
    whatsapp_number: PhoneNumber | None = None
    external_ref: str | None = None
    notes: str | None = None
    labels: list[str] = field(default_factory=list)
    onboarding_source: str = "api"
    bot_instance_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="Client code").upper()
        self.full_name = _clean_text(self.full_name, field_name="Client name")
        if self.telegram_id is not None and self.telegram_id <= 0:
            raise DomainValidationError("Telegram id must be positive when provided.")


@dataclass(slots=True)
class PaymentTemplate:
    id: UUID
    provider_id: UUID
    code: str
    name: str
    description: str
    item_code: ItemCode | None = None
    default_amount: Money | None = None
    currency: str = "INR"
    destination_code: str | None = None
    message_template: str | None = None
    custom_message: str | None = None
    pre_generate: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="Template code").upper()
        self.name = _clean_text(self.name, field_name="Template name")
        self.description = _clean_text(self.description, field_name="Template description")
        normalized_currency = self.currency.strip().upper()
        if normalized_currency != "INR":
            raise DomainValidationError("Only INR payment templates are supported.")
        self.currency = normalized_currency
        if self.destination_code is not None:
            self.destination_code = _clean_text(
                self.destination_code,
                field_name="Destination code",
            ).upper()


@dataclass(slots=True)
class PaymentRequest:
    id: UUID
    merchant_id: UUID | None
    reference: PaymentReference
    amount: Money
    description: str
    upi_uri: str
    provider_id: UUID | None = None
    client_id: UUID | None = None
    template_id: UUID | None = None
    item_code: str | None = None
    custom_message: str | None = None
    channel: str | None = None
    status: PaymentStatus = PaymentStatus.PENDING
    due_at: datetime | None = None
    paid_at: datetime | None = None
    status_updated_at: datetime | None = None
    notes_summary: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    walk_in: bool = False
    qr_mime_type: str = "image/png"
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        merchant: Merchant,
        amount: Money,
        description: str,
        now: datetime | None = None,
    ) -> PaymentRequest:
        merchant.ensure_ready_for_generation()
        clean_description = description.strip()
        if not clean_description:
            raise DomainValidationError("Payment description is required.")
        reference = PaymentReference.new()
        payee_name = merchant.telegram_user.display_name or "TezQR Merchant"
        upi_link = UpiPaymentLink(
            vpa=merchant.vpa,
            amount=amount,
            description=clean_description,
            reference=reference,
            payee_name=payee_name,
        )
        return cls(
            id=uuid4(),
            merchant_id=merchant.id,
            reference=reference,
            amount=amount,
            description=clean_description,
            upi_uri=upi_link.uri,
            created_at=now or utc_now(),
        )

    @classmethod
    def create_for_provider(
        cls,
        *,
        provider_id: UUID,
        destination: PaymentDestination,
        amount: Money,
        description: str,
        client_id: UUID | None = None,
        template_id: UUID | None = None,
        item_code: str | None = None,
        custom_message: str | None = None,
        channel: MessageChannel | None = None,
        due_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
        walk_in: bool = False,
        now: datetime | None = None,
    ) -> PaymentRequest:
        clean_description = description.strip()
        if not clean_description:
            raise DomainValidationError("Payment description is required.")
        reference = PaymentReference.new()
        upi_link = UpiPaymentLink(
            vpa=destination.vpa,
            amount=amount,
            description=clean_description,
            reference=reference,
            payee_name=destination.payee_name,
        )
        timestamp = now or utc_now()
        return cls(
            id=uuid4(),
            merchant_id=None,
            provider_id=provider_id,
            client_id=client_id,
            template_id=template_id,
            reference=reference,
            amount=amount,
            description=clean_description,
            upi_uri=upi_link.uri,
            item_code=item_code.strip().upper() if item_code else None,
            custom_message=custom_message.strip() if custom_message else None,
            channel=channel.value if channel else None,
            status=PaymentStatus.PENDING,
            due_at=due_at,
            status_updated_at=timestamp,
            metadata=metadata or {},
            walk_in=walk_in,
            created_at=timestamp,
        )

    def mark_status(
        self,
        status: PaymentStatus,
        *,
        now: datetime | None = None,
        notes_summary: str | None = None,
    ) -> None:
        timestamp = now or utc_now()
        self.status = status
        self.status_updated_at = timestamp
        if status == PaymentStatus.PAID:
            self.paid_at = timestamp
        if notes_summary is not None:
            self.notes_summary = notes_summary.strip() or None


@dataclass(slots=True)
class PaymentNote:
    id: UUID
    payment_request_id: UUID
    note: str
    created_by: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.note = _clean_text(self.note, field_name="Payment note")
        self.created_by = _clean_text(self.created_by, field_name="Created by")


@dataclass(slots=True)
class PaymentLog:
    id: UUID
    payment_request_id: UUID
    event_type: str
    message: str
    payload: dict[str, str] = field(default_factory=dict)
    created_by: str = "system"
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.event_type = _clean_text(self.event_type, field_name="Payment log event")
        self.message = _clean_text(self.message, field_name="Payment log message")
        self.created_by = _clean_text(self.created_by, field_name="Created by")


@dataclass(slots=True)
class PaymentReminder:
    id: UUID
    provider_id: UUID
    code: str
    reminder_type: ReminderType
    channel: MessageChannel
    status: ReminderStatus
    message: str
    payment_request_id: UUID | None = None
    client_id: UUID | None = None
    task_name: str | None = None
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    include_qr: bool = True
    created_by: str = "system"
    last_error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="Reminder code").upper()
        self.message = _clean_text(self.message, field_name="Reminder message")
        self.created_by = _clean_text(self.created_by, field_name="Created by")
        if self.task_name is not None:
            self.task_name = self.task_name.strip() or None


@dataclass(slots=True)
class QrAsset:
    id: UUID
    code: str
    asset_type: QrAssetType
    mime_type: str
    filename: str
    content_bytes: bytes
    upi_uri: str
    provider_id: UUID | None = None
    payment_request_id: UUID | None = None
    template_id: UUID | None = None
    item_code: str | None = None
    amount: Decimal | None = None
    is_pre_generated: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = _clean_text(self.code, field_name="QR asset code").upper()
        self.filename = _clean_text(self.filename, field_name="QR asset filename")
        self.mime_type = _clean_text(self.mime_type, field_name="QR asset mime type")
        if not self.content_bytes:
            raise DomainValidationError("QR asset content is required.")


@dataclass(slots=True)
class OutboundMessage:
    id: UUID
    provider_id: UUID
    channel: MessageChannel
    delivery_state: DeliveryState
    recipient: str
    message: str
    client_id: UUID | None = None
    payment_request_id: UUID | None = None
    reminder_id: UUID | None = None
    bot_instance_id: UUID | None = None
    share_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    sent_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.recipient = _clean_text(self.recipient, field_name="Recipient")
        self.message = _clean_text(self.message, field_name="Outbound message")


@dataclass(slots=True)
class UpgradeRequest:
    id: UUID
    merchant_id: UUID
    approval_code: UpgradeRequestCode
    telegram_chat_id: int
    telegram_message_id: int
    telegram_file_id: str
    telegram_file_unique_id: str | None
    media_kind: str
    status: str = "pending"
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        merchant_id: UUID,
        telegram_chat_id: int,
        telegram_message_id: int,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        media_kind: str,
        approval_code: UpgradeRequestCode | None = None,
        now: datetime | None = None,
    ) -> UpgradeRequest:
        if media_kind not in {"photo", "document"}:
            raise DomainValidationError("Unsupported upgrade media kind.")
        if not telegram_file_id.strip():
            raise DomainValidationError("Telegram file id is required.")
        return cls(
            id=uuid4(),
            merchant_id=merchant_id,
            approval_code=approval_code or UpgradeRequestCode.new(telegram_chat_id),
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_file_id=telegram_file_id,
            telegram_file_unique_id=telegram_file_unique_id,
            media_kind=media_kind,
            created_at=now or utc_now(),
        )


@dataclass(frozen=True, slots=True)
class AdminStats:
    daily_active_users: int
    total_generations: int


@dataclass(frozen=True, slots=True)
class ProviderDashboard:
    total_clients: int
    pending_payments: int
    paid_payments: int
    overdue_payments: int
    total_templates: int
    total_bot_instances: int
    scheduled_reminders: int
