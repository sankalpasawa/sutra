# HANDOFF-PRICING — the three edits I could not make myself

**written**: 2026-09-10 · **from**: the agent that owns `seo_agent/brand/**` and
`seo_agent/workspace/**` · **to**: whoever owns `agents_api.py`, `static/**`, `test_agents.js`
and `test_agents_api.py`

Two jobs landed in the engine this run:

1. **a missing `pricing.md` reads as the blank form**, everywhere the engine is asked for it,
   instead of raising or coming back as nothing;
2. **`pricing.md` travels on the live pipe**, as a row in a new `brand_inputs` table, so a price
   somebody types reaches their teammates in about a second rather than waiting for the next pack.

The engine half of both is built, tested and green (`bash seo_agent/tests/run_all.sh`). Three edits
are left, and all three are in files I am not allowed to touch this run. They are written out below
verbatim. Nothing here changes a version number.

---

## 1. `agents_api.py` — a missing typed-in file must not 404

**The fault, in the owner's words:** he opened the Knowledge tab and got
`not found (/api/agents/seo/knowledge/brand/pricing.md -> 404)`. His brand pack was built before
`pricing.md` existed, so `features.ensure_pricing()` never ran for it and there is no copy on disk.
The screen offers a door to a file nobody created.

`brand/_common.read()` now stands the blank form in for any typed-in file that is not on disk
(`brand/_common.INPUTS` is the list of them, one entry today). This route reads
`store.knowledge(...)` directly, so it bypasses that and still 404s.

**Replace this** (`agents_api.py`, `api_brand_file`, line ~850):

```python
@router.get("/knowledge/brand/{name}")
def api_brand_file(name: str):
    if not _BRAND_FILE.match(name or ""):
        return _bad("bad name")
    v = store.knowledge("brand/" + name)
    if v is None:
        return _bad("not found", 404)
    return v if isinstance(v, (dict, list)) else {"name": name, "text": v}
```

**with this:**

```python
@router.get("/knowledge/brand/{name}")
def api_brand_file(name: str):
    if not _BRAND_FILE.match(name or ""):
        return _bad("bad name")
    v = store.knowledge("brand/" + name)
    if v is None:
        # A FILE A PERSON TYPES IN IS NEVER A 404. The blank form only reaches disk when the
        # brand-pack builder runs, so a pack built before that form existed has no copy of it,
        # and this screen still offers a door to it (the owner, 2026-09-10). brand/_common.read
        # hands back the blank form for exactly those names, so what a person opens is the form
        # they are being asked to fill in rather than an error. Any other missing name is still
        # a 404, which is the truth for it.
        try:
            from seo_agent.brand import _common as bcm
            if bcm.is_input(name):
                return {"name": name, "text": bcm.read(name)}
        except Exception:  # noqa: BLE001 -- the engine may not be installed yet
            pass
        return _bad("not found", 404)
    return v if isinstance(v, (dict, list)) else {"name": name, "text": v}
```

**What you can rely on:** `bcm.is_input(name)` is true only for the typed-in forms
(`pricing.md` today), and `bcm.read(name)` returns the template text verbatim out of
`prompts/brand/templates/`. Neither raises for an unknown name.

**And the row the screen draws is already right.** `pack.inputs()` now reports a missing form as
`exists: True`, `words: <the form's own length>`, `filled: False`, so `agInputsHtml` draws it as the
same ask it draws an untouched form as ("yours to write", the accent edge, the primary button).
`exists` there means "there is a form to open", which is what the screen branches on. No JS change
is needed for this item.

---

## 2. `agents_api.py` — a saved `pricing.md` has to reach the team

The save route already marks `features.md` for a rebuild. It now also has to push the file, and
both of those live behind one call in the module that owns the file, so the route does not grow a
second thing to remember.

**Replace this** (`agents_api.py`, the tail of `api_save_brand_file`, line ~884):

```python
    if name == "pricing.md":
        try:
            from seo_agent.brand import features
            features.pricing_saved()
        except Exception:  # noqa: BLE001 -- the engine may not be installed
            pass
    return {"ok": True}
```

**with this:**

```python
    # ...and it is also the one brand file that travels on the LIVE pipe. It is small, and a
    # person typed it, so it is a row in `brand_inputs` rather than a wait for the next pack
    # rebuild (design/WORKSPACE-PLAN.md section 3; features.md next door is 13,219 machine-written
    # words and stays in the pack). brand/_common.input_saved does both halves: the stamp above,
    # and the push. It never writes the file (this route already did) and it never raises: a save
    # that reached disk has succeeded, and no workspace, no network, or a workspace a version
    # behind must not turn it into a failed save.
    try:
        from seo_agent.brand import _common as bcm
        if bcm.is_input(name):
            bcm.input_saved(name, data)
    except Exception:  # noqa: BLE001 -- the engine may not be installed
        pass
    return {"ok": True}
```

**What it returns**, if you ever want it on screen: `{"stale": bool, "pushed": bool}`. `stale` is
whether a `features.md` rebuild is now owed (false when nothing has been built yet, which is the
existing behaviour `test_25` pins). `pushed` is whether the change reached the outbox.

**The comment block above the old code stays as it is.** It explains the stamp, and every word of it
is still true.

**This preserves `test_25_saving_pricing_marks_product_facts_for_rebuild` exactly.** With no
workspace configured, `input_saved` marks the stamp and the push fails inside its own try, so the
observable behaviour of the route is unchanged: one stamp file, no model call, a 200 either way.

---

## 3. The Connections tab needs an "update this workspace" button

**This is the one that decides whether job 2 does anything on the owner's real project**, so it is
worth the paragraph.

`brand_inputs` is a new table. His workspace is at `schema_version` 2 and
`create table if not exists` in `schema.sql` does nothing to a database whose tables already exist,
so the table can only ever arrive through `schema.MIGRATIONS`. `schema.migrate()` has existed since
the package shipped and **nothing calls it**. Until something does, his workspace stays on 2, and
`pricing.md` goes on travelling with the pack exactly as it does today.

**What the engine does in the meantime, so nothing is stranded and nothing is silent:**

- `sync.push` asks the workspace's version before it queues a `brand_inputs` row, and **declines
  rather than queueing** when the workspace is behind. This is not caution for its own sake: the
  outbox is a queue, a failing item blocks the ones behind it, and it retries for ever with no
  maximum attempt count. One undeliverable row would sit at the head of it and hold every idea,
  article and prompt edit behind it. `test_workspace_sync` proves the queue keeps flowing, and
  proves it wedges when the guard is removed.
- The decline is recorded: `sync.status()["needs_update"]` is
  `{"kind": "brand_inputs", "have": 2, "needs": 3, "why": "<a sentence>", "at": ...}`, cleared by
  the first push that gets through.
- `schema.verify()` now also returns `behind` (tables a migration adds that this workspace has not
  got yet) and `needs_update` (a bool). A workspace one migration behind is **still `ok: True`**,
  and its `reason` says an update is available and what is not syncing until it is run. That is
  deliberate and it is load-bearing: `migrate()` refuses to migrate a workspace `verify()` has not
  called ready, so counting a not-yet-migrated table as *missing* would report his workspace broken
  and then refuse the one operation that could fix it.
- `schema.ready()` (the cheap poll) also carries `needs_update`.

**The route to add** (`agents_api.py`, beside the other `/workspace/*` routes). It follows
`create`/`confirm`: validate, thread, one job dict the screen polls.

```python
@router.post("/workspace/update")
def api_workspace_update(body: dict = Body(default={})):
    """Bring an existing workspace up to the schema this Sutra expects.

    A workspace made before a change cannot get a new table from the setup script: every statement
    in it is `create ... if not exists`, and the tables are already there. schema.migrate() applies
    only the steps that workspace has not run, in order, each in its own transaction with its own
    version bump, and stops at the first failure. With no personal access token it comes back as
    the paste route carrying JUST those steps, never the whole create script.
    """
    mods = _ws()
    if not _ws_ready(mods, "schema", "client"):
        return _bad("The team workspace is not in this build of Sutra, so nothing was "
                    "attempted. Update Sutra and try again.", 501)
    token = str(body.get("token") or "").strip()
    if token:
        problem = _ws_check_token(token)
        if problem:
            return _bad(problem)

    def work():
        try:
            res = mods["schema"].migrate(token=token or None) or {}
        except Exception as e:  # noqa: BLE001
            _ws_fail("The update could not run.", _ws_scrub(e, token))
            return
        if res.get("route") == "paste":
            _ws_paste_route(res, res.get("reason") or "")
            return
        if res.get("ok"):
            _ws_verify(mods, force=True)          # the cached verdict is now out of date
            _ws_say(phase="done", step=str(res.get("reason") or "Workspace updated."),
                    finished_at=time.time())
        else:
            _ws_fail("The update did not finish.", _ws_scrub(res.get("reason") or "", token))

    _ws_start_job("update")
    if not _spawn("workspace", work):
        return _bad("A workspace job is already running. Wait for it to finish.", 409)
    return {"started": True}
```

**On the screen.** The paste phase already has a renderer (`_ws_paste_route` fills the same `paste`
job dict the create route uses), so the update reuses it: the SQL it hands back is the migration
steps, not the create script. What is new is the prompt to press it. `GET /workspace` already
carries `verify`, so:

- when `verify.needs_update` is true, show one line and one button in the workspace section:
  *"This workspace is on version N. Update it so the prices you type reach your team straight
  away."* / **Update workspace**;
- `sync.needs_update` (add it to the `sync` dict the route returns, it is already in
  `sync.status()`) is the same news arriving from the other direction, after somebody has saved a
  form that could not be sent. Either one is enough to show the button; showing it twice is not.

**Do not** wire the update to run by itself. It needs either a personal access token or a person
pasting into the SQL Editor, and both are choices somebody makes.

---

## 4. What changed in my lane, in one table

| File | What |
|---|---|
| `seo_agent/brand/_common.py` | `INPUTS` (the class, decided once), `is_input`, `blank_form`; `read()` stands the blank form in for a missing typed-in file; `feeds_stale` (the one hop to `features.md`); `input_saved` (the local-save door: mark, then push) |
| `seo_agent/brand/features.py` | `untouched(text, name=PRICING)` now answers for the class, comparing against `cm.blank_form(name)`; `ensure_pricing` writes that same form |
| `seo_agent/brand/pack.py` | `INPUTS` derived from `_common.INPUTS` and `FILES`; `inputs()` reports a missing form as the blank form, `filled: False` |
| `seo_agent/workspace/schema.sql` | the `brand_inputs` table, its trigger, RLS, grant and policy; a fresh workspace is born at version 3; the verdict row counts eleven tables |
| `seo_agent/workspace/schema.py` | `SCHEMA_VERSION = 3`; `BASE_TABLES` / `ADDED_IN` / `TABLES`; migration step 3; `verify()` reports `behind` and `needs_update` and no longer sleeps on a table a workspace is merely behind on; `ready()` carries `needs_update` |
| `seo_agent/workspace/mirror.py` | the `brand_inputs` kind: wire shapes both ways, and a handler that lands through `brand/_common.save` and then `feeds_stale`, refusing any name that is not a typed-in form |
| `seo_agent/workspace/sync.py` | `KIND_NEEDS_VERSION`, `_schema_version` (cached in `sync-state.json`), `_may_push`; `push` returns `None` rather than queueing into a table this workspace has not got; `status()` carries `needs_update` |
| `seo_agent/tests/test_brand.py` · `test_workspace_sync.py` · `test_workspace_core.py` | the checks for all of the above |

**Tests:** `bash seo_agent/tests/run_all.sh` is green (`ALL SUITES PASS`), and
`python -m pytest test_agents_api.py` is green as it stands, before any of the three edits above.
Every new check was mutation-tested: take out the synthesis, the one-hop marking, or the push guard
and a named check goes red.

---

## 5. The two rules I would not want undone

1. **The trigger writes the log.** `brand_inputs` gets the same
   `after insert or update or delete` trigger every other domain table has, and the client only
   ever writes the row. If a client wrote both, a client that died between them would leave a
   change nobody ever hears about.
2. **The chain is one hop.** `pricing.md` marks `features.md`, and stops. Not
   `writing-integrity.md`, not `writer-brief.md`. That is the owner's ruling and both the local
   save and an arriving change obey it, which is why they go through the same function.
