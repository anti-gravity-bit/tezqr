"""Repository helpers for the provider control-plane bounded context."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tezqr.domain.enums import BotPlatform, PaymentStatus, QrAssetType, ReminderStatus
from tezqr.infrastructure.persistence.models import (
    ClientModel,
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


class SQLAlchemyProviderControlRepository:
    """Centralize provider-side SQL so application services stay readable."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_provider_by_id(self, provider_id: UUID) -> ProviderModel | None:
        return await self._session.get(ProviderModel, provider_id)

    async def get_provider_by_slug(self, provider_slug: str) -> ProviderModel | None:
        return await self._session.scalar(
            select(ProviderModel).where(ProviderModel.slug == provider_slug)
        )

    async def get_active_member(
        self,
        provider_id: UUID,
        actor_code: str,
    ) -> ProviderMemberModel | None:
        return await self._session.scalar(
            select(ProviderMemberModel).where(
                ProviderMemberModel.provider_id == provider_id,
                ProviderMemberModel.actor_code == actor_code.strip().upper(),
                ProviderMemberModel.is_active.is_(True),
            )
        )

    async def get_active_member_by_telegram_id(
        self,
        provider_id: UUID,
        telegram_id: int,
    ) -> ProviderMemberModel | None:
        return await self._session.scalar(
            select(ProviderMemberModel).where(
                ProviderMemberModel.provider_id == provider_id,
                ProviderMemberModel.telegram_id == telegram_id,
                ProviderMemberModel.is_active.is_(True),
            )
        )

    async def get_active_member_by_whatsapp_number(
        self,
        provider_id: UUID,
        whatsapp_number: str,
    ) -> ProviderMemberModel | None:
        return await self._session.scalar(
            select(ProviderMemberModel).where(
                ProviderMemberModel.provider_id == provider_id,
                ProviderMemberModel.whatsapp_number == whatsapp_number,
                ProviderMemberModel.is_active.is_(True),
            )
        )

    async def clear_default_destinations(self, provider_id: UUID) -> None:
        rows = (
            await self._session.scalars(
                select(PaymentDestinationModel).where(
                    PaymentDestinationModel.provider_id == provider_id
                )
            )
        ).all()
        for row in rows:
            row.is_default = False

    async def get_active_destination(
        self,
        provider_id: UUID,
        destination_code: str | None,
    ) -> PaymentDestinationModel | None:
        query = select(PaymentDestinationModel).where(
            PaymentDestinationModel.provider_id == provider_id,
            PaymentDestinationModel.is_active.is_(True),
        )
        if destination_code:
            query = query.where(PaymentDestinationModel.code == destination_code.strip().upper())
        else:
            query = query.where(PaymentDestinationModel.is_default.is_(True))
        destination = await self._session.scalar(
            query.order_by(PaymentDestinationModel.created_at.asc())
        )
        if destination is None and destination_code is None:
            destination = await self._session.scalar(
                select(PaymentDestinationModel)
                .where(
                    PaymentDestinationModel.provider_id == provider_id,
                    PaymentDestinationModel.is_active.is_(True),
                )
                .order_by(PaymentDestinationModel.created_at.asc())
            )
        return destination

    async def get_bot_instance_by_code(
        self,
        provider_id: UUID,
        code: str | None,
        platform: BotPlatform | None = None,
    ) -> ProviderBotInstanceModel | None:
        if not code:
            return None
        query = select(ProviderBotInstanceModel).where(
            ProviderBotInstanceModel.provider_id == provider_id,
            ProviderBotInstanceModel.code == code.strip().upper(),
        )
        if platform is not None:
            query = query.where(ProviderBotInstanceModel.platform == platform.value)
        return await self._session.scalar(query)

    async def get_active_platform_bot(
        self,
        provider_id: UUID,
        platform: BotPlatform,
    ) -> ProviderBotInstanceModel | None:
        return await self._session.scalar(
            select(ProviderBotInstanceModel).where(
                ProviderBotInstanceModel.provider_id == provider_id,
                ProviderBotInstanceModel.platform == platform.value,
                ProviderBotInstanceModel.is_active.is_(True),
            )
        )

    async def get_active_bot_by_webhook_secret(
        self,
        webhook_secret: str,
        platform: BotPlatform,
    ) -> ProviderBotInstanceModel | None:
        return await self._session.scalar(
            select(ProviderBotInstanceModel).where(
                ProviderBotInstanceModel.webhook_secret == webhook_secret,
                ProviderBotInstanceModel.platform == platform.value,
                ProviderBotInstanceModel.is_active.is_(True),
            )
        )

    async def list_active_platform_bots(
        self,
        platform: BotPlatform,
    ) -> list[ProviderBotInstanceModel]:
        return (
            await self._session.scalars(
                select(ProviderBotInstanceModel)
                .where(
                    ProviderBotInstanceModel.platform == platform.value,
                    ProviderBotInstanceModel.is_active.is_(True),
                )
                .order_by(ProviderBotInstanceModel.created_at.asc())
            )
        ).all()

    async def list_clients(self, provider_id: UUID) -> list[ClientModel]:
        return (
            await self._session.scalars(
                select(ClientModel)
                .where(ClientModel.provider_id == provider_id)
                .order_by(ClientModel.created_at.asc())
            )
        ).all()

    async def get_client_by_code(
        self,
        provider_id: UUID,
        client_code: str | None,
    ) -> ClientModel | None:
        if not client_code:
            return None
        return await self._session.scalar(
            select(ClientModel).where(
                ClientModel.provider_id == provider_id,
                ClientModel.code == client_code.strip().upper(),
            )
        )

    async def get_client_by_telegram_id(
        self,
        provider_id: UUID,
        telegram_id: int,
    ) -> ClientModel | None:
        return await self._session.scalar(
            select(ClientModel).where(
                ClientModel.provider_id == provider_id,
                ClientModel.telegram_id == telegram_id,
            )
        )

    async def get_client_by_whatsapp_number(
        self,
        provider_id: UUID,
        whatsapp_number: str,
    ) -> ClientModel | None:
        return await self._session.scalar(
            select(ClientModel).where(
                ClientModel.provider_id == provider_id,
                ClientModel.whatsapp_number == whatsapp_number,
            )
        )

    async def get_template(
        self,
        provider_id: UUID,
        template_code: str | None,
        item_code: str | None,
    ) -> PaymentTemplateModel | None:
        query = None
        if template_code:
            query = select(PaymentTemplateModel).where(
                PaymentTemplateModel.provider_id == provider_id,
                PaymentTemplateModel.code == template_code.strip().upper(),
            )
        elif item_code:
            query = select(PaymentTemplateModel).where(
                PaymentTemplateModel.provider_id == provider_id,
                PaymentTemplateModel.item_code == item_code.strip().upper(),
            )
        if query is None:
            return None
        return await self._session.scalar(query)

    async def get_latest_pre_generated_asset(
        self,
        template_id: UUID,
        item_code: str,
    ) -> QrAssetModel | None:
        return await self._session.scalar(
            select(QrAssetModel)
            .where(
                QrAssetModel.template_id == template_id,
                QrAssetModel.item_code == item_code,
                QrAssetModel.is_pre_generated.is_(True),
                QrAssetModel.asset_type == QrAssetType.PAYMENT_CARD.value,
            )
            .order_by(QrAssetModel.created_at.desc())
        )

    async def get_payment_by_reference(
        self,
        provider_id: UUID,
        payment_reference: str | None,
    ) -> PaymentRequestModel | None:
        if not payment_reference:
            return None
        return await self._session.scalar(
            select(PaymentRequestModel).where(
                PaymentRequestModel.provider_id == provider_id,
                PaymentRequestModel.reference == payment_reference.strip().upper(),
            )
        )

    async def list_notes(self, payment_request_id: UUID) -> list[PaymentNoteModel]:
        return (
            await self._session.scalars(
                select(PaymentNoteModel)
                .where(PaymentNoteModel.payment_request_id == payment_request_id)
                .order_by(PaymentNoteModel.created_at.asc())
            )
        ).all()

    async def list_logs(self, payment_request_id: UUID) -> list[PaymentLogModel]:
        return (
            await self._session.scalars(
                select(PaymentLogModel)
                .where(PaymentLogModel.payment_request_id == payment_request_id)
                .order_by(PaymentLogModel.created_at.asc())
            )
        ).all()

    async def list_payments_by_client(self, client_id: UUID) -> list[PaymentRequestModel]:
        return (
            await self._session.scalars(
                select(PaymentRequestModel)
                .where(PaymentRequestModel.client_id == client_id)
                .order_by(PaymentRequestModel.created_at.desc())
            )
        ).all()

    async def list_due_reminders(
        self,
        provider_id: UUID,
        now: datetime,
    ) -> list[PaymentReminderModel]:
        return (
            await self._session.scalars(
                select(PaymentReminderModel)
                .where(
                    PaymentReminderModel.provider_id == provider_id,
                    PaymentReminderModel.status.in_(
                        [ReminderStatus.SCHEDULED.value, ReminderStatus.DRAFT.value]
                    ),
                    or_(
                        PaymentReminderModel.scheduled_for.is_(None),
                        PaymentReminderModel.scheduled_for <= now,
                    ),
                )
                .order_by(PaymentReminderModel.created_at.asc())
            )
        ).all()

    async def count_clients(self, provider_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(ClientModel.id)).where(ClientModel.provider_id == provider_id)
            )
            or 0
        )

    async def count_templates(self, provider_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(PaymentTemplateModel.id)).where(
                    PaymentTemplateModel.provider_id == provider_id
                )
            )
            or 0
        )

    async def count_bot_instances(self, provider_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(ProviderBotInstanceModel.id)).where(
                    ProviderBotInstanceModel.provider_id == provider_id
                )
            )
            or 0
        )

    async def count_payments_by_status(
        self,
        provider_id: UUID,
        status: PaymentStatus,
    ) -> int:
        return int(
            await self._session.scalar(
                select(func.count(PaymentRequestModel.id)).where(
                    PaymentRequestModel.provider_id == provider_id,
                    PaymentRequestModel.status == status.value,
                )
            )
            or 0
        )

    async def count_scheduled_reminders(self, provider_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(PaymentReminderModel.id)).where(
                    PaymentReminderModel.provider_id == provider_id,
                    PaymentReminderModel.status == ReminderStatus.SCHEDULED.value,
                )
            )
            or 0
        )

    async def list_payments_with_clients(
        self,
        provider_id: UUID,
    ) -> list[tuple[PaymentRequestModel, ClientModel | None]]:
        return (
            await self._session.execute(
                select(PaymentRequestModel, ClientModel)
                .outerjoin(ClientModel, ClientModel.id == PaymentRequestModel.client_id)
                .where(PaymentRequestModel.provider_id == provider_id)
                .order_by(PaymentRequestModel.created_at.asc())
            )
        ).all()

    async def list_assets(self, provider_id: UUID) -> list[QrAssetModel]:
        return (
            await self._session.scalars(
                select(QrAssetModel)
                .where(QrAssetModel.provider_id == provider_id)
                .order_by(QrAssetModel.created_at.desc())
            )
        ).all()

    async def get_asset_by_code(
        self,
        provider_id: UUID,
        asset_code: str,
    ) -> QrAssetModel | None:
        return await self._session.scalar(
            select(QrAssetModel).where(
                QrAssetModel.provider_id == provider_id,
                QrAssetModel.code == asset_code.strip().upper(),
            )
        )

    async def get_preferred_payment_asset(
        self,
        payment_request_id: UUID,
    ) -> QrAssetModel | None:
        return await self._session.scalar(
            select(QrAssetModel)
            .where(
                QrAssetModel.payment_request_id == payment_request_id,
                QrAssetModel.asset_type == QrAssetType.PAYMENT_CARD.value,
            )
            .order_by(QrAssetModel.created_at.desc())
        )
