# ADR-007 — Decision Provenance as Typed Primitive

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §2.9, §3, §6.1; invariants I-7, I-9, I-17.

## Context
Every consequential decision (policy_decision, approval_granted, tenant_boundary_violation, cutover gate, etc.) needs a replayable record. Two prior records were live but partial:

- **PROTO-019 gate-log JSONL** — appends per-hook decisions but rows omit `policy_id` and `policy_version`, so the same decision under different policy versions is indistinguishable. (Gap-audit `Q10 UNMET`.)
- **Free-form log lines** — printf-style messages scattered across hooks; not parseable for replay.

Sources `holding/research/2026-04-29-native-d2-decision-provenance-spec.md` §1-§2 + `holding/research/2026-04-29-native-d1-authority-map.md` §2 A-AUDIT defined the gap: every consequential decision must be reconstructible from `agent_identity + policy_id + policy_version + data_refs + outcome` to enable cross-process replay (deferred to OS-3).

### Alternatives considered
- Unstructured log append only — rejected because grep-level recovery loses policy version, fails F-8, blocks replay.
- Extend existing PROTO-019 gate-log row schema only — rejected because gate-log is hook-scoped; Workflow/Step/Tenant/Cutover scopes need the same primitive uniformly.

## Decision
Native engine MUST emit a typed `DecisionProvenance` row for every consequential decision (I-7), with `policy_id` AND `policy_version` non-empty (I-9, I-17).

- Schema fields: `id` (uuid v4), `ts_ms`, `agent_identity` (chain), `policy_id`, `policy_version`, `scope ∈ {WORKFLOW, STEP, HOOK, TENANT, CUTOVER}`, `outcome ∈ {allow, deny, pause, escalate}`, `reason` (sanitized: no colons / no newlines), `data_refs[]` (each carrying `authoritative_status` per ADR-008).
- `PolicyDispatcher.evaluate(scope, evidence)` returns DecisionProvenance; emitters APPEND via `UserKit.appendDecisionProvenance` with fsync (ADR-013).
- DecisionProvenance is the replay surface — `holding/state/decision-provenance.jsonl` reconstructible by re-running the policy dispatcher on the recorded evidence.

## Consequences

| Kind | Effect |
|---|---|
| + | Every consequential decision is replayable from a structured row |
| + | Policy version drift is detectable (same evidence + different policy_version → different outcome) |
| + | Five scopes (WORKFLOW/STEP/HOOK/TENANT/CUTOVER) cover every decision surface uniformly |
| − | Every hook + executor must call PolicyDispatcher (cannot inline ad-hoc allow/deny) |
| − | Schema migration: PROTO-019 gate-log rows must be backfilled or marked legacy |
| 0 | OS-3 cross-process replay deferred — single-process replay works at v1.0 |
