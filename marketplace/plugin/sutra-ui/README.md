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

### Open in a browser, or hand it to an agent

The app's UI is the same web page the backend serves, so it can run in your own
browser with everything the window can do: sign-ins, keys, updates, the folder
picker.

| How | What happens |
|---|---|
| Dock icon, right-click, **Open in Browser** | opens a paired tab on `127.0.0.1:8340` (Beta `8341`) |
| `open -a Sutra --args --browser` | starts with no window and opens the browser tab |
| `open -a Sutra --args --browser --no-open` | no browser; writes a one-time link to `~/Library/Application Support/Sutra/browser-pair-url` (mode 0600) and prints `SUTRA_BROWSER_URL=...` for an agent |
| `SUTRA_DEBUG_PORT=9229` or `--debug-port=9229` | opens a Chrome DevTools Protocol port on `127.0.0.1` so an agent can drive the app window itself. Off by default: while it is open, any program on this Mac can control the app |

Each link works once, for two minutes, and swaps itself for an HttpOnly,
SameSite=Strict cookie. Every request to the browser port needs that cookie;
other sites and other hostnames are refused. Credentials still never reach the
backend: the browser's calls run in the app process, exactly as the window's do.
With a browser tab in use, closing the window does not quit Sutra; quit from the
Dock. Design and threat model: `electron/browser_mode.js`. Tests:
`node electron/test_browser_mode.js`.

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
| `SUTRA_UI_SAFE_PERM_MODES` | `0` | `1` restores the consent gate: `acceptEdits` / `bypassPermissions` clamp to `plan` until acknowledged |
| `SUTRA_UI_ALLOW_UNSAFE_PERM_MODES` | `0` | `1` opens the write-capable modes when the gate above is engaged (no-op otherwise) |
| `SUTRA_UI_ALLOW_EDIT` | `0` | `1` lets the Editor pane SAVE. The `.app` reads `~/.sutra-ui/allow-edit` instead |

### Permission mode: stored vs effective

**Setup → Access and permissions defaults to Full access** (`bypassPermissions`)
and that is what sessions actually start as. All four choices — Read only,
Edits, Auto, Full access — are settable over the API, and a deliberate
narrowing is honoured: choose Read only and every session spawns `plan`.

The panel still reports two values, the stored mode and the one that will
actually run, because they can differ. What makes them differ is now narrowing,
not widening:

| Cause | Effective mode |
|---|---|
| nothing on file | `bypassPermissions` — the shipped default |
| an unreadable/unknown value on file | `plan` — the floor, never the default |
| Shadow autonomy at L0/L1/L2 | `plan` for the worker; the founder's own chats are untouched |
| `SUTRA_UI_SAFE_PERM_MODES=1` | `plan` until acknowledged (see below) |

#### Restoring the consent gate

Before 2026-09-18 the default was `plan` and the write-capable modes were gated
out of band: the server had to be started with
`SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1` before either could be chosen. That gate
answered one threat — something reaching the unauthenticated local port raising
the ceiling without the operator agreeing — and it stopped answering it when the
default itself became `bypassPermissions`, because a process that can rewrite
`~/.sutra-ui/settings.json` to widen the mode can instead delete it and inherit
full access from the default. What it reliably still did was show Full access as
selected while sessions ran `plan`.

It is preserved in full as an **opt-out** for kiosk, demo and shared machines:

```bash
SUTRA_UI_SAFE_PERM_MODES=1 sutra-ui                 # gate back on
SUTRA_UI_SAFE_PERM_MODES=1 SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1 sutra-ui   # ...and pre-authorised
```

With the gate engaged, both original ways through it still work: the env var
above, or clicking through the panel's confirmation (which records an
acknowledgement that `POST /api/settings` only writes when the caller sends the
confirmation phrase).

What is **not** affected by any of this: the origin guard on the unauthenticated
port, `PERMISSION_MODE_FLOOR` (every narrowing path still lands on `plan`), and
the Shadow autonomy ceiling — a worker the founder's autonomy level says may not
write is still capped at `plan`.

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

Python lanes go through `run-tests.sh`. It picks an interpreter that actually
has the app's dependencies — system `python3` on macOS is 3.9 with no `fastapi`,
and lanes that fail on it fail with `ModuleNotFoundError` and
`asyncio.Event() needs a running loop`, which read like product defects and
have been misread as exactly that.

```bash
./run-tests.sh                             # every Python lane
./run-tests.sh test_shadow_criteria.py     # one lane
./run-tests.sh --which                     # which interpreter it resolved
```

**Run it from this directory.** `run-tests.sh` resolves its own location to find
the lane files, but it never `cd`s there — each lane inherits *your* working
directory. Lanes that walk the tree therefore change verdict with where you
stood: `test_shadow_flag.py` passes here and fails from the repo root, where its
"is the accessor the only read path" grep escapes into the whole monorepo and
returns 48 offenders. That is a real cwd bug in the runner, not a flaky test —
until it is fixed, `cd` first and the results are stable.

**One process per file is not incidental.** Under a single pytest process the
Shadow lanes leak an asyncio event loop into one another: `pytest -k shadow`
reports dozens of `RuntimeError: Event loop is closed` and `There is no current
event loop` failures in lanes that pass cleanly on their own. Reach for pytest
to run *one* file, or to get `conftest.py`'s collection rules — not to sweep a
subsystem.

**pytest is not installed by `install.sh` and is not in `requirements.txt`.** It
has to be added deliberately:

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q test_shadow_criteria.py
```

That matters more than one broken command, because `conftest.py` applies **only**
under pytest. It repoints the registry home and the SEO agent's data dir at temp
dirs *before collection*, after a whole-directory run emptied the operator's live
registry twice on 2026-09-11. So on an install that never added pytest, that
guard is not merely unused — it is unreachable, and every lane is relying on the
temp home it binds itself in `setUp()`. `test_shadow_home_guard.py` pins both
layers, but pytest is still the safer invocation for anything you did not write,
and installing it is what makes that choice available.

JS lanes are plain `node` — no runner, no `npm install`, no browser. They load
the real `static/js/*.js` through `vm`, so they test the shipped module, not a
copy.

```bash
node test_panel.js                         # the DOM contract
node test_shadow_home.js                   # Focus > Shadow
```

`test_forbidden_calls.py` is a provable negative: it greps `org_api.py` and
`reorg_sim.py` for the engine's mutating calls and fails if any appear. It is
written pytest-style, so `unittest` collects **0** tests from it — run it with
`pytest`, or call its three functions directly.

`PUBLISH-CHECK.md` is the full release gate. Nothing below runs in CI — the
GitHub workflows build the DMG and cover `marketplace/native`; every lane here
is enforced locally.

### Shadow tests

60 lanes, all at this directory's root: 48 `test_shadow_*.py` and 12
`test_shadow_*.js`. Another ~45 non-Shadow-named files touch Shadow too, most
of them `test_mission_engine.py`, `test_mission_scheduler.py` and the
`test_goal_*` pair that wraps missions.

One command, copy-pasteable from the repo root, no install step beyond
`install.sh`:

```bash
cd marketplace/plugin/sutra-ui && ./run-tests.sh test_shadow_*.py
```

The `cd` is part of the command, not a preamble. The glob is expanded by your
shell against the lane files, so from the repo root it matches nothing and the
shell refuses with `no matches found` before the script ever starts — and the
cwd bug above would flip verdicts even if it did. Already in this directory,
`./run-tests.sh test_shadow_*.py` is the same thing.

```bash
./run-tests.sh test_shadow_*.py            # the 39 Python lanes, one process each

# the 11 JS lanes — run-tests.sh covers Python only
for f in test_shadow_*.js; do
  node "$f" >/dev/null 2>&1 && echo "PASS  $f" || echo "FAIL  $f"
done
```

Run the JS sweep to a **summary, not a `break`**: these lanes are independent, so
stopping at the first red hides the state of every lane after it and leaves you
reading a raw stack trace instead of a result. To see why one failed, run that
one on its own — `node test_shadow_overlay.js` — where it prints its `ok` lines
up to the assertion that went.

#### What a pass looks like

Nothing here runs in CI, so recognising a pass by eye *is* the gate. Both sweeps
answer in the same shape: one line per lane, and an exit code.

**Python.** `run-tests.sh` prints the lane name padded to 34 columns, then `PASS`
and the `Ran N tests` it greps back out of unittest's own summary. A contiguous
stretch of one real run — lanes 4 through 17 of 38, copied unedited, nothing
dropped from inside it:

```
test_shadow_completion_summary.py  PASS  Ran 55 tests
test_shadow_criteria.py            PASS  Ran 38 tests
test_shadow_decider_window.py      PASS  Ran 16 tests
test_shadow_decision_integrity.py  PASS  Ran 13 tests
test_shadow_delegate.py            PASS  Ran 8 tests
test_shadow_drives.py              PASS  Ran 33 tests
test_shadow_early_admit.py         PASS  Ran 10 tests
test_shadow_evidence_prose.py      PASS  Ran 14 tests
test_shadow_feed.py                PASS  Ran 6 tests
test_shadow_flag.py                PASS  Ran 6 tests
test_shadow_floor_choke.py         PASS  Ran 7 tests
test_shadow_founder_says.py        PASS  Ran 11 tests
test_shadow_home_api.py            PASS  Ran 3 tests
test_shadow_home_guard.py          PASS  Ran 4 tests
```

Green means every line reads `PASS` and the script exits `0`. A red lane prints
`FAIL`, then the last 18 lines of its output indented four spaces, and the sweep
keeps going and exits `1` at the end, so one failure never hides the lanes behind
it. Abridged below; the elapsed time differs every run:

```
test_shadow_intervention.py        FAIL
    ERROR: test_the_template_formats_with_a_context_that_has_no_answer (...)
    The substitution dict must not KeyError on an old-shaped context.
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File ".../test_shadow_intervention.py", line 562, in test_the_template_...
        rendered = shadow_runner._DECIDE_PROMPT % {
    KeyError: 'founder_says'
    ----------------------------------------------------------------------
    Ran 61 tests in 0.077s
    FAILED (errors=1)
```

**JS.** Each lane prints `ok <n> <description>` per assertion, then a summary in
one of two wordings — both mean pass:

```
test_shadow_home.js: all green        # home, overlay, now, completion_ui, floor_needs_you, briefing
all shadow RHS tests passed           # rhs, live_refresh, task_chat, task_status, intervention_ui
```

**The summary is not reliably the last line.** The async lanes resolve their `ok`
lines after it — `test_shadow_home.js` prints its summary at line 47 of 53. So
the exit code is the signal and the summary is the confirmation; never judge a
lane by tailing it. That is why the sweep loop above branches on `&&` rather than
grepping for the wording. A green sweep is 11 `PASS` lines and nothing else.

**The suite is not all-green today** (checked 2026-09-15): 35 of 38 Python lanes
and 9 of 11 JS lanes pass. `test_shadow_chat_publication.py`,
`test_shadow_intervention.py`, `test_shadow_signs_e2e.py`,
`test_shadow_briefing.js` and `test_shadow_overlay.js` are red, and all five are
red on a clean checkout of `main` too — they are standing breakage, not something
your working tree did. Re-check that list before trusting it; the point of the
paragraph is that a first run showing five red lanes is the expected state, not
evidence you installed something wrong.

| Lane | What it pins |
|---|---|
| `test_shadow_flag.py` | the off-state — no process, no context read, no state |
| `test_shadow_criteria.py` | `done_when` is optional, and Shadow may only write onto an **empty** set |
| `test_shadow_home_guard.py` | a test can never write the live Shadow home, in two layers |
| `test_shadow_floor_choke.py` | the floors hold on the direct say path |
| `test_shadow_journeys.py` | the designed journeys, end to end |
| `test_shadow_run_limit.py` | "Running at once" end to end — the store clamps and never raises, admission re-reads the cap per decision, the route drains on a raise and refuses to kill on a lower, **every** way a slot frees advances the queue (finish, stop, take over, delete, abandon a goal), and no door reaches `running` past the cap |
| `test_shadow_turn_budget.py` | "Budget per task" end to end — the store clamps in the STORE (not the stepper) and never raises, `create()` stamps the configured number, the snapshot means a change binds new tasks only, a retry takes the current setting while a goal continuation deliberately does not, and `watch` is refused at the route and ignored even when hand-edited into the file |
| `test_shadow_nudge_rate.py` | "Nudges per hour" end to end — the store clamps, refuses junk (a boolean included) and never raises, `0` is a stored value meaning *never unasked* rather than an absent one, the other `presence.json` keys survive a rate write, and a **subprocess** reads back what the route wrote, which is the restart claim asserted rather than clicked |
| `test_shadow_home.js` · `test_shadow_rhs.js` | the two screens, against the real shipped modules |

One lane is **opt-in and deliberately outside the gate**:

```bash
SUTRA_SHADOW_SMOKE=1 ./run-tests.sh test_shadow_smoke_cycle.py
```

It runs the **real `claude` binary** against your **real** `~/.sutra-ui/shadow`.
It costs two Claude turns and leaves a say row and a done row in the live
actions ledger for a mission that actually drove a chat. Without the variable
it skips. Everything else about that flow is covered by `test_shadow_runner.py`
against mocks, which is where you should look first.

The browser lane needs the installed app and is driven over CDP — never run the
script directly, it says so itself:

```bash
cd qa-shell && QA_SCRIPTS="$PWD/shadow-check.mjs" QA_BACKEND=repo bash run.sh
```

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
| `agents_api.py` | the Agents destination's routes, `/api/agents/seo/*` — read a file or kick the engine's loop |
| `seo_agent/` | the SEO Writer engine: loop, store, tools, checks, prompts. Standalone; imports nothing from this app. Its own checks: `seo_agent/tests/run_all.sh` |
| `static/js/17-agents.js` + `static/agents.css` | the Agents screen — agent column, run log, review panel; self-mounts into the shell `SCREENS.agents` returns |
| `modules_api.py` | Org > Modules routes, `/api/modules/*` — the folder `~/.sutra-ui/modules/<id>/` IS the registry; system seeds; sandboxed `/page` for page modules |
| `static/js/18-modules.js` | the Modules screen — list column (Yours / System) + detail; renders only what the API returns. Styles live in `panel.css` (asset-hashed) |

## Agents

**Agents** is the rail destination after Chats. The first agent is the
**SEO Writer**, a port of the SEO workflow (`Backlink gets Automated`, layers 00, 01, 03
and 04) into an agent that works in front of you.

How we build agents, for any job: `design/AGENT-PRINCIPLES.md` (the rules and the
checks, with the code) and `design/AGENT-PRINCIPLES-plain.md` (the same in plain
English). The step-by-step recipe is `design/NEW-AGENT-plan.md` / `NEW-AGENT-plain.md`.

**Setup, once.** Give it the website. It catalogues every page (CMS API, sitemaps, web
archive, crawl, with coverage gates), indexes every page by meaning with Voyage, and
builds the brand pack from the site's own pages: voice, style guide, product facts,
readers, real numbers, customer stories, brand cards, the pages a call to action may
link to, and the one-page writer brief every article follows. You confirm the flagged
rows in the review panel. All of it is visible in Knowledge, including a map of the
pages by meaning.

**Per article.** Topic → research (real keyword numbers with the world check, who ranks,
Google's own answer, the winning pages, evidence cards with verbatim quotes and sources,
the gap check, your own pages found by meaning) → the plan → the draft (planner,
architect by format, writer with its editing passes, internal links laid in by meaning
and judged on real page text, sources numbered). You look at each before the next.

| | |
|---|---|
| Model | the `claude` CLI the chat already drives — **billed to your Claude subscription**, never an API key. `agents_api` hands the agent the binary `providers.py` resolved. Up to three calls run at once. |
| Keyword data | DataForSEO, login + password on the Connections view. Research needs it; paid steps do a balance pre-flight and say when they skipped. |
| Meaning index | Voyage (`voyage-4-large` + `rerank-2.5`, free tier), key on the Connections view. Without it internal links fall back to weaker matching. |
| Memory | standing rules the user states; every step that shapes or writes prose receives them. |
| Data | `~/.sutra-ui/agents/seo/` — chats, runs, artifacts, knowledge (catalogue, page index, brand pack), memory, library. `connections.json` is owner-only. Never inside the bundle. |
| Design | `design/GAME-PLAN-agents.md` · building the next agent: `design/NEW-AGENT-plan.md` |

---

## Shadow

Shadow is the chief of staff inside the app. It watches every live Claude Code
session, rescues chats that drop or stall or error, and runs missions you
delegate. You describe **what you want done**; Shadow drives a separate worker
session toward it and comes back when it is done or when it genuinely needs you.

The division is the whole idea: the worker's job is to do the task, Shadow's job
is to make sure the task actually gets done. A worker can produce a great deal
of activity without making progress, and telling those apart is what Shadow is
for.

One conversation, two views — the overlay card (`static/js/15-shadow-overlay.js`)
and Focus > Shadow (`static/js/16-shadow-home.js`), which tabs into
**Watching / Working / Goals**.

### How you use it

There is no Shadow CLI. You talk to it, in the overlay or in Focus > Shadow, and
say what you want done.

1. **You describe the outcome.** Shadow proposes a mission back — or you ask for
   one directly. Either way it lands in `brief_confirm` and does nothing yet.
2. **Start is your confirm.** Nothing runs until you press it; that press is the
   confirm *and* the admit. Past five running missions the rest queue FIFO.
3. **Shadow drives a separate worker session** toward the objective, turn by
   turn, deciding each turn from what the target actually said. Every turn it
   injects is tagged `[Shadow · mission <id>]`.
4. **It comes back through the needs-you feed** — when the work is done, or when
   it genuinely cannot proceed. A `needs_decision` item is the one that wants you;
   the rest are `info`.
5. **You settle what only you can settle.** A `founder_confirm` check is ticked
   by your explicit action and nothing else — not the transcript, not a verifier,
   not Shadow.

From a mission card: `take_over`, `stop`, `drop`, `start_now`, `retry`,
`confirm_check`, `resume`, `say`, `intervene`, `delete`. Taking over hands the
chat back to you mid-flight; Shadow stops saying and keeps watching.

### On by default

`providers.shadow_enabled()` is the single read path, and it returns true unless
the settings file carries a literal boolean `false`. An absent file, an absent
key and a junk value all mean **on**.

```json
{ "shadow.enabled": false }
```

in `~/.sutra-ui/settings.json`, then relaunch. With it off there is no Shadow
process, no context read and no state: the flag is checked at call time, not at
import time, so turning it dark mid-mission stops the loop at the next check,
and every `/api/shadow/*` route answers `403` — the overlay then renders no DOM
at all rather than an empty shell.

### Goal, mission, watch

| | |
|---|---|
| **Goal** | the durable commitment that one chat reaches one outcome. Outlives its attempts. |
| **Mission** | **one attempt** at that outcome, and the only way Shadow acts at all |
| **Watch** | the observer lane — no saying, it turns error signals into feed items |

`goal_lifecycle.py` is the one place that knows how a goal maps onto its
attempts, so the mission engine keeps owning execution and the goal store keeps
owning persistence; neither learns about the other. A blocked mission is
deliberately **not** terminal — it means "Shadow cannot continue autonomously
right now", never "the chat is dead".

Templates set the turn budget up front, and those numbers are now **defaults,
not ceilings**: `feature` 30, `fix` 20, `research` 15 (read-only), `watch` 0
(never says anything). **Budget per task** on the Shadow settings page
overrides them per kind, anywhere in 1–100 turns, and the clamp is the
server's — a hand-written POST cannot reach 0 or 500 either.

The budget is stamped onto a task when it is created, so a change binds the
**next** task and never re-budgets one already running. `watch` is stated but
not settable: it never speaks, so it never spends a turn. One exception worth
knowing: a goal's *continuation* attempt carries the previous attempt's
ceiling forward rather than re-reading the setting, because a goal's budget is
cumulative across its attempts — `extra_turns` is what moves that one.

At most five missions run at once; the rest queue FIFO.

### Done when

`done_when` is what will count as done, in three tiers:

| Tier | Met by |
|---|---|
| `contains_artifact` | a string that must appear in the chat |
| `verify` | a real check someone can run |
| `founder_confirm` | only you — it **never** auto-passes |

An empty check set evaluates to false, which used to mean a mission with no
criteria could never finish: it ran to `max_turns` and failed as budget
exhausted. Leaving "Done when" blank was never a refusal to be served, so
Shadow now writes the criteria itself — **only onto an empty set**, capped at
six, and only in the `verify` and `founder_confirm` tiers. Your own words can
never be edited, replaced or appended to; a mission that arrived with criteria
does not even carry the request in its prompt.

`contains_artifact` is refused to Shadow deliberately: it is a literal substring
search over the worker's words, so a check describing a *state* could be
satisfied by uttering the sentence rather than doing the thing.

**Observed, not yet decided (run-limit walkthrough, 2026-09-16).** That refusal
plus the Delegate form's own tier leaves no path from the UI to a
`contains_artifact` check: the form writes `founder_confirm`, Shadow may write
`founder_confirm` or `verify`, and no verifier is wired into the runner today,
so `verify` cannot pass either. A task created on the Shadow screen therefore
reaches `done` only when you sign its checks off — otherwise it ends at
`max_turns` or on ping-pong. The tier still arrives through a Shadow `mission`
block proposed in chat, which is how it was exercised. Whether that is the
intended shape, or wants a verifier, is an open product question; nothing has
been built for it.

### What stands between Shadow and an effect

- **Missions are the only way it acts.** One JSON file holds the mutable state,
  and every transition is *also* appended to the missions ledger, so the audit
  trail survives any edit to the store.
- **The ledger is append-only by construction** — `shadow_ledger.py` exposes no
  rewrite. Three JSONL files: instructions, missions, actions.
- **Everything outbound is scrubbed** through `shadow_egress.scrub()`, and every
  turn Shadow injects is tagged `[Shadow · mission <id>]`. That tag is also a
  verification boundary: Shadow's own prompt names the outstanding checks
  verbatim, so without it a transcript check would satisfy itself from Shadow's
  words on the second turn.
- **Three floors are confirm-first and cannot be overridden by anything stored**
  — destructive git ops, external client repos, irreversible external sends.
  They live in code, above the precedence ranking rather than inside it.
- **Precedence**: floors > this session's words > project instructions >
  confirmed standing instructions > taste > history. Instructions land
  **unconfirmed** and are inert until you confirm them.
- Pauses are requests, not failures: a target waiting on permission, or you
  typing in the target chat, pauses rather than pushing through.

### Files

| File | Role |
|---|---|
| `mission_engine.py` | the state machine, the store, and the say → boundary → evaluate loop |
| `shadow_runner.py` | mounts that engine in the app process; the watcher, the decider, delegate spawn |
| `shadow_session.py` | Shadow's own persistent session; loads `SHADOW.md` at boot |
| `shadow_protocol.py` | the fenced blocks a reply may carry — `mission`, `goal`, `chips`, `remember`, `module` |
| `shadow_intervention.py` | one typed question, N typed fields, when a 300-char reason will not do |
| `shadow_feed.py` | the needs-you feed contract — schema, dedupe, append |
| `shadow_egress.py` | outbound scrubbing, the say tag, the tool-gating table |
| `shadow_ledger.py` · `shadow_precedence.py` | append-only memory, and how instructions rank |
| `goal_store.py` · `goal_lifecycle.py` | the goal layer and its binding to missions |
| `SHADOW.md` | **not documentation** — the context injected into Shadow's session: persona, doctrine, precedence, the fenced protocol |

Routes are `/api/shadow/{status,chat,instructions,settings,watches,missions,goals,feed}`,
all `403` when the flag is off. `POST /api/shadow/missions/{mid}/act` carries the
verbs: `take_over`, `stop`, `drop`, `start_now`, `retry`, `confirm_check`,
`resume`, `say`, `intervene`, `delete`.

Running the tests: **Shadow tests** under `## Tests` above — the command, and
**What a pass looks like** for reading the result.
