# UI-9 as built: scripted smoke, visual checks, token contrast
Files: `tests/ui/js/contrast.test.js` (node, 16 tests, 0.15 s, runs in the gate through `test_node_suite.py`), `tests/ui/test_browser_smoke.py` (3 browser tests, 12 s),
`tests/ui/test_visual.py` (9 page tests + the audit probe + the matcher test, 42 s; browser tests skip unless `SUTRA_BROWSER=1`).

## What was built
- contrast: parses `j2.css` (dark `:root`, light override) and the three `sutra-*.css` with a small rule parser (flattens `@media`, skips `@keyframes`),
  resolves `var()` with fallbacks and `color-mix(in srgb, ...)`. Every `color` of the new CSS is 4.5:1 on `--bg`, `--panel`, `--panel2` in both sets; a rule with its
  own `color` and `background` keeps 4.5:1 between them; every stroke/border/outline colour is 3:1; J2's own promise (text tokens 4.5, `--edge` and `--e-reads` 3).
- smoke: ONE walk test (a failure names the step): Home start page, a brief, progress, chart_change and task cards, chart mark "added", Detail graph, a
  read-only function node and its Details sections, the Identity chip with its composer, `atom.updated` + `graph.updated` turning the node green in the same
  document, the needs_you card reading "Answered" (to the department's session), Open the team, `/d/web/` offline, Workflow graph and Org chart tabs, Esc.
  After every step: zero console errors and zero failed requests. Second test: the stream is refused, the `○ polling` chip shows and the graph is re-read.
  Third: both pages carry a hash-based CSP and an unhashed inline script is refused and reported (so "zero console errors" does catch a CSP violation).
- visual: 9 pages x 4 themes (light, dark, system with emulated light and dark) x 3 widths = 108 PNGs in `tests/ui/screens/` (ignored). Per file: `data-theme`,
  the emulated scheme, `scrollWidth <= innerWidth` at 900 and 390, no console error, and a page-side audit of every visible text (colour against the opaque
  background or SVG box under it, 4.5:1, 3:1 for large text; gradients and faded elements are counted as skipped, and `measured > 3` is required).

## Deviations and decisions
- The real-app run (`-k real`, `create_app(settings, connector=ScriptedConnector, launcher=FakeLauncher)`) is NOT here: ORCH-7 and ORCH-8 are not merged and none of
  those names exists in `sutra_app/`. Follow-up for whoever merges them: run the walk against that app.
- `--line` is left out of the 3:1 rule: it is J2's hairline between sections (J2's own comment in `j2.css` names `--edge`, `--spoke` and the map strokes as line
  tokens). A `stroke` next to `paint-order` is the halo of a label, not a line.
- KNOWN GAP (real finding, owned by UI-4): in dark, `--muted` (`.tsub`, the second line) on the filed (green) graph box is 4.22:1. `contrast.test.js` and
  `test_visual.py` list it as `KNOWN_GAPS`, accept only that number range (4.0 to 4.5, dark, `tsub` on `st-filed`) and FAIL the day it is fixed or gets worse,
  so the exception cannot go stale. Fix in `graph_render.js`/`sutra-graph.css`: a lighter mix than 14 % or `--ink` for the second line on `st-filed`; then empty `KNOWN_GAPS`.
- The walk uses a copy of the fixtures in `tmp_path` with two changes: `graph.v3` has Identity `filed` (the stock one is `idle`, which is not green) and
  `needs-you["3"]` keeps the question (the fake treats graph stage 3 as answered). Nothing under `fixtures/` was edited.
- The home graph at Detail is 1:1 and the five function boxes (about 900 px) do not fit a 600 px pane, `Fit` included (by design, `homeOf`), so Identity sits off the
  left edge: the walk opens it by focusing the box and pressing Enter (boxes are `role=button`).
- `dept-simple` and `dept-detail-map` audit the whole body (J2's own text with the new chip beside it); the other seven audit the new views only.
- The 108 PNGs were reviewed as nine contact sheets (thumbnails) plus the full-size audit, not one by one; `tests/ui/screens/REVIEW.md` has one line per file. No overlap,
  clipping or broken layout; the Preview pane of J2's page is a white page in dark (the generated site's own colours).
## Known limits and follow-ups
- UI-0 (`cdp.py`): after a real `Escape` key press every following `Input.dispatchMouseEvent mouseMoved` takes 5.1 s to be acknowledged (Chrome 156, seen
  after Enter then Escape); the walk presses Esc once, last, and closes drawers with their button. A mouse-free key sequence is the workaround.
- The matrix is 42 s with one Chrome per page; it never runs in the gate. Dark-theme `data-theme` for `system` is checked against the emulation, not against
  a real OS switch.
- Contrast is measured on computed colours, not on antialiased pixels; text over a gradient is not measured (none was met in the nine pages).
## Mutation self-check (one pass, scratch copy)
11 mutants in a scratch copy, all killed, none needed a new test: swapped luminance weights, swapped `color-mix` weights, a washed-out light `--muted`, text coloured
`--line` in `sutra-shell.css` (contrast, node); polling state never entered, the org chat instead of the team's session for an answer, `'unsafe-inline'` in `script-src`,
`filed` unknown to the look table (smoke); a 1000 px page at 390, `system` never light, the filed box without its green mix (visual, the last one through the stale-gap check).
Equivalent mutants seen and dropped: the first-paint theme script of `home.html` (`themeApply` in `home.js` sets `data-theme` again) and a CSS rule appended
behind a more specific one.
