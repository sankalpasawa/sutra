# Phase 1 Research — Summary of Key Findings

## 23 Sources Studied Across 3 Tracks

### KEY INSIGHTS (distilled from all sources)

1. **Constraints determine throughput** (The Goal) — Your attention is the bottleneck. Everything else is subordinate.

2. **Make all work visible** (Phoenix Project) — Unplanned work is the silent killer. Track all four types: features, infrastructure, changes, unplanned.

3. **Stocks change slowly, flows change fast** (Thinking in Systems) — Map the system by feedback loops, not by org chart. Find the leverage points.

4. **Align by intent, not instruction** (Art of Action) — Brief agents with WHAT and WHY. Leave HOW open. Directed opportunism beats detailed plans.

5. **Boundaries enable speed** (Team Topologies + DDD) — Clear bounded contexts with typed interfaces let each part move independently.

6. **Separate things that change at different rates** (How Buildings Learn) — Shearing layers. Don't fuse fast-changing to slow-changing.

7. **Start simple, earn complexity** (Systemantics) — A complex system designed from scratch never works. Start with one working thing.

8. **Learn faster than you build** (Lean Startup) — The purpose is validated learning, not features shipped.

9. **Start from the customer, work backwards** (Working Backwards) — Write the press release before building. If it's not compelling, don't build it.

10. **Context is programming, not documentation** (LLM research) — Every token in the context window biases the output. Precision beats completeness.

11. **Types beat tests for error prevention** (Error reduction) — TypeScript strict mode prevents errors. Tests catch them. Both needed, types first.

12. **One good agent beats five unguarded ones** (Multi-agent) — Writer + Critic pattern. Single agent with structured self-review.

13. **The knowledge graph is 2-3 hops, not the whole repo** (Knowledge graphs) — Focused structural context beats massive dumps.

### EMERGING OPERATING MODEL

From the synthesis of all sources, the operating model has these layers:

```
IDEA FORMATION
  Sources: user feedback, analytics, founder vision, competitive observation,
           agent-driven discovery, OKR-driven generation
  Process: PR/FAQ (Working Backwards) + Hypothesis (Lean Startup)
  Decision: RICE scoring + constraint analysis (is this at the bottleneck?)

EVALUATION
  Cross-functional impact scan (all practices assess)
  Shearing layer analysis (which layers does this touch?)
  Constraint check (does this improve throughput at the bottleneck?)
  Founder approves: Go / Defer / Kill

SPECIFICATION
  Three specs in parallel + negotiation round:
  - Design spec (bounded context: what users see)
  - Tech spec (bounded context: what the system does)
  - Test spec (bounded context: how we verify)
  Feedback loops between specs (Art of Action: backbrief)
  P1/P2/P3 scoping with tech debt annotations

EXECUTION
  Knowledge system check (dependency graph for affected nodes)
  Build layer by layer (shearing layers: slow → fast)
  Incremental validation (TypeScript check after each change)
  Writer + Critic self-review
  Sensors verify boundaries

SHIPPING
  Automated checks (tests, types, design tokens)
  Deploy
  Analytics events confirmed
  Knowledge system updated

MONITORING + LEARNING
  Analytics: did this improve the target metric?
  Feedback: is this at the constraint or not?
  Incidents: update failure flow map
  Learning feeds back to IDEA FORMATION
```

### WHAT THE CASE STUDIES WILL ADD (pending)
- Amazon: the PR/FAQ process in detail, how it scales
- Apple: functional org, DRI model
- Stripe: writing culture, API-first impact on all functions
- Spotify: what actually worked vs what didn't
- Netflix: when less structure wins
- Toyota: continuous improvement, andon cord
- Bridgewater: codified decision-making
- Linear: small team, high output
