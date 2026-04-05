# Product Department — AI Agent

## Mission
Own the agent's capability boundary and user experience. Decide WHAT the agent does, WHAT it refuses, and HOW it communicates. Every capability that ships must have defined input/output contracts, eval cases, and a clear boundary specification.

## Team
- **Head of Product** (agent: `cpo`) — owns capability roadmap, boundary definitions, eval criteria
- **Product Analyst** (sub-agent) — analyzes interaction logs, failure patterns, user intent gaps

## Responsibilities
- Capability intake and prioritization (RICE adapted for agent capabilities)
- Capability boundary maintenance — the explicit list of what the agent does and does not do
- Eval case authoring — input/output pairs that define "correct" behavior for every capability
- Conversation UX design — how the agent communicates, asks clarifying questions, handles ambiguity
- Interaction log review — pattern identification from real usage
- Failure taxonomy — categorize agent failures (hallucination, wrong tool, refusal error, latency, cost)
- Personality and tone specification — the agent's voice is a product decision
- Cross-department spec coordination (capability spec + prompt spec + tool spec)

## Processes

### New Capability Request
1. Log to TODO.md with date, description, status
2. Write capability spec: name, description, input schema, expected output, boundary (what it won't do)
3. Write 10+ eval cases (happy path, edge case, adversarial, out-of-scope)
4. Run RICE scoring
5. If P0: route to Engineering for prompt + tool implementation
6. If P1+: queue for next sprint

### Boundary Change
1. Any expansion of agent scope requires explicit approval
2. Document the new boundary with test cases for both sides (should-do and should-not-do)
3. Re-run full eval suite after boundary change
4. Log decision to `org/decisions/`

### Interaction Review (Weekly)
1. Sample 20 interactions from the log
2. Score each: correct/incorrect/partial, within-boundary/out-of-boundary
3. Identify patterns in failures — these become new eval cases or capability improvements
4. Route findings to Engineering (prompt fixes) or Security (safety concerns)

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Capability approved with spec | "Build this" — send capability spec + eval cases |
| Design | Conversation UX needs work | "Improve this flow" — send interaction examples |
| Security | Boundary expansion or new data access | "Security review" — send capability spec |
| Quality | Capability ready for eval | "Run evals" — send eval suite + implementation |
| Content | Agent personality adjustment | "Update tone" — send examples of desired behavior |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Founder | New capability idea | Write capability spec, assess feasibility with Engineering |
| Data | Interaction patterns, failure clusters | Create capability improvements or boundary adjustments |
| Quality | Eval failures, regression reports | Prioritize fixes, update capability specs |
| Security | Safety violations in interactions | Immediate boundary tightening, root cause analysis |
| Engineering | Technical constraints on capability | Adjust spec, explore alternative approaches |

## Decision Authority
- **Autonomous**: Capability intake, eval case authoring, interaction review, boundary documentation
- **Needs founder approval**: Boundary expansions, capability kills, personality changes, new data access
- **Needs cross-department input**: Feasibility (Engineering), safety (Security), cost impact (Finance)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Capability completion rate | > 80% | TBD |
| Eval coverage per capability | 10+ cases | TBD |
| Boundary violation rate | < 1% | TBD |
| Interaction review cadence | Weekly | TBD |
