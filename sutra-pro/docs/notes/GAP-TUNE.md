# GAP-TUNE as built: reply classes and write scope tuned on the golden run (G14)
## Built
- `library/functions.py` (L5). The nine refused replies were three defects, loosened in validators only (no field changed, so the
  exported schemas, the transport schemas and every J2 prompt are byte-identical; `reply-valid` untouched):
  1. `Intake` (1 atom): J2's charter has no `kind`. A `before` validator fills it with `goal_kind(goal)` (document when it names a
     product, else site); a goal that says its kind keeps it, and the rest of the charter is still checked.
  2. `Propose`, `Respond`, `Price` (7 atoms): J2 words a workflow with `atoms` and no `id`; the class says `steps` and wants `id`.
     `workflows` is now `_ReplyWorkflows` (same JSON schema, array of `ProposedWorkflow`, at most 20) whose items go through
     `from_j2` (atoms) or get `P-<position>` (steps, no id), with the parser's tolerant pass applied; errors are reported at
     `workflows.<i>.<field>`. It is a class of its own because `ReplyParser` drops undeclared keys (`atoms`) before any validator runs.
  3. `AtomVerdict` (1 atom): BUILD_WRONG may leave out `build_wrong_reason` when `say` carries the words (J2:9021 reads a missing one as
     "no specific reason"; its own mock does that). Neither present is still refused; `affordable` is still required.
- Write scope: terms `conflict positions` (Adaptation, Priority: `conflicts.json`) and `split registrations` (Identity: `workflows.json`)
  in `function_specs.json` and in `WRITE_TERMS`. The re-recorded run shows no other miss: `touches_miss == {}`.
- Golden re-recorded: 31 atoms, all `closed`, `touches_miss == {}`, prompt digests unchanged. `--check` is green.
- `tests/engine/test_engine_fn_tuning.py` (36 tests, ~5 s): one test per refused J2 reply and for what stays refused, schemas unchanged,
  the new terms, `enforce` still reserved (G18), the mock run (live) has no `verify_failed` outside `ALLOWED_VERIFY_FAILED`
  (empty today; a key is `(function, check)`, a value is the reason) and no `touches_miss`, the guard itself on synthetic events.
## Report (the table `check_report` makes from the golden events: `scripts/py tests/engine/test_engine_fn_tuning.py`)
| check | judged | failed | recovered | waived |
|---|---:|---:|---:|---:|
| answer-recorded / atom-rules / audience-split | 1 / 5 / 4 | 0 | 0 | 0 |
| charter-stamp / code-measure-wins / finding-per-item | 2 / 2 / 2 | 0 | 0 | 0 |
| judge-gate / order-registered / pass-needs-proof | 3 / 7 / 2 | 0 | 0 | 0 |
| price-kept / workable / within-budget | 3 / 2 / 8 | 0 | 0 | 0 |
| reply-valid / turn-posted | 21 / 30 | 0 | 0 | 0 |
(Three checks per row to fit 45 lines; the script prints one row per check. No recovered or waived close in the mock run.)
## Deviations (all decided on my own, owner asleep)
1. `WRITE_TERMS` lives in `engine/fnodes/layer.py` (E6, last held by GAP-W1), not in `registry.py`, and `registry.py` has no `touches`
   parser; `layer.py` was edited for the two dictionary entries only (the one unowned file touched). `registry.py` is unchanged.
2. `scripts/record_fn_golden.py` is not an owned path, so it has no `--report`; the same table is made by `check_report` /
   `render_report` in the tuning test and printed by running that file. A one-line `--report` calling it is a follow-up.
3. Existing tests changed because the intended behaviour changed (none weakened beyond what G14 asks): `test_lib_functions.py::
   test_atom_verdict_rules` (the two BUILD_WRONG refusals now also blank `say`); `test_engine_fn_golden.py::
   test_a_failed_close_keeps_the_atom_open...` (no longer asserts that some atom is abandoned; the retry path stays pinned by
   `test_engine_fn_layer.py`) and `::test_the_golden_atoms_file_tells_the_story_per_function` (no failing check, `touches_miss == {}`); also `test_contract_run_events.py` (169 -> 151 golden lines) and `test_projector_fnodes.py` (151 lines; ledger statuses are only `closed`; `verify_failed` stays covered by its other tests).
4. The allow-list is empty: the mock run has no intended `refused` or `abandoned` atom (stop/abandon are covered by GAP-W1 tests).
## Decisions
- A workflow's `id` is its position (`P-1`..) when J2 gave none; the registered id (`W-n`) is the validator's, not the reply's.
## Known limits
- Real replies are untested (G07): tuned on J2's mock only; GAP-LIVE adds `ALLOWED_VERIFY_FAILED` entries only with a reason. Enforce stays reserved (G18).
- A real structured-output reply (library shape: `steps`, `id`) and a J2-shape reply are both read; mixed shapes are not repaired.
- Mutation pass (14 breakages): 13 killed, 1 survivor (`removeprefix("Value error,")` without the space leaves a leading space in a
  message; cosmetic, no test worth it).
