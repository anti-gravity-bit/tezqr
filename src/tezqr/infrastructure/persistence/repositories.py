from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tezqr.application.ports import (
    MerchantRepository,
    PaymentRequestRepository,
    UpgradeRequestRepository,
)
from tezqr.domain.entities import Merchant, PaymentRequest, UpgradeRequest
from tezqr.domain.enums import MerchantTier
from tezqr.domain.value_objects import TelegramUser, UpgradeRequestCode, UpiVpa
from tezqr.infrastructure.persistence.models import (
    MerchantModel,
    PaymentRequestModel,
    UpgradeRequestModel,
)


def _merchant_to_domain(model: MerchantModel) -> Merchant:
    return Merchant(
        id=model.id,
        telegram_user=TelegramUser(
            telegram_id=model.telegram_id,
            first_name=model.first_name,
            username=model.username,
            last_name=model.last_name,
        ),
        tier=MerchantTier(model.tier),
        generation_count=model.generation_count,
        vpa=UpiVpa(model.vpa) if model.vpa else None,
        last_command_at=model.last_command_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _upgrade_request_to_domain(model: UpgradeRequestModel) -> UpgradeRequest:
    return UpgradeRequest(
        id=model.id,
        merchant_id=model.merchant_id,
        approval_code=UpgradeRequestCode(model.approval_code),
        telegram_chat_id=model.telegram_chat_id,
        telegram_message_id=model.telegram_message_id,
        telegram_file_id=model.telegram_file_id,
        telegram_file_unique_id=model.telegram_file_unique_id,
        media_kind=model.media_kind,
        status=model.status,
        created_at=model.created_at,
    )


class SQLAlchemyMerchantRepository(MerchantRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, merchant_id: object) -> Merchant | None:
        result = await self._session.get(MerchantModel, merchant_id)
        if result is None:
            return None
        return _merchant_to_domain(result)

    async def get_by_telegram_id(self, telegram_id: int) -> Merchant | None:
        result = await self._session.scalar(
            select(MerchantModel).where(MerchantModel.telegram_id == telegram_id)
        )
        if result is None:
            return None
        return _merchant_to_domain(result)

    async def add(self, merchant: Merchant) -> None:
        self._session.add(
            MerchantModel(
                id=merchant.id,
                telegram_id=merchant.telegram_user.telegram_id,
                username=merchant.telegram_user.username,
                first_name=merchant.telegram_user.first_name,
                last_name=merchant.telegram_user.last_name,
                vpa=merchant.vpa.value if merchant.vpa else None,
                tier=merchant.tier.value,
                generation_count=merchant.generation_count,
                last_command_at=merchant.last_command_at,
                created_at=merchant.created_at,
                updated_at=merchant.updated_at,
            )
        )

    async def save(self, merchant: Merchant) -> None:
        model = await self._session.get(MerchantModel, merchant.id)
        if model is None:
            await self.add(merchant)
            return
        model.telegram_id = merchant.telegram_user.telegram_id
        model.username = merchant.telegram_user.username
        model.first_name = merchant.telegram_user.first_name
        model.last_name = merchant.telegram_user.last_name
        model.vpa = merchant.vpa.value if merchant.vpa else None
        model.tier = merchant.tier.value
        model.generation_count = merchant.generation_count
        model.last_command_at = merchant.last_command_at
        model.created_at = merchant.created_at
        model.updated_at = merchant.updated_at

    async def count_active_between(
        self,
        start,
        end,
        *,
        exclude_telegram_id: int | None = None,
    ) -> int:
        filters = [
            MerchantModel.last_command_at.is_not(None),
            MerchantModel.last_command_at >= start,
            MerchantModel.last_command_at < end,
        ]
        if exclude_telegram_id is not None:
            filters.append(MerchantModel.telegram_id != exclude_telegram_id)
        result = await self._session.scalar(select(func.count(MerchantModel.id)).where(*filters))
        return int(result or 0)

    async def list_telegram_ids(self, *, exclude_telegram_id: int | None = None) -> list[int]:
        query = select(MerchantModel.telegram_id).order_by(MerchantModel.telegram_id.asc())
        if exclude_telegram_id is not None:
            query = query.where(MerchantModel.telegram_id != exclude_telegram_id)
        result = await self._session.scalars(query)
        return [int(telegram_id) for telegram_id in result.all()]


class SQLAlchemyPaymentRequestRepository(PaymentRequestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment_request: PaymentRequest) -> None:
        self._session.add(
            PaymentRequestModel(
                id=payment_request.id,
                merchant_id=payment_request.merchant_id,
                reference=payment_request.reference.value,
                amount=payment_request.amount.amount,
                description=payment_request.description,
                upi_uri=payment_request.upi_uri,
                qr_mime_type=payment_request.qr_mime_type,
                created_at=payment_request.created_at,
            )
        )

    async def count_total(self) -> int:
        result = await self._session.scalar(select(func.count(PaymentRequestModel.id)))
        return int(result or 0)


class SQLAlchemyUpgradeRequestRepository(UpgradeRequestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, upgrade_request: UpgradeRequest) -> None:
        self._session.add(
            UpgradeRequestModel(
                id=upgrade_request.id,
                merchant_id=upgrade_request.merchant_id,
                approval_code=upgrade_request.approval_code.value,
                telegram_chat_id=upgrade_request.telegram_chat_id,
                telegram_message_id=upgrade_request.telegram_message_id,
                telegram_file_id=upgrade_request.telegram_file_id,
                telegram_file_unique_id=upgrade_request.telegram_file_unique_id,
                media_kind=upgrade_request.media_kind,
                status=upgrade_request.status,
                created_at=upgrade_request.created_at,
            )
        )

    async def get_pending_by_approval_code(self, approval_code: str) -> UpgradeRequest | None:
        result = await self._session.scalar(
            select(UpgradeRequestModel).where(
                UpgradeRequestModel.approval_code == approval_code.strip().upper(),
                UpgradeRequestModel.status == "pending",
            )
        )
        if result is None:
            return None
        return _upgrade_request_to_domain(result)

    async def mark_as_approved(self, approval_code: str) -> None:
        await self._session.execute(
            update(UpgradeRequestModel)
            .where(
                UpgradeRequestModel.approval_code == approval_code.strip().upper(),
                UpgradeRequestModel.status == "pending",
            )
            .values(status="approved")
        )

    async def mark_pending_as_approved(self, merchant_id: str) -> None:
        await self._session.execute(
            update(UpgradeRequestModel)
            .where(
                UpgradeRequestModel.merchant_id == UUID(merchant_id),
                UpgradeRequestModel.status == "pending",
            )
            .values(status="approved")
        )
