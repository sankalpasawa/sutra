# B2C AI Agent — Stage 1: Pre-Launch (1 person, 0 users)

This is the minimal operating system for an AI agent product at the earliest stage. Everything else in Sutra is future. Use THIS file.

An AI agent is fundamentally different from a consumer app. The product IS the model behavior — prompts, tool use, safety boundaries, and fallback logic are first-class engineering artifacts, not backend utilities. Cost accrues per interaction, not per deploy. Failures are probabilistic, not deterministic. This template accounts for all of that.

## What You Need Right Now (and nothing else)

### Before Building Anything
1. **One sentence**: What does this agent do and who does it serve? Define the agent's job in terms the user would use, not the LLM's capabilities.
2. **Capability boundary test**: List 5 things the agent DOES and 5 things it explicitly DOES NOT. If the boundary is fuzzy, the agent will hallucinate scope.
3. **P0 only**: What is the smallest set of capabilities that tests the core hypothesis? A single well-executed tool is better than five mediocre ones.

### When Building
4. **Prompt engineering is product work.** System prompts, few-shot examples, and tool definitions are product specs. Version them. Review them. Test them against edge cases.
5. **One capability at a time.** Build one tool/action, verify it works across 20+ varied inputs, then move to the next. Do not build the second tool until the first is reliable.
6. **Cost ceiling before code.** Set a max cost-per-interaction (e.g., $0.02) and a max monthly budget. Architect around these constraints — model selection, caching, token limits.
7. **Intent + boundaries** for every task: what outcome, what constraints, method is free.

### After Building
8. **Does it handle the unhappy path?** Feed it ambiguous inputs, contradictory instructions, edge cases, and adversarial prompts. The agent must degrade gracefully, not hallucinate.
9. **Does the output match the quality bar?** Run the 5 sensors from PRODUCT-KNOWLEDGE-SYSTEM.md adapted for agent output (see Sensors below).
10. **Log every interaction.** Prompt, response, latency, token count, cost. This is your telemetry — you cannot improve what you cannot see.

### Weekly
11. **What capabilities shipped?** List agent behaviors that are production-ready.
12. **What failed?** Hallucinations, wrong tool calls, safety violations, cost spikes. Feed back to Sutra as learning.
13. **What's next?** Top 3 items from TODO.md.
14. **Cost review.** Total spend, cost-per-interaction trend, model usage breakdown.

## Functions Active at This Stage

| Function | What it does now | What it does NOT do yet |
|----------|-----------------|----------------------|
| **Product** | Define agent capabilities. Define what the agent refuses. Maintain the capability boundary. | User research (no users yet) |
| **Design** | Conversation UX. Response formatting. Error message copy. Loading states. | Design system documentation (conversation UI is the design system) |
| **Engineering** | Prompt engineering. Tool definitions. LLM integration. Fallback chains. | CI/CD, monitoring, multi-model orchestration |
| **Security** | Don't expose API keys. Input sanitization. Prompt injection defense. Output filtering. PII handling. | Pen testing, SOC2, red-teaming at scale |
| **Quality** | Run eval suites. Test edge cases. Measure hallucination rate. Cost tracking. | Automated regression suite, A/B prompt testing |
| **Growth** | Not yet. Ship first. | Everything |
| **Data** | Log all interactions (prompt, response, tokens, cost, latency). | Dashboards, cohort analysis, feedback loops |
| **Ops** | Git push. Deploy to hosting. LLM API key management. | Multi-environment, auto-scaling, rate limiting |
| **Content** | Agent personality. System prompt tone. Error messages that help. | Documentation, changelog, marketing copy |
| **Finance** | Cost-per-interaction tracking. Monthly budget enforcement. Don't run out of money. | Unit economics, pricing model, margin analysis |
| **Legal** | AI usage disclosure. Data retention policy. Terms of service. | IP ownership, liability framework, compliance audit |

## The Only Process

```
CAPABILITY IDEA → Does it pass the boundary test? → Is it P0?
  YES → Define expected behavior (input/output pairs)
      → Write system prompt + tool definition
      → Test against 20+ inputs (including adversarial)
      → Measure: accuracy, latency, cost, safety
      → Does it degrade gracefully on bad input?
      → Commit → Push → Log metrics
  NO  → Add to TODO.md for later
```

## AI Agent-Specific Processes

### Prompt Lifecycle
Prompts are versioned artifacts. Every prompt change follows:
```
DRAFT → TEST (20+ inputs) → REVIEW (check edge cases) → DEPLOY → MONITOR (cost + quality)
```
Never deploy a prompt change without testing it against the existing eval set first.

### Model Selection
| Decision | Criteria |
|----------|----------|
| **Which model?** | Capability needed vs cost ceiling. Use the cheapest model that meets the quality bar. |
| **When to upgrade?** | When the current model fails >10% of eval cases on a P0 capability. |
| **When to downgrade?** | When cost exceeds budget and a cheaper model passes >95% of evals. |
| **Fallback chain** | Primary model → fallback model → graceful error. Never return a raw API error to the user. |

### Cost Management
| Control | Implementation |
|---------|---------------|
| **Token budget per request** | Set max_tokens. Truncate context if needed. |
| **Monthly spend cap** | Track cumulative cost. Alert at 80%. Hard stop at 100% (return cached/default response). |
| **Caching** | Cache identical or near-identical requests. Use semantic similarity for cache hits. |
| **Model routing** | Route simple requests to cheaper models. Reserve expensive models for complex reasoning. |

### Safety & Alignment
| Layer | What it does |
|-------|-------------|
| **Input filtering** | Reject prompt injection patterns. Sanitize user input before it enters the system prompt. |
| **Output filtering** | Check agent responses for PII leakage, harmful content, off-topic drift. |
| **Capability boundary** | The agent must refuse requests outside its defined scope. "I can't help with that" is a feature. |
| **Fallback behavior** | When the model is uncertain, return a safe default rather than a confident wrong answer. |
| **Audit trail** | Every interaction is logged: who asked, what was asked, what was returned, what was filtered. |

### Tool/Action Architecture
| Principle | Why |
|-----------|-----|
| **Tools are typed contracts** | Every tool has an input schema, output schema, and description. The LLM selects tools based on these contracts. |
| **One tool, one job** | Do not build multi-purpose tools. A tool that "searches and summarizes" should be two tools. |
| **Tools fail explicitly** | Return structured errors, not empty results. The agent needs signal to decide what to do next. |
| **Tool execution is sandboxed** | Tools cannot modify system state without explicit permission gates. |
| **Tool descriptions are prompts** | The description string is the primary way the LLM understands when to use a tool. Write it like a product spec. |

## Agent Quality Sensors (adapted from PRODUCT-KNOWLEDGE-SYSTEM.md)

| Sensor | What it checks | Pass criteria |
|--------|---------------|---------------|
| **Accuracy** | Does the agent return correct information? | >90% correct on eval set |
| **Boundary** | Does the agent refuse out-of-scope requests? | 100% refusal on boundary test set |
| **Latency** | Response time for the user | P95 < 5 seconds (streaming first token < 1s) |
| **Cost** | Per-interaction cost | Below cost ceiling |
| **Safety** | No PII leakage, no harmful output, no prompt injection passthrough | 100% pass on safety eval set |
| **Graceful degradation** | Agent behavior on API failure, timeout, or ambiguous input | Never returns raw error. Always returns helpful fallback. |

## Stage Graduation Criteria

**Stage 1 → Stage 2** (when ALL of these are true):
- Agent deployed and accessible to users
- 25+ active users
- Interaction logging live (prompt, response, cost, latency)
- Eval suite with 50+ test cases across all P0 capabilities
- Cost-per-interaction stable and within budget
- Safety eval passing at 100%
- Terms of service and AI disclosure published

**Stage 2 will add**: user feedback loops, A/B prompt testing, multi-model routing, conversation memory optimization, retention tracking, weekly eval review.

**Stage 3+ is documented in Sutra but not loaded until earned.**

## Feedback to Sutra

When the company discovers something that Sutra should learn:
1. Write a short note in `feedback-to-sutra/`
2. Format: what happened, what principle was missing or wrong, what we learned
3. Sutra picks this up and updates its layers

Examples of feedback:
- "The LLM hallucinated a tool call that doesn't exist. Sutra needs a principle about strict tool schema enforcement."
- "Cost spiked 3x when users started sending long context. Sutra needs a principle about input truncation strategies."
- "The fallback chain failed silently. Sutra needs observability requirements for fallback behavior."
- "Prompt injection via user input bypassed the system prompt. Sutra needs defense-in-depth for prompt construction."
