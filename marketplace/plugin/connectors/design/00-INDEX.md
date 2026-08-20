# GitHub Connector — Architecture Pack

**Phase**: architecture (implementation follows founder review — founder chose architecture-first, 2026-08-20).
**Decision of record**: [ADR-034](../../../../os/decisions/ADR-034-connector-token-ownership.md) — the Connector Service is the only confidential client.
**Verification stance**: every GitHub behavioural claim in this pack was fetched from docs.github.com on 2026-08-20 and is tagged `F1`–`F7` (table in ADR-034) or cited inline. Claims sourced from memory rather than docs are marked **[unverified]**. There are none as of this revision.

## Reading order

| # | File | Deliverables covered (founder brief §46) |
|---|---|---|
| 1 | [01-architecture.md](01-architecture.md) | 1 product · 2 component · 3 OAuth · 4 callback · 5 sequence diagrams |
| 2 | [02-data-model.md](02-data-model.md) | 6 connector lifecycle · 7 database schema · 8 credential architecture |
| 3 | [03-github-integration.md](03-github-integration.md) | 9 GitHub API integration · 10 repository discovery · 11 organization discovery |
| 4 | [04-capabilities-agent.md](04-capabilities-agent.md) | 12 capability model · 13 agent tool architecture · 14 agent authorization · 15 human approval |
| 5 | [05-api-contracts.md](05-api-contracts.md) | 16 backend API contracts · 17 desktop API contracts |
| 6 | [06-security.md](06-security.md) | 18 threat model · 19 prompt-injection defences |
| 7 | [07-operations.md](07-operations.md) | 20 rate limits · 21 caching · 22 audit architecture · 23 observability |
| 8 | [08-delivery.md](08-delivery.md) | 24 testing · 26 deployment · 27 production security checklist · 28 troubleshooting |

Deliverable **25 (complete implementation)** is in progress: **P1–P3 have shipped**
(lifecycle, discovery, permission layer, panel surface). P4–P7 — the agent tool
gateway, approval cards, rate budgets and the CI security gate — have not.
`08-delivery.md §8.6` carries the phase table and, more usefully, the explicit
list of what P1–P3 do *not* yet give you.

## The five claims this pack rests on

If any of these is wrong, re-read before building.

1. **PKCE does not make a desktop app a public client on GitHub.** `client_secret` remains required for the web-flow code exchange (F2). Only the device flow is secret-free (F3).
2. **Device-flow tokens refresh without a secret** (F4). So a secret-less client gets the full 8h/6-month lifecycle, not a degraded one.
3. **Installation tokens need the app's RSA private key** (F6). Therefore user-absent background work is impossible in a local-only deployment, and we say so rather than fake it.
4. **A GitHub App's per-repository permissions are the only honest basis for "read-only on repo X."** An OAuth App `repo` scope cannot express it.
5. **The model never decides authorization and never names the connector.** Both are bound server-side. Everything in `04` and `06` depends on this.
