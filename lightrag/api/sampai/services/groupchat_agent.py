"""@SAMpai — respond-only group-chat tutor agent.

SAMpai is passive: it answers ONLY when a student @mentions it. No off-topic guard,
no proactive messages. The respond pipeline refuses obvious manipulation attempts,
gates on the file being processed, builds clean multi-speaker history, then answers
grounded in the file via the scoped gateway.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.group_chat import GroupChatMessage, GroupMessageRole
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.realtime import events
from lightrag.api.sampai.schemas.group_chat import GroupMessageOut
from lightrag.api.sampai.services.engine_access import get_engine
from lightrag.api.sampai.services.groupchat_service import send_message
from lightrag.api.sampai.services.rag_gateway import scoped_answer

logger = logging.getLogger("sampai.agent")

_MANIPULATION = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bstop\s+(talking|responding|replying|answering)\b",
        r"\bshut\s+up\b",
        r"\bbe\s+(quiet|quite|silent)\b",
        r"\bdon'?t\s+(respond|reply|answer|talk)\b",
        r"\bdo\s+not\s+(respond|reply|answer|talk)\b",
        r"\balways\s+(say|reply|answer|respond)\s+(with|that|this)\b",
        r"\bonly\s+(say|reply|answer|respond)\s+(with|that|this)\b",
        r"\b(reply|respond|answer|say)\s+only\s+with\b",
        r"\bignore\s+(your|all|the|previous|these)\s+(instructions?|prompt|rules?|system)\b",
        r"\bforget\s+(your|all|the|previous|these)\s+(instructions?|prompt|rules?|system)\b",
        r"\boverride\s+(your|all|the)\s+(instructions?|prompt|rules?)\b",
        r"\bnew\s+(system\s+)?instructions?\b",
        r"\bsystem\s+prompt\b",
        r"\byou\s+are\s+now\s+(a|an|the)\b",
        r"\bpretend\s+(you\s+are|to\s+be)\b",
        r"\bact\s+as\s+(if|though|a|an|the)\b",
    ]
]
_REFUSAL_MARKERS = ("i'm here to help with", "what would you like to know about")

_sampai_uid: int | None = None


def _looks_like_manipulation(text: str) -> bool:
    return any(p.search(text) for p in _MANIPULATION)


def _is_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


async def _system_user_id(db) -> int | None:
    global _sampai_uid
    if _sampai_uid is None:
        _sampai_uid = await db.scalar(select(User.id).where(User.is_system == True))  # noqa: E712
    return _sampai_uid


async def run_respond(message_id: int, thread_id: int, file_id: int, classroom_id: int, hub) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        trigger = (
            await db.execute(select(GroupChatMessage).where(GroupChatMessage.id == message_id))
        ).scalar_one_or_none()
        if trigger is None or trigger.is_discarded:
            return
        file = await db.get(File, file_id)
        if file is None:
            return
        sampai_uid = await _system_user_id(db)

        if file.processing_status != ProcessingStatus.COMPLETED:
            await _reply(db, hub, thread_id, sampai_uid, message_id,
                        "SAMpai is still indexing this file. Please try again in a moment.")
            return

        question = re.sub(r"@SAMpai\b", "", trigger.content, flags=re.IGNORECASE).strip()
        if not question:
            question = "Can you help me understand this document?"

        if _looks_like_manipulation(question):
            await _reply(db, hub, thread_id, sampai_uid, message_id,
                        f"I'm here to help with **{file.filename}** — what would you like to know about it?")
            return

        # Recent multi-speaker history (exclude discarded), strip manipulations + past refusals.
        recent = (
            await db.execute(
                select(GroupChatMessage)
                .options()
                .where(
                    GroupChatMessage.group_chat_id == thread_id,
                    GroupChatMessage.is_discarded == False,  # noqa: E712
                    GroupChatMessage.seq < trigger.seq,
                )
                .order_by(GroupChatMessage.seq.desc())
                .limit(12)
            )
        ).scalars().all()
        history: list[dict] = []
        for m in reversed(recent):
            if m.role == GroupMessageRole.USER and _looks_like_manipulation(m.content):
                continue
            if m.role == GroupMessageRole.AGENT and _is_refusal(m.content):
                continue
            role = "assistant" if m.role == GroupMessageRole.AGENT else "user"
            history.append({"role": role, "content": m.content})

        doc_id = file.rag_doc_id

    # Typing on
    await hub.broadcast_thread(thread_id, events.agent_typing(thread_id, True))
    try:
        engine = await get_engine(classroom_id)
        answer = await scoped_answer(engine, question, {doc_id} if doc_id else set(), history=history, top_k=15)
    except Exception:
        logger.exception("agent respond failed thread=%s", thread_id)
        answer = "Sorry, I encountered an error while processing your question."
    finally:
        await hub.broadcast_thread(thread_id, events.agent_typing(thread_id, False))

    async with sm() as db:
        await _reply(db, hub, thread_id, sampai_uid, message_id, answer)


async def _reply(db, hub, thread_id: int, sampai_uid: int | None, reply_to_id: int | None, content: str, role=GroupMessageRole.AGENT) -> None:
    msg = await send_message(db, thread_id=thread_id, user_id=sampai_uid, content=content, reply_to_id=reply_to_id, role=role)
    await hub.broadcast_thread(thread_id, events.message_new(GroupMessageOut.model_validate(msg).model_dump(mode="json")))
