from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit, urlunsplit

import httpx

from tezqr.infrastructure.telegram.client import TelegramBotClient
from tezqr.shared.config import get_settings

logger = logging.getLogger(__name__)


def _redact_webhook_url(url: str) -> str:
    parts = urlsplit(url)
    path_bits = parts.path.rstrip("/").split("/")
    if path_bits:
        path_bits[-1] = "<redacted>"
    safe_path = "/".join(path_bits)
    return urlunsplit((parts.scheme, parts.netloc, safe_path, "", ""))


async def register_webhook_once() -> None:
    settings = get_settings()
    if not settings.auto_register_webhook or not settings.webhook_url:
        return

    http_client = httpx.AsyncClient(timeout=20.0)
    telegram_client = TelegramBotClient(settings=settings, http_client=http_client)
    try:
        await telegram_client.set_webhook(settings.webhook_url)
        logger.info("Telegram webhook registered for %s", _redact_webhook_url(settings.webhook_url))
    except Exception:
        logger.warning("Telegram webhook registration failed during prestart.", exc_info=True)
    finally:
        await telegram_client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    asyncio.run(register_webhook_once())


if __name__ == "__main__":
    main()
