"""Engine resolver hook for background tasks.

Background tasks (deck/mindmap generation) run without a ``request``, so they reach
the per-classroom registry through this small settable hook, wired once at startup.
"""

from __future__ import annotations

_resolver = None


def set_engine_resolver(resolver) -> None:
    global _resolver
    _resolver = resolver


async def get_engine(classroom_id: int):
    if _resolver is None:
        raise RuntimeError("engine resolver not set — call set_engine_resolver in startup")
    return await _resolver(classroom_id)
