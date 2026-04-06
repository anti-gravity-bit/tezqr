"""Message-formatting helpers for provider payment workflows."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from tezqr.domain.value_objects import PhoneNumber
from tezqr.infrastructure.persistence.models import ClientModel, PaymentRequestModel, ProviderModel


class _DefaultFormatDict(dict[str, str]):
    """Keep format-map placeholders stable when optional values are missing."""

    def __missing__(self, key: str) -> str:
        return ""


class ProviderMessageComposer:
    """Build outbound human-readable messages from provider payment models."""

    def build_payment_message(
        self,
        *,
        provider: ProviderModel,
        client: ClientModel | None,
        payment: PaymentRequestModel,
        custom_message: str | None,
    ) -> str:
        base_message = custom_message or payment.custom_message or "Please complete your payment."
        mapping = _DefaultFormatDict(
            {
                "provider_name": provider.name,
                "client_name": client.full_name if client else "",
                "amount": f"{payment.amount:.2f}",
                "description": payment.description,
                "item_code": payment.item_code or "",
                "payment_link": payment.upi_uri,
                "reference": payment.reference,
            }
        )
        rendered = base_message.format_map(mapping)
        return (
            f"{provider.name}\n\n"
            f"{rendered}\n\n"
            f"Amount: Rs {payment.amount:.2f}\n"
            f"Reference: {payment.reference}\n"
            f"UPI link: {payment.upi_uri}"
        )

    def build_whatsapp_share_link(self, phone: PhoneNumber, message: str) -> str:
        return f"https://wa.me/{phone.wa_id}?text={quote(message)}"

    def build_bot_welcome_message(
        self,
        provider_name: str,
        branding: dict[str, str] | None,
    ) -> str:
        logo_text = (branding or {}).get("logo_text", provider_name[:2].upper())
        return (
            f"{provider_name} {logo_text}\n\n"
            "Commands:\n"
            "/item-code <code> [amount] - get a product or service QR\n"
            "/pay <amount> <description> - create a custom payment QR"
        )

    def build_bot_payment_caption(self, provider_name: str, payment: dict[str, Any]) -> str:
        return (
            f"{provider_name} payment\n\n"
            f"Reference: {payment['reference']}\n"
            f"Amount: Rs {payment['amount']}\n"
            f"Description: {payment['description']}\n"
            f"UPI link: {payment['upi_uri']}"
        )
