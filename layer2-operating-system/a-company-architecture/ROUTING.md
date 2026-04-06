# Cross-Department Routing Table

When a department discovers a signal that another department needs to act on, this table defines the routing. Follow it precisely — no ad-hoc communication. Every cross-department handoff goes through this table.

---

## How to Use This Table

1. **Detecting department** identifies a signal (column 2)
2. Look up the signal in this table
3. Route to the specified department(s) (column 3)
4. Include the specified action/context (column 4)
5. Receiving department follows their Inbox Protocol (in their DEPARTMENT.md)
6. Operations tracks handoffs that are cross-department blockers

---

## Master Routing Table

### Data Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 1 | Data | Low retention metric (D7 < 40%) | Growth + Product | Growth investigates churn causes, Product evaluates feature impact on retention |
| 2 | Data | Feature adoption < 10% after 7 days | Product | Product evaluates: is the feature discoverable? Useful? Needs iteration? |
| 3 | Data | Error rate spike (> 1%) | Engineering | P1 investigation — identify failing endpoint/screen, fix |
| 4 | Data | Funnel drop-off identified | Product + Growth | Product reviews flow, Growth proposes optimization |
| 5 | Data | Analytics event not firing | Engineering | Investigate implementation, fix broken tracking code |
| 6 | Data | Session duration declining | Product + Design | Investigate UX friction, review recent changes |
| 7 | Data | New user activation rate low | Growth + Design | Optimize onboarding, review first-time experience |

### Quality Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 8 | Quality | Pixel mismatch found | Design + Engineering | Design specs the correct values, Engineering implements fix |
| 9 | Quality | Design token violation | Engineering | Fix hardcoded value, replace with design token |
| 10 | Quality | Regression detected | Engineering | P0/P1 fix — find causing commit, revert or fix |
| 11 | Quality | Test coverage dropped | Engineering | Write missing tests before next feature work |
| 12 | Quality | QA verdict: BLOCK | Operations + Engineering | Operations tracks blocker, Engineering fixes blocking issues |
| 13 | Quality | Performance regression (fps < 60) | Engineering | Profile and fix frame drops |
| 14 | Quality | Accessibility failure | Design + Engineering | Design updates spec, Engineering implements fix |

### Security Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 15 | Security | Critical vulnerability found | Engineering + Operations | P0 fix — block all deploys, Engineering fixes immediately |
| 16 | Security | Secret detected in code | Engineering | Remove secret, rotate credential, add to .gitignore |
| 17 | Security | RLS policy missing | Engineering | Implement RLS before any deploy with that table |
| 18 | Security | Dependency vulnerability (high) | Engineering | Update dependency or find alternative |
| 19 | Security | Privacy concern with feature | Product + Engineering | Product reviews scope, Engineering adjusts data handling |
| 20 | Security | Compliance deadline approaching | Operations + Content | Operations allocates resources, Content updates policies |

### Engineering Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 21 | Engineering | Tech debt score < 6/10 | Operations | Schedule refactoring sprint, protect from new feature work |
| 22 | Engineering | File exceeds 400 lines | Quality | Track in debt list, schedule split in current sprint |
| 23 | Engineering | Architecture violation found | Product | Discuss scope — may need spec revision |
| 24 | Engineering | New component implemented | Quality + Design | Quality writes tests, Design runs pixel QA |
| 25 | Engineering | Edge function deployed | Security + Data | Security reviews auth, Data verifies events |
| 26 | Engineering | Schema migration needed | Security + Data | Security reviews RLS, Data updates event properties |
| 27 | Engineering | Build broken | Operations | P0 — block all work until build restored |
| 28 | Engineering | Technical constraint on feature | Product | Scope adjustment needed — propose alternative |

### Product Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 29 | Product | New P0 feature approved | Design + Engineering + Content | Design creates spec, Engineering estimates, Content writes copy |
| 30 | Product | Priority change (P0 shift) | Operations + Engineering | Operations cascades to all departments, Engineering adjusts sprint |
| 31 | Product | Feature killed | Operations | Operations notifies all departments, stops in-progress work |
| 32 | Product | User feedback trend identified | Design + Growth | Design reviews UX, Growth assesses retention impact |
| 33 | Product | Roadmap updated | Operations | Operations communicates changes to all departments |
| 34 | Product | Success criteria defined | Data | Data sets up tracking events and dashboard |

### Design Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 35 | Design | New component spec ready | Engineering + Content | Engineering implements, Content writes labels/copy |
| 36 | Design | Design system update | Engineering + Quality | Engineering updates theme.ts, Quality updates token audit |
| 37 | Design | Accessibility audit failed | Engineering | Fix contrast, touch targets, or screen reader labels |
| 38 | Design | New animation spec | Engineering | Implement with specified spring configs/durations |
| 39 | Design | Layout constraint with copy | Content | Content adjusts copy length to fit design |

### Growth Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 40 | Growth | Onboarding drop-off identified | Product + Design | Product reviews flow, Design proposes improvements |
| 41 | Growth | Push notification ready | Engineering + Content | Engineering implements trigger, Content writes copy |
| 42 | Growth | ASO update needed | Content | Content updates app store listing |
| 43 | Growth | Retention hook proposal | Product + Engineering | Product evaluates, Engineering estimates effort |
| 44 | Growth | Churn analysis complete | Product | Product prioritizes retention features based on findings |
| 45 | Growth | A/B test results in | Product + Data | Product decides on winner, Data archives experiment |

### Content Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 46 | Content | Inconsistent terminology found | Design + Product | Align on standard terms, update all instances |
| 47 | Content | Missing empty state copy | Design + Engineering | Design specs the empty state, Engineering implements |
| 48 | Content | App store listing ready | Growth | Growth reviews ASO, gives final approval |
| 49 | Content | Documentation outdated | Operations | Operations schedules doc update, assigns to relevant dept |
| 50 | Content | Copy audit findings | Engineering | Engineering implements copy fixes |

### Operations Department Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 51 | Operations | Cross-department blocker | Founder | Escalate with context, options, recommendation |
| 52 | Operations | Department underperforming | Relevant department | Investigate cause, propose improvement |
| 53 | Operations | Process compliance failure | Relevant department | Re-educate on process, track improvement |
| 54 | Operations | Sprint capacity exceeded | Product | Deprioritize lowest-ranked items |
| 55 | Operations | Weekly planning complete | All Departments | Distribute updated priorities and OKRs |

### Founder Signals

| # | From | Signal | Routes To | Action |
|---|------|--------|-----------|--------|
| 56 | Founder | New idea | Product | CPO creates INTAKE.md, begins evaluation |
| 57 | Founder | Direction change | Operations | Operations cascades to all departments |
| 58 | Founder | Taste decision made | Design + Engineering | Design updates spec, Engineering implements |
| 59 | Founder | Feature approved | Engineering + Design + Content | Begin implementation per FEATURE-LIFECYCLE.md |
| 60 | Founder | Feature killed | Operations + Product | Operations stops work, Product logs reason |

---

## Depth Integration

Routing decisions reference the depth assessment from the Adaptive Protocol Engine (PROTO-000). Higher depth means more departments are consulted before routing.

| Depth | Routing Behavior |
|-------|------------------|
| 1-2 | Route to primary department only. No cross-department consultation. |
| 3 | Route per table. Check for secondary department impact. |
| 4-5 | Full routing: all affected departments notified, Operations tracks handoff, resolution requires sign-off. |

**Rule**: The depth assessment output determines how many routing hops a signal takes. Low-depth signals go direct; high-depth signals follow the full multi-department routing protocol.

---

## Routing Rules

### General Rules
1. **Always follow the table.** No ad-hoc routing. If a signal isn't in the table, add it.
2. **Include context.** Never route a bare signal. Include: what was found, why it matters, what action is expected.
3. **Acknowledge receipt.** Receiving department acknowledges within their SLA (see DEPARTMENT.md Inbox Protocol).
4. **Track completion.** Operations tracks all P0/P1 cross-department handoffs to completion.
5. **Escalate blockers.** If a handoff is stuck for > 24 hours, Operations intervenes.

### Priority Rules
- Security signals (rows 15-20) are always P0 until classified otherwise
- Regression signals (rows 10, 13) are always P0/P1
- Build broken (row 27) is always P0
- Everything else follows the originating department's priority assessment

### Multi-Department Routing
When a signal routes to multiple departments:
- All departments are notified simultaneously
- Operations assigns a primary owner
- Primary owner coordinates with secondary departments
- Resolution requires sign-off from all routed departments

---

*Last updated: 2026-04-02*
*To add a routing rule: propose at weekly planning, Operations approves and adds to table.*
