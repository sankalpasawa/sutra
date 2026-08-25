---
name: onboard
description: "Onboard THIS repo as a company — 8-phase intake from raw idea to operating structure"
argument-hint: "<company-name>"
---

# Sutra — Company Onboarding (single-repo, fleet edition)

Onboard the CURRENT repository as company **$ARGUMENTS** (ask for the name if omitted). Everything lands inside this repo — no submodules, no external holding. Save incrementally after every phase; each phase output is one file under `os/company/`.

## The 8 phases

| # | Phase | Output file | What you do |
|---|-------|-------------|-------------|
| 1 | INTAKE | os/company/BRIEF.md | Ask the founder: what is it, for whom, why now, what exists already. Write the brief in their words. |
| 2 | MARKET | os/company/MARKET.md | Research the space: 3-5 comparable products, the wedge, the risk that kills this. |
| 3 | SHAPE | os/company/SHAPE.md | Define the bet: target user, core loop, what is explicitly OUT of scope. |
| 4 | DECIDE | os/company/DECISION.md | One page: proceed / pivot / park, with the reason. Founder signs off before phase 5. |
| 5 | ARCHITECT | os/company/ARCHITECTURE.md | System shape: stack, data, deploy target, the 3 riskiest technical calls. |
| 6 | CONFIGURE | os/SUTRA-CONFIG.md | Tier, depth range, enforcement level, test command (also set `test_command` in .claude/sutra-project.json to arm the git gates). |
| 7 | DEPLOY | — | First runnable slice committed + pushed. Verify before claiming done. |
| 8 | ACTIVATE | os/TODO.md | Seed the real backlog (Impact + Effort columns). From here the founder is CEO; Sutra is the operating system. |

## Rules

- Run `/core:start --profile company` first if `os/` does not exist.
- One phase at a time; show the file after writing it; founder can redirect at any phase boundary.
- Phase 4 is a hard gate: do not architect before the decision is recorded.
- Apply the full per-turn governance stack throughout.
