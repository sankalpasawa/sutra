# sutra-ui design QA (child of dayflow/products/design-qa)

`./run.sh` — starts nothing; requires the panel already live at `http://127.0.0.1:8330/`.
It syncs `rules-sutra.json` + `../tests/fixtures/toolruns-fanout.json` into `config.json`
(the product CLI reads exactly one file), then runs the imported product:
`node /Users/asawa/Claude/dayflow/products/design-qa/cli.mjs run config.json`.
Playwright: `run.sh` exports `PLAYWRIGHT` (pinned to this machine's
`sutra-ui-workspace/app/node_modules/playwright/index.js`) unless the caller already
set it — the product itself has no machine-specific fallback.
States: boot, fanout (the captured fan-out rendered by the page's own `turnResponse()`,
drive-app.mjs style: timestamps rebased, demo failure appended, `S.thinkOpen` set),
log-open, chip-open, collapsed-pane (real fold click), dark, light, reduced-motion
(captured UNDER emulated `prefers-reduced-motion: reduce` via state `media`; the rule
scans every element incl. `::before`/`::after` — no element cap — and states its coverage).
Rules: the 41 `:root` token colors (both themes), contrast pairs (`.tname` on `--inset`,
`.gv-ln` states on `--card`), focus-visible on `[data-thinkopen]`/`[data-agentrow]`/`.gv-chip`.
Live-panel determinism: boot freezes background `render()` (QA page only; original kept as
`__qaRender` for the fold states) so transcript tailing cannot wipe the injected turn, and
tokens/contrast are pinned to an offscreen `#qa-probe` rig of the same app-rendered markup.
Output: `runs/<runId>/` — 8 PNGs + `report.md`/`report.json`; exit 0 pass, 1 findings, 2 tool error.

## Known gaps (completeness critic, 2026-08-19)

The 8 states all mount the same pre-opened, full-bodied, governance-free turn,
so this sweep would stay green on a build where the founder's three reported
defects (empty-log affordance, lone streaming caret, unfenced governance leak)
were live. Those three ARE gated — by `qa-shell/shell-check.mjs` lane 1 (L3)
and by test_panel/test_governance (L1+L2) — so the publish gate still catches
them; this sweep does not. Adding defect-exposing states (a preamble-only
streaming turn; an open log with zero runs) is the next improvement to this
config, not to the product.

Repeatability note: verdict-level output is stable across back-to-back runs
(identical rule/state/selector signatures); the reduced-motion finding's DETAIL
text flakes with the live activity poll (`/api/activity`, 2s). Freeze it with a
stubbed activity response in `boot` actions if byte-stable reports matter.
