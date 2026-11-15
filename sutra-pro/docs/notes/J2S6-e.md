# J2S6-e as built: the engine application for J2 sync 6 (settings, reviewer, say carrier, cleanup), lane E

Owns `sutra_app/engine/{spec,paths,features,hooks,forms,rehydrate}.py`, `engine/host/**`, `engine/capabilities/**` (with `data/`), `engine/fnodes/**`,
`engine/api/{commands,settings}.py`, `orchestrator/models.py` (the two task keys), the engine and contract tests of these, `docs/ENVIRONMENT.md` (the five
rows, with their fields), this note. Spec: `docs/design/j2-sync-6.md` sections 5 to 8b (D177 to D179, D182, D187, D188). Paths are relative to `sutra-pro/`.

## What was built

- **E1 settings (D177, D178).** `EngineSettings` has `run_templates`, `auto_reuse`, `artifact_library` (off), `reviewer` (on) and `reviewer_wait` (float, 120,
  `ge=0`, `0` = do not wait), all editable, none locked, env names by rule; `effective()` returns the frozen `EffectiveFlags(auto_reuse, run_templates,
  template_library, artifact_schema)` by J2's own chain and rewrites nothing. `DataPaths.j2_env()` fixes `J2_PUSH_RUNS=0` and `J2_RUN_BY=sutra-pro`
  (`FIXED_PUSH_RUNS`, `FIXED_RUN_BY`); the host applies that dict after `to_env()`, so a developer shell, a task key and an engine file cannot change them.
  The project capability's `FORCE` names all five flags, so `effective()` is all false for a project run (the `output.selected` trace line lists them under
  `forced`). `host/finish.py` `catalog` reads `effective().template_library`. `docs/ENVIRONMENT.md` has the five rows, in the commit of their fields, and a
  sentence for the two task-only keys and the two fixed values (which are not rows: they are not fields).
- **E2 reviewer (D179).** `hooks.review_enabled()` (`NullHooks` True; `EventHooks.reviewer`, set by the host from the setting; `HostHooks` forwards and
  answers True for hooks without the method). `Host._join_reviewer()` runs first in `_conclude`, after `inbox.close()` and before `publisher.stop()`: it joins
  `run.review_thread` for at most `reviewer_wait` seconds (at most `STOP_WAIT_S` when the run is being stopped), then bumps `run.report_gen`, writes one
  `reviewer.late` trace line and gives the thread `REVIEWER_SETTLE_S` (0.25 s) to leave a write it had already begun. The excepthook sends a failure of
  the review thread to a `reviewer.error` trace line and the original hook (stderr); it no longer sets the run's crash.
- **E3 carrier (D182).** `TASK_SETTING_KEYS` has ten keys; `TaskSettings` (orchestrator) has `J2_RUN_TEMPLATE` (`[a-z0-9-]{1,80}`) and
  `J2_RUN_TEMPLATE_WORKFLOWS` (at most 400 characters, `all` or at most 40 keys of at most 20 characters; the shape is `spec.run_template_keys`, shared with
  the host). `DeptCommands.say(text, template=None, workflows=None)` adds the two keys to the settings of that one delivery, never to `page.json`; workflows
  may be a text or a list; workflows without a template are dropped. `Host._take_run_template` runs after `run.started` and before the first line is posted
  (J2's `set_run_template` is False once the chat has a line, and the host's own system lines would make it so), only for a first run: a follow-up or a
  refused rehydrate ignores both keys. A refusal says why in one system line ("The run template X was not used: <reason>; the team starts from scratch.") and
  one `run_template.requested` trace line: flag off by `effective()`, a bad id, a bad list, an id the library lacks, or the engine's own refusal.
- **E4 rehydrate (D187).** `rehydrate()` sets `auto_pick = {}`; `run_tpl` stays None. `RESTORED_REUSE = ("auto_pick",)` and `NOT_RESTORED_REUSE = ("run_tpl",)` sit
  beside `RESTORED_CHAIN`.
- **E5 hard-coded cleanup (D188, table 8b), the rows of lane E.** 1 to 3: `fnodes/registry.py` reads J2 lazily through `gate()`, `not_checkable()`,
  `agent_content()`, `user_content()`, `j2_routes()`; the character parity tests became "the registry hands back J2's own objects" plus a clean-process test
  that importing the registry imports no J2. 4: `J2_STRINGS` stay with their parity tests. 5: the word table moved to `capabilities/data/project.words.json`
  (patterns, reasons, `weak`), read and checked by `select.load_words()` when `select.py` is imported. 6: `project.TYPE` is the one definition of the type name;
  new `engine/forms.py` (`PAGE`, `DOCUMENT`, `is_document`, `is_page`, `check_forms`); `base.py` and `rehydrate.py` read it. 7: `force()` compares with `TYPE`; the two
  limits are `capabilities/data/project.limits.json` (`load_limits()`). 8: the guard test is widened (below). 9: one parity test reads J2's module constants in a clean
  process and compares every default that has one (`delay` is the named exception). 10: `ENDED_WELL` and rehydrate's `ENDED` are `events.END_STATUSES[:2]`; the loop,
  folder-watch and step constants stay as they were, named and commented. 11: `hooks.AGENT_PURPOSES` is the one definition that `workspace.py` and `agents.py` read.
  Rows 12 to 14 are not lane E's (12 is U's, 13 and 14 stay).
- **E6 features.** Two chips, "Run templates and auto-reuse" (`run_templates`, `auto_reuse`; `set_run_template`, `_auto_reuse_pick`, `run_templates_on`) and "Content door"
  (`artifact_library`; `enabled`, `source_section`, `door` of `j2_artifact_lib.py`); the extras row has the flags `reviewer`, `reviewer_wait`. 17 chips, 26 rows; every symbol
  is checked against the extraction with `SUTRA_J2_CHECKOUT`.

## Deviations from the design, and why

1. **`effective` of the settings answer.** The answer already has a key `effective`: the full resolved settings (`EngineSettings.model_dump()` of the layers, as
   stored; two contract tests pin that it equals what the host will write to `settings.json`). The design says "`effective` object". I kept that key as it is and added
   **`effective_flags`**: `{auto_reuse, run_templates, template_library, artifact_schema}` after J2's implications. A row that is on only by implication is
   `effective_flags[x] and not effective[x]`. Lane U reads this name; if U read `effective.<flag>` as the implied value, it must change to `effective_flags`.
2. **The form check is made at registration, not at import.** The design says `forms.py` has an import-time check that `j2_types.FORMS == (PAGE, DOCUMENT)`. The host
   imports `capabilities` (to choose the output) BEFORE it exports the J2 environment, and `j2_types` reads `J2_AGENTS_DIR` when it is imported, so an import-time
   `j2_types` read there would freeze the wrong value. `forms.check_forms(j2_types)` is called by `capabilities.register(j2)`, where J2 is loaded and its environment is set;
   a third form stops the start by name (`RuntimeError`) all the same. `forms.py` imports nothing of J2.
3. **`select.py` imports `TYPE` and `DATA` from `project.py`, and `project.py` imports `select` lazily** (inside `ProjectCapability.select`), to avoid a cycle. The select rule id
   `project` is a rule, not a type: `RULE_PROJECT` is its one spelling.
4. **The reviewer join has a 0.25 s settle after a discard.** J2's `_review_later` checks `gen == self.report_gen` and then saves; a bump that lands between the check and the
   writes would let those writes happen after `run.ended`. The short join closes that window; it is paid only by a run whose reviewer was late.
5. **The excepthook does not make a reviewer failure the run's crash at any time**, not only after a discard: a reviewer thread that dies while a later message is being worked
   on must not crash that work. Its traceback still goes to stderr through the original hook.
6. **The widened guard has one pending entry for a file that is lane U's.** `tests/engine/test_engine_no_type_names.py` spells `engine/views.py` three times with the form word
   `document` (lines 400, 520, 684 of the file at this branch); row 6 of table 8b moves them to `forms.is_document` / `forms.DOCUMENT` / the run's label in lane U. The entry is an upper bound
   (`PENDING`): it passes before and after U's change; the integrator deletes the entry once `views.py` is clean. The owners (`project.py`, `forms.py`, `select.py`) are
   listed with their counts, and a test fails when an owner no longer spells what it owns.
7. **The follow-up test race was in the test helper, not in the app.** `test_a_classic_follow_up_reaches_done_with_one_more_workflow` compared a finished folder with itself
   while J2's reviewer thread was still writing `artifacts.json`. The helper `say()` of `tests/engine/test_engine_rehydrate.py` now waits for the reviewer thread, as the host does
   (D179); nothing was weakened. Five runs in a row and `test_p8_a_hooked_run_pairs_every_turn_start_with_its_finish` five (then ten, below) times pass.

## Tests added or changed

`test_engine_spec` (fields, `effective()` over the six cases, the two task-only keys, the shapes, the parity with J2's constants, 17 chips and the new digest),
`test_engine_host_reviewer` (new: the join and the cap over a fake run, the hook, the excepthook, and end to end with the vendored J2: on, off, slow past the cap, raising,
dying outside its try; no file changes after `run.ended`), `test_engine_host_run_template` (new: whole, selected workflows, flag off, unknown id, bad shapes, implied by
`auto_reuse`, project never, no key, follow-up), `test_engine_host` (inherited `J2_PUSH_RUNS` and `J2_RUN_BY` never reach the run), `test_engine_api_commands` and
`orchestrator/test_task_setting` (the carrier), `test_engine_finish`, `test_engine_project` (the chain forced off), `test_engine_rehydrate` (+chain), `test_engine_fn_registry`,
`test_capabilities_registry` (forms), `test_select_output` and `test_engine_project_data` (the two data files and their loaders), `test_engine_no_type_names` (widened), the contract tests
(`test_contract_settings`, `test_contract_env_and_spec`: ten keys, two of them task-only), `test_engine_events` (the protocol has `review_enabled`).

## What other lanes and the integrator must know

- Lane U: `GET /api/engine/settings` has `effective_flags` (deviation 1); `Commands.say(text, template=None, workflows=None)` is implemented by `DeptCommands.say`, which takes `workflows`
  as `all`, a comma text or a list and trusts that the route validated the shape (`spec.is_run_template_id`, `spec.run_template_keys` are the shared checks, and the orchestrator refuses
  a bad one with 422); the three form words of `views.py` (deviation 6).
- Lane L: the run template runs write `chat.jsonl` rows with `run_template` and `humans_only`, and `templates.json` with `run_template`; the default-mode records log
  `record_rejected` for them until the closed models learn the keys (`MessageMeta`, `TemplatesFile`).
- Integrator: the guard `PENDING` entry; `docs/diagram/*`, `DECISIONS.md`, `TRACEABILITY.md` are not touched here; the decision texts below are the as-built form of D177, D178, D179,
  D182, D187 and D188 (the design's text is right except where a line below says otherwise).

## Decisions (as built)

## D177 — The reuse flags are Engine settings; `J2_PUSH_RUNS` and `J2_RUN_BY` are fixed values of the host
- Sources: D129 (settings layers), D152 (an environment variable with no field does nothing), D169, `docs/design/j2-sync-5.md` section 7.
- Decided: `EngineSettings` gains `run_templates`, `auto_reuse` and `artifact_library` (bool, default `False`, editable, env names `J2_RUN_TEMPLATES`, `J2_AUTO_REUSE`, `J2_ARTIFACT_LIBRARY` by the existing rule). `DataPaths.j2_env()` exports `J2_PUSH_RUNS=0` and `J2_RUN_BY=sutra-pro` (constants `FIXED_PUSH_RUNS`, `FIXED_RUN_BY`); the host applies it after the settings, so it wins over the inherited environment; they are not fields, so no settings file, task key or environment can change them. `docs/ENVIRONMENT.md` has the three rows in the commit of their fields, and says in prose that the two fixed values are the host's.
- Why: J2 only reads its environment, the host is what sets it; the page has the buttons, so the owner needs the switch; a fixed `J2_RUN_BY` keeps the OS or git user name out of `chat.jsonl` and removes a `git config` subprocess per run; a pushed run folder is the one J2 flag that writes outside the data folder.
- Rejected: leaving the variables to the environment (D152); exposing `J2_PUSH_RUNS` read-only; `J2_RUN_BY` from the owner's name (a personal identifier in run data).
- Diagram: label "reuse flags are settings", pill on band:EXPERIENCE.

## D178 — Implied flags are computed once by `EngineSettings.effective()`; the finish step and the project force read it
- Sources: D142, D164, J2 `j2_template_lib.enabled`, `auto_reuse`, `j2.run_templates_on`, `artifact_schema_on`.
- Decided: `EngineSettings.effective()` returns a frozen `EffectiveFlags(auto_reuse, run_templates, template_library, artifact_schema)`: `auto_reuse = auto_reuse or artifact_library`; `run_templates = run_templates or auto_reuse`; `template_library = template_library or auto_reuse`; `artifact_schema = artifact_schema or template_library`. The stored settings are not rewritten. `GET /api/engine/settings` keeps `effective` (the stored values, resolved) and adds `effective_flags` (the object above); a row that is on only by implication is `effective_flags[x] and not effective[x]`. `host/finish.py` calls `effective()`. The project capability's `FORCE` sets all five of `run_templates`, `auto_reuse`, `artifact_library`, `artifact_schema` and `template_library` to `False`, so the chain is off for a project run (the `output.selected` trace line lists them under `forced`).
- Why: J2 does the implying inside the run, the app must agree without a second copy of the rule; a project has no template and the content door would serve document text into a working-folder run.
- Rejected: normalising the stored settings (the owner's file would change under them); forcing only `template_library` for project (J2's chain would turn it on again through `auto_reuse`); replacing the `effective` key of the answer (two contract tests pin it).
- Diagram: label "implied flags: effective()", pill on band:DEPARTMENT RUNTIME.

## D179 — The reviewer: on by default, two settings, a host that waits (capped) and discards a late result; patch P19
- Sources: D142, D143, J2 `_make_report`, `_review_later`, `report_gen`.
- Decided: `EngineSettings` gains `reviewer` (bool, `True`, `J2_REVIEWER`, read by the host, not by J2) and `reviewer_wait` (float seconds, `120`, `ge=0`, `J2_REVIEWER_WAIT`, `0` = do not wait). `hooks.review_enabled() -> bool` (`NullHooks` True; `EventHooks` returns its `reviewer` attribute, which the host sets from the setting; `HostHooks` forwards). In `Host._conclude`, first after `inbox.close()` and before `publisher.stop()`, `_join_reviewer` joins `run.review_thread` (when alive) for at most `reviewer_wait` seconds (at most `STOP_WAIT_S` when the run is being stopped); past the cap it increments `run.report_gen` (J2's `_review_later` then saves nothing), writes one `reviewer.late` trace line and joins the thread for `REVIEWER_SETTLE_S` (0.25 s) so a write already begun finishes before the finish steps. A failure of the review thread is a `reviewer.error` trace line and a stderr traceback, never the run's crash.
- Why: the host decides when a run ended and must make the folder stable before it collects, publishes and closes its writer; J2 already has the supersede counter, so no J2 text beyond the switch is needed.
- Rejected: leaving the thread unjoined; a patch that names or joins the thread; default off; a hidden constant for the wait.
- Diagram: label "reviewer: join, cap, switch (P19)", pill on band:DEPARTMENT RUNTIME.

## D182 — The `say` carrier is in scope: `template` and `workflows` travel as two task-only settings keys; the start page gets no control of its own
- Sources: D18, D129, `TASK_SETTING_KEYS`, `TaskSettings`, J2 `POST /api/say` (`RUN.set_run_template`), J2 `set_run_template`.
- Decided: `POST /api/say` accepts `template` and `workflows` (the route is lane U's; the shape rules are `spec.RUN_TEMPLATE_ID_RE`, `spec.run_template_keys`). `DeptCommands.say(text, template=None, workflows=None)` adds `J2_RUN_TEMPLATE` and `J2_RUN_TEMPLATE_WORKFLOWS` to the settings of that one delivery (never to `page.json`). `TASK_SETTING_KEYS` and `TaskSettings` have ten keys; the last two are not `EngineSettings` fields, so `layered()` ignores them and they cannot reach J2's environment. The host calls `set_run_template` after `run.started` and before the first line is posted (J2 refuses once the chat has a line), for a first run only; a refusal is one system line "The run template <id> was not used: <reason>; the team starts from scratch." and a `run_template.requested` trace line, never a refused start. A follow-up ignores both keys.
- Why: the page's links must work, not silently start without the template; the settings channel is validated, stored in the task and visible to the engine without a new column.
- Rejected: hiding the buttons; a new `RunSpec` field and a new `deliver_to_department` parameter; a start-page picker.
- Diagram: label "say carries run template", pill on band:EXPERIENCE.

## D187 — A follow-up never re-fires auto-reuse and does not restore the run template
- Sources: D135, `rehydrate.py`, J2 `_auto_reuse_pick`, `set_run_template`.
- Decided: `rehydrate.py` sets `run.auto_pick = {}` for a continued run (J2's own "already decided" marker) and leaves `run_tpl` as `None`. Both are named beside `RESTORED_CHAIN` (`RESTORED_REUSE`, `NOT_RESTORED_REUSE`), with the reason: the earlier run's template shaped its first plan; a follow-up is a change request on finished work.
- Why: without the marker a follow-up that stamps a charter would score the run templates again and could swap the plan under finished work.
- Rejected: restoring `run_tpl` from `templates.json` (its rows and per-workflow state would steer stages that are already done).
- Diagram: label "follow-up: no auto-reuse", pill on band:EXPERIENCE.

## D188 — The Sutra-side hard-coded behaviour is cleaned by three rules, applied to a list; what stays is named
- Sources: the owner's refactoring task, D165, D166, "agents decide, code validates", `docs/design/function-nodes.md`.
- Decided: three rules. (R-1) A value that is J2's is read from J2 where the layer already imports J2, lazily at first use (`fnodes/registry.py`: `gate()`, `not_checkable()`, `agent_content()`, `user_content()`, `j2_routes()`); where a layer cannot import J2 (`spec.py`) a copy stays, with one parity test in a clean process. (R-2) A value that is a decision leaves code: the word table to `capabilities/data/project.words.json`; the type name has one owner, `project.TYPE`; J2's two form words have one owner, `engine/forms.py`, whose `check_forms` runs at registration. (R-3) A limit stays a named, commented constant with one owner: the follow-up limits are `capabilities/data/project.limits.json`, `AGENT_PURPOSES` is defined once in `hooks.py`, and `ENDED_WELL` reads `events.END_STATUSES`. `tests/engine/test_engine_no_type_names.py` is widened to `website|prd|hld|lld|document|project|business_report` over every `*.py` of `sutra_app/engine/` and `sutra_app/library/` except the 19 vendored J2 modules, with the owners listed by count and reason and one pending entry for a file of the views lane.
- Why: the owner asked for the cleaner design; the three rules separate what J2 owns from what the host decides from what is only a size.
- Rejected: moving every number into settings; deleting the parity of `J2_STRINGS` before J2 posts them as data; a model call to choose `project`; an import-time form check (the host imports the capabilities before it exports J2's environment).
- Diagram: label "hard-coded cleanup: 3 rules", pill on band:DEPARTMENT RUNTIME.
