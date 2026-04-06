# Sutra — Unified Skill Catalog

## What This Is

Every Sutra client has access to two skill systems: **gstack** (32 skills) and **GSD** (57 skills). Together, 89 skills. This catalog maps every skill to when it's used, organized by what you're trying to DO, not by which tool it comes from.

A founder building a company should never think "which tool system do I use?" They think "I need to plan this feature" and the catalog tells them: use `/gsd:discuss-phase` for decisions, then `/gsd:plan-phase` for the plan, then `/office-hours` if the idea needs brainstorming first.

---

## How to Read This

- **GSD skills** are prefixed with `/gsd:` (e.g., `/gsd:plan-phase`)
- **gstack skills** are prefixed with `/` only (e.g., `/office-hours`)
- **When both exist for the same job**, the catalog says which to prefer and why

---

## 1. STARTING A NEW PROJECT

*"I have an idea and want to build it."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Brainstorm the idea | `/office-hours` | YC-style forcing questions. Is this worth building? |
| Initialize the project | `/gsd:new-project` | Creates PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md in `.planning/` |
| Map existing codebase | `/gsd:map-codebase` | Analyze brownfield project before adding features |
| Design the system | `/design-consultation` | Full design system (colors, type, spacing, components) |
| Set up deployment | `/setup-deploy` | Detect platform, configure auto-deploy to CLAUDE.md |

**Recommended flow**:
```
/office-hours → validate idea
/gsd:new-project → create project structure + roadmap
/design-consultation → create DESIGN.md
/setup-deploy → configure deployment
```

---

## 2. PLANNING A FEATURE

*"I know what to build. Now I need a plan."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Scope check (too big? too small?) | `/plan-ceo-review` | CEO-mode scope review. Expand or reduce. |
| Gather context + lock decisions | `/gsd:discuss-phase` | Extracts gray areas, locks implementation decisions into CONTEXT.md |
| Research approaches | `/gsd:research-phase` | Investigates ecosystem, patterns, pitfalls. Creates RESEARCH.md |
| Create the plan | `/gsd:plan-phase` | Generates executable PLAN.md with tasks, verified by plan-checker |
| Architecture review | `/plan-eng-review` | Lock tech stack, data flow, edge cases, test plan |
| Design review (pre-build) | `/plan-design-review` | Rate design dimensions 0-10, fix gaps |
| Auto-review all three | `/autoplan` | Runs CEO + design + eng reviews sequentially |
| UI design contract | `/gsd:ui-phase` | Creates UI-SPEC.md with component specs, layout rules |
| Explore visual options | `/design-shotgun` | Generate multiple design variants, compare, pick |
| Finalize to HTML | `/design-html` | Turn approved mockup into production HTML/CSS |
| Get second opinion | `/codex` | Independent review via OpenAI Codex |
| Cross-AI review | `/gsd:review` | Invokes external AIs (Gemini, Claude, Codex) to review plans |

**When to use GSD planning vs gstack planning**:
- `/gsd:plan-phase` → when you want an executable task list with dependency ordering and wave execution
- `/autoplan` → when you want high-level scope/design/architecture review before planning
- **Best combo**: `/autoplan` first (validates the idea), then `/gsd:plan-phase` (creates executable plan)

---

## 3. BUILDING / EXECUTING

*"Plan is ready. Time to code."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Execute the plan | `/gsd:execute-phase` | Runs all tasks in parallel waves via subagents |
| Quick ad-hoc task | `/gsd:quick` | Small task with GSD guarantees (atomic commits, state tracking) |
| Trivial change | `/gsd:fast` | One-liner fix. No planning overhead. |
| Auto-route next step | `/gsd:next` | Detects where you are, invokes the right command |
| Run autonomously | `/gsd:autonomous` | Runs all remaining phases unattended. Pauses for blockers. |
| Freeform dispatch | `/gsd:do` | Routes any text to the right GSD command |

**When to use GSD execution vs manual coding**:
- `/gsd:execute-phase` → multi-file features with dependencies between tasks
- `/gsd:fast` → typo fix, config change, small refactor
- Manual coding → when you know exactly what to change and it's 1-2 files

---

## 4. DEBUGGING

*"Something's broken."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Investigate root cause | `/investigate` | gstack systematic debugging. Iron Law: no fix without root cause. |
| Debug with persistence | `/gsd:debug` | Persists debug state across sessions (.planning/debug/) |
| Post-mortem | `/gsd:forensics` | Analyze why a workflow or build failed |

**When to use which**:
- `/investigate` → single-session bugs. Fast, thorough, fixes inline.
- `/gsd:debug` → complex bugs that span multiple sessions. State persists.

---

## 5. TESTING & QA

*"Does it work?"*

| Step | Skill | What It Does |
|------|-------|-------------|
| Full QA + fix | `/qa` | Test, find bugs, fix them, verify, commit atomically |
| QA report only | `/qa-only` | Structured bug report without code changes |
| Verify specific features | `/gsd:verify-work` | Conversational UAT per phase. Generates gap-closure plans. |
| Visual QA on live site | `/design-review` | Find visual issues, fix spacing/hierarchy, before/after screenshots |
| UI audit (code-level) | `/gsd:ui-review` | 6-pillar visual audit of frontend code. Graded assessment. |
| Browser testing | `/browse` | Headless Chromium: navigate, click, fill forms, screenshot, assert |
| Audit UAT coverage | `/gsd:audit-uat` | Find phases missing user acceptance testing |
| Add tests | `/gsd:add-tests` | Generate test cases for existing code |
| Performance check | `/benchmark` | Core Web Vitals, load times, bundle sizes, regression detection |

**When to use which**:
- `/qa` → after shipping a feature to a live URL. Tests in browser, fixes bugs, commits.
- `/gsd:verify-work` → after executing a GSD phase. Validates against plan acceptance criteria.
- `/design-review` → pixel-level visual polish. Spacing, alignment, hierarchy.
- `/gsd:ui-review` → code-level UI audit. Accessibility, responsive, component structure.

---

## 6. CODE REVIEW

*"Review before merge."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Pre-landing review | `/review` | gstack diff analysis. SQL safety, architecture issues. |
| Cross-AI review | `/gsd:review` | External AIs independently review your plans/code |
| Second opinion | `/codex` | OpenAI Codex adversarial review |
| Validate phase plan | `/gsd:validate-phase` | Check plan quality and completeness |

---

## 7. SHIPPING & DEPLOYMENT

*"Get it live."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Prepare PR | `/ship` | gstack: merge base, run tests, bump version, create PR |
| Ship GSD phase | `/gsd:ship` | GSD: push branch, create PR with auto-description |
| Create clean PR branch | `/gsd:pr-branch` | Strip .planning/ commits for clean PR |
| Land + deploy | `/land-and-deploy` | Merge PR, wait for CI, verify production health |
| Post-deploy monitor | `/canary` | Watch live app for 10 min. Console errors, perf regression, page failures. |

**When to use which**:
- `/gsd:ship` → when working within GSD's phase system (has planning artifacts)
- `/ship` → standalone shipping. Works with any branch/diff.
- Always run `/canary` after deploy.

---

## 8. DOCUMENTATION & LEARNING

*"Keep docs in sync. Learn from what happened."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Update docs after ship | `/document-release` | Sync README/ARCHITECTURE/CHANGELOG with what shipped |
| GSD docs update | `/gsd:docs-update` | Verified documentation generation |
| Weekly retro | `/retro` | Commit history analysis, work patterns, quality trends |
| Session report | `/gsd:session-report` | Summary of what happened this session |
| Milestone summary | `/gsd:milestone-summary` | Comprehensive milestone completion report |
| Review learnings | `/learn` | Search past learnings, prune stale ones |
| Complete milestone | `/gsd:complete-milestone` | Archive milestone, tag release |

---

## 9. SESSION MANAGEMENT

*"Pause, resume, track progress across sessions."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Check progress | `/gsd:progress` | Where am I? What's next? Routes to next action. |
| Project stats | `/gsd:stats` | Phase progress, git stats, timeline |
| Pause session | `/gsd:pause-work` | Creates .continue-here.md handoff file |
| Resume session | `/gsd:resume-work` | Restores context from previous session |
| Persistent thread | `/gsd:thread` | Cross-session context for ongoing work |
| Command center | `/gsd:manager` | Multi-phase dashboard, dispatch work |
| Capture idea | `/gsd:note` | Zero-friction idea capture |
| Plant seed | `/gsd:plant-seed` | Forward-looking idea with trigger conditions |
| Add to backlog | `/gsd:add-backlog` | Park ideas for later |
| Review backlog | `/gsd:review-backlog` | Promote backlog items to roadmap |

---

## 10. SAFETY & SECURITY

*"Don't break production."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Safety mode | `/careful` | Warns before destructive commands (rm -rf, DROP, force push) |
| Lock directory scope | `/freeze` | Block edits outside allowed path |
| Unlock scope | `/unfreeze` | Remove edit restriction |
| Full safety | `/guard` | /careful + /freeze combined |
| Security audit | `/cso` | OWASP Top 10, secrets scanning, supply chain, threat modeling |
| Security enforcement | `/gsd:secure-phase` | GSD security with threat modeling per phase |

---

## 11. WORKSTREAM & WORKSPACE MANAGEMENT

*"Multiple things in flight."*

| Step | Skill | What It Does |
|------|-------|-------------|
| Create workstream | `/gsd:workstreams create` | Namespaced parallel work tracks |
| Switch workstream | `/gsd:workstreams switch` | Context-switch between work tracks |
| List workstreams | `/gsd:workstreams list` | See all active workstreams |
| Complete workstream | `/gsd:workstreams complete` | Finish and merge a workstream |
| Create workspace | `/gsd:new-workspace` | Isolated workspace with repo copies |
| List workspaces | `/gsd:list-workspaces` | See all workspaces |
| Remove workspace | `/gsd:remove-workspace` | Clean up workspace |

---

## Quick Decision: GSD or gstack?

| Situation | Use | Why |
|-----------|-----|-----|
| Building a feature from scratch with multiple phases | **GSD** (`/gsd:new-project` → phases) | GSD excels at multi-phase orchestration with state tracking |
| Quick bug fix or small change | **gstack** (`/investigate` → `/qa` → `/ship`) | Faster, no planning overhead |
| Design exploration | **gstack** (`/design-shotgun` → `/design-html`) | gstack has richer design tools |
| Browser testing | **gstack** (`/qa`, `/browse`) | GSD has no browser testing |
| Autonomous long-running build | **GSD** (`/gsd:autonomous`) | GSD has state machine autonomy with crash recovery |
| Code review | **Either** | `/review` (gstack) for diff review, `/gsd:review` for cross-AI review |
| Post-deploy monitoring | **gstack** (`/canary`) | GSD has no post-deploy monitoring |
| Session continuity across days | **GSD** (`/gsd:pause-work`, `/gsd:resume-work`) | GSD has explicit handoff with state files |
| Security audit | **Both** | `/cso` (gstack) for infrastructure, `/gsd:secure-phase` for per-feature |
| Performance tracking | **gstack** (`/benchmark`) | GSD has no performance benchmarking |

---

## Sutra Phase → Skill Mapping (Complete)

| Sutra Phase | gstack Skills | GSD Skills | Recommended Flow |
|-------------|---------------|------------|-----------------|
| **SENSE** | `/learn`, `/canary`, `/cso`, `/benchmark` | `/gsd:progress`, `/gsd:stats` | Start with `/gsd:progress` (where are we?), then `/canary` (is prod healthy?) |
| **SHAPE** | `/office-hours`, `/design-consultation`, `/design-shotgun`, `/plan-ceo-review` | `/gsd:discuss-phase`, `/gsd:research-phase` | `/office-hours` → `/gsd:discuss-phase` → `/gsd:research-phase` |
| **DECIDE** | `/plan-eng-review`, `/plan-design-review`, `/autoplan`, `/codex` | `/gsd:review`, `/gsd:validate-phase` | `/autoplan` (or manual reviews) → `/gsd:validate-phase` |
| **SPECIFY** | `/design-html`, `/careful`, `/freeze` | `/gsd:plan-phase`, `/gsd:ui-phase` | `/gsd:plan-phase` → `/gsd:ui-phase` (if frontend) |
| **EXECUTE** | `/investigate`, `/review`, `/qa`, `/design-review`, `/browse` | `/gsd:execute-phase`, `/gsd:quick`, `/gsd:fast`, `/gsd:autonomous` | `/gsd:execute-phase` (or `/gsd:autonomous` for hands-off) |
| **SHIP** | `/ship`, `/land-and-deploy`, `/canary` | `/gsd:ship`, `/gsd:pr-branch` | `/gsd:ship` (or `/ship`) → `/land-and-deploy` → `/canary` |
| **LEARN** | `/document-release`, `/retro`, `/learn` | `/gsd:session-report`, `/gsd:milestone-summary`, `/gsd:complete-milestone` | `/document-release` → `/retro` → `/gsd:complete-milestone` |

---

---

## Skill Tiers (Progressive Activation)

Skills activate based on company maturity, not loaded all at once.

### Tier 1: Foundation (every company, day 1)
| Skill | Purpose |
|-------|---------|
| `/office-hours` | Brainstorm and validate ideas |
| `/gsd:plan-phase` | Plan features |
| `/gsd:execute-phase` | Execute plans |
| `/ship` | Deploy code |
| `/investigate` | Debug bugs |
| `/gsd:progress` | Check where you are |
| `/gsd:pause-work` | Save context when stopping |
| `/gsd:resume-work` | Restore context when continuing |

**8 skills. Enough to build and ship.**

### Tier 2: Quality (when external users depend on it)
All Tier 1, plus:
| Skill | Purpose |
|-------|---------|
| `/qa` | Test and fix bugs |
| `/review` | Code review before merge |
| `/canary` | Post-deploy health check |
| `/design-review` | Visual QA |
| `/gsd:verify-work` | UAT verification |
| `/gsd:add-tests` | Generate test suites |

**+6 skills = 14 total.**

### Tier 3: Scale (team, revenue, or regulation)
All Tier 2, plus:
| Skill | Purpose |
|-------|---------|
| `/autoplan` | Full CEO + design + eng review pipeline |
| `/retro` | Weekly engineering retrospective |
| `/cso` | Security audit |
| `/design-consultation` | Full design system |
| `/gsd:autonomous` | Run phases without human intervention |
| `/gsd:manager` | Multi-phase command center |
| `/codex` | Cross-AI second opinion |

**+7 skills = 21 total.**

### Specialist (fetched on demand, not installed by default)
| Skill | When Fetched |
|-------|-------------|
| `/benchmark` | Performance work |
| `/browse`, `/gstack` | QA testing with browser |
| `/design-shotgun` | Design exploration |
| `/design-html` | Production HTML from mockups |
| `/land-and-deploy` | CI/CD setup |
| `/setup-browser-cookies` | Auth testing |
| `/connect-chrome` | Live browser debugging |
| Other GSD skills | As needed per workflow |

### How Companies Get Skills

**During Onboarding (Phase 6: CONFIGURE):**
Sutra reads the company's tier and product type, then:
1. Installs Tier 1 skills (always)
2. If Tier 2+: adds quality skills
3. If Tier 3: adds scale skills
4. Writes available skills to company CLAUDE.md "Skill Routing" section

**During Upgrade:**
When a company's tier changes (e.g., first external user -> Tier 2):
1. Sutra notifies via feedback-from-sutra/
2. Company CLAUDE.md is updated with new skills
3. New hooks/processes associated with those skills are installed

**On Demand:**
Any company can request a specialist skill. These are session-only (not permanently installed) unless the company requests it.

### Product Type Skill Packs

| Product Type | Additional Skills |
|-------------|-------------------|
| **Web app (Next.js)** | `/browse`, `/gstack`, `/qa`, `/benchmark` |
| **Mobile app (Expo)** | Design QA via screenshots, no browser skills |
| **CLI tool** | `/gsd:add-tests` (unit tests critical), no design skills |
| **B2B SaaS** | `/cso` (security from day 1), `/retro` (team cadence) |
| **Content platform** | `/design-shotgun` (visual exploration), `/canary` (uptime critical) |

### Integration with Existing Systems

- **Adaptive Protocol Engine**: When selecting depth, the engine checks which skills are available. If a Level 3 depth needs `/autoplan` but the company is Tier 1, it falls back to Level 2.
- **SUTRA-CONFIG.md**: Each company lists their installed skill tier and any specialist skills.
- **Process Generation**: When a new process is generated, it can reference skills by checking what's available.

---

## Skill Acquisition Process

When a company needs a capability that no existing skill covers, Sutra finds, evaluates, and installs one.

### When This Triggers

- Agent encounters a task with no matching skill in this catalog
- Founder requests a specific capability ("I need performance benchmarking")
- A gap report identifies a missing tool

### The Process

```
NEED -> SEARCH -> EVALUATE -> INSTALL -> CONFIGURE -> VERIFY -> CATALOG
```

1. **NEED**: Identify what capability is missing. Be specific.
2. **SEARCH**: Look for existing solutions (Claude Code plugins, npm packages, MCP servers, built-in skills, open source tools).
3. **EVALUATE**: Before installing, check: Does it solve the specific need? Is it maintained (last commit < 6 months)? Security implications? Cost? Overlap with existing skills?
4. **INSTALL**: Based on type (plugin, npm package, MCP server, shell tool, custom skill in `.claude/commands/`).
5. **CONFIGURE**: Add to company's SUTRA-CONFIG.md specialist skills list. Set permissions and env vars.
6. **VERIFY**: Run the skill on a real task. Does it solve the original need? Does it break anything?
7. **CATALOG**: Add to this file under the right situation category. Note which company first used it. If reusable: add to appropriate tier.

---

## For New Companies

When Sutra onboards a new client, include this in the OS:

```
## Available Skills

You have 89 skills across two systems (gstack + GSD).
See asawa-inc/sutra/layer2-operating-system/SKILL-CATALOG.md for the complete catalog.

Quick start:
- New project: /gsd:new-project
- Plan a feature: /gsd:plan-phase
- Build it: /gsd:execute-phase
- Test it: /qa
- Ship it: /ship → /canary
- Learn: /retro
```
