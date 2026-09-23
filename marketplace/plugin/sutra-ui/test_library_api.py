"""The Library's backend: does every row come from a record, and can the
module write? (holding/plans/library-program/TEST-PLAN.md, backend lane)

Run: python3 test_library_api.py

No app, no network: the module is imported and its functions called against
the repository on disk. Every assertion is about a fact the module cannot
invent -- a count that matches the template folder, a floor line that matches
the file, an absence of writers in the source.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import function_templates as FT  # noqa: E402
import library_api as LIB  # noqa: E402

FAIL = []
N = 0


def check(name, cond, detail=""):
    global N
    N += 1
    if not cond:
        FAIL.append("%s%s" % (name, (" -- " + detail) if detail else ""))


# ── 1. the shelves ──────────────────────────────────────────────────────────

payload = LIB.shelves()
rows = payload["shelves"]
check("seven shelves", len(rows) == 7, "got %d" % len(rows))
check("five of them are functions",
      sum(1 for r in rows if r["kind"] == "Function") == 5)
check("two of them are parts",
      sum(1 for r in rows if r["kind"] == "Part") == 2)
check("two groups", [g["id"] for g in payload["groups"]] == ["functions", "parts"])
check("every shelf names its list tab", all(r["list_tab"] for r in rows))
check("the engines shelf's list tab is Engines",
      next(r for r in rows if r["id"] == "engines")["list_tab"] == "Engines")
check("the work atom shelf's list tab is Examples",
      next(r for r in rows if r["id"] == "work-atom")["list_tab"] == "Examples")
check("no shelf reports an error", all(not r["error"] for r in rows),
      "; ".join(r["error"] for r in rows if r["error"]))

# ── 2. the function shelves come from the template repository ───────────────

for fn in LIB.FUNCTIONS:
    disk = FT.templates(fn)
    sh = LIB.shelf(fn)
    got = sh["list"]["rows"]
    check("%s: a row per template on disk" % fn, len(got) == len(disk),
          "disk %d, shelf %d" % (len(disk), len(got)))
    ids_disk = sorted(t["id"] for t in disk)
    ids_shelf = sorted(r["id"] for r in got)
    check("%s: the same ids, no invented row" % fn, ids_disk == ids_shelf,
          "%s vs %s" % (ids_disk, ids_shelf))
    for t in disk:
        row = next(r for r in got if r["id"] == t["id"])
        check("%s: %s carries its own use case" % (fn, t["id"]),
              row["use"] == (t.get("use_case") or ""))
        check("%s: %s counts its own floor" % (fn, t["id"]),
              row["right"] == "%d always" % len(t.get("floor") or []))
        check("%s: %s carries at least one tag" % (fn, t["id"]), len(row["tags"]) >= 1)
    check("%s: About has four ways" % fn, len(sh["about"]["ways"]) == 4)
    check("%s: every way says what lands" % fn,
          all(w["lands"] for w in sh["about"]["ways"]))
    check("%s: About has the settings" % fn, len(sh["about"]["settings"]) >= 4)
    check("%s: every setting names where it lives" % fn,
          all(s["source"] for s in sh["about"]["settings"]))
    check("%s: seven parts, one per record field" % fn,
          len(sh["about"]["parts"]) == len(LIB.FIELD_PART))
    check("%s: the head names two tabs" % fn, len(sh["head"]["tabs"]) == 2)
    check("%s: the first tab is About" % fn, sh["head"]["tabs"][0] == "About")

# fifteen templates in all, the number the repository ships
total = sum(len(LIB.shelf(fn)["list"]["rows"]) for fn in LIB.FUNCTIONS)
check("fifteen template rows across the function shelves", total == 15, "got %d" % total)

# ── 3. an opened row, and the narrowing rule at the edge ────────────────────

for fn in LIB.FUNCTIONS:
    for t in FT.templates(fn):
        item = LIB.shelf_item(fn, t["id"])
        check("%s: opened row has no error" % t["id"], not item.get("error"),
              str(item.get("error")))
        floor = t.get("floor") or []
        keeps, adds = item["keeps"], item["adds"]
        if t.get("derives_from"):
            parent = FT.get(t["derives_from"])
            missing = [ln for ln in (parent.get("floor") or []) if ln not in floor]
            check("%s: narrowing holds, a child drops nothing" % t["id"], not missing,
                  "missing: %s" % missing[:1])
            check("%s: keeps is the parent's floor" % t["id"],
                  keeps == (parent.get("floor") or []))
            check("%s: adds is exactly what the child added" % t["id"],
                  adds == [ln for ln in floor if ln not in keeps])
            check("%s: a child adds at least one line" % t["id"], len(adds) >= 1)
        else:
            check("%s: a base keeps nothing and adds its own floor" % t["id"],
                  keeps == [] and adds == floor)

check("an unknown template answers with an error, not a crash",
      LIB.shelf_item("identity", "identity/not-a-template").get("error"))
check("an unknown shelf answers None", LIB.shelf("not-a-shelf") is None)
check("the endpoint turns that into an error payload",
      LIB.shelf_get("not-a-shelf").get("error"))

# ── 4. the part shelves ─────────────────────────────────────────────────────

eng = LIB.shelf("engines")
check("engines: two tabs", len(eng["head"]["tabs"]) == 2)
check("engines: the list tab is Engines", eng["head"]["tabs"][1] == "Engines")
check("engines: eight parts", len(eng["about"]["parts"]) == 8)
check("engines: every row carries a state",
      all(r["state"] in ("ready", "in-use", "to-build") for r in eng["list"]["rows"]))
check("engines: every row carries its own id",
      all(r["id"] for r in eng["list"]["rows"]))
check("engines: a shelf with no records still answers a list",
      isinstance(eng["list"]["rows"], list))

wi = LIB.shelf("work-atom")
check("work atom: the list tab is Examples", wi["head"]["tabs"][1] == "Examples")
check("work atom: seven parts", len(wi["about"]["parts"]) == 7)
check("work atom: the note says there are no skills",
      "no skills" in wi["about"]["note"].lower())
check("work atom: no part is a skill",
      not any("skill" in p["name"].lower() for p in wi["about"]["parts"]))
check("work atom: every example carries a check",
      all(r["use"].startswith("Done when") for r in wi["list"]["rows"]))
check("work atom: at most three examples", len(wi["list"]["rows"]) <= 3)

# ── 5. the module cannot write ──────────────────────────────────────────────

src = open(os.path.join(HERE, "library_api.py"), encoding="utf-8").read()
check("no write_pick call", "write_pick" not in src)
check("no file opened for writing", not re.search(r'open\([^)]*["\'][wax]', src))
check("no os.replace, no rename", "os.replace" not in src and "os.rename" not in src)
check("no POST route", "@router.post" not in src)
check("no proposal applied here", "_apply_proposal" not in src)

# ── 6. the shape the renderer relies on ─────────────────────────────────────

for sid in [f for f in LIB.FUNCTIONS] + ["engines", "work-atom"]:
    sh = LIB.shelf(sid)
    check("%s: head carries a line" % sid, bool(sh["head"]["line"]))
    check("%s: head carries a count line" % sid, bool(sh["head"]["count_line"]))
    check("%s: list carries a tag label" % sid, bool(sh["list"]["tag_label"]))
    check("%s: tags are a list of strings" % sid,
          isinstance(sh["list"]["tags"], list)
          and all(isinstance(x, str) for x in sh["list"]["tags"]))
    for r in sh["list"]["rows"]:
        check("%s: row %s has every field the renderer draws" % (sid, r["id"]),
              all(k in r for k in ("id", "name", "sub", "use", "tags", "right",
                                   "state", "action")))
    check("%s: the payload is JSON" % sid, json.dumps(sh) and True)

print("%d checks, %d failed" % (N, len(FAIL)))
for f in FAIL:
    print("  FAIL " + f)
sys.exit(1 if FAIL else 0)
