# UI-2 as built: port of the J2 page

Owns `scripts/port_j2_ui.py`, `sutra_app/ui/pages/{j2_ui.html,j2_ui_render.js,j2_graph_layout.js}`, `static/css/j2.css`,
`static/vendor/{d3.min.js,d3-LICENSE,README.md}`, `tests/ui/test_port_edits.py`, `tests/ui/js/page_render.test.js`, this note.
Spec: `docs/design/ui.md` 5, 10, 11; S3-web-10, -14; D6, D74, D76; `docs/design/j2-sync.md`.

## What was built
- `port_j2_ui.py --j2 <J2> [--root <repo>] [--check] | --e13-json`. The edit table is `Edit(id, old, new, count)`, 17 rows for the 13 edits
  (E6 = E6a+E6b, E13 = E13a-d; E2 is one regex row with count 2). A count that is not met raises `DriftError` naming EVERY drifted row; nothing is
  written. Outputs (7 files): the page, `j2.css` (the `<style>` text, leading newline included), d3 + licence + readme (verbatim), both harnesses.
- Ported from J2 `33aeeda`: all 12 anchors and the four E13 pairs matched their counts on the first run (design line numbers are +2 from the
  Library view on; rows are located by text). The Library "From" column and template source are inside the copied script, untouched by any edit.
- Parity checked: ported harness on the ported page equals J2's own harness on J2's own page for all 21 keys, `priorities` differing only by
  E13; the 7 goldens (E13 applied; none of them holds an E13 word) and `golden-layout.json` match byte for byte as parsed JSON.
- Tests: `test_port_edits.py` 72 (1.5 s; 71 + 1 opt-in), `page_render.test.js` 22 (1.5 s; 21 + 1 opt-in). Opt in with
  `SUTRA_J2_CHECKOUT=<J2>`: a fresh port equals the committed files, and J2's harness output equals the ported one (D84).
- Mutation check, one pass, scratch copy: 17 single-site breakages (E2/E4/E5/E6a/E7/E10/E12/E13 text, count check off, `--check` blind to a missing file
  or returning 0, vendor file dropped, d3 path, ctx order, commit lookup, empty css group), 0 survivors (one died in the port's own count check).

## Deviations from the specification
1. `--root` and `--e13-json` are extra flags: tests write into a scratch root; `page_render.test.js` reads `E13_WORDS` through `scripts/py` (no copy).
2. `href='?view=detail'` in S3-web-10 is `href="?view=detail"` in J2 (double quotes); the test pins the real text.
3. The department variant in `page_render.test.js` runs the harness copy in this process with a `vm.createContext` hook (boot block, `location`,
   `CustomEvent`, a recording `fetch`, `closest()` on elements) instead of a second stub: the harness output code is not copied.

## Decisions
- All counts are checked on J2's original text before any edit is applied, so one run lists all drift; `--check` also builds first, so drift beats "differs".
- The port only reads J2 (`git rev-parse --short` for the commit shown; "unknown" without git). A test makes the J2 folder read-only and ports.
- `tests/ui/test_port_edits.py` states every edit a second time (fragment, count, text that must be gone, neighbours pin the position) and runs
  that one table on the committed page AND on the port of a miniature J2; the edit rows in the script cannot vouch for themselves.
- Sources are ASCII (escapes for the arrow and the middle dot).

## Known limits
- The page names files that other packages add: `sutra-graph.css` (UI-5), `sutra-panel.css` (UI-6), `graph_view.js`, `orgchart_view.js` (UI-5),
  `fnode_view.js`, `chat_view.js`, `node_panel.js` (UI-6), `dept_ext.js` (UI-8). A browser shows 404s for them until they merge; the
  browser tests of UI-5 to UI-9 need them anyway. `sutra_events.js`, `graph_layout.js`, `chart_marks.js`, `graph_render.js` exist.
- Sandboxed preview frames: a generated site that uses storage or cookies fails in the preview (S3-web-14, accepted).
- Fonts are not vendored (D74); the page falls back to Arial and Menlo.

## Follow-ups for other packages
- UI-6/UI-8: the page holds `.railhome`, `#to-home`, `#deptchip`, `#pane-graph`, `#pane-orgchart`, `#nodepanel`; `body.archived` rules belong in
  `sutra-panel.css`; `dept_ext.js` reads `SutraCtx.currentTab` (a `?tab=` pane is shown at parse time, before the module scripts).
- Next J2 pull: `scripts/py scripts/port_j2_ui.py --j2 <J2>` then `git diff`, run the three acceptance commands; on drift update the table, never the copy.
- UI-0: the goldens still say `ce2631f` in `MANIFEST.json`; the bytes are the same at `33aeeda`.
