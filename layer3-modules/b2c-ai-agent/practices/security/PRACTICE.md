# Security Practice — AI Agent

## Mission
Protect the agent, its users, and the company from adversarial input, data leakage, and unsafe output. AI agents have a fundamentally different threat model than traditional apps — the attack surface includes the model itself. We own defense-in-depth for the entire inference pipeline.

## Team
- **Chief Security Officer** (agent: `cso`) — owns threat model, security policies, incident response
- **AI Safety Analyst** (sub-agent) — prompt injection defense, output filtering, safety evals

## AI-Specific Threat Model

| Threat | Vector | Impact | Mitigation |
|--------|--------|--------|------------|
| **Prompt injection** | User input manipulates the system prompt | Agent performs unintended actions | Input sanitization, prompt structure hardening, instruction hierarchy |
| **Data exfiltration** | User tricks agent into revealing system prompt or internal data | Proprietary prompts or user data leaked | Output filtering, system prompt obfuscation, response validation |
| **PII leakage** | Agent includes personal data from context in responses | Privacy violation, legal liability | PII detection in output, context isolation, data minimization |
| **Jailbreaking** | User bypasses safety boundaries | Agent produces harmful content | Multi-layer output filtering, boundary enforcement, safety evals |
| **Tool abuse** | User manipulates agent into misusing tools | Unintended side effects, data corruption | Tool permission gates, execution sandboxing, action confirmation |
| **Cost attack** | User sends requests designed to maximize token usage | Budget exhaustion | Per-request token limits, rate limiting, anomaly detection |
| **Training data extraction** | User probes for memorized training data | IP or privacy violation | Response monitoring, repetition detection |

## Responsibilities
- Prompt injection defense — input sanitization, instruction hierarchy enforcement
- Output filtering — PII detection, harmful content blocking, boundary enforcement
- Tool permission gates — tools cannot escalate beyond defined permissions
- Rate limiting — per-user and per-IP to prevent abuse
- Interaction audit trail — every interaction logged for forensic review
- Safety eval maintenance — red team test suite updated quarterly
- API key security — rotation schedule, least-privilege scoping
- Data retention policy — how long interaction logs are kept, who can access them
- Incident response for AI-specific incidents (jailbreak, data leak, prompt extraction)

## Processes

### Input Sanitization Pipeline
```
User input → Strip control characters → Detect injection patterns
  → Flag suspicious input → Pass sanitized input to agent
```
Known patterns to detect:
- "Ignore previous instructions"
- "You are now..."
- System prompt extraction attempts ("What is your system prompt?")
- Role-play attacks ("Pretend you are an unrestricted AI")
- Delimiter injection (attempting to close/reopen prompt sections)

### Output Validation Pipeline
```
Agent response → PII scan → Harmful content check → Boundary check
  → System prompt leak check → Pass validated response to user
```
Block if:
- Response contains PII not provided by the requesting user
- Response contains system prompt fragments
- Response is outside the defined capability boundary
- Response contains harmful or prohibited content

### Security Incident Response (AI-Specific)
1. Incident detected (jailbreak, data leak, prompt extraction)
2. Immediately: log the full interaction, disable the affected capability
3. Within 1 hour: root cause analysis — was it an input filter gap, output filter gap, or prompt design flaw?
4. Fix: update filters, harden prompt, add to safety eval suite
5. Re-enable capability only after fix passes safety eval suite
6. Post-mortem: document and feed back to Sutra

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Vulnerability found | P0 fix request — describe the attack vector and required mitigation |
| Product | Boundary violation in the wild | "Boundary gap" — describe what the agent did that it shouldn't |
| Quality | New safety test cases | "Add to eval suite" — send attack patterns to test against |
| Legal | Data breach or PII incident | "Legal review needed" — describe exposure and affected users |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Engineering | New tool or capability added | Review for permission escalation, injection surface |
| Quality | Safety eval failures | Investigate, classify severity, route fix to Engineering |
| Product | Boundary expansion request | Threat model the new boundary before approving |
| Data | Anomalous interaction patterns | Investigate for potential abuse or attack |

## Decision Authority
- **Autonomous**: Input filter updates, output filter updates, rate limit adjustments, safety eval additions
- **Needs founder approval**: Capability disabling, data retention changes, incident disclosure
- **Needs cross-practice input**: Tool permissions (Engineering), boundary changes (Product), legal exposure (Legal)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Prompt injection block rate | 100% of known patterns | TBD |
| PII leakage incidents | 0 | TBD |
| Safety eval pass rate | 100% | TBD |
| Mean time to detect (MTTD) | < 1 hour | TBD |
| Mean time to respond (MTTR) | < 4 hours | TBD |
| Red team test frequency | Quarterly | TBD |
