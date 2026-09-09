# HANDOFF-W2 — the sync engine

**written**: 2026-09-10 · **from**: the agent that built `sync.py`, `outbox.py`, `mirror.py`
**to**: whoever owns `client.py`, `schema.sql`, `link.py`, `pack.py`, and the Connections tab

The sync half is built and green: `seo_agent/tests/test_workspace_sync.py`, 77 checks, offline
against a fake Supabase whose primary keys and `op` column are lifted from the real `schema.sql`.
`bash seo_agent/tests/run_all.sh` is green with it in the list.

Everything below is written against the files as they actually are, not against the brief I
started from. Where the brief and the code disagreed, the code won and I changed my side.

---

## 1. What I built

| File | What it is |
|---|---|
| `seo_agent/workspace/sync.py` | pull (drain the `changes` log), push (write the row; the trigger logs it), the poll timer |
| `seo_agent/workspace/outbox.py` | the on-disk queue: offline is not a lost change |
| `seo_agent/workspace/mirror.py` | landing an arriving change in the local knowledge base, and the wire↔local translation |

The calls the Connections tab and the tools want:

    sync.push(kind, key, local_payload)     queue a change; sent at once when there is a network
    sync.push_delete(kind, key)             the same, as a removal
    sync.pull_once()                        one drain of the log. Never raises for a network failure.
    sync.start() / sync.stop()              the poll timer. Idempotent. NOTHING CALLS THESE YET.
    sync.status()                           cursor, queue depth, what is stuck — one dict for the tab
    mirror.recent(limit)                    the last applied changes WITH their actor, for "Ravi, 21:40"
    mirror.recent(limit, mirror.REFUSED_LOG)  what could never land, and why
    outbox.status()                         queued count, oldest, attempts, last error

`kind` is the table name: `ideas · prompts · competitors · cta_links · company · library · pages`.
`workspace` and `members` are known and applied as **no-ops** (`mirror.IGNORED_KINDS`) — they log
changes but there is nothing local to write, and refusing them would fill `refused.jsonl` with
every teammate's `last_seen_at` heartbeat.

`mirror.TABLES` is the single source of truth for kind → (table, primary key). It is taken from
`schema.sql`; if you rename a column there, change it there and nowhere else.

---

## 2. WHAT I CHANGED AFTER READING YOUR CODE

I was handed an interface that turned out not to be the one you shipped. I have adapted to yours,
not the other way round. For the record, so nobody re-introduces the old assumptions:

| I was told | What `client.py` / `schema.sql` actually do | What I do now |
|---|---|---|
| `client.creds()` | `client.settings()` + `client.actor()` | use those |
| `where={"id": "gt.42"}` | `_filter` takes `("gt", 42)` tuples | I call `client.since(last, limit)` and never build a filter |
| `changes` has no `op` column | it has one: `insert \| update \| delete` | `mirror.is_gone` reads `op`, not the payload |
| a delete logs a NULL payload | a delete logs `to_jsonb(OLD)` | as above — the payload of a delete is an ordinary row |
| the payload is the local row | the payload is the DATABASE row (`ideas.data`, `library.meta`, `company.one_liner`…) | `mirror.from_wire` / `to_wire` translate, in one place |

**The cursor.** It lives in `connections.json` as `last_seen_id`, written through
`client.save_settings(last_seen_id=…)`, and there is exactly one copy of it. I keep no second copy:
`workspace/sync-state.json` beside it holds only the diagnostics (which row is stuck, and why). It
has to be your file, because `link.py` writes it when somebody joins — please write **the log id
the pack was built at**, so a joiner starts from the pack instead of replaying the whole log on top
of it. (Replaying is harmless, every apply is idempotent, but it is pointless and slow.)

---

## 3. THE THREE GUARDS, AND THE ONE THING I STILL WANT

### 3a. `pages` is a delta that gets trimmed, and a trim looks exactly like a deletion

This is the one that would have quietly destroyed data, so it is first.

`pages` carries only what changed since the pack was built, and is **trimmed when the pack is
rebuilt** (WORKSPACE-PLAN section 3). A trim is a `delete` of rows from `pages`, and the trigger
logs it exactly like any other delete. If a client read that as "these pages are gone", **every
pack rebuild would delete real pages out of every teammate's catalogue.**

What I implemented, and what the pack must therefore do:

- **A page going away is `op = 'gone'` on the pages row** — an UPDATE, using the column the table
  already carries for it. `sync.push_delete("pages", url)` does this automatically.
- **A log row with `op='delete'` and `kind='pages'` is ignored by the mirror.** It is the delta
  being tidied and says nothing about whether the page exists.
- So `pack.py`'s trim may `delete` from `pages` freely. **It must never delete a page as a way of
  saying the page is gone.**

There is a test for this (`TRIMMING THE PAGES DELTA DOES NOT DELETE THE PAGE LOCALLY`).

**Reconciled 2026-09-10:** I have read `schema.sql` as it now stands. `pages.op` is
`changed | gone`, which is exactly what `mirror.is_gone` reads, so the two sides agree and there is
nothing outstanding here. If that column is ever renamed or its values changed, `mirror.is_gone` is
the one function that has to change with it.

### 3b. The bigserial race — CLOSED, on both sides. Here is what the two halves are.

`changes.id` is a `bigserial`, allocated at INSERT and not at COMMIT, so a row that took the LOWER
id can become visible AFTER one that took a higher id. A poller that consumed the higher one first
would advance its cursor past a change it had never seen, and that change would be unreachable for
ever. Nothing reports it; the two people quietly disagree from then on.

**`schema.sql` (already landed):** `changes.at` defaults to `clock_timestamp()` — the wall clock at
the insert, never `now()`, which is the transaction's START time and for a slow transaction would
stamp a time EARLIER than rows that committed before it, defeating the guard exactly backwards.
Plus a `(at, id)` index.

**`sync.py` (this change):** the pull reads only rows older than `CHANGES_LAG_SECONDS` (3.0), on the
**server's** clock. Two details of that are not obvious and are both load-bearing:

1. **The clock is corrected for skew** — see 3c, it is the half that took the most care.
2. **The server's filter is not trusted on its own.** `id` and `at` are both column defaults,
   evaluated microseconds apart inside one INSERT, so two racing writers can produce
   `(id 7, at T+50µs)` and `(id 8, at T+10µs)`: **`at` is very nearly, but not exactly, monotonic in
   `id`.** If the cutoff fell between those two, a filter we simply trusted would return 8 and hide
   7 — the same loss, by a different door. So the server filters at **`cutoff + CHANGES_LAG_SECONDS`**
   (cheap, and it uses your `(at, id)` index), the boundary rows come back, and `sync` stops at the
   first row that is genuinely too new. **That is why the filter on the wire is wider than the
   comment in `schema.sql` says; the two are not in disagreement, the wider one is deliberate.**

Tests: `a change committing out of order is not lost` (parts a and b). Mutation-tested — delete the
lag and part (b) fails by losing a change permanently.

### 3c. The reader's clock — and the one thing I want from `client.py`

The cutoff has to be a literal in the query string, because PostgREST cannot evaluate
`now() - interval` in a filter. That handed the guard to this Mac's clock, which nobody has checked.

**A Mac running SLOW only lags more, which is harmless. A Mac running FAST computes a cutoff ahead
of the server's own and reads rows still in flight — the race, reopened, silently, on one person's
machine, with nobody able to reproduce it.** Three seconds of margin against unbounded clock drift
is not a guard.

So `sync` measures `skew = server_time - local_time` from the **`Date` header** every Supabase
response carries, and computes the cutoff as `local_now + skew - CHANGES_LAG_SECONDS`. Three
deliberate asymmetries, all tested:

- **A negative skew (server behind us) is always believed** — it pushes the cutoff back, which is
  always safe. A **positive** skew is believed only up to `SKEW_TRUST_SECONDS` (a day); a Date
  claiming to be a year ahead is a broken clock or proxy, and obeying it would switch the guard off.
- **Until a `Date` has ever been seen, we lag MORE**, by `UNKNOWN_SKEW_LAG_SECONDS` (60), never
  falling back to the naive local clock. Extra latency is free; the other error loses changes.
- The `Date` header has one-second resolution and truncates, so the server time we read is never
  *later* than the truth — the sub-second error falls on the safe side and needs no correction.

`sync.status()["clock_skew"]` reports the measurement and its source, for a support conversation
about a workspace that looks stuck.

**THE ONE THING I WANT FROM YOU.** `client.select` returns `resp.json()`, so the response headers —
and the `Date` in them — are gone by the time I see anything. Today `sync` therefore opens **one
HEAD request of its own every `SKEW_REFRESH_SECONDS` (5 minutes)** to
`<workspace_url>/rest/v1/`, using `client.headers()` and `client.settings()`, purely to read the
clock. It ignores the status code — your own docstring records that the REST root refuses a
publishable key, and the 401 carries a `Date` exactly like a 200 would.

That works, but it is a socket this module opens for itself, which I would rather it did not. The
exact signature that lets me delete it:

```python
def select(table, where=None, order=None, limit=None, columns="*", offset=None,
           url=None, key=None, with_response=False):
    """... with_response=True returns (rows, resp) instead of rows, so a caller can read
    resp.headers."""
```

With that, `sync._server_epoch` reads the `Date` off the log query it was already making, the probe
goes away, and the skew estimate refreshes on every poll instead of every five minutes — strictly
better on all three counts. Nothing breaks if you never add it.

## 4. THINGS `client.py` COULD DO BETTER FOR ME (none are blocking)

1. **`since()` is no longer what I call.** It asks only for `id > last` and has no lag clause, so
   using it would reopen 3b. I call `select("changes", where={"id": ("gt", n), "at": ("lt", …)},
   order="id.asc", limit=500)` and page it myself. If you want `since` to stay the one door to the
   log, give it the lag clause and I will go back to it.
2. **A no-workspace call.** `settings()` and `actor()` never raise, `configured()` answers cleanly,
   and everything I call is inside a `try` anyway. Nothing needed.
3. **`upsert(..., on_conflict=)`** — I never pass it, so PostgREST infers the primary key. That is
   right for all seven tables. If any table ever gets a composite key, I need to start passing it.

---

## 5. WHAT THE PANEL SHOULD DO — three changes, all small

### 5a. Start the poller when the BACKEND comes up, not when a tab is opened

`agents_api._ws_start_poller` calls `sync.start()` from `GET /workspace`. It works, and
`start()` is now **idempotent and thread-safe** — eight calls make one poller, and six threads
calling it at once make one poller (both tested, and mutation-tested). So nothing there is broken
and nothing has to change in a hurry.

But it means **sync only runs while somebody has the Connections tab open**, and section 1's
"nobody presses sync, nobody imports anything" is quietly untrue: a teammate who works all morning
in Chat and Library hears about nothing anybody else did. That is the promise, not a nicety.

**Where it belongs:** the same place `prompts/store.install()` is called — `agents_api`, at import.
That module's own docstring says it is "the process the run actually happens in: the panel's routes
and the agent's loop share it". One line, beside that call:

```python
try:
    from seo_agent.workspace import sync as _ws_sync
    _ws_sync.start()
except Exception:                     # noqa: BLE001 — no workspace, no network, still boots
    pass
```

`start()` deliberately does **not** check `configured()` first: with no workspace the poller sits in
the backoff doing nothing (one wakeup every `POLL_BACKOFF_SECONDS`) and picks a workspace up by
itself the moment Create or Join finishes. Refusing to start without one would mean somebody has to
remember to start it again afterwards, and that is exactly what nobody remembers.

Leave `_ws_start_poller` where it is as a belt — it now costs an `is_alive()` check.

### 5b. Read the pack's state from `status()`, not from a callback of your own

`sync.status()` now carries it:

```python
status()["pack"]  ->  {"state", "note", "at", "builds", "last_error"}
    state: idle · building · uploading · joining · waiting
```

`waiting` is a rebuild that has been asked for and is armed behind the coalesce window — the one in
section 2 that stops a long catch-up session uploading the same pack six times. It had no
representation on screen before.

To wire it, two lines where `_ws_rebuilder` builds the Rebuilder:

```python
_ws_rebuilder_ref[0] = pack.Rebuilder(
    client, progress=sync.pack_progress,            # <- was _ws_pack_progress
    cursor=lambda: sync.last_seen_id(client))
sync.attach_pack(_ws_rebuilder_ref[0])              # <- new
```

`sync.pack_progress` has pack.py's exact `progress` signature, so it drops straight in. Then
**delete `_ws_pack_progress` and `_ws_pack`** — that is the side channel, and while it exists there
are two answers to the same question.

`running` and `pending` are read off the Rebuilder itself, so the engine's own state wins wherever
the two could disagree (a stage left over from the last run cannot report "building" when nothing is
running). There is a test asserting **every stage `pack.py` actually emits** is one `sync` knows how
to show — read out of their source, so a stage they add that I do not know about fails my suite
instead of quietly reading as "idle" in the middle of an upload.

**The one getter I would rather have** (nothing blocks without it): `pack.Rebuilder` has no state
accessor, so `sync.pack_state()` reads its public attributes — `running`, `pending`, `builds`,
`last_error` — from outside. Tidier:

```python
class Rebuilder:
    def state(self):
        """{running, pending, builds, stage, last_error, last_started} under the lock."""
```

If it also recorded the `stage` it already sees in `_run`, `sync` could drop its progress sink
entirely and the whole thing would come from one object.

### 5c. Catch a joiner up before the screen says "done"

`agents_api` line ~1348 saves `replay_from` as `last_seen_id` and returns. For the next few seconds
the new teammate has a knowledge base that is **known to be stale** — everything that happened while
33.6 MB was downloading — with nothing saying so, until the poller's next tick quietly fixes it.

Replace the save with:

```python
sync.catch_up(client, replay_from=got.get("replay_from"))
```

It sets the cursor and drains once. **I checked `pack.py` rather than assuming:** `join()`'s own
docstring says "the joiner then drains `changes` for `id > replay_from` and is level with everyone
else", and both files rest on the same property — every apply is an upsert keyed by the row's own
key, so replaying is a no-op. So the `full_replay` case (an old workspace with no `pack_change_id`,
boundary 0) is slow, never wrong. The cursor is only ever moved FORWARD, and the call never raises:
a join that fetched 33 MB successfully must not be reported as failed because the poll after it hit
a flat network.

### 5d. And the things that were already true

- Call `sync.push(kind, key, local_row)` **after** the local write has landed. Push does not write
  the local knowledge base — whatever made the change already did, which is why Sutra stays fast —
  and the row comes back down the log a moment later and lands through `mirror` as an upsert of the
  same values. One direction of travel, no special case for "my own change".
- Pass the **local** shape, not the database shape. `{"note": …}` for a CTA link,
  `{"brand_oneliner": …}` for the company, the whole idea row for an idea. `mirror.to_wire`
  translates.
- `status()` also carries `outbox` (how much is waiting, and why the head is stuck), `stuck` (a log
  row that will not apply) and `clock_skew` (3c). One request, one dict.

## 6. DECISIONS I MADE THAT NOBODY ASKED ME TO

Listed so they can be overruled.

1. **A row that cannot apply is set aside, not retried for ever.** An unknown kind, or a prompt that
   fails `prompts/store`'s own `{{TOKEN}}` check, goes to `workspace/refused.jsonl` with its reason
   and the cursor moves past it. A *transient* failure blocks the drain and retries; after
   `sync.POISON_TRIES` (5) consecutive failures on the same row it is set aside too. Blocking for
   ever would freeze every future change for that person behind one bad row. Nothing is dropped
   silently: it is in a file, with its error, and `sync.status()` reports it.
2. **The outbox is a queue, so a failing item blocks the ones behind it.** Two edits of one prompt
   must land in the order they were made; stepping over a failure would let the older overwrite the
   newer.
3. **No maximum attempt count.** Backoff is 1s, 2s, 5s, 15s, 60s, then 5 minutes for ever. Telling
   somebody their work went up when it did not is the failure this module exists to prevent.
4. **The cursor advances per contiguous same-kind batch, not per row** (`sync.APPLY_BATCH`, 200). A
   crash replays a batch, never skips it, and a 40-page delete rewrites `content-database.jsonl`
   once instead of forty times. Every handler is upsert-by-key or delete-by-key, so a replay
   converges rather than doubling.
5. **`company` is merged field by field, not replaced.** `brand/company.json` also holds
   `wordpress_url` and `location_name`, which are per-install and are not columns in the `company`
   table; a whole-row replace would blank them on every teammate.
6. **`cta_links` lands through `cta.parse` + `cta.render`, not `cta.save`.** `cta.save` marks every
   row it is handed `<!--mine-->`, so it would flip the generated rows to person-authored the first
   time a synced link arrived. The per-install facts under a row (its kind, traffic, product
   features — what the writer reads when it picks a close) are kept across a synced edit.
7. **A `library` payload with an empty `body_md` keeps the article already on disk.** Meta-only
   updates are the common case after the first send, and blanking a colleague's article would be
   unrecoverable.
8. **`ideas.data` and `library.meta` are the authority; the flat columns beside them are for
   reading in the Supabase Table Editor.** Nothing takes a value off both.
9. **`POLL_SECONDS = 2.0`.** The person who made the change is not waiting on it (push drains at
   once), so this is only the receiving-end delay against the plan's "about a second".
10. **The pull re-checks the server's clock every five minutes, not every poll.** A failed probe
    resets the timer too, so a proxy that strips `Date` costs one HEAD every five minutes rather
    than one per poll — the price being five minutes in the conservative path, which is the safe
    direction.
11. **The client-side truncation stops at the first row that is too new and does not look past it.**
    Order is the protocol; skipping a held-back row to "make progress" is the exact bug the lag
    exists to prevent.
12. **`start()` does not check `configured()`.** A poller with no workspace idles in the backoff
    and picks one up by itself; the alternative is somebody having to remember to start it again
    after Create or Join.
13. **`sync.pack_state()` reads `pack.Rebuilder`'s public attributes rather than owning a copy.**
    The Rebuilder is the only thing that knows whether a rebuild is in flight or armed, and a
    second copy of that in `sync` would be a second thing to be wrong.
14. **`company.workspace_id` is never sent.** The column defaults to `current_workspace_id()`, and
    that default is what makes a second company row impossible. `outbox` skips stamping a key into
    a pk listed in `mirror.PK_DEFAULTED`.

---

## 7. WHAT IS NOT BUILT, AND IS NOT MINE

- **The pack** (section 2's "one click updates both", the ~1 minute background rebuild, the
  five-minute supersede guard). Sync carries the ~2 second half only.
- **Trimming `pages` when the pack is rebuilt.** See 3a for the rule it must follow.
- **Migrations.** When one adds a table, add it to `mirror.TABLES` and `mirror.HANDLERS` together,
  and add its primary key name to `log_change()`'s `coalesce` list in `schema.sql` or the log row
  will carry an empty key.
