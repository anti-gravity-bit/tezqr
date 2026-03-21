from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from tezqr.application.commands import (
    EmptyInput,
    MalformedCommand,
    PayCommand,
    ScreenshotSubmission,
    SetupiCommand,
    StartCommand,
    StatsCommand,
    UnsupportedCommand,
    UpgradeCommand,
    parse_message,
)
from tezqr.application.dto import IncomingMessage
from tezqr.application.ports import QrCodeGenerator, TelegramGateway, UnitOfWorkFactory
from tezqr.application.replies import (
    admin_only_message,
    admin_upgrade_request_message,
    admin_upgrade_success_message,
    already_premium_message,
    free_plan_still_available_message,
    help_message,
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
from tezqr.domain.exceptions import DomainValidationError, MerchantSetupRequiredError
from tezqr.domain.value_objects import Money, UpiVpa
from tezqr.shared.config import Settings
from tezqr.shared.time import current_local_day_bounds, utc_now


class BotService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        telegram_gateway: TelegramGateway,
        qr_generator: QrCodeGenerator,
        settings: Settings,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._telegram_gateway = telegram_gateway
        self._qr_generator = qr_generator
        self._settings = settings
        self._now_provider = now_provider

    async def handle_message(self, message: IncomingMessage) -> None:
        parsed = parse_message(message)

        if isinstance(parsed, EmptyInput):
            return
        if isinstance(parsed, UnsupportedCommand):
            await self._telegram_gateway.send_text(
                message.chat_id,
                help_message(),
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
        if isinstance(parsed, UpgradeCommand):
            await self._handle_upgrade(message, parsed)
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
            screenshot_received_message(),
            reply_to_message_id=message.message_id,
        )
        await self._telegram_gateway.copy_message(
            self._settings.admin_telegram_id,
            message.chat_id,
            message.message_id,
        )
        await self._telegram_gateway.send_text(
            self._settings.admin_telegram_id,
            admin_upgrade_request_message(message.from_user),
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
            merchant_upgrade_confirmation_message(),
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
