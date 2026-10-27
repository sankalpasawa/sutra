# The layers' interface, as JSON Schema

| Field | Value |
|---|---|
| **status** | Generated, schema version 1 (PRD amendment A1, wave 0; the templates at every level added by amendment A3) |
| Source of record | `layer_schema.py`, the interface of Root and the five layers, hard-coded |
| Rule | Every file here except this README and `fixtures/` is generated from `layer_schema.py` and never edited by hand: run `python layer_schema.py --write` in the commit that changes the interface. A conflict in a generated file is resolved by running it again. `test_layer_schema.py` fails when a file here differs from what the code generates |
| Implementation | Each layer's behaviour, its recipe and its step bodies, is `layers/<layer>/v<N>.py` and `v<N>.json`; the interface here changes only with a new schema version and a migration (A1.21) |

## Per layer: the `layer_schema` names that hold it

| Layer | Its entries in `layer_schema` |
|---|---|
| Root | `LAYERS['root']`; the department keys `DEPARTMENT_KEYS` gives to root (kind, ref, name, engines, artifacts, workflows, layers, ...); `RECORDS['root']` (department, registration, pins, engine); `DEFS` department, `department.*`, `root.pins`, `engine.template`, `workflow`, `workflow.engine`, `workflow.check`, `workflow.registration`; `WORKFLOW_STANDARDS` and `STAGES` (their code is `workflow_schema.py`); `SENDS['Root']`; `CALLS` from Root; `VERDICTS['root']`; `CHECKS['root']`; `PROMPTS['root']` and `GROUPS['root']` (setup: converse, shape); `OPTION_KINDS` root_setup and pin; `MIGRATIONS` |
| Identity | `LAYERS['identity']`; its keys in `DEPARTMENT_KEYS` (goal, done, done_items, to_be_confirmed, rules, owner, windows, ...); `RECORDS['identity']` (done_item, rule, ask); `DEFS` `identity.done_item`, `identity.rule`, `identity.ask`, `option`, `option.words`; `ASK_KINDS`, `ASK_STATUSES`; `HEARS['identity']`; `SENDS['Identity']` (the only one with Owner among its destinations); `CALLS` from Identity; `VERDICTS['identity']`; `CHECKS['identity']`; `SETTINGS['identity']`; `PROMPTS['identity']` and `GROUPS['identity']` (goal, completeness, take); `OPTION_KINDS` words, leave and stop; `VIEWS['identity']` = `view.identity` |
| Adaptation | `LAYERS['adaptation']` (no department key); `RECORDS['adaptation']` (proposal, idea, ladder, round); `DEFS` `act.line`, `adaptation.idea`, `adaptation.ladder`, `adaptation.round`, `act.doubt`, `act.round`; `HEARS['adaptation']`; `SENDS['Adaptation']` (propose and inform only); `VERDICTS['adaptation']`; `CHECKS['adaptation']`; `SETTINGS['adaptation']`; `PROMPTS['adaptation']` and `GROUPS['adaptation']` (goal, sense, decide, make); `VIEWS['adaptation']` = `view.adaptation` |
| Priority | `LAYERS['priority']`; its keys in `DEPARTMENT_KEYS` (envelopes, ceiling); `RECORDS['priority']` (envelope, price, ceiling); `DEFS` `envelope`, `priority.estimate`, `priority.price`, `priority.ceiling`, `option.raise`; `HEARS['priority']`; `SENDS['Priority']` (to Adaptation only, never an order); `VERDICTS['priority']`; `CHECKS['priority']`; `SETTINGS['priority']`; `PROMPTS['priority']` and `GROUPS['priority']` (goal, bargain); `OPTION_KINDS` raise; `VIEWS['priority']` = `view.priority` |
| Coordination | `LAYERS['coordination']` (no department key: its record is coordination.json); `RECORDS['coordination']` (table, slot, question); `DEFS` `coordination.table`, `coordination.slot`, `coordination.left_out`, `coordination.question`, `act.question`, `act.answer`; `TABLE_FIELDS`, `SLOT_FIELDS`, `LEFT_OUT_FIELDS`, `BORN_FIELDS`, `BOUNDS`, `CHAIN_LIMIT`; `HEARS['coordination']`; `SENDS['Coordination']`; `VERDICTS['coordination']`; `CHECKS['coordination']`; `SETTINGS['coordination']`; `PROMPTS['coordination']` and `GROUPS['coordination']` (goal, tie); `OUTPUTS`; `VIEWS['coordination']` = `view.coordination` and `VIEWS['engine_card']` = `view.engine_card` (`COORDINATION_FIELDS`, `TIMETABLE_ROW`, `ENGINE_CARD_FIELDS`, `ENGINE_FIVE_ROW`) |
| Audit | `LAYERS['audit']` (no key, no artifact: the checker is never the writer); `RECORDS['audit']` (finding, reading, spot_check); `DEFS` `act.finding`, `audit.reading`, `audit.reading_item`, `audit.finding`, `audit.spot_check`, `act.reading`; `HEARS['audit']` (none); `SENDS['Audit']` (to Identity only); `VERDICTS['audit']`; `CHECKS['audit']`; `SETTINGS['audit']`; `PROMPTS['audit']` and `GROUPS['audit']` (goal, judge); `VIEWS['audit']` = `view.audit` |
| Shared | `SCHEMA_VERSION`, `LAYER_NAMES`, `ACTORS`, `ACTS`, `DEFAULT_PINS`, `MODE`, `NEVER_REFUSE`, `REFUSED`; `SHARED_CHECKS`; `CONTRACT_SAMPLES`; `SINK` and `SINK_JOURNALS`; `edges()`, `check()`, `check_act()`, `check_department()`, `migrate()`, `describe()`; `TEMPLATE_LEVELS`, `ASK_FORMS`, `LEDGER_ACTIONS`, `RECOGNITIONS` (amendment A3) |

## Per level: the templates (PRD amendment A3)

A template is an interface is a base class, at every level; what fills it is a child, a module or a data file that conforms. `TEMPLATE_LEVELS` holds the table of levels as data (the sentence a child keeps and the ids of the rules that hold it), and `template_checks.py` the rules a type cannot say.

| Level | Its entries in `layer_schema` | Its children |
|---|---|---|
| L0 User journey | `DEFS` `journey` and `journey.lane`, `.bind`, `.branch`, `.step`, `.outcome`, `.edge`, `.sub`, `.ruling`, `.quote`, `.scenario`, `.backlog`, `.direction`, `.build_row`, `.was`, `.file`, `.row_status`, `.status`; `JOURNEY_KINDS`, `LANE_KINDS`, `STEP_ACTS`, `BIND_KINDS`, `OUTCOME_KINDS`, `OUTCOME_VOICES`, `SITE_STATUS`, `DISPOSITIONS`, `ROW_STATES`, `READ_STATES`, `JOURNEY_STATES`, `RULING_STATUS`; the id grammars `JOURNEY_ID`, `SUB_ID`, `STEP_N`, `EDGE_ID`, `LANE_ID`, `BACKLOG_ID`, `SAME_AS`, `SYMBOL`, `TEST_REF`, `STEP_REF`, `RULING_ID`; `LEDGER_ACTIONS`, `RECOGNITIONS` | `journeys/*.json` |
| L1 Department kind | `DEFS` `kind`; `template_checks.kind_faults` | the kinds of `engine_defs/website.json` |
| L2 Function | the layer's interface (`LAYERS`, `HEARS`, `SENDS`, `CHECKS`, `PROMPTS`, `VIEWS`) extended by the function template: `FUNCTION_TEMPLATE` (the five functions and Root: role, is not, never, hands on to, `in_card`), `DEPARTMENT_AGREEMENT`, `TEMPLATE_PARTS`, `ROLE_INPUTS`, `ROLE_BLOCK_MAX`, `TEMPLATE_BANNED`, `TEMPLATE_BANNED_AGENT`, `TEMPLATE_NEVER_SAY`; `template_checks.function_template_faults`, `agreement_faults`, `hands_on_faults` | `layers/<layer>/v<N>.py`; the Default and use-case templates under `function-templates/` |
| L3 Engine and workflow | `DEFS` `engine.library`, `engine.start`; `engine.template` is its born child (it requires `made_by`); `workflow`, `workflow.engine` | `engine-templates/*.json`; the `_library` of born templates |
| L4 Step | `DEFS` `step` (every field `x-law` fixed or free), `step.row`, `engine.start`; `NATURES`, `RUNGS`, `GATE_ANSWERS`, `STEP_KINDS`, `STEP_CTX`, `STEP_ROW`, `MODEL_TOOLS`; `step_kind()`; `template_checks.step_faults`, `step_law` | the steps of `layers/<layer>/v<N>.json` and of `engine-templates/*.json` |
| L5 Artifact | `DEFS` `artifact.template`; `template_checks.artifact_faults` | `artifact-templates/*.json` |
| L6 Ask | `DEFS` `identity.ask`; `ASK_KINDS`, `ASK_STATUSES`, `OPTION_KINDS`, `OPTIONS_MAX`; `ASK_FORMS` | one form for each kind of ask |

## The files

| File | What it holds |
|---|---|
| `department.schema.json` | dept.json as the interface types it, each key's owner in `x-owner` |
| `workflow.schema.json` | workflow, workflow.engine, workflow.registration and workflow.check; Root's standards in `x-standards` |
| `records.schema.json` | every layer record: asks, done-when items, rules, Coordination's table and slots, prices, the ceiling, readings, findings, rounds, questions between engines, spot checks, engine templates (`x-records` maps each layer's records to them) |
| `acts.schema.json` | every board act's payload (`act.*`), the edges (`x-edges`) and the words each actor sends (`x-sends`) |
| `instructions.schema.json` | `{ref}/instructions.json` and the field types of every prompt part (`x-fields`) |
| `views.schema.json` | the panes' read models the UI renders and its fixtures are checked against |
| `templates.schema.json` | the step and its row, an engine's start, the department kind, the Library's engine template and the artifact template; `x-levels` holds the seven levels, `x-steps` the constants of the step and `x-ask-forms` the form of each kind of ask |
| `journeys.schema.json` | the user-journey template and its parts, and the status document computed for each journey; `x-ledger-actions` and `x-recognitions` |
| `interface.v1.json` | `describe()`: the whole interface as JSON, what `GET /api/native/{ref}/layers` serves the parts of |
| `fixtures/department.v0.json`, `fixtures/department.v1.json` | a department record from before A1, and the same record as the migration reads it (written by hand; `migrate('department', v0) == v1`) |
| `fixtures/workflow.<kind>.good.json`, `fixtures/workflow.bad.<standard>.json` | one workflow for each of the four kinds that passes every stage, and one for each of Root's standards that fails exactly that one (written by hand; `workflow_schema.py` is the code of the standards, and `test_layer_root.py` runs the fixtures through it) |
| `fixtures/view.audit.v1.json` | Audit's pane (`view.audit`, S12) in the four states its screen draws: nothing read, a reading with an item not met and one to confirm, a version not read, every item met (written by hand; each validates as `view.audit`) |
