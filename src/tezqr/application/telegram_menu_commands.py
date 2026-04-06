from __future__ import annotations

from dataclasses import dataclass

from tezqr.domain.enums import ProviderMemberRole


@dataclass(frozen=True, slots=True)
class TelegramMenuCommand:
    command: str
    description: str


def legacy_public_commands() -> list[TelegramMenuCommand]:
    return [
        TelegramMenuCommand("start", "Show welcome and help"),
        TelegramMenuCommand("setupi", "Save your UPI ID"),
        TelegramMenuCommand("pay", "Create a payment QR"),
        TelegramMenuCommand("provider_register", "Create a provider workspace"),
        TelegramMenuCommand("provider_bot", "Connect a BotFather bot"),
        TelegramMenuCommand("provider_destination", "Add a provider UPI destination"),
        TelegramMenuCommand("provider_me", "Show your provider workspaces"),
    ]


def legacy_admin_commands() -> list[TelegramMenuCommand]:
    return [
        *legacy_public_commands(),
        TelegramMenuCommand("stats", "View bot stats"),
        TelegramMenuCommand("approve", "Approve an upgrade request"),
        TelegramMenuCommand("broadcast", "Send a broadcast message"),
        TelegramMenuCommand("upgrade", "Upgrade a merchant"),
        TelegramMenuCommand("providers", "List provider workspaces"),
        TelegramMenuCommand("provider_overview", "Inspect a provider workspace"),
        TelegramMenuCommand("provider_members", "List provider team members"),
        TelegramMenuCommand("provider_bots", "List provider bot instances"),
        TelegramMenuCommand("provider_clients", "List provider clients"),
        TelegramMenuCommand("provider_payments", "List provider payments"),
    ]


def provider_public_commands() -> list[TelegramMenuCommand]:
    return [
        TelegramMenuCommand("start", "Show welcome and help"),
        TelegramMenuCommand("help", "Show command help"),
        TelegramMenuCommand("item_code", "Get a QR by item code"),
        TelegramMenuCommand("pay", "Create a payment QR"),
        TelegramMenuCommand("login", "Link this chat to a provider role"),
    ]


def provider_staff_commands(role: ProviderMemberRole) -> list[TelegramMenuCommand]:
    commands = [
        *provider_public_commands(),
        TelegramMenuCommand("whoami", "Show your linked provider role"),
        TelegramMenuCommand("onboardlink", "Get the client onboarding link"),
        TelegramMenuCommand("dashboard", "View provider counts"),
        TelegramMenuCommand("clients", "List saved client codes"),
        TelegramMenuCommand("payments", "List payments for a client"),
        TelegramMenuCommand("history", "Review payment history"),
        TelegramMenuCommand("logout", "Unlink this staff session"),
    ]
    if role in {
        ProviderMemberRole.OWNER,
        ProviderMemberRole.MANAGER,
        ProviderMemberRole.OPERATOR,
    }:
        commands.extend(
            [
                TelegramMenuCommand("charge", "Create a client payment"),
                TelegramMenuCommand("share", "Deliver an existing payment"),
                TelegramMenuCommand("status", "Update payment status"),
                TelegramMenuCommand("note", "Add an internal note"),
                TelegramMenuCommand("remind", "Send a reminder now"),
                TelegramMenuCommand("remindat", "Schedule a reminder"),
                TelegramMenuCommand("runreminders", "Process due reminders"),
            ]
        )
    if role in {ProviderMemberRole.OWNER, ProviderMemberRole.MANAGER}:
        commands.append(
            TelegramMenuCommand("memberadd", "Add a team member")
        )
    return commands


def to_telegram_menu_payload(
    commands: list[TelegramMenuCommand],
) -> list[dict[str, str]]:
    return [
        {"command": command.command, "description": command.description}
        for command in commands
    ]
