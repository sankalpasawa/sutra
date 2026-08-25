---
name: skill-resolution
description: Use when starting any dispatched unit of work and you must declare which reusable skill governs it — the none / follow / SEARCH / CREATE ladder. Answers "does a skill already exist for this shape of work, and if not, do I look outside or write one?" Invoke at resolve time, before the first mutation. Skip for read-only questions with no unit of work.
---

# Choosing the skill rung

Every dispatched unit declares one of four rungs. The declaration is frozen
into the dispatch record and validated mechanically — a name that does not
exist is refused, `none` without a reason is refused, and SEARCH and CREATE
carry close-time postconditions.

This skill is about picking the RIGHT rung, which no script can check.

```
+-- THE RUNG QUESTION ----------------------------------------------+
|                                                                   |
|   Does reusable guidance already exist for this SHAPE of work?    |
|                                                                   |
|     yes, locally      -> FOLLOW <name>                            |
|     yes, but elsewhere-> SEARCH                                   |
|     no, and it recurs -> CREATE                                   |
|     no, and it is one-off -> none (with a reason)                 |
|                                                                   |
+-------------------------------------------------------------------+
```

## Decide in this order

1. **Look before you declare.** List the child catalog (`.claude/skills/`,
   `holding/skills/`, `.claude/commands/`) then the platform catalog
   (the plugin's `skills/`). Child custody wins on a tie — a company-local
   skill beats a platform one of the same name, per ADR-026.
2. **Match on SHAPE, not topic.** "Reviewing a diff" is a shape. "Reviewing
   the dispatch diff" is an instance. A skill that governs the shape applies
   even when the instance is new.
3. **If nothing fits, ask whether it recurs.** One-off work takes `none`.
   Work you can see arriving again takes CREATE.
4. **SEARCH only when you have reason to believe it exists outside.** A named
   methodology, a documented practice, a published playbook. SEARCH is not a
   synonym for "I didn't look hard enough locally."

## The trap

`none` is the cheapest rung because it asks nothing of you, so it is the one
that quietly eats the ladder. The mechanical counterweight is that it demands
a written reason. The judgment counterweight is this: if you find yourself
writing the same reason twice, that is not a `none` — that is a CREATE you
have been avoiding.

The telemetry watches for exactly that pattern: the same shape of work
declared `none` repeatedly with no SEARCH or CREATE follow-up.

## Over-declaring is also a failure

Naming a weakly-related skill to look compliant is worse than `none`, because
it freezes a false governance record and the mechanism cannot detect it — the
name exists, so validation passes. If the fit is a stretch, it is `none` with
an honest reason.

## What each rung obliges you to

| Rung | Obligation |
|---|---|
| `none` | a reason that would satisfy a reader who disagrees |
| `<name>` | actually follow it — its steps become the skeleton |
| `SEARCH` | resolve to a concrete name + source before close, or the close is refused |
| `CREATE` | a skill file that did not exist at resolve time, or the close is refused |

## Worked example

The unit that built this ladder declared `CREATE`. At close it was refused —
a spec, a CLI change and a test suite are not a skill. The declaration was
either wrong or unfinished. It was unfinished: the missing reusable thing was
guidance for choosing a rung, which is this file. The refusal is what surfaced
that, and it is the intended behaviour, not an obstacle.

Canon: `holding/plans/dispatch-program/SKILL-RESOLUTION.md`. Related:
`workflow-type-resolve` (the Flow station this extends), ADR-026.
