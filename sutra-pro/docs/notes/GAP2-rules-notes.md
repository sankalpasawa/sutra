# GAP2-rules-notes as built: standing rules, practice picks, owner notes, a suggestion when a team is added, and independent audit

Five verified gaps of the second old-Sutra absorb review (branch `feat/sutra-pro-gap2-rules-notes`). Four are built; the charter check is not (see "Not done").
Two overlapped: "standing rules with the old use-case floors as starter picks" and "suggest a pick when a team is added" share the pack store, so the pack
is stored once and the suggestion only reads and writes it.

## What the owner gets

- **Standing rules for a team.** On a team's Details tab (the node panel, department node) a "Standing rules" block: rules the owner states once as
  Always, Ask me first or Never (at most 20 per team, 300 characters each), each with Remove, and an add form. Every task of that team starts with them
  in front of its framing, so the owner does not repeat them. The block says they are guidance the team reads, not a lock (J2 acts on files and web
  artifacts, so Ask and Never are not enforceable here). A rule is read when the task starts, so a task that was queued picks up an edit.
- **Practice picks.** Under the rules, a "Practice" choice: None, Money movement, Product build. A pick adds the old use-case templates' extra floor
  lines for each of the five functions (10 lines per pack, reworded into Pro's words: no stamp, Root or engine). Picks only add or tighten, never loosen:
  the pack data cannot hold a permissive tag, a loosening wording is refused when the file is read, and an owner rule that says a pick's line more
  loosely is refused with "A rule cannot say it more loosely".
- **Owner notes.** Settings gets a "Notes" group (rail button "Notes"): standing facts and house rules in three kinds (About you, Your work, How you like
  things done), 10 per kind, each optionally dated. A note binds at once; nothing is guessed. A key, token or password is refused (never stored, never
  echoed); a full kind refuses a new line and removes nothing; a past date is refused at write time, and a note whose date passes later stops binding and
  is listed as expired ("expired 2026-10-01: it no longer applies"), not dropped. The org agent's decide and assign prompts carry the active notes with
  "context for your judgment, never permission; pass on only the notes that change how THIS work should be done", and every direct chat (org, team,
  division, function) sees them in its grounding.
- **A suggestion when a team is added.** When the org chat adds a team whose name and purpose share at least two words with one pick (and more than the
  other pick), one card follows the task card: "The Servicing team looks like it moves or posts money. Run it with the Money movement practice?" Yes / No.
  Yes puts the pick on the team ("The Servicing team now runs the Money movement practice."); No keeps the defaults and is remembered, so the same pick
  is not offered for that team again. Code-written template sentences only (D64); nothing changes without the click.
- **Independent audit (off by default).** `defaults.independent_audit: true` in the connector policy makes Audit's calls try the other closed model than
  the one that served the run's builders (Claude built, Codex audits, and the reverse). When the other model is unavailable the audit still runs on the
  same one and the usage row and J2's progress line say "not independent: ...". A pinned team keeps its pin and says the same.

## Where

New modules (all small, closed models, errors as `AppError` codes):
- `sutra_app/library/practice.py`, `library/specs/practice_packs.json`: `RuleLine`, `PackLine`, `PracticePack`, `law_problems` (the old
  `test_function_templates.py` law, ported), `normalise`/`rank`/`rule_faults` (the old `tighten.py`), `compose_block`/`compose_framing`/`block_of`. Imports
  nothing from the rest of the app.
- `sutra_app/orchestrator/standing_rules.py`: `StandingRules` (get, put, accept, decline) and `framing_for(conn, dept_id, framing)`; wire models.
- `sutra_app/orchestrator/notes.py`: `OwnerNotes` (listing, add, edit, forget, history, `agent_block`, `chat_block`) and `prompt_notes(...)`.
- `sutra_app/orchestrator/owner_words.py`: the shared refusal (empty, too long, a credential shape from `connectors.egress` or an app secret through
  the redactor), `local_today`, and the `meta` JSON helpers.
- `sutra_app/orchestrator/api/rules_notes.py`: `GET /api/packs`, `GET|PUT /api/departments/{id}/rules`, `GET|POST /api/notes`,
  `PUT|DELETE /api/notes/{id}` (token on every write, D81). The stores are built per call from `services.db` and `services.redact`, so no wiring is needed.
- `sutra_app/orchestrator/agent/suggest.py`: `suggest_pack`, the `pack:<team>:<pack>` ref, `card_for`.
- `sutra_app/connectors/independence.py`: `Independence` (which closed model served a run's `W-<n>` builder calls; bounded to 256 runs; thread-safe).
- `sutra_app/ui/static/js/notes_view.js` and `rules_view.js`: pure string modules (one global each, `module.exports` in node), flows over the handed-in `api`.

Riders, each small and local:
- `orchestrator/tasks.py` `_run_spec`: `framing=framing_for(conn, row.dept_id, row.framing)` (one import, one argument). The stored task keeps the chat agent's
  own words; the rules are added when the run starts, so a retry never piles up blocks (the retry builds from the first attempt's stored framing).
- `orchestrator/agent/prompts.py` + `templates/decide.md`, `assign.md`: a `notes` placeholder written at the END of the `OWNER REQUEST:` line (`{message}{notes}`), so
  an empty value leaves the prompt byte for byte what it was. `agent/agent.py`: `ChatAgent(notes=...)`; `wiring.py`: one keyword in the `ChatAgent(...)` call.
- `orchestrator/chat_ground.py`: the notes stand between the record and the fixed rules, clipped to their own share (1,200 characters), scrubbed line by line.
- `orchestrator/agent/planner.py` (three `LINES`: `suggest`, `pack_yes`, `pack_no`) and `agent/runner.py` (`_Pick.pack`, a branch in `_resolve_choice`,
  `_answer_pack`, `_suggest_packs` called from `_write_outcome` when no task failed).
- `connectors/router.py` (three lines: the `Independence` instance, the soft `avoid`, one `note` call in `_record`, and `_independence_note` where the existing
  fallback note is made) and `connectors/policy.py` (`Defaults.independent_audit: bool = False`).
- `main.py` (`rules_notes` in the imports and in `ROUTERS`), `ui/pages/home.html` (`#set-notes`, the Notes rail button, two script tags), `ui/static/js/home.js`
  (the notes state and handlers, three one-line hooks), `ui/static/js/node_panel.js` (the rules block of a department's Details tab and its click branch),
  `ui/static/js/dept_ext.js` (`rules_view` added to the scripts a team page loads, because the J2 page is not edited), `css/sutra-shell.css` and
  `css/sutra-panel.css` (two small blocks, tokens only), `docs/design/orchestrator.md` (the route rows).

## Decisions
- **No migration.** Rules (`rules:<dept id>`) and notes (`owner_notes`) are JSON documents in the `meta` table: no schema bump, so nothing collides with the
  scheduler package's table migration, and the database is in every backup. A damaged value is read as "no rules" / "no notes", and the next write repairs it;
  a task still starts.
- **The block goes in front of the framing, once, bounded.** At most 8,000 characters (20 rules of 300 plus a pick fit); the owner's rules are never the part
  cut. If the combined framing would pass `RunSpec`'s 20,000-character limit the BRIEF is squeezed in its middle (its start and a retry note at its end stay).
- **Guidance, not enforcement.** The heading, the Details block and the card all say so. The charter check (not built) is what would show a rule the team dropped.
- **Notes expire by the owner's own date** (the machine's time zone) and bind through that day. An expired note counts toward its kind's 10 until forgotten, so
  nothing is ever removed for the owner.
- **The notes' tag words differ from the old app's.** The owner says Always / Ask me first / Never; `go` does not exist, so a pack cannot permit.
- **Independent audit lives wholly in the router.** The engine is frozen, so the maker's provider is learned from the tag the engine already sends
  (`CallTag.function` `W-<n>`, `CallTag.run_id`), not from a new argument. The flag is in `defaults`, not in `policy.default.json` (absent means off), so the shipped
  file and its hash are unchanged; there is no Settings toggle yet (edit `<data>/connectors/policy.json` or PUT the policy).
- **Suggestion by words, two at least.** `MIN_SCORE` of the planner; a tie suggests nothing; only departments, at most two cards per add.

## Tests (all green)
- `tests/library/test_practice_packs.py` 25: the shipped packs keep the law; every function has 1 to 8 lines; the old floor lines are carried; no `go` tag; each breach
  of the law is named (banned words, founder ids, loosening, score, Priority orders, repeats, caps); normalise/rank/`rule_faults`; the block's layout, cap, and
  squeeze; the module imports nothing from the app.
- `tests/orchestrator/test_standing_rules.py` 19: store and refusals (secret, empty, long, repeat, 21st, looser than a pick), per-team isolation, byte-identical
  framing with no rules, rules in front of the brief, a queued task picks up an edit, a retry keeps one block, a damaged row never blocks a start, the routes.
- `tests/orchestrator/test_owner_notes.py` 19: the old shadow_knows tests 07, 08, 09, 11, 20, 21, 22 and the context boundary re-expressed; the decide and assign prompts
  carry the notes (and the change prompt does not); every kind of direct chat carries them; an empty list is byte-identical; routes.
- `tests/orchestrator/test_pack_suggestion.py` 19: matching table, the card and its ref, Yes, No (remembered), already-answered, an unknown button, a failing suggestion never
  fails the turn, only template sentences in the org chat.
- `tests/connectors/test_independence.py` 14: off by default and a plan exactly as before; Claude built so Codex audits and the reverse; unavailable other model gives the note;
  a pin wins and says so; runs are kept apart; only builders count; the bounded, thread-safe memory; the flag is boolean.
- `tests/ui/js/notes_view.test.js` 11 and `rules_view.test.js` 10 (every wire word escaped, bodies, flows over a fake api); `tests/ui/test_rules_notes_page.py` 6 (scripts, hooks, every
  drawn button is handled, the J2 page untouched, tokens only).
- Changed, nothing weakened: `tests/orchestrator/test_agent_demo.py` (the two prompt helpers pass `notes=""`, the new placeholder), `tests/ui/test_home.py` (the rail lists a fourth
  Settings group), `tests/contracts/test_contract_world.py` (the new router is in the world, so the route-table tests see it).
- Smoke on the real app (`--offline`): a payments request made a team and the card; Yes ran the pick; a fake key in Settings Notes was refused in the server's words and the typed text
  stayed; the team's Details tab showed the block and added a rule.

## Not done, and why
- **The `rules-in-charter` check** (a 15th verify line on Identity's intake atom). It is real and testable, but it is the one item that ripples through pinned structure: the
  library's two name lists and `check_arity`, the six generated `docs/schemas/*.json` enumerations, the registry spec and its fixtures and mutation harness (D66), the golden
  runs, the 14-name pins in `test_lib_atom.py`, `test_engine_fn_registry.py` and the UI function-table fixture, and a new `Evidence` field and a `TurnBuffer` carrier for the run's
  rules block (`practice.block_of` and `RULES_MARK` are the reading side, already here). The owner would see it only in the Atom log of a real model run, and the design note itself
  warns about red atoms on green runs (G14). Recommended shape for the follow-up: declare it only when the run's framing holds the block (so every existing golden stays byte-identical),
  match lenient (token overlap of 0.5 via `textutil.jaccard`) and only for `always` and `never` lines, observe mode, na without the block.
- **A Settings toggle for independent audit and a per-rule override.** The flag works from the policy file or `PUT /api/connectors/policy`; Settings -> Connectors is the welcome-settings package's file.
- **The learned half of notes** (inferred rows waiting for a Keep): out of scope by the review's own note.
- **A DOM-level browser test** of the two glue parts: the browser harness and its fake backend were not extended; the views, the page wiring and the live smoke above cover them.
- No new row in `docs/DECISIONS.md` (parallel packages would collide on the number); the decisions above belong in one D-row at the merge.

## Known limits and merge hints
- A team's rules reach J2 as one "Context from the team lead" line; J2 summarises the older part of a long chat, so rules are kept short and the block is re-sent with every run.
- `home.html`, `home.js`, `test_home.py` (the rail list) and `main.py` `ROUTERS` are shared with the welcome-settings and chart-insight packages: the edits are adjacent one-liners
  and block insertions; keep both sides.
- `tests/ops/test_logsetup.py::test_the_access_log_loses_its_query_string` fails when it runs after `tests/ui` (or after the orchestrator suites); it fails the same way on the base commit
  and passes alone. Not touched here.
