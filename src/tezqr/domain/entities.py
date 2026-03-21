from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from tezqr.domain.enums import MerchantTier
from tezqr.domain.exceptions import (
    DomainValidationError,
    FreeQuotaExceededError,
    MerchantSetupRequiredError,
)
from tezqr.domain.value_objects import (
    Money,
    PaymentReference,
    TelegramUser,
    UpiPaymentLink,
    UpiVpa,
)
from tezqr.shared.time import utc_now

FREE_GENERATION_LIMIT = 20


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
        self.updated_at = now or utc_now()

    @property
    def is_upi_configured(self) -> bool:
        return self.vpa is not None

    @property
    def quota_reached(self) -> bool:
        return self.tier == MerchantTier.FREE and self.generation_count >= FREE_GENERATION_LIMIT

    def ensure_ready_for_generation(self) -> None:
        if not self.vpa:
            raise MerchantSetupRequiredError(
                "Merchant must register a UPI VPA before generating QR codes."
            )
        if self.quota_reached:
            raise FreeQuotaExceededError("Free-tier generation quota has been exhausted.")

    def record_generation(self, now: datetime | None = None) -> None:
        self.ensure_ready_for_generation()
        self.generation_count += 1
        self.updated_at = now or utc_now()


@dataclass(slots=True)
class PaymentRequest:
    id: UUID
    merchant_id: UUID
    reference: PaymentReference
    amount: Money
    description: str
    upi_uri: str
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


@dataclass(slots=True)
class UpgradeRequest:
    id: UUID
    merchant_id: UUID
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
        now: datetime | None = None,
    ) -> UpgradeRequest:
        if media_kind not in {"photo", "document"}:
            raise DomainValidationError("Unsupported upgrade media kind.")
        if not telegram_file_id.strip():
            raise DomainValidationError("Telegram file id is required.")
        return cls(
            id=uuid4(),
            merchant_id=merchant_id,
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
