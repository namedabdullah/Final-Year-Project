"""Group chat thread / invite / message logic."""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lightrag.api.sampai.models.classroom import Folder, classroom_members
from lightrag.api.sampai.models.file import File
from lightrag.api.sampai.models.group_chat import (
    GroupChat,
    GroupChatInvite,
    GroupChatMember,
    GroupChatMessage,
    GroupMessageRole,
    GroupRole,
    InviteStatus,
)
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.services.mentions import parse_mentions

logger = logging.getLogger("sampai.groupchat")


async def _classroom_of_file(db: AsyncSession, file_id: int) -> int:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    return folder.classroom_id


# ── threads ──────────────────────────────────────────────────────────────────
async def create_thread(db: AsyncSession, file_id: int, classroom_id: int, creator_id: int) -> GroupChat:
    file = await db.get(File, file_id)
    gc = GroupChat(file_id=file_id, classroom_id=classroom_id, created_by=creator_id, name=f"{file.filename} — group")
    db.add(gc)
    await db.flush()
    db.add(GroupChatMember(group_chat_id=gc.id, user_id=creator_id, role=GroupRole.OWNER))
    await db.flush()
    return await _load_thread(db, gc.id)


async def _load_thread(db: AsyncSession, group_chat_id: int) -> GroupChat:
    return (
        await db.execute(
            select(GroupChat)
            .options(selectinload(GroupChat.members).selectinload(GroupChatMember.user))
            .where(GroupChat.id == group_chat_id)
        )
    ).scalar_one()


async def get_thread(db: AsyncSession, group_chat_id: int, user_id: int) -> GroupChat:
    gc = (
        await db.execute(
            select(GroupChat)
            .options(selectinload(GroupChat.members).selectinload(GroupChatMember.user))
            .where(GroupChat.id == group_chat_id)
        )
    ).scalar_one_or_none()
    if gc is None:
        raise HTTPException(status_code=404, detail="Group chat not found")
    if user_id not in {m.user_id for m in gc.members}:
        raise HTTPException(status_code=403, detail="You are not a member of this group chat")
    return gc


async def list_threads_for_user(db: AsyncSession, user_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(GroupChat)
            .join(GroupChatMember, GroupChatMember.group_chat_id == GroupChat.id)
            .where(GroupChatMember.user_id == user_id)
        )
    ).scalars().all()
    out = []
    for gc in rows:
        member = (
            await db.execute(
                select(GroupChatMember).where(
                    GroupChatMember.group_chat_id == gc.id, GroupChatMember.user_id == user_id
                )
            )
        ).scalar_one()
        max_seq = await db.scalar(
            select(func.coalesce(func.max(GroupChatMessage.seq), 0)).where(
                GroupChatMessage.group_chat_id == gc.id, GroupChatMessage.is_discarded == False  # noqa: E712
            )
        )
        last = (
            await db.execute(
                select(GroupChatMessage)
                .where(GroupChatMessage.group_chat_id == gc.id, GroupChatMessage.is_discarded == False)  # noqa: E712
                .order_by(GroupChatMessage.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append({
            "id": gc.id, "file_id": gc.file_id, "classroom_id": gc.classroom_id,
            "name": gc.name, "is_archived": gc.is_archived,
            "unread_count": max(0, (max_seq or 0) - member.last_read_seq),
            "last_message_preview": last.content[:100] if last else None,
        })
    return out


async def leave_thread(db: AsyncSession, group_chat_id: int, user_id: int) -> None:
    member = (
        await db.execute(
            select(GroupChatMember).where(
                GroupChatMember.group_chat_id == group_chat_id, GroupChatMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Not a member")
    await db.delete(member)
    await db.flush()
    # Archive if no human members remain.
    human = await db.scalar(
        select(func.count())
        .select_from(GroupChatMember)
        .join(User, User.id == GroupChatMember.user_id)
        .where(GroupChatMember.group_chat_id == group_chat_id, User.is_system == False)  # noqa: E712
    )
    if (human or 0) == 0:
        gc = await db.get(GroupChat, group_chat_id)
        if gc:
            gc.is_archived = True


async def update_read_seq(db: AsyncSession, group_chat_id: int, user_id: int, last_seq: int) -> None:
    member = (
        await db.execute(
            select(GroupChatMember).where(
                GroupChatMember.group_chat_id == group_chat_id, GroupChatMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member and last_seq > member.last_read_seq:
        member.last_read_seq = last_seq


# ── invites ──────────────────────────────────────────────────────────────────
async def list_eligible(db: AsyncSession, file_id: int, current_user_id: int, group_chat_id: int | None) -> list[User]:
    classroom_id = await _classroom_of_file(db, file_id)
    q = (
        select(User)
        .join(classroom_members, classroom_members.c.user_id == User.id)
        .where(classroom_members.c.classroom_id == classroom_id, User.id != current_user_id, User.is_system == False)  # noqa: E712
    )
    if group_chat_id is not None:
        members_sq = select(GroupChatMember.user_id).where(GroupChatMember.group_chat_id == group_chat_id)
        pending_sq = select(GroupChatInvite.invitee_id).where(
            GroupChatInvite.group_chat_id == group_chat_id, GroupChatInvite.status == InviteStatus.PENDING
        )
        q = q.where(User.id.not_in(members_sq), User.id.not_in(pending_sq))
    return list((await db.execute(q)).scalars().all())


async def _load_invite(db: AsyncSession, invite_id: int) -> GroupChatInvite | None:
    return (
        await db.execute(
            select(GroupChatInvite)
            .options(selectinload(GroupChatInvite.inviter), selectinload(GroupChatInvite.invitee))
            .where(GroupChatInvite.id == invite_id)
        )
    ).scalar_one_or_none()


async def send_invites(db: AsyncSession, file_id: int, current_user: User, user_ids: list[int], group_chat_id: int | None):
    classroom_id = await _classroom_of_file(db, file_id)
    if group_chat_id is None:
        gc = await create_thread(db, file_id, classroom_id, current_user.id)
        group_chat_id = gc.id
    else:
        gc = await get_thread(db, group_chat_id, current_user.id)

    invites = []
    for uid in user_ids:
        is_member = (
            await db.execute(
                select(GroupChatMember).where(GroupChatMember.group_chat_id == group_chat_id, GroupChatMember.user_id == uid)
            )
        ).scalar_one_or_none()
        if is_member is not None:
            raise HTTPException(status_code=409, detail=f"User {uid} is already a member")
        existing = (
            await db.execute(
                select(GroupChatInvite).where(
                    GroupChatInvite.group_chat_id == group_chat_id,
                    GroupChatInvite.invitee_id == uid,
                    GroupChatInvite.status == InviteStatus.PENDING,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"A pending invite already exists for user {uid}")
        inv = GroupChatInvite(group_chat_id=group_chat_id, inviter_id=current_user.id, invitee_id=uid, status=InviteStatus.PENDING)
        db.add(inv)
        invites.append(inv)
    await db.flush()
    loaded = [await _load_invite(db, i.id) for i in invites]
    return gc, loaded


async def get_pending_invites(db: AsyncSession, user_id: int) -> list[GroupChatInvite]:
    return list(
        (
            await db.execute(
                select(GroupChatInvite)
                .options(selectinload(GroupChatInvite.inviter), selectinload(GroupChatInvite.invitee))
                .where(GroupChatInvite.invitee_id == user_id, GroupChatInvite.status == InviteStatus.PENDING)
            )
        ).scalars().all()
    )


async def accept_invite(db: AsyncSession, invite_id: int, current_user: User) -> GroupChat:
    inv = await _load_invite(db, invite_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if inv.invitee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your invite")
    if inv.status != InviteStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Invite already {inv.status.value}")
    inv.status = InviteStatus.ACCEPTED
    inv.responded_at = datetime.utcnow()
    db.add(GroupChatMember(group_chat_id=inv.group_chat_id, user_id=current_user.id, role=GroupRole.MEMBER))
    await db.flush()
    return await get_thread(db, inv.group_chat_id, current_user.id)


async def _respond_invite(db: AsyncSession, invite_id: int, current_user: User, who: str, new: InviteStatus) -> GroupChatInvite:
    inv = await _load_invite(db, invite_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    owner_id = inv.inviter_id if who == "inviter" else inv.invitee_id
    if owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not permitted")
    if inv.status != InviteStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Invite already {inv.status.value}")
    inv.status = new
    inv.responded_at = datetime.utcnow()
    await db.flush()
    return inv


async def reject_invite(db, invite_id, current_user):
    return await _respond_invite(db, invite_id, current_user, "invitee", InviteStatus.REJECTED)


async def cancel_invite(db, invite_id, current_user):
    return await _respond_invite(db, invite_id, current_user, "inviter", InviteStatus.CANCELLED)


# ── messages ─────────────────────────────────────────────────────────────────
async def _load_message(db: AsyncSession, message_id: int) -> GroupChatMessage:
    return (
        await db.execute(
            select(GroupChatMessage)
            .options(selectinload(GroupChatMessage.author))
            .where(GroupChatMessage.id == message_id)
        )
    ).scalar_one()


async def send_message(db: AsyncSession, thread_id: int, user_id: int | None, content: str, reply_to_id: int | None = None, client_msg_id: str | None = None, role: GroupMessageRole = GroupMessageRole.USER) -> GroupChatMessage:
    parsed_cmid = None
    if client_msg_id:
        try:
            parsed_cmid = _uuid.UUID(client_msg_id)
        except (ValueError, AttributeError):
            parsed_cmid = None

    if parsed_cmid is not None:
        existing = (
            await db.execute(
                select(GroupChatMessage)
                .options(selectinload(GroupChatMessage.author))
                .where(GroupChatMessage.group_chat_id == thread_id, GroupChatMessage.client_msg_id == parsed_cmid)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    mentions = await parse_mentions(content, thread_id, db) if role == GroupMessageRole.USER else []

    # Lock the thread row to serialize seq assignment.
    gc = (await db.execute(select(GroupChat).where(GroupChat.id == thread_id).with_for_update())).scalar_one_or_none()
    if gc is None:
        raise HTTPException(status_code=404, detail="Group chat not found")
    next_seq = await db.scalar(
        select(func.coalesce(func.max(GroupChatMessage.seq), 0) + 1).where(GroupChatMessage.group_chat_id == thread_id)
    )
    msg = GroupChatMessage(
        group_chat_id=thread_id, seq=next_seq, user_id=user_id, role=role, content=content,
        mentions=mentions, reply_to_id=reply_to_id, client_msg_id=parsed_cmid,
    )
    db.add(msg)
    await db.commit()
    return await _load_message(db, msg.id)


async def list_messages(db: AsyncSession, thread_id: int, before_seq: int | None, limit: int) -> list[GroupChatMessage]:
    q = (
        select(GroupChatMessage)
        .options(selectinload(GroupChatMessage.author))
        .where(GroupChatMessage.group_chat_id == thread_id, GroupChatMessage.is_discarded == False)  # noqa: E712
    )
    if before_seq is not None:
        q = q.where(GroupChatMessage.seq < before_seq)
    q = q.order_by(GroupChatMessage.seq.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return list(reversed(rows))
