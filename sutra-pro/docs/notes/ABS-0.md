# ABS-0 as built

Re-vendored from J2_Prototype `9200cf6` with `scripts/vendor_j2.py` (`--check` passes). Changed vendored files: `j2.py`, `j2_artifact_models.py`, `j2_template_lib.py` and `VENDORED.md` (hashes, line ranges). No prompt file changed; no route changed.
Script: `BASELINE` is `9200cf6`; patch P12 (Windows) is now in the script (it was hand edits, which a re-vendor would have lost); proven by `--check` against `33aeeda` before the baseline moved.
Tests: `tests/engine/test_engine_vendor.py` names the new baseline; `tests/engine/legacy/j2_flow_test.py` has the new blocks; one new connector test for the refused-schema report.
Not done: the Run settings page (only in the old repository's copy; see `docs/design/j2-sync-2.md`).
