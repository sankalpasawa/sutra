"""The Library's first trip to the team (2026-09-17).

Found on Devansh's own Mac: 3 Library rows, an empty outbox, 9 outbox-sent.json entries and ZERO
of them for `library` -- none of his articles had ever reached Supabase. loop.save_to_library only
started pushing a `library` row on 2026-09-16, and nothing about a FINISHED article ever changes
again to trigger an ordinary push, so every row saved before that date was stuck on its own Mac
for good.

Unlike the idea sheet (one all-or-nothing gate: "does the team have ANY ideas"), Library rows
arrive one article at a time from possibly many Macs, so a team can already hold some of a
person's rows and be missing others. This suite proves sync.backfill_library():
  * with no workspace it does nothing
  * a row the team is missing is sent, once, through the same push("library", id, library_get(id))
    path a fresh save uses -- never a second table, never a bumped version, never a touched editor
  * a row the team already has is left alone
  * a mix sends only what is missing
  * a failure (the team unreachable) is recorded, not marked done, and retried after the same gap
    the ideas backfill uses -- never on every poll
"""
import os
import sys
import time

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

from seo_agent import store
from seo_agent.workspace import mirror, outbox, sync

FAILS = []


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


class Team(object):
    """The team's project, as far as the Library goes: one table keyed by item_id.

    Faithful to the only two things a push and a backfill do to it: an upsert (one row, from the
    queue) and a select of every item_id already there.
    """

    def __init__(self):
        self.library = {}
        self.calls = []          # (table, rows) for every write that landed
        self.fail_writes = 0
        self.fail_reads = 0
        self.on = True

    def configured(self):
        return self.on

    def actor(self):
        return "Devansh"

    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        assert table == "library", "only the library table is asked about on this path, got %r" % table
        if self.fail_reads:
            self.fail_reads -= 1
            raise RuntimeError("the network is down")
        rows = [{"item_id": k} for k in self.library]
        return rows[:int(limit)] if limit else rows

    def one(self, table, where=None, columns="*"):
        return {}

    def upsert(self, table, rows, on_conflict=None):
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("the network is down")
        assert table == "library", "a library push wrote to the %r table" % table
        for r in rows:
            self.library[str(r["item_id"])] = dict(r)
        self.calls.append((table, [dict(r) for r in rows]))

    def delete(self, table, where):
        raise AssertionError("a library backfill never deletes")


TEAM = Team()
# The whole real chain runs -- backfill_library, push, the queue, drain, _send -- and only the
# client at the very end is the team's project in memory.
sync._client = lambda client=None: client if client is not None else TEAM


def article(n, status="ready"):
    """A finished Library row, saved the way store.library_finish always has -- with no push, the
    way every row saved before 2026-09-16 sits on disk today."""
    item_id = "run-c%03d-r%03d" % (n, n)
    store.library_finish(item_id, "Article %d" % n, "# Article %d\n\nbody text." % n,
                         {"primary_keyword": "kw-%d" % n}, chat_id="c%03d" % n, run_id="r%03d" % n)
    return item_id


def reset():
    TEAM.library.clear()
    TEAM.calls[:] = []
    TEAM.fail_writes = 0
    TEAM.fail_reads = 0
    TEAM.on = True
    for item in outbox.pending():
        try:
            os.remove(item["_path"])
        except OSError:
            pass
    st = sync.read_state()
    st.pop("library_backfill", None)
    sync._save_state(st)
    import shutil
    if os.path.isdir(store.library_dir()):
        shutil.rmtree(store.library_dir())


# ---- no workspace --------------------------------------------------------------------------------
print("with no workspace, nothing happens")
reset()
TEAM.on = False
article(1)
ok("a clean no-op", sync.backfill_library(now=1000.0) == "" and TEAM.calls == [], TEAM.calls)
ok("and nothing queued either", outbox.count() == 0, outbox.count())

# ---- rows missing on the team ---------------------------------------------------------------------
print("\nrows the team is missing are sent, once")
reset()
ids = [article(i) for i in range(3)]
got = sync.backfill_library(now=1000.0)
ok("it sent them", got == "sent", got)
ok("all three landed on the team", sorted(TEAM.library) == sorted(ids), (sorted(TEAM.library), ids))
ok("it remembers that it has finished", (sync.read_state().get("library_backfill") or {}).get("done") is True,
   sync.read_state().get("library_backfill"))
before = list(TEAM.calls)
ok("so the next poll sends nothing more", sync.backfill_library(now=99999.0) == "" and TEAM.calls == before,
   TEAM.calls)

# ---- never a second edit ---------------------------------------------------------------------------
print("\nit is a SEND, never an edit: no version bump, no touched editor")
reset()
item_id = article(9)
before_meta = store.read_json(os.path.join(store.library_dir(), item_id, "meta.json"))
sync.backfill_library(now=1000.0)
after_meta = store.read_json(os.path.join(store.library_dir(), item_id, "meta.json"))
ok("meta.json on disk is byte-for-byte what it was before the backfill", after_meta == before_meta,
   (before_meta, after_meta))

# ---- rows already there ----------------------------------------------------------------------------
print("\nrows already on the team are left alone")
reset()
have_id = article(5)
missing_id = article(6)
TEAM.library[have_id] = {"item_id": have_id, "title": "already the team's"}
got = sync.backfill_library(now=1000.0)
ok("it still sent something (the missing one)", got == "sent", got)
ok("the already-there row was never re-sent", TEAM.library[have_id] == {"item_id": have_id, "title": "already the team's"},
   TEAM.library[have_id])
ok("but the missing one arrived", missing_id in TEAM.library, TEAM.library)
ok("exactly one write landed", len(TEAM.calls) == 1 and len(TEAM.calls[0][1]) == 1, TEAM.calls)

# ---- a team with everything already --------------------------------------------------------------
print("\na team that already has every row is left alone, and marked done")
reset()
one_id = article(7)
TEAM.library[one_id] = {"item_id": one_id}
ok("nothing sent", sync.backfill_library(now=1000.0) == "" and TEAM.calls == [], TEAM.calls)
ok("and marked done, so a later poll costs nothing",
   (sync.read_state().get("library_backfill") or {}).get("done") is True,
   sync.read_state().get("library_backfill"))

# ---- a failure is recorded and retried later -------------------------------------------------------
print("\na failure is recorded, not marked done, and retried after the gap -- never on every poll")
reset()
article(8)
TEAM.fail_reads = 10 ** 6          # the team's table cannot even be read
sync.backfill_library(now=1000.0)
bf = sync.read_state().get("library_backfill") or {}
ok("not marked done", bf.get("done") is False, bf)
ok("the reason is on record", "network" in (bf.get("why") or ""), bf)
TEAM.calls[:] = []
ok("no retry before the gap", sync.backfill_library(now=1000.0 + sync.LIBRARY_BACKFILL_EVERY - 1) == ""
   and TEAM.calls == [], TEAM.calls)
TEAM.fail_reads = 0
ok("but it does once the wait is over",
   sync.backfill_library(now=1000.0 + sync.LIBRARY_BACKFILL_EVERY + 1) == "sent" and len(TEAM.library) == 1,
   (TEAM.calls, len(TEAM.library)))

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all library-backfill checks passed")
