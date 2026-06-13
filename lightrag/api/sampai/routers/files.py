"""File routes: upload, list, get, status, reprocess, download, delete."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership, require_owner
from lightrag.api.sampai.integrations import r2
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.classroom import FileOut
from lightrag.api.sampai.schemas.file import DownloadOut, FileStatusOut
from lightrag.api.sampai.services.ingestion import delete_file_kb

router = APIRouter(prefix="/files", tags=["sampai-files"])
logger = logging.getLogger("sampai.files")

ALLOWED_EXT = {".pdf", ".docx", ".pptx", ".txt", ".xlsx"}


async def _folder_classroom(db: AsyncSession, folder_id: int) -> tuple[Folder, int]:
    folder = await db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder, folder.classroom_id


async def _file_classroom(db: AsyncSession, file_id: int) -> tuple[File, int]:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return file, folder.classroom_id


@router.post("/upload/{folder_id}", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    folder_id: int,
    upload: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _folder_classroom(db, folder_id)
    await require_membership(classroom_id, db, user)

    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported: {', '.join(sorted(ALLOWED_EXT))}",
        )

    content = await upload.read()
    settings = request.app.state.sampai_settings
    max_bytes = settings.app_upload_max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.app_upload_max_mb} MB")

    key = f"classrooms/{classroom_id}/folders/{folder_id}/{upload.filename}"
    obj = await r2.put_object(key, content, upload.content_type)

    file = File(
        filename=upload.filename,
        file_url=obj.url,
        file_key=key,
        file_type=ext.lstrip("."),
        file_size=len(content),
        processing_status=ProcessingStatus.PENDING,
        folder_id=folder_id,
    )
    db.add(file)
    await db.commit()
    await db.refresh(file)

    request.app.state.sampai_ingestion.enqueue(classroom_id, file.id)
    logger.info("upload file_id=%s folder=%s classroom=%s", file.id, folder_id, classroom_id)
    return file


@router.get("/folder/{folder_id}", response_model=list[FileOut])
async def list_files(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, classroom_id = await _folder_classroom(db, folder_id)
    await require_membership(classroom_id, db, user)
    result = await db.execute(select(File).where(File.folder_id == folder_id).order_by(File.id))
    return list(result.scalars().all())


@router.get("/{file_id}", response_model=FileOut)
async def get_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    return file


@router.get("/{file_id}/status", response_model=FileStatusOut)
async def file_status(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)

    stage = None
    if file.processing_status == ProcessingStatus.PROCESSING and file.track_id:
        # Surface the live LightRAG sub-stage (parsing/analyzing/processing) for the UI.
        try:
            engine = await request.app.state.sampai_registry.get_engine(classroom_id)
            docs = await engine.aget_docs_by_track_id(file.track_id)
            ds = next(iter(docs.values()), None)
            stage = getattr(getattr(ds, "status", None), "value", None)
        except Exception:
            stage = None

    return FileStatusOut(
        file_id=file.id,
        filename=file.filename,
        status=file.processing_status.value,
        stage=stage,
        processed_at=file.processed_at,
    )


@router.post("/{file_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    file.processing_status = ProcessingStatus.PENDING
    await db.commit()
    request.app.state.sampai_ingestion.enqueue(classroom_id, file.id)
    return {"detail": "reprocessing started", "file_id": file.id}


@router.get("/{file_id}/download", response_model=DownloadOut)
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    url = await r2.presigned_get_url(file.file_key)
    return DownloadOut(download_url=url)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_owner(classroom_id, db, user)

    # External cleanup first (best-effort), then the DB row.
    try:
        await r2.delete_object(file.file_key)
    except Exception:
        logger.warning("R2 delete failed for file_id=%s", file_id, exc_info=True)
    if file.rag_doc_id:
        engine = await request.app.state.sampai_registry.get_engine(classroom_id)
        await delete_file_kb(engine, file.rag_doc_id)

    await db.delete(file)
    await db.commit()
    logger.info("deleted file_id=%s", file_id)
    return None
