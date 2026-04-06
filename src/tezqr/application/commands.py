from __future__ import annotations

from dataclasses import dataclass

from tezqr.application.dto import IncomingAttachment, IncomingMessage


@dataclass(frozen=True, slots=True)
class StartCommand:
    name: str = "start"


@dataclass(frozen=True, slots=True)
class SetupiCommand:
    vpa: str
    name: str = "setupi"


@dataclass(frozen=True, slots=True)
class PayCommand:
    amount: str
    description: str
    name: str = "pay"


@dataclass(frozen=True, slots=True)
class StatsCommand:
    name: str = "stats"


@dataclass(frozen=True, slots=True)
class UpgradeCommand:
    target_telegram_id: int
    name: str = "upgrade"


@dataclass(frozen=True, slots=True)
class ApproveCommand:
    approval_code: str
    name: str = "approve"


@dataclass(frozen=True, slots=True)
class BroadcastCommand:
    message: str
    name: str = "broadcast"


@dataclass(frozen=True, slots=True)
class ProviderRegisterCommand:
    slug: str
    provider_name: str
    name: str = "provider_register"


@dataclass(frozen=True, slots=True)
class ProviderBotCommand:
    provider_slug: str
    bot_token: str
    public_handle: str | None = None
    name: str = "provider_bot"


@dataclass(frozen=True, slots=True)
class ProviderDestinationCommand:
    provider_slug: str
    code: str
    vpa: str
    payee_name: str
    name: str = "provider_destination"


@dataclass(frozen=True, slots=True)
class ProviderMeCommand:
    name: str = "provider_me"


@dataclass(frozen=True, slots=True)
class ProvidersCommand:
    name: str = "providers"


@dataclass(frozen=True, slots=True)
class ProviderOverviewCommand:
    provider_slug: str
    name: str = "provider_overview"


@dataclass(frozen=True, slots=True)
class ProviderMembersCommand:
    provider_slug: str
    name: str = "provider_members"


@dataclass(frozen=True, slots=True)
class ProviderBotsCommand:
    provider_slug: str
    name: str = "provider_bots"


@dataclass(frozen=True, slots=True)
class ProviderClientsCommand:
    provider_slug: str
    name: str = "provider_clients"


@dataclass(frozen=True, slots=True)
class ProviderPaymentsCommand:
    provider_slug: str
    client_code: str | None = None
    name: str = "provider_payments"


@dataclass(frozen=True, slots=True)
class ScreenshotSubmission:
    attachment: IncomingAttachment


@dataclass(frozen=True, slots=True)
class PlainTextMessage:
    raw: str


@dataclass(frozen=True, slots=True)
class UnsupportedCommand:
    raw: str


@dataclass(frozen=True, slots=True)
class MalformedCommand:
    name: str
    usage: str


@dataclass(frozen=True, slots=True)
class EmptyInput:
    pass


ParsedInput = (
    StartCommand
    | SetupiCommand
    | PayCommand
    | StatsCommand
    | UpgradeCommand
    | ApproveCommand
    | BroadcastCommand
    | ProviderRegisterCommand
    | ProviderBotCommand
    | ProviderDestinationCommand
    | ProviderMeCommand
    | ProvidersCommand
    | ProviderOverviewCommand
    | ProviderMembersCommand
    | ProviderBotsCommand
    | ProviderClientsCommand
    | ProviderPaymentsCommand
    | ScreenshotSubmission
    | PlainTextMessage
    | UnsupportedCommand
    | MalformedCommand
    | EmptyInput
)


def parse_message(message: IncomingMessage) -> ParsedInput:
    text = (message.text or "").strip()
    if text.startswith("/"):
        parts = text.split(maxsplit=4)
        command = parts[0].split("@", 1)[0].lower()
        remainder = text[len(parts[0]) :].strip()

        if command == "/start":
            return StartCommand()
        if command == "/setupi":
            if not remainder:
                return MalformedCommand(name="setupi", usage="/setupi <vpa_id>")
            return SetupiCommand(vpa=remainder)
        if command == "/pay":
            pay_parts = remainder.split(maxsplit=1)
            if len(pay_parts) < 2 or not pay_parts[1].strip():
                return MalformedCommand(name="pay", usage="/pay <amount> <desc>")
            return PayCommand(amount=pay_parts[0].strip(), description=pay_parts[1].strip())
        if command == "/stats":
            return StatsCommand()
        if command == "/upgrade":
            if not remainder:
                return MalformedCommand(name="upgrade", usage="/upgrade <target_telegram_id>")
            try:
                target_telegram_id = int(remainder)
            except ValueError:
                return MalformedCommand(name="upgrade", usage="/upgrade <target_telegram_id>")
            return UpgradeCommand(target_telegram_id=target_telegram_id)
        if command == "/approve":
            if not remainder:
                return MalformedCommand(name="approve", usage="/approve <request_code>")
            return ApproveCommand(approval_code=remainder)
        if command == "/broadcast":
            if not remainder:
                return MalformedCommand(name="broadcast", usage="/broadcast <message>")
            return BroadcastCommand(message=remainder)
        if command == "/provider_register":
            register_parts = remainder.split(maxsplit=1)
            if len(register_parts) < 2:
                return MalformedCommand(
                    name="provider_register",
                    usage="/provider_register <slug> <provider_name>",
                )
            return ProviderRegisterCommand(
                slug=register_parts[0].strip(),
                provider_name=register_parts[1].strip(),
            )
        if command == "/provider_bot":
            bot_parts = remainder.split(maxsplit=2)
            if len(bot_parts) < 2:
                return MalformedCommand(
                    name="provider_bot",
                    usage="/provider_bot <provider_slug> <bot_token> [public_handle]",
                )
            return ProviderBotCommand(
                provider_slug=bot_parts[0].strip(),
                bot_token=bot_parts[1].strip(),
                public_handle=bot_parts[2].strip() if len(bot_parts) > 2 else None,
            )
        if command == "/provider_destination":
            destination_parts = remainder.split(maxsplit=3)
            if len(destination_parts) < 4:
                return MalformedCommand(
                    name="provider_destination",
                    usage="/provider_destination <provider_slug> <code> <vpa> <payee_name>",
                )
            return ProviderDestinationCommand(
                provider_slug=destination_parts[0].strip(),
                code=destination_parts[1].strip(),
                vpa=destination_parts[2].strip(),
                payee_name=destination_parts[3].strip(),
            )
        if command == "/provider_me":
            return ProviderMeCommand()
        if command == "/providers":
            return ProvidersCommand()
        if command == "/provider_overview":
            if not remainder:
                return MalformedCommand(
                    name="provider_overview",
                    usage="/provider_overview <provider_slug>",
                )
            return ProviderOverviewCommand(provider_slug=remainder)
        if command == "/provider_members":
            if not remainder:
                return MalformedCommand(
                    name="provider_members",
                    usage="/provider_members <provider_slug>",
                )
            return ProviderMembersCommand(provider_slug=remainder)
        if command == "/provider_bots":
            if not remainder:
                return MalformedCommand(
                    name="provider_bots",
                    usage="/provider_bots <provider_slug>",
                )
            return ProviderBotsCommand(provider_slug=remainder)
        if command == "/provider_clients":
            if not remainder:
                return MalformedCommand(
                    name="provider_clients",
                    usage="/provider_clients <provider_slug>",
                )
            return ProviderClientsCommand(provider_slug=remainder)
        if command == "/provider_payments":
            payment_parts = remainder.split(maxsplit=1)
            if not payment_parts or not payment_parts[0].strip():
                return MalformedCommand(
                    name="provider_payments",
                    usage="/provider_payments <provider_slug> [client_code]",
                )
            return ProviderPaymentsCommand(
                provider_slug=payment_parts[0].strip(),
                client_code=payment_parts[1].strip() if len(payment_parts) > 1 else None,
            )
        return UnsupportedCommand(raw=parts[0])

    if message.attachment is not None:
        return ScreenshotSubmission(attachment=message.attachment)

    if text:
        return PlainTextMessage(raw=text)

    return EmptyInput()
