---
part-id: B18
bucket: blocks
template: L8-feature-spec
parity-source: §12.21 row B18 + §14.15.2 rank 5 + §10.2 P7
parity-source-sha256: dcb53ebb3d23f44e5c101c0ca28a6d1751e66b2d01e877919c251ec7b01ef6ca
status: DRAFT v1
authored: 2026-05-09
---

# B18: Person Formation

## 1-line summary

Native models the operator's persona over time by aggregating decisions + events + utterances + estimates from existing logs into a queryable taste / decision-style / voice / risk-tolerance / cadence / factor-weights model — v1 ships read-only view, v2 active learning + bias-injection into B11 PromptBuilder.

## Scope (in / out)

**In scope (v1)**:
- NEW `Person` primitive per §12.21 row B18.
- v1 is READ-ONLY view over already-existing logs (DecisionProvenance + EngineEvent + H-Sutra + ESTIMATION-LOG per §12.21 row B18).
- Fields (per Q37 confirmed 2026-05-09): `{id, taste_signals[], decision_style{}, voice_profile{}, risk_tolerance, cadence_preferences{}, factor_weights{}}`.
- Queryable interface so PromptBuilder (B11) + lifecycle orchestrator (7d) can read persona for context (passive consumption v1 per P7 + Q12 default).

**Out of scope (v1)**:
- Active learning (v2 per §12.21 row B18 "v2 = active learning + bias-injection into PromptBuilder").
- Autonomous fix authorship via persona (deferred per Q44 — autonomous fix v2+ once Person reaches confidence threshold).
- Explicit founder ratings as REQUIRED inputs (Q12 default 2026-05-09 — logs remain DEFAULT substrate; explicit ratings are OPTIONAL high-signal corrections, never required).
- Cross-operator persona aggregation (B18 is per-Tenant; multi-human-org persona view deferred to B14).

## User outcome

> "Native learns me + adapts; I grow + it grows" (per §14.15.2 rank 5).

The operator notices, over time, that Native increasingly fits their decision-style, voice, risk tolerance, cadence — without the operator having to manually train a profile. Long-term value driver (rank-5 rationale, §14.15.2). Pillar anchor: P7 (Native grows with the operator).

## UX flow (narrative; terminal + audit log)

1. Operator interacts with Native as normal — utterances, decisions, estimates, executions all logged to canon substrate (DecisionProvenance per §2.9, EngineEvent per §2.7, H-Sutra log, ESTIMATION-LOG).
2. Person aggregator reads existing logs (no new collection mechanism per §12.21 — uses existing substrate).
3. Aggregator computes persona fields (decision-style + voice + risk-tolerance + cadence + factor-weights + taste-signals) — v1 = read-only summary, v2 = active learning.
4. B11 PromptBuilder reads Person primitive at prompt-build time (per P11 constrained problem construction).
5. PromptBuilder embeds persona fields into prompt context (bias-injection deferred to v2 per §12.21).
6. LLM call fires with persona-aware context; output reflects operator's taste/voice/style.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Operator has DecisionProvenance + EngineEvent log entries for the Tenant | Person aggregator runs | Person primitive returned with computed fields; v1 returns read-only view; aggregation method NOT specified in canon (gap per F2; future ADR may codify) |
| 2 | Operator marked an explicit rating (per Q12 — optional high-signal correction) | rating arrives | rating logged AND amplifies passive substrate; rating does NOT replace passive logs (per Q12 confirmed 2026-05-09 + codex round-3 P7-tightening) |
| 3 | B11 PromptBuilder requests Person for active Tenant | request made | Person v1 returned synchronously with read-only view fields; B11 embeds in prompt context (per Q12 P7-tightening compatible) |
| 4 | Two Tenants for the same human (multi-tenant per §6.2) | Person queried | per-Tenant Person returned; cross-Tenant aggregation NOT in v1 scope; B14 multi-human-org architecture is the upstream extension |
| 5 | Person v1 has zero log entries (fresh install) | query fires | empty Person returned (canonical empty shape NOT specified in canon — gap per F2; future ADR may codify cold-start behavior); B11 falls back to no-persona prompt |

## Data model

NEW `Person` primitive per §12.21 row B18 + Q37 (confirmed 2026-05-09).

Per F5: B18 is canon-authorized to be NEW (§12.21 row B18 explicit "NEW: `Person` primitive"), unlike B9 which extends Asset/DataRef. Person is a new §2-style primitive entry (sub-section TBD when canon §2 grows; v1 ships shape declaration without yet renumbering §2).

Conceptual shape (per §12.21 + Q37 — verbatim field list confirmed 2026-05-09):

```
Person = {
  id
  taste_signals[]
  decision_style{}
  voice_profile{}
  risk_tolerance
  cadence_preferences{}
  factor_weights{}
}
```

Cross-refs:
- `../primitives/tenant.md` (Person is per-Tenant scoped)
- `../primitives/decision-provenance.md` (substrate Person aggregates)
- `../primitives/engine-event.md` (substrate Person aggregates)

## Edge cases

- **Cold start (no log history)** → empty Person; B11 falls back to no-persona prompt. Specific empty-Person shape NOT specified in canon (gap per F2).
- **Persona drift** → P7 (Native grows with operator) intends persona evolves; specific eviction / decay rule NOT specified in canon (gap per F2; future ADR may codify decay semantics).
- **Two operators sharing one Tenant** → not v1 scope; persona is per-Tenant. Multi-operator-per-Tenant deferred to B14.
- **Operator-explicit rating contradicts passive signal** → per Q12 P7-tightening, explicit rating is high-signal correction (amplifies, never replaces); reconciliation rule NOT specified in canon (gap per F2).
- **Persona used by an autonomous fix** → not v1 (Q44 defers autonomous-fix-via-persona to v2+).

## Telemetry

Events emitted by B18 (canon-existing events; no new event invented per F3):
- `policy_decision` (§3.2) — when persona materially shapes a decision (DecisionProvenance per ADR-007 captures the policy_id chain).
- `artifact_registered` (#9) — when Person snapshot is persisted as an artifact (per P1 closed-loop).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved (long-tail) — persona fit reduces context-restatement per session.
- Pattern-detection precision (canon §14.9 leading metric ≥75%) — persona-aware proposals raise founder approval rate.

## Dependencies

- **Primitives**: `tenant` (scope), `decision-provenance` (substrate), `engine-event` (substrate), `workflow` (consumer via B11).
- **Events**: `policy_decision`, `artifact_registered`.
- **Surfaces**: `audit` (Person reads from audit substrate), `route` (route may use Person for matching per P7).
- **Hardstops**: HS-3 (tenant-boundary — Person never leaks cross-Tenant), HS-4 (audit-unwritable — Person snapshots subject to same fail-closed rule).
- **Blocks (downstream)**: B11 PromptBuilder (consumes Person at prompt-build), 7d Lifecycle Orchestrator (lifecycle phases consult Person for style).
- **Pillars**: P7 (Native grows with the operator) — Person's anchor.
- **ADRs**: ADR-007 (DecisionProvenance schema — substrate), ADR-015 (H-Sutra event classification — substrate).

## References

- NATIVE-ENGINE.md §12.21 row B18 (founder voice round 6 — dynamic improvement + person formation).
- NATIVE-ENGINE.md §14.15.2 rank 5 (outcome-first ordering — B18 = "Native learns me + adapts").
- NATIVE-ENGINE.md §10.2 P7 (Native grows with the operator).
- NATIVE-ENGINE.md §10.2 P14 (Outcomes drive design — persona is an outcome lever, not infra).
- Q37 (§12.23) — confirmed Person field list 2026-05-09; v1 read-only, v2 active.
- Q12 (§12.4) — passive logs are DEFAULT substrate; explicit ratings amplify, never replace.
- Q44 (§12.27) — autonomous fix via persona deferred v2+.
