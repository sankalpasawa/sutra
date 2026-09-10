"""sync.py — how a change travels from one person's Mac to everyone else's.

TWO HALVES, AND THE PROTOCOL IS DELIBERATELY DULL (WORKSPACE-PLAN.md section 3).

PULL. Every domain table has an `after insert or update or delete` trigger that appends one row to
`changes` (id bigserial, kind, key, payload jsonb, actor, at). A client keeps `last_seen_id`, asks
for `id > last_seen_id` in order, applies each row, and advances. That is the whole of it. There is
no diff, no vector clock, no reconciliation pass, and deletions are ordinary rows — "40 pages are
gone" is 40 log rows and needs no special path.

PUSH. A local change is a write to its own table. THE CLIENT NEVER WRITES THE LOG. That is the
point of the trigger: a client that wrote both the row and the log entry and died between them
would leave a change nobody else ever hears about, and the log and the tables would disagree for
ever. A trigger cannot be forgotten, cannot be skipped by an old build, and cannot be got around by
editing the app. `outbox._send` asserts it.

THE CURSOR RULE, WHICH IS THE ONE THING THAT MUST NOT BE GOT WRONG.
`last_seen_id` advances only after the rows it covers are ON DISK, and it is persisted atomically
the moment they are. A crash mid-pull therefore REPLAYS, never skips. Replaying is safe because
every handler in mirror.py is an upsert by key or a delete of a key; losing a change silently is
the worst thing this system could do, and nothing here trades safety for a duplicate write.

WHY POLLING AND NOT WEBSOCKETS. It adds no dependency and it cannot half-connect. A websocket that
believes it is connected while receiving nothing is the failure mode that loses changes without
anybody noticing; a poll that fails just fails, and the next one succeeds.

Reads:  the `changes` table, through client.select.
Writes: connections.json's `last_seen_id` (the cursor, via client.save_settings),
        workspace/sync-state.json (what is stuck, and why), and the knowledge base via mirror.
"""
import datetime
import email.utils
import os
import threading
import time

from .. import store
from . import _common
from . import mirror
from . import outbox

# HOW OFTEN A CONFIGURED WORKSPACE ASKS FOR NEW ROWS.
# The spec promises a teammate sees a change in about a second. The person who MADE the change is
# not waiting on this timer at all — `push` drains the outbox immediately — so this interval is
# only the delay on the receiving end, and two seconds against a log query that returns nothing
# 99% of the time is cheap. Section 9's 5 GB monthly egress is the budget this has to respect, and
# an empty `id > n` answer is a few hundred bytes.
POLL_SECONDS = 2.0

# HOW LONG TO WAIT AFTER A FAILED POLL. Supabase being unreachable should not become a hot loop;
# a free project asleep after 7 days idle takes about a minute to wake (section 9), so the retry
# has to still be trying then.
POLL_BACKOFF_SECONDS = 15.0

# HOW FAR BEHIND THE HEAD OF THE LOG THE PULL DELIBERATELY STAYS.
#
# THE RACE THIS EXISTS FOR (found 2026-09-10, before the first real workspace). `changes.id` is a
# `bigserial`, and a serial is allocated at INSERT, not at COMMIT. So two teammates writing at once
# can interleave like this:
#
#     Ravi's write inserts, takes id 7, its transaction is still open
#     Devansh's write inserts, takes id 8, and commits first
#     a poller reads the log, sees 8, never saw 7, and sets last_seen_id = 8
#     Ravi's write commits. Row 7 is now visible, and that client will NEVER read it.
#
# A change lost that way is the worst failure this system has — worse than a crash, because nothing
# reports it and the two people quietly disagree for ever afterwards.
#
# THE GUARD IS THIS NUMBER. The pull reads only rows OLDER than this window, so a row is never
# consumed until long after any transaction that could still be holding an earlier id has finished.
# `schema.sql` is the other half: `changes.at` defaults to clock_timestamp() (the wall clock at the
# insert), never now() (the transaction's START time, which for a slow transaction would stamp a
# time EARLIER than rows that committed before it, and would defeat this exactly backwards), and
# there is an (at, id) index to serve the filtered read.
#
# IT COSTS A TEAMMATE AT MOST THREE SECONDS, which is invisible against the "about a second" the
# plan promises, and it buys a thousand-fold margin over writes that commit in milliseconds. If you
# are reading this because you saw a three-second lag and wanted to delete it: the test
# `a change committing out of order is not lost` in tests/test_workspace_sync.py fails without it,
# and what it fails by is a change silently gone for ever.
#
# TWO RESIDUALS, stated because somebody will rely on this.
#   1. A transaction held OPEN for longer than this window can still be skipped. That is acceptable
#      for what Sutra writes — single-row REST calls that commit in milliseconds — and it is NOT
#      acceptable for anything batched. If any write path ever becomes a long multi-row
#      transaction, this guard must be revisited before that path ships.
#   2. A transaction the DATABASE holds open is the only thing left. Everything about the reader's
#      own clock is handled below, and that half is not optional either — read on.
CHANGES_LAG_SECONDS = 3.0

# ---- THE SECOND HALF OF THE SAME GUARD: THE READER'S CLOCK (2026-09-10) --------------------------
#
# The lag above is only a guard if it is measured against the SERVER's clock. PostgREST cannot
# evaluate `now() - interval '3 seconds'` inside a filter — the value has to be a literal in the
# query string — so the cutoff is computed here, on this Mac, and that hands the whole guard to a
# clock nobody has checked.
#
# WHICH DIRECTION HURTS. A Mac running SLOW computes a cutoff further back than the server's own,
# so it holds rows longer than it needs to: extra latency, nothing worse. A Mac running FAST is the
# dangerous one. It computes a cutoff AHEAD of the server's clock and reads rows that are still in
# flight, which brings the bigserial race straight back — silently, on one person's machine, with
# nobody else able to reproduce it. Three seconds of margin against unbounded clock drift is not a
# guard, it is a hope. Macs drift, and a laptop waking from sleep can be seconds out before NTP
# catches up.
#
# THE FIX. Every HTTPS response Supabase sends carries a `Date` header, which is the server's own
# wall clock. So we measure `skew = server_time - local_time` and compute the cutoff as
# `local_now + skew - CHANGES_LAG_SECONDS`. The three seconds then buys margin against commit
# timing alone, which is what it was budgeted for, instead of sharing it with arbitrary drift.
#
# IF YOU ARE DELETING THIS because a skew correction looked like superstition: the three tests
# under "the reader's clock cannot defeat the guard" in tests/test_workspace_sync.py fail without
# it, and one of them fails by reading a row that has not committed.
#
# THE ASYMMETRY IS DELIBERATE, and it is the part that is easy to get subtly wrong. A NEGATIVE skew
# (the server behind us) pushes the cutoff back and is always safe, so it is always believed. A
# POSITIVE skew pushes the cutoff forward and is the direction that can defeat the guard, so it is
# believed only up to SKEW_TRUST_SECONDS; a Date claiming to be a year ahead is a broken clock or a
# broken proxy, not a fact, and we fall back to the conservative path rather than obey it.
#
# UNTIL A `Date` HAS EVER BEEN SEEN we do not guess: we lag MORE. Erring toward latency is free;
# erring the other way loses changes.

# How long a measured skew is believed before it is measured again. Drift is slow — seconds a day —
# so this is really about the step change when a laptop wakes from sleep.
SKEW_REFRESH_SECONDS = 300.0

# The EXTRA lag applied while the server's clock is unknown: the first poll of a session, or a
# proxy that strips `Date`. Deliberately large. A minute of extra latency is a thing somebody might
# notice; a lost change is a thing nobody notices, which is worse.
UNKNOWN_SKEW_LAG_SECONDS = 60.0

# How far AHEAD of us a server may claim to be and still be believed. Beyond a day, something is
# broken rather than skewed, and believing it would move the cutoff into the future and switch the
# guard off entirely. There is no matching bound below zero: being told to wait longer is safe.
SKEW_TRUST_SECONDS = 86400.0

# The clock probe is one HEAD request every SKEW_REFRESH_SECONDS, so it must never be the thing
# that holds up a poll.
SKEW_PROBE_TIMEOUT = 10.0

# HOW MANY LOG ROWS ONE REQUEST ASKS FOR. The log is paged, never assumed to fit: a teammate who
# was on a plane for a week comes back to thousands of rows, and one request that tried to carry
# them all would time out and then time out again on every retry.
CHANGES_PAGE = 500

# HOW MANY ROWS OF THE SAME KIND ARE APPLIED IN ONE FILE WRITE. The cursor advances per batch, so a
# crash replays a batch rather than skipping it — and a refresh that dropped 40 pages rewrites
# content-database.jsonl once instead of forty times.
APPLY_BATCH = 200

# HOW MANY TIMES ONE ROW MAY BLOCK THE LOG BEFORE IT IS SET ASIDE. A row that fails to apply stops
# the drain, because the rows behind it may depend on it. But a row that can never apply would then
# freeze every future change for that person for ever, which is a worse failure than the one row.
# After this many consecutive attempts it is written to workspace/refused.jsonl — loudly, with its
# error — and the cursor moves past it. Set aside where somebody can see it, never silently dropped.
POISON_TRIES = 5

# ---- KINDS WHOSE TABLE A MIGRATION ADDED -----------------------------------------------------
#
# `brand_inputs` arrived at schema version 3 (schema.py ADDED_IN). A workspace created before it
# has no such table, and PostgREST answers a write to it with a 404 that will never become
# anything else until somebody runs the migration.
#
# WHY THAT MUST NOT BE QUEUED. The outbox is a QUEUE and a failing item deliberately blocks the
# ones behind it, retrying for ever with no maximum attempt count (outbox.py, decisions 2 and 3).
# Both of those are right for a network that is merely down. Against a table that does not exist,
# they would park one undeliverable row at the head of the queue and hold every idea, article and
# prompt edit behind it for as long as the workspace stayed un-migrated -- which is the owner's
# live workspace, today, at version 2.
#
# So push ASKS FIRST, and declines rather than queueing. Nothing is lost by declining: the file is
# already saved locally, and the brand pack still carries it to the team on the next rebuild, which
# is exactly what happened before this table existed. It is slow, it is the old behaviour, and it
# is recorded in sync-state.json so `status()` can say so instead of leaving it to be guessed at.
KIND_NEEDS_VERSION = {"brand_inputs": 3}

# HOW LONG A SCHEMA-VERSION ANSWER IS TRUSTED. One row of one table, asked at most this often, and
# only ever before a push of a version-gated kind -- which is a person saving a form by hand, not
# anything on the poll loop. Short enough that a migration run in the Connections tab takes effect
# a minute later without a restart.
SCHEMA_CHECK_SECONDS = 60.0


class SyncError(Exception):
    """The pull could not run at all: no workspace, or the log could not be read."""


# ---- the cursor ------------------------------------------------------------------------------------

def state_path():
    """The DIAGNOSTICS file. Not the cursor — see `last_seen_id` for where that lives."""
    return os.path.join(mirror.dir_(), "sync-state.json")


def read_state():
    return store.read_json(state_path(), {}) or {}


def _save_state(st):
    st["updated_at"] = store.now()
    store.write_json(state_path(), st)      # temp file in the same dir, then rename
    return st


def last_seen_id(client=None):
    """Where this Mac has got to in the log.

    ONE COPY, and it is the client's: `connections.json`, written by `client.save_settings`. It has
    to be that one, because `link.py` writes it when a person joins — the log position the pack was
    built at — so a joiner starts from the pack rather than replaying the whole log on top of it. A
    second copy of this number in a file of my own would be a second thing to be wrong.

    `sync-state.json` beside it holds the diagnostics only (what is stuck, and why), never the
    cursor.
    """
    try:
        return int((_client(client).settings() or {}).get("last_seen_id") or 0)
    except Exception:                       # noqa: BLE001 — no workspace yet is not an error here
        return 0


def _advance(client, to_id, extra=None):
    """Move the cursor, on disk, now. Called only after the rows it covers have landed.

    `save_settings` merges into connections.json through `store.save_connections`, which is a
    temp-file-then-rename write at 0600. A crash mid-write therefore leaves the OLD cursor, and the
    rows replay. It can never leave a cursor half way through a number.
    """
    _client(client).save_settings(last_seen_id=int(to_id))
    st = read_state()
    st.pop("stuck", None)
    if extra:
        st.update(extra)
    _save_state(st)
    return to_id


# ---- the client ------------------------------------------------------------------------------------

def _client(client=None):
    """The injected client, or the real one. Imported lazily so this module loads with no workspace
    configured and so the tests can run entirely offline against a stub."""
    if client is not None:
        return client
    from . import client as real
    return real


def configured(client=None):
    try:
        return bool(_client(client).configured())
    except Exception:                       # noqa: BLE001 — not built, not configured, same answer
        return False


def _actor(client=None):
    """The name stamped on this person's writes. `client.actor()` owns the fallback chain."""
    try:
        return _client(client).actor() or ""
    except Exception:                       # noqa: BLE001
        return ""


def _now_epoch():
    """The clock the lag window is measured against.

    ONE function, so a test can hold it still, and so a server-side `now()` has exactly one place
    to land if residual 2 above ever has to be closed.
    """
    return time.time()


# What we currently believe about the server's clock. `seconds` is None until a Date has been read.
_SKEW = {"seconds": None, "at": 0.0, "source": "never measured"}


def forget_skew():
    """Throw the estimate away: leaving a workspace, or a test that wants a clean slate."""
    _SKEW.update({"seconds": None, "at": 0.0, "source": "never measured"})


def _probe(url, headers, timeout):
    """Ask the server for its headers, through the ONE DOOR. A seam, so no test opens a socket.

    NOT `httpx` directly, deliberately. `_common.request` is the only place in this package that
    touches the wire, and test_workspace_core asserts it; going round it would also mean going round
    its retries, its timeouts and its errors-turned-into-English, and rebuilding all three here for
    a HEAD request would be three more things to keep in step.

    A HEAD on a real table rather than on the REST root: the root refuses a publishable key
    outright ("Secret API key required"), and `request` raises on a 4xx, so the response — and the
    `Date` in it — would be gone. `select=id&limit=1` on the log is a 200 with no body worth
    mentioning. We are reading the clock, not the rows.
    """
    return _common.request("HEAD", url, "check the server's clock", headers=headers,
                           params={"select": "id", "limit": 1}, timeout=timeout)


def _server_epoch(client):
    """The server's own wall clock, or None when we could not get one.

    Never raises. A clock we could not read is a clock we do not know, and `_skew` handles not
    knowing by lagging more — a probe that failed must not be able to stop a poll.
    """
    try:
        c = _client(client)
        base = ((c.settings() or {}).get("workspace_url") or "").strip().rstrip("/")
        if not base.startswith("http"):
            return None
        resp = _probe(base + "/rest/v1/changes", c.headers(), SKEW_PROBE_TIMEOUT)
        stamp = (getattr(resp, "headers", None) or {}).get("Date")
        if not stamp:
            return None
        parsed = email.utils.parsedate_tz(str(stamp))
        return email.utils.mktime_tz(parsed) if parsed else None
    except Exception:                       # noqa: BLE001 — offline, no workspace, a odd proxy
        return None


def _skew(client=None, now=None):
    """server clock - this Mac's clock, in seconds, or None when we do not know.

    Re-measured at most every SKEW_REFRESH_SECONDS. A failed probe also resets the timer, so a
    server that never sends a Date costs one HEAD every five minutes rather than one per poll; the
    price of that is five minutes in the conservative path, which is the safe direction.
    """
    now = _now_epoch() if now is None else now
    if _SKEW["at"] and (now - _SKEW["at"]) < SKEW_REFRESH_SECONDS:
        return _SKEW["seconds"]
    _SKEW["at"] = now
    server = _server_epoch(client)
    if server is None:
        _SKEW["seconds"], _SKEW["source"] = None, "no Date header"
        return None
    # The Date header has ONE-SECOND resolution and is truncated, so the server time we read is
    # never later than the truth. That makes the skew we measure never larger than the truth, which
    # makes the cutoff never later than the truth: the error is under a second and it falls on the
    # safe side. Nothing to correct for.
    gap = float(server) - float(now)
    if gap > SKEW_TRUST_SECONDS:
        # Forward is the direction that switches the guard off. A Date this far ahead is broken,
        # not skewed, and obeying it would be worse than admitting we do not know.
        _SKEW["seconds"], _SKEW["source"] = None, "Date %.0fs ahead — not believable" % gap
        return None
    _SKEW["seconds"], _SKEW["source"] = gap, "Date header"
    return gap


def _lag_cutoff(client=None):
    """The epoch after which a row is too new to consume, on the SERVER's clock.

    Measured against the server wherever we know it, and against a deliberately pessimistic version
    of our own where we do not. See the block above CHANGES_LAG_SECONDS for why.
    """
    now = _now_epoch()
    skew = _skew(client, now)
    basis = (now + skew) if skew is not None else (now - UNKNOWN_SKEW_LAG_SECONDS)
    return basis - CHANGES_LAG_SECONDS


def _iso(epoch):
    """The form the filter goes on the wire in. UTC with a `Z`, deliberately: a `+05:30` offset
    would have to be percent-encoded into the query string, and a filter that is right in the code
    and wrong on the wire is the worst kind."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch_of(stamp):
    """A timestamptz as PostgREST hands it back — "2026-09-10T01:50:00.123456+00:00" — as an epoch.

    Parsed, never string-compared. The wire form carries fractional seconds and a numeric offset
    while `_iso` writes a bare `Z`, and "…:00.123456+00:00" sorts BELOW "…:00Z" as text because '.'
    is below 'Z'. A row a fraction too new would compare as old enough, which is a guard failing by
    the width of one second in the one direction that loses changes.
    """
    text = str(stamp or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:               # Postgres always sends one; belt and braces
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.timestamp()


def _changes_after(client, last, limit):
    """One page of the log: past my cursor, and old enough to be safe.

    NOT `client.since()`, which asks only for `id > last` and has no lag clause. This is the query
    `schema.sql` documents beside the (at, id) index, and CHANGES_LAG_SECONDS above says why the
    `at` half of it is not optional.

    The re-sort is not paranoia about PostgREST — the request asks for `order=id.asc`. It is that
    the whole protocol is "apply in id order", and a sync that leans on an unstated ordering
    guarantee is a sync that silently reorders on the day the guarantee changes. It costs nothing
    on 500 rows.
    """
    cutoff = _lag_cutoff(client)
    # THE SERVER PRUNES AT A WIDER CUTOFF THAN WE APPLY, and the difference is not slack for its own
    # sake. `id` and `at` are both column defaults, evaluated microseconds apart inside one INSERT,
    # so two racing writers can produce (id 7, at T+50us) and (id 8, at T+10us): `at` is very
    # nearly, but not exactly, monotonic in `id`. If the cutoff fell between those two, a filter we
    # simply trusted would hand back 8 and hide 7, we would advance past 7, and 7 would be
    # unreachable for ever — the same loss this whole guard exists to prevent, arriving by a
    # different door. So the server filters at cutoff + the lag window, which is cheap and uses the
    # (at, id) index, and we then stop at the first row that is genuinely too new. Seeing the
    # boundary rows is what makes stopping in the right place possible.
    rows = client.select("changes",
                         where={"id": ("gt", int(last)),
                                "at": ("lt", _iso(cutoff + CHANGES_LAG_SECONDS))},
                         order="id.asc", limit=int(limit)) or []
    rows = sorted(rows, key=lambda r: int(r.get("id") or 0))
    out = []
    for row in rows:
        at = _epoch_of(row.get("at"))
        if at is None or at >= cutoff:
            break                           # too new. Everything behind it waits too: order is the protocol.
        out.append(row)
    return out


# ---- pull -------------------------------------------------------------------------------------------

def _runs(rows):
    """Split a page of the log into contiguous runs of one kind, each at most APPLY_BATCH long.

    Contiguous, never regrouped: the log's order is the order things happened in, and applying a
    later idea before an earlier delete of the same key would land the wrong state.
    """
    out, cur = [], []
    for r in rows:
        if cur and (r.get("kind") != cur[0].get("kind") or len(cur) >= APPLY_BATCH):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def _apply_run(batch):
    """Apply one run. Returns (applied, refused). Raises for a transient failure.

    A MirrorRefused on a run of several is retried ONE ROW AT A TIME, so only the row that is
    actually unappliable gets set aside; the others in the run still land. Refusing the whole run
    on one bad prompt would throw away good changes to make the bookkeeping simpler.
    """
    try:
        mirror.apply_batch(batch)
        return len(batch), 0
    except mirror.MirrorRefused as e:
        if len(batch) == 1:
            mirror.refuse(batch[0], e)
            return 0, 1
    applied = refused = 0
    for row in batch:
        try:
            mirror.apply_batch([row])
            applied += 1
        except mirror.MirrorRefused as e:
            mirror.refuse(row, e)
            refused += 1
    return applied, refused


def pull_once(client=None):
    """Drain the log as far as it goes. Returns what happened; never raises for a network failure.

    {"applied", "refused", "pages", "last_seen_id", "blocked", "why"}
    """
    c = _client(client)
    if not configured(c):
        return {"applied": 0, "refused": 0, "pages": 0, "last_seen_id": 0,
                "blocked": True, "why": "no workspace"}
    last = last_seen_id(c)
    applied = refused = pages = 0
    while True:
        try:
            rows = _changes_after(c, last, CHANGES_PAGE)
        except Exception as e:              # noqa: BLE001 — offline is the normal case, not a crash
            return {"applied": applied, "refused": refused, "pages": pages,
                    "last_seen_id": last, "blocked": True, "why": str(e)[:300]}
        pages += 1
        if not rows:
            return {"applied": applied, "refused": refused, "pages": pages,
                    "last_seen_id": last, "blocked": False, "why": ""}
        for batch in _runs(rows):
            try:
                a, r = _apply_run(batch)
            except Exception as e:          # noqa: BLE001 — transient: a full disk, a file in flux
                return _stick(c, batch[0], last, e, applied, refused, pages)
            applied += a
            refused += r
            # ON DISK FIRST, THEN THE CURSOR. Every handler has written its file by the time
            # _apply_run returns, so this is the moment the rows are safe to skip on a restart.
            last = int(batch[-1].get("id") or last)
            _advance(c, last)
        if len(rows) < CHANGES_PAGE:
            return {"applied": applied, "refused": refused, "pages": pages,
                    "last_seen_id": last, "blocked": False, "why": ""}


def _stick(client, row, last, err, applied, refused, pages):
    """A row failed to apply for a reason that might pass next time. Count it, and stop.

    Stopping is the point: the rows behind it may depend on it, so the drain waits rather than
    reordering. POISON_TRIES consecutive failures on the SAME row is the signal that it will never
    pass, and it is then set aside to refused.jsonl so it stops holding up everyone's changes.
    """
    st = read_state()
    stuck = st.get("stuck") or {}
    rid = int(row.get("id") or 0)
    tries = int(stuck.get("tries") or 0) + 1 if int(stuck.get("id") or 0) == rid else 1
    if tries >= POISON_TRIES:
        mirror.refuse(row, "gave up after %d tries: %s" % (tries, err))
        _advance(client, rid, {"last_refused_id": rid})
        return {"applied": applied, "refused": refused + 1, "pages": pages,
                "last_seen_id": rid, "blocked": False, "why": "set aside change %d: %s" % (rid, err)}
    st["stuck"] = {"id": rid, "tries": tries, "why": str(err)[:300], "kind": row.get("kind")}
    _save_state(st)
    return {"applied": applied, "refused": refused, "pages": pages, "last_seen_id": last,
            "blocked": True, "why": str(err)[:300]}


# ---- push --------------------------------------------------------------------------------------------

def _schema_version(client=None, now=None):
    """What version this workspace's schema is on. 0 when it cannot be told.

    Cached in sync-state.json for SCHEMA_CHECK_SECONDS, and read THROUGH THE INJECTED CLIENT rather
    than through schema.ready(): `ready()` talks to the real client module, and a push handed a
    client must not go somewhere else behind its back.

    A failed read returns the last answer we had, or 0. 0 means "not known", and the caller's rule
    for a version-gated kind is to decline -- the safe direction, because the alternative is
    wedging the queue behind a row that can never be delivered.
    """
    now = _now_epoch() if now is None else now
    st = read_state()
    cached = st.get("schema") or {}
    try:
        if cached.get("at") and 0 <= now - float(cached["at"]) < SCHEMA_CHECK_SECONDS:
            return int(cached.get("version") or 0)
    except (TypeError, ValueError):
        pass
    try:
        row = _client(client).one("workspace", columns="id,schema_version") or {}
        version = int(row.get("schema_version") or 0)
    except Exception:                       # noqa: BLE001 — offline, or not created yet
        return int(cached.get("version") or 0)
    st = read_state()
    st["schema"] = {"version": version, "at": now}
    _save_state(st)
    return version


def _may_push(kind, client=None):
    """(True, "") when this workspace can take a row of this kind; (False, why) when it is behind.

    Only the kinds in KIND_NEEDS_VERSION are ever asked about, so an ordinary push costs nothing.
    """
    need = KIND_NEEDS_VERSION.get(kind)
    if not need:
        return True, ""
    have = _schema_version(client)
    if have >= need:
        st = read_state()
        if st.pop("needs_update", None) is not None:
            _save_state(st)
        return True, ""
    why = ("This team workspace is on version %d and %s needs version %d. It travels with the "
           "knowledge pack until somebody runs the update from the Connections tab."
           % (have, kind, need))
    st = read_state()
    st["needs_update"] = {"kind": kind, "have": have, "needs": need, "why": why,
                          "at": store.now()}
    _save_state(st)
    return False, why


def push(kind, key, payload=None, op="upsert", actor=None, client=None, item_id=None):
    """A local change goes up. Queued first, sent immediately when there is a network.

    Queued FIRST, always, even when the network is fine: the queue is what makes the promise in
    section 6 true, and a code path that sometimes skips it is a code path that loses work on the
    one afternoon the wifi drops mid-write.

    This does NOT write the local knowledge base. Whatever made the change already did that — that
    is why Sutra is fast — and the row comes back down the log a moment later and lands through
    mirror, which is an upsert of the same values and therefore a no-op. One direction of travel,
    no special case for "my own change".

    Returns the queued item, or None when this workspace is too old to hold this kind
    (KIND_NEEDS_VERSION). None is not an error and it is not a lost change: the local write stands,
    the reason is in sync-state.json and in status(), and the knowledge pack still carries the file
    to the team the way it did before that table existed.
    """
    if kind not in mirror.TABLES:
        raise ValueError("unknown kind %r (known: %s)" % (kind, ", ".join(mirror.KINDS)))
    allowed, _why = _may_push(kind, client)
    if not allowed:
        # NOT queued, and that is the whole point. See KIND_NEEDS_VERSION: a row this workspace has
        # no table for would sit at the head of the queue for ever and hold everything else behind
        # it. Returning None says "it did not go", the state file says why, and status() shows it.
        return None
    table, pk = mirror.TABLES[kind]
    who = actor if actor is not None else _actor(client)
    # The knowledge base's shape is not the database's shape; `mirror.to_wire` is the one
    # translation and it lives beside `from_wire` so the two cannot drift apart.
    row = mirror.to_wire(kind, str(key), payload, actor=who, gone=(op == "gone"))
    if kind in mirror.PK_DEFAULTED:
        # The database fills this one. Blank the pk on the queued item too, or `outbox._send` would
        # stamp the queue's key into it — and `company.workspace_id` is a uuid, so "1" is not a
        # value it can hold. Caught reading schema.sql, 2026-09-10.
        row.pop(pk, None)
        pk = ""
    # Every write carries its author (section 5, "everyone can do everything"). The trigger prefers
    # the x-sutra-actor header the client sends, and falls back to this column, so a write made from
    # somewhere else still says who.
    if who:
        row.setdefault("actor", who)
    item = outbox.enqueue(kind, table, pk, key, row=row,
                          op="upsert" if op in ("upsert", "gone") else op,
                          actor=who, item_id=item_id)
    try:
        outbox.drain(_client(client))
    except Exception:                       # noqa: BLE001 — it is on disk; the poller will retry
        pass
    return item


def catch_up(client=None, replay_from=None):
    """Land a joiner level with everybody BEFORE the join screen says they are done.

    THE HOLE THIS FILLS (2026-09-10). `pack.join` installs the files and hands back `replay_from`,
    the boundary the pack was built at. Saving that as `last_seen_id` is correct, but it leaves the
    new teammate holding a knowledge base that is slightly stale — everything that happened while
    the pack was being downloaded — with nothing on screen saying so, until the poller's next tick
    quietly fixes it. Seconds, but seconds in which the app is showing them something it knows is
    out of date.

    WHY ONE PULL HERE IS SAFE, checked against pack.py rather than assumed:
      * `join()`'s own docstring: "The joiner then drains `changes` for `id > replay_from` and is
        level with everyone else." Draining is exactly what this does, on the boundary they wrote.
      * Replaying too much is harmless in this direction and pack.py says so for the same reason
        mirror.py does: every apply is an upsert keyed by the row's own key. So the `full_replay`
        case (an older workspace with no `pack_change_id`, boundary 0) is slow, never wrong.
      * `replay_from` is only ever moved FORWARD here. Winding a cursor back would be safe but
        would replay the whole log for nothing, and on an already-joined workspace it would be a
        caller's mistake this function should not act on.

    Never raises. A join that fetched 33 MB successfully must not be reported as failed because the
    catch-up poll afterwards hit a flat network — the files are on disk and the poller will finish
    the job. The return says what happened so the screen can be honest either way.
    """
    c = _client(client)
    if replay_from is not None:
        try:
            have = last_seen_id(c)
            want = int(replay_from or 0)
            if want > have:
                c.save_settings(last_seen_id=want)
        except Exception as e:              # noqa: BLE001
            return {"applied": 0, "blocked": True, "why": str(e)[:300]}
    try:
        return pull_once(c)
    except Exception as e:                  # noqa: BLE001 — pull_once already swallows the network
        return {"applied": 0, "blocked": True, "why": str(e)[:300]}


def push_delete(kind, key, actor=None, client=None, item_id=None):
    """The thing is gone. The trigger logs it, and it reaches everyone as an ordinary change.

    `pages` is the one that is not a DELETE, and it matters. That table is a delta which is TRIMMED
    when the pack is rebuilt (section 3), and a trim is a delete of its rows. If a page going away
    were also a delete, no client could tell the two apart, and every pack rebuild would wipe real
    pages out of everybody's catalogue. So a gone page is an UPDATE to `op = 'gone'` — the column
    the pages table carries for exactly this — and `mirror.is_gone` reads it there.
    """
    if kind == "pages":
        return push(kind, key, None, op="gone", actor=actor, client=client, item_id=item_id)
    return push(kind, key, None, op="delete", actor=actor, client=client, item_id=item_id)


# ---- the poll loop -------------------------------------------------------------------------------------

class Poller(threading.Thread):
    """Drain the outbox, then the log, every POLL_SECONDS while a workspace is configured.

    Outbox first, deliberately: my own changes should be up before I ask what everyone else did, so
    a person who edits and immediately looks at the activity line sees their own change in it.

    A daemon thread with an Event rather than a sleep, so quitting Sutra does not wait out a poll.
    """

    def __init__(self, client=None, interval=POLL_SECONDS):
        threading.Thread.__init__(self, name="workspace-sync", daemon=True)
        self._client = client
        self._interval = float(interval)
        # NOT `self._stop`. threading.Thread already has a private `_stop()` method and `join()`
        # calls it; shadowing it with an Event makes every join die with "'Event' object is not
        # callable" — which is exactly how quitting Sutra would have hung on this thread. Caught by
        # the poller test, 2026-09-10.
        self._quit = threading.Event()
        self.last = {}

    def run(self):
        while not self._quit.is_set():
            wait = self._interval
            try:
                c = _client(self._client)
                if configured(c):
                    outbox.drain(c)
                    self.last = pull_once(c)
                    if self.last.get("blocked"):
                        wait = POLL_BACKOFF_SECONDS
                else:
                    wait = POLL_BACKOFF_SECONDS
            except Exception as e:          # noqa: BLE001 — a poll thread never dies of one bad poll
                self.last = {"blocked": True, "why": str(e)[:300]}
                wait = POLL_BACKOFF_SECONDS
            self._quit.wait(wait)

    def stop(self, timeout=5):
        self._quit.set()
        if self.is_alive():
            self.join(timeout)


_POLLER = [None]
_POLLER_LOCK = threading.Lock()


def start(client=None, interval=POLL_SECONDS):
    """Start the one poller for this process, and return it. Safe to call from anywhere, always.

    IDEMPOTENT AND THREAD-SAFE, and both halves matter. Idempotent because more than one thing
    wants to be sure sync is running and none of them should have to know whether another already
    did it; thread-safe because two requests arriving together would otherwise both see "not
    running" and start two pollers, which would double every poll and race each other's cursor
    writes. The lock costs nothing — this is called on a screen render, not in a loop.

    It does NOT check `configured()` first, deliberately. A poller with no workspace sits in the
    backoff (one wakeup every POLL_BACKOFF_SECONDS, doing nothing) and picks the workspace up by
    itself the moment one is connected. Refusing to start without one would mean somebody has to
    remember to start it again after Create or Join, and that is exactly the kind of thing nobody
    remembers.

    WHERE THIS BELONGS, since somebody has to decide: the agent's backend coming up, not a screen
    being looked at. See HANDOFF-W2.md section 5 — a teammate whose changes only flow while they
    happen to have the Connections tab open is the promise in section 1 quietly broken.
    """
    with _POLLER_LOCK:
        if _POLLER[0] is not None and _POLLER[0].is_alive():
            return _POLLER[0]
        p = Poller(client, interval)
        _POLLER[0] = p
        p.start()
        return p


def stop():
    with _POLLER_LOCK:
        p = _POLLER[0]
        _POLLER[0] = None
    if p is not None:
        p.stop()
    return p


# ---- the pack's state, so the screen reads ONE dict ---------------------------------------------
#
# The pack is `pack.Rebuilder`'s business and none of mine. This is a window onto it, not a second
# copy of it: `running` and `pending` are read off the Rebuilder itself, which is the only thing
# that knows whether a rebuild is in flight or armed. The stage — building versus uploading — has
# no getter, so it is recorded from the progress callback the Rebuilder already calls, and the
# Rebuilder's own state wins wherever the two could disagree.
#
# Written 2026-09-10 to replace the panel deriving this from a progress callback of its own. A
# screen inferring engine state from a side channel drifts the first time the engine changes, and
# the drift shows up as a status line that is confidently wrong.

# pack.py's real stage names (its `say(...)` calls), mapped to what a person is told. Grounded in
# that file, not invented here: build/pack/verify/start are the rebuild, upload/publish are the
# send, download/install are the JOIN side, and done/error end a run.
PACK_STAGES = {"start": "building", "build": "building", "pack": "building", "verify": "building",
               "upload": "uploading", "publish": "uploading",
               "download": "joining", "install": "joining",
               "done": "idle", "error": "idle"}

_PACK = {"rebuilder": None, "stage": "", "note": "", "at": None}


def attach_pack(rebuilder):
    """Hand the one `pack.Rebuilder` over, so `status()` can report the engine's own state."""
    _PACK["rebuilder"] = rebuilder
    return rebuilder


def pack_progress(stage, done=0, total=0, note=""):
    """Pass this as the Rebuilder's `progress` (chain it if you want a second listener).

    Its signature is pack.py's, unchanged, so it drops straight in where the panel's own callback
    was.
    """
    stage = str(stage or "")
    if stage in PACK_STAGES:
        _PACK["stage"] = stage
    _PACK["note"] = str(note or "")
    _PACK["at"] = store.now()
    return stage


def pack_state():
    """{state, note, builds, last_error, at} — what the Connections tab shows about the pack.

    `state` is one of: idle · building · uploading · joining · waiting.
    "waiting" is a rebuild that has been asked for and is armed behind the coalesce window — the
    one in section 2 that stops a long catch-up session uploading the same pack six times.
    """
    r = _PACK["rebuilder"]
    stage = PACK_STAGES.get(_PACK["stage"], "idle")
    out = {"state": stage, "note": _PACK["note"], "at": _PACK["at"],
           "builds": 0, "last_error": None}
    if r is None:
        return out
    try:
        out["builds"] = int(getattr(r, "builds", 0) or 0)
        out["last_error"] = getattr(r, "last_error", None)
        if getattr(r, "running", False):
            # It is definitely working; the stage says which half. A stale "idle" from the last
            # run's `done` must not win over the Rebuilder saying it is running right now.
            out["state"] = stage if stage in ("building", "uploading") else "building"
        elif getattr(r, "pending", False):
            out["state"] = "waiting"
        elif stage in ("building", "uploading"):
            out["state"] = "idle"          # the run ended; a stage left over from it is not news
    except Exception:                      # noqa: BLE001 — a window on the pack never breaks status
        pass
    return out


def status(client=None):
    """One dict for the Connections tab: where the cursor is, what is queued, what is stuck."""
    st = read_state()
    p = _POLLER[0]
    return {"configured": configured(client),
            "last_seen_id": last_seen_id(client),
            "updated_at": st.get("updated_at"),
            "stuck": st.get("stuck"),
            # Set when a push was declined because this workspace is a version behind. It carries
            # the sentence to show; it is cleared by the first push that gets through.
            "needs_update": st.get("needs_update"),
            "clock_skew": {"seconds": _SKEW["seconds"], "source": _SKEW["source"]},
            "polling": bool(p is not None and p.is_alive()),
            "last_poll": (p.last if p is not None else {}),
            "outbox": outbox.status(),
            "pack": pack_state()}
