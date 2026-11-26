# Review: remove-real-run-gates (D452, P46, E31)

## Round 1  (2026-11-26, commit 6dc52d5e)
Verdict: Changes requested

No P0 or P1 findings. Four P2 findings, all small to fix. The engine change matches the spec and passes every suite I ran. Two P2s change behaviour: a live builder prompt still promises approval and copies, and a script that leaves an unreadable file breaks "once per workflow id". The other two P2s are untested guarantees: the summary catch-all and NFR-8's write limit.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R1-1 | P2 | sutra_app/engine/templates/builder.md:12-17 | The tools builder's system prompt still says "Code runs it on the Requester's folder only after the Requester approves the exact command" and "code first runs it on copies ... Code refuses a build whose files hold one of those paths". Since D452 all three statements are false. This is the live prompt for every builder with tools, which are the builders that write real-run scripts. FR-34's file list left it out, but it breaks FR-22/FR-34's intent and the founder's "no leftover Run text in prompts". | `artifacts/types.json:7` `"builder": "templates/builder.md"`, loaded by `j2_types.builder_tools()` (j2_types.py:283). `llm.tools_on()` is true live whenever the Claude CLI connector can take a tools call (llm.py:125-130). | Add a P46 data edit, using T2's mechanism, that rewrites those two bullets (keep "never run it on the Requester's files yourself"). Re-record the affected goldens. Extend AC-25's phrase scan to templates/builder.md. |
| R1-2 | P2 | sutra_app/engine/j2.py:13423 (vendor_j2.py:3243); j2.py:5340 | FR-40's catch-all in `_write_summary` is not tested. When it fires, the Requester has already seen "Done: ..." in chat. Mutation check: I replaced the condition with `if False and ...`. All 378 tests of test_engine_patches.py and test_engine_finish.py still pass. The catch-all is the only guard for `_run_tpl_stage_end` (j2.py:4120), `_stages_finished` (:5734) and the passing branch of `_deeds_finished` (:6188). Also, `_finish` posts the closing system line `self.outcome + ...` at j2.py:5340 before it calls `_write_summary` at :5347. On those paths, chat shows "Done:" while summary.json says done_with_open_items. The rewrite also drops the original outcome text, such as the deed words. | Mutation run on a copy of the tree in the scratchpad. The order is visible at j2.py:5340-5348. | Apply `_real_run_open()` inside `_chain_done` (one place, every chain/deed/template ending), or move the catch-all ahead of the closing post. Add a test that ends a run through `_chain_done` (or calls `_write_summary` with outcome "Done: ...") while a required real run is open, and assert that both the outcome and the last system line start "Done with open items". |
| R1-3 | P2 | sutra_app/engine/j2.py:6011-6013 (vendor_j2.py:3181-3183) | `_real_run_once` hashes the folder after the command with `_tree`, before it writes the receipt row. `_tree` opens every file and raises on a broken symlink or an unreadable file. A script that leaves one behind (for example a symlink or a `chmod 000` file) therefore crashes the run after the real run has already changed the Requester's folder. No row is written and no "Ran for real" line is posted. A follow-up then finds no row (`_ran_real_run`, :5958) and runs the command again unasked, which breaks FR-2's "at most once per workflow id". Before D452 the dry run hit this on the copies, before the real run. | `j2._tree` on a folder with a broken symlink raises `FileNotFoundError` (checked). | Make `_tree` skip entries it cannot read (try/except per file, or `os.path.isfile` and `os.access`), or write the row before the diff. Add one test with a script that leaves a broken symlink. |
| R1-4 | P2 | tests/engine/test_engine_patches.py:4641 | NFR-8 and AC-19 require a real-srt test showing that a real run writes nothing outside its folder. The only real-srt P46 test covers the network half only. No test, here or on main, asserts the real run's `allowWrite: [folder]`. The behaviour itself is intact: I ran `j2.real_run` under the installed srt with a script that writes outside its folder, got `PermissionError`, and the outside folder stayed empty. | Grep of `allowWrite` in tests/engine finds only the env install test at :4221. | Add the write half to `test_p46_real_srt_*`: a script writes to its folder and to a sibling folder; assert the first file exists and the second does not. |
| R1-5 | P3 | sutra_app/engine/j2.py:5703, :6188 | FR-40 says every ending names the real-run reason. Two endings already start "Done with open items" but never name it: the stage gate's "finish as it is" (:5703) and the failing branch of `_deeds_finished` (:6188). Real runs in document chains are unlikely. | Code read. | Fold this into R1-2's `_chain_done` fix. |
| R1-6 | P3 | sutra_app/ui/pages/j2_ui.html:2404 (E31, port_j2_ui.py:320) | Old rows that were approved and ran now show "ran automatically". NFR-6 is met (no error), but the label is wrong for history. | Code read. | Optional: `r.approved === true ? "approved by you" : r.ran ? ...`, or leave it as is and note the choice. |
| R1-7 | P3 | tests/engine/test_engine_patches.py:2822, :3506 | `p32_card` and `p35_again` are now dead test helpers. Neither is referenced. | grep: one hit each. | Delete them. |
| R1-8 | P3 | tests/engine/legacy/j2_flow_test.py (D452_GONE) | Skipping `real_run_checks` as a whole also drops J2's checks-validation asserts: "not a done-when item" and "real_run checks is empty". Those asserts are unrelated to approval, and no test outside the legacy file asserts these two refusals. | grep across tests/engine and tests/ui. | Add two `_register` asserts to test_engine_patches.py. |
| R1-9 | P3 | tests/engine/test_engine_patches.py:2729 | AC-29 copies receipts.jsonl by hand instead of going through `rehydrate` (deviation 9). The property under test, `_ran_real_run` reading the copied file, holds, and rehydrate does copy `*.jsonl` (rehydrate.py:175, :347). | Code read. | Acceptable. An end-to-end rehydrate test would be better when the fixture allows. |

Checked and fine (no finding):
- No row writes `approved`, `code`, `answer_msg`, `dry_run` or `offline`. AC-23's test asserts the exact FR-27 key order.
- The `env_install` row matches FR-28.
- No new switch, getenv or host literal.
- Nothing Pulse-specific.
- No new dead definitions in j2.py compared with main (scripted scan).
- E28 and E29 are gone from the port, the mirror and the page.
- `REAL_RUN_DECLINE`, `real_runs_asked`, `_dry_run_failed`, `real_run_env_lines`, `real_runs_dry`, `_real_path_leak` and `real_paths_in` survive only as old-text anchors in vendor_j2.py and as history notes.

### Spec coverage
| Requirement | Covered by | Status |
|---|---|---|
| FR-1, FR-3, FR-4 (no question, pause or buttons) | `_real_run_next`; test_p46_a_planned_real_run_runs_once_unasked, test_p46_no_real_run_or_hosts_pause_exists; port --check | Met |
| FR-2 / AC-29 (once per workflow id, follow-ups) | `_ran_real_run` (receipts.jsonl); AC-2 and AC-29 tests | Met, except R1-3 |
| FR-5, FR-6 | `_real_run_once`, `_real_run_answer`; j2_artifacts.py:775 | Met |
| FR-7 to FR-9 (install, no question) | `_env_install`, `_env_stops_real_run` and `_real_run_back` | Met |
| FR-10 to FR-13 (no dry run, offline, folder-argument rule, leak rule) | code removed; AC-9 to AC-12 tests | Met |
| FR-14 to FR-18 (expect after the run) | `_real_run_once`; AC-14 and AC-15 tests | Met |
| FR-19 to FR-23 (hosts: syntax only) | `real_run_hosts_problems`, `real_hosts`; AC-16 to AC-18 tests | Met |
| FR-24, FR-25 | P43 trimmed; AC-20 test | Met |
| FR-26 (D446 secrets) | `real_run`: `llm.run_env`, wrap, path-only `allowRead`; AC-22 test | Met |
| FR-27, FR-28 (row shapes) | AC-1/AC-23 and AC-6 tests | Met |
| FR-29 (`unparsed`) | moved to P46; tests kept | Met |
| FR-30 (srt write limit) | `allowWrite: [folder]` unchanged; checked by hand with real srt | Met, untested (R1-4) |
| FR-31 to FR-34 (prompt text) | P46 data edits; vendor --check | Met for the listed files; templates/builder.md missed (R1-1) |
| FR-35 to FR-38 (records) | DECISIONS.md +15 −0; decisions.json; VENDORED.md; test_diagram_decisions | Met |
| FR-39 | tests rewritten; legacy D452_GONE | Met (R1-8) |
| FR-40 / AC-28 | `_real_run_open` in `_goal_done`, `_ship_outcome` and `_write_summary`; 5 parametrised cases | Met on the tested paths. A mutation of `_goal_done` kills 5 tests and a mutation of `_ship_outcome` kills 1; a mutation of `_write_summary` kills none (R1-2) |
| NFR-1 | code (sutra_app + scripts, non-.md) +825 −1284, net −459; with the vendored .md files +860 −1320; j2.py 14001 → 13630 | Met |
| NFR-2, NFR-3 | diff scan | Met |
| NFR-8 / AC-19 | network half only | Partly met (R1-4) |

### Tests run
| command | result |
|---|---|
| `scripts/py -m pytest tests/engine/test_engine_patches.py tests/engine/test_engine_views.py tests/ui/test_port_edits.py tests/test_diagram_decisions.py tests/engine/test_engine_vendor.py` | 689 passed, 3 skipped |
| `SUTRA_SLOW=1 SUTRA_J2_CHECKOUT=<extraction of ee659fb5> scripts/py -m pytest tests/engine/test_engine_vendor.py tests/engine/test_engine_legacy.py` | 85 passed, 1 skipped |
| `scripts/py scripts/vendor_j2.py --source <extraction> --commit ee659fb5... --check` | 527 files, ok |
| `scripts/py scripts/port_j2_ui.py --j2 <extraction> --commit ee659fb5... --check` | ok, 57 anchors |
| `node --test tests/ui/js/page_render.test.js tests/ui/js/result_view.test.js` | 96 tests: 95 pass, 1 skipped |
| FR-40 mutations (on a copy of the tree in the scratchpad) | `_goal_done` guard removed: 5 fail. `_ship_outcome` guard removed: 1 fail. `_write_summary` guard removed: 0 fail across test_engine_patches.py and test_engine_finish.py (378 pass) |
| `j2.real_run` with real srt and a script that writes outside its folder | outside write refused (`PermissionError`) |
| `j2._tree` on a folder with a broken symlink | `FileNotFoundError` |

Not run: the full `scripts/gate.sh` (the developer reports 13618 passed and 4 failed, the 4 identical on origin/main), browser tests, live smoke and the beta install. AGENTS.md step 3 expects a beta install for a change that shows in the app (E31, behaviour); none was made.

### Deviations (implementation.md)
| # | judgement |
|---|---|
| 1 (T2 data-file edits) | Sound. It is needed for FR-33, and the same mechanism fixes R1-1. |
| 2 (goldens) | Verified: only Identity's system digest moved in every golden. |
| 3 (E31 wording) | Fine (founder note). See R1-6 for historical rows. |
| 4 (P28/P29/P30/P42 carry D452 text) | Acceptable under the rule that a patch's new text survives; VENDORED rows say so. |
| 5 (`_real_run_back`/`_real_run_once` in P46) | Fine. |
| 6 (follow-up reads the copied row) | Correct: `_real_run_open` falls back to the row's `ran`/`exit`/`audit` when `real_runs_done` is empty. Without it a follow-up of a passed run would report "did not pass". |
| 7 (`rest and real_runs_done` kept) | Fine. |
| 8, 11, 12 | Fine. |
| 9 | See R1-9. |
| 10 (legacy blocks print D452 skips; EXPECTED.json −4 ok lines) | Matches FR-39, but see R1-8. |

### Earlier findings
None (first round).
