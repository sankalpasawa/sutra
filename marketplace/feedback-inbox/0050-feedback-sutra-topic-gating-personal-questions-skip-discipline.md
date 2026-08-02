---
id: 0011
date: 2026-05-03
source: dogfood (T4 fresh sim)
sim_session: fresh-20260503T051738Z
plugin_version: core@sutra v2.17.0
severity: high
status: fixed-in-2.18.0-pending-release
type: bug
tags: [topic-gating, discipline-skipped, personal-questions, fleet-wide, codex-converged]
---

# Topic-gating: Sutra skips per-turn discipline on personal/non-coding questions

## What happened

In a fresh T4 sim session (the rig built earlier 2026-05-03), founder ran:
```
research on if wife does more of mangaging for my needs, its feel inauthentic
```

Sutra-plugin response opened with:
```
That's a personal question, not a coding one — happy to think through it with you,
though I'll be brief and you can push back.
```

**No H-Sutra header. No INPUT/TYPE routing block. No DEPTH/EFFORT/COST/IMPACT block.**

The plugin classified the input as out-of-scope ("personal not coding") and downgraded to brief unstructured prose, skipping the entire per-turn discipline stack.

## Founder direction

> "sutra for anything and everything"

Discipline applies to every input regardless of topic. No topic gates.

## Root cause (3 layers)

1. **Anthropic harness** — Claude Code's system prompt frames Claude as "primarily software engineering tasks". Personal questions register as tangential → Claude defaults to "I'll be brief".
2. **Plugin per-turn-discipline-prompt.sh hook** — fires on UserPromptSubmit but is SOFT GUIDANCE; Claude can ignore (per the hook's own archived codex caveat: "hook-injects-prompt is SOFT GUIDANCE ONLY. Failure modes: prompt dilution, collision, token bloat, cosmetic emission, subagent drift").
3. **input-routing + depth-estimation skill descriptions** — say "Use on every user message" / "Use at start of multi-step tasks", but Claude must recognize the trigger. For personal topics it skipped both. The "multi-step tasks" phrasing in depth-estimation specifically lets Claude exempt short single-message turns.

## Codex consult (session 019ded1b-9bb8-7ad1-b17c-71c46e4382b5, 2026-05-03)

6 findings. Key insights:

- A+B+C (3-file fix) gives **60-75% probability of materially reducing topic-gating; 20-35% of eliminating**. Soft guidance alone rarely defeats Anthropic's harness prior consistently.
- **Structure universality, not depth universality** — "All required blocks must appear on every turn. Brevity may vary by turn size; omission may not."
- **Hard validator is the missing system-level lever** — post-generation gate that checks for required markers and rejects/repairs if missing. Without it, the harness prior wins on some turns.
- Stronger wording: "TOPIC-GATING FORBIDDEN. Emit the full per-turn discipline blocks for every user input, regardless of topic. For lightweight inputs, keep block content minimal but present."
- Wider sweep needed: any phrasing implying "real work" / "substantive task" / "multi-step" recreates the gate. Found in `depth-estimation/SKILL.md`.

## Fix shipped (4 files this commit, plugin v2.18.0)

| # | File | Change |
|---|---|---|
| F1 | `sutra-defaults.json` | Added top-level `topic_gating` policy with `policy=forbidden`, `structure_universality_not_depth_universality=true`, examples list |
| F2 | `hooks/per-turn-discipline-prompt.sh` | Added imperative anti-topic-gating reminder above the numbered block stack |
| F3 | `skills/input-routing/SKILL.md` | Strengthened description: "NO topic exemptions; personal/research/non-coding/emotional/chitchat all receive identical routing block" |
| F4 | `skills/depth-estimation/SKILL.md` | Broadened from "multi-step tasks" to "every turn — multi-step or single; coding or non-coding; substantive or chitchat. NO topic exemptions" |

## Deferred follow-up — P1, promote-by 2026-05-17

**Hard validator hook** (codex P5). Post-generation gate that inspects draft Claude output for required markers (H-Sutra header, input-routing block, depth block) and rejects/repairs if missing. Analogous to D13 cascade gate but for response shape, not file edits. Without this, fix relies entirely on guidance-layer alignment which leaves a 25-40% miss rate on topic-gating per codex estimate.

Owner: CEO of Sutra (plugin runtime).

## Why this got missed (process lesson)

Same failure mode as v2.14.1 (BLUEPRINT not showing) → v2.15.0 (four disciplines not showing) → v2.15.1 (H-Sutra not showing). All same root cause: imperative phrasing tightening, not enforcement. Each iteration closed one gap, exposed the next.

The dogfood rig (built same session) IS what caught this. Without a fresh T4 sim, the bug would have shipped to fleet untouched.

## Verification

- Manually verified plugin reinstall in fresh sim before/after fix → behavior change deferred until founder re-runs sim with v2.18.0
- Codex consulted before edits (session above)
- All 4 files: parse-checked, content verified
- Cascade entry added to `holding/TODO.md`

## Founder direction worth formalizing

"sutra for anything and everything" deserves a numbered direction in `holding/FOUNDER-DIRECTIONS.md` (suggested: D45). Pending founder confirmation.
