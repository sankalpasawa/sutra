# J2 sync 4, lane A (foundation) as built

Branch `lane/sync4-a`, cut from `feat/sutra-pro-j2-sync-4` @ `ca5ac4d8`. Design: `docs/design/j2-sync-4.md` (D136, D140, D143, D145 and 2.1 to 2.4). A1 and A2 are done; A3 (recorders and goldens) is another agent's.

| Commit | What |
|---|---|
| `846d8d7d` | A1: the first vendoring (pin `00efb179`, 207 files), `engine/runlist.py`, P15, the vendor tests. Superseded by A1b. |
| `338f4c6f` | the two library fixture builders take an explicit extraction of `prototypes/j2` (no default path) |
| `7e9ed3a6` | A1b: re-pin to `025e265c` (tree `21c67045`), `j2_studio.py`, 208 files |
| `16f10cd1` | A2: `judge`, `auto_label`, `LateEntry`, `RealizationDoc.late`, `settings.json`, workflow `version` 0, the three schemas |
| `3501a5ba`, `a16ba25b`, `006798d0` | A2 tests: wire, records (strict mode over real runs), host runs in strict mode, Document generics |
| `71858392` | P16: Decide for me merges into `settings.json` instead of replacing the host's file |

## Built

- `scripts/vendor_j2.py`: `BASELINE` and `BASELINE_TREE`; the only source is the extraction of `prototypes/j2` (the header written into `VENDORED.md` names the sutra commit, the tree id and the `git archive` recipe; the older commit ids stay there as history only); `CODE` has 17 modules (`j2_agent_models.py`, `j2_agent_views.py`, `j2_studio.py` added); P1 counts the three lazy `j2_map` imports of `j2_artifacts.py`, rewrites the three flat imports and the `sys.path` insert of `j2_agent_views.py`, and takes the new `j2_studio` import of `j2.py`; P13 is gone; P15 is the data patch on the seed's `library/index.json` (`scrub_seed_index`: exactly six `runs[].library` values that held a home-folder path become `not recorded`, the script holds the pattern and never a path, the patch table names the six lines); P16 (below); `REF_DOCS` gains `agent-views-j2-proposal.md`.
- `sutra_app/engine/runlist.py`: `run_row`, `run_list`, `run_changes`, the bodies P13 held, on `j2.saved_dir`, `j2._read`, `j2._jsonl`. `views.runlist` and `views.changes` call it (the import sits inside those two bodies: the module and the view share a name, and it keeps lane B's half of `views.py` untouched).
- Records (D145 and what the new J2 adds): `MessageMeta.judge` and `auto_label`; a closed `LateEntry` (14 keys) and `RealizationDoc.late` (up to 200, left out of `wire()` when unset); `settings.json` catalogued as an open run object (Decide for me writes it, strict mode refused it as an unknown file); `RegisteredWorkflow.version` may be 0 (below); `docs/schemas/{realization,run_message,workflow}.v1.json` re-exported by `sutra_app.library.export` (`--check`: up to date), family versions stay 1.
- P16: Decide for me saves `{"decide_for_me": X}` to `<run>/settings.json` in two places (`set_auto`, and the start of `_run_safe`), which replaced the file the engine host writes there (its resolved engine settings, `HOST_FILES` in `rehydrate.py`). Both writes now merge into what the file holds; a missing or torn file reads as empty.
- Tests: `test_engine_vendor.py` (rewritten pins), `test_engine_runlist.py` (new, 37 cases), `test_engine_patches.py` (8 cases for P16), `test_engine_host.py` (two strict-records host runs), `test_lib_chat.py`, `test_lib_wire.py`, `test_lib_records.py`, `test_lib_templates.py`.

## Measured

- `scripts/py scripts/vendor_j2.py --source <extraction> --commit 025e265c594564f47a2365874cd5a5cc5d0d20a6 --check`: `208 files, ok` (the manifest has 207 rows: the files minus itself). My own extraction is identical to the coordinator's.
- 55 edits: P1 10, P2 2, P3 1, P4 1, P5 9, P7 6, P8 12, P9 1, P10 3, P11 1, P12 6, P14 1, P16 2; the seed is 157 files, 39 `meta.json`, 32 templates, 39 versions, 8 runs, unchanged by the re-pin.
- Anchors against the first pin: one failed, `j2_artifacts.py` P1 (`import j2_map`: 3, not 2). Against `025e265c`: one failed, the P1 import block of `j2.py` (it now names `j2_studio`); of the 53 edits that existed, 32 moved lines (`j2.py` by 1 to 11 lines before `saved_snapshot`, 15 to 29 through the `J2Run` constructor, 83 after it; `j2_realization.py` P7 by 2) and match unchanged.
- `build_artifact_cases.py` run in scratch space against the pinned extraction writes a `cases.json` byte-identical to the committed one: J2's models, rules, renderers and error lines did not change. Only the reference copies of the five generics and four stored templates differ, and they stay (the library rebuilds exactly that J2 file).
- Probes (scratch, not committed): a full mock run with realization on and `J2_FORCE_AUDIT_FAIL=1` gives one late entry ("Fix item 1", revises W-2, 1 judge call, score 0.95); every file and chat line of it passes `gate_record` in strict mode after A2 and, before it, three things were refused: `late`/`judge`, `settings.json`, and `workflows.json` (the Plan workflow's `version: 0`).
- Last run of the lane's set (library, vendor, runlist, patches, host, ownership, extraction available): 2574 passed, 4 skipped (live CLI tests, `SUTRA_LIVE=1`), 0 failed. All of `tests/engine` before P16: 11 failed, all goldens or snapshot-key pins (list below).

## Deviations from the design, and why

1. Pin: `025e265c`, not `00efb179` (coordinator, after `main` moved): 208 files, 17 modules, one more patch (P16).
2. The header has no "equals J2's own repository" sentence and no `UPSTREAM_J2` constant (owner rule: one source, `prototypes/j2`); the older commit ids are history.
3. Strict mode needed more than the two record changes of 2.4: `auto_label`, the `settings.json` route, and `RegisteredWorkflow.version` >= 0. J2 gives the Plan workflow of a realization run `version: 0` and the model demanded 1, so strict mode refused `workflows.json` for every run with realization on (the default); log mode only traced it. The analysis called the complaint pre-existing; the design's own strict test cannot pass without the change.
4. `docs/schemas/run_message.v1.json` and `workflow.v1.json` are re-exported too (the exporter writes every family; the first embeds `MessageMeta`).
5. "A registered late row keeps `judge`": `registered_from_j2` copies named keys only, so `judge`, `stage_from` and `certainty_from` are not in the library's workflow; the row is accepted and keeps `stage`, `version`, `revises`. The test pins that.
6. The Document generics load through the library's closed `GenericTemplate` with `schema_sha` and `render` set aside (no library model has `render`). J2's `sha` equals the library's own.
7. P16 replaces the number D145 reserved for a late-judge switch (that one would be P17).
8. `build_view_cases.py` cannot be re-run from an extraction of `prototypes/j2`: the saved runs it reads are not in it (it now says so). Its output `view_cases.json` is committed.

## Left, for others

- A3: re-record the goldens and `api_shapes.json` against the new tree. Red now, all by recorded data: `test_engine_fn_golden` (3), `test_engine_prompts` (`brewlab_fixes0`, `realization`, `test_a_changed_role_file_is_seen`), `test_engine_views` live, saved and idle shapes (3). `test_engine_views.py::test_live_state_builds_the_snapshot_and_the_live_dict_of_a_run` and `::test_idle_snapshot_has_the_keys_of_a_fresh_j2_snapshot` pin the snapshot's key count (56, now 59: `decide_for_me`, `auto_answers`, `studio`): lane B's file.
- Lane B: `EngineSettings.decide_for_me` (the host exports only the engine settings it knows, so a task setting `J2_DECIDE_FOR_ME` never reached J2; `test_a_decide_for_me_run_...` sets the environment variable and asserts the host's dump keys survive and `decide_for_me` is true).
- Lane G: `docs/design/j2-sync-4.md` still says pin `00efb179`, 207 files, 16 modules, P1 to P15; D136, D145 (P16 now taken), 2.1 and 6.2 step 3 need the new numbers.
- Stale `J2_MODULES` lists (they reset the fresh import of J2) remain in `test_engine_views.py` (lane B), `test_engine_library_lock.py`, `test_engine_rehydrate.py` and `test_engine_fn_registry.py`; the two of my lane (`test_engine_host.py`, `test_engine_patches.py`) are fixed.
- `docs/reference/j2/SETUP.md` is a byte copy of J2's own setup guide and still has the line `git clone ... .git` of the earlier repository (J2's own words, 2 lines). Leave it, or stop vendoring `SETUP.md` (`REF_TOP`): the owner's call.
