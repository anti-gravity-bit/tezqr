from __future__ import annotations

from tezqr.domain.entities import (
    FREE_GENERATION_LIMIT,
    PREMIUM_GENERATION_LIMIT,
    AdminStats,
    PaymentRequest,
)
from tezqr.domain.enums import MerchantTier
from tezqr.domain.value_objects import TelegramUser
from tezqr.shared.config import Settings


def welcome_message() -> str:
    return (
        "Welcome to TezQR.\n\n"
        "Create polished UPI payment QRs for your customers directly from Telegram.\n\n"
        f"Free plan: {FREE_GENERATION_LIMIT} QR generations\n"
        f"Growth pack: Rs 99 for {PREMIUM_GENERATION_LIMIT} QR generations\n\n"
        "Quick start:\n"
        "1. /setupi your@upi\n"
        "2. /pay 499 Advance payment\n\n"
        "Want your own branded provider bot?\n"
        "Use /provider_register <slug> <provider_name>"
    )


def help_message(*, is_admin: bool = False) -> str:
    admin_lines = ""
    if is_admin:
        admin_lines = (
            "\n\nOwner tools:\n"
            "/stats - view today's merchant activity\n"
            "/approve <request_code> - activate a paid 1000 QR pack\n"
            "/broadcast <message> - send an update or offer to all merchants\n"
            "/upgrade <telegram_id> - manual fallback upgrade\n"
            "/providers - list provider workspaces\n"
            "/provider_overview <provider_slug> - inspect a provider workspace\n"
            "/provider_members <provider_slug> - list provider team members\n"
            "/provider_bots <provider_slug> - list provider bot instances\n"
            "/provider_clients <provider_slug> - list provider clients\n"
            "/provider_payments <provider_slug> [client_code] - list provider payments"
        )
    return (
        "TezQR menu\n\n"
        "Merchant options:\n"
        "/start - activate your TezQR account\n"
        "/setupi <vpa_id> - save or update your UPI ID\n"
        "/pay <amount> <description> - generate a shareable UPI QR\n"
        "Send your payment screenshot here after buying a pack\n\n"
        "Provider onboarding:\n"
        "/provider_register <slug> <provider_name> - create your provider workspace\n"
        "/provider_bot <provider_slug> <bot_token> [public_handle] - connect a BotFather bot\n"
        "/provider_destination <provider_slug> <code> <vpa> <payee_name> - add a UPI destination\n"
        "/provider_me - show your linked provider workspaces\n\n"
        "Examples:\n"
        "/setupi yourname@upi\n"
        "/pay 499 Website design advance\n"
        "/provider_register orbit-pay Orbit Pay\n"
        "/provider_bot orbit-pay 123456:ABCDEF https://t.me/orbitpaybot\n"
        "/provider_destination orbit-pay MAIN orbit@okaxis Orbit Pay\n\n"
        f"Plans:\nFree: {FREE_GENERATION_LIMIT} QRs\n"
        f"Growth pack: Rs 99 for {PREMIUM_GENERATION_LIMIT} QRs"
        f"{admin_lines}"
    )


def fallback_menu_message(*, is_admin: bool = False) -> str:
    return (
        "I did not recognise that message, but I can help with the options below.\n\n"
        f"{help_message(is_admin=is_admin)}"
    )


def malformed_command_message(name: str, usage: str) -> str:
    return f"The /{name} command is incomplete.\nUse: {usage}"


def invalid_vpa_message() -> str:
    return "That UPI ID looks invalid.\nUse: /setupi your@upi"


def setup_success_message(vpa: str) -> str:
    return (
        "UPI ID saved successfully.\n\n"
        f"UPI ID: {vpa}\n\n"
        "You can now generate a payment QR with:\n"
        "/pay <amount> <description>"
    )


def invalid_amount_message() -> str:
    return "Amount must be a valid positive number.\nUse: /pay <amount> <description>"


def start_required_message() -> str:
    return (
        "Your TezQR account is not active yet.\n"
        "Send /start first, then save your UPI ID with /setupi <vpa_id>."
    )


def setup_required_message() -> str:
    return "Please save your UPI ID first with /setupi <vpa_id>."


def missing_description_message() -> str:
    return "Please add a payment description.\nUse: /pay <amount> <description>"


def payment_qr_caption(payment_request: PaymentRequest, bot_public_link: str) -> str:
    return (
        "TezQR Payment Pass\n\n"
        "Collect Rs "
        f"{payment_request.amount.as_upi_amount()} for {payment_request.description}.\n\n"
        "Share this with your customer. They can scan it "
        "or pay instantly from the UPI link below.\n\n"
        f"Tap to pay:\n{payment_request.upi_uri}\n\n"
        f"Reference: {payment_request.reference.value}\n"
        "Fast checkout. Clean records. Zero confusion.\n\n"
        "Powered by TezQR on Telegram.\n"
        f"Make your own payment QR: {bot_public_link}"
    )


def paywall_message(
    settings: Settings,
    tier: MerchantTier,
    payment_link: str | None = None,
) -> str:
    if tier == MerchantTier.PREMIUM:
        header = f"Your current {PREMIUM_GENERATION_LIMIT} QR pack is exhausted."
        offer = (
            f"Renew for Rs {settings.subscription_price_inr} to unlock another "
            f"{PREMIUM_GENERATION_LIMIT} QR generations."
        )
    else:
        header = f"You have used all {FREE_GENERATION_LIMIT} free TezQR QR generations."
        offer = (
            f"Upgrade for Rs {settings.subscription_price_inr} to unlock "
            f"{PREMIUM_GENERATION_LIMIT} QR generations."
        )
    lines = [
        header,
        offer,
        "",
        "Next steps:",
        "1. Pay using the QR or UPI details below",
        "2. Reply here with the payment screenshot",
        "3. The TezQR owner will verify your payment and activate your next pack",
        "",
        f"UPI ID: {settings.effective_subscription_upi_id}",
    ]
    effective_link = payment_link or settings.subscription_payment_link
    if effective_link:
        lines.extend(["Payment link:", effective_link])
    return "\n".join(lines)


def screenshot_received_message(approval_code: str) -> str:
    return (
        "Payment screenshot received.\n\n"
        f"Request code: {approval_code}\n"
        "We will verify it shortly and activate your "
        f"{PREMIUM_GENERATION_LIMIT} QR pack once the payment is confirmed."
    )


def already_premium_message() -> str:
    return (
        "TezQR Premium is already active on your account.\n"
        "Use /pay <amount> <description> to keep generating payment QRs."
    )


def free_plan_still_available_message() -> str:
    return (
        "Your free plan is still active.\n"
        "You can continue using /pay <amount> <description> until you reach 20 generations."
    )


def admin_upgrade_request_message(user: TelegramUser, approval_code: str) -> str:
    return (
        "New pack approval request received.\n\n"
        f"Merchant: {user.display_name}\n"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"Request code: {approval_code}\n\n"
        f"After verifying payment, run:\n/approve {approval_code}"
    )


def stats_message(local_date: str, stats: AdminStats) -> str:
    return (
        "TezQR daily stats\n\n"
        f"Date: {local_date}\n"
        f"Active merchants: {stats.daily_active_users}\n"
        f"Total QR generations: {stats.total_generations}"
    )


def merchant_not_found_message(telegram_id: int) -> str:
    return f"No merchant account was found for Telegram ID {telegram_id}."


def admin_upgrade_success_message(telegram_id: int) -> str:
    return (
        f"Merchant {telegram_id} has been upgraded to TezQR Premium "
        f"with a fresh {PREMIUM_GENERATION_LIMIT} QR pack."
    )


def approve_request_not_found_message(approval_code: str) -> str:
    return (
        f"No pending payment request was found for code {approval_code.upper()}.\n"
        "Check the code and try again."
    )


def admin_approval_success_message(approval_code: str, telegram_id: int) -> str:
    return (
        f"Approved {approval_code.upper()} for merchant {telegram_id}.\n"
        f"A fresh {PREMIUM_GENERATION_LIMIT} QR pack is now active."
    )


def merchant_upgrade_confirmation_message(approval_code: str) -> str:
    return (
        "TezQR Premium is now active on your account.\n"
        f"Approval code: {approval_code}\n"
        f"You now have {PREMIUM_GENERATION_LIMIT} QR generations in this pack."
    )


def broadcast_delivery_message(message: str, bot_public_link: str) -> str:
    return (
        "TezQR update\n\n"
        f"{message.strip()}\n\n"
        f"Need a payment QR? Open TezQR here: {bot_public_link}"
    )


def broadcast_summary_message(*, recipients: int, delivered: int, failed: int) -> str:
    return (
        "Broadcast complete.\n\n"
        f"Target merchants: {recipients}\n"
        f"Delivered: {delivered}\n"
        f"Failed: {failed}"
    )


def admin_only_message() -> str:
    return "This command is available only to the TezQR owner account."
