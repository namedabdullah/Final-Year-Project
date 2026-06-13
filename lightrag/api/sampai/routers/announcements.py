"""Announcement + comment routes (clean paths — no double prefix).

Owner posts rich-text (sanitized) announcements; any member comments in plain
text. New posts/comments fan out to members over the user WebSocket for the bell.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership, require_owner
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.realtime import events
from lightrag.api.sampai.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementOut,
    CommentCreate,
    CommentOut,
)
from lightrag.api.sampai.services import announcement_service as svc

router = APIRouter(prefix="/announcements", tags=["sampai-announcements"])
logger = logging.getLogger("sampai.announcements")


def _hub(request: Request):
    return request.app.state.sampai_hub


@router.get("/classrooms/{classroom_id}", response_model=list[AnnouncementOut])
async def feed(classroom_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await require_membership(classroom_id, db, user)
    return [AnnouncementOut.model_validate(a) for a in await svc.list_announcements(db, classroom_id)]


@router.post("/classrooms/{classroom_id}", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
async def create(
    classroom_id: int,
    body: AnnouncementCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_owner(classroom_id, db, user)
    ann = await svc.create_announcement(db, classroom_id, user.id, body.content)
    member_ids = await svc.classroom_member_ids(db, classroom_id)
    await db.commit()
    hub = _hub(request)
    for uid in member_ids:
        if uid != user.id:
            await hub.send_user(uid, events.announcement_new(ann.id, classroom_id, user.username))
    logger.info("announcement created id=%s classroom=%s", ann.id, classroom_id)
    return AnnouncementOut.model_validate(ann)


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(announcement_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await svc.delete_announcement(db, announcement_id, user)
    await db.commit()
    return None


@router.post("/{announcement_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    announcement_id: int,
    body: CommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    comment, ann = await svc.add_comment(db, announcement_id, user, body.content)
    await db.commit()
    if ann.created_by_id != user.id:
        await _hub(request).send_user(
            ann.created_by_id, events.comment_new(ann.id, ann.classroom_id, user.username)
        )
    return CommentOut.model_validate(comment)


@router.delete("/{announcement_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_comment(
    announcement_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await svc.delete_comment(db, announcement_id, comment_id, user)
    await db.commit()
    return None
