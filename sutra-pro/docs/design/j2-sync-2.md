# J2 sync 2: the baseline moves to `9200cf6` (ABS-0)

The vendoring baseline was `33aeeda` (see `j2-sync.md`). It is now **J2_Prototype `9200cf626e5c05032caefda4f96b694284efdc5e`** (main on 2026-11-06, PR #31 `template-library-fixes`, 9 commits, 5 files). The prototype's own repository is the source (as design risk 7 says); `scripts/vendor_j2.py --source <checkout> --check` passes against it.

## What landed (the five diffs of `33aeeda..9200cf6`)
| J2 file | Change | Where it is in Sutra Pro | Covered by |
|---|---|---|---|
| `j2.py` | `parse_decision` reads negation (`affirmed`, `NEGATION`, `OPTION_WORDS`): a negated option never selects it, the affirmed one wins, all negated asks again; `template_line` writes the one chat line of a template decision (an overruled extend shows the coverage that overruled it) | vendored `engine/j2.py` (patches P1-P5, P7-P9, P11 re-applied by anchor, no anchor moved) | the vendored `j2_flow_test.py` (legacy suite `tests/engine/legacy`), run with `SUTRA_SLOW=1` |
| `j2_template_lib.py` | the router overrules an extend of a candidate that covers under 0.5 to a create (`EXTEND_MIN`; `_accept` returns the action taken; a numbered name when the generator kept the candidate's) | vendored `engine/j2_template_lib.py` (P1, P10, P12) | the vendored flow test, plus the library tests |
| `j2_artifact_models.py` | `inline_definitions`: the first page builder's reply schema is written with its definitions in place (a nested `definitions` block made `claude -p --json-schema` refuse it) | vendored `engine/j2_artifact_models.py` | the vendored flow test (block (h), the `$ref` check of the reply schema) |
| `llm.py` | a refused `--json-schema` (exit 1, no stdout, reason on stderr) is reported with the exit code and the stderr text | J2's `llm.py` is not vendored: the seam is Sutra Pro's `engine/llm.py` over the Claude connector, which already reports `CrashedError(exit, stderr)` for that case | `tests/connectors/test_claude_errors.py::test_a_schema_the_cli_refuses_itself_names_the_exit_code_and_the_stderr_text` (new); the flow test's `_run_claude_cli` blocks are skipped in the port, as they were for block (g) |
| `j2_flow_test.py` | +133 lines for all of the above | `tests/engine/legacy/j2_flow_test.py`, the new blocks patched in; the one block that calls J2's own `llm._run_claude_cli` is guarded like its neighbour | itself |

## Script change: patch P12 is now in `vendor_j2.py`
The Windows port (D101) had edited `j2_check.py` and `j2_template_lib.py` by hand and recorded it as P12, but the script did not carry it, so re-vendoring would have dropped it. P12 is now six exact edits in the script (the lock and the `oslayer` import ride in P10's text, which the script writes), and `--check` against the old baseline `33aeeda` reproduced the committed files byte for byte before the baseline moved. `BASELINE` in the script is `9200cf6`.

## Not vendored, on purpose
- **The Run settings page** (landed afterwards: see `j2-sync-3.md`; the text below is why it was left out of this sync) (`GET /api/runlist`, `GET /api/changes`, the Run settings tab, `j2_flow_test.run_settings()`): it exists only in the copy `prototypes/j2` of the old repository (`e7800503`), not in the prototype's own repository, which is what Sutra Pro vendors. Taking it would mean vendoring from a file set that never existed as one commit. It lands when the change reaches the prototype's repository; then `vendor_j2.py`, `port_j2_ui.py --check` (all anchors must match), `record_api_shapes.py` for the two routes and `engine/views.py` are the steps.
- **Branch `build-on-run`** (`80f8704`, one file, `docs/build-on-run-design.md`): design only, "fork a finished run with a new brief through `J2_CHANGE`". Recorded as pending in `j2-sync.md`; no code to vendor.

## Prompts and goldens
No prompt changed. The prompt goldens and the vendored hash list were re-recorded only through `VENDORED.md`; the API shape goldens did not move (no route changed).
