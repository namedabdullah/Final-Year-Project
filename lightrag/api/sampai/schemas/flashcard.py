"""Flashcard schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class GenerateDeckRequest(BaseModel):
    card_count: Literal[10, 20, 30] = 20


class GenerateDeckResponse(BaseModel):
    deck_id: int
    status: str


class CardPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    front: str
    back: str
    card_type: str
    box: int
    next_review_at: datetime

    @field_validator("card_type", mode="before")
    @classmethod
    def _ct(cls, v: object) -> object:
        return v.value if isinstance(v, Enum) else v


class DeckDetail(BaseModel):
    deck_id: int
    status: str
    card_count: int | None = None
    created_at: datetime
    ready_at: datetime | None = None
    error_msg: str | None = None
    cards: list[CardPublic] | None = None


class DueCardsResponse(BaseModel):
    cards: list[CardPublic]
    total_due: int


class ReviewRequest(BaseModel):
    result: Literal["know", "unsure", "forgot"]


class ReviewResponse(BaseModel):
    card_id: int
    box: int
    next_review_at: datetime


class DeckHistoryItem(BaseModel):
    deck_id: int
    status: str
    card_count: int | None = None
    created_at: datetime
    ready_at: datetime | None = None


class DeckHistoryResponse(BaseModel):
    items: list[DeckHistoryItem]
    box_counts: dict[str, int] | None = None
    has_open_deck: bool
    open_deck_id: int | None = None
