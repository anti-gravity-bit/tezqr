from __future__ import annotations

from tezqr.application.telegram_menu_commands import (
    legacy_admin_commands,
    legacy_public_commands,
    provider_public_commands,
    provider_staff_commands,
    to_telegram_menu_payload,
)
from tezqr.domain.enums import ProviderMemberRole


def test_legacy_admin_commands_extend_public_menu() -> None:
    public = legacy_public_commands()
    admin = legacy_admin_commands()

    assert [command.command for command in public[:3]] == ["start", "setupi", "pay"]
    assert any(command.command == "provider_register" for command in public)
    assert any(command.command == "provider_me" for command in public)
    assert any(command.command == "stats" for command in admin)
    assert any(command.command == "broadcast" for command in admin)
    assert any(command.command == "providers" for command in admin)


def test_provider_staff_commands_are_role_aware() -> None:
    viewer = provider_staff_commands(ProviderMemberRole.VIEWER)
    manager = provider_staff_commands(ProviderMemberRole.MANAGER)

    assert any(command.command == "item_code" for command in viewer)
    assert not any(command.command == "memberadd" for command in viewer)
    assert any(command.command == "runreminders" for command in manager)
    assert any(command.command == "memberadd" for command in manager)


def test_to_telegram_menu_payload_preserves_command_names() -> None:
    payload = to_telegram_menu_payload(provider_public_commands())

    assert payload[0] == {"command": "start", "description": "Show welcome and help"}
    assert any(command["command"] == "item_code" for command in payload)
