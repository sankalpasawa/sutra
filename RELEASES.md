# Sutra — Release History

> For current version, see CURRENT-VERSION.md. This file is the full release history — load only when reviewing versions or debugging regressions.

## How Sutra and Client Companies Interact

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

## The Versioning

### Sutra v1.6 (current)
- **CHARTERS.md**: Cross-functional goal framework — horizontal outcome goals that span vertical practices; KRAs, KPIs, OKRs per charter; DRI + contributors model
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

### Sutra v1.5
- **CHARTERS.md**: Cross-functional goal framework — horizontal outcome goals that span vertical practices; KRAs, KPIs, OKRs per charter; DRI + contributors model; scales by complexity tier (1-2 at Tier 1, 3-5 at Tier 2, unlimited at Tier 3)
- **ROADMAP-MEETING.md**: Replaces HOD Meeting — OKR-driven, impact/effort matrix, forward-looking goal-setting instead of backward-looking status updates
- **INPUT-ROUTING.md**: Human input classification protocol — every founder input classified (direction/task/feedback/new concept/question) before action; 3 enforcement levels (hook gate, protocol, skill); whitelisted system-maintenance actions
- **OKRs.md**: Sutra's own company OKRs — 4 charters (Speed/Simplicity/Accuracy/Efficiency) mapped to V/C/A/U KPIs with Q2 2026 targets and roadmaps
- **CLIENT-ONBOARDING.md**: Phase 6 updated — Step 10 generates OKRs.md with charters, Step 11 configures input routing enforcement level
- Triggered by: Founder session 2026-04-06 — speed direction, OKR/charter framework design, input routing enforcement

### Sutra v1.4
- **TASK-LIFECYCLE.md**: unified 5-phase lifecycle (THINK → PRE → EXECUTE → POST → COMPRESS) replacing 3 separate pipelines; Parallelization Gate at PRE phase; thoroughness scales with change, not company
- **DEFAULTS-ARCHITECTURE.md**: 3-tier directive governance (Immutable Invariants / Controlled Defaults / Tunable Parameters); formal safety property analysis (Lamport); FMEA blast radius assessment; convention-over-configuration inheritance
- **PARALLELIZATION-ARCHITECTURE.md**: Bernstein conditions for formal independence testing; BSP (Bulk Synchronous Parallel) wave model adapted for LLM agent orchestration; structural enforcement after 15-agent collapse
- **READABILITY-STANDARD.md**: Tier 1 Immutable invariant — all agent output must conform; output format taxonomy (9 types); 10 anti-patterns with enforcement; format selection rules
- **SYSTEM-HEALTH.md**: 13 growth protocols (G1-G13) with triggers — refactoring, pruning, consolidation, deprecation, archival, migration, documentation gardening, and more; Lehman's Laws of Software Evolution as foundation
- **SUTRA-KPI.md**: 4 metrics (V/C/A/U — Velocity, Cognitive Load, Accuracy, Unit Cost) with v1.3.1 baselines; per-level normalization; statistical methods defined
- **ESTIMATION-LOG-FORMAT.md**: JSONL schema (v1) for persistent estimation data; EWMA rolling accuracy tracking; UUID-keyed records with full estimate/actual pairs
- **CLIENT-ONBOARDING.md**: Phase 2 updated with practitioner identification (D32); 8-phase flow from raw idea to deployed OS
- Client registry: 5 companies (DayFlow, PPR, Maze, Jarvis, + Asawa itself as meta-client)
- Triggered by: Asawa CEO session 2026-04-05 — comprehensive infrastructure buildout

### Sutra v1.3.1
- Estimation Engine calibrated with real data from 22 evolution cycles (8 task-category multipliers)
- Adaptive Protocol Level 4: platform-specific rollout patterns (web, mobile, edge functions, CLI, DB)
- Client Onboarding: Phase 7 now includes mandatory identity, boundary hooks, isolation tests, engine deployment
- MID-STAGE-DEPLOY.md: 7-step protocol for deploying to existing codebases
- PROTOCOL-CREATION.md: meta-protocol for how new protocols get created (lifecycle: EXPERIMENTAL → STABLE → REMOVED)
- PROCESS-GENERATION.md: generate processes on the fly for new situations
- SKILL-ACQUISITION.md: how to find, evaluate, install new skills
- Skill Registry: tiered activation (Tier 1: 8 skills, Tier 2: 14, Tier 3: 21)
- Client registry: 4 companies (DayFlow, PPR, Maze, Jarvis)
- Triggered by: Evolution Protocol session — 22 cycles across 3 active companies

### Sutra v1.3
- **Engines layer** (`d-engines/`): three runtime intelligence systems added to Layer 2
- **Estimation Engine**: pre-task cost/impact/confidence table with token estimation, JSONL feedback format, rolling accuracy tracking, configurable gates
- **Adaptive Protocol Engine**: dynamic process depth routing (4 levels: Minimal→Critical), 13-parameter max-severity scoring model, mid-task escalation, learning loop
- **Enforcement Review**: 3-cadence review system (3-day micro, weekly, monthly calibration), sensitivity scoring replacing file-count proxy, per-company sensitivity.jsonl, judgment inheritance
- All three engines interconnect: Estimation feeds Adaptive Protocol (cost informs depth), Enforcement Review feeds sensitivity scores into both, all validated post-task
- Triggered by: founder design session — static one-size-fits-all process depth needed dynamic routing

### Sutra v1.2
- Phase 1 INTAKE rewritten as conversational flow: one question at a time, react-and-follow-up, build Intake Card progressively
- Internal checklist preserved (all fields still required), but founder never sees a numbered list
- Conversation tips added for handling the bet question, involvement level inference, and short answers
- Triggered by: founder feedback during onboarding — "too many questions at once, make it back and forth"

### Sutra v1.1.1
- External resource sovereignty: before pausing/deleting any external resource, verify ownership — even under full autonomy
- Phase 7 deploy step: verify MCP-connected account ownership before touching any external service
- "Full autonomy" scoped: covers product decisions, NOT destructive infrastructure actions
- Triggered by: Maze onboarding — Sutra paused wrong Supabase project on shared MCP account

### Sutra v1.1
- Complexity tiers: OS is mandatory for all companies, depth scales with company complexity (Personal → Product → Company)
- Infrastructure guardrail: parallel operations require isolation verification (from PPR deploy collision feedback)
- Enforcement tiering: compliance checks, metrics logging, and shipping log requirements scale with tier
- Clients: DayFlow (Tier 2), PPR (Tier 1)

### Sutra v1.0
- Stage 1 Pre-Launch OS (12 rules)
- Basic product knowledge system (shearing layers, flow maps, sensors)
- Functional principles (product, design, eng, security, quality)
- Intent + boundaries + effort delegation model
- One process: idea → PR/FAQ → P1 → mockup → build → test → ship

### Sutra v2.0 (future — when DayFlow hits Stage 2: 25 users)
- Analytics and metrics process
- User research process
- Onboarding optimization
- Retention tracking
- Weekly metrics review
- Expanded practice functions

## How a Release Gets Created

1. Sutra works on improvements in `asawa-inc/sutra/` (the development branch)
2. When a set of improvements is ready, Sutra tags a release: `sutra-v1.1`
3. The release is a snapshot: specific versions of the operating model, principles, and modules
4. DayFlow's adapted version lives in `asawa-inc/dayflow/sutra-version`

## How DayFlow Fetches a Release

1. DayFlow reads `asawa-inc/sutra/RELEASES.md` to see what's new
2. DayFlow decides: upgrade or stay
3. If upgrade: copy the new version's files to `asawa-inc/dayflow/adapted-principles/`
4. Adapt any generic principles to DayFlow's specific context
5. Update `CLAUDE.md` if the operating process changed

## How DayFlow Sends Feedback

1. DayFlow encounters something: bug, missing principle, principle violation, or validation
2. Writes to `asawa-inc/dayflow/feedback-to-sutra/YYYY-MM-DD-topic.md`
3. Format:
   ```
   Type: incident | violation | missing | validation
   Sutra version: v1.0
   What happened: [description]
   What principle was relevant: [or "none — this is a gap"]
   What we learned: [the insight]
   Suggested update: [if any]
   ```
4. Sutra's Learner agent reads feedback and incorporates into next version

## Current State

| Company | Pinned to | Status |
|---------|-----------|--------|
| DayFlow | Sutra v1.0 | Running. No feedback sent yet. |
| PPR | Sutra v1.0 | Running. First feedback sent (parallel deploy collision). |
| Maze | Sutra v1.3 | Upgrading. First company to receive engines layer. |
| Jarvis | Sutra v1.3.1 | Onboarded. |
| Paisa | Sutra v1.4 | Onboarded. MVP stage. |
| Asawa | Sutra v1.6 | Meta-client. Running latest as governance layer. |

## Release History

| Version | Date | What changed | Triggered by |
|---------|------|-------------|-------------|
| v1.0 | 2026-04-03 | Initial: Stage 1 OS, 12 rules, basic knowledge system | DayFlow creation |
| v1.1 | 2026-04-04 | Complexity tiers, infrastructure guardrail, enforcement tiering | PPR onboarding + parallel deploy collision |
| v1.1.1 | 2026-04-04 | External resource sovereignty rule, Phase 7 ownership verification step | Maze Supabase org confusion |
| v1.2 | 2026-04-05 | Phase 1 INTAKE → conversational flow (no question dump) | Founder onboarding friction feedback |
| v1.3 | 2026-04-05 | Engines layer: Estimation, Adaptive Protocol, Enforcement Review | Founder design session — process depth must match problem |
| v1.3.1 | 2026-04-05 | Estimation calibration (22 cycles), Adaptive Protocol L4, expanded onboarding, mid-stage deploy, protocol creation, process generation, skill acquisition | Evolution Protocol session — 22 cycles across 3 companies |
| v1.4 | 2026-04-05 | Task Lifecycle, Defaults Architecture, Parallelization Architecture, Readability Standard, System Health, KPI System, Estimation Log Format, onboarding D32, Asawa as meta-client | Asawa CEO session — comprehensive infrastructure buildout |
| v1.6 | 2026-04-06 | Adaptive Protocol v2 (10 params, pre-scoring gates, two-axis routing), Task Lifecycle L1 fast-path + artifact matrix, Estimation auto-calibration, HUMAN-AGENT-INTERFACE consolidated, 4 artifact templates (HLD/ADR/Research Gate/Bug Fix), 8 Sutra charters, tiered research cadence, versioning split | Founder session — infrastructure hardening, adaptive protocol v2, artifact gates, estimation auto-calibration |
| v1.5 | 2026-04-06 | Charters framework, Roadmap Meeting (replaces HOD), Input Routing protocol (3 enforcement levels), Sutra OKRs (4 charters), onboarding Phase 6 Steps 10-11 | Founder session — speed direction, OKR/charter design, input routing enforcement |
| v2.1.1 (plugin patch) | 2026-04-25 | core plugin hotfix: `/core:start` project-root guard (refuse in $HOME / non-project dirs; canonical path compare; .git-as-file recognition); `/core:feedback` docs synced to v2.1 `--public` wiring; `reset-turn-markers.sh` root-cause fix (empty PROMPT = synthetic). 10-case test suite + codex-reviewed (DIRECTIVE-ID 1777065370). | T4 user reported home-dir CLAUDE.md poisoning; feedback loop silently severed due to outdated "No --send" docs |
