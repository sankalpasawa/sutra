# J2S5-e as built: the engine application (capabilities, host, settings, views, wire), lane E

Owns `sutra_app/engine/{capabilities,host,api}/**`, `engine/{spec,views,runlist,j2_server}.py`, `capabilities/data/project.*`, the engine tests that
are not V's or U's, `tests/contracts/**`, this note. Spec: `docs/design/j2-sync-5.md` sections 5, 6 (D164 to D169), 7, 8 and 10 (lane E).
Everything is relative to `sutra-pro/`.

## What was built

- **E1 capabilities (D164, D165).** `OutputSpec` is now the description of a type: `name`, `label`, `noun`, `file`, `sections`, `rubric`,
  `check_types`, `done`, the paths of its text files (`conditions`, `builder`, `intake`, `charter_format`, `atom_rules`, `template`), and the
  host-only keys (`single`, `workspace`, `deliver`, `mock_charter`, `mock_section`, `mock_atom`). `to_type_entry(owner)` is the JSON-safe
  `kind: "type"` entry (`form: "document"`, `deliverable: false`, `triggers/groups/depends_on: []`, `export: null`, `cost.item_parts` that prices no item
  as a requirements section, `host: <capability>`); `extras()` is what rides beside it. `capabilities.register(j2)` calls `j2.j2_types.register(entry,
  extras)` for each output; a name that J2, the local store or another capability owns is a `CapabilityConflict` (all or nothing). There is no
  `j2.OUTPUTS` and no `to_j2`.
  The five project files are flat in `capabilities/data/` (`project.builder.md`, `project.intake.md`, `project.charter.txt`, `project.atom_rules.md`,
  `project.generic.json`; `project.json`, the conditions, was there). `project.py` reads builder and intake from them (one closing newline stripped,
  as `j2_types._text` does); the rest are read by J2. The plan guidance (`PROJECT_PLAN`, now naming the `sections` field) is part of the Adaptation
  addendum. `Selection.output` is `Optional[str]`; `select.py` lost the `deliver` phrase list and the `default` rule; the fall-through is
  `Selection(None, "planner", "the team's planner chooses")`; `EngineContext.output` is `None` while no type is chosen.
- **E2 settings (D166, D169).** `EngineSettings.output` is `auto` or a name matching `OUTPUT_NAME_RE` (`[a-z][a-z0-9_]{1,40}`), also in the env
  reader (lower-cased, shape-checked there so a layer reports every bad variable at once); `OUTPUT_NAMES` is gone (`orchestrator/models.py`
  `TaskSettings.J2_OUTPUT` takes the same shape: that file had to change, it imported the removed list). `builder_timeout` (float, 600, `ge=0`, 0 = no
  limit, editable, `J2_BUILDER_TIMEOUT`). `GET /api/engine/settings` answers `output_types` (`[{name, label, form, pin}]`, in `types.json` order, `pin`
  true for a deliverable type or a host type); `GET /api/engine/capabilities` answers `outputs = j2_types.names()`; `PUT` refuses an unknown output name
  (`set.output`, code `unknown_output`). `api/commands.py` `_output_type` returns `auto`, a known name, else `None`. The host checks membership right
  after `capabilities.register(j2)` (`_check_output_known`): an unknown type the owner pinned is `Could not start: unknown output type X (known: ...)`
  in the chat; a follow-up whose earlier type no longer exists falls back to the planner with one trace line (`output.unknown`). With no type chosen
  the host leaves `J2_OUTPUT` unset, `settings.json` says `auto`, `output.json` says `output: null`, `chat.jsonl`'s start row says `output: null`.
  `api/__init__.py` exports `J2_TYPES_DIR=<default data dir>/types` (unless already set) before anything imports J2.
- **E3 views and wire (D167 engine part, D168).** `EMPTY_LIVE` has `output`/`out_label` `null`, `live_state` reads `(run.out or {}).get("label")`; the live
  page stub calls the thing by the run's own label (`result` when there is none); `docs` is J2's `docs_view` over `j2_artifacts.load_types(run_dir)`;
  `refs` walks `j2_types.names()` with `j2.output_def`; `file` allows the run's own type file (none for no type) and the `documents.json` keys;
  `stage_words()` from `J2Run.stage_words()` in `views.py` and `host/publisher.py`; `runlist.run_row` gives `label` and `form` (empty for no type),
  through `j2_types.info`, or `j2_types.recorded` for a type the store lost; new route `GET /api/timing` (`views.timing`, `HANDLER_COUNT` 42, the
  FastAPI route in `api/state.py`, the stdlib route table). `artifacts_groups` already merged the capability row after J2's by id: unchanged.

## Deviations from the design, and why

1. **The drift guard of the atom rules and the charter reads the `prd` type's files, not the `document` type's.** The design says
   `project.atom_rules.md` equals "the vendored document atom rules with the four edits"; the document type's `atom_rules.md` is a different text (no ids,
   "section names"), while sync 4's project rules were `PRD_ATOM_RULES` with the four edits, and `templates/prd/atom_rules.md` equals `PRD_ATOM_RULES`
   (finding 5). Byte-identical project prompts (the owner's rule) need the PRD text, so the guard compares with `templates/prd/atom_rules.md` and
   `templates/prd/charter.txt`.
2. **`OutputSpec.name` and `tag` are new fields**, and `register` requires an `OutputSpec` whose `name` is its key (plain dicts are not accepted
   any more; `Capability.documents` still reads a dict spec).
3. **The live run's `/api/timing`** reads the run folder (`timing.json` once saved, else the record rebuilt from `calls.jsonl`, `from_calls_only`): the
   API process has no `J2Run` (the host process holds it), so J2's `RUN.timing()` cannot be called.
4. **`_chat_system_line`** writes `output: null` in the start row when nothing is pinned.
5. **A working folder now claims a brief that names a deliverable** ("build a florist site" with a folder set selects `project`, rule `folder`): the
   `deliver` rule used to answer first. That follows from removing the phrase list (D165); the owner's pin or the start page's choice still wins.

## Decisions (text for `docs/DECISIONS.md`, D164 to D169, engine part)

Taken as written in `docs/design/j2-sync-5.md` section 6, with these as-built amendments, so the integrator copies the design text and adds the lines
below to the Decided paragraph of each:

- **D164**: "The drift guard of the project atom rules and charter reads the `prd` type's files (deviation 1); `OutputSpec` carries `name` and `tag`;
  `register` takes `OutputSpec`s only."
- **D165**: "A working folder claims a brief that names a deliverable (deviation 5). The rule names are `owner, project, followup, weak, folder, planner`."
- **D166 (backend)**: "`PUT` of an unknown `output` is the violation `unknown_output`; a follow-up whose type is gone is left to the planner (trace line
  `output.unknown`)."
- **D167 (engine part)**: "The live page stub says `result` while no type is chosen."
- **D168**: "`/api/timing` of a live run reads the run folder (deviation 3)."
- **D169 (backend)**: "`builder_timeout` is exported as `J2_BUILDER_TIMEOUT` (`0` or `0.0` for no limit)."

## Measurements

(see the end of this note, filled when the lane's tests ran on top of V-core)
