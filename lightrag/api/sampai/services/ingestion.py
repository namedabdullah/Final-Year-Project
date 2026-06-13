"""Document ingestion: R2 download -> on-disk temp -> LightRAG parse+index
(MinerU/Docling/legacy via the server's own pipeline_index_file) -> status + summary.

A small lifespan-managed bounded queue runs ingestion off the request path so the
upload endpoint returns immediately. Concurrency is intentionally low (heavy MinerU
/ entity-extraction work); the LightRAG pipeline parallelizes internally.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.integrations import r2
from lightrag.api.sampai.models.file import File, ProcessingStatus

logger = logging.getLogger("sampai.ingestion")

INGEST_CONCURRENCY = 1  # sequential by default; raise once GPU MinerU is in play

_SUMMARY_SYSTEM = (
    "You are a concise academic assistant. In 2-3 sentences, summarize the document's "
    "main topic, key concepts, and scope. Plain text only."
)


@dataclass
class _Job:
    classroom_id: int
    file_id: int


class IngestionService:
    def __init__(self, get_engine) -> None:
        self._get_engine = get_engine
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        for i in range(INGEST_CONCURRENCY):
            self._workers.append(asyncio.create_task(self._worker(i), name=f"sampai-ingest-{i}"))
        logger.info("ingestion workers started (n=%d)", INGEST_CONCURRENCY)

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            try:
                await w
            except (asyncio.CancelledError, Exception):
                pass
        self._workers.clear()

    def enqueue(self, classroom_id: int, file_id: int) -> None:
        self._queue.put_nowait(_Job(classroom_id, file_id))

    # ── worker ───────────────────────────────────────────────────────────────
    async def _worker(self, idx: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            except Exception:
                logger.exception("ingestion worker %d failed for file_id=%s", idx, job.file_id)
                await self._mark_failed(job.file_id)
            finally:
                self._queue.task_done()

    async def _process(self, job: _Job) -> None:
        sm = get_sessionmaker()

        # Load file + flip to PROCESSING.
        async with sm() as db:
            file = await db.get(File, job.file_id)
            if file is None:
                logger.warning("ingest: file %s vanished", job.file_id)
                return
            file.processing_status = ProcessingStatus.PROCESSING
            await db.commit()
            file_key, filename, working_subdir = file.file_key, file.filename, job.classroom_id

        engine = await self._get_engine(job.classroom_id)

        # Download original bytes from R2 and write to the LightRAG input dir under
        # the engine's workspace — this is exactly where the MinerU/Docling parse
        # workers resolve the source file by basename (see
        # pipeline._resolve_source_file_for_parser: input_dir/<workspace>/<name>).
        # The file must persist through processing (the parser reads it lazily).
        from lightrag.utils_pipeline import input_dir_path

        content = await r2.get_bytes(file_key)
        input_dir = input_dir_path() / engine.workspace
        input_dir.mkdir(parents=True, exist_ok=True)
        disk_path = input_dir / f"{job.file_id}_{filename}"
        await asyncio.to_thread(disk_path.write_bytes, content)

        track_id = f"sampai-{job.file_id}-{uuid.uuid4().hex[:8]}"

        # Reuse the server's exact parse+index path (handles MinerU/Docling/legacy
        # dispatch via LIGHTRAG_PARSER + triggers processing to a terminal state).
        from lightrag.api.routers.document_routes import pipeline_index_file

        await pipeline_index_file(engine, disk_path, track_id)

        # Resolve the resulting doc + status by our track_id.
        from lightrag.base import DocStatus

        docs = await engine.aget_docs_by_track_id(track_id)
        doc_id = next(iter(docs), None)
        doc_status = docs.get(doc_id) if doc_id else None

        async with sm() as db:
            file = await db.get(File, job.file_id)
            if file is None:
                return
            if doc_id:
                file.rag_doc_id = doc_id
            file.track_id = track_id

            status = getattr(doc_status, "status", None)
            if status == DocStatus.PROCESSED:
                file.processing_status = ProcessingStatus.COMPLETED
                file.processed_at = datetime.utcnow()
                file.description = await self._summarize(engine, doc_id)
                logger.info("ingest OK file_id=%s doc_id=%s", job.file_id, doc_id)
            elif status == DocStatus.FAILED:
                file.processing_status = ProcessingStatus.FAILED
                logger.warning(
                    "ingest FAILED file_id=%s err=%s",
                    job.file_id,
                    getattr(doc_status, "error_msg", None),
                )
            else:
                # Shouldn't happen (pipeline ran to terminal); leave processing for retry.
                file.processing_status = ProcessingStatus.FAILED
                logger.warning("ingest indeterminate file_id=%s status=%s", job.file_id, status)
            await db.commit()

    async def _summarize(self, engine, doc_id: str | None) -> str | None:
        if not doc_id:
            return None
        try:
            doc = await engine.full_docs.get_by_id(doc_id)
            content = (doc or {}).get("content") if isinstance(doc, dict) else None
            if not content:
                return None
            summary = await engine.llm_model_func(
                f"Summarize this document:\n\n{content[:4000]}",
                system_prompt=_SUMMARY_SYSTEM,
            )
            return (summary or "").strip() or None
        except Exception:
            logger.warning("summary generation failed for doc_id=%s", doc_id, exc_info=True)
            return None

    async def _mark_failed(self, file_id: int) -> None:
        try:
            sm = get_sessionmaker()
            async with sm() as db:
                file = await db.get(File, file_id)
                if file is not None:
                    file.processing_status = ProcessingStatus.FAILED
                    await db.commit()
        except Exception:
            logger.exception("could not mark file %s FAILED", file_id)


async def delete_file_kb(engine, doc_id: str | None) -> None:
    """Remove a file's data from the classroom knowledge base (best-effort)."""
    if not doc_id:
        return
    try:
        await engine.adelete_by_doc_id(doc_id)
    except Exception:
        logger.warning("KB delete failed for doc_id=%s", doc_id, exc_info=True)
