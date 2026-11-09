# Experimental reference — one kernel, 25 extension cases

**Build label:** `sutra-kernel-extensions/0.2.0-experimental`. This is an independent study; do not treat it as a released implementation of production Sutra Core or J2/Native.

Requirements: Python 3.10+ standard library. From **this `lab/` directory**:

```bash
python3 tools/make_packs.py
python3 tools/run_all.py
python3 tools/make_extra.py
python3 -m unittest discover -s tests -v
python3 qa/independent_verify.py
```

Expected results with the included authored fixture packs: 25 deterministic recorded cases, 54 passing unit tests and 31 independent local checks. `qa/independent_verify.py` **does not import** the resolver and rejects a deliberately altered event chain, but verifies synthetic consistency only. `tools/build_viewer.py` and `qa/browser_test.py` optionally render/check the offline viewer with Playwright and Chromium installed; the earlier archive recorded 21 browser assertions, not rerun for this publication.

`results/` and `site/` are generated locally, not authoritative external observations. Source integrity of the historical experiment was checked before importing here; commits to this department create new repository object hashes, not a retroactive Core v0.2.2 release.

### Structure

- `kernel/core.py`: bounded recursive resolver and safe local action boundary.
- `scenarios/`: authored, reviewed-in-fixture JSON packs.
- `extensions/knowledge.py`, `reflection.py`, `j2_projection.py`: bounded proposal utilities, **not** true external data/model/J2 integration.
- `tools/`: fixture, run and static-viewer scripts.
- `qa/`: independent verifier (does not import kernel), optional browser tests.
- `tests/`: regression and negative tests.
- `release/baseline_v0_1_core.py`: historic experimental v0.1 reference fixture used by unit/trace verifier, not frozen historical Sutra Core v0.2.2.

### Do not claim

This test uses toy resource units, human-authored domain rules, simulated effect receipts and seeded candidate components. It does not move inventory, send a message, deploy an app, generate unknown code independently or allow itself to approve any release.
