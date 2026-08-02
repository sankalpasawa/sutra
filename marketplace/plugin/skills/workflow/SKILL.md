---
name: workflow
preamble-tier: 1
version: 1.0.0
description: |
  Pedagogical Sutra-discipline wrapper. ONE invocation walks Claude through
  the canonical operating sequence (Input Routing → Depth + Estimation →
  BLUEPRINT → optional codex consult at Depth ≥ 3 → Build-Layer if D38 path
  → Execute → TRIAGE/ESTIMATE/ACTUAL → Output Trace). Convention only —
  governance hooks fire deterministically regardless. Use this skill for
  discoverability, onboarding, or when you want the full discipline visibly
  applied to a single task.
allowed-tools: []
---

## Why this skill exists

Per founder direction D40: every Sutra plugin client gets the governance
discipline by default. The 7 governance skills (`input-routing`,
`depth-estimation`, `blueprint`, `output-trace`, `readability-gate`,
`codex-sutra`, `skill-explain`) cover individual blocks; this skill gives
you ONE entry point that runs the **full canonical sequence** so you can
SEE Sutra's discipline in action on a single task.

Convention only — Claude Code lacks PreSkillUse enforcement, and the
underlying governance hooks fire on every turn regardless of whether you
invoke this skill. Skills/docs EXPLAIN; hooks ENFORCE.

## When to invoke

- **Onboarding**: a fresh client wants to see the discipline applied
  end-to-end on a real task they brought.
- **Pedagogy**: explaining Sutra to a teammate / founder / observer.
- **Reset**: a long session has drifted from per-turn discipline; one
  `/core:workflow <task>` resets the sequence visibly.
- **Audit**: confirming the discipline is being applied (per the G7
  acceptance harness expectation).

## When to skip

- Trivial fast-path tasks (read a file, answer a one-liner). The full
  sequence has cost; per `[Cadence is hours not days]` keep it for
  meaningful work.
- When governance is already clearly emitted (don't double up).
- When the user has set `~/.workflow-skill-disabled`.

## The canonical sequence

```
1. INPUT ROUTING (skill: core:input-routing)
   Emit: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION
   Skip when: never. Route every input.

2. DEPTH + ESTIMATION (skill: core:depth-estimation)
   Emit: TASK / DEPTH X/5 / EFFORT / COST / IMPACT
   Skip when: never. Pick a depth; document the cost.

3. BLUEPRINT (skill: core:blueprint)
   Emit: Doing / Steps / Scale / Stops if / Switch
   Skip when: pure-question turn (no tool calls planned).

4. CODEX CONSULT (skill: core:codex-sutra, consult mode)
   Trigger: Depth >= 3 AND Edit/Write/MultiEdit planned (per
            sutra-defaults.json .consult_policy).
   Skip when: Depth < 3, or no Edit/Write planned, or founder says
              "skip consult".

5. BUILD-LAYER MARKER (auto via hook)
   Trigger: path is governed by D38 (PLUGIN-RUNTIME / SHARED-RUNTIME /
            HOLDING-IMPL / LEGACY-HARD).
   Skip when: SOFT path or whitelisted path.

6. EXECUTE
   Apply the planned tool calls. Per per-step convergence (codex agreed),
   execute end-to-end without further approval gates per
   `[Converge and proceed]`.

7. TRIAGE / ESTIMATE / ACTUAL (skill: core:depth-estimation post)
   Emit after task completion:
     TRIAGE: depth_selected=X, depth_correct=X, class=correct|over|under
     ESTIMATE: tokens_est=N, files_est=M, time_min_est=T
     ACTUAL: tokens=<observed>, files=<touched>, time_min=<measured>

8. OUTPUT TRACE (skill: core:output-trace)
   Emit one line at end of response:
     > route: <skill> > <domain> > <nodes> > <terminal>
   Skip when: explicitly disabled at L0 verbosity.
```

## Decision tree (the short form)

```
Question? → 1, 2, 7, 8 (skip 3-6)
Read-only task? → 1, 2, 3, 7, 8 (skip 4-6)
Edit at Depth 1-2? → 1, 2, 3, 5, 6, 7, 8 (skip 4)
Edit at Depth 3+? → ALL 8 steps including consult (4)
```

## Override path

- `~/.workflow-skill-disabled` — disable this skill specifically
- `~/.sutra-defaults-disabled` — disables all D40 governance defaults
- Founder explicit override phrase: applies per memory `[Never bypass governance]` — founder authority is not a bypass

## Source-of-truth

- Founder direction: D40 in `holding/FOUNDER-DIRECTIONS.md`
- Canonical policy: `sutra-defaults.json` (machine) + `SUTRA-DEFAULTS.md` (human)
- Codex consult on this skill design: ADVISORY (renamed from `core:do`,
  honesty fix on sutra-learn classification)
- Companion skills: see the 7 governance skills referenced in each step

## 3-Layer Verification Stack (founder direction 2026-05-10)

Per-node verification composes 3 orthogonal layers with distinct depth gating + enforcement status:

| Layer | What | When | Depth gate | Enforcement (today) | Source |
|---|---|---|---|---|---|
| L1 | BLUEPRINT per-step Verify | each step in Steps list of BLUEPRINT box | D3+ | **HARD** via `blueprint-check.sh` V2.2 — marker must carry `HAS_PER_STEP_VERIFY=1` | `core:blueprint` V2.1 |
| L2 | PHASE-EXIT-VERIFY | end of each PHASE-* node (OBJECTIVE→OBSERVE etc.) | D3+ | **CONVENTION ONLY** — method-registry row exists; **no hook fires**. Discipline-level only. | method-registry: `PHASE-EXIT-VERIFY` |
| L3 | VERIFY-* family | end of full task (MEASURE phase) | **D2-D5 graduated** (BASIC@D2 → EVIDENCE@D3 → STAGED@D4 → MULTISTAGE@D5) | Convention (no hook) | method-registry: `VERIFY-BASIC/EVIDENCE/STAGED/MULTISTAGE` |

Three granularities. Each layer's failure triggers its own fix-loop. L1 fails → fix this step. L2 fails → re-shape or re-plan upstream. L3 fails → full-task re-execute.

**Enforcement honesty** (codex P2.2 fold, 2026-05-10): Only L1 has a hook backing it today. L2 + L3 are method-registry rows + per-turn discipline — they "describe what should fire" but no runtime check enforces them. Future ship may add L2 hook (text-scan model response for PHASE-* boundaries); L3 hooks are deferred indefinitely as VERIFY-* is task-shape dependent.

Founder direction "All three (layered)" picked 2026-05-10. "Force it" picked L1 enforcement at V2.2.

## Operationalization

1. **Measurement**: count `/core:workflow` invocations in `.enforcement/d40-compliance.log`
2. **Adoption**: ships with Sutra plugin; surfaced via `/core:start`
3. **Monitoring**: if invocation rate is < 10% of sessions after 30d on T2
   fleet, the skill is invisible — add discoverability nudge
4. **Iteration**: trigger redesign if users ignore the convention or if it
   gets cosmetically emitted without affecting actual work
5. **DRI**: Sutra-OS team
6. **Decommission**: when Native v1.0 absorbs the workflow shape as a
   primitive (V2 §A11 Skill = LEAF Workflow pattern)
