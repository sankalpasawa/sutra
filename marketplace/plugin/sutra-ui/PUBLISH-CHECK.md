# PUBLISH-CHECK — the standard way a feature ships into the Sutra Mac app

Every feature published to this app is verified **end-to-end in production** —
the real Electron shell, the real backend, the real sessions — through two
lanes, in this order. Screenshots come second by design: pixels tell you *what*
rendered; only state tells you *why*.

## The two lanes

| Lane | What it is | What it answers | Primary tool |
|---|---|---|---|
| **1 · STATE** ("one-S") | Attach to the running app over CDP (`--remote-debugging-port`), read the page's own global `S`, call its own pure functions (`gvBody`, `gvLog`, `gvAgents`, `turnResponse`), assert on the values | *Why* — the truth the DOM is drawn from | `qa-shell/shell-check.mjs` lane 1 |
| **2 · PIXELS** | Screenshot the same attached session; verify perceptual claims (theme brightness, layout presence) from the saved bytes | *What a human will perceive* | `qa-shell/shell-check.mjs` lane 2 |

Lane 1 is primary because this app makes it unusually strong: **all state lives
in one global `S`** and every renderer is a pure global function — the running
app can testify about itself. Lane 2 is confirmatory; a lane-2 check without a
lane-1 backing is screenshot archaeology.

## The publish gate, in order

```
1. node test_panel.js            # 134 — the DOM contract, in a vm
2. node test_governance.js       # 51  — pure projections vs a real captured fan-out
3. node test_charter_filter.js   # 31  — untouched neighbors stay green
4. pytest (7 files)              # 341 — backend
5. PLAYWRIGHT=<path> bash qa-shell/run.sh   # 13 — BOTH lanes vs the PRODUCTION shell
6. qa/run.sh                     # the productized design-QA sweep (states x rules),
                                 # once the design-qa product lands (in flight)
```

Steps 1–4 are code truth. Step 5 is production truth. Step 6 is design truth.
A feature is publishable when all three kinds agree.

## What `qa-shell/run.sh` does (and why each part exists)

1. **Quiesce + ownership.** Stops any running shell and kills any backend still
   holding 8330 whose parent shell died — attaching to a stale server means
   testing code no app owns. After relaunch it asserts the backend's *parent
   pid is this shell*, not merely that the port answers.
2. **Transient debug mode.** Relaunches with `--remote-debugging-port=9223`
   only for the check. An unauthenticated CDP port lets any local process
   puppet the app, so the app never *stays* in debug mode; the trap restores a
   normal portless launch even on failure.
3. **Both lanes** via `shell-check.mjs`.
4. **Detach without harm.** `browser.close()` on a CDP attachment **kills the
   target app** (observed 2026-08-18 — the founder found the app gone).
   Detach is disconnect-or-exit, never close. The run then *proves* liveness:
   process up, backend answering, before restoring normal mode.

## Writing a lane-1 check

Ask the app, don't look at it:

```js
const state = await page.evaluate(() => ({
  isButton: /<button class="gv-thinkbtn"/.test(
    turnResponse({ uid:"t", streaming:true, response:"", tools:[], toolRuns:[] })),
  leak: gvBody("Answer.\nINPUT: x\nTYPE: task").includes("INPUT:"),
}));
```

That two-line interrogation found, in one live run, that the thinking loader
*was* clickable (the bug was affordance: an empty log renders nothing) and that
unfenced governance blocks leak into bodies — neither visible in a screenshot,
both fixed with the evidence attached.

## Writing a test case — the same pipeline, as the authoring standard

Every new test case — for ANY feature, not just the chat surface — is written
through the same four levels, in this order. A behavior is "tested" when it has
the levels its row demands; skipping a mandatory level is a review-blocking gap.

| Level | Where it lives | Idiom | Mandatory when |
|---|---|---|---|
| **L1 · projection** | `test_governance.js` (or a sibling suite) | extract the REAL shipped function via the `slice()` harness — never a copy — and feed it real captured fixtures from `tests/fixtures/` | the change has any pure logic |
| **L2 · rendered DOM** | `test_panel.js` | the vm sandbox: assert the HTML the real renderer emits — escaping, anchors, bounded growth, state round-trips | always — L1 alone cannot see a correct projection rendered into the wrong place |
| **L3 · production state** | `qa-shell/shell-check.mjs` lane 1 | one interrogation assertion against the RUNNING app's own `S`/functions | the behavior is reachable in the shipped app |
| **L4 · pixels** | `qa-shell` lane 2 / `qa/` states | screenshot + byte-level verification (brightness, diff) | the claim is perceptual (theme, layout, motion) |

Rules that make the levels honest:

- **L1+L2 are the double-test floor** (founder directive, 2026-08-18): the same
  behavior asserted twice, through different failure modes. A bug must be wrong
  the same way twice to survive.
- **Fixtures are captured, never invented.** New wire shapes get captured the
  way `tests/fixtures/toolruns-fanout.json` was (`design/capture-fanout.py`) —
  through the server's own transform.
- **A test that cannot run is not a test.** The async-tail lesson (test 31e):
  the harness must actually await what it asserts; a silently-skipped assertion
  is worse than none.
- **Fix the product, not the test** — unless the test itself is provably stale
  (test 15's `balanceTab`), in which case the correction is documented in the
  commit with the reason.
- **Every fix lands with its levels in the same commit.** The gate order above
  is also the authoring order: write L1 red → green, L2 red → green, then wire
  L3/L4 where mandated.

## Rules of the road

- **Never `browser.close()`** on a `connectOverCDP` session.
- **Never leave the app in debug mode.** Transient by script, always restored.
- **Never trust "port open" as "backend mine".** Assert the pid tree.
- **A screenshot claim needs a byte check.** A file named `light.png` that is
  dark has happened; `shell-check.mjs` measures mean brightness of the saved
  bytes before believing the label.
- **Fixtures over fabrication.** Lane-1 turn objects use the shape of
  `tests/fixtures/toolruns-fanout.json` (captured from a real transcript),
  never invented field names.
