from __future__ import annotations

from tezqr.application.control_plane_messages import ProviderMessageComposer
from tezqr.domain.enums import BotPlatform, ProviderMemberRole


def test_build_bot_welcome_message_includes_staff_login_hint() -> None:
    composer = ProviderMessageComposer()

    message = composer.build_bot_welcome_message("Orbit Pay", {"logo_text": "OP"})

    assert "/login <actor_code> <api_key>" in message
    assert "Provider staff can link this chat" in message


def test_build_staff_help_is_role_aware() -> None:
    composer = ProviderMessageComposer()

    viewer_help = composer.build_staff_help("Orbit Pay", ProviderMemberRole.VIEWER)
    manager_help = composer.build_staff_help("Orbit Pay", ProviderMemberRole.MANAGER)

    assert "/dashboard" in viewer_help
    assert "/memberadd" not in viewer_help
    assert "/memberadd" in manager_help
    assert "/runreminders" in manager_help


def test_build_onboarding_link_message_uses_platform_label() -> None:
    composer = ProviderMessageComposer()

    message = composer.build_onboarding_link_message(
        "Orbit Pay",
        BotPlatform.TELEGRAM,
        "https://t.me/orbitpaybot",
    )

    assert "telegram entry point" in message
    assert "https://t.me/orbitpaybot" in message
