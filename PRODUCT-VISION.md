# Sutra — Holding Company as a Service

## The Vision

A founder runs one command and gets:
1. A holding company structure (governance, portfolio, infrastructure)
2. Sutra OS installed (protocols, engines, onboarding)
3. The ability to onboard their first company immediately
4. An evolution loop that improves everything through use

They don't need to design principles. They don't need to build enforcement hooks. They don't need to figure out hierarchy. Sutra provides all of it — and it improves based on EVERY founder who uses it.

## What Gets Deployed

### Tier 1: Solo Founder (one holding + first company)
```
my-holding/
├── holding/
│   ├── PRINCIPLES.md (starter set — 5 principles, not 10)
│   ├── HIERARCHY.md (3 levels: holding → OS → company)
│   ├── TODO.md
│   └── os/ (Sutra engines for the holding itself)
├── sutra/ (OS — deployed as read-only reference)
└── my-first-company/ (scaffolded, ready to build)
```
Time: 30 minutes. Cost: $0.

### Tier 2: Growing Portfolio (2-5 companies)
Everything in Tier 1, plus:
- Boundary enforcement between companies
- Cross-company evolution loop
- Shared infrastructure (AI providers, deploy config)
- Daily Pulse across portfolio

### Tier 3: Scaled (5+ companies)
Everything in Tier 2, plus:
- Full governance framework (10 principles, enforcement hooks)
- Portfolio office (resource allocation, health monitoring)
- Custom protocol creation
- Multi-founder support (different people running different companies)

## What Sutra Learns From Every Holding Company

This is the network effect:

```
Founder A builds 3 companies through Sutra
  → gaps found, protocols improved
  
Founder B gets Sutra with Founder A's improvements already baked in
  → starts from a better baseline
  → finds NEW gaps, protocols improve further

Founder C gets improvements from both A and B
  → (cycle continues, each founder starts stronger)
```

Every holding company makes Sutra better for ALL holding companies.
This is Sutra's real moat — accumulated operational intelligence from real company building.

## What's Needed to Make This Real

### Already Built (from Asawa's evolution):
- Governance principles (P1-P10) — generalizable
- Enforcement framework — generalizable
- Hierarchy with cascade rules — generalizable
- Engines (estimation, routing, review) — generalizable
- Onboarding (8-phase + Tier 1 quick) — generalizable
- Boundary enforcement hooks — generalizable
- Evolution protocol — generalizable

### Needs Generalization:
| Component | Currently | Needs |
|-----------|-----------|-------|
| Principles | Asawa-specific (P9 "Direction Not Instruction") | Some are universal, some are Asawa-specific. Split them. |
| Founder Directions | Sankalp's behavioral preferences | Template: empty, founder fills in as they go |
| Holding structure | Hardcoded paths (holding/, sutra/) | Configurable via init script |
| Daily Pulse | Reads from specific submodule paths | Generic: scan for company dirs |
| Evolution state | In holding/evolution/ | Template: created during init |

### The Product Surface:
1. **CLI**: `npx sutra-os init --holding` → scaffolds everything
2. **MCP Server**: Sutra runs as a service, founder's Claude Code connects to it
3. **GitHub Template**: fork and customize

## What This Means for Asawa

Asawa is the FIRST customer. The reference implementation.
Every protocol we build, we ask: "Would this work for another founder's holding company?"
If yes: it goes in Sutra (generalizable).
If no: it stays in Asawa (specific to us).

This is why the separation matters:
- Asawa-specific: Founder Directions (Sankalp's preferences), specific company configs
- Sutra-universal: Principles framework, engines, enforcement, hierarchy pattern
