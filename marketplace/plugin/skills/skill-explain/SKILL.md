---
name: skill-explain
preamble-tier: 1
version: 1.0.0
description: |
  Emit a 4-line WHAT/WHY/EXPECT/ASKS card before any other Skill is invoked.
  Per founder direction D40, this is the convention every Sutra plugin client
  follows so the user can predict the experience of any skill before it runs.
  Convention only — Claude Code lacks PreSkillUse hook, so this is unenforceable
  via plumbing. The card lives in the model's response, not as a hook side-effect.
allowed-tools: []
---

## Why this skill exists

Per founder memory `[Explain skills on first use]` and direction D40 (2026-04-30):

> "Non-tech founders need to predict every skill before it runs. Emit a 4-line skill card (WHAT/WHY/EXPECT/ASKS) before every Skill invocation."

This skill provides the canonical card template + invocation rules. Other skills don't have to duplicate the template; they reference this skill. Per the D40 single-canonical-policy-surface principle, the rule lives in `sutra-defaults.json` `.skill_explanation`.

## When to invoke (i.e. when the model emits a card)

**Before every Skill tool call**, the model emits this card in its visible response:

```
SKILL:  <name>
WHAT:   <what the skill does in one sentence>
WHY:    <why it applies to the current task>
EXPECT: <what the user will see — interactions, files written, time>
ASKS:   <what input the skill will request from the user, or "none">
```

## When to skip

- The skill being invoked IS `core:skill-explain` (no card-for-card recursion)
- The skill is invoked by another skill mid-task — the parent skill has already emitted its card
- The user has set `~/.skill-explain-disabled` (per-user opt-out)
- The user explicitly says "skip skill cards" in this session

## Format requirements

- 5 lines exactly: SKILL line + 4 content lines
- Each label is left-aligned at column 0; values aligned after the colon (single space minimum)
- Use plain ASCII only (no unicode box-drawing) per `[Terminal box formatting]` memory
- Place inside a fenced code block so it renders as monospace
- Maximum 80 characters per line — split long values onto continuation lines indented 8 chars

## Why convention not enforcement

Per codex caveat (D40 verdict 2026-04-30): hook-injects-prompt is fragile, and Claude Code has no PreSkillUse hook to enforce this. The card lives in the model's response — the model must choose to emit it. Skills/docs EXPLAIN; hooks ENFORCE.

If the model habitually skips the card, the gap surfaces in the 5-turn acceptance harness (G7) Q4 scenario, which fails the install verification — that's the deterministic backstop.

## Source-of-truth

- Founder direction: D40 in `holding/FOUNDER-DIRECTIONS.md`
- Memory promoted to plugin: `[Explain skills on first use]` (was Asawa-only)
- Canonical policy surface: `sutra-defaults.json` `.skill_explanation`
- Companion human-readable: `SUTRA-DEFAULTS.md` § "Skill Explanation Cards (4-line)"
- Execution plan: `holding/plans/governance-parity-execution-plan.md` Task F

## Example invocation

Before invoking `superpowers:brainstorming` for a new feature design:

```
SKILL:  superpowers:brainstorming
WHAT:   Structured design exploration before implementation
WHY:    User asked "what is the best way" — this is design, not code
EXPECT: ~1-2 min interaction; options table; 2-3 sharpening questions
ASKS:   none mid-skill; surfaces at the recommendation gate
```

Before invoking `core:codex-sutra` (consult mode):

```
SKILL:  core:codex-sutra (consult mode)
WHAT:   Sutra-owned wrapper for Codex CLI; independent xhigh review
WHY:    Depth >= 3 + Edit/Write planned (D40 consult-before-edit policy)
EXPECT: 2-5 min wait; codex returns confidence-tagged structured response
ASKS:   none until codex returns; then I surface convergence/divergence
```

## Operationalization (per OPERATIONALIZATION charter)

1. **Measurement**: 5-turn acceptance harness Q4 scenario (G7) checks card emission
2. **Adoption**: ships with Sutra plugin; documented in `SUTRA-DEFAULTS.md` and `core:start` onboarding
3. **Monitoring**: `.enforcement/d40-compliance.log` (introduced with G7) — count card-present turns vs total
4. **Iteration**: if compliance < 80% across T2 fleet sessions, surface to founder for prompt-strengthening
5. **DRI**: Sutra-OS team
6. **Decommission**: when Claude Code introduces PreSkillUse hook, this skill becomes hook-backed (still useful as the canonical template definition)
