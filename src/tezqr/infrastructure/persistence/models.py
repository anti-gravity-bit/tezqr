"""SQLAlchemy persistence models.

The file contains two bounded contexts that currently share the same database:

- the legacy merchant bot tables (`merchants`, `upgrade_requests`)
- the provider control-plane tables (`providers`, `clients`, `payment_requests`, and related assets)

Keeping the tables in one module makes migrations easy to follow, while the class
docstrings and section ordering help the team understand how records relate to each
other when tracing a payment flow end to end.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    UUID,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tezqr.shared.db import Base


class MerchantModel(Base):
    """Legacy merchant account used by the original Telegram-only bot."""

    __tablename__ = "merchants"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vpa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_command_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderModel(Base):
    """Top-level provider workspace with API credentials and default branding."""

    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    branding_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderMemberModel(Base):
    """Provider team member used for role-based access control."""

    __tablename__ = "provider_members"
    __table_args__ = (UniqueConstraint("provider_id", "actor_code"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderBotInstanceModel(Base):
    """White-label Telegram or WhatsApp bot instance owned by a provider."""

    __tablename__ = "provider_bot_instances"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    webhook_secret: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    bot_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branding_override_json: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    configuration_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentDestinationModel(Base):
    """A provider-owned payment destination such as a specific UPI VPA."""

    __tablename__ = "payment_destinations"
    __table_args__ = (UniqueConstraint("provider_id", "code"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    vpa: Mapped[str] = mapped_column(String(255), nullable=False)
    payee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClientModel(Base):
    """Saved provider client that can receive payment requests and reminders."""

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("provider_id", "code"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    onboarding_source: Mapped[str] = mapped_column(String(64), nullable=False, default="api")
    bot_instance_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_bot_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentTemplateModel(Base):
    """Reusable product or service template that can also power `/item-code` flows."""

    __tablename__ = "payment_templates"
    __table_args__ = (UniqueConstraint("provider_id", "item_code"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    default_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    destination_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_generate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentRequestModel(Base):
    """Concrete provider payment request linked to clients, templates, and QR assets."""

    __tablename__ = "payment_requests"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    upi_uri: Mapped[str] = mapped_column(Text, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    custom_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    walk_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qr_mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentLogModel(Base):
    """Append-only operational events recorded against a payment request."""

    __tablename__ = "payment_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_request_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentNoteModel(Base):
    """Manual operator notes attached to a payment request."""

    __tablename__ = "payment_notes"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_request_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentReminderModel(Base):
    """Scheduled, manual, or task-based reminder records for provider workflows."""

    __tablename__ = "payment_reminders"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payment_request_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    include_qr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QrAssetModel(Base):
    """Stored QR artifacts such as raw QR images, branded cards, and print-ready files."""

    __tablename__ = "qr_assets"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    provider_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    payment_request_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    template_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_templates.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    item_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    upi_uri: Mapped[str] = mapped_column(Text, nullable=False)
    is_pre_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboundMessageModel(Base):
    """Audit trail for outbound delivery attempts across channels and bot instances."""

    __tablename__ = "outbound_messages"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_request_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reminder_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_reminders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bot_instance_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_bot_instances.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    share_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UpgradeRequestModel(Base):
    """Legacy premium-upgrade request created from merchant screenshot submissions."""

    __tablename__ = "upgrade_requests"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
