# UI-4 as built: graph pure core

Owns `sutra_app/ui/static/js/{graph_layout,graph_render,chart_marks}.js`, `tests/ui/js/{graph_layout,graph_render,chart_marks}.test.js`, this note.
Spec: `docs/design/ui.md` 3.3, 6.1, 6.3, 7, 10, 11; S2-models-01 and -03, S3-web-04 and -13, S4-fnodes-10; D75.

## What was built
- Three classic scripts, one global each (`GraphLayout`, `GraphRender`, `ChartMarks`), also `module.exports`; no DOM and no random number (`logHtml` reads the
  viewer's time zone through `Date`, as specified). The sources, and the tests too, stay ASCII: the middle dot and the ellipsis are written as unicode escapes.
- `graph_layout.js`: `validate` (GraphView to `{graph{nodes,links,cross}, warnings}`), `layout` (layered tree, S-curve tree links, cross links with ports, arcs,
  loops), `diff`, plus `forest` (the tree repairs, shared with the renderer) and the vocabulary and sizes.
- `graph_render.js`: `svg`, `outline`, `summary`, `statusLook`, `statusWord`, `kindWord`, `PERSONA`, `chipText`, plus `edgeLook`, `textWidth`, `fit`.
- `chart_marks.js`: `toGraph`, `marks`, `logHtml`.
- Tests: 193 cases (layout 74, render 79, chart 40), about 1.2 s together. They run as a browser loads the files (vm context: one global; `module` null or empty) and feed them seeded garbage (never throws, the
  markup is always well formed XML with no stray text; checked by a small XML reader in the tests). 500 nodes lay out in 8 ms and draw in 15 ms.
- By hand in headless Chrome 156 (scratch pages in /tmp, nothing committed): the five scripts loaded as classic scripts one after the other (no console error, SVG in
  the SVG namespace, a `<b>` label stays text); a two-team graph in dark and light with J2's own tokens and edge CSS, a hover state, and the org chart with all marks.
  Screenshots read: persona line and `Identity . 0 open . 5 closed`, `?` and `!` badges, double ring, dashed loops, `.hot`/`.dim`, dashed `added`, `moved`, ring.
- Mutation check on a scratch copy in /tmp: 2,407 single-token breakages (every comparison, operator, number, string and call of the three sources) and 125
  hand-made ones (a guard deleted, two arguments swapped, a branch returned early, a type widened, a constant changed). Five rounds: 14 survivors of the first round
  became tests or a simpler source (a redundant guard is dead code, so it was removed); the last round: 2,401 and 124 caught, 3 hung or crashed (an endless loop),
  4 equivalent (below).

## Deviations from the specification
1. Layout: the leftmost box starts at x = pad, as the top row at y = pad (read as the first box, not the first slot); width and height end one pad past the last box;
   an empty graph is two pads square. Coordinates are rounded to a tenth of a pixel, so "centred over its children" holds to 0.1.
2. Cross links meet a box at ports 12 px apart and never at the middle (the tree links' place), not all at the middle; an arc's rise is measured between its ports; an
   arc never rises above y = 2 (a same-row link in the top row would leave the picture).
3. Tooltips say `1 call` and `1 token` (the spec's template is `<n> calls`).
4. Line widths are estimated from Arial's advance table (no DOM here), not from a character count, so the standard `Coordination . 1 open . 5 closed` fits 168 px; a
   line that is cut also goes, in full, into the tooltip.
5. `summary().waiting` counts a team and its Identity that wait on the same question once (the spec's example data gives `1 waiting on you`); other nodes count again.
6. More than listed: `layout` nodes keep every field and links carry their end points; `svg` view options `fresh`, `ring`, `uid`, `title`, `action`; classes `.near`,
   `.cur`, `.mk-*`, `.wtag`, `.wedgelab`, `.wring`, `.wcur`, `.wdot`; `data-tone`; `xmlns`; `statusLook` also returns `status`, `badgeFill`, `ring`, `warning`.
7. `data-edge` holds the link kind (`org handoff depends_on speaks_to step`, class `e-<kind>` as in 3.3), not J2's tone (`reads makes fix`), which is `data-tone` and
   the marker class; J2's `svg path[data-edge]` rules apply all the same.

## Decisions
- The default `uid` is a fingerprint of the drawing (FNV-1a over boxes and paths), so the graph and the org chart on one page never share arrowhead or gradient ids.
- `wait_on` is worded `you`, a function's persona or the text sent; none gives `someone`. A node is `st-waiting`, `?` badge, `waiting on Prioritiser`.
- Unknown node kind: a step; unknown status: idle; unknown link kind: a plain blue link; each with a warning from `validate` and drawn the same without one.
- Sibling order relies on `Array.prototype.sort` being stable (ES2019); links are keyed `JSON.stringify([kind, from, to])` (ids that run together cannot collide).
- Two links between one pair of boxes keep their order and never cross; a pair of arcs nests (the first is the outer one).

## Known limits
- The width table is Arial's; a wider font (IBM Plex Sans, if installed) may push a long chip line a few pixels past its box.
- Cross links are not routed round boxes (the spec says so): one that spans two rows may run behind a box. Two nested arcs that both reach the 60 px cap touch at the top.
- Equivalent mutants left (4): the first slot number (`next = 0`: the shift to the pad hides it), `0` or `1` as the answer for tied ports (a stable sort keeps ordered input
  either way), `secs < 10` at exactly 10 (both branches print `10`), `codePointAt` for `charCodeAt` in `textWidth` (a character outside the BMP is wide either way).

## Follow-ups
- UI-5: pass a distinct `uid` per view; "This team" = filter the raw GraphView (nodes by `dept_id`, edges with both ends kept) before `validate`; merge the `warnings` of
  `validate` and `layout` for the pills; `fresh` = `diff().added` for 1.2 s; style the classes of the markup (only J2's `svg path[data-edge]` rules exist): `.wgsvg .wnode .sel
  .hot .dim .near .wnew .cur .mk-add .mk-move .mk-reuse .wedge .loop .wtag .wedgelab .wring .wcur .wtree .woitem .wobtn .wounread .chglog .chgrow .chgreason .chgstatus .chgnone`.
- UI-5: log rows are the click targets (`.chgrow[data-change]`, `role=button`, `tabindex=0`: Enter and Space too). `outline` is the List view and the phone view.
- `tests/ui/test_node_suite.py` (UI-3) already runs every `tests/ui/js/*.test.js`, so the gate runs these three files.
