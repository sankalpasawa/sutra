# Engineering Practice — AI Agent

## Mission
Build reliable, cost-efficient, safe agent infrastructure. Prompt engineering, tool definitions, LLM integration, and fallback chains are first-class engineering artifacts. We own the HOW — architecture, model selection, cost optimization, and the entire inference pipeline.

## Team
- **Chief Technology Officer** (agent: `cto`) — owns architecture, model strategy, cost optimization
- **Prompt Engineer** (sub-agent) — system prompts, few-shot examples, eval-driven iteration
- **Tool Engineer** (sub-agent) — tool definitions, action execution, sandboxing
- **Infrastructure Lead** (sub-agent) — hosting, API gateway, caching, observability

## Sub-Teams

### Prompt Engineering
- System prompt design and versioning (prompts are code — they live in version control)
- Few-shot example curation for each capability
- Prompt compression — achieve same quality with fewer tokens
- Context window management — what goes in, what gets truncated, in what order
- Eval-driven iteration — every prompt change is tested against the eval suite before deploy

### Tool/Action Layer
- Tool schema definitions (typed input/output contracts)
- Tool execution sandboxing — tools cannot escalate privileges
- Tool orchestration — multi-step tool chains, parallel tool calls
- Error handling — structured errors that the agent can reason about
- Tool description optimization — the description IS the prompt for tool selection

### LLM Integration
- Model selection and fallback chains (primary → fallback → graceful error)
- API client with retry logic, timeout handling, streaming support
- Token counting and budget enforcement per request
- Response parsing and validation (structured output when possible)
- Provider abstraction — swap models without changing application code

### Infrastructure
- Hosting and deployment (serverless preferred for cost control)
- Request/response logging (every interaction, full fidelity)
- Caching layer (exact match + semantic similarity cache)
- Rate limiting (per-user and global)
- Cost monitoring and alerting

## Responsibilities
- Prompt versioning and deployment (prompts are deployed artifacts, not config)
- Model selection based on capability requirements vs cost constraints
- Fallback chain design — the agent must never return a raw API error
- Token budget management — max_tokens, context truncation, response limits
- Tool schema enforcement — strict typing, no untyped tool calls
- Interaction logging — prompt, response, model, tokens, cost, latency for every call
- Cost optimization — caching, model routing, prompt compression
- Streaming implementation — first token latency matters more than total latency

## Architecture Rules (Enforced)
1. **Prompts are code.** Version controlled, reviewed, tested. Never edited in production.
2. **Tools are typed contracts.** Input schema, output schema, description. No untyped tool calls.
3. **Fallback is mandatory.** Every LLM call has: primary model → fallback model → cached/default response.
4. **Cost ceiling is a hard constraint.** If a request would exceed the per-interaction budget, use a cheaper model or return a cached response.
5. **Provider abstraction.** Application code calls an internal API. The model behind it can change without code changes.
6. **Log everything.** Every LLM call: model, prompt hash, response, tokens in/out, cost, latency, cache hit/miss.

## Processes

### Prompt Change Flow
1. Draft new prompt version in version control
2. Run eval suite against new prompt (all existing test cases)
3. Compare: accuracy, cost, latency vs current prompt
4. If regression on any metric: investigate before proceeding
5. Deploy to staging (shadow mode — log but don't serve to users)
6. Promote to production after 24h with no regressions
7. Keep previous prompt version tagged for instant rollback

### Model Migration
1. New model available — run full eval suite
2. Compare: accuracy, cost, latency, safety evals
3. If better on all axes: migrate
4. If tradeoff: document the tradeoff, get founder approval
5. Deploy as fallback first, promote to primary after validation

### Cost Spike Response
1. Alert fires at 80% of monthly budget
2. Investigate: which capability is expensive? Which users?
3. Immediate: enable aggressive caching, route to cheaper model
4. If structural: redesign the capability (fewer tokens, simpler prompt)
5. Hard stop at 100% budget — return cached/default responses only

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Quality | Prompt change deployed | "Run evals" — send new prompt version + eval suite |
| Security | New tool or data access added | "Security review" — describe new attack surface |
| Product | Technical constraint on capability | "Scope adjustment" — propose alternative approach |
| Data | New interaction logging schema | "Schema update" — describe new fields |
| Operations | Cost spike or infrastructure issue | "Alert" — describe issue and mitigation |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Product | Capability spec with eval cases | Estimate effort, design prompt + tools, implement |
| Quality | Eval failures or regressions | Root cause analysis, prompt fix or tool fix |
| Security | Prompt injection vulnerability | P0 fix — add input filtering or prompt hardening |
| Data | Cost anomaly or latency spike | Investigate, optimize, report back |
| Operations | Infrastructure issue | Fix, document, add monitoring |

## Key Artifacts
- `prompts/` — versioned system prompts and few-shot examples
- `tools/` — tool schema definitions
- `evals/` — eval test suites (input/expected-output pairs)
- `src/lib/ai.ts` — LLM provider abstraction
- `src/lib/tools.ts` — tool execution layer
- `ARCHITECTURE.md` — agent architecture document

## Decision Authority
- **Autonomous**: Prompt wording (within approved capability), caching strategy, model fallback order, code refactoring
- **Needs founder approval**: Model changes (primary), new tool creation, cost ceiling changes, new data access
- **Needs cross-practice input**: Capability scope (Product), safety implications (Security), eval criteria (Quality)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Eval pass rate | > 95% | TBD |
| Cost per interaction | Below ceiling | TBD |
| First token latency (P95) | < 1s | TBD |
| Total response latency (P95) | < 5s | TBD |
| Fallback trigger rate | < 5% | TBD |
| Cache hit rate | > 30% | TBD |
| Prompt version rollback rate | < 10% | TBD |
