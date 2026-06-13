"""SAMpai health + readiness endpoints (no auth — used by compose healthchecks)."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["sampai"])


@router.get("/health")
async def sampai_health():
    """Liveness probe for the SAMpai layer."""
    return {"status": "ok", "service": "sampai"}


@router.get("/ready")
async def sampai_ready(request: Request):
    """Readiness: reports whether the engine registry has been initialized."""
    registry = getattr(request.app.state, "sampai_registry", None)
    return {
        "status": "ok" if registry is not None else "starting",
        "engine_registry": registry is not None,
        "resident_engines": getattr(registry, "resident_count", 0),
    }
