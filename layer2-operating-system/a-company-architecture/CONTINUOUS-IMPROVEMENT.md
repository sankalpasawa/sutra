# Sutra — Continuous Improvement Architecture

## How Findings Flow Through the System

Every session, for every company, generates findings. Bugs, learnings, protocol gaps, design decisions, performance issues. These findings must not be lost. They must flow to the right place and get picked up.

## The Flow

```
SESSION produces a finding
  ↓
CLASSIFY: Is this a...
  ├── Bug (code)        → company's TODO.md [P0/P1/P2]
  ├── Bug (process)     → feedback-to-sutra/ (Sutra needs to improve)
  ├── Learning          → feedback-to-sutra/ (useful for future)
  ├── Protocol gap      → feedback-to-sutra/ + immediate Sutra doc update
  ├── Design decision   → company's DESIGN.md or OS file
  ├── New TODO          → company's TODO.md
  └── Cross-company     → asawa-inc/holding/ (Daily Pulse or TODO)
```

## Where Findings Live

| Finding Type | Where It Goes | Who Picks It Up | When |
|-------------|---------------|----------------|------|
| Code bug (this company) | `{company}/TODO.md` | Next session for this company | Next feature or immediately if P0 |
| Process bug (Sutra) | `{company}/feedback-to-sutra/` | Next Sutra session | Weekly batch or immediately if critical |
| New protocol | Sutra doc (immediate) + `ENFORCEMENT.md` | All future sessions | Immediately (hard-enforced) |
| Performance finding | `{company}/METRICS.md` + TODO | Next session | Next feature |
| Design debt | `{company}/TODO.md` [P1-Design] | Next design-focused session | When design work is scheduled |
| Security finding | `{company}/TODO.md` [P0-Security] | Immediately | Cannot ship until resolved |
| Cross-company learning | `asawa-inc/holding/LEARNINGS.md` | Sutra session | Next version update |

## Automatic Finding Generation

Every session automatically generates findings at these moments:

### After every feature ships
```
1. Log to METRICS.md: ship time, breaks, quality
2. If breaks > 0: create TODO entry [P0-Bug] + feedback-to-sutra/
3. If ship time > 2x average: create feedback-to-sutra/ (process overhead?)
4. If any protocol was violated: log to ENFORCEMENT violations
5. Run /gsd:session-report → captures session findings
```

### After every bug fix
```
1. Root cause analysis: was this preventable?
2. If yes: what sensor/check was missing? → feedback-to-sutra/
3. If no: was it a novel failure? → learning → feedback-to-sutra/
4. Add regression test to TODO [P1-Quality]
```

### After every session ends
```
1. /gsd:pause-work → preserves state
2. Any unfinished work → TODO.md with context
3. Any findings not yet written → write them before closing
4. Compliance check: did we follow the protocols?
```

### Weekly (Sutra session)
```
1. Read all feedback-to-sutra/ across all companies
2. Batch findings by type:
   ├── Protocol gaps → update Sutra docs
   ├── Template gaps → update modules
   ├── Process overhead → simplify
   └── New patterns → add to knowledge base
3. If 5+ changes accumulated → publish new Sutra version
4. Write update notices to existing client folders
5. Update holding TODO with cross-company items
```

## The TODO Architecture

Each company has a TODO.md with this structure:

```markdown
# {Company} — TODO

## P0: Critical (must fix before next feature)
- [ ] [Bug] {description} — found {date}
- [ ] [Security] {description} — found {date}

## P1: High (fix this week)
- [ ] [Feature] {next feature from roadmap}
- [ ] [Quality] {regression test needed}
- [ ] [Design] {design debt item}

## P2: Medium (fix this month)
- [ ] [Feature] {backlog item}
- [ ] [Improvement] {nice to have}

## P3: Low (someday)
- [ ] [Idea] {captured for future}
```

**Rules:**
- Bugs found during a session → immediately added to TODO with priority
- P0 items block shipping. Cannot deploy with open P0s.
- Items are never deleted, only moved to DONE section with date
- Each item includes: when found, who/what found it, context

## The Feedback Architecture

Each company has `feedback-to-sutra/` with files like:

```
feedback-to-sutra/
├── 2026-04-03-landing-page-default.md
├── 2026-04-03-web-design-in-code.md
├── 2026-04-04-content-quality-metrics.md
└── ...
```

Each file:
```markdown
# {Title}

**Date**: {YYYY-MM-DD}
**Company**: {company name}
**Type**: protocol-gap | learning | process-overhead | new-pattern
**Severity**: critical | normal | minor

## What Happened
{description}

## What Was Missing in Sutra
{what should have been there}

## Suggested Change
{concrete suggestion}

## Status
PENDING → REVIEWED → INCORPORATED (in v{X}) | REJECTED (reason)
```

## Depth Integration

Improvement initiatives are assessed at depth like any task (PROTO-000). The depth determines how much investigation and process surrounds a finding.

| Depth | Improvement Behavior |
|-------|---------------------|
| 1 (Surface) | Log finding to TODO.md. No investigation. |
| 2 (Considered) | Log finding + classify type. Route to correct destination. |
| 3 (Thorough) | Full classification, root cause analysis for bugs, feedback-to-sutra/ for process issues. |
| 4 (Rigorous) | Full flow + cross-company check ("does this apply elsewhere?"). Sutra doc update if protocol gap. |
| 5 (Exhaustive) | Full flow + systemic review + version bump consideration + update notices to all clients. |

**Rule**: Not every finding warrants a full investigation. Depth 1-2 captures and routes; Depth 3+ investigates and improves.

---

## Cross-Company Improvement

When Sutra learns from Company A, it checks: does this apply to Company B?

```
Company A discovers: "design-in-code is faster for web MVPs"
  ↓
Sutra evaluates:
  - Is this specific to Company A? (no, it's platform-specific)
  - Which companies share this platform? (all web companies)
  - Update: add to web product template
  ↓
Existing web companies get update notice
Future web companies get it by default
```

This is how the system gets smarter with every company.
