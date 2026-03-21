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
class ScreenshotSubmission:
    attachment: IncomingAttachment


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
    | ScreenshotSubmission
    | UnsupportedCommand
    | MalformedCommand
    | EmptyInput
)


def parse_message(message: IncomingMessage) -> ParsedInput:
    text = (message.text or "").strip()
    if text.startswith("/"):
        parts = text.split(maxsplit=2)
        command = parts[0].split("@", 1)[0].lower()

        if command == "/start":
            return StartCommand()
        if command == "/setupi":
            if len(parts) < 2:
                return MalformedCommand(name="setupi", usage="/setupi <vpa_id>")
            return SetupiCommand(vpa=parts[1].strip())
        if command == "/pay":
            if len(parts) < 3 or not parts[2].strip():
                return MalformedCommand(name="pay", usage="/pay <amount> <desc>")
            return PayCommand(amount=parts[1].strip(), description=parts[2].strip())
        if command == "/stats":
            return StatsCommand()
        if command == "/upgrade":
            if len(parts) < 2:
                return MalformedCommand(name="upgrade", usage="/upgrade <target_telegram_id>")
            try:
                target_telegram_id = int(parts[1].strip())
            except ValueError:
                return MalformedCommand(name="upgrade", usage="/upgrade <target_telegram_id>")
            return UpgradeCommand(target_telegram_id=target_telegram_id)
        return UnsupportedCommand(raw=parts[0])

    if message.attachment is not None:
        return ScreenshotSubmission(attachment=message.attachment)

    return EmptyInput()
