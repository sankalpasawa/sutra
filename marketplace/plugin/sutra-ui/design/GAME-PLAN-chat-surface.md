# Game plan v2 — live agents in the turn

Status: ready to execute · 2026-08-18 · Depth 5 (exhaustive)
Design: `design/app-preview.html` (full app) · `design/chat-surface-v1.html` (component stages)
Build layer: **L0 / fleet** · repo `sankalpasawa/sutra` (submodule of asawa-holding)
IA: **frozen** — rail, panes, composer, session fold all unchanged.
Coordination: not required (founder approval 2026-08-18).

---

## The correction that produced this plan

The v1 plan assumed the chat-surface design had to be ported. **It is already shipped.**
`05-chat.js` carries the port under a `chat-surface DS port` banner, and it includes:

| Already shipping (v2.102.0) | Where |
|---|---|
| `parseGov()` — the governance grammar | `05-chat.js:741` |
| `gvBody()` — governance stripped from the reply prose | `05-chat.js:767` |
| `gvChipHtml()` — collapsed chip + drop-open panel | `05-chat.js:775` |
| Chip-less bottommost thinking loader (`gv-think`/`gv-pulse`/`gv-tlabel`) | `05-chat.js:832`, `panel.css:1434` |
| Placement / Grounding / Trace rows | `05-chat.js:806-811` |
| Tool rows with lifecycle + duration + caller attribution | `05-chat.js:858-885` |
| Session-level subagents fold, opening a real transcript | `06-render.js:15` |
| `agents_live` badge, fully wired end to end | `app.py:727` → `09-tail.js:9` → `02-helpers.js:700` |

It even carries the two parser hardenings the prototype earned (blank-line fence guard,
backtick-tolerant `OS:` trace) **plus one it did not have**: a trailing unterminated fence is
hidden mid-stream so raw governance never flashes (`05-chat.js:761`).

**Therefore nothing in this plan re-ports any of that.** Three gaps remain.

| # | Gap | Why it matters |
|---|---|---|
| 1 | No **per-turn agent roster** | `agents_live` counts them and the fold lists them per *session*; nothing says what the agents in **this turn** are doing |
| 2 | The thinking loader **cannot be opened** | it says a turn is working, never what it is working on |
| 3 | A live agent **cannot be opened from the turn** | drill-down exists, but only from the session fold |

## The reuse thesis — no new data, no backend work

The roster is a **projection of `t.toolRuns`**, not a new data source. `app.py` already tags
Agent/Task calls with `subagent_type` (`app.py:415-421`), and each run already carries
`{id, name, summary, caller, running, ok, startedAt, endedAt}`. So:

- **no** new socket message, **no** `app.py` change, **no** new `S` state for the roster
- the log is likewise a projection of the same array plus fields the turn already holds
- the drill-down calls `loadAgents()`/`agentsFold()` — existing functions
- the row itself **is a `.trow`** — the tool row component, reused verbatim, so the roster
  inherits its dot states, typography, verdict alignment and reduced-motion rule and adds
  no row CSS of its own
- the open/closed state reuses the `S.govOpen[uid]` pattern from `gvChipHtml()`

Net new CSS for the whole feature: **one container rule, one button reset, and the log block.**

Anything that cannot be derived from data already on the wire is **not built**.

## Binding constraints

1. **Patch, don't rebuild.** `render()` replaces `#panes` wholesale; token frames rewrite only
   `[data-resp]`. The roster lives inside `[data-aturn]`, which `patchTurn()` already replaces
   on tool frames — so it updates for free and never triggers a full render.
2. **`09-tail.js` must stay last** — it ends with `boot()` and `test_panel.js` test 21b asserts it.
   Any new script tag goes *before* it.
3. **No invented numbers.** No progress bar, no percentage, no ETA.
4. **`02-helpers.js` is dirty in another session** — do not touch it.
5. **Every string through `esc()`**; no stream content reaches `innerHTML` unescaped.

---

## The 25 steps

### Phase A — evidence and baseline (1-5)

**1. Record the test baseline.**
Run `node test_panel.js`, `node test_charter_filter.js`, and `.venv/bin/python -m pytest test_app.py test_local.py -q`.
· *Artifact:* `design/baseline.md` with exact counts and any pre-existing failure named.
· *Reuse:* their runners as-is. · *Verify:* counts recorded before any edit; a red test is documented, never masked.

**2. Record the visual baseline.**
Screenshot a real streaming turn with a fan-out from the running panel.
· *Artifact:* `design/baseline-turn.png`. · *Verify:* image shows tool rows + loader as they ship today.

**3. Capture a real fan-out `toolRuns` array.**
From a live session, dump `S.sessions[x].turns[y].toolRuns` for a turn that spawned agents.
· *Artifact:* `tests/fixtures/toolruns-fanout.json` (committed). · *Verify:* the JSON contains ≥2 entries with `name==="Agent"`, and the exact field set is recorded in `design/baseline.md`.
· **This step gates 6-12.** Any roster field with no source in this fixture is cut.

**4. Confirm agent identity.**
Determine, from the fixture, which field names an agent (`caller`, `summary`, or `subagent_type` surfaced through the tool row) and whether it is stable across the run's lifecycle.
· *Artifact:* a one-paragraph finding in `design/baseline.md`. · *Verify:* the chosen field is present on every Agent run in the fixture, at every lifecycle stage.

**5. Confirm the patch path covers the roster.**
Read `patchTurn()` and confirm `[data-aturn]` is replaced on tool frames.
· *Artifact:* finding recorded. · *Verify:* the roster's planned position is inside `[data-aturn]`; if it is not, the plan changes here rather than after implementation.

### Phase B — the agent roster (6-12)

**6. Write the projection function, test-first.**
`gvAgents(t)` in `05-chat.js` beside the other `gv*` functions: maps `t.toolRuns` → agent rows. Pure, no DOM.
· *Artifact:* failing test in `test_governance.js`. · *Reuse:* `t.toolRuns` verbatim; no new state. · *Test:* fixture from step 3 → expected roster. · *Verify:* `node test_governance.js` fails for the right reason before any implementation.

**7. Implement `gvAgents(t)`.**
Filter Agent/Task runs; map lifecycle to `run|done|bad|unk` using the same ternary the tool row already uses (`r.running ? run : r.ok===false ? bad : r.ok===null ? unk : ok`).
· *Reuse:* that exact state ternary — one rule, two surfaces. · *Verify:* step 6's test passes.

**8. Non-fan-out turns produce nothing.**
`gvAgents()` returns `[]` when no Agent runs exist.
· *Test:* a plain tool turn and an empty turn both yield `[]`. · *Verify:* a normal turn's DOM is byte-identical to today's.

**9. Add the roster container CSS — and nothing else.**
An agent row **is a `.trow`**. `panel.css:791-806` already provides the state dot
(`run` spinner / `ok` / `bad` / `unk`), the bold-mono `.tname`, the ellipsised `.tsum`,
the right-aligned uppercase `.tverdict`, and the reduced-motion rule. Verified in the
preview: the roster is visually indistinguishable from the tool rows above it.
So the only new CSS is `.gv-agents` (the nested container) and a 2-line button reset
so a row can be clicked without changing how it looks.
· *Reuse:* the entire `.trow` component, verbatim — zero new row CSS, zero new state colours.
· *Verify:* `grep -c "gv-arow" panel.css` returns 0; the roster and the tool rows render identically.

**10. Render the roster.**
Emit it in `turnResponse()` immediately after `tools`, inside `[data-aturn]`.
· *Reuse:* `esc()` on every field. · *Test:* DOM assertion in `test_panel.js` idiom — fixture turn renders 3 `.gv-arow` with the expected classes. · *Verify:* preview matches `design/app-preview.html`.

**11. Truncate honestly.**
Cap the roster the way the tool row caps at 12, with the same "N earlier …" line.
· *Reuse:* the existing truncation copy pattern. · *Test:* 20 agents → 12 rows + 1 summary row. · *Verify:* no unbounded DOM growth.

**12. Prove no full re-render.**
Stream a fan-out turn; confirm roster updates ride `patchTurn()`.
· *Test:* count `render()` invocations across a simulated tool-frame sequence; must not increase. · *Verify:* no scroll jump, no caret loss — the bug class `01-state.js:575` documents.

### Phase C — the openable log (13-16)

**13. Make the loader a button, test-first.**
`gv-think` becomes `<button>`; `S.thinkOpen[t.uid]` holds state so `render()` preserves it.
· *Artifact:* failing test. · *Reuse:* the `S.govOpen[uid]` pattern from `gvChipHtml()`, verbatim. · *Verify:* test fails first, then passes.

**14. Project the log lines.**
`gvLog(t)` derives lines from `t.toolRuns` + turn state. Nothing invented — every line traces to a real event.
· *Test:* fixture → expected lines; assert no line exists without a source field. · *Verify:* `node test_governance.js` green.

**15. Add log CSS + render it.**
`.gv-log`, `.gv-ln` with `ok`/`bad` variants.
· *Reuse:* `--ok`/`--block`/`--muted`, `--mono`. · *Verify:* opens and closes; closed by default.

**16. Cap the log.**
Bound it; oldest trimmed with a single marker line.
· *Test:* 2000-line turn stays at the cap. · *Verify:* DOM node count flat.

### Phase D — drill-down from the turn (17-19)

**17. Make a roster row open its agent.**
`data-agentopen="<id>"` on the row, handled where the panel's other `data-*` clicks are handled.
· *Reuse:* `loadAgents()` + `S.agentOpen` + `agentsFold()` — no new surface, no new view.
· *Verify:* clicking a row opens that agent in the existing fold.

**18. Degrade honestly when the transcript is not on disk yet.**
A running agent may have no readable transcript; the row must say so rather than open an empty view.
· *Test:* row with no matching transcript → disabled state with a reason. · *Verify:* no empty pane, no invented content.

**19. Keyboard and a11y parity.**
Rows are real buttons: focusable, Enter/Space activate, `aria-label` names the agent and its state.
· *Test:* every row has an accessible name; tab order is source order. · *Verify:* full keyboard traversal.

### Phase E — verification (20-22)

**20. Both themes, both motion settings.**
Dark, light, and `prefers-reduced-motion: reduce`.
· *Artifact:* 3 screenshots in `design/`. · *Verify:* the roster dot stops animating under reduced motion; contrast holds in light.

**21. Full suite green.**
`node test_panel.js`, `node test_governance.js`, `node test_charter_filter.js`, pytest.
· *Verify:* matches or beats the step-1 baseline. Any new failure blocks the ship.

**22. Adversarial review of the diff.**
Independent verification pass over the change — XSS on agent names, unbounded growth, state leaks between turns, render-loop regressions.
· *Artifact:* findings list; each either fixed or explicitly accepted with a reason. · *Verify:* no unaddressed finding.

### Phase F — ship (23-25)

**23. Update the design artifacts to match what shipped.**
Fold any implementation-driven change back into `design/app-preview.html` so the design never lies about the app.
· *Verify:* preview and app render the same structure.

**24. Commit to the submodule.**
One commit in `sankalpasawa/sutra` with the build-layer marker and an honest message naming what was reused. Then bump the submodule pointer in `asawa-holding` as a separate commit.
· *Verify:* `git -C sutra log -1`; parent bump is its own commit.

**25. Verify in the packaged app.**
Rebuild the Electron shell; confirm the roster, the log and the drill-down in the real `Sutra.app`.
· *Artifact:* screenshot from the packaged app. · *Verify:* the feature works outside the dev server.

---

## Test inventory

| Test | File | Covers |
|---|---|---|
| roster projection | `test_governance.js` | steps 6-8, 11 |
| log projection | `test_governance.js` | steps 14, 16 |
| roster DOM | `test_panel.js` | step 10 |
| open-state persistence | `test_panel.js` | step 13 |
| no-full-render | `test_panel.js` | step 12 |
| drill-down + degrade | `test_panel.js` | steps 17-18 |
| a11y names | `test_panel.js` | step 19 |
| existing suites unchanged | `test_panel.js`, `test_app.py` | step 21 |

## Deferred — agreed to-dos, not in these 25 steps

| To-do | Decision | Why deferred |
|---|---|---|
| **Routing UI treatment** | Keep the feature; improve how it is presented | Founder 2026-08-18: "keep the routing, but the UI treatment can be a little better — that is a to-do for later." Today `routingChart()` swaps the whole pane body for an org chart of the departments a session touched. It stays reachable from the composer menu; the visual design of the chart itself is a separate piece of work |
| Chat/Routing as pane tabs | Removed with the pane header | Routing moves into the composer menu; it is a session report, not a chat control |

## Chat-surface chrome decisions (founder, 2026-08-18)

| Change | Rationale | Where the function went |
|---|---|---|
| Pane header removed | It repeated the session name the rail already shows, and carried three non-chat controls | see rows below |
| Activity button removed | Running turns and agents are visible in the turn itself, now including the agent roster | the turn |
| Side chat ignored | Out of scope for this work | unchanged, untouched |
| Composer meta consolidated into one ⋯ menu | One place for everything about the session | `.uchip` trigger + `.upop` popover, both reused |
| ⋯ moved to the **left** of the composer | Founder preference | left of the attach button |
| ⋯ chip carries the session name + live dot | The pane loses all identity when the rail is collapsed (`.app.railcol`) | composer chip |
| Pane fold | Multi-pane must stay usable without a header | left-edge grip (reusing the `.termgrip` idiom) **and** a Fold row in the menu |
| Composer placeholder trimmed to "Message" | The hint was the longest text in the pane; `/` and Shift+Enter are learned by use | — |

## Defects found by making the preview drivable (2026-08-18)

The founder could not click the preview, so it became one: `design/app-preview.html`
now carries a real interaction layer, driven by `drive-preview.mjs` (31 assertions,
all green). Making it clickable found three defects a static mockup could not have
shown — one of them in the shipped app.

| # | Defect | Found by | Status |
|---|---|---|---|
| 1 | **Deleting the pane header breaks the collapsed pane.** `panel.css:690` renders a collapsed pane *entirely* from `.ph` (vertical `<h3>` + `.pfold`). With `.ph` gone, collapsing left a blank 38px strip and no way back | codex consult, before any code | Fixed — `.pane:not(.collapsed) > .ph{display:none}`: the header exists only in the collapsed state, reusing the shipped treatment verbatim |
| 2 | **The pane lost its accessible name.** `display:none` on the only `<h3>` removes it from the accessibility tree, so the pane had no name while expanded | codex consult, `[P1]` | Fixed — the `<section>` carries `aria-label`; a named section stays a navigable region in both states |
| 3 | **`.agents` spills into a collapsed pane — a bug in the app today.** `agentsFold()` (`06-render.js:15`) emits `.agents` as a sibling of `.pb`, but panel.css's collapsed rule hides only `.pb/.pc/.tabs/.src/[data-close]`. Collapse a real session that spawned subagents and the fold wraps one letter per line inside the 38px strip | driving the preview + reading the screenshot | Fixed in the preview (`.pane.collapsed .agents{display:none}`); **the same one-line fix belongs in `panel.css` when this ports** |

Two further consequences, both folded in:

- **Close needed a home.** It was the one header control with nowhere to go once
  the header stopped rendering while expanded — it is now a menu row.
- **`[hidden]` is not safe here.** `[hidden]{display:none}` comes from the UA
  sheet, so any class rule that sets a `display` outranks it. `.aglist` stayed on
  screen when hidden that way. The port must render conditionally, as the app
  already does, rather than toggling the attribute.

## Risk register

| Risk | Mitigation |
|---|---|
| Fixture does not support a planned field | Step 3 gates Phase B; unsupported fields are cut, not faked |
| Roster triggers full re-render | Step 5 verifies the patch anchor; step 12 tests it |
| New script tag breaks `boot()` ordering | No new script — code lands in existing `05-chat.js` beside its siblings |
| Collision with the live session | `02-helpers.js` untouched; commit early |
| Agent name is attacker-controlled | Step 22 checks `esc()` on every projected field |
| Design drifts from implementation | Step 23 folds reality back into the preview |
