"""
verify_cross_file_quiz.py — smoke test for the folder-level cross-file quiz.

Prerequisites (run BEFORE this script):
  • Backend running at localhost:9621
  • At least one classroom with ≥2 COMPLETED files in a folder
    (each file must have rag_doc_id set = processing fully complete)

Run:
  python sampai/docker/scripts/verify_cross_file_quiz.py

All 25 checks must PASS.
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:9621/api/sampai"
TIMEOUT = 10
GENERATE_POLL_LIMIT = 120  # seconds to wait for generation


def req(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


_pass = _fail = 0


def ok(label, cond, hint=""):
    global _pass, _fail
    if cond:
        print(f"  PASS  {label}")
        _pass += 1
    else:
        print(f"  FAIL  {label}{(' — ' + hint) if hint else ''}")
        _fail += 1


# ── helpers ──────────────────────────────────────────────────────────────────

def signup_login(suffix):
    username = f"fqtest_{suffix}_{int(time.time())}"
    req("POST", "/auth/signup", {"username": username, "email": f"{username}@x.com", "password": "Test1234!"})
    _, body = req("POST", "/auth/login", {"username": username, "password": "Test1234!"})
    return body.get("access_token")


def create_classroom(token):
    _, body = req("POST", "/classrooms/", {"name": f"FQClass_{int(time.time())}", "description": "FQ test"}, token)
    return body["id"], body["join_code"]


def create_folder(token, classroom_id, name="FQFolder"):
    _, body = req("POST", f"/classrooms/{classroom_id}/folders", {"name": name}, token)
    return body["id"]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n=== verify_cross_file_quiz ===\n")

    # 1. auth
    print("[1] Auth setup")
    owner_tok = signup_login("owner")
    member_tok = signup_login("member")
    ok("owner token obtained", bool(owner_tok))

    # 2. Classroom + folder
    print("\n[2] Classroom + folder")
    cls_id, join_code = create_classroom(owner_tok)
    folder_id = create_folder(owner_tok, cls_id)
    ok("classroom created", cls_id > 0)
    ok("folder created", folder_id > 0)

    # 3. Check for ≥2 completed files
    print("\n[3] Check completed files")
    _, folder_files = req("GET", f"/classrooms/{cls_id}/folders/{folder_id}/files", token=owner_tok)
    completed = [f for f in (folder_files if isinstance(folder_files, list) else [])
                 if f.get("processing_status") == "completed" and f.get("rag_doc_id")]
    ok(f"≥2 completed files in folder ({len(completed)} found)",
       len(completed) >= 2,
       "Upload and process ≥2 files in the folder before running this script")

    if len(completed) < 2:
        print("\nCannot continue: need ≥2 completed files. Skipping generation tests.")
        # Use a known classroom instead — try to find one in the DB
        print(f"\nTotal: {_pass} PASS, {_fail} FAIL (aborted — no multi-file folder available)")
        sys.exit(1)

    # 4. Attempt on folder with no completed files → 400
    print("\n[4] Empty-folder guard")
    empty_folder_id = create_folder(owner_tok, cls_id, "EmptyFolder")
    status, body = req("POST", f"/folder-quiz/folders/{empty_folder_id}/generate",
                       {}, owner_tok)
    ok("empty folder → 400", status == 400, f"got {status}")

    # 5. Member can't generate (not owner — just membership check, no owner gate)
    print("\n[5] Membership gate")
    req("POST", f"/classrooms/{cls_id}/join", {"code": join_code}, member_tok)
    s, _ = req("POST", f"/folder-quiz/folders/{folder_id}/generate", {}, member_tok)
    ok("member can generate (membership is enough)", s == 202, f"got {s}")

    # 5b. File-selection validation: empty selection → 400
    se, _ = req("POST", f"/folder-quiz/folders/{folder_id}/generate",
                {"file_ids": []}, owner_tok)
    ok("empty file_ids → 400", se == 400, f"got {se}")

    # 6. Generate quiz (hard, 20 questions) as owner — SELECTING a subset of files
    # (all completed files except the first) to exercise file scoping.
    print("\n[6] Generate quiz (hard, 20 Qs) — subset selection")
    excluded_file = completed[0]
    excluded_name = excluded_file.get("filename", "")
    selected_ids = [f["id"] for f in completed[1:]]
    selected_names = {f.get("filename", "") for f in completed[1:]}
    t0 = time.time()
    s, body = req("POST", f"/folder-quiz/folders/{folder_id}/generate",
                  {"difficulty": "hard", "file_ids": selected_ids}, owner_tok)
    ok("202 accepted", s == 202, f"got {s}: {body}")
    quiz_id = body.get("quiz_id")
    ok("quiz_id returned", quiz_id is not None)

    # 7. Poll until READY
    print("\n[7] Poll to READY")
    final_status = None
    for _ in range(GENERATE_POLL_LIMIT):
        time.sleep(2)
        _, poll = req("GET", f"/folder-quiz/{quiz_id}", token=owner_tok)
        final_status = poll.get("status")
        if final_status in ("ready", "failed"):
            break
    elapsed = time.time() - t0
    ok(f"status=ready (took {elapsed:.0f}s)", final_status == "ready", f"status={final_status}: {poll.get('error_msg')}")

    # 8. Inspect READY payload
    print("\n[8] READY payload checks")
    ok("questions present (public, no ref answers)", isinstance(poll.get("questions"), list) and len(poll["questions"]) > 0)
    q_sample = poll["questions"][0] if poll.get("questions") else {}
    ok("question has text", bool(q_sample.get("question")))
    ok("reference_answer hidden pre-submit", q_sample.get("reference_answer") is None and not q_sample.get("submitted"))
    ok("source_file_names present per question", isinstance(q_sample.get("source_file_names"), list))
    ok("no verification fields", "verification" not in q_sample and "pedagogy" not in q_sample)
    ok("file_contributions present", len(poll.get("files", [])) > 0)
    ok("diversity present", isinstance(poll.get("diversity"), dict))

    # file-selection scoping: the excluded file must never appear; all sources ⊆ selection
    seen_sources = set()
    for q in poll.get("questions", []):
        seen_sources.update(q.get("source_file_names", []))
    ok("excluded (unselected) file never appears", excluded_name not in seen_sources,
       f"leaked {excluded_name}")
    ok("all question sources ⊆ selected files", seen_sources.issubset(selected_names),
       f"unexpected={seen_sources - selected_names}")
    ok("file_contributions only selected files",
       {f["filename"] for f in poll.get("files", [])}.issubset(selected_names))

    # cross-file proof: ≥1 question spans ≥2 files (only meaningful with ≥2 selected files)
    if len(selected_ids) >= 2:
        cross_file_questions = [q for q in poll.get("questions", []) if len(q.get("source_file_names", [])) >= 2]
        ok(f"≥1 question spans ≥2 files (cross-file proof) — found {len(cross_file_questions)}",
           len(cross_file_questions) >= 1,
           "May fail if all seeds happened to come from one file (try with a denser multi-topic folder)")
    else:
        print("  SKIP  cross-file proof (only 1 file selected)")

    # hop depth should be 3 for hard
    hop_depths = [q.get("hop_depth") for q in poll.get("questions", []) if q.get("hop_depth") is not None]
    ok("hop_depth=3 for hard difficulty", any(d == 3 for d in hop_depths), f"depths={hop_depths[:5]}")

    # 9. One-open constraint
    print("\n[9] One-open constraint")
    s2, _ = req("POST", f"/folder-quiz/folders/{folder_id}/generate", {}, owner_tok)
    ok("second generate → 409", s2 == 409, f"got {s2}")

    # 10. Submit each question (per-question grade reveals reference + critique + 0–5 score)
    print("\n[10] Submit each question (per-question grade)")
    qlist = poll["questions"]
    n = len(qlist)
    last = None
    for i, q in enumerate(qlist):
        ans = "" if i == 0 else f"My attempt at {q['id']}."  # q0 blank → must score 0
        sr, r = req("POST", f"/folder-quiz/{quiz_id}/questions/{q['id']}/submit", {"user_answer": ans}, owner_tok, timeout=40)
        if sr != 200:
            ok(f"submit q{i+1} → 200", False, f"{sr}: {r}")
            continue
        last = r
        ok(f"q{i+1}: int score 0..5 + reference revealed + critique shape",
           isinstance(r["score"], int) and 0 <= r["score"] <= 5 and bool(r["reference_answer"])
           and isinstance(r["missing"], list) and isinstance(r["incorrect"], list))
        ok(f"q{i+1}: finished flag correct", r["finished"] == (i == n - 1), f"finished={r['finished']} graded={r['graded_count']}/{r['total_count']}")
    ok("blank answer (q1) scored 0", qlist and req("GET", f"/folder-quiz/{quiz_id}", token=owner_tok)[1]["questions"][0]["score"] == 0)

    # 11. Re-submit a graded question → 409
    s4, _ = req("POST", f"/folder-quiz/{quiz_id}/questions/{qlist[0]['id']}/submit", {"user_answer": "again"}, owner_tok)
    ok("re-submit graded question → 409", s4 == 409, f"got {s4}")

    # 12. Completed detail: aggregate + per-topic + references visible
    print("\n[12] Completed detail")
    _, fin = req("GET", f"/folder-quiz/{quiz_id}", token=owner_tok)
    ok("status submitted", fin.get("status") == "submitted")
    ok("all questions submitted + references visible", all(q["submitted"] and q["reference_answer"] for q in fin["questions"]))
    ok("aggregate score set (0-1)", fin.get("score") is not None and 0.0 <= fin["score"] <= 1.0)
    ok("correct_count set", fin.get("correct_count") is not None)
    ok("topic_scores present (per file)", len(fin.get("topic_scores", [])) >= 1)
    ok("graded_count == total_count", fin.get("graded_count") == fin.get("total_count"))

    # 13. History (clickable data)
    print("\n[13] History")
    s6, hist = req("GET", f"/folder-quiz/folders/{folder_id}/history", token=owner_tok)
    ok("history → 200", s6 == 200, f"got {s6}")
    done = next((it for it in hist.get("items", []) if it["quiz_id"] == quiz_id), None)
    ok("finished quiz in history with score", done is not None and done.get("score") is not None)
    ok("history exposes graded_count/total_count", done and done["graded_count"] == done["total_count"])
    ok("has_open_quiz=false after completion", not hist.get("has_open_quiz"))
    ok("n_files reflects completed count", all(item["n_files"] >= 2 for item in hist.get("items", [])))

    # 14. Auto difficulty (no manual difficulty)
    print("\n[14] Auto-difficulty (baseline = medium for new user)")
    s_auto, auto_body = req("POST", f"/folder-quiz/folders/{folder_id}/generate",
                            {}, owner_tok)
    ok("auto-difficulty generate → 202", s_auto == 202, f"got {s_auto}: {auto_body}")
    auto_id = auto_body.get("quiz_id")
    for _ in range(GENERATE_POLL_LIMIT):
        time.sleep(2)
        _, auto_poll = req("GET", f"/folder-quiz/{auto_id}", token=owner_tok)
        if auto_poll.get("status") in ("ready", "failed"):
            break
    ok("auto-difficulty quiz reaches ready or failed", auto_poll.get("status") in ("ready", "failed"))
    ok("difficulty_source=baseline or inferred", auto_poll.get("difficulty_source") in ("baseline", "inferred"))

    # ── summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    total = _pass + _fail
    print(f"Result: {_pass}/{total} PASS")
    if _fail:
        print("Some checks failed — review output above.")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    main()
