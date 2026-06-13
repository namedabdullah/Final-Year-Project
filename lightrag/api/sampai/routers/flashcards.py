"""Flashcard routes: generate deck, poll, due cards, history, review (Leitner)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.flashcard import (
    Flashcard,
    FlashcardDeck,
    FlashcardDeckStatus,
    FlashcardReview,
)
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.flashcard import (
    CardPublic,
    DeckDetail,
    DeckHistoryItem,
    DeckHistoryResponse,
    DueCardsResponse,
    GenerateDeckRequest,
    GenerateDeckResponse,
    ReviewRequest,
    ReviewResponse,
)
from lightrag.api.sampai.services import flashcard_service

router = APIRouter(prefix="/flashcards", tags=["sampai-flashcards"])
logger = logging.getLogger("sampai.flashcards")

_OPEN = (FlashcardDeckStatus.PENDING, FlashcardDeckStatus.GENERATING)
_STALE_MIN = 5


async def _file_classroom(db: AsyncSession, file_id: int) -> tuple[File, int]:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    return file, folder.classroom_id


@router.post("/files/{file_id}/generate", response_model=GenerateDeckResponse, status_code=202)
async def generate_deck(
    file_id: int,
    body: GenerateDeckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="File is still processing")

    open_deck = (
        await db.execute(
            select(FlashcardDeck)
            .where(
                FlashcardDeck.user_id == user.id,
                FlashcardDeck.file_id == file_id,
                FlashcardDeck.status.in_(_OPEN),
            )
            .order_by(FlashcardDeck.created_at.desc())
        )
    ).scalars().first()
    if open_deck is not None:
        stale = datetime.utcnow() - timedelta(minutes=_STALE_MIN)
        if open_deck.status == FlashcardDeckStatus.GENERATING and open_deck.created_at < stale:
            open_deck.status = FlashcardDeckStatus.FAILED
            open_deck.error_msg = "abandoned — timed out"
            await db.commit()
        else:
            raise HTTPException(status_code=409, detail="A deck is already generating for this file")

    deck = FlashcardDeck(
        file_id=file_id, user_id=user.id, status=FlashcardDeckStatus.PENDING, card_count=body.card_count
    )
    db.add(deck)
    await db.commit()
    await db.refresh(deck)

    asyncio.create_task(
        flashcard_service.generate_deck_task(deck.id, classroom_id, file_id, file.rag_doc_id)
    )
    return GenerateDeckResponse(deck_id=deck.id, status="pending")


@router.get("/files/{file_id}/due", response_model=DueCardsResponse)
async def due_cards(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    cards = (
        await db.execute(
            select(Flashcard)
            .where(
                Flashcard.user_id == user.id,
                Flashcard.file_id == file_id,
                Flashcard.next_review_at <= datetime.utcnow(),
            )
            .order_by(Flashcard.next_review_at)
        )
    ).scalars().all()
    return DueCardsResponse(cards=[CardPublic.model_validate(c) for c in cards], total_due=len(cards))


@router.get("/files/{file_id}/history", response_model=DeckHistoryResponse)
async def deck_history(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    decks = (
        await db.execute(
            select(FlashcardDeck)
            .where(FlashcardDeck.user_id == user.id, FlashcardDeck.file_id == file_id)
            .order_by(FlashcardDeck.created_at.desc())
        )
    ).scalars().all()

    has_open = False
    open_id = None
    items = []
    for d in decks:
        items.append(DeckHistoryItem(deck_id=d.id, status=d.status.value, card_count=d.card_count, created_at=d.created_at, ready_at=d.ready_at))
        if d.status in _OPEN and not has_open:
            has_open, open_id = True, d.id

    box_counts = None
    latest_ready = next((d for d in decks if d.status == FlashcardDeckStatus.READY), None)
    if latest_ready is not None:
        rows = await db.execute(
            select(Flashcard.box, func.count(Flashcard.id)).where(Flashcard.deck_id == latest_ready.id).group_by(Flashcard.box)
        )
        box_counts = {str(box): cnt for box, cnt in rows.all()}

    return DeckHistoryResponse(items=items, box_counts=box_counts, has_open_deck=has_open, open_deck_id=open_id)


@router.get("/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = (
        await db.execute(select(FlashcardDeck).options(selectinload(FlashcardDeck.cards)).where(FlashcardDeck.id == deck_id))
    ).scalar_one_or_none()
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    cards = (
        [CardPublic.model_validate(c) for c in deck.cards]
        if deck.status == FlashcardDeckStatus.READY
        else None
    )
    return DeckDetail(
        deck_id=deck.id, status=deck.status.value, card_count=deck.card_count,
        created_at=deck.created_at, ready_at=deck.ready_at, error_msg=deck.error_msg, cards=cards,
    )


@router.post("/cards/{card_id}/review", response_model=ReviewResponse)
async def review(
    card_id: int,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    card = await db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    box_before = card.box
    new_box, next_at = flashcard_service.review_card(card.box, body.result)
    card.box, card.next_review_at = new_box, next_at
    db.add(FlashcardReview(card_id=card.id, user_id=user.id, result=body.result, box_before=box_before, box_after=new_box))
    await db.commit()
    return ReviewResponse(card_id=card.id, box=new_box, next_review_at=next_at)
