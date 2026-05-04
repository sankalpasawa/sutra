# Eval E1 — Greenfield SaaS (B2B, blank slate)

## Input

> Architect a B2B SaaS for engineering team retrospectives. Subject: a web app where engineering managers schedule weekly retros, the team submits anonymous feedback before the meeting, and the retro session surfaces themes via lightweight clustering. Scale targets: 500 paying companies, ~5K monthly active users, ~50K feedback items/month at maturity, p95 < 300ms for the dashboard. Constraints: needs SOC2 readiness within 12 months, 3 engineers, 6-month MVP deadline, TypeScript + React + Postgres preferred. Risk profile: B2B with PII (employee feedback).

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 8 main sections emitted (no silent omission; placeholder line if any section truly N/A) | grep section headings |
| 2 | C4 Level 1 explicitly names users (engineering manager / team member), external systems (auth provider, email/Slack notification destination), and "our system" | section 2 |
| 3 | C4 Level 2 enumerates containers (e.g., web app, API, database, background worker, notification service) — each with a deployment story | section 3 |
| 4 | C4 Level 3 emitted for 1-3 containers with non-obvious internal complexity (e.g., the clustering / theme-surfacing logic); rest get a placeholder line | section 4 |
| 5 | ADRs cover at least one of: data model (anonymous feedback storage), auth choice, hosting / deployment target, framework choice rationale | section 5 |
| 6 | Each ADR has a non-empty Consequences section with at least one "harder" or "locked in" item | section 5 |
| 7 | STRIDE threat model includes a SYSTEM-SPECIFIC entry for at least 3 of the 6 letters (not generic STRIDE boilerplate) | section 6 |
| 8 | Threat model addresses anonymity guarantee (since feedback is anonymous and PII-adjacent) | section 6 |
| 9 | Scaling axes section addresses load + data + team + geography (each with a target or "n/a today, watch for X") | section 7 |
| 10 | Sutra D38 Build-Layer table classifies each container into L0 / L1 / L2 with rationale; L1/L2 entries have promotion deadline or instance-only reason | section 8 |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Generic ADRs like "Use SQL database" without specifying which DB and why
- Microservices proposed for a 3-engineer team with 6-month MVP deadline (taste violation)
- ADR Consequences sections that are all upside ("decision makes everything easier") — those aren't real choices
- Threat model that lists generic STRIDE definitions instead of system-specific risks
- C4 L3 emitted for every container (over-decomposition)
- Build-layer table with every component as L0 without justification (build-layer cosplay)

## Baseline comparison

Without the skill, Claude typically:
- Produces a flat description without the 4-level C4 hierarchy
- Lists components without a deployment story
- Skips ADRs or produces ADR templates without Consequences
- Does generic security advice instead of STRIDE
- Doesn't address Sutra D38 build-layers at all

Skill should win on assertions 2, 4, 6, 7, 10 vs baseline.
