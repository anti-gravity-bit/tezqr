from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tezqr.application.ports import AbstractUnitOfWork
from tezqr.infrastructure.persistence.repositories import (
    SQLAlchemyMerchantRepository,
    SQLAlchemyPaymentRequestRepository,
    SQLAlchemyUpgradeRequestRepository,
)


class SQLAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.merchants = SQLAlchemyMerchantRepository(self._session)
        self.payment_requests = SQLAlchemyPaymentRequestRepository(self._session)
        self.upgrade_requests = SQLAlchemyUpgradeRequestRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is None:
            return
        if exc is not None:
            await self.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("Unit of work has not been entered.")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            return
        await self._session.rollback()
