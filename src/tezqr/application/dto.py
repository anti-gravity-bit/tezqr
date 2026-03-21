from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tezqr.domain.value_objects import TelegramUser


@dataclass(frozen=True, slots=True)
class IncomingAttachment:
    kind: Literal["photo", "document"]
    file_id: str
    file_unique_id: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    message_id: int
    chat_id: int
    from_user: TelegramUser
    text: str | None = None
    attachment: IncomingAttachment | None = None
