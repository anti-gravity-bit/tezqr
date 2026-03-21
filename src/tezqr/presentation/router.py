from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from tezqr.application.dto import IncomingAttachment, IncomingMessage
from tezqr.domain.value_objects import TelegramUser
from tezqr.presentation.schemas import TelegramMessageSchema, TelegramUpdateSchema

router = APIRouter()


def _message_to_dto(message: TelegramMessageSchema) -> IncomingMessage:
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


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.container.settings
    return {"status": "ok", "environment": settings.app_env}


@router.post("/webhooks/telegram/{webhook_secret}")
async def telegram_webhook(
    webhook_secret: str,
    payload: TelegramUpdateSchema,
    request: Request,
) -> dict[str, bool]:
    container = request.app.state.container
    if webhook_secret != container.settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")

    message = payload.message or payload.edited_message
    if message is None:
        return {"ok": True}

    await container.bot_service.handle_message(_message_to_dto(message))
    return {"ok": True}
