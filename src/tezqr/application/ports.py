from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime

from tezqr.domain.entities import AdminStats, Merchant, PaymentRequest, UpgradeRequest


class MerchantRepository(ABC):
    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> Merchant | None:
        raise NotImplementedError

    @abstractmethod
    async def add(self, merchant: Merchant) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, merchant: Merchant) -> None:
        raise NotImplementedError

    @abstractmethod
    async def count_active_between(
        self,
        start: datetime,
        end: datetime,
        *,
        exclude_telegram_id: int | None = None,
    ) -> int:
        raise NotImplementedError


class PaymentRequestRepository(ABC):
    @abstractmethod
    async def add(self, payment_request: PaymentRequest) -> None:
        raise NotImplementedError

    @abstractmethod
    async def count_total(self) -> int:
        raise NotImplementedError


class UpgradeRequestRepository(ABC):
    @abstractmethod
    async def add(self, upgrade_request: UpgradeRequest) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_pending_as_approved(self, merchant_id: str) -> None:
        raise NotImplementedError


class TelegramGateway(ABC):
    @abstractmethod
    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        *,
        filename: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_photo_reference(
        self,
        chat_id: int,
        photo_reference: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def copy_message(self, chat_id: int, from_chat_id: int, message_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_webhook(self, url: str) -> None:
        raise NotImplementedError


class QrCodeGenerator(ABC):
    @abstractmethod
    async def generate_png(self, data: str) -> bytes:
        raise NotImplementedError


class AbstractUnitOfWork(ABC):
    merchants: MerchantRepository
    payment_requests: PaymentRequestRepository
    upgrade_requests: UpgradeRequestRepository

    @abstractmethod
    async def __aenter__(self) -> AbstractUnitOfWork:
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(self, exc_type, exc, tb) -> None:
        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]


__all__ = [
    "AbstractUnitOfWork",
    "AdminStats",
    "MerchantRepository",
    "PaymentRequestRepository",
    "QrCodeGenerator",
    "TelegramGateway",
    "UnitOfWorkFactory",
    "UpgradeRequestRepository",
]
