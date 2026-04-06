"""Shared HTTP adapter helpers for FastAPI controllers."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from typing import TypeVar

from fastapi import HTTPException, Request, status

from tezqr.application.control_plane import ControlPlaneService
from tezqr.application.dto import IncomingAttachment, IncomingMessage
from tezqr.domain.exceptions import AuthorizationError, DomainValidationError
from tezqr.domain.value_objects import TelegramUser
from tezqr.presentation.schemas import TelegramMessageSchema

T = TypeVar("T")


def message_to_dto(message: TelegramMessageSchema) -> IncomingMessage:
    """Convert an inbound Telegram webhook payload into the application DTO."""
    attachment = None
    if message.photo:
        largest = message.photo[-1]
        attachment = IncomingAttachment(
            kind="photo",
            file_id=largest.file_id,
            file_unique_id=largest.file_unique_id,
        )
    elif message.document:
        attachment = IncomingAttachment(
            kind="document",
            file_id=message.document.file_id,
            file_unique_id=message.document.file_unique_id,
            mime_type=message.document.mime_type,
        )

    return IncomingMessage(
        message_id=message.message_id,
        chat_id=message.chat.id,
        from_user=TelegramUser(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username,
            last_name=message.from_user.last_name,
        ),
        text=(message.text or message.caption or None),
        attachment=attachment,
    )


def get_control_plane_service(request: Request) -> ControlPlaneService:
    """Resolve the provider control-plane service from the application container."""
    service = getattr(request.app.state.container, "control_plane_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Control plane service is unavailable.")
    return service


async def run_control(operation: Awaitable[T]) -> T:
    """Translate domain/application errors into stable HTTP responses."""
    try:
        return await operation
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse ISO-8601 timestamps used by provider APIs."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime: {value}",
        ) from exc
