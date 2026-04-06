from __future__ import annotations

from dataclasses import dataclass

from tezqr.presentation.app import create_app
from tezqr.shared.config import Settings


@dataclass
class DummyContainer:
    settings: Settings

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def make_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )


def test_openapi_includes_team_friendly_tags_and_endpoint_summaries() -> None:
    settings = make_settings()
    app = create_app(settings=settings, container=DummyContainer(settings))

    spec = app.openapi()

    assert spec["info"]["title"] == "TezQR"
    assert "merchant bot" in spec["info"]["description"].lower()

    tags = {tag["name"]: tag["description"] for tag in spec["tags"]}
    assert "System" in tags
    assert "Merchant Bot" in tags
    assert "Provider Webhooks" in tags
    assert "Provider API" in tags

    create_provider = spec["paths"]["/api/providers"]["post"]
    assert create_provider["summary"] == "Create Provider"
    assert create_provider["tags"] == ["Provider API"]

    create_payment = spec["paths"]["/api/providers/{provider_slug}/payments"]["post"]
    assert create_payment["summary"] == "Create Payment Request"
    assert create_payment["tags"] == ["Provider API"]


def test_openapi_schema_examples_describe_provider_payment_requests() -> None:
    settings = make_settings()
    app = create_app(settings=settings, container=DummyContainer(settings))

    spec = app.openapi()

    payment_request_schema = spec["components"]["schemas"]["PaymentRequestCreateSchema"]
    assert "provider payment request" in payment_request_schema["description"].lower()
    assert (
        payment_request_schema["properties"]["client_code"]["description"]
        == "Optional client code for a saved provider client."
    )
    assert (
        payment_request_schema["properties"]["walk_in"]["description"]
        == "Flag the request as a walk-in payment with no pre-linked client."
    )
