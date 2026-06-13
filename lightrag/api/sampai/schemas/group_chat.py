"""Group chat schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


def _ev(v: object) -> object:
    return v.value if isinstance(v, Enum) else v


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    role: str
    joined_at: datetime
    last_read_seq: int
    user: UserSummary

    @field_validator("role", mode="before")
    @classmethod
    def _r(cls, v): return _ev(v)


class GroupChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_id: int
    classroom_id: int
    created_by: int | None = None
    name: str | None = None
    is_archived: bool
    created_at: datetime
    members: list[MemberOut] = []


class ThreadListItem(BaseModel):
    id: int
    file_id: int
    classroom_id: int
    name: str | None = None
    is_archived: bool
    unread_count: int = 0
    last_message_preview: str | None = None


class InviteIn(BaseModel):
    user_ids: list[int]
    group_chat_id: int | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_chat_id: int
    inviter_id: int
    invitee_id: int
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    inviter: UserSummary
    invitee: UserSummary

    @field_validator("status", mode="before")
    @classmethod
    def _s(cls, v): return _ev(v)


class SendMessageIn(BaseModel):
    content: str
    reply_to_id: int | None = None
    client_msg_id: str | None = None


class GroupMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_chat_id: int
    seq: int
    user_id: int | None = None
    role: str
    content: str
    mentions: list = []
    reply_to_id: int | None = None
    is_discarded: bool = False
    created_at: datetime
    author: UserSummary | None = None

    @field_validator("role", mode="before")
    @classmethod
    def _r(cls, v): return _ev(v)

    @field_validator("client_msg_id", check_fields=False, mode="before")
    @classmethod
    def _ignore(cls, v): return v


class ReadReceiptIn(BaseModel):
    last_seq: int
