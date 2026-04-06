"""Presenter helpers that turn internal models into stable API payloads."""

from __future__ import annotations

import json
from typing import Any

from tezqr.domain.entities import Provider
from tezqr.infrastructure.persistence.models import (
    ClientModel,
    PaymentDestinationModel,
    PaymentReminderModel,
    PaymentRequestModel,
    PaymentTemplateModel,
    ProviderBotInstanceModel,
    ProviderMemberModel,
    ProviderModel,
    QrAssetModel,
)


class ProviderControlPresenter:
    """Keep HTTP payload shaping out of the use-case orchestration layer."""

    def serialize_provider(
        self,
        provider: Provider,
        *,
        include_api_key: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "slug": provider.slug.value,
            "name": provider.name,
            "branding": provider.branding,
            "created_at": provider.created_at.isoformat(),
        }
        if include_api_key:
            payload["api_key"] = provider.api_key
        return payload

    def serialize_provider_model(self, provider: ProviderModel) -> dict[str, Any]:
        return {
            "slug": provider.slug,
            "name": provider.name,
            "branding": provider.branding_json,
            "created_at": provider.created_at.isoformat(),
        }

    def serialize_member(self, model: ProviderMemberModel) -> dict[str, Any]:
        return {
            "actor_code": model.actor_code,
            "display_name": model.display_name,
            "role": model.role,
            "is_active": model.is_active,
        }

    def serialize_destination(self, model: PaymentDestinationModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "label": model.label,
            "vpa": model.vpa,
            "payee_name": model.payee_name,
            "is_default": model.is_default,
            "is_active": model.is_active,
        }

    def serialize_bot_instance(self, model: ProviderBotInstanceModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "platform": model.platform,
            "display_name": model.display_name,
            "public_handle": model.public_handle,
            "webhook_secret": model.webhook_secret,
            "branding_override": model.branding_override_json,
            "is_active": model.is_active,
        }

    def serialize_client(self, model: ClientModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "full_name": model.full_name,
            "telegram_id": model.telegram_id,
            "telegram_username": model.telegram_username,
            "whatsapp_number": model.whatsapp_number,
            "external_ref": model.external_ref,
            "notes": model.notes,
            "labels": model.labels_json,
            "onboarding_source": model.onboarding_source,
        }

    def serialize_template(self, model: PaymentTemplateModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "name": model.name,
            "description": model.description,
            "item_code": model.item_code,
            "default_amount": f"{model.default_amount:.2f}"
            if model.default_amount is not None
            else None,
            "destination_code": model.destination_code,
            "message_template": model.message_template,
            "custom_message": model.custom_message,
            "pre_generate": model.pre_generate,
        }

    def serialize_payment(self, model: PaymentRequestModel) -> dict[str, Any]:
        return {
            "reference": model.reference,
            "amount": f"{model.amount:.2f}",
            "description": model.description,
            "upi_uri": model.upi_uri,
            "status": model.status,
            "client_id": str(model.client_id) if model.client_id else None,
            "template_id": str(model.template_id) if model.template_id else None,
            "item_code": model.item_code,
            "channel": model.channel,
            "due_at": model.due_at.isoformat() if model.due_at else None,
            "paid_at": model.paid_at.isoformat() if model.paid_at else None,
            "notes_summary": model.notes_summary,
            "walk_in": model.walk_in,
            "created_at": model.created_at.isoformat(),
        }

    def serialize_asset(self, model: QrAssetModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "asset_type": model.asset_type,
            "filename": model.filename,
            "mime_type": model.mime_type,
            "item_code": model.item_code,
            "amount": f"{model.amount:.2f}" if model.amount is not None else None,
            "is_pre_generated": model.is_pre_generated,
            "payment_request_id": str(model.payment_request_id)
            if model.payment_request_id
            else None,
            "template_id": str(model.template_id) if model.template_id else None,
        }

    def serialize_reminder(self, model: PaymentReminderModel) -> dict[str, Any]:
        return {
            "code": model.code,
            "reminder_type": model.reminder_type,
            "channel": model.channel,
            "status": model.status,
            "message": model.message,
            "task_name": model.task_name,
            "scheduled_for": model.scheduled_for.isoformat() if model.scheduled_for else None,
            "sent_at": model.sent_at.isoformat() if model.sent_at else None,
            "include_qr": model.include_qr,
        }

    def json_string(self, payload: Any) -> str:
        return json.dumps(payload, default=str)
