---
part-id: B8
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B8 + §12.8 founder voice round 3 + Q25
parity-source-sha256: d931a4f1f711d805937e64a6928b0bebba150778a4f3f79afa85ada6452b6704
status: DRAFT v1
authored: 2026-05-09
---

# B8: Task Framework + Factors-Reasoning

## 1-line summary

Sutra's existing 8-phase TASK-LIFECYCLE (D30a) gains a required `factors[]` typed array between SHAPE and PLAN — enumerated, weighted factors that frame the reasoning step.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Task lifecycle (D30a 8-phase referenced by canon §12.6 row 7d) — add `factors[]` between SHAPE and PLAN per §12.9 row B8.
- Each factor weighted (per Sutra core IP weight-distribution per memory `project_sutra_core_ip` referenced in §12.9 row B8).
- Per Q25 default (2026-05-09) — extends Right-Effort Discipline factors to first-class typed array; same conceptual root.

**Out of scope (v1)**:
- Auto-derivation of factors from intent (Native proposes factors automatically) — canon-silent (gap per F2).
- Re-weighting of factors mid-Workflow — single-pass v1.
- Cross-Task factor reuse across Workflows — not specified in canon (gap per F2).

## User outcome

Operator's task reasoning is grounded in named factors with weights, instead of implicit reasoning. Founder voice round 3: "we have a basic framework of how that task should be created, which is the task framework which we have, and then we figure out factors and everything around them in the reasoning part of it".

## UX flow (narrative; terminal + audit log)

1. Workflow enters SHAPE phase per 7d lifecycle.
2. SHAPE phase completes; B8 mandates `factors[]` array authored before PLAN phase.
3. Each factor: `{name, weight, rationale}` (specific schema NOT specified in canon — gap per F2; runtime implementation choice).
4. Factors persisted as artifact per B9.
5. PLAN phase consumes factors as reasoning anchors (B11 PromptBuilder embeds).

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Workflow in 7d SHAPE phase completes | transition to PLAN attempted | `factors[]` array required; if empty, transition rejected; specific error shape NOT specified in canon (gap per F2) |
| 2 | factors[] populated | transition to PLAN | `artifact_registered` (§3.2 #9) emitted with factors artifact; PLAN phase fires |
| 3 | Factor weights do not sum to 1.0 (or canonical normalization) | weight validation | normalization rule NOT specified in canon (gap per F2; runtime implementation choice) |
| 4 | Operator overrides factors mid-Workflow | overlaps 7e mutation | classified per Q17; trivial vs material |

## Data model

Per §12.9 row B8: EXTEND existing TaskLifecycle (D30a). No new §2 primitive (per F5).

Per Q25 default: extends Right-Effort Discipline factors (memory) to first-class typed array.

```
Factor = {
  name
  weight
  rationale
}
TaskLifecycle (extended) = {
  ...D30a 8-phase,
  factors: Factor[]    // required between SHAPE and PLAN
}
```

Cross-refs:
- `../primitives/workflow.md` (lifecycle host)
- `../primitives/execution-result.md` (lifecycle_phase per 7d extension)
- `../primitives/engine-event.md` (factor artifact persistence)

## Edge cases

- **Single factor** (factors array length 1) → degenerate but allowed; canon-silent on minimum (gap per F2).
- **Factor with weight=0** → meaning ambiguous; canon-silent (gap per F2).
- **Factors conflict with Charter constraints (per B10)** → conflict-resolution rule NOT specified in canon (gap per F2; Charter constraints likely supersede per canon Charter binding).
- **Operator skips SHAPE phase** → not allowed per 7d (lifecycle is sequential v1).

## Telemetry

Events (canon-existing only):
- `artifact_registered` (#9) — factors artifact persisted.
- `step_completed` (#6) — at SHAPE phase boundary.
- `policy_decision` — if factors fail normalization gate.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Pattern-detection precision — explicit factors raise reasoning quality + emergence proposal precision.
- Operator-Hours-Saved (long-tail) — named factors reduce re-reasoning across sessions.

## Dependencies

- **Primitives**: `workflow`, `execution-result`, `engine-event`.
- **Events**: `artifact_registered`, `step_completed`, `policy_decision`.
- **Surfaces**: `run`, `audit`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: 7d (lifecycle phase host), B11 (PromptBuilder consumes factors), B10 (Charter constraints may conflict; canon supersedes), B9 (factors emitted as artifact).
- **Pillars**: P11 (Constrained problem construction), P14 (Outcomes drive design).
- **Memory**: `project_sutra_core_ip` (weight-distribution engine — substrate B8 references).

## References

- NATIVE-ENGINE.md §12.9 row B8 (founder voice round 3).
- Q25 (§12.11) — extends Right-Effort Discipline factors.
- D30a (Sutra TASK-LIFECYCLE 8-phase).
- Memory `project_sutra_core_ip` (weight-distribution engine).
