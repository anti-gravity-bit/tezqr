"""Legacy Telegram merchant bot webhook controller."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from tezqr.presentation.dependencies import message_to_dto
from tezqr.presentation.schemas import TelegramUpdateSchema

router = APIRouter(tags=["Merchant Bot"])


@router.post(
    "/webhooks/telegram/{webhook_secret}",
    summary="Process Legacy Telegram Webhook",
    description=(
        "Handle inbound Telegram updates for the original TezQR merchant bot flow. "
        "This route keeps the historic onboarding, `/setupi`, `/pay`, and upgrade "
        "approval workflow intact."
    ),
)
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

    await container.bot_service.handle_message(message_to_dto(message))
    return {"ok": True}
