<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-011-on-failure-policy-five-set.md. -->
# ADR-011 — `on_failure` Policy: Closed 5-Set

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.3 (`Workflow.failure_policy`), §2.4 (`WorkflowStep.on_failure`), §6.5; events 4, 7, 19-24.

## Context
Workflow steps fail (timeout, host crash, validation reject, downstream tenant deny). The engine needs a deterministic + replayable response. A boolean `retry: true/false` is too coarse; a custom callback per Workflow defeats replay (non-deterministic; every replay needs the callback definition still loaded).

`RESUME-V1.X.md` §2 Wave 4 + `holding/plans/native-v1.0/M5-workflow-engine.md` §Goal A-6 + `holding/research/2026-04-29-native-d5-invariant-register.md` §2 degradation matrix together identified five distinct response shapes that real Workflows need, each with a distinct EngineEvent + state transition.

### Alternatives considered
- Boolean `retry: true/false` — rejected because retry conflates with rollback, escalation, pause; degradation matrix demands more shapes.
- Custom callback per Workflow — rejected because non-deterministic + not replayable; loses I-7 audit guarantee.
- Single `abort` only — rejected because legitimate pause/escalate/continue paths get killed (RESUME-V1.X Wave 4 evidence).

## Decision
Native engine MUST define `step.on_failure` as exactly one of `{rollback, escalate, pause, abort, continue}` — closed 5-set, no extension without ADR.

| Policy | Effect |
|---|---|
| `rollback` | Compensate steps in reverse; emit `workflow_rollback_started` → `_complete` or `_partial`. |
| `escalate` | Emit `workflow_escalated`; route to founder channel. |
| `pause` | Emit `step_paused`; persist queue entry; resume on signal. |
| `abort` | Emit `workflow_failed` immediately. |
| `continue` | Log failure; advance to step[i+1]; set `partial=true`; skip outputs validation for the failed step; do NOT abort. |

- `Workflow.failure_policy` is the default; `step.on_failure` overrides per-step.
- Each policy has a typed event family (events 4, 7, 19-24) — no free-form failure log.
- Sixth policy requires a new ADR + new event types + parser + executor branch (extension cost is deliberate).

## Consequences

| Kind | Effect |
|---|---|
| + | Five concrete shapes cover observed degradation matrix without overload |
| + | Replay is deterministic — same failure + same policy → same event sequence |
| + | Rollback/escalate/pause are first-class events (4, 7, 19-24) — auditable end-to-end |
| − | Authors must pick the right policy per step; defaults push the choice up to Workflow level |
| − | `continue` semantics surface OS-5 open seam (`commitment_broken` per-step vs terminal-only) |
| 0 | Closed-set extension blocked by deliberate ADR cost — keeps the 5-set stable |
