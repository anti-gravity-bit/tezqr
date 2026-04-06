"""Message-formatting helpers for provider payment workflows."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from tezqr.domain.enums import BotPlatform, ProviderMemberRole
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
        *,
        member_role: ProviderMemberRole | None = None,
    ) -> str:
        logo_text = (branding or {}).get("logo_text", provider_name[:2].upper())
        lines = [
            f"{provider_name} {logo_text}\n\n"
            "Commands:\n"
            "/item-code <code> [amount] - get a product or service QR\n"
            "/pay <amount> <description> - create a custom payment QR\n"
            "/login <actor_code> <api_key> - link this chat to a provider role"
        ]
        if member_role is not None:
            lines.append(self.build_staff_help(provider_name, member_role))
        else:
            lines.append("\nProvider staff can link this chat and unlock role-based commands.")
        return "".join(lines)

    def build_bot_payment_caption(self, provider_name: str, payment: dict[str, Any]) -> str:
        return (
            f"{provider_name} payment\n\n"
            f"Reference: {payment['reference']}\n"
            f"Amount: Rs {payment['amount']}\n"
            f"Description: {payment['description']}\n"
            f"UPI link: {payment['upi_uri']}"
        )

    def build_staff_help(self, provider_name: str, role: ProviderMemberRole) -> str:
        lines = [
            f"\n\n{provider_name} staff commands:\n"
            "/whoami - show your linked provider role\n"
            "/onboardlink - get the client onboarding link\n"
            "/dashboard - view provider counts\n"
            "/clients - list saved client codes\n"
            "/payments <client_code> - list payments for a client\n"
            "/history <payment_reference> - review payment notes and events"
        ]
        if role in {
            ProviderMemberRole.OWNER,
            ProviderMemberRole.MANAGER,
            ProviderMemberRole.OPERATOR,
        }:
            lines.extend(
                [
                    "\n/charge <client_code> <amount> <description> - create a client payment",
                    (
                        "\n/share <payment_reference> [telegram|whatsapp] - "
                        "deliver an existing payment"
                    ),
                    (
                        "\n/status <payment_reference> <pending|paid|overdue> [notes] - "
                        "update payment status"
                    ),
                    "\n/note <payment_reference> <note> - add an internal payment note",
                    "\n/remind <payment_reference> <message> - send a reminder now",
                    (
                        "\n/remindat <payment_reference> <iso_datetime> <message> - "
                        "schedule a reminder"
                    ),
                    "\n/runreminders - process due reminders",
                ]
            )
        if role in {ProviderMemberRole.OWNER, ProviderMemberRole.MANAGER}:
            lines.append(
                "\n/memberadd <actor_code> <owner|manager|operator|viewer> "
                "<display_name> - add a team member"
            )
        lines.append("\n/logout - unlink this chat from the staff role")
        return "".join(lines)

    def build_member_identity_message(
        self,
        provider_name: str,
        actor_code: str,
        display_name: str,
        role: ProviderMemberRole,
    ) -> str:
        return (
            f"{provider_name} staff session\n\n"
            f"Actor: {actor_code}\n"
            f"Name: {display_name}\n"
            f"Role: {role.value}"
        )

    def build_onboarding_link_message(
        self,
        provider_name: str,
        platform: BotPlatform,
        public_handle: str | None,
    ) -> str:
        if public_handle:
            return (
                f"{provider_name} onboarding\n\n"
                f"Share this {platform.value} entry point with clients:\n"
                f"{public_handle}"
            )
        return (
            f"{provider_name} onboarding\n\n"
            f"No public {platform.value} handle is configured on this bot yet."
        )
