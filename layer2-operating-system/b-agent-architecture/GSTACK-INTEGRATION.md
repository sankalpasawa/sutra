# Sutra × gstack — Skill Integration Map

## Why This Matters

Sutra defines HOW a company should operate. gstack provides the TOOLS to execute it. Every step in Sutra's operating model maps to one or more gstack skills. This means Sutra's process isn't just documentation... it's executable.

## The Operating Model → gstack Mapping

### Phase: SENSE (understand the situation)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Gather context | `/learn` | Review past learnings, search for patterns |
| Check production health | `/canary` | Monitor live app, detect regressions |
| Security check | `/cso` | Infrastructure security audit, threat modeling |
| Performance check | `/benchmark` | Core Web Vitals, load times, bundle sizes |

### Phase: SHAPE (turn fuzzy into clear)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Brainstorm the idea | `/office-hours` | YC-style forcing questions, demand reality check |
| Design the system | `/design-consultation` | Full design system from scratch (colors, type, spacing) |
| Explore visual options | `/design-shotgun` | Generate multiple design variants, compare, pick |
| Review scope | `/plan-ceo-review` | CEO-mode: expand/reduce/hold scope, find 10-star product |

### Phase: DECIDE (commit or kill)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Architecture review | `/plan-eng-review` | Lock in tech stack, data flow, edge cases, test plan |
| Design review | `/plan-design-review` | Rate each design dimension 0-10, fix gaps |
| Full auto-review | `/autoplan` | Runs CEO + design + eng reviews sequentially, auto-decides |
| Get second opinion | `/codex` | Independent review via Codex, adversarial challenge |

### Phase: SPECIFY (define what to build)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Finalize design | `/design-html` | Turn approved mockup into production HTML/CSS |
| Safety boundaries | `/careful` | Destructive command guardrails |
| Scope lock | `/freeze` | Restrict edits to specific directory |

### Phase: EXECUTE (build it)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Investigate bugs | `/investigate` | Systematic root cause analysis, Iron Law: no fix without RCA |
| Code review | `/review` | Pre-landing diff analysis, SQL safety, architecture issues |
| QA test + fix | `/qa` | Test, find bugs, fix them, verify, commit atomically |
| QA report only | `/qa-only` | Structured bug report without code changes |
| Design QA | `/design-review` | Visual audit on live site, fix spacing/hierarchy/slop |
| Browser testing | `/browse` | Headless Chromium: navigate, click, screenshot, verify |
| Full safety mode | `/guard` | /careful + /freeze combined for high-risk work |

### Phase: SHIP (deploy it)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Prepare for merge | `/ship` | Merge base, run tests, review diff, bump version, create PR |
| Deploy + verify | `/land-and-deploy` | Merge PR, wait for CI, canary health check |
| Setup deploy config | `/setup-deploy` | One-time: detect platform, configure deploy automation |
| Post-deploy monitor | `/canary` | Watch live app for 10 min, detect regressions |

### Phase: LEARN (feed back)

| Sutra Step | gstack Skill | What It Does |
|------------|-------------|-------------|
| Update docs | `/document-release` | Sync README/ARCHITECTURE/CHANGELOG with what shipped |
| Weekly retro | `/retro` | Commit history analysis, work patterns, code quality trends |
| Review learnings | `/learn` | Search past learnings, prune stale ones |
| Security retro | `/cso` | Monthly deep scan, trend tracking |

---

## Sutra Workflows as gstack Pipelines

### Workflow 1: New Feature (Depth 3+)

```
/office-hours          → brainstorm, validate the idea
/plan-ceo-review       → scope check: too big? too small?
/design-consultation   → design system (if new project)
/design-shotgun        → visual exploration, pick a direction
/plan-eng-review       → architecture lock-in
/plan-design-review    → design dimension check
  (or /autoplan to run all three reviews automatically)
/design-html           → production HTML from approved mockup
  [BUILD THE FEATURE]
/review                → code review before merge
/qa                    → test + fix + verify
/design-review         → visual QA on live site
/ship                  → prepare PR, bump version
/land-and-deploy       → merge, deploy, verify
/canary                → post-deploy health watch
/document-release      → update docs
/retro                 → weekly review of what shipped
```

### Workflow 2: Bug Fix (Depth 1-2)

```
/investigate           → root cause analysis
  [FIX THE BUG]
/review                → code review
/qa-only               → verify fix, report
/ship                  → PR + merge
/canary                → post-deploy check
```

### Workflow 3: New Client Onboarding

```
/office-hours          → founder brainstorms idea with Sutra
/plan-ceo-review       → scope the product
/design-consultation   → create design system
/plan-eng-review       → lock architecture
/autoplan              → full review pipeline
/setup-deploy          → configure deployment
  [GENERATE OS from Sutra modules]
  [BUILD MVP]
/qa                    → test everything
/ship                  → deploy
/canary                → monitor
/document-release      → docs
```

### Workflow 4: Weekly Company Meeting

```
/retro                 → what shipped, trends, quality
/learn                 → review learnings across sessions
/benchmark             → performance trends
/cso                   → security status (monthly)
/qa-only               → current bug report
```

### Workflow 5: Incident Response

```
/investigate           → root cause (Iron Law)
/careful               → safety mode ON
/freeze                → lock edits to affected module
  [FIX]
/unfreeze              → unlock
/qa                    → verify fix
/review                → code review
/ship                  → deploy fix
/canary                → watch for 10 min
/document-release      → update incident docs
```

---

## A/B Test Integration

When running the Sutra A/B test (depth level comparison):

**Depth 3+ features** use the full pipeline (Workflow 1):
- /office-hours → /autoplan → /design-shotgun → build → /qa → /ship → /canary

**Depth 1-2 features** use the minimal pipeline (Workflow 2):
- /investigate (if bug) or just build → /review → /ship

The A/B test measures whether the full pipeline produces better outcomes (fewer breaks, higher quality) at acceptable speed cost.

---

## Agent ↔ Skill Mapping

| Sutra Agent | Primary gstack Skills |
|-------------|----------------------|
| Sutra OS Agent (adoption) | `/retro`, `/learn` — tracks if clients use the process |
| Sutra Quality Agent (break rate) | `/qa`, `/qa-only`, `/benchmark`, `/canary` |
| Sutra Learner Agent (feedback) | `/learn`, `/document-release`, `/retro` |
| DayFlow Executor Agent (speed) | `/ship`, `/land-and-deploy` |
| DayFlow Quality Agent (zero breaks) | `/qa`, `/investigate`, `/review`, `/cso` |
| DayFlow Reporter Agent (docs) | `/document-release`, `/retro`, `/learn` |

---

## Client-Specific Skill Configs

Each Sutra client may need different skill configurations:

### iOS Apps (e.g., DayFlow)
- `/browse` — limited (Expo Go, not web)
- `/qa` — device testing via screenshots
- `/design-review` — via simulator screenshots
- `/benchmark` — app startup time, not web vitals
- `/setup-deploy` — Expo/TestFlight, not Vercel

### Web Apps (future clients)
- `/browse` — full power (headless Chromium on web app)
- `/qa` — full browser QA, click-through testing
- `/design-review` — live site visual audit
- `/benchmark` — full Core Web Vitals, bundle size
- `/setup-deploy` — Vercel/Netlify deploy
- `/canary` — full post-deploy monitoring

Web apps get MORE gstack coverage because browser testing is native. iOS apps need adapter patterns for device-specific testing.

---

## Depth-Based Skill Activation

The Adaptive Protocol Engine (PROTO-000) depth assessment determines which gstack skills activate. Higher depth = more skills in the pipeline.

| Depth | Active Skills | Rationale |
|-------|--------------|-----------|
| 1 (Surface) | None — direct execution | Skill overhead exceeds task complexity |
| 2 (Considered) | `/review` (optional) | Light review before shipping small changes |
| 3 (Thorough) | `/plan-eng-review`, `/review`, `/qa`, `/ship` | Standard quality pipeline |
| 4 (Rigorous) | + `/plan-ceo-review`, `/plan-design-review`, `/canary`, `/cso` | Full review + post-deploy monitoring |
| 5 (Exhaustive) | + `/autoplan`, `/codex`, `/retro`, `/benchmark` | Full pipeline with independent review and performance tracking |

**Rule**: At Depth 1, no skills fire — the agent executes directly. At Depth 3+, the skill pipeline from "Sutra Workflows as gstack Pipelines" activates progressively.

---

## Minimum Skill Set Per Stage

| Stage | Required Skills | Optional |
|-------|----------------|----------|
| Pre-launch (0 users) | `/office-hours`, `/ship`, `/qa`, `/review` | `/design-consultation`, `/autoplan` |
| Beta (25+ users) | + `/canary`, `/benchmark`, `/cso` | `/retro`, `/learn` |
| Growth (1000+ users) | + `/retro`, `/learn`, `/guard` | `/codex` |
| Scale (10000+ users) | All skills active | — |
