# J2 sync 6 as built: Sutra Pro 0.5.0 takes over J2 main `1adb8ecd` (note of record)

_Status: As built, release 0.5.0 (not pushed, not tagged) · Date: 2026-11-13 · Pin: commit `1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb`, tree `9a7cb34c028248de7d3b436647f8baf39be6f77e` · Branch `release/0.5.0` = lanes V, L, E, U merged, then the integrator._

This section is the note of record. The design as proposed follows it unchanged, below the line "Design as proposed". Decisions D176 to D193 are in `docs/DECISIONS.md` in their as-built text (D182 with the route's amendment), D194 to D200 are the shared-library design (`docs/design/shared-library.md`). The lane notes `docs/notes/J2S6-{v,l,e,u}.md` hold the detail.

## A. What was built

- **V** (vendoring): tree of 516 files at the new pin (`sutra_app/engine/seed` 437 files, `templates/` 25 with `library-settings.json`, 19 code modules with `j2_artifact_lib.py`); patches re-anchored and extended; the four recorders pin `J2_RUN_BY=sutra-pro` and `J2_PUSH_RUNS=0`; goldens re-recorded (seven prompt goldens differ in `j2_commit` only); the legacy flow test is a three-way merge with 0 conflicts and 11 new J2 blocks.
- **L** (library): `reuse.json` row and closed models for the new run files and keys, `RunHeader`, `RunTemplateBundle`; the seed sync adds run templates, their folders and provenance keys, additive. Measured on the 0.4.0 seed: 81 families, 107 versions, 4 run templates, 437 files, nothing lost.
- **E** (engine): five settings (`run_templates`, `auto_reuse`, `artifact_library`, `reviewer`, `reviewer_wait`), `effective()`, `J2_PUSH_RUNS`/`J2_RUN_BY` fixed by the host, the reviewer join with cap (P19), the `say` carrier (two task-only keys), the follow-up rule, the hard-coded cleanup (`forms.py`, the two data files, lazy reads of J2 in the function-node registry), two new feature chips.
- **U** (views and page): `GET /api/run-template`, team-scoped Artifacts shelf, `POST /api/say` with `template` and `workflows`, the regenerated page (40 edits), the Engine settings page (37 rows), route pins at 43 handlers and 35 exact paths.
- **Integrator**: shared documents, `decisions.json` (D1 to D200), traceability (200 decisions, 43 endpoints, 17 chips), the version, the verification list of section 9 (results in F).

## B. Deviations from the design (from the lane notes)

1. **Settings answer** (E): the existing key `effective` stays (the stored values, resolved); the implied values are the new key `effective_flags`. The page reads `effective_flags` (`impliedOf` in `settings_view.js`).
2. **Form check at registration** (E): `forms.check_forms(j2_types)` is called by `capabilities.register(j2)`, not at import; the host imports capabilities before it exports J2's environment.
3. **Reviewer** (E): a 0.25 s settle after a discard; the excepthook never makes a reviewer failure the run's crash.
4. **Guard `PENDING`** (E): one pending entry for `views.py`; the integrator removed it (see C).
5. **P1 changes 42 lines, not 41** (V): 40 + 2; `P1_COUNTS` is the script's own count.
6. **Seed index** (V): five `/tmp/...` library values remain next to the six scrubbed home paths; P15 still finds exactly six.
7. **`HANDLER_COUNT` stays a literal** (U): table 8 row 12 asked for a computed value; `test_traceability.py` reads it as text. `ASK_CHARS` stays a copy with a parity test.
8. **`say` limits** (U/E): 40 keys of 20 characters cannot fit 400 characters; the 400-character limit decides.
9. **E20f** (U): one anchor fails at the pin (the Library button is now two); it is E20f1 and E20f2, plus E24a to E24f (D191): 40 edits, 7 files.
10. **`TemplateMeta`, `RunHeader`** (L): also learn the four sync 4 provenance keys; the run header is its own closed model, not a `RunMessage`. `door` of `TemplateDecision` is in the design and was not seen in any mock run.
11. **`scripts/engine_gate.sh`** (V): still runs only the four old legacy scripts; the two new ones run in `tests/engine/test_engine_legacy.py`.

## C. Patch statuses (as in `sutra_app/engine/VENDORED.md`)

| Patch | Status at 1adb8ecd |
|---|---|
| P1 | re-anchored: `CODE` gains `j2_artifact_lib.py`; 42 lines |
| P2, P3, P4, P5, P11, P12, P14, P15, P16, P17, P18 | applied unchanged (P15: six home paths) |
| P7 | re-anchored (the planner expression, one statement) |
| P8 | re-anchored (run-end anchor includes the `_make_report` line) |
| P9 | re-anchored (`call_delay()` in the delay lines of `call` only) |
| P10 | extended: four writers (`store`, `mark_used`, `note_version`, `mark_run_template_used`) |
| P19 | new: the reviewer switch (`review_enabled` hook) |
| P20 | reserved (the late-judge switch of D145) |
| P6, P13 | none: the design's table skips P6; P13 was retired in sync 4 (D140), its code is `engine/runlist.py` |

## D. Not done, and why

- J2's group-A hard-coding fixes: they live on J2's branch `fix-run-blockers`, not in main (D189); they arrive with a later pin.
- Parallel builds, scripts and actions, a "save this run as a run template" owner action, cross-team sharing (the publish gate of D197): later work, see `shared-library.md`.
- A real-model run of `auto_reuse` and the content door (item 8 of section 9): no connector with quota was used; the by-hand check with a real model stays open.
- The memory store and the external catalogue (D196, D199) are designed, not built.

## E. Three open questions for J2's maintainers

1. **Tag.** J2 has not tagged `1adb8ecd`; the pin is the full commit. Please tag it (the tag name is then added to `vendor_j2.py` and `VENDORED.md` as a comment) and review the seven "needs owner review" commits that are carried inert.
2. **The shared-library maintainer.** What does the shared-library maintainer already hold (contract text, seam list, tag policy)? Section 6 and D195 to D200 of `shared-library.md` are drafts for that person to correct.
3. **Inventory fixes on a J2 branch.** The group-A fixes of the 547-row inventory live on `fix-run-blockers`, not in main: should the next pin wait for them, or move to main as it is? The ten reports of section 11 below stay as listed.

## F. Verification as run (integrator)

- Recorders: `vendor_j2 --check` 516 files ok; `port_j2_ui --check` 40 anchors, 7 files; `record_engine_golden`, `record_api_shapes`, `record_fn_golden` current; `capture_j2_fixtures --check` 81 files equal; `j2_diff_of_record --check` PASS. Nothing was re-recorded by the integrator.
- Gate: first run 11,204 passed, 340 skipped, 4 failed; the four were fixed (see G); the affected files then passed five runs in a row. Node 1,261 passed, 2 skipped. Slow suite (`SUTRA_SLOW=1`, with the extraction) 230 passed, 1 skipped. Browser suite 305 passed. The wheel builds as 0.5.0 with the 437 seed files and `templates/library-settings.json`; `check_wheel.py` ok.
- Offline manual checks (stub connector, scratch data folders, HTTP API): (a) flags off: a website brief ends `done_with_open_items` and a PRD brief `stopped`, identical to the 0.4.0 code run the same way (the stub's answers, not a change); no `templates.json` or `reuse.json`; (b) with `run_templates` and `auto_reuse` on: `effective_flags` all true, `GET /api/run-templates`, `GET /api/run-template?id=` (`enabled: true`; 404 for an unknown id) and the catalog (4 run templates, shelves) answer; a `say` with `template` and `workflows: all` writes `templates.json` `run_template` (5 of 5 workflows), the chat line "Using run template Thread: boutique website: 5 of 5 workflows." and a `run_template.requested` trace line; a second brief auto-picks `thread-boutique-website` with a score of 0.94; (c) reviewer on, off and `reviewer_wait` 0: no file of the run folder changed in the 4 to 6 seconds after the run ended; with the reviewer off `calls.jsonl` has no reviewer row; a slow reviewer past the cap cannot be made with the stub (the engine tests do it with a scripted slow reviewer); (d) the 0.4.0 seed copy (32 families, 157 files) with an owner edit, an owner file and an owner family: `config sync-library` gives 82 families (81 plus the owner's), 107 versions, 4 run templates; only `index.json` changed among the old files; a second sync changes nothing; (e) the project output team with all five flags on: the run's `settings.json` has them all false and the `output.selected` trace line lists them under `forced`; it ends `stopped` as on 0.4.0 because the stub has no working folder.

## G. Red tests of the merged tree that belonged to nobody

`tests/test_traceability.py` (42 endpoints and 15 chips: now 43 and 17); `tests/ui/test_fake_backend.py` (the catalog capture has 11 runs, the five `/tmp` library values of the seed, the scrubbed environment has `J2_RUN_BY` and `J2_PUSH_RUNS`); `tests/library/test_lib_wire.py` (a race: the harness read `map.json` while J2's reviewer thread was still writing; it now joins `review_thread`); `views.py` spelled the form word three times, now `forms.DOCUMENT` and `forms.is_document`, and the `PENDING` entry of the type-name guard is deleted. `test_engine_api_scope`, the views shape tests, `record_rejected` for the new keys and `settings_view.js` (reads `effective_flags`) needed no change.

---

# Design as proposed (unchanged)

# J2 sync 6: Sutra Pro takes over J2 main `1adb8ecd` (design and lane plan)
_Status: Proposed · Date: 2026-11-13 · Branch: `lane/s6-library-docs` (release 0.4.0 plus the two library documents) · Source: commit `1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb` of this repository, tree of `prototypes/j2` `9a7cb34c028248de7d3b436647f8baf39be6f77e` · Replaces: the sync 5 pin `1d537295eb11cb034956fa9d8a4026eaa1e3f44e` (tag `cut-off/2026-11-12`) · Decisions: D176 to D193 (written into `docs/DECISIONS.md` by the integrator from the lane notes) · Ships as: 0.5.0 · Companion: `docs/design/shared-library.md` (D194 onward)_

Paths are relative to `sutra-pro/` unless they start with `prototypes/`. `$J2SRC` is the extraction of the new pin: `git archive 1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"` (a new, empty folder, never the working tree; D154). The scratch trial vendoring that the analyst made is a read-only reference for numbers; nothing is copied from it.

The owner's rules, kept as the test of every choice below: one central engine that capabilities enhance, nothing replaced or rerouted; no owner name and no home-folder path in any file under `sutra-pro/` (`tests/test_ownership.py` fails on them); J2's vendored text is byte-identical except numbered patches recorded in `sutra_app/engine/VENDORED.md`; the generated page only through `scripts/port_j2_ui.py`; goldens only through the recorder scripts; "agents decide, code validates": no type names, keyword lists or brief-specific rules in app code. Team members appear below only as roles.

Out of scope, a later sync: J2's group-A hard-coding fixes (they live on J2's branch `fix-run-blockers`, not in main), parallel builds, scripts and actions, a "save this run as a run template" action for owners, cross-team sharing of finished artifacts, J2's `J2_PUSH_RUNS`.

## 1. What this design relied on, and what it corrected

The analyst's findings were re-checked against `$J2SRC`, the vendored tree and the worktree. Verified as stated: 53 J2 commits and 316 files in `1d537295..1adb8ecd` (+33,821/-3,104); the seed grows from 157 to 437 files (0.8 MB to 2.2 MB), from 32 to 81 families, 39 to 107 versions, 8 to 11 runs, with a new top-level `run_templates` key (4 rows) and `library/run-templates/<id>/{template.json,schema.json}`; 67 versions carry `renamed_from` or `adapted_from`; `j2_artifact_lib.py` is new (223 lines, `import j2_template_lib as L`); `P1_COUNTS` is 15 for `j2.py` and 1 for `j2_artifact_lib.py` (checked with the script's own two regexes: 41 lines, 40 today); the four failing anchors are P7, P8, P9 and the P1 rule; `llm` attributes used by J2 are unchanged (`MOCK`, `ask`, `MODEL`, `PROVIDER`, `extract_json`, `LAST_META`, `CallTimeout`, `can_read_files`, all in the shim); the only home-folder paths in the extraction are the six values of `library/index.json` that P15 already scrubs; no personal identifier is in any file of the extraction. Corrections and additions found while checking:

| # | Finding | Consequence |
|---|---|---|
| 1 | `call_delay()` is read in three places of `j2.py` (`_summarize`, `call`, the reviewer call). P9's anchor starts with the `system = system_prompt(...)` line, so it matches only the one in `call`; the other two are not under any patch. | P9's old and new text change by the two `call_delay()` lines only (section 4). `llm.MOCK` makes `call_delay()` return 0 in mock runs, as `DELAY` was effectively 0 there. |
| 2 | The new planner expression `self._run_tpl_start(said) if self.run_tpl else self._deliverables(said)` is one statement. `_run_tpl_start` calls `_deliverables` itself (twice: the whole-template path and the "no buildable type" fallback). | P7 keeps the expression whole inside the existing `llm.tagged(function="adaptation", step=2, ...)` block, so every planner call of both paths is charged to Adaptation by one edit. |
| 3 | `_review_later` skips its save when `gen != self.report_gen` (J2's own "a newer report wins over a late review"). The thread is unnamed (`Thread-N`), the host's `threading.excepthook` treats an exception of a thread whose name does not start with `sutra-` as a crash of the run, and `_save_report` is outside the thread's `try`. | A late write after the host closed its writer could fail a finished run. Join with a cap, then bump `report_gen` so a late reviewer saves nothing (D179). No J2 text is changed for this. |
| 4 | When the reviewer is skipped the only placeholder text J2 has is "Paused for the Requester; the reviewer runs when the run ends.", which would be false at a run end. | The reviewer switch needs one small patch with its own placeholder text (P19, D179). |
| 5 | `host/finish.py` runs its `catalog` step only when `host.settings.template_library` is on. J2 turns the template library on itself when `J2_AUTO_REUSE=1` (and the content door implies auto-reuse). With the new setting on and `template_library` off, templates would be stored by the run and never catalogued. | Implied flags are computed once, by `EngineSettings.effective()`, and the finish step and the project force read that (D178). |
| 6 | The host does `os.environ.update(settings.to_env())` and `os.environ.update(paths.j2_env())`: it adds, never clears. A developer shell that exported `J2_PUSH_RUNS=1` or `J2_RUN_BY=<name>` would reach the engine child. `run_author()` also runs `git config user.name` (5 s timeout) at every run start when `J2_RUN_BY` is unset and writes the result into `chat.jsonl`. | Both are fixed by `DataPaths.j2_env()`, which wins over the inherited environment (D177). |
| 7 | The generated page already has "Use whole template" and "Use selected workflows" links (`rtHref`) that open the start page with `template` and `workflows` and then `POST /api/say` with both. Sutra's `say(text)` has no carrier. Without one the page would start the run without the template and say nothing. | The carrier is in scope (D182). |
| 8 | `catalog_view()` reads Shelf 1 (Artifacts) from `runs_root()` = `J2_RUNS_DIR`. The API process sets only `J2_LIBRARY_DIR` per call, so every team would see an empty shelf; and the docstring of the `catalog` handler ("nothing of the team is read") stops being true. | `_library(ctx)` also sets `J2_RUNS_DIR` to the asking team's runs folder (D184). |
| 9 | `GET /api/run-template` answers `enabled` from the server process's `os.environ` (`J2_RUN_TEMPLATES` or `auto_reuse()`). The API process never has those variables, since the flags live in the team's resolved settings. | The handler reads `enabled` from the team's effective settings (D183). |
| 10 | `match_run_templates(..., live=not llm.MOCK)` makes a mock-made run template ineligible for a live run. Of the four seed run templates two are live-made and two mock-made (`thread-boutique-website` and `still-point-yoga-studio-website`). | The by-hand check offline (stub or mock) can pick the mock ones; a real-model run can pick only the two live ones. Section 9 says which brief hits which. |
| 11 | `eb0d28a7` adds a `section-not-empty` receipt for every section a document workflow owns, using `wf_sections(w, out["sections"])`. The project type (P18) carries `sections` through its template and lists `section-not-empty` in its check types. | No change needed; a test proves a project run still ends Done, and the receipts differ from sync 5 (D190). |
| 12 | `J2Run.rehydrate` restores `RESTORED_CHAIN`; `run_tpl` and `auto_pick` are new attributes of `__init__`. `_auto_reuse_pick` returns at once when `auto_pick is not None`. | A follow-up gets `auto_pick = {}` (J2's own "already decided" marker) and no `run_tpl` (D187). |
| 13 | `sutra_app/library/templates.py` already has a class `RunTemplate` (a row of `GET /api/run-templates`, payload `template.run`), unrelated to J2's new run-template bundle. | The bundle is `RunTemplateBundle`, payload `run_template.bundle` (D186). |
| 14 | `sutra_app/engine/fnodes/registry.py` already imports `j2_check`; the host sets the environment before J2 is imported, and J2 reads some module constants from the environment at import time. | Reads of J2 symbols from the Sutra layer are lazy (first use), never at module import (D188). |

## 2. Approach

One engine, as in every earlier sync. The vendored tree moves to the new pin with the patch set P1 to P19 (P19 is new, P1, P7, P8, P9 are re-anchored, P10 covers two more writers; the reserve of D145 for a late-judge switch moves from P19 to P20). Nothing in the run path is replaced or rerouted: run templates, auto-reuse and the content door are J2's own, switched on by flags that are off by default, so flag-off behaviour is byte-neutral (the analyst's golden comparison: all seven prompt goldens identical except `j2_commit`).

Three things need a Sutra-side design because J2 gives them no place:

1. The flags become **owner-visible settings**, three for reuse (`run_templates`, `auto_reuse`, `artifact_library`) and two for the run report (`reviewer`, `reviewer_wait`). Implications between flags are computed once. `J2_PUSH_RUNS` and `J2_RUN_BY` are fixed values of the host, never settings.
2. **The team scopes the library's runs.** The templates are one global store (D26); the Artifacts shelf and the content door read finished runs, and those are per team. Both read the asking or running team's runs folder, so no team reads another team's finished documents (D184). Sharing across teams is a later, owner-triggered "publish" step with scrubbing (`docs/design/shared-library.md`).
3. **The end of a run is made stable.** J2 now writes `report.json`, `report.md` and `artifacts.json` after the run is "waiting", from a daemon thread. The host joins that thread (capped), then runs the finish steps, then publishes; a reviewer that outlives the cap is discarded by J2's own supersede counter.

The wire changes are J2's own (`GET /api/run-template`, `reuse_rows` and `run_template` on `GET /api/run-templates`, `template` and `workflows` on `POST /api/say`) plus Sutra's `effective` and the five settings. The page is regenerated by the script (one anchor fails, six more edits for new root-absolute URLs). The records catalogue and the closed models learn the new run files and keys. The seed sync learns the run templates. The Sutra-side hard-coded behaviour named in the owner's refactoring task is cleaned in the same release, by rules, not by case (D188).

## 3. Alternatives considered

| Question | Options | Chosen, and why the others lost |
|---|---|---|
| Reuse flags | (a) developer-only environment variables; (b) editable Engine settings, default off | (b). (a) is the D152 mistake: `J2_AUTO_REUSE` in the process environment does nothing in a run, because the host exports only `EngineSettings.to_env()` and `paths.j2_env()`; a variable documented before its field exists is a promise the app does not keep. The page also has the buttons, so the owner needs the switch. |
| `J2_PUSH_RUNS` | (a) a setting; (b) fixed off | (b). It runs `git add`, `commit`, `pull --rebase` and `push` in the folder that holds the run, with the owner's credentials. Nothing in Sutra pushes (the standing rule: nothing is pushed unless the owner says so); the value is fixed to `0` by the host. |
| Reviewer | (a) leave J2's thread alone and fix the tests; (b) host joins with a cap, no switch; (c) join plus a setting plus P19 | (c). (a) leaves usage rows and hook events after `run.ended` and a race the tests already show; (b) cannot avoid a high-effort QA call that costs the owner's quota every ended run and whose notes are about J2's own design; (c) costs one two-line patch and keeps the default as J2's. |
| Reviewer default | (a) on; (b) off | (a). It is J2's behaviour and the goldens stay byte-neutral; (b) would move call counts and spend of every golden for a saving the owner can make with one switch. Revisit when real runs show the notes unread. |
| `say` carrier | (a) out of scope: hide the buttons; (b) a new column and a changed `deliver_to_department` signature; (c) two task-only keys through the existing settings channel | (c). (a) edits the generated page (forbidden) or leaves dead buttons; (b) touches the orchestrator's database and ports for two optional strings. (c) reuses the validated, persisted `settings` dict end to end; the engine's `layered()` ignores keys that are not settings fields, and the host reads the two keys itself. |
| Artifacts shelf and content door scope | (a) every team's runs; (b) the asking or running team's runs; (c) a per-install global shelf | (b). (a) lets team B read team A's finished documents and put team A's facts into team B's prompts (the content door serves text, not structure); (c) is (a). The owner can share deliberately later. |
| Seed sync of renamed families | (a) rename or move the owner's folders to follow J2; (b) additive: add the new family, keep the old | (b). D144 never overwrites or renumbers; J2's resolver already opens an older reference through the row's `renamed_from`. A duplicate family is harmless; a moved folder changes what an old run's `templates.json` points at. |
| Hard-coded behaviour of Sutra's own layer | (a) one big rewrite into settings; (b) three rules applied to a list | (b) (D188). (a) would also move numbers that are not decisions. |
| J2-side hard-coding | (a) patch it in the vendored copy; (b) report it | (b). The owner's rule: no app-side fixes of upstream; J2's group-A fixes arrive by a later pin. |

## 4. Decisions

Numbers continue from D175. Each lane writes the text of its decisions into its note `docs/notes/J2S6-<lane>.md` in exactly this shape; the integrator copies them into `docs/DECISIONS.md` in number order, adds the pills to the diagram key (`docs/diagram/decisions.json`) and records the amendments (D129, D141, D142, D145, D162, D175).

## D176 — The pin moves to J2 main `1adb8ecd`; the source stays the extraction of this repository's `prototypes/j2`
- Sources: D136, D154, D160, `docs/design/j2-sync-5.md`.
- Decided: `scripts/vendor_j2.py` takes `BASELINE = 1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb` and tree `9a7cb34c028248de7d3b436647f8baf39be6f77e`; `VENDORED.md` names it "sync 6"; the sync 5 pin joins the history list. The pin is a commit of main because J2 has not tagged it; J2's maintainers are asked (D189) to tag it, and the tag name is added to `VENDORED.md` when they do (a comment, not a source change). The extraction is made with `git archive`, never from the working tree. Of the 53 commits, the seven labelled "needs owner review" (all `j2.py`, run templates and auto-reuse) are carried inert: every one is behind `J2_RUN_TEMPLATES` or `J2_AUTO_REUSE`, off by default.
- Why: the owner's task is "J2 sync 6"; the commit is a fixed point; the flag-off behaviour was measured byte-neutral.
- Rejected: waiting for a tag (nothing in the app is blocked on a name); vendoring a branch tip (D154); carrying only part of the span (the content door, the shelves and the run templates share `j2_template_lib.py`).
- Diagram: label "J2 pin: main 1adb8ecd", pill on band:DEPARTMENT RUNTIME.

## D177 — The reuse flags are Engine settings; `J2_PUSH_RUNS` and `J2_RUN_BY` are fixed values of the host
- Sources: D129 (settings layers), D152 (an environment variable with no field does nothing), D169, `docs/design/j2-sync-5.md` section 7.
- Decided: `EngineSettings` gains `run_templates`, `auto_reuse` and `artifact_library` (bool, default `False`, editable, env names `J2_RUN_TEMPLATES`, `J2_AUTO_REUSE`, `J2_ARTIFACT_LIBRARY` by the existing rule). The Engine settings page groups them as "Reuse (experimental)" with texts that say what each does and that each is off by default. `DataPaths.j2_env()` exports `J2_PUSH_RUNS=0` and `J2_RUN_BY=sutra-pro`; they are not fields, so no settings file, task key or environment can change them, and the inherited environment is overridden. `docs/ENVIRONMENT.md` documents a variable only in the same commit as its field (the integrator adds the rows when the field has merged).
- Why: J2 only reads its environment, the host is what sets it; the page has the buttons, so the owner needs the switch; a fixed `J2_RUN_BY` keeps the OS or git user name out of `chat.jsonl` and out of the goldens, and removes a `git config` subprocess per run; a pushed run folder is the one J2 flag that writes outside the data folder.
- Rejected: leaving the variables to the environment (D152); exposing `J2_PUSH_RUNS` read-only (a visible field invites the question "why can I not set it"); `J2_RUN_BY` from the owner's name (a personal identifier in run data, R5).
- Diagram: label "reuse flags are settings", pill on band:EXPERIENCE.

## D178 — Implied flags are computed once by `EngineSettings.effective()`; the finish step and the project force read it
- Sources: D142, D164, J2 `j2_template_lib.enabled`, `auto_reuse`, `j2.run_templates_on`, `artifact_schema_on`.
- Decided: `EngineSettings.effective()` returns a frozen `EffectiveFlags(auto_reuse, run_templates, template_library, artifact_schema)`: `auto_reuse = auto_reuse or artifact_library`; `run_templates = run_templates or auto_reuse`; `template_library = template_library or auto_reuse`; `artifact_schema = artifact_schema or template_library` (J2's own chain). The settings are not rewritten: the stored values stay what the owner chose, `GET /api/engine/settings` adds `effective` and the page shows a row that is on only by implication as "on (implied by Reuse earlier work)". `host/finish.py` and every other place that asks "is the template library on" call `effective()`. The project capability's `FORCE` sets `run_templates`, `auto_reuse`, `artifact_library`, `artifact_schema` and `template_library` to `False`, so the whole chain is off for a project run (the host says so in its trace line).
- Why: J2 does the implying inside the run, the app must agree without a second copy of the rule scattered over the code; a project has no template and the content door would serve document text into a working-folder run.
- Rejected: normalising the stored settings (the owner's file would change under them); forcing only `template_library` for project (J2's chain would turn it on again through `auto_reuse`).
- Diagram: label "implied flags: effective()", pill on band:DEPARTMENT RUNTIME.

## D179 — The reviewer: on by default, two settings, a host that waits (capped) and discards a late result; patch P19
- Sources: D142, D143, J2 `_make_report`, `_review_later`, `report_gen`, the analyst's finding on `test_a_classic_follow_up_reaches_done_with_one_more_workflow`.
- Decided: `EngineSettings` gains `reviewer` (bool, default `True`, env name `J2_REVIEWER`, read by the host, not by J2) and `reviewer_wait` (seconds, float, default `120`, `ge=0`, `J2_REVIEWER_WAIT`, `0` = do not wait). `hooks.py` gets `review_enabled() -> bool` (NullHooks true; `EventHooks` reads the setting). P19 (section 5): `_make_report` asks `self._hook("review_enabled")`; only an explicit `False` turns the reviewer off, and the run report then says "The reviewer is switched off in this team's settings." In `Host._conclude`, first after `inbox.close()` and before `publisher.stop()`, the host joins `run.review_thread` (when it exists and is alive) for at most `reviewer_wait` seconds, with the heartbeat and the publisher still running; when the cap passes it increments `run.report_gen`, which makes J2's `_review_later` save nothing, and writes one `finish.step`-style trace line (`reviewer.late`). The finish steps, the final publish and `run.ended` come after. A reviewer call in flight at SIGTERM is cancelled with the model port as today.
- Why: the host decides when a run ended and must make the folder stable before it collects, publishes and closes its writer; the reviewer call is a high-effort QA call about J2's own design that costs the owner's quota; J2 already has the supersede counter, so no J2 text beyond the switch is needed.
- Rejected: leaving the thread unjoined (usage rows and hook events after `run.ended`, a deterministic test failure and a race); a patch that names or joins the thread (J2's text for what host code does); default off (moves every golden's call count); a hidden constant for the wait (it changes when the owner sees "Done", so it is a setting).
- Diagram: label "reviewer: join, cap, switch (P19)", pill on band:DEPARTMENT RUNTIME.

## D180 — P1, P7, P8, P9 are re-anchored; P19 is new; the late-judge reserve is P20
- Sources: D13, D136, D145, D162, section 5 of this design.
- Decided: verdicts, recorded in `VENDORED.md` and in `PATCH_NOTES`: applies P2, P3, P4, P5, P11, P12, P14, P15 (still exactly six home paths), P16, P17, P18; conflict fixed P1 (`CODE` gains `j2_artifact_lib.py`, `P1_COUNTS`: `j2.py` 15, `j2_artifact_lib.py` 1, 41 lines), P7 (the planner expression), P8 (the run-end anchor), P9 (`call_delay()`); extended P10 (D181); new P19 (the reviewer switch). The reserve of D145 moves from P19 to P20.
- Why: every changed anchor is explained by a J2 change; the reviewer switch is the one place where J2 gives the host no seam.
- Rejected: dropping P8's run-end hook (`run_status` is how the host sees a run end); a regex for P7/P8/P9 (an anchor that stops the run when J2 moves is the safety).
- Diagram: label "patch table P1-P19", pill on band:DEPARTMENT RUNTIME.

## D181 — P10 covers the two runtime writers J2 added: `note_version` and `mark_run_template_used`
- Sources: D26, D142, P10, J2 `j2_template_lib.py` (`note_version`, `mark_run_template_used`, `_save_index`).
- Decided: both become wrappers that take `_library_lock()` around the original, renamed `_note_version` and `_mark_run_template_used`, exactly as `store` and `mark_used` are. `save_run_template`, `move_versions` and the module's `__main__` commands are developer tools the app never calls and stay unpatched. The lock is not reentrant (a second `flock` on a new file descriptor of the same process waits): a wrapper never calls another wrapper, and `collect` (which the host runs under the lock in the finish step) calls neither of them. A static test asserts that no function that takes the lock calls one that takes it, over `j2_template_lib.py`.
- Why: both read the index, change it and write it back (`_save_index`); two runs adapting templates or using one run template at the same time could lose a row. They are runtime writers now (`route`'s adapt path, `_auto_reuse_pick`, `_run_tpl_start`).
- Rejected: one lock around the whole of `route` (it calls `store`, which locks: a deadlock for 30 s then `LibraryBusy`); a Sutra-side lock in the host (the runs are separate processes; the lock file is the one P10 already uses).
- Diagram: label "library lock covers 4 writers", pill on Template library.

## D182 — The `say` carrier is in scope: `template` and `workflows` travel as two task-only settings keys; the start page gets no control of its own
- Sources: D18, D129, `TASK_SETTING_KEYS`, `TaskSettings`, J2 `POST /api/say` (`RUN.set_run_template`), J2 `set_run_template`.
- Decided: `POST /api/say` accepts `template` (a run-template id, `[a-z0-9-]{1,80}`) and `workflows` (the string `all`, a comma list of workflow keys, or a list of such keys, at most 40 keys of at most 20 characters each); a malformed one is 400 with the violation. `Commands.say(text, template=None, workflows=None)` (the Protocol in `views.py`) is implemented by `DeptCommands.say`, which puts the two values into the settings dict it already hands to `deliver_to_department` as `J2_RUN_TEMPLATE` and `J2_RUN_TEMPLATE_WORKFLOWS`. `TASK_SETTING_KEYS` and `TaskSettings` gain the two keys (both text, optional, closed validators; they are not `EngineSettings` fields, so `layered()` ignores them and they cannot reach J2's environment). The host reads them from the task and, before `run.user_says(task.user_text)`, calls `run.set_run_template(id, keys)`; a `False` answer (flag off, unknown id) is one host system line "The run template <id> was not used: <reason>; the team starts from scratch" and a trace line, never a refused start. A follow-up ignores both keys (J2: `set_run_template` is False once the run has chat), and `say` keeps only `J2_DECIDE_FOR_ME` of the stored settings as before. The generated page already carries the buttons; the app adds no start-page control.
- Why: the page's links must work, not silently start without the template; the settings channel is validated, stored in the task and visible to the engine without a new column.
- Rejected: hiding the buttons (a page edit by hand, or a dead link); a new `RunSpec` field and a new `deliver_to_department` parameter (an orchestrator signature and a schema change for two strings); a start-page picker (J2's own Templates page is the picker).
- Diagram: label "say carries run template", pill on band:EXPERIENCE.

## D183 — The run-template views read the team's resolved settings, never the server's environment
- Sources: D129, D141, J2 `GET /api/run-template`, `GET /api/run-templates`.
- Decided: `views.run_template(ctx, q)` (route `GET /api/run-template?id=`, the 43rd handler: `HANDLER_COUNT` 43, `J2_EXACT` +1) answers `j2_template_lib.run_template_view(id)` plus `enabled = RunCtx.run_templates_on`, which `api/ctx.py` fills from the team's `effective()` settings (page `next_settings`, department `engine.json`, `data/engine.json`: the existing layering); an id that is not `[a-z0-9-]+` or not found is 404 `{"error": "no such run template"}`. `views.run_templates` adds `run_template` (J2's `run_template_use(dir)`) and passes the rows through `reuse_rows`. No view reads `os.environ["J2_RUN_TEMPLATES"]`.
- Why: the flags are the team's settings; the API process has none of them.
- Rejected: setting the variable in the API process per call (a global switch for all teams); computing `enabled` in the page.
- Diagram: label "run template views: team settings", pill on band:EXPERIENCE.

## D184 — The Artifacts shelf and the content door are team-scoped: `J2_RUNS_DIR` is the team's runs folder
- Sources: D26, D141, J2 `shelf_artifacts`, `runs_root`, `j2_artifact_lib`.
- Decided: `views._library(ctx)` sets `J2_RUNS_DIR` to `ctx.runs_dir` together with `J2_LIBRARY_DIR` (and restores both, under the existing lock); the engine child already runs with `J2_RUNS_DIR` = the team's runs folder (`DataPaths.j2_env()`). So `GET /api/catalog` lists the asking team's finished artifacts only, the templates shelf and the library index stay global (D26), and the content door can serve a section only from a run of its own team. The catalog handler's docstring and D141's sentence "nothing of the team is read" are amended: the team picks the page and the runs shelf; the library stays one. The `runs` rows of the global index (run id, date, business) stay visible to every team as today.
- Why: a finished document holds the business's own facts; the shelf and the door read text, not structure; teams are the unit of scope in this app.
- Rejected: all teams' runs (cross-team disclosure and cross-team prompt content); a per-install shelf with a filter (the same disclosure, one click away).
- Diagram: label "artifact shelf per team", pill on Template library.

## D185 — The seed sync adds run templates, their folders and the two provenance keys; it stays additive
- Sources: D144, D26, `ops/doctor.py` `_apply_seed`, `_fill`, J2 seed (`run_templates`, `renamed_from`, `adapted_from`).
- Decided: `_apply_seed` also syncs the index key `run_templates`: a seed row whose id the library lacks is appended and its folder `library/run-templates/<id>/` (`template.json`, `schema.json`) is copied; an id that is present is left alone (its `used_by` is the library's own); a folder with no row, or a row with no folder, is handled by the same present, restore, adopt and skipped states as versions. `_fill` adds `renamed_from` and `adapted_from` to a present version's row and `meta.json` when it lacks them (never changes one that is there). A seed version whose spec sha the library already holds under another family name is added as its own family (additive); the report lists it under `renamed` (seed row has `renamed_from`) so the owner can see both. Nothing is moved or renamed on disk. `missing_seed_templates`, `missing_seed_versions` and the `doctor` check count run templates; the report gains `run_templates`. A first run and `_seed_whole` copy the whole seed tree, so a new install has everything; the marker (`.seed-sync`, the sha of the seed index) changes with the seed index, so every existing install syncs once at its next start.
- Why: existing installs must gain what is new without losing what they made; J2's resolver already opens an old reference through `renamed_from`.
- Rejected: following J2's renames on disk (changes what an old run points at); skipping a version whose sha exists under the old name (the new J2 routing and the seed's run templates name the new family).
- Diagram: label "seed library: + run templates", pill on Template library.

## D186 — The records catalogue and the closed models learn the new run files and keys; J2's run-template bundle is `RunTemplateBundle`
- Sources: D47, D172, D151, `docs/design/library.md` sections 9 and 10.
- Decided: `records.py` gains a row for `reuse.json` (`artifact-reuse/1`, written only with the content door on; strict mode refuses unknown files, so it needs its row before the first run that writes it) and checks every other run file the new J2 writes by mock runs of the vendored J2 with the three flags on. `TemplatesFile` gains the optional keys `run_template` and `auto_reuse`; `TemplateDecision` gains `run_template`, `from_template`, `template_workflow`, `adapted_from`, `new_family`, `refused`, `door`; `TemplateMeta` (closed) gains `renamed_from` and `adapted_from`; `MessageMeta` (closed) gains `humans_only`, `run_template`, `content_door`; the first line of `chat.jsonl` (`by`) is checked against `RunMessage`. A new closed class `RunTemplateBundle` (family payload `run_template.bundle`, J2's `run-template/1`, no model call field) validates `library/run-templates/<id>/template.json`; the existing `RunTemplate` of `templates.py` (a row of `GET /api/run-templates`, payload `template.run`) keeps its name. `docs/schemas/` is regenerated by the export. Default log mode only warns; strict mode is what the tests run.
- Why: the library's closed models are what makes `GATE.check` mean something; every key J2 adds and the model refuses is a strict-mode failure of a run.
- Rejected: leaving the new files in `UNCHECKED` (D172's reason); renaming the existing `RunTemplate` (a published payload name and schema file).
- Diagram: label "records: reuse, run template bundle", pill on band:DEPARTMENT RUNTIME.

## D187 — A follow-up never re-fires auto-reuse and does not restore the run template
- Sources: D135, `rehydrate.py`, J2 `_auto_reuse_pick`, `set_run_template`.
- Decided: `rehydrate.py` sets `run.auto_pick = {}` for a continued run (J2's own "already decided" marker: `_auto_reuse_pick` returns at once) and leaves `run_tpl` as `None`. Both are listed beside `RESTORED_CHAIN` as deliberate (`RESTORED_REUSE`), with the reason: the earlier run's template shaped its first plan; a follow-up is a change request on finished work.
- Why: without the marker a follow-up that stamps a charter would score the run templates again and could swap the plan under finished work.
- Rejected: restoring `run_tpl` from `templates.json` (its rows and per-workflow state would steer stages that are already done).
- Diagram: label "follow-up: no auto-reuse", pill on band:EXPERIENCE.

## D188 — The Sutra-side hard-coded behaviour is cleaned by three rules, applied to a list; what stays is named
- Sources: the owner's refactoring task ("review hard-coded paths including validator behaviour; propose and implement a cleaner design; check existing workflows still work"), D165, D166, "agents decide, code validates", `docs/design/function-nodes.md`.
- Decided: three rules. (R-1) A value that is J2's is read from J2 where the layer already imports J2, lazily at first use (never at module import, because J2 reads some constants from the environment when it is imported and the host sets the environment first). Where a layer cannot import J2 (`spec.py` is read before J2 exists, the orchestrator, the UI) a copy may stay, with one parity test that reads J2's own value. (R-2) A value that is a decision (a type name, a word table, a validator behaviour) leaves code: into J2's data, into the capability's data file, or into a setting, with one owner. (R-3) A number that is a limit stays a named, commented constant with one owner; a duplicate definition is removed. The list, with the action and the size, is table 8 below. The one word table (`STRONG_PROJECT_WORDS`) is kept by D165's reason, moved into the project capability's data file so no word is in code, and has a stated exit (a planner that can choose a host type). `tests/engine/test_engine_no_type_names.py` is widened to `document|project|business_report` as well as `website|prd|hld|lld`, over every engine file outside the vendored ones; the two owners of a literal are listed with their reason (`capabilities/project.py` owns the type name `project` through `TYPE`; the new `engine/forms.py` owns J2's two form words).
- Why: the owner asked for the cleaner design; the three rules separate what J2 owns from what the host decides from what is only a size.
- Rejected: moving every number into settings (an owner cannot judge `STEP_SECONDS`); deleting the parity of `NOT_CHECKABLE` before J2 deletes it (the upstream fix is not in main); a model call to choose `project` (D129).
- Diagram: label "hard-coded cleanup: 3 rules", pill on band:DEPARTMENT RUNTIME.

## D189 — J2's own hard-coded behaviour is reported to J2's maintainers, not patched; the group-A fixes are adopted at the pin that contains them
- Sources: the owner's rule "no app-side fixes of upstream", the handoff of sync 5 ("write it down and send it"), J2 `docs/hardcoding-inventory.md` (547 rows: 357 decisions, 190 guardrails; NAME 160, FORCED 243, HIDDEN 47, KEYWORD 104).
- Decided: `docs/reference/j2/docs/hardcoding-inventory.md` and `library-reuse-order.md` are carried as reference documents (`REF_DOCS`, byte copies). The lane V note ends with the list for J2's maintainers (section 11 below). The group-A fixes (A4 `NOT_CHECKABLE` deleted, A5 `min_done_when`, A8 `ACTION_GOAL`, A10 quotes in CSS) are on J2's branch `fix-run-blockers` and not in main: the app does nothing about them now. At the sync whose pin contains A4, `fnodes/registry.py` loses its `NOT_CHECKABLE` read together with the check that uses it, in the same lane, and the parity tests that read J2's symbol say so by failing at import.
- Why: patching J2 in the copy makes two truths; the app's layer reads J2's symbols so it breaks loudly, not silently, when J2 moves.
- Rejected: a patch P-n for each inventory row (545 recorded edits of upstream text).
- Diagram: label "J2 hard-coding: reported", pill on band:DEPARTMENT RUNTIME.

## D190 — Goldens and fixtures move only through the recorders; `J2_RUN_BY` is pinned in every recorder and the engine child
- Sources: D150, D174, R5.
- Decided: flag-off J2 behaviour is byte-neutral, so the proof is a diff of each re-recorded golden against its predecessor: seven prompt goldens differ in `j2_commit` only, `record_fn_golden --check` is current, `api_shapes.json` changes on the routes that changed (`catalog`, `library`, `library_item`, `run_templates`, `run_template`, and the closed `say` body), 6 of the 81 UI fixtures change (three only through the author line, removed by the pin), and each change is explained in its commit message. The recorders set `J2_RUN_BY=sutra-pro` and `J2_PUSH_RUNS=0` in the environment they build. A project run's receipts differ by the new `section-not-empty` owned-section receipt (`eb0d28a7`) in a way the lane records. The legacy flow test is a three-way merge again (base: J2's file at `1d537295`, ours: Sutra's copy, theirs: the extraction; the analyst measured 0 conflicts, J2's file grew by 1,366 lines); `EXPECTED.json` records the pin, the new hash, the minimums and the known failures. J2's two new tests `artifact_lib_test.py` and `content_door_test.py` and `fixtures/folder-run/**` are decided in `j2_diff_of_record.py`: carried only if the merged flow test does not already exercise `j2_artifact_lib` (lane V checks by running the flow test with the module's coverage; the default is "not carried: J2's own test of a module that its flow test covers").
- Why: the goldens are the proof that the pin changed nothing a team can see with the flags off.
- Rejected: re-recording by hand; carrying 11 undecided files without a ruling.
- Diagram: label "goldens by recorder only", pill on band:DEPARTMENT RUNTIME (amends D174's label with the pin).

## D191 — The page is regenerated by the script; one anchor changes and six edits are added
- Sources: D137, D173, `scripts/port_j2_ui.py`.
- Decided: `port_j2_ui.py` regenerates the seven page files; the anchor E20f (`data-catgo="/library`) is now two buttons and becomes two edits (`${SutraCtx.libraryPath}`), and six edits are added for root-absolute URLs that the Sutra page must not follow: `shelfHref` and the `replaceState` of the library page to `SutraCtx.libraryPath`, the run links of the shelves and the `rtHref` (`/?view=simple&template=..&workflows=..`) to `SutraCtx.pagePath`. `sutra_ctx.js` `J2_EXACT` gains `/api/run-template`; the page's own route pins follow. No hand edit of `j2_ui.html` or `j2.css`.
- Why: the page is generated; a root-absolute link would leave the team's page.
- Rejected: leaving the links (they open the studio's own root); a redirect for `/library` (D141: no global library page).
- Diagram: label "page regenerated for sync 6", pill on band:EXPERIENCE.

## D192 — The diff of record decides every new file; two reference documents are carried
- Sources: D161, D154, `scripts/j2_diff_of_record.py`.
- Decided: of the 11 undecided files and 2 unlisted documents: `hardcoding-inventory.md` and `library-reuse-order.md` join `REF_DOCS` (carried, reference only); the two tests and `fixtures/folder-run/**` follow D190; `j2_server.py` and `j2_ui.html` stay not-carried-by-design as before (Sutra has its own server and generates the page). `j2_diff_of_record.py --check` must report 0 undecided.
- Why: a file without a ruling is how a sync forgets something.
- Rejected: carrying J2's server (a replaced engine surface).
- Diagram: none (tooling), listed in the key.

## D193 — One release, 0.5.0, in one merge order; the flags ship off
- Sources: D100, D175.
- Decided: lanes V, L, E, U merge in the order of section 8, the integrator then writes the as-built note (`docs/design/j2-sync-6.md` gets its section A to G in front of this design, as sync 5's did), `docs/DECISIONS.md`, the diagram key, `docs/TRACEABILITY.md`, `docs/ENVIRONMENT.md` (five rows), the counts of `tests/test_traceability.py` (43 endpoints), and the version 0.5.0 (`pyproject.toml`, `sutra_app/__init__.py`, `desktop/package.json`, `desktop/package-lock.json`); `scripts/check_release_tag.py sutra-pro-v0.5.0` passes. The three reuse flags and the content door ship off; the reviewer ships on. Amended: D129 (a pinned non-project type gets J2's planner call also through `_run_tpl_start`; the project type is never given a run template, D178), D141 (the team picks the runs shelf), D142 (the catalog step reads `effective()`), D145 (late-judge reserve P20), D162 (P19 used), D175 (0.4.0 history).
- Why: one wire change, once.
- Rejected: shipping the settings and the vendoring separately (the page already has the buttons).
- Diagram: label "release 0.5.0", pill on band:DEPARTMENT RUNTIME.

## 5. The patches: exact mechanics at the new pin

The script applies exact text edits that name their anchor and the count they must find; a J2 change under an anchor stops the run. Verdicts, with the J2 text found at `1adb8ecd`:

| Patch | Verdict | Mechanics |
|---|---|---|
| P1 imports | conflict fixed | `CODE` gains `"j2_artifact_lib.py"` between `j2_agent_views.py` and `j2_artifact_models.py`. `P1_COUNTS`: `j2.py` 15 (the new line `import j2_artifact_lib`), new `"j2_artifact_lib.py": 1` (`import j2_template_lib as L` becomes `from . import j2_template_lib as L`); every other count unchanged; total 41 lines. The two regexes and the `p1_lines` finder are unchanged. |
| P2, P3, P4, P5, P11, P14, P16, P17, P18 | applies | No anchor moved (the analyst's trial applied all of them). P2's three edits are unchanged. |
| P12 | applies | Both anchors unchanged (`import os / import re / import shutil` of `j2_template_lib.py`; the `CHROME_PATH` tuple of `j2_check.py`). |
| P15 | applies | The script still finds exactly six home paths in `library/index.json` (`runs[].library`); the new run-template files hold none. The count stays an error if it changes. |
| P7 | conflict fixed | One anchor changes. Old: `chosen = self._run_tpl_start(said) if self.run_tpl else self._deliverables(said)      # J2_RUN_TEMPLATES=1: the template's stages` (one line, 8 spaces). New: the same line, indented under `with llm.tagged(function="adaptation", step=2, cycle=self.cycle, stage=self.stage_kind or self.output):      # P7: Adaptation's planner call, made before its turn`. Count 1. Every other P7 anchor (the `call` loop, the summary, the template generator, the reviewer, the two `j2_realization.py` calls, `_dispatch_turn`) is unchanged. |
| P8 | conflict fixed | One anchor changes. Old (count 1): `        self.save("timing.json", self.timing())` / `        self._make_report(review=not self.paused)` / `        self.status = "waiting"` / blank / `    def timing(self):`. New: the same five lines with `        self._run_status()      # P8` after the `status = "waiting"` line. The hook therefore fires after `_make_report` has started the reviewer thread: the host's join (D179) is what makes the folder stable, not the hook order. The crash-path anchor is unchanged. |
| P9 | conflict fixed | Old (count 1): `        system = system_prompt(fn, reply_format, self._builder_for(fn))` / `        if self.calls and call_delay():` / `            time.sleep(call_delay())` / `        self.calls += 1` / `        self.thinking = fn`. New: the same with the addendum block (`if self._observed(): addendum = self._hook("system_addendum", fn); system += addendum if isinstance(addendum, str) else ""`) after the first line, as today. The two other `call_delay()` sites (`_summarize`, the reviewer) are not under a patch. |
| P10 | extended | Two more wrappers in `j2_template_lib.py` (D181): `def note_version(t, **notes):` becomes `with _library_lock(): return _note_version(t, **notes)` and the original body is `_note_version`; `def mark_run_template_used(tid, use):` the same with `_mark_run_template_used`. Each edit anchors on its `def` line plus the first docstring line (count 1), like the two existing ones. `PATCH_NOTES["P10"]` names four writers. |
| P19 | new (D179) | One edit in `j2.py`, count 1. Old: `        metrics = self._metrics()` / `        self.thinking = None` / `        metrics["ai_calls"] = self.calls + (1 if review else 0)      # counting the reviewer's call` / `        self.report_gen = getattr(self, "report_gen", 0) + 1` / `        self._save_report(metrics, {"verdict": "The reviewer is writing its notes; they appear here when done." if review` / `                                    else "Paused for the Requester; the reviewer runs when the run ends."})`. New: first two lines before them: `        off = review and self._hook("review_enabled") is False      # P19: the host's reviewer setting; only an explicit False switches it off` and `        review = review and not off`; the verdict expression becomes `... if review` / `else "The reviewer is switched off in this team's settings." if off` / `else "Paused for the Requester; the reviewer runs when the run ends."`. Under `NullHooks` `_hook` returns `None`, so a bare J2 and a host without the hook behave as before. |
| P20 | reserved | The late-judge switch of D145. |

`scripts/vendor_j2.py` further changes: `BASELINE`, `BASELINE_TREE`, `PREVIOUS_BASELINES` (adds `1d537295`), `REF_DOCS` (adds `hardcoding-inventory.md`, `library-reuse-order.md`), the module docstring's patch list, `PATCH_NOTES` for P1, P7, P8, P9, P10 and the new P19. The `TREES` copy of `templates/` already takes the new `templates/library-settings.json` and the new `library/` seed tree by the tree rules; no list of type or family names is added (D161). A trial run with these edits writes 514 files (229 today); with the two reference documents the lane records the exact figure.

## 6. Settings and wire table

| Where | Change | Lane |
|---|---|---|
| `EngineSettings` | new fields `run_templates`, `auto_reuse`, `artifact_library` (bool, `False`), `reviewer` (bool, `True`), `reviewer_wait` (float, `120`, `ge=0`, `0` = no wait); all editable; `ENV_NAMES` by rule (`J2_RUN_TEMPLATES`, `J2_AUTO_REUSE`, `J2_ARTIFACT_LIBRARY`, `J2_REVIEWER`, `J2_REVIEWER_WAIT`; the last two are read by the host, as `J2_WORKSPACE` is); `effective()` returns `EffectiveFlags` | E |
| `LOCKED_FIELDS` | unchanged (the five are not dangerous switches); `J2_PUSH_RUNS`, `J2_RUN_BY` are not fields | E |
| `DataPaths.j2_env()` | adds `J2_PUSH_RUNS=0`, `J2_RUN_BY=sutra-pro` | E |
| `TASK_SETTING_KEYS`, `TaskSettings` | 10 keys: adds `J2_RUN_TEMPLATE` (`[a-z0-9-]{1,80}`), `J2_RUN_TEMPLATE_WORKFLOWS` (text, at most 400 characters, `all` or a comma list); not `EngineSettings` fields | E |
| `POST /api/say` | body gains `template`, `workflows`; 400 on a bad shape; 409 busy as before | U (route), E (command) |
| `GET /api/run-template?id=` | new: `run_template_view` plus `enabled`; 404 `{"error": "no such run template"}`; handler 43, `HANDLER_COUNT` 43, `J2_EXACT` +1 | U |
| `GET /api/run-templates` | adds `run_template`; rows gain `group` (through `reuse_rows`) | U |
| `GET /api/catalog` | `artifacts` is the asking team's (D184); `run_templates` and `shelf` as J2 | U |
| `GET /api/engine/settings` | fields above; `effective` object | E |
| Engine settings page | 32 rows become 37 (`.setfield`): 13 editable checkboxes (9 + 4), 12 number inputs (11 + 1), group "Reuse (experimental)" and "Run report" | U |
| Run files | `reuse.json` (content door only); `templates.json` keys `run_template`, `auto_reuse`; decision keys; `report.json`, `report.md`, `artifacts.json` are written after the run is `waiting` (until the host's join) | L (records), E (host) |
| Seed library | `run_templates` key and `library/run-templates/<id>/` | V (vendor), L (sync) |
| Hooks | `review_enabled()` | E |

## 7. Lane plan, exact file ownership

Four lanes and an integrator. No file is in two lanes; the shared documents (`docs/DECISIONS.md`, `docs/diagram/**`, `docs/TRACEABILITY.md`, `docs/ENVIRONMENT.md`, `docs/design/*.md`, the version files, `tests/test_traceability.py`, `tests/test_docs.py`, `tests/test_diagram_decisions.py`, `README.md`) are the integrator's. Each lane writes `docs/notes/J2S6-<lane>.md` (its decision texts in the shape above, what it measured, deviations, what it sent to J2's maintainers). A test that goes red because of another lane's change is fixed by the lane that owns its file; the lane note lists it. Sizes are agent working hours.

### Lane V: vendoring, patches, goldens, legacy test (branch `lane/s6-v`; 6 to 8 h)

Owns: `scripts/vendor_j2.py`, `scripts/j2_diff_of_record.py`, `scripts/record_engine_golden.py`, `scripts/record_fn_golden.py`, `scripts/record_api_shapes.py`, `scripts/capture_j2_fixtures.py` (the script only: the `J2_RUN_BY`/`J2_PUSH_RUNS` pin; the capture run belongs to U), `sutra_app/engine/**` that is J2's (the 19 code modules, `agents/`, `conditions/`, `templates/`, `artifacts/`, `seed/`), `sutra_app/engine/VENDORED.md`, `docs/reference/j2/**`, `tests/engine/golden/**`, `tests/engine/legacy/**`, `tests/engine/test_engine_vendor.py`, `test_engine_patches.py`, `test_engine_prompts.py`, `test_engine_legacy.py`, `test_engine_fn_golden.py`, `test_engine_library_lock.py`, `test_j2_scope.py`.

Tasks, in order: (V1) the script edits of section 5 and `--check` against the extraction until only the intended files differ; (V2) vendor: write the tree and `VENDORED.md` (514 files plus two documents, P15 still six paths), `python -m` import smoke (`test_every_vendored_module_imports_in_a_clean_process` gains `j2_artifact_lib`); (V3) patch tests: P1 (41 lines), P7 (the planner call in a template run is tagged Adaptation), P8 (run-end order: `run_status` after `_make_report`), P9, P10 (four writers; the no-nesting static test; two processes use one run template and adapt one section at once without losing a row), P19 (reviewer on, off, `NullHooks`, hook returns `None`); (V4) diff of record: decisions of D190 and D192, 0 undecided; (V5) three-way merge of the flow test (`git merge-file`, base `1d537295`), `EXPECTED.json` (pin, hash, minimums, known failures `map_focus`, `graph_map`, `warm_ui`), the same for `realization_test.py`, `change_test.py`, `j2_replay_size.py` where Sutra edited them; (V6) re-record the goldens with the recorders and prove neutrality (diff table in the note); (V7) the note, including section 11 for J2's maintainers.

Done when: `vendor_j2.py --check` clean; `j2_diff_of_record.py --check` PASS with 0 undecided; `test_ownership.py` green; `SUTRA_SLOW=1 pytest tests/engine -k "prompts or legacy or vendor or patches"` green with the extraction; the diff table shows seven prompt goldens differing in `j2_commit` only; no test of another lane is edited.

### Lane L: library, records, seed sync, schemas (branch `lane/s6-l`; 5 to 7 h)

Owns: `sutra_app/library/**` (`templates.py`, `records.py`, `chat.py`, `wire.py` if a view shape needs a closed model, new `reuse.py` if the lane prefers a module), `docs/schemas/**` (regenerated by the export), `sutra_app/ops/doctor.py`, `tests/library/**`, `tests/ops/**` (including `tests/ops/seedlib.py`).

Tasks: (L1) record catalogue: `reuse.json` row; `TemplatesFile`, `TemplateDecision`, `TemplateMeta`, `MessageMeta`, `RunTemplateBundle` as D186, each key proved by a mock run of the extraction with the three flags on (the lane runs J2's own flow-test helpers with `STUDIO_MOCK=1`, `J2_AUTO_REUSE=1`, `J2_ARTIFACT_LIBRARY=1` into a scratch folder and validates every file in strict mode); (L2) export and the drift test; (L3) seed sync D185: run templates, folders, `_fill` keys, the `renamed` report line, the doctor check; (L4) the seed index and `library/run-templates/*/template.json` of the extraction validate against `RunTemplateBundle`; (L5) note.

Done when: `pytest tests/library tests/ops` green; `python -m sutra_app.library.export --check` clean; a scratch data folder at the sync 5 library, synced with the new seed, holds 81 families, 107 versions, 4 run templates, loses nothing it had, and a second sync changes nothing; strict mode accepts every file of three mock runs (flags off, flags on, content door on).

### Lane E: engine application (branch `lane/s6-e`; 8 to 11 h)

Owns: `sutra_app/engine/spec.py`, `paths.py`, `features.py`, `hooks.py`, `llm.py` (only if the purposes constant lands there), `forms.py` (new), `rehydrate.py`, `runlist.py`, `host/**`, `capabilities/**` (including `capabilities/data/**`), `fnodes/**`, `api/commands.py`, `api/settings.py`, `sutra_app/orchestrator/models.py` and `orchestrator/tasks.py` only if a settings filter needs the two keys (the lane lists it), tests `tests/engine/test_engine_{spec,paths,host,host_output,host_process,finish,events,events_contract,crash,live,publisher,inbox_setting,picks,port_contract,project,project_data,project_followup,workspace,rehydrate,rehydrate_chain,runlist,features,no_type_names,fn_checks,fn_declare,fn_layer,fn_mutations,fn_output,fn_registry,fn_tuning,llm_shim,api_commands,api_settings,agent_live,deliverable}.py`, `tests/engine/test_capabilities_registry.py`, `test_deliverable_contract.py`, `test_select_output.py`, `tests/contracts/test_contract_{settings,env_and_spec,fnodes,run_events,usage,world,make_port,atom_output,diagram_strings,json_extract_parity}.py`, `tests/orchestrator/**`.

Tasks: (E1) settings: five fields, `effective()`, `ENV_NAMES`, `to_env`, the `effective` object of the settings answer, fixed `J2_PUSH_RUNS`/`J2_RUN_BY`, project `FORCE` (D177, D178) and `finish.py` reading `effective()`; (E2) reviewer: `hooks.review_enabled`, the join and discard in `_conclude`, `reviewer.late` trace (D179); (E3) the carrier: `TASK_SETTING_KEYS`, `TaskSettings`, `DeptCommands.say`, host call and the "not used" system line (D182); (E4) rehydrate marker `RESTORED_REUSE` (D187); (E5) hard-coded cleanup of table 8 (D188); (E6) `features.py`: a chip "Run templates and auto-reuse" (flags `run_templates`, `auto_reuse`; symbols `set_run_template`, `_auto_reuse_pick`, `run_templates_on`), a chip "Content door" (flag `artifact_library`; symbols in `j2_artifact_lib.py`), and the `reviewer` flags on the extras row; (E7) note.

Done when: the lane's tests pass with the vendored tree of lane V (E merges after V); `test_a_classic_follow_up_reaches_done_with_one_more_workflow` passes five times in a row and `test_p8_a_hooked_run_pairs_every_turn_start_with_its_finish` ten times; an inherited `J2_PUSH_RUNS=1` or `J2_RUN_BY=x` never reaches a run (test over the engine child's environment); a project run has all five flags off in its environment; a stale reviewer (a scripted slow reviewer past `reviewer_wait`) leaves no write after `run.ended`.

### Lane U: views, page, UI and route pins (branch `lane/s6-u`; 6 to 8 h)

Owns: `scripts/port_j2_ui.py`, the generated `sutra_app/ui/pages/j2_ui.html` and the other generated page files (`sutra_app/ui/static/css/j2.css` and the rest the script writes), `sutra_app/ui/static/js/sutra_ctx.js`, `settings_view.js`, any other hand-written UI file the settings page needs, `sutra_app/engine/views.py`, `j2_server.py` (the stdlib adapter), `api/__init__.py`, `ctx.py`, `library.py`, `run_views.py`, `state.py`, `files.py`, `ports.py`, `reply.py`, `tests/ui/**` (fixtures, `fake_backend.py`, js tests, browser tests: `tests/ui/test_home.py` counts 32 to 37), `tests/engine/test_engine_views.py`, `test_engine_api_scope.py`, `test_engine_api_headers.py`, `test_engine_api_redact.py`, `tests/contracts/test_contract_route_table.py`, `tests/e2e/**`.

Tasks: (U1) `port_j2_ui.py`: E20f split, six new edits, `--check` against the extraction, regenerate; (U2) `views.py`: `run_template`, `run_templates` (+ `run_template`, `reuse_rows`), `say` (`template`, `workflows`, 400s), `Commands.say(text, template=None, workflows=None)`, `_library(ctx)` sets `J2_RUNS_DIR`, `RunCtx.run_templates_on`, `HANDLER_COUNT` 43; `api/*` and `j2_server.py` routes; (U3) `sutra_ctx.js` `J2_EXACT` +1, `settings_view.js` rows and groups, fake backend; (U4) tests; (U5) after V, L and E are merged into the lane branch: capture the fixtures (`capture_j2_fixtures.py --check` last), route pins, note.

Done when: `port_j2_ui.py --check` clean (40 edits: 33 today, E20f becomes two, six are added; 7 files); `node --test tests/ui/js/*.test.js` green; `SUTRA_BROWSER=1 pytest tests -m browser` green; the by-hand check of section 9 (page buttons start a run from a template); a team that has two finished runs sees only its own on the Artifacts shelf (test with two teams); `GET /api/run-template` says `enabled: false` with the flags off and `true` with `run_templates` on, whatever the server's environment holds.

### Integrator (after the four merge; 3 to 4 h)

Edits the shared files above; writes the as-built note; runs the verification list of section 9; tags nothing (the release is the owner's). Does not touch a lane's files.

## 8. Merge order, and what can start before the vendoring lands

Merge order: V, then L and E (independent of each other; L first, because E's host tests with real mock runs use the library records), then U (its fixture capture needs V, L and E), then the integrator. Each merge is a "Create a merge commit" (never squash), after the lane's own tests and a rebase on the previous merge; nothing is pushed.

| Lane | Can start now (no vendoring needed) | Waits for V |
|---|---|---|
| V | everything (it is the critical path); start first | n/a |
| L | the closed-model drafts from the extraction's files and J2's own flow-test helpers; the doctor seed sync against a fabricated seed tree and the extraction's `library/`; `reuse.json` samples from a mock run of the extraction | strict-mode checks of runs of the vendored engine; the final seed-tree test; the schema export (needs the seed in place) |
| E | settings fields, `effective()`, fixed env, `FORCE`, `TaskSettings` keys, `DeptCommands.say`, `hooks.review_enabled`, the join (tested with a fake run object that has `review_thread` and `report_gen`), `forms.py`, the guard, the cleanup items that read symbols the old pin already has (`j2_realization.THRESHOLD`, `j2.ROUTES`) | the P19 end-to-end test, `rehydrate` marker test on a real J2, `features.py` symbols, the reviewer-race tests, project runs with `eb0d28a7` |
| U | `port_j2_ui.py` edits and regeneration against the extraction, `sutra_ctx.js`, `settings_view.js`, `fake_backend.py`, JS tests | `views.py` handlers' tests (they import vendored `j2_template_lib.run_template_view`), fixture capture (also needs E and L), browser tests |

Frozen interfaces between lanes (so they can start together): `EngineSettings.effective() -> EffectiveFlags(auto_reuse, run_templates, template_library, artifact_schema)` and the `effective` key of the settings answer (E to U); `Commands.say(text, template=None, workflows=None) -> bool` and the two settings keys `J2_RUN_TEMPLATE`, `J2_RUN_TEMPLATE_WORKFLOWS` (U to E); `hooks.review_enabled() -> bool` and J2's attributes `review_thread`, `report_gen`, `run_tpl`, `auto_pick` (V to E); the seed layout `run_templates` and `library/run-templates/<id>/` (V to L).

## 8b. Table 8: the Sutra-side hard-coded behaviour (D188), with the action, the size and what stays

| # | Where | What | Rule and action | Size | Lane |
|---|---|---|---|---|---|
| 1 | `fnodes/registry.py` `GATE` 0.80 | copy of `j2_realization.THRESHOLD` | R-1: `gate()` reads `j2_realization.THRESHOLD` lazily; the parity test becomes "the registry reads it" | S | E |
| 2 | `fnodes/registry.py` `NOT_CHECKABLE`, `AGENT_CONTENT`, `USER_CONTENT` regexes | copies of `J2Run` attributes | R-1: lazy reads of `j2.J2Run.NOT_CHECKABLE` etc.; the three constants become functions; the character-for-character parity tests are deleted (equal by construction); when J2 deletes `NOT_CHECKABLE` (A4, D189) the check goes with it | M | E |
| 3 | `fnodes/registry.py` `J2_ROUTES` | copy of `j2.ROUTES` | R-1: lazy read | S | E |
| 4 | `fnodes/registry.py` `J2_STRINGS` (ten prose fragments) | text J2 posts inline (f-strings); no symbol to read | stays: the parity tests pin each fragment against the vendored source, and fail loudly when J2 rewords | none | E (tests) |
| 5 | `capabilities/select.py` `STRONG_PROJECT_WORDS`, `WEAK_REASONS` | the one word table (D165) | R-2: moved to `capabilities/data/project.words.json` (patterns and reasons), loaded and validated once; no word in code; exit: a planner that can choose a host type | S | E |
| 6 | `capabilities/select.py`, `base.py`, `project.py`, `rehydrate.py`, `views.py` quoted `"project"` and `"document"` | the type name and J2's form word | R-2: `project.TYPE` is the one definition of the type name (`Selection`, `force`, `addendum`, `register` read it); `engine/forms.py` (new, ~15 lines) holds `PAGE`, `DOCUMENT` and `is_document(info)` with an import-time check that `j2_types.FORMS == (PAGE, DOCUMENT)`; `views.py:684` reads the run's label, not a word. The select rule id `"project"` is a rule id, not a type: allowed by name in the guard's allowlist | M | E |
| 7 | `capabilities/project.py` `FORCE` keyed by the literal, texts, `EARLIER_MAX` 12000, `EARLIER_FILES` 40 | policy numbers and texts of the capability | R-2/R-3: `force()` compares with `TYPE`; the two limits move to `capabilities/data/project.limits.json` (validated ints), texts already data | S | E |
| 8 | `tests/engine/test_engine_no_type_names.py` | guards four names over a fixed file list | widened to `website|prd|hld|lld|document|project|business_report` over every `*.py` under `sutra_app/engine/` and `sutra_app/library/` except the vendored J2 files and the two listed owners | S | E |
| 9 | `spec.py` `tap_min` 44 and the other defaults that copy J2's | copies in a layer that cannot import J2 | R-1 exception: stay, plus one parity test that imports J2 in a clean process and compares every default that has a J2 module constant | S | E |
| 10 | `host/finish.py` `ENDED_WELL`, `STEP_SECONDS`; `host/loop.py` ticks and stop lists; `host/folder_watch.py` timeouts | limits | R-3: stay as named, commented constants; `ENDED_WELL` is read from the event vocabulary (`events.py`) so the statuses have one owner | S | E |
| 11 | `capabilities/workspace.py` and `capabilities/agents.py`: `("agent_turn","plan","judge")` twice | a duplicate | R-3: one `AGENT_PURPOSES` next to the P7 tag vocabulary (`hooks.py`), both import it | S | E |
| 12 | `views.py` `HANDLER_COUNT`, `ASK_CHARS` | literal count; a limit equal to the orchestrator's note limit | `HANDLER_COUNT` is computed from the handler table (the test pins 43); `ASK_CHARS` imports the orchestrator's constant | S | U |
| 13 | `orchestrator/agent/planner.py` `MIN_SCORE` 2 and the `textutil` stop words | the deterministic fallback when no connector can plan | stays: it is the offline fallback (`fallback_plan`), not a decision about a brief; a test pins that it runs only when the model's plan is unavailable | none | none |
| 14 | UI `MIN_MS`, `MIN_SCALE`, `OVERVIEW_KINDS`, `MIN_CHARS` | presentation limits; `OVERVIEW_KINDS` are chart node kinds (`root`, `department`, `division`), Sutra's own vocabulary, not output types | stay | none | none |

The J2-side rows (the 547 of the inventory) are not touched (D189).

## 9. Verification list

Run in the integrator's worktree after the merges, with `SUTRA_J2_CHECKOUT` naming a fresh extraction of the pin (full commit).

1. The recorders and checks: `scripts/py scripts/vendor_j2.py --source "$J2SRC" --commit 1adb8ecd8fa8eef47fb7a0fc63a1616f556cdfeb --check`; `port_j2_ui.py --check`; `record_engine_golden.py --check`; `record_api_shapes.py --check`; `capture_j2_fixtures.py --check`; `record_fn_golden.py --check`; `j2_diff_of_record.py --check` (0 undecided); `scripts/check_release_tag.py sutra-pro-v0.5.0`; `scripts/check_docs.py`.
2. The gate: `scripts/gate.sh` prints `gate: ok` (sync 5: 10,808 passed; the count rises by the new tests; no test weakened; the integrator lists each red test it fixed and whose it was).
3. Node: `node --test tests/ui/js/*.test.js`.
4. Slow suites: `SUTRA_SLOW=1 scripts/py -m pytest tests/engine -k "prompts or legacy or vendor or patches"` (both flow-test runs, with and without the extraction; the three known upstream failures stay pinned).
5. Browser suite: `SUTRA_BROWSER=1 scripts/py -m pytest tests -m browser`.
6. The ownership test: `scripts/py -m pytest tests/test_ownership.py` (no owner name, no home path in any new file, including the lane notes and `VENDORED.md`).
7. Manual offline checks, on a scratch data folder with `python -m sutra_app --offline --no-browser` and the stub connector, driven by the HTTP API as in sync 5 (`POST /api/chart/changes` to add two teams, `POST /api/tasks`, `GET /api/runlist`, `/api/state`, `/api/artifacts/groups`, `/api/catalog`, `/api/run-templates`, `/api/run-template`), no error or traceback in the server log or any run's stderr:
   - Flags off (the default): a website brief and a document brief behave as in sync 5; `GET /api/run-template?id=thread-boutique-website` answers with `enabled: false`; `reuse.json` is absent; the report says the reviewer's notes arrived (the stub answers), and no file of the run changes after `run.ended` (compare the folder's mtimes before and 3 s after).
   - `POST /api/engine/settings {run_templates: true}` for team A, then `POST /api/say {text: "a website for a boutique", template: "thread-boutique-website", workflows: "all"}`: `templates.json` has `run_template` with `selected` = all five workflows; the chat has "Using run template ..."; the run template's `used_by` count rises by one; team B (flag off) given the same body starts from scratch and its chat says the template was not used.
   - `{auto_reuse: true}` for team A with `{template_library: false}`: a "website for a boutique" brief (offline mock, so mock-made templates are eligible): `templates.json` `auto_reuse.picked` is `thread-boutique-website` with a score of at least 0.6 and the effective settings show `template_library` on by implication; the finish step catalogued the run (`finish.step catalog ok` in `trace.jsonl`); a brief about "a freight company" scores below 0.6, picks nothing, and the chat says so. A follow-up message of the first run makes no `match_run_templates` call (D187).
   - `{artifact_library: true}` for team A: a second document run that repeats a finished run's section serves it from that run with no model call (`reuse.json` row, receipt `door: reuse`, the budget refunded); team B's identical brief never serves from team A's run, and `GET /api/catalog` for team B lists none of team A's artifacts.
   - `{reviewer: false}`: the run report's verdict is "The reviewer is switched off in this team's settings." and `calls.jsonl` has no reviewer row; `{reviewer_wait: 0}` with a slow scripted reviewer: `reviewer.late` is in `trace.jsonl` and `report.json` still holds the placeholder.
   - A project-output team with all three flags on: the run's environment shows all five off (`settings.json` of the run), and the run ends Done with the owned-section receipts.
   - An old saved run (sync 5 data folder) opens; a library synced from the sync 5 state gains run templates and loses nothing (L's done-when, repeated here on a copy of a real data folder).
8. One real-model run, if a connector with quota is available and the owner agrees: a document run with `auto_reuse` on, after one run with it off; the by-hand check of sync 5 for a real model is still open and this one covers it.

## 10. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Library lock (the lock is a non-reentrant `flock`, the finish step runs `collect` inside it) | a nested acquire waits 30 s then `LibraryBusy`; a new J2 writer that is not wrapped loses a row | D181's static no-nesting test and a grep test over `j2_template_lib.py` and `j2.py` for `_save_index` and `index()` writers; every sync re-runs both (shared-library.md: the contract check) |
| Reviewer thread | an unjoined thread after the cap; a fatal hook error in an unnamed thread fails a finished run | join, then `report_gen` bump so the thread saves nothing; the thread is a daemon; `_review_later` catches the call's exceptions; test with a scripted slow and a raising reviewer |
| Seed growth | wheel and install 0.8 MB to 2.2 MB, first-run copy 157 to 437 files, a one-time sync at every existing install | measured by lane L (time of `_seed_whole` and of the sync on a copy); the sync is under the lock and writes the index once; the marker makes later starts free |
| Family renames | a seed family that J2 renamed appears next to the old one; the shelf shows two | additive on purpose (D185); the report names both; J2's resolver opens old references; revisit if owners complain |
| Business names in family names | the global library's family and run-template names carry the business of the run that made them (J2 names an adapted family for the run's business), visible to every team | unchanged in kind from sync 4 (the seed has such names); the shelf shows structure with slots; a publish and scrub gate is the shared library's next design (D196); stated in the lane note |
| Flags | three experimental flags the owner can switch; seven J2 commits are "needs owner review" | default off, project forced off, one by-hand check each; the page text says "experimental"; the upstream owners are asked to review (section 11) |
| Content door in a node layer built for one call per builder turn | a served section has no model call, so no `call_finished` for that builder atom | lane E tests the function-node layer on a served section (the atom closes through the turn events); if it does not, the atom is closed by the host from the receipt `door: reuse` and the lane says so |
| `section-not-empty` receipt (`eb0d28a7`) in project runs | a project builder that leaves an owned section empty is now retried | a mock project run test; the real-model check of item 8 covers a folder run |
| `J2_REVIEWER`, `J2_REVIEWER_WAIT` named like J2 variables | confusion with J2's environment | `ENVIRONMENT.md` says "read by the host, not by J2" (as for `J2_WORKSPACE`) |
| The pin is a commit of main, not a tag | a later force-push of J2's main would remove it | the extraction is by full hash; this repository holds the commit; the maintainers are asked to tag |
| Lane overlap on `settings_view.js` and `spec.py` | a rename on one side breaks the other | the field names and the `effective` shape are frozen in section 8 |

## 11. For J2's maintainers (reported, not patched; D189)

Written into the lane V note as a list with file and line, no app-side change:

1. The seven "needs owner review" commits of `j2.py` (run templates, auto-reuse) are carried inert; please review, and tag the pin.
2. `GET /api/run-template` reads `J2_RUN_TEMPLATES`/`auto_reuse()` from the server's `os.environ`; a host with per-team settings needs the value as an argument or a callable.
3. The reviewer thread (`_make_report`, `_review_later`) is unnamed and cannot be awaited; a public `join_review(timeout)` and a name starting with the host's thread prefix would let hosts avoid the race. The placeholder text for a skipped reviewer does not exist (P19 adds one in the copy).
4. `note_version` and `mark_run_template_used` write the library index without a lock (the copy wraps them, P10); `save_run_template` and `move_versions` too.
5. `set_run_template` returns `False` silently for a flag-off, an unknown id and a started run; callers cannot tell which.
6. `run_author()` runs `git config user.name` at every run start and records the result in `chat.jsonl`; a personal name goes into run data unless `J2_RUN_BY` is set.
7. `J2_PUSH_RUNS` pushes with the user's credentials; it is the only flag that writes outside the data folder.
8. `catalog_view()` reads Shelf 1 from `J2_RUNS_DIR` while the library is one global store; a host with per-team runs needs a runs-folder argument (the copy sets the variable per call).
9. `AUTO_MIN` 0.6, `AUTO_WEIGHTS`, `VAGUE_TYPES`, `run_slots`/`_noun` and the `style.json` lookup remain in code; `NOT_CHECKABLE`, `ACTION_GOAL` and the other group-A rows are fixed on `fix-run-blockers` but not in main; the 547-row inventory is carried as `docs/reference/j2/docs/hardcoding-inventory.md`.
10. `j2_template_lib.py` `shelf_view` says "GET /api/shelf: not there yet"; the Artifacts and Artifact-templates shelves have no J2 caller but `catalog_view`.

## 12. Change log

- 2026-11-13: design and lane plan (first version), written after re-checking the analyst's findings against the extraction and the worktree; corrections 1 to 14 of section 1.
