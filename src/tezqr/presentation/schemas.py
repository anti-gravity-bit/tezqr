from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TelegramUserSchema(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None

    model_config = ConfigDict(extra="ignore")


class TelegramChatSchema(BaseModel):
    id: int

    model_config = ConfigDict(extra="ignore")


class TelegramPhotoSchema(BaseModel):
    file_id: str
    file_unique_id: str | None = None

    model_config = ConfigDict(extra="ignore")


class TelegramDocumentSchema(BaseModel):
    file_id: str
    file_unique_id: str | None = None
    mime_type: str | None = None
    file_name: str | None = None

    model_config = ConfigDict(extra="ignore")


class TelegramMessageSchema(BaseModel):
    message_id: int
    from_user: TelegramUserSchema = Field(alias="from")
    chat: TelegramChatSchema
    text: str | None = None
    caption: str | None = None
    photo: list[TelegramPhotoSchema] = Field(default_factory=list)
    document: TelegramDocumentSchema | None = None

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TelegramUpdateSchema(BaseModel):
    update_id: int
    message: TelegramMessageSchema | None = None
    edited_message: TelegramMessageSchema | None = None

    model_config = ConfigDict(extra="ignore")
