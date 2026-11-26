# Plan: a planned real run runs without approval, a dry run or internet rules
Branch: remove-real-run-gates (already cut from origin/main at 6c79a1db; do not switch)

Inputs: spec.md (Refined), architecture.md. Commands run from `sutra-pro/`.

## Rules for every step

| rule | detail |
|---|---|
| one commit per step | message `D452: <plain sentence> (<patch/edit ids>)`; the repository's git identity; no Co-Authored-By trailer |
| staging | `git add <each file named in the step>`; never `git add -A` or `git add .` |
| engine | `sutra_app/engine/j2.py`, `j2_artifacts.py`, the vendored data files and VENDORED.md change only by editing `scripts/vendor_j2.py` and re-running it on the extraction; never by hand |
| page | `j2_ui.html` changes only by `scripts/port_j2_ui.py` |
| stay out | `prototypes/j2`, `~/.sutra-pro`, the stable app, anything outside `sutra-pro/` |
| no push, PR, beta install or release | the owner decides |
| tests | targeted per step (below); `scripts/gate.sh` only in T12, in the foreground, once the owner has cleared it; never `scripts/live_smoke.py` |
| paths and names | no home path or person's name in any file (`tests/test_ownership.py`) |
| tests first | write or rewrite each step's tests before its code where practical |

Setup, once (an extraction of the pin; reuse it in every step):
```
J2SRC=$(mktemp -d) && (cd .. && git archive ee659fb54aec75bf7f5139516791aee20a0474fa prototypes/j2) | tar -x --strip-components=2 -C "$J2SRC"
PIN=ee659fb54aec75bf7f5139516791aee20a0474fa
```
"Regenerate" = `scripts/py scripts/vendor_j2.py --source "$J2SRC" --commit $PIN`, then "vendor check" = the same with `--check` (must print ok).
"Patch tests" = `scripts/py -m pytest tests/engine/test_engine_patches.py -q` (about 2 min).
"Vendor tests" = `SUTRA_J2_CHECKOUT="$J2SRC" scripts/py -m pytest tests/engine/test_engine_vendor.py tests/engine/test_engine_legacy.py -q`.

## Steps

| step | goal | Impact | Effort |
|---|---|---|---|
| T1 | D452 recorded | low (record, reserves the number) | ~25 lines, 15 min |
| T2 | vendor_j2.py can edit a vendored data file | medium (enables FR-31-33) | ~40 lines, 45 min |
| T3 | hosts: syntax only, no question, no `offline` (P44 retired, P46 starts, E29 gone) | high | ~-450 lines, 2-3 h |
| T4 | the two dry-run-only rules go | medium | ~-80 lines, 45 min |
| T5 | no dry run; `expect` checked after the real run (P32 retired) | high | ~-250 lines, 3 h |
| T6 | packages install unasked (P42) | high | ~-120 lines, 2 h |
| T7 | the real run runs unasked; row keys; E28 gone, E31 | high | ~-200 lines, 3 h |
| T8 | never "Done:" without the required real run (FR-40) | high | ~+60 lines, 1-2 h |
| T9 | answers can confirm real-run items (P43 trimmed) | medium | ~-60 lines, 45 min |
| T10 | prompt text and the two data files | medium | ~80 lines, 1 h |
| T11 | records: superseded lines, VENDORED intro, comments | low | ~60 lines, 45 min |
| T12 | full run, counts, implementation.md | n/a | 30 min + gate |

- [x] T1: Record D452
  - Files: `docs/DECISIONS.md`, `docs/diagram/decisions.json`
  - Change: `git fetch origin`; confirm D452 is still the next free number (`grep -n "^## D45" docs/DECISIONS.md` on origin/main); if taken, use the next free one everywhere in this plan and say so in the commit body. Append the D452 entry exactly as in architecture.md "Decisions" (sources, decided, why, rejected, diagram label) and its decisions.json entry in the shape of the D451 entry.
  - Tests: none new.
  - Done when: `scripts/py -m pytest tests/test_diagram_decisions.py tests/test_docs.py tests/test_ownership.py -q` passes
  - Covers: FR-35

- [x] T2: vendor_j2.py applies edits to vendored data files
  - Files: `scripts/vendor_j2.py`, `tests/engine/test_engine_vendor.py`
  - Change: in the role-file loop (vendor_j2.py:3767-3769) and the tree loop (:3770-3774), apply `[e for e in EDITS if e.file == <source rel path>]` with `apply_edits` (UTF-8 decode/encode, the same error as code files), record ranges and pass the patch ids to `add`. The `unknown` check (:3764) admits a file named `agents/j2/<ROLE_FILES name>` or a path under a `TREES` folder. No data edit yet, so the output is unchanged. Update the module docstring step 3 ("byte for byte, but for data edits").
  - Tests: a unit test that builds the tree from a small fake source with one data `Edit` and sees the edited bytes and the patch id in its row; an edit naming `agents/j2/nosuch.md` raises VendorError.
  - Done when: regenerate shows no diff (`git status --short sutra_app docs/reference` empty), vendor check ok, vendor tests pass
  - Covers: FR-33 (mechanism)

- [x] T3: Hosts are listed by the planner and syntax-checked only; no host question, no `offline` (P44 retired, P46 begins, E29 deleted)
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `scripts/port_j2_ui.py`, `sutra_app/ui/pages/j2_ui.html`, `tests/ui/test_port_edits.py`, `tests/engine/test_engine_patches.py`, `tests/engine/test_engine_vendor.py`
  - Change:
    1. Delete every `Edit("P44", ...)` (vendor_j2.py:3119-3412) and the `P44` PATCH_NOTES row. Add `P46` edits (after P43's) that put back only: `unparsed` (today's text at :3377, :3406-3412); `HOST`, `HOST_ENTRY`, `real_hosts`, `host_entry_ok`; `real_run_hosts_problems(rr)` with only the syntax check (key `real_run_hosts`, today's message without "named"); in `_register`, after P41's fields, `if bad := real_run_hosts_problems(...)` refuse, else `wf["real_run"]["hosts"] = real_hosts(rr)` when non-empty; in `real_run`, `allowedDomains: [] if fence else real_hosts(rr)` (fence goes in T5); `REAL_RUN_NET_RULE` = list every host the script reaches (bare name, optional `*.` and `:port`, no scheme, path or address) and never set HTTP_PROXY, HTTPS_PROXY, ALL_PROXY or NO_PROXY; `SCRIPT_NET_RULE` = test the network part with a fake local server, never the internet. Both joined where P44 joined them (j2.py:4393, :11085). Nothing about offline, naming, asking, a card or approval.
    2. Re-anchor any later edit that anchored on P44 text (vendor check names it).
    3. Add a `P46` PATCH_NOTES row (D452, prompt-changing per D249: the net rules); the row grows in later steps.
    4. Delete E29 from port_j2_ui.py and its mirror rows (test_port_edits.py:71, :185-187); fix the count at :18; re-port: `scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <the page's pin, port_j2_ui.py header>`.
    5. test_engine_vendor.py: id list `range(1, 47)` minus 6, 13, 20, 36-40, 44, 45 (P32 still in until T5); marks: drop `P44`, add `"P46": ("j2.py", "def real_run_hosts_problems(rr)")`; docstring sentence for P44 retired and P46.
  - Tests: delete the R2 tests of impact.md §4 (test_p44_* at 4616-4860, 4948-5041, 5053-5071 that test naming, asking, offline). Rename and keep: `test_p44_host_format_refused_and_accepted` → p46 (AC-17), `test_p44_the_real_run_gets_exactly_the_hosts` → p46, `test_p44_real_srt_takes_the_hosts_and_still_refuses_others` → p46 (AC-19, network half), `test_p44_rerun_and_install_keep_their_network`, `test_p44_proxy_settings_are_refused_with_or_without_hosts` (AC-18), `test_p44_rules_join_with_tools_and_runner`, the two `unparsed` tests (AC-24). New: AC-10 (`offline` neither needed nor stored), AC-16 (an unnamed host registers, no question, srt settings hold it).
  - Done when: regenerate; vendor check ok; patch tests, vendor tests, `scripts/py -m pytest tests/ui/test_port_edits.py -q`, `scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <pin> --check` pass
  - Covers: FR-11, FR-19, FR-20, FR-21 (network), FR-22 (net rules), FR-23, FR-29, FR-4 (E29), FR-38 (part)

- [x] T4: The two rules that existed only for the dry run go
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_patches.py`, `tests/engine/test_engine_legacy.py`
  - Change: P46 edits delete the folder-argument rule in `real_run_problems` (j2.py:731-737) and its docstring's last sentence; delete `_real_path_leak` (j2.py:11188-11196), its two callers (:11096-11097, the `leak` lines at :11134-11137 and the `leak` variable), `real_paths_in` and `real_folders` (:777-800). P28's `real_path` failure kind: drop it from the P28 note if nothing else sets it (grep `"real_path"`).
  - Tests: AC-11 (no folder argument, registers), AC-12 (a built file holding the real folder path is neither refused nor rebuilt). Delete tests of those two rules; legacy J2 flow blocks on them (`dry_run_real_folders`, impact §4) skipped with "D452: the rule existed only for the dry run".
  - Done when: regenerate; vendor check ok; patch tests and vendor tests pass
  - Covers: FR-12, FR-13

- [x] T5: No dry run; the real run's own before/after diff is checked against `expect` (P32 retired; P31, P33, P35, P41 amended)
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_patches.py`, `tests/engine/test_engine_vendor.py`, `tests/engine/test_engine_legacy.py`
  - Change:
    1. Delete every `Edit("P32", ...)` and its note. Change P35 and P41 edits in place so no `new` text holds `real_run_dry`, `fence`, `deny_read`, `dry_secret_files`, `reads_changed`, `real_changed` or placeholder lines. P46 deletes J2's own `real_run_dry` (j2.py:1092-1135), the `fence` branch of `real_run` (:912-918), `real_runs_dry` (:3978).
    2. In `_ask_real_run` (still the card in this step): no dry run; the card keeps the command, folders, settings and the RUN line only. On the approved run in `_identity_real_run`: `before = _tree(realpath(folder))`, run, `diff = _tree_diff(...)`; `mm = expect_mismatch(rr["expect"], diff)` when it ran and exited 0; on `mm` no Audit call, items NEEDS_REVISION with "not what it said it would do: <mm>", the row's `audit` key carries it per item, `real_runs_done[wid] = False`; else P33 with the prompt line `WHAT THE RUN DID TO THE FOLDER: <diff>`. Row: drop `dry_run`.
    3. `_dry_run_failed` → `_real_run_back(w, detail)`: failure `["real_run_setup", detail]`, no row, no `dry_run_output`, `dry_failure` → `setup_failure`; info line "Sent back to the builder: <detail>"; Adaptation reason without "dry run" or "copies". `_item_states` (j2.py:11275-11282) reads `"real_run_setup"` in place of `"dry_run"`. Delete the builder brief's `dry_run_failure` (j2.py:10514-10518).
    4. Notes P31, P33, P35, P41 say only what they still do; test_engine_vendor.py: drop P32 from the id list and marks; P41's mark becomes `def real_run_env_problems`, P31's `def home_expanded`.
  - Tests: delete the R3 tests of impact.md §4. Rewrite: `test_p35_expect_mismatch_missing_and_unexpected` (pure, kept); new AC-9, AC-14 (mismatch: NEEDS_REVISION, no `audit` LLM call, row `audit` holds it, no `created`/`changed`/`deleted` keys), AC-15 (prompt holds the real diff, no "DRY RUN"); `test_p41_real_srt_*` that read a placeholder → deleted, the others kept (AC-19 write half: a write outside the folder is refused). Legacy blocks `real_run_dry`, `real_run_checks` skipped with "D452: no dry run".
  - Done when: regenerate; vendor check ok; patch tests and vendor tests pass; `SUTRA_SLOW=1` vendor tests pass
  - Covers: FR-9 (wording), FR-10, FR-14, FR-15, FR-16, FR-17, FR-18, FR-21 (filesystem), FR-30, NFR-4, NFR-5, NFR-8, FR-38 (part)

- [x] T6: Packages install without a question (P42 amended)
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `sutra_app/engine/runenv.py` (docstring lines 7-9 only), `tests/engine/test_engine_patches.py`, `tests/engine/test_engine_vendor.py`
  - Change: P42 edits: `_env_ask` + `_identity_env_install` → `_env_install(w, cwd)` per architecture.md "Interfaces"; callers at j2.py:11098 (`reused, evidence = None, bad`) and :11145 (`evidence = bad; continue`); delete `w["resume"]` (:11094, :11108-11116, and the setters), the `real_runs_asked["env:..."]` code, the `"env_install"` dispatch; `env_install` row per spec FR-28; `env_missing`/`_run_env` say "not installed yet"; one info line naming packages and folder. runenv.py docstring: code installs with no question (no `RUN <code>`, no dry run). Vendor test mark `P42` → `def _env_install`.
  - Tests: rewrite `test_p42_*` (4195-4355): AC-6 (installed once, no pause, row keys exactly FR-28's), AC-7 (pip error to the builder; same hash not installed again), a cached environment is reused, AC-8 import check still sends back without "dry run" in any message. The runenv-equals-J2 comparison test still passes.
  - Done when: regenerate; vendor check ok; patch tests and vendor tests pass
  - Covers: FR-7, FR-8, FR-9, FR-28, FR-34 (runenv)

- [x] T7: The real run runs unasked, once per workflow id; gate keys leave the row; E28 deleted, E31 added
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/j2_artifacts.py`, `sutra_app/engine/VENDORED.md`, `scripts/port_j2_ui.py`, `sutra_app/ui/pages/j2_ui.html`, `tests/ui/test_port_edits.py`, `tests/engine/test_engine_patches.py`, `tests/engine/test_engine_vendor.py`, `tests/engine/test_engine_legacy.py`, `tests/engine/test_engine_views.py`, `sutra_app/library/records.py` (comment)
  - Change:
    1. P46 (and P31/P33 in place): `_ask_real_run` + `_identity_real_run` → `_real_run_next(r)` and `_ran_real_run(wid)` exactly as architecture.md "Interfaces" steps 1-10; `_goal_done` (j2.py:7331) and the audit path (:7595) call it. Delete `real_runs_asked`, `REAL_RUN_DECLINE`, `PAUSES["real_run"]`, `real_run` from `AUTO_ASK` and `DECISION_PAUSES`, the `"real_run"` dispatch, snapshot `paused.code` (:4455-4456), `real_run_env_lines` (Q-7), the card. `_real_run_answer`: "<wid>: ran, <evidence>" or "<wid>: did not start, <evidence>"; none: "none yet: code runs it once the rest is workable". P30's real-run evidence (:11358-11363): "its real run exited 0 and Audit passed its output" / "its real run did not pass". Row exactly spec FR-27.
    2. P46 edit on `j2_artifacts.py:775`: drop `"approved"` from the tuple.
    3. port_j2_ui.py: delete E28a, E28b (and their mirror rows :71, :181-184); add E31 (architecture.md "Interfaces") and its mirror row; count at :18; re-port.
    4. records.py:351-352 comment names `_real_run_next` and `_env_install`.
    5. Vendor test marks: `P46` → `def _real_run_next`.
  - Tests: delete the R1 tests of impact.md §4. New/rewritten: AC-1, AC-2, AC-3 (incl. `AUTO_ASK == {"send_confirm", "limit"}`), AC-4 (Decide for me on: runs once), AC-5, AC-23 (exact keys), AC-29 (follow-up via `rehydrate`: a row for W-1 → `real_run` not called; no row → called once), P33 tests that asserted `r["approved"]` assert `"approved" not in r`. test_engine_views.py: `/api/artifacts` lists an old row (`approved: false`, filled `dry_run`) and a new row without error. Legacy `run_for_real`, `real_run_order` blocks skipped with "D452: no approval".
  - Done when: regenerate; vendor check ok; patch tests, vendor tests, `scripts/py -m pytest tests/ui/test_port_edits.py tests/engine/test_engine_views.py tests/ui/test_dept_page.py -q`, port `--check`, `node --test tests/ui/js/result_view.test.js tests/ui/js/page_render.test.js` pass
  - Covers: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-27, NFR-6

- [x] T8: A run never ends "Done:" while a required real run has not passed
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_patches.py`
  - Change: P46: `real_run_why = {}` in the state init (beside `real_runs_done`), set by `_real_run_next` step 8; `_real_run_open()`; `_goal_done` outcome (replace j2.py:7351-7356 and delete the P44 "Left out" lines if any remain); `_ship_outcome` (:4411) uses `_real_run_open()` in place of `_real_run_pending()`; `_write_summary` (:13795) net. All per architecture.md "Outcome rules".
  - Tests (first): `test_p46_no_done_without_the_required_real_run`, parametrized (a) exit 1, (b) expect mismatch, (c) workflow sent back by FR-9 then finish as it is (`_ship_outcome`), (d) exit 1 with `run.audits = []`, (e) the failing item accepted as is by the Requester: each outcome starts "Done with open items:" and names the workflow and the reason, and `summary.json` `status == "done_with_open_items"`; plus a passing run → "Done:"; plus a replacement whose run passed after a failed one (follow-up) → "Done:".
  - Done when: regenerate; vendor check ok; patch tests pass; `scripts/py -m pytest tests/engine/test_engine_views.py -q` passes
  - Covers: FR-40

- [x] T9: An answer can confirm a real-run item (P43 trimmed)
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_patches.py`
  - Change: delete the P43 edits behind j2.py:7061-7076 (`rr2`, `held`, "Noted. This part is checked ...", the appended sentence). Keep `picked` (:5436-5438, :5591, :9085-9092) and `named_whole`. P43 note says only what it still does.
  - Tests: delete `test_p43_an_answer_never_confirms_a_real_run_item`; add AC-20; keep `test_p43_an_answer_still_confirms_an_item_that_is_not_real_run`, the pick tests (AC-21), `test_p31_d448_*`, `test_p41_d448_*`; check `test_p30_a_to_be_confirmed_real_run_item_is_never_blocked` still holds.
  - Done when: regenerate; vendor check ok; patch tests pass
  - Covers: FR-24, FR-25

- [x] T10: Prompt text and the two data files say what code now does
  - Files: `scripts/vendor_j2.py`, `sutra_app/engine/j2.py`, `sutra_app/engine/agents/j2/identity.md`, `sutra_app/engine/artifacts/real_run.md`, `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_vendor.py`
  - Change: P46 data edits: identity.md:43 per FR-31; real_run.md:1 per FR-32. P35's `REAL_RUN_EXPECT_RULE`: "exactly what running it on the folder creates, changes and deletes; code compares the result after the run, and a difference fails the items it checks". P41's `REAL_RUN_ENV_RULE`: drop "the Requester sees before approving" and the placeholder sentence. `_real_run_note`: code runs it once when the rest is workable; no approval. `real_run` docstring and the SANDBOX_OFF comment (j2.py:611-613). P46 note lists every prompt it changes (D249).
  - Tests: AC-25 in test_engine_vendor.py: the vendored identity.md, real_run.md, the constants `REAL_RUN_EXPECT_RULE`, `REAL_RUN_ENV_RULE`, `REAL_RUN_NET_RULE`, `SCRIPT_NET_RULE`, `_real_run_note()` of a run with a planned real run, the P33 prompt (captured from a mock call) and runenv.py's docstring hold none of FR-34's phrases (case-insensitive); VENDORED.md's Files table lists P46 for both data files with a vendored sha256 unlike J2's.
  - Done when: regenerate; vendor check ok; patch tests and vendor tests pass
  - Covers: FR-22, FR-31, FR-32, FR-33, FR-34

- [ ] T11: Records: superseded and amended decisions, VENDORED intro, stale comments
  - Files: `docs/DECISIONS.md`, `docs/diagram/decisions.json`, `scripts/vendor_j2.py` (the intro text at :3825 and the docstring at :13), `sutra_app/engine/VENDORED.md`, `tests/engine/test_engine_vendor.py` (docstring at :170-181)
  - Change: append `- Superseded by D452 (2026-11-26): ...` to D434, D435, D449, and to D448 (real-run confirmation part) and D447 (the approval part); an amend line to D436 (Audit reads the real diff), D438 (`expect` checked after the run), D446 (no placeholders). No earlier text deleted. decisions.json labels "(superseded)" / "(amended by D452)". The intro paragraph: P32 and P44 retired by D452 (as P13), P31/P33/P35/P41/P42/P43 described as they now are, P46 added.
  - Tests: none new.
  - Done when: regenerate; vendor check ok; `scripts/py -m pytest tests/test_diagram_decisions.py tests/test_docs.py tests/test_ownership.py tests/test_traceability.py tests/engine/test_engine_vendor.py -q` passes
  - Covers: FR-36, FR-37, FR-38

- [ ] T12: Full run, counts, hand-over
  - Files: `docs/ai/remove-real-run-gates/implementation.md` (new: results, deviations, line counts, what was not verified)
  - Change: none to code. Run, in this order: vendor check; patch tests; `SUTRA_SLOW=1` vendor tests; `scripts/py -m pytest tests/engine/test_engine_views.py tests/ui/test_port_edits.py tests/ui/test_dept_page.py tests/test_diagram_decisions.py tests/test_traceability.py tests/test_docs.py tests/test_ownership.py -q`; `node --test tests/ui/js/page_render.test.js tests/ui/js/result_view.test.js`; then `scripts/gate.sh` in the foreground once the owner has cleared it (if not cleared, say it was not run). Record `git diff --shortstat origin/main -- sutra_app/engine/j2.py scripts/vendor_j2.py scripts/port_j2_ui.py` and `wc -l sutra_app/engine/j2.py` before (6c79a1db) and after (NFR-1, Q-8). Scan `git diff origin/main -- sutra_app scripts` for an added `getenv`, `agent_setting(` name or host literal outside tests (NFR-2, NFR-3). Not run: browser tests unless asked (`SUTRA_BROWSER=1`), desktop tests outside the gate, live smoke.
  - Done when: every command above passes, or each failure is named in implementation.md with its cause
  - Covers: NFR-1, NFR-2, NFR-3, NFR-7, FR-39, AC-27
