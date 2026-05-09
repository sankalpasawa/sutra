---
part-id: B12
bucket: blocks
template: L8-feature-spec
parity-source: §12.13 row B12 + §12.12 founder voice round 4 + §10.2 P12 + Q31
parity-source-sha256: 3603a6b600b700a0379b7ac4ad6af68ef5337d946b716c6346e64e0ae0026e55
status: DRAFT v1
authored: 2026-05-09
---

# B12: End-to-End Testing (TestSurface contract)

## 1-line summary

Every Native primitive + every PromptBuilder + every artifact-resolve has a deterministic test; only `invoke_host_llm` (LLM call) and `host_action` (action execution) are marked stochastic — the deterministic surface is exhaustively tested.

## Scope (in / out)

**In scope (v1)**:
- NEW TestSurface contract per §12.13 row B12.
- Every Native primitive (§2) has ≥1 contract test (per Q31 default).
- Top-10 journey paths get deterministic-replay tests (per Q31 default).
- Existing coverage gate ≥80% per build remains active (per Q31 default + §14.16.8).
- Only `invoke_host_llm` + `host_action` marked stochastic — everything else (prompt construction per B11, artifact retrieval per 7a, gate evaluation per B7, output validation per B7, state transitions per §4 I-5) is deterministic + tested.

**Out of scope (v1)**:
- Stochastic-side evaluation (LLM reasoning quality) — explicitly out per P12.
- Manifest drift fix (OS-19 per §14.16.8 — `marketplace.json` 1207 vs source 1273) — deferred to next plugin release.
- Auto-generated tests from canon primitives — canon-silent (gap per F2).

## User outcome

Founder trusts that everything in the deterministic surface is tested and replayable — only LLM reasoning + action execution are by-design stochastic. Founder voice round 4: "we ensure there's end to end testing of everything so that nothing is left to chance only the reasoning part is left ... the decision-making part or the really execution via the actions part".

## UX flow (narrative; terminal + audit log)

1. Native primitive authored or modified.
2. B12 contract requires ≥1 test for that primitive before Phase D codex review (per §14.15.4 + Q31).
3. Top-10 journey paths exercised via deterministic-replay tests.
4. Coverage gate ≥80% checked per build.
5. Ship gates fail-closed if any of the three sub-gates fails (per F3 — fail-closed inherited from canon §6.5).

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | New Native primitive authored | Phase D codex review fires | ≥1 contract test required; ship rejected if missing (per Q31 default) |
| 2 | Top-10 journey paths defined | replay test runs | each journey deterministically replays; pass = identical EngineEvent sequence per ADR-013 (no fail-open invention per F3) |
| 3 | Coverage drops below 80% | build runs | build fails per §14.16.8 gate; specific failure message NOT specified in canon (gap per F2) |
| 4 | `invoke_host_llm` step in test | test fires | marked stochastic per P12; not required to deterministically pass (LLM output variance allowed) |
| 5 | `host_action` step in test | test fires | marked stochastic per P12; action outcome variance allowed |

## Data model

Per §12.13 row B12: NEW TestSurface contract. Per F5, canon authorizes new contract. Not a new §2 primitive — TestSurface lives in test-infra layer.

```
TestSurface = {
  primitive_id           // §2 entity under test
  contract_tests[]       // ≥1 required
  journey_tests[]        // top-10 deterministic-replay
  coverage_threshold     // 0.80 default per §14.16.8
  stochastic_marks[]     // 'invoke_host_llm', 'host_action'
}
```

Cross-refs:
- `../primitives/engine-event.md` (substrate journey-replay reads)
- All §2 primitives (subjects of contract tests)

## Edge cases

- **New primitive shipped without contract test** → ship rejected at Phase D codex review per Q31.
- **Journey test produces non-deterministic event sequence outside stochastic marks** → per F3 fail-closed; replay-mismatch flagged as drift.
- **Test infra unavailable** → Phase D codex review blocks per canon §14.15.1.
- **Coverage measurement tool drift** → manifest drift OS-19 per §14.16.8; deferred.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — when test gate evaluates as a policy decision.
- `commitment_broken` — if ship policy commitment fails (canon-existing per §8 OS-5).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Cross-company decision-replay success rate (canon §14.9 ≥99% target) — B12 is the substrate that makes 99% replay possible.

## Dependencies

- **Primitives**: every §2 primitive (subjects), `engine-event` (substrate).
- **Events**: `policy_decision`, `commitment_broken`.
- **Surfaces**: `audit`.
- **Hardstops**: HS-4 (audit-unwritable — tests rely on audit substrate).
- **Blocks**: B7 (pre/post LLM gate composes with B12 contract), B11 (PromptBuilder deterministic; subject to B12 tests), B9 (artifact catalog deterministic; subject to B12 tests).
- **Pillars**: P12 (Deterministic surface around stochastic core) — B12's anchor.
- **ADRs**: ADR-013 (3-channel JSONL durability — replay substrate).

## References

- NATIVE-ENGINE.md §12.13 row B12 (founder voice round 4).
- NATIVE-ENGINE.md §10.2 P12.
- NATIVE-ENGINE.md §14.16.8 (quality gates note).
- NATIVE-ENGINE.md §14.15.4 (governance / security / agentic-framework infra inventory — testing is infra).
- Q31 (§12.15) — every primitive ≥1 contract test + top-10 deterministic-replay; coverage ≥80%.
- OS-19 (manifest drift) per §8.
