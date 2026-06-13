"""In-process WebSocket connection hub.

Tracks per-thread rooms (for group-chat events) and a per-user registry (for
user-level events like invites). Presence is derived from who's connected to a
thread room. Single-process by design (the SAMpai server runs 1 worker); Redis
pub/sub fan-out would slot in here as the multi-instance scaling seam.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from starlette.websockets import WebSocket

logger = logging.getLogger("sampai.hub")


class ConnectionManager:
    def __init__(self) -> None:
        self._thread_rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._thread_user: dict[WebSocket, tuple[int, int]] = {}  # ws -> (thread_id, user_id)
        self._user_conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    # ── thread rooms ─────────────────────────────────────────────────────────
    async def join_thread(self, ws: WebSocket, thread_id: int, user_id: int) -> None:
        async with self._lock:
            self._thread_rooms[thread_id].add(ws)
            self._thread_user[ws] = (thread_id, user_id)

    async def leave_thread(self, ws: WebSocket) -> tuple[int, int] | None:
        async with self._lock:
            info = self._thread_user.pop(ws, None)
            if info:
                self._thread_rooms[info[0]].discard(ws)
            return info

    def presence_for_thread(self, thread_id: int) -> list[int]:
        return sorted({self._thread_user[ws][1] for ws in self._thread_rooms.get(thread_id, set()) if ws in self._thread_user})

    async def broadcast_thread(self, thread_id: int, event: dict, exclude: WebSocket | None = None) -> None:
        payload = json.dumps(event)
        for ws in list(self._thread_rooms.get(thread_id, set())):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                await self.leave_thread(ws)

    # ── user registry ───────────────────────────────────────────────────────
    async def register_user(self, ws: WebSocket, user_id: int) -> None:
        async with self._lock:
            self._user_conns[user_id].add(ws)

    async def unregister_user(self, ws: WebSocket, user_id: int) -> None:
        async with self._lock:
            self._user_conns[user_id].discard(ws)

    async def send_user(self, user_id: int, event: dict) -> None:
        payload = json.dumps(event)
        for ws in list(self._user_conns.get(user_id, set())):
            try:
                await ws.send_text(payload)
            except Exception:
                await self.unregister_user(ws, user_id)
