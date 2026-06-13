"""Phase 1 backend acceptance test (run against a live server on :9621).

Covers the acceptance criteria:
  - signup/login for two users
  - owner creates a classroom; member joins by code
  - owner-only routes 403 for members
  - reserved username 'sampai' rejected (422); duplicate rejected (400)
  - folder create/list/delete with the right guards
"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = "http://127.0.0.1:9621/api/sampai"
_passed, _failed = 0, 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {extra}")


def main() -> int:
    sfx = uuid.uuid4().hex[:8]
    teacher = {"username": f"teach_{sfx}", "email": f"teach_{sfx}@x.com", "password": "Passw0rd123"}
    student = {"username": f"stud_{sfx}", "email": f"stud_{sfx}@x.com", "password": "Passw0rd123"}

    with httpx.Client(base_url=BASE, timeout=30) as c:
        # signup
        r = c.post("/auth/signup", json=teacher)
        check("signup teacher 201", r.status_code == 201, str(r.status_code))
        r = c.post("/auth/signup", json=student)
        check("signup student 201", r.status_code == 201, str(r.status_code))

        # reserved + duplicate
        r = c.post("/auth/signup", json={"username": "sampai", "email": f"s_{sfx}@x.com", "password": "Passw0rd123"})
        check("reserved username 'sampai' -> 422", r.status_code == 422, str(r.status_code))
        r = c.post("/auth/signup", json=teacher)
        check("duplicate signup -> 400", r.status_code == 400, str(r.status_code))

        # login
        rt = c.post("/auth/login", json={"email": teacher["email"], "password": teacher["password"]})
        check("teacher login 200", rt.status_code == 200, str(rt.status_code))
        t_tok = rt.json().get("access_token", "")
        rs = c.post("/auth/login", json={"email": student["email"], "password": student["password"]})
        check("student login 200", rs.status_code == 200, str(rs.status_code))
        s_tok = rs.json().get("access_token", "")

        r = c.post("/auth/login", json={"email": teacher["email"], "password": "wrong"})
        check("wrong password -> 401", r.status_code == 401, str(r.status_code))

        TH = {"Authorization": f"Bearer {t_tok}"}
        SH = {"Authorization": f"Bearer {s_tok}"}

        # /me
        r = c.get("/auth/me", headers=TH)
        check("/auth/me 200", r.status_code == 200 and r.json()["username"] == teacher["username"])
        r = c.get("/auth/me")
        check("/auth/me no token -> 401", r.status_code == 401, str(r.status_code))

        # create classroom (teacher)
        r = c.post("/classrooms", headers=TH, json={"name": f"OS {sfx}", "description": "Operating Systems"})
        check("create classroom 201", r.status_code == 201, str(r.status_code))
        cls = r.json()
        cid, code = cls["id"], cls["code"]
        check("classroom has 6-char code", len(code) == 6, code)
        check("owner auto-member", any(m["username"] == teacher["username"] for m in cls["members"]))

        # student not yet a member -> 403 on GET
        r = c.get(f"/classrooms/{cid}", headers=SH)
        check("non-member GET classroom -> 403", r.status_code == 403, str(r.status_code))

        # student joins by code
        r = c.post(f"/classrooms/join/{code}", headers=SH)
        check("student join by code 200", r.status_code == 200, str(r.status_code))
        r = c.get(f"/classrooms/{cid}", headers=SH)
        check("member GET classroom 200", r.status_code == 200, str(r.status_code))

        # owner-only guards for student
        r = c.post(f"/folders/classroom/{cid}", headers=SH, json={"name": "Notes"})
        check("student create folder -> 403", r.status_code == 403, str(r.status_code))
        r = c.delete(f"/classrooms/{cid}", headers=SH)
        check("student delete classroom -> 403", r.status_code == 403, str(r.status_code))

        # owner folder CRUD
        r = c.post(f"/folders/classroom/{cid}", headers=TH, json={"name": "Lecture Notes"})
        check("owner create folder 201", r.status_code == 201, str(r.status_code))
        fid = r.json()["id"]
        r = c.get(f"/folders/classroom/{cid}", headers=SH)
        check("member list folders 200", r.status_code == 200 and len(r.json()) == 1, str(r.status_code))
        r = c.delete(f"/folders/{fid}", headers=TH)
        check("owner delete folder 204", r.status_code == 204, str(r.status_code))

        # list my classrooms (both should see it)
        r = c.get("/classrooms", headers=SH)
        check("student lists joined classroom", r.status_code == 200 and any(x["id"] == cid for x in r.json()))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
