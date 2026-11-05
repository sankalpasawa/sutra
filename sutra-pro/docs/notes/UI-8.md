# UI-8 as built: department page glue

Owns `sutra_app/ui/static/js/dept_ext.js`, `tests/ui/test_dept_page.py`, this note. Spec: `docs/design/ui.md` 5 (E6, E12), 6.7, 7, 9, 10;
S3-web-10; UI-D10. The source is ASCII (escapes for the middle dot).

## What was built
- `dept_ext.js`, one global `DeptExt` (also `module.exports`; in node it starts nothing). It starts itself only when the boot block says `page:"dept"`:
  `init()` (once, at DOMContentLoaded), `chip()`, `title()`, `onTab(name)`, `events()`, `drawers()`, plus `destroy()`, `state()`, `helpers` (`touchesDept`,
  `bannerText`, `titleText`, pure).
- `init()` runs `chip()` and `title()`, mounts `NodePanel` on `#nodepanel`, listens to `sutra:tab` and `sutra:seen`, and mounts the view named by
  `SutraCtx.currentTab` when it is `graph` or `orgchart` (J2 shows a `?tab=` or `#hash` pane at parse time; both end in `showTab`).
- A view mounts the first time its tab shows; nothing is requested before. Graph: `GraphView.create({mode:"graph", scope:"this", level:"chart"})`,
  `GET /api/graph?level=chart&dept=`, `update(raw)`. Org chart: `OrgChartView.create` and its own `refresh()` (`/api/chart`, `/api/chart/changes`).
- One `SutraEvents` stream (topics graph, chart, chat), opened by the first view: `graph.updated` refetches the graph (coalesced 150 ms), `chart.changed` and
  `chart.approval` the chart, `server.resync` both, `chat.message` of anyone but the owner gives that session's node an unread dot, `sutra:seen` clears it;
  `onState` goes to `setLive` of both views and `pollFn` refetches both (X4).
- Archived (`boot.archived === true`): `body.archived` (UI-6's CSS hides the composers) and a banner with `boot.note`.
- Tests: 5 in node (gate) and 28 in Chrome (`SUTRA_BROWSER=1`, about 30 s; one Chrome each, the real page on the fake backend).
- Mutation check, one pass on a scratch copy: 15 single-site breakages (tab read at init, archived class, own-team filter, root click, select before drawn, revisit
  refetch, All-teams filter, owner's message dot, title, chart.approval, chart live state, panel graph, pollFn, resync, banner fallback). 12 died at once; 3
  survived: a redundant guard (removed), the chart's live state (the polling test now mounts both views before the stream drops) and a redundant close in
  `drawers()` (removed; its replacement mutant, the panel's `getGraph`, got a test and died). No second round.

## Deviations from the specification
1. The banner is one element at the top of each of J2's two views (`#sview`, `#dview .dcol`), not one in `<body>`: the body is a flex box that turns into a row in the
   chat view, so a body child became a third column. Its text is `boot.note` (the server's sentence, which names the team merged into), else a generic one;
   the spec's "merged into <label>" would name the archived team itself.
2. `events()` connects when the first view mounts, not at `init()`: a page that never opens a new tab holds no stream. The panel keeps its own stream.
3. The org chart is loaded by `OrgChartView.refresh()`, not `update(chart, changes)` from here: the same two calls, and it drops stale answers.
4. `drawers()` only mounts the panel; the two-way exclusion with J2's Agent drawer is `NodePanel`'s (UI-6) and a test drives it end to end.
5. Extra members: `destroy()`, `state()`, `helpers`. A click on the root node goes to the Org chart tab (a team page has no org chat).

## Decisions
- The panel's `getGraph()` is the last raw `GET /api/graph` of this page (null before the graph tab opened: the panel then asks the server).
- A `graph.updated` whose changed nodes all belong to another team is ignored while the graph shows "This team"; no nodes, a root change or "All teams" refetch.
- "Show in graph" selects the node once the graph view has had its first answer, at once when it already has.
- A revisit of a mounted tab refetches only when the stream is not live. A view that throws on `create` is logged and its tab stays empty; J2's page works on.

## Known limits
- "This team" holds no other team's node, so "Show in graph" for another team's chart node selects nothing.
- Chrome only. The banner colour is J2's `.banner` (`--priority`); contrast is UI-9's. The polling test uses a stub `EventSource` (the fake cannot drop a
  stream); the refetch on a revisit while the stream is down is only weakly pinned (a 2 s poll could give the same request).
## Follow-ups
- UI-9: the smoke can walk `?tab=orgchart` and `?tab=graph` on `/d/web/` and the archived page (a stub row with `archived` and `merged_into_name`, patched
  into `fake_backend._Services.department` before the server starts: the router keeps the bound method).
