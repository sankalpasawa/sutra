"""tests/test_workspace_sync.py — the sync engine: push, pull, the outbox, the mirror.

Entirely offline. There is a fake Supabase in this file — a dict of tables, an append-only log, and
a TRIGGER that writes the log when a row is written, exactly as `workspace/schema.sql` does. The
client never writes the log here either, which is the property the whole design rests on. The
tables' primary keys and the log's `op` column are taken from the real schema, so a change to it
breaks this suite rather than the first real workspace.

What it proves, in the order these things would hurt if they broke:

  * A CRASH MID-PULL REPLAYS, NEVER SKIPS. The cursor moves only after the rows it covers are on
    disk, so a process killed in the middle of applying a batch comes back and applies that batch
    again — and lands exactly the same state, not two copies of it. Losing a change silently is the
    worst thing this system could do.
  * A DELETION IS AN ORDINARY ROW. Forty pages going away is forty log rows, and they leave the
    catalogue AND content-database.jsonl together. No special path.
  * TRIMMING THE PAGES DELTA IS NOT A DELETION. `pages` is a delta that is emptied every time the
    pack is rebuilt, and if that read as "these pages are gone" every rebuild would wipe real pages
    out of everybody's catalogue.
  * THE OUTBOX DRAINS IN ORDER AND DOES NOT DOUBLE-APPLY. Offline, everything queues and nothing is
    lost. Back online, it sends in the order it was queued. A crash between the send and the queue
    file being removed replays into the ledger and drops the file rather than sending twice.
  * TWO CLIENTS CONVERGE. Two data dirs, one log: after both have polled, the two knowledge bases
    hold the same ideas, prompts, competitors, company record, CTA list and Library.
  * ONE BAD ROW CANNOT WEDGE THE LOG. A kind this build has never heard of, and a row that keeps
    failing, are both set aside to refused.jsonl and the changes behind them still land.

No model is called and no socket is opened.
"""
import os
import shutil
import sys
import tempfile
import time

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store                            # noqa: E402
from seo_agent.workspace import mirror, outbox, schema, sync    # noqa: E402

FAILS = []
CHECKS = [0]

# ONE CLOCK, shared by the fake database and the pull. `sync` reads time through `_now_epoch` for
# exactly this reason: the lag guard compares a cutoff it computes against an `at` the database
# stamped, and a test that let those two run off different clocks would prove nothing.
CLOCK = [None]


def now_epoch():
    return time.time() if CLOCK[0] is None else CLOCK[0]


def iso(epoch):
    """The `Z` form the pull sends and the database stores. Lexicographic order is chronological
    order in this format, which is what lets the fake compare them with `<`."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# THE STUBBED SERVER'S CLOCK, as an offset from this Mac's. The fake database stamps `at` from it
# (it IS the server) and the fake Date header reports it, so the two can never disagree — which is
# the whole point: the guard is about the gap between those two clocks.
SERVER_SKEW = [0.0]
SENDS_DATE = [True]


def server_epoch():
    return now_epoch() + SERVER_SKEW[0]


def fake_head(url, headers, timeout, **kw):
    """What `_common.request` hands back for the clock probe. Only `Date` is read off it."""
    class Resp(object):
        status_code = 200
        headers = ({"Date": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(server_epoch()))}
                   if SENDS_DATE[0] else {})
    return Resp()


sync._now_epoch = now_epoch
sync._probe = fake_head                  # NO TEST EVER OPENS A SOCKET


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


# ---- a Supabase made of dictionaries ---------------------------------------------------------------

class FakeDB(object):
    """One company's project. The TRIGGER lives here, on the table write, not in the client.

    That is not decoration: the whole reason the real design uses a database trigger is that a
    client which wrote both the row and its log entry could die between them. A fake where the
    client appends to the log would quietly test a system we are not building.

    Faithful to schema.sql in the three ways the protocol depends on: the log carries an `op`
    column, a DELETE logs `to_jsonb(old)` rather than a null, and the log's `key` is whichever
    primary key that table happens to use.
    """

    PK = {t: k for t, k in mirror.TABLES.values()}
    # WHICH TABLES A PROJECT ACTUALLY HAS, taken from the real schema. A table a migration added
    # does not exist on a workspace that has not run that migration, and PostgREST answers a write
    # to it with a 404 that never becomes anything else. A fake that accepted such a row would test
    # a database we are not building, and would prove nothing about the guard in sync.push.
    ADDED_IN = schema.ADDED_IN
    WORKSPACE = "w-0000"

    def __init__(self):
        self.tables = {}
        self.log = []
        self.writes = 0
        # HOW OLD A ROW IS STAMPED. Every test but the out-of-order one is about applying changes
        # that are long since committed, and stamping those at this instant would put every one of
        # them inside `sync.CHANGES_LAG_SECONDS` and hold them all back. A minute means "settled".
        # The race test sets this to 0 to get rows as fresh as a real insert makes them.
        self.settled = 60
        # What version this project's schema is on. A workspace created from today's schema.sql is
        # on schema.SCHEMA_VERSION; the owner's live one is older, and `push` asks before it queues
        # a change into a table a migration added.
        self.schema_version = 3
        # Log ids that have been ALLOCATED but whose transaction has not committed, so no reader
        # can see them yet. This is the bigserial race, in a dict.
        self.uncommitted = set()

    def _key_of(self, table, row):
        return str(row.get(self.PK[table]) or row.get("workspace_id") or self.WORKSPACE)

    def _trigger(self, table, op, key, payload, actor):
        # `at` is clock_timestamp() in the real schema: the wall clock at the INSERT, which is why
        # a row that commits late still carries an early time. The fake stamps it the same way.
        self.log.append({"id": len(self.log) + 1, "workspace_id": self.WORKSPACE,
                         "kind": table, "op": op, "key": str(key), "payload": payload,
                         "actor": actor or "unknown",
                         "at": iso(server_epoch() - self.settled)})
        return self.log[-1]["id"]

    def _must_exist(self, table):
        if self.ADDED_IN.get(table, 0) > self.schema_version:
            raise RuntimeError("Could not find the table 'public.%s' in the schema cache" % table)

    def upsert(self, table, rows):
        self._must_exist(table)
        for r in rows:
            row = dict(r)
            # workspace_id defaults in the database, which is what makes a second company row
            # impossible; the fake fills it the same way.
            row.setdefault("workspace_id", self.WORKSPACE)
            key = self._key_of(table, row)
            held = self.tables.setdefault(table, {})
            op = "update" if key in held else "insert"
            held[key] = row
            self.writes += 1
            self._trigger(table, op, key, dict(row), row.get("actor") or row.get("added_by"))

    def delete(self, table, where):
        self._must_exist(table)
        key = str(list(where.values())[0])
        old = self.tables.setdefault(table, {}).pop(key, None)
        self.writes += 1
        # A DELETE logs to_jsonb(OLD) — a perfectly ordinary payload. `op` is the only signal.
        self._trigger(table, "delete", key, dict(old or {}),
                      (old or {}).get("actor") or (old or {}).get("added_by"))

    def insert_uncommitted(self, table, rows):
        """Write a row and hold its transaction OPEN: it has an id, and nobody can read it yet."""
        before = len(self.log)
        self.upsert(table, rows)
        for row in self.log[before:]:
            self.uncommitted.add(row["id"])
        return [r["id"] for r in self.log[before:]]

    def commit(self):
        """The open transaction lands. Its rows become visible, keeping their original `at`."""
        self.uncommitted.clear()

    def log_after(self, last, limit):
        return [dict(r) for r in self.log
                if r["id"] > last and r["id"] not in self.uncommitted][:limit]


class FakeClient(object):
    """workspace/client.py, stubbed to the interface it really publishes."""

    def __init__(self, db, member_id="m-ravi", member_name="Ravi"):
        self.db = db
        self.member_id, self.member_name = member_id, member_name
        self.fail_writes = 0        # this many writes raise before any succeeds
        self.fail_reads = 0
        self.sent = []              # every write that actually reached the database

    # -- the connection. Settings live in connections.json, as the real client's do, so the
    #    cursor follows the data dir when a test switches Macs.
    def settings(self):
        conn = store.connections()
        return {"workspace_url": "https://fake.supabase.co", "workspace_key": "sb_publishable_x",
                "workspace_id": FakeDB.WORKSPACE, "member_id": self.member_id,
                "member_name": self.member_name,
                "last_seen_id": conn.get("last_seen_id") or 0}

    def save_settings(self, **fields):
        conn = store.connections()
        conn.update(fields)
        store.save_connections(conn)
        return self.settings()

    def configured(self):
        return True

    def headers(self, url=None, key=None, extra=None):
        return {"apikey": "sb_publishable_x", "x-sutra-actor": self.actor()}

    def actor(self):
        return self.member_name or self.member_id or "unknown"

    # -- rows
    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        """The pull's one query. Faithful to `_filter`: a value is a bare equal or an (op, value)."""
        if self.fail_reads:
            self.fail_reads -= 1
            raise RuntimeError("the network is down")
        assert table == "changes", "only the log is ever selected by sync"
        assert order == "id.asc", "the log is applied in id order"
        w = where or {}
        assert w.get("id", ("", 0))[0] == "gt", "the log is asked for by id > last_seen_id"
        rows = self.db.log_after(int(w["id"][1]), 10 ** 9)
        if "at" in w:                     # the lag clause. Absent means somebody deleted it.
            assert w["at"][0] == "lt"
            rows = [r for r in rows if r["at"] < w["at"][1]]
        return rows[:int(limit or 500)]

    def one(self, table, where=None, columns="*"):
        """The only row read that is not the log: `workspace`, for its schema_version. push() asks
        it before queueing a kind whose table a migration added (sync.KIND_NEEDS_VERSION)."""
        if self.fail_reads:
            self.fail_reads -= 1
            raise RuntimeError("the network is down")
        assert table == "workspace", "only the workspace row is read this way"
        return {"id": FakeDB.WORKSPACE, "schema_version": self.db.schema_version}

    def since(self, last_seen_id=None, limit=500):
        if self.fail_reads:
            self.fail_reads -= 1
            raise RuntimeError("the network is down")
        return self.db.log_after(int(last_seen_id or 0), int(limit or 500))

    def upsert(self, table, rows, on_conflict=None):
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("the network is down")
        self.db.upsert(table, rows)
        self.sent.append(("upsert", table, [dict(r) for r in rows]))

    def insert(self, table, rows):
        self.upsert(table, rows)

    def update(self, table, where, patch):
        self.upsert(table, [dict(patch, **where)])

    def delete(self, table, where):
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("the network is down")
        self.db.delete(table, where)
        self.sent.append(("delete", table, dict(where)))

    def upload(self, bucket, path, data):
        raise AssertionError("sync never touches the file cupboard")

    def download(self, bucket, path):
        raise AssertionError("sync never touches the file cupboard")


# ---- a fresh Mac ---------------------------------------------------------------------------------

MADE = []


def fresh_mac():
    """A clean data dir, pointed at, and returned. Nothing here shares state with anything else."""
    d = tempfile.mkdtemp(prefix="ws-sync-")
    MADE.append(d)
    store.set_data_dir(d)
    return d


def idea(n, title=None, status="open"):
    return {"id": "a%04d" % n, "title": title or ("Idea %d" % n), "rank": n,
            "status": status, "angle": "", "format": "calculator"}


def log_row(n, kind, key, payload, op="insert", actor="Devansh"):
    """A log row written straight into the fake, for the cases a push cannot produce."""
    return {"id": n, "kind": kind, "op": op, "key": key, "payload": payload,
            "actor": actor, "at": iso(now_epoch() - 60)}


def ideas_on_disk():
    from seo_agent.assets import _common as acm
    return acm.ideas()


def pages_on_disk():
    idx = store.knowledge("site_index.json") or {}
    return [p.get("url") for p in (idx.get("pages") or [])]


def bodies_on_disk():
    return [ln for ln in (store.knowledge("content-database.jsonl") or "").splitlines() if ln.strip()]


# =====================================================================================================
print("\na crash mid-pull replays, and never skips")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
for n in range(1, 6):
    sync.push("ideas", "a%04d" % n, idea(n), client=c)
ok("five pushes reached the database", len(db.tables.get("ideas", {})) == 5)
ok("the trigger wrote five log rows; the client wrote none", len(db.log) == 5)
ok("the sheet row travels in the data blob, and the readable columns beside it agree",
   db.tables["ideas"]["a0001"]["data"]["title"] == db.tables["ideas"]["a0001"]["title"])

real_apply = mirror.apply_batch
BOOM = [1]


def apply_that_dies(rows):
    if BOOM[0]:
        BOOM[0] -= 1
        real_apply(rows[:2])                  # some of it landed on disk...
        raise RuntimeError("power cut")       # ...and then the Mac went off
mirror.apply_batch = apply_that_dies
sync.mirror.apply_batch = apply_that_dies

r1 = sync.pull_once(client=c)
ok("the pull reports it was blocked", r1["blocked"] is True, r1)
ok("THE CURSOR DID NOT MOVE past a batch that did not finish", sync.last_seen_id(c) == 0,
   sync.last_seen_id(c))

mirror.apply_batch = real_apply
sync.mirror.apply_batch = real_apply
r2 = sync.pull_once(client=c)
rows = ideas_on_disk()
ok("the replay applied the whole batch", r2["applied"] == 5, r2)
ok("and left FIVE ideas, not seven and not ten", len(rows) == 5, len(rows))
ok("every idea arrived exactly once",
   sorted(r["id"] for r in rows) == ["a0001", "a0002", "a0003", "a0004", "a0005"])
ok("the cursor is now at the end of the log", sync.last_seen_id(c) == 5, sync.last_seen_id(c))
r3 = sync.pull_once(client=c)
ok("a pull with nothing new applies nothing", r3["applied"] == 0, r3)

# A crash BETWEEN batches: the finished batch must not be replayed.
fresh_mac()
db2 = FakeDB()
c2 = FakeClient(db2)
sync.push("ideas", "a0101", idea(101), client=c2)
sync.push("competitors", "rival.com", {"why": "same buyer"}, client=c2)
sync.push("ideas", "a0102", idea(102), client=c2)
BOOM[0] = 0
seen = []


def apply_second_run_dies(rows):
    seen.append(rows[0]["kind"])
    if rows[0]["kind"] == "competitors" and len(seen) == 2:
        raise RuntimeError("disk full")
    return real_apply(rows)
mirror.apply_batch = apply_second_run_dies
sync.mirror.apply_batch = apply_second_run_dies
sync.pull_once(client=c2)
ok("the cursor stopped at the end of the run that finished", sync.last_seen_id(c2) == 1,
   sync.last_seen_id(c2))
mirror.apply_batch = real_apply
sync.mirror.apply_batch = real_apply
seen[:] = []
r5 = sync.pull_once(client=c2)
ok("the replay picked up from there and applied the remaining two", r5["applied"] == 2, r5)
ok("the idea from the finished run was not applied a second time",
   [r["id"] for r in ideas_on_disk()] == ["a0101", "a0102"], [r["id"] for r in ideas_on_disk()])


# =====================================================================================================
print("\na deletion is an ordinary log row: 40 pages gone needs no special path")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
store.save_knowledge("site_index.json", {"domain": "example.com", "pages": []})
store.save_knowledge("content-database.jsonl", "")
for n in range(40):
    url = "https://example.com/p%02d" % n
    sync.push("pages", url, {"url": url, "title": "Page %d" % n, "type": "blog",
                             "body": "the words of page %d" % n}, client=c)
sync.pull_once(client=c)
ok("forty pages landed in the catalogue", len(pages_on_disk()) == 40, len(pages_on_disk()))
ok("and forty bodies landed beside them", len(bodies_on_disk()) == 40, len(bodies_on_disk()))

for n in range(40):
    sync.push_delete("pages", "https://example.com/p%02d" % n, client=c)
ok("a page going away is op='gone' on the row, NOT a deleted row",
   all(r["payload"].get("op") == "gone" for r in db.log[-40:]), db.log[-1])
r = sync.pull_once(client=c)
ok("all forty are gone from the catalogue", pages_on_disk() == [], pages_on_disk())
ok("and gone from content-database.jsonl too", bodies_on_disk() == [], len(bodies_on_disk()))
ok("the deletes went through the ordinary apply path", r["applied"] == 40, r)
ok("nothing was refused", r["refused"] == 0, r)

# one page back, then one page gone, with the other untouched
sync.push("pages", "https://example.com/keep", {"title": "Keep", "body": "still here"}, client=c)
sync.push("pages", "https://example.com/drop", {"title": "Drop", "body": "not for long"}, client=c)
sync.pull_once(client=c)
sync.push_delete("pages", "https://example.com/drop", client=c)
sync.pull_once(client=c)
ok("a single deletion removes exactly that page",
   pages_on_disk() == ["https://example.com/keep"], pages_on_disk())
ok("and exactly that body", len(bodies_on_disk()) == 1, bodies_on_disk())

# THE PACK TRIM. Emptying the pages delta must not empty anybody's catalogue.
c.delete("pages", {"url": "https://example.com/keep"})
ok("trimming the delta logs an ordinary delete", db.log[-1]["op"] == "delete", db.log[-1])
r = sync.pull_once(client=c)
ok("TRIMMING THE PAGES DELTA DOES NOT DELETE THE PAGE LOCALLY",
   pages_on_disk() == ["https://example.com/keep"], pages_on_disk())
ok("nor its body", len(bodies_on_disk()) == 1, bodies_on_disk())
ok("and the cursor still moved past it", r["blocked"] is False, r)

# an idea deleted the ordinary way — a real DELETE, because ideas is not a delta
sync.push("ideas", "a0007", idea(7), client=c)
sync.pull_once(client=c)
sync.push_delete("ideas", "a0007", client=c)
ok("an idea going away IS a deleted row", db.log[-1]["op"] == "delete", db.log[-1])
sync.pull_once(client=c)
ok("and it leaves the sheet with no code of its own",
   [r["id"] for r in ideas_on_disk()] == [], ideas_on_disk())


# =====================================================================================================
print("\nthe outbox: a plane, then the network comes back")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
c.fail_writes = 99                       # the plane
for n in range(1, 4):
    sync.push("ideas", "a%04d" % n, idea(n), client=c)
ok("nothing reached the database", db.writes == 0, db.writes)
ok("three changes are on disk, waiting", outbox.count() == 3, outbox.count())
ok("the queue says what is wrong", "network" in outbox.status()["last_error"], outbox.status())

res = outbox.drain(c)
ok("an immediate retry is held off by the backoff", res["sent"] == 0 and res["blocked"], res)
ok("and nothing was dropped for failing", outbox.count() == 3, outbox.count())

c.fail_writes = 0
res = outbox.drain(c, now=9e9)           # long after the backoff expired
ok("back online, the whole queue drains", res["sent"] == 3 and outbox.count() == 0, res)
ok("IN THE ORDER IT WAS QUEUED",
   [r[2][0]["idea_id"] for r in c.sent] == ["a0001", "a0002", "a0003"],
   [r[2][0]["idea_id"] for r in c.sent])

# order is the contract: a failure blocks the queue rather than being stepped over
outbox.clear()
c.sent[:] = []
offline = FakeClient(db)
offline.fail_writes = 99                 # still on the plane, so both edits stay queued
sync.push("ideas", "a0010", idea(10, "first"), client=offline)
sync.push("ideas", "a0010", idea(10, "second"), client=offline)
ok("two edits of one row are two queued items", outbox.count() == 2, outbox.count())
c.fail_writes = 1
res = outbox.drain(c, now=9e9)
ok("the head failing holds the queue rather than letting the later edit overtake",
   res["sent"] == 0 and outbox.count() == 2, res)
outbox.drain(c, now=9e9 + 100)
ok("once it clears, both go in order",
   [r[2][0]["title"] for r in c.sent] == ["first", "second"], [r[2][0]["title"] for r in c.sent])


# =====================================================================================================
print("\nreplaying the queue after a crash does not send twice")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
outbox.enqueue("ideas", "ideas", "idea_id", "a0055",
               row=mirror.to_wire("ideas", "a0055", idea(55), actor="Ravi"), actor="Ravi")
real_drop = outbox._drop
DIE = [1]


def drop_that_dies(path):
    if DIE[0]:
        DIE[0] -= 1
        raise RuntimeError("killed between the send and the delete")
    return real_drop(path)
outbox._drop = drop_that_dies
try:
    outbox.drain(c, now=9e9)
except RuntimeError:
    pass
outbox._drop = real_drop
ok("the send happened", len(c.sent) == 1, c.sent)
ok("the queue file is still there, because the process died before it was removed",
   outbox.count() == 1, outbox.count())
res = outbox.drain(c, now=9e9)
ok("THE REPLAY DID NOT SEND IT AGAIN", len(c.sent) == 1, len(c.sent))
ok("it dropped the file instead", outbox.count() == 0 and res["sent"] == 0, res)
ok("and the database holds one row, logged once", len(db.log) == 1, db.log)

# and the belt behind the braces: a genuine resend is an upsert, so it converges
wire = mirror.to_wire("ideas", "a0056", idea(56), actor="Ravi")
outbox.enqueue("ideas", "ideas", "idea_id", "a0056", row=wire, actor="Ravi", item_id="fixed-1")
outbox.drain(c, now=9e9)
outbox.enqueue("ideas", "ideas", "idea_id", "a0056", row=wire, actor="Ravi", item_id="fixed-2")
outbox.drain(c, now=9e9)
sync.pull_once(client=c)
ok("a row sent twice is still one idea on disk",
   len([r for r in ideas_on_disk() if r["id"] == "a0056"]) == 1, ideas_on_disk())


# =====================================================================================================
print("\ntwo clients converge on the same state")

from seo_agent.prompts import store as pstore   # noqa: E402

db = FakeDB()
mac_a, mac_b = tempfile.mkdtemp(prefix="ws-a-"), tempfile.mkdtemp(prefix="ws-b-")
MADE += [mac_a, mac_b]
a, b = FakeClient(db, "m-ravi", "Ravi"), FakeClient(db, "m-dev", "Devansh")

PROMPT = pstore.shipped_text("write/readable") + "\n\nRavi's line.\n"

store.set_data_dir(mac_a)
sync.push("ideas", "a0001", idea(1, "The salary benchmark"), client=a)
sync.push("ideas", "a0002", idea(2, "The hiring calculator", status="done"), client=a)
sync.push("prompts", "write/readable", PROMPT, client=a)
sync.push("competitors", "rival.com", {"why": "same buyer"}, client=a)
sync.push("company", "unused", {"brand": "Testlify", "domain": "testlify.com",
                                "brand_oneliner": "assessments that hire",
                                "niche_definition": "hiring assessments"}, client=a)
sync.push("library", "run-c1-r1", {"title": "How to hire", "draft": "# How to hire\n\nBody.\n",
                                   "status": "ready", "words": 3}, client=a)
sync.push("cta_links", "https://testlify.com/pricing", {"note": "the pricing page"}, client=a)
ra = sync.pull_once(client=a)

store.set_data_dir(mac_b)
rb = sync.pull_once(client=b)

ok("both Macs applied the same number of changes", ra["applied"] == rb["applied"] == 7,
   (ra["applied"], rb["applied"]))


def snapshot():
    from seo_agent.assets import _common as acm
    from seo_agent.brand import cta
    lib = store.library_get("run-c1-r1") or {}
    return {
        "ideas": sorted((r["id"], r.get("title"), r.get("status")) for r in acm.ideas()),
        "prompt": pstore.current_text("write/readable"),
        "competitors": sorted(r["domain"] for r in
                              (store.knowledge("competitors.json") or {}).get("competitors", [])),
        "company": {k: v for k, v in (store.knowledge("brand/company.json") or {}).items()
                    if k in ("brand", "domain", "brand_oneliner", "niche_definition")},
        "cta": sorted(r["url"] for r in cta.rows()),
        "library": (lib.get("title"), lib.get("draft")),
    }


snap_b = snapshot()
store.set_data_dir(mac_a)
snap_a = snapshot()

for field in ("ideas", "prompt", "competitors", "company", "cta", "library"):
    ok("the two Macs agree on %s" % field, snap_a[field] == snap_b[field],
       "\n    A=%r\n    B=%r" % (snap_a[field], snap_b[field]))
ok("the tick travelled with the idea", ("a0002", "The hiring calculator", "done") in snap_a["ideas"])
ok("the company push carries NO made-up workspace_id; the database fills it",
   all("workspace_id" not in r[2][0] for r in a.sent if r[1] == "company"),
   [r[2][0] for r in a.sent if r[1] == "company"])
ok("the company record landed under the names the rest of the code reads",
   snap_a["company"].get("brand_oneliner") == "assessments that hire", snap_a["company"])
ok("the prompt landed in the OVERRIDE dir, not the app bundle",
   os.path.exists(os.path.join(mac_a, "prompts", "write", "readable.md")))
ok("and it is the edited text the next article would use", "Ravi's line." in snap_b["prompt"])
ok("every applied change carries its actor, so the UI can say who",
   all(r["actor"] == "Ravi" for r in mirror.recent(20)), mirror.recent(3))

# and a later edit from the OTHER Mac travels back, last-write-wins
store.set_data_dir(mac_b)
sync.push("ideas", "a0001", idea(1, "The salary benchmark, redone"), client=b)
sync.pull_once(client=b)
title_b = [r["title"] for r in ideas_on_disk() if r["id"] == "a0001"][0]
store.set_data_dir(mac_a)
sync.pull_once(client=a)
title_a = [r["title"] for r in ideas_on_disk() if r["id"] == "a0001"][0]
ok("last write wins, on both Macs",
   title_a == title_b == "The salary benchmark, redone", (title_a, title_b))
ok("and the change is attributed to the person who made it",
   mirror.recent(1)[0]["actor"] == "Devansh", mirror.recent(1))


# =====================================================================================================
print("\npricing.md reaches the team in seconds, not minutes")
#
# The brand pack travels in the knowledge pack and goes on doing so. pricing.md is the exception:
# it is the ONE part of that pack a person types by hand, it holds prices no crawler can reach, and
# features.md -- what the writer reads for product claims -- is filled from it. Carried by the pack
# alone it reached teammates when the pack was next rebuilt, minutes later, with nothing saying so.

from seo_agent.brand import _common as bcm       # noqa: E402
from seo_agent.brand import features             # noqa: E402

PRICES = ("# Prices and hidden facts\n\n## Pricing and plans\n\nStarter is $69 a month billed "
          "annually, 100 credits a year. The trial runs 7 days with no card.\n")

db = FakeDB()
mac_a, mac_b = tempfile.mkdtemp(prefix="ws-pa-"), tempfile.mkdtemp(prefix="ws-pb-")
MADE += [mac_a, mac_b]
a, b = FakeClient(db, "m-ravi", "Ravi"), FakeClient(db, "m-dev", "Devansh")

# Mac A: a person types their prices in. The panel saves the file; `input_saved` is everything that
# has to happen next, and it is the only call the panel makes.
store.set_data_dir(mac_a)
bcm.save("pricing.md", PRICES)
saved = bcm.input_saved("pricing.md", PRICES, actor="Ravi", client=a)
ok("saving the form sends it to the team", saved["pushed"] is True, saved)
ok("as a row in its own table, never as a write to the log — the trigger owns the log",
   [(op, table) for op, table, _rows in a.sent] == [("upsert", "brand_inputs")], a.sent)
ok("and the log row the TRIGGER wrote carries the file name as its key",
   db.log[-1]["kind"] == "brand_inputs" and db.log[-1]["key"] == "pricing.md"
   and db.log[-1]["actor"] == "Ravi", db.log[-1])

# Mac B: a teammate with a brand pack already built, so there is something for the arriving price
# to make stale.
store.set_data_dir(mac_b)
bcm.save("features.md", "# Product facts\n\nStarter is $59 a month.\n")
bcm.save("writing-integrity.md", "# Writing integrity\n")
bcm.save("writer-brief.md", "# Writer brief\n")
features._stamp()
untouched_before = {f: os.path.getmtime(bcm.path(f))
                    for f in ("writing-integrity.md", "writer-brief.md")}
r = sync.pull_once(client=b)
ok("the prices land in the teammate's own brand pack, off the changes log",
   r["applied"] == 1 and bcm.read("pricing.md") == PRICES, (r, bcm.read("pricing.md")[:60]))
ok("and they read as somebody's writing, not as the blank form",
   bcm.exists("pricing.md") and not features.untouched(bcm.read("pricing.md")))

# THE ONE HOP. features.md is filled FROM pricing.md, so the Mac that RECEIVES a price has to
# rebuild its product facts or it goes on quoting the old one. Marked only -- the rebuild is model
# work and a poll thread does none.
ok("features.md is marked for a rebuild on the receiving Mac, the same way a local save marks it",
   features.pricing_stale() is True
   and (bcm.read(features.STAMP) or {}).get("pricing") == features.HAND_EDITED,
   bcm.read(features.STAMP))
ok("THE CHAIN STAYS ONE HOP: writing-integrity.md and writer-brief.md are not touched",
   all(os.path.getmtime(bcm.path(f)) == m for f, m in untouched_before.items()))
# It lands through brand/_common.save, which is where a brand file's format is decided -- including
# the HTML-entity tidy every builder's output goes through.
store.set_data_dir(mac_a)
sync.push("brand_inputs", "pricing.md", PRICES.replace("$69", "&gt; $69"), client=a, actor="Ravi")
store.set_data_dir(mac_b)
sync.pull_once(client=b)
ok("it lands through the module that owns the file, so an entity typed elsewhere is a character here",
   "> $69" in bcm.read("pricing.md") and "&gt;" not in bcm.read("pricing.md"),
   bcm.read("pricing.md")[:80])

# A NAME THAT IS NOT A TYPED-IN FORM IS REFUSED, never written blind. features.md is 13,219
# machine-written words that belong in the pack; a log row claiming otherwise must not overwrite it.
before_features = bcm.read("features.md")
db.log.append(log_row(len(db.log) + 1, "brand_inputs", "features.md", {"body": "# Nonsense\n"}))
r = sync.pull_once(client=b)
ok("a brand file that is not one of the typed-in forms is refused", r["refused"] == 1, r)
ok("and the file it named is untouched", bcm.read("features.md") == before_features)
ok("with the reason written down where somebody can see it",
   any("features.md" in (x.get("key") or "") for x in mirror.recent(5, mirror.REFUSED_LOG)))


# =====================================================================================================
print("\na workspace a version behind is told, not wedged")
#
# `brand_inputs` arrived at schema version 3. The owner's live workspace is on 2, where the table
# does not exist and a write to it can only ever 404. The outbox is a QUEUE with no maximum attempt
# count, so queueing that row would park it at the head for ever and hold every idea, article and
# prompt edit behind it. So push asks first and declines, and the pack carries the file as before.

fresh_mac()
old_db = FakeDB()
old_db.schema_version = 2
c = FakeClient(old_db)
item = sync.push("brand_inputs", "pricing.md", PRICES, client=c)
ok("a workspace with no such table is never handed a row for it", item is None)
ok("nothing was queued, so nothing can sit at the head of the queue for ever", outbox.count() == 0)
ok("and nothing reached the database either",
   not any(table == "brand_inputs" for _op, table, _rows in c.sent), c.sent)
ok("it says which change is waiting and why, rather than leaving it to be guessed at",
   (sync.status(client=c).get("needs_update") or {}).get("kind") == "brand_inputs"
   and "version 2" in (sync.status(client=c).get("needs_update") or {}).get("why", ""),
   sync.status(client=c).get("needs_update"))
sync.push("ideas", "a0001", idea(1), client=c)
r = sync.pull_once(client=c)
# THE CHECK THAT MATTERS. Take the guard out and this is the one that goes red: the undeliverable
# row sits at the head of the queue, backing off for ever, and the idea behind it never leaves the
# Mac. That is the failure the guard exists to stop, and it would be somebody's real workspace.
ok("EVERY OTHER CHANGE STILL GOES UP: the queue is not wedged behind it",
   outbox.count() == 0 and any(table == "ideas" for _op, table, _rows in c.sent)
   and [x["id"] for x in ideas_on_disk()] == ["a0001"], (outbox.count(), c.sent))

# The workspace is updated from the Connections tab, and the cached answer ages out.
st = sync.read_state()
st.pop("schema", None)
sync._save_state(st)
old_db.schema_version = 3
item = sync.push("brand_inputs", "pricing.md", PRICES, client=c)
ok("and the moment the update has run, the prices go up by themselves",
   item is not None and any(table == "brand_inputs" for _op, table, _rows in c.sent))
ok("and the warning clears itself", sync.status(client=c).get("needs_update") is None,
   sync.status(client=c).get("needs_update"))


# =====================================================================================================
print("\none bad row cannot wedge everybody's log")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
sync.push("ideas", "a0001", idea(1), client=c)
# a kind from a NEWER Sutra, straight into the log
db.log.append(log_row(len(db.log) + 1, "widgets", "w1", {"a": 1}))
sync.push("ideas", "a0002", idea(2), client=c)
r = sync.pull_once(client=c)
ok("the unknown kind was refused, not retried for ever", r["refused"] == 1, r)
ok("the changes behind it still landed", r["applied"] == 2, r)
ok("and it is written down where somebody can see it",
   any(x["kind"] == "widgets" for x in mirror.recent(10, mirror.REFUSED_LOG)))
ok("the cursor moved past it", sync.last_seen_id(c) == 3, sync.last_seen_id(c))

# the two tables that log but have nothing local: a no-op, not a refusal
db.log.append(log_row(len(db.log) + 1, "members", "m-dev",
                      {"member_id": "m-dev", "name": "Devansh"}, op="update"))
r = sync.pull_once(client=c)
ok("a members heartbeat is a no-op, not a refusal", r["refused"] == 0 and not r["blocked"], r)
ok("and it is not paraded on the activity line",
   all(x["kind"] != "members" for x in mirror.recent(10)))

# a row that keeps failing for a reason that MIGHT clear
fresh_mac()
db = FakeDB()
c = FakeClient(db)
sync.push("ideas", "a0003", idea(3), client=c)
sync.push("ideas", "a0004", idea(4), client=c)
POISON = ["a0003"]


def apply_poisoned(rows):
    if any(r["key"] in POISON for r in rows):
        raise RuntimeError("this row never applies")
    return real_apply(rows)
mirror.apply_batch = apply_poisoned
sync.mirror.apply_batch = apply_poisoned
tries = 0
while tries < sync.POISON_TRIES + 3 and sync.last_seen_id(c) < 1:
    sync.pull_once(client=c)
    tries += 1
mirror.apply_batch = real_apply
sync.mirror.apply_batch = real_apply
ok("a row that keeps failing is set aside after POISON_TRIES, not retried for ever",
   tries <= sync.POISON_TRIES + 2, tries)
ok("it is recorded as given up on, with its error",
   any("gave up" in (x.get("why") or "") for x in mirror.recent(10, mirror.REFUSED_LOG)))
sync.pull_once(client=c)
ok("and the change behind it finally lands",
   any(r["id"] == "a0004" for r in ideas_on_disk()), ideas_on_disk())


# =====================================================================================================
print("\nthe log is paged, and the client never writes it")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
big = sync.CHANGES_PAGE + 37
for n in range(big):
    db.log.append(log_row(n + 1, "ideas", "a%04d" % n,
                          mirror.to_wire("ideas", "a%04d" % n, idea(n))))
r = sync.pull_once(client=c)
ok("a log longer than one response is paged, not truncated", r["applied"] == big, r)
ok("it took more than one request", r["pages"] >= 2, r)
ok("every row landed", len(ideas_on_disk()) == big, len(ideas_on_disk()))

refused_log_write = False
try:
    outbox.enqueue("ideas", "changes", "id", "1", row={"id": 1})
except ValueError:
    refused_log_write = True
ok("NOTHING here can even QUEUE a write to the changes log; the trigger owns it", refused_log_write)


# =====================================================================================================
print("\na change committing out of order is not lost")
#
# The bigserial race, both ways round. `changes.id` is allocated at INSERT and not at COMMIT, so a
# row that took the LOWER id can become visible AFTER one that took a higher id. A poller that
# consumed the higher one first would move its cursor past a change it had never seen, and that
# change would then be unreachable for ever — the worst failure this system has, because nothing
# reports it and the two people quietly disagree from then on.
#
# Part (a) removes the guard and shows the loss. Part (b) puts it back and shows the change arrives.
# If somebody deletes the lag clause because three seconds looked like a mistake, (b) fails.

# ---- (a) WITHOUT the lag clause, to show exactly what is being guarded against
fresh_mac()
db = FakeDB()
db.settled = 0                              # rows stamped now, the way a real insert stamps them
c = FakeClient(db)
real_cutoff = sync._lag_cutoff
sync._lag_cutoff = lambda client=None: now_epoch() + 3600   # an hour ahead == no lag at all

db.insert_uncommitted("ideas", [mirror.to_wire("ideas", "a0007", idea(7))])   # log id 1, in flight
db.upsert("ideas", [mirror.to_wire("ideas", "a0008", idea(8))])               # log id 2, committed
ok("only the row that committed is readable", [r["id"] for r in db.log_after(0, 99)] == [2],
   db.log_after(0, 99))

r = sync.pull_once(client=c)
ok("without the lag the poller consumes it", r["applied"] == 1, r)
ok("and moves the cursor PAST the row still in flight", sync.last_seen_id(c) == 2,
   sync.last_seen_id(c))
db.commit()                                  # the earlier transaction lands, keeping its id and time
r = sync.pull_once(client=c)
ok("WITHOUT THE LAG THE EARLIER CHANGE IS LOST FOR EVER",
   r["applied"] == 0 and not any(x["id"] == "a0007" for x in ideas_on_disk()),
   [x["id"] for x in ideas_on_disk()])
sync._lag_cutoff = real_cutoff

# ---- (b) WITH it: the same sequence, and nothing is lost
fresh_mac()
db = FakeDB()
db.settled = 0
c = FakeClient(db)
CLOCK[0] = 1000000.0                         # a clock we can move by hand
sync.forget_skew()                           # ...and re-measure the skew against it

db.insert_uncommitted("ideas", [mirror.to_wire("ideas", "a0007", idea(7))])
db.upsert("ideas", [mirror.to_wire("ideas", "a0008", idea(8))])
r = sync.pull_once(client=c)
ok("the fresh head is held back: it is still inside the race window", r["applied"] == 0, r)
ok("so the cursor does not move", sync.last_seen_id(c) == 0, sync.last_seen_id(c))

db.commit()                                  # the in-flight write lands, still stamped earlier
CLOCK[0] += sync.CHANGES_LAG_SECONDS + 5     # and the window passes
r = sync.pull_once(client=c)
ok("once the window passes BOTH arrive", r["applied"] == 2, r)
ok("in id order, with the out-of-order one among them",
   [x["id"] for x in ideas_on_disk()] == ["a0007", "a0008"], [x["id"] for x in ideas_on_disk()])
ok("and the cursor is at the true end of the log", sync.last_seen_id(c) == 2, sync.last_seen_id(c))

# the guard must not also stall an idle log: settled rows go straight through
db.settled = 60
sync.push("ideas", "a0009", idea(9), client=c)
r = sync.pull_once(client=c)
ok("a settled change is not held back at all", r["applied"] == 1, r)
CLOCK[0] = None

ok("the lag is a named constant, and it is seconds not minutes",
   1.0 <= sync.CHANGES_LAG_SECONDS <= 10.0, sync.CHANGES_LAG_SECONDS)


# =====================================================================================================
print("\nthe reader's clock cannot defeat the guard")
#
# The lag above is only a guard if it is measured against the SERVER's clock. It is computed on this
# Mac, so a Mac running FAST would read rows still in flight and reopen the race — silently, on one
# person's machine. `sync` corrects for the gap using the `Date` header every response carries.
# These three prove the correction is real; delete it and the second one below reads an uncommitted
# row. A stubbed server whose clock we move by hand, and no socket is opened.


def clock_case(server_skew, sends_date):
    """A fresh Mac and a fresh database against a server whose clock is `server_skew` from ours."""
    fresh_mac()
    SERVER_SKEW[0], SENDS_DATE[0] = server_skew, sends_date
    CLOCK[0] = 2000000.0
    sync.forget_skew()
    db = FakeDB()
    return db, FakeClient(db)


def aged(db, c, key, seconds_old):
    """Put one change in the log, stamped `seconds_old` on the SERVER's clock."""
    db.settled = seconds_old
    sync.push("ideas", key, idea(int(key[1:])), client=c)


# ---- the server 30 seconds AHEAD of us: the cutoff has to move with it
db, c = clock_case(+30.0, True)
aged(db, c, "a0010", 10)                     # ten seconds old by the SERVER's clock: safe to apply
aged(db, c, "a0011", 0)                      # this instant: still inside the race window
ok("the skew was measured off the Date header", abs(sync._skew(c) - 30.0) < 1.5, sync._SKEW)
r = sync.pull_once(client=c)
ok("the cutoff moved with the server, so the settled change is applied", r["applied"] == 1, r)
ok("and it is the older one", [x["id"] for x in ideas_on_disk()] == ["a0010"], ideas_on_disk())
ok("NO IN-FLIGHT ROW IS READ", not any(x["id"] == "a0011" for x in ideas_on_disk()))
ok("uncorrected, this Mac would have held the settled one back and stalled",
   iso(now_epoch() - sync.CHANGES_LAG_SECONDS) < iso(server_epoch() - 10),
   "naive cutoff would be 33s behind the server")

# ---- the server 30 seconds BEHIND us: this is the direction that loses changes
db, c = clock_case(-30.0, True)
aged(db, c, "a0020", 300)                    # long settled
aged(db, c, "a0021", 0)                      # this instant on the server's clock
ok("the skew was measured, and it is negative", -31.5 < sync._skew(c) < -28.5, sync._SKEW)
r = sync.pull_once(client=c)
ok("it still makes progress and does not stall for ever", r["applied"] == 1, r)
ok("THE FRESH ROW IS STILL HELD, though this Mac's clock says it is 30s old",
   [x["id"] for x in ideas_on_disk()] == ["a0020"], ideas_on_disk())
ok("uncorrected, this Mac would have read it — that is the race, reopened",
   iso(now_epoch() - sync.CHANGES_LAG_SECONDS) > iso(server_epoch()),
   "naive cutoff would be 27s AHEAD of the server's own clock")
CLOCK[0] += 60                               # the window passes on the server's clock too
r = sync.pull_once(client=c)
ok("and it arrives once it really is old enough",
   [x["id"] for x in ideas_on_disk()] == ["a0020", "a0021"], ideas_on_disk())

# ---- no Date header at all: fall back to lagging MORE, never to the naive local clock
db, c = clock_case(0.0, False)
aged(db, c, "a0030", 300)                    # five minutes old: past even the conservative window
aged(db, c, "a0031", 10)                     # ten seconds old: the naive path would read this
ok("the skew is unknown, and says so", sync._skew(c) is None, sync._SKEW)
ok("and status() reports why, for whoever is looking at a stuck workspace",
   "Date" in (sync.status(c)["clock_skew"]["source"] or ""), sync.status(c)["clock_skew"])
r = sync.pull_once(client=c)
ok("it falls back to CONSERVATIVE, not to the naive local clock",
   [x["id"] for x in ideas_on_disk()] == ["a0030"], ideas_on_disk())
ok("so a ten-second-old change waits rather than being read early",
   not any(x["id"] == "a0031" for x in ideas_on_disk()))
ok("but it still makes progress: it does not stall for ever", r["applied"] == 1, r)
ok("the extra lag is a named constant and errs toward latency",
   sync.UNKNOWN_SKEW_LAG_SECONDS >= 10 * sync.CHANGES_LAG_SECONDS, sync.UNKNOWN_SKEW_LAG_SECONDS)

# ---- a Date claiming to be a year ahead is a broken clock, not a fact
db, c = clock_case(400 * 86400.0, True)
aged(db, c, "a0040", 300)
ok("a wildly forward Date is not believed", sync._skew(c) is None, sync._SKEW)
ok("and the reason is recorded", "believable" in (sync._SKEW["source"] or ""), sync._SKEW)

SERVER_SKEW[0], SENDS_DATE[0], CLOCK[0] = 0.0, True, None
sync.forget_skew()


# =====================================================================================================
print("\nthe poller: nobody presses sync")

fresh_mac()
db = FakeDB()
c = FakeClient(db)
for n in range(3):
    db.log.append(log_row(n + 1, "ideas", "a%04d" % n,
                          mirror.to_wire("ideas", "a%04d" % n, idea(n))))
p1 = sync.start(client=c, interval=0.01)
ok("start() gives back the one poller, not a second one", sync.start(client=c) is p1)
deadline = time.time() + 5
while time.time() < deadline and len(ideas_on_disk()) < 3:
    time.sleep(0.02)
got = len(ideas_on_disk())
sync.stop()
ok("the timer pulled the log with nobody pressing anything", got == 3, got)
ok("stop() ends it", not p1.is_alive())
ok("the interval is a named constant, and it is a few seconds",
   0.5 <= sync.POLL_SECONDS <= 5.0, sync.POLL_SECONDS)

# a read failure is not a crash and not a lost change
fresh_mac()
db = FakeDB()
c = FakeClient(db)
c.fail_reads = 1
r = sync.pull_once(client=c)
ok("a failed poll reports itself and moves nothing", r["blocked"] and r["applied"] == 0, r)


# =====================================================================================================
print("\nthe screen reads ONE dict")
#
# The Connections tab shows what is happening right now. It was inferring the pack half from a
# progress callback of its own, which is a screen deriving engine state from a side channel — it
# drifts the first time the engine changes, and the drift reads as a status line that is
# confidently wrong. `status()["pack"]` is that state from the Rebuilder itself.


class FakeRebuilder(object):
    """pack.Rebuilder's public surface, which is what sync reads and all it reads."""

    def __init__(self):
        self.running = False
        self.pending = False
        self.builds = 0
        self.last_error = None


fresh_mac()
db = FakeDB()
c = FakeClient(db)
sync._PACK.update({"rebuilder": None, "stage": "", "note": "", "at": None})

ok("with no pack attached the state is idle, not a crash",
   sync.status(c)["pack"]["state"] == "idle", sync.status(c)["pack"])

rb = FakeRebuilder()
sync.attach_pack(rb)
ok("attaching does not invent a build", sync.status(c)["pack"]["builds"] == 0)

# the panel passes sync.pack_progress straight in where its own callback was: same signature
rb.running, rb.builds = True, 1
sync.pack_progress("build", 0, 0, "updating the shared knowledge pack")
ok("a rebuild in flight reads as building", sync.status(c)["pack"]["state"] == "building",
   sync.status(c)["pack"])
ok("and the quiet line comes with it",
   "knowledge pack" in sync.status(c)["pack"]["note"], sync.status(c)["pack"])
sync.pack_progress("upload", 1, 2, "sending 1 of 2")
ok("the upload half reads as uploading", sync.status(c)["pack"]["state"] == "uploading")

rb.running = False
sync.pack_progress("done", 0, 0, "knowledge pack v2 shared")
ok("a finished rebuild is idle again", sync.status(c)["pack"]["state"] == "idle")

# THE REBUILDER'S OWN STATE WINS. A stage left over from the last run must not report "building"
# when nothing is running, nor "idle" while something is.
rb.running = True
ok("running beats a stale done", sync.status(c)["pack"]["state"] == "building",
   sync.status(c)["pack"])
rb.running, rb.pending = False, True
ok("a coalesced rebuild waiting behind the window says so",
   sync.status(c)["pack"]["state"] == "waiting", sync.status(c)["pack"])
rb.pending, rb.last_error = False, "the bucket is missing"
ok("a failed rebuild carries its reason",
   sync.status(c)["pack"]["last_error"] == "the bucket is missing")

# EVERY STAGE pack.py ACTUALLY EMITS IS MAPPED. Read out of their source rather than listed here,
# so a stage they add and I do not know about fails this instead of quietly reading as "idle" in
# the middle of an upload.
import re as _re                                                             # noqa: E402
_pack_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "workspace", "pack.py"), encoding="utf-8").read()
_stages = {m.group(1) for m in _re.finditer(r'(?:say|progress)\(\s*"([a-z_]+)"', _pack_src)}
ok("every stage pack.py emits is one sync knows how to show",
   _stages and _stages <= set(sync.PACK_STAGES), sorted(_stages - set(sync.PACK_STAGES)))

sync._PACK.update({"rebuilder": None, "stage": "", "note": "", "at": None})
ok("the outbox is in the same dict, so the screen asks once",
   "outbox" in sync.status(c) and "pack" in sync.status(c) and "clock_skew" in sync.status(c))


# =====================================================================================================
print("\nnobody presses sync, and a joiner is not left behind")

# start() is called by more than one thing and none of them should have to know about the others.
fresh_mac()
db = FakeDB()
c = FakeClient(db)
made = []
for _ in range(8):
    made.append(sync.start(client=c, interval=0.01))
ok("eight calls to start() make ONE poller", len(set(id(p) for p in made)) == 1)
ok("and it is running", made[0].is_alive())

import threading as _threading                                               # noqa: E402
racers = []
sync.stop()
barrier = _threading.Barrier(6)


def racer():
    barrier.wait()
    racers.append(sync.start(client=c, interval=0.01))


threads = [_threading.Thread(target=racer) for _ in range(6)]
for t in threads:
    t.start()
for t in threads:
    t.join()
ok("six threads calling start() at once still make ONE poller",
   len(set(id(p) for p in racers)) == 1, len(set(id(p) for p in racers)))
sync.stop()
ok("stop() ends it however many times it was started", not made[0].is_alive())

# ---- a joiner is level before the screen says they are done
fresh_mac()
db = FakeDB()
c = FakeClient(db)
# what the creator did before the pack was built, and what happened while it downloaded
for n in range(1, 4):
    sync.push("ideas", "a%04d" % n, idea(n), client=c)
boundary = len(db.log)                       # pack.publish writes this as workspace.pack_change_id
sync.push("ideas", "a0004", idea(4, "added while the pack was downloading"), client=c)
sync.push("competitors", "late.com", {"why": "added during the join"}, client=c)

# the joiner: pack.install has put a0001..a0003 on disk, and the panel saved the boundary
from seo_agent.assets import _common as _acm                                 # noqa: E402
_acm.save_ideas([idea(n) for n in range(1, 4)])
r = sync.catch_up(client=c, replay_from=boundary)
ok("the catch-up applied only what happened AFTER the pack", r["applied"] == 2, r)
ok("so the joiner has the late change before the screen says done",
   any(x["id"] == "a0004" for x in ideas_on_disk()), ideas_on_disk())
ok("and nothing in the pack was applied twice",
   [x["id"] for x in ideas_on_disk()] == ["a0001", "a0002", "a0003", "a0004"], ideas_on_disk())
ok("the cursor is level with the log", sync.last_seen_id(c) == len(db.log), sync.last_seen_id(c))

# the older-workspace case: no boundary at all means replay everything, which is slow, never wrong
fresh_mac()
db2 = FakeDB()
c2 = FakeClient(db2)
for n in range(1, 4):
    sync.push("ideas", "a%04d" % n, idea(n), client=c2)
_acm.save_ideas([idea(n) for n in range(1, 4)])
r = sync.catch_up(client=c2, replay_from=0)     # pack.join's `full_replay` case
ok("with no boundary it replays the whole log", r["applied"] == 3, r)
ok("and still lands three ideas, not six",
   [x["id"] for x in ideas_on_disk()] == ["a0001", "a0002", "a0003"], ideas_on_disk())

# a cursor is never wound BACKWARDS by a stale boundary
before = sync.last_seen_id(c2)
sync.catch_up(client=c2, replay_from=1)
ok("a stale boundary does not wind the cursor back", sync.last_seen_id(c2) == before,
   (before, sync.last_seen_id(c2)))

# and a join that finished must not be reported as failed by a flat network afterwards
c2.fail_reads = 1
r = sync.catch_up(client=c2)
ok("a catch-up that cannot reach the network says so instead of raising",
   r["blocked"] and r["applied"] == 0, r)


# =====================================================================================================
print("\nthe one door")

MINE = ("sync.py", "mirror.py", "outbox.py")
_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")
_src = {n: open(os.path.join(_pkg, n), encoding="utf-8").read() for n in MINE}
ok("no module of mine reaches for httpx at ANY indentation — _common is the one door",
   not [n for n, t in _src.items() if _re.search(r"\bimport\s+httpx\b", t)],
   [n for n, t in _src.items() if _re.search(r"\bimport\s+httpx\b", t)])
ok("and none of them imports a Postgres driver",
   not [n for n, t in _src.items()
        if _re.search(r"\b(import|from)\s+(psycopg2?|asyncpg|pg8000|sqlalchemy)\b", t)])
ok("the clock probe is a HEAD, and it is rate-limited to one every SKEW_REFRESH_SECONDS",
   sync.SKEW_REFRESH_SECONDS >= 60, sync.SKEW_REFRESH_SECONDS)


# ---- clean up -------------------------------------------------------------------------------------
store.set_data_dir(os.environ.get("SEO_AGENT_DATA"))
for d in MADE:
    shutil.rmtree(d, ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
