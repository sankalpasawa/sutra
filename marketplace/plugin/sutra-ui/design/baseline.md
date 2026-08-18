# Test baseline — before the chat-surface port

Step 1 of `GAME-PLAN-chat-surface.md`. Measured **before any source edit**, so that
every later run can be diffed against it and a regression of mine can never hide
behind someone else's red.

Commit measured: `a3ebacf` (design-only; no source touched).
Working tree at measure time: `static/js/02-helpers.js` modified by a concurrent
session — **not touched by this work**.

## Counts

| Suite | Command | Passed | Failed | State |
|---|---|---|---|---|
| `test_panel.js` | `node test_panel.js` | 80 | **1** | RED at HEAD — stale expectation, see below |
| `test_charter_filter.js` | `node test_charter_filter.js` | 31 | 0 | green |
| python (7 files) | `.venv/bin/python -m pytest test_app.py test_local.py test_activity.py test_composio.py test_forbidden_calls.py test_perm_mode_default.py test_ws_origin_guard.py -q` | 340 | **1** | RED in a full run, green in isolation — race, see below |
| `design/drive-preview.mjs` | `node design/drive-preview.mjs` | 31 | 0 | green (added by this work) |

## The two reds, named

### 1. `test_panel.js` — "15. a corrupt/hostile stored layout degrades to defaults"

**Stale test, correct code.** `loadLayout()` (`static/js/01-state.js:101`) gained a
`balanceTab:"today"` default when the today/week/month balance tabs shipped. Test 15
asserts the whole defaults object with `deepEq`, and its two expected literals were
never updated:

```
expected … railTab:"home"
got      … railTab:"home", balanceTab:"today"
```

Both the code and the test are committed on `main`, so **HEAD is red** — this is not
the concurrent session's uncommitted diff (`balanceTab` appears nowhere in it).

The hardening the test exists to prove is intact and was in fact extended: line 113
validates the new key against an allowlist (`["today","week","month"]`), so hostile
input still degrades to the default.

**Action taken:** the expectation is corrected to include the key, and an assertion is
added for the case the new key introduced and nobody covered — a hostile `balanceTab`
value must be rejected. Fixing this is a precondition for the port: leaving it red
would mean every later `test_panel.js` run is red, and my regressions would be
indistinguishable from this one.

### 2. `test_app.py::test_52_sessions_are_real_files_under_dot_claude_projects`

**Environmental race, no code defect.** The test lists sessions, then asserts the
recorded `size` equals `os.path.getsize()` of the transcript on disk. A live Claude
session appends to its own `.jsonl` between those two reads:

```
AssertionError: 962240 != 966976 : 269c4446-…: size must be the file's, not a guess
```

Run in isolation it passes — verified twice, back to back. **Not touched.** It will
fail intermittently for anyone with a live session while the suite runs; that is a
property of the test, and fixing it is not this work.

## Step 3 — the fan-out fixture

`tests/fixtures/toolruns-fanout.json`, captured from a real transcript
(`~/.claude/projects/-Users-asawa-sutra-ui-workspace/9c14162c-….jsonl`) and pushed
through **app.py's own `_tool_summary()`**, so it is the exact shape the socket
delivers, not a hand-written guess.

Contents: 6 runs — 4 `Agent` (3 finished, 1 still running) and 2 `Bash`. The live
row matters: a roster's hardest state is the one that is still moving.

The field set `01-state.js:904` stores, verbatim:

| Field | Source | Notes |
|---|---|---|
| `id` | `tool_use.id` | the only thing correlating a start with its end |
| `name` | `tool_use.name` | `"Agent"` for a spawned subagent |
| `summary` | `_tool_summary(input)` | see step 4 — this is where identity lives |
| `command` | `_tool_command()` | shell only; **the roster never reads it** |
| `caller` | `tool_use.caller.type` | observed only as `"direct"` |
| `running` / `ok` | lifecycle | `ok===null` means "never reported" |
| `startedAt` / `endedAt` | client clock | `endedAt` absent while running |
| `output` | `tool_result` content | only on end |

## Step 4 — agent identity: already solved server-side

**`caller` is not it.** `app.py:1664` forwards `caller.type`, and the only shape
observed in practice is `"direct"`. The code comment says other shapes are not
guessed at. In the captured fixture every run, agents included, has
`caller:"direct"` — so it identifies nothing.

**`summary` is it.** `_tool_summary()` (`app.py:400`) special-cases Agent/Task
inputs and returns `"<subagent_type>: <description>"`, with a comment naming the
exact bug it fixed: without it, "three parallel agents rendered as three identical
rows". Real captured values:

```
Explore: Audit model PRD pages
Explore: Audit platform block pages
Explore: Audit engineering pages
Explore: Audit hub/products/roadmap/archive
```

**Consequence — the preview was wrong and the design changes here.** The mockup
named rows `placement`, `lens`, `cynefin`, as though each agent had a unique name.
Real fan-outs share a *type* and differ by *description*. So the row maps:

| Slot | Field | Why |
|---|---|---|
| `.tname` | subagent type (`Explore`) | matches the tool row, where `.tname` is the *kind* |
| `.tsum` | description (`Audit model PRD pages`) | the part that tells four parallel agents apart |
| `.tverdict` | elapsed + state | the existing ternary, unchanged |

There is **no `subagent_type` field on the wire** — only the composed `summary`.
So `gvAgents()` splits on the first `": "` and degrades to "whole string is the
kind" when there is no colon. No server change is required: **zero backend work**,
as the reuse thesis claimed.

## Step 5 — the patch path already covers the roster

`patchTurn()` (`01-state.js:638`) replaces the **entire** `[data-aturn]` node with
`turnResponse(t)` on every tool frame. The roster is emitted inside
`turnResponse()`, so it rides the existing patch with no new plumbing.

## Codex consult on the port — findings and what was done

| # | Finding | Resolution |
|---|---|---|
| A `[P2]` | "Rebuilding the roster every tick defeats the patch anchor — gate it behind a signature" | **No change — the premise does not hold here.** `patchTurn()` already replaces the whole `.a` block per tool frame; the roster costs exactly what the tool rows above it already cost. A signature gate would save nothing, because the node is replaced wholesale either way |
| B `[P1]` | "Turn-uid-keyed UI state breaks on reload — state can attach to the wrong turn" | **Downgraded on evidence, and pinned by a test.** `turnUid()` (`02-helpers.js:7`) is a monotonic counter, assigned once and never reused, and the uid-keyed maps are in-memory only — they are not in `saveLayout()`'s persisted `S.ui`. So a reload *forgets* open state; it cannot cross-attach. The rule that keeps it true — never persist a uid-keyed map — is now a test |
| C `[P2]` | "`esc()` is not enough for wire text — control chars, length, spoofed verdicts" | **Fixed.** `gvAgents()` normalizes: control characters stripped, whitespace collapsed, name and summary capped, and the verdict rendered from an allowlist rather than wire text |
| D `[P2]` | "A focused row removed mid-stream dumps focus to `body`" | **Fixed, and it was a pre-existing bug.** `patchTurn()`'s `outerHTML =` already destroys focus on the shipped `.tout` / `.tterm` buttons. Focus is now restored across the patch by stable `data-*` identity, which fixes those too |

## What the implementation changed about the design

Two things the mockup got wrong, corrected in `design/app-preview.html` (step 23):

| Mockup said | The wire actually says |
|---|---|
| Rows named `placement`, `lens`, `cynefin` — one name per agent | There is no per-agent name. `_tool_summary()` composes `"<type>: <description>"`, so a real fan-out is several agents of the **same type**, told apart by description. `.tname` is the type, `.tsum` the description — the same split the tool rows already use |
| Every row opens its transcript | A row is only openable when there is something to join on. The roster's `tool_use` id and the fold's transcript filename are **different keys**, so the join is on description + type — and a running agent often has no transcript yet |

## The roster is a LIVE surface — stated, not hidden

`transcriptTurns()` (`01-state.js:509`) builds replayed turns with `tools` (flat
names) and never `toolRuns`, because a transcript on disk records no lifecycle.
So a session **read from disk shows no roster and no log**. Deriving one from the
flat names would mean inventing a state, a summary and an elapsed time for agents
whose outcome was never written down.

This is not a gap left open by accident — it is the same rule the tool rows
already follow ("a replayed turn shows what ran but never claims a pass/fail it
does not know"), and the session-level subagent fold is what covers replayed
sessions, because it reads the transcripts themselves. Pinned by test 28o.

## Verified in the running app, not just in unit tests

`design/drive-app.mjs` boots the real FastAPI panel, calls **the page's own**
`turnResponse()` with the captured fixture, mounts it in a real `.pane`, and
measures computed style. 30 assertions, all green, across three modes:

| Claim | How it was checked |
|---|---|
| A `<button>` roster row is indistinguishable from a `<div>` tool row | computed font, size, background, border, radius and padding compared **directly against the tool row** rather than against a guessed value |
| The dark and light themes both apply | `[data-theme]` set the way the theme button sets it, then body background measured: `rgb(12,11,9)` → `rgb(250,250,249)` |
| Screenshots are of the theme they claim | mean pixel brightness of the saved PNG sampled over the chat pane: light **239**, dark **41** |
| Reduced motion stops the spinner without losing the state | `animation-name: none`, while the accent ring is still painted |
| A failed step is legible as a failure | `.gv-ln.bad` colour is a real colour, not inherited default |

Artifacts: `design/app-dark.png`, `design/app-light.png`, `design/app-reduced-motion.png`.

## Step 25 — the packaged app: what is and is not verified

The Electron shell does not bundle the panel; it loads it
(`electron/main.js:339`, `win.loadURL(ORIGIN)` against `127.0.0.1:8330`). The
page verified in step 20 — served by the real FastAPI app — **is** the page the
shell renders, so the feature is verified in the app's own runtime.

What is **not** yet true: the installed `/Applications/Sutra.app` stages a *copy*
of the runtime into `~/Library/Application Support/Sutra/plugin/sutra-ui/`, and
that copy is still the old code:

```
grep -c gv-agents ~/Library/Application Support/Sutra/plugin/sutra-ui/static/panel.css   -> 0
grep -c gv-agents  <repo>/static/panel.css                                               -> 1
```

So the packaged app will show the roster after the next `bundle-runtime.sh`
re-stage. That is a release action and was not performed here.

## Step 22 — adversarial review of the diff

An independent pass over the finished diff (`codex exec`, high effort, prompted to
hunt for XSS, unbounded growth, state leaks, wrong matches, render loops and
comments the code does not honour) returned **CHANGES-REQUIRED** with four
findings. All four were real. All four are fixed.

| # | Finding | Why it was real | Fix |
|---|---|---|---|
| 1 `[P1]` | **`agentMatch()` could still open the wrong transcript.** It checked uniqueness among *transcripts* but not among *roster rows* | If two rows in one turn normalise to the same key and only one of them has a transcript on disk, **both** rows resolved to it — and the comment claimed ambiguity resolves to nothing | `agentMatch(list, kind, desc, peers)`: the caller counts rows sharing the key, and more than one refuses to resolve. Test `7j` |
| 2 `[P2]` | **Focus restore searched the whole document.** `document.querySelector(refocus)` could match the same `data-*` value in another turn or pane | Losing focus is bad; silently moving it into a *different* turn is worse | The lookup is now scoped to the replaced `[data-aturn]` block. Test `29f` |
| 3 `[P2]` | **The new log button was not in `PATCH_FOCUS_KEYS`** | The control added by this very change missed the accessibility fix added by the same change | `data-thinkopen` added to the list |
| 4 `[P2]` | **The async drill-down had a race and no error path.** A slow first click could land after a fast second one; a rejected fetch left an unhandled rejection and no feedback | The operator would see a selection they did not ask for, or silence | A click token — only the newest click may apply — plus a `try/catch` that states the failure |

It found no XSS or attribute-injection path surviving `esc()`.

## Re-run contract

Step 21 re-runs every row above and diffs against this file. The port is only
finished when:

- `test_panel.js` is **green** (81+ after the stale fix, plus everything the port adds)
- `test_charter_filter.js` stays **31 / 0**
- python stays **341 / 0** in isolation, with `test_52` the only permitted flake
- `drive-preview.mjs` stays green, since the preview is the design contract

## Final counts (step 21)

| Suite | Before | After | Δ |
|---|---|---|---|
| `test_panel.js` | 80 passed / **1 failed** | **110 / 0** | +30, and the pre-existing red is gone |
| `test_governance.js` | did not exist | **44 / 0** | +44 |
| `test_charter_filter.js` | 31 / 0 | **31 / 0** | untouched |
| python (7 files) | 340 / 1 (race) | **341 / 0** | +1, no flake this run |
| `design/drive-preview.mjs` | 31 / 0 | **31 / 0** | the design contract holds |
| `design/drive-app.mjs` | did not exist | **30 / 0** | +30, against the running app |
| **Total** | **482** | **566** | **+84 assertions** |

Every suite is green. No test was deleted, skipped or loosened to get there; the
one expectation that changed (`test 15`) was stale against shipped code, and the
change is documented above with the reason.
