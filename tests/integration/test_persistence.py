from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from tezqr.domain.entities import Merchant, PaymentRequest, UpgradeRequest
from tezqr.domain.value_objects import Money, TelegramUser, UpiVpa
from tezqr.infrastructure.persistence.models import UpgradeRequestModel
from tezqr.infrastructure.persistence.uow import SQLAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_sqlalchemy_uow_persists_merchants_requests_and_stats(db_session_factory) -> None:
    now = datetime(2026, 3, 21, 9, 0, tzinfo=UTC)
    merchant = Merchant.onboard(TelegramUser(telegram_id=3001, first_name="Riya"), now=now)
    merchant.setup_vpa(UpiVpa("riya@okaxis"), now)
    merchant.register_command(now)
    payment_request = PaymentRequest.create(merchant, Money(Decimal("249")), "Consulting", now)
    upgrade_request = UpgradeRequest.create(
        merchant_id=merchant.id,
        telegram_chat_id=merchant.telegram_user.telegram_id,
        telegram_message_id=42,
        telegram_file_id="telegram-file",
        telegram_file_unique_id="unique-file",
        media_kind="photo",
        now=now,
    )

    async with SQLAlchemyUnitOfWork(db_session_factory) as uow:
        await uow.merchants.add(merchant)
        await uow.payment_requests.add(payment_request)
        await uow.upgrade_requests.add(upgrade_request)
        await uow.commit()

    async with SQLAlchemyUnitOfWork(db_session_factory) as uow:
        loaded_merchant = await uow.merchants.get_by_telegram_id(3001)
        assert loaded_merchant is not None
        assert loaded_merchant.vpa is not None
        assert loaded_merchant.vpa.value == "riya@okaxis"
        assert await uow.payment_requests.count_total() == 1
        assert (
            await uow.merchants.count_active_between(
                datetime(2026, 3, 21, 0, 0, tzinfo=UTC),
                datetime(2026, 3, 22, 0, 0, tzinfo=UTC),
            )
            == 1
        )
        await uow.upgrade_requests.mark_pending_as_approved(str(merchant.id))
        await uow.commit()

    async with db_session_factory() as session:
        statuses = (await session.scalars(select(UpgradeRequestModel.status))).all()
        assert statuses == ["approved"]
