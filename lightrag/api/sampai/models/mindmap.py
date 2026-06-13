"""Mindmaps (one shared tree per file) + per-user node chat."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base


class MindmapStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class MindmapMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    MARKER = "marker"


def _enum(e):
    return SQLEnum(e, values_callable=lambda x: [m.value for m in x])


class Mindmap(Base):
    __tablename__ = "mindmaps"
    __table_args__ = (Index("ix_mindmap_classroom_status", "classroom_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    root_topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    root_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tree_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[MindmapStatus] = mapped_column(_enum(MindmapStatus), nullable=False, default=MindmapStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    node_chats = relationship("MindmapNodeChat", back_populates="mindmap", cascade="all, delete-orphan")


class MindmapNodeChat(Base):
    __tablename__ = "mindmap_node_chats"
    __table_args__ = (
        Index("ix_mindmap_chat_user_time", "mindmap_id", "user_id", "created_at"),
        Index("ix_mindmap_chat_node", "mindmap_id", "user_id", "node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mindmap_id: Mapped[int] = mapped_column(ForeignKey("mindmaps.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[MindmapMessageRole] = mapped_column(_enum(MindmapMessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    mindmap = relationship("Mindmap", back_populates="node_chats")
