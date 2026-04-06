from __future__ import annotations

import json

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from tezqr.application.control_plane import ControlPlaneService
from tezqr.infrastructure.qr.generator import QRCodeGeneratorService
from tezqr.presentation.app import create_app
from tezqr.shared.config import Settings


class NoopBotService:
    async def handle_message(self, message) -> None:
        return None


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.calls.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": body.decode(errors="ignore"),
            }
        )
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})


class AppTestContainer:
    def __init__(self, settings: Settings, control_plane_service: ControlPlaneService) -> None:
        self.settings = settings
        self.control_plane_service = control_plane_service
        self.bot_service = NoopBotService()

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        if self.control_plane_service._http_client is not None:  # noqa: SLF001
            await self.control_plane_service._http_client.aclose()  # noqa: SLF001


@pytest.mark.asyncio
async def test_control_plane_routes_cover_provider_payment_and_export_flow(
    db_session_factory,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )
    recording_transport = RecordingTransport()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recording_transport), timeout=20.0
    )
    service = ControlPlaneService(
        session_factory=db_session_factory,
        qr_generator=QRCodeGeneratorService(),
        http_client=http_client,
        settings=settings,
    )
    app = create_app(settings=settings, container=AppTestContainer(settings, service))

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            provider_response = await client.post(
                "/api/providers",
                json={
                    "slug": "acme-pay",
                    "name": "Acme Pay",
                    "owner_actor_code": "OWNER1",
                    "owner_display_name": "Owner One",
                    "logo_text": "AC",
                },
            )
            assert provider_response.status_code == 200
            provider_payload = provider_response.json()
            api_key = provider_payload["api_key"]
            headers = {"x-api-key": api_key, "x-actor-code": "OWNER1"}

            member_response = await client.post(
                "/api/providers/acme-pay/members",
                headers=headers,
                json={
                    "actor_code": "VIEW1",
                    "display_name": "View Only",
                    "role": "viewer",
                },
            )
            assert member_response.status_code == 200
            assert member_response.json()["role"] == "viewer"

            destination_response = await client.post(
                "/api/providers/acme-pay/destinations",
                headers=headers,
                json={
                    "code": "MAIN",
                    "label": "Primary UPI",
                    "vpa": "acme@okaxis",
                    "payee_name": "Acme Pay",
                    "is_default": True,
                },
            )
            assert destination_response.status_code == 200

            bot_response = await client.post(
                "/api/providers/acme-pay/bots",
                headers=headers,
                json={
                    "platform": "telegram",
                    "display_name": "Acme Pay Bot",
                    "bot_token": "provider-telegram-token",
                    "public_handle": "t.me/acmepaybot",
                },
            )
            assert bot_response.status_code == 200

            client_response = await client.post(
                "/api/providers/acme-pay/clients",
                headers=headers,
                json={
                    "full_name": "Riya Sharma",
                    "telegram_id": 551001,
                    "telegram_username": "riya",
                    "whatsapp_number": "+919876543210",
                    "notes": "Priority account",
                },
            )
            assert client_response.status_code == 200
            client_code = client_response.json()["code"]

            template_response = await client.post(
                "/api/providers/acme-pay/templates",
                headers=headers,
                json={
                    "name": "Repair Service",
                    "description": "Repair service charge",
                    "item_code": "REPAIR-01",
                    "default_amount": "350",
                    "destination_code": "MAIN",
                    "pre_generate": True,
                },
            )
            assert template_response.status_code == 200
            template_code = template_response.json()["code"]

            item_code_response = await client.get(
                "/api/providers/acme-pay/item-code/repair-01",
                headers=headers,
            )
            assert item_code_response.status_code == 200
            assert item_code_response.json()["pre_generated"] is True

            payment_response = await client.post(
                "/api/providers/acme-pay/payments",
                headers=headers,
                json={
                    "client_code": client_code,
                    "template_code": template_code,
                    "amount": "499",
                    "custom_message": "Hello {client_name}, please pay for {description}.",
                },
            )
            assert payment_response.status_code == 200
            payment_payload = payment_response.json()
            payment_reference = payment_payload["payment"]["reference"]
            assert payment_payload["quick_share_link"].startswith("upi://pay?")
            assert len(payment_payload["assets"]) == 3

            share_telegram = await client.post(
                f"/api/providers/acme-pay/payments/{payment_reference}/share",
                headers=headers,
                json={"channel": "telegram"},
            )
            assert share_telegram.status_code == 200
            assert share_telegram.json()["delivery_state"] == "sent"

            share_whatsapp = await client.post(
                f"/api/providers/acme-pay/payments/{payment_reference}/share",
                headers=headers,
                json={"channel": "whatsapp"},
            )
            assert share_whatsapp.status_code == 200
            assert share_whatsapp.json()["delivery_state"] == "manual_share"
            assert share_whatsapp.json()["share_url"].startswith("https://wa.me/")

            status_response = await client.post(
                f"/api/providers/acme-pay/payments/{payment_reference}/status",
                headers=headers,
                json={"status": "paid", "notes_summary": "Paid in person"},
            )
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "paid"

            note_response = await client.post(
                f"/api/providers/acme-pay/payments/{payment_reference}/notes",
                headers=headers,
                json={"note": "Manual confirmation logged."},
            )
            assert note_response.status_code == 200

            reminder_response = await client.post(
                "/api/providers/acme-pay/reminders",
                headers=headers,
                json={
                    "reminder_type": "task",
                    "channel": "telegram",
                    "message": "Please complete the pending payment.",
                    "payment_reference": payment_reference,
                    "task_name": "collect-proof",
                    "include_qr": True,
                },
            )
            assert reminder_response.status_code == 200
            assert reminder_response.json()["status"] == "sent"

            history_response = await client.get(
                f"/api/providers/acme-pay/payments/{payment_reference}/history",
                headers=headers,
            )
            assert history_response.status_code == 200
            history_payload = history_response.json()
            assert any(log["event_type"] == "shared" for log in history_payload["logs"])
            assert any(log["event_type"] == "status_changed" for log in history_payload["logs"])
            assert any(log["event_type"] == "note_added" for log in history_payload["logs"])
            assert any(log["event_type"] == "reminder_sent" for log in history_payload["logs"])

            client_payments = await client.get(
                f"/api/providers/acme-pay/clients/{client_code}/payments",
                headers=headers,
            )
            assert client_payments.status_code == 200
            assert len(client_payments.json()["payments"]) == 1

            dashboard_response = await client.get(
                "/api/providers/acme-pay/dashboard",
                headers=headers,
            )
            assert dashboard_response.status_code == 200
            assert dashboard_response.json()["dashboard"]["total_clients"] == 1
            assert dashboard_response.json()["dashboard"]["paid_payments"] == 1

            assets_response = await client.get(
                "/api/providers/acme-pay/qr-assets",
                headers=headers,
            )
            assert assets_response.status_code == 200
            first_asset_code = assets_response.json()[0]["code"]

            download_response = await client.get(
                f"/api/providers/acme-pay/qr-assets/{first_asset_code}/download",
                headers=headers,
            )
            assert download_response.status_code == 200
            assert download_response.headers["content-disposition"].startswith("attachment;")

            export_response = await client.get(
                "/api/providers/acme-pay/exports/payments?format=csv",
                headers=headers,
            )
            assert export_response.status_code == 200
            assert "reference,status,amount" in export_response.text

    assert any(
        "provider-telegram-token/sendPhoto" in call["url"] for call in recording_transport.calls
    )


@pytest.mark.asyncio
async def test_provider_telegram_bot_webhook_onboards_client_and_serves_item_code(
    db_session_factory,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )
    recording_transport = RecordingTransport()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recording_transport), timeout=20.0
    )
    service = ControlPlaneService(
        session_factory=db_session_factory,
        qr_generator=QRCodeGeneratorService(),
        http_client=http_client,
        settings=settings,
    )
    app = create_app(settings=settings, container=AppTestContainer(settings, service))

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            provider_response = await client.post(
                "/api/providers",
                json={
                    "slug": "bravo-pay",
                    "name": "Bravo Pay",
                    "owner_actor_code": "OWNER1",
                    "owner_display_name": "Owner One",
                },
            )
            api_key = provider_response.json()["api_key"]
            headers = {"x-api-key": api_key, "x-actor-code": "OWNER1"}

            await client.post(
                "/api/providers/bravo-pay/destinations",
                headers=headers,
                json={
                    "code": "MAIN",
                    "label": "Primary UPI",
                    "vpa": "bravo@okaxis",
                    "payee_name": "Bravo Pay",
                    "is_default": True,
                },
            )
            bot_response = await client.post(
                "/api/providers/bravo-pay/bots",
                headers=headers,
                json={
                    "platform": "telegram",
                    "display_name": "Bravo Bot",
                    "bot_token": "bravo-telegram-token",
                },
            )
            webhook_secret = bot_response.json()["webhook_secret"]
            await client.post(
                "/api/providers/bravo-pay/templates",
                headers=headers,
                json={
                    "name": "Consulting",
                    "description": "Consulting session",
                    "item_code": "CONSULT-01",
                    "default_amount": "250",
                    "destination_code": "MAIN",
                    "pre_generate": True,
                },
            )

            start_webhook = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 101,
                    "message": {
                        "message_id": 1,
                        "from": {"id": 7001, "first_name": "Aditi", "username": "aditi"},
                        "chat": {"id": 7001},
                        "text": "/start",
                    },
                },
            )
            item_code_webhook = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 102,
                    "message": {
                        "message_id": 2,
                        "from": {"id": 7001, "first_name": "Aditi", "username": "aditi"},
                        "chat": {"id": 7001},
                        "text": "/item-code CONSULT-01",
                    },
                },
            )

            assert start_webhook.status_code == 200
            assert item_code_webhook.status_code == 200

            clients_response = await client.get(
                "/api/providers/bravo-pay/clients",
                headers=headers,
            )
            assert clients_response.status_code == 200
            assert clients_response.json()[0]["onboarding_source"] == "telegram_bot"

    urls = [call["url"] for call in recording_transport.calls]
    assert any("bravo-telegram-token/sendMessage" in url for url in urls)
    assert any("bravo-telegram-token/sendPhoto" in url for url in urls)
    command_calls = [
        json.loads(call["body"])
        for call in recording_transport.calls
        if "bravo-telegram-token/setMyCommands" in call["url"]
    ]
    assert any(call.get("scope") is None for call in command_calls)
    assert any(
        any(command["command"] == "item_code" for command in call["commands"])
        for call in command_calls
    )


@pytest.mark.asyncio
async def test_provider_telegram_bot_rbac_commands_support_staff_workflows(
    db_session_factory,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )
    recording_transport = RecordingTransport()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recording_transport), timeout=20.0
    )
    service = ControlPlaneService(
        session_factory=db_session_factory,
        qr_generator=QRCodeGeneratorService(),
        http_client=http_client,
        settings=settings,
    )
    app = create_app(settings=settings, container=AppTestContainer(settings, service))

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            provider_response = await client.post(
                "/api/providers",
                json={
                    "slug": "orbit-pay",
                    "name": "Orbit Pay",
                    "owner_actor_code": "OWNER1",
                    "owner_display_name": "Owner One",
                },
            )
            api_key = provider_response.json()["api_key"]
            headers = {"x-api-key": api_key, "x-actor-code": "OWNER1"}

            await client.post(
                "/api/providers/orbit-pay/destinations",
                headers=headers,
                json={
                    "code": "MAIN",
                    "label": "Primary UPI",
                    "vpa": "orbit@okaxis",
                    "payee_name": "Orbit Pay",
                    "is_default": True,
                },
            )
            bot_response = await client.post(
                "/api/providers/orbit-pay/bots",
                headers=headers,
                json={
                    "platform": "telegram",
                    "display_name": "Orbit Bot",
                    "bot_token": "orbit-telegram-token",
                    "public_handle": "t.me/orbitpaybot",
                },
            )
            webhook_secret = bot_response.json()["webhook_secret"]

            client_response = await client.post(
                "/api/providers/orbit-pay/clients",
                headers=headers,
                json={
                    "full_name": "Neha Patel",
                    "telegram_id": 8801,
                    "telegram_username": "neha",
                },
            )
            client_code = client_response.json()["code"]

            unlinked_dashboard = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 201,
                    "message": {
                        "message_id": 1,
                        "from": {"id": 9101, "first_name": "Arjun", "username": "arjun"},
                        "chat": {"id": 9101},
                        "text": "/dashboard",
                    },
                },
            )
            owner_login = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 202,
                    "message": {
                        "message_id": 2,
                        "from": {"id": 9101, "first_name": "Arjun", "username": "arjun"},
                        "chat": {"id": 9101},
                        "text": f"/login OWNER1 {api_key}",
                    },
                },
            )
            onboard_link = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 203,
                    "message": {
                        "message_id": 3,
                        "from": {"id": 9101, "first_name": "Arjun", "username": "arjun"},
                        "chat": {"id": 9101},
                        "text": "/onboardlink",
                    },
                },
            )
            member_add = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 204,
                    "message": {
                        "message_id": 4,
                        "from": {"id": 9101, "first_name": "Arjun", "username": "arjun"},
                        "chat": {"id": 9101},
                        "text": "/memberadd OPS1 operator Ops Lead",
                    },
                },
            )
            operator_login = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 205,
                    "message": {
                        "message_id": 5,
                        "from": {"id": 9202, "first_name": "Mira", "username": "mira"},
                        "chat": {"id": 9202},
                        "text": f"/login OPS1 {api_key}",
                    },
                },
            )
            charge_payment = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 206,
                    "message": {
                        "message_id": 6,
                        "from": {"id": 9202, "first_name": "Mira", "username": "mira"},
                        "chat": {"id": 9202},
                        "text": f"/charge {client_code} 499 Quarterly retainer",
                    },
                },
            )

            client_payments = await client.get(
                f"/api/providers/orbit-pay/clients/{client_code}/payments",
                headers=headers,
            )
            payment_reference = client_payments.json()["payments"][0]["reference"]

            send_reminder = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/telegram",
                json={
                    "update_id": 207,
                    "message": {
                        "message_id": 7,
                        "from": {"id": 9202, "first_name": "Mira", "username": "mira"},
                        "chat": {"id": 9202},
                        "text": f"/remind {payment_reference} Please complete the payment today.",
                    },
                },
            )

            assert unlinked_dashboard.status_code == 200
            assert owner_login.status_code == 200
            assert onboard_link.status_code == 200
            assert member_add.status_code == 200
            assert operator_login.status_code == 200
            assert charge_payment.status_code == 200
            assert send_reminder.status_code == 200

    send_message_bodies = [
        call["body"]
        for call in recording_transport.calls
        if "orbit-telegram-token/sendMessage" in call["url"]
    ]
    assert any("Use /login <actor_code> <api_key>" in body for body in send_message_bodies)
    assert any("Role: owner" in body for body in send_message_bodies)
    assert any("https://t.me/orbitpaybot" in body for body in send_message_bodies)
    assert any("Actor: OPS1" in body for body in send_message_bodies)
    assert any("Created payment" in body for body in send_message_bodies)
    assert any("Delivery: sent" in body for body in send_message_bodies)
    assert any(
        "orbit-telegram-token/sendPhoto" in call["url"] for call in recording_transport.calls
    )
    command_calls = [
        json.loads(call["body"])
        for call in recording_transport.calls
        if "orbit-telegram-token/setMyCommands" in call["url"]
    ]
    assert any(call.get("scope") is None for call in command_calls)
    assert any(call.get("scope") == {"type": "chat", "chat_id": 9101} for call in command_calls)
    assert any(call.get("scope") == {"type": "chat", "chat_id": 9202} for call in command_calls)
    assert any(
        any(command["command"] == "memberadd" for command in call["commands"])
        for call in command_calls
        if call.get("scope") == {"type": "chat", "chat_id": 9101}
    )
    assert any(
        any(command["command"] == "runreminders" for command in call["commands"])
        for call in command_calls
        if call.get("scope") == {"type": "chat", "chat_id": 9202}
    )


@pytest.mark.asyncio
async def test_provider_whatsapp_bot_rbac_commands_return_role_aware_replies(
    db_session_factory,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://tezqr:tezqr@localhost:5432/tezqr",
        telegram_bot_token="test-token",
        admin_telegram_id=9999,
        admin_upi_id="owner@upi",
        telegram_webhook_secret="secret",
        auto_register_webhook=False,
    )
    recording_transport = RecordingTransport()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(recording_transport), timeout=20.0
    )
    service = ControlPlaneService(
        session_factory=db_session_factory,
        qr_generator=QRCodeGeneratorService(),
        http_client=http_client,
        settings=settings,
    )
    app = create_app(settings=settings, container=AppTestContainer(settings, service))

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            provider_response = await client.post(
                "/api/providers",
                json={
                    "slug": "nova-pay",
                    "name": "Nova Pay",
                    "owner_actor_code": "OWNER1",
                    "owner_display_name": "Owner One",
                },
            )
            api_key = provider_response.json()["api_key"]
            headers = {"x-api-key": api_key, "x-actor-code": "OWNER1"}

            await client.post(
                "/api/providers/nova-pay/destinations",
                headers=headers,
                json={
                    "code": "MAIN",
                    "label": "Primary UPI",
                    "vpa": "nova@okaxis",
                    "payee_name": "Nova Pay",
                    "is_default": True,
                },
            )
            bot_response = await client.post(
                "/api/providers/nova-pay/bots",
                headers=headers,
                json={
                    "platform": "whatsapp",
                    "display_name": "Nova WA",
                    "public_handle": "+919999000000",
                },
            )
            webhook_secret = bot_response.json()["webhook_secret"]

            login_response = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/whatsapp",
                json={
                    "from_number": "+919999111111",
                    "name": "Owner One",
                    "text": f"/login OWNER1 {api_key}",
                },
            )
            onboard_response = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/whatsapp",
                json={
                    "from_number": "+919999111111",
                    "name": "Owner One",
                    "text": "/onboardlink",
                },
            )
            dashboard_response = await client.post(
                f"/webhooks/provider-bots/{webhook_secret}/whatsapp",
                json={
                    "from_number": "+919999111111",
                    "name": "Owner One",
                    "text": "/dashboard",
                },
            )

            assert login_response.status_code == 200
            assert onboard_response.status_code == 200
            assert dashboard_response.status_code == 200

            assert "Role: owner" in login_response.json()["replies"][0]
            assert "https://wa.me/919999000000" in onboard_response.json()["replies"][0]
            assert "Clients:" in dashboard_response.json()["replies"][0]
