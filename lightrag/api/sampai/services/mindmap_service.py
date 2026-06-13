"""Mindmap generation (shared hierarchical tree) + per-user node summaries & chat.

- Tree generation uses the KG-heavy scoped mix context + an OpenAI structured-output
  call (recursive json_schema) to produce a topic tree, then assembles the stable
  ``tree_data`` shape (version 2) with ``n_root`` / ``n_0001`` ids.
- Node summaries and follow-up chat are per-user and file-scoped via the gateway.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import time
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.models.file import File
from lightrag.api.sampai.models.mindmap import (
    Mindmap,
    MindmapMessageRole,
    MindmapNodeChat,
    MindmapStatus,
)
from lightrag.api.sampai.services.engine_access import get_engine
from lightrag.api.sampai.services.rag_gateway import scoped_answer, scoped_mix_context

logger = logging.getLogger("sampai.mindmap")

MAX_DEPTH = 5
MAX_CHILDREN = 7

_TREE_SEED = (
    "List the document's main topic, the major sub-topics it covers, and the relationships "
    "between them. Include named entities, key concepts, and concrete examples. Be exhaustive — "
    "this is the source material for a hierarchical mindmap."
)

# Recursive json_schema for OpenAI structured outputs.
_NODE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "2-6 word noun phrase"},
        "description": {"type": "string", "description": "1-2 sentences from the document"},
        "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
    },
    "required": ["topic", "description", "children"],
    "additionalProperties": False,
}
_TREE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "description": {"type": "string"},
        "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
    },
    "required": ["topic", "description", "children"],
    "additionalProperties": False,
    "$defs": {"node": _NODE_SCHEMA},
}

_TREE_SYSTEM = (
    "You build a hierarchical mindmap from study material. The root is the document's core "
    "topic (2-5 words, NOT the filename). Structure rules: root has 2-8 children (major "
    f"themes); each non-leaf node has 2-{MAX_CHILDREN} children; max depth {MAX_DEPTH} below "
    "root. Expand every branch until leaves are CONCRETE atomic concepts (a technique, "
    "definition, mechanism, formula, or example) — never leave an abstract category "
    "('Types', 'Examples') as a leaf. Each topic: 2-6 word noun phrase. Each description: "
    "1-2 sentences drawn strictly from the document. Do NOT invent topics absent from the "
    "source. Output JSON only."
)


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.getenv("LLM_BINDING_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("LLM_BINDING_HOST", "https://api.openai.com/v1"),
    )


# ── tree assembly ────────────────────────────────────────────────────────────
def _assemble(root_topic: str, root_desc: str, raw_children: list) -> dict:
    counter = itertools.count(1)

    def build(node: dict, depth: int) -> dict | None:
        topic = (node.get("topic") or "").strip()
        if not topic:
            return None
        kids_raw = node.get("children") or []
        kids = []
        if depth < MAX_DEPTH:
            for k in kids_raw[:MAX_CHILDREN]:
                built = build(k, depth + 1)
                if built:
                    kids.append(built)
        return {
            "id": f"n_{next(counter):04d}",
            "topic": topic,
            "description": (node.get("description") or "").strip(),
            "depth": depth,
            "has_children": bool(kids),
            "children": kids,
        }

    root_children = [c for c in (build(k, 1) for k in (raw_children or [])[:8]) if c]
    return {
        "version": 2,
        "root": {
            "id": "n_root",
            "topic": root_topic.strip(),
            "description": root_desc.strip(),
            "depth": 0,
            "has_children": bool(root_children),
            "children": root_children,
        },
    }


def _count_nodes(node: dict) -> int:
    return 1 + sum(_count_nodes(c) for c in node.get("children", []))


def find_node(tree_data: dict, node_id: str) -> Optional[dict]:
    if not tree_data or "root" not in tree_data:
        return None

    def walk(n: dict) -> Optional[dict]:
        if n.get("id") == node_id:
            return n
        for c in n.get("children", []):
            r = walk(c)
            if r:
                return r
        return None

    return walk(tree_data["root"])


# ── row helpers ──────────────────────────────────────────────────────────────
async def load_or_create(db: AsyncSession, file_id: int, classroom_id: int, force: bool) -> Mindmap:
    mm = (await db.execute(select(Mindmap).where(Mindmap.file_id == file_id))).scalar_one_or_none()
    if mm is None:
        mm = Mindmap(file_id=file_id, classroom_id=classroom_id, status=MindmapStatus.PENDING, tree_data={}, node_count=0)
        db.add(mm)
        await db.flush()
    elif force:
        mm.status = MindmapStatus.PENDING
        mm.tree_data = {}
        mm.node_count = 0
        mm.root_topic = None
        mm.root_description = None
        mm.error_message = None
    return mm


async def get_by_file(db: AsyncSession, file_id: int) -> Optional[Mindmap]:
    return (await db.execute(select(Mindmap).where(Mindmap.file_id == file_id))).scalar_one_or_none()


# ── tree generation (background) ─────────────────────────────────────────────
async def generate_mindmap_task(file_id: int, classroom_id: int, force: bool):
    sm = get_sessionmaker()
    async with sm() as db:
        mm = await load_or_create(db, file_id, classroom_id, force)
        if mm.status == MindmapStatus.READY and not force:
            return
        mm.status = MindmapStatus.GENERATING
        mindmap_id = mm.id
        await db.commit()
        file = await db.get(File, file_id)
        filename = file.filename if file else "document"
        doc_id = file.rag_doc_id if file else None

    try:
        engine = await get_engine(classroom_id)
        context = await scoped_mix_context(engine, _TREE_SEED, {doc_id} if doc_id else set(), "hard")
        if not context or context == "(no context retrieved)":
            raise RuntimeError("No content retrieved for this file")

        t0 = time.time()
        resp = await _client().chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _TREE_SYSTEM},
                {"role": "user", "content": f"FILENAME: {filename}\n\nDOCUMENT CONTEXT:\n{context[:32000]}"},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "mindmap", "strict": True, "schema": _TREE_SCHEMA}},
            temperature=0.3,
        )
        data = json.loads(resp.choices[0].message.content)
        tree = _assemble(data.get("topic", filename), data.get("description", ""), data.get("children", []))
        if len(tree["root"]["children"]) < 2:
            raise RuntimeError("Document too short for a useful mindmap (fewer than 2 top-level topics)")

        async with sm() as db:
            mm = await db.get(Mindmap, mindmap_id)
            mm.tree_data = tree
            mm.root_topic = tree["root"]["topic"]
            mm.root_description = tree["root"]["description"]
            mm.node_count = _count_nodes(tree["root"])
            mm.status = MindmapStatus.READY
            mm.error_message = None
            mm.generation_meta = {
                "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                "elapsed_s": round(time.time() - t0, 2),
                "context_chars": len(context),
            }
            await db.commit()
        logger.info("mindmap %s ready (%d nodes)", mindmap_id, _count_nodes(tree["root"]))
    except Exception as exc:
        logger.exception("mindmap %s failed", mindmap_id)
        async with sm() as db:
            mm = await db.get(Mindmap, mindmap_id)
            if mm is not None:
                mm.status = MindmapStatus.FAILED
                mm.error_message = str(exc)[:500]
                await db.commit()


# ── per-user node explore + chat ─────────────────────────────────────────────
_locks: dict[tuple[int, int], asyncio.Semaphore] = {}
_locks_mutex = asyncio.Lock()


async def _lock(mindmap_id: int, user_id: int) -> asyncio.Semaphore:
    async with _locks_mutex:
        return _locks.setdefault((mindmap_id, user_id), asyncio.Semaphore(1))


async def explore_node(db: AsyncSession, mindmap_id: int, node_id: str, user_id: int):
    """Returns (already_explored, last_message_id, marker_id, placeholder_id)."""
    existing = (
        await db.execute(
            select(MindmapNodeChat)
            .where(
                MindmapNodeChat.mindmap_id == mindmap_id,
                MindmapNodeChat.user_id == user_id,
                MindmapNodeChat.node_id == node_id,
                MindmapNodeChat.role == MindmapMessageRole.ASSISTANT,
                MindmapNodeChat.message_metadata["pending"].as_string() != "true",
            )
            .order_by(MindmapNodeChat.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return True, existing.id, None, None

    marker = MindmapNodeChat(mindmap_id=mindmap_id, user_id=user_id, node_id=node_id, role=MindmapMessageRole.MARKER, content="", message_metadata={"node_id": node_id})
    db.add(marker)
    await db.flush()
    placeholder = MindmapNodeChat(mindmap_id=mindmap_id, user_id=user_id, node_id=node_id, role=MindmapMessageRole.ASSISTANT, content="", message_metadata={"pending": True, "node_id": node_id})
    db.add(placeholder)
    await db.flush()
    return False, None, marker.id, placeholder.id


async def generate_node_summary_task(mindmap_id: int, node_id: str, placeholder_id: int, file_id: int, classroom_id: int, user_id: int):
    sem = await _lock(mindmap_id, user_id)
    async with sem:
        sm = get_sessionmaker()
        try:
            async with sm() as db:
                mm = await db.get(Mindmap, mindmap_id)
                file = await db.get(File, file_id)
                node = find_node(mm.tree_data or {}, node_id) if mm else None
                if node is None or file is None:
                    raise RuntimeError("node or file not found")
                root_topic = mm.root_topic or "the document"
                doc_id = file.rag_doc_id

            engine = await get_engine(classroom_id)
            question = (
                f'In the context of "{root_topic}" (from "{file.filename}"), explain the sub-topic '
                f'"{node["topic"]}" in detail. {node.get("description", "")} Include key concepts, '
                "examples, definitions, and relationships to neighbouring topics."
            )
            answer = await scoped_answer(engine, question, {doc_id} if doc_id else set(), top_k=15)

            async with sm() as db:
                ph = await db.get(MindmapNodeChat, placeholder_id)
                if ph:
                    ph.content = answer or "Sorry, I couldn't generate a summary for this topic."
                    ph.message_metadata = {"node_id": node_id}
                    await db.commit()
        except Exception as exc:
            logger.exception("node summary failed mindmap=%s node=%s", mindmap_id, node_id)
            async with sm() as db:
                ph = await db.get(MindmapNodeChat, placeholder_id)
                if ph:
                    ph.content = "Sorry, I couldn't generate a summary for this topic. Please try again."
                    ph.message_metadata = {"node_id": node_id, "error": str(exc)[:200]}
                    await db.commit()


async def ask_in_thread(db: AsyncSession, mindmap_id: int, user_id: int, content: str, active_node_id: str | None, file_id: int, classroom_id: int) -> MindmapNodeChat:
    mm = await db.get(Mindmap, mindmap_id)
    file = await db.get(File, file_id)

    active_label = None
    if active_node_id and mm and mm.tree_data:
        node = find_node(mm.tree_data, active_node_id)
        active_label = node["topic"] if node else None

    db.add(MindmapNodeChat(mindmap_id=mindmap_id, user_id=user_id, node_id=active_node_id, role=MindmapMessageRole.USER, content=content, message_metadata={"active_node_id": active_node_id}))
    await db.flush()

    # last 10 non-marker messages as history
    rows = (
        await db.execute(
            select(MindmapNodeChat)
            .where(
                MindmapNodeChat.mindmap_id == mindmap_id,
                MindmapNodeChat.user_id == user_id,
                MindmapNodeChat.role != MindmapMessageRole.MARKER,
            )
            .order_by(MindmapNodeChat.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    history = [
        {"role": ("assistant" if m.role == MindmapMessageRole.ASSISTANT else "user"), "content": m.content}
        for m in reversed(rows)
        if m.content
    ]

    augmented = f"[Currently exploring: {active_label}]\n\n{content}" if active_label else content
    try:
        engine = await get_engine(classroom_id)
        answer = await scoped_answer(engine, augmented, {file.rag_doc_id} if file and file.rag_doc_id else set(), history=history, top_k=10)
    except Exception:
        logger.exception("mindmap ask failed mindmap=%s", mindmap_id)
        answer = "Sorry, I encountered an error while searching the document. Please try again."

    assistant = MindmapNodeChat(mindmap_id=mindmap_id, user_id=user_id, node_id=active_node_id, role=MindmapMessageRole.ASSISTANT, content=answer, message_metadata={"active_node_id": active_node_id})
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return assistant
