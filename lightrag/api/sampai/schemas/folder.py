"""Folder schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lightrag.api.sampai.schemas.classroom import FileOut


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    classroom_id: int
    files: list[FileOut] = []
