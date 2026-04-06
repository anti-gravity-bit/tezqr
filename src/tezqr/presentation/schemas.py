"""Request and transport schemas for the FastAPI presentation layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TelegramUserSchema(BaseModel):
    """Telegram sender payload received from webhook updates."""

    id: int = Field(description="Telegram user ID.")
    first_name: str = Field(description="Telegram first name.")
    last_name: str | None = Field(default=None, description="Telegram last name.")
    username: str | None = Field(default=None, description="Telegram username.")

    model_config = ConfigDict(extra="ignore")


class TelegramChatSchema(BaseModel):
    """Telegram chat metadata used by inbound bot updates."""

    id: int = Field(description="Telegram chat ID.")

    model_config = ConfigDict(extra="ignore")


class TelegramPhotoSchema(BaseModel):
    """Telegram photo payload metadata."""

    file_id: str = Field(description="Telegram file ID.")
    file_unique_id: str | None = Field(default=None, description="Stable Telegram file identifier.")

    model_config = ConfigDict(extra="ignore")


class TelegramDocumentSchema(BaseModel):
    """Telegram document payload metadata."""

    file_id: str = Field(description="Telegram file ID.")
    file_unique_id: str | None = Field(default=None, description="Stable Telegram file identifier.")
    mime_type: str | None = Field(default=None, description="Optional Telegram MIME type.")
    file_name: str | None = Field(default=None, description="Original Telegram file name.")

    model_config = ConfigDict(extra="ignore")


class TelegramMessageSchema(BaseModel):
    """Telegram message payload accepted by both legacy and provider webhooks."""

    message_id: int = Field(description="Telegram message ID.")
    from_user: TelegramUserSchema = Field(alias="from", description="Telegram sender details.")
    chat: TelegramChatSchema = Field(description="Telegram chat details.")
    text: str | None = Field(default=None, description="Plain-text message body.")
    caption: str | None = Field(
        default=None, description="Caption used for photo and file messages."
    )
    photo: list[TelegramPhotoSchema] = Field(
        default_factory=list,
        description="Photo variants included in the message.",
    )
    document: TelegramDocumentSchema | None = Field(
        default=None,
        description="Attached document metadata when present.",
    )

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TelegramUpdateSchema(BaseModel):
    """Telegram webhook envelope."""

    update_id: int = Field(description="Telegram update ID.")
    message: TelegramMessageSchema | None = Field(
        default=None,
        description="Incoming message payload.",
    )
    edited_message: TelegramMessageSchema | None = Field(
        default=None,
        description="Edited message payload when Telegram sends an update for a prior message.",
    )

    model_config = ConfigDict(extra="ignore")


class ProviderCreateSchema(BaseModel):
    """Request body for creating a provider workspace."""

    slug: str = Field(description="URL-safe provider slug used in API paths.")
    name: str = Field(description="Provider display name.")
    primary_color: str | None = Field(
        default=None, description="Primary theme color as a hex value."
    )
    secondary_color: str | None = Field(
        default=None,
        description="Secondary theme color as a hex value.",
    )
    accent_color: str | None = Field(default=None, description="Accent theme color as a hex value.")
    logo_text: str | None = Field(
        default=None, description="Short text rendered inside branded QR cards."
    )
    owner_actor_code: str | None = Field(
        default=None,
        description="Optional owner actor code that seeds provider access control.",
    )
    owner_display_name: str | None = Field(
        default=None,
        description="Display name for the seeded provider owner.",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "slug": "acme-pay",
                "name": "Acme Pay",
                "logo_text": "AC",
                "owner_actor_code": "OWNER1",
                "owner_display_name": "Owner One",
            }
        },
    )


class ProviderMemberCreateSchema(BaseModel):
    """Request body for creating a provider team member."""

    actor_code: str = Field(description="Unique actor code used in the `x-actor-code` header.")
    display_name: str = Field(description="Human-readable team member name.")
    role: str = Field(description="Provider role such as owner, manager, operator, or viewer.")

    model_config = ConfigDict(extra="forbid")


class PaymentDestinationCreateSchema(BaseModel):
    """Request body for adding a provider payment destination."""

    code: str = Field(description="Provider-specific destination code.")
    label: str = Field(description="Human-readable destination label.")
    vpa: str = Field(description="UPI VPA used for payment collection.")
    payee_name: str = Field(description="Payee name embedded into generated UPI links.")
    is_default: bool = Field(
        default=False,
        description="Mark this destination as the provider default for new requests.",
    )

    model_config = ConfigDict(extra="forbid")


class ProviderBotInstanceCreateSchema(BaseModel):
    """Request body for creating a provider-specific bot instance."""

    platform: str = Field(description="Bot platform, for example `telegram` or `whatsapp`.")
    display_name: str = Field(description="Bot display name shown to operators and clients.")
    public_handle: str | None = Field(
        default=None, description="Optional public bot handle or profile URL."
    )
    bot_token: str | None = Field(
        default=None,
        description="Telegram bot token when direct Telegram delivery should be enabled.",
    )
    primary_color: str | None = Field(default=None, description="Optional primary color override.")
    secondary_color: str | None = Field(
        default=None, description="Optional secondary color override."
    )
    accent_color: str | None = Field(default=None, description="Optional accent color override.")
    logo_text: str | None = Field(
        default=None, description="Optional bot-specific logo text override."
    )

    model_config = ConfigDict(extra="forbid")


class ClientCreateSchema(BaseModel):
    """Request body for creating a provider client."""

    full_name: str = Field(description="Client full name.")
    telegram_id: int | None = Field(default=None, description="Client Telegram user ID.")
    telegram_username: str | None = Field(default=None, description="Client Telegram username.")
    whatsapp_number: str | None = Field(
        default=None, description="Client WhatsApp number in E.164 format."
    )
    external_ref: str | None = Field(default=None, description="External CRM or ERP reference.")
    notes: str | None = Field(default=None, description="Internal notes about the client.")
    labels: list[str] = Field(
        default_factory=list, description="Free-form labels used for segmentation."
    )
    onboarding_source: str = Field(
        default="api",
        description=(
            "How the client entered the system, for example `api`, `telegram_bot`, "
            "or `whatsapp_bot`."
        ),
    )
    bot_instance_code: str | None = Field(
        default=None,
        description="Optional provider bot instance code linked to the client.",
    )

    model_config = ConfigDict(extra="forbid")


class PaymentTemplateCreateSchema(BaseModel):
    """Request body for creating a reusable provider payment template."""

    name: str = Field(description="Template name used by operators.")
    description: str = Field(description="Payment description embedded into generated links.")
    item_code: str | None = Field(
        default=None, description="Optional product or service item code."
    )
    default_amount: str | None = Field(default=None, description="Optional default INR amount.")
    destination_code: str | None = Field(
        default=None,
        description="Optional payment destination code for this template.",
    )
    message_template: str | None = Field(
        default=None,
        description="Optional message template with placeholders such as `{client_name}`.",
    )
    custom_message: str | None = Field(
        default=None,
        description="Default custom payment message used when sharing requests.",
    )
    pre_generate: bool = Field(
        default=False,
        description="Pre-generate QR assets immediately when a default amount is available.",
    )

    model_config = ConfigDict(extra="forbid")


class PaymentRequestCreateSchema(BaseModel):
    """Request body for creating a provider payment request."""

    amount: str | None = Field(default=None, description="Optional fixed INR amount.")
    description: str | None = Field(default=None, description="Optional payment description.")
    client_code: str | None = Field(
        default=None,
        description="Optional client code for a saved provider client.",
    )
    template_code: str | None = Field(
        default=None, description="Optional reusable payment template code."
    )
    item_code: str | None = Field(
        default=None, description="Optional product or service item code."
    )
    destination_code: str | None = Field(
        default=None,
        description="Optional provider payment destination code.",
    )
    custom_message: str | None = Field(
        default=None,
        description="Optional custom message rendered into the outgoing payment note.",
    )
    due_at: str | None = Field(
        default=None,
        description="Optional ISO-8601 due date used for manual tracking and reminders.",
    )
    channel: str | None = Field(
        default=None,
        description="Preferred delivery channel, typically `telegram` or `whatsapp`.",
    )
    walk_in: bool = Field(
        default=False,
        description="Flag the request as a walk-in payment with no pre-linked client.",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "template_code": "TPL-AB12CD34EF",
                "client_code": "CLI-AB12CD34EF",
                "amount": "499",
                "custom_message": "Hello {client_name}, please pay for {description}.",
                "channel": "telegram",
            }
        },
    )


class PaymentShareSchema(BaseModel):
    """Request body for sharing an existing provider payment request."""

    channel: str = Field(description="Target channel such as `telegram` or `whatsapp`.")
    client_code: str | None = Field(
        default=None, description="Optional client override for delivery."
    )
    custom_message: str | None = Field(
        default=None, description="Optional delivery message override."
    )
    bot_instance_code: str | None = Field(
        default=None,
        description="Optional provider bot instance used for the share operation.",
    )

    model_config = ConfigDict(extra="forbid")


class PaymentStatusUpdateSchema(BaseModel):
    """Request body for manually updating the status of a payment request."""

    status: str = Field(description="Manual status value such as `pending`, `paid`, or `overdue`.")
    notes_summary: str | None = Field(
        default=None,
        description="Optional status note that is also stored on the payment request.",
    )

    model_config = ConfigDict(extra="forbid")


class PaymentNoteCreateSchema(BaseModel):
    """Request body for adding a payment note."""

    note: str = Field(description="Operator note attached to the payment request.")

    model_config = ConfigDict(extra="forbid")


class ReminderCreateSchema(BaseModel):
    """Request body for creating a provider reminder."""

    reminder_type: str = Field(description="Reminder type: scheduled, manual, or task.")
    channel: str = Field(description="Delivery channel such as `telegram` or `whatsapp`.")
    message: str = Field(description="Reminder text or message template.")
    payment_reference: str | None = Field(
        default=None,
        description="Optional payment reference linked to the reminder.",
    )
    client_code: str | None = Field(default=None, description="Optional explicit client target.")
    task_name: str | None = Field(
        default=None, description="Optional task name for task-based reminders."
    )
    scheduled_for: str | None = Field(
        default=None,
        description="Optional ISO-8601 datetime for scheduled delivery.",
    )
    include_qr: bool = Field(
        default=True,
        description="Attach the preferred QR asset when the reminder is payment-linked.",
    )

    model_config = ConfigDict(extra="forbid")


class BroadcastCreateSchema(BaseModel):
    """Request body for sending a multi-client broadcast."""

    channel: str = Field(description="Target channel such as `telegram` or `whatsapp`.")
    message: str = Field(description="Broadcast text or payment-share message.")
    client_codes: list[str] = Field(
        default_factory=list,
        description="Optional subset of client codes. Leave empty to target all provider clients.",
    )
    template_code: str | None = Field(
        default=None, description="Optional payment template for broadcasted requests."
    )
    amount: str | None = Field(
        default=None, description="Optional amount when creating payment-backed broadcasts."
    )
    item_code: str | None = Field(
        default=None, description="Optional item code used to resolve a template."
    )

    model_config = ConfigDict(extra="forbid")


class WhatsAppInboundSchema(BaseModel):
    """Inbound WhatsApp webhook payload accepted by provider bot routes."""

    from_number: str = Field(description="Sender phone number in E.164 format.")
    name: str = Field(description="Sender display name.")
    text: str = Field(description="Inbound message text.")

    model_config = ConfigDict(extra="forbid")
