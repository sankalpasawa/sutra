# J2S4-e3a as built: the capture script, the fixtures of the studio pin and the page render tests
Branch `lane/sync4-e3a`. The method, the file table and the choices are in `docs/notes/J2-SYNC-4.md`; this note is what was built, measured and left.

## Built
- `scripts/capture_j2_fixtures.py`: takes an extraction of `prototypes/j2` (`--j2`, `--commit`), Sutra's own Python by default; the new routes, one feed and one answer per function, one record per part and deliverable, the three readable pages, 25 goldens, the new harness inputs, a frozen node clock, a digest that proves the extraction untouched, the R5 scrub and guard.
- `tests/ui/fixtures/j2/` (80 files), captured at `025e265c` (tree `21c67045`): two captures are byte-equal, with and without `--commit`.
- `tests/ui/js/page_render.test.js`: 53 tests (52, and one that runs with `SUTRA_J2_CHECKOUT`; 53 of 53 with it).
- `tests/ui/test_fake_backend.py`: section 7 (the script's own tests) and the two fixture-reading tests of section 1, with `tests/ui/fixtures/tools/standin_j2/` (the stand-in J2 serves the new routes and prints the new keys). A shared edit with lane e3b: a trial merge of `lane/sync4-e3b` into this branch has no conflict.
- Commits: `04491f7a`, `cffd7552` (the script, the stand-in and its tests), `89936b08` (the fixtures), `1c84f80e` (page_render), and the merges of `lane/sync4-e1` (`7ad23d30`, `a002eca3`). The fixtures first captured at the previous pin (`9ceb3aa9`) are replaced by `89936b08`.

## Measured (on the merged tree of this branch)
- `scripts/capture_j2_fixtures.py ... --check`: ok, 80 files. `port_j2_ui.py --check` against my own extraction of the pin: ok, 32 edits, 7 files.
- `node --test tests/ui/js/page_render.test.js`: 52 pass, 1 skipped; with `SUTRA_J2_CHECKOUT` naming the extraction: 53 pass.
- `pytest tests/ui/test_fake_backend.py`: one failure, `test_the_j2_routes_the_fake_registers_are_the_ones_the_client_wrapper_adds_dept_to` (the fake's route count, 23, against the 33 exact names of `sutra_ctx.js`: lane e3b's file); everything else of the file passes, section 7 and the fixture tests included. `tests/test_ownership.py` passes (no owner name in the fixtures or notes).
- J2's mock server runs on the shared venv: it needs `pydantic` only (present); `anthropic` and `google-genai` are not installed and not needed.

## Left
- The motion probe numbers (lane e3b) go into `docs/notes/J2-SYNC-4.md`; the table there is empty.
- `finish` and `files` goldens are empty (the captured run waits for an answer); the finish card has a test, the files list has none. The mock brief has no change request, so no golden shows a journey stop for one.
- Lane e2's `sutra-panel.css` must style `.steamstrip` (the Simple view's strip).
- The integrator's step 5 of design 6.2 reads `--j2-python "$(scripts/py -c 'import sys;print(sys.executable)')"`: still valid; the flag is now optional, and `--commit` should be added.
