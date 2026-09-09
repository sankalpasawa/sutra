# HANDOFF-W1 — the workspace core

**written**: 2026-09-10 · **covers**: `seo_agent/workspace/{__init__,_common,client,schema,link}.py`,
`seo_agent/workspace/schema.sql`, `seo_agent/tests/test_workspace_core.py`

Built to `design/WORKSPACE-PLAN.md`. Two things live here: the **live proof still to run** (part 1,
because it gates everything) and the **changes other people's files need** (part 2).

---

## Part 1 — the live proof, in the order it must be run

None of this has been run. The blocker is single and specific: **there is no Supabase personal
access token (`sbp_…`) on this machine**, and nothing else can create a table. `~/.sutra-supabase`
holds the project URL and the database password only, the database password is a dead end
(WORKSPACE-PLAN section 4: IPv6-only host, no IPv6 on this Mac), there is no `supabase` CLI, and
there is no local Postgres or Docker to dry-run the SQL against.

Two ways to unblock: paste an `sbp_` token, or open the project's SQL Editor, paste
`seo_agent/workspace/schema.sql`, press Run, and report the verdict row it prints.

**Step 1 comes first on purpose.** If the publishable key cannot work the bucket, the join flow is
dead and steps 2 to 5 do not matter.

### 1. The four storage operations, with the publishable key — THE ONE THAT GATES EVERYTHING

Run after the SQL has been applied. `KEY` is the publishable key, `URL` the project URL.

```
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from seo_agent.workspace import client
U, K = "<project url>", "<sb_publishable_ key>"
print("bucket   :", client.bucket_exists("knowledge", url=U, key=K))
print("upload   :", client.upload("knowledge", "probe/hello.txt", b"one", url=U, key=K))
print("download :", client.download("knowledge", "probe/hello.txt", url=U, key=K))
print("replace  :", client.upload("knowledge", "probe/hello.txt", b"two", url=U, key=K))
print("re-read  :", client.download("knowledge", "probe/hello.txt", url=U, key=K))
print("list     :", [o.get("name") for o in client.objects("knowledge", "probe", url=U, key=K)])
print("remove   :", client.remove("knowledge", "probe/hello.txt", url=U, key=K))
print("gone     :", [o.get("name") for o in client.objects("knowledge", "probe", url=U, key=K)])
EOF
```

**Look for:** `bucket True`; upload returns the path; download returns `b'one'`; the replace
succeeds and the re-read returns `b'two'`; list shows `hello.txt`; remove returns True and the
final list is empty.

**What each failure means:**

| Failure | Meaning | Fix |
|---|---|---|
| `bucket False` | the `do $storage$` block hit `insufficient_privilege` and rolled itself back | make a private bucket named `knowledge` by hand in Storage, then rerun the script for the policies |
| upload raises 400/403 "new row violates row-level security policy" | `knowledge_write` did not attach to `storage.objects` | the policy shape is wrong, or the role is not `anon` — check `select * from pg_policies where schemaname='storage'` |
| replace raises but upload worked | `knowledge_replace` (the UPDATE policy) is missing. `x-upsert` needs **both** insert and update | add the update policy |
| remove raises | `knowledge_remove` missing. Non-fatal: old packs would pile up, nothing breaks |
| download raises but upload worked | `knowledge_read` missing. **Fatal** — this is exactly the join flow |

**This is the known unproven risk, stated plainly:** the four `storage.objects` policies are
written from the documented shape, not from a measurement. `storage.objects` is owned by
`supabase_storage_admin`, so the transaction may lack the privilege to attach policies to it at
all — which is why the whole block is wrapped in an exception handler that lets the tables
survive. If step 1 fails, the fix is a policy change, not a redesign: the bucket, the key and the
endpoints are all already proved to work.

### 2. The tables

```
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from seo_agent.workspace import schema; \
  print(schema.verify('<url>','<key>'))"
```

**Look for:** `ok: True`, ten names in `present`, `missing: []`, `unreadable: {}`, `bucket: True`,
and a real uuid in `workspace_id`.

A non-empty `missing` means the transaction did not complete — rerunning the script is safe and
finishes the job. A non-empty `unreadable` is worse and more interesting: the table exists but the
publishable key cannot read it, which means an RLS policy or a grant is wrong. That is the failure
the OpenAPI-root approach could never have seen.

### 2c. That both pack counters are there

```
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from seo_agent.workspace import client; \
  print(client.one('workspace', columns='schema_version,pack_version,index_version', \
  url='<url>', key='<key>'))"
```

**Look for:** `{'schema_version': 2, 'pack_version': 0, 'index_version': 0}`.

`index_version` **missing** is the one to catch, and it is easy to miss because it is not a
crash: `pack.py` detects the absent column, falls back to reading the sidecar to avoid
re-sending an unchanged index, and reports `index_versioning: False`. Everything keeps working
— except the index is then overwritten in place, and a teammate 171 MB into downloading it
during a replace can get a torn object. Run `schema.migrate(...)` to add it. `schema_version`
reading 1 rather than 2 means the same thing from the other end.

### 3. The trigger, which is the whole sync protocol

```
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from seo_agent.workspace import client
U, K = "<url>", "<key>"
client.save_settings(workspace_url=U, workspace_key=K, member_name="ProofRun")
client.insert("competitors", {"domain": "probe.example", "why": "trigger proof"})
client.update("competitors", {"domain": "probe.example"}, {"why": "changed"})
client.delete("competitors", {"domain": "probe.example"})
for row in client.select("changes", where={"kind": "competitors"}, order="id.asc"):
    print(row["id"], row["op"], row["key"], row["actor"])
EOF
```

**Look for:** three rows, `insert` / `update` / `delete`, all keyed `probe.example`, all with
actor `ProofRun`.

Fewer than three rows means the trigger is not attached to that table and the sync protocol is
silently lossy — the exact failure the trigger exists to prevent. Actor `unknown` instead of
`ProofRun` means PostgREST is not publishing `request.headers`; not fatal, but the Library would
stop being able to say who wrote what, so say so.

### 2b. That the bucket's object limit is the pinned one

```
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from seo_agent.workspace import client; \
  print([(b['name'], b.get('file_size_limit')) for b in client.objects.__globals__['request']( \
  'GET','<url>/storage/v1/bucket','list buckets',headers=client.headers(key='<key>')).json()])"
```

**Look for:** `('knowledge', 47185920)` — 45 MiB.

`None` means the bucket is running on the plan default and the pin did not take: `pack.py` will
then adapt its part size to whatever the plan reports, which works but means the split changes
if the plan does. A value **lower** than 47185920 is the one to worry about — `pack.py` sizes a
part as `min(PART_BYTES, limit - PART_HEADROOM)`, so a smaller limit silently shrinks every
part, and parts already stored at the old size would be stranded. Costs nothing to check now,
confusing to diagnose later.

### 3b. That the lag window actually holds under concurrent writers

The one thing steps 1-3 cannot show. Two writers, at once, one of them slow:

```
.venv/bin/python - <<'EOF'
import sys, threading, time; sys.path.insert(0, ".")
from seo_agent.workspace import client
U, K = "<url>", "<key>"
def w(n): client.insert("competitors", {"domain": "race%d.example" % n, "why": "race"}, url=U, key=K)
ts = [threading.Thread(target=w, args=(n,)) for n in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
rows = client.select("changes", where={"kind": "competitors"}, order="id.asc", url=U, key=K)
ids = [r["id"] for r in rows]; ats = [r["at"] for r in rows]
print("ids gapless :", ids == list(range(min(ids), max(ids) + 1)))
print("at ascends  :", ats == sorted(ats))     # the property the guard needs
for n in range(20): client.delete("competitors", {"domain": "race%d.example" % n}, url=U, key=K)
EOF
```

**Look for:** both True. `at ascends` matching id order is the whole point: it is what makes
"only read rows older than the window" equivalent to "only read rows nothing can still slip in
front of". If `at` does NOT ascend with `id`, the column is being stamped at transaction start
and something has changed it back to `now()`.

### 3c. That the heartbeat does not reach the log

```
client.register_member("ProofRun", url=U, key=K)     # should appear in `changes`
before = len(client.select("changes", where={"kind": "members"}, url=U, key=K))
for _ in range(3): client.heartbeat(url=U, key=K, force=True)
after  = len(client.select("changes", where={"kind": "members"}, url=U, key=K))
print("join logged:", before >= 1, "| heartbeats logged:", after - before)
```

**Look for:** `join logged: True` and `heartbeats logged: 0`. Any number above zero means the
trigger's `last_seen_at` exemption is not firing and the log will fill with heartbeats — not
data loss, but an append-only table that grows for ever and re-mirrors the member list on every
poll.

### 4. That the log cannot be forged

```
client.insert("changes", {"kind": "ideas", "op": "insert", "key": "x"})
```

**Look for:** a raised error. A success means `changes` is writable by the app, the append-only
guarantee is gone, and a bad client could rewrite history.

### 5. Idempotency

Run the whole of `schema.sql` a second time. **Look for:** the same verdict row, no error, and
`verify()` still `ok: True` with the same `workspace_id`. A changed workspace id means the
`workspace_single_row` index is not doing its job.

### Then clean up

Delete the probe object if step 1 stopped early, and drop the tables so the owner's own first run
starts from an empty project:

```sql
drop table if exists public.changes, public.pages, public.library, public.company,
  public.cta_links, public.competitors, public.prompts, public.ideas, public.members,
  public.workspace cascade;
drop function if exists public.log_change(); drop function if exists public.current_workspace_id();
delete from storage.objects where bucket_id = 'knowledge';
delete from storage.buckets where id = 'knowledge';
```

---

## Part 2 — changes needed in files W1 does not own

### `seo_agent/store.py` — no change needed

`connections()` and `save_connections()` are enough as they are, and `save_connections` already
chmods to 0600. The workspace keeps six fields in there: `workspace_url`, `workspace_key`,
`workspace_id`, `member_id`, `member_name`, `last_seen_id`. `client.save_settings()` merges rather
than replaces, so the DataForSEO and Voyage credentials in the same file are safe.

### `agents_api.py` — five routes, all thin

Every one is a pass-through. **No route may decide whether a workspace is ready** — only
`schema.verify()` does that, and every one of these returns its dict unchanged.

| Route | Calls | Returns |
|---|---|---|
| `GET  /api/agents/seo/workspace` | `schema.ready()` normally, `schema.verify()` when the request says `?check=1` | the dict as-is. It carries `checked: "shallow"` or `"full"` — pass that through so the screen can say which it got |
| `POST /api/agents/seo/workspace/create` | `schema.create(url, key, token=body.get("token"), member_name=body.get("name"))` | the dict as-is. **Do not log the body, and do not store `token` anywhere** — it arrives, is passed as an argument, and dies with the request |
| `POST /api/agents/seo/workspace/confirm` | `schema.confirm(url, key, member_name=body.get("name"))` | the dict as-is. This is the paste route's "I've run it" button |
| `POST /api/agents/seo/workspace/join` | `schema.join(body["link"], body.get("name"))` | the dict as-is. It reads the link, verifies, remembers and enrols — the route does none of that itself |
| `POST /api/agents/seo/workspace/members` | `client.heartbeat()` then `client.members(active_within=client.ACTIVE_SECONDS)` | the rows |
| `POST /api/agents/seo/workspace/leave` | `client.forget()` | `{"ok": true}` |

Wrap each in `try/except WorkspaceError as e: return {"ok": False, "error": str(e)}, 400`.
`str(e)` is already the sentence to show the person; **do not rewrite it, and do not append a
status code.** Never put `e.body` in a response — it is for the log.

### The panel's members stopgap comes out — these are the functions to call instead

The engine owns `members`. Nothing outside `seo_agent/workspace/` may insert into it: two
writers deciding what a member row looks like drift, and the one that drifts is always the one
nobody re-reads.

| Instead of the panel writing the row | Call |
|---|---|
| on create | `schema.create(url, key, token=..., member_name=...)` — enrols the creator itself |
| on confirm (the paste route) | `schema.confirm(url, key, member_name=...)` — same |
| on join | `schema.join(link_text, name)` — reads the link, verifies, remembers, enrols |
| "I'm still here" | `client.heartbeat()` — safe to call on every poll, rate-limited to `client.HEARTBEAT_SECONDS` (60) internally |
| "who is in it" | `client.members(active_within=client.ACTIVE_SECONDS)` for who is around now, or `client.members()` for everybody who ever joined |
| this seat's id | `client.member_id()` — minted once, kept for good, no network call |
| enrol directly, if a flow ever needs it alone | `client.register_member(name)` |

All of it is idempotent on `member_id`: a retried create, a rejoin, or a link pasted twice
updates the existing row and never adds a second. `joined_at` is deliberately not touched on
re-registration — a `joined_at` that moves is just a second `last_seen_at`.

A member row that fails to write does **not** fail the join. The person is connected, their
Library and prompts work, and they appear in the list at the next heartbeat; the result carries
`member: {"ok": false, "error": ...}` so the screen can say so quietly.

### The cheap readiness check exists — drop the 60-second cache

There is a clean way, so it belongs here rather than in the panel: **`schema.ready()`, one round
trip.** Use it for the poll and keep `schema.verify()` for `?check=1`.

It works because of rule 1 of `schema.sql`: the tables are created in **one transaction**, so a
`workspace` row this key can read proves the other nine exist and that RLS lets this key read
them. The bucket is the one piece allowed to fail on its own — its block catches
`insufficient_privilege` so a storage problem cannot cost somebody nine tables — which is
exactly why `schema.sql` now **records** it in `workspace.bucket_ready` instead of leaving it
to be inferred. So one read answers tables, bucket, id, name, schema version and pack version.

**Its limit, stated so nobody stretches it:** `bucket_ready` is a record of what happened at
creation, not an observation of what is true now. A bucket deleted by hand afterwards still
leaves it true. So `ready()` may never report a workspace ready for the *first* time —
`create()`, `confirm()` and `join()` all go through `verify()`, and a test asserts they do. The
result labels itself `checked: "shallow"` vs `"full"` so this is visible at the call site.

### `static/**` — the Connections tab

Create: two boxes (Project URL, publishable key), an optional third for an access token labelled
*"optional — used once and never saved"*, and a Create button. When the response comes back with
`route: "paste"`, show `reason`, then `sql` in a copy box, then `editor_url` as a button, then an
"I've run it" button that hits `/confirm`. **That is not an error state, it is the other route**,
so it must not be styled as a failure.

Join: one box for the link, one for a name, a Done button.

The share link comes from `link.make_link(url, key, workspace_id)` and stays in the tab for good,
with a copy button.

### `seo_agent/tests/run_all.sh` — done

`test_workspace_core` was added between `test_find_prompt` and `test_workspace_sync`.

---

## Decisions made without asking

-4. **`workspace.index_version`, and the first migration.** The pack is a 33.6 MB core plus a
   171.5 MB meaning index, and they publish on different terms — the core on every refresh, the
   index only when its content hash moves. `pack_version` counted the core; the index was
   uncounted and therefore overwritten in place, so a teammate mid-download could get a torn
   object. One shared counter cannot serve both: it would either re-upload 171 MB on every
   refresh to keep the number honest, or claim an index version that was never written. Hence a
   second column. `SCHEMA_VERSION` is now **2**, `schema.sql` writes 2 at creation, and
   `MIGRATIONS` carries step 2 (`add column if not exists`) — because `create table if not
   exists` will not add a column to a table that already exists, so a workspace made before
   today can only get it that way. Fresh workspaces need no migration; the test asserts both.
-3. **`workspace.bucket_ready`, and `schema.ready()`.** A one-call readiness check for the
   once-a-second poll, sound only because the tables are created atomically. See the section
   above for the contract and its limit.
-2. **The `changes` trigger skips a heartbeat.** An update to `members` that changed nothing but
   `last_seen_at` is not logged. Otherwise five people heartbeating once a minute would append
   five rows a minute to an append-only log for ever, and every client would re-mirror the
   members table each time — a log filling up with the fact that nothing happened. Any other
   change to a member, including a rename, still logs.
-1. **The `knowledge` bucket pins `file_size_limit` to 47185920 (45 MiB).** Supabase Free caps one
   object at 50 MB and the owner's real pack is 205 MB zipped, so the pack goes up in parts and
   the part size must be decided here, not discovered from whatever plan the bucket was made on.
   **45 and not a rounder 40**: `pack.py` sizes a part as `min(PART_BYTES, limit - PART_HEADROOM)`
   = `min(40 MiB, limit - 4 MiB)`, so a 40 MiB pin would have cut its parts to 36 MiB and made
   the pin the very thing that changed the split it was added to stop. The upper bound is the
   smaller reading of "50 MB" (50,000,000), because the decimal and binary readings are four
   megabytes apart. The conflict clause only ever **raises**, since lowering strands parts
   already stored. `test_workspace_core` asserts the number against `pack.py`'s own constants,
   so moving either turns the suite red on purpose.
0. **`changes.at` is `clock_timestamp()`, not `now()`, and there is an index on `(at, id)`.**
   `bigserial` allocates at INSERT and not at COMMIT, so a writer holding id 7 can commit after a
   writer holding id 8, and a poller that read 8 would never read 7. The reader guards against it
   with a three-second lag window; `now()` is transaction START time and would stamp a slow writer
   early, defeating the guard. Residual, written into `schema.sql` above the column: a transaction
   held open longer than the window can still be skipped. Fine for single-row REST writes,
   **not fine for anything batched** — revisit this before any long multi-row write path ships.
1. **`changes` has an `op` column** (`insert` / `update` / `delete`) which WORKSPACE-PLAN section 3
   does not list. The plan says deletions arrive as ordinary log rows; a client cannot act on one
   unless it can tell a delete from an update, and every consumer would otherwise have to guess
   from the payload.
2. **The workspace id is generated by the database**, not by Sutra, which is what lets `schema.sql`
   be a file with no placeholders — literally the same bytes for every company, as section 4 asks.
   The name defaults to "Team workspace" and is renameable through `update`.
3. **`verify()` probes each table rather than reading the OpenAPI root.** Measured 2026-09-10:
   `GET /rest/v1/` answers a publishable key with 401 "Secret API key required". Probing is also
   the stronger check — it proves each table is reachable with the exact key the app will use.
   Do not "simplify" it back.
4. **The storage block catches `insufficient_privilege`** rather than aborting the transaction, so
   a storage-permission problem cannot cost the person their nine tables. `verify()` is what
   reports the workspace as not ready.
5. **`update()` and `delete()` refuse an empty `where`.** In PostgREST an empty filter means every
   row, so a caller that meant "this one" and passed `{}` would rewrite the whole table.

## The one number two files have to agree on

`changes.at` defaults to `clock_timestamp()` and the reader in `sync.py` filters
`at < now() - interval '3 seconds'`. Neither half works alone, and the number lives in two
places: a comment in `schema.sql` and a constant in `sync.py`. **If either moves, both move.**
There is deliberately no shared constant for it — the SQL cannot import Python — so the coupling
is written into both files instead. `test_workspace_core` asserts the SQL comment still says
three seconds, which will at least make a one-sided change fail loudly.

## Running the migration, when it is needed

A workspace created before today (there are none that I know of — the owner's project was still
empty at the time of writing) reports `schema_version: 1`. To bring it up:

```
schema.migrate(url, key, token="<sbp_ token>")   # seamless
schema.migrate(url, key)                          # no token: returns the paste route,
                                                  # carrying ONLY the missing steps
```

The paste route hands back just the migration SQL, never the whole create script. Each step is
wrapped in its own transaction with the version bump inside it, so the recorded version can
never be ahead of the change it describes. `migrate()` refuses outright on a workspace that
`verify()` says is incomplete.

## Open, for whoever comes next

- `changes` is append-only and grows for ever. Trimming it (rows older than the current pack, say)
  belongs with the pack rebuild, which is W2's.
- `seo_agent/workspace/` now also holds `sync.py`, `pack.py`, `mirror.py` and `outbox.py` from W2.
  `workspace/__init__.py` deliberately imports only `client`, `link` and `schema`, so a half-built
  module there cannot break importing the core. Add them to `__init__` when they are green.
