"""White-label provider bot webhook controller."""

from __future__ import annotations

from fastapi import APIRouter, Request

from tezqr.presentation.dependencies import (
    get_control_plane_service,
    message_to_dto,
    run_control,
)
from tezqr.presentation.schemas import TelegramUpdateSchema, WhatsAppInboundSchema

router = APIRouter(tags=["Provider Webhooks"])


@router.post(
    "/webhooks/provider-bots/{webhook_secret}/telegram",
    summary="Process Provider Telegram Webhook",
    description=(
        "Handle inbound Telegram messages for a white-label provider bot instance. "
        "The controller translates Telegram payloads into application DTOs and hands "
        "the workflow to the provider control-plane service."
    ),
)
async def provider_telegram_webhook(
    webhook_secret: str,
    payload: TelegramUpdateSchema,
    request: Request,
) -> dict[str, bool]:
    message = payload.message or payload.edited_message
    if message is None:
        return {"ok": True}
    service = get_control_plane_service(request)
    await run_control(
        service.handle_provider_telegram_message(
            webhook_secret=webhook_secret,
            message=message_to_dto(message),
        )
    )
    return {"ok": True}


@router.post(
    "/webhooks/provider-bots/{webhook_secret}/whatsapp",
    summary="Process Provider WhatsApp Webhook",
    description=(
        "Handle inbound WhatsApp messages for a provider bot instance. "
        "The current implementation is provider-agnostic and returns structured "
        "replies plus a manual-share link when a payment needs to be sent back."
    ),
)
async def provider_whatsapp_webhook(
    webhook_secret: str,
    payload: WhatsAppInboundSchema,
    request: Request,
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.handle_provider_whatsapp_message(
            webhook_secret=webhook_secret,
            from_number=payload.from_number,
            name=payload.name,
            text=payload.text,
        )
    )
