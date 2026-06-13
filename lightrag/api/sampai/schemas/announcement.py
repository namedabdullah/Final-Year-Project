"""Announcement + comment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from lightrag.api.sampai.schemas.group_chat import UserSummary


class AnnouncementCreate(BaseModel):
    content: str = Field(min_length=1)  # raw editor HTML; sanitized server-side


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)  # plain text


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    announcement_id: int
    created_by_id: int
    content: str
    created_at: datetime
    author: UserSummary | None = None


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    classroom_id: int
    created_by_id: int
    content: str  # sanitized HTML
    created_at: datetime
    updated_at: datetime
    author: UserSummary | None = None
    comments: list[CommentOut] = []
