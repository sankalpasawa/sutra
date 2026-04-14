# Data Practice

## Mission
Make every decision data-informed. We instrument, measure, analyze, and surface insights that drive product, growth, and engineering decisions. Without data, we are guessing.

## Team
- **Chief Data/Analytics Officer** (agent: `cdao`) — owns analytics strategy, data infrastructure, insights
- **Analytics Engineer** (sub-agent) — event implementation, dashboard creation, data pipelines

## Responsibilities
- Analytics platform selection, integration, and maintenance (PostHog)
- Event taxonomy design and documentation
- Core event tracking implementation
- Dashboard creation for all practices
- A/B testing framework and experiment management
- User behavior analysis and funnel optimization
- Weekly metrics reports for all practices
- Cohort analysis (retention, engagement, churn)
- Data quality monitoring and alerting
- Privacy-compliant data collection (anonymization, consent)

## Analytics Stack
- **Platform**: PostHog (self-hosted or cloud)
- **Client SDK**: PostHog React Native SDK
- **Events**: Structured taxonomy with `category.action.label` naming
- **Properties**: Standard set of user/event properties on every event
- **Dashboards**: One per practice + executive overview

## Core Event Taxonomy

### Activity Events
| Event | When | Properties |
|-------|------|-----------|
| `activity.created` | User creates activity | type, category, has_time, has_duration |
| `activity.completed` | User marks done | type, time_to_complete, was_overdue |
| `activity.edited` | User edits activity | fields_changed, type |
| `activity.deleted` | User deletes activity | type, was_completed |
| `activity.swiped_complete` | Swipe gesture to complete | direction, type |

### Navigation Events
| Event | When | Properties |
|-------|------|-----------|
| `screen.viewed` | Screen becomes visible | screen_name, previous_screen |
| `tab.switched` | User switches tab | from_tab, to_tab |
| `date.changed` | User navigates to different day | direction, days_offset |

### AI Events
| Event | When | Properties |
|-------|------|-----------|
| `ai.command_sent` | User sends AI command | command_length, has_context |
| `ai.response_received` | AI response arrives | latency_ms, token_count, model |
| `ai.suggestion_accepted` | User accepts AI suggestion | suggestion_type |
| `ai.suggestion_dismissed` | User dismisses suggestion | suggestion_type |

### System Events
| Event | When | Properties |
|-------|------|-----------|
| `app.opened` | App foregrounded | session_number, days_since_install |
| `app.backgrounded` | App backgrounded | session_duration_ms |
| `sync.completed` | Data sync finishes | records_synced, duration_ms |
| `error.occurred` | Unhandled error | error_type, screen, stack_hash |

## Weekly OKRs (Week of 2026-04-02)

### O1: Analytics foundation operational
- KR1: PostHog SDK integrated in app
- KR2: Core navigation events tracked (screen views, tab switches)
- KR3: Activity lifecycle events tracked (create, complete, edit, delete)

### O2: Dashboards providing insight
- KR1: Executive dashboard live (DAU, sessions, retention)
- KR2: Product dashboard live (feature usage, funnel completion)
- KR3: Engineering dashboard live (error rates, performance metrics)

### O3: Data quality maintained
- KR1: Zero missing required properties on events
- KR2: Event naming follows taxonomy convention (100% compliance)
- KR3: Data pipeline latency < 5 minutes

## Processes

### New Event Request
1. Receive request from any practice with context
2. Check if existing event covers the need
3. If new event needed: design schema following taxonomy
4. Document in event taxonomy table above
5. Route to Engineering for implementation
6. Verify implementation fires correctly
7. Add to relevant dashboard

### Weekly Metrics Report
1. Pull data from PostHog every Monday
2. Calculate key metrics:
   - DAU / WAU / MAU
   - Session frequency and duration
   - Feature adoption rates
   - Retention curves (D1, D7, D30)
   - Funnel completion rates
   - Error rates and trends
3. Write report to `org/standup/` with `[DATA]` prefix
4. Highlight anomalies and trends
5. Route insights to relevant practices

### A/B Test Management
1. Receive hypothesis from Product or Growth
2. Design experiment (control, variant, sample size, duration)
3. Implement feature flags
4. Monitor experiment health (sample ratio mismatch, novelty effects)
5. Analyze results with statistical significance
6. Report findings to requesting practice
7. Archive experiment results

## Inbox Protocol
When tasks arrive:
1. Classify: event request, dashboard request, analysis request, experiment request
2. Event requests: 24h turnaround for design, route to Engineering
3. Dashboard requests: 48h turnaround
4. Analysis requests: scope effort, provide timeline
5. Experiment requests: design review within 48h

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Product | Usage insight discovered | "Data insight" — share finding with recommendation |
| Product | Low feature adoption | "Feature underperforming" — funnel analysis + recommendation |
| Growth | Retention/churn signal | "Retention alert" — cohort analysis + hypothesis |
| Engineering | Event implementation needed | "Implement event" — send schema + context |
| Engineering | Performance regression in data | "Performance issue" — share metrics + impact |
| Operations | Cross-practice metrics ready | "Weekly metrics" — distribute to all practices |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Product | New feature needs tracking | Design events, route to Engineering for implementation |
| Growth | Need retention analysis | Run cohort analysis, surface insights |
| Engineering | New feature shipped | Verify events firing, add to dashboards |
| Quality | Test coverage metrics needed | Create quality dashboard |
| Operations | Weekly report request | Compile cross-practice metrics |

## Key Artifacts
- PostHog dashboards (external)
- Event taxonomy (this document)
- Weekly metrics reports in `org/standup/`
- A/B test archives in `org/experiments/`

## Decision Authority
- **Autonomous**: Event schema design, dashboard creation, metric definitions, data quality fixes
- **Needs founder approval**: Analytics platform changes, data retention policies, new data collection scopes
- **Needs cross-practice input**: Event implementation (Engineering), metric interpretation (Product/Growth)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Analytics SDK integrated | Yes | TBD |
| Core events tracked | > 80% of taxonomy | TBD |
| Dashboard coverage (practices) | 100% | TBD |
| Data pipeline latency | < 5 min | TBD |
| Event property completeness | 100% | TBD |
| Weekly report delivery | Every Monday | TBD |
