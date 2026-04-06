from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProviderBotStartCommand:
    name: str = "start"


@dataclass(frozen=True, slots=True)
class ProviderBotHelpCommand:
    name: str = "help"


@dataclass(frozen=True, slots=True)
class ProviderBotLoginCommand:
    actor_code: str
    api_key: str
    name: str = "login"


@dataclass(frozen=True, slots=True)
class ProviderBotLogoutCommand:
    name: str = "logout"


@dataclass(frozen=True, slots=True)
class ProviderBotWhoamiCommand:
    name: str = "whoami"


@dataclass(frozen=True, slots=True)
class ProviderBotOnboardLinkCommand:
    name: str = "onboardlink"


@dataclass(frozen=True, slots=True)
class ProviderBotDashboardCommand:
    name: str = "dashboard"


@dataclass(frozen=True, slots=True)
class ProviderBotClientsCommand:
    name: str = "clients"


@dataclass(frozen=True, slots=True)
class ProviderBotClientPaymentsCommand:
    client_code: str
    name: str = "payments"


@dataclass(frozen=True, slots=True)
class ProviderBotHistoryCommand:
    payment_reference: str
    name: str = "history"


@dataclass(frozen=True, slots=True)
class ProviderBotChargeCommand:
    client_code: str
    amount: str
    description: str
    name: str = "charge"


@dataclass(frozen=True, slots=True)
class ProviderBotShareCommand:
    payment_reference: str
    channel: str | None = None
    name: str = "share"


@dataclass(frozen=True, slots=True)
class ProviderBotStatusCommand:
    payment_reference: str
    status: str
    notes_summary: str | None = None
    name: str = "status"


@dataclass(frozen=True, slots=True)
class ProviderBotNoteCommand:
    payment_reference: str
    note: str
    name: str = "note"


@dataclass(frozen=True, slots=True)
class ProviderBotReminderCommand:
    payment_reference: str
    message: str
    scheduled_for: datetime | None = None
    name: str = "remind"


@dataclass(frozen=True, slots=True)
class ProviderBotRunRemindersCommand:
    name: str = "runreminders"


@dataclass(frozen=True, slots=True)
class ProviderBotMemberAddCommand:
    actor_code: str
    role: str
    display_name: str
    name: str = "memberadd"


@dataclass(frozen=True, slots=True)
class ProviderBotItemCodeCommand:
    item_code: str
    amount: str | None = None
    name: str = "item-code"


@dataclass(frozen=True, slots=True)
class ProviderBotPayCommand:
    amount: str
    description: str
    name: str = "pay"


@dataclass(frozen=True, slots=True)
class ProviderBotUnsupportedCommand:
    raw: str


@dataclass(frozen=True, slots=True)
class ProviderBotMalformedCommand:
    name: str
    usage: str


@dataclass(frozen=True, slots=True)
class ProviderBotPlainText:
    raw: str


@dataclass(frozen=True, slots=True)
class ProviderBotEmptyInput:
    pass


ProviderBotParsedInput = (
    ProviderBotStartCommand
    | ProviderBotHelpCommand
    | ProviderBotLoginCommand
    | ProviderBotLogoutCommand
    | ProviderBotWhoamiCommand
    | ProviderBotOnboardLinkCommand
    | ProviderBotDashboardCommand
    | ProviderBotClientsCommand
    | ProviderBotClientPaymentsCommand
    | ProviderBotHistoryCommand
    | ProviderBotChargeCommand
    | ProviderBotShareCommand
    | ProviderBotStatusCommand
    | ProviderBotNoteCommand
    | ProviderBotReminderCommand
    | ProviderBotRunRemindersCommand
    | ProviderBotMemberAddCommand
    | ProviderBotItemCodeCommand
    | ProviderBotPayCommand
    | ProviderBotUnsupportedCommand
    | ProviderBotMalformedCommand
    | ProviderBotPlainText
    | ProviderBotEmptyInput
)


def parse_provider_bot_input(text: str | None) -> ProviderBotParsedInput:
    normalized = (text or "").strip()
    if not normalized:
        return ProviderBotEmptyInput()

    if not normalized.startswith("/"):
        return ProviderBotPlainText(raw=normalized)

    parts = normalized.split(maxsplit=3)
    command = parts[0].split("@", 1)[0].lower()
    remainder = normalized[len(parts[0]) :].strip()

    if command == "/start":
        return ProviderBotStartCommand()
    if command == "/help":
        return ProviderBotHelpCommand()
    if command == "/login":
        if len(parts) < 3:
            return ProviderBotMalformedCommand("login", "/login <actor_code> <api_key>")
        return ProviderBotLoginCommand(actor_code=parts[1].strip(), api_key=parts[2].strip())
    if command == "/logout":
        return ProviderBotLogoutCommand()
    if command == "/whoami":
        return ProviderBotWhoamiCommand()
    if command == "/onboardlink":
        return ProviderBotOnboardLinkCommand()
    if command == "/dashboard":
        return ProviderBotDashboardCommand()
    if command == "/clients":
        return ProviderBotClientsCommand()
    if command == "/payments":
        if len(parts) < 2:
            return ProviderBotMalformedCommand("payments", "/payments <client_code>")
        return ProviderBotClientPaymentsCommand(client_code=parts[1].strip())
    if command == "/history":
        if len(parts) < 2:
            return ProviderBotMalformedCommand("history", "/history <payment_reference>")
        return ProviderBotHistoryCommand(payment_reference=parts[1].strip())
    if command == "/charge":
        if len(parts) < 4:
            return ProviderBotMalformedCommand(
                "charge",
                "/charge <client_code> <amount> <description>",
            )
        return ProviderBotChargeCommand(
            client_code=parts[1].strip(),
            amount=parts[2].strip(),
            description=parts[3].strip(),
        )
    if command == "/share":
        if len(parts) < 2:
            return ProviderBotMalformedCommand(
                "share",
                "/share <payment_reference> [telegram|whatsapp]",
            )
        channel = parts[2].strip() if len(parts) > 2 else None
        return ProviderBotShareCommand(payment_reference=parts[1].strip(), channel=channel)
    if command == "/status":
        if len(parts) < 3:
            return ProviderBotMalformedCommand(
                "status",
                "/status <payment_reference> <pending|paid|overdue> [notes]",
            )
        notes = parts[3].strip() if len(parts) > 3 else None
        return ProviderBotStatusCommand(
            payment_reference=parts[1].strip(),
            status=parts[2].strip(),
            notes_summary=notes,
        )
    if command == "/note":
        if len(parts) < 3:
            return ProviderBotMalformedCommand("note", "/note <payment_reference> <note>")
        return ProviderBotNoteCommand(
            payment_reference=parts[1].strip(),
            note=remainder.split(maxsplit=1)[1],
        )
    if command == "/remind":
        if len(parts) < 3:
            return ProviderBotMalformedCommand("remind", "/remind <payment_reference> <message>")
        return ProviderBotReminderCommand(
            payment_reference=parts[1].strip(),
            message=remainder.split(maxsplit=1)[1],
        )
    if command == "/remindat":
        if len(parts) < 4:
            return ProviderBotMalformedCommand(
                "remindat",
                "/remindat <payment_reference> <iso_datetime> <message>",
            )
        try:
            scheduled_for = datetime.fromisoformat(parts[2].strip())
        except ValueError:
            return ProviderBotMalformedCommand(
                "remindat",
                "/remindat <payment_reference> <iso_datetime> <message>",
            )
        return ProviderBotReminderCommand(
            payment_reference=parts[1].strip(),
            message=parts[3].strip(),
            scheduled_for=scheduled_for,
        )
    if command == "/runreminders":
        return ProviderBotRunRemindersCommand()
    if command == "/memberadd":
        if len(parts) < 4:
            return ProviderBotMalformedCommand(
                "memberadd",
                "/memberadd <actor_code> <owner|manager|operator|viewer> <display_name>",
            )
        return ProviderBotMemberAddCommand(
            actor_code=parts[1].strip(),
            role=parts[2].strip(),
            display_name=parts[3].strip(),
        )
    if command in {"/item-code", "/item_code"}:
        if len(parts) < 2:
            return ProviderBotMalformedCommand("item_code", "/item_code <code> [amount]")
        amount = parts[2].strip() if len(parts) > 2 else None
        return ProviderBotItemCodeCommand(item_code=parts[1].strip(), amount=amount)
    if command == "/pay":
        if len(parts) < 3 or not parts[2].strip():
            return ProviderBotMalformedCommand("pay", "/pay <amount> <description>")
        return ProviderBotPayCommand(amount=parts[1].strip(), description=parts[2].strip())

    return ProviderBotUnsupportedCommand(raw=parts[0])
