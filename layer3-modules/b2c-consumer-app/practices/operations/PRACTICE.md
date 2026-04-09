# Operations Department

## Mission
Keep the organization running smoothly. We are the connective tissue between all departments. Cross-department coordination, process enforcement, resource allocation, and organizational health are our domain. When something is blocked, we unblock it. When processes fail, we fix them.

## Team
- **Chief Operating Officer** (agent: `coo`) — owns cross-department coordination, process management, org health
- **Program Manager** (sub-agent) — tracks cross-department dependencies, manages timelines, runs ceremonies

## Responsibilities
- Daily standup orchestration and synthesis
- Weekly planning session facilitation
- Cross-department dependency tracking and resolution
- Process documentation and improvement
- Resource allocation across departments
- Sprint planning and velocity tracking
- Blocker identification and escalation
- OKR tracking and accountability
- Meeting facilitation (standups, planning, retros)
- Organizational health monitoring
- Decision log maintenance (`org/decisions/`)
- Department performance reviews
- Process compliance auditing

## Weekly OKRs (Week of 2026-04-02)

### O1: All departments producing and aligned
- KR1: Daily standup reports generated every session
- KR2: All 9 departments have current OKRs (updated this week)
- KR3: Weekly planning session conducted on Monday

### O2: Zero cross-department blockers
- KR1: All identified blockers have an owner and ETA
- KR2: Cross-department handoffs complete within 24 hours
- KR3: No department waiting on another for > 48 hours

### O3: Processes documented and followed
- KR1: All processes in `org/processes/` are current
- KR2: Feature lifecycle followed for 100% of features
- KR3: Decision log maintained (all decisions within 24h)
- KR4: Routing table followed for 100% of cross-department signals

## Processes

### Daily Standup Orchestration
1. Trigger standup at session start (see `org/processes/DAILY-STANDUP.md`)
2. Launch parallel agents: Quality, Design, Engineering, Data
3. Collect reports from all departments
4. Synthesize with CEO agent into prioritized action list
5. Write report to `org/standup/{date}.md`
6. Route action items to responsible departments
7. Track completion of yesterday's action items

### Weekly Planning (Monday)
1. Review last week's OKRs across all departments
2. Calculate OKR completion rates per department
3. Update this week's OKRs for all departments
4. Stack rank priorities across all departments
5. Identify cross-department dependencies
6. Resolve blockers or escalate to founder
7. Update roadmap based on actual progress
8. Write weekly plan to `org/standup/{date}-weekly.md`
(See `org/processes/WEEKLY-PLANNING.md` for full protocol)

### Blocker Resolution
1. Blocker identified by any department
2. Operations assesses: is this within one department or cross-department?
3. If within one department: route to department head with priority
4. If cross-department:
   a. Identify all involved departments
   b. Determine critical path (what unblocks first?)
   c. Assign owner for resolution
   d. Set deadline (24h for P0, 48h for P1, this sprint for P2)
   e. Track until resolved
   f. Log resolution in decision log if significant

### Process Improvement
1. Monthly: audit all processes in `org/processes/`
2. Identify bottlenecks (what takes too long?)
3. Identify waste (what doesn't add value?)
4. Propose improvements with rationale
5. Implement changes, update documentation
6. Monitor impact for two weeks
7. Iterate or revert based on results

### Sprint Velocity Tracking
1. Track planned vs completed items per sprint
2. Calculate velocity (items completed / sprint)
3. Use velocity for capacity planning
4. Flag when velocity drops > 20% (investigate cause)
5. Report velocity trends at weekly planning

## Organizational Calendar

### Daily
- Standup report generated (every session)
- Action items routed to departments
- Blocker status checked

### Weekly (Monday)
- Weekly planning session
- OKR review and update
- Roadmap adjustment
- Department health check

### Weekly (Friday)
- Sprint retrospective
- Velocity calculation
- Next sprint preview

### Monthly
- Process audit
- Department performance review
- Organizational health assessment
- Charter review

## Inbox Protocol
When tasks arrive:
1. Classify: blocker, coordination request, process question, escalation
2. Blockers: triage within 1 hour, assign owner, set deadline
3. Coordination requests: schedule handoff within 24 hours
4. Process questions: answer or update documentation within 48 hours
5. Escalations: assess severity, route to founder if needed

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| All Departments | Weekly OKR updates | "OKR review" — share previous week results, new targets |
| All Departments | Process change | "Process update" — describe change, effective date |
| Founder | Escalation needed | "Founder decision needed" — context, options, recommendation |
| Product | Priority conflict | "Priority resolution" — competing priorities, need decision |
| Engineering | Resource constraint | "Capacity alert" — workload exceeds capacity, need scope adjustment |
| Quality | Release coordination | "Release readiness" — checklist of items for QA before ship |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Any Department | Blocker reported | Assess, assign owner, track resolution |
| Any Department | Resource request | Evaluate capacity, allocate or negotiate |
| Engineering | Tech debt critical (score < 6) | Schedule refactoring sprint, protect from new work |
| Quality | Release blocked | Assess blocking issues, coordinate fixes across departments |
| Product | Priority change | Communicate to all affected departments, adjust schedules |
| Security | Compliance deadline | Allocate resources, track progress, ensure deadline met |
| Founder | Direction change | Cascade to all departments, adjust plans |

## Cross-Department Dependencies (Current)

| Dependency | From | To | Status | ETA |
|-----------|------|-----|--------|-----|
| *Updated at weekly planning* | | | | |

## Key Artifacts
- `org/processes/` — all process documents
- `org/standup/` — daily and weekly reports
- `org/decisions/` — decision log
- `org/ROUTING.md` — cross-department routing table
- Sprint velocity tracking data
- OKR scorecards per department

## Decision Authority
- **Autonomous**: Meeting scheduling, blocker routing, process documentation, sprint velocity tracking
- **Needs founder approval**: Organizational structure changes, process changes affecting all departments, resource allocation conflicts
- **Needs cross-department input**: Sprint planning (all departments), priority resolution (Product + affected departments)

## Department Health Dashboard

| Department | OKR Score | Blockers | Process Compliance | Status |
|-----------|-----------|----------|-------------------|--------|
| Product | TBD | TBD | TBD | -- |
| Design | TBD | TBD | TBD | -- |
| Engineering | TBD | TBD | TBD | -- |
| Data | TBD | TBD | TBD | -- |
| Security | TBD | TBD | TBD | -- |
| Quality | TBD | TBD | TBD | -- |
| Growth | TBD | TBD | TBD | -- |
| Operations | TBD | TBD | TBD | -- |
| Content | TBD | TBD | TBD | -- |

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Standup report frequency | Daily | TBD |
| Weekly planning conducted | Every Monday | TBD |
| Blocker resolution time (P0) | < 24h | TBD |
| Blocker resolution time (P1) | < 48h | TBD |
| Cross-department handoff time | < 24h | TBD |
| OKR completion rate (org-wide) | > 70% | TBD |
| Process compliance | 100% | TBD |
| Decision log freshness | < 24h | TBD |
