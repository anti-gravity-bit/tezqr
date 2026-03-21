from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tezqr.domain.entities import Merchant, PaymentRequest
from tezqr.domain.exceptions import DomainValidationError, FreeQuotaExceededError
from tezqr.domain.value_objects import Money, TelegramUser, UpiVpa


def test_upi_vpa_normalizes_valid_values() -> None:
    vpa = UpiVpa("Merchant.Store@OKAXIS")
    assert vpa.value == "merchant.store@okaxis"


def test_upi_vpa_rejects_invalid_values() -> None:
    with pytest.raises(DomainValidationError):
        UpiVpa("not-a-vpa")


def test_money_quantizes_to_two_decimal_places() -> None:
    amount = Money(Decimal("10.236"))
    assert amount.as_upi_amount() == "10.24"


def test_free_merchant_blocks_generation_after_twenty_requests() -> None:
    merchant = Merchant.onboard(
        TelegramUser(telegram_id=1001, first_name="Asha"),
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )
    merchant.setup_vpa(UpiVpa("asha@okaxis"), now=datetime(2026, 3, 21, tzinfo=UTC))

    for _ in range(20):
        merchant.record_generation(now=datetime(2026, 3, 21, tzinfo=UTC))

    assert merchant.generation_count == 20
    assert merchant.quota_reached is True

    with pytest.raises(FreeQuotaExceededError):
        merchant.record_generation(now=datetime(2026, 3, 21, tzinfo=UTC))


def test_payment_request_embeds_reference_in_upi_uri() -> None:
    merchant = Merchant.onboard(
        TelegramUser(telegram_id=1002, first_name="Rohan"),
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )
    merchant.setup_vpa(UpiVpa("rohan@okaxis"), now=datetime(2026, 3, 21, tzinfo=UTC))
    payment_request = PaymentRequest.create(
        merchant=merchant,
        amount=Money(Decimal("199")),
        description="Monthly subscription",
        now=datetime(2026, 3, 21, tzinfo=UTC),
    )

    assert payment_request.reference.value in payment_request.upi_uri
    assert "pa=rohan%40okaxis" in payment_request.upi_uri
