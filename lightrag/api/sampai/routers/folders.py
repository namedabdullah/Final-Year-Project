"""Folder routes: create (owner), list (member), delete (owner)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership, require_owner
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.folder import FolderCreate, FolderOut

router = APIRouter(prefix="/folders", tags=["sampai-folders"])
logger = logging.getLogger("sampai.folders")


async def _load(db: AsyncSession, folder_id: int) -> Folder:
    result = await db.execute(
        select(Folder).options(selectinload(Folder.files)).where(Folder.id == folder_id)
    )
    return result.scalar_one()


@router.post("/classroom/{classroom_id}", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    classroom_id: int,
    payload: FolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_owner(classroom_id, db, user)
    folder = Folder(name=payload.name, classroom_id=classroom_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    logger.info("folder created id=%s classroom=%s", folder.id, classroom_id)
    return await _load(db, folder.id)


@router.get("/classroom/{classroom_id}", response_model=list[FolderOut])
async def list_folders(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_membership(classroom_id, db, user)
    result = await db.execute(
        select(Folder)
        .options(selectinload(Folder.files))
        .where(Folder.classroom_id == classroom_id)
        .order_by(Folder.id)
    )
    return list(result.scalars().all())


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = await db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await require_owner(folder.classroom_id, db, user)
    # NOTE (Phase 2+): tear down each contained file's KB data + R2 objects first.
    await db.delete(folder)
    await db.commit()
    logger.info("folder deleted id=%s", folder_id)
    return None
