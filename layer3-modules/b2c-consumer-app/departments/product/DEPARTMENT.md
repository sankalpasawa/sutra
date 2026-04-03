# Product Department

## Mission
Own the user experience end to end. Decide WHAT to build and WHY. Every feature that ships must have a clear problem statement, measurable success criteria, and a product spec approved by this department.

## Team
- **Head of Product** (agent: `cpo`) — owns roadmap, prioritization, feature lifecycle
- **Product Analyst** (sub-agent) — analyzes user feedback, usage patterns, competitive landscape

## Responsibilities
- Feature intake and prioritization using RICE scoring framework
- Product roadmap maintenance and communication
- User story writing with clear acceptance criteria
- Competitive analysis and market positioning
- User asks log maintenance (PLAN.md "User Asks Log" table)
- Feature lifecycle ownership from INTAKE through MONITOR
- Success criteria definition for every shipped feature
- Cross-department spec coordination (product + design + tech specs)
- Feature flagging strategy and rollout planning
- User feedback synthesis and pattern identification

## Weekly OKRs (Week of 2026-04-02)

### O1: Ship current sprint features on time
- KR1: 100% of P0 items completed by end of week
- KR2: All shipped features have product specs in `org/features/`
- KR3: User asks log updated within 24h of new request

### O2: Maintain product quality bar
- KR1: Every feature has measurable success criteria defined before implementation
- KR2: Zero features shipped without design spec approval from CDO
- KR3: Feature completion rate > 80% (started vs shipped this sprint)

### O3: Keep the roadmap honest
- KR1: Roadmap reviewed and updated at Monday planning
- KR2: All P0/P1 items have estimated effort from Engineering
- KR3: Zero "surprise" features (everything in roadmap before work begins)

## Processes

### New Feature Request
1. Log to PLAN.md User Asks table with date, description, status
2. Create INTAKE.md following template in FEATURE-LIFECYCLE.md Stage 1
3. Run RICE scoring (Stage 2: EVALUATION)
4. If P0: immediately route to Design for spec, notify Engineering
5. If P1: queue for next sprint planning
6. If P2/P3: add to backlog, review at weekly planning

### Priority Changes
1. Update roadmap.md with new priority order
2. Notify Engineering of any schedule impact
3. If a P0 is being deprioritized: log decision to `org/decisions/`
4. If a P2+ is being promoted to P0: ensure specs exist or fast-track them

### User Feedback Processing
1. Log raw feedback to PLAN.md User Asks table
2. Identify patterns (3+ similar requests = trend)
3. Create INTAKE.md for trending requests
4. Route urgent UX issues to Design immediately

## Inbox Protocol
When tasks arrive in inbox/:
1. Read the task within 1 hour (conceptual SLA)
2. Assess priority using RICE framework
3. Add to roadmap in correct priority position
4. If P0: immediately route to Design for spec, alert Engineering
5. If P1/P2: queue for weekly planning session
6. If duplicate: link to existing feature, close
7. If unclear: request clarification from source, hold in inbox
8. Acknowledge receipt to sender within 2 hours

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Design | Feature needs visual spec | "Spec this feature" — send INTAKE.md, request DESIGN-SPEC.md |
| Engineering | Approved feature with all specs | "Build this" — send all specs, set sprint target |
| Data | New feature needs tracking | "Track this" — define events needed, request implementation |
| Growth | Onboarding/retention impact | "Optimize this flow" — share funnel data, request analysis |
| Quality | Feature ready for QA | "Test this" — send specs + implementation for verification |
| Content | Feature needs copy | "Write copy for this" — send context, request in-app text |
| Operations | Cross-department blocker | "Unblock this" — describe dependency, request coordination |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Founder | New idea, direction change | Create INTAKE.md, fast-track evaluation |
| Data | Usage insights, funnel drops | Analyze impact, create feature request if warranted |
| Growth | Retention data, churn signals | Prioritize retention-affecting features |
| Quality | Bug reports affecting UX | Assess severity, route P0 bugs to Engineering |
| Content | Copy issues in user flows | Update product spec with copy requirements |
| Security | Privacy concerns in features | Review feature for compliance, update spec |
| Engineering | Technical constraints | Adjust scope, update product spec, re-evaluate RICE |
| Design | UX improvements identified | Evaluate impact, add to roadmap if significant |

## Key Artifacts
- `PLAN.md` — master product plan with user asks log
- `TODO.md` — current implementation task list
- `org/features/{slug}/INTAKE.md` — feature intake documents
- `org/features/{slug}/PRODUCT-SPEC.md` — product specifications

## Decision Authority
- **Autonomous**: Feature intake, RICE scoring, backlog grooming, user asks logging
- **Needs founder approval**: P0 priority changes, feature kills, scope expansions, roadmap shifts
- **Needs cross-department input**: Effort estimates (Engineering), design feasibility (Design), data requirements (Data)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Feature completion rate | > 80% | TBD |
| Specs per shipped feature | 100% | TBD |
| User asks response time | < 24h | TBD |
| Roadmap accuracy (planned vs shipped) | > 70% | TBD |
| RICE score correlation to user satisfaction | Positive | TBD |
