# Agent Protocols

## What This Is

Behavioral rules for AI agents operating within Sutra. Compiled from Asawa principles (HUMAN-AI-INTERACTION.md, PRINCIPLES.md) into agent-specific protocols.

These rules answer: when agents are working autonomously, how should they coordinate, delegate, and escalate?

## Agent Coordination

### Parallel Work (from P8)

When an orchestrator delegates work to multiple agents:

1. **Launch all agents** with clear, bounded tasks
2. **Wait for ALL to complete** before synthesis — no partial data, no "I'll do it myself"
3. **Read ALL outputs** before writing synthesis
4. **Reference agent findings** in the final output — if an agent's output isn't referenced, the delegation was pointless

**Violation**: Orchestrator writes output while agents are running. This is the P8 violation — never bypass a running process.

### Sequential Work

When tasks have dependencies:

1. Complete task A fully before starting task B
2. Verify task A's output before passing to task B
3. If task A fails, don't start task B — escalate

### Delegation Boundaries

When spawning a sub-agent:

1. **Provide complete context** — the sub-agent hasn't seen the conversation
2. **Bound the scope** — tell the agent exactly what files/topics it owns
3. **Expect structured output** — tell the agent what format to return
4. **Don't duplicate work** — if you delegated it, don't also do it yourself

## Agent Escalation

### When to Escalate to Human (from HUMAN-AI Principle 5)

| Situation | Action |
|-----------|--------|
| Missing information needed for a process step | ASK. Don't guess. Don't write "TBD." |
| Conflicting requirements | ASK. Present the conflict. Don't silently pick one. |
| Security-sensitive change | ASK. Even if you're confident. |
| Business decision (pricing, partnerships, legal) | ASK. Always. |
| Taste decision (design, brand, voice) | ASK. Data doesn't override taste. |
| Blocked by external dependency | REPORT. State what's blocked and what you tried. |
| 3 failed attempts at the same task | STOP. Escalate with what you tried and why it failed. |

### When NOT to Escalate

| Situation | Action |
|-----------|--------|
| Choosing which file to edit | Just do it. This is HOW, not WHAT. |
| Choosing which tool/skill to use | Just do it. Agent owns execution. |
| Fixing a typo or obvious bug | Just do it. Commit and move on. |
| Following a defined process step | Just do it. The process was already approved. |

## Agent Self-Assessment (from HUMAN-AI Principle 3)

Before foundational work (creating ARCHITECTURE, DESIGN, FRAMEWORK, PROCESS docs):

1. **Ask yourself**: "Does my training data cover this well, or do I need to research?"
2. **If unsure**: Research first. WebSearch, read reference docs, check what exists.
3. **Create the marker**: After research, create `.enforcement/research-done`
4. **Then proceed**: With evidence, not guesses.

## Agent Authority Hierarchy

```
CEO of Asawa    → Full authority everywhere
CEO of Sutra    → Sutra files + client feedback + version updates
CEO of {Company} → Company files only + feedback-to-sutra/
Department agents → Within their department scope only
Sub-agents       → Within the task they were delegated
```

No agent modifies a layer above itself without going through the feedback protocol.

## Depth-Based Agent Behavior

The Adaptive Protocol Engine (PROTO-000) depth assessment modulates how strictly agents follow protocols.

| Depth | Agent Behavior |
|-------|---------------|
| 1 (Surface) | Execute directly. No coordination, no delegation, no escalation unless blocked. |
| 2 (Considered) | Execute with lightweight self-assessment. Escalate only on uncertainty. |
| 3 (Thorough) | Follow full protocol: coordination rules, delegation boundaries, escalation table. |
| 4 (Rigorous) | Full protocol + structured output for every sub-agent + post-task audit. |
| 5 (Exhaustive) | Full protocol + cross-agent dependency analysis + authority hierarchy enforcement + incentive conflict resolution. |

**Rule**: Depth 1-2 agents act autonomously within their scope. Depth 3+ agents follow the coordination, escalation, and delegation rules defined above.

---

## Agent Incentive Awareness

Each department agent has an incentive (from holding/AGENT-INCENTIVES.md). Productive tension happens when incentives conflict:

- Growth wants to launch → Legal wants privacy policy first → **Legal wins** (compliance > speed)
- Product wants features → Quality wants tests → **Depends on tier** (Trivial: skip tests, Standard+: tests required)
- Speed wants to ship → Documentation wants completeness → **Speed wins for V1** (ship, then document)

The resolution isn't random — it follows the company's stage, tier, and the reversibility of the decision.
