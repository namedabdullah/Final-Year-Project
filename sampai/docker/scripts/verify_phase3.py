"""Phase 3 acceptance test (live server :9621): scoped chat + leakage merge-gate.

Two files with unique INVENTED facts (so the model can only know them from context):
  A: Glimmerwock Scheduling Protocol -> 7 quantum bands
  B: Throttlejack Memory Manager     -> 19 cascade tiers

Gates:
  - chat on A answers A's fact (7)
  - chat on A does NOT reveal B's fact (19)   <-- leakage merge-gate
  - chat on B answers B's fact (19)
  - streaming arrives incrementally (multiple token events)
  - per-user history persists
"""

from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:9621/api/sampai"
_passed = _failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  PASS  {name}")
    else:
        _failed += 1; print(f"  FAIL  {name}  {extra}")


def upload_txt(c, H, folder_id, name, text):
    return c.post(f"/files/upload/{folder_id}", headers=H, files={"upload": (name, text.encode(), "text/plain")}).json()["id"]


def wait_completed(c, H, fid, timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        st = c.get(f"/files/{fid}/status", headers=H).json()["status"]
        if st in ("completed", "failed"):
            return st
        time.sleep(3)
    return "timeout"


def ask(c, H, fid, question):
    """Consume the SSE stream; return (answer, num_token_events)."""
    tokens, n = [], 0
    with c.stream("POST", f"/chat/files/{fid}/ask", headers=H, json={"question": question}) as r:
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if payload.get("token"):
                tokens.append(payload["token"]); n += 1
            if payload.get("done"):
                break
    return "".join(tokens), n


def main() -> int:
    sfx = uuid.uuid4().hex[:8]
    teacher = {"username": f"t3_{sfx}", "email": f"t3_{sfx}@x.com", "password": "Passw0rd123"}

    with httpx.Client(base_url=BASE, timeout=120) as c:
        c.post("/auth/signup", json=teacher)
        tok = c.post("/auth/login", json={"email": teacher["email"], "password": teacher["password"]}).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        cid = c.post("/classrooms", headers=H, json={"name": f"Chat {sfx}"}).json()["id"]
        folder = c.post(f"/folders/classroom/{cid}", headers=H, json={"name": "Docs"}).json()["id"]

        a_text = (
            "The Glimmerwock Scheduling Protocol is a fictional CPU scheduler. "
            "It divides CPU time into exactly 7 quantum bands. "
            "It was designed by the Aldebaran Institute."
        )
        b_text = (
            "The Throttlejack Memory Manager is a fictional memory system. "
            "It organizes pages into exactly 19 cascade tiers. "
            "It originates from the Castoria Lab."
        )
        fa = upload_txt(c, H, folder, "file_a.txt", a_text)
        fb = upload_txt(c, H, folder, "file_b.txt", b_text)
        print("  ingesting two files…")
        check("file A completed", wait_completed(c, H, fa) == "completed")
        check("file B completed", wait_completed(c, H, fb) == "completed")

        # In-scope answer on A
        ans_a, n_a = ask(c, H, fa, "How many quantum bands does the Glimmerwock Scheduling Protocol use?")
        print(f"      A answer: {ans_a[:120]!r}")
        check("A answers its own fact (7)", "7" in ans_a or "seven" in ans_a.lower(), ans_a[:80])
        check("streaming is incremental (>1 token event)", n_a > 1, f"events={n_a}")

        # LEAKAGE GATE: ask A about B's fact
        ans_leak, _ = ask(c, H, fa, "How many cascade tiers does the Throttlejack Memory Manager use?")
        print(f"      A-leak answer: {ans_leak[:120]!r}")
        check(
            "LEAKAGE GATE: A does NOT reveal B's fact (19)",
            "19" not in ans_leak and "nineteen" not in ans_leak.lower(),
            ans_leak[:100],
        )

        # In-scope answer on B
        ans_b, _ = ask(c, H, fb, "How many cascade tiers does the Throttlejack Memory Manager use?")
        print(f"      B answer: {ans_b[:120]!r}")
        check("B answers its own fact (19)", "19" in ans_b or "nineteen" in ans_b.lower(), ans_b[:80])

        # History (per-user) — 2 asks on A => 2 user + 2 assistant
        hist = c.get(f"/chat/files/{fa}/history", headers=H).json()["messages"]
        check("per-user history persisted (>=4 msgs on A)", len(hist) >= 4, f"n={len(hist)}")

        # Clear history
        r = c.delete(f"/chat/files/{fa}/history", headers=H)
        check("clear history 204", r.status_code == 204, str(r.status_code))
        hist2 = c.get(f"/chat/files/{fa}/history", headers=H).json()["messages"]
        check("history empty after clear", len(hist2) == 0, f"n={len(hist2)}")

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
