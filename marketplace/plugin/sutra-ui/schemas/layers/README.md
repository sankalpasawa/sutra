# The layers' interface, as JSON Schema

| Field | Value |
|---|---|
| **status** | Generated, schema version 1 (PRD amendment A1, wave 0) |
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
| Shared | `SCHEMA_VERSION`, `LAYER_NAMES`, `ACTORS`, `ACTS`, `DEFAULT_PINS`, `MODE`, `NEVER_REFUSE`, `REFUSED`; `SHARED_CHECKS`; `CONTRACT_SAMPLES`; `SINK` and `SINK_JOURNALS`; `edges()`, `check()`, `check_act()`, `check_department()`, `migrate()`, `describe()` |

## The files

| File | What it holds |
|---|---|
| `department.schema.json` | dept.json as the interface types it, each key's owner in `x-owner` |
| `workflow.schema.json` | workflow, workflow.engine, workflow.registration and workflow.check; Root's standards in `x-standards` |
| `records.schema.json` | every layer record: asks, done-when items, rules, Coordination's table and slots, prices, the ceiling, readings, findings, rounds, questions between engines, spot checks, engine templates (`x-records` maps each layer's records to them) |
| `acts.schema.json` | every board act's payload (`act.*`), the edges (`x-edges`) and the words each actor sends (`x-sends`) |
| `instructions.schema.json` | `{ref}/instructions.json` and the field types of every prompt part (`x-fields`) |
| `views.schema.json` | the panes' read models the UI renders and its fixtures are checked against |
| `interface.v1.json` | `describe()`: the whole interface as JSON, what `GET /api/native/{ref}/layers` serves the parts of |
| `fixtures/department.v0.json`, `fixtures/department.v1.json` | a department record from before A1, and the same record as the migration reads it (written by hand; `migrate('department', v0) == v1`) |
| `fixtures/workflow.<kind>.good.json`, `fixtures/workflow.bad.<standard>.json` | one workflow for each of the four kinds that passes every stage, and one for each of Root's standards that fails exactly that one (written by hand; `workflow_schema.py` is the code of the standards, and `test_layer_root.py` runs the fixtures through it) |
