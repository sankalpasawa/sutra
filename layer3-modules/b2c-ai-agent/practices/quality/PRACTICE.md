# Quality Practice — AI Agent

## Mission
Ensure the agent is accurate, reliable, safe, and cost-efficient. Quality for AI agents is eval-driven — not manual testing. We own the eval suites, run them on every prompt or tool change, and block deploys that regress.

## Team
- **Head of Quality** (agent: `qa_lead`) — owns eval strategy, regression gates, quality metrics
- **Eval Engineer** (sub-agent) — maintains eval suites, analyzes failures, writes new test cases

## How AI Agent QA Differs from App QA
Traditional app QA tests deterministic behavior (click X, expect Y). Agent QA tests probabilistic behavior — the same input can produce different outputs. This requires:
- **Eval suites** instead of unit tests (statistical pass rates, not binary pass/fail)
- **Boundary testing** (does the agent correctly refuse out-of-scope requests?)
- **Adversarial testing** (does the agent withstand prompt injection, jailbreaking?)
- **Cost testing** (does the interaction stay within budget?)
- **Regression tracking over time** (quality can drift without code changes due to model updates)

## Responsibilities
- Eval suite authorship and maintenance (10+ test cases per capability, 50+ total before Stage 2)
- Regression detection — run evals on every prompt change, tool change, or model update
- Boundary eval — test cases for things the agent should refuse
- Safety eval — adversarial inputs, prompt injection patterns, PII probing
- Cost eval — verify interactions stay within per-request and monthly budgets
- Latency eval — response times meet SLA (first token < 1s, total < 5s)
- Deploy gate — no prompt or tool change ships without passing the eval suite
- Failure analysis — categorize failures (hallucination, wrong tool, refusal error, timeout, cost overrun)

## Eval Suite Structure

```
evals/
├── capabilities/
│   ├── {capability-1}.jsonl   # Input/expected-output pairs for capability 1
│   ├── {capability-2}.jsonl   # Input/expected-output pairs for capability 2
│   └── ...
├── boundary/
│   └── out-of-scope.jsonl     # Inputs the agent MUST refuse
├── safety/
│   ├── prompt-injection.jsonl # Known injection patterns
│   ├── pii-probing.jsonl      # Attempts to extract PII
│   └── jailbreak.jsonl        # Jailbreak attempts
├── cost/
│   └── budget-limits.jsonl    # Inputs that should stay under cost ceiling
└── regression/
    └── golden-set.jsonl       # Stable set of 50+ cases that must always pass
```

Each `.jsonl` file contains lines of:
```json
{"input": "user message", "expected": "correct response or pattern", "type": "exact|contains|regex|semantic", "tags": ["p0", "happy-path"]}
```

## Processes

### Eval Run (on every prompt/tool/model change)
1. Engineering submits change + declares affected capabilities
2. Quality runs eval suite for affected capabilities + full regression suite
3. Results: pass rate, regressions (cases that used to pass but now fail), improvements
4. If regression on any P0 capability: BLOCK deploy
5. If regression on P1+ only: flag, document, founder decides
6. If all pass: approve deploy

### Weekly Eval Review
1. Run full eval suite (all capabilities, boundary, safety, cost)
2. Compare to last week: any drift? (model provider updates can cause silent regression)
3. Review interaction logs for new failure patterns not covered by existing evals
4. Write new eval cases for discovered gaps
5. Report: pass rates by category, cost trends, latency trends

### Failure Taxonomy
Every failure is classified:
| Category | Description | Severity |
|----------|------------|----------|
| **Hallucination** | Agent states something false with confidence | P0 |
| **Wrong tool** | Agent selects the wrong tool for the task | P0 |
| **Refusal error** | Agent refuses a valid in-scope request | P1 |
| **Boundary failure** | Agent accepts an out-of-scope request | P0 |
| **Safety failure** | Agent outputs harmful/leaked content | P0 |
| **Cost overrun** | Interaction exceeds budget | P1 |
| **Latency violation** | Response exceeds SLA | P2 |
| **Formatting error** | Response is correct but poorly formatted | P2 |

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Eval failure on deploy | "Blocked — regression on {capability}" with failure details |
| Product | Pattern of user-facing failures | "Capability gap" — users expect X but agent can't do it |
| Security | Safety eval failure | "Safety incident" — describe the attack pattern that passed |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Engineering | Prompt/tool/model change submitted | Run eval suite, report results |
| Product | New capability spec with eval cases | Add to eval suite, verify coverage |
| Security | New attack patterns discovered | Add to safety eval suite |
| Data | Interaction log anomalies | Write new eval cases for uncovered patterns |

## Decision Authority
- **Autonomous**: Eval case authoring, regression reports, failure classification, eval suite organization
- **Needs founder approval**: Deploy blocks on non-P0 regressions, quality bar adjustments
- **Needs cross-practice input**: Eval criteria (Product), attack patterns (Security), feasibility of fix (Engineering)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Eval coverage (cases per capability) | 10+ | TBD |
| Overall eval pass rate | > 95% | TBD |
| Safety eval pass rate | 100% | TBD |
| Boundary eval pass rate | 100% | TBD |
| Regression rate per deploy | 0 | TBD |
| Time to write evals for new capability | < 2 hours | TBD |
| Weekly eval review cadence | 100% | TBD |
