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
