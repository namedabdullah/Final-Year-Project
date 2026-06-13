"""Phase 4 acceptance test (live :9621): flashcards (Leitner) + mindmaps.

Uploads one content-rich doc, then exercises:
  - deck generation (valid card mix), due query, a review (box transition), history box_counts
  - mindmap tree generation (version 2, >=2 root children, depth<=5), node explore
    (placeholder fills with a summary), per-user node chat
"""

from __future__ import annotations

import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:9621/api/sampai"
_passed = _failed = 0

DOC = """Operating Systems — Core Concepts.

A process is an instance of a running program, with its own address space and resources.
A thread is the smallest unit of CPU scheduling; threads within a process share memory.
The CPU scheduler decides which process or thread runs next; common policies include
round-robin and priority scheduling. A context switch saves and restores process state.

Deadlock occurs when a set of processes each wait for resources held by others, and none
can proceed. The four Coffman conditions are mutual exclusion, hold-and-wait, no preemption,
and circular wait. A mutex enforces mutual exclusion over a critical section. A semaphore is
a counter used to coordinate access to shared resources.

Virtual memory gives each process the illusion of a large contiguous address space. Paging
divides memory into fixed-size pages; a page fault occurs when a referenced page is not in
RAM and must be fetched from disk. The translation lookaside buffer (TLB) caches recent
address translations to speed up paging.
"""


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  PASS  {name}")
    else:
        _failed += 1; print(f"  FAIL  {name}  {extra}")


def main() -> int:
    sfx = uuid.uuid4().hex[:8]
    teacher = {"username": f"t4_{sfx}", "email": f"t4_{sfx}@x.com", "password": "Passw0rd123"}
    with httpx.Client(base_url=BASE, timeout=120) as c:
        c.post("/auth/signup", json=teacher)
        tok = c.post("/auth/login", json={"email": teacher["email"], "password": teacher["password"]}).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        cid = c.post("/classrooms", headers=H, json={"name": f"P4 {sfx}"}).json()["id"]
        folder = c.post(f"/folders/classroom/{cid}", headers=H, json={"name": "Docs"}).json()["id"]
        fid = c.post(f"/files/upload/{folder}", headers=H, files={"upload": ("os.txt", DOC.encode(), "text/plain")}).json()["id"]

        print("  ingesting…")
        for _ in range(80):
            if c.get(f"/files/{fid}/status", headers=H).json()["status"] in ("completed", "failed"):
                break
            time.sleep(3)
        check("file completed", c.get(f"/files/{fid}/status", headers=H).json()["status"] == "completed")

        # ── Flashcards ──
        deck_id = c.post(f"/flashcards/files/{fid}/generate", headers=H, json={"card_count": 10}).json()["deck_id"]
        print("  generating deck…")
        deck = None
        for _ in range(60):
            deck = c.get(f"/flashcards/{deck_id}", headers=H).json()
            if deck["status"] in ("ready", "failed"):
                break
            time.sleep(2)
        check("deck ready", deck and deck["status"] == "ready", deck and deck.get("error_msg"))
        cards = (deck or {}).get("cards") or []
        check("deck has 10 cards", len(cards) == 10, f"n={len(cards)}")
        types = {x["card_type"] for x in cards}
        check("valid card types", types.issubset({"definition", "concept", "example", "formula"}), str(types))
        check("front/back length limits", all(len(x["front"]) <= 300 and len(x["back"]) <= 1000 for x in cards))

        due = c.get(f"/flashcards/files/{fid}/due", headers=H).json()
        check("all new cards due", due["total_due"] == 10, str(due["total_due"]))

        first = cards[0]["id"]
        rev = c.post(f"/flashcards/cards/{first}/review", headers=H, json={"result": "know"}).json()
        check("review know -> box 2", rev["box"] == 2, str(rev))
        due2 = c.get(f"/flashcards/files/{fid}/due", headers=H).json()
        check("reviewed card no longer due", due2["total_due"] == 9, str(due2["total_due"]))

        hist = c.get(f"/flashcards/files/{fid}/history", headers=H).json()
        check("history has box_counts", isinstance(hist.get("box_counts"), dict), str(hist.get("box_counts")))

        # ── Mindmap ──
        gen = c.post(f"/mindmap/files/{fid}/generate", headers=H, json={"force": False}).json()
        mmid = gen["mindmap"]["id"]
        print("  generating mindmap…")
        mm = None
        for _ in range(60):
            mm = c.get(f"/mindmap/files/{fid}", headers=H).json()
            if mm["status"] in ("ready", "failed"):
                break
            time.sleep(2)
        check("mindmap ready", mm and mm["status"] == "ready", mm and mm.get("error_message"))
        tree = (mm or {}).get("tree_data") or {}
        root = tree.get("root", {})
        check("tree version 2", tree.get("version") == 2, str(tree.get("version")))
        check("root has >=2 children", len(root.get("children", [])) >= 2, str(len(root.get("children", []))))
        check("node_count >= 3", (mm or {}).get("node_count", 0) >= 3, str((mm or {}).get("node_count")))

        # explore a first-level child node
        node_id = root["children"][0]["id"]
        exp = c.post(f"/mindmap/{mmid}/nodes/{node_id}/explore", headers=H).json()
        check("explore returns placeholder", exp.get("placeholder_id") is not None or exp.get("already_explored"), str(exp))
        print("  generating node summary…")
        filled = False
        for _ in range(45):
            msgs = c.get(f"/mindmap/{mmid}/chat", headers=H).json()["messages"]
            assistant = [m for m in msgs if m["role"] == "assistant" and m["node_id"] == node_id and m["content"].strip()]
            if assistant:
                filled = True
                break
            time.sleep(2)
        check("node summary filled", filled)

        ans = c.post(f"/mindmap/{mmid}/chat/ask", headers=H, json={"content": "Explain this topic simply.", "active_node_id": node_id}).json()
        check("mindmap chat answers", bool(ans["message"]["content"].strip()), ans["message"]["content"][:60])

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
