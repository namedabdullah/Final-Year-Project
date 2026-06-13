"""Async SQLAlchemy engine + session management for the SAMpai app database.

The engine/sessionmaker are created once at lifespan startup (init_db) and disposed
at shutdown (close_db). Routers depend on :func:`get_db`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> AsyncEngine:
    """Create the global async engine + sessionmaker (idempotent)."""
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
        _sessionmaker = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("SAMpai DB not initialized — call init_db() in lifespan startup")
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, rolls back on error, always closes."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
