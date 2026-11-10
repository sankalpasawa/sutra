# Experimental reference — one kernel, 29 extension cases

**Build label:** `sutra-kernel-extensions/0.7.0-handlers`. This is an independent study; do not treat it as a released implementation of production Sutra Core or J2/Native. 0.7.0 (Core Algorithm program, 2026-11-10) is the second shrink version (move-outs M2 and M3): the kernel gets one generic primitive, an action-handler registry, keeps the gate (re-admission, prerequisites true, cost, provider slot, the receipt's own fields, the log) and gives up the effect; `compile_candidate` and `emit_artifact` leave `kernel/core.py` for `extensions/constructor.py` with byte-identical receipts and trace roots on cases 04, 15, 16 and an artifact fixture. A State keeps the registry as it stood when it was built; packs can never add a kind. 0.6.0 (kernel unchanged from 0.4.0) makes the implementation generator emit each step's prerequisites (`after`) and the plan's dependency edges, refuse a workflow whose step comes before its prerequisite, and adds a fourth domain, a website (plan, write, build, check), as case 28. 0.5.0 was a pack-only version (Core Algorithm program slice S3, 2026-11-10; kernel unchanged from 0.4.0): a standard becomes an ordinary approved rule (`R-REGISTRABLE@1`), its facts come from an evidence adapter over a workflow JSON (`extensions/standards.py`), and cases 25 to 27 record a hand-written workflow failing the standard, a reviewed method repairing it, and a generated workflow passing on evidence alone. 0.4.0 was the first shrink version (Core Algorithm program rule R2, move-out M1, 2026-11-10): the learning block and its `learned_signatures` memory left `kernel/core.py` (341 to 323 lines) for `extensions/reflection.py` (`Learner`), with a counterexample test that fails on 0.3.0 and an equivalence test on the recorded learning cases. 0.3.0 added the proposal-only implementation generator (`extensions/implementation.py`, program rung L1); the kernel was unchanged from 0.2.0 until 0.4.0.

Requirements: Python 3.10+ standard library. From **this `lab/` directory**:

```bash
python3 tools/make_packs.py
python3 tools/run_all.py
python3 tools/make_extra.py
python3 -m unittest discover -s tests -v
python3 qa/independent_verify.py
```

Expected results with the included authored fixture packs: 29 deterministic recorded cases, 75 passing unit tests and 41 independent local checks (0.6.0 had 70 and 39; 0.5.0 had 28 cases, 67 and 37; 0.4.0 had 25 cases, 62 and 36; 0.3.0 had 57 and 33, 0.2.0 had 54 and 31; the five tests and three checks added in 0.4.0 cover the move-out of learning, those of 0.3.0 the implementation generator). What changed in the record with 0.4.0: the trace of a learning case no longer carries a `LEARN_CANDIDATE` event, so the trace roots of cases 05 to 08 differ from 0.3.0 and case 05 now shares its root with case 04; each learning list is bound to its run by `learning_record` (trace root + sha256 of the list), which check S36 verifies. `qa/independent_verify.py` **does not import** the resolver and rejects a deliberately altered event chain, but verifies synthetic consistency only. `tools/build_viewer.py` and `qa/browser_test.py` optionally render/check the offline viewer with Playwright and Chromium installed; the earlier archive recorded 21 browser assertions, not rerun for this publication.

`results/` and `site/` are generated locally, not authoritative external observations. Source integrity of the historical experiment was checked before importing here; commits to this department create new repository object hashes, not a retroactive Core v0.2.2 release.

### Structure

- `kernel/core.py`: bounded recursive resolver and safe local action boundary; since 0.4.0 it carries no learning, since 0.7.0 only the `simulate_fact` effect and a registry for the rest.
- `extensions/constructor.py`: the `compile_candidate` and `emit_artifact` action handlers (out of the kernel since 0.7.0).
- `scenarios/`: authored, reviewed-in-fixture JSON packs.
- `extensions/knowledge.py`, `reflection.py` (with `Learner`, the per-run candidate-only learning since 0.4.0), `j2_projection.py`: bounded proposal utilities, **not** true external data/model/J2 integration.
- `extensions/standards.py`: the evidence adapter: a checklist over a workflow JSON becomes verified evidence rows (source = the adapter, version = the digest of what was checked); it runs when packs are authored, never inside the kernel.
- `extensions/implementation.py`: the implementation generator: from a plan and its state, a workflow in the `sutra-native` user-kit shape, its atoms, the owning department's scaffold and a page; PROPOSED_ONLY, deterministic, writes nothing, runs nothing.
- `tools/`: fixture, run and static-viewer scripts.
- `qa/`: independent verifier (does not import kernel), optional browser tests.
- `tests/`: regression and negative tests.
- `release/baseline_v0_1_core.py`: historic experimental v0.1 reference fixture used by unit/trace verifier, not frozen historical Sutra Core v0.2.2.

### Do not claim

This test uses toy resource units, human-authored domain rules, simulated effect receipts and seeded candidate components. It does not move inventory, send a message, deploy an app, generate unknown code independently or allow itself to approve any release.
