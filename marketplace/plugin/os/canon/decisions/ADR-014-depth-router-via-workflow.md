<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-014-depth-router-via-workflow.md. -->
# ADR-014 — Depth Router via Native's Own Workflow (W-load-native-context)

## Status
Accepted 2026-05-07 (formalized as part of Native formalization v1.0). Charter contract: see `sutra/os/engines/NATIVE-ENGINE.md` §5.5; related: `sutra/os/decisions/ADR-004-registry-and-effector-split.md` (effector boundary).

## Context
Native needs a depth-router: pull only the Native context (charters / ADRs / engine docs) needed for a turn, scored by depth + task class. Three implementations were live during Wave 1:

- **Bash script reading docs directly** — fast but no Execution audit row, no structured `return_contract` validation, no replay.
- **Inline LLM logic** in the founder session — works but no replay; no deterministic load-matrix; founder cannot inspect what was loaded.
- **Native Workflow (`W-load-native-context`)** — fires `codex exec` (sandboxed analysis), emits a structured load-plan JSON as `return_contract`, persists Execution row.

Sources: `holding/research/2026-05-06-w-load-native-context-design.md` §1-§2; `holding/RESUME-NATIVE-CHARTER.md` §depth-router; `holding/research/2026-04-29-native-v1.0-final-architecture.md` §Goals.

The Workflow option is also dogfood: Native dogfooding its own registry+audit pattern proves the pattern works for read-only orchestration (no mutation), AND every depth-router fire is an Execution row replayable like any other.

### Alternatives considered
- Bash script reading docs — rejected: no audit row, no `return_contract` validation, no Execution lineage.
- Inline LLM logic in-session — rejected: not replayable; deterministic load-matrix not provable.
- Hybrid (bash for fast path, Workflow for slow path) — rejected for v1.0: maintains two code paths with the same semantics; defer until measured fast-path need.

## Decision
Native engine MUST implement the depth-router as the `W-load-native-context` Workflow — fires `codex exec`, emits a structured load-plan JSON via `return_contract`, persists an Execution row.

- Workflow uses `host='codex'` (read-only sandbox per ADR-005) — analysis only, no mutation.
- Inputs: turn context, depth signal, task class slug.
- Outputs: load-plan JSON `{include: [paths], exclude: [paths], rationale}` — schema-validated by `return_contract`.
- Execution row + EngineEvent audit applies same as any Workflow.
- Pattern is the canonical example of "Native runs Native" — reuse_tag=true makes it discoverable as a Skill via `SkillEngine.resolve`.

## Consequences

| Kind | Effect |
|---|---|
| + | Every depth-router fire is replayable from the Execution row |
| + | Dogfood: Native's registry+audit pattern proven on a read-only use case |
| + | `return_contract` schema validation catches bad load plans at boundary |
| − | Per-fire cost includes Workflow boot + codex subprocess (~300ms baseline) |
| − | Single workflow centralizes the loader — extension via more workflows, not config |
| 0 | First fast-path measurement may force a hybrid (bash fast-path + Workflow slow-path) |
