# J2 sync 5, lane V: the vendoring (note)

_Lane V of `docs/design/j2-sync-5.md`. Branch `lane/s5-v`. Paths relative to `sutra-pro/`._

## What was built

- `scripts/vendor_j2.py`: pin `1d537295eb11cb034956fa9d8a4026eaa1e3f44e` (tree `30c71fea4679716c9f48d297ee4b2c3463eeebfd`); `j2_types.py` in `CODE` (18 modules); `conditions/` and `templates/` copied as whole trees (`TREES`, only `templates/README.md` excluded); P1 as one counted rule (`apply_p1`, `P1_COUNTS`, 40 lines); repaired P7, P8, P9, P12, P14; P2's third edit; new P17 and P18; `PATCH_NOTES` P1 to P18; `--check`: 229 files, ok.
- The vendored tree, `VENDORED.md` (patch table P1-P18 with line ranges, file hashes), `llm.py` (`timeout`, `CallTimeout`, `can_read_files`), `paths.py` (`DataPaths.types_dir`, `J2_TYPES_DIR` in `j2_env()`), `features.py`.
- Goldens by the recorders: seven prompt goldens and the API shape golden.
- The legacy scripts by three-way merge, `EXPECTED.json`, `scripts/j2_diff_of_record.py` exclusions.

## Patch verdicts (final)

| Patch | Verdict |
|---|---|
| P1 | conflict fixed: counted rule, 40 lines (j2.py 14, j2_agent_views 4, j2_artifact_models 2, j2_artifacts 5, j2_change 2, j2_map 2, j2_realization 2, j2_rules 1, j2_story 2, j2_template_lib 4, j2_types 2); the `sys.path` insert of `j2_agent_views.py` is an anchor edit |
| P2 | applies, extended: third edit `j2_types.AGENTS_DIR` |
| P3, P4, P5, P10, P11, P15, P16 | applies (no anchor changed; P15 still finds exactly six home paths) |
| P7 | conflict fixed (the `call` loop: same arguments through `_ask(...)`, the loop, event and second-stop `raise` untouched); plus one addition not in the design, see Deviations |
| P8 | conflict fixed (run-end anchor `timing.json` / `status = "waiting"` / `def timing`) |
| P9 | conflict fixed (`self._builder_for(fn)`) |
| P12 | conflict fixed (two anchors: `import os/re/shutil`, the `CHROME_PATH` tuple) |
| P14 | conflict fixed: `(self.out or {}).get("single")` |
| P17 | new: local type store (`J2_TYPES_DIR`), atomic write, exclusive lock, busy lock is a `ValueError` |
| P18 | new: `HOST`, `register(entry, extras=None)`, `_read_types`, `template_path` (absolute), `load` extras, `templated` |
| P6, P13 | none; P19 reserved |

## Deviations from the design

1. P7 gets one more edit (the design did not list it): `_plan_stages` now makes the `_deliverables` planner call before Adaptation's first turn, outside `_dispatch_turn`, so its planner and judge calls carried no function and step 0 (a usage row with an empty `fn`). The call is wrapped in `llm.tagged(function="adaptation", step=2, ...)`. `test_p7_the_planner_and_the_judge_inherit_the_function_of_the_turn` pins it. Lane E's usage-ledger tests see `adaptation`/`J2.b` on those rows.
2. `features.py`: the design says drop `detect_documents` and `export_prd`; `PRD_BUILDER`, `HLD_BUILDER` and `LLD_BUILDER` are gone from J2 too, so they are dropped as well and `_builder_for` is named instead.
3. `record_fn_golden.py` takes no `--source` or `--commit` (it records the engine itself); it only gains `j2_types` in its module list. It cannot record before lane E's capabilities change (see below).
4. `EXPECTED.json` keeps `j2_flow_test_sha256` as the hash of J2's own file (the pin test needs it to recognise the extraction) and adds `legacy_flow_test_sha256` (the merged copy) and `known_upstream_failures`.
5. The legacy copy: the engine port of the new blocks (sibling imports to `sutra_app.engine`, `page_file` for J2's page, `types.json`, `j2_template_lib.py` CLI, the N6 fixture and `j2_types.py --promote`, `server_run_list()` and a `server_docs_view()` helper for J2's `j2_server.run_list` and `docs_view`, which the adapter does not carry, J2's `git check-ignore` of the local store dropped because P17 keeps the store outside the package, J2's provider internals in `builder_time_limit` replaced by the same checks of the shim) and six more blocks in the `skippable` list (`deliverables_generic`, `forms_and_new_types`, `local_types`, `types_constants`, `generic_source`, `n6_sources`).

## Golden explanations

All seven prompt goldens changed; in every one the call count, order of functions, outcome, spend and site hash are unchanged (28, 29, 24, 17, 73, 24, 25 calls). The system hash changed in every call of every scenario but one call of `agent_answer` (J2 changed `team.md`, `builder.md` and `adaptation.md`; `team.md` is in every system prompt) and the prompt hash in all but one call per scenario (the builder inputs, the document and page forms' plan text, `DOC_NOTE`, the types list). The deliverables planner call is not a logged call, so it adds no row. The shape golden: `runs[].label` and `form`; `output_info` gains `generic`, `page`, `types` (`types` is now a `*` map: its keys are data, `MAPS` gained `types`); the deliverables group items gain `type` and `why`; workflows gain `kind` and `atoms[].results[].actual.dense`; `/api/docs` is `{}` for a website run (the old `prd`/`hld`/`lld` keys are gone). `fn_atoms_brewlab.json` and `run_events.jsonl` are NOT re-recorded (lane E needed).

## Measurements

- `vendor_j2.py --check`: 229 files, ok. `record_engine_golden.py --check` and `record_api_shapes.py --check` (extraction, full commit): up to date.
- Vendor, patch, library-lock, shim, paths, features tests: 350 passed, 2 skipped. `test_engine_prompts.py` with `SUTRA_J2_CHECKOUT` and `SUTRA_SLOW=1`: 31 passed. `change_test.py` 192 checks, `realization_test.py` 98 checks (both passed in a clean child process).
- `j2_flow_test.py --fast` in a scratch copy with lane E's registration stubbed and every block run through `_try`: the only failing blocks are the E-dependent ones (`timing_records`, `run_list_local_type`, `deleted_local_type`, `page_type_from_data`, `artifacts_tab`, `docs_views`, `docs_tab`, `fresh_page_run`, `missing_run_endpoints`, `prd_page`, `decide_for_me`). Ok lines: 93 without the extraction, 131 with it (the minimums in `EXPECTED.json`; they rise when those blocks pass).
- `j2_diff_of_record.py` classification: 313 source files, 0 undecided; `--check` still exits 1 because the generated page check (`port_j2_ui.py --check`) differs until lane U's regenerated page is merged.

## What other lanes and the integrator must know

- Lane E: `capabilities.register` and `project.py` read `j2.PRD_CHARTER_FMT`, `j2.PRD_ATOM_RULES`, `j2.OUTPUTS`, all gone: every import of `views.py` (so `j2_server`, the legacy script, `record_fn_golden.py`) fails until E1 lands. The eleven blocks above need E's views, runlist rows (`label`, `form`), docs shape and `/api/timing`. After E merges: run `scripts/py scripts/record_fn_golden.py` (writes `fn_atoms_brewlab.json` and `run_events.jsonl`), then `SUTRA_J2_CHECKOUT=$J2SRC SUTRA_SLOW=1 pytest tests/engine/test_engine_legacy.py tests/engine/test_engine_prompts.py tests/engine/test_engine_fn_golden.py`.
- `j2_types.register` is used from `capabilities.register(j2)`; `HOST` is process-local; `J2_TYPES_DIR` is read when `j2_types` is imported (export it before the first import).
- `docs/notes/J2-DIFF-OF-RECORD.md` was regenerated at the end of lane V; the integrator regenerates it once U is merged (the port check then passes).
- `VENDORED.md` is regenerated by `vendor_j2.py`; do not edit it.

## Decisions (text for `docs/DECISIONS.md`)

## D160 — The pin moves to J2 `cut-off/2026-11-12` (`1d537295`); the source stays the extraction of this repository's `prototypes/j2`
- Sources: D136, D154, the owner's handoff for this sync, `docs/design/j2-sync-4.md`.
- Decided: `scripts/vendor_j2.py` takes `BASELINE = 1d537295eb11cb034956fa9d8a4026eaa1e3f44e` and tree `30c71fea4679716c9f48d297ee4b2c3463eeebfd` (`git rev-parse <commit>:prototypes/j2`), `VENDORED.md` names it as "sync 5", and the sync 4 pin becomes history next to `9200cf6` and `33aeeda`. The extraction is made with `git archive`, never from the working tree. The 38 later commits of main (auto-reuse, run templates) are not vendored: they are a later sync.
- Why: the owner asked for exactly this tag; a tag is a fixed point, main moves under the work.
- Rejected: vendoring main (it holds features nobody designed for); vendoring the tag from a git checkout of the working tree (an edited file would be vendored silently).
- Diagram: label "J2 pin: cut-off 2026-11-12", pill on band:DEPARTMENT RUNTIME.

## D161 — The vendoring script copies types as data: `templates/**`, `conditions/*.json`, `artifacts/types.json`; it names no type
- Sources: D13, D136, `docs/design/j2-sync-4.md` (the lists `CONDITIONS` and `GENERIC_TEMPLATES`).
- Decided: `CODE` gains `j2_types.py`. `CONDITIONS` and `GENERIC_TEMPLATES` are replaced by tree copies of `conditions/` and `templates/` (all files, byte for byte), minus `templates/README.md`. Exclusions are named, each with its reason, in `scripts/j2_diff_of_record.py` (which must still report 0 undecided): `templates/README.md`, `tools/check_deliverables.py`, `tools/check_doc_plan.py`, `fixtures/n6-sudoku-*`, `docs/word-matching-followups.md`. The seed library is already a tree copy (`library/`). The sync 5 tree adds 18 type text files (`builder.md`, `atom_rules.md`, `charter.txt`, `intake.md` for `prd`, `hld`, `lld`, `document`, and `charter.txt`, `intake.md` for `website`), `conditions/document.json`, `templates/business_report/generic.json` and `j2_types.py`.
- Why: a list of type folders in the script is a list of type names in app tooling; the next type J2 adds must arrive by a re-vendor with no script edit.
- Rejected: extending the two tuples by hand (the next sync breaks the same way); copying `docs/word-matching-followups.md` (a working note of J2's, not an engine file).
- Diagram: label "types vendored as data", pill on band:DEPARTMENT RUNTIME.

## D162 — Patches P1 to P16 are accounted for; P17 and P18 are new; P14 gets a guard; P19 is the new reserve
- Sources: D13, D136, D145, section 4 of `docs/design/j2-sync-5.md`.
- Decided: verdicts, recorded in `VENDORED.md` and in `scripts/vendor_j2.py` `PATCH_NOTES`: applies P2 (extended to `j2_types.AGENTS_DIR`), P3, P4, P5, P10, P11, P15, P16; conflict fixed P1 (a counted rule instead of anchors: 40 lines), P7 (the `call` loop with `timeout`), P8 (the run end), P9 (`_builder_for`), P12 (the `keyword` import, the Chrome tuple), P14 (`(self.out or {}).get("single")`); none for P6 and P13 (retired); new P17 (local type store) and P18 (host type registration). The reserve of D145 for a late-judge switch moves from P17 to P19.
- Why: every changed anchor is explained by the J2 change that moved it; P14 would crash on a run with no type; the reserve number was only ever a placeholder.
- Rejected: dropping P14 (the project output needs it, finding 2 and section 5); keeping P17 for the late judge (a number reserved for a switch nobody asked for would block the patch that is needed now).
- Diagram: label "patch table P1-P18", pill on band:DEPARTMENT RUNTIME.

## D163 — Types a run makes are kept per user in the data folder, under a lock (patch P17)
- Sources: D26 (the one global library lives under the data folder), D144, J2's `j2_types.create`.
- Decided: `DataPaths.types_dir` is `<data>/types`; `DataPaths.j2_env()` exports `J2_TYPES_DIR` with it; the API process exports it before it first imports J2. P17 puts `types.local.json` and the local templates there and serialises `create` with an exclusive lock on `<data>/types/.lock`. Local types are not shipped, not part of the package, and shared by every team of the user (J2's own meaning of "local"). A busy lock is a `ValueError` that J2 already turns into a refused-type event.
- Why: the installed package is read-only and shared; two runs creating types at once must not lose one; a user's types are the user's data (backup, uninstall).
- Rejected: leaving the files in the package (fails in the installed app, leaks between users); one store per team (J2's planner lists every type for every run; per-team stores would hide a type the user already made); a Sutra-side copy of `create` (a second implementation to keep in step).
- Diagram: label "local types in the data folder", pill on band:DEPARTMENT RUNTIME.

## D170 — The `llm` shim carries `timeout`, `CallTimeout` and `can_read_files`
- Sources: D13, J2's `llm.py`, `CompletionRequest.timeout_s`.
- Decided: `llm.ask(..., schema=None, timeout=None, *, tag=None)`: `timeout` becomes `CompletionRequest.timeout_s` (the router already honours it and cuts it to the envelope's deadline); a `ModelError` with code `timeout` is re-raised as `llm.CallTimeout(RuntimeError)` so J2's `except llm.CallTimeout` works; every other error is unchanged. `llm.can_read_files()` returns `False`: the agents' file tools are bound to the owner's working folder, never to a run folder, so J2's "read the rest at <path>" hint would point at nothing. `READS_FILES` is not defined.
- Why: the new P7 text and J2's builders call all three; the port of J2's contract belongs in the one shim.
- Rejected: `can_read_files()` true when the working folder is on (the cut text lives in the run folder, outside the agents' reach).
- Diagram: label "llm shim: timeout", pill on band:DEPARTMENT RUNTIME.

## D174 — Goldens move only through the recorders; the legacy flow test is a three-way merge
- Sources: D150, R5, `docs/notes/J2S4-l.md`.
- Decided: all seven prompt goldens are re-recorded (each differs: the page and document forms' plan text, the deliverables planner call, `DOC_NOTE`, the builder inputs; the lane note says why for each); the function-node goldens and the API shape golden are re-recorded from the extraction with `--source` and `--commit` (the shape recorder reports `types` as a `*` map: its keys are data); the legacy flow test is `git merge-file` with base = J2's `j2_flow_test.py` at `025e265c`, ours = Sutra's copy, theirs = the extraction (the same for `realization_test.py`, `change_test.py`, `j2_replay_size.py` where Sutra edited them); the three known upstream failures (`map_focus`, `graph_map`, `warm_ui`) are wrapped by `known_upstream_failure` inside `skippable` (a failure of one of the three ends the block with the printed reason "known upstream failure at cut-off/2026-11-12"; a fourth failing block fails the script), and `EXPECTED.json` records the pin, the sha256 of J2's file and of the merged copy, the new minimums and the skip lines. At the pin, in this harness (an extraction: no saved runs, no Chrome) the three do not fail: `graph_map` stops at "no saved runs" and `map_focus` and `warm_ui` print their ok line, so the wrapper is latent here and active in a J2 checkout with saved runs.
- Why: R5 allows goldens to move only through recorders; the known failures are upstream's, to be sent to J2's maintainers, not fixed here.
- Rejected: editing a golden by hand; fixing the three upstream blocks in the copy.
- Diagram: label "goldens by recorder only", pill on band:DEPARTMENT RUNTIME.
