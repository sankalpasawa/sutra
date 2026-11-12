# Word matching left in j2.py (follow-ups)

Branch `validator-speed` replaced word matching in two places: the sections a document workflow writes (its `sections`
field, checked exactly against the type's template or the sections the deliverables plan declared for a new type) and
whether a workflow is Audit's job (its `kind`: `build` or `audit`). The decisions below still read words. None of them
changed on this branch. Line numbers are j2.py as of the commit that adds this file.

| # | Where (j2.py) | What the words decide | Field that would replace them |
|---|---|---|---|
| 1 | `item_kind` 237, `item_min` 243; data: `types.json` `cost.item_parts` | Which rate-card part a done-when item needs at least, read from the item's words. Used by `_underpriced` 7581/7583, `_per_item` 7053, STATE `item_minimums` 3310-3311, `_cheapest_fit` 6816/6819, `_flag_unpaid` (UNPAID) 9978, `_left_by_ruling` 6847, the realization plan's cost 6162, the mock planners 5714/5796/6411/6585 | A part per item marked by Identity in the charter, or `covers: [{item, part}]` on each workflow |
| 2 | `BUDGET_TALK` 254, `_budget_question` 6804-6806 | Whether Adaptation's POLICY_QUESTION is about budget (it is rejected) | `question_topic` on the reply (`budget`, `policy`, ...) |
| 3 | `_plan_gaps` 6571 (the `plan` regex in `conditions/<type>.json`) | Whether a necessary condition has a workflow: some proposed or registered workflow's JSON mentions the condition's words | `conditions: [condition id]` per workflow |
| 4 | `_template_need` 9130 | What a section must carry: the covered items and charter facts, matched by words for a page section | `facts` per workflow or per atom |
| 5 | `_finding_item.like` 9722 (in `_finding_item` 9718) | Which done-when item an Audit finding is about when its number doesn't fit, by shared words | `item` on every finding (Audit's reply), required |
| 6 | `PLAN_NAME` 7260, `_plan_name` 7262, `_plan_row` 7366 | Which realization-plan row a fix or a change's revision belongs to, by stripping "Revise W-n " / "Fix " / " (change n)" from its name | `revises` and the plan row's `id` |
| 7 | `check_problems` 708, `target_problem` 568, `css_problem` 535, `behavior_problems` 609, `untold_selector` 675; regexes `SPECIFIC` 333, `FACT_VALUE` 337, `NEGATED` 340, `NAME_WITH_DIGIT` 352, `ACTION_GOAL` 356, `DATE_RULE` 359, `DATE_CONTROL` 361 | Whether an atom's checks fit its goal: a goal with a number needs a facts check, an action goal needs a behavior item, a date rule needs a date control, a selector must be named in how.steps | On the atom: `creates` (ids and classes it makes), `facts` (charter strings it shows), `needs_behavior` (bool) |
| 8 | `facts_to_headings` 1052 | Whether a facts-present string in a file workflow's atom is really a heading (short, no digit, not in the charter) | `expected_output` items of kind `heading` |
| 9 | `NOT_CHECKABLE` 4588, `_stamp_check` 4591 | Whether a done-when item can be checked by code or Audit (words like approve, launch, sign off) | `checkable_by` per done-when item (`code`, `audit`, `requester`) |
| 10 | `_blames_other` 9036 | Whether a builder's report puts the cause of its failure in another workflow's section | `cause_in: "W-n"` on the builder's reply |
| 11 | `_supersede` 7523 | Whether a new workflow replaces a waiting one: the same name once " (change n)" is stripped, case folded | `revises` / the replaced workflow's `id` |
| 12 | `is_artifact` 1595, `_file_wf` 6761 | Whether a workflow's output is a file later workflows read, from the shape of its `outputs` strings | `kind: "file"` as a third `kind` option |
| 13 | `must_keep` 258 fallback: `CORE_FACT` 252, `NO_ERRORS_GATE` 249 | Which done-when items can't be left out for budget, when the charter has no `core_items` | `core_items` already exists (Identity marks them at J2.a); drop the keyword fallback |

## Mock-only matching (not a validator decision)

| Where (j2.py) | What |
|---|---|
| `_mock_doc_plan` 6406 (`sec_of`) | The mock planner's covers: a done-when item belongs to the first section its words name |
| `_audit_doc` mock 9922 | The mock Audit reads the section a done-when item names |
| `_mock_board_answer_doc` 8914 | The mock answer reads the section its workflow's name ends with |

## Removed on this branch

`match_sections`, `SEC_STOP`, `_fill_sections`, `_doc_remap`, `_fix_sections` (and its finding-text path), `CHECK_WORK`,
`AUDIT_FIRST`, `AUDIT_LAST`, `BUILD_VERB`, `_audit_name`, `wf_sections`' name fallback, the "name inside target"
heading-check rule in `_atom_problems`, and the section-by-words lookups in `_gap_rows`, `_identity_limit` and
`_board_doc_owner`.

## Form-name checks and send code (cleanup after agent-tools)

Branch `agent-tools` adds builder tools and a folder form whose code reads only `artifacts/types.json` (a form's
`tools`, `allow`, output kind and checks). The code below predates it and still names forms, or sends email and Slack
messages. None of it changed on that branch. Line numbers are as of the commit that adds this section.

### Form names in code

| Where | What it decides | Data that would replace it |
|---|---|---|
| `j2.py` `is_page` 2442-2444; callers 2657, 2963, 4070, 4228, 4356, 5121, 9211, 9250, 9397, 9422 | Whether a type is a page (`form == "page"`) | The form's output kind and its own fields (`essentials`, `style_guide`, `preview`) |
| `j2.py` `_apply_output` 3141 (`self.doc`, used in 77 places) | Document or not (`form == "document"`): prompts, check types, file names, export | The form's output kind and fields (`sections`, `export`, `file`) |
| `j2.py` `_plan_stages` 3956 | Which chosen types run first as documents | A stage order in the forms' data |
| `j2.py` `PAGE_FILE` 333, `SITE_FILES` 1625 | The page form's file, read by name | The current form's `file` |
| `j2_types.py` `FORMS` 18, `DOC_NEEDED` 20, `load` 320, `named` 243-246, `page_type` 249, `style_guide` 90, `create` 418 | Required fields and lookups per named form | Required fields declared per output kind in `types.json` |
| `j2_artifacts.py` 41, 89, 362, 384-386, 644 | Rows, open view and version files by form name | The form's `preview` and output kind |
| `j2_realization.py` `type_list` 281 | Only documents have `needs` | `depends_on` for every form |
| `j2_agent_views.py` 35; `j2_server.py` 366; `j2_studio.py` 204 | Document types only; a page means "site" | The form's output kind |
| `j2_ui.html` 2362, 2777, 2806, 2941 | Tabs and icons by `"page"` or a document type name | The form's `preview` |

### Send code (email and Slack)

| Where | What |
|---|---|
| `j2_send.py` (whole file, 269 lines) | Send deeds by channel (email, Slack), detected from the brief's words, with test and live modes |
| `j2.py` 225-227 `RATES_DEED`; 839 `deed-send` check | Deed prices; the receipt check |
| `j2.py` 3958-3968, 3981-3983 (`_plan_stages`) | Deeds read from the brief; the note naming an email address or Slack target |
| `j2.py` 4068-4080, 4216-4217, 4249-4336 (`_deed_stage`, `_confirm_send`, `_identity_send_confirm`, `_send_args`, `_send_status`, `_send_note`) | The send stage, its confirmation and receipts |
| `j2.py` 4353-4410 (milestone email, `_deeds_finished`) | The milestone email after a build |
