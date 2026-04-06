from __future__ import annotations

from tezqr.application.commands import (
    ProviderBotCommand,
    ProviderDestinationCommand,
    ProviderPaymentsCommand,
    ProviderRegisterCommand,
    parse_message,
)
from tezqr.application.dto import IncomingMessage
from tezqr.domain.value_objects import TelegramUser


def make_message(text: str) -> IncomingMessage:
    return IncomingMessage(
        message_id=1,
        chat_id=2001,
        from_user=TelegramUser(telegram_id=2001, first_name="Neha", username="neha"),
        text=text,
        attachment=None,
    )


def test_parse_provider_register_command_uses_name_remainder() -> None:
    parsed = parse_message(make_message("/provider_register orbit-pay Orbit Pay"))

    assert parsed == ProviderRegisterCommand(slug="orbit-pay", provider_name="Orbit Pay")


def test_parse_provider_bot_command_accepts_optional_handle() -> None:
    parsed = parse_message(
        make_message("/provider_bot orbit-pay 123456:ABCDEF https://t.me/orbitpaybot")
    )

    assert parsed == ProviderBotCommand(
        provider_slug="orbit-pay",
        bot_token="123456:ABCDEF",
        public_handle="https://t.me/orbitpaybot",
    )


def test_parse_provider_destination_command_uses_payee_name_remainder() -> None:
    parsed = parse_message(
        make_message("/provider_destination orbit-pay MAIN orbit@okaxis Orbit Pay")
    )

    assert parsed == ProviderDestinationCommand(
        provider_slug="orbit-pay",
        code="MAIN",
        vpa="orbit@okaxis",
        payee_name="Orbit Pay",
    )


def test_parse_provider_payments_command_accepts_optional_client_code() -> None:
    parsed = parse_message(make_message("/provider_payments orbit-pay CLI-123"))

    assert parsed == ProviderPaymentsCommand(
        provider_slug="orbit-pay",
        client_code="CLI-123",
    )
