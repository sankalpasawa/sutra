---
part-id: B13
bucket: blocks
template: L8-feature-spec
parity-source: §12.17 row B13 + §12.16 founder voice round 5 + Q33
parity-source-sha256: e6619b95abc02680d8fcb05014f1388bb58f8a8686afef7dbae03e8ec4a31e0e
status: DRAFT v1
authored: 2026-05-09
---

# B13: Multi-Runtime Concurrency

## 1-line summary

Two simultaneous runtime processes interact safely — file-based locks on Artifact.id + ExecutionResult.id, lock table visible across processes, deadlock detection deferred to v2.

## Scope (in / out)

**In scope (v1)**:
- NEW `ConcurrencyCoordinator` per §12.17 row B13.
- File-based locks per Q33 default (2026-05-09) — matches existing JSONL fsync pattern + portable + observable.
- Lock targets: `Artifact.id` (per B9 / canon Asset/DataRef substrate) + `ExecutionResult.id` (per §2.6).
- Lock table visible across processes.

**Out of scope (v1)**:
- DB-style serializable transactions — Q33 default rejects for v1.
- Optimistic concurrency control with retry — Q33 v2 upgrade if perf signal lands.
- Deadlock detection — explicitly v2 per §12.17 row B13.
- Cross-process replay — per §8 OS-3 deferred.

## User outcome

Operator runs two runtime processes (e.g., Native + a parallel agent) and they coordinate safely on shared artifacts without corruption. Founder voice round 5: "When two runtime processes are there, how do they interact with each other? The one runtime process probably puts a lock on all the artifacts and everything on the states, and that second time, who is trying to do the same thing, they also know those things."

## UX flow (narrative; terminal + audit log)

1. Runtime A starts work touching Artifact A1 + ExecutionResult E1.
2. ConcurrencyCoordinator acquires file-based lock on A1.id + E1.id.
3. Runtime B starts and attempts to touch same A1 / E1.
4. Lock visible → Runtime B observes lock + waits OR exits depending on policy (canon-silent on wait-vs-exit default — gap per F2; runtime implementation choice).
5. Runtime A finishes → releases lock.
6. Runtime B proceeds with fresh read.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Runtime A holds lock on Artifact A1 | Runtime B attempts read-write on A1 | lock visible to B; B waits OR errors per policy (canon-silent — gap per F2) |
| 2 | Runtime A releases lock | Runtime B re-attempts | acquires lock; proceeds |
| 3 | Lock-file write fails (filesystem error) | acquisition fails | HS-4 fires per canon §6.9.4 (audit-unwritable); fail-closed per F3 |
| 4 | Deadlock scenario (circular wait) | v1 | NOT handled v1 per §12.17 (deferred v2); behavior undefined per F2 |

## Data model

NEW ConcurrencyCoordinator per §12.17 row B13. Per F5, canon authorizes new component. Not a new §2 primitive.

```
Lock = {
  target_id           // Artifact.id OR ExecutionResult.id
  holder_runtime_id
  acquired_at
  ttl                 // optional; specific value NOT specified in canon (gap per F2)
}
LockTable = Lock[]    // file-based, cross-process visible
```

Cross-refs:
- `../primitives/execution-result.md` (lock target)
- `../primitives/engine-event.md` (substrate for B9 artifact references)

## Edge cases

- **Lock holder crashes without release** → stale-lock recovery NOT specified in canon (gap per F2; future ADR may codify TTL eviction).
- **Lock-file corruption** → recovery via canon §6.8 recovery path (no new recovery per F3).
- **Many runtimes waiting on same lock** → ordering / fairness NOT specified in canon (gap per F2).
- **Filesystem doesn't support atomic file rename** → portability assumption fails; canon assumes POSIX-style fsync per ADR-013.

## Completion barrier (COMPLETION-BARRIER sub-spec)

**Amendment (2026-06-12 — lesson-port from RETIRED PROTO-002 "Wait for Parallel Completion")**: locks (above) serialize access to shared artifacts; the completion barrier is the join rule for fan-out. An orchestrating Execution MUST NOT transition to synthesis or any terminal state while any `sibling_group` member Execution is non-terminal (§2.6 state enum), and MUST NOT substitute its own work for an unfinished sibling's output. PROTO-002 check text verbatim: *"ALL agents complete? → proceed. No? → wait. Never substitute own work."*

- **Barrier semantics**: synthesis is gated on ALL fan-out Executions reaching a terminal state. The daemon owns Execution rows with terminal states, so the barrier is a first-class invariant — block or queue the orchestrator step on violation, never warn-and-proceed. This is deliberately NOT a port of production's /tmp-mtime heuristic (output files modified <60s + background-job count + `.running` markers), which is a workaround for not owning the execution substrate.
- **Never-substitute rule**: a missing or failed sibling output is surfaced as missing/failed in the synthesis input set; the orchestrator never fabricates a stand-in. Production hook warning verbatim: "Do NOT write synthesis/output until ALL agents complete. Read ALL agent outputs before proceeding. Do NOT substitute your own work for pending agent work."
- **Host-LLM advisory analog**: outside daemon control (host-LLM sessions), a SOFT advisory analog of the production hook remains the right shape — warn, exit 0, never block.
- **Origin incidents (rationale, ported with the lesson)**: Maze HOD 2026-04-04 — orchestrator wrote report over 3 running agents, missed 6 bugs. Dharmik SEO audit 2026-04-07 — orchestrator compiled before 4 agents returned, incomplete JS analysis.

Living evidence (production, fleet-shipped): `sutra/marketplace/plugin/hooks/agent-completion-check.sh` — PostToolUse on `Bash|Edit|Write` (hooks.json L236-L243), SOFT exit-0; fast-path skip unless `/tmp/claude-agent-*` or `/tmp/claude-tasks` markers exist; on any running-sibling signal it prints the PROTO-002 warning block restating the rule.

Acceptance criteria (barrier):

| # | Given | When | Then |
|---|---|---|---|
| B1 | Orchestrating Execution with sibling_group fan-out; ≥1 sibling non-terminal | orchestrator attempts synthesis/terminal transition | transition blocked or queued; never proceeds with substituted work |
| B2 | All sibling_group Executions terminal | orchestrator proceeds to synthesis | allowed; failed siblings surfaced as failed in synthesis inputs, never back-filled |

**Falsification test**: the audit log shows an orchestrating Execution reaching synthesis/terminal state while a `sibling_group` member Execution is still non-terminal, OR a synthesis artifact contains orchestrator-fabricated content standing in for a sibling output that never arrived — either observation proves the barrier violated.

Provenance: lesson-port from RETIRED PROTO-002 — retired as a protocol ("agent-execution concern, not a system invariant") but the lesson ships fleet-wide as living hook text. Amendment parity-source (deviation from the NATIVE-ENGINE.md-anchor norm — this content is a canon gap; source is the protocol corpus): `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-002 L132-143, sha256 `b33aeb22699dc457977ab5f314a7621dff793f2808ee5a4f896f44ee885b1570`.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — lock acquisition / release as policy decisions.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Cross-company decision-replay success rate (canon §14.9 ≥99%) — concurrent runtimes must preserve replay determinism.

## Dependencies

- **Primitives**: `execution-result`, `engine-event`, `tenant`.
- **Events**: `policy_decision`.
- **Surfaces**: `audit`, `run`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: B9 (Artifact catalog substrate locks), 7e (mid-exec mutation race control composes with B13), 7d (lifecycle phases coordinate via B13).
- **Pillars**: P12 (Deterministic surface around stochastic core).
- **ADRs**: ADR-013 (3-channel JSONL durability + fsync — substrate).

## References

- NATIVE-ENGINE.md §12.17 row B13 (founder voice round 5).
- Q33 (§12.19) — file-based locks v1; OCC v2 if perf signal lands.
- §8 OS-3 (cross-process replay deferred).
- §8 OS-22 (A2A cross-process workflow comm deferred v2).
- `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-002 (RETIRED) — completion-barrier lesson source.
- `sutra/marketplace/plugin/hooks/agent-completion-check.sh` + `sutra/marketplace/plugin/hooks/hooks.json` L236-L243 — living production evidence (SOFT PostToolUse warning).
