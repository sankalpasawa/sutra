# Sutra UI

A desktop app for reading and steering the Sutra placement registry — the
departments (domains), charters and placements that ADR-028 files your work
into — with a Claude chat panel alongside it.

> **Bills as your Claude subscription**, the same as the terminal. Never the API.
> The launcher refuses to start if `ANTHROPIC_API_KEY` is set.

The panel is **read-only against the registry**. It reads through
`placement_engine`; it never mints, retires or restructures a domain. That is
enforced by a test (`test_forbidden_calls.py`), not just by convention. The one
exception is explicit: `POST /api/classify` appends a single placement row.

---

## Requirements

| | |
|---|---|
| **macOS** | The installer builds a `.app` bundle (`sips`, `iconutil`, `codesign`, `osascript`). There is no Linux/Windows path yet — the script says so and exits. |
| **Python 3.9+** | Only `fastapi`, `uvicorn`, `websockets` (see `requirements.txt`). |
| **Node 18+** | Only if you want the Electron desktop app. Without it you get a script-based `.app` instead, and the installer tells you so. |
| **`claude` CLI, logged in** | Required for chat. Without it the panel still runs; the provider list reports exactly why chat is unavailable. |

## Install

```bash
git clone https://github.com/tchandrakar/sutra.git
cd sutra/marketplace/plugin/sutra-ui

cd electron && npm install && cd ..   # for the Electron desktop app
./install.sh
```

`npm install` is not optional if you want the desktop app: `electron/node_modules`
is gitignored, so a fresh clone never has it. Skip it and you get the
script-based bundle — the installer prints a note saying which one it installed.

This gives you two things:

- **`/Applications/Sutra.app`** — the desktop app. Always serves `127.0.0.1:8330`.
- **`~/.local/bin/sutra-ui`** — a CLI that serves on a free port (never 8330), so
  the app and a dev server can run at the same time.

```bash
open -a Sutra          # desktop app  -> http://127.0.0.1:8330
sutra-ui               # CLI          -> a free port, opens your browser
sutra-ui --no-open     # serve without opening a browser
./install.sh --uninstall
```

If `~/.local/bin` is not on your `PATH` the installer says so; it does not edit
your shell profile for you.

### Where things live

The runtime is **staged** into `~/Library/Application Support/Sutra` and the app
runs from there — never from your checkout. macOS TCC protects `~/Desktop`,
`~/Documents` and `~/Downloads`, so an app launched from Finder cannot read a
checkout that lives in one of them. Staging outside those folders is why Sutra
needs **no Full Disk Access grant**.

The consequence: after editing the checkout, **re-run `./install.sh`** to pick
the change up.

| Path | What |
|---|---|
| `~/Library/Application Support/Sutra/` | staged runtime + its venv (created by the installer) |
| `~/.sutra-native/user-kit/` | the registry the panel reads (auto-created empty on first run) |
| `~/.sutra-ui/settings.json` | provider + permission mode + workdir |
| `~/.sutra-native/run/sutra-app.log` | why a Finder launch failed |

First run against an empty registry works: it seeds `domains/`, `charters/` and
`placements/` and shows a `T-local` workspace with zero counts. It is not padded
with example data.

## Providers

A provider is offered only when three things hold, checked live on every call:

- `installed` — `shutil.which(<bin>)`, nothing else
- `configured` — its config directory exists
- `adapter` — **this build can actually drive it**

The third is a property of the codebase, not your machine. Today only `claude`
has an adapter: the chat channel speaks Claude's `-p --output-format stream-json`
protocol. Installing the `codex` CLI makes it installed and configured within
seconds, but it still cannot be used here — so it is listed, disabled, with that
exact reason. Adding a provider means adding its id to `ADAPTERS` in
`providers.py` **and** writing the adapter.

## Workspaces (tenants)

The footer control switches workspace. Every request carries `?tenant=`, and the
whole panel re-scopes — departments, charters, placements.

This is a **scope, not an isolation boundary**. All workspaces share one registry
directory, and `placement_engine`'s own `tenant_refs()` docstring says so
explicitly: *"MISROUTING GUARD, not isolation … Do not describe it with the word
isolation."* Treat it as a filter, not a security control.

There is no "create workspace" button because a workspace is not a stored thing —
it is a `tenant_id` observed on a domain or placement, and its root domain is
minted lazily the first time work is placed under it.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `SUTRA_UI_PORT` | free port (CLI) | CLI only — the `.app` is pinned to 8330 and ignores this |
| `SUTRA_UI_WORKDIR` | `~/sutra-ui-workspace` | directory the chat session works in (created if absent) |
| `SUTRA_NATIVE_HOME` | `~/.sutra-native/user-kit` | registry root |
| `SUTRA_REPO_ROOT` | the checkout | where governance-log views read from |
| `SUTRA_APPS_DIR` | `/Applications` | where the `.app` is installed |
| `SUTRA_SKIP_ELECTRON` | `0` | `1` forces the script-based bundle |

**Known limitation:** the governance-log views (`/api/logs/*`) read from
`SUTRA_REPO_ROOT`. Their four sources (`.sutra/`, `.enforcement/`, `holding/`)
live in whichever project Sutra governance actually runs in, which is not
knowable at install time — so those views are empty unless you point
`SUTRA_REPO_ROOT` at that project.

## Tests

```bash
.venv/bin/python -m unittest test_app      # 59 tests — API, tenant scoping, safety invariants
node test_panel.js                         # 32 assertions — panel logic, no browser needed
```

`test_forbidden_calls.py` is a provable negative: it greps `org_api.py` and
`reorg_sim.py` for the engine's mutating calls and fails if any appear. It is
written pytest-style, so `unittest` collects **0** tests from it — run it with
`pytest`, or call its three functions directly.

## Layout

| File | Role |
|---|---|
| `install.sh` | stages the runtime, builds the venv, installs the app + CLI |
| `electron/main.js` | desktop shell — spawns the backend, owns the window, single-instance |
| `app.py` | FastAPI: panel, `/ws/chat`, session + log APIs |
| `org_api.py` | read-only registry API over `placement_engine` |
| `providers.py` | which AI CLIs are actually usable, and the settings file |
| `session_reader.py` | read-only parser for `~/.claude/projects/*.jsonl` |
| `static/panel.html` | the entire UI — no build step, no framework |
