from __future__ import annotations

from datetime import datetime

from tezqr.application.provider_bot_commands import (
    ProviderBotItemCodeCommand,
    ProviderBotLoginCommand,
    ProviderBotMalformedCommand,
    ProviderBotMemberAddCommand,
    ProviderBotReminderCommand,
    ProviderBotShareCommand,
    parse_provider_bot_input,
)


def test_parse_provider_bot_login_command() -> None:
    parsed = parse_provider_bot_input("/login OWNER1 super-secret-key")

    assert parsed == ProviderBotLoginCommand(actor_code="OWNER1", api_key="super-secret-key")


def test_parse_provider_bot_share_defaults_channel_to_none() -> None:
    parsed = parse_provider_bot_input("/share TEZQR-ABCD1234")

    assert parsed == ProviderBotShareCommand(payment_reference="TEZQR-ABCD1234", channel=None)


def test_parse_provider_bot_remindat_command() -> None:
    parsed = parse_provider_bot_input(
        "/remindat TEZQR-ABCD1234 2026-04-08T09:30:00+05:30 Payment is due today."
    )

    assert parsed == ProviderBotReminderCommand(
        payment_reference="TEZQR-ABCD1234",
        scheduled_for=datetime.fromisoformat("2026-04-08T09:30:00+05:30"),
        message="Payment is due today.",
    )


def test_parse_provider_bot_member_add_command_uses_display_name_remainder() -> None:
    parsed = parse_provider_bot_input("/memberadd OPS1 operator Ops Lead")

    assert parsed == ProviderBotMemberAddCommand(
        actor_code="OPS1",
        role="operator",
        display_name="Ops Lead",
    )


def test_parse_provider_bot_note_command_requires_message() -> None:
    parsed = parse_provider_bot_input("/note TEZQR-ABCD1234")

    assert parsed == ProviderBotMalformedCommand(
        name="note",
        usage="/note <payment_reference> <note>",
    )


def test_parse_provider_bot_item_code_accepts_telegram_menu_alias() -> None:
    parsed = parse_provider_bot_input("/item_code CONSULT-01 499")

    assert parsed == ProviderBotItemCodeCommand(item_code="CONSULT-01", amount="499")
