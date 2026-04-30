---
name: workflow
description: Pedagogical Sutra-discipline wrapper. Walks through the canonical operating sequence (Input Routing → Depth + Estimation → BLUEPRINT → optional codex consult at Depth ≥ 3 → Build-Layer if D38 path → Execute → TRIAGE/ESTIMATE/ACTUAL → Output Trace) on a single task. Convention only — governance hooks fire deterministically regardless. Use for onboarding, pedagogy, reset, or audit.
disable-model-invocation: false
---

# /core:workflow — Run the full Sutra discipline on one task

One invocation walks Claude through the **canonical operating sequence** so the user can SEE Sutra's discipline applied end-to-end on a single task they bring.

## Usage

```
/core:workflow <task description>
```

Or with no argument — Claude will ask what task to run the discipline against.

## What you'll see

The 8-step canonical sequence (per `sutra-defaults.json`):

1. **Input Routing** — TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION
2. **Depth + Estimation** — TASK / DEPTH X/5 / EFFORT / COST / IMPACT
3. **BLUEPRINT** — Doing / Steps / Scale / Stops if / Switch (skip on pure-question turns)
4. **Codex consult** — only if Depth ≥ 3 AND Edit/Write/MultiEdit planned
5. **Build-Layer marker** — only if path is governed by D38 (PLUGIN-RUNTIME / SHARED-RUNTIME / etc.)
6. **Execute** — apply the planned tool calls
7. **TRIAGE / ESTIMATE / ACTUAL** — post-completion variance triple
8. **Output Trace** — one-line route at end

## Decision tree (the short form)

| Task shape | Steps emitted |
|---|---|
| Pure question | 1, 2, 7, 8 (skip 3-6) |
| Read-only task | 1, 2, 3, 7, 8 (skip 4-6) |
| Edit at Depth 1-2 | 1, 2, 3, 5, 6, 7, 8 (skip 4) |
| Edit at Depth ≥ 3 | All 8 steps including consult |

## When NOT to use

- Trivial fast-path tasks (per `[Cadence is hours not days]` — keep this for meaningful work)
- When governance is already clearly emitted in your turn (don't double up)
- When `~/.workflow-skill-disabled` is set

## Convention only

This is a pedagogical wrapper — Claude Code lacks `PreSkillUse`, so no hook enforces the sequence. The 51 governance hooks fire deterministically on every turn regardless of whether you invoke this. Skills/docs EXPLAIN; hooks ENFORCE.

## Source

- Skill body: `sutra/marketplace/plugin/skills/workflow/SKILL.md` (full pedagogy + sequence)
- Canonical policy: `sutra-defaults.json` + `SUTRA-DEFAULTS.md`
- Founder direction: D40 in `holding/FOUNDER-DIRECTIONS.md`

## Related

- `/core:depth-check` — manual Depth + Estimation only (faster than the full workflow)
- `/core:learn` — interactive Sutra tutor (lesson-based, not workflow-based)
- `/core:start` — onboarding (run this first)
