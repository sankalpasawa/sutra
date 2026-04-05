# Sutra — Abstraction Architecture

## The Three Questions

### 1. What layers make Sutra/Asawa better?

Current hierarchy (HIERARCHY.md) has 6 levels. But the ABSTRACTION isn't just about nesting.
The real question: what changes at different rates?

Applying shearing layers (from DayFlow's PRODUCT-KNOWLEDGE-SYSTEM.md):

| Layer | Changes Every... | What Lives Here | Example |
|-------|-----------------|-----------------|---------|
| **Doctrine** | Years / never | Why Sutra exists. The 5 meta-principles. | "Dynamic, Flexible, Scalable, Simple, Nuanced" |
| **Principles** | Months | How humans and AI work together. P1-P9. | "Direction, Not Instruction" |
| **Protocols** | Weeks | Enforceable rules with hooks. PROTO-001-010. | "Narration is not artifact" |
| **Engines** | Per-cycle | Runtime intelligence that self-calibrates. | Estimation multipliers improve every cycle |
| **Processes** | Per-task | How a specific task gets done. Generated on the fly. | "How to deploy to edge functions" |
| **Config** | Per-company | Company-specific settings, tier, skills. | Maze is Tier 2 with 14 skills |

Things that change slowly should be FEW and STABLE.
Things that change fast should be MANY and DISPOSABLE.

### 2. Shocks and Diversity

A system that only works for B2C web apps on Next.js isn't resilient.
Sutra needs to handle SHOCKS — unexpected situations:

| Shock Type | How Sutra Handles It | Current Strength |
|-----------|---------------------|-----------------|
| New product type (B2B, AI, CLI) | Layer 3 modules adapt | WEAK — only B2C template exists |
| New tech stack (mobile, Python, Rust) | Engines are stack-agnostic | MEDIUM — tested on Next.js + Expo |
| New team size (1 → 5 → 50) | Tier system scales process depth | MEDIUM — only Tier 1-2 tested |
| New domain (finance, health, education) | Process Generation creates domain processes | UNTESTED |
| Founder leaves (someone else takes over) | CLAUDE.md + docs should be self-sufficient | MEDIUM — tested with parallel agents |
| AI model changes (Claude → different LLM) | Prompts are model-agnostic | WEAK — untested |

The DIVERSITY model: by testing on 4 companies (content, productivity, AI, wedding), we stress-test Sutra across product types. Each new company is a "shock" that reveals what Sutra assumed but shouldn't have.

### 3. Deployment Modes — Simple vs Full

The problem: daily work needs the Quick Reference (36 lines). But sometimes you need the full 500-line engine spec. How to have both?

**Telescoping depth**: the same system at different zoom levels.

```
ZOOM 0: Quick Reference (36 lines)
  "Estimate → pick depth → build → log"
  
ZOOM 1: Engine summaries (~50 lines each)
  What the engine does, parameters, scoring model, output format
  
ZOOM 2: Full engine specs (~500 lines each)
  Complete spec with all heuristics, calibration data, examples
  
ZOOM 3: Source code + evolution history
  Gap reports, calibration logs, protocol evolution log
```

A Tier 1 solo founder never goes past ZOOM 0.
A Tier 2 team lead reads ZOOM 1 when something unexpected happens.
A Sutra developer reads ZOOM 2-3 when modifying the engine.

**Implementation**: the Quick Reference IS Zoom 0. The engine files are Zoom 2. What's missing is Zoom 1 (summaries) — but that's the CLAUDE.md "Engines (Sutra v1.3)" section we already wrote for Maze. So it's already there.

## What This Means for External Founders

An external founder using Sutra sees:

```
DAY 1: Quick Reference + CLAUDE.md (Zoom 0)
  → build features, run engines, ship

WEEK 1: When something doesn't fit
  → read engine summaries in CLAUDE.md (Zoom 1)
  → generate a process for the new situation

MONTH 1: When customizing Sutra for their domain
  → read full engine specs (Zoom 2)
  → modify calibration, add domain-specific heuristics

NEVER: Source code / evolution history
  → that's Sutra's internal concern
```

This is how an OS should work. You don't read the Linux kernel source to use Linux.
