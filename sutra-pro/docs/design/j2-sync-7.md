# J2 sync 7 as built: the engine takes J2 main `dee83d5c` (note of record)

_Status: As built on branch `app-one-front` (not pushed, not tagged) · Date: 2026-11-16 · Pin: commit `dee83d5c565fe7d82631a4f7eb555543160a6d41`, tree `b9a14370c35a6309062821b549b311d662a8ed3d` · Page: J2 `133942b1` (studio-combine: the owner's studio design with J2 main `dee83d5c` merged in) · Decisions D239 to D241._

## A. What moved

- **Engine** (`scripts/vendor_j2.py`, D239): 527 files. Disha's two merged PRs are in: remove-restrictions (#202: builders with tools on one general path, folder outputs typed by the planner, a planned real run behind `RUN <code>`, the sandbox off by default) and group C (#203: hard-coded decisions become fields the agents set). New data: `conditions/agent.json`, `templates/agent/`, `templates/atom_rules.md`, `templates/builder.md`, `artifacts/real_run.md` (the `artifacts/` folder is now a vendored tree). New reference docs: `remove-restrictions-plan.md`, `remove-group-c-plan.md`, `planner-thresholds-proposal.md`.
- **Page** (`scripts/port_j2_ui.py`): the 40 edits apply with no anchor moved; the page has one artifact view (no Documents tab) in the studio's look. Goldens re-derived with J2's harness on the new page over the 1adb8ecd capture: only `golden-rail.json`, `golden-railst.json` and `render-docs.json` (the rail's tab list) changed.

## B. Patch verdicts

| Patch | Verdict at dee83d5c |
|---|---|
| P1 | re-anchored: `j2_artifacts.py` has 7 sibling imports (was 5); 44 lines in all |
| P7 | re-anchored: `J2Run.call` passes `tools=tools` on, so the tagged `_ask` keeps J2's new argument |
| P8 | re-anchored: the import block (`subprocess` and `tempfile` sit between `shutil` and `threading`) |
| P17 | re-anchored: `create` and `_create` take the planner's `form` (J2 no longer picks one) |
| P2, P3, P4, P5, P9, P10, P11, P12, P14, P15, P16, P18, P19 | applied unchanged |
| dropped | none |

## C. Where Sutra met Disha's changes

1. **`engine/forms.py` fought "J2 does whatever a prompt asks"** (D241). It required J2's form list to be exactly page and document, and J2 removed the `FORMS` constant for data-defined forms with a third, folder-making `agent` form; the engine would not start. It now reads `j2_types.forms()`, allows any form whose `output` is `folder`, and still stops on a new file form.
2. **Builder tools** (D240). Sutra's `llm` shim has no tools seam (the router and the connectors run plain completions). It now has J2's new surface (`tools_on`, `can_use_tools`, `TOOLS`, `sandbox_on`, `inside`, `ask(tools=)`), with tools off for a live run: J2 takes its section path, and folder outputs, the real run and the test rerun are not offered (`j2_realization.type_list` drops a folder form when tools are off). Offline, `J2_AGENT_TOOLS=1` turns J2's general path on with scripted replies, as in J2, so the legacy flow test walks it.
3. **No sandbox by default**: nothing in Sutra re-imposes a sandbox; `sandbox_on()` is J2's switch. With tools off there is no builder command to confine.
4. **The library's closed models refused J2's new fields** (strict records and the `reply-valid` check): `goal.json` now holds `item_kinds`, `exact_facts`, `date_rules`, `email_updates`; Identity's intake reply carries `email_updates`, `item_kinds`, `exact_facts`, `date_rule_items`; J2.h questions are objects (`question`, `kind`, `item`); a question may name its `plan_option`; Adaptation's POLICY_QUESTION names its `about`; Coordination's schedule names `ready_now` and no longer `next`; chat lines gain `ready_now` and `real_run`. All are added (schemas re-exported); before, every scheduling atom of the mock run ended `verify_failed`.
5. **The charter stamp** (`fnodes/registry.stamp_check`) is J2's again: a statement and the form's `min_done_when`; J2 deleted `NOT_CHECKABLE`, so `not_checkable()` is gone (the `fail_not_checkable` fixture became `pass_words_are_not_read`).
6. **Capability rows** carry J2's new Summary keys (`conditions`, `warnings`, `failed`, `failed_checks`, `retried`, `real_runs`, `template`, `type_label`).

## D. Tests that moved

- Legacy flow test: three-way merge (base J2 1adb8ecd, ours the sync 6 copy, theirs dee83d5c), 3 conflicts, each J2's new text plus the existing port edit. New J2 blocks that read J2's own files sit in `skippable`; `agent_tools_cli` (J2's own claude-cli runner) is rewritten for the shim. `--fast`: 118 ok lines, 181 with an extraction.
- `realization_test.py`: J2's own check "'8 practice starts' needs no facts-present" fails at dee83d5c in J2 too (since aebddc0b no word of the goal is read); the copy keeps the half the check is named for, and the fact loop passes `rules={"facts": True}`.
- Goldens: the seven prompt goldens and `api_shapes.json` re-recorded from J2 at the pin.

## E. Reported upstream

- J2's `realization_test.py` fails on main (item D above).
- J2's flow test blocks `left_bar_toggle`, `artifacts_groups`, `map_motion`, `map_tab`, `map_focus` and `graph_map` read local saved runs (J2's own plan lists them as skips).
- One real-model run on the app (Calm Flow brief, 2026-11-16): J2's planner chose a PRD and then the website for "a one-page website"; the PRD took three of five workflows, so the contact form was never proposed before the cycle limit and the run ended "Done with open items" (44 calls, $2.77, 27 minutes).
