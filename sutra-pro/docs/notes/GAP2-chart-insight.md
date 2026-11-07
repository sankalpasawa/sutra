# GAP2-chart-insight as built: what a merge will do, what has drifted in the chart, find a team across the org, names not paths

Four verified gaps of the old-Sutra absorb review, built as one package (branch `feat/sutra-pro-gap2-chart-insight`). No J2 file, prompt, route or golden is
touched; the J2 team page is reached only from `dept_ext.js` (one script added, as `attention()` does).

Built:
- `sutra_app/orchestrator/reorg_preview.py` (new, reads only): `ReorgPreview(db).describe(change, before)` -> `ImpactOut {lines, notes}`; `ChangeImpactOut`; `card_lines`.
- `sutra_app/orchestrator/chart_health.py` (new, reads only): `ChartHealth(db).notes(now)` -> `ChartNotesOut`; the pure `overlap_pairs`, `thin_purpose`, `labels_of`, `related`.
- `sutra_app/orchestrator/team_find.py` (new, reads only): `TeamFind(db).search(q, limit)` -> `TeamFindOut`.
- `sutra_app/orchestrator/pathwords.py` (new, pure): `shorten(text, roots)`, `machine_roots`, `compile_rule`.
- `sutra_app/orchestrator/api/insight.py` (new): `GET /api/chart/changes/{id}/impact`, `GET /api/chart/notes`, `GET /api/find?q=` (reads, no token). One router for the three reads.
- `sutra_app/ui/static/js/chart_notes.js` (new, pure, global `ChartNotes`), `team_find.js` (new, global `TeamFind`: pure parts and `mount`).
- Riders (small and local): `orchestrator/models.py` (`ApprovalCard.impact`, optional, at most 8 lines of 160), `orchestrator/agent/runner.py` (`_ask_approval` fills it,
  `_impact_of`), `orchestrator/runs.py` (`crash_outcome`) and `orchestrator/tasks.py` (the 'could not start' line) call `shorten`, `main.py` (`insight` in `ROUTERS`),
  `ui/static/js/chat_view.js` (`impactList`, drawn under an open approval's question), `orgchart_view.js` (notes panel, card address, `setFind`), `home.js`
  (`wireFind`, one line in `boot`, one line in `ensureChart`), `home.html` (the search box and result area in the Teams section, two script tags), `dept_ext.js`
  (`insight()` adds `chart_notes.js` to a team page), `css/sutra-graph.css`, `css/sutra-panel.css`, `css/sutra-shell.css` (appended or placed beside their kin).
- Tests: `tests/orchestrator/test_pathwords.py` 46, `test_chart_health.py` 13, `test_reorg_preview.py` 18, `test_team_find.py` 12, `test_api_insight.py` 11, plus
  `test_turn_runner.py` +2, `test_projector.py` +1, `test_tasks.py` +1; `tests/ui/js/chart_notes.test.js` 7, `team_find.test.js` 14, `chat_view_impact.test.js` 5;
  `tests/ui/test_chart_insight.py` 2 + 9 browser (`SUTRA_BROWSER=1`). `tests/ui/fake_backend.py` serves `GET /api/chart/notes` and `GET /api/find` and the controls
  `POST /__fake/chart-notes {notes}` and `POST /__fake/find {teams, messages}`; `tests/contracts/test_contract_world.py` mounts the new router.

## What the owner sees
- **Approval card.** Under 'Merge Leads into Quotes? Their chats and history stay available.' (the question is byte-identical) a short list, while the card is open:
  'The chat of Leads (6 messages) becomes read-only history under Quotes.', 'The chat of Quotes (14 messages) stays open.', '2 step nodes of Leads would move to Quotes.',
  'Deep Dive would move under Quotes.', '2 older chats of Leads are filed under Quotes too.', 'Nothing is running in Leads.' A split says 'The chat of Leads (9 messages)
  stays open.' and 'Warm Leads and Cold Leads start with an empty chat.' A merge changes more than the old sentence said: the merged-away chat stops taking messages.
  Cautions come first: 'Leads is busy with Quote follow-ups: a yes would be refused until it finishes', 'The chart changed since you were asked: a yes would be refused',
  'The chart would be 5 levels deep (6 is the most).', 'Price list and Price list today would look alike (67% of their words).' Only what THIS change adds is said:
  a depth or a look-alike pair that is true on the chart as it stands is never repeated (the old studio's rule), and a division nobody works in gets 'Nothing is running'.
- **Chart notes** (Org chart pane, under the change log; also the Org chart tab of a team page): 'FAQ and Menu look alike (45% of their words)', 'Content has no purpose
  written', 'Florist site has had nothing for 90 days'. Each name is a button that opens that node's card; the line to act on is words for the chat agent ('Say: "merge
  Menu into FAQ"'), and nothing for two teams or a quiet team (only divisions can be merged, D68; a team is never archived, DL5). 'Nothing flagged' when it is clean, and a
  line that the notes change nothing. The card of a division now says where it sits ('Content > Menu').
- **The rail's search** (a box above the Teams list): from two characters, after a 220 ms pause. 'Found in teams': each row titled by its address ('Web > FAQ'), why it
  matched ('matched on purpose', 'name, a task', 'a task's result') and a snippet, a link to the team's page. 'Found in chats': the chat search's messages (a click opens the
  node that owns the chat; an archived chat opens the node it was filed under). In the Org chart pane the hits stay lit, the boxes above them are a little faded and the
  rest fade; Escape clears the box and the lit boxes.
- **Crash and start-failure lines** name files: 'File "tools.py", line 12', never the install folder or the home folder. The log files keep the whole text.

## Decisions
- **One router** (`api/insight.py`) for the three reads: one entry in `main.ROUTERS` and one in the contract world, which keeps the merge small. The package text named three
  router files; the routes are the ones it named except that the notes route is `/api/chart/notes` (the verifier's name) and the find route is `/api/find`.
- **The dry run is the library's own.** `describe` runs `apply_change` and `carry_links` over the pending change and reads counts (`chat_messages`, `graph_nodes` of kind
  step, archived sessions filed under a source). It writes nothing (a test compares every table before and after), and a failure in it leaves the card without its lines,
  never without the card (`_impact_of` logs and returns nothing). A card made before this version has no lines; the route answers the same words for it.
- **`impact` is a list on the card, not part of `question`**: the 500-character question limit and every test of its words stay as they are. `card_lines` puts the cautions
  first, then the effects, at most 8 lines of 160 characters.
- **Thresholds.** `OVERLAP_WARN` 0.40 (the old tuned value) is its own name, apart from `JACCARD_REUSE` 0.5 which refuses a NEW node: this one only tells. Ancestors and
  descendants of one kind are exempt, a team is never compared with a division. `DEPTH_WARN` 5 applies to the impact notes only (what a change makes deeper); the notes panel
  has no depth warning (the verifier: `MAX_DEPTH` is already 6). `QUIET_DAYS` 60, measured from the newest task, chat message or birth of the team; a team with anything unfinished
  is never quiet.
- **A thin purpose** is an empty one, or one whose every word is already in the name ('Support desk' for 'Support desk'). The old rule (under 60 characters with no second
  sentence) is not ported: the chat agent writes one-sentence purposes, so it would flag nearly every team and the panel would be noise (gap G14's lesson).
- **Find** reads the live nodes (`org_nodes.state = 'active'`) and the newest 2000 tasks. A field matches when it holds every word of the query, ignoring case; a name hit's
  snippet is the node's purpose; a task of a merged-away division belongs to its team. Ranking: name, purpose, task, outcome, then a name that starts with the first word, then chart
  order. `a b` is not a search (one word needs two characters). The messages group is `ChatSearch`, joined in by the route (at most 8), so the FTS table is not searched twice.
- **Fading by style rules, not classes.** The graph paints its boxes again on every update and on hover; `orgchart_view.setFind` writes one `<style class="ocfind">` with
  attribute selectors on `g.wnode[data-id]` (ids checked against a pattern first), so the dimming survives every repaint. The CSP already allows inline style.
- **`shorten` takes its folders from the caller**: the home, the temp folder, the folder `sutra_app` is installed in (and the interpreter's prefix when two names deep), the
  Mac's `/private/var/folders` and `/Volumes`, and the data folder. A route of the owner's site ('/home/about'), a relative path, a date and a URL are never touched.
- The team page loads `chart_notes.js` after the J2 page (the J2 page file is frozen), so the org chart view looks the global up when a note arrives and, if it is not there yet,
  tries again for up to 1.5 s.

## Not done, and why
- **The impact route has no page caller.** The card carries the lines from the moment it is asked; the route is for a card made before this version and for a script. Showing
  the same words for a pending row of the change log in the Org chart pane is a small follow-up (`selectChange` of a pending row).
- **No `kind/state/subtree` filter** of the old Org tree (the verifier's "smaller follow-on"), and no collapse of the non-hit branches: Pro's pane is the whole graph, so the
  non-hits fade instead.
- **The address of a deep division** is on the Org chart card only; the Workflow graph's node card (`fnode_view.nodeHtml`: "a division of X") is not changed.
- **No catch-up of old impact lines** for approvals already waiting, and no depth note in Chart notes (see Decisions).
- **`shorten` is applied to the crash tail and the 'could not start' line only**, as the package said: not the logs, not J2's documents or route bodies, not the retry brief
  (`attempts.py`, which goes to a model), not a `Stopped:` line the engine wrote itself. A Windows data folder outside Users, Windows, ProgramData or Documents is not
  recognised (a Windows drive path is shortened only under those folders).
- **Pre-existing, not touched:** `tests/ui/test_fake_backend.py::test_the_panel_mount_page_opens_the_node_it_is_asked_for_on_the_graph_it_loaded` (browser) fails at the
  base commit: its `mount_server` fixture copies a fixed list of scripts and lacks the two chat-comfort scripts (`chat_draft.js`, `chat_scroll.js`), so they 404.
