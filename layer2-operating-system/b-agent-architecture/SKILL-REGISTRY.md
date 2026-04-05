# Sutra — Skill Registry

## What Changed

The Skill Catalog (SKILL-CATALOG.md) maps all 89 skills by situation. This registry adds:
1. **Which skills each company type needs** (not all 89 — only relevant ones)
2. **Skill tiers** that activate with company maturity (like Progressive OS)
3. **How to fetch/install** when a company upgrades

## Skill Tiers

Skills activate based on company maturity, not loaded all at once:

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

## How Companies Get Skills

### During Onboarding (Phase 6: CONFIGURE)
Sutra reads the company's tier and product type, then:
1. Installs Tier 1 skills (always)
2. If Tier 2+: adds quality skills
3. If Tier 3: adds scale skills
4. Writes available skills to company CLAUDE.md "Skill Routing" section

### During Upgrade
When a company's tier changes (e.g., first external user → Tier 2):
1. Sutra notifies via feedback-from-sutra/
2. Company CLAUDE.md is updated with new skills
3. New hooks/processes associated with those skills are installed

### On Demand
Any company can request a specialist skill:
```
"I need to do a security audit" → fetches /cso skill
"I want to benchmark performance" → fetches /benchmark skill
```
These are session-only (not permanently installed) unless the company requests it.

## Product Type Skill Packs

Beyond tiers, some skills are relevant only to certain product types:

| Product Type | Additional Skills |
|-------------|-------------------|
| **Web app (Next.js)** | `/browse`, `/gstack`, `/qa`, `/benchmark` |
| **Mobile app (Expo)** | Design QA via screenshots, no browser skills |
| **CLI tool** | `/gsd:add-tests` (unit tests critical), no design skills |
| **B2B SaaS** | `/cso` (security from day 1), `/retro` (team cadence) |
| **Content platform** | `/design-shotgun` (visual exploration), `/canary` (uptime critical) |

## Integration with Existing Systems

- **SKILL-CATALOG.md**: Remains the full reference (all 89 skills by situation). This registry adds tier/type filtering.
- **Adaptive Protocol Engine**: When selecting depth, the engine checks which skills are available. If a Level 3 depth needs `/autoplan` but the company is Tier 1, it falls back to Level 2.
- **SUTRA-CONFIG.md**: Each company lists their installed skill tier and any specialist skills.
- **Process Generation**: When a new process is generated, it can reference skills by checking what's available.
