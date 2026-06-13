"""Classrooms + membership (many-to-many) + folders."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Column,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base

# Association table for classroom membership (composite PK).
classroom_members = Table(
    "classroom_members",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("classroom_id", ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True),
)


class Classroom(Base):
    __tablename__ = "classrooms"
    # Fix vs old app: classroom name is unique PER OWNER, not globally.
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_classrooms_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("User", secondary=classroom_members, lazy="selectin")
    folders = relationship(
        "Folder", back_populates="classroom", cascade="all, delete-orphan"
    )


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )

    classroom = relationship("Classroom", back_populates="folders")
    files = relationship("File", back_populates="folder", cascade="all, delete-orphan")
