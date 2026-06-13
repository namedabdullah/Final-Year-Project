"""Per-file, per-user chat with SSE streaming, grounded in the single file's content."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db, get_sessionmaker
from lightrag.api.sampai.deps import get_current_user, require_membership
from lightrag.api.sampai.models.chat import ChatMessage, MessageRole
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.chat import AskRequest, ChatHistoryOut, ChatMessageOut
from lightrag.api.sampai.services.rag_gateway import scoped_answer_stream

router = APIRouter(prefix="/chat", tags=["sampai-chat"])
logger = logging.getLogger("sampai.chat")

HISTORY_TURNS = 10


async def _file_classroom(db: AsyncSession, file_id: int) -> tuple[File, int]:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return file, folder.classroom_id


async def _load_history(db: AsyncSession, file_id: int, user_id: int, limit: int) -> list[dict]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.file_id == file_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [{"role": m.role.value, "content": m.content} for m in reversed(rows)]


@router.post("/files/{file_id}/ask")
async def ask(
    file_id: int,
    body: AskRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="File is still processing. Please wait.")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    history = await _load_history(db, file_id, user.id, HISTORY_TURNS)

    # Persist the user's message immediately (survives an interrupted stream).
    db.add(ChatMessage(file_id=file_id, user_id=user.id, role=MessageRole.USER, content=question))
    await db.commit()

    engine = await request.app.state.sampai_registry.get_engine(classroom_id)
    doc_ids = {file.rag_doc_id} if file.rag_doc_id else set()
    uid = user.id  # capture for the generator closure
    sm = get_sessionmaker()

    async def event_stream():
        collected: list[str] = []
        try:
            async for token in scoped_answer_stream(engine, question, doc_ids, history):
                collected.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:  # pragma: no cover
            logger.error("chat stream failed file_id=%s: %s", file_id, exc)
            yield f"data: {json.dumps({'token': ' [error]'})}\n\n"
        answer = "".join(collected)
        # Persist the assistant reply in a fresh session (the request session is gone).
        try:
            async with sm() as s2:
                s2.add(ChatMessage(file_id=file_id, user_id=uid, role=MessageRole.ASSISTANT, content=answer))
                await s2.commit()
        except Exception:
            logger.exception("failed to persist assistant message file_id=%s", file_id)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/files/{file_id}/history", response_model=ChatHistoryOut)
async def history(
    file_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.file_id == file_id, ChatMessage.user_id == user.id)
            .order_by(ChatMessage.timestamp.asc())
            .limit(limit)
        )
    ).scalars().all()
    return ChatHistoryOut(messages=[ChatMessageOut.model_validate(r) for r in rows])


@router.delete("/files/{file_id}/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.file_id == file_id, ChatMessage.user_id == user.id
        )
    )
    await db.commit()
    return None
