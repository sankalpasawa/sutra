---
part-id: HS-1
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9 row HS-1 + §7 row "Reflexive primitive modification" + §4 F-7
parity-source-sha256: da6f0c1519553967ba17a28a5849ac27fbf72c6d182c9ba22f654220792dfaba
status: ACTIVE
authored: 2026-05-09
---

# HS-1: Reflexive check Constraint violation

## Status

ACTIVE (v1.0 — shipped with Native runtime).

## Context (when this fires)

HS-1 fires when a Workflow attempts to modify Sutra core primitives (e.g., `sutra/marketplace/plugin/hooks/`, `sutra/marketplace/plugin/skills/`, charter files) WITHOUT the `reflexive_check` Constraint cleared.

Trigger conditions:
1. Workflow has `modifies_sutra=true` field set.
2. AND `reflexive_check` Constraint is NOT cleared at the moment of step dispatch.
3. The step's action attempts to write to a path within sutra/marketplace/plugin/** or sutra/os/charters/**.

Observable state at trigger time:
- `Workflow.modifies_sutra === true`
- `reflexive_check.cleared === false` OR Constraint not present in step's invariant set
- WorkflowStep about to invoke a tool with target_path matching Sutra core glob

## Decision (fail-mode)

**HARD reject + Founder ASK gate** (per canon §6.9 row HS-1 + §7 STRIDE Elevation-of-Privilege row + §4 F-7).

- LiteExecutor rejects the step dispatch (no host-LLM call fires).
- `policy_decision` event emits (per §3.2 row #8) with `outcome='deny'`, `policy_id='HS-1'`.
- DecisionProvenance row written with `reason` referencing F-7 violation.
- Founder ASK gate fires: native daemon surfaces the rejected step + provenance to founder via approval primitive (per ADR-009).
- Workflow does NOT auto-retry; founder must clear `reflexive_check` Constraint via explicit approval before resumption.

(Implementation details — specialized state names, escalation thresholds, N* impact — are NOT specified in canon §6.9. Runtime implementation chooses these; this part-file is the spec, not the implementation. Future ADR may codify implementation choices.)

## Recovery path

Per canon §6.9 row HS-1, recovery requires the Founder ASK gate to clear. Specific utterance forms + per-Execution-vs-per-Workflow scope of the clearance are implementation choices NOT specified in canon — to be codified in a future ADR if/when ambiguity costs founder time. v1.0 default: founder utterance approves clearance; LiteExecutor resumes.

## Downstream effects

Per canon §6.9 + §7 + F-7, the directly canon-specified downstream effects are:
- LiteExecutor hard-rejects the step dispatch (no host-LLM call fires).
- AUDIT surface persists the rejection (DecisionProvenance JSONL).
- Founder ASK gate is the unblocking mechanism (no auto-retry; no auto-escalation).

Specialized runtime states (e.g., a distinct `paused_hs1` Execution state), per-tenant fire-count escalation thresholds, and N* metric debit semantics are NOT specified in canon. Runtime implementations may choose these; this part-file does not codify them. If/when an implementation choice becomes important enough to lock down, a new ADR records it.

## STRIDE relevance

**Elevation of Privilege**: HS-1 guards against Workflow elevating its own permissions by modifying Sutra core. Specifically blocks:
- Hook modification (an unprivileged Workflow attempting to overwrite a PreToolUse hook to disable governance).
- Skill registration tampering (a Workflow attempting to register a malicious replacement skill).
- Charter rewrites (a Workflow attempting to relax discipline charters).

Per §7 STRIDE table row "Elevation of Privilege / Reflexive primitive modification": HS-1 is the terminal guard; L6 REFLEXIVITY law + F-7 are the upstream guards.

## References

- NATIVE-ENGINE.md §6.9 row HS-1 (canonical hardstop definition).
- NATIVE-ENGINE.md §4 F-7 — Forbidden Coupling: "Workflow with modifies_sutra=true MUST have reflexive_check Constraint cleared".
- NATIVE-ENGINE.md §7 STRIDE row — Elevation of Privilege / Reflexive primitive modification.
- ADR-009 — per-workflow approval gate (mechanism behind the founder ASK gate).
- L6 REFLEXIVITY law — upstream meta-rule that primitives cannot self-modify without governance clearance.
- `build-layer-check.sh` PreToolUse hook — companion mechanical guard that fires on Edit/Write to Sutra core paths.
