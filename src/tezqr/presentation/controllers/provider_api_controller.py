"""Provider control-plane controller.

These route handlers deliberately stay thin. They convert HTTP inputs into simple
service arguments and let the application layer own orchestration and business rules.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import PlainTextResponse

from tezqr.domain.enums import ProviderMemberRole
from tezqr.presentation.dependencies import (
    get_control_plane_service,
    parse_optional_datetime,
    run_control,
)
from tezqr.presentation.schemas import (
    BroadcastCreateSchema,
    ClientCreateSchema,
    PaymentDestinationCreateSchema,
    PaymentNoteCreateSchema,
    PaymentRequestCreateSchema,
    PaymentShareSchema,
    PaymentStatusUpdateSchema,
    PaymentTemplateCreateSchema,
    ProviderBotInstanceCreateSchema,
    ProviderCreateSchema,
    ProviderMemberCreateSchema,
    ReminderCreateSchema,
)

router = APIRouter(tags=["Provider API"])


@router.post(
    "/api/providers",
    summary="Create Provider",
    description=(
        "Create a provider workspace, issue its API key, and optionally seed the owner role."
    ),
)
async def create_provider(
    payload: ProviderCreateSchema,
    request: Request,
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_provider(
            slug=payload.slug,
            name=payload.name,
            primary_color=payload.primary_color,
            secondary_color=payload.secondary_color,
            accent_color=payload.accent_color,
            logo_text=payload.logo_text,
            owner_actor_code=payload.owner_actor_code,
            owner_display_name=payload.owner_display_name,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/members",
    summary="Create Provider Member",
    description=(
        "Add a provider team member with a role used by the control-plane authorization "
        "model."
    ),
)
async def create_provider_member(
    provider_slug: str,
    payload: ProviderMemberCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_member(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            requesting_role=ProviderMemberRole.MANAGER,
            new_actor_code=payload.actor_code,
            display_name=payload.display_name,
            role=payload.role,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/destinations",
    summary="Create Payment Destination",
    description=(
        "Register a provider payment destination such as a UPI VPA and optional default "
        "route."
    ),
)
async def create_provider_destination(
    provider_slug: str,
    payload: PaymentDestinationCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_payment_destination(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            code=payload.code,
            label=payload.label,
            vpa=payload.vpa,
            payee_name=payload.payee_name,
            is_default=payload.is_default,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/bots",
    summary="Create Provider Bot",
    description=(
        "Create a provider-specific Telegram or WhatsApp bot instance with optional "
        "branding overrides."
    ),
)
async def create_provider_bot(
    provider_slug: str,
    payload: ProviderBotInstanceCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_bot_instance(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            platform=payload.platform,
            display_name=payload.display_name,
            public_handle=payload.public_handle,
            bot_token=payload.bot_token,
            primary_color=payload.primary_color,
            secondary_color=payload.secondary_color,
            accent_color=payload.accent_color,
            logo_text=payload.logo_text,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/clients",
    summary="Create Client",
    description=(
        "Create a client record that can be targeted for payment requests, reminders, "
        "and broadcasts."
    ),
)
async def create_provider_client(
    provider_slug: str,
    payload: ClientCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_client(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            full_name=payload.full_name,
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
            whatsapp_number=payload.whatsapp_number,
            external_ref=payload.external_ref,
            notes=payload.notes,
            labels=payload.labels,
            onboarding_source=payload.onboarding_source,
            bot_instance_code=payload.bot_instance_code,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/clients",
    summary="List Clients",
    description="List the saved clients that belong to the provider workspace.",
)
async def list_provider_clients(
    provider_slug: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> list[dict[str, object]]:
    service = get_control_plane_service(request)
    return await run_control(
        service.list_clients(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/templates",
    summary="Create Payment Template",
    description=(
        "Create a reusable payment template that can be linked to an item code and "
        "pre-generated QR assets."
    ),
)
async def create_payment_template(
    provider_slug: str,
    payload: PaymentTemplateCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_payment_template(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            name=payload.name,
            description=payload.description,
            item_code=payload.item_code,
            default_amount=payload.default_amount,
            destination_code=payload.destination_code,
            message_template=payload.message_template,
            custom_message=payload.custom_message,
            pre_generate=payload.pre_generate,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/item-code/{item_code}",
    summary="Resolve QR By Item Code",
    description=(
        "Load a pre-generated QR asset for an item code or create a live payment request "
        "when needed."
    ),
)
async def get_qr_by_item_code(
    provider_slug: str,
    item_code: str,
    request: Request,
    amount: str | None = Query(default=None),
    client_code: str | None = Query(default=None),
    custom_message: str | None = Query(default=None),
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.get_qr_by_item_code(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            item_code=item_code,
            amount=amount,
            client_code=client_code,
            custom_message=custom_message,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/payments",
    summary="Create Payment Request",
    description=(
        "Create a provider payment request and generate its QR, card, and print-ready "
        "asset bundle."
    ),
)
async def create_payment_request(
    provider_slug: str,
    payload: PaymentRequestCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_payment_request(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            amount=payload.amount,
            description=payload.description,
            client_code=payload.client_code,
            template_code=payload.template_code,
            item_code=payload.item_code,
            destination_code=payload.destination_code,
            custom_message=payload.custom_message,
            due_at=parse_optional_datetime(payload.due_at),
            channel=payload.channel,
            walk_in=payload.walk_in,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/payments/{payment_reference}/share",
    summary="Share Payment Request",
    description="Share an existing payment request over Telegram or WhatsApp.",
)
async def share_payment_request(
    provider_slug: str,
    payment_reference: str,
    payload: PaymentShareSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.share_payment_request(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            payment_reference=payment_reference,
            channel=payload.channel,
            client_code=payload.client_code,
            custom_message=payload.custom_message,
            bot_instance_code=payload.bot_instance_code,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/payments/{payment_reference}/status",
    summary="Mark Payment Status",
    description="Manually update the payment status for provider-side tracking.",
)
async def mark_payment_status(
    provider_slug: str,
    payment_reference: str,
    payload: PaymentStatusUpdateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.mark_payment_status(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            payment_reference=payment_reference,
            status=payload.status,
            notes_summary=payload.notes_summary,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/payments/{payment_reference}/notes",
    summary="Add Payment Note",
    description="Attach a manual note to the payment request and keep it in the payment history.",
)
async def add_payment_note(
    provider_slug: str,
    payment_reference: str,
    payload: PaymentNoteCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.add_payment_note(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            payment_reference=payment_reference,
            note=payload.note,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/payments/{payment_reference}/history",
    summary="Get Payment History",
    description="Return notes and event logs recorded against a provider payment request.",
)
async def get_payment_history(
    provider_slug: str,
    payment_reference: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.get_payment_history(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            payment_reference=payment_reference,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/clients/{client_code}/payments",
    summary="List Client Payments",
    description="Return all payment requests linked to a saved client record.",
)
async def get_client_payments(
    provider_slug: str,
    client_code: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.list_client_payments(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            client_code=client_code,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/reminders",
    summary="Create Reminder",
    description="Create a scheduled, manual, or task-based reminder with optional QR delivery.",
)
async def create_payment_reminder(
    provider_slug: str,
    payload: ReminderCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.create_reminder(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            reminder_type=payload.reminder_type,
            channel=payload.channel,
            message=payload.message,
            payment_reference=payload.payment_reference,
            client_code=payload.client_code,
            task_name=payload.task_name,
            scheduled_for=parse_optional_datetime(payload.scheduled_for),
            include_qr=payload.include_qr,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/reminders/run-due",
    summary="Run Due Reminders",
    description="Process all scheduled reminders that are due for delivery.",
)
async def run_due_reminders(
    provider_slug: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, int]:
    service = get_control_plane_service(request)
    return await run_control(
        service.run_due_reminders(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
        )
    )


@router.post(
    "/api/providers/{provider_slug}/broadcasts",
    summary="Create Broadcast",
    description="Send a plain message or payment-backed broadcast to many clients at once.",
)
async def create_broadcast(
    provider_slug: str,
    payload: BroadcastCreateSchema,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.broadcast_message(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            channel=payload.channel,
            message=payload.message,
            client_codes=payload.client_codes,
            template_code=payload.template_code,
            amount=payload.amount,
            item_code=payload.item_code,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/dashboard",
    summary="Get Provider Dashboard",
    description=(
        "Return provider-level counts for clients, payments, reminders, templates, and "
        "bots."
    ),
)
async def get_provider_dashboard(
    provider_slug: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> dict[str, object]:
    service = get_control_plane_service(request)
    return await run_control(
        service.get_dashboard(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/exports/payments",
    summary="Export Payments",
    description="Export provider payment data in JSON or CSV format for downstream reporting.",
)
async def export_payments(
    provider_slug: str,
    request: Request,
    format: str = Query(default="json"),
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
):
    service = get_control_plane_service(request)
    media_type, payload = await run_control(
        service.export_payments(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            format=format,
        )
    )
    if media_type == "text/csv":
        return PlainTextResponse(payload, media_type=media_type)
    return Response(content=payload, media_type=media_type)


@router.get(
    "/api/providers/{provider_slug}/qr-assets",
    summary="List QR Assets",
    description=(
        "List stored QR assets for a provider, including pre-generated and "
        "payment-linked files."
    ),
)
async def list_qr_assets(
    provider_slug: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> list[dict[str, object]]:
    service = get_control_plane_service(request)
    return await run_control(
        service.list_assets(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
        )
    )


@router.get(
    "/api/providers/{provider_slug}/qr-assets/{asset_code}/download",
    summary="Download QR Asset",
    description="Download a stored QR asset such as the raw QR, branded card, or print-ready file.",
)
async def download_qr_asset(
    provider_slug: str,
    asset_code: str,
    request: Request,
    x_api_key: str = Header(...),
    x_actor_code: str | None = Header(default=None),
) -> Response:
    service = get_control_plane_service(request)
    filename, media_type, content = await run_control(
        service.download_asset(
            provider_slug=provider_slug,
            api_key=x_api_key,
            actor_code=x_actor_code,
            asset_code=asset_code,
        )
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
