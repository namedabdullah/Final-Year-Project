"""Redis sliding-window rate limits for group chat.

- messages: 10 per 10s per (user, thread)
- @SAMpai:  3 per 60s per (user, thread)

Uses an async Redis client created from REDIS_URI (the same broker LightRAG uses).
If Redis is unavailable the limiter fails open (returns allowed) so chat never breaks.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("sampai.ratelimit")

_redis = None


async def init_redis() -> None:
    global _redis
    if _redis is not None:
        return
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(os.getenv("REDIS_URI", "redis://localhost:6379"), decode_responses=True)
        await _redis.ping()
        logger.info("rate-limit Redis connected")
    except Exception as exc:
        logger.warning("rate-limit Redis unavailable (failing open): %s", exc)
        _redis = None


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None


async def _allow(key: str, limit: int, window: float) -> bool:
    if _redis is None:
        return True
    now = time.time()
    try:
        async with _redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {f"{now}": now})
            pipe.zcard(key)
            pipe.expire(key, int(window) + 1)
            results = await pipe.execute()
        return results[2] <= limit
    except Exception:
        return True  # fail open


async def check_message_rate(user_id: int, thread_id: int) -> bool:
    return await _allow(f"rl:msg:{user_id}:{thread_id}", 10, 10.0)


async def check_agent_rate(user_id: int, thread_id: int) -> bool:
    return await _allow(f"rl:agent:{user_id}:{thread_id}", 3, 60.0)
