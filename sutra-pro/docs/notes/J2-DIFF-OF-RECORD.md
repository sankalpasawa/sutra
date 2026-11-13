# J2 difference of record: `prototypes/j2` against Sutra Pro as committed

Standing note of the tool `scripts/j2_diff_of_record.py` (J2 sync 4, lane V0). Its guard is `tests/engine/test_j2_scope.py`; what the lane built and decided is in `J2S4-v0.md`. The note holds three things: the report the tool made before the sync (section "Before sync 4"), the report it makes now that the engine is merged ("After sync 4"), and the table of what Sutra Pro does not carry, with a reason for each file and where else each reason is written ("What is not carried, and why").

## What it compares, and how to run it

There is one reference: the folder `prototypes/j2` of this repository, at a commit (the pin; today `1d537295eb11cb034956fa9d8a4026eaa1e3f44e`, tree `30c71fea4679716c9f48d297ee4b2c3463eeebfd`, the tag `cut-off/2026-11-12`, sync 5; sync 4 was `025e265c594564f47a2365874cd5a5cc5d0d20a6`, tree `21c67045fe3230c1ab9be381c2f21465ea91849c`). It is compared with Sutra Pro as committed. There is no second reference: no other repository and no earlier baseline, so the tool is pin-agnostic and needs no knowledge of an older state.

```
cd sutra-pro
scripts/py scripts/j2_diff_of_record.py                                  # print the report (exit 0)
scripts/py scripts/j2_diff_of_record.py --check                          # the same report; exit 0 only when nothing is left to decide or take
scripts/py scripts/j2_diff_of_record.py --source "$J2SRC" --commit <id>  # an extraction you made yourself:
#   J2SRC=$(mktemp -d); git archive <id> prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"
```

Without `--source` the tool makes that extraction itself, from `--commit` (default: the commit VENDORED.md names while its `prototypes/j2` is the folder HEAD has, otherwise the last commit that touched the folder), into a temporary folder it removes. A folder that holds a `.git` is refused: only an extraction is a source (an edited working-tree file or a `.pyc` cannot be vendored).

It does three things:

1. **Classifies every file** of the source. Class: `vendored` (named in the Files table of `sutra_app/engine/VENDORED.md`, which `scripts/vendor_j2.py` writes; the tool imports nothing from the script), `page` (written by `scripts/port_j2_ui.py`: the page, its two harnesses and the vendored d3), `legacy` (a J2 test script with a copy in `tests/engine/legacy/`), `excluded` (with a reason from the table in the tool), `unlisted` (of a kind the vendor script carries but VENDORED.md does not name: a new J2 file nobody has vendored), `undecided` (no rule: a new J2 file nobody decided about). Status: `identical` (byte for byte), `patched` (the J2 file is the one the copy was built from, the J2 sha256 recorded in VENDORED.md, and the copy is what the numbered patches made of it), `edited` (a legacy copy: Sutra edits those on purpose), `differs` (J2's file is not the one the copy was built from), `missing` (nothing in Sutra Pro), `unverified` (a generated page file while the port check does not pass).
2. **Runs the two machinery checks** as subprocesses, `vendor_j2.py --source <folder> --commit <id> --dest <root> --check` and `port_j2_ui.py --j2 <folder> --root <root> --check` (with `--commit <id>` once that script takes it), and shows what they say. A build that stops (an anchor that no longer matches) is reported as that.
3. **Prints a markdown report** (below) and, with `--check`, exits 1 unless both checks pass and every file is vendored, generated, a legacy copy or excluded with a reason. The statuses are evidence for a reader; the verdict is the two checks (they rebuild every file and compare bytes) and the classification.

## Before sync 4

The committed tree is the one the lanes started from: VENDORED.md names no commit of this repository and its Files table has 151 rows. The report was made against that tree (a `git archive` of it) with the final tool, from the extraction of the pin:

```
scripts/py scripts/j2_diff_of_record.py --root <the committed tree> --source "$J2SRC" --commit 025e265c594564f47a2365874cd5a5cc5d0d20a6
```

### What the two real scripts say

`vendor_j2.py --check` cannot finish its build: J2 added `import j2_studio` to the import block of `j2.py`, so its first anchor no longer matches. The exact message:

```
vendor_j2: j2.py: P1 expects its anchor 1 time(s), found 0: 'import j2_artifacts\nimport j2_artifact_models\nimport j2_board\nimport j2_change\nimport j2_c'
```

`port_j2_ui.py --check` stops at drift: thirteen anchors of the page edits no longer match (E2, E5, E6a, E7, E13b, E14 to E18, E19a to E19c); the list is in the report below.

### The report (real scripts)

- Source: `prototypes/j2` at commit `025e265c594564f47a2365874cd5a5cc5d0d20a6`, 284 files, an extraction given with --source.
- Compared with: Sutra Pro as committed (the working tree of the sutra-pro folder).
- VENDORED.md names this commit: no.

#### The two checks

##### vendor_j2.py --check: FAILED, build error

`scripts/vendor_j2.py --source <source> --commit <commit> --dest <root> --check`, exit 2

```
vendor_j2: j2.py: P1 expects its anchor 1 time(s), found 0: 'import j2_artifacts\nimport j2_artifact_models\nimport j2_board\nimport j2_change\nimport j2_c'
(1 informational note line(s) not repeated)
```

##### port_j2_ui.py --check: FAILED, build error

`scripts/port_j2_ui.py --j2 <source> --root <root> --check`, exit 1

```
DRIFT: J2's j2_ui.html no longer matches the port:
  E2: expected 2 matches, found 1
  E5: expected 1 match, found 0
  E6a: expected 1 match, found 0
  E7: expected 1 match, found 0
  E13b: expected 2 matches, found 3
  E14: expected 1 match, found 0
  E15: expected 1 match, found 0
  E16: expected 1 match, found 0
  E17: expected 1 match, found 0
  E18: expected 1 match, found 0
  E19a: expected 1 match, found 0
  E19b: expected 1 match, found 0
  E19c: expected 1 match, found 0
No file was written. Update the edit table in scripts/port_j2_ui.py, then port again.
```

#### Counts

| class | files | identical | patched | edited | differs | unverified | missing | n/a |
|---|---|---|---|---|---|---|---|---|
| vendored | 151 | 107 | 4 |  | 40 |  |  |  |
| page | 6 | 3 |  |  |  | 3 |  |  |
| legacy | 4 |  |  | 4 |  |  |  |  |
| excluded | 67 |  |  |  |  |  |  | 67 |
| unlisted | 56 |  |  |  |  |  | 56 |  |
| undecided | 0 |  |  |  |  |  |  |  |
| all | 284 | 110 | 4 | 4 | 40 | 3 | 56 | 67 |

By kind (excluded files are listed at the end):

| kind | files | identical | patched or edited | differs | unverified | missing | new (not in VENDORED.md) |
|---|---|---|---|---|---|---|---|
| artifact types | 1 | 1 |  |  |  |  |  |
| code module | 17 | 4 | 4 | 6 |  | 3 | 3 |
| condition | 4 | 4 |  |  |  |  |  |
| generic template | 5 |  |  | 5 |  |  |  |
| legacy test copy | 4 |  | 4 |  |  |  |  |
| page | 3 |  |  |  | 3 |  |  |
| page asset | 3 | 3 |  |  |  |  |  |
| reference doc | 13 | 10 |  | 2 |  | 1 | 1 |
| role file | 10 | 10 |  |  |  |  |  |
| seed library | 157 | 78 |  | 27 |  | 52 | 52 |

Edited copies (generated page files and legacy tests: Sutra edits them on purpose, so their bytes are not compared). Non-blank J2 lines that are not a line of the copy:

- `change_test.py` (legacy, edited): 2
- `j2_flow_test.py` (legacy, edited): 1555
- `j2_graph_layout.js` (page, unverified): 0
- `j2_replay_size.py` (legacy, edited): 3
- `j2_ui.html` (page, unverified): 2669
- `j2_ui_render.js` (page, unverified): 14
- `realization_test.py` (legacy, edited): 5

#### Differing (40): J2's file is not the one the committed copy was built from

- code module (6)
  - `j2.py`, `j2_agent.py`, `j2_artifacts.py`, `j2_map.py`, `j2_realization.py`, `j2_template_lib.py`
- generic template (5)
  - `templates/design/generic.json`
  - `templates/hld/generic.json`
  - `templates/lld/generic.json`
  - `templates/prd/generic.json`
  - `templates/website/generic.json`
- reference doc (2)
  - `README.md`, `SETUP.md`
- seed library (27)
  - `library/hld/components/still-point-yoga-components/v1/meta.json`
  - `library/hld/data-flow/still-point-yoga-data-flow/v1/meta.json`
  - `library/hld/hosting-and-deployment/still-point-yoga-hosting-and-deployment/v1/meta.json`
  - `library/hld/pages/still-point-yoga-pages/v1/meta.json`
  - `library/hld/purpose-and-scope/still-point-yoga-purpose-and-scope/v1/meta.json`
  - `library/hld/risks/still-point-yoga-risks/v1/meta.json`
  - `library/index.json`
  - `library/lld/file-structure/still-point-yoga-file-structure/v1/meta.json`
  - `library/lld/form-fields/still-point-yoga-form-fields/v1/meta.json`
  - `library/lld/interactive-elements/still-point-yoga-interactive-elements/v1/meta.json`
  - `library/lld/pages-and-sections/still-point-yoga-pages-and-sections/v1/meta.json`
  - `library/lld/responsive-and-accessibility-rules/still-point-yoga-responsive-and-accessibility-rules/v1/meta.json`
  - `library/prd/goals/still-point-yoga-goals/v1/meta.json`
  - `library/prd/out-of-scope/still-point-yoga-out-of-scope/v1/meta.json`
  - `library/prd/problem/still-point-yoga-problem/v1/meta.json`
  - `library/prd/requirements/still-point-yoga-requirements/v1/meta.json`
  - `library/prd/success-metrics/still-point-yoga-success-metrics/v1/meta.json`
  - `library/prd/users/still-point-yoga-users/v1/meta.json`
  - `library/website/section/still-point-yoga-section-s1/v1/meta.json`
  - `library/website/section/still-point-yoga-section-s2/v1/meta.json`
  - `library/website/section/still-point-yoga-section-s3/v1/meta.json`
  - `library/website/section/still-point-yoga-section-s4/v1/meta.json`
  - `library/website/section/still-point-yoga-section-s5/v1/meta.json`
  - `library/website/section/thread-filter/v1/meta.json`
  - `library/website/section/thread-order-on-whatsapp/v1/meta.json`
  - `library/website/section/thread-products/v1/meta.json`
  - `library/website/section/thread-scaffold-and-styling/v1/meta.json`

#### Unverified (3): generated page files while the port check does not pass

- page (3)
  - `j2_graph_layout.js`, `j2_ui.html`, `j2_ui_render.js`

#### Missing in Sutra Pro (56): a place where the file belongs, with nothing in it

- code module (3)
  - `j2_agent_models.py`, `j2_agent_views.py`, `j2_studio.py`
- reference doc (1)
  - `docs/agent-views-j2-proposal.md`
- seed library (52)
  - `library/hld/components/still-point-yoga-components/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/lld/pages-and-sections/still-point-yoga-pages-and-sections/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/goals/still-point-yoga-prd-goals/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/goals/still-point-yoga-prd-goals/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/out-of-scope/still-point-yoga-prd-out-of-scope/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/out-of-scope/still-point-yoga-prd-out-of-scope/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/problem/still-point-yoga-problem-users-and-goals/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/problem/still-point-yoga-problem/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/requirements/still-point-yoga-requirements/v2/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/requirements/still-point-yoga-requirements/v3/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/success-metrics/still-point-yoga-prd-success-metrics-and-out-of-scope/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/success-metrics/still-point-yoga-prd-success-metrics/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`
  - `library/prd/users/still-point-yoga-prd-users/v1/`: `meta.json`, `model.py`, `schema.json`, `spec.json`

#### Not decided (56)

- 56 file(s) of a kind the vendor script carries that VENDORED.md does not name: the script has not taken them yet (a new J2 file; the Missing list above shows where each one belongs).

#### Stale (0): held by Sutra Pro, no J2 source

none

#### Verdict (what `--check` says)

FAIL:
- vendor_j2.py --check: build error (vendor_j2: j2.py: P1 expects its anchor 1 time(s), found 0: 'import j2_artifacts\nimport j2_artifact_models\nimport j2_board\nimport j2_change\nimport j2_c')
- port_j2_ui.py --check: build error (DRIFT: J2's j2_ui.html no longer matches the port:)
- 56 file(s) of the source are not decided: 56 of a vendored kind that VENDORED.md does not name, 0 with no rule and no exclusion

(The exclusion table of this report is the one under "What is not carried, and why": the same 67 files, the same reasons.)

### The counts the machinery gives once its build can finish (a throwaway copy)

The real `vendor_j2.py` stops before it can count anything. For the machinery's own counts, a throwaway copy of the script was used (kept outside the repository; `--vendor-script` takes it), with exactly two anchors changed so that its build finishes: the P1 import block of `j2.py` gained the line `import j2_studio` (J2's change), and the P1 count of `    import j2_map` in `j2_artifacts.py` went from 2 to 3 (J2 added a third lazy import). Nothing else was touched, so the three new modules are not in its list (the classification above counts them). Its check block:


##### vendor_j2.py --check: FAILED, differences

`vendor_j2_fixed.py (a copy outside the repository) --source <source> --commit <commit> --dest <root> --check`, exit 1

```
differs: docs/reference/j2/README.md
differs: docs/reference/j2/SETUP.md
differs: sutra_app/engine/VENDORED.md
differs: sutra_app/engine/j2.py
differs: sutra_app/engine/j2_agent.py
differs: sutra_app/engine/j2_artifacts.py
differs: sutra_app/engine/j2_map.py
differs: sutra_app/engine/j2_realization.py
differs: sutra_app/engine/j2_template_lib.py
differs: sutra_app/engine/seed/library/hld/components/still-point-yoga-components/v1/meta.json
missing: sutra_app/engine/seed/library/hld/components/still-point-yoga-components/v2/meta.json
missing: sutra_app/engine/seed/library/hld/components/still-point-yoga-components/v2/model.py
missing: sutra_app/engine/seed/library/hld/components/still-point-yoga-components/v2/schema.json
missing: sutra_app/engine/seed/library/hld/components/still-point-yoga-components/v2/spec.json
differs: sutra_app/engine/seed/library/hld/data-flow/still-point-yoga-data-flow/v1/meta.json
differs: sutra_app/engine/seed/library/hld/hosting-and-deployment/still-point-yoga-hosting-and-deployment/v1/meta.json
differs: sutra_app/engine/seed/library/hld/pages/still-point-yoga-pages/v1/meta.json
differs: sutra_app/engine/seed/library/hld/purpose-and-scope/still-point-yoga-purpose-and-scope/v1/meta.json
differs: sutra_app/engine/seed/library/hld/risks/still-point-yoga-risks/v1/meta.json
differs: sutra_app/engine/seed/library/index.json
differs: sutra_app/engine/seed/library/lld/file-structure/still-point-yoga-file-structure/v1/meta.json
differs: sutra_app/engine/seed/library/lld/form-fields/still-point-yoga-form-fields/v1/meta.json
... 71 more line(s)
vendor_j2 --check: 204 files, 93 problem(s)
(1 informational note line(s) not repeated)
```

The check names 41 file(s) that differ, 52 that are missing and 0 that are not in the snapshot (stale).

41 files differ: `VENDORED.md` itself, six modules (`j2.py`, `j2_agent.py`, `j2_artifacts.py`, `j2_map.py`, `j2_realization.py`, `j2_template_lib.py`), the five generic templates, 27 seed files (`library/index.json` and 26 `v1/meta.json`) and the two top-level reference docs (`README.md`, `SETUP.md`); 52 are missing (13 new version folders of four seed files each). The tool's classification agrees: 40 differ (the same files without VENDORED.md) and 56 are missing (those 52, the three new modules `j2_agent_models.py`, `j2_agent_views.py` and `j2_studio.py`, and the new reference doc `docs/agent-views-j2-proposal.md`).

### Reading the numbers

- 284 files at the pin. Vendored 151 (107 identical, 4 patched, 40 differ); page 6; legacy 4; excluded 67; unlisted 56; undecided 0 (every file has a decision except the 56 new ones that wait for the vendor script).
- Modules: 6 of the 14 vendored ones changed; 3 are new. Generic templates: 5 changed. Seed: 27 changed, 52 new. Reference docs: 2 changed, 1 new. The page: `j2_ui.html` and `j2_ui_render.js` changed (the port check cannot say file by file once it drifts: all three generated files are `unverified`; `j2_graph_layout.js` is wholly contained in the committed copy, 0 lines missing, which is evidence it did not change).
- The flow test: 1,555 of its non-blank lines are not in the legacy copy, against 2, 3 and 5 for the three untouched scripts (the handful of lines Sutra edits on purpose; `realization_test.py` is at 5 because `j2_realization.py` changed).
- The new J2 files that need no vendoring decision: nine screenshots `docs/ui-studio-*.png` (excluded by kind).

## After sync 4

The command the integrator runs after the merge, from the `sutra-pro` folder, with no arguments:

```
scripts/py scripts/j2_diff_of_record.py --check
```

A pass is exit code 0 and a report whose last line is `PASS: both checks pass and every file is decided.`, with: `vendor_j2 --check: 208 files, ok`; `port_j2_ui.py --check` printing `ok: ... the committed files equal a fresh port of J2 <pin>`; no `differs`, `unverified` or `missing` column in the counts; Differing (0), Missing (0), Not decided (0), Stale (0). Anything else is a finding, and the report says which file and why. When J2 moves on in this repository, the folder is no longer the pin's: the label becomes the newer commit, VENDORED.md differs, and the report lists what changed.

The real output, after the merge of the engine (commit `025e265c` is the pin; the working tree was clean):

- Source: `prototypes/j2` at commit `025e265c594564f47a2365874cd5a5cc5d0d20a6` (tree `21c67045fe3230c1ab9be381c2f21465ea91849c`), 284 files, extracted from this repository with git archive.
- Compared with: Sutra Pro as committed (the working tree of the sutra-pro folder).
- VENDORED.md names this commit: yes.

#### The two checks

##### vendor_j2.py --check: ok

`scripts/vendor_j2.py --source <source> --commit <commit> --dest <root> --check`, exit 0

```
vendor_j2 --check: 208 files, ok
```

##### port_j2_ui.py --check: ok

`scripts/port_j2_ui.py --j2 <source> --root <root> --check --commit <commit>`, exit 0

```
ok: the 33 anchors of the page edits match their counts, and the 7 committed files equal a fresh port of J2 025e265
```

#### Counts

| class | files | identical | patched | edited | n/a |
|---|---|---|---|---|---|
| vendored | 207 | 196 | 11 |  |  |
| page | 6 | 3 | 3 |  |  |
| legacy | 4 |  |  | 4 |  |
| excluded | 67 |  |  |  | 67 |
| unlisted | 0 |  |  |  |  |
| undecided | 0 |  |  |  |  |
| all | 284 | 199 | 14 | 4 | 67 |

By kind (excluded files are listed at the end):

| kind | files | identical | patched or edited | differs | unverified | missing | new (not in VENDORED.md) |
|---|---|---|---|---|---|---|---|
| artifact types | 1 | 1 |  |  |  |  |  |
| code module | 17 | 7 | 10 |  |  |  |  |
| condition | 4 | 4 |  |  |  |  |  |
| generic template | 5 | 5 |  |  |  |  |  |
| legacy test copy | 4 |  | 4 |  |  |  |  |
| page | 3 |  | 3 |  |  |  |  |
| page asset | 3 | 3 |  |  |  |  |  |
| reference doc | 13 | 13 |  |  |  |  |  |
| role file | 10 | 10 |  |  |  |  |  |
| seed library | 157 | 156 | 1 |  |  |  |  |

Edited copies (generated page files and legacy tests: Sutra edits them on purpose, so their bytes are not compared). Non-blank J2 lines that are not a line of the copy:

- `change_test.py` (legacy, edited): 2
- `j2_flow_test.py` (legacy, edited): 1555
- `j2_graph_layout.js` (page, patched): 0
- `j2_replay_size.py` (legacy, edited): 3
- `j2_ui.html` (page, patched): 1024
- `j2_ui_render.js` (page, patched): 2
- `realization_test.py` (legacy, edited): 5

#### Differing (0): J2's file is not the one the committed copy was built from

none

#### Missing in Sutra Pro (0): a place where the file belongs, with nothing in it

none

#### Not decided (0)

none

#### Stale (0): held by Sutra Pro, no J2 source

none

#### Verdict (what `--check` says)

PASS: both checks pass and every file is decided.

(The exclusion table is below.)

## What is not carried, and why (67)

Every file of `prototypes/j2` that Sutra Pro does not carry has a reason in the table `EXCLUDED` of the tool; the tool lists them grouped, with the other places each reason is written down (`VENDORED.md` is its 'Not vendored' paragraph, "engine design" is `docs/design/engine.md` section 3.2 (left out) and 3.3 (rewritten), "design 7.4" is `docs/design/j2-sync-4.md`, D91 is the decision about excluded J2 material). A file that matches no entry and is not vendored fails `--check`.

| group | files | which | reason | also written in |
|---|---|---|---|---|
| older studio | 4 | `mock_site.py`, `server.py`, `studio.py`, `ui.html` | J2's older three-agent studio (a stdlib server, its page and a mock site): not part of J2's loop, since no J2 module of the loop imports it, and nothing in Sutra imports or reads these files. Sutra serves the department page and J2's routes itself. | VENDORED.md; engine design 3.2; design 7.4; D91 |
| older studio agents | 4 | `agents/design.md`, `agents/development.md`, `agents/product.md`, `agents/team.md` | role files of the older studio (product, design, development, team): not the J2 team's roles, which are agents/j2/*, and no engine code reads them. | VENDORED.md; engine design 3.2 (design 7.4 does not name the four role files) |
| budget-conflict demo | 5 | `negotiate.py`, `negotiate_server.py`, `negotiate_ui.html`, `scenarios/budget.json`, `scenarios/rules.md` | J2's budget-conflict demo (its own script, server, page and scenario files): not the J2 run flow, and nothing in Sutra uses it. | VENDORED.md; engine design 3.2; design 7.4; D91 |
| replaced by Sutra's own code | 1 | `j2_server.py` | replaced: engine/views.py holds the one implementation of the routes (D25), engine/api serves them and sutra_app/engine/j2_server.py (Sutra's own file of the same name) is the stdlib adapter. What a J2 change adds arrives as routes and views, never as a copy of this file. | VENDORED.md ('j2_server.py (WP E2)'); engine design 3.3 (rewritten); design 7.4 |
| replaced by Sutra's own code | 1 | `llm.py` | replaced: sutra_app/engine/llm.py is Sutra's own seam (J2's call syntax over the ModelPort, D17). J2's llm.py holds J2's own model providers; vendoring it would put a second way to a model beside the connector layer. | engine design 3.3 (rewritten on the ModelPort); VENDORED.md 'Not vendored' and design 7.4 do not name it |
| placeholders | 6 | `agents/j2/_placeholders/adaptation.md`, `agents/j2/_placeholders/audit.md`, `agents/j2/_placeholders/coordination.md`, `agents/j2/_placeholders/identity.md`, `agents/j2/_placeholders/priority.md`, `agents/j2/_placeholders/sutra.unused.md` | never read: j2.py's _placeholders() only checks the live role files for the word PLACEHOLDER. The vendor script copies the ten role files that are read. | VENDORED.md; engine design 3.2 |
| J2 development files | 1 | `.env.example` | J2's own environment template (API keys and switches of its scripts). Sutra's settings are in docs/ENVIRONMENT.md and its model calls go through the connector layer, with no model API keys (D7). | engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it) |
| J2 development files | 1 | `.gitignore` | J2's ignore rules for its own folder; Sutra Pro has its own. | engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it) |
| J2 development files | 1 | `requirements.txt` | J2's pip list (anthropic, google-genai, python-docx, pydantic); Sutra's dependencies are in pyproject.toml. | engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it) |
| J2 development files | 1 | `run_checks.sh` | J2's runner for its flow test in two throwaway copies of its folder; the gate for the legacy copies in Sutra Pro is scripts/engine_gate.sh. | engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it) |
| J2 development files | 1 | `screenshot.png` | a screenshot of J2's page at the top of its folder; no file in the folder refers to it. | engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it) |
| solar mock | 1 | `docs/mocks/team-solar-mock.html` | an HTML mock of the team view as a solar system: a design sketch, not code. | VENDORED.md ('docs/mocks/*.html'); design 7.4 does not name it; D91 says it is kept as reference under docs/reference/j2/, but the vendor script does not carry it (a disagreement) |
| mocks | 2 | `docs/mocks/j2-artifacts-mock.html`, `docs/mocks/j2-run-settings-mock.html` | HTML mock-ups of screens that are ported (the Artifacts groups, Run settings): design sketches, not engine or page code. | VENDORED.md ('docs/mocks/*.html'); design 7.4 names two of the three mocks |
| sudoku comparison | 8 | `docs/sudoku-comparison/base-final.png`, `docs/sudoku-comparison/realization-final.png`, `docs/sudoku-comparison/sudoku-adaptation-flows.pdf`, `docs/sudoku-comparison/sudoku-comparison.html`, `docs/sudoku-comparison/sudoku-map-evolution.html`, `docs/sudoku-comparison/sudoku-map-evolution.pdf`, ... | a one-off comparison write-up with its HTML, PDF and PNG renders (the Sudoku runs): not read by any code, not a reference the engine needs. | engine design 3.2 (docs/*.html, docs/*.png, docs/*.pdf); D91 says explainer pages are kept as reference under docs/reference/j2/, but the vendor script does not carry them (a disagreement) |
| build-on-run design | 1 | `docs/build-on-run-design.md` | a design with no code behind it (552 lines); no J2 file mentions it. The follow-up waits for J2 to ship the code. | VENDORED.md; design 7.4 |
| design docs (HTML) | 8 | `docs/adaptation-sudoku-walkthrough.html`, `docs/board-doc-change.html`, `docs/certainty-realization-flow.html`, `docs/design-stage-trace-standalone.html`, `docs/design-stage-trace.html`, `docs/realization-axis.html`, ... | rendered explainers and trace pages of J2's design work (adaptation walkthrough, certainty flow, design-stage trace, realization brief...): not read by any code. The Markdown references that matter are carried in docs/reference/j2. | engine design 3.2 (docs/*.html); D91 says the explainer pages are kept as reference under docs/reference/j2/, but the vendor script does not carry them (a disagreement) |
| flow picture | 1 | `docs/j2-flow.jpg` | the picture of the J2 flow that J2's README points to (docs/j2-flow.jpg): an image, not code. The vendored README therefore points at a file Sutra Pro does not carry. | engine design 3.2 (docs/*.jpg); D91 says the flow picture is kept as reference under docs/reference/j2/, but the vendor script does not carry it (a disagreement) |
| doc images | 18 | `docs/ui-simple-detailview-1280.png`, `docs/ui-simple-detailview-390.png`, `docs/ui-simple-question-1280.png`, `docs/ui-simple-question-390.png`, `docs/ui-simple-ready-1280.png`, `docs/ui-simple-ready-390.png`, ... | screenshots of J2's Simple view and of its studio view (docs/ui-simple-*.png, docs/ui-studio-*.png): images, not code. J2's README points at them, so the vendored README shows no pictures; the legacy flow test copies ui-simple-start-390.png as a stand-in file and Sutra's copy generates a plain PNG instead. | engine design 3.2 (docs/*.png, docs/*.jpg) |
| diagram picture | 2 | `docs/realization-axis.dot`, `docs/realization-axis.svg` | the Graphviz source and the SVG render of realization-axis.md. The vendored realization-axis.md names the .dot file as its picture, so that reference is dead in Sutra Pro. | none: engine design 3.2 lists html, png, jpg and pdf only (D91's 'explainer pages' may mean these too) |

### Where the reasons disagree with the other records

1. **D91 against the vendor script.** D91 says the explainer pages, the flow picture and the solar mock "are kept as reference only under `docs/reference/j2/`". The vendor script's reference list carries none of them and the committed `docs/reference/j2/` holds none. The table follows what the machinery does (they are excluded). Either the script's list gains the eight HTML pages, `docs/j2-flow.jpg` and `docs/mocks/team-solar-mock.html`, or D91 is amended.
2. **`llm.py`** is named by neither VENDORED.md's 'Not vendored' paragraph nor design 7.4; engine design 3.3 records it as rewritten on the `ModelPort`.
3. **`requirements.txt`, `run_checks.sh`, `screenshot.png`, `.gitignore`, `.env.example`**: engine design 3.2 names them; VENDORED.md says only 'the IDE and environment files'; design 7.4 is silent.
4. **Design 7.4 names two of the three mocks** (`j2-artifacts-mock.html`, `j2-run-settings-mock.html`); `team-solar-mock.html` is not there. VENDORED.md now says `docs/mocks/*.html`, which covers all three.
5. **`docs/*.svg` and `docs/*.dot`** are named by no record (engine design 3.2 lists `docs/*.html`, `*.png`, `*.jpg`, `*.pdf`); D91's 'explainer pages' may mean them.
6. **`vendor/` is not excluded.** The brief allowed excluding it "if the page's d3 is served from elsewhere". It is not: `port_j2_ui.py` writes J2's `vendor/d3.min.js`, `d3-LICENSE` and `README.md` byte for byte to `sutra_app/ui/static/vendor/`, and `ui/routes.py` serves that folder at `/ui`, so the page loads `/ui/vendor/d3.min.js`. The three files are class `page`, verbatim; VENDORED.md says the same ("the UI package ports them").

### Dead references in the vendored copies

- `docs/reference/j2/README.md` points at `docs/ui-studio-*.png` and `docs/j2-flow.jpg`, which are not carried (it shows no pictures).
- `docs/reference/j2/docs/realization-axis.md` names `docs/realization-axis.dot` as its picture, which is not carried.

Neither is a fault of the vendoring (the copies are byte for byte what J2 has); carrying the three small pictures would close them.

## After sync 5 (lane V, before lanes E and U are merged)

Sync 5 moved the pin to `1d537295eb11cb034956fa9d8a4026eaa1e3f44e` (D160) and vendored the types as data (D161): `conditions/` and `templates/` are tree copies, so a type J2 adds needs no script edit. Four exclusions were added with their reasons (D161): `templates/README.md`, `tools/*`, `fixtures/n6-sudoku-*` and `docs/word-matching-followups.md`. The real output on the lane V branch (working tree clean, extraction made with `git archive`):

- Source: `prototypes/j2` at commit `1d537295eb11cb034956fa9d8a4026eaa1e3f44e` (tree `30c71fea4679716c9f48d297ee4b2c3463eeebfd`), 313 files.
- `vendor_j2.py --check`: ok, 229 files.
- `port_j2_ui.py --check`: differences in `j2_ui.html` and `j2.css` (lane U regenerates the page; the 33 anchors match). It passes once lane U is merged.

| class | files | identical | patched | edited | unverified | n/a |
|---|---|---|---|---|---|---|
| vendored | 228 | 215 | 13 | | | |
| page | 6 | 3 | | | 3 | |
| legacy | 4 | | | 4 | | |
| excluded | 75 | | | | | 75 |
| unlisted | 0 | | | | | |
| undecided | 0 | | | | | |
| all | 313 | 218 | 13 | 4 | 3 | 75 |

Differing 0, missing 0, not decided 0, stale 0. The verdict of `--check` is FAIL only for the page check above; the integrator re-runs it after the merge of lane U. What the lane built and decided is in `J2S5-v.md`.
