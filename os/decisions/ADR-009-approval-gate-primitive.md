# ADR-009 — Approval Gate as Workflow-Level Primitive

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.3 (`Workflow.requires_approval`), §2.4 (`WorkflowStep.requires_approval`), §3.4, §6.6; invariants I-14, I-15.

## Context
Some Workflows (and some steps within Workflows) must pause for explicit founder approval before mutating state — e.g. promoting a proposed pattern to a registered Workflow (ADR-010), or running an irreversible publication step. The native daemon is detached from stdin (`organic-emergence-v1-SPEC.md` §0 P1.3), so an inline `read -p "Y/N"` prompt is impossible.

Two approaches were considered and live-tested:

- **Free-form Y/N stdin gate** — physically impossible: daemon has no controlling TTY; subprocess host steps run async.
- **Re-execute-from-scratch on approval** — wasteful + non-replayable; loses prior step outputs; violates "execution row is one identity".

Gap-audit `Q9 UNMET` (`holding/research/2026-04-29-native-gap-audit.md`) and `RESUME-V1.X.md` §2 Wave 2 surfaced the gap: approval needs a typed field on the Workflow/Step + persisted ledger row + utterance-driven resume.

### Alternatives considered
- Inline founder confirmation (Y/N stdin) — rejected because daemon is detached.
- Approval external to Workflow (separate "approval queue" subsystem) — rejected because it splits state across two registries; replay becomes ambiguous.

## Decision
Native engine MUST add `requires_approval: bool` at both `Workflow` and `WorkflowStep` levels, and emit/handle the typed event triplet `approval_requested → approval_granted | approval_denied`.

- Step with `requires_approval=true` reaches → executor emits `approval_requested` → Execution transitions to `awaiting_approval` → ledger row persisted at `user-kit/pending-approvals/E-<id>.json` (I-15).
- Founder utterance `approve E-<id>` parsed → `NativeEngine.resumeApproved(execId)` → continue at `step_index+1`. `reject E-<id> <reason>` → `approval_denied` → terminal `workflow_failed`.
- Idempotent: re-fire on resolved approval emits `approval_already_handled` (I-14 holds: exactly one terminal event per Execution).
- Multi-party approval / quorum predicate deferred (`sutra/os/engines/NATIVE-ENGINE.md` §8 OS-15).

## Consequences

| Kind | Effect |
|---|---|
| + | Approval gate is a typed primitive, not a free-form pause — replayable + auditable |
| + | Daemon-detached: founder approves via utterance from their interactive session (not stdin) |
| + | Persistent ledger row survives daemon restart — pending approvals are recoverable |
| − | Two-state model (`Workflow.requires_approval` vs `WorkflowStep.requires_approval`) — author must pick the right level |
| − | Idempotency contract requires de-dup logic on resume |
| 0 | OS-15 multi-party / quorum approval shape revisits when first use case lands |
