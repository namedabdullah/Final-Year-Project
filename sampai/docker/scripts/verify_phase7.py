"""Phase 7 acceptance test (live :9621): per-file adaptive quiz.

generate(202) → poll → ready (answers hidden) → submit → review (answers revealed) →
history/resume. Plus one-open 409, manual vs auto-inferred difficulty, and that both
easy and hard quizzes generate (difficulty → multi-hop BFS retrieval, easy 1 / hard 3).
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:9621/api/sampai"
Q = "/quiz"
_passed = _failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  PASS  {name}")
    else:
        _failed += 1; print(f"  FAIL  {name}  {extra}")


async def poll_ready(c, headers, quiz_id, timeout=90):
    for _ in range(timeout):
        d = (await c.get(f"{Q}/{quiz_id}", headers=headers)).json()
        if d["status"] in ("ready", "failed"):
            return d
        await asyncio.sleep(1)
    return {"status": "timeout"}


async def main() -> int:
    sfx = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        u = {"username": f"q_{sfx}", "email": f"q_{sfx}@x.com", "password": "Passw0rd123"}
        await c.post("/auth/signup", json=u)
        tok = (await c.post("/auth/login", json={"email": u["email"], "password": u["password"]})).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}

        cls = (await c.post("/classrooms", headers=H, json={"name": f"Quiz {sfx}"})).json()
        folder = (await c.post(f"/folders/classroom/{cls['id']}", headers=H, json={"name": "D"})).json()["id"]
        DOC = ("Photosynthesis converts light energy into chemical energy stored in glucose. "
               "Chlorophyll in the chloroplast absorbs light, mainly red and blue wavelengths. "
               "The light-dependent reactions produce ATP and NADPH. The Calvin cycle uses ATP "
               "and NADPH to fix carbon dioxide into glucose. Cellular respiration later breaks "
               "glucose down to release energy, the reverse flow of carbon and energy.")
        fid = (await c.post(f"/files/upload/{folder}", headers=H,
                            files={"upload": ("bio.txt", DOC.encode(), "text/plain")})).json()["id"]
        print("  ingesting bio.txt …")
        st = "pending"
        for _ in range(80):
            st = (await c.get(f"/files/{fid}/status", headers=H)).json()["status"]
            if st in ("completed", "failed"):
                break
            await asyncio.sleep(3)
        check("file ingested -> completed", st == "completed", f"status={st}")

        # ── manual difficulty, 5 questions ──
        gen = await c.post(f"{Q}/files/{fid}/generate", headers=H, json={"num_questions": 5, "difficulty": "easy"})
        check("generate returns 202", gen.status_code == 202, str(gen.status_code))
        quiz_id = gen.json()["quiz_id"]

        # one-open 409 while first is pending/generating/ready
        dup = await c.post(f"{Q}/files/{fid}/generate", headers=H, json={"num_questions": 5, "difficulty": "easy"})
        check("second quiz while open -> 409", dup.status_code == 409, str(dup.status_code))

        d = await poll_ready(c, H, quiz_id)
        check("quiz reaches ready", d["status"] == "ready", str(d.get("status")) + " " + str(d.get("error_msg")))
        check("difficulty_source = manual", d.get("difficulty_source") == "manual", str(d.get("difficulty_source")))
        qs = d.get("questions") or []
        check("5 questions returned", len(qs) == 5, str(len(qs)))
        check("answers hidden pre-submit", all("answer" not in q and "answer_index" not in q and "explanation" not in q for q in qs), str(qs[:1]))
        check("question shape ok", all(q.get("id") and q.get("type") in ("mcq", "tf") and q.get("question") for q in qs))
        check("MCQs carry options", all(len(q.get("options", [])) >= 2 for q in qs if q["type"] == "mcq"))

        # ── submit (answer first option / True) ──
        answers = []
        for q in qs:
            if q["type"] == "mcq":
                answers.append({"question_id": q["id"], "answer_index": 0})
            else:
                answers.append({"question_id": q["id"], "answer_bool": True})
        res = await c.post(f"{Q}/{quiz_id}/submit", headers=H, json={"answers": answers})
        check("submit returns result", res.status_code == 200, str(res.status_code))
        rj = res.json()
        check("result graded over all questions", rj["total_count"] == 5 and 0.0 <= rj["score"] <= 1.0, str(rj.get("score")))
        check("review reveals correct_answer + explanation",
              all("correct_answer" in a and "explanation" in a and "correct" in a for a in rj["answers"]), str(rj["answers"][:1]))

        # poll after submit -> review, no questions
        d2 = await c.get(f"{Q}/{quiz_id}", headers=H)
        d2j = d2.json()
        check("poll after submit -> status submitted", d2j["status"] == "submitted")
        check("poll after submit -> review present, questions hidden", d2j.get("review") is not None and d2j.get("questions") is None)

        # double submit -> 409
        dbl = await c.post(f"{Q}/{quiz_id}/submit", headers=H, json={"answers": answers})
        check("re-submit -> 409", dbl.status_code == 409, str(dbl.status_code))

        # ── history + resume ──
        hist = (await c.get(f"{Q}/files/{fid}/history", headers=H)).json()
        check("history lists the quiz", any(i["quiz_id"] == quiz_id for i in hist["items"]))
        check("no open quiz after submit", hist["has_open_quiz"] is False, str(hist["has_open_quiz"]))
        item = next(i for i in hist["items"] if i["quiz_id"] == quiz_id)
        check("history item carries score + submitted_at", item["score"] is not None and item["submitted_at"] is not None)

        # ── auto-infer difficulty now that one attempt exists ──
        gen2 = await c.post(f"{Q}/files/{fid}/generate", headers=H, json={"num_questions": 5})
        quiz2 = gen2.json()["quiz_id"]
        d3 = await poll_ready(c, H, quiz2)
        check("auto-infer quiz reaches ready", d3["status"] == "ready", str(d3.get("status")))
        check("difficulty auto-inferred (not manual)", d3.get("difficulty_source") in ("inferred", "baseline"), str(d3.get("difficulty_source")))
        # submit to free the open slot
        ans2 = [{"question_id": q["id"], "answer_index": 0} if q["type"] == "mcq" else {"question_id": q["id"], "answer_bool": True} for q in (d3.get("questions") or [])]
        await c.post(f"{Q}/{quiz2}/submit", headers=H, json={"answers": ans2})

        # ── hard quiz generates too (deeper BFS, hops easy 1 / hard 3) ──
        gen3 = await c.post(f"{Q}/files/{fid}/generate", headers=H, json={"num_questions": 5, "difficulty": "hard"})
        d4 = await poll_ready(c, H, gen3.json()["quiz_id"])
        check("hard quiz generates (deeper-hop retrieval path runs)", d4["status"] == "ready", str(d4.get("status")) + " " + str(d4.get("error_msg")))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
