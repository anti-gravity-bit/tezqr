from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar
from urllib.parse import quote, urlencode
from uuid import uuid4

from tezqr.domain.exceptions import DomainValidationError

_TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class UpiVpa:
    value: str

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}$")

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or not self._PATTERN.fullmatch(normalized):
            raise DomainValidationError("A valid UPI VPA is required.")
        object.__setattr__(self, "value", normalized.lower())


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal

    def __post_init__(self) -> None:
        quantized = Decimal(str(self.amount)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        if quantized <= 0:
            raise DomainValidationError("Amount must be greater than zero.")
        object.__setattr__(self, "amount", quantized)

    def as_upi_amount(self) -> str:
        return f"{self.amount:.2f}"


@dataclass(frozen=True, slots=True)
class TelegramUser:
    telegram_id: int
    first_name: str
    username: str | None = None
    last_name: str | None = None

    def __post_init__(self) -> None:
        if self.telegram_id <= 0:
            raise DomainValidationError("Telegram user id must be positive.")
        if not self.first_name.strip():
            raise DomainValidationError("Telegram first name is required.")

    @property
    def display_name(self) -> str:
        parts = [self.first_name.strip()]
        if self.last_name:
            parts.append(self.last_name.strip())
        return " ".join(part for part in parts if part).strip()


@dataclass(frozen=True, slots=True)
class PaymentReference:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not normalized.startswith("TEZQR-") or len(normalized) < 12:
            raise DomainValidationError("Payment reference must start with TEZQR-.")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def new(cls) -> PaymentReference:
        return cls(f"TEZQR-{uuid4().hex[:12].upper()}")


@dataclass(frozen=True, slots=True)
class UpiPaymentLink:
    vpa: UpiVpa
    amount: Money
    description: str
    reference: PaymentReference
    payee_name: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise DomainValidationError("Payment description is required.")
        if not self.payee_name.strip():
            raise DomainValidationError("Payee name is required.")

    @property
    def uri(self) -> str:
        params = {
            "pa": self.vpa.value,
            "pn": self.payee_name.strip(),
            "am": self.amount.as_upi_amount(),
            "cu": "INR",
            "tn": self.description.strip(),
            "tr": self.reference.value,
        }
        return f"upi://pay?{urlencode(params, quote_via=quote)}"
