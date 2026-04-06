"""Legacy Telegram merchant bot application service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from tezqr.application.commands import (
    ApproveCommand,
    BroadcastCommand,
    EmptyInput,
    MalformedCommand,
    PayCommand,
    PlainTextMessage,
    ProviderBotCommand,
    ProviderBotsCommand,
    ProviderClientsCommand,
    ProviderDestinationCommand,
    ProviderMeCommand,
    ProviderMembersCommand,
    ProviderOverviewCommand,
    ProviderPaymentsCommand,
    ProviderRegisterCommand,
    ProvidersCommand,
    ScreenshotSubmission,
    SetupiCommand,
    StartCommand,
    StatsCommand,
    UnsupportedCommand,
    UpgradeCommand,
    parse_message,
)
from tezqr.application.control_plane import ControlPlaneService
from tezqr.application.dto import IncomingMessage
from tezqr.application.ports import QrCodeGenerator, TelegramGateway, UnitOfWorkFactory
from tezqr.application.replies import (
    admin_approval_success_message,
    admin_only_message,
    admin_upgrade_request_message,
    admin_upgrade_success_message,
    already_premium_message,
    approve_request_not_found_message,
    broadcast_delivery_message,
    broadcast_summary_message,
    fallback_menu_message,
    free_plan_still_available_message,
    invalid_amount_message,
    invalid_vpa_message,
    malformed_command_message,
    merchant_not_found_message,
    merchant_upgrade_confirmation_message,
    missing_description_message,
    payment_qr_caption,
    paywall_message,
    screenshot_received_message,
    setup_required_message,
    setup_success_message,
    start_required_message,
    stats_message,
    welcome_message,
)
from tezqr.domain.entities import (
    PREMIUM_GENERATION_LIMIT,
    AdminStats,
    Merchant,
    PaymentRequest,
    UpgradeRequest,
)
from tezqr.domain.enums import MerchantTier
from tezqr.domain.exceptions import (
    AuthorizationError,
    DomainValidationError,
    MerchantSetupRequiredError,
)
from tezqr.domain.value_objects import Money, UpiVpa
from tezqr.shared.config import Settings
from tezqr.shared.time import current_local_day_bounds, utc_now


class BotService:
    """Handle the original TezQR merchant bot workflow.

    This service preserves the simpler merchant-facing product surface while the
    provider control plane grows alongside it. The bot logic still follows the same
    application-service role: parse transport DTOs, load aggregates through the unit
    of work, apply domain rules, and delegate outbound delivery to ports.
    """

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        telegram_gateway: TelegramGateway,
        qr_generator: QrCodeGenerator,
        settings: Settings,
        control_plane_service: ControlPlaneService | None = None,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._telegram_gateway = telegram_gateway
        self._qr_generator = qr_generator
        self._settings = settings
        self._control_plane_service = control_plane_service
        self._now_provider = now_provider

    async def handle_message(self, message: IncomingMessage) -> None:
        parsed = parse_message(message)

        if isinstance(parsed, EmptyInput):
            return
        if isinstance(parsed, PlainTextMessage):
            await self._telegram_gateway.send_text(
                message.chat_id,
                fallback_menu_message(is_admin=self._is_admin(message.from_user.telegram_id)),
                reply_to_message_id=message.message_id,
            )
            return
        if isinstance(parsed, UnsupportedCommand):
            await self._telegram_gateway.send_text(
                message.chat_id,
                fallback_menu_message(is_admin=self._is_admin(message.from_user.telegram_id)),
                reply_to_message_id=message.message_id,
            )
            return
        if isinstance(parsed, MalformedCommand):
            await self._record_existing_merchant_command(message)
            await self._telegram_gateway.send_text(
                message.chat_id,
                malformed_command_message(parsed.name, parsed.usage),
                reply_to_message_id=message.message_id,
            )
            return
        if isinstance(parsed, ScreenshotSubmission):
            await self._handle_screenshot_submission(message)
            return
        if isinstance(parsed, StartCommand):
            await self._handle_start(message)
            return
        if isinstance(parsed, SetupiCommand):
            await self._handle_setupi(message, parsed)
            return
        if isinstance(parsed, PayCommand):
            await self._handle_pay(message, parsed)
            return
        if isinstance(parsed, StatsCommand):
            await self._handle_stats(message)
            return
        if isinstance(parsed, ApproveCommand):
            await self._handle_approve(message, parsed)
            return
        if isinstance(parsed, BroadcastCommand):
            await self._handle_broadcast(message, parsed)
            return
        if isinstance(parsed, UpgradeCommand):
            await self._handle_upgrade(message, parsed)
            return
        if isinstance(parsed, ProviderRegisterCommand):
            await self._handle_provider_register(message, parsed)
            return
        if isinstance(parsed, ProviderBotCommand):
            await self._handle_provider_bot(message, parsed)
            return
        if isinstance(parsed, ProviderDestinationCommand):
            await self._handle_provider_destination(message, parsed)
            return
        if isinstance(parsed, ProviderMeCommand):
            await self._handle_provider_me(message)
            return
        if isinstance(parsed, ProvidersCommand):
            await self._handle_admin_providers(message)
            return
        if isinstance(parsed, ProviderOverviewCommand):
            await self._handle_admin_provider_overview(message, parsed)
            return
        if isinstance(parsed, ProviderMembersCommand):
            await self._handle_admin_provider_members(message, parsed)
            return
        if isinstance(parsed, ProviderBotsCommand):
            await self._handle_admin_provider_bots(message, parsed)
            return
        if isinstance(parsed, ProviderClientsCommand):
            await self._handle_admin_provider_clients(message, parsed)
            return
        if isinstance(parsed, ProviderPaymentsCommand):
            await self._handle_admin_provider_payments(message, parsed)
            return

    async def _handle_start(self, message: IncomingMessage) -> None:
        now = self._now_provider()
        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(message.from_user.telegram_id)
            if merchant is None:
                merchant = Merchant.onboard(message.from_user, now)
                merchant.register_command(now)
                await uow.merchants.add(merchant)
            else:
                merchant.refresh_profile(message.from_user, now)
                merchant.register_command(now)
                await uow.merchants.save(merchant)
            await uow.commit()

        await self._telegram_gateway.send_text(
            message.chat_id,
            welcome_message(),
            reply_to_message_id=message.message_id,
        )

    async def _handle_setupi(self, message: IncomingMessage, command: SetupiCommand) -> None:
        now = self._now_provider()
        try:
            vpa = UpiVpa(command.vpa)
        except DomainValidationError:
            await self._telegram_gateway.send_text(
                message.chat_id,
                invalid_vpa_message(),
                reply_to_message_id=message.message_id,
            )
            return

        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(message.from_user.telegram_id)
            if merchant is None:
                merchant = Merchant.onboard(message.from_user, now)
                merchant.register_command(now)
                merchant.setup_vpa(vpa, now)
                await uow.merchants.add(merchant)
            else:
                merchant.refresh_profile(message.from_user, now)
                merchant.register_command(now)
                merchant.setup_vpa(vpa, now)
                await uow.merchants.save(merchant)
            await uow.commit()

        await self._telegram_gateway.send_text(
            message.chat_id,
            setup_success_message(vpa.value),
            reply_to_message_id=message.message_id,
        )

    async def _handle_pay(self, message: IncomingMessage, command: PayCommand) -> None:
        now = self._now_provider()
        try:
            amount = Money(Decimal(command.amount))
        except (InvalidOperation, DomainValidationError):
            await self._telegram_gateway.send_text(
                message.chat_id,
                invalid_amount_message(),
                reply_to_message_id=message.message_id,
            )
            return

        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(message.from_user.telegram_id)
            if merchant is None:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    start_required_message(),
                    reply_to_message_id=message.message_id,
                )
                return

            merchant.refresh_profile(message.from_user, now)
            merchant.register_command(now)

            if merchant.quota_reached:
                await uow.merchants.save(merchant)
                await uow.commit()
                await self._send_paywall_response(message, merchant.tier)
                return

            try:
                payment_request = PaymentRequest.create(merchant, amount, command.description, now)
                merchant.record_generation(now)
            except MerchantSetupRequiredError:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    setup_required_message(),
                    reply_to_message_id=message.message_id,
                )
                return
            except DomainValidationError:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    missing_description_message(),
                    reply_to_message_id=message.message_id,
                )
                return

            await uow.payment_requests.add(payment_request)
            await uow.merchants.save(merchant)
            await uow.commit()

        qr_bytes = await self._qr_generator.generate_png(payment_request.upi_uri)
        await self._telegram_gateway.send_photo(
            message.chat_id,
            qr_bytes,
            filename=f"{payment_request.reference.value}.png",
            caption=payment_qr_caption(payment_request, self._settings.bot_public_link),
            reply_to_message_id=message.message_id,
        )

    async def _handle_screenshot_submission(self, message: IncomingMessage) -> None:
        now = self._now_provider()
        attachment = message.attachment
        if attachment is None:
            return

        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(message.from_user.telegram_id)
            if merchant is None:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    start_required_message(),
                    reply_to_message_id=message.message_id,
                )
                return

            merchant.refresh_profile(message.from_user, now)
            await uow.merchants.save(merchant)

            if merchant.tier == MerchantTier.PREMIUM and not merchant.quota_reached:
                await uow.commit()
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    already_premium_message(),
                    reply_to_message_id=message.message_id,
                )
                return

            if merchant.tier == MerchantTier.FREE and not merchant.quota_reached:
                await uow.commit()
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    free_plan_still_available_message(),
                    reply_to_message_id=message.message_id,
                )
                return

            upgrade_request = UpgradeRequest.create(
                merchant_id=merchant.id,
                telegram_chat_id=message.chat_id,
                telegram_message_id=message.message_id,
                telegram_file_id=attachment.file_id,
                telegram_file_unique_id=attachment.file_unique_id,
                media_kind=attachment.kind,
                now=now,
            )
            await uow.upgrade_requests.add(upgrade_request)
            await uow.commit()

        await self._telegram_gateway.send_text(
            message.chat_id,
            screenshot_received_message(upgrade_request.approval_code.value),
            reply_to_message_id=message.message_id,
        )
        await self._telegram_gateway.copy_message(
            self._settings.admin_telegram_id,
            message.chat_id,
            message.message_id,
        )
        await self._telegram_gateway.send_text(
            self._settings.admin_telegram_id,
            admin_upgrade_request_message(message.from_user, upgrade_request.approval_code.value),
        )

    async def _handle_stats(self, message: IncomingMessage) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        now = self._now_provider()
        start, end = current_local_day_bounds(now, self._settings.tz)
        async with self._uow_factory() as uow:
            stats = AdminStats(
                daily_active_users=await uow.merchants.count_active_between(
                    start,
                    end,
                    exclude_telegram_id=self._settings.admin_telegram_id,
                ),
                total_generations=await uow.payment_requests.count_total(),
            )
            await uow.commit()

        local_date = now.astimezone(ZoneInfo(self._settings.tz)).date().isoformat()
        await self._telegram_gateway.send_text(
            message.chat_id,
            stats_message(local_date, stats),
            reply_to_message_id=message.message_id,
        )

    async def _handle_upgrade(self, message: IncomingMessage, command: UpgradeCommand) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        now = self._now_provider()

        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(command.target_telegram_id)
            if merchant is None:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    merchant_not_found_message(command.target_telegram_id),
                    reply_to_message_id=message.message_id,
                )
                return

            merchant.upgrade(now)
            await uow.merchants.save(merchant)
            await uow.upgrade_requests.mark_pending_as_approved(str(merchant.id))
            await uow.commit()

        await self._telegram_gateway.send_text(
            message.chat_id,
            admin_upgrade_success_message(command.target_telegram_id),
            reply_to_message_id=message.message_id,
        )
        await self._telegram_gateway.send_text(
            command.target_telegram_id,
            merchant_upgrade_confirmation_message("MANUAL-UPGRADE"),
        )

    async def _handle_approve(self, message: IncomingMessage, command: ApproveCommand) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        now = self._now_provider()

        async with self._uow_factory() as uow:
            upgrade_request = await uow.upgrade_requests.get_pending_by_approval_code(
                command.approval_code
            )
            if upgrade_request is None:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    approve_request_not_found_message(command.approval_code),
                    reply_to_message_id=message.message_id,
                )
                return

            merchant = await uow.merchants.get_by_id(upgrade_request.merchant_id)
            if merchant is None:
                await self._telegram_gateway.send_text(
                    message.chat_id,
                    approve_request_not_found_message(command.approval_code),
                    reply_to_message_id=message.message_id,
                )
                return

            merchant.upgrade(now)
            await uow.merchants.save(merchant)
            await uow.upgrade_requests.mark_as_approved(upgrade_request.approval_code.value)
            await uow.commit()

        await self._telegram_gateway.send_text(
            message.chat_id,
            admin_approval_success_message(
                upgrade_request.approval_code.value,
                merchant.telegram_user.telegram_id,
            ),
            reply_to_message_id=message.message_id,
        )
        await self._telegram_gateway.send_text(
            merchant.telegram_user.telegram_id,
            merchant_upgrade_confirmation_message(upgrade_request.approval_code.value),
        )

    async def _handle_broadcast(self, message: IncomingMessage, command: BroadcastCommand) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return

        async with self._uow_factory() as uow:
            recipient_ids = await uow.merchants.list_telegram_ids(
                exclude_telegram_id=self._settings.admin_telegram_id
            )
            await uow.commit()

        delivered = 0
        failed = 0
        broadcast_text = broadcast_delivery_message(command.message, self._settings.bot_public_link)
        for recipient_id in recipient_ids:
            try:
                await self._telegram_gateway.send_text(recipient_id, broadcast_text)
                delivered += 1
            except Exception:
                failed += 1

        await self._telegram_gateway.send_text(
            message.chat_id,
            broadcast_summary_message(
                recipients=len(recipient_ids),
                delivered=delivered,
                failed=failed,
            ),
            reply_to_message_id=message.message_id,
        )

    async def _handle_provider_register(
        self,
        message: IncomingMessage,
        command: ProviderRegisterCommand,
    ) -> None:
        control_plane = self._require_control_plane_service()
        try:
            payload = await control_plane.create_provider_from_telegram(
                slug=command.slug,
                name=command.provider_name,
                owner_telegram_id=message.from_user.telegram_id,
                owner_display_name=message.from_user.display_name,
                owner_telegram_username=message.from_user.username,
            )
        except (AuthorizationError, DomainValidationError) as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return

        text = (
            "Provider workspace created\n\n"
            f"Name: {payload['name']}\n"
            f"Slug: {payload['slug']}\n"
            f"Owner actor: {payload['owner_actor_code']}\n"
            f"API key: {payload['api_key']}\n\n"
            "Next steps:\n"
            f"1. /provider_bot {payload['slug']} <bot_token> [public_handle]\n"
            f"2. /provider_destination {payload['slug']} MAIN <vpa> <payee_name>\n"
            "3. Open your provider bot and send /start"
        )
        await self._telegram_gateway.send_text(
            message.chat_id,
            text,
            reply_to_message_id=message.message_id,
        )

    async def _handle_provider_bot(
        self,
        message: IncomingMessage,
        command: ProviderBotCommand,
    ) -> None:
        control_plane = self._require_control_plane_service()
        try:
            payload = await control_plane.create_bot_instance_from_telegram_owner(
                provider_slug=command.provider_slug,
                owner_telegram_id=message.from_user.telegram_id,
                bot_token=command.bot_token,
                public_handle=command.public_handle,
            )
        except (AuthorizationError, DomainValidationError) as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return

        lines = [
            "Provider Telegram bot created",
            "",
            f"Provider slug: {command.provider_slug}",
            f"Bot code: {payload['code']}",
        ]
        if payload.get("public_handle"):
            lines.append(f"Public handle: {payload['public_handle']}")
        if payload.get("webhook_url"):
            lines.append(f"Webhook URL: {payload['webhook_url']}")
        if payload.get("webhook_registration") == "configured":
            lines.append("Webhook: configured")
        elif payload.get("webhook_registration") == "manual_required":
            lines.append("Webhook: manual setup required")
        lines.extend(
            [
                "",
                "Your Telegram account is already linked as the provider owner.",
                "Open the provider bot and send /start to see the role-based menu.",
            ]
        )
        await self._telegram_gateway.send_text(
            message.chat_id,
            "\n".join(lines),
            reply_to_message_id=message.message_id,
        )

    async def _handle_provider_destination(
        self,
        message: IncomingMessage,
        command: ProviderDestinationCommand,
    ) -> None:
        control_plane = self._require_control_plane_service()
        try:
            payload = await control_plane.create_payment_destination_from_telegram_member(
                provider_slug=command.provider_slug,
                telegram_id=message.from_user.telegram_id,
                code=command.code,
                vpa=command.vpa,
                payee_name=command.payee_name,
                is_default=True,
            )
        except (AuthorizationError, DomainValidationError) as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return

        await self._telegram_gateway.send_text(
            message.chat_id,
            (
                "Provider destination saved\n\n"
                f"Code: {payload['code']}\n"
                f"UPI ID: {payload['vpa']}\n"
                f"Payee name: {payload['payee_name']}\n"
                f"Default: {'yes' if payload['is_default'] else 'no'}"
            ),
            reply_to_message_id=message.message_id,
        )

    async def _handle_provider_me(self, message: IncomingMessage) -> None:
        control_plane = self._require_control_plane_service()
        payloads = await control_plane.list_member_workspaces_by_telegram(
            message.from_user.telegram_id
        )
        if not payloads:
            await self._telegram_gateway.send_text(
                message.chat_id,
                (
                    "No provider workspaces are linked to your Telegram account yet.\n\n"
                    "Use /provider_register <slug> <provider_name> to create one."
                ),
                reply_to_message_id=message.message_id,
            )
            return

        sections = ["Your provider workspaces"]
        for payload in payloads:
            provider = payload["provider"]
            member = payload["member"]
            destination = payload["default_destination"]
            section = [
                "",
                f"{provider['name']} ({provider['slug']})",
                f"Role: {member['role']}",
                f"Actor: {member['actor_code']}",
                f"API key: {payload['api_key']}",
                f"Telegram bots: {payload['bot_count']}",
                f"Clients: {payload['client_count']}",
            ]
            if destination is not None:
                section.append(
                    f"Default destination: {destination['code']} -> {destination['vpa']}"
                )
            else:
                section.append(
                    "Default destination: missing\n"
                    f"Use /provider_destination {provider['slug']} MAIN <vpa> "
                    "<payee_name>"
                )
            sections.extend(section)

        await self._telegram_gateway.send_text(
            message.chat_id,
            "\n".join(sections),
            reply_to_message_id=message.message_id,
        )

    async def _handle_admin_providers(self, message: IncomingMessage) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        control_plane = self._require_control_plane_service()
        rows = await control_plane.list_all_providers_for_admin()
        if not rows:
            text = "No provider workspaces have been created yet."
        else:
            lines = ["Provider workspaces"]
            for row in rows:
                provider = row["provider"]
                lines.extend(
                    [
                        "",
                        f"{provider['name']} ({provider['slug']})",
                        f"Members: {row['member_count']}",
                        f"Bots: {row['bot_count']}",
                        f"Clients: {row['client_count']}",
                        "Pending/Paid/Overdue: "
                        f"{row['pending_payments']}/"
                        f"{row['paid_payments']}/"
                        f"{row['overdue_payments']}",
                        f"Scheduled reminders: {row['scheduled_reminders']}",
                    ]
                )
            text = "\n".join(lines)
        await self._telegram_gateway.send_text(
            message.chat_id,
            text,
            reply_to_message_id=message.message_id,
        )

    async def _handle_admin_provider_overview(
        self,
        message: IncomingMessage,
        command: ProviderOverviewCommand,
    ) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        control_plane = self._require_control_plane_service()
        try:
            payload = await control_plane.get_provider_overview_for_admin(command.provider_slug)
        except DomainValidationError as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return
        provider = payload["provider"]
        lines = [
            "Provider overview",
            "",
            f"Name: {provider['name']}",
            f"Slug: {provider['slug']}",
            f"API key: {provider['api_key']}",
            f"Members: {payload['member_count']}",
            f"Bots: {payload['bot_count']}",
            f"Clients: {payload['client_count']}",
            f"Templates: {payload['template_count']}",
            "Pending/Paid/Overdue: "
            f"{payload['pending_payments']}/"
            f"{payload['paid_payments']}/"
            f"{payload['overdue_payments']}",
            f"Scheduled reminders: {payload['scheduled_reminders']}",
        ]
        if payload["default_destination"] is not None:
            lines.append(
                "Default destination: "
                f"{payload['default_destination']['code']} -> "
                f"{payload['default_destination']['vpa']}"
            )
        if payload["members"]:
            lines.append(
                "Members: "
                + ", ".join(row["actor_code"] for row in payload["members"][:5])
            )
        if payload["bots"]:
            lines.append("Bots: " + ", ".join(row["code"] for row in payload["bots"][:5]))
        if payload["recent_payments"]:
            recent = ", ".join(
                row["payment"]["reference"] for row in payload["recent_payments"][:5]
            )
            lines.append(f"Recent payments: {recent}")
        await self._telegram_gateway.send_text(
            message.chat_id,
            "\n".join(lines),
            reply_to_message_id=message.message_id,
        )

    async def _handle_admin_provider_members(
        self,
        message: IncomingMessage,
        command: ProviderMembersCommand,
    ) -> None:
        await self._send_admin_provider_listing(
            message,
            provider_slug=command.provider_slug,
            title="Provider members",
            loader=lambda: self._require_control_plane_service().list_provider_members_for_admin(
                command.provider_slug
            ),
            formatter=lambda row: (
                f"{row['actor_code']} ({row['role']}) - {row['display_name']}"
                + (f" - TG {row['telegram_id']}" if row["telegram_id"] else "")
            ),
        )

    async def _handle_admin_provider_bots(
        self,
        message: IncomingMessage,
        command: ProviderBotsCommand,
    ) -> None:
        await self._send_admin_provider_listing(
            message,
            provider_slug=command.provider_slug,
            title="Provider bots",
            loader=lambda: self._require_control_plane_service().list_provider_bots_for_admin(
                command.provider_slug
            ),
            formatter=lambda row: (
                f"{row['code']} ({row['platform']}) - {row['display_name']}"
                + (f" - {row['public_handle']}" if row["public_handle"] else "")
            ),
        )

    async def _handle_admin_provider_clients(
        self,
        message: IncomingMessage,
        command: ProviderClientsCommand,
    ) -> None:
        await self._send_admin_provider_listing(
            message,
            provider_slug=command.provider_slug,
            title="Provider clients",
            loader=lambda: self._require_control_plane_service().list_provider_clients_for_admin(
                command.provider_slug
            ),
            formatter=lambda row: (
                f"{row['code']} - {row['full_name']}"
                + (f" - @{row['telegram_username']}" if row["telegram_username"] else "")
                + (
                    f" - {row['whatsapp_number']}"
                    if row["whatsapp_number"]
                    else ""
                )
            ),
        )

    async def _handle_admin_provider_payments(
        self,
        message: IncomingMessage,
        command: ProviderPaymentsCommand,
    ) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        control_plane = self._require_control_plane_service()
        try:
            rows = await control_plane.list_provider_payments_for_admin(
                command.provider_slug,
                client_code=command.client_code,
            )
        except DomainValidationError as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return
        if not rows:
            text = f"No payments were found for provider {command.provider_slug}."
        else:
            lines = [f"Provider payments for {command.provider_slug}"]
            for row in rows[:20]:
                payment = row["payment"]
                lines.extend(
                    [
                        "",
                        f"{payment['reference']} - Rs {payment['amount']} - {payment['status']}",
                        f"Description: {payment['description']}",
                        f"Client: {row['client_name'] or 'walk-in'}",
                    ]
                )
            if len(rows) > 20:
                lines.append(f"\n... and {len(rows) - 20} more")
            text = "\n".join(lines)
        await self._telegram_gateway.send_text(
            message.chat_id,
            text,
            reply_to_message_id=message.message_id,
        )

    async def _send_admin_provider_listing(
        self,
        message: IncomingMessage,
        *,
        provider_slug: str,
        title: str,
        loader,
        formatter,
    ) -> None:
        if not self._is_admin(message.from_user.telegram_id):
            await self._telegram_gateway.send_text(
                message.chat_id,
                admin_only_message(),
                reply_to_message_id=message.message_id,
            )
            return
        try:
            rows = await loader()
        except DomainValidationError as exc:
            await self._telegram_gateway.send_text(
                message.chat_id,
                str(exc),
                reply_to_message_id=message.message_id,
            )
            return
        if not rows:
            text = f"No rows were found for provider {provider_slug}."
        else:
            lines = [f"{title} for {provider_slug}"]
            for row in rows[:20]:
                lines.append(f"\n{formatter(row)}")
            if len(rows) > 20:
                lines.append(f"\n... and {len(rows) - 20} more")
            text = "\n".join(lines)
        await self._telegram_gateway.send_text(
            message.chat_id,
            text,
            reply_to_message_id=message.message_id,
        )

    async def _record_existing_merchant_command(self, message: IncomingMessage) -> None:
        now = self._now_provider()
        async with self._uow_factory() as uow:
            merchant = await uow.merchants.get_by_telegram_id(message.from_user.telegram_id)
            if merchant is None:
                return
            merchant.refresh_profile(message.from_user, now)
            merchant.register_command(now)
            await uow.merchants.save(merchant)
            await uow.commit()

    def _is_admin(self, telegram_id: int) -> bool:
        return telegram_id == self._settings.admin_telegram_id

    def _require_control_plane_service(self) -> ControlPlaneService:
        if self._control_plane_service is None:
            raise DomainValidationError("Provider tools are unavailable right now.")
        return self._control_plane_service

    async def _send_paywall_response(
        self,
        message: IncomingMessage,
        tier: MerchantTier,
    ) -> None:
        subscription_payment_link = self._resolve_subscription_payment_link()
        message_text = paywall_message(self._settings, tier, subscription_payment_link)
        if self._settings.subscription_payment_qr:
            await self._telegram_gateway.send_photo_reference(
                message.chat_id,
                self._settings.subscription_payment_qr,
                caption=message_text,
                reply_to_message_id=message.message_id,
            )
            return
        if subscription_payment_link:
            qr_bytes = await self._qr_generator.generate_png(subscription_payment_link)
            await self._telegram_gateway.send_photo(
                message.chat_id,
                qr_bytes,
                filename="tezqr-premium-pack.png",
                caption=message_text,
                reply_to_message_id=message.message_id,
            )
            return
        await self._telegram_gateway.send_text(
            message.chat_id,
            message_text,
            reply_to_message_id=message.message_id,
        )

    def _resolve_subscription_payment_link(self) -> str | None:
        if self._settings.subscription_payment_link:
            return self._settings.subscription_payment_link
        try:
            upi_vpa = UpiVpa(self._settings.effective_subscription_upi_id)
            amount = Money(Decimal(self._settings.subscription_price_inr))
        except (DomainValidationError, InvalidOperation):
            return None
        params = {
            "pa": upi_vpa.value,
            "pn": "TezQR",
            "am": amount.as_upi_amount(),
            "cu": "INR",
            "tn": f"TezQR Premium {PREMIUM_GENERATION_LIMIT} QR pack",
        }
        return f"upi://pay?{urlencode(params, quote_via=quote)}"
