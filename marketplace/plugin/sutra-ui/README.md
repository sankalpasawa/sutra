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

## Install the desktop app

Three commands. The installer builds `/Applications/Sutra.app` — a real Electron
desktop app, not a browser tab pointed at localhost.

From a clone of this repository:

```bash
cd marketplace/plugin/sutra-ui && ./install.sh
```

```bash
open -a Sutra
```

`install.sh` runs `npm install` in `electron/` for you on first run (it downloads
Electron, ~1–2 min). Earlier versions did not: `electron/node_modules` is gitignored,
so every fresh clone silently fell back to a script bundle that opened a **browser
window**, and people believed they had installed a desktop app when they had not.

If Node is not on `PATH` the installer says so and installs that script-based
fallback instead, naming which one it installed — it never guesses silently.

### Updating

Re-run the installer from an updated checkout. It replaces `/Applications/Sutra.app`
and re-stages the runtime:

```bash
git pull && ./install.sh
```

```bash
./install.sh --uninstall
```

### What you get

| | |
|---|---|
| `/Applications/Sutra.app` | the desktop app, always on `127.0.0.1:8330` |
| `~/.local/bin/sutra-ui` | CLI on a free port, so app and dev server coexist |
| Terminal pane | your own login shell (`$SHELL`), resizable, top-right toggle |
| First run | a one-time screen naming the CLI, workdir and permission mode in force |

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
cd marketplace/plugin/sutra-ui

cd electron && npm install && cd ..   # optional: install.sh does this for you
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
| `~/.sutra-ui/composio.json` | Composio API key + user id + enabled toolkits (owner-only, 0600) |
| `~/.sutra-ui/composio-catalog.json` | mirrored toolkit catalog — derived, safe to delete |
| `~/.sutra-ui/local.json` | local MCP servers, their tags, and the pinned aggregator version |
| `~/.sutra-ui/1mcp/mcp.json` | 1MCP's own config — **derived** from local.json on every change |
| `~/.sutra-ui/mcp-registry.json` | cached MCP Registry page — derived, safe to delete |
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

## Connectors

Two connectors, and the difference that decides which you want is **where the
tool runs**:

| | Hosted — Composio | Local — 1MCP |
|---|---|---|
| Backend | a [tool router](https://docs.composio.dev/docs/sessions-via-mcp) session | `npx @1mcp/agent serve --transport=stdio` |
| Reaches | 1000+ SaaS toolkits on Composio's infrastructure | MCP servers on *this machine* — files, git, browsers, databases |
| Catalog | `ComposioHQ/composio` toolkit list | the open MCP Registry |
| Needs | an API key | Node on PATH |

Both **aggregate**: each is ONE entry in the `--mcp-config` of every turn,
however many services sit behind it (see `app._sutra_mcp_config`). A session
therefore sees at most three MCP servers — `sutra`, `composio`, `local` — no
matter how much is enabled.

### Local connector (1MCP)

`@1mcp/agent` (Apache-2.0) fronts every enabled local server as one stdio
process, so N servers cost one tool namespace instead of N. MetaMCP was the
other candidate and was rejected on shape, not licence: it needs Docker,
Postgres and its own web UI. `1mcp proxy` was rejected too — it requires a
separate long-lived `1mcp serve` to proxy to, and `serve --transport=stdio` has
no such daemon.

Every server carries a **tag**, which is 1MCP's own per-server field, not a UI
label: the screen groups by it and `--filter` narrows on it. Tags come from
Composio's category for the same slug where one exists, so `github` files under
`developer-tools` in **both** connectors; otherwise a keyword heuristic guesses,
says that it guessed, and the tag is editable per server.

The launch command **pins** the aggregator version. An unpinned `npx -y` would
resolve whatever npm calls latest at spawn time, which could swap the process
fronting every local tool between two turns of one session.

Routing Composio *through* the aggregator is a switch on the screen, off by
default — one connector for everything, at the cost of a subprocess in front of
an endpoint that already works. With it on, `_sutra_mcp_config` emits the
aggregator **instead of** the direct Composio entry, never both.

### Hosted connector (Composio)

Enabling a toolkit widens what that one endpoint carries; nothing is installed
locally and no per-service secret is pasted here.

| | |
|---|---|
| Set up | Connectors screen → API key from `dashboard.composio.dev/settings` + a user id |
| Connect an account | the agent does it — the session carries Composio's connection manager and hands you an in-browser auth link the first time it touches an unconnected toolkit |
| Permissions | connector tools are **not** pre-allowed; they run under the session's `--permission-mode` (only `mcp__sutra__*` is cleared by the PreToolUse hook) |
| Workbench | disabled — `connectors/CHARTER.md` RULE 2 forbids Composio's remote code-execution surface |

**What auto-updates, and how** — five different claims, five mechanisms:

| Changes upstream | How this app picks it up | Latency |
|---|---|---|
| New/changed tools inside a toolkit | nothing to update — the endpoint is remote and served by Composio | immediate |
| The toolkit catalog (which apps exist) | conditional `GET` of `ComposioHQ/composio@next:docs/public/data/toolkits-list.json`, which their bot refreshes on a schedule | ≤ 6h |
| Which toolkits are on | session re-provisioned when the (user id, toolkits) fingerprint changes | next turn |
| A local server publishes a new version | nothing to update — every stdio server launches through `npx -y` / `uvx`, which resolve at spawn time | immediate |
| The 1MCP aggregator ships a release | npm `latest` dist-tag, TTL-gated; the pin moves deliberately and the version is recorded | ≤ 24h |

Both checks are TTL-gated and run on screen open **and** on the Electron
shell's existing update tick (`checkUpstreams` in `main.js`) — never as a
boot-time poller, for the reason `updates.py` documents: the CLI serves this
same app to a plain browser, and a fetch on import would make every CLI user
phone GitHub on launch. A copy of the catalog ships in `composio-toolkits.json`,
so the screen works offline on first run.

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
| `SUTRA_UI_ALLOW_UNSAFE_PERM_MODES` | `0` | `1` lets `acceptEdits` / `bypassPermissions` be selected |
| `SUTRA_UI_ALLOW_EDIT` | `0` | `1` lets the Editor pane SAVE. The `.app` reads `~/.sutra-ui/allow-edit` instead |

### Permission mode: stored vs effective

`plan` is the default and the only mode settable over the API. `acceptEdits` and
`bypassPermissions` auto-approve the spawned agent, and the settings endpoint is
unauthenticated by construction (it is a localhost control plane), so they are
gated **out of band** — the server must be started with
`SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1` before either can be chosen.

A mode left on file without that opt-in is **not** honoured: it is clamped to
`plan` at the point of use. The panel therefore reports two values — the stored
one and the one that will actually run — and says so out loud when they differ.
Reading only the stored value is how it came to state "nothing will prompt you
per edit" while sessions were in fact spawning `plan`.

```bash
SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1 sutra-ui
```

### Editing files

The Editor pane opens files under the workdir without any setting. **Saving** is off
by default: it writes to your source, and this panel is unauthenticated by
construction, so the gate is deliberately out of band.

```bash
SUTRA_UI_ALLOW_EDIT=1 sutra-ui
```

The desktop app cannot read your shell environment (a Finder launch inherits
launchd's), so it reads a marker file at launch instead:

```bash
mkdir -p ~/.sutra-ui && touch ~/.sutra-ui/allow-edit
```

Then relaunch Sutra. The marker is read **by the launcher, at start** — a running
server still trusts only its own environment, so nothing reachable over the HTTP
port can turn saving on mid-session. Remove the file and relaunch to turn it off.

### Skills stay current

The panel re-reads `~/.claude` (and the other configured assistants) while it runs,
so installing a plugin or writing a new command shows up without a restart.

`GET /api/skills` returns a `signature` — a hash of the exact payload it is
returning — and the same value as an `ETag`. The panel polls with `If-None-Match`
and gets a bodyless `304` when nothing has changed. It never polls while the window
is hidden, and backs off after failures.

The signature covers the whole payload rather than a count or a timestamp, because
the changes that matter are not all size changes: a provider dropping off `PATH`
flips `runnable` on every entry while the count and the command names stay identical.

### First run

`settings.onboarded` gates a one-time screen naming which CLI the panel drives,
its workdir, the permission mode in force, and what the registry currently holds
— every value read live, nothing illustrative. It lives in the settings file
rather than the browser so clearing site data cannot skip the disclosure.
"Not now" does not persist; the screen returns next launch.

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
