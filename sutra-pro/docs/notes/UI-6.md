# UI-6 as built: node panel

Owns `sutra_app/ui/static/js/{fnode_view,chat_view,node_panel}.js`, `static/css/sutra-panel.css`, `tests/ui/js/{fnode_view,chat_view}.test.js`,
`tests/ui/test_view_panel.py`, this note. Spec: `docs/design/ui.md` 6.4, 6.5, 7, 8, 10; S3-web-05, S4-fnodes-06/-10/-12; D62, D63, D64.

## What was built
- `fnode_view.js` (`FnodeView`, pure): `normalize` (reads a NodeDetail or just a function's `meta`), `render` (head, Goal, Task, "What this function is given",
  Work atoms with the legend, Constraints, Hands to, then Go-to-tab and J2's block on the department page or the team-page line on Home), `atomHtml` and
  `normalizeAtom` (J2's labels, the five states, tries, pills, Concern on record, cost line; `work-atom/0.3` and `atom/1`), `verifySentence`, `stateWord`,
  `functionsOf` (the five chips of a division or team), `nodeHtml` (any other node kind), `usageText`, `statsText`, `nodeWord`.
- `chat_view.js` (`ChatView`, pure): `transcript`, `card` (task, chart_change, approval, choice, needs_you, done, atom, unknown), `composerState`, `safeText`,
  `whoLabel`, `parseAsk` (J2's own reader), `stripTag`. Buttons carry `data-act`; a team link is a real `<a href>`.
- `node_panel.js` (`NodePanel`): `#nodepanel` with Chat and Details tabs, division lens, Earlier chats, own event stream and polling; handle `{open, openFunction,
  wants, chatSessionFor, close, isOpen, destroy}`; the static `NodePanel.*` act on the last mounted panel. `sutra-panel.css`: panel, atom cards, chat cards, the
  `body.archived` rule, `.railhome`, the J2 block's hidden head. Tokens only, no url().
- Tests: 134 node tests (0.2 s), 28 browser tests (about 90 s, `SUTRA_BROWSER=1`) on the fake backend's `panel` mount page.
- Mutation pass in /tmp: 19 single-site breakages, 18 caught at once; the survivor (`attempt >= 1` read as `> 1` in the pill) got a test, then died.

## Deviations from the specification
1. `normalize(raw)` takes the whole NodeDetail (the head, the usage line and "Working for" need more than `meta`) or a bare `meta`; unknown keys, `atom_count` ignored.
2. Card shapes follow ORCH 3.3 (`change_id`, `approval{change_id}`, `done` with no `dept_id`); `seq`/`change_seq` of ui.md 6.6 are read too (`data-seq`).
3. The panel opens its OWN `SutraEvents` stream while open (the 7 interface gives a host no way to feed it events); the host forwards nothing.
4. `wants(id)` is false until a panel is mounted (J2's Agent drawer then works as before); `openFunction(fn, tab="details")` (the Agent drawer's place).
5. A department, division or Identity chat is closed while `NodeDetail.task.status` is running or starting (J2's Simple view does the same); 409 still handled.
6. Evidence "deferred: ..." reads "attempt 1: deferred, ..." (a check not judged yet is not "passed"); "Handed from" uses a copy of HANDOFFS (S3-web-04(c)).
7. Owner-facing chats drop a leading `@Requester` address; a working log keeps it. Wire text is otherwise verbatim (no J2 `dv()` or `plain()`).

## Decisions
- Persona, FN_TAB, GIVEN and the J2 status words are copied in (Home and the mount page do not load graph_render.js).
- Atoms: open first, then newest by `ts_open` (`/api/atoms` has no such order); the open atom is unfolded on first drawing; Show all, then pages of 100 (offset).
- "Show everything for <Department>" loads the team's session in the same panel with a link back; Earlier chats are forced read-only, with the filed note.
- The panel writes `sutra:seen:<sid>` and dispatches `sutra:seen` {session, id}, so a graph can clear its unread dot at once.
- J2's own `data-agent`, `data-agentclose`, `data-maptab` names are never used (a click on them reopens the Agent drawer); the J2 slot is `data-fnagent`.

## Known limits
- Identity's own working log (its atom cards) is not shown in the Chat tab, only as the atoms of Details; the J2 block is fetched once per open.
- The fake keeps a division's transcript fixed, so a line written there is seen only as a POST. Chrome 156 is the only browser tried; focus is not trapped.
- Until UI-2 merges `j2.css`, the browser test uses a stand-in with J2's tokens (the real file is used when it exists).

## Follow-ups
- UI-7 (Home): `ChatView.transcript(cs_org, ...)` with `opts.answers` and `opts.deptSessions`; handle `data-act` open-team (`<a>`, or a button with
  `data-task` and `data-dept-name`), show-node, show-change (`data-change`, `data-seq`), choose (`data-option` = the label), answer-option (`data-opt` N and
  `data-session`: post "Option N" there, never to cs_org), answer, retry; mount with `NodePanel.mount(#nodepanel, {getGraph, navigate})`.
- UI-8: load fnode_view, chat_view, node_panel in E12's order; the panel reads the boot block for `withAgent`. UI-5: a node click calls `NodePanel.open(id)`.
- UI-9: the contrast test reads sutra-panel.css (text tokens only); the visual matrix has `fnode-drawer` and `node-chat`.
