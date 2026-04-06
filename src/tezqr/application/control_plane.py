"""Provider control-plane application service.

This module coordinates provider-side workflows such as onboarding, payment creation,
sharing, reminders, exports, and white-label bot handling.

The service intentionally sits above the domain layer and below the FastAPI controllers:

- controllers translate HTTP/webhook payloads into simple method calls
- this service orchestrates the use case
- repositories isolate persistence concerns
- presenter and message helpers keep formatting concerns out of orchestration
"""

from __future__ import annotations

import csv
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tezqr.application.control_plane_messages import ProviderMessageComposer
from tezqr.application.control_plane_presenter import ProviderControlPresenter
from tezqr.application.ports import QrCodeGenerator
from tezqr.application.provider_bot_commands import (
    ProviderBotChargeCommand,
    ProviderBotClientPaymentsCommand,
    ProviderBotClientsCommand,
    ProviderBotDashboardCommand,
    ProviderBotHelpCommand,
    ProviderBotHistoryCommand,
    ProviderBotItemCodeCommand,
    ProviderBotLoginCommand,
    ProviderBotLogoutCommand,
    ProviderBotMalformedCommand,
    ProviderBotMemberAddCommand,
    ProviderBotNoteCommand,
    ProviderBotOnboardLinkCommand,
    ProviderBotPayCommand,
    ProviderBotPlainText,
    ProviderBotReminderCommand,
    ProviderBotRunRemindersCommand,
    ProviderBotShareCommand,
    ProviderBotStartCommand,
    ProviderBotStatusCommand,
    ProviderBotUnsupportedCommand,
    ProviderBotWhoamiCommand,
    parse_provider_bot_input,
)
from tezqr.domain.entities import (
    Client,
    OutboundMessage,
    PaymentDestination,
    PaymentLog,
    PaymentNote,
    PaymentReminder,
    PaymentRequest,
    PaymentTemplate,
    Provider,
    ProviderBotInstance,
    ProviderDashboard,
    ProviderMember,
    QrAsset,
)
from tezqr.domain.enums import (
    BotPlatform,
    DeliveryState,
    MessageChannel,
    PaymentStatus,
    ProviderMemberRole,
    QrAssetType,
    ReminderStatus,
    ReminderType,
)
from tezqr.domain.exceptions import AuthorizationError, DomainValidationError
from tezqr.domain.value_objects import ItemCode, Money, PhoneNumber, ProviderSlug, UpiVpa
from tezqr.infrastructure.persistence.models import (
    ClientModel,
    OutboundMessageModel,
    PaymentDestinationModel,
    PaymentLogModel,
    PaymentNoteModel,
    PaymentReminderModel,
    PaymentRequestModel,
    PaymentTemplateModel,
    ProviderBotInstanceModel,
    ProviderMemberModel,
    ProviderModel,
    QrAssetModel,
)
from tezqr.infrastructure.persistence.provider_control_repository import (
    SQLAlchemyProviderControlRepository,
)
from tezqr.infrastructure.qr.generator import render_payment_card_png
from tezqr.infrastructure.telegram.client import TelegramBotClient
from tezqr.shared.config import Settings

ROLE_RANK = {
    ProviderMemberRole.VIEWER: 10,
    ProviderMemberRole.OPERATOR: 20,
    ProviderMemberRole.MANAGER: 30,
    ProviderMemberRole.OWNER: 40,
    ProviderMemberRole.API: 50,
}


@dataclass(slots=True)
class ProviderAccessContext:
    provider: ProviderModel
    member: ProviderMemberModel | None


@dataclass(slots=True)
class OutboundDispatchResult:
    delivery_state: DeliveryState
    recipient: str
    share_url: str | None
    bot_instance: ProviderBotInstanceModel | None


@dataclass(slots=True)
class ProviderBotCommandResult:
    texts: list[str]
    photo_bytes: bytes | None = None
    photo_filename: str | None = None
    photo_caption: str | None = None
    share_url: str | None = None
    payment_reference: str | None = None


class ControlPlaneService:
    """Application service that coordinates provider workflows end to end."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        qr_generator: QrCodeGenerator,
        http_client: httpx.AsyncClient,
        settings: Settings,
        now_provider: callable | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._qr_generator = qr_generator
        self._http_client = http_client
        self._settings = settings
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._messages = ProviderMessageComposer()
        self._presenter = ProviderControlPresenter()

    async def create_provider(
        self,
        *,
        slug: str,
        name: str,
        primary_color: str | None = None,
        secondary_color: str | None = None,
        accent_color: str | None = None,
        logo_text: str | None = None,
        owner_actor_code: str | None = None,
        owner_display_name: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        provider = Provider(
            id=uuid4(),
            slug=ProviderSlug(slug),
            name=name,
            api_key=self._generate_api_key(),
            branding=self._build_branding_payload(
                name=name,
                primary_color=primary_color,
                secondary_color=secondary_color,
                accent_color=accent_color,
                logo_text=logo_text,
            ),
            created_at=now,
            updated_at=now,
        )

        async with self._session_factory() as session:
            session.add(
                ProviderModel(
                    id=provider.id,
                    slug=provider.slug.value,
                    name=provider.name,
                    api_key=provider.api_key,
                    branding_json=provider.branding,
                    created_at=provider.created_at,
                    updated_at=provider.updated_at,
                )
            )
            await session.flush()
            if owner_actor_code and owner_display_name:
                member = ProviderMember(
                    id=uuid4(),
                    provider_id=provider.id,
                    actor_code=owner_actor_code,
                    display_name=owner_display_name,
                    role=ProviderMemberRole.OWNER,
                    created_at=now,
                    updated_at=now,
                )
                session.add(
                    ProviderMemberModel(
                        id=member.id,
                        provider_id=member.provider_id,
                        actor_code=member.actor_code,
                        display_name=member.display_name,
                        role=member.role.value,
                        is_active=member.is_active,
                        created_at=member.created_at,
                        updated_at=member.updated_at,
                    )
                )
            await session.commit()

        return self._serialize_provider(provider, include_api_key=True)

    async def create_member(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        requesting_role: ProviderMemberRole,
        new_actor_code: str,
        display_name: str,
        role: str,
    ) -> dict[str, Any]:
        role_enum = ProviderMemberRole(role)
        now = self._now_provider()
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=requesting_role,
            )
            member = ProviderMember(
                id=uuid4(),
                provider_id=access.provider.id,
                actor_code=new_actor_code,
                display_name=display_name,
                role=role_enum,
                telegram_id=None,
                telegram_username=None,
                whatsapp_number=None,
                created_at=now,
                updated_at=now,
            )
            model = ProviderMemberModel(
                id=member.id,
                provider_id=member.provider_id,
                actor_code=member.actor_code,
                display_name=member.display_name,
                role=member.role.value,
                telegram_id=member.telegram_id,
                telegram_username=member.telegram_username,
                whatsapp_number=member.whatsapp_number.value if member.whatsapp_number else None,
                is_active=member.is_active,
                created_at=member.created_at,
                updated_at=member.updated_at,
            )
            session.add(model)
            await session.commit()
            return self._serialize_member(model)

    async def create_payment_destination(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        code: str,
        label: str,
        vpa: str,
        payee_name: str,
        is_default: bool,
    ) -> dict[str, Any]:
        now = self._now_provider()
        destination = PaymentDestination(
            id=uuid4(),
            provider_id=uuid4(),
            code=code,
            label=label,
            vpa=UpiVpa(vpa),
            payee_name=payee_name,
            is_default=is_default,
            created_at=now,
            updated_at=now,
        )
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            destination.provider_id = access.provider.id
            if destination.is_default:
                await self._clear_default_destinations(session, access.provider.id)
            model = PaymentDestinationModel(
                id=destination.id,
                provider_id=destination.provider_id,
                code=destination.code,
                label=destination.label,
                vpa=destination.vpa.value,
                payee_name=destination.payee_name,
                is_default=destination.is_default,
                is_active=destination.is_active,
                created_at=destination.created_at,
                updated_at=destination.updated_at,
            )
            session.add(model)
            await session.commit()
            return self._serialize_destination(model)

    async def create_bot_instance(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        platform: str,
        display_name: str,
        public_handle: str | None = None,
        bot_token: str | None = None,
        primary_color: str | None = None,
        secondary_color: str | None = None,
        accent_color: str | None = None,
        logo_text: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        platform_enum = BotPlatform(platform)
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.MANAGER,
            )
            provider_branding = dict(access.provider.branding_json or {})
            branding_override = self._build_branding_payload(
                name=display_name,
                primary_color=primary_color or provider_branding.get("primary_color"),
                secondary_color=secondary_color or provider_branding.get("secondary_color"),
                accent_color=accent_color or provider_branding.get("accent_color"),
                logo_text=logo_text or provider_branding.get("logo_text") or display_name[:2],
            )
            entity = ProviderBotInstance(
                id=uuid4(),
                provider_id=access.provider.id,
                code=self._generate_code("BOT"),
                platform=platform_enum,
                display_name=display_name,
                webhook_secret=secrets.token_urlsafe(18),
                bot_token=bot_token,
                public_handle=public_handle,
                branding_override=branding_override,
                created_at=now,
                updated_at=now,
            )
            model = ProviderBotInstanceModel(
                id=entity.id,
                provider_id=entity.provider_id,
                code=entity.code,
                platform=entity.platform.value,
                display_name=entity.display_name,
                webhook_secret=entity.webhook_secret,
                bot_token=entity.bot_token,
                public_handle=entity.public_handle,
                branding_override_json=entity.branding_override,
                configuration_json=entity.configuration,
                is_active=entity.is_active,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            session.add(model)
            await session.commit()
            return self._serialize_bot_instance(model)

    async def create_client(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        full_name: str,
        telegram_id: int | None = None,
        telegram_username: str | None = None,
        whatsapp_number: str | None = None,
        external_ref: str | None = None,
        notes: str | None = None,
        labels: list[str] | None = None,
        onboarding_source: str = "api",
        bot_instance_code: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            bot_instance = await self._find_bot_instance_by_code(
                session,
                provider_id=access.provider.id,
                code=bot_instance_code,
            )
            entity = Client(
                id=uuid4(),
                provider_id=access.provider.id,
                code=self._generate_code("CLI"),
                full_name=full_name,
                telegram_id=telegram_id,
                telegram_username=telegram_username,
                whatsapp_number=PhoneNumber(whatsapp_number) if whatsapp_number else None,
                external_ref=external_ref,
                notes=notes,
                labels=labels or [],
                onboarding_source=onboarding_source,
                bot_instance_id=bot_instance.id if bot_instance else None,
                created_at=now,
                updated_at=now,
            )
            model = ClientModel(
                id=entity.id,
                provider_id=entity.provider_id,
                code=entity.code,
                full_name=entity.full_name,
                telegram_id=entity.telegram_id,
                telegram_username=entity.telegram_username,
                whatsapp_number=entity.whatsapp_number.value if entity.whatsapp_number else None,
                external_ref=entity.external_ref,
                notes=entity.notes,
                labels_json=entity.labels,
                onboarding_source=entity.onboarding_source,
                bot_instance_id=entity.bot_instance_id,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            session.add(model)
            await session.commit()
            return self._serialize_client(model)

    async def list_clients(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            rows = await self._repository(session).list_clients(access.provider.id)
            return [self._serialize_client(row) for row in rows]

    async def create_payment_template(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        name: str,
        description: str,
        item_code: str | None = None,
        default_amount: str | None = None,
        destination_code: str | None = None,
        message_template: str | None = None,
        custom_message: str | None = None,
        pre_generate: bool = False,
    ) -> dict[str, Any]:
        now = self._now_provider()
        default_money = self._parse_money(default_amount) if default_amount is not None else None
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            template = PaymentTemplate(
                id=uuid4(),
                provider_id=access.provider.id,
                code=self._generate_code("TPL"),
                name=name,
                description=description,
                item_code=ItemCode(item_code) if item_code else None,
                default_amount=default_money,
                destination_code=destination_code,
                message_template=message_template,
                custom_message=custom_message,
                pre_generate=pre_generate,
                created_at=now,
                updated_at=now,
            )
            model = PaymentTemplateModel(
                id=template.id,
                provider_id=template.provider_id,
                code=template.code,
                name=template.name,
                description=template.description,
                item_code=template.item_code.value if template.item_code else None,
                default_amount=template.default_amount.amount if template.default_amount else None,
                currency=template.currency,
                destination_code=template.destination_code,
                message_template=template.message_template,
                custom_message=template.custom_message,
                pre_generate=template.pre_generate,
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            session.add(model)
            if pre_generate and default_money is not None:
                destination = await self._resolve_destination(
                    session,
                    provider_id=access.provider.id,
                    destination_code=destination_code,
                )
                pseudo_payment = PaymentRequest.create_for_provider(
                    provider_id=access.provider.id,
                    destination=self._destination_entity(destination),
                    amount=default_money,
                    description=template.description,
                    template_id=template.id,
                    item_code=template.item_code.value if template.item_code else None,
                    custom_message=template.custom_message,
                    metadata={"mode": "pre_generated"},
                    now=now,
                )
                await self._create_asset_bundle(
                    session,
                    provider=access.provider,
                    payment=pseudo_payment,
                    template=model,
                    payment_request_model=None,
                    is_pre_generated=True,
                )
            await session.commit()
            return self._serialize_template(model)

    async def get_qr_by_item_code(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        item_code: str,
        amount: str | None = None,
        client_code: str | None = None,
        custom_message: str | None = None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            normalized_item_code = ItemCode(item_code).value
            repository = self._repository(session)
            template = await repository.get_template(
                access.provider.id,
                template_code=None,
                item_code=normalized_item_code,
            )
            if template is None:
                raise DomainValidationError(
                    f"No template found for item code {normalized_item_code}."
                )
            if amount is None and template.pre_generate:
                asset = await repository.get_latest_pre_generated_asset(
                    template.id,
                    normalized_item_code,
                )
                if asset is not None:
                    return {
                        "template": self._serialize_template(template),
                        "asset": self._serialize_asset(asset),
                        "pre_generated": True,
                    }
            payment = await self.create_payment_request(
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                client_code=client_code,
                template_code=template.code,
                item_code=normalized_item_code,
                amount=amount,
                description=template.description,
                custom_message=custom_message,
                walk_in=client_code is None,
            )
            return {
                "template": self._serialize_template(template),
                "payment": payment,
                "pre_generated": False,
            }

    async def create_payment_request(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        amount: str | None,
        description: str | None = None,
        client_code: str | None = None,
        template_code: str | None = None,
        item_code: str | None = None,
        destination_code: str | None = None,
        custom_message: str | None = None,
        due_at: datetime | None = None,
        channel: str | None = None,
        walk_in: bool = False,
    ) -> dict[str, Any]:
        now = self._now_provider()
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            template = await self._find_template(
                session,
                provider_id=access.provider.id,
                template_code=template_code,
                item_code=item_code,
            )
            client = await self._find_client(
                session,
                provider_id=access.provider.id,
                client_code=client_code,
            )
            destination = await self._resolve_destination(
                session,
                provider_id=access.provider.id,
                destination_code=destination_code
                or (template.destination_code if template else None),
            )
            effective_amount = self._resolve_amount(amount, template)
            effective_description = self._resolve_description(
                description=description,
                template=template,
                item_code=item_code,
                walk_in=walk_in,
            )
            payment = PaymentRequest.create_for_provider(
                provider_id=access.provider.id,
                destination=self._destination_entity(destination),
                amount=effective_amount,
                description=effective_description,
                client_id=client.id if client else None,
                template_id=template.id if template else None,
                item_code=ItemCode(item_code).value
                if item_code
                else template.item_code
                if template
                else None,
                custom_message=custom_message or (template.custom_message if template else None),
                channel=MessageChannel(channel) if channel else None,
                due_at=due_at,
                metadata={
                    "client_code": client.code if client else "",
                    "template_code": template.code if template else "",
                    "destination_code": destination.code,
                },
                walk_in=walk_in,
                now=now,
            )
            payment_model = PaymentRequestModel(
                id=payment.id,
                merchant_id=payment.merchant_id,
                provider_id=payment.provider_id,
                client_id=payment.client_id,
                template_id=payment.template_id,
                reference=payment.reference.value,
                amount=payment.amount.amount,
                description=payment.description,
                upi_uri=payment.upi_uri,
                item_code=payment.item_code,
                custom_message=payment.custom_message,
                channel=payment.channel,
                status=payment.status.value,
                due_at=payment.due_at,
                paid_at=payment.paid_at,
                status_updated_at=payment.status_updated_at,
                notes_summary=payment.notes_summary,
                metadata_json=payment.metadata,
                walk_in=payment.walk_in,
                qr_mime_type=payment.qr_mime_type,
                created_at=payment.created_at,
            )
            session.add(payment_model)
            await session.flush()
            assets = await self._create_asset_bundle(
                session,
                provider=access.provider,
                payment=payment,
                template=template,
                payment_request_model=payment_model,
                is_pre_generated=False,
            )
            await self._append_payment_log(
                session,
                payment_request_id=payment_model.id,
                event_type="created",
                message="Payment request created.",
                created_by=actor_code or "api",
                payload={
                    "client_code": client.code if client else "",
                    "template_code": template.code if template else "",
                    "destination_code": destination.code,
                },
                now=now,
            )
            await session.commit()
            return {
                "payment": self._serialize_payment(payment_model),
                "assets": [self._serialize_asset(asset) for asset in assets],
                "quick_share_link": payment_model.upi_uri,
            }

    async def share_payment_request(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        payment_reference: str,
        channel: str,
        client_code: str | None = None,
        custom_message: str | None = None,
        bot_instance_code: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        channel_enum = MessageChannel(channel)
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            payment = await self._load_payment(session, access.provider.id, payment_reference)
            client = await self._resolve_client_for_payment(
                session,
                provider_id=access.provider.id,
                payment=payment,
                explicit_client_code=client_code,
            )
            asset = await self._preferred_payment_asset(session, payment.id)
            bot_instance = await self._find_bot_instance_by_code(
                session,
                provider_id=access.provider.id,
                code=bot_instance_code,
                platform=BotPlatform.TELEGRAM if channel_enum == MessageChannel.TELEGRAM else None,
            )
            message = self._build_payment_message(
                provider=access.provider,
                client=client,
                payment=payment,
                custom_message=custom_message,
            )
            dispatch = await self._dispatch_message(
                provider=access.provider,
                client=client,
                channel=channel_enum,
                message=message,
                asset=asset,
                bot_instance=bot_instance,
            )
            outbound = OutboundMessage(
                id=uuid4(),
                provider_id=access.provider.id,
                channel=channel_enum,
                delivery_state=dispatch.delivery_state,
                recipient=dispatch.recipient,
                message=message,
                client_id=client.id if client else None,
                payment_request_id=payment.id,
                bot_instance_id=dispatch.bot_instance.id if dispatch.bot_instance else None,
                share_url=dispatch.share_url,
                metadata={"payment_reference": payment.reference, "channel": channel_enum.value},
                sent_at=now if dispatch.delivery_state == DeliveryState.SENT else None,
                created_at=now,
            )
            session.add(
                OutboundMessageModel(
                    id=outbound.id,
                    provider_id=outbound.provider_id,
                    client_id=outbound.client_id,
                    payment_request_id=outbound.payment_request_id,
                    reminder_id=outbound.reminder_id,
                    bot_instance_id=outbound.bot_instance_id,
                    channel=outbound.channel.value,
                    delivery_state=outbound.delivery_state.value,
                    recipient=outbound.recipient,
                    message=outbound.message,
                    share_url=outbound.share_url,
                    metadata_json=outbound.metadata,
                    sent_at=outbound.sent_at,
                    created_at=outbound.created_at,
                )
            )
            await self._append_payment_log(
                session,
                payment_request_id=payment.id,
                event_type="shared",
                message=f"Payment shared over {channel_enum.value}.",
                created_by=actor_code or "api",
                payload={
                    "recipient": dispatch.recipient,
                    "delivery_state": dispatch.delivery_state.value,
                },
                now=now,
            )
            await session.commit()
            return {
                "payment_reference": payment.reference,
                "channel": channel_enum.value,
                "delivery_state": dispatch.delivery_state.value,
                "recipient": dispatch.recipient,
                "share_url": dispatch.share_url,
            }

    async def mark_payment_status(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        payment_reference: str,
        status: str,
        notes_summary: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        status_enum = PaymentStatus(status)
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            payment = await self._load_payment(session, access.provider.id, payment_reference)
            payment.status = status_enum.value
            payment.status_updated_at = now
            payment.paid_at = now if status_enum == PaymentStatus.PAID else payment.paid_at
            payment.notes_summary = notes_summary or payment.notes_summary
            await self._append_payment_log(
                session,
                payment_request_id=payment.id,
                event_type="status_changed",
                message=f"Payment status marked as {status_enum.value}.",
                created_by=actor_code or "api",
                payload={"status": status_enum.value},
                now=now,
            )
            await session.commit()
            return self._serialize_payment(payment)

    async def add_payment_note(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        payment_reference: str,
        note: str,
    ) -> dict[str, Any]:
        now = self._now_provider()
        note_entity = PaymentNote(
            id=uuid4(),
            payment_request_id=uuid4(),
            note=note,
            created_by=actor_code or "api",
            created_at=now,
        )
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            payment = await self._load_payment(session, access.provider.id, payment_reference)
            note_entity.payment_request_id = payment.id
            model = PaymentNoteModel(
                id=note_entity.id,
                payment_request_id=note_entity.payment_request_id,
                note=note_entity.note,
                created_by=note_entity.created_by,
                created_at=note_entity.created_at,
            )
            session.add(model)
            payment.notes_summary = note_entity.note
            await self._append_payment_log(
                session,
                payment_request_id=payment.id,
                event_type="note_added",
                message="Payment note added.",
                created_by=note_entity.created_by,
                payload={"note": note_entity.note},
                now=now,
            )
            await session.commit()
            return {
                "payment_reference": payment.reference,
                "note_id": str(model.id),
                "note": model.note,
                "created_by": model.created_by,
            }

    async def get_payment_history(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        payment_reference: str,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            payment = await self._load_payment(session, access.provider.id, payment_reference)
            repository = self._repository(session)
            notes = await repository.list_notes(payment.id)
            logs = await repository.list_logs(payment.id)
            return {
                "payment": self._serialize_payment(payment),
                "notes": [
                    {
                        "note": note.note,
                        "created_by": note.created_by,
                        "created_at": note.created_at.isoformat(),
                    }
                    for note in notes
                ],
                "logs": [
                    {
                        "event_type": log.event_type,
                        "message": log.message,
                        "payload": log.payload_json,
                        "created_by": log.created_by,
                        "created_at": log.created_at.isoformat(),
                    }
                    for log in logs
                ],
            }

    async def list_client_payments(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        client_code: str,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            client = await self._find_client(
                session,
                provider_id=access.provider.id,
                client_code=client_code,
                required=True,
            )
            payments = await self._repository(session).list_payments_by_client(client.id)
            return {
                "client": self._serialize_client(client),
                "payments": [self._serialize_payment(payment) for payment in payments],
            }

    async def create_reminder(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        reminder_type: str,
        channel: str,
        message: str,
        payment_reference: str | None = None,
        client_code: str | None = None,
        task_name: str | None = None,
        scheduled_for: datetime | None = None,
        include_qr: bool = True,
    ) -> dict[str, Any]:
        now = self._now_provider()
        reminder_type_enum = ReminderType(reminder_type)
        channel_enum = MessageChannel(channel)
        status = (
            ReminderStatus.SCHEDULED
            if scheduled_for and scheduled_for > now
            else ReminderStatus.DRAFT
        )
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            payment = (
                await self._load_payment(session, access.provider.id, payment_reference)
                if payment_reference
                else None
            )
            client = await self._resolve_client_for_payment(
                session,
                provider_id=access.provider.id,
                payment=payment,
                explicit_client_code=client_code,
            )
            reminder = PaymentReminder(
                id=uuid4(),
                provider_id=access.provider.id,
                code=self._generate_code("RMD"),
                reminder_type=reminder_type_enum,
                channel=channel_enum,
                status=status,
                message=message,
                payment_request_id=payment.id if payment else None,
                client_id=client.id if client else None,
                task_name=task_name,
                scheduled_for=scheduled_for,
                include_qr=include_qr,
                created_by=actor_code or "api",
                created_at=now,
                updated_at=now,
            )
            model = PaymentReminderModel(
                id=reminder.id,
                provider_id=reminder.provider_id,
                code=reminder.code,
                reminder_type=reminder.reminder_type.value,
                channel=reminder.channel.value,
                status=reminder.status.value,
                message=reminder.message,
                payment_request_id=reminder.payment_request_id,
                client_id=reminder.client_id,
                task_name=reminder.task_name,
                scheduled_for=reminder.scheduled_for,
                sent_at=reminder.sent_at,
                include_qr=reminder.include_qr,
                created_by=reminder.created_by,
                last_error=reminder.last_error,
                created_at=reminder.created_at,
                updated_at=reminder.updated_at,
            )
            session.add(model)
            dispatch: OutboundDispatchResult | None = None
            if reminder.reminder_type == ReminderType.MANUAL or (
                reminder.scheduled_for is None or reminder.scheduled_for <= now
            ):
                dispatch = await self._send_single_reminder(
                    session=session,
                    provider=access.provider,
                    reminder=model,
                    payment=payment,
                    client=client,
                    actor_code=actor_code or "api",
                    now=now,
                )
            await session.commit()
            payload = self._serialize_reminder(model)
            if dispatch is not None:
                payload["delivery_state"] = dispatch.delivery_state.value
                payload["share_url"] = dispatch.share_url
                payload["recipient"] = dispatch.recipient
            return payload

    async def run_due_reminders(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        sent = 0
        failed = 0
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.OPERATOR,
            )
            reminders = await self._repository(session).list_due_reminders(access.provider.id, now)
            for reminder in reminders:
                payment = None
                client = None
                if reminder.payment_request_id:
                    payment = await session.get(PaymentRequestModel, reminder.payment_request_id)
                if reminder.client_id:
                    client = await session.get(ClientModel, reminder.client_id)
                try:
                    await self._send_single_reminder(
                        session=session,
                        provider=access.provider,
                        reminder=reminder,
                        payment=payment,
                        client=client,
                        actor_code=actor_code or "api",
                        now=now,
                    )
                    sent += 1
                except Exception as exc:
                    reminder.status = ReminderStatus.FAILED.value
                    reminder.last_error = str(exc)
                    reminder.updated_at = now
                    failed += 1
            await session.commit()
            return {"processed": len(reminders), "sent": sent, "failed": failed}

    async def broadcast_message(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        channel: str,
        message: str,
        client_codes: list[str] | None = None,
        template_code: str | None = None,
        amount: str | None = None,
        item_code: str | None = None,
    ) -> dict[str, Any]:
        now = self._now_provider()
        channel_enum = MessageChannel(channel)
        sent = 0
        manual = 0
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.MANAGER,
            )
            clients = await self._repository(session).list_clients(access.provider.id)
            if client_codes:
                normalized_codes = {code.strip().upper() for code in client_codes}
                clients = [client for client in clients if client.code in normalized_codes]
            template = await self._find_template(
                session,
                provider_id=access.provider.id,
                template_code=template_code,
                item_code=item_code,
                required=False,
            )
            for client in clients:
                payment_model = None
                asset = None
                if template or amount:
                    payment_payload = await self.create_payment_request(
                        provider_slug=provider_slug,
                        api_key=api_key,
                        actor_code=actor_code,
                        amount=amount
                        or (
                            str(template.default_amount)
                            if template and template.default_amount
                            else None
                        ),
                        description=template.description if template else message,
                        client_code=client.code,
                        template_code=template.code if template else None,
                        item_code=template.item_code if template else item_code,
                        custom_message=message,
                        walk_in=False,
                    )
                    payment_model = await self._load_payment(
                        session,
                        access.provider.id,
                        payment_payload["payment"]["reference"],
                    )
                    asset = await self._preferred_payment_asset(session, payment_model.id)
                    text = self._build_payment_message(
                        provider=access.provider,
                        client=client,
                        payment=payment_model,
                        custom_message=message,
                    )
                else:
                    text = message.strip()
                dispatch = await self._dispatch_message(
                    provider=access.provider,
                    client=client,
                    channel=channel_enum,
                    message=text,
                    asset=asset,
                    bot_instance=None,
                )
                state = dispatch.delivery_state
                outbound = OutboundMessageModel(
                    id=uuid4(),
                    provider_id=access.provider.id,
                    client_id=client.id,
                    payment_request_id=payment_model.id if payment_model else None,
                    reminder_id=None,
                    bot_instance_id=dispatch.bot_instance.id if dispatch.bot_instance else None,
                    channel=channel_enum.value,
                    delivery_state=state.value,
                    recipient=dispatch.recipient,
                    message=text,
                    share_url=dispatch.share_url,
                    metadata_json={"broadcast": "true"},
                    sent_at=now if state == DeliveryState.SENT else None,
                    created_at=now,
                )
                session.add(outbound)
                if state == DeliveryState.SENT:
                    sent += 1
                else:
                    manual += 1
            await session.commit()
            return {
                "target_clients": len(clients),
                "sent": sent,
                "manual_share": manual,
                "channel": channel_enum.value,
            }

    async def get_dashboard(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            repository = self._repository(session)
            total_clients = await repository.count_clients(access.provider.id)
            total_templates = await repository.count_templates(access.provider.id)
            total_bot_instances = await repository.count_bot_instances(access.provider.id)
            pending = await self._count_payments_by_status(
                session, access.provider.id, PaymentStatus.PENDING
            )
            paid = await self._count_payments_by_status(
                session, access.provider.id, PaymentStatus.PAID
            )
            overdue = await self._count_payments_by_status(
                session, access.provider.id, PaymentStatus.OVERDUE
            )
            scheduled = await repository.count_scheduled_reminders(access.provider.id)
            dashboard = ProviderDashboard(
                total_clients=total_clients,
                pending_payments=pending,
                paid_payments=paid,
                overdue_payments=overdue,
                total_templates=total_templates,
                total_bot_instances=total_bot_instances,
                scheduled_reminders=scheduled,
            )
            return {
                "provider": self._serialize_provider_model(access.provider),
                "dashboard": {
                    "total_clients": dashboard.total_clients,
                    "pending_payments": dashboard.pending_payments,
                    "paid_payments": dashboard.paid_payments,
                    "overdue_payments": dashboard.overdue_payments,
                    "total_templates": dashboard.total_templates,
                    "total_bot_instances": dashboard.total_bot_instances,
                    "scheduled_reminders": dashboard.scheduled_reminders,
                },
            }

    async def export_payments(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        format: str = "json",
    ) -> tuple[str, str]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            payments = await self._repository(session).list_payments_with_clients(
                access.provider.id
            )
            rows = [
                {
                    "reference": payment.reference,
                    "status": payment.status,
                    "amount": payment.amount,
                    "description": payment.description,
                    "client_code": client.code if client else "",
                    "client_name": client.full_name if client else "",
                    "item_code": payment.item_code or "",
                    "channel": payment.channel or "",
                    "due_at": payment.due_at.isoformat() if payment.due_at else "",
                    "paid_at": payment.paid_at.isoformat() if payment.paid_at else "",
                    "created_at": payment.created_at.isoformat(),
                }
                for payment, client in payments
            ]
            if format == "csv":
                output = StringIO()
                writer = csv.DictWriter(
                    output,
                    fieldnames=list(rows[0].keys())
                    if rows
                    else [
                        "reference",
                        "status",
                        "amount",
                        "description",
                        "client_code",
                        "client_name",
                        "item_code",
                        "channel",
                        "due_at",
                        "paid_at",
                        "created_at",
                    ],
                )
                writer.writeheader()
                writer.writerows(rows)
                return "text/csv", output.getvalue()
            return "application/json", self._json_string(rows)

    async def list_assets(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            rows = await self._repository(session).list_assets(access.provider.id)
            return [self._serialize_asset(row) for row in rows]

    async def download_asset(
        self,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        asset_code: str,
    ) -> tuple[str, str, bytes]:
        async with self._session_factory() as session:
            access = await self._authorize(
                session,
                provider_slug=provider_slug,
                api_key=api_key,
                actor_code=actor_code,
                required_role=ProviderMemberRole.VIEWER,
            )
            asset = await self._repository(session).get_asset_by_code(
                access.provider.id, asset_code
            )
            if asset is None:
                raise DomainValidationError(f"No asset found for code {asset_code}.")
            return asset.filename, asset.mime_type, asset.content_bytes

    async def handle_provider_telegram_message(
        self,
        *,
        webhook_secret: str,
        message,
    ) -> None:
        async with self._session_factory() as session:
            bot_instance = await self._load_active_bot(
                session, webhook_secret, BotPlatform.TELEGRAM
            )
            provider = await self._repository(session).get_provider_by_id(bot_instance.provider_id)
            if provider is None:
                raise DomainValidationError("Provider bot is not linked to a provider.")
            repository = self._repository(session)
            member = await repository.get_active_member_by_telegram_id(
                provider.id, message.from_user.telegram_id
            )
            parsed = parse_provider_bot_input(message.text)
            try:
                result = await self._execute_provider_bot_command(
                    session=session,
                    provider=provider,
                    bot_instance=bot_instance,
                    platform=BotPlatform.TELEGRAM,
                    parsed=parsed,
                    member=member,
                    telegram_user=message.from_user,
                )
                await session.commit()
            except (AuthorizationError, DomainValidationError) as exc:
                await session.rollback()
                result = ProviderBotCommandResult(texts=[str(exc)])

            if result.photo_bytes and result.photo_filename and result.photo_caption:
                await self._send_provider_bot_photo(
                    bot_instance.bot_token,
                    message.chat_id,
                    result.photo_bytes,
                    filename=result.photo_filename,
                    caption=result.photo_caption,
                )
            for text in result.texts:
                await self._send_provider_bot_text(bot_instance.bot_token, message.chat_id, text)

    async def handle_provider_whatsapp_message(
        self,
        *,
        webhook_secret: str,
        from_number: str,
        name: str,
        text: str,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            bot_instance = await self._load_active_bot(
                session, webhook_secret, BotPlatform.WHATSAPP
            )
            provider = await self._repository(session).get_provider_by_id(bot_instance.provider_id)
            if provider is None:
                raise DomainValidationError("Provider bot is not linked to a provider.")
            repository = self._repository(session)
            member = await repository.get_active_member_by_whatsapp_number(
                provider.id, PhoneNumber(from_number).value
            )
            parsed = parse_provider_bot_input(text)
            try:
                result = await self._execute_provider_bot_command(
                    session=session,
                    provider=provider,
                    bot_instance=bot_instance,
                    platform=BotPlatform.WHATSAPP,
                    parsed=parsed,
                    member=member,
                    whatsapp_name=name,
                    whatsapp_number=from_number,
                )
                await session.commit()
            except (AuthorizationError, DomainValidationError) as exc:
                await session.rollback()
                result = ProviderBotCommandResult(texts=[str(exc)])
            return {
                "replies": result.texts,
                "share_url": result.share_url,
                "payment_reference": result.payment_reference,
            }

    async def _execute_provider_bot_command(
        self,
        *,
        session: AsyncSession,
        provider: ProviderModel,
        bot_instance: ProviderBotInstanceModel,
        platform: BotPlatform,
        parsed,
        member: ProviderMemberModel | None,
        telegram_user=None,
        whatsapp_name: str | None = None,
        whatsapp_number: str | None = None,
    ) -> ProviderBotCommandResult:
        if isinstance(parsed, ProviderBotLoginCommand):
            linked_member = await self._link_provider_member(
                session=session,
                provider=provider,
                platform=platform,
                actor_code=parsed.actor_code,
                api_key=parsed.api_key,
                telegram_user=telegram_user,
                whatsapp_number=whatsapp_number,
            )
            role = ProviderMemberRole(linked_member.role)
            return ProviderBotCommandResult(
                texts=[
                    self._messages.build_member_identity_message(
                        provider.name,
                        linked_member.actor_code,
                        linked_member.display_name,
                        role,
                    ),
                    self._messages.build_staff_help(provider.name, role),
                ]
            )

        if isinstance(parsed, ProviderBotLogoutCommand):
            if member is None:
                return ProviderBotCommandResult(
                    texts=["No linked provider staff session was found for this chat."]
                )
            await self._unlink_provider_member(
                session=session,
                member=member,
                platform=platform,
            )
            return ProviderBotCommandResult(
                texts=[f"{provider.name} staff session has been disconnected from this chat."]
            )

        if isinstance(parsed, ProviderBotWhoamiCommand):
            if member is None:
                return ProviderBotCommandResult(texts=[self._staff_login_prompt()])
            role = ProviderMemberRole(member.role)
            return ProviderBotCommandResult(
                texts=[
                    self._messages.build_member_identity_message(
                        provider.name,
                        member.actor_code,
                        member.display_name,
                        role,
                    )
                ]
            )

        if isinstance(parsed, ProviderBotOnboardLinkCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.VIEWER)
            return ProviderBotCommandResult(
                texts=[
                    self._messages.build_onboarding_link_message(
                        provider.name,
                        platform,
                        self._format_bot_public_handle(platform, bot_instance.public_handle),
                    )
                ]
            )

        if isinstance(parsed, ProviderBotDashboardCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.VIEWER)
            payload = await self.get_dashboard(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
            )
            return ProviderBotCommandResult(texts=[self._dashboard_message(provider.name, payload)])

        if isinstance(parsed, ProviderBotClientsCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.VIEWER)
            rows = await self.list_clients(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
            )
            return ProviderBotCommandResult(texts=[self._clients_message(provider.name, rows)])

        if isinstance(parsed, ProviderBotClientPaymentsCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.VIEWER)
            payload = await self.list_client_payments(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                client_code=parsed.client_code,
            )
            return ProviderBotCommandResult(
                texts=[self._client_payments_message(provider.name, payload)]
            )

        if isinstance(parsed, ProviderBotHistoryCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.VIEWER)
            payload = await self.get_payment_history(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                payment_reference=parsed.payment_reference,
            )
            return ProviderBotCommandResult(
                texts=[self._payment_history_message(provider.name, payload)]
            )

        if isinstance(parsed, ProviderBotChargeCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            payload = await self.create_payment_request(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                amount=parsed.amount,
                description=parsed.description,
                client_code=parsed.client_code,
                channel=platform.value,
                walk_in=False,
            )
            return await self._payment_command_result(
                provider=provider,
                platform=platform,
                payment_payload=payload,
                share_to_phone=PhoneNumber(whatsapp_number).value if whatsapp_number else None,
                follow_up_text=(
                    f"Created payment {payload['payment']['reference']}.\n"
                    "Use /share <payment_reference> [telegram|whatsapp] or /remind to deliver it."
                ),
            )

        if isinstance(parsed, ProviderBotShareCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            payload = await self.share_payment_request(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                payment_reference=parsed.payment_reference,
                channel=(parsed.channel or platform.value),
            )
            return ProviderBotCommandResult(
                texts=[self._share_result_message(provider.name, payload)],
                share_url=payload.get("share_url"),
                payment_reference=payload["payment_reference"],
            )

        if isinstance(parsed, ProviderBotStatusCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            payload = await self.mark_payment_status(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                payment_reference=parsed.payment_reference,
                status=parsed.status,
                notes_summary=parsed.notes_summary,
            )
            return ProviderBotCommandResult(
                texts=[self._payment_status_message(provider.name, payload)]
            )

        if isinstance(parsed, ProviderBotNoteCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            payload = await self.add_payment_note(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                payment_reference=parsed.payment_reference,
                note=parsed.note,
            )
            return ProviderBotCommandResult(
                texts=[self._payment_note_message(provider.name, payload)]
            )

        if isinstance(parsed, ProviderBotReminderCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            reminder_type = (
                ReminderType.SCHEDULED.value
                if parsed.scheduled_for is not None
                else ReminderType.MANUAL.value
            )
            payload = await self.create_reminder(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                reminder_type=reminder_type,
                channel=platform.value,
                message=parsed.message,
                payment_reference=parsed.payment_reference,
                scheduled_for=parsed.scheduled_for,
                include_qr=True,
            )
            return ProviderBotCommandResult(
                texts=[self._reminder_message(provider.name, payload)],
                share_url=payload.get("share_url"),
                payment_reference=parsed.payment_reference,
            )

        if isinstance(parsed, ProviderBotRunRemindersCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.OPERATOR)
            payload = await self.run_due_reminders(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
            )
            return ProviderBotCommandResult(
                texts=[
                    (
                        f"{provider.name} reminders\n\n"
                        f"Processed: {payload['processed']}\n"
                        f"Sent: {payload['sent']}\n"
                        f"Failed: {payload['failed']}"
                    )
                ]
            )

        if isinstance(parsed, ProviderBotMemberAddCommand):
            self._ensure_provider_bot_member_role(member, ProviderMemberRole.MANAGER)
            payload = await self.create_member(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=member.actor_code,
                requesting_role=ProviderMemberRole.MANAGER,
                new_actor_code=parsed.actor_code,
                display_name=parsed.display_name,
                role=parsed.role,
            )
            return ProviderBotCommandResult(
                texts=[
                    (
                        f"{provider.name} team member created\n\n"
                        f"Actor: {payload['actor_code']}\n"
                        f"Role: {payload['role']}\n"
                        "Share the provider API key privately so they can run:\n"
                        f"/login {payload['actor_code']} <provider_api_key>"
                    )
                ]
            )

        if isinstance(parsed, ProviderBotItemCodeCommand):
            client = await self._ensure_provider_bot_client(
                session=session,
                provider=provider,
                bot_instance=bot_instance,
                platform=platform,
                telegram_user=telegram_user,
                whatsapp_name=whatsapp_name,
                whatsapp_number=whatsapp_number,
            )
            await session.commit()
            payload = await self.get_qr_by_item_code(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=None,
                item_code=parsed.item_code,
                amount=parsed.amount,
                client_code=client.code,
            )
            return await self._item_code_command_result(
                provider=provider,
                platform=platform,
                payload=payload,
                item_code=parsed.item_code,
                client_code=client.code,
                actor_code=None,
                share_to_phone=PhoneNumber(whatsapp_number).value if whatsapp_number else None,
            )

        if isinstance(parsed, ProviderBotPayCommand):
            client = await self._ensure_provider_bot_client(
                session=session,
                provider=provider,
                bot_instance=bot_instance,
                platform=platform,
                telegram_user=telegram_user,
                whatsapp_name=whatsapp_name,
                whatsapp_number=whatsapp_number,
            )
            await session.commit()
            payload = await self.create_payment_request(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=None,
                amount=parsed.amount,
                description=parsed.description,
                client_code=client.code,
                channel=platform.value,
                walk_in=False,
            )
            return await self._payment_command_result(
                provider=provider,
                platform=platform,
                payment_payload=payload,
                share_to_phone=PhoneNumber(whatsapp_number).value if whatsapp_number else None,
            )

        if isinstance(parsed, (ProviderBotStartCommand, ProviderBotHelpCommand)):
            if member is None:
                await self._ensure_provider_bot_client(
                    session=session,
                    provider=provider,
                    bot_instance=bot_instance,
                    platform=platform,
                    telegram_user=telegram_user,
                    whatsapp_name=whatsapp_name,
                    whatsapp_number=whatsapp_number,
                )
            return ProviderBotCommandResult(
                texts=[self._provider_bot_help_message(provider, member)]
            )

        if isinstance(parsed, ProviderBotMalformedCommand):
            return ProviderBotCommandResult(
                texts=[f"Use: {parsed.usage}", self._provider_bot_help_message(provider, member)]
            )

        if isinstance(parsed, (ProviderBotUnsupportedCommand, ProviderBotPlainText)):
            if member is None:
                await self._ensure_provider_bot_client(
                    session=session,
                    provider=provider,
                    bot_instance=bot_instance,
                    platform=platform,
                    telegram_user=telegram_user,
                    whatsapp_name=whatsapp_name,
                    whatsapp_number=whatsapp_number,
                )
            return ProviderBotCommandResult(
                texts=[self._provider_bot_help_message(provider, member)]
            )

        return ProviderBotCommandResult(
            texts=[self._provider_bot_help_message(provider, member)]
        )

    async def _link_provider_member(
        self,
        *,
        session: AsyncSession,
        provider: ProviderModel,
        platform: BotPlatform,
        actor_code: str,
        api_key: str,
        telegram_user=None,
        whatsapp_number: str | None = None,
    ) -> ProviderMemberModel:
        if provider.api_key != api_key:
            raise AuthorizationError("Invalid provider API key.")
        repository = self._repository(session)
        member = await repository.get_active_member(provider.id, actor_code)
        if member is None:
            raise AuthorizationError("Unknown or inactive provider actor.")
        now = self._now_provider()
        if platform == BotPlatform.TELEGRAM:
            if telegram_user is None:
                raise DomainValidationError("Telegram identity is required for login.")
            existing = await repository.get_active_member_by_telegram_id(
                provider.id, telegram_user.telegram_id
            )
            if existing is not None and existing.id != member.id:
                raise AuthorizationError(
                    f"This Telegram account is already linked to actor {existing.actor_code}."
                )
            member.telegram_id = telegram_user.telegram_id
            member.telegram_username = telegram_user.username
        else:
            if whatsapp_number is None:
                raise DomainValidationError("WhatsApp identity is required for login.")
            normalized_number = PhoneNumber(whatsapp_number).value
            existing = await repository.get_active_member_by_whatsapp_number(
                provider.id, normalized_number
            )
            if existing is not None and existing.id != member.id:
                raise AuthorizationError(
                    f"This WhatsApp number is already linked to actor {existing.actor_code}."
                )
            member.whatsapp_number = normalized_number
        member.updated_at = now
        return member

    async def _unlink_provider_member(
        self,
        *,
        session: AsyncSession,
        member: ProviderMemberModel,
        platform: BotPlatform,
    ) -> None:
        member.updated_at = self._now_provider()
        if platform == BotPlatform.TELEGRAM:
            member.telegram_id = None
            member.telegram_username = None
        else:
            member.whatsapp_number = None

    async def _ensure_provider_bot_client(
        self,
        *,
        session: AsyncSession,
        provider: ProviderModel,
        bot_instance: ProviderBotInstanceModel,
        platform: BotPlatform,
        telegram_user=None,
        whatsapp_name: str | None = None,
        whatsapp_number: str | None = None,
    ) -> ClientModel:
        if platform == BotPlatform.TELEGRAM:
            if telegram_user is None:
                raise DomainValidationError("Telegram client context is missing.")
            return await self._upsert_client_from_telegram(
                session,
                provider=provider,
                bot_instance=bot_instance,
                telegram_id=telegram_user.telegram_id,
                first_name=telegram_user.display_name or telegram_user.first_name,
                username=telegram_user.username,
            )
        if whatsapp_name is None or whatsapp_number is None:
            raise DomainValidationError("WhatsApp client context is missing.")
        return await self._upsert_client_from_whatsapp(
            session,
            provider=provider,
            bot_instance=bot_instance,
            full_name=whatsapp_name,
            whatsapp_number=whatsapp_number,
        )

    def _ensure_provider_bot_member_role(
        self,
        member: ProviderMemberModel | None,
        required_role: ProviderMemberRole,
    ) -> None:
        if member is None:
            raise AuthorizationError(self._staff_login_prompt())
        member_role = ProviderMemberRole(member.role)
        if ROLE_RANK[member_role] < ROLE_RANK[required_role]:
            raise AuthorizationError(f"This command requires {required_role.value} access.")

    async def _item_code_command_result(
        self,
        *,
        provider: ProviderModel,
        platform: BotPlatform,
        payload: dict[str, Any],
        item_code: str,
        client_code: str,
        actor_code: str | None,
        share_to_phone: str | None,
    ) -> ProviderBotCommandResult:
        payment_info = payload.get("payment")
        if payment_info:
            return await self._payment_command_result(
                provider=provider,
                platform=platform,
                payment_payload=payment_info,
                share_to_phone=share_to_phone,
            )
        asset_info = payload.get("asset")
        if asset_info is None:
            return ProviderBotCommandResult(texts=[self._provider_bot_help_message(provider, None)])
        if platform == BotPlatform.TELEGRAM:
            filename, _, content = await self.download_asset(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=actor_code,
                asset_code=asset_info["code"],
            )
            template = payload["template"]
            return ProviderBotCommandResult(
                texts=[],
                photo_bytes=content,
                photo_filename=filename,
                photo_caption=f"{provider.name} payment QR\nItem: {template['item_code']}",
            )
        live_payment = await self.create_payment_request(
            provider_slug=provider.slug,
            api_key=provider.api_key,
            actor_code=actor_code,
            amount=None,
            description=None,
            client_code=client_code,
            item_code=item_code,
            channel=platform.value,
            walk_in=False,
        )
        return await self._payment_command_result(
            provider=provider,
            platform=platform,
            payment_payload=live_payment,
            share_to_phone=share_to_phone,
        )

    async def _payment_command_result(
        self,
        *,
        provider: ProviderModel,
        platform: BotPlatform,
        payment_payload: dict[str, Any],
        share_to_phone: str | None,
        follow_up_text: str | None = None,
    ) -> ProviderBotCommandResult:
        payment = payment_payload["payment"]
        if platform == BotPlatform.TELEGRAM:
            asset = next(
                (
                    row
                    for row in payment_payload["assets"]
                    if row["asset_type"] == QrAssetType.PAYMENT_CARD.value
                ),
                payment_payload["assets"][0],
            )
            filename, _, content = await self.download_asset(
                provider_slug=provider.slug,
                api_key=provider.api_key,
                actor_code=None,
                asset_code=asset["code"],
            )
            texts = [follow_up_text] if follow_up_text else []
            return ProviderBotCommandResult(
                texts=texts,
                photo_bytes=content,
                photo_filename=filename,
                photo_caption=self._bot_payment_caption(provider.name, payment),
                payment_reference=payment["reference"],
            )
        payment_text = self._bot_payment_caption(provider.name, payment)
        if follow_up_text:
            payment_text = f"{payment_text}\n\n{follow_up_text}"
        share_url = None
        if share_to_phone:
            share_url = self._build_whatsapp_share_link(PhoneNumber(share_to_phone), payment_text)
        return ProviderBotCommandResult(
            texts=[payment_text],
            share_url=share_url,
            payment_reference=payment["reference"],
        )

    def _provider_bot_help_message(
        self,
        provider: ProviderModel,
        member: ProviderMemberModel | None,
    ) -> str:
        role = ProviderMemberRole(member.role) if member is not None else None
        return self._bot_welcome_message(provider.name, provider.branding_json, member_role=role)

    def _staff_login_prompt(self) -> str:
        return "This command is for linked provider staff. Use /login <actor_code> <api_key>."

    def _format_bot_public_handle(
        self,
        platform: BotPlatform,
        public_handle: str | None,
    ) -> str | None:
        if not public_handle:
            return None
        normalized = public_handle.strip()
        if normalized.startswith("http"):
            return normalized
        if platform == BotPlatform.TELEGRAM:
            if normalized.startswith("t.me/"):
                return f"https://{normalized}"
            return f"https://t.me/{normalized.lstrip('@')}"
        if normalized.startswith(("wa.me/", "api.whatsapp.com/")):
            return f"https://{normalized}"
        if platform == BotPlatform.WHATSAPP:
            return f"https://wa.me/{normalized.lstrip('+')}"
        return normalized

    def _dashboard_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        dashboard = payload["dashboard"]
        return (
            f"{provider_name} dashboard\n\n"
            f"Clients: {dashboard['total_clients']}\n"
            f"Pending payments: {dashboard['pending_payments']}\n"
            f"Paid payments: {dashboard['paid_payments']}\n"
            f"Overdue payments: {dashboard['overdue_payments']}\n"
            f"Templates: {dashboard['total_templates']}\n"
            f"Bots: {dashboard['total_bot_instances']}\n"
            f"Scheduled reminders: {dashboard['scheduled_reminders']}"
        )

    def _clients_message(self, provider_name: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return f"{provider_name} clients\n\nNo clients are saved yet."
        preview = rows[:10]
        lines = [f"{provider_name} clients\n"]
        for row in preview:
            lines.append(
                f"\n{row['code']} - {row['full_name']} ({row['onboarding_source']})"
            )
        if len(rows) > len(preview):
            lines.append(f"\n\nShowing {len(preview)} of {len(rows)} clients.")
        return "".join(lines)

    def _client_payments_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        client = payload["client"]
        payments = payload["payments"]
        if not payments:
            return (
                f"{provider_name} payments\n\n"
                f"{client['full_name']} ({client['code']}) has no payments yet."
            )
        lines = [f"{provider_name} payments\n\n{client['full_name']} ({client['code']})\n"]
        for payment in payments[:10]:
            lines.append(
                f"\n{payment['reference']} - Rs {payment['amount']} - {payment['status']}"
            )
        if len(payments) > 10:
            lines.append(f"\n\nShowing 10 of {len(payments)} payments.")
        return "".join(lines)

    def _payment_history_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        payment = payload["payment"]
        notes = payload["notes"][-3:]
        logs = payload["logs"][-5:]
        lines = [
            f"{provider_name} payment history\n\n"
            f"Reference: {payment['reference']}\n"
            f"Amount: Rs {payment['amount']}\n"
            f"Status: {payment['status']}"
        ]
        if notes:
            lines.append("\n\nNotes:")
            for note in notes:
                lines.append(f"\n- {note['created_by']}: {note['note']}")
        if logs:
            lines.append("\n\nRecent events:")
            for log in logs:
                lines.append(f"\n- {log['event_type']}: {log['message']}")
        return "".join(lines)

    def _share_result_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        message = (
            f"{provider_name} payment share\n\n"
            f"Reference: {payload['payment_reference']}\n"
            f"Channel: {payload['channel']}\n"
            f"State: {payload['delivery_state']}\n"
            f"Recipient: {payload['recipient']}"
        )
        if payload.get("share_url"):
            message += f"\nShare URL: {payload['share_url']}"
        return message

    def _payment_status_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        return (
            f"{provider_name} payment updated\n\n"
            f"Reference: {payload['reference']}\n"
            f"Status: {payload['status']}\n"
            f"Notes: {payload['notes_summary'] or '-'}"
        )

    def _payment_note_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        return (
            f"{provider_name} payment note saved\n\n"
            f"Reference: {payload['payment_reference']}\n"
            f"Note: {payload['note']}"
        )

    def _reminder_message(self, provider_name: str, payload: dict[str, Any]) -> str:
        message = (
            f"{provider_name} reminder\n\n"
            f"Code: {payload['code']}\n"
            f"Status: {payload['status']}\n"
            f"Channel: {payload['channel']}"
        )
        if payload.get("scheduled_for"):
            message += f"\nScheduled for: {payload['scheduled_for']}"
        if payload.get("delivery_state"):
            message += f"\nDelivery: {payload['delivery_state']}"
        if payload.get("recipient"):
            message += f"\nRecipient: {payload['recipient']}"
        if payload.get("share_url"):
            message += f"\nShare URL: {payload['share_url']}"
        return message

    async def _authorize(
        self,
        session: AsyncSession,
        *,
        provider_slug: str,
        api_key: str,
        actor_code: str | None,
        required_role: ProviderMemberRole,
    ) -> ProviderAccessContext:
        repository = self._repository(session)
        provider = await repository.get_provider_by_slug(ProviderSlug(provider_slug).value)
        if provider is None:
            raise DomainValidationError(f"Provider {provider_slug} was not found.")
        if provider.api_key != api_key:
            raise AuthorizationError("Invalid provider API key.")
        member = None
        if actor_code:
            member = await repository.get_active_member(provider.id, actor_code)
            if member is None:
                raise AuthorizationError("Unknown or inactive provider actor.")
            if ROLE_RANK[ProviderMemberRole(member.role)] < ROLE_RANK[required_role]:
                raise AuthorizationError("Provider actor does not have enough access.")
        return ProviderAccessContext(provider=provider, member=member)

    async def _clear_default_destinations(self, session: AsyncSession, provider_id: UUID) -> None:
        await self._repository(session).clear_default_destinations(provider_id)

    async def _resolve_destination(
        self,
        session: AsyncSession,
        *,
        provider_id: UUID,
        destination_code: str | None,
    ) -> PaymentDestinationModel:
        destination = await self._repository(session).get_active_destination(
            provider_id,
            destination_code,
        )
        if destination is None:
            raise DomainValidationError("No active payment destination is configured.")
        return destination

    async def _find_bot_instance_by_code(
        self,
        session: AsyncSession,
        *,
        provider_id: UUID,
        code: str | None,
        platform: BotPlatform | None = None,
    ) -> ProviderBotInstanceModel | None:
        return await self._repository(session).get_bot_instance_by_code(
            provider_id,
            code,
            platform,
        )

    async def _find_client(
        self,
        session: AsyncSession,
        *,
        provider_id: UUID,
        client_code: str | None,
        required: bool = False,
    ) -> ClientModel | None:
        client = await self._repository(session).get_client_by_code(provider_id, client_code)
        if client is None and required:
            raise DomainValidationError(f"No client found for code {client_code}.")
        return client

    async def _find_template(
        self,
        session: AsyncSession,
        *,
        provider_id: UUID,
        template_code: str | None,
        item_code: str | None,
        required: bool = False,
    ) -> PaymentTemplateModel | None:
        template = await self._repository(session).get_template(
            provider_id,
            template_code.strip().upper() if template_code else None,
            ItemCode(item_code).value if item_code else None,
        )
        if template is None and required:
            raise DomainValidationError("Payment template could not be found.")
        return template

    def _resolve_amount(self, amount: str | None, template: PaymentTemplateModel | None) -> Money:
        if amount is not None:
            return self._parse_money(amount)
        if template and template.default_amount is not None:
            return Money(Decimal(template.default_amount))
        raise DomainValidationError("Amount is required when the template has no default amount.")

    def _resolve_description(
        self,
        *,
        description: str | None,
        template: PaymentTemplateModel | None,
        item_code: str | None,
        walk_in: bool,
    ) -> str:
        if description and description.strip():
            return description.strip()
        if template is not None:
            return template.description
        if item_code:
            return f"Payment for {ItemCode(item_code).value}"
        if walk_in:
            return "Walk-in payment"
        raise DomainValidationError("Payment description is required.")

    async def _create_asset_bundle(
        self,
        session: AsyncSession,
        *,
        provider: ProviderModel,
        payment: PaymentRequest,
        template: PaymentTemplateModel | None,
        payment_request_model: PaymentRequestModel | None,
        is_pre_generated: bool,
    ) -> list[QrAssetModel]:
        branding = self._merge_branding(provider.branding_json, None)
        qr_bytes = await self._qr_generator.generate_png(payment.upi_uri)
        card_bytes = render_payment_card_png(
            provider_name=provider.name,
            payment_reference=payment.reference.value,
            description=payment.description,
            amount=payment.amount.as_upi_amount(),
            upi_uri=payment.upi_uri,
            branding=branding,
            qr_bytes=qr_bytes,
            print_ready=False,
        )
        print_ready_bytes = render_payment_card_png(
            provider_name=provider.name,
            payment_reference=payment.reference.value,
            description=payment.description,
            amount=payment.amount.as_upi_amount(),
            upi_uri=payment.upi_uri,
            branding=branding,
            qr_bytes=qr_bytes,
            print_ready=True,
        )
        specs = [
            (QrAssetType.PAYMENT_QR, qr_bytes, f"{payment.reference.value}-qr.png"),
            (QrAssetType.PAYMENT_CARD, card_bytes, f"{payment.reference.value}-card.png"),
            (QrAssetType.PRINT_READY, print_ready_bytes, f"{payment.reference.value}-print.png"),
        ]
        assets: list[QrAssetModel] = []
        for asset_type, content, filename in specs:
            asset = QrAsset(
                id=uuid4(),
                code=self._generate_code("QRA"),
                provider_id=provider.id,
                payment_request_id=payment_request_model.id if payment_request_model else None,
                template_id=template.id if template else None,
                item_code=payment.item_code,
                asset_type=asset_type,
                mime_type="image/png",
                filename=filename,
                content_bytes=content,
                amount=payment.amount.amount,
                upi_uri=payment.upi_uri,
                is_pre_generated=is_pre_generated,
                metadata={
                    "reference": payment.reference.value,
                    "provider_slug": provider.slug,
                    "template_code": template.code if template else "",
                },
                created_at=self._now_provider(),
                updated_at=self._now_provider(),
            )
            model = QrAssetModel(
                id=asset.id,
                code=asset.code,
                provider_id=asset.provider_id,
                payment_request_id=asset.payment_request_id,
                template_id=asset.template_id,
                item_code=asset.item_code,
                asset_type=asset.asset_type.value,
                mime_type=asset.mime_type,
                filename=asset.filename,
                content_bytes=asset.content_bytes,
                amount=asset.amount,
                upi_uri=asset.upi_uri,
                is_pre_generated=asset.is_pre_generated,
                metadata_json=asset.metadata,
                created_at=asset.created_at,
                updated_at=asset.updated_at,
            )
            session.add(model)
            assets.append(model)
        return assets

    async def _append_payment_log(
        self,
        session: AsyncSession,
        *,
        payment_request_id: UUID,
        event_type: str,
        message: str,
        created_by: str,
        payload: dict[str, str],
        now: datetime,
    ) -> None:
        log = PaymentLog(
            id=uuid4(),
            payment_request_id=payment_request_id,
            event_type=event_type,
            message=message,
            payload=payload,
            created_by=created_by,
            created_at=now,
        )
        session.add(
            PaymentLogModel(
                id=log.id,
                payment_request_id=log.payment_request_id,
                event_type=log.event_type,
                message=log.message,
                payload_json=log.payload,
                created_by=log.created_by,
                created_at=log.created_at,
            )
        )

    async def _load_payment(
        self,
        session: AsyncSession,
        provider_id: UUID,
        payment_reference: str | None,
    ) -> PaymentRequestModel:
        if not payment_reference:
            raise DomainValidationError("Payment reference is required.")
        payment = await self._repository(session).get_payment_by_reference(
            provider_id,
            payment_reference,
        )
        if payment is None:
            raise DomainValidationError(
                f"No payment request found for reference {payment_reference}."
            )
        return payment

    async def _resolve_client_for_payment(
        self,
        session: AsyncSession,
        *,
        provider_id: UUID,
        payment: PaymentRequestModel | None,
        explicit_client_code: str | None,
    ) -> ClientModel | None:
        if explicit_client_code:
            return await self._find_client(
                session,
                provider_id=provider_id,
                client_code=explicit_client_code,
                required=True,
            )
        if payment and payment.client_id:
            return await session.get(ClientModel, payment.client_id)
        return None

    async def _preferred_payment_asset(
        self,
        session: AsyncSession,
        payment_request_id: UUID,
    ) -> QrAssetModel | None:
        return await self._repository(session).get_preferred_payment_asset(payment_request_id)

    def _build_payment_message(
        self,
        *,
        provider: ProviderModel,
        client: ClientModel | None,
        payment: PaymentRequestModel,
        custom_message: str | None,
    ) -> str:
        return self._messages.build_payment_message(
            provider=provider,
            client=client,
            payment=payment,
            custom_message=custom_message,
        )

    async def _dispatch_message(
        self,
        *,
        provider: ProviderModel,
        client: ClientModel | None,
        channel: MessageChannel,
        message: str,
        asset: QrAssetModel | None,
        bot_instance: ProviderBotInstanceModel | None,
    ) -> OutboundDispatchResult:
        if channel == MessageChannel.TELEGRAM:
            if client is None or client.telegram_id is None:
                return OutboundDispatchResult(
                    delivery_state=DeliveryState.MANUAL_SHARE,
                    recipient=client.full_name if client else "unknown",
                    share_url=None,
                    bot_instance=None,
                )
            active_bot = bot_instance or await self._find_active_platform_bot(
                provider_id=provider.id,
                platform=BotPlatform.TELEGRAM,
            )
            if active_bot is None or not active_bot.bot_token:
                return OutboundDispatchResult(
                    delivery_state=DeliveryState.MANUAL_SHARE,
                    recipient=str(client.telegram_id),
                    share_url=None,
                    bot_instance=active_bot,
                )
            if asset is not None:
                await self._send_provider_bot_photo(
                    active_bot.bot_token,
                    client.telegram_id,
                    asset.content_bytes,
                    filename=asset.filename,
                    caption=message,
                )
            else:
                await self._send_provider_bot_text(
                    active_bot.bot_token, client.telegram_id, message
                )
            return OutboundDispatchResult(
                delivery_state=DeliveryState.SENT,
                recipient=str(client.telegram_id),
                share_url=None,
                bot_instance=active_bot,
            )
        if channel == MessageChannel.WHATSAPP:
            if client is None or not client.whatsapp_number:
                return OutboundDispatchResult(
                    delivery_state=DeliveryState.MANUAL_SHARE,
                    recipient=client.full_name if client else "unknown",
                    share_url=None,
                    bot_instance=None,
                )
            share_url = self._build_whatsapp_share_link(
                PhoneNumber(client.whatsapp_number), message
            )
            active_bot = await self._find_active_platform_bot(
                provider_id=provider.id,
                platform=BotPlatform.WHATSAPP,
            )
            return OutboundDispatchResult(
                delivery_state=DeliveryState.MANUAL_SHARE,
                recipient=client.whatsapp_number,
                share_url=share_url,
                bot_instance=active_bot,
            )
        return OutboundDispatchResult(
            delivery_state=DeliveryState.MANUAL_SHARE,
            recipient=client.code if client else provider.slug,
            share_url=None,
            bot_instance=None,
        )

    async def _find_active_platform_bot(
        self,
        *,
        provider_id: UUID,
        platform: BotPlatform,
    ) -> ProviderBotInstanceModel | None:
        async with self._session_factory() as session:
            return await self._repository(session).get_active_platform_bot(provider_id, platform)

    async def _send_single_reminder(
        self,
        *,
        session: AsyncSession,
        provider: ProviderModel,
        reminder: PaymentReminderModel,
        payment: PaymentRequestModel | None,
        client: ClientModel | None,
        actor_code: str,
        now: datetime,
    ) -> OutboundDispatchResult:
        asset = (
            await self._preferred_payment_asset(session, payment.id)
            if payment and reminder.include_qr
            else None
        )
        message = reminder.message
        if payment is not None:
            message = self._build_payment_message(
                provider=provider,
                client=client,
                payment=payment,
                custom_message=reminder.message,
            )
        dispatch = await self._dispatch_message(
            provider=provider,
            client=client,
            channel=MessageChannel(reminder.channel),
            message=message,
            asset=asset,
            bot_instance=None,
        )
        reminder.status = (
            ReminderStatus.SENT.value
            if dispatch.delivery_state == DeliveryState.SENT
            else ReminderStatus.SCHEDULED.value
        )
        reminder.sent_at = now if dispatch.delivery_state == DeliveryState.SENT else None
        reminder.updated_at = now
        session.add(
            OutboundMessageModel(
                id=uuid4(),
                provider_id=provider.id,
                client_id=client.id if client else None,
                payment_request_id=payment.id if payment else None,
                reminder_id=reminder.id,
                bot_instance_id=dispatch.bot_instance.id if dispatch.bot_instance else None,
                channel=reminder.channel,
                delivery_state=dispatch.delivery_state.value,
                recipient=dispatch.recipient,
                message=message,
                share_url=dispatch.share_url,
                metadata_json={"reminder_code": reminder.code},
                sent_at=now if dispatch.delivery_state == DeliveryState.SENT else None,
                created_at=now,
            )
        )
        if payment is not None:
            await self._append_payment_log(
                session,
                payment_request_id=payment.id,
                event_type="reminder_sent",
                message=f"Reminder {reminder.code} processed.",
                created_by=actor_code,
                payload={
                    "reminder_type": reminder.reminder_type,
                    "channel": reminder.channel,
                    "delivery_state": dispatch.delivery_state.value,
                },
                now=now,
            )
        return dispatch

    async def _load_active_bot(
        self,
        session: AsyncSession,
        webhook_secret: str,
        platform: BotPlatform,
    ) -> ProviderBotInstanceModel:
        bot = await self._repository(session).get_active_bot_by_webhook_secret(
            webhook_secret,
            platform,
        )
        if bot is None:
            raise DomainValidationError("Provider bot was not found.")
        return bot

    async def _upsert_client_from_telegram(
        self,
        session: AsyncSession,
        *,
        provider: ProviderModel,
        bot_instance: ProviderBotInstanceModel,
        telegram_id: int,
        first_name: str,
        username: str | None,
    ) -> ClientModel:
        client = await self._repository(session).get_client_by_telegram_id(
            provider.id,
            telegram_id,
        )
        now = self._now_provider()
        if client is None:
            entity = Client(
                id=uuid4(),
                provider_id=provider.id,
                code=self._generate_code("CLI"),
                full_name=first_name,
                telegram_id=telegram_id,
                telegram_username=username,
                onboarding_source="telegram_bot",
                bot_instance_id=bot_instance.id,
                created_at=now,
                updated_at=now,
            )
            client = ClientModel(
                id=entity.id,
                provider_id=entity.provider_id,
                code=entity.code,
                full_name=entity.full_name,
                telegram_id=entity.telegram_id,
                telegram_username=entity.telegram_username,
                whatsapp_number=None,
                external_ref=None,
                notes=None,
                labels_json=[],
                onboarding_source=entity.onboarding_source,
                bot_instance_id=entity.bot_instance_id,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            session.add(client)
        else:
            client.full_name = first_name
            client.telegram_username = username
            client.updated_at = now
        return client

    async def _upsert_client_from_whatsapp(
        self,
        session: AsyncSession,
        *,
        provider: ProviderModel,
        bot_instance: ProviderBotInstanceModel,
        full_name: str,
        whatsapp_number: str,
    ) -> ClientModel:
        number = PhoneNumber(whatsapp_number).value
        client = await self._repository(session).get_client_by_whatsapp_number(
            provider.id,
            number,
        )
        now = self._now_provider()
        if client is None:
            entity = Client(
                id=uuid4(),
                provider_id=provider.id,
                code=self._generate_code("CLI"),
                full_name=full_name,
                whatsapp_number=PhoneNumber(number),
                onboarding_source="whatsapp_bot",
                bot_instance_id=bot_instance.id,
                created_at=now,
                updated_at=now,
            )
            client = ClientModel(
                id=entity.id,
                provider_id=entity.provider_id,
                code=entity.code,
                full_name=entity.full_name,
                telegram_id=None,
                telegram_username=None,
                whatsapp_number=entity.whatsapp_number.value if entity.whatsapp_number else None,
                external_ref=None,
                notes=None,
                labels_json=[],
                onboarding_source=entity.onboarding_source,
                bot_instance_id=entity.bot_instance_id,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            session.add(client)
        else:
            client.full_name = full_name
            client.updated_at = now
        return client

    async def _count_payments_by_status(
        self,
        session: AsyncSession,
        provider_id: UUID,
        status: PaymentStatus,
    ) -> int:
        return await self._repository(session).count_payments_by_status(provider_id, status)

    def _build_branding_payload(
        self,
        *,
        name: str,
        primary_color: str | None,
        secondary_color: str | None,
        accent_color: str | None,
        logo_text: str | None,
    ) -> dict[str, str]:
        return {
            "brand_name": name.strip(),
            "primary_color": self._normalize_color(primary_color or "#104252"),
            "secondary_color": self._normalize_color(secondary_color or "#FAF6F0"),
            "accent_color": self._normalize_color(accent_color or "#D97706"),
            "logo_text": (logo_text or name[:2]).strip().upper()[:8],
        }

    def _merge_branding(
        self,
        provider_branding: dict[str, str] | None,
        override_branding: dict[str, str] | None,
    ) -> dict[str, str]:
        merged = dict(provider_branding or {})
        merged.update({key: value for key, value in (override_branding or {}).items() if value})
        if "logo_text" not in merged:
            merged["logo_text"] = merged.get("brand_name", "TZ")[:2].upper()
        if "primary_color" in merged:
            merged["primary_color"] = self._normalize_color(merged["primary_color"])
        if "secondary_color" in merged:
            merged["secondary_color"] = self._normalize_color(merged["secondary_color"])
        if "accent_color" in merged:
            merged["accent_color"] = self._normalize_color(merged["accent_color"])
        return merged

    def _normalize_color(self, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("#"):
            normalized = f"#{normalized}"
        if len(normalized) != 7:
            raise DomainValidationError("Theme colors must be 6-digit hex values.")
        return normalized.upper()

    def _destination_entity(self, model: PaymentDestinationModel) -> PaymentDestination:
        return PaymentDestination(
            id=model.id,
            provider_id=model.provider_id,
            code=model.code,
            label=model.label,
            vpa=UpiVpa(model.vpa),
            payee_name=model.payee_name,
            is_default=model.is_default,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _generate_api_key(self) -> str:
        return secrets.token_urlsafe(24)

    def _generate_code(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:10].upper()}"

    def _parse_money(self, value: str) -> Money:
        try:
            return Money(Decimal(value))
        except (InvalidOperation, DomainValidationError) as exc:
            raise DomainValidationError("Amount must be a valid positive number.") from exc

    def _build_whatsapp_share_link(self, phone: PhoneNumber, message: str) -> str:
        return self._messages.build_whatsapp_share_link(phone, message)

    async def _send_provider_bot_text(self, bot_token: str | None, chat_id: int, text: str) -> None:
        if not bot_token:
            raise DomainValidationError("Telegram bot token is required for provider bot delivery.")
        client = TelegramBotClient(bot_token=bot_token, http_client=self._http_client)
        await client.send_text(chat_id, text)

    async def _send_provider_bot_photo(
        self,
        bot_token: str | None,
        chat_id: int,
        content: bytes,
        *,
        filename: str,
        caption: str,
    ) -> None:
        if not bot_token:
            raise DomainValidationError("Telegram bot token is required for provider bot delivery.")
        client = TelegramBotClient(bot_token=bot_token, http_client=self._http_client)
        await client.send_photo(chat_id, content, filename=filename, caption=caption)

    def _bot_welcome_message(
        self,
        provider_name: str,
        branding: dict[str, str] | None,
        *,
        member_role: ProviderMemberRole | None = None,
    ) -> str:
        return self._messages.build_bot_welcome_message(
            provider_name,
            branding,
            member_role=member_role,
        )

    def _bot_payment_caption(self, provider_name: str, payment: dict[str, Any]) -> str:
        return self._messages.build_bot_payment_caption(provider_name, payment)

    def _serialize_provider(
        self, provider: Provider, *, include_api_key: bool = False
    ) -> dict[str, Any]:
        return self._presenter.serialize_provider(provider, include_api_key=include_api_key)

    def _serialize_provider_model(self, provider: ProviderModel) -> dict[str, Any]:
        return self._presenter.serialize_provider_model(provider)

    def _serialize_member(self, model: ProviderMemberModel) -> dict[str, Any]:
        return self._presenter.serialize_member(model)

    def _serialize_destination(self, model: PaymentDestinationModel) -> dict[str, Any]:
        return self._presenter.serialize_destination(model)

    def _serialize_bot_instance(self, model: ProviderBotInstanceModel) -> dict[str, Any]:
        return self._presenter.serialize_bot_instance(model)

    def _serialize_client(self, model: ClientModel) -> dict[str, Any]:
        return self._presenter.serialize_client(model)

    def _serialize_template(self, model: PaymentTemplateModel) -> dict[str, Any]:
        return self._presenter.serialize_template(model)

    def _serialize_payment(self, model: PaymentRequestModel) -> dict[str, Any]:
        return self._presenter.serialize_payment(model)

    def _serialize_asset(self, model: QrAssetModel) -> dict[str, Any]:
        return self._presenter.serialize_asset(model)

    def _serialize_reminder(self, model: PaymentReminderModel) -> dict[str, Any]:
        return self._presenter.serialize_reminder(model)

    def _json_string(self, payload: Any) -> str:
        return self._presenter.json_string(payload)

    def _repository(self, session: AsyncSession) -> SQLAlchemyProviderControlRepository:
        """Create a repository adapter bound to the active SQLAlchemy session."""
        return SQLAlchemyProviderControlRepository(session)
