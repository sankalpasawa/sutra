"""tests/test_store_live.py — the live Library. Run it after touching store.py's library section.

What it proves, in the order the owner asked for it (2026-09-09):

  * a row is born when the run STARTS, not when the article finishes, and starting twice for the
    same run gives back the same row rather than a second one;
  * the rename at the end changes the name and NOTHING else, above all not the id, because the
    screen is holding that id while it watches the row;
  * the progress strip is derived from the run's own artifacts, so it says what the run actually
    wrote, marks what it has not written yet, and a run that dies half way leaves a row that
    honestly shows how far it got;
  * `library_finish` works on a run that never started a row, because old runs exist;
  * the artifact route refuses a bad id and refuses a name that climbs out of the run folder. That
    last one is the one that matters: it serves files off disk.

No model is called. Everything here is files.
"""
import os
import shutil
import sys
import time

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store  # noqa: E402

FAILS = []
CHECKS = [0]


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


def strip(row):
    """{key: exists} for one Library row — the shape the screen greys things by."""
    return {m["key"]: m["exists"] for m in (row or {}).get("milestones") or []}


MADE = []          # chats to remove at the end
ITEMS = []         # library rows to remove at the end


def chat_and_run(topic):
    c = store.new_chat("live library test")
    r = store.new_run(c, topic)
    MADE.append(c)
    return c, r


# ---- 1. the row is born at run start -------------------------------------------------------
print("\nthe row is born when the run starts")

c1, r1 = chat_and_run("cost per hire")
item = store.library_start(c1, r1, "write me something about cost per hire")
ITEMS.append(item)

row = store.library_get(item)
ok("starting a run puts a row in the Library", bool(row), row)
ok("it is named for what it is doing, not left blank", row["title"] == "Writing…", row.get("title"))
ok("and it is tagged as still running", row["status"] == "writing", row.get("status"))
ok("it remembers the run it came from", row["chat_id"] == c1 and row["run_id"] == r1)
ok("it keeps what the person asked for", "cost per hire" in row.get("request", ""))
ok("the Library screen lists it", any(x["id"] == item for x in store.library_list()))

again = store.library_start(c1, r1, "asked a second time")
ok("starting the same run twice returns the same row", again == item, (item, again))
ok("and never makes a second row",
   len([x for x in store.library_list() if x.get("run_id") == r1]) == 1,
   [x["id"] for x in store.library_list() if x.get("run_id") == r1])
ok("the second call does not overwrite what the first wrote",
   store.library_get(item)["created_at"] == row["created_at"])

ok("the id does not carry the title, because there is no title yet",
   "writing" not in item.lower() and item.startswith("run-"), item)
ok("the id is safe as a folder name and in a url",
   all(ch.isalnum() or ch in "-_." for ch in item) and len(item) <= 80, item)


# ---- 2. the strip is derived from the run ---------------------------------------------------
print("\nthe strip says what the run actually wrote")

ok("a run that has written nothing shows five milestones, all grey",
   strip(store.library_get(item)) == {"research": False, "picture": False, "plan": False,
                                      "draft": False, "edited": False},
   strip(store.library_get(item)))
# The picture comes AFTER the plan, because gather (which writes it) is planner step 1 inside
# write_article, and write_article only runs once the blueprint exists. Settled against the code on
# integration, 2026-09-09; the contract and the design doc had disagreed.
ok("the strip is in the order the run actually produces them",
   [m["key"] for m in store.library_get(item)["milestones"]]
   == ["research", "plan", "picture", "draft", "edited"])
ok("every milestone is named in plain English",
   all(m["label"] and m["note"] for m in store.library_get(item)["milestones"]))

store.save_artifact(c1, r1, "research.json", {"topic": "cost per hire"})
ok("the research lands and the strip says so", strip(store.library_get(item))["research"] is True)
ok("and nothing else lit up with it",
   strip(store.library_get(item)) == {"research": True, "picture": False, "plan": False,
                                      "draft": False, "edited": False})
ok("a milestone that exists carries when it happened",
   bool(next(m for m in store.library_get(item)["milestones"] if m["key"] == "research")["at"]))
ok("a milestone that does not exist carries no time",
   next(m for m in store.library_get(item)["milestones"] if m["key"] == "plan")["at"] is None)

store.save_artifact(c1, r1, "search-picture.md", "# The search picture\n\nWhat the results show.\n")
store.save_artifact(c1, r1, "blueprint.json", {"h1": "Cost per hire", "sections": [{"h2": "x"}]})
ok("the picture and the plan fill in as the run makes them",
   strip(store.library_get(item)) == {"research": True, "picture": True, "plan": True,
                                      "draft": False, "edited": False})
ok("the list route shows the same strip as the item route",
   strip(next(x for x in store.library_list() if x["id"] == item))
   == strip(store.library_get(item)))

# nothing was copied to do any of that: the Library folder still holds only the meta
files = sorted(os.listdir(os.path.join(store.library_dir(), item)))
ok("nothing was copied into the Library while the run is live", files == ["meta.json"], files)

# a half-written file is a step that crashed, not a step that finished
store.save_artifact(c1, r1, "draft.md", "")
ok("an empty file does not count as a milestone", strip(store.library_get(item))["draft"] is False)
store.save_artifact(c1, r1, "draft.md", "# Cost per hire\n\nThe body of the article.\n")
ok("a real file does", strip(store.library_get(item))["draft"] is True)

# write_article writes write-report.json even when the plan fails to freeze and no draft is
# written, so `edited` must never light up above a draft that is not there
c_fz, r_fz = chat_and_run("froze")
fz = store.library_start(c_fz, r_fz, "a run that stopped at freeze")
ITEMS.append(fz)
store.save_artifact(c_fz, r_fz, "write-report.json", {"stopped_at": "freeze"})
ok("a run that stopped at the freeze check does not claim it was edited",
   strip(store.library_get(fz)) == {"research": False, "picture": False, "plan": False,
                                    "draft": False, "edited": False},
   strip(store.library_get(fz)))

store.save_artifact(c1, r1, "write-report.json", {"steps": {"slop": {"before": 4, "after": 0}}})
ok("with a draft beside it, the editing record does count",
   strip(store.library_get(item))["edited"] is True)


# ---- 3. the rename keeps the id -------------------------------------------------------------
print("\nthe rename is a rename, not a move")

meta = store.library_finish(item, "Cost per hire: the formula",
                            "# Cost per hire: the formula\n\nA real body, several words long.\n",
                            {"primary_keyword": "cost per hire"})
ok("finishing gives the row its real name", meta["title"] == "Cost per hire: the formula")
ok("and marks it ready", meta["status"] == "ready", meta.get("status"))
ok("THE ID DID NOT MOVE", meta["id"] == item, (item, meta["id"]))
ok("the screen can still find it under the id it was watching",
   (store.library_get(item) or {}).get("title") == "Cost per hire: the formula")
ok("there is still exactly one row for this run",
   len([x for x in store.library_list() if x.get("run_id") == r1]) == 1)
ok("it counted the words", meta["words"] == len(
    "# Cost per hire: the formula\n\nA real body, several words long.\n".split()))
ok("the extra the caller passed is on the row", meta["primary_keyword"] == "cost per hire")
ok("the article reads back", "A real body" in store.library_get(item)["draft"])
ok("and the research is now copied in beside it, so deleting the chat cannot empty it",
   bool(store.library_get(item)["research"]))
ok("finishing does not lose the run it came from",
   store.library_get(item)["chat_id"] == c1 and store.library_get(item)["run_id"] == r1)


# ---- 4. a run that crashes half way ---------------------------------------------------------
print("\na run that dies half way leaves an honest row")

c2, r2 = chat_and_run("half a run")
crashed = store.library_start(c2, r2, "this one will not finish")
ITEMS.append(crashed)
store.save_artifact(c2, r2, "research.json", {"topic": "half a run"})
store.save_artifact(c2, r2, "search-picture.md", "# The search picture\n\nTwo milestones in.\n")
# ...and then nothing. The process died.
row = store.library_get(crashed)
ok("the row is still there after the run died", bool(row))
ok("it still says it was writing, because nothing finished it", row["status"] == "writing")
ok("it shows the two milestones it reached and the three it did not",
   strip(row) == {"research": True, "picture": True, "plan": False,
                  "draft": False, "edited": False}, strip(row))
ok("it can still be deleted in that state", store.library_delete(crashed) is True)
ok("and it is gone", store.library_get(crashed) is None)

c2b, r2b = chat_and_run("still writing")
mid = store.library_start(c2b, r2b, "mid run")
ITEMS.append(mid)
ok("a row still writing can have its status set by hand",
   (store.library_set_status(mid, "draft") or {}).get("status") == "draft")


# ---- 5. an old run that never started a row -------------------------------------------------
print("\nan old run that never started a row")

c3, r3 = chat_and_run("old run")
store.save_artifact(c3, r3, "research.json", {"topic": "old run"})
store.save_artifact(c3, r3, "draft.md", "# An old article\n\nWritten before any of this.\n")
meta = store.library_finish(None, "An old article",
                            "# An old article\n\nWritten before any of this.\n",
                            {"chat_id": c3, "run_id": r3})
ITEMS.append(meta["id"])
ok("finishing with no row makes one", bool(store.library_get(meta["id"])))
ok("it is ready, not writing", meta["status"] == "ready")
ok("it took the run's own id, so a later start cannot double it",
   meta["id"] == store.library_item_id(c3, r3), meta["id"])
ok("and a start fired afterwards lands on the same row",
   store.library_start(c3, r3, "late") == meta["id"])
ok("which did not undo the finish", store.library_get(meta["id"])["status"] == "ready")
ok("its strip still works", strip(store.library_get(meta["id"]))["research"] is True)

# and with no chat/run at all, which is what the api test does
solo = store.library_finish(None, "Typed by hand", "# Typed by hand\n\nbody\n")
ITEMS.append(solo["id"])
ok("a finish with no run at all still saves the article",
   store.library_get(solo["id"])["draft"].startswith("# Typed by hand"))
ok("and says nothing about milestones rather than five falses",
   store.library_get(solo["id"])["milestones"] == [],
   store.library_get(solo["id"])["milestones"])

# the old one-shot save must still work, and must land on the run's row rather than a new one
c4, r4 = chat_and_run("one shot")
started = store.library_start(c4, r4, "one shot")
ITEMS.append(started)
saved = store.library_save(c4, r4, "One shot", "# One shot\n\nbody words here\n")
ok("library_save merges into the row the run already started", saved == started, (started, saved))
ok("so a run can never end up with two rows",
   len([x for x in store.library_list() if x.get("run_id") == r4]) == 1)


# ---- 6. a row whose chat was deleted ---------------------------------------------------------
print("\na finished row whose chat was deleted")

shutil.rmtree(store.chat_dir(c4), ignore_errors=True)
row = store.library_get(started)
ok("the row survives its chat", bool(row))
ok("it says nothing about milestones rather than showing five falses",
   row["milestones"] == [], row["milestones"])
ok("the article is still readable, because it was copied in at finish",
   "body words here" in row["draft"])


# ---- 7. the artifact route --------------------------------------------------------------------
print("\nthe artifact route: it serves files off disk, so it is gated twice")

got = store.library_artifact(item, "plan")
ok("a milestone key returns that milestone's file", got and got["file"] == "blueprint.json", got)
ok("a json milestone comes back parsed", (got or {}).get("data", {}).get("h1") == "Cost per hire")
ok("it carries the label the strip uses", (got or {}).get("label") == "Planned")
pic = store.library_artifact(item, "picture")
ok("a text milestone comes back as text", "The search picture" in (pic or {}).get("text", ""))
ok("the file name works as well as the key",
   (store.library_artifact(item, "blueprint.json") or {}).get("data") == got["data"])
ok("a milestone the run never wrote is nothing, not an empty file",
   store.library_artifact(mid, "draft") is None)
ok("an article with no run behind it has nothing to serve",
   store.library_artifact(solo["id"], "plan") is None)

for bad in ("../state.json", "../../../../etc/passwd", "_work/keywords.json",
            "artifacts/../state.json", "/etc/passwd"):
    ok("a name that climbs out of the run folder is refused: %r" % bad,
       store.library_artifact(item, bad) is None)
for nope in ("cards.json", "state.json", "events.jsonl", "article.json", ""):
    ok("a file that is not a milestone is refused: %r" % nope,
       store.library_artifact(item, nope) is None)
ok("an article id that is not there is refused",
   store.library_artifact("no-such-article", "plan") is None)

# the route itself, called as a function: no server needed to prove what it refuses
try:
    import agents_api
except Exception as e:                                        # noqa: BLE001
    agents_api = None
    print("  SKIP  the route itself (agents_api would not import: %s)" % str(e)[:120])
if agents_api:
    r = agents_api.api_library_artifact(item, "plan")
    ok("the route serves a milestone", isinstance(r, dict) and r.get("file") == "blueprint.json", r)
    for bad_id in ("../etc", "..", "a" * 200, "has space"):
        r = agents_api.api_library_artifact(bad_id, "plan")
        ok("the route refuses a bad id: %r" % bad_id, getattr(r, "status_code", None) == 400, r)
    for bad_name in ("../state.json", "..%2Fstate.json", "a/b", ""):
        r = agents_api.api_library_artifact(item, bad_name)
        ok("the route refuses a bad name: %r" % bad_name,
           getattr(r, "status_code", None) == 400, r)
    r = agents_api.api_library_artifact(item, "cards.json")
    ok("a real file that is not a milestone is a 404, not a leak",
       getattr(r, "status_code", None) == 404, r)
    r = agents_api.api_library_artifact(mid, "draft")
    ok("a milestone that has not happened yet is a 404 with a sentence a person can read",
       getattr(r, "status_code", None) == 404, r)


# ---- 8. the strip on a list is cheap enough to poll --------------------------------------------
print("\nthe Library screen polls the list, so the strip has to be cheap")

t0 = time.time()
for _ in range(20):
    store.library_list()
per = (time.time() - t0) / 20
ok("twenty full list reads take under a tenth of a second each", per < 0.1, "%.4fs" % per)


# ---- clean up -----------------------------------------------------------------------------------
for i in ITEMS + [meta["id"], solo["id"]]:
    store.library_delete(i)
for c in MADE:
    shutil.rmtree(store.chat_dir(c), ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
