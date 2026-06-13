"""File status / download schemas (FileOut lives in schemas.classroom)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FileStatusOut(BaseModel):
    file_id: int
    filename: str
    status: str           # our coarse gate: pending|processing|completed|failed
    stage: str | None = None   # live LightRAG sub-stage while processing
    processed_at: datetime | None = None


class DownloadOut(BaseModel):
    download_url: str
