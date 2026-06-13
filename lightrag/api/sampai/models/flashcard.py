"""Flashcard decks + cards + review audit (Leitner spaced repetition)."""

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


class FlashcardDeckStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class FlashcardCardType(str, enum.Enum):
    DEFINITION = "definition"
    CONCEPT = "concept"
    EXAMPLE = "example"
    FORMULA = "formula"


def _enum(e):
    return SQLEnum(e, values_callable=lambda x: [m.value for m in x])


class FlashcardDeck(Base):
    __tablename__ = "flashcard_decks"
    __table_args__ = (
        Index("ix_deck_user_file", "user_id", "file_id"),
        Index("ix_deck_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[FlashcardDeckStatus] = mapped_column(
        _enum(FlashcardDeckStatus), nullable=False, default=FlashcardDeckStatus.PENDING
    )
    card_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cards = relationship("Flashcard", back_populates="deck", cascade="all, delete-orphan")


class Flashcard(Base):
    __tablename__ = "flashcards"
    __table_args__ = (
        Index("ix_card_user_file", "user_id", "file_id"),
        Index("ix_card_due", "user_id", "next_review_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("flashcard_decks.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    card_type: Mapped[FlashcardCardType] = mapped_column(_enum(FlashcardCardType), nullable=False)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    deck = relationship("FlashcardDeck", back_populates="cards")


class FlashcardReview(Base):
    __tablename__ = "flashcard_reviews"
    __table_args__ = (Index("ix_review_card_user", "card_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)  # know|unsure|forgot
    box_before: Mapped[int] = mapped_column(Integer, nullable=False)
    box_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
