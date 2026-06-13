---
part-id: C1
bucket: components
template: L8-feature-spec
parity-source: ADR-023 (net-new; post-cutover canon, not from pre-cutover monolith)
status: DRAFT v0.1 — LLD, PARKED pending HLD lock (see components/INDEX.md)
authored: 2026-06-13
---

# C1: Approval Inbox (UI Kit component)

> **PARKED — LLD.** Gated behind HLD lock (components/INDEX.md). Dual-lane verdict: PASS-WITH-MODIFY. **Provenance note:** F.1/F.2/F.5 trust gates + the reversibility taxonomy cited below live ONLY in the frozen monolith `master/index.html` §2.F, NOT yet in any canon part-file — pulled in via ADR-023 Context, pending the UI-block canon-migration prerequisite (components/INDEX.md). Deferred must-fixes (Edge cases + Telemetry L8 sections) handled at unpark. Inherits P6 (default-quiet · operator-tunable · no surface inversion) per ADR-023 Decision 4.

## 1-line summary

Operator-facing inbox of every pending authority-gated action — execution approvals (`E-<id>`) and emergence proposals (`P-<id>`) — each shown with its reversibility tag and a one-tap approve/reject, rendered inside the UI block's Receive part. Closes the `gate.md` §14.7 gap (no specified founder-notification channel).

## Category

UI Kit **component** (ADR-023 Decision 2) — below Module granularity: no independent lifecycle/charter/authority/deployment, mutates no engine state, renders one exposure-contract projection. Composed INTO the Charter Console Module alongside C2.

## Scope (in / out)

**In scope (v1)**:
- Read + render the pending-approval set: `E-<id>` (workflow/step awaiting approval) + `P-<id>` (EMERGE proposed Workflow awaiting `approve P-<id>`).
- One-tap actions that emit the EXISTING utterances only: `approve E-<id>`, `reject E-<id> <reason>`, `approve P-<id>`, `reject P-<id> <reason>` (GATE + EMERGE surfaces own the write path; this component issues no new mutation).
- Per-row reversibility tag (F.2: reversible / reversible-with-effort / not-reversible) and required-capability badge.
- Unread-pending count exposed as UI-LOCAL state (ADR-023 Decision 3 UI row) for the notification surface.

**Out of scope (v1)**:
- Settled-approval history view (depends on ADR-022 #1 SoR truth upgrade — see Dependencies).
- Bulk approve/reject (one decision at a time v1; preserves per-action audit intent).
- Editing the underlying workflow/charter from the inbox (mint-new path, not a render concern).

## User outcome

> "I can see everything waiting on my decision, and act on it, without polling a log or grepping JSON files."

Today the founder must poll or be alerted by the host-LLM session (gate.md §14.7 declares the channel an unspecified runtime choice). C1 makes the pending set a first-class operator surface.

## Read model (ADR-023 Decision 1b — sourced, truth-class-tagged)

| Field group | Source block | Truth-class |
|---|---|---|
| Pending `E-<id>` (workflow_id, step_index, prompt_summary, ts) | Orchestration pending-state (`user-kit/pending-approvals/E-<id>.json`) | eventually-consistent |
| Pending `P-<id>` (draft Workflow, sample utterances, k-count) | Orchestration / EMERGE (`pattern_proposed` event 12) | eventually-consistent |
| Settled approvals (approved/rejected, by, when, reason) | System of Record (approval events) | authoritative / durable |

## Exposure-contract row (ADR-023 Decision 3 field schema)

```
projection: approval-inbox
source_blocks: [Orchestration, System of Record]
truth_class: per-field (see read model)
tenant_scope: requesting operator's tenant; cross-tenant rows require delegated read capability
required_capability: approve:<domain> (per the Domain whose principles gate the action)
redaction: prompt_summary redacts payload secrets; cross-tenant rows hidden absent capability
freshness: pending list <= 2s after pending-approvals write; settled view = SoR read latency
auditable: yes — every approve/reject emits an EngineEvent + DecisionProvenance row
```

## UX flow (narrative)

1. A Workflow/Step with `requires_approval` pauses → Orchestration writes `user-kit/pending-approvals/E-<id>.json` (state `awaiting_approval`).
2. C1 projects the pending set; the unread count surfaces via the M5 approval-card modality + notification state.
3. Operator opens the inbox: each row shows action summary, source workflow/step, reversibility tag, required capability, requested-at.
4. Operator taps approve/reject → component emits the existing utterance → GATE resumes (`NativeEngine.resumeApproved`) or terminates (state=failed).
5. The decision emits an EngineEvent + DecisionProvenance row; the row leaves the pending set and (post ADR-022 #1) appears in the settled view.

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | One `E-<id>` and one `P-<id>` pending in the operator's tenant | operator opens C1 | both rows render with reversibility tag + required-capability badge; no other tenant's rows appear |
| 2 | A pending `E-<id>` whose action is not-reversible (F.2) | operator taps approve | a confirm step is required before the `approve E-<id>` utterance is emitted (per F.1/F.5 ask-before-acting) |
| 3 | operator lacks `approve:<domain>` capability for a pending row | inbox renders | that row is shown read-only (visible, not actionable) OR hidden per redaction policy; approve/reject controls are disabled |
| 4 | operator rejects `E-<id>` with a reason | utterance emitted | execution terminates state=failed; an EngineEvent + DecisionProvenance row records actor + reason; row leaves pending set |
| 5 | ADR-022 #1 not yet shipped | operator requests settled history | component shows pending set fully + flags settled-history as "live view only — durable history pending SoR upgrade" (degraded-fidelity, ADR-023 Decision 1b) |

## Dependencies

- **ADR-022 #1 (SoR truth upgrade)** — required for the settled-approval history view. The pending list works today (reads pending-approvals JSON). v1 may ship pending-only with history flagged degraded.
- ADR-009 (approval-gate primitive) · gate.md (GATE surface) · ADR-006 (tenant isolation) · F.1/F.2/F.5 (trust gates) · EMERGE surface (P-<id>).

## Open gaps

- Notification transport for the unread count (terminal stdout vs M2 Slack ping vs M3 email) — inherits gate.md §14.7; resolved by binding config per Deployment, not hardcoded here.
- Whether `reject P-<id>` is a canonical utterance (EMERGE canon notes a rejection-event gap) — confirm or add before coding.
