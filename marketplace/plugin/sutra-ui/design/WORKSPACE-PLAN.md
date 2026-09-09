# The team workspace — the agreed build

**written**: 2026-09-10 · **status**: agreed, building · **owner's ruling is quoted where he gave it**

Five people on one team. One person sets up; nobody else builds a knowledge base. His design, not
to be re-argued: **each company brings its OWN Supabase project.** The data lives in the company's
own account and each company gets its own free 500 MB.

---

## 1. What a person actually does

### The creator, once

    Connections tab -> Create workspace
      a "Go to Supabase" button (opens the browser)
      two boxes: Project URL, publishable key (the sb_publishable_ one)
      a Create button
    press Create
      spinner: "Creating your workspace"
      Sutra makes the tables, then uploads the knowledge pack
      a LINK appears with a copy button, and stays in the Connections tab for good

### A teammate, once

    Connections tab -> Join workspace
      paste the link, type a name, press Done
      progress bar while the pack comes down (~5 min)
      done: their Library, ideas and prompts are the team's

### Forever after

Nobody presses sync. Nobody imports anything.

---

## 2. THE OWNER'S RULING ON THE PACK (2026-09-10) — read this before designing anything

I proposed rebuilding the shared knowledge pack only occasionally, and letting it drift between
rebuilds. He rejected it and he was right:

> *"Why can't it happen something like whenever the user clicks on update or something? It gets
> updated for first it gets updated in that zip file and it also simultaneously gets updated in the
> knowledge base of everybody. Like why can't it happen so simply?"*

**So: one click updates BOTH, every time.** No drift, no catching up later, no "occasionally".

The only concession, and it is invisible to him: he does not WAIT for the pack.

    click "Go ahead"
      ~2 seconds   the changes reach every teammate            <- the click finishes here
      ~1 minute    the pack is rebuilt and uploaded, quietly   <- he has already moved on

**One guard only:** two refreshes inside five minutes do not rebuild the pack twice; the second
supersedes the first. That exists so a long catch-up session does not upload the same thing six
times. Nothing else about the pack is deferred.

---

## 3. What lives in Supabase

### The tables

Nine of them, all readable by a person in Supabase's own Table Editor. Nothing encoded, nothing
hidden. He was promised he could open the dashboard and read his own rows.

| Table | Rows | What it holds |
|---|---|---|
| `workspace` | 1 | name, schema_version, pack_version, created_at |
| `members` | ~5 | member_id, name, joined_at, last_seen_at |
| `ideas` | ~1,900 | the asset sheet and which are ticked |
| `prompts` | 0-14 | ONLY the ones somebody edited |
| `competitors` | ~10 | domain, why, added_by |
| `cta_links` | ~50 | the links a close may point at |
| `company` | 1 | brand, domain, one-liner, niche |
| `library` | grows | finished articles |
| `pages` | delta only | page changes SINCE the current pack (see below) |
| `changes` | append-only | the log every client polls |

**`pages` holds a DELTA, never the whole site.** The full 12,318 pages live in the pack. `pages`
carries only what has changed since the pack was built, and is TRIMMED when the pack is rebuilt.
That is what keeps the database under 5 MB against a 500 MB limit, and it is only correct because
of the ruling in section 2: the pack is rebuilt on every click, so the delta is never large.

### The `changes` log, and why a trigger writes it

Every domain table has an `after insert or update or delete` trigger that appends one row to
`changes` (`id bigserial`, `kind`, `key`, `payload jsonb`, `actor`, `at`).

**The trigger is the point.** If the client wrote both the row and the log entry, a client that
crashed between the two would leave a change nobody else ever hears about, and the log and the
tables would disagree for ever. A database trigger cannot be forgotten, cannot be skipped by an old
build of Sutra, and cannot be got around by editing the app.

A client keeps `last_seen_id` and asks for `id > last_seen_id`. That is the whole sync protocol.
Deletions arrive as ordinary log rows, so "40 pages are gone" needs no special path.

### The file cupboard

One bucket, `knowledge`. One object per pack version: `pack/<version>.zip` (~100 MB zipped from
~326 MB raw: the site catalogue, every page's text, the meaning index, the brand pack).

---

## 4. Creating the tables — the hard part, and the evidence

**The SQL is one fixed script shipped inside Sutra.** The same bytes every time. No model writes
it, nothing is decided at runtime. It runs in ONE transaction, so either every table exists or none
does; every statement is `create ... if not exists`, so a retry after a dropped wifi is harmless;
and afterwards Sutra READS THE TABLE LIST BACK and only reports success once it has seen every
table it expected. Never report success from "the request did not error".

### Measured on his real project, 2026-09-09, before any of this was designed

- `db.<ref>.supabase.co` resolves to **IPv6 only** (`2406:da18:…`, AWS Mumbai). His Mac has **no
  IPv6 address at all**, so a direct Postgres connection can never work from it. Most Indian home
  broadband is the same.
- The IPv4 poolers answer but reject the login for a fresh project.
- So **the database password route is a dead end** and must not be built. This was found by testing
  against a real project inside ten minutes, which is the entire reason we tested against one.

### And the storage bucket cannot be made at runtime either (measured 2026-09-10)

    POST /storage/v1/bucket  with the publishable key
      -> 400 {"statusCode":"403","error":"Unauthorized",
              "message":"new row violates row-level security policy"}

So the `knowledge` bucket is created by the SAME setup SQL, in the same transaction as the tables
(`storage.buckets` is an ordinary Postgres table), together with RLS policies on `storage.objects`
for select/insert/update/delete scoped to `bucket_id = 'knowledge'`. Setup is the only moment we
hold admin rights, so anything needing them happens there or not at all.

`verify()` therefore checks the BUCKET as well as the nine tables. A workspace with tables and no
bucket is a workspace nobody can ever join, and reporting that as success is exactly the failure
section 10 exists to stop.

Also measured, so nobody adds a compatibility shim for it: the new `sb_publishable_…` format and
the legacy anon JWT behave identically on both REST and Storage. Use the new format.

### Therefore, two routes over plain HTTPS, and BOTH ship

1. **Seamless.** The person pastes a Supabase **personal access token** (`sbp_…`). Sutra POSTs the
   SQL to `https://api.supabase.com/v1/projects/{ref}/database/query`. **The token is used once and
   thrown away — never written to disk, never in the link.**
2. **Fallback.** Sutra shows the SQL with a copy button and a link to the project's SQL Editor. The
   person pastes it and presses Run. Thirty seconds, no secret anywhere.

If route 1 fails for any reason, route 2 is offered automatically with the reason shown. A person
must never be stuck.

### Schema versioning is not optional

`workspace.schema_version` is written at creation. Every later Sutra compares its own version and
applies the missing migration steps in order. Without this, every future change breaks every
existing workspace. The migration list is a plain ordered list of SQL steps in the same file as the
create script.

---

## 5. Credentials, and which key is which

Measured from his real project. Getting this wrong is the whole security story.

| Thing | What it does | Where it lives |
|---|---|---|
| Project URL | public address | `connections.json`, and IN the share link |
| `sb_publishable_…` | read + write rows, bounded by RLS | `connections.json`, and IN the share link |
| `sb_secret_…` / service_role JWT | admin, bypasses RLS | **NEVER asked for, NEVER stored, NEVER in the link** |
| personal access token `sbp_…` | account admin | **used once at creation, then discarded** |
| database password | direct Postgres | **not used at all** (section 4) |

**The share link is `URL + publishable key + workspace id`, base64'd into one string with a copy
button.** Nothing in it can create a table, drop a table, or read another project.

Row Level Security is ON for every table. The publishable key may read and write rows of THIS
workspace and nothing else. That is a database rule, so it holds even if somebody edits the app.

`connections.json` stays 0600, the way `store.save_connections` already does it.

### Everyone can do everything

His words: *"everyone can change the prompts, let's give that capability to everyone for now."* No
owner role, no permission tiers. Every write carries `actor`, so the Library and the log can say
"Ravi, 21:40". The Prompts tab's existing Reset button is the undo.

---

## 6. The local copy is still the truth Sutra reads

**Supabase is not where Sutra reads from.** Every person keeps a full local knowledge base, exactly
as today. That is why it is fast, and why a plane or a Supabase outage does not stop work: changes
queue locally and go up when the network returns.

    local knowledge  <-- reads -- Sutra
           ^
           |  a change goes up, comes back down through the log, lands locally

## 7. What NEVER syncs

- the raw page cache (4.1 GB of downloaded HTML)
- drafts in progress
- run folders and working files

Only finished, agreed things go up.

## 8. The three defaults he approved

- a teammate's finished article goes **straight into the shared Library**
- a refresh that drops 40 pages **drops them for everyone**
- two people editing one prompt: **last save wins**

## 8b. The pack, as MEASURED (2026-09-10) — the plan's estimates were wrong

Built from a clone of his real install. The estimates in sections 1 and 3 were mine and they were
guesses; these are measurements and they win.

| | the plan said | measured |
|---|---|---|
| raw | ~326 MB | **337.2 MB**, 533 files |
| zipped | ~100 MB | **205.0 MB** |
| build | — | 8.0 s |

84% of the pack is `content-index/`: float32 vectors that deflate to 0.89 and never will do better.
`brand/` is 0.4 MB, not 3 MB — the 3 MB counted `brand/_work`, builder scratch that does not travel.

**And a blocker the measurement found: Supabase Free caps ONE stored object at 50 MB.** A 205 MB
pack cannot exist as a single object on the plan this whole design rests on. So a pack is stored as
numbered parts with its sha256 in a sidecar written LAST, so a half-finished upload can never be
mistaken for a finished one. The bucket pins `file_size_limit` at 45 MiB at creation, chosen from
both ends: below it the pack's own part arithmetic silently shrinks the parts, above it the
ambiguity between 50×10^6 and 50×2^20 bites on somebody's project and nobody else's.

### The split, and why it does not soften section 2

| half | contents | zipped | rebuilt |
|---|---|---|---|
| **core** | catalogue + page text + brand | **33.6 MB** | **every refresh, always** |
| **index** | the meaning index | 171.5 MB | whenever its content hash differs |

A normal refresh: **2.9 s of CPU and 33.6 MB up** — about 30 s on a 10 Mbps line, 10 s on 40. The
205 MB case happens only when the index itself was rebuilt, which follows a Voyage run the person
has just sat through anyway.

**Neither half may be deferred, and both are pinned by tests**: one publishes twice with nothing
changed and asserts a new core object both times; another appends a single line to the index and
asserts it republishes on the very next call. The index decision is an exact byte comparison with
two answers — no threshold, no window, nothing that could become drift.

A joiner is ready on the core alone (`ready: True`) and the index lands behind them; all three
places the index is used already gate on `_index.status()["built"]` and degrade to title matching,
which is what a person with no Voyage key gets today.

**Two generations of each half are kept, deliberately.** Deleting the previous one the instant the
new one verifies would delete it out from under a teammate five minutes into downloading it.

**The UI prints the STAGE, never a time.** "Part 3 of 5" is honest on any uplink; "about a minute"
is a promise about a line nobody has measured.

## 9. The free tier, measured against his real data

500 MB database against under 5 MB of rows · 1 GB file storage against 410 MB (two generations
of both halves, and it does not grow with the number of refreshes) · 5 GB
egress a month, which is why section 3 sends changes rather than packs. The one gotcha: a free
project sleeps after 7 days idle and the next person waits about a minute. Nothing is lost.

## 10. The bar

Nothing reports success it has not verified. Nothing is deferred that he was told is immediate.
No secret is stored that does not have to be. Every failure says what failed and what to do.
