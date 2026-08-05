# WORK-DISPATCH Charter

Status: ACTIVE (founder-directed 2026-08-04, mid-WDP)
Engine of record: `sutra/os/engines/DISPATCH-ENGINE.md` (HLD, frozen at G2)
Decisions: `sutra/os/decisions/ADR-030-work-dispatch.md` (ACCEPTED, founder sign-off as-is)
Operating department: `holding/departments/dispatch/`

## Purpose

Every unit of work carries a dispatch decision BEFORE mutation: where it runs
(parent session / spawned session), at what grain (one atom / many), on which
model, at what effort — resolved from policy, frozen at bind, escalated only
through the audited ladder. This charter is the governance contract ABOVE the
engine: the engine says HOW; this charter says WHAT MUST ALWAYS HOLD.

## Invariants (violations are incidents, not candidates)

| # | Invariant | Enforced by |
|---|---|---|
| 1 | One open Work-Atom per session; mutation requires it | atom-floor.sh (HARD) |
| 2 | Atom touches sit INSIDE the resolved dispatch envelope; envelope frozen at bind | sutra-dispatch bind + close-time A5 both-must-agree |
| 3 | Verify declared BEFORE work; close only via pre-declared verify; targets covered by envelope | sutra-atom open/close (A4, hash-pin) |
| 4 | Top-tier (rank-1) model routing requires founder approval — initial AND escalation; auto flags never approve | routing-policy-resolve + sutra-dispatch escalate (exit 2) |
| 5 | Escalations capped (max_total_escalations); every escalation is a ledger row with trigger + approver | sutra-dispatch escalate |
| 6 | Ledgers are append-only; dispatch rows route through the controlled writer (jq-valid, <4KB, exactly-one-append) | wdp-ledger.sh (W6-T51 hardens) |
| 7 | Orphan mutation (journal row, no attributable open atom) is the ONE red line in telemetry — always surfaced, never a candidate | dispatch-report.sh |

## Authority boundaries

- Routing policy (`routing-policy.json`) versioned; ladder/floor changes bump
  `version` and land as policy rows, never silent edits. Governance floors are
  bidirectional (touch under floor path OR dir-touch containing floored file).
- Telemetry emits REVIEW CANDIDATES; humans judge; policy version bumps;
  nothing auto-retunes (TELEMETRY-DESIGN law).
- The fable gate answers to the founder alone. `DISPATCH_FOUNDER_APPROVAL=yes`
  is the only approval channel; it is honor-system at env level and audit-logged.

## Amendment

Charter edits follow D38/PROTO-021 (founder identity check for non-founder
operators). Engine changes route through the engine doc + a new ADR; this
charter references, never duplicates, engine mechanics (D54 pattern).
