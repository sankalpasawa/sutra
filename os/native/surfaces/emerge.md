---
part-id: EMERGE
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §3.2 #12-#14 + §3.4 + §14.10 Q4
parity-source-sha256: 898335012fcb6dd137e849ca5e9c80af56924c9a89d46e500771e94156d1707b
status: DRAFT v1
authored: 2026-05-09
---

# Surface: EMERGE

## Purpose

Detect a repeating utterance pattern that does NOT match any registered Workflow → propose a new Workflow when the pattern crosses the threshold k → surface the proposal to the founder for approve/reject.

Canon: §14.7 row 4 — *"EMERGE | Propose new Workflow when pattern repeats ≥4"*. Threshold k=4 ANSWERED Q4 2026-05-09 (per-tenant configurable in v2).

## Interface (operator-facing)

The operator's surface to EMERGE is the founder utterance set for proposals (§3.4):

| Utterance | Effect |
|---|---|
| `approve P-<id>` | Approve a proposed Workflow → emit `proposal_approved` → mint a real Workflow in user-kit (ADR-010) |
| reject (canonical utterance not specified for proposals — see canon gap below) | Reject a proposed Workflow → emit `proposal_rejected` |

§3.4 lists `approve P-<id>` but does NOT list a `reject P-<id>` utterance. Canon gap: the rejection-utterance form is NOT specified in canon — runtime implementation choice; reasonable default is `reject P-<id> <reason>` mirroring the E-form.

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| EMERGE-I1 | Pattern detector emits `pattern_proposed` (#12) exactly once when the running count of an unmatched pattern reaches k. | §3.2 row 12 + Q4 k=4 |
| EMERGE-I2 | Approval of a proposed Workflow emits exactly one `proposal_approved` (#13); rejection emits exactly one `proposal_rejected` (#14). | §3.2 rows 13-14 |
| EMERGE-I3 | False-positive guard: if the founder rejects ≥3 proposals per week, the detector pauses per memory rule [≥3 erroneous proposals/week → pause emergence] (§14.8 R3 mitigation). | §14.8 R3 |
| EMERGE-I4 | A proposal_approved transitions a candidate-pattern into a registered Workflow in user-kit (one-shot; the Workflow becomes routable by ROUTE thereafter). | ADR-010 |

Canon gap: §14.7 + ADR-010 do not specify the *exact data flow* between ROUTE's "unmatched" routing_decisions and EMERGE's pattern detector. Implementation options (detector tails routing_decision events vs. ROUTE calls a detector method synchronously) are NOT specified in canon — runtime implementation choice; future ADR may codify.

Canon gap: pattern signature / similarity threshold. Canon says "pattern repeats ≥4" but does not define what makes two utterances "the same pattern" (exact match? embedding cosine? n-gram?). NOT specified in canon — runtime implementation choice; future ADR may codify.

## Integration points

- **Primitives consumed**: [`Workflow`](../primitives/workflow.md) (proposed Workflow shape), [`DecisionProvenance`](../primitives/decision-provenance.md) (every proposal-approval emits one), [`Tenant`](../primitives/tenant.md) (proposals are per-Tenant per Q4 v2 per-tenant configurability).
- **Events emitted**:
  - [`pattern_proposed`](../events/pattern_proposed.md) (#12)
  - [`proposal_approved`](../events/proposal_approved.md) (#13)
  - [`proposal_rejected`](../events/proposal_rejected.md) (#14)
- **Events consumed**: [`routing_decision`](../events/routing_decision.md) (#1) from ROUTE — unmatched decisions feed the pattern counter (exact wire implementation-shaped; see canon gap above).
- **Surfaces upstream**: [ROUTE](route.md) (unmatched routing_decision is the input signal).
- **Surfaces downstream**: [AUDIT](audit.md) (every emitted event persisted). On `proposal_approved`, the new Workflow is registered in user-kit, becoming available to ROUTE on next match cycle — so a long-cycle dependency back to ROUTE exists.

## C4 context

```
[ROUTE emits routing_decision (matched=false)]
        |
        v
[EMERGE pattern detector: increment k for this pattern signature]
        |
        v
k >= 4 (Q4 ANSWERED)?
        |
        yes
        v
[Mint proposal P-<id>] --> emit pattern_proposed
        |
        v
[Surface to founder]
        |
        +-- "approve P-<id>" --> emit proposal_approved --> [Mint Workflow in user-kit] --(routable)--> [ROUTE]
        |
        +-- (implementation-defined reject utterance) --> emit proposal_rejected
        |
        +-- ≥3 rejections/week (R3 mitigation) --> [Pause detector]
        |
        v
[AUDIT JSONL]
```

EMERGE is the organic-emergence surface (D45 ratification 2026-05-03). It is the closed-loop that converts repeated-but-unmatched founder behavior into ratified Workflows.

## References

- `NATIVE-ENGINE.md` §14.7 row "EMERGE"
- `NATIVE-ENGINE.md` §3.2 rows 12-14
- `NATIVE-ENGINE.md` §3.4 `approve P-<id>` utterance
- `NATIVE-ENGINE.md` §14.8 R3 (false-positive overload mitigation)
- `NATIVE-ENGINE.md` §14.10 Q4 (k threshold = 4 answered)
- ADR-010 (pattern emergence)
- D45 (T0/T2 organic emergence)
- `../surfaces/route.md`
- `../surfaces/audit.md`
- `../events/routing_decision.md` + `../events/pattern_proposed.md` + `../events/proposal_approved.md` + `../events/proposal_rejected.md`
- `../primitives/workflow.md` + `../primitives/decision-provenance.md`
- `../open-questions/Q4-pattern-emergence-k.md`
