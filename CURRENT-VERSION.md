# Sutra — Current Version

## v1.7 (2026-04-06)

- **ADAPTIVE-PROTOCOL.md v3**: "Gear" renamed to "Depth" (customer focus). 5 depth levels (1-5) controlling task decomposition granularity. Speed vs precision as governing trade-off. Company size no longer determines depth. Progressive OS merged as Company State.
- **P9 principle**: Structure adapts, content is configurable. Don't hardcode values that vary by company.
- **Task-to-protocol conversion**: LEARN phase now converts solved tasks into reusable protocols. First time = problem-solving. Second time = follow the protocol.
- **PROTO-013/014**: Enterprise-grade version deploy + client-side auto-check. 5-phase deploy (classify > deploy > verify > graduate > deprecate). 4-level verification (install > behavioral > adoption scorecard > mechanical). Phase 0 baseline check catches gaps from previous versions.
- **Founding Principle 0**: Customer Focus First — supersedes all five founding principles. If the customer doesn't get it, the rest doesn't matter.
- **verify-os-deploy.sh**: Runnable verification script for all 4 levels. CEO of Asawa can audit any company's OS compliance.

## v1.6 (2026-04-06)

- **CHARTERS.md**: Cross-functional goal framework — horizontal outcome goals that span vertical departments; KRAs, KPIs, OKRs per charter; DRI + contributors model
- **ROADMAP-MEETING.md**: Replaces HOD Meeting with OKR-driven process — impact/effort matrix, forward-looking goal-setting instead of backward-looking status updates
- **INPUT-ROUTING.md**: Human input classification protocol — every founder input classified (direction/task/feedback/new concept/question) before action; 3 enforcement levels (hook gate, protocol, skill); whitelisted system-maintenance actions
- **ADAPTIVE-PROTOCOL.md v2**: 10 parameters, pre-scoring gates, two-axis routing, undertriage tracking
- **TASK-LIFECYCLE.md updated**: L1 fast-path added; artifact requirements matrix (HLD, ADR, research gate, regression test at L3+)
- **ESTIMATION-ENGINE.md updated**: Auto-calibration feedback loop, CALIBRATION-STATE.json, log format v1.1
- **HUMAN-AGENT-INTERFACE**: Consolidated from L2 contraction
- **4 artifact templates**: HLD, ADR, Research Gate, Bug Fix
- **OKRs.md**: 8 charters for Sutra (expanded from 4)
- **Versioning protocol**: CURRENT-VERSION.md split from RELEASES.md
- **Tiered research cadence**: AI research weekly, frameworks bi-weekly
- **Client registry**: 6 companies (DayFlow, PPR, Maze, Jarvis, Paisa, Asawa)
- Triggered by: Founder session 2026-04-06 — infrastructure hardening, adaptive protocol v2, artifact gates, estimation auto-calibration

## Client Registry

| # | Company | Pinned to | Status |
|---|---------|-----------|--------|
| 1 | DayFlow | v1.7 | Running. Depth system deployed. feedback-to-sutra/ created. |
| 2 | PPR | v1.7 | Deploying. Depth system + engines + version check. |
| 3 | Maze | v1.7 | Deploying. Depth system + engine upgrade + version check. |
| 4 | Jarvis | v1.3.1 | Onboarded. Upgrade pending. |
| 5 | Paisa | v1.7 | Deploying. Depth system + engines + version check. |
| 6 | Asawa | v1.7 | Meta-client. Running latest as governance layer. |

## Release Model

```
SUTRA (develops continuously)
  │
  │ Publishes: v1.0, v1.1, v1.2, v2.0...
  │
  ▼
RELEASE (versioned, stable snapshot)
  │
  │ Client fetches a specific version
  │
  ▼
DAYFLOW (pins to v1.0, runs it, gives feedback)
  │
  │ Feedback goes to Sutra (not to the release)
  │
  ▼
SUTRA (incorporates feedback into next version)
  │
  │ Publishes v1.1 (includes DayFlow's learnings)
  │
  ▼
DAYFLOW (decides when to upgrade: stay on v1.0 or fetch v1.1)
```
