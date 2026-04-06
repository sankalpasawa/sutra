# Sutra OKRs

**Period**: Q2 2026 (April - June)
**Review cadence**: Roadmap Meeting (bi-weekly for Sutra)
**Scoring**: 0.0-1.0 per KR, 0.7 = on target

---

## Charter: Speed

**Objective**: Ship features faster without quality regression
**DRI**: Sutra Core
**KPI**: V (Velocity)

### KRAs (Key Result Areas)
- Session startup latency
- Governance overhead
- Fast-path for simple tasks
- Lazy loading

### KPIs (Always-on Metrics)
| Metric | Current (v1.4) | Target (v1.5) |
|--------|---------------|---------------|
| V_L2 (min/feature) | 24.7 | < 20 |
| V_L3 (min/feature) | 23.0 | < 20 |
| Governance overhead | unmeasured | < 15% |
| Startup to first action | unmeasured | < 10s |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Implement lazy loading for session-start files | All non-essential files deferred | 0.0 | Not started |
| Add fast-path for L1 tasks (skip PRE/POST) | L1 tasks bypass full governance stack | 0.0 | Not started |
| Enforce context budget per session | Governance overhead < 15% of tokens | 0.0 | Not started |
| Audit all hooks for deferral opportunities | Reduce hook count firing at session start | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Lazy loading for FOUNDER-DIRECTIONS, SYSTEM-MAP, NEW-THING-PROTOCOL | Cuts startup token load ~40% | Medium | Apr 2026 |
| 2 | Fast-path L1 in TASK-LIFECYCLE | L1 tasks 2-3x faster | Medium | May 2026 |
| 3 | Context budget tracking in checkpoint JSON | Enables measurement | Low | May 2026 |
| 4 | Hook audit and deferral pass | Reduces unnecessary session-start work | Low | Jun 2026 |

---

## Charter: Simplicity

**Objective**: Reduce system complexity without losing capability
**DRI**: Sutra Core
**KPI**: C (Cognitive Load)

### KRAs (Key Result Areas)
- File count
- Doc verbosity
- Protocol consolidation
- Progressive disclosure

### KPIs (Always-on Metrics)
| Metric | Current (v1.4) | Target (v1.5) |
|--------|---------------|---------------|
| C index | 4,621 | < 4,000 |
| L2 file count | 35 | < 28 |
| Avg words per governance file | 1,393 | < 1,200 |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Run L2 contraction cycle (merge overlapping docs) | Reduce L2 file count by 20% | 0.0 | Not started |
| Implement progressive OS loading | Context loaded by task scope, not globally | 0.0 | Not started |
| Merge overlapping protocols into unified docs | Fewer files, same coverage | 0.0 | Not started |
| Compress verbose governance docs | Avg words/file < 1,200 | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | L2 contraction cycle — identify merge candidates | Reduces file count, lowers C | High | Apr 2026 |
| 2 | Progressive OS — load context by task scope | Sessions only see what they need | High | May 2026 |
| 3 | Merge overlapping docs (e.g., charters into OKRs) | Fewer files, clearer ownership | Medium | May 2026 |
| 4 | Doc compression pass — tighten prose across L2 | Lower avg words/file | Low | Jun 2026 |

---

## Charter: Accuracy

**Objective**: Estimation and compliance approach reliability
**DRI**: Sutra Core
**KPI**: A (Accuracy)

### KRAs (Key Result Areas)
- Estimation calibration
- Principle compliance
- Feedback loop tightness

### KPIs (Always-on Metrics)
| Metric | Current (v1.4) | Target (v1.5) |
|--------|---------------|---------------|
| A_EWMA | 89.6% | > 92% |
| A_mean | 77.6% | > 85% |
| A_sigma | 23.3% | < 15% |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Close estimation feedback loop (auto-update calibration) | Calibration updates after every task | 0.0 | Not started |
| Collect 30+ calibration data points across categories | Reduce cold-start inaccuracy | 0.0 | Not started |
| Add principle regression tests | Compliance measured automatically | 0.0 | Not started |
| Reduce A_sigma below 15% | Consistent estimation, not just high average | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Estimation feedback loop — auto-calibrate after POST | Reduces cold-start bias | High | Apr 2026 |
| 2 | Accumulate 30+ calibration records across task types | Broadens estimation accuracy | Medium | May 2026 |
| 3 | Principle regression test suite | Catches compliance drift | Medium | Jun 2026 |
| 4 | Sigma analysis — identify high-variance categories | Targeted calibration fixes | Low | Jun 2026 |

---

## Charter: Efficiency

**Objective**: Deliver more value per token and dollar spent
**DRI**: Sutra Core
**KPI**: U (Unit Cost)

### KRAs (Key Result Areas)
- Token optimization
- Context window management
- Agent dispatch efficiency

### KPIs (Always-on Metrics)
| Metric | Current (v1.4) | Target (v1.5) |
|--------|---------------|---------------|
| U_tokens (per feature) | 47.5K | < 40K |
| U_cost (per feature) | $1.47 | < $1.20 |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Enforce context budget — cap governance token spend | Governance < 15% of total tokens | 0.0 | Not started |
| Smarter agent dispatch — avoid unnecessary sub-agents | Reduce overhead on simple tasks | 0.0 | Not started |
| Implement context compression for long sessions | Fewer tokens for same output quality | 0.0 | Not started |
| Track U per-level to isolate efficiency from task mix | Level-segmented cost reporting | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Context budget enforcement in session hooks | Directly reduces token waste | Medium | Apr 2026 |
| 2 | Smarter agent dispatch — inline L1, dispatch L3+ | Saves agent-startup token cost | Medium | May 2026 |
| 3 | Compression pass — reduce governance doc tokens | Lower baseline context cost | Low | May 2026 |
| 4 | Per-level U tracking in checkpoint JSON | Enables apples-to-apples comparison | Low | Jun 2026 |

---

## Charter: Human Readability

**Objective**: Every system output earns founder confidence through clarity and visual design
**DRI**: Sutra Core
**KPI**: Founder confidence (qualitative), decision visibility, output scannability

### KRAs (Key Result Areas)
- Decision highlighting (decisions must be boxed/bold/impossible to miss)
- Output formatting (tables, badges, icons)
- Document scannability (30-second comprehension test)
- Progressive detail (summary first, depth on demand)

### KPIs (Always-on Metrics)
| Metric | Current | Target |
|--------|---------|--------|
| Decision miss rate | unmeasured | 0 |
| Time-to-comprehend per output | unmeasured | < 30s |
| Founder asks "what?" count | unmeasured | 0 |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| All Roadmap Meeting decisions visually highlighted with blockquote/bold format | Decisions impossible to miss | 0.0 | Not started |
| Every governance output passes 30-second scan test | Instant comprehension | 0.3 | Some outputs already use tables/badges |
| Founder never misses a decision requiring input | Zero missed decisions | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Update Roadmap Meeting process with decision highlighting format | Decisions visually unmissable | Low | Apr 2026 |
| 2 | Audit all output templates for scannability | Consistent quality across outputs | Medium | May 2026 |
| 3 | Add decision-box format to READABILITY-STANDARD.md | Codified standard for all sessions | Low | May 2026 |

---

## Charter: Human-LLM Interaction

**Objective**: Every human input is routed through the system before the LLM acts
**DRI**: Sutra Core (c-human-agent-interface/)
**KPI**: Classification compliance rate, routing accuracy, skip rate

### KRAs (Key Result Areas)
- Input classification (every input classified before action)
- Routing accuracy (input goes to correct protocol)
- Enforcement (hook/protocol/skill levels)
- 7 interaction types coverage

### KPIs (Always-on Metrics)
| Metric | Current | Target |
|--------|---------|--------|
| Classification compliance | unmeasured | > 90% |
| Routing accuracy | unmeasured | > 95% |
| Interaction type coverage | 1/7 | 7/7 |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Input routing Level 2 deployed to Asawa + all clients | Full deployment | 0.1 | Protocol designed, not deployed |
| 7/7 interaction types defined (Human↔LLM, Agent↔Agent, Session↔Session, Company↔Company, process enforcement, natural language authority, self-assessment) | Complete coverage | 0.14 | 1/7 done: Human↔LLM via INPUT-ROUTING.md |
| Classification compliance > 90% across all sessions | Measured and enforced | 0.0 | Not measured yet |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Deploy Level 2 to CLAUDE.md | Input routing active for all sessions | Medium | Apr 2026 |
| 2 | Research remaining 6 interaction types | Full interaction model designed | High | May 2026 |
| 3 | Build measurement for classification compliance | Enables tracking and enforcement | Medium | Jun 2026 |

---

## Charter: First-Time QA

**Objective**: Every company's first deployment passes quality gates without rework
**DRI**: Sutra Core (onboarding)
**KPI**: First-deploy pass rate, rework count, onboarding QA coverage

### KRAs (Key Result Areas)
- Onboarding QA checklist
- Self-check automation (grep for placeholders, DayFlow references)
- Deployment verification
- Post-deploy smoke test

### KPIs (Always-on Metrics)
| Metric | Current | Target |
|--------|---------|--------|
| First-deploy pass rate | unmeasured | 100% |
| Rework items per onboarding | ~2-3 | < 2 |
| Time from deploy to first working feature | unmeasured | < 1 session |

### OKRs (Q2 2026: Apr-Jun)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Automated self-check catches 100% of placeholder/reference errors | Zero escapes | 0.3 | Manual grep exists in Phase 6 Step 12 |
| Post-deploy smoke test runs automatically for every new company | Automated verification | 0.0 | Not started |
| Rework items per onboarding < 2 | Near-zero rework | 0.3 | Paisa onboarding was relatively clean |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Automate Phase 6 self-check as hook | Catches placeholder errors automatically | Medium | Apr 2026 |
| 2 | Build post-deploy smoke test | Verifies deployment end-to-end | Medium | May 2026 |
| 3 | Track rework count per onboarding | Enables measurement and improvement | Low | Jun 2026 |

---

## Charter: External Research

**Objective**: Sutra evolves by learning from the best process frameworks, AI orchestration patterns, and operating system designs worldwide
**DRI**: Sutra Core

### KRAs
- AI/tech/market research — **weekly** cadence (AI agent orchestration, competing AI OS products, new tools/models)
- Framework/methodology research — **bi-weekly** cadence (Cynefin, Wardley, Shape Up, Toyota Kata, military doctrine)
- Best-in-class company operations (how Stripe, Linear, Basecamp scale processes)

### KPIs (Always-on)
| Metric | Current (v1.5) | Target (v2.0) |
|--------|---------------|---------------|
| Research docs produced | 4 (in progress via agents) | 10+ per quarter |
| Frameworks evaluated | 8+ (Cynefin, Wardley, military, medical, Toyota, Shape Up, Spotify, legal) | 15+ |
| Patterns adopted into Sutra | 0 (research phase) | 5+ per quarter |

### OKRs (Q2 2026)
| KR | Target | Current Score | Status |
|----|--------|--------------|--------|
| Adaptive Protocol research complete (8 frameworks evaluated) | Research doc with synthesis | 0.3 | Agent running now |
| Human-AI Interaction research complete | Research doc with 7 interaction types | 0.3 | Agent running now |
| Discipline artifact chains mapped (eng/design/product) | Full artifact chain with gap analysis | 0.3 | Agent running now |
| 5+ patterns from research adopted into Sutra protocols | Implemented and tested | 0.0 | Not started |

### Roadmap
| # | Action | Impact | Effort | Due |
|---|--------|--------|--------|-----|
| 1 | Complete Adaptive Protocol research | High | High | Apr 2026 |
| 2 | Complete Human-AI Interaction research | High | High | Apr 2026 |
| 3 | Complete Discipline Artifact Chains research | High | High | Apr 2026 |
| 4 | Synthesize research into Sutra protocol updates | High | Medium | May 2026 |
| 5 | Scan for emerging AI OS competitors (weekly) | Medium | Low | Ongoing |
| 6 | Framework/methodology refresh (bi-weekly) | Medium | Low | Ongoing |

---

## Charter: Revenue/Viability

**Objective**: Every launched company generates revenue or proves a path to it
**DRI**: Sutra Core
**Status**: INACTIVE — activates when first company launches to real users

### KRAs
- Revenue generation
- Path to monetization
- Unit economics

### KPIs (activate at launch)
| Metric | Current | Target |
|--------|---------|--------|
| Companies with revenue | 0 | 1+ |
| Companies with revenue path | 0 | all launched |
| Time from launch to first $ | N/A | < 90 days |

### OKRs — set when charter activates
