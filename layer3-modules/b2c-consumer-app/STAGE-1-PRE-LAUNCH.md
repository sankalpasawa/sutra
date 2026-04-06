# B2C Consumer App — Stage 1: Pre-Launch (1 person, 0 users)

This is the minimal operating system for DayFlow's current stage. Everything else in Sutra is future. Use THIS file.

## What You Need Right Now (and nothing else)

### Before Building Anything
1. **One sentence**: What is this and who is it for? (Already done: "Personal OS for structured achievers")
2. **PR/FAQ test**: Can you write a compelling 3-sentence press release? If not, don't build it.
3. **P1 only**: What is the smallest version that tests the core hypothesis?

### When Building
4. **Read PRODUCT-KNOWLEDGE-SYSTEM.md** before changing any code file. Check the change flow map.
5. **One file at a time**. Commit after each file. Type-check after each change.
6. **Design mockup before code** for any visible change. Show the user. Get approval.
7. **Intent + boundaries** for every task: what outcome, what constraints, method is free.

### After Building
8. **Does it work on the phone?** Test via Expo Go. Not theoretical — actually tap through it.
9. **Does it match the design spec?** Run the 5 sensors from PRODUCT-KNOWLEDGE-SYSTEM.md.
10. **Commit and push.** Every working change, immediately.

### Weekly
11. **What did we ship?** List features that reached the phone.
12. **What broke?** Any bugs or regressions. Feed back to Sutra as learning.
13. **What's next?** Top 3 items from TODO.md Layer 2 (DayFlow P0).

## Depth by Stage

The depth system (Layer 2) controls how thoroughly each task is executed. Modules activate different depth ranges as the company matures.

| Stage | Default Depth | When to use higher |
|-------|--------------|-------------------|
| **Stage 1 — Pre-Launch** (current) | 1-3 | Depth 3 for architecture decisions, data model changes |
| **Stage 2 — Beta** (25+ users) | 2-4 | Depth 4 for user-facing flows, security, data migrations |
| **Stage 3 — Growth** (scaling) | 2-5 | Depth 5 for compliance, performance-critical paths, pricing |

At Stage 1, most tasks are Depth 1-2. Only reach for Depth 3 when the decision is hard to reverse.

---

## Functions Active at This Stage

| Function | What it does now | What it does NOT do yet |
|----------|-----------------|----------------------|
| **Product** | Decide what to build. Say no to everything else. | User research (no users yet) |
| **Design** | Mockups before code. Design QA after code. | Design system documentation (just theme.ts) |
| **Engineering** | Write code. Fix bugs. Keep it simple. | CI/CD, monitoring, performance optimization |
| **Security** | Don't expose API keys. Sanitize inputs. Privacy policy. | Pen testing, SOC2, vulnerability scanning |
| **Quality** | Run sensors. Test on phone. Catch regressions. | Automated test suite, visual regression |
| **Growth** | Not yet. Ship first. | Everything |
| **Data** | Not yet. Add PostHog before first beta users. | A/B testing, cohorts, dashboards |
| **Ops** | Git push. Supabase deploy. That's it. | CI/CD, monitoring, alerting, on-call |
| **Content** | Button labels and placeholders are clear. | App store listing, docs, changelog |
| **Finance** | Don't run out of money. | Unit economics, pricing model |
| **Legal** | Privacy policy before App Store. Terms of service. | IP, contracts, compliance audit |

## The Only Process

```
IDEA → Does it pass the PR/FAQ test? → Is it P0?
  YES → Design mockup → Approve → Build (one file at a time)
      → Sensors → Test on phone → Commit → Push
  NO  → Add to TODO.md for later
```

That's the entire operating system for Stage 1. When DayFlow graduates to Stage 2 (25+ beta users), more process gets added. Not before.

## Stage Graduation Criteria

**Stage 1 → Stage 2** (when ALL of these are true):
- App on TestFlight
- 25+ beta users
- PostHog analytics live
- Privacy policy published
- At least 5 user interviews completed

**Stage 2 will add**: user research process, analytics review, A/B testing, onboarding optimization, retention tracking, weekly metrics review.

**Stage 3+ is documented in Sutra but not loaded until earned.**

## Feedback to Sutra

When DayFlow discovers something that Sutra should learn:
1. Write a short note in `asawa-inc/dayflow/feedback-to-sutra/`
2. Format: what happened, what principle was missing or wrong, what we learned
3. Sutra picks this up and updates its layers

Examples of feedback:
- "The virtual ID handling caused 3 bugs. Sutra needs a principle about runtime-generated IDs."
- "The 10-stage SDLC was too heavy for a bug fix. Sutra needs operating intensity levels."
- "Design mockups before code saved us 2 hours on the duration picker."
