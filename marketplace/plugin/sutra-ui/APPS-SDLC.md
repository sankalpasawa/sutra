# Apps SDLC — how a step of the Apps program becomes shipped code

The process every code step of `holding/plans/apps-program/PROGRAM.md` follows, made of the Mac app's existing idempotent processes; nothing here is new machinery.

| Field | Value |
|---|---|
| **status** | ACTIVE — program step 41 |
| **updated** | 2026-09-11 |
| Branch | `main` of sankalpasawa/sutra; routine commit + push is autonomous (D52); no PR lane exists (D69) |
| Release | tag `v<version>-desktop` → `.github/workflows/release-dmg.yml` (see `PUBLISH-CHECK.md`) |

## <a id="loop"></a>The step loop

| # | Action | Runs through | Evidence |
|---|---|---|---|
| 1 | Open a Work-Atom whose verify IS the step's Verify column; the pre-check must fail (declare before work) | `holding/bin/sutra-atom open`, `sutra-dispatch bind` | atom card shown to the founder |
| 2 | Tests first: write or extend the test that will prove the step, run it, watch it fail | `.venv/bin/python -m pytest -q <file>`, `node test_<x>.js` | failing run in the atom's EVAL |
| 3 | Do the smallest change that turns it green; no drive-by refactors | Edit | diff |
| 4 | Run the neighbours: the API suite, the node suites the step touches; from step 59 on, `test_modules_pkg.py` is the security gate on every server step (PUBLISH-CHECK 3d) | `run-tests.sh` (backend, collects all `test_*.py`), `node test_modules.js test_nav.js`, `pytest -q test_modules_pkg.py` | green |
| 5 | Codex review at the risk transitions R1-R5 only (program D-I); fold every point or write its disposition | `core:codex-sutra` via the in-envelope launcher | `.tmp/modules-review/codex-r*.out` + fold table in PROGRAM §0.5 |
| 6 | Close the atom; append the ledger row | `sutra-atom close` | `LEDGER.jsonl` |

## <a id="release"></a>Release (Phase I)

| # | Action | Reuse |
|---|---|---|
| 1 | CHANGELOG entry ≤ 5 lines, human words; delete the stale duplicate 2.247.0 block | version-bump discipline |
| 2 | Bump the 3 manifests (`plugin.json`, `marketplace.json`, `CHANGELOG.md`) to the same version | same |
| 3 | The full publish gate in order, including the security gate and the design sweep | `PUBLISH-CHECK.md` steps 1-3d (node suites + `test_modules_pkg.py`), 4 (pytest), 5 (qa-shell both lanes), 6 (`qa/run.sh` design sweep) |
| 4 | Commit + push `main` (D52); bump the submodule pointer in asawa-holding | git |
| 5 | Tag `v<version>-desktop`; watch `release-dmg.yml`; never hand-upload assets | release pipeline |
| 6 | Fresh-install smoke on the DMG; founder sees the Apps row and a New app chat | founder |

## <a id="rules"></a>Rules

| Rule | Why |
|---|---|
| One atom per step; one step per atom | the ledger is only honest at that grain |
| A runner used as an atom's check covers ONLY that atom's goal | an over-broad runner can never close (lesson of atom a-c0a2923c-08) |
| No commit before Phase I | the release is one commit + one tag, reviewable as one unit |
| `flags.modules=false` is the operator rollback; `git revert` + re-tag is the fleet rollback | program §5 |
| Never `--force`, `--no-verify`, or a history rewrite | D52 keeps those gated |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-13) from PUBLISH-CHECK.md, D52, D69, the release pipeline memory and the atom lessons of this session; program step 41.
