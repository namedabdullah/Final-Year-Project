# SAMpai — Upstream Edit Ledger

This file is the single source of truth for **every change made to upstream LightRAG
files** outside the `lightrag/api/sampai/` subpackage. Keep it exhaustive so a future
rebase onto `HKUDS/LightRAG` is mechanical. All edits are wrapped in
`# --- SAMpai --- … # --- end SAMpai ---` fences in the source.

> **Off-limits (never edit):** `CLAUDE.md`, `AGENTS.md`.
> **Diff budget (clean-source gate):** ≤ ~20 changed lines in `lightrag_server.py`;
> **0 lines** in `lightrag/lightrag.py`, `operate.py`, `kg/`, `parser/`, `quiz/`.

---

## `lightrag/api/lightrag_server.py`

The SAMpai graft is **fail-soft**: the import is wrapped in try/except, and every call
site is guarded by `_SAMPAI_AVAILABLE`, so if the subpackage or its optional deps are
missing the original server boots unchanged.

1. **Module imports (top of file)** — fenced block:
   ```python
   # --- SAMpai ---
   try:
       from lightrag.api.sampai import mount_sampai, sampai_startup, sampai_shutdown
       _SAMPAI_AVAILABLE = True
   except Exception as _sampai_exc:  # optional extension / deps
       _SAMPAI_AVAILABLE = False
       logger.warning(f"SAMpai extension not loaded: {_sampai_exc}")
   # --- end SAMpai ---
   ```

2. **Inside `create_app().lifespan` (~after `await rag.check_and_migrate_data()`)** —
   startup hook before `yield`:
   ```python
   # --- SAMpai ---
   if _SAMPAI_AVAILABLE:
       await sampai_startup(app, args, embedding_func, config_cache, rag)
   # --- end SAMpai ---
   ```
   And in the `finally:` block, before `await rag.finalize_storages()`:
   ```python
   # --- SAMpai ---
   if _SAMPAI_AVAILABLE:
       await sampai_shutdown(app)
   # --- end SAMpai ---
   ```

3. **After the core `app.include_router(...)` calls (~line 2020)** — mount hook:
   ```python
   # --- SAMpai ---
   if _SAMPAI_AVAILABLE:
       mount_sampai(app, args=args, embedding_func=embedding_func, config_cache=config_cache)
   # --- end SAMpai ---
   ```

## `pyproject.toml` (repo root)
- Added `[project.optional-dependencies] sampai = [...]` (SQLAlchemy/asyncpg/alembic/PyJWT/
  passlib[argon2]/boto3/nh3/redis/python-multipart/pydantic-settings). Additive only.

## `env.example` (repo root)
- Added the `APP_*` / `R2_*` block consumed by `lightrag/api/sampai/config.py:SampaiSettings`.
  Additive only; the server ignores these vars.

---

*Nothing else upstream is touched. New code lives entirely under `lightrag/api/sampai/`.*
