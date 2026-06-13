"""Group chats: threads, members, invites, messages."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base


class GroupRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class GroupMessageRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


def _enum(e):
    return SQLEnum(e, values_callable=lambda x: [m.value for m in x])


class GroupChat(Base):
    __tablename__ = "group_chats"
    __table_args__ = (
        Index("ix_gc_file_archived", "file_id", "is_archived"),
        Index("ix_gc_classroom", "classroom_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    members = relationship("GroupChatMember", back_populates="group_chat", cascade="all, delete-orphan")
    invites = relationship("GroupChatInvite", back_populates="group_chat", cascade="all, delete-orphan")
    messages = relationship("GroupChatMessage", back_populates="group_chat", cascade="all, delete-orphan")


class GroupChatMember(Base):
    __tablename__ = "group_chat_members"

    group_chat_id: Mapped[int] = mapped_column(
        ForeignKey("group_chats.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[GroupRole] = mapped_column(_enum(GroupRole), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_read_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    group_chat = relationship("GroupChat", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], lazy="select")


class GroupChatInvite(Base):
    __tablename__ = "group_chat_invites"
    __table_args__ = (
        UniqueConstraint("group_chat_id", "invitee_id", name="uq_gc_invite_per_invitee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(ForeignKey("group_chats.id", ondelete="CASCADE"), nullable=False)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[InviteStatus] = mapped_column(_enum(InviteStatus), nullable=False, default=InviteStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    group_chat = relationship("GroupChat", back_populates="invites")
    inviter = relationship("User", foreign_keys=[inviter_id], lazy="select")
    invitee = relationship("User", foreign_keys=[invitee_id], lazy="select")


class GroupChatMessage(Base):
    __tablename__ = "group_chat_messages"
    __table_args__ = (
        UniqueConstraint("group_chat_id", "seq", name="uq_gc_message_seq"),
        Index("ix_gcm_group_created", "group_chat_id", "created_at"),
        Index("ix_gcm_group_user", "group_chat_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(ForeignKey("group_chats.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role: Mapped[GroupMessageRole] = mapped_column(_enum(GroupMessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("group_chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    is_discarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discard_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_msg_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    group_chat = relationship("GroupChat", back_populates="messages")
    author = relationship("User", foreign_keys=[user_id], lazy="select")
