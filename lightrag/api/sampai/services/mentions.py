"""@mention parsing — done once at message write time; the stored ``mentions`` JSONB
is the source of truth (never re-parsed from content)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.constants import SAMPAI_USERNAME
from lightrag.api.sampai.models.group_chat import GroupChatMember
from lightrag.api.sampai.models.user import User

_MENTION = re.compile(r"@(\w+)")


async def parse_mentions(content: str, thread_id: int, db: AsyncSession) -> list[dict]:
    """Resolve @tokens against thread members.

    Returns ``[{"kind":"agent","username":"SAMpai"} | {"kind":"user","user_id","username"}]``.
    @SAMpai is recognized case-insensitively; unknown tokens are dropped; deduped.
    """
    tokens = _MENTION.findall(content)
    if not tokens:
        return []

    members = (
        await db.execute(
            select(User).join(GroupChatMember, GroupChatMember.user_id == User.id).where(
                GroupChatMember.group_chat_id == thread_id
            )
        )
    ).scalars().all()
    by_name = {m.username.lower(): m for m in members}

    out: list[dict] = []
    seen: set[str] = set()
    for tok in tokens:
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        if key == SAMPAI_USERNAME.lower():
            out.append({"kind": "agent", "username": SAMPAI_USERNAME})
        elif key in by_name:
            u = by_name[key]
            out.append({"kind": "user", "user_id": u.id, "username": u.username})
    return out
