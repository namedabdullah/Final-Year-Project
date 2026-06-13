"""Uploaded files + their processing-status lifecycle."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"   # single gate: all AI features unlock here (DocStatus.PROCESSED)
    FAILED = "failed"


def _enum(e):
    # Store the enum *value* (lowercase) in the DB, not the member name.
    return SQLEnum(e, values_callable=lambda x: [m.value for m in x])


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)  # R2 URL = citation key
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)  # R2 object key
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        _enum(ProcessingStatus), nullable=False, default=ProcessingStatus.PENDING
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI summary
    folder_id: Mapped[int] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rag_doc_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    track_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    folder = relationship("Folder", back_populates="files")
