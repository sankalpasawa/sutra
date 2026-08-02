---
part-id: B5
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B5 + §14.15.2 rank 4 + §10.2 P6
parity-source-sha256: e1e7a025f3c79665ae7e6c766c15e164c09e0ab700a43c553e2ae6a41b3444b8
status: DRAFT v1
authored: 2026-05-09
---

# B5: Explanation Surface (founder-controlled)

## 1-line summary

Artifacts are produced silently in the background; the human-facing explanation surface is a separate, operator-controlled layer (verbosity, what to surface, what to hide, which channel) — per §10.2 P6 the system controls production, the operator controls explanation.

## Scope (in / out)

**In scope**:
- NEW config primitive `ExplainProfile` per §12.9 row B5 — `{verbosity, what_to_surface, what_to_hide, channel}` typed config.
- ExplainProfile applied per-Domain v1 (per Q23 default 2026-05-09 — per-domain primary; per-founder default cascades).
- Explanation rendering is a separate render-stage from artifact production; founder mutates ExplainProfile without changing underlying Workflow logic.
- Existing renderer registry (§3 + ADR-015 partial per §12.9) is the substrate B5 extends.

**Out of scope (v1)**:
- Multi-channel routing (channel = single primary v1; multi-channel orchestration deferred).
- Auto-tuned verbosity (Native learns per-operator preferred verbosity automatically) — deferred (canon-silent; per F2 future ADR may codify; B18 Person Formation is the upstream dependency).
- Per-Workflow override of ExplainProfile — not specified in canon; runtime implementation choice per F2.

## User outcome

> "I control how Native explains things to me" (per §14.15.2 rank 4).

The operator separates two concerns: (1) what Native PRODUCES (audit-complete artifacts, system-readable per P1) from (2) what Native EXPLAINS to the operator (curated surface tuned to operator preference). Founder dogfood quality directly tracks ExplainProfile fit (rank-4 rationale, §14.15.2).

## UX flow (narrative; terminal + audit log)

1. Founder configures `ExplainProfile` per Domain via canon write-path (canon-silent on exact mechanism — gap per F2).
2. Workflow executes; artifacts produced + persisted per B9 (closed-loop).
3. At explanation time, renderer reads operator's `ExplainProfile` for the active Domain.
4. Renderer selects subset of artifacts per `what_to_surface` + applies `verbosity` setting (per Q23 default — per-domain).
5. Rendered output emitted to `channel` (terminal v1 per §14.10 Q9 — terminal-only v1).
6. Underlying artifact catalog is unchanged; explanation is a view over it.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Domain has ExplainProfile configured | Workflow in that Domain completes | rendered explanation respects ExplainProfile's verbosity + surface/hide filters; underlying artifact catalog (per B9) is unchanged |
| 2 | No ExplainProfile set for Domain | Workflow completes | per-founder default cascades (per Q23 default 2026-05-09); if no founder default exists either, native renders raw artifact catalog with default verbosity (default value NOT specified in canon; runtime implementation choice per F2) |
| 3 | Founder mutates ExplainProfile mid-Workflow | next render-call after mutation | new ExplainProfile applies to subsequent explanations; in-flight artifacts are NOT retroactively re-rendered (replay-from-prior-config semantics NOT specified in canon per F2) |
| 4 | ExplainProfile `what_to_hide` lists an artifact-type | render attempts to surface that type | renderer omits that type from explanation; artifact remains in audit log (audit visibility is governed by `../surfaces/audit.md` invariants, NOT by ExplainProfile) |

## Data model

NEW config primitive `ExplainProfile` per §12.9 row B5. This is a per-Domain configuration shape (NOT a §2 unit-theory primitive — per F5, canon authorizes B5 as a "NEW config primitive", which lives alongside Domain config, not as a new §2 entry).

Per Q23 default: per-Domain v1; per-founder default cascades.

Conceptual shape (per §12.9 row B5):

```
ExplainProfile = {
  verbosity            // enum or scale (specific values NOT specified in canon per F2)
  what_to_surface[]    // list of artifact-types / topics to include
  what_to_hide[]       // list to omit
  channel              // primary channel (terminal v1 per Q9)
}
```

Cross-refs:
- `../primitives/domain.md` (host — ExplainProfile attaches per-Domain)
- `../primitives/charter.md` (Charter may carry its own override v2; not v1)
- `../primitives/engine-event.md` (renderer reads events for surface composition)

## Edge cases

- **Operator misconfigures ExplainProfile to hide everything** → renderer emits a meta-notice (canon-silent; runtime implementation choice per F2). Audit log remains complete per P1.
- **Channel unavailable (e.g., terminal closed)** → renderer queues OR drops (NOT specified in canon per F2; future ADR may codify).
- **Per-Domain conflict between two ExplainProfile entries** → not possible in v1 (per-Domain is 1:1 by Q23 default).
- **Founder asks for raw audit dump** → renderer can fall back to "raw" mode (canon-silent on exact toggle; future ADR may codify).
- **ExplainProfile carries sensitive filter rules** → DecisionProvenance per ADR-007 covers audit trail of who set what filter when.

## Telemetry

Events emitted by B5 (canon-existing events only; no new event invented per F3):
- `policy_decision` (§3.2) — when ExplainProfile filter applies (renderer choice = a policy decision).
- `artifact_registered` (#9) — when ExplainProfile itself is persisted as a config artifact (config-as-artifact per P1).

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Founder weekly active sessions (canon §14.9 lagging) — explanation fit gates session-stickiness.
- Approval-gate latency (canon §14.9 ≤2 min median) — fit-tuned explanation surfaces the right context, faster approvals.

## Dependencies

- **Primitives**: `domain` (host), `charter`, `engine-event`, `decision-provenance`.
- **Events**: `policy_decision`, `artifact_registered`.
- **Surfaces**: `audit` (substrate B5 renders over), `route` (B5 may shape route's explanation output).
- **Hardstops**: HS-4 (audit log unwritable — explanation cannot mask audit-completeness invariant).
- **Pillars**: P6 (Operator controls explanation; system controls production), P1 (Artifact-first — explanation does NOT mutate artifact substrate).
- **ADRs**: ADR-015 (H-Sutra event classification + routing — renderer substrate).

## References

- NATIVE-ENGINE.md §12.9 row B5 (founder voice round 3).
- NATIVE-ENGINE.md §14.15.2 rank 4 (outcome-first ordering — B5 = "I control how Native explains things").
- NATIVE-ENGINE.md §10.2 P6 (Operator controls explanation; system controls production).
- NATIVE-ENGINE.md §3 + ADR-015 (renderer substrate B5 extends).
- Q23 (§12.11) — per-Domain ExplainProfile v1; per-founder default cascades.
- §14.10 Q9 (terminal-only v1; web/app v2+).
