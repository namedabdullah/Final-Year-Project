"""Phase 0 live smoke test.

Verifies the SAMpai graft end-to-end against the running data services:
  1. The grafted server's create_app() builds (mounts /api/sampai routes).
  2. A per-classroom engine (workspace="classroom_smoke") connects to the
     configured stores (Neo4j + Qdrant + Redis) via the real EngineRegistry path.
  3. The app database (APP_DATABASE_URL) is reachable via asyncpg.

Run AFTER `docker compose -f sampai/docker/docker-compose.dev.yml up -d` and after
`uv pip install -e .[sampai]`:

    .venv/Scripts/python.exe sampai/docker/scripts/smoke_phase0.py

It does NOT call any LLM/embedding API (connectivity only), so it costs no tokens.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace


async def _check_postgres(dsn: str) -> None:
    import asyncpg

    # asyncpg wants a plain postgres:// DSN, not the SQLAlchemy +asyncpg form.
    plain = dsn.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(plain)
    try:
        val = await conn.fetchval("SELECT 1")
        print(f"[smoke] Postgres OK (SELECT 1 -> {val})")
    finally:
        await conn.close()


async def main() -> int:
    import lightrag.api.lightrag_server as srv
    from lightrag.api.config import global_args
    from lightrag.api.sampai.config import SampaiSettings
    from lightrag.api.sampai.registry import EngineRegistry
    from lightrag.kg.shared_storage import (
        initialize_share_data,
        finalize_share_data,
    )

    # Connectivity-only smoke: initialize_storages() never calls the LLM, so a
    # no-op stands in for the real llm_model_func.
    async def _noop_llm(*_args, **_kwargs):
        return ""

    settings = SampaiSettings.load()

    # 1) Postgres reachability (Phase 1 dependency).
    try:
        await _check_postgres(settings.app_database_url)
    except Exception as exc:
        print(f"[smoke] Postgres FAILED: {exc}")
        return 1

    # 2) Build the grafted app (proves mount + reuses the real embedding func).
    initialize_share_data(workers=1)
    app = srv.create_app(global_args)
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/sampai/health" in paths, "SAMpai routes not mounted"
    assert "/query" in paths, "core /query route missing (regression!)"
    print("[smoke] create_app OK (/api/sampai/health mounted, /query intact)")

    args = app.state.sampai_args
    emb = app.state.sampai_embedding_func

    # 3) Real registry path → classroom engine connects to Neo4j/Qdrant/Redis.
    base = SimpleNamespace(
        llm_model_func=_noop_llm,
        llm_model_name=args.llm_model,
    )
    registry = EngineRegistry(args=args, base_rag=base, embedding_func=emb)
    try:
        engine = await registry.get_engine("smoke")
        counts = await engine.get_docs_by_status_counts() if hasattr(
            engine, "get_docs_by_status_counts"
        ) else None
        print(
            f"[smoke] classroom engine OK (workspace={engine.workspace}, "
            f"resident={registry.resident_count})"
        )
    except Exception as exc:
        print(f"[smoke] classroom engine FAILED: {exc}")
        await registry.aclose()
        finalize_share_data()
        return 1

    await registry.aclose()
    finalize_share_data()
    print("[smoke] ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
