# Test strategy — Apps (Sutra Desktop)

| Field | Value |
|---|---|
| **status** | ACTIVE — program step 42; skill `core:test-strategy` shape (8 sections) |
| **updated** | 2026-09-11 |
| Subject | `modules_api.py` (+ `modules_events.py`, `modules_pkg.py` when they exist), `static/js/18-modules.js`, the seeded chats |
| Runner of record | `.tmp/modules-review/run-v12-tests.sh` (program step 50), then `PUBLISH-CHECK.md` |

## Subject and risk profile

Apps is user-facing runtime content with one trust boundary: import of third-party packages (APPS-THREATS.md). Risk profile: user-facing for the screen and the API; safety-critical for the extraction contract (a bad import can write outside the app folder). Existing infra: pytest + FastAPI `TestClient` for the backend, node `vm` suites for the panel, `qa-shell` CDP lanes for the real shell.

## Test pyramid

| Layer | Share | Carries |
|---|---|---|
| Unit (pytest, node vm) | 30 | `_Registry.resolve`, `_normalize`, seeds, `dirRail` slice, seed builders, query keys |
| Integration (TestClient, real temp folders, real temp registry) | 50 | every route: grouped query, assign, create, touch, export, import; migration on fixtures; golden responses |
| End to end (qa-shell STATE + PIXELS) | 15 | the real shell: rail rows, app view, Edit/New open a pane, narrow crumb |
| Property / eval | 5 | seeded-chat eval pack (§AI eval-pack); property test over extraction paths |

Deviation from the "API / HTTP boundary" heuristic (30/50/15/5): none.

## Fixture strategy

| Boundary | Fixture | Where |
|---|---|---|
| App folders | real temp dir via `SUTRA_MODULES_HOME` | `test_modules_api.py` setUp wipes it per test |
| Department registry | real temp dir via `SUTRA_NATIVE_HOME`, 4 domains minted by `_tree()` with a 2 ms gap (ordinal determinism) | `test_modules_api.py` |
| On-disk manifests | `schemas/fixtures/schema1-*.json` copied in | migration tests |
| Grouped responses | `schemas/fixtures/golden-grouped-experience.json`, refs normalised to `<name>` | golden test |
| Tarballs | built in-test with `tarfile` (traversal, symlink, oversize, bad sha256) | `test_modules_pkg.py` |
| Panel | `vm` context with `DOMAINS`, the rail-helpers slice, stub `apiGet`/`apiPost` | `test_modules.js` |
| Clock | not injected; `updated_at` is stripped before golden comparison | — |

Extraction contract coverage (APPS-THREATS.md X-rules → `test_modules_pkg.py`; every row fails until steps 59-60 land, codex R2 P1/P5):

| X-rule | Test |
|---|---|
| X-1 sha256 before opening | `test_05_import_refuses_a_sha256_mismatch_before_opening_the_archive` |
| X-2 manifest first, id equals target | `test_07_import_refuses_a_manifest_whose_id_differs_from_the_target` |
| X-3 member whitelist | `test_08_import_refuses_members_outside_the_whitelist` |
| X-4 realpath containment, no symlinks | `test_02_import_refuses_path_traversal_and_nothing_lands`, `test_03_import_refuses_symlinks` |
| X-5 caps | `test_04_import_refuses_oversized_members` (per-file), `test_09_import_refuses_too_many_members` (count); total-bytes cap: pending |
| X-6 existing folder | `test_10_import_refuses_an_existing_folder_unless_replace_is_explicit` |
| X-7 atomic rename, quarantine cleaned | `test_06_import_lands_atomically_with_marketplace_origin` |
| X-8 events on every outcome | `test_11_import_appends_an_event_for_ok_and_for_refusal_and_overwrites_origin` |
| X-9 installer overwrites origin/publish | same as X-8 |
| X-10 flag off → 404 with hint | `test_00_flag_off_answers_404_with_the_hint` |

## Mock-vs-real boundary

```
+--- BOUNDARY ----------------------------------------------------+
| Real:    modules_api, placement_engine, the folder, the temp    |
|          registry, FastAPI routing, the vm-loaded panel modules |
| Mock:    apiGet/apiPost in the panel suites (pending promises), |
|          the chat provider (never called by tests)              |
| Reason:  the folder and the registry ARE the product; mocking   |
|          them would test nothing. The provider is an external   |
|          model call: eval pack only, never in the unit loop.    |
+----------------------------------------------------------------+
```

## Coverage targets

| Scope | Line | Branch | Mutation |
|---|---:|---:|---|
| `modules_api.py` overall | 80 | 70 | — |
| `_Registry.resolve` + `list_grouped` + `apply_action("assign")` | 95 | 90 | yes — the mutation subset (program step 49) |
| `modules_pkg.py` extraction (when it exists) | 95 | 90 | yes — the mutation subset |
| `18-modules.js` | 80 | 70 | — |

Mutation testing runs on the two subsets only (`mutmut` on the named functions), never on the whole tree.

## AI eval-pack design

AI is in the loop for the seeded chats (Edit, New). Eval pack: `evals/apps-seeds.jsonl` (6 cases). Each case = seed text + expected first-reply properties, scored by a rubric, not string equality.

| Case | Expects |
|---|---|
| edit-page | first reply names both files and asks what should change |
| edit-chat | first reply quotes the current instructions and asks what to change |
| new-blank | first reply asks kind: chat, page, or link |
| new-with-kind | when the seed already says "page", no kind question; asks what it should do |
| move-in-edit | "move this app to Analytics" → reply proposes the structured assign, does not rewrite JSON by hand |
| pin-respected | the placement row lands under the pinned department (checked in the registry, not the text) |

Run: on demand and at R2/R5; never in the unit loop; results logged to `.tmp/modules-review/evals-*.out`. Provider absent → SKIPPED row, never a fake pass.

## CI gates

| Gate | When | Blocks |
|---|---|---|
| `node test_modules.js`, `node test_nav.js` | every code step; PUBLISH-CHECK step 3c | merge to release |
| `.venv/bin/python -m pytest -q` (all `test_*.py`) | every code step; PUBLISH-CHECK step 4 | merge to release |
| `test_modules_pkg.py` | every server step from 59 on | merge to release |
| qa-shell both lanes with the Apps checks (steps 81, 83, 84) | Phase H; PUBLISH-CHECK step 5 | release |
| eval pack | R2, R5, on demand | release (R5) |

## Anti-patterns to avoid

| Anti-pattern | Instead |
|---|---|
| Mocking the folder or the registry "for speed" | temp dirs are already sub-second |
| Asserting on D-path literals without the 2 ms mint gap | use `_tree()`; ordinals tie on `ts_minted_ms` |
| Golden files with raw refs | refs are hashes of time; normalise to names |
| Skipping the import tests when the flag is off | the tests turn the flag on in a temp settings file |
| Calling the model in a unit test | eval pack only |
| One runner for everything as an atom's check | a runner covers only that atom's goal |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-13) with the `core:test-strategy` skill's 8-section shape, from `test_modules_api.py`, `test_modules.js`, `PUBLISH-CHECK.md` and APPS-THREATS.md; program steps 42-49.
