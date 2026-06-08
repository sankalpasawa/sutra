---
name: founder-360-review
description: Use when a founder asks for retrospective feedback on a fixed time window — last week, last month, last quarter, or "since X". Triggers include "what have I done in the last X", "where did my time go", "how am I managing my energy", "give me 360 feedback", "neutral feedback on me", "am I burning out", "review my abstraction levels", "holistic mirror". Different from a status report — produces evidence-anchored neutral mirror across eight founder-mind angles, not a release note.
---

# Founder 360 Review

## Overview

A founder retro is not a status report. Status counts ships. A 360 review mirrors the founder — time, energy, abstraction, learning, decision quality, durability, identity, reflection.

**Iron law: no fabrication.** Every observation traces to a commit, file, D-tag, or memory entry. Gaps are named, not filled.

## When to Use

- Founder asks "what have I done in the last [window]"
- Founder asks for energy / time / abstraction / learning review
- Founder uses words "neutral", "honest", "360", "mirror"
- End of week / month / quarter / milestone

**When NOT to use:**
- Founder wants project status (use `/retro` or `/gsd-session-report`)
- Founder wants peer code review (use `/codex-sutra` or `superpowers:code-reviewer`)
- Founder wants help debugging a feeling (this is data, not therapy)

## Mindset (read before delivery)

1. **Operator's mirror.** Show what a third-party CTO sees, not what the founder hopes.
2. **Patterns over events.** Name the repeating shape, not one bad day.
3. **Forward-leaning.** Feedback is fuel for next window, not penalty for last.
4. **Compassionate honesty.** No flattery. No shame. No hedging.
5. **Evidence anchored.** Commits, files, D-tags, memory entries. Gaps named, never filled.

## Framework: 8 Angles

| # | Angle | Question | Evidence source |
|---|-------|----------|-----------------|
| 1 | Time Allocation | Where did the hours physically go? | git log + dir touch counts |
| 2 | Energy Profile | When were peaks vs burns? | commits-per-hour, late-night clusters |
| 3 | Abstraction Discipline | Code vs schema vs charter vs strategy — balanced? | dir mix (hooks vs research vs charter) |
| 4 | Learning Velocity | What new concepts crystallized? | new D-tags, protocols, memory entries |
| 5 | Decision Quality | What got ratified? Reversed? | D-tags, codex consults, renumberings |
| 6 | Output Durability | What survives the window? | shipped vs archived, L0 vs L2 |
| 7 | Identity Coherence | Hat-switches: how many, how reconciled? | dirs spanned vs founder-stated focus |
| 8 | Reflection Cadence | Pause-and-think moments? | retro/checkpoint/RESUME files |

## Procedure

1. **Set window.** Default = last 30 days. Else founder-specified.
2. **Gather raw signals (parallel bash):**
   - `git log --since="<date>" --pretty=format:"%h|%ad|%s" --date=short`
   - Top dir touch counts: `git log --since=... --name-only --pretty=format: | awk -F/ '{print $1"/"$2}' | sort | uniq -c | sort -rn`
   - Commits-per-day-hour for energy: `git log --since=... --date=format:"%Y-%m-%d %H" | uniq -c`
   - Recent D-tags: `grep "^## D[0-9]" holding/FOUNDER-DIRECTIONS.md | tail -20`
   - Memory deltas: list `memory/*.md` mtimes within window
3. **Score each angle low / mid / high** with one-line evidence row.
4. **Write one to two sentence neutral observation per angle.** Third person about the founder.
5. **Identify 2 patterns:** one strength, one drag. No more, no less.
6. **Recommend 2 changes** for next window. Format as Impact + Effort table per CLAUDE.md table-shape rule.
7. **Output ASCII table** + boxed decisions. No unicode box-drawing.

## Output Shape

```
+-- Scorecard --------------------------------------+
| #  Angle                    Score   1-line cite   |
| 1  Time Allocation          HIGH    <evidence>    |
| 2  Energy Profile           MID     <evidence>    |
| ...                                                |
+----------------------------------------------------+

8 observations (one per angle, 1-2 sentences each)

Two patterns: one strength, one drag.

Two changes for next window (Impact + Effort table).
```

## Common Mistakes

- **Status-report drift.** Listing what shipped, not mirroring the founder. If output reads like a release note, restart.
- **Flattery.** "You shipped a lot!" is not feedback. Specificity or silence.
- **Numbers without meaning.** "250 commits" is data; "250 commits across 14 directions = abstraction-heavy month" is feedback.
- **Filling gaps.** If energy data is sparse, say "energy data sparse — need timesheets / mood log". Do not invent feelings from timestamps.
- **Recommendation overflow.** More than 2 changes = founder leaves overwhelmed, not directed.
- **Second-person without invitation.** Default to third person; switch to "you" only if founder explicitly asks for a directly-addressed mirror.

## Red Flags — STOP

- Listing achievements without observation
- Inventing energy/mood data from commit timestamps alone (timestamps show *when committed*, not *when worked* or *how felt*)
- More than 2 recommendations
- Any sentence that starts "You should..." without a cited piece of evidence in the same sentence

## TDD Status

This skill is **v0.1**. Pressure-test scenarios (RED phase per `superpowers:writing-skills`) are deferred to first real founder run. After delivery, capture rationalizations the agent uses, fold counter-rules into the Common Mistakes / Red Flags tables. Re-test until bulletproof.
