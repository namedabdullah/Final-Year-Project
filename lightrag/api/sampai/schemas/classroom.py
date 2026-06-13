"""Classroom + folder schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lightrag.api.sampai.schemas.user import UserOut


class ClassroomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ClassroomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None
    code: str
    owner_id: int
    members: list[UserOut] = []


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_url: str
    file_type: str | None = None
    processing_status: str
    description: str | None = None

    @field_validator("processing_status", mode="before")
    @classmethod
    def _status_value(cls, v: object) -> object:
        return v.value if isinstance(v, Enum) else v
