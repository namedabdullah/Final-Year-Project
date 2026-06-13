"""SAMpai extension — the multi-tenant classroom layer grafted onto the LightRAG server.

ALL SAMpai backend code is isolated in this subpackage. The only edits to upstream
files live in ``lightrag/api/lightrag_server.py`` (recorded in ``CHANGES.md``) and call
the three functions exported here:

- ``mount_sampai(app, *, args, embedding_func, config_cache)`` — router + state wiring
  at app-build time (called once from ``create_app`` after the core routers).
- ``sampai_startup(app, args, embedding_func, config_cache, rag)`` — lifespan startup
  hook (builds the per-classroom engine registry; engines are created lazily).
- ``sampai_shutdown(app)`` — lifespan shutdown hook (finalizes resident engines).

The graft is intentionally fail-soft: if this subpackage or its optional dependencies
are missing, the server logs a warning and the original LightRAG pipeline keeps working.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sampai")

#: All SAMpai routes live under this prefix so they never collide with the
#: server's own routes (/documents, /query, /graph, /quiz, /login, /webui).
SAMPAI_PREFIX = "/api/sampai"


def mount_sampai(app, *, args, embedding_func, config_cache) -> None:
    """Register SAMpai routers and stash build-time context on ``app.state``.

    Called once from ``create_app()`` after the core routers are included. This does
    NOT open any connections — that happens lazily / in :func:`sampai_startup`.
    """
    from lightrag.api.sampai.config import SampaiSettings
    from lightrag.api.sampai.realtime.hub import ConnectionManager
    from lightrag.api.sampai.routers import (
        announcements,
        auth,
        chat,
        classrooms,
        files,
        flashcards,
        folder_quizzes,
        folders,
        groupchat,
        health,
        mindmap,
        quizzes,
    )

    settings = SampaiSettings.load()
    app.state.sampai_settings = settings
    app.state.sampai_args = args
    app.state.sampai_embedding_func = embedding_func
    app.state.sampai_config_cache = config_cache
    app.state.sampai_hub = ConnectionManager()  # in-process WebSocket hub

    for module in (health, auth, classrooms, folders, files, chat, flashcards, mindmap, groupchat, announcements, quizzes, folder_quizzes):
        app.include_router(module.router, prefix=SAMPAI_PREFIX)
    logger.info("SAMpai routers mounted under %s", SAMPAI_PREFIX)


async def sampai_startup(app, args, embedding_func, config_cache, rag) -> None:
    """Lifespan startup: build the per-classroom engine registry.

    Engines are created lazily on first classroom access, so this does not connect to
    Neo4j/Qdrant/Redis here. (App DB / Redis / R2 clients are wired in Phase 1-2.)
    """
    from lightrag.api.sampai.db import init_db
    from lightrag.api.sampai.integrations import r2
    from lightrag.api.sampai.registry import EngineRegistry
    from lightrag.api.sampai.services.ingestion import IngestionService

    settings = getattr(app.state, "sampai_settings", None)

    # App database (Postgres) — engine + sessionmaker for all SAMpai routers.
    if settings is not None:
        init_db(settings.app_database_url)
        logger.info("SAMpai app database engine initialized")
        r2.init_r2(settings)
        logger.info("SAMpai R2 client initialized (bucket=%s)", settings.r2_bucket)

    registry = EngineRegistry(
        args=args,
        base_rag=rag,
        embedding_func=embedding_func,
        idle_ttl=getattr(settings, "app_engine_idle_ttl", 1800),
        max_resident=getattr(settings, "app_max_resident_engines", 8),
    )
    app.state.sampai_registry = registry
    logger.info("SAMpai engine registry ready (lazy per-classroom engines)")

    # Let background tasks (deck/mindmap generation) reach the registry.
    from lightrag.api.sampai.services.engine_access import set_engine_resolver

    set_engine_resolver(registry.get_engine)

    ingestion = IngestionService(registry.get_engine)
    ingestion.start()
    app.state.sampai_ingestion = ingestion
    logger.info("SAMpai ingestion service started")

    # Rate-limit Redis (group chat). Fails open if unavailable.
    from lightrag.api.sampai.realtime.ratelimit import init_redis

    await init_redis()


async def sampai_shutdown(app) -> None:
    """Lifespan shutdown: stop ingestion, finalize engines, close the app DB."""
    ingestion = getattr(app.state, "sampai_ingestion", None)
    if ingestion is not None:
        await ingestion.stop()
        logger.info("SAMpai ingestion service stopped")

    from lightrag.api.sampai.realtime.ratelimit import close_redis

    await close_redis()

    registry = getattr(app.state, "sampai_registry", None)
    if registry is not None:
        await registry.aclose()
        logger.info("SAMpai engine registry closed")

    from lightrag.api.sampai.db import close_db

    await close_db()
    logger.info("SAMpai app database engine disposed")


__all__ = ["mount_sampai", "sampai_startup", "sampai_shutdown", "SAMPAI_PREFIX"]
