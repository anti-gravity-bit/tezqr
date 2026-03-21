from __future__ import annotations

import httpx

from tezqr.application.ports import TelegramGateway
from tezqr.shared.config import Settings


class TelegramBotClient(TelegramGateway):
    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http_client = http_client

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> None:
        await self._post_json(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        *,
        filename: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        form_data = {"chat_id": str(chat_id)}
        if caption:
            form_data["caption"] = caption
        if reply_to_message_id is not None:
            form_data["reply_to_message_id"] = str(reply_to_message_id)
        response = await self._http_client.post(
            self._build_url("sendPhoto"),
            data=form_data,
            files={"photo": (filename, photo_bytes, "image/png")},
        )
        self._raise_for_telegram_error(response)

    async def copy_message(self, chat_id: int, from_chat_id: int, message_id: int) -> None:
        await self._post_json(
            "copyMessage",
            {
                "chat_id": chat_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
            },
        )

    async def send_photo_reference(
        self,
        chat_id: int,
        photo_reference: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        await self._post_json(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": photo_reference,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def set_webhook(self, url: str) -> None:
        await self._post_json(
            "setWebhook",
            {
                "url": url,
                "drop_pending_updates": False,
            },
        )

    async def _post_json(self, method: str, payload: dict[str, object]) -> None:
        body = {key: value for key, value in payload.items() if value not in {None, ""}}
        response = await self._http_client.post(self._build_url(method), json=body)
        self._raise_for_telegram_error(response)

    def _build_url(self, method: str) -> str:
        return f"{self._settings.telegram_api_base_url}/{method}"

    @staticmethod
    def _raise_for_telegram_error(response: httpx.Response) -> None:
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
