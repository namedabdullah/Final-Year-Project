"""Mindmap routes: generate/get/delete tree, explore node, per-user node chat."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership, require_owner
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.mindmap import Mindmap, MindmapNodeChat, MindmapStatus
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.mindmap import (
    AskInThreadRequest,
    AskResponse,
    ChatHistoryResponse,
    ExploreNodeResponse,
    GenerateMindmapRequest,
    MindmapOut,
    NodeChatMessageOut,
)
from lightrag.api.sampai.services import mindmap_service as svc

router = APIRouter(prefix="/mindmap", tags=["sampai-mindmap"])
logger = logging.getLogger("sampai.mindmap")


async def _file_classroom(db: AsyncSession, file_id: int) -> tuple[File, int]:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    return file, folder.classroom_id


async def _mindmap_ctx(db: AsyncSession, mindmap_id: int) -> tuple[Mindmap, File, int]:
    mm = await db.get(Mindmap, mindmap_id)
    if mm is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    file, classroom_id = await _file_classroom(db, mm.file_id)
    return mm, file, classroom_id


@router.post("/files/{file_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate(
    file_id: int,
    body: GenerateMindmapRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="File is still processing")

    mm = await svc.load_or_create(db, file_id, classroom_id, force=body.force)
    already_ready = mm.status == MindmapStatus.READY and not body.force
    generating = mm.status == MindmapStatus.GENERATING
    await db.commit()
    await db.refresh(mm)  # reload server-default cols (updated_at) so model_validate does no lazy IO
    out = MindmapOut.model_validate(mm)

    if already_ready:
        return {"detail": "already ready", "mindmap": out}
    if generating:
        return {"detail": "generating", "mindmap": out}

    asyncio.create_task(svc.generate_mindmap_task(file_id, classroom_id, body.force))
    return {"detail": "generation started", "mindmap": out}


@router.get("/files/{file_id}", response_model=MindmapOut)
async def get_mindmap(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    mm = await svc.get_by_file(db, file_id)
    if mm is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    return mm


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mindmap(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _file_classroom(db, file_id)
    await require_owner(classroom_id, db, user)
    mm = await svc.get_by_file(db, file_id)
    if mm is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    await db.delete(mm)
    await db.commit()
    return None


@router.post("/{mindmap_id}/nodes/{node_id}/explore", response_model=ExploreNodeResponse)
async def explore(
    mindmap_id: int,
    node_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mm, file, classroom_id = await _mindmap_ctx(db, mindmap_id)
    await require_membership(classroom_id, db, user)
    if mm.status != MindmapStatus.READY:
        raise HTTPException(status_code=409, detail="Mindmap is not ready yet")
    if svc.find_node(mm.tree_data or {}, node_id) is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    already, last_id, marker_id, placeholder_id = await svc.explore_node(db, mindmap_id, node_id, user.id)
    await db.commit()

    if not already and placeholder_id is not None:
        asyncio.create_task(
            svc.generate_node_summary_task(mindmap_id, node_id, placeholder_id, file.id, classroom_id, user.id)
        )
    return ExploreNodeResponse(already_explored=already, last_message_id=last_id, marker_id=marker_id, placeholder_id=placeholder_id)


@router.get("/{mindmap_id}/chat", response_model=ChatHistoryResponse)
async def chat_history(
    mindmap_id: int,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mm, _, classroom_id = await _mindmap_ctx(db, mindmap_id)
    await require_membership(classroom_id, db, user)
    rows = (
        await db.execute(
            select(MindmapNodeChat)
            .where(MindmapNodeChat.mindmap_id == mindmap_id, MindmapNodeChat.user_id == user.id)
            .order_by(MindmapNodeChat.id.asc())
            .limit(limit)
        )
    ).scalars().all()
    return ChatHistoryResponse(messages=[NodeChatMessageOut.model_validate(r) for r in rows], has_more=False)


@router.post("/{mindmap_id}/chat/ask", response_model=AskResponse)
async def chat_ask(
    mindmap_id: int,
    body: AskInThreadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mm, file, classroom_id = await _mindmap_ctx(db, mindmap_id)
    await require_membership(classroom_id, db, user)
    if mm.status != MindmapStatus.READY:
        raise HTTPException(status_code=409, detail="Mindmap is not ready yet")
    msg = await svc.ask_in_thread(db, mindmap_id, user.id, body.content.strip(), body.active_node_id, file.id, classroom_id)
    return AskResponse(message=NodeChatMessageOut.model_validate(msg))


@router.delete("/{mindmap_id}/chat", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat(
    mindmap_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, _, classroom_id = await _mindmap_ctx(db, mindmap_id)
    await require_membership(classroom_id, db, user)
    await db.execute(
        delete(MindmapNodeChat).where(
            MindmapNodeChat.mindmap_id == mindmap_id, MindmapNodeChat.user_id == user.id
        )
    )
    await db.commit()
    return None
