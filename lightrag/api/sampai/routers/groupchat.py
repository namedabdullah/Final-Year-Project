"""Group chat routes: invites, threads, messages (rate-limited), + 2 WebSockets."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db, get_sessionmaker
from lightrag.api.sampai.deps import get_current_user, require_membership
from lightrag.api.sampai.models.group_chat import GroupChat, GroupChatMember
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.realtime import events
from lightrag.api.sampai.realtime.ratelimit import check_agent_rate, check_message_rate
from lightrag.api.sampai.schemas.group_chat import (
    GroupChatOut,
    GroupMessageOut,
    InviteIn,
    InviteOut,
    ReadReceiptIn,
    SendMessageIn,
    ThreadListItem,
    UserSummary,
)
from lightrag.api.sampai.security import decode_access_token
from lightrag.api.sampai.services import groupchat_service as svc
from lightrag.api.sampai.services.groupchat_agent import run_respond

router = APIRouter(prefix="/group-chat", tags=["sampai-groupchat"])
logger = logging.getLogger("sampai.groupchat")


def _hub(request: Request):
    return request.app.state.sampai_hub


async def _classroom_of_file(db: AsyncSession, file_id: int) -> int:
    return await svc._classroom_of_file(db, file_id)


# ── invites ──────────────────────────────────────────────────────────────────
@router.get("/files/{file_id}/eligible-invitees", response_model=list[UserSummary])
async def eligible(file_id: int, group_chat_id: int | None = Query(None), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await require_membership(await _classroom_of_file(db, file_id), db, user)
    return [UserSummary.model_validate(u) for u in await svc.list_eligible(db, file_id, user.id, group_chat_id)]


@router.post("/files/{file_id}/invite", status_code=201)
async def invite(file_id: int, body: InviteIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await require_membership(await _classroom_of_file(db, file_id), db, user)
    gc, invites = await svc.send_invites(db, file_id, user, body.user_ids, body.group_chat_id)
    await db.commit()
    for inv in invites:
        await _hub(request).send_user(inv.invitee_id, events.invite_new(InviteOut.model_validate(inv).model_dump(mode="json")))
    return {"group_chat_id": gc.id, "invites": [InviteOut.model_validate(i).model_dump(mode="json") for i in invites]}


@router.get("/invites/pending", response_model=list[InviteOut])
async def pending(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return [InviteOut.model_validate(i) for i in await svc.get_pending_invites(db, user.id)]


@router.post("/invites/{invite_id}/accept", response_model=GroupChatOut)
async def accept(invite_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    gc = await svc.accept_invite(db, invite_id, user)
    await db.commit()
    for m in gc.members:
        if m.user_id != user.id:
            await _hub(request).send_user(m.user_id, events.invite_accepted(invite_id, gc.id, user.id))
    return GroupChatOut.model_validate(gc)


@router.post("/invites/{invite_id}/reject", response_model=InviteOut)
async def reject(invite_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    inv = await svc.reject_invite(db, invite_id, user)
    await db.commit()
    return InviteOut.model_validate(inv)


@router.post("/invites/{invite_id}/cancel", response_model=InviteOut)
async def cancel(invite_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    inv = await svc.cancel_invite(db, invite_id, user)
    await db.commit()
    await _hub(request).send_user(inv.invitee_id, events.invite_cancelled(invite_id, inv.group_chat_id))
    return InviteOut.model_validate(inv)


# ── threads ──────────────────────────────────────────────────────────────────
@router.get("/threads", response_model=list[ThreadListItem])
async def threads(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return [ThreadListItem(**t) for t in await svc.list_threads_for_user(db, user.id)]


@router.get("/threads/{thread_id}", response_model=GroupChatOut)
async def thread(thread_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return GroupChatOut.model_validate(await svc.get_thread(db, thread_id, user.id))


@router.post("/threads/{thread_id}/leave")
async def leave(thread_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await svc.get_thread(db, thread_id, user.id)
    await svc.leave_thread(db, thread_id, user.id)
    await db.commit()
    await _hub(request).broadcast_thread(thread_id, events.member_left(thread_id, user.id))
    return {"detail": "left"}


@router.post("/threads/{thread_id}/read")
async def read(thread_id: int, body: ReadReceiptIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await svc.get_thread(db, thread_id, user.id)
    await svc.update_read_seq(db, thread_id, user.id, body.last_seq)
    await db.commit()
    await _hub(request).broadcast_thread(thread_id, events.read_receipt(thread_id, user.id, body.last_seq))
    return {"detail": "ok"}


# ── messages ─────────────────────────────────────────────────────────────────
@router.post("/threads/{thread_id}/messages", response_model=GroupMessageOut)
async def send(thread_id: int, body: SendMessageIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    gc = await svc.get_thread(db, thread_id, user.id)
    if not await check_message_rate(user.id, thread_id):
        raise HTTPException(status_code=429, detail="Message rate limit exceeded (max 10 / 10s)")

    msg = await svc.send_message(db, thread_id=thread_id, user_id=user.id, content=body.content, reply_to_id=body.reply_to_id, client_msg_id=body.client_msg_id)
    hub = _hub(request)
    out = GroupMessageOut.model_validate(msg)
    await hub.broadcast_thread(thread_id, events.message_new(out.model_dump(mode="json")))

    # Bell bump for @-mentioned users who aren't currently in the thread room.
    online = set(hub.presence_for_thread(thread_id))
    mentioned = {m.get("user_id") for m in (msg.mentions or []) if m.get("kind") == "user" and isinstance(m.get("user_id"), int)}
    for uid in mentioned:
        if uid != user.id and uid not in online:
            await hub.send_user(uid, events.thread_unread_bump(thread_id))

    # @SAMpai → respond (rate-limited).
    if any(m.get("kind") == "agent" for m in (msg.mentions or [])):
        if await check_agent_rate(user.id, thread_id):
            asyncio.create_task(run_respond(msg.id, thread_id, gc.file_id, gc.classroom_id, hub))
        else:
            from lightrag.api.sampai.models.group_chat import GroupMessageRole
            sys_msg = await svc.send_message(db, thread_id=thread_id, user_id=None, content="@SAMpai rate limit reached. Please wait before mentioning again.", role=GroupMessageRole.SYSTEM)
            await hub.broadcast_thread(thread_id, events.message_new(GroupMessageOut.model_validate(sys_msg).model_dump(mode="json")))
    return out


@router.get("/threads/{thread_id}/messages", response_model=list[GroupMessageOut])
async def messages(thread_id: int, before_seq: int | None = Query(None), limit: int = Query(50, le=100), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await svc.get_thread(db, thread_id, user.id)
    rows = await svc.list_messages(db, thread_id, before_seq, limit)
    return [GroupMessageOut.model_validate(m) for m in rows]


# ── WebSockets ───────────────────────────────────────────────────────────────
def _auth_ws(ws: WebSocket, token: str) -> int | None:
    payload = decode_access_token(token, ws.app.state.sampai_settings.app_jwt_secret)
    if not payload or "sub" not in payload:
        return None
    return int(payload["sub"])


@router.websocket("/ws/user")
async def ws_user(websocket: WebSocket, token: str = Query(...)):
    uid = _auth_ws(websocket, token)
    if uid is None:
        await websocket.close(code=4401)
        return
    hub = websocket.app.state.sampai_hub
    await websocket.accept()
    await hub.register_user(websocket, uid)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister_user(websocket, uid)


@router.websocket("/ws/group-chat/{thread_id}")
async def ws_thread(websocket: WebSocket, thread_id: int, token: str = Query(...)):
    uid = _auth_ws(websocket, token)
    if uid is None:
        await websocket.close(code=4401)
        return

    sm = get_sessionmaker()
    async with sm() as db:
        member = (
            await db.execute(
                select(GroupChatMember).where(GroupChatMember.group_chat_id == thread_id, GroupChatMember.user_id == uid)
            )
        ).scalar_one_or_none()
        if member is None:
            await websocket.close(code=4403)
            return
        username = (await db.get(User, uid)).username

    hub = websocket.app.state.sampai_hub
    await websocket.accept()
    await hub.join_thread(websocket, thread_id, uid)
    # presence snapshot to joiner + member_joined to others
    await websocket.send_json(events.presence(thread_id, hub.presence_for_thread(thread_id)))
    await hub.broadcast_thread(thread_id, events.member_joined(thread_id, uid, username), exclude=websocket)
    await hub.broadcast_thread(thread_id, events.presence(thread_id, hub.presence_for_thread(thread_id)))

    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            if t == "typing":
                await hub.broadcast_thread(thread_id, events.typing(thread_id, uid, username, bool(data.get("is_typing", True))), exclude=websocket)
            elif t == "read_receipt":
                last_seq = data.get("last_seq")
                if last_seq is not None:
                    async with sm() as db:
                        await svc.update_read_seq(db, thread_id, uid, int(last_seq))
                        await db.commit()
                    await hub.broadcast_thread(thread_id, events.read_receipt(thread_id, uid, int(last_seq)), exclude=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave_thread(websocket)
        await hub.broadcast_thread(thread_id, events.member_left(thread_id, uid))
        await hub.broadcast_thread(thread_id, events.presence(thread_id, hub.presence_for_thread(thread_id)))
