# Eval E3 — Regulated System (constraint-driven design)

## Input

> Architect a payments aggregator for the Indian digital lending market. Subject: a service that orchestrates loan application flow across multiple lender APIs (HDFC, ICICI, Bajaj, etc.), pulls credit bureau data (CIBIL), persists application + decision records, and emits webhook notifications to a partner app. Scale targets: 100K applications/month, p95 < 2s for the lender-quote step, 7 years of record retention per RBI mandate. Constraints: RBI compliance (data localization in India), DPDP Act compliance (consent management), 4 engineers, 9-month MVP. Risk profile: regulated FinTech with PII + financial data.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 8 main sections emitted | grep section headings |
| 2 | RBI data-localization constraint appears in at least one ADR + shapes at least one Container choice (e.g., region-locked database, India-region cloud) | section 3 + section 5 |
| 3 | DPDP Act consent management addressed as a Container or Component (consent ledger, audit log) | section 3 or 4 |
| 4 | At least one ADR explicitly addresses a regulatory tradeoff (e.g., self-hosted vs managed DB, audit log retention strategy) | section 5 |
| 5 | STRIDE threat model includes ≥1 entry specific to the lending flow (e.g., loan-decision tampering, applicant identity spoofing, repudiation of consent grant) | section 6 |
| 6 | Threat model addresses repudiation specifically (R in STRIDE) given regulatory audit requirements — append-only / signed actions | section 6 |
| 7 | Scaling axes section addresses geography axis with India-only constraint declared (not generic multi-region) | section 7 |
| 8 | Scaling axes addresses data axis with 7-year retention storage growth projection | section 7 |
| 9 | Sutra D38 Build-Layer table classifies the credit-bureau adapter and lender-API adapters appropriately (likely L1 if generalizable across regulated markets, L2 if India-specific) — with rationale referencing the regulatory scope | section 8 |
| 10 | At least one open question or assumption acknowledged about regulatory interpretation (the skill should not pretend to be a compliance lawyer) | end of document |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Multi-region / global-distribution architecture (violates RBI data-localization constraint)
- Microservices proposed for a 4-engineer team with 9-month deadline (taste violation)
- Mock STRIDE entries that don't reference the lending domain
- ADR consequences sections that ignore regulatory tradeoffs ("all upside" when the regulation actually forces a hard choice)
- Build-Layer table that puts everything as L0 (taste violation: lender-API adapters are at minimum L1 given they need promotion across markets)
- Generic security recommendations instead of STRIDE-letter-specific entries

## Baseline comparison

Without the skill, Claude typically:
- Lists generic FinTech patterns without grounding them in RBI/DPDP specifics
- Misses repudiation as a first-class threat
- Doesn't address the 7-year retention as a scaling-axis trigger
- Doesn't surface regulatory tradeoffs in ADR consequences

Skill should win on assertions 2, 3, 4, 6, 8 vs baseline. This is the eval that exercises the "constraint shapes architecture" discipline most strongly.
