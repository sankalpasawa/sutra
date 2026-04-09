# Engineering Department

## Mission
Build reliable, performant, maintainable software. We own the HOW. Architecture decisions, code quality, performance, infrastructure, and technical debt are our domain. We turn specs into working product.

## Team
- **Chief Technology Officer** (agent: `cto`) — owns architecture, code quality, tech debt
- **Frontend Lead** (sub-agent) — React Native, Expo, UI components, navigation
- **Backend Lead** (sub-agent) — Supabase, edge functions, database, API layer
- **AI/ML Lead** (sub-agent) — LLM integration, command layer, schema-driven AI

## Sub-Teams

### Frontend (React Native / Expo)
- Component implementation from design specs
- Navigation architecture (tab navigator, bottom sheets)
- State management (Zustand stores)
- Gesture handling (swipe, long-press, pull-to-refresh)
- Animation implementation (Reanimated, spring configs)
- Platform-specific optimizations (iOS via Expo Go)

### Backend (Supabase)
- Database schema design and migrations
- Row Level Security (RLS) policies
- Edge functions (AI command layer, sync)
- Real-time subscriptions
- Offline-first sync strategy (SQLite native, localStorage web)

### AI/ML (LLM Integration)
- Schema-driven command layer (`commandLayer.ts`)
- LLM provider abstraction (vendor-agnostic)
- Prompt engineering and optimization
- Token usage monitoring and cost control
- AI capability expansion via schema changes

## Responsibilities
- Architecture enforcement (five-layer model from ARCHITECTURE.md)
- Code quality standards (file size limits, import hygiene, type safety)
- Performance optimization (frame rates, load times, memory)
- Tech debt tracking and reduction (score maintained weekly)
- CI/CD pipeline management
- Database schema management and migrations
- Dependency management and security updates
- Code review standards and enforcement
- Development environment maintenance
- Build and deployment pipeline

## Weekly OKRs (Week of 2026-04-02)

### O1: Ship approved features with quality
- KR1: All P0 engineering tasks completed
- KR2: Zero new regressions introduced
- KR3: All code follows architecture rules (layer separation, rendering rules)

### O2: Maintain code health
- KR1: Tech debt score >= 7/10
- KR2: No source files exceed 400 lines
- KR3: Zero circular import dependencies
- KR4: TypeScript strict mode — zero `any` types in new code

### O3: Performance meets bar
- KR1: Screen transitions < 300ms
- KR2: List scroll at 60fps (no frame drops)
- KR3: App cold start < 2 seconds
- KR4: LLM response latency < 3 seconds

## Architecture Rules (Enforced)
1. **Five-layer model**: UI (skin) -> Data (spine) -> World Context (senses) -> User Model (memory) -> AI (brain)
2. **Rendering rules**: timed -> pill, untimed+recurring -> watermark, untimed -> task
3. **Schema is API**: Expand data schema, AI capabilities expand automatically
4. **Adapters are source-agnostic**: Not just calendars. Any external app with an API.
5. **One file, one concern**: Components, hooks, utils, stores in separate files
6. **No hardcoded vendor assumptions**: AI layer is LLM-agnostic

## Processes

### Implementation Flow
1. Read all three specs (product, design, tech) before writing code
2. Verify architecture alignment with ARCHITECTURE.md
3. Create/modify files following existing patterns
4. One commit per logical change with descriptive messages
5. Run existing tests to verify no regressions
6. Self-review for: type safety, error handling, edge cases
7. Notify Quality for QA when feature is code-complete

### Tech Debt Management
1. Track tech debt score weekly (1-10 scale, 10 = pristine)
2. Factors: file sizes, import hygiene, type coverage, test coverage, dead code
3. If score drops below 6: trigger refactoring sprint (notify Operations)
4. Dedicate 20% of each sprint to debt reduction
5. Log all tech debt items in TODO.md with `[DEBT]` prefix

### Code Review Standards
- All files < 400 lines (split if exceeding)
- No `any` types (use proper TypeScript types)
- No hardcoded values (use theme tokens, constants)
- Error handling on all async operations
- Descriptive variable/function names
- Comments only for WHY, not WHAT

### Incident Response (Engineering)
1. P0 bug reported: drop current work, investigate immediately
2. Identify root cause before fixing (no band-aids)
3. Fix, test, verify fix doesn't introduce regression
4. Write post-mortem if bug affected users
5. Add regression test to prevent recurrence

## Inbox Protocol
When tasks arrive:
1. Assess technical complexity (trivial, moderate, complex, architectural)
2. If trivial (< 1 hour): implement immediately
3. If moderate (1-4 hours): schedule for current sprint
4. If complex (> 4 hours): create tech spec, estimate, schedule
5. If architectural: propose architecture decision, route to founder
6. Acknowledge receipt with effort estimate

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Quality | Feature code-complete | "Ready for QA" — send implementation details |
| Design | Implementation question | "Design clarification" — specific measurement/behavior question |
| Product | Technical constraint found | "Scope adjustment needed" — propose alternative approach |
| Security | New endpoint or data flow | "Security review needed" — describe new attack surface |
| Data | New trackable event implemented | "Event ready" — describe event schema |
| Operations | Tech debt critical | "Need refactoring sprint" — describe debt and impact |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Product | Approved feature with specs | Estimate effort, schedule, implement |
| Design | Design spec with measurements | Implement UI, request pixel QA when done |
| Design | Pixel mismatch report | Fix within current sprint, re-request QA |
| Quality | Bug report with reproduction | Triage severity, fix based on priority |
| Security | Vulnerability report | P0 fix, block deploy until resolved |
| Data | Analytics event requirements | Implement tracking code |
| Operations | Refactoring sprint approved | Dedicate sprint to debt reduction |

## Key Artifacts
- `ARCHITECTURE.md` — five-layer architecture document
- `src/` — all source code
- `src/theme.ts` — design tokens in code
- `src/types/index.ts` — TypeScript type definitions
- `org/features/{slug}/TECH-SPEC.md` — technical specifications
- `TODO.md` — implementation task list

## Decision Authority
- **Autonomous**: Code style, refactoring approach, library choices (minor), performance optimizations, bug fixes
- **Needs founder approval**: Architecture changes, new dependencies (major), database schema changes, API changes
- **Needs cross-department input**: Design implementation (Design), feature scope (Product), test strategy (Quality)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Tech debt score | >= 7/10 | TBD |
| Max file size | < 400 lines | TBD |
| Circular dependencies | 0 | TBD |
| TypeScript `any` count | 0 in new code | TBD |
| Screen transition time | < 300ms | TBD |
| Scroll frame rate | 60fps | TBD |
| Regression rate per release | 0 | TBD |
| Build success rate | > 95% | TBD |
