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

**HARD reject + Founder ASK gate.**

- LiteExecutor rejects the step dispatch (no host-LLM call fires).
- Execution enters `state='paused_hs1'` (specialized pause, NOT a regular pause).
- `policy_decision` event emits with `outcome='deny'`, `policy_id='HS-1'`, `policy_version='1.0'`.
- DecisionProvenance row written with `reason='HS-1: reflexive_check Constraint violated; modifies_sutra=true without authorization'`.
- Founder ASK gate fires: native daemon surfaces the rejected step + provenance to founder via approval primitive.
- Workflow does NOT auto-retry; founder MUST explicitly clear `reflexive_check` Constraint via signed approval utterance before resumption.

## Recovery path

To resume after HS-1:

1. Founder reviews the rejected step + provenance reason.
2. Founder evaluates: is the modification legitimate (e.g., authorized plugin update) OR malicious (e.g., Workflow attempting unauthorized hook modification)?
3. **If legitimate**: founder utterance `approve reflexive E-<execution-id> reason="<justification>"` → `reflexive_check.cleared = true` for THIS Execution only; LiteExecutor resumes step.
4. **If malicious**: founder utterance `reject E-<execution-id> reason="reflexive boundary violation"` → Workflow terminates; rejection logged immutably; `policy_decision` event emits with `outcome='reject'`.

Override is per-Execution, not per-Workflow — clearance does NOT persist across Executions of the same Workflow.

## Downstream effects

When HS-1 fires:
- Current Execution state pinned at `paused_hs1`; no further steps dispatch until founder responds.
- Sibling Executions of the SAME Workflow continue independently (HS-1 is per-Execution scope).
- Sibling Executions of OTHER Workflows continue independently.
- AUDIT surface persists the rejection to immutable log.
- Telemetry: `hs1_fire_count` counter increments; >3 fires/24h in same Tenant escalates to founder via dedicated alert channel.
- Operator-Hours-Saved (N*) metric receives `-0.5h` adjustment (debit) for the paused work pending founder review.

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
