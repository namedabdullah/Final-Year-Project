"""Chat schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    timestamp: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _role_value(cls, v: object) -> object:
        return v.value if isinstance(v, Enum) else v


class ChatHistoryOut(BaseModel):
    messages: list[ChatMessageOut]
