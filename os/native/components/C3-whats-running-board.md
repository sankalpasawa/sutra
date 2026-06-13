---
part-id: C3
bucket: components
template: L8-feature-spec
parity-source: ADR-023 (net-new; post-cutover canon, not from pre-cutover monolith)
status: DRAFT v0.1 — LLD, PARKED pending HLD lock (see components/INDEX.md)
authored: 2026-06-13
---

# C3: What's-Running Board (UI Kit component)

> **PARKED — LLD.** This component spec is gated behind HLD lock (components/INDEX.md). Dual-lane verdict: PASS-WITH-MODIFY. Fabricated citations from the first draft have been corrected (see Changelog). Remaining must-fixes (Edge cases + Telemetry L8 sections) deferred until unpark.

## 1-line summary

Live board of in-flight work — which Workflows are executing right now, the current Step and progress, plus recent completions and failures — rendered inside the UI block's Receive part. Gives the named-but-unspec'd Workforce Status Module (§1.4) and the Daily Pulse "workforce health" row their spec base. This is the digital factory's andon board.

## Category

UI Kit **component** (ADR-023 Decision 2). The Workforce Status Module composes C3; Daily Pulse (§7.5) embeds a summarized projection of it. Inherits P6 (default-quiet · operator-tunable verbosity · no surface inversion) per ADR-023 Decision 4 — for a read-only board, P6 means: show the active set by default, deeper per-execution detail on request only.

## Scope (in / out)

**In scope (v1)**:
- Render active Executions: execution id, workflow id, current `step_index` (see open gap — canon surfaces no step-total), state, started-at.
- Execution state from the canon `ExecutionResult.state` enum: **running · awaiting_approval · success · failed** (`completed` is the EVENT name `workflow_completed`, not a state).
- Render recent terminal Executions (success / failed) within a bounded window.
- Per-field truth-class labelling (ephemeral live status vs durable terminal record) — ADR-023 Decision 1b.
- Tenant-scoped by default; cross-tenant workforce view requires delegated read capability.

**Out of scope (v1)**:
- Cancelling / pausing an execution from the board (read-only v1; control actions route through existing utterances/engine API).
- Full step-by-step timeline replay (System-of-Record audit-replay viewer — separate component).
- Per-step token/cost breakdown (Compute exposure, separate projection).

## User outcome

> "I can see what my agent workforce is doing right now — what's running, what's stuck waiting on me, what just finished or failed — at a glance."

The visual-management / andon-board function from operations science — the human comparator that turns the record from telemetry into a system (ADR-022 #1/#4; `holding/research/2026-06-12-unit-work-record-science.md`).

## Read model (ADR-023 Decision 1b — sourced, truth-class-tagged)

| Field group | Source block | Truth-class |
|---|---|---|
| Live execution status (current `step_index`, running flag) | System of Process runtime | **ephemeral** (live, not yet durable) |
| awaiting_approval state | Orchestration pending-state | eventually-consistent |
| Terminal executions (success / failed, outcome, ended-at) | System of Record (`workflow_completed` / `workflow_failed` events) | authoritative / durable |

> **Heaviest ADR-022 #1 dependency of the three components.** Live step progress is not durably recorded until ADR-022 #1 (SoR truth upgrade) lands. v1 ships degraded: durable terminal rows from SoR are exact; live in-flight fields are best-effort from System of Process and MUST be labelled "live — not yet durable."

## Exposure-contract row (ADR-023 Decision 3 field schema)

```
projection: whats-running-board
source_blocks: [System of Process, Orchestration, System of Record]
truth_class: per-field (ephemeral live / eventually-consistent pending / authoritative terminal)
tenant_scope: operator's tenant; cross-tenant workforce view requires delegated read capability
required_capability: read:executions:<domain>
redaction: workflow names + step summaries naming other tenants masked; payloads never shown
freshness: live fields best-effort <= 5s; terminal rows = SoR read latency
auditable: terminal rows trace to workflow_completed/workflow_failed EngineEvents; live fields are not audit-grade
```

## UX flow (narrative)

1. `sutra-native run <workflow-id>` (or a Trigger fire) starts an Execution → System of Process runs the Steps.
2. C3 projects: active rows from System-of-Process live state, awaiting-approval rows from Orchestration, recent terminal rows from SoR.
3. Operator scans the board: each active row shows workflow, current step_index, state; live fields carry a "live — not yet durable" marker until ADR-022 #1.
4. A row entering `awaiting_approval` cross-links to its C1 (Approval Inbox) entry.
5. On terminal, the row moves to the recent-success/failures window, now sourced from the durable SoR event.

## Acceptance criteria (Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | 2 Executions running in the operator's tenant | operator opens C3 | both render with workflow id + current step_index + state=running; no other tenant's executions appear |
| 2 | An Execution pauses at `awaiting_approval` | board refreshes | its row shows state=awaiting_approval and links to the matching C1 inbox entry |
| 3 | An Execution fails | board refreshes | row moves to recent-failures sourced from the durable `workflow_failed` event; failure reason shown in plain operator words (no stack trace — see open gap on canon anchor) |
| 4 | ADR-022 #1 not yet shipped | live execution renders | current-step/running fields carry a visible "live — not yet durable" label; terminal rows remain exact (degraded-fidelity, ADR-023 Decision 1b) |
| 5 | operator lacks `read:executions:<domain>` | board renders | executions in that domain are omitted or shown as sealed rows (count only); no payloads leak |

## Dependencies

- **ADR-022 #1 (SoR truth upgrade)** — primary; gates full-fidelity live status. v1 ships degraded per above.
- `primitives/workflow.md` · `primitives/step.md` · `primitives/execution-result.md` · `events/workflow_started.md` / `workflow_completed.md` / `workflow_failed.md` / `step_started.md` / `step_completed.md` · ADR-006 (tenant isolation).

## Open gaps

- **No step-total in canon.** `step_index` exists (step_started.md payload) but NO total-step / `total_steps` field exists on any event or primitive. The "progress" denominator must be derived (e.g. from the Workflow's declared Step count at mint) or omitted. Resolve before coding.
- **Plain-words-failure anchor.** The "no stack trace / plain operator words" rule (used in AC#3) lives in the frozen monolith §2.F G.x error cluster, NOT in any canon part-file (G.2/G2 in canon = the D40 codex-consult gate, unrelated). Blocked on the UI-block canon-migration prerequisite (components/INDEX.md).
- Live System-of-Process → render transport (poll vs stream) — runtime choice; spec fixes the contract (truth-class + freshness), not the mechanism.
- Retention window for recent terminal rows — binding config per Deployment.

## Changelog

- v0.1 (2026-06-13): dual-lane corrections — `step_complete.md` → `step_completed.md`; removed fabricated `total` denominator (→ open gap); state enum `completed` → `success` per ExecutionResult; G.2 plain-words citation re-sourced to frozen monolith §2.F + flagged (no canon anchor); P6 inheritance stated.
