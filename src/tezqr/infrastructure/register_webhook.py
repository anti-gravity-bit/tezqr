from __future__ import annotations

import asyncio
import logging

import httpx

from tezqr.infrastructure.telegram.client import TelegramBotClient
from tezqr.shared.config import get_settings

logger = logging.getLogger(__name__)


async def register_webhook_once() -> None:
    settings = get_settings()
    if not settings.auto_register_webhook or not settings.webhook_url:
        return

    http_client = httpx.AsyncClient(timeout=20.0)
    telegram_client = TelegramBotClient(settings=settings, http_client=http_client)
    try:
        await telegram_client.set_webhook(settings.webhook_url)
        logger.info("Telegram webhook registered for %s", settings.webhook_url)
    except Exception:
        logger.warning("Telegram webhook registration failed during prestart.", exc_info=True)
    finally:
        await telegram_client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(register_webhook_once())


if __name__ == "__main__":
    main()
