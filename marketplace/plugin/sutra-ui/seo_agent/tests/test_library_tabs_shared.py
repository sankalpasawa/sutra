"""tests/test_library_tabs_shared.py — the five Library tabs travelling with the article.

THE INCIDENT (owner, 2026-09-21): "when I open Sutra in the Library, all the things which are
there, the search picture, the research, the write, all of that, that particular file stays
locally only. I don't want that. Not the intermediate outputs, all those JSON, not required. Just
these things should be available for everybody in the workspace."

The body of a saved article reached the team; the tabs did not, because they were assembled on
demand out of the RUN folder and a teammate has no run folder. This suite proves the four halves
of the fix, entirely offline, with no model call and no network:

  * the assembled tabs are kept beside the article the moment it is saved (and only the
    assembled 28 KB, never the megabytes of raw run artifacts);
  * they travel in the workspace payload both ways -- up through mirror.to_wire, and back down
    through from_wire into a teammate's own tabs.json;
  * the route serves the kept copy once the run folder is gone, which is what a teammate has,
    and says plainly when there is nothing kept to serve;
  * the size guard keeps the small tabs and drops the largest, on the record;
  * the one-off backfill is idempotent and is a SEND, never an edit.
"""
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store, library_tabs as lt          # noqa: E402
from seo_agent.workspace import mirror, outbox, sync     # noqa: E402

FAILS = []
CHECKS = [0]


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


MADE = []
ITEMS = []

DRAFT = "# Cost per hire\n\nThe body of the article, as the writer left it.\n"

RESEARCH = {
    "angle": "Cost per hire is a lever, not a scoreboard",
    "spine": "One number, three real inputs",
    "world": {"about": "How to calculate it", "not_about": "Salary negotiation"},
    "persona": {"name": "Heads of talent", "lens": "budget owner"},
    "evidence": {"team": [{"role": "Recruiter", "focus": "sourcing costs"}],
                 "turns": [{"persona": "Recruiter", "question": "What counts as a sourcing cost?"}]},
    "keywords": {"primary": {"keyword": "cost per hire", "volume": 2400, "kd": 38},
                 "variations": [{"keyword": "cost per hire formula", "volume": 320, "kd": 30}],
                 "secondary": [], "in_body": ["recruiting costs"]},
    "serp": {"who_ranks": [{"rank": 1, "title": "A result", "url": "https://example.com",
                            "domain": "example.com"}],
             "ai_overview": {"text": "About $4,700 in the US."},
             "paa_on": ["What is a good cost per hire?"]},
    "winners": {"common_h2s": ["What it is"], "gaps_to_own": ["A worked example"]},
    "build_spec": {"word_band": {"min": 2400, "max": 3000}},
}
HEADINGS = {"structure": {"format_archetype": "How-to guide", "spine": "The spine",
                          "word_budget": {"target": 2700},
                          "sections": [{"headline": "What it costs", "h3s": ["The formula"]}]}}
SHAPE = {"structure": {"sections": [{"headline": "What it costs", "job": "Explain the cost.",
                                     "boxes": [1, 2, 3]}]}}
REPORT = {"steps": {"blend": {}, "readable": {}, "clean": {}}, "length": {"words": 2650}}


def full_run(topic="cost per hire"):
    """A chat and a run with every artifact the four tabs read, and a Library row over it."""
    chat_id = store.new_chat("tabs shared test")
    run_id = store.new_run(chat_id, topic)
    MADE.append(chat_id)
    store.save_artifact(chat_id, run_id, "research.json", RESEARCH)
    store.save_artifact(chat_id, run_id, "search-picture.md", "# The search picture\n\nx\n")
    store.save_artifact(chat_id, run_id, "blueprint.json", {"sections": [{"h2": "A dropped one"}]})
    store.save_artifact(chat_id, run_id, "work-headings.json", HEADINGS)
    store.save_artifact(chat_id, run_id, "work-shape.json", SHAPE)
    store.save_artifact(chat_id, run_id, "draft.md", DRAFT)
    store.save_artifact(chat_id, run_id, "write-report.json", REPORT)
    item_id = store.library_save(chat_id, run_id, "Cost per hire", DRAFT)
    ITEMS.append(item_id)
    return chat_id, run_id, item_id


def tabs_path(item_id):
    return os.path.join(store.library_dir(), item_id, store.TABS_FILE)


def kill_run(chat_id):
    """What every teammate's Mac looks like: the article, and no run behind it."""
    shutil.rmtree(store.chat_dir(chat_id), ignore_errors=True)


# ---- 1. the tabs are kept with the article, at save time -----------------------------------------
print("\nthe assembled tabs are kept beside the article while the run is still on disk")

c1, r1, item1 = full_run()
ok("nothing is kept until something keeps it", not os.path.exists(tabs_path(item1)))

kept = lt.save(item1)
ok("save() returns the four tabs", isinstance(kept, dict) and kept.get("search_picture"), kept and list(kept))
ok("tabs.json is written into the row's own folder", os.path.exists(tabs_path(item1)))
on_disk = store.read_library_tabs(item1)
ok("what is on disk is what the assembler produced",
   {k: on_disk.get(k) for k in lt.TAB_KEYS} == {k: kept.get(k) for k in lt.TAB_KEYS})
ok("all four tabs are there", all(on_disk.get(k) for k in lt.TAB_KEYS),
   {k: bool(on_disk.get(k)) for k in lt.TAB_KEYS})
ok("it is the ASSEMBLED tabs, not the run's raw files: well under 400 KB",
   0 < lt._bytes(on_disk) < lt.TABS_MAX_BYTES, lt._bytes(on_disk))
ok("the row records what was kept",
   sorted((store.library_get(item1).get("tabs_saved") or {}).get("kept") or []) == sorted(lt.TAB_KEYS),
   store.library_get(item1).get("tabs_saved"))
ok("and nothing was dropped", (store.library_get(item1)["tabs_saved"]).get("dropped") == [])
ok("keeping them is not an edit: no version, no editor",
   not store.library_get(item1).get("version") and not store.library_get(item1).get("edited_by"),
   (store.library_get(item1).get("version"), store.library_get(item1).get("edited_by")))

ok("library_get hands the tabs on, which is what carries them to the team",
   isinstance(store.library_get(item1).get("tabs"), dict))
ok("but library_list does not, so the polled list stays cheap",
   all("tabs" not in row for row in store.library_list()))

before = store.read_library_tabs(item1)
lt.save(item1)
ok("running it twice writes the same file: same run, same tables",
   {k: store.read_library_tabs(item1).get(k) for k in lt.TAB_KEYS} ==
   {k: before.get(k) for k in lt.TAB_KEYS})

# the real save path, end to end
print("\nthe save path itself keeps them: loop.save_to_library")
c2, r2 = store.new_chat("tabs via the loop"), None
MADE.append(c2)
r2 = store.new_run(c2, "second article")
for name, data in (("research.json", RESEARCH), ("search-picture.md", "# x\n"),
                   ("blueprint.json", {"sections": []}), ("work-headings.json", HEADINGS),
                   ("work-shape.json", SHAPE), ("draft.md", DRAFT),
                   ("write-report.json", REPORT)):
    store.save_artifact(c2, r2, name, data)
from seo_agent import loop                                 # noqa: E402
saved = loop.save_to_library(c2, r2)
ITEMS.append(saved["item_id"])
ok("save_to_library kept the tabs with the article it just saved",
   bool(store.read_library_tabs(saved["item_id"])), saved)
ok("and the row it hands back is unchanged in every other way", saved["title"] == "Cost per hire", saved)


# ---- 2. the wire, both ways ----------------------------------------------------------------------
print("\nthe tabs travel in the workspace payload, both ways")

row = store.library_get(item1)
wire = mirror.to_wire("library", item1, row, actor="Devansh")
ok("they ride inside the meta jsonb, not a column that does not exist",
   isinstance(wire["meta"].get("tabs"), dict) and set(wire) == {
       "item_id", "title", "status", "url", "body_md", "meta", "actor"}, sorted(wire))
ok("the body is still the body_md column, exactly as before",
   wire["body_md"] == DRAFT and wire["title"] == "Cost per hire")
ok("the raw run files do not travel: research and blueprint stay off the wire",
   "research" not in wire["meta"] and "blueprint" not in wire["meta"], sorted(wire["meta"]))
ok("nor does the derived strip", "milestones" not in wire["meta"])

back = mirror.from_wire("library", item1, wire)
ok("from_wire hands the same tabs back",
   {k: back["tabs"].get(k) for k in lt.TAB_KEYS} ==
   {k: row["tabs"].get(k) for k in lt.TAB_KEYS})

# a row with no tabs must not carry a null, and must not blank a teammate's
bare = dict(row)
bare.pop("tabs", None)
ok("a row with no tabs sends no `tabs` key at all",
   "tabs" not in mirror.to_wire("library", item1, bare, actor="x")["meta"])
empty = dict(row, tabs={"search_picture": None, "research": None, "architect": None, "edits": None})
ok("nor does a row whose four tabs are all empty",
   "tabs" not in mirror.to_wire("library", item1, empty, actor="x")["meta"])

print("\na teammate's Mac: the row arrives with its tabs and no run at all")
TEAMMATE = "run-cteam-rteam"
# their row names a chat and a run that exist on HIS Mac and on no other, which is the whole
# reason the tabs had to travel: nothing here can assemble them
their_wire = dict(wire, item_id=TEAMMATE,
                  meta=dict(wire["meta"], chat_id="c-not-here", run_id="r-not-here"))
mirror.apply({"id": 1, "kind": "library", "op": "insert", "key": TEAMMATE,
              "payload": their_wire, "actor": "Devansh"})
ITEMS.append(TEAMMATE)
their = store.library_get(TEAMMATE)
ok("the article landed", (their or {}).get("draft") == DRAFT)
ok("the tabs landed with it, as their own file",
   os.path.exists(tabs_path(TEAMMATE)) and isinstance(their.get("tabs"), dict))
ok("all four of them",
   all(their["tabs"].get(k) for k in lt.TAB_KEYS), {k: bool(their["tabs"].get(k)) for k in lt.TAB_KEYS})
ok("and the 28 KB never went into meta.json, which the Library polls",
   "tabs" not in store.read_json(os.path.join(store.library_dir(), TEAMMATE, "meta.json")))
ok("the search picture reads the same on their Mac as on his",
   their["tabs"]["search_picture"] == store.read_library_tabs(item1)["search_picture"])

served_theirs = lt.served(their)
ok("the route serves them the kept copy, because they have no run",
   served_theirs["source"] == "saved" and served_theirs["search_picture"], served_theirs.get("source"))
ok("a row with no run still draws a strip, or there is no way in to the tabs",
   sorted(m["key"] for m in their["milestones"] if m["exists"]) ==
   ["draft", "edited", "picture", "plan", "research"], their["milestones"])

# a later meta-only update (a status change) must not wipe what they have
status_only = mirror.to_wire("library", TEAMMATE, dict(their, tabs=None, status="published"), actor="Ravi")
mirror.apply({"id": 2, "kind": "library", "op": "update", "key": TEAMMATE,
              "payload": status_only, "actor": "Ravi"})
ok("a later update carrying no tabs leaves theirs alone",
   bool(store.read_library_tabs(TEAMMATE)) and store.library_get(TEAMMATE)["status"] == "published",
   store.library_get(TEAMMATE).get("status"))


# ---- 3. serving: the run wins while it is there, the kept copy after --------------------------------
print("\nthe run is read first while it is there; the kept copy answers once it is gone")

live = lt.served(store.library_get(item1))
ok("a live run is assembled fresh", live["source"] == "run", live["source"])
ok("and nothing is reported dropped", live["dropped"] == [])

# the freshest wins: change the run under the kept copy and the route follows the run
store.save_artifact(c1, r1, "research.json", dict(RESEARCH, angle="A different angle"))
ok("a changed run shows through immediately, the kept copy does not go stale on screen",
   lt.served(store.library_get(item1))["research"]["angle"] == "A different angle")

kill_run(c1)
gone = lt.served(store.library_get(item1))
ok("with the run deleted the kept copy answers", gone["source"] == "saved", gone["source"])
ok("and it is the tabs as they were kept, not an empty shell",
   gone["search_picture"]["primary"]["keyword"] == "cost per hire" and gone["research"]["angle"] ==
   RESEARCH["angle"], gone["research"])
ok("the strip survives the run too, so the overlay can still be opened",
   sorted(m["key"] for m in store.library_get(item1)["milestones"] if m["exists"]) ==
   ["draft", "edited", "picture", "plan", "research"], store.library_get(item1)["milestones"])

print("\nan article whose steps were never kept says so, rather than drawing an empty tab")
c3 = store.new_chat("no tabs ever")
MADE.append(c3)
r3 = store.new_run(c3, "old")
old_id = store.library_save(c3, r3, "An old article", DRAFT)
ITEMS.append(old_id)
kill_run(c3)
never = lt.served(store.library_get(old_id))
ok("every tab is None", all(never[k] is None for k in lt.TAB_KEYS), never)
ok("and the source says which kind of empty this is", never["source"] == "none", never["source"])
ok("a row nobody kept tabs for still says nothing about milestones, exactly as before",
   store.library_get(old_id)["milestones"] == [], store.library_get(old_id)["milestones"])


# ---- 4. the size guard ------------------------------------------------------------------------------
print("\nthe size guard: the largest tab is dropped, the smaller ones are kept, on the record")

small = {"search_picture": {"primary": {"keyword": "k"}}, "research": {"angle": "a"},
         "architect": {"sections": ["x" * (lt.TABS_MAX_BYTES + 5000)]}, "edits": {"passes": ["p"]}}
fitted, dropped = lt.fit(small)
ok("the one over the ceiling is dropped", dropped == ["architect"], dropped)
ok("the other three are untouched",
   fitted["search_picture"] and fitted["research"] and fitted["edits"] and fitted["architect"] is None)
ok("and the result is under the ceiling", lt._bytes(fitted) <= lt.TABS_MAX_BYTES, lt._bytes(fitted))
ok("a normal set is not touched at all", lt.fit(small if False else {
    "search_picture": {"a": 1}, "research": None, "architect": None, "edits": None}) ==
   ({"search_picture": {"a": 1}, "research": None, "architect": None, "edits": None}, []))

c4, r4, item4 = full_run("a very big architect")
store.save_artifact(c4, r4, "work-headings.json", {"structure": dict(
    HEADINGS["structure"], sections=[{"headline": "h" * 900, "h3s": ["x" * 900]} for _ in range(400)])})
big = lt.save(item4)
ok("the real save path applies the guard too", big["dropped"] == ["architect"], big.get("dropped"))
ok("the architect tab is the one that went", big["architect"] is None)
ok("the other three survived", all(big[k] for k in ("search_picture", "research", "edits")))
ok("what was dropped is on the row, so the screen can say so",
   (store.library_get(item4)["tabs_saved"] or {}).get("dropped") == ["architect"],
   store.library_get(item4).get("tabs_saved"))
ok("and it is not counted as kept",
   "architect" not in (store.library_get(item4)["tabs_saved"] or {}).get("kept", []))
ok("the file that will travel is under the ceiling",
   lt._bytes(store.read_library_tabs(item4)) <= lt.TABS_MAX_BYTES,
   lt._bytes(store.read_library_tabs(item4)))
kill_run(c4)
after_guard = lt.served(store.library_get(item4))
ok("the served payload names the dropped tab", after_guard["dropped"] == ["architect"], after_guard["dropped"])


# ---- 5. the backfill ---------------------------------------------------------------------------------
print("\nthe one-off backfill: every row whose run is still here, once")


class Team(object):
    """The team's `library` table, as far as a push is concerned. Same stub as the Library
    backfill suite next door: an upsert of one row, and a select of the ids already there."""

    def __init__(self):
        self.library = {}
        self.calls = []
        self.on = True

    def configured(self):
        return self.on

    def actor(self):
        return "Devansh"

    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        return [{"item_id": k} for k in self.library]

    def one(self, table, where=None, columns="*"):
        return {}

    def upsert(self, table, rows, on_conflict=None):
        assert table == "library", "a tabs backfill wrote to the %r table" % table
        for r in rows:
            self.library[str(r["item_id"])] = dict(r)
        self.calls.append((table, [dict(r) for r in rows]))

    def delete(self, table, where):
        raise AssertionError("a tabs backfill never deletes")


TEAM = Team()
sync._client = lambda client=None: client if client is not None else TEAM

for item in outbox.pending():
    try:
        os.remove(item["_path"])
    except OSError:
        pass
shutil.rmtree(store.library_dir(), ignore_errors=True)
for c in MADE:
    shutil.rmtree(store.chat_dir(c), ignore_errors=True)
MADE[:] = []
ITEMS[:] = []
_st = sync.read_state()
_st.pop("tabs_backfill", None)
sync._save_state(_st)

cA, rA, itemA = full_run("has its run")           # run still here: the tabs can be assembled
cB, rB, itemB = full_run("run deleted")           # run gone: nothing to assemble, ever
kill_run(cB)

got = sync.backfill_tabs(now=1000.0)
ok("it sent something", got == "sent", got)
ok("the row with a run got its tabs", bool(store.read_library_tabs(itemA)))
ok("and went to the team", itemA in TEAM.library, sorted(TEAM.library))
ok("the tabs went with it",
   isinstance((TEAM.library.get(itemA) or {}).get("meta", {}).get("tabs"), dict),
   sorted((TEAM.library.get(itemA) or {}).get("meta", {})))
ok("the row with no run has no tabs to keep", store.read_library_tabs(itemB) is None)
ok("but it was looked at, and says so",
   (store.library_get(itemB).get("tabs_saved") or {}).get("kept") == [],
   store.library_get(itemB).get("tabs_saved"))
ok("which is what gives it a strip, so its tabs can be opened and can say they were not kept",
   [m["key"] for m in store.library_get(itemB)["milestones"] if m["exists"]] == ["draft"],
   store.library_get(itemB)["milestones"])
ok("and that article's tabs say exactly that",
   lt.served(store.library_get(itemB))["source"] == "none")
ok("it remembers that it has finished",
   (sync.read_state().get("tabs_backfill") or {}).get("done") is True, sync.read_state().get("tabs_backfill"))

print("\nit is idempotent, and it is a SEND, never an edit")
meta_before = store.read_json(os.path.join(store.library_dir(), itemA, "meta.json"))
tabs_before = store.read_library_tabs(itemA)
calls_before = list(TEAM.calls)
ok("a second pass does nothing at all",
   sync.backfill_tabs(now=99999.0) == "" and TEAM.calls == calls_before, TEAM.calls)
_st = sync.read_state()
_st.pop("tabs_backfill", None)                    # even with its memory thrown away
sync._save_state(_st)
ok("and neither does one whose memory was lost: the rows say for themselves that they are done",
   sync.backfill_tabs(now=99999.0) == "" and TEAM.calls == calls_before, TEAM.calls)
ok("meta.json is what it was: no version bump, no editor stamped",
   store.read_json(os.path.join(store.library_dir(), itemA, "meta.json")) == meta_before)
ok("and the tabs themselves were not rewritten", store.read_library_tabs(itemA) == tabs_before)

print("\nwith no workspace it does nothing, quietly")
TEAM.on = False
_st = sync.read_state()
_st.pop("tabs_backfill", None)
sync._save_state(_st)
cC, rC, itemC = full_run("no workspace")
ok("no tabs kept, nothing sent",
   sync.backfill_tabs(now=1000.0) == "" and store.read_library_tabs(itemC) is None)
TEAM.on = True


# ---- 6. the route ------------------------------------------------------------------------------------
print("\nthe route itself")

# see test_library_tabs.py on this: importing agents_api re-pins the data dir to the person's
# saved company, so the one this suite has been using is captured first and reasserted after.
_data_dir = store.data_dir()
try:
    import agents_api
    store.set_data_dir(_data_dir)
except Exception as e:                                        # noqa: BLE001
    agents_api = None
    print("  SKIP  the route itself (agents_api would not import: %s)" % str(e)[:120])
if agents_api:
    res = agents_api.api_library_tabs(itemA)
    ok("the route answers with the four tabs plus where they came from",
       isinstance(res, dict) and set(res) == set(lt.TAB_KEYS) | {"source", "dropped"}, res and sorted(res))
    ok("assembled from the run, which is still there", res["source"] == "run", res["source"])
    kill_run(cA)
    res2 = agents_api.api_library_tabs(itemA)
    ok("and from the kept copy once it is not", res2["source"] == "saved", res2["source"])
    ok("with the same search picture either way",
       res2["search_picture"] == res["search_picture"])


# ---- clean up -------------------------------------------------------------------------------
for i in ITEMS:
    store.library_delete(i)
for c in MADE:
    shutil.rmtree(store.chat_dir(c), ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
