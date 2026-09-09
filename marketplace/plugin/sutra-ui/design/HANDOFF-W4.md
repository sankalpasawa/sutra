# HANDOFF-W4 — the workspace screens

**written**: 2026-09-10 · **covers**: `agents_api.py` (the `/workspace/*` routes),
`static/js/17-agents.js` (the Connections tab's workspace section), `static/agents.css`,
`test_agents.js`, `test_agents_api.py`

Built to `design/WORKSPACE-PLAN.md` sections 1–4 and 10, and to `design/HANDOFF-W1.md` part 2,
which overrode three of the guesses in the original brief. This file is what W4 needed from files
it does not own, what it did outside its lane and why, and the faults it found and left alone.

---

## 1. Routes, as built

Six, not the five HANDOFF-W1 listed. The extra one is `dismiss`, and the reason is below.

| Route | Calls | Notes |
|---|---|---|
| `POST /workspace/create` | `schema.create(url, key, token=…)` | `token` OPTIONAL. Runs on a thread |
| `POST /workspace/confirm` | `schema.confirm(url, key)` | the "I've run it" / "Check again" button |
| `POST /workspace/join` | `link.read_link` → `schema.verify` → `client.save_settings` → `pack.join` | on a thread |
| `GET  /workspace` | `client.configured`, `client.settings`, `sync.status`, `schema.verify` (cached), `client.select("members")` | `?check=1` forces the verify |
| `POST /workspace/dismiss` | nothing | forgets a job that has STOPPED |
| `POST /workspace/leave` | `sync.stop()`, `client.forget()` | |

**Why the routes are threaded rather than pass-through.** HANDOFF-W1 specifies each route as a
thin pass-through returning the dict unchanged. Two of them cannot be: `schema.create` with a
token makes a management-API call and then eleven verify probes, and it is followed by
`pack.publish`, which is minutes and hundreds of megabytes. `pack.join` is the five-minute
download the plan asks for a real progress bar over. So create/confirm/join start a worker and
return `{"started": true}`, and the screen polls `GET /workspace` for one `job` dict.

**What did NOT change is the verdict.** No route decides readiness. `schema.create`/`confirm`
already ran `verify()` themselves, and the worker reads their `ok` and nothing else; `reason` is
carried through verbatim, scrubbed only for secret-shaped substrings. The one place `ok` is
turned into a screen state is `_ws_create_worker`, and it has exactly one branch.

**Why `dismiss` exists.** Cancel on the setup-script screen and Start over on a failure both mean
"forget this job". Doing that only in the browser puts the same screen back on the next four-second
poll. It refuses while a job is still running — throwing away the only record of a worker that is
still making tables is how a half-made workspace ends up on screen as if nothing had happened.

---

## 2. What W4 did in the engine's lane, and should probably move

Three things. All are guarded, none is fatal if it fails, and each is here because the screen
could not do its job without it.

### 2.1 The panel writes the `members` row

`_ws_announce()` in `agents_api.py` does

```python
client.upsert("members", [{"member_id": …, "name": …, "last_seen_at": store.now()}],
              on_conflict="member_id")
```

after a create and after a join. Nothing in `seo_agent/workspace/` writes that table, and
WORKSPACE-PLAN section 3 promises the Connections tab shows **who is in it**, so without this the
member list is always empty. It belongs in the engine — something like `client.join_as(member_id,
name)` or a `members` kind in `mirror.KINDS` — and the panel should call that instead.
`last_seen_at` also wants touching on every poll, which is `sync`'s job rather than a screen's.

### 2.2 The panel keeps `workspace_name` in `connections.json`

`client.save_settings` refuses keys outside `client.SETTINGS`, and there is no setting for the
name. The tab needs one to draw, so the panel writes `workspace_name` into `connections.json`
directly through `store`, beside the engine's six. **Ask:** add `workspace_name` to
`client.SETTINGS` and the panel's `_ws_save_name` / `_ws_name` delete themselves. Note that
`client.forget()` does not clear it today, which is why `POST /workspace/leave` clears it by hand.

The name is also written into the `workspace` row (`client.update("workspace", {"id": …},
{"name": …})`) so joiners see it. That call is non-fatal on purpose: a display name is not worth
failing a create over.

### 2.3 The panel owns the pack rebuilder, and fires it from the catalogue refresh

WORKSPACE-PLAN section 2 is the owner's ruling: one click updates everybody AND the joining copy,
and he does not wait for the pack. `pack.Rebuilder` implements exactly that and **nothing calls
it**. So `agents_api.ws_pack_refresh()` holds one lazily-made `Rebuilder` and
`POST /knowledge/refresh` calls it after a real (non-preview) refresh that did not error.

Two things follow that are worth someone's eye:

* **`sync.status()` has no `pack_state`.** The quiet line at the foot of the screen needs to know
  whether a rebuild is running. The panel derives it from the `Rebuilder`'s own progress callback
  (`build`/`pack`/`verify` → building, `upload`/`publish` → uploading, `done`/`error` → idle) and
  reports it as `sync.pack_state`. **Ask:** expose it from the engine — `pack.Rebuilder.state()`
  or a `pack_state` key on `sync.status()` — and the panel reads it instead of inferring it.
* **A refresh is not the only thing that should rebuild the pack.** Any change that goes up ought
  to, per section 2. Today only the catalogue refresh does, because that is the only "click" the
  panel owns. Whoever wires the rest of the write path should call the same rebuilder.

### 2.4 The panel starts the sync poller

Nothing in the app called `sync.start()`. Section 1's "forever after: nobody presses sync" is not
true without it — a workspace would be set up perfectly and never hear another person's change.
`GET /workspace` now calls `sync.start()` on every read while a workspace is connected (it is
idempotent, so this is an `is_alive()` check), and `POST /workspace/leave` calls `sync.stop()`.

**This is a placement question, not a correctness one.** A background poller arguably belongs in
`app.py`'s startup, not in a GET handler. It is here because `agents_api.py` is the file W4 owns
and because hanging it off the route means it also comes back after an app restart. Move it if
there is a better home.

---

## 3. Asks, in one list

1. `client.SETTINGS` gains `workspace_name`; `client.forget()` clears it. (2.2)
2. A member-join call in the engine — `client.join_as(member_id, name)` or a `members` mirror
   kind — and `last_seen_at` touched by the poller. (2.1)
3. `pack_state` exposed from the engine rather than inferred by the panel. (2.3)
4. A decision on where `sync.start()` belongs. (2.4)
5. `seo_agent/workspace/__init__.py` re-exports only `client`, `link`, `schema`. The panel reaches
   `pack` and `sync` through `importlib.import_module("seo_agent.workspace.pack")`, which works.
   Add them to `__init__` when they are green and the panel's `_ws()` gets simpler.

---

## 4. Found and NOT fixed

### 4.1 `pack.join` does not replay the log; the panel writes the cursor by hand

`pack.join()` returns `replay_from` and installs the files, but nothing applies the changes that
have landed since the pack was built. The join worker therefore does

```python
client.save_settings(last_seen_id=int(got.get("replay_from") or 0))
```

and leaves the catching-up to the poller's first tick. That is correct as far as it goes, but it
means a joiner is briefly behind and nothing on screen says so. A `sync.pull_once()` at the end of
join, inside the progress bar, would close it. Left alone because the boundary arithmetic is
`pack`'s and getting it wrong in either direction is the bug that bites.

### 4.2 `GET /workspace` cannot afford `schema.verify()` on every poll

W1 part 2 specifies the GET as `schema.verify()`. Verify probes ten tables and the bucket — eleven
network calls — and the screen polls this route once a second while a job runs and once every four
otherwise. So the route caches verify for sixty seconds and only refreshes it when the client sends
`?check=1`, which the screen does exactly when the Connections tab is the open tab. Off that tab
the route returns the last known answer, or `null` if there is none. `null` is drawn as "nobody has
been able to ask yet", never as a fault.

### 4.3 The bucket-missing state is drawn, and it is worth a look on real hardware

A project with all ten tables and no `knowledge` bucket has a URL, a key and an id, so everything
that reads settings calls it connected — and nobody can ever join it. The tab draws that as **not
finished**, with `verify()`'s own sentence and the setup script underneath. It has been tested
against a stub, never against a project where the storage policies actually failed to attach. If
HANDOFF-W1's part 1 step 1 comes back `bucket False`, that is the screen to look at first.

### 4.4 The quiet line can be missed

The quiet line appears from `sync.pack_state`, which the screen learns on its next poll. If a
rebuild finishes inside one poll interval the line never appears at all. Nothing is lost and
nothing untrue is shown — it just says less than it could. Deliberate: an optimistic line drawn
from "he pressed Update" would keep claiming a rebuild that never started.
