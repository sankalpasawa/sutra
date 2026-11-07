# Getting started with Sutra Pro

Sutra Pro is one chat on top of one global org chart. You write what you need; the chat agent reads the chart and reuses a team,
adds one or rearranges the chart; the team then works as a department of five function nodes (Identity, Adaptation, Priority,
Coordination, Audit) and asks you only what it must. Everything runs on your machine, on `127.0.0.1`, with the Claude and Codex
command-line tools you are already signed in to. No API key is used or stored (D7).

This page takes you from nothing to a first finished request. The other documents: [OPERATIONS.md](OPERATIONS.md) (data folder,
backup, upgrade, logs), [TROUBLESHOOTING.md](TROUBLESHOOTING.md) (one entry per failure) and [ENVIRONMENT.md](ENVIRONMENT.md)
(every variable and setting).

## 1. Prerequisites

| You need | For | Check |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | installing; it fetches Python 3.11 when the machine has none | `uv --version` |
| Claude CLI, signed in with a subscription account (not an API key) | the main model connector | `claude auth status` |
| Codex CLI, signed in with ChatGPT | the second connector, used when Claude is out of quota or unavailable | `codex login status` |
| Google Chrome | Audit screenshots the site at 360 and 1280 px; without it Audit judges from code only. It is also the one browser the app is measured in (D92) | `sutra-pro doctor` |
| Node 20 | development only (the JavaScript tests of the gate); never needed to run the app | `node --version` |

You need at least one of the two CLIs for real work. With neither, the app still starts: use `--offline` (section 3) to look around.
An API-key login is refused on purpose (D34); sign out and sign in with your subscription (`claude auth login`, `codex login`).

## 2. Install

From a checkout of the repository:

```bash
uv venv .venv --python 3.11 && uv pip install --python .venv/bin/python -e ".[dev]"
scripts/run.sh
```

`scripts/run.sh` checks the setup offline, then starts the server and opens the browser. It creates `.venv` itself when there is none.

The apps need no Python and no uv. Download them from the [Sutra Pro releases](https://github.com/sankalpasawa/sutra/releases?q=sutra-pro)
(the release is named by its tag `sutra-pro-vX.Y.Z`; it is never the repository's "Latest" one, D100):

| System | Asset | What to do |
|---|---|---|
| macOS | `Sutra-Pro-arm64.dmg` (Apple silicon) or `Sutra-Pro-x86_64.dmg` (Intel) | open it, drag **Sutra Pro** onto Applications, open it; see [RELEASE-macos.md](RELEASE-macos.md) |
| Windows 10 / 11 | `Sutra-Pro-Setup-x64.exe`, or `Sutra-Pro-win-x64.zip` to unzip anywhere | run it, start **Sutra Pro** from the Start menu; see [RELEASE-windows.md](RELEASE-windows.md) |

Both are unsigned for now (D102), so the first launch needs one extra click: macOS "right-click, Open"; Windows "More info, Run anyway".
An app starts the same server as the command and opens your browser; there is no window of its own. On Windows an icon in the notification area
opens it again or quits it; on a Mac, quit it from the Dock.

From a release as a command (the wheel on the same page; see [RELEASE.md](RELEASE.md)):

```bash
uv tool install https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/sutra_pro-X.Y.Z-py3-none-any.whl
sutra-pro --help
```

Then look at the machine once:

```bash
sutra-pro doctor
```

`doctor` runs fourteen checks (Python, data folder, free space, database, `.env`, both CLIs, `gh`, Chrome, port, second instance,
template library, default browser, locked settings). Each failure carries a one-line fix; [TROUBLESHOOTING.md](TROUBLESHOOTING.md) has
an entry per check. It makes no model call.

## 3. First run

```bash
sutra-pro
```

The server takes the first free port from 8780 to 8799 (`--port N` or `SUTRA_PORT` means exactly that port), prints the address
and opens Chrome on it (or your default browser when Chrome is missing; `--browser default` forces the default). Add `--no-browser`
to open nothing. The first start creates the data folder (`~/.sutra-pro` when installed, `./data` in a checkout; `--data-dir D` or
`SUTRA_DATA_DIR` choose another one) and seeds the template library.

To try it with no model at all, start it offline: `sutra-pro --offline`. The stub connector answers in place of Claude and Codex and
the engine plays its mock mode, so nothing is spent and nothing needs a login. The answers are canned; it is for looking at the screens.

The window you see is Home. Left: the chat with Sutra. Right: the graph, the org chart or Settings, chosen from the menu. On a
phone-width window the same two sides become a Chat | Graph switch.

Until you press **Got it**, Home opens with a welcome card of four readings from this machine: which of Claude and Codex can answer right
now (and, for one that cannot, the one line that fixes it, such as `claude auth login`), where the data lives and how to back it up, what
leaves the machine (prompts go only to your own CLIs, on a subscription login, never an API key, with credential shapes scrubbed) and what
Sutra does by itself and what it asks you. **Got it** is stored in the data folder's database, so another browser does not bring the card
back; **Not now** hides it for this page load only.

## 4. The first message

Type what you need in the box ("Tell Sutra what you need") and press Send, for example: *Build a landing page for a coffee shop*.

1. The chat agent reads the org chart and decides to **reuse** a team that fits, **add** one, or **rearrange** (move a division).
   You see a card saying which, and the change is applied. A merge or a split of divisions is the one step that waits for your
   approval; everything else is applied at once and can be seen in the Org chart's change log.
2. A **task** card appears: the team's work has started. A new team shows up in the Teams list of the menu, and as a box in the graph.
3. The team works. Its Identity function talks to you; the other four function nodes work behind it. You may watch, or leave.
4. When the team needs you, a **needs you** card appears at the top of Home with the team's own question and its option buttons.
5. When it is finished, a **done** card links to the team's page, where the site and the documents are.

If something cannot be done the chat says so in plain words and changes nothing: for instance "I can't reach Claude or Codex right now"
(see [TROUBLESHOOTING.md](TROUBLESHOOTING.md), F1) with a Retry button.

## 5. Reading the screens

### The graph

The Workflow graph shows what is being done and who is doing it. A wide box is a team (a department). A box with five dots on top is
a division of a team. A box with a role name and two counts is one of the five **function nodes**; the counts are its open and
closed work atoms. A small box is a step of a task. The Legend in the pane explains the lines (belongs to, hands over
to, reads, speaks to, revises) and the outlines:

| Outline | Meaning |
|---|---|
| green ring | filed and checked |
| amber ring with `?` | waiting (for you or for another node) |
| red ring with `!` | blocked: the run crashed or could not start |
| double ring | running now |
| dashed | left open (stopped, or done with open items) |
| dotted amber | done, but the checks did not pass |
| hollow | not made yet |

The graph updates by itself as the agents work (it listens to the server's live event stream, and falls back to polling when that is
cut). Header buttons: Graph | List, Overview | Detail, This team | All teams, Fit. Drag to move, scroll or pinch to zoom, Fit to come back.
A very large graph opens as a list; choose Graph to see the picture.

### The org chart

There is **one** chart for the whole app. A request reuses, adds to or rearranges it; it never makes a chart per task. The Org chart pane
draws it and keeps a change log: a plain box was reused, a dashed tinted box was added, a thick outline was moved by the change.

### The drawer

Click any node to open its drawer. Every node has its own chat. A team or division chat is the Identity voice, as in the J2 prototype:
your lines and Identity's lines. A function node's chat is its working log, read-only. The drawer for a function shows:

- **Goal**: the node's standing goal. **Task**: what it does at its stage. **What this function is given**: the context it reads.
- **Work atoms**: the cards of its turns (next part). **Constraints**: what the node may not do. **Hands to**: the next function.
- A usage line: calls, seconds and tokens.

### Atom cards

Each turn of a function is one **work atom**: a goal, constraints, the context it was given, the work, and a declared **verify**. The code, not the
model, runs the checks. A card moves along a short life: open, work, verify, close. Its state word is one of:

| State | Plain meaning |
|---|---|
| OPEN | in progress (it may say "attempt 2" after a failed try) |
| CLOSED | goal reached, and checked |
| VERIFY FAILED | the check did not pass, so nothing is marked done; the reason is kept |
| ABANDONED | stopped on purpose; the reason is kept |
| REFUSED | not started: the goal was too vague or a declared check was missing |

A card lists each check with its result: passed, failed, not run, or deferred (not judged yet in that try). Open an atom to read
the evidence. Every atom, with its cost, is also listed in the Atom log of the console (section 8).

## 6. Answering a team's question

A team asks through its Identity function: a needs-you card on Home, and the same question in the team's chat. Click an option button or
type an answer in the card's box. The answer goes to that team's session only, never to the chat agent. Typical questions are "keep
going or finish as it is", a budget top-up, or a choice between two readings of your brief.

Words the team understands in an answer: `continue`, `ship` (finish as it is), `drop` and `stop` (stop the whole run here). A budget
can be raised with a number ("add 20"). Owner overrides such as `budget +N` need the override key (`J2_OVERRIDE_KEY`; see
[ENVIRONMENT.md](ENVIRONMENT.md)).

To continue finished work, open the team and write in its chat: the next request becomes a follow-up task of the same team that starts
from the old records.

## 7. Stopping

- **A question the team asks you** with a stop choice: answer `stop`; the run ends with the state "left open" and keeps what it has.
- **The whole app**: press Ctrl+C in the terminal that runs `sutra-pro`, or run `sutra-pro stop` from another one. Live teams are
  stopped cleanly (up to about 12 seconds), their work is kept, and the team chat offers to continue next time (F8).
- **Check what runs**: `sutra-pro status` says whether it is running, where and whether it is healthy (exit code 0 when running, 1 when not).
- **Open it again**: `sutra-pro open` opens the browser on the running instance. Starting `sutra-pro` a second time on the same data
  folder does the same instead of starting a second server (D94).

## 8. Where to look next

- The console at `/console` ("Usage and log" in the menu): what the week cost, by team and function; the append-only Atom log; health and a
  diagnostics download. See [OPERATIONS.md](OPERATIONS.md).
- Settings (menu): Appearance, Connectors (test and sign in, per connector) and Engine (the J2 flags; a few are locked and change
  only with `sutra-pro config set`). See [ENVIRONMENT.md](ENVIRONMENT.md).
- Something wrong: run `sutra-pro doctor`, then read [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
