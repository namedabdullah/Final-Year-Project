"""Announcement + comment logic. Owner posts, members comment; HTML is sanitized
on write (nh3). Authorization is enforced here since most routes only carry the
announcement/comment id, not the classroom id."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lightrag.api.sampai.deps import is_member
from lightrag.api.sampai.integrations.sanitize import clean_announcement_html, is_effectively_empty
from lightrag.api.sampai.models.announcement import Announcement, AnnouncementComment
from lightrag.api.sampai.models.classroom import Classroom, classroom_members
from lightrag.api.sampai.models.user import User

logger = logging.getLogger("sampai.announcements")


async def _load(db: AsyncSession, announcement_id: int) -> Announcement:
    ann = (
        await db.execute(
            select(Announcement)
            .options(
                selectinload(Announcement.author),
                selectinload(Announcement.comments).selectinload(AnnouncementComment.author),
            )
            .where(Announcement.id == announcement_id)
        )
    ).scalar_one_or_none()
    if ann is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return ann


async def classroom_member_ids(db: AsyncSession, classroom_id: int) -> list[int]:
    return list(
        (await db.execute(select(classroom_members.c.user_id).where(classroom_members.c.classroom_id == classroom_id)))
        .scalars()
        .all()
    )


async def list_announcements(db: AsyncSession, classroom_id: int) -> list[Announcement]:
    return list(
        (
            await db.execute(
                select(Announcement)
                .options(
                    selectinload(Announcement.author),
                    selectinload(Announcement.comments).selectinload(AnnouncementComment.author),
                )
                .where(Announcement.classroom_id == classroom_id)
                .order_by(Announcement.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def create_announcement(db: AsyncSession, classroom_id: int, author_id: int, raw_content: str) -> Announcement:
    clean = clean_announcement_html(raw_content)
    if is_effectively_empty(clean):
        raise HTTPException(status_code=422, detail="Announcement cannot be empty")
    ann = Announcement(classroom_id=classroom_id, created_by_id=author_id, content=clean)
    db.add(ann)
    await db.flush()
    return await _load(db, ann.id)


async def delete_announcement(db: AsyncSession, announcement_id: int, user: User) -> int:
    """Owner-only. Returns the classroom id (for cache/notification use)."""
    ann = await db.get(Announcement, announcement_id)
    if ann is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    classroom = await db.get(Classroom, ann.classroom_id)
    if classroom is None or classroom.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the classroom owner can delete announcements")
    cid = ann.classroom_id
    await db.delete(ann)  # cascades comments
    return cid


async def add_comment(db: AsyncSession, announcement_id: int, user: User, content: str) -> tuple[AnnouncementComment, Announcement]:
    ann = await db.get(Announcement, announcement_id)
    if ann is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if not await is_member(db, ann.classroom_id, user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")

    comment = AnnouncementComment(announcement_id=announcement_id, created_by_id=user.id, content=text)
    db.add(comment)
    await db.flush()
    loaded = (
        await db.execute(
            select(AnnouncementComment)
            .options(selectinload(AnnouncementComment.author))
            .where(AnnouncementComment.id == comment.id)
        )
    ).scalar_one()
    return loaded, ann


async def delete_comment(db: AsyncSession, announcement_id: int, comment_id: int, user: User) -> None:
    """Comment author OR classroom owner."""
    comment = await db.get(AnnouncementComment, comment_id)
    if comment is None or comment.announcement_id != announcement_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    ann = await db.get(Announcement, announcement_id)
    classroom = await db.get(Classroom, ann.classroom_id) if ann else None
    is_owner = classroom is not None and classroom.owner_id == user.id
    if comment.created_by_id != user.id and not is_owner:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    await db.delete(comment)
