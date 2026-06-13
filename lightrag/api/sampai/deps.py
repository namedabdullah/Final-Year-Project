"""Shared FastAPI dependencies: current user + classroom access guards."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.models.classroom import Classroom, classroom_members
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.security import decode_access_token

# auto_error=False so we can return a clean 401 (not 403) when the header is absent.
_bearer = HTTPBearer(auto_error=False)


def _jwt_secret(request: Request) -> str:
    settings = request.app.state.sampai_settings
    return settings.app_jwt_secret


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(creds.credentials, _jwt_secret(request))
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


async def is_member(db: AsyncSession, classroom_id: int, user_id: int) -> bool:
    return bool(
        await db.scalar(
            select(
                exists().where(
                    (classroom_members.c.classroom_id == classroom_id)
                    & (classroom_members.c.user_id == user_id)
                )
            )
        )
    )


async def require_membership(
    classroom_id: int, db: AsyncSession, user: User
) -> Classroom:
    """Return the classroom if `user` is a member, else 404/403."""
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not await is_member(db, classroom_id, user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    return classroom


async def require_owner(classroom_id: int, db: AsyncSession, user: User) -> Classroom:
    """Return the classroom if `user` owns it, else 404/403."""
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if classroom.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the classroom owner can do this")
    return classroom
