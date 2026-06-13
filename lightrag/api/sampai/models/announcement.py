"""Classroom announcements + comments."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcement_classroom_id", "classroom_id"),
        Index("ix_announcement_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # sanitized HTML (nh3)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    author = relationship("User", foreign_keys=[created_by_id], lazy="select")
    comments = relationship(
        "AnnouncementComment",
        back_populates="announcement",
        cascade="all, delete-orphan",
        order_by="AnnouncementComment.created_at",
    )


class AnnouncementComment(Base):
    __tablename__ = "announcement_comments"
    __table_args__ = (Index("ix_comment_announcement_id", "announcement_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    announcement = relationship("Announcement", back_populates="comments")
    author = relationship("User", foreign_keys=[created_by_id], lazy="select")
