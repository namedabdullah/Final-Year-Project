"""Classroom routes: create, join by code, list, get, leave, delete."""

from __future__ import annotations

import logging
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, is_member
from lightrag.api.sampai.models.classroom import Classroom, classroom_members
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.classroom import ClassroomCreate, ClassroomOut

router = APIRouter(prefix="/classrooms", tags=["sampai-classrooms"])
logger = logging.getLogger("sampai.classrooms")

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _gen_code(n: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


async def _load(db: AsyncSession, classroom_id: int) -> Classroom:
    result = await db.execute(
        select(Classroom)
        .options(selectinload(Classroom.members))
        .where(Classroom.id == classroom_id)
    )
    return result.scalar_one()


@router.post("", response_model=ClassroomOut, status_code=status.HTTP_201_CREATED)
async def create_classroom(
    payload: ClassroomCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Unique join code.
    code = _gen_code()
    while await db.scalar(select(Classroom.id).where(Classroom.code == code)):
        code = _gen_code()

    classroom = Classroom(
        name=payload.name, description=payload.description, code=code, owner_id=user.id
    )
    db.add(classroom)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="You already have a classroom with this name")

    await db.execute(
        classroom_members.insert().values(classroom_id=classroom.id, user_id=user.id)
    )
    await db.commit()
    logger.info("classroom created id=%s code=%s owner=%s", classroom.id, code, user.id)
    return await _load(db, classroom.id)


@router.post("/join/{code}", response_model=ClassroomOut)
async def join_classroom(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = await db.scalar(select(Classroom).where(Classroom.code == code.upper()))
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if await is_member(db, classroom.id, user.id):
        raise HTTPException(status_code=400, detail="Already a member of this classroom")

    await db.execute(
        classroom_members.insert().values(classroom_id=classroom.id, user_id=user.id)
    )
    await db.commit()
    logger.info("classroom join id=%s user=%s", classroom.id, user.id)
    return await _load(db, classroom.id)


@router.get("", response_model=list[ClassroomOut])
async def my_classrooms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Classroom)
        .join(classroom_members, classroom_members.c.classroom_id == Classroom.id)
        .where(classroom_members.c.user_id == user.id)
        .options(selectinload(Classroom.members))
        .order_by(Classroom.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{classroom_id}", response_model=ClassroomOut)
async def get_classroom(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not await is_member(db, classroom_id, user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    return await _load(db, classroom_id)


@router.post("/{classroom_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_classroom(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if classroom.owner_id == user.id:
        raise HTTPException(status_code=400, detail="Owner cannot leave; delete the classroom instead")
    if not await is_member(db, classroom_id, user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    await db.execute(
        delete(classroom_members).where(
            (classroom_members.c.classroom_id == classroom_id)
            & (classroom_members.c.user_id == user.id)
        )
    )
    await db.commit()
    return None


@router.delete("/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classroom(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    classroom = await db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if classroom.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete this classroom")
    # NOTE (Phase 2+): also tear down each file's KB data + R2 objects before delete.
    await db.delete(classroom)
    await db.commit()
    logger.info("classroom deleted id=%s by owner=%s", classroom_id, user.id)
    return None
