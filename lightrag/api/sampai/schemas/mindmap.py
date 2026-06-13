"""Mindmap schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerateMindmapRequest(BaseModel):
    force: bool = False


class MindmapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_id: int
    classroom_id: int
    status: str
    root_topic: str | None = None
    root_description: str | None = None
    tree_data: Any | None = None
    node_count: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("status", mode="before")
    @classmethod
    def _s(cls, v: object) -> object:
        return v.value if isinstance(v, Enum) else v


class ExploreNodeResponse(BaseModel):
    already_explored: bool
    last_message_id: int | None = None
    marker_id: int | None = None
    placeholder_id: int | None = None


class NodeChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mindmap_id: int
    node_id: str | None = None
    role: str
    content: str
    message_metadata: Any = {}
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _r(cls, v: object) -> object:
        return v.value if isinstance(v, Enum) else v


class ChatHistoryResponse(BaseModel):
    messages: list[NodeChatMessageOut]
    has_more: bool = False


class AskInThreadRequest(BaseModel):
    content: str = Field(min_length=1)
    active_node_id: str | None = None


class AskResponse(BaseModel):
    message: NodeChatMessageOut
