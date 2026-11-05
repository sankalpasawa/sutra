# UI-5 as built: workflow graph and org chart views

Owns `sutra_app/ui/static/js/{graph_view,orgchart_view}.js`, `static/css/sutra-graph.css`, `tests/ui/test_view_graph.py`, this note.
Spec: `docs/design/ui.md` 3.3, 6.1 to 6.3, 7, 9 (X4, X5, X8, X9), 10, 11; S3-web-13, S4-fnodes-10; D75, D80. Sources stay ASCII (escapes for the dots).

## What was built
- `graph_view.js`, one global `GraphView` (also `module.exports`): `create(host, {mode, scope, level, dept, title, onOpen, onSelect, onRetry})` -> `{update, select,
  fit, setView, setLive, destroy}` plus `refresh, fail, noteMessage, markSeen, state, el`. Header (title, pills, live chip, Graph|List, Overview|Detail, This team|All
  teams, Fit), SVG, List view, legend, banner, `aria-live` sentence. `GraphView.helpers` holds the pure parts (narrow, serves, zoom arithmetic, sentence, legend).
- `orgchart_view.js`, one global `OrgChartView`: `create(host, {onOpen, onShow, dept})` -> `{update(chart, changes), selectChange, setLive, refresh, fail, destroy,
  graphView, state, el}`. It is `GraphView` in mode "chart" plus the change log (`ChartMarks.logHtml`), the marks of the picked change and a node card.
- `sutra-graph.css`: `--e-org`, sky, boxes (hot, dim, sel, wnew, focus), List view, 600 px switch, legend, live region, card, change log; tokens only.
- 59 tests in one file, about 20 s: 10 in node (the pure helpers, in the merge gate) and 49 in Chrome (`SUTRA_BROWSER=1`) on UI-0's mount page and fake backend.
  One Chrome and one fake serve the module; each test starts from stage 1 with empty storage and fails on any console error or failed request.
- Mutation pass on a scratch copy: 20 single breakages (toggle logic, zoom clamp, reveal, sentence priority, hover classes, selection, refetch query, reduced motion,
  stored choice, 500 limit, unread, click after a drag, pinch, org chart pick, card, three CSS rules), all caught, none survived. No second round.

## Deviations from the specification
1. Pan and zoom are the pane's own (pointer events, wheel, pinch, one transform on `g.wview`), not `d3.zoom`: same extent 0.25 to 4, same 4 px click distance, same
   first view. UI-0's mount page and Home do not load d3, and X9's "no zoom without d3" becomes moot. The view never touches `d3`.
2. Toggles: the spec lets the view call `GET /api/graph` but gives it no way to hear its own toggle. The pane narrows what it holds (a full graph to an overview, all teams
   to one team) and asks `GET /api/graph?level=&dept=` itself only when the data in hand is too narrow; after that it treats the host's `update()` as "something changed" and
   asks again, so a host fetching at its creation level never undoes the owner's choice. "This team" never shows the root, whoever cut the graph.
3. `onSelect` fires for the owner's click or key, not for `select(id)`. In mode "chart" a click only selects (the card), `onOpen` is the card's Open chat.
4. The card has Show in graph only with `onShow` and Open chat only with `onOpen`: the view cannot know "the graph holds that node" (the ids are the same, D44).
5. Added to the handles (not in 7): `refresh`, `fail`, `noteMessage`, `markSeen`, `state`, `el`, `graphView`, `setLive` on the chart, `onShow`, `onRetry`, `dept`, `title`.
6. The banner button reads "Retry" for a server that does not answer (X8) and "Try again" otherwise (X5). The title is a bare `h3` (J2's `.maphead h3`; `.wtitle` is J2's).

## Decisions
- The first view is 1:1 on the top middle; `fit()` returns to it and gives the position back to the layout (resize follows it until the owner moves).
- A graph over 500 nodes opens as a list with a note unless a view was ever chosen (stored `sutra:graph:<team or all>` `{level, scope, view}`; chart mode stores nothing).
- Hover, focus and the glow are DOM classes only (no repaint, so the focus survives); selection, marks, unread dots and the ring go through `SutraCtx.paint`.
- Sentence priority: a node that now needs the owner (waiting on you, fault), new nodes, other status changes, removed nodes. A toggle is never announced.
- Unread: `noteMessage(session, id)` records the newest id heard of; a node is unread when that is above `localStorage sutra:seen:<session>`; opening a node, or
  `markSeen`, writes the key. Nothing on the wire says what was unread before the page loaded, so dots start empty.

## Known limits
- Verified in Chrome 156 only; touch is tested with synthetic pointer events. Cross links are not routed round boxes (UI-4).
- The stage is J2's `clamp(440px, 64vh, 760px)` high; Home may override `.wgpane .wstage` to fill its column. Nothing here needs the token.
- The tests serve the real static folder; a checkout without `css/j2.css` gets a copy with a stand-in sheet. All 59 pass with the stand-in and with J2's real sheet.

## Follow-ups
- UI-7 and UI-8: on `graph.updated`, `server.resync` and a later hello fetch and call `update(graph)` (coalesce about 150 ms); pass `level` and `scope` that match the
  fetch; `SutraEvents.connect({onState})` -> `setLive`; `chat.message` -> `noteMessage(d.session_id, d.message.id)`; NodePanel writes `sutra:seen:<session>`; pass `onShow`
  to `OrgChartView` ("Show in graph" = switch pane and `select(id)`); `select(id)` from "See it on the graph"; call `destroy()` when a pane goes.
