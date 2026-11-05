# GAP-TRACE as built: design overview and traceability matrix

## Built
- `scripts/build_traceability.py`: reads `docs/build-plan.json`, `docs/DECISIONS.md`, `docs/notes/*.md`, `sutra_app/engine/features.py`, the engine route table
  (`ROUTES` of `sutra_app/engine/api/*.py`, `VIEWS` of `views.py`, `J2_EXACT` of `sutra_ctx.js`, `tests/engine/golden/api_shapes.json`), `docs/diagram/gen.py` (the 15
  chip labels), `sutra_app/` and `tests/` (decision numbers and source tags they cite) and `git log --merges --grep '^Merge wp/'`. It writes `docs/design/traceability.json`
  (schema `traceability/1`) and `docs/TRACEABILITY.md`; same inputs give the same bytes (rows sorted, no dates).
- Rows: (a) 7 owner rules -> decisions -> modules -> tests; (b) the 7 draw.io steps -> modules -> tests that exist (`tests/e2e/test_step<n>_*` as a pattern, not checked);
  (c) the 15 chips -> files of `FEATURES`; (d) the 30 J2 endpoints -> view -> adapter -> golden keys and tests; (e) 97 decisions -> packages -> status; (f) 62 packages -> owns ->
  notes -> merge commits (every merge of the id, newest first; `pending` when none).
- `--check [--root R]`: parses the json; every named module, test, note or owned path must exist (folders end in `/`, a glob must match); each owner rule needs a module and a
  test; a merged package needs a merge commit; a decision row names only known packages; prints the first 20 problems, exit 1.
- `tests/test_traceability.py` (32 tests, 0.3 s): the check on the real repository, determinism, parsers on fixtures (heading, owner table, notes, plan entry, merge log, ownership),
  dead and unsafe paths, a fixture repository for every check branch, a tiny repository for every row kind.
- `docs/DESIGN.md` (141 lines, by hand) and `docs/TRACEABILITY.md` (generated).

## Decisions and deviations
- Owner rules, the seven steps and 10 decisions' packages are curated tables in the script (`OWNER_RULE_MAP`, `STEPS`, `DECISION_PACKAGES`): judgment, not parsing. The check proves
  every path they name is real. A new owner rule in `DECISIONS.md` without a map entry gets empty modules (the next `--check` after a refresh reports it).
- Decision status: `implemented` when a note or a source file cites `D<n>` or one of the decision's source tags (S1-contracts-09, ENG-D3, CD5 ...), or it is in
  `DECISION_PACKAGES`; `rejected` when its title or a `Status:` bullet says rejected, vetoed or withdrawn (none now); else `documented only` (D87, D91, D93, D96). A later decision
  that says "supersedes D<n>" fills `superseded_by`. The packages of a row are the union of notes, code owners, packages named in its text, and the curated list.
- `--check` deviates from the literal spec in one place on purpose: a decision newer than the highest one in the committed json is a NOTICE on stderr (exit 0), a missing one
  below it is a problem. Reason: the brief says later decisions must not fail other merges. Refresh with `scripts/py scripts/build_traceability.py`.
- Package rows check `owns` and `notes` only when the package is `merged`; the owns of a planned package (GAP-E2E ...) do not exist yet. A renamed or deleted file of a merged
  package fails the check until the json is refreshed: that is a real stale reference, not noise.
- The endpoint table follows `engine.md` 7.1: rows 1 and 2 (`index`, `vendor`) are served by `sutra_app/ui/routes.py`; `site` is rows 24 and 25. All 30 rows share four golden
  tests (`test_engine_views.py`, the golden json, `test_engine_api_scope.py`, `test_contract_route_table.py`); the golden keys are matched by longest view-name prefix.
- `docs/design/traceability.json` replaces the protected `docs/traceability.json` (the plan moved it); `tests/test_traceability.py` is not evidence of citations (`SELF_FILES`).
- Merge hashes: GAP-TRACE's own row says `pending` (its merge commit does not exist when the json is made); refresh after the merge to record it.

## Known limits
- The json is a snapshot: new packages, tests and decisions appear in it only after a refresh; `--check` never compares it with a fresh run.
- Package touches of a decision can be broad (a source tag cited in many files lists every owner); they are evidence, not a design claim.
- `git log` is read from the checkout the script runs in; outside git the merge commits are empty and every package reads `pending`.
- `docs/DESIGN.md` names the packages merged on 2026-11-04; GAP-E2E, GAP-E2E-UI, GAP-LIVE, GAP-CONSOLE, GAP-DATA, GAP-DOCS and GAP-INSTALL are described as planned.

## Follow-ups for other packages and the scheduler
- After GAP-E2E merges: add `tests/e2e/test_step<n>_*` to `STEPS` (needs this script; not owned by GAP-E2E) or refresh the pattern column; run the generator after each wave.
- GAP-DOCS: `docs/DESIGN.md` section 6 says its four documents may not exist yet. Diagram refresh (G20): add the pills of D88 to D97.

## Mutation check (one pass, copy in /tmp)
17 breakages (decision-number lookbehind, range step, dotdot refusal, notice versus problem, 20 cap, merged-only check, longest-prefix golden match, rejected status, folder ownership,
duplicate plan id, merge-log accumulation, unknown package, exit code, source-tag evidence, row without heading, glob match, supersedes): 16 killed at once; the source-tag one survived
(an equivalent route through code owners) and got a fixture decision cited only by a note. All 17 killed.
