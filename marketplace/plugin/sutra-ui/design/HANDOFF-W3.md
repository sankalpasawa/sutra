# HANDOFF-W3 — the knowledge pack

**written**: 2026-09-10 · **from**: the agent that built `seo_agent/workspace/pack.py`
**to**: whoever owns `workspace/client.py`, `workspace/schema.sql`, `sync.py`, and the UI

The pack is built and green: `seo_agent/tests/test_workspace_pack.py`, **185 checks**, offline
against a fake Supabase, plus real end-to-end runs against a copy of the owner's install.
Below is the headline measurement, then everything this file assumes about the parts it does
not own.

**The pack is now two objects, core and index** (approved 2026-09-10). Section 1 has the
numbers; section 1a has the rule, which is the thing not to get loose.

---

## 1. The numbers, measured, not estimated

Built from a clone of `~/.sutra-ui/agents/seo/knowledge` on 2026-09-10, on the owner's Mac.
The plan's "~326 MB raw, about 100 MB zipped" is right on the raw and wrong on the zipped:

| | plan said | measured |
|---|---|---|
| raw knowledge in the pack | ~326 MB | **337.2 MB**, 533 files |
| zipped, both halves | **~100 MB** | **205.1 MB** |
| deterministic across two builds | — | yes, byte-identical, per half |

84% of it is the meaning index — float32 vectors that deflate to 0.89 and never will do
better. `brand/` is 0.4 MB, not 3 MB; the 3 MB figure counted `brand/_work`, which is builder
scratch and does not travel (WORKSPACE-PLAN section 7).

### The two halves

| half | contents | raw | zipped | build | parts |
|---|---|---|---|---|---|
| **core** | `site_index.json` + `content-database.jsonl` + `brand/` | 143.5 MB | **33.6 MB** | 2.7 s | 1 |
| **index** | `content-index/` | 193.3 MB | **171.5 MB** | 4.9 s | 5 |

### What a refresh actually costs now

| | time (CPU) | uploaded | peak RSS |
|---|---|---|---|
| first publish, both halves new | 8.0 s | 205.1 MB | 32.9 MB |
| **a normal refresh, index unchanged** | **2.9 s** | **33.6 MB** | 32.9 MB |
| a refresh after `build_page_index` ran | 7.8 s | 205.1 MB | 32.9 MB |

### So: is "about a minute, in the background" a promise we can keep?

**Yes now, and it was not before.** The common case is 33.6 MB, and 2.9 seconds of it is fixed:

| uplink | 33.6 MB (normal refresh) | 205 MB (after an index rebuild) |
|---|---|---|
| 10 Mbps | 27 s → **~30 s total** | 164 s → ~3 min |
| 20 Mbps | 13 s → **~16 s** | 82 s → ~1.5 min |
| 40 Mbps | 7 s → **~10 s** | 41 s → ~50 s |
| 100 Mbps | 3 s → **~6 s** | 16 s → ~25 s |

A normal refresh is comfortably inside a minute at any uplink worth the name, including a bad
one. The 205 MB case only happens when the index itself was rebuilt, which is rare and which
the person has just sat through a Voyage embedding run for anyway.

**The UI should still print the stage, not a time** — "part 3 of 5" is honest on any line and
"about a minute" is a promise on a line nobody has measured. `progress()` already emits it.

### And a join

The teammate is working after the core: 33.6 MB, about 7 seconds on a 40 Mbps line, against
the five minutes the plan budgeted. `join()` returns at that point and the 171 MB index lands
behind them on a background thread. See section 4a for what that costs them in the meantime
(answer: internal links match on titles, which is what a person with no Voyage key gets today).

---

## 1a. THE RULE, and the seam where drift could sneak back in

The split is **not** permission to defer either half. It is written into `pack.py`'s docstring
in those words, and there is a test asserting that sentence is still in the file, because this
is exactly the place a future reader could quietly reintroduce what the owner rejected.

| half | when it is rebuilt and re-uploaded | how that is decided |
|---|---|---|
| **core** | **every single refresh**, with no test of whether it was worth it | not decided at all — it just happens |
| **index** | **whenever the index has changed** | its content hash against the `content_sha256` in the published sidecar |

The index test is an **exact comparison of the bytes**, not a threshold and not a heuristic.
There are only two answers: identical, in which case the bytes in the bucket already *are* the
bytes on disk and re-sending them would arrive at the file that is already there; or not
identical, in which case it is stale from that moment and goes up on the same call as the core.
If `build_page_index` runs, the hash differs. There is no window and no "has it moved enough".

Hashing 193 MB to find out costs about a third of a second and is streamed, so it never loads
the index to decide whether the index moved. Tests pin all of it: a refresh with *nothing*
changed still re-uploads the core and still does not re-upload the index; appending one line to
`content-index/body/meta.jsonl` puts the index up on the very next publish.

**The two halves are committed separately, on purpose.** The core is the half the ruling is
about and it must not be held hostage to the index: if the 171 MB index upload fails, the core
has already landed and every teammate already has the new pages. The row still points at the
previous index version, which still exists, and the next refresh finds the hash still different
and tries again. A joiner in between gets the new core with the older index, which is a valid
pair — the index is a search aid, and a page it has not heard of simply does not come back from
semantic search.

---

## 2. What `client.py` needs to grow

`pack.py` is written against the five calls in the brief plus `client.delete`, and it works
today with only those. Each extra below is **used when present and degraded honestly when
absent** — the result dict always says which path ran, so nothing ever reports a check it did
not perform. The tests take each one away to prove that.

```python
buckets() -> list[dict]
    # GET /storage/v1/bucket. Each dict: {"name": str, "file_size_limit": int|None, ...}.
    # WITHOUT IT: the bucket pre-flight is skipped and a missing bucket is discovered after
    # 337 MB has been packed, and the part size falls back to the 40 MB constant.

stat(bucket, path) -> dict | None            # {"size": int}; None when not there
    # HEAD, or one row of the existing objects(bucket, prefix=...) listing.
    # WITHOUT IT: publish cannot prove a part landed whole. It reports
    # upload_verified="none" rather than claiming the upload was verified.

upload_file(bucket, path, file_path, offset=0, length=None, progress=None) -> str
    # Upload a SLICE of a local file without reading it into memory.
    # WITHOUT IT: pack.py reads one 40 MB part into bytes and calls upload(). Measured:
    # 116 MB peak RSS instead of 32 MB. Works, but it is 84 MB of a laptop for nothing.

download_stream(bucket, path, start=0) -> iterator[bytes]
    # GET with `Range: bytes=<start>-`. Supabase Storage supports it.
    # WITHOUT IT: resume still works, but only at whole-part granularity — a dropped
    # connection costs up to 40 MB instead of a few kilobytes. download() reports
    # resume="range" or resume="part" so the UI knows which it got.
```

Already there and used exactly as written: `upload`, `download`, `remove`, `select`
(including `where={"col": ("lt", v)}`, `order="id.desc"`, `limit=`), `upsert`, `delete`.

**`upload` needs its `x-upsert` behaviour kept.** A part is re-uploaded when a publish is
retried, and it must overwrite rather than 409. `client.upload` already sends it.

---

## 3. What `schema.sql` needs to grow — SIX COLUMNS ON `workspace`

`pack.py` works without them (it writes only the columns the row already has, and names the
rest in `result["row_fields_missing"]`), but two of them cost real correctness if they are
missing. Add to the create block, and to the migration list:

```sql
alter table public.workspace add column if not exists pack_sha256     text    not null default '';
alter table public.workspace add column if not exists pack_bytes      bigint  not null default 0;
alter table public.workspace add column if not exists pack_parts      integer not null default 0;
alter table public.workspace add column if not exists pack_part_bytes integer not null default 0;
alter table public.workspace add column if not exists pack_change_id  bigint  not null default 0;
alter table public.workspace add column if not exists pack_built_at   timestamptz;
alter table public.workspace add column if not exists index_version   integer not null default 0;
```

| column | what breaks without it |
|---|---|
| `pack_change_id` | **The one that matters.** It is the joiner's replay boundary — the `changes.id` the pack stops at. Without it a joiner replays the ENTIRE log on top of the pack. That is the safe direction (every replay is an upsert, so it is slow rather than wrong) and `join()` returns `full_replay: True` to say so, but it is minutes of pointless work on every join. HANDOFF-W2 §146 asks for the same thing. |
| `pack_sha256`, `pack_bytes`, `pack_parts`, `pack_part_bytes` | Nothing breaks: `download()` falls back to reading `pack/<v>.zip.sha256` out of the bucket, which carries all four. It is one extra request. |
| `pack_built_at` | Nothing. It is for the UI. |
| `index_version` | **The one that costs real bytes.** It is which version of the meaning index the workspace is on. Without it the index has no generations: it is pinned at version 1 and overwritten in place, so the "keep the previous one" safety applies to the core only and a teammate downloading the index while it is being replaced can get a torn object. `pack.py` detects the missing column, still avoids re-sending an unchanged index (the published sidecar answers the question when the row cannot), and reports `index_versioning: False` so nobody is surprised. |

**No change is needed to `pages`.** `pack.py` trims on `pages.pack_version`, which is already
there and already documented in `schema.sql` as "the pack this delta is measured against". I
had written this against a `change_id` column and changed it to match yours — one concept, one
column name.

**One thing whoever writes `pages` rows must do:** set `pack_version` to the workspace's
current `pack_version` on every insert. The default is 0, and if it stays 0 every row looks
older than the next pack and gets trimmed on the first rebuild.

### The trim rule, held identically by all three of us

Agreed with the sync and schema agents, 2026-09-10, and pinned by a test on my side
(`trimming pages is a DELETE and only a delete`):

| what happened | how it is written | what consumers do |
|---|---|---|
| a page is genuinely gone from the site | `op='gone'` on the row — an **UPDATE** | apply it: drop the page locally |
| the delta was trimmed after a pack rebuild | a plain **DELETE** of the rows | **ignore it** |

`_trim_pages()` issues `delete from pages where pack_version < N` and writes nothing else — it
never marks a row, never blanks a field, never touches `op`, and never expresses "this page
went away". `mirror._trimmed()` is the consumer half of the same rule and keys on the log
row's `op` being `delete`. If the schema ever makes a trim look like content, routine
housekeeping reaches four other people as "these 12,318 pages are gone" and empties their
catalogues on every rebuild. **My reading of `schema.sql` agrees with this in full** — nothing
in it contradicts the rule.

---

## 4. What `sync.py` must guarantee before calling `publish()`

`publish(client, kroot=..., last_seen_id=...)`. The `last_seen_id` you pass is used for three
things at once, which is deliberate — one number, so they cannot disagree:

1. it becomes `workspace.pack_change_id`, the joiner's replay boundary;
2. it decides whether the trim is safe to run;
3. it is the claim "this pack contains everything up to here".

**Pass the cursor as it was BEFORE the pack was asked for**, i.e. the value after your last
completed pull. Reading it early means the pack may contain a change it does not claim, which
is harmless (the change gets replayed onto data that already has it, and every replay is an
upsert). Reading it late means a change could be claimed as packed when it is not, which is a
page a teammate never sees. Always err early.

`publish()` also reads `max(changes.id)` itself, one row, and if the log is ahead of the cursor
it uploads the pack as normal but **trims nothing** — a page another teammate changed is not in
the pack we just built, and deleting that row would lose the change for every future joiner.
`result["behind"]` says how far behind we were. So the ideal call order is **pull, then
publish**, and if you cannot, nothing breaks: the delta just stays a bit longer.

---

## 4a. Joining on the core alone — checked, not assumed

The coordinator asked me to find any path that silently assumes the meaning index is present
and make it degrade rather than fail. I read all three call sites. **They already degrade, and
correctly** — every one of them gates on `tools/_index.status()["built"]`, which returns
`{"built": False, ...}` without raising when `content-index/title/` is not there:

| file | what it does with no index |
|---|---|
| `editing/links_pass.py:370` | `have_index = bool(_index.status().get("built")) and voyage.available()` → falls back to title matching for internal links |
| `research/ownpage.py:50` | returns `(None, NO_INDEX_NOTE)` — a plain sentence, not an error |
| `assets/reuse.py:153` | `say("Skipped the reuse check", NO_INDEX)` and carries on |

That is the same behaviour a person with no Voyage key gets today, so it is a degradation
Sutra already understands and already words properly. **No change is needed in any file I do
not own.**

**One thing I did have to fix, in my own file.** `install()` moves files into place one at a
time, so there was a window where `content-index/title/*` had landed and `content-index/body/*`
had not — and in that window `_index.status()` says `built: True` over vectors that are half
absent, which is a crash rather than a degrade. `install()` now moves the two files
`status()` gates on **last** (`INDEX_GATE_FILES`, `_install_order()`). A torn install therefore
reads as "no index", which is the safe answer. There is a test that kills an install half way
and asserts exactly that.

---

## 5. What the UI needs from this — and the one thing it must not print

`Rebuilder` is the thing to wire to the "Go ahead" click:

```python
rb = pack.Rebuilder(client, progress=say, cursor=lambda: sync.last_seen_id())
rb.request("refresh")     # returns "started" or "coalesced" IMMEDIATELY. Never blocks.
```

`request()` returns in microseconds and the work happens on a daemon thread, because the owner
was promised the click finishes in ~2 seconds when the rows land, not when the pack lands.
**Never call `rb.wait()` from the UI** — that is the wait he was told he would not have. It
exists for tests and shutdown.

`progress(stage, done, total, note)` fires with:

| stage | done / total | note |
|---|---|---|
| `start` | 0 / 0 | "updating the shared knowledge pack" |
| `pack` | bytes / 337 MB | the file being packed |
| `verify` | total / total | — |
| `upload` | bytes / 205 MB | "part 3 of 5" |
| `publish` | 0 / 0 | "pointing the workspace at pack 7" |
| `done` | bytes / bytes | "knowledge pack v7 shared (205 MB)" |
| `error` | 0 / 0 | a sentence a person can act on |

A quiet line, never a modal and never a spinner that blocks. **Do not print "about a minute"**
— see §1. Print the stage.

An `error` stage is not a failed refresh. The rows already reached every teammate; only the
pack is behind. Word it that way.

### The joining side, and this is the part that changed

```python
j = pack.join(client, progress=say)     # returns once the CORE is in
# j["ready"] is True. The person can pick an idea and write. Let them.
# j["index_pending"] is True and j["index_thread"] is the daemon fetching the other half.
```

`join()` installs the 33.6 MB core and comes back. **Show the workspace at that point** — do
not hold the join screen open for the 171 MB. `index=` controls it: `"background"` (default),
`"wait"` for a script, `"skip"` if the caller will do it. `pack.fetch_index(client)` is public,
repeatable and resumable, so a Retry button is one call.

`pack.index_ready(kroot)` says whether the meaning index has landed — deliberately the same
two-file test `tools/_index.status()` uses, not a second one. Use it if you want to grey out a
"search my pages" affordance; nothing needs it to avoid a crash (section 4a).

Progress from a join: `download` (real bytes of the real total, hundreds of updates — draw the
bar off these), then `install`, then, for the background half, either nothing or one
`index-error` line. **A failed index fetch is not a failed join.** It is reported as a quiet
line and never raised into the app, because the teammate is already working.

---

## 6. Two decisions I made rather than asking

**The pack is stored in parts, not as one `pack/<version>.zip`.** Supabase caps a single
stored object at **50 MB on the Free plan**, and the real pack is 205 MB, so the object the
plan describes cannot exist on the plan this design is built around. It is still ONE
deterministic zip with ONE sha256 — that does not change — but its bytes live as
`pack/<v>.zip.000 … .004`, joined back on the way down, with `pack/<v>.zip.sha256` beside them
carrying the checksum and the part count. The sidecar is written LAST, so a half-finished
upload can never be mistaken for a pack. Part size adapts to whatever `file_size_limit` the
bucket reports, and falls back to 40 MB.

> **Please verify this against the real project**, since I have no credentials: `GET
> /storage/v1/bucket` returns `file_size_limit` for the `knowledge` bucket. If it comes back
> null or large, nothing needs changing — the code already reads it and sizes parts to it.

### The storage path is built against a documented policy shape, not a measured one

Nothing here has run against a live bucket — there is no Supabase access token on this
machine, so `schema.sql`'s storage block has never executed and its four `storage.objects`
policies are unproved. That block is also wrapped in an exception handler, so a project can
finish setup with nine good tables and **no bucket at all**, and `verify()` is what is meant to
catch it.

So every storage WRITE in `pack.py` goes through one function, `_storage_write()`, and a 400 /
401 / 403 — above all `new row violates row-level security policy`, which is byte for byte what
both a missing bucket and a missing insert policy return — is raised as `WorkspaceNotSetUp`
with a message that names the setup script, says the pack every teammate already has is
untouched, and quotes what Supabase said. `BucketMissing` is a subclass, so one handler catches
both. The point is that nobody reads that sentence and starts looking for a bug in `pack.py`:
there is no bug in `pack.py` that can produce it.

**Two generations are kept per half, not one.** The plan says remove the previous pack once the
new one is verified. Doing that literally reintroduces the race the same paragraph warns about:
a teammate who read `pack_version` two seconds ago is downloading a pack we are about to delete.
So `publish()` of version N deletes version **N-2**, of that half. Cost: one extra object in a
1 GB bucket. `PACK_KEEP_GENERATIONS` is the constant.

**Storage, with the split and two generations:** 2 × 33.6 MB core + 2 × 171.5 MB index =
**410 MB** against the free 1 GB. Comfortable, and it does not grow with the number of
refreshes.

---

## 7. What is left on the table, and what stays unbuilt

**Done:** the split, which was the recommendation here and is now section 1a.

**The next honest win, if anyone wants it.** The index stores float32; float16 would halve
171 MB with no measurable recall loss on cosine similarity. That is the indexer's format
(`tools/_index.py` / `build_page_index.py`), not mine, and it would need the index rebuilt
once. Nobody has asked, and the split already removed the index from the common path, so this
is now a storage saving rather than a speed one.

**What I did NOT do, deliberately.** `content_sha256` in the manifest is a version-independent
hash of the knowledge itself, so it is now technically possible to notice that a CORE rebuild
produced identical content and skip its upload too. **I did not wire that up, and it should
stay unbuilt.** It is one short step from there to "only rebuild when it has moved enough",
which is exactly the drift the owner rejected — and unlike the index case, the core genuinely
changes on every refresh, so the branch would earn nothing and cost the clarity of a rule with
no exceptions. If anyone wants it, it needs his word first, not ours.

---

## 8. Things I did not build, said plainly

- **Resume across app restarts on the upload side.** A publish that dies re-uploads all five
  parts next time. Parts already stored could be skipped by comparing `stat()` sizes; it is
  about ten lines, and nobody has asked for it.
- **Skipping index parts that are already stored.** Same as above, for the 171 MB half, where
  it would matter more.
- **A progress bar for the build phase in bytes-of-final-zip.** `progress("pack", ...)` counts
  raw bytes read, not compressed bytes written, so a bar drawn from it moves smoothly but is
  measuring the input. That is the honest thing to show; just do not label it "uploaded".
- **Anything for the 7-day sleep.** A free project that has been idle a week takes about a
  minute to wake, and `_common.WAKE_TIMEOUT` already exists for it. `pack.py` makes no special
  case; the first call simply takes longer.
