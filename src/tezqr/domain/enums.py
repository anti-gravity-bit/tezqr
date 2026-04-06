from __future__ import annotations

from enum import StrEnum


class MerchantTier(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class ProviderMemberRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"
    API = "api"


class BotPlatform(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"


class ReminderType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    TASK = "task"


class ReminderStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageChannel(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SHARE_LINK = "share_link"
    MANUAL = "manual"


class DeliveryState(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    MANUAL_SHARE = "manual_share"
    FAILED = "failed"


class QrAssetType(StrEnum):
    PAYMENT_QR = "payment_qr"
    PAYMENT_CARD = "payment_card"
    PRINT_READY = "print_ready"
    TEMPLATE_QR = "template_qr"
