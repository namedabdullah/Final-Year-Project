"""Phase 6 acceptance test (live :9621): announcements + comments + bell.

Verifies nh3 sanitization (XSS stripped), owner-only posting, member commenting,
author/owner delete rules, empty-content 422s, and that new announcements/comments
fan out over the /ws/user socket for the bell.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets

BASE = "http://127.0.0.1:9621/api/sampai"
WS_USER = "ws://127.0.0.1:9621/api/sampai/group-chat/ws/user"
A = "/announcements"
_passed = _failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  PASS  {name}")
    else:
        _failed += 1; print(f"  FAIL  {name}  {extra}")


class WSClient:
    def __init__(self, url):
        self.url, self.events, self._ws, self._task = url, [], None, None

    async def __aenter__(self):
        self._ws = await websockets.connect(self.url, max_size=2**22)
        self._task = asyncio.create_task(self._recv())
        return self

    async def _recv(self):
        try:
            async for raw in self._ws:
                self.events.append(json.loads(raw))
        except Exception:
            pass

    async def __aexit__(self, *a):
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def wait_for(self, pred, timeout=8):
        start = time.time()
        while time.time() - start < timeout:
            for e in self.events:
                if pred(e):
                    return e
            await asyncio.sleep(0.2)
        return None


async def main() -> int:
    sfx = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        async def su(t):
            u = {"username": f"{t}_{sfx}", "email": f"{t}_{sfx}@x.com", "password": "Passw0rd123"}
            await c.post("/auth/signup", json=u)
            r = await c.post("/auth/login", json={"email": u["email"], "password": u["password"]})
            return r.json()["access_token"], r.json()["user"]["id"]

        a_tok, a_id = await su("a")  # owner
        b_tok, b_id = await su("b")  # member
        cc_tok, _ = await su("c")    # non-member
        AH = {"Authorization": f"Bearer {a_tok}"}
        BH = {"Authorization": f"Bearer {b_tok}"}
        CH = {"Authorization": f"Bearer {cc_tok}"}

        cls = (await c.post("/classrooms", headers=AH, json={"name": f"Ann {sfx}"})).json()
        cid, code = cls["id"], cls["code"]
        await c.post(f"/classrooms/join/{code}", headers=BH)

        # Connect A and B to the user socket for bell checks.
        async with WSClient(f"{WS_USER}?token={a_tok}") as aws, WSClient(f"{WS_USER}?token={b_tok}") as bws:
            await asyncio.sleep(0.5)

            # ── owner-only posting ──
            r = await c.post(f"{A}/classrooms/{cid}", headers=BH, json={"content": "<p>hi</p>"})
            check("member cannot post (403)", r.status_code == 403, str(r.status_code))
            r = await c.post(f"{A}/classrooms/{cid}", headers=CH, json={"content": "<p>hi</p>"})
            check("non-member cannot post (403)", r.status_code == 403, str(r.status_code))

            # empty after sanitize -> 422
            r = await c.post(f"{A}/classrooms/{cid}", headers=AH, json={"content": "<p>&nbsp;</p>"})
            check("empty announcement -> 422", r.status_code == 422, str(r.status_code))

            # XSS payload -> sanitized
            xss = '<p>Read <strong>chapter 3</strong></p><script>alert(1)</script><img src=x onerror=alert(2)><a href="https://x.com">link</a>'
            r = await c.post(f"{A}/classrooms/{cid}", headers=AH, json={"content": xss})
            check("owner posts announcement (201)", r.status_code == 201, str(r.status_code))
            ann = r.json()
            content = ann["content"]
            check("XSS stripped from announcement", "<script" not in content and "onerror" not in content and "<img" not in content, content)
            check("safe formatting + link preserved", "<strong>chapter 3</strong>" in content and 'href="https://x.com"' in content, content)
            check("announcement author flattened", (ann.get("author") or {}).get("id") == a_id, str(ann.get("author")))
            ann_id = ann["id"]

            # ── bell: B receives announcement_new ──
            bell = await bws.wait_for(lambda e: e.get("type") == "announcement_new" and e.get("announcement_id") == ann_id)
            check("member's bell gets announcement_new", bell is not None and bell.get("classroom_id") == cid, str(bell))

            # ── feed visibility ──
            feed = await c.get(f"{A}/classrooms/{cid}", headers=BH)
            check("member sees feed (newest-first)", feed.status_code == 200 and any(x["id"] == ann_id for x in feed.json()))
            r = await c.get(f"{A}/classrooms/{cid}", headers=CH)
            check("non-member cannot read feed (403)", r.status_code == 403, str(r.status_code))

            # ── comments ──
            r = await c.post(f"{A}/{ann_id}/comments", headers=BH, json={"content": "Got it, thanks!"})
            check("member comments (201)", r.status_code == 201, str(r.status_code))
            comment_id = r.json()["id"]
            check("comment author flattened", (r.json().get("author") or {}).get("id") == b_id)

            # owner gets comment_new on the bell
            cbell = await aws.wait_for(lambda e: e.get("type") == "comment_new" and e.get("announcement_id") == ann_id)
            check("author's bell gets comment_new", cbell is not None, str(cbell))

            r = await c.post(f"{A}/{ann_id}/comments", headers=BH, json={"content": "   "})
            check("empty comment -> 422", r.status_code == 422, str(r.status_code))
            r = await c.post(f"{A}/{ann_id}/comments", headers=CH, json={"content": "sneaky"})
            check("non-member cannot comment (403)", r.status_code == 403, str(r.status_code))

            # ── delete rules ──
            r = await c.delete(f"{A}/{ann_id}/comments/{comment_id}", headers=CH)
            check("non-member cannot delete comment", r.status_code in (403, 404), str(r.status_code))
            # owner deletes a member's comment
            r = await c.delete(f"{A}/{ann_id}/comments/{comment_id}", headers=AH)
            check("owner deletes member comment (204)", r.status_code == 204, str(r.status_code))

            # member cannot delete the announcement; owner can
            r = await c.delete(f"{A}/{ann_id}", headers=BH)
            check("member cannot delete announcement (403)", r.status_code == 403, str(r.status_code))
            r = await c.delete(f"{A}/{ann_id}", headers=AH)
            check("owner deletes announcement (204)", r.status_code == 204, str(r.status_code))

            feed = (await c.get(f"{A}/classrooms/{cid}", headers=AH)).json()
            check("feed empty after delete", all(x["id"] != ann_id for x in feed))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
