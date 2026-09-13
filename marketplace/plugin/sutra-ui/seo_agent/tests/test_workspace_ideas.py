"""The idea sheet reaches the team (2026-09-13).

Owner: "why is the asset ideas tab not getting updated when users write the code in the
connections". A teammate who joined got the catalogue and the brand pack and an empty Asset ideas
tab, for good. The sheet was designed to travel as rows in the team's `ideas` table, and mirror.py
could receive them, but nothing ever sent one, and the knowledge pack does not carry assets/. On the
owner's workspace the table held 0 rows while his Mac held 1,892.

What this suite holds on to, because each is how it would hurt somebody:
  * with no workspace the file is written and nothing else happens
  * a tick reaches the team through the queue, so it survives the wifi dropping
  * saving a sheet that did not change sends nothing
  * rewriting the whole sheet goes in a few bulk requests, not one request per idea
  * a bulk request that fails loses nothing: what did not go waits on disk
  * rows that came FROM the team are never sent back, or they would bounce between Macs for ever
  * what the sender had is exactly what the receiver gets
  * a sheet built before any of this reaches a team whose table is empty, once, and only once
"""
import os
import sys
import time

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

from seo_agent.assets import _common as acm
from seo_agent.workspace import mirror, outbox, sync

FAILS = []


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


class Team(object):
    """The team's project, as far as ideas go: one table keyed by idea_id.

    Faithful to the only two things this path does to it: an upsert (one row from the queue, or a
    chunk from the bulk route) and a one-row select asking whether the table is empty.
    """

    def __init__(self):
        self.ideas = {}
        self.calls = []          # (rows in the request, on_conflict) for every write that landed
        self.fail_writes = 0
        self.on = True

    def configured(self):
        return self.on

    def actor(self):
        return "Devansh"

    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        assert table == "ideas", "only the ideas table is asked about on this path, got %r" % table
        rows = list(self.ideas.values())
        return rows[:int(limit)] if limit else rows

    def one(self, table, where=None, columns="*"):
        return {}

    def upsert(self, table, rows, on_conflict=None):
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("the network is down")
        assert table == "ideas", "an idea push wrote to the %r table" % table
        for r in rows:
            self.ideas[str(r["idea_id"])] = dict(r)
        self.calls.append((len(rows), on_conflict))

    def delete(self, table, where):
        raise AssertionError("an idea push never deletes")


TEAM = Team()
# The whole real chain runs -- save_ideas, push_ideas, push, the queue, drain, _send -- and only
# the client at the very end is the team's project in memory.
sync._client = lambda client=None: client if client is not None else TEAM


def sheet(n, start=0, status="open"):
    return [{"id": "a%04d" % i, "title": "Idea %d" % i, "format": "Calculator",
             "status": status, "rank": i + 1, "method": ["competitors"]}
            for i in range(start, start + n)]


def reset():
    TEAM.ideas.clear()
    TEAM.calls[:] = []
    TEAM.fail_writes = 0
    TEAM.on = True
    for item in outbox.pending():
        try:
            os.remove(item["_path"])
        except OSError:
            pass
    st = sync.read_state()
    st.pop("ideas_backfill", None)
    sync._save_state(st)
    acm.save_ideas([], push=False)


# ---- no workspace ------------------------------------------------------------------------------
print("with no workspace, the sheet is written and nothing else happens")
reset()
TEAM.on = False
acm.save_ideas(sheet(3))
ok("the file is written", len(acm.ideas()) == 3, acm.ideas())
ok("nothing went anywhere", TEAM.calls == [] and outbox.count() == 0, (TEAM.calls, outbox.count()))

# ---- a tick ------------------------------------------------------------------------------------
print("\na tick reaches the team, through the queue")
reset()
acm.save_ideas(sheet(3), push=False)             # the sheet as it stood
rows = sheet(3)
rows[1]["status"] = "done"
acm.save_ideas(rows)
ok("exactly one row went up, in one request", TEAM.calls == [(1, None)], TEAM.calls)
ok("it is the idea that was ticked", sorted(TEAM.ideas) == ["a0001"], sorted(TEAM.ideas))
ok("and it arrives ticked", TEAM.ideas.get("a0001", {}).get("ticked") is True, TEAM.ideas.get("a0001"))
ok("nothing is left waiting in the queue", outbox.count() == 0, outbox.count())

before = list(TEAM.calls)
acm.save_ideas(rows)
ok("saving the same sheet again sends nothing", TEAM.calls == before, TEAM.calls)

# ---- a whole-sheet rewrite ---------------------------------------------------------------------
print("\nrewriting the whole sheet goes in bulk, not one request per idea")
reset()
acm.save_ideas(sheet(1200))
ok("three requests for 1,200 ideas", len(TEAM.calls) == 3, TEAM.calls)
ok("none bigger than the chunk", all(n <= sync.IDEAS_BULK_CHUNK for n, _ in TEAM.calls), TEAM.calls)
ok("every one keyed on idea_id, so a retry replaces instead of duplicating",
   all(oc == "idea_id" for _, oc in TEAM.calls), TEAM.calls)
ok("all 1,200 are on the team", len(TEAM.ideas) == 1200, len(TEAM.ideas))

# ---- a bulk request that fails -----------------------------------------------------------------
print("\na bulk request that fails loses nothing")
reset()
TEAM.fail_writes = 10 ** 6                       # down, and staying down
res = sync.push_ideas([], sheet(60))
ok("it says the network was the reason", "network" in (res.get("why") or ""), res)
ok("nothing reached the team", len(TEAM.ideas) == 0, len(TEAM.ideas))
ok("all 60 are waiting on disk", outbox.count() == 60, outbox.count())
TEAM.fail_writes = 0
outbox.drain(TEAM, now=time.time() + 10 ** 6)    # well past every backoff
ok("when the network is back, every one reaches the team", len(TEAM.ideas) == 60, len(TEAM.ideas))
ok("and the queue is empty again", outbox.count() == 0, outbox.count())

# ---- no bounce ---------------------------------------------------------------------------------
print("\nrows that came FROM the team are never sent back")
reset()
theirs = sheet(1, 100)[0]
incoming = [{"kind": "ideas", "key": "a0100", "op": "insert",
             "payload": mirror.to_wire("ideas", "a0100", theirs, actor="Ravi")}]
mirror._ideas(incoming)
ok("the teammate's idea landed in the sheet",
   any(r.get("id") == "a0100" for r in acm.ideas()), acm.ideas())
ok("and nothing was sent back up", TEAM.calls == [] and outbox.count() == 0,
   (TEAM.calls, outbox.count()))

# ---- the round trip ----------------------------------------------------------------------------
print("\nwhat the sender had is exactly what the receiver gets")
row = sheet(1)[0]
row["status"] = "done"
row["notes"] = "ticked by Ravi"
back = mirror.from_wire("ideas", row["id"], mirror.to_wire("ideas", row["id"], row, actor="Ravi"))
ok("the row survives the trip unchanged", back == row, (back, row))

# ---- the backfill ------------------------------------------------------------------------------
print("\na sheet built before any of this reaches a team whose table is empty, once")
reset()
acm.save_ideas(sheet(700), push=False)           # the owner's sheet, from before ideas were pushed
got = sync.backfill_ideas(now=1000.0)
ok("it sent them", got == "sent", got)
ok("all 700, in bulk", len(TEAM.ideas) == 700 and len(TEAM.calls) == 2, (len(TEAM.ideas), TEAM.calls))
ok("and it remembers that it has", (sync.read_state().get("ideas_backfill") or {}).get("done") is True,
   sync.read_state().get("ideas_backfill"))
TEAM.calls[:] = []
ok("so the next poll sends nothing", sync.backfill_ideas(now=99999.0) == "" and TEAM.calls == [],
   TEAM.calls)

reset()
acm.save_ideas(sheet(5), push=False)
TEAM.ideas["zzz"] = {"idea_id": "zzz", "title": "already the team's"}
ok("a team that already has ideas is left alone",
   sync.backfill_ideas(now=1000.0) == "" and TEAM.calls == [], TEAM.calls)
ok("for good", (sync.read_state().get("ideas_backfill") or {}).get("done") is True,
   sync.read_state().get("ideas_backfill"))

reset()
acm.save_ideas(sheet(40), push=False)
TEAM.fail_writes = 10 ** 6
sync.backfill_ideas(now=1000.0)
ok("a backfill that could not finish is not marked done",
   (sync.read_state().get("ideas_backfill") or {}).get("done") is False,
   sync.read_state().get("ideas_backfill"))
TEAM.fail_writes = 0
for item in outbox.pending():                    # the fallback's copies, so the retry is measured alone
    os.remove(item["_path"])
TEAM.calls[:] = []
ok("and it does not try again on every poll",
   sync.backfill_ideas(now=1000.0 + sync.IDEAS_BACKFILL_EVERY - 1) == "" and TEAM.calls == [],
   TEAM.calls)
ok("but it does once the wait is over",
   sync.backfill_ideas(now=1000.0 + sync.IDEAS_BACKFILL_EVERY + 1) == "sent" and len(TEAM.ideas) == 40,
   (TEAM.calls, len(TEAM.ideas)))

reset()
TEAM.on = False
acm.save_ideas(sheet(5), push=False)
ok("with no workspace there is nothing to backfill", sync.backfill_ideas(now=1000.0) == "", TEAM.calls)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all idea-sheet sync checks passed")
