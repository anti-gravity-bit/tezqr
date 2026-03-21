from __future__ import annotations

from tezqr.domain.entities import AdminStats, PaymentRequest
from tezqr.domain.value_objects import TelegramUser
from tezqr.shared.config import Settings


def welcome_message() -> str:
    return (
        "Welcome to TezQR.\n\n"
        "You can use this bot to create clean UPI payment QR codes for your customers.\n\n"
        "Getting started:\n"
        "1. Save your UPI ID with /setupi your@upi\n"
        "2. Generate a payment QR with /pay <amount> <description>\n\n"
        "Your free plan includes 20 QR generations."
    )


def help_message() -> str:
    return (
        "TezQR commands:\n"
        "/start\n"
        "/setupi <vpa_id>\n"
        "/pay <amount> <description>\n\n"
        "Example:\n"
        "/pay 499 Website design advance"
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


def payment_qr_caption(payment_request: PaymentRequest) -> str:
    return (
        "Payment QR ready.\n\n"
        f"Amount: Rs {payment_request.amount.as_upi_amount()}\n"
        f"Description: {payment_request.description}\n"
        f"Reference: {payment_request.reference.value}\n\n"
        f"UPI link:\n{payment_request.upi_uri}"
    )


def paywall_message(settings: Settings) -> str:
    lines = [
        "Free plan limit reached.",
        "",
        "You have used all 20 free TezQR QR generations.",
        f"Upgrade to TezQR Premium for Rs {settings.subscription_price_inr}.",
        "",
        "Next steps:",
        "1. Pay using the details below",
        "2. Reply here with the payment screenshot",
        "3. The TezQR owner will verify your payment and activate premium access",
        "",
        f"UPI ID: {settings.effective_subscription_upi_id}",
    ]
    if settings.subscription_payment_link:
        lines.extend(["Payment link:", settings.subscription_payment_link])
    return "\n".join(lines)


def screenshot_received_message() -> str:
    return (
        "Payment screenshot received.\n\n"
        "We will verify it shortly and upgrade your TezQR account once the payment is confirmed."
    )


def already_premium_message() -> str:
    return "TezQR Premium is already active on your account."


def free_plan_still_available_message() -> str:
    return (
        "Your free plan is still active.\n"
        "You can continue using /pay <amount> <description> until you reach 20 generations."
    )


def admin_upgrade_request_message(user: TelegramUser) -> str:
    return (
        "New premium upgrade request received.\n\n"
        f"Merchant: {user.display_name}\n"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"After verifying payment, run:\n/upgrade {user.telegram_id}"
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
    return f"Merchant {telegram_id} has been upgraded to TezQR Premium."


def merchant_upgrade_confirmation_message() -> str:
    return (
        "TezQR Premium is now active on your account.\nYou can generate unlimited payment QR codes."
    )


def admin_only_message() -> str:
    return "This command is available only to the TezQR owner account."
