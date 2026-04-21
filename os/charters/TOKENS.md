# Charter: Tokens

**Objective**: Every session spends tokens on value, not ceremony.
**DRI**: Sutra-OS
**Contributors**: Analytics, Engineering, Operations
**Status**: ACTIVE
**Applies to**: Sutra (self) — first instance. **Downstream propagation queued**, not live. `upgrade-clients.sh` (PROTO-018) is currently manifest-driven, not charter-aware; extending it is tracked in TODO. Until then, propagation is a manual deploy via god mode.
**Created**: 2026-04-20
**Review cadence**: Weekly (Roadmap Meeting), scored quarterly (OKR Review)
**Source plan**: `holding/research/2026-04-20-token-optimization-plan.md` (to create)
**Governs**: Big Rock 2 (Estimation Loop — token accuracy is the currency of KR), Big Rock 3 (Simplify Through Contraction — file usage data drives cuts). Tokens charter provides the measurement spine both Rocks depend on.

---

## 1. Why this charter exists

Sutra and Asawa have been running for months with no measurement of where tokens go. Every Claude Code session loads CLAUDE.md, MEMORY.md, hook logs, and auto-emits routing/depth/estimation blocks per task. The waste is unmeasured; the governance overhead is unknown; optimization is impossible.

Founder direction (2026-04-20): "A lot of tokens have been used; we need to find some optimization ways." Feedback memory "Speed is core" sets target <15% governance overhead.

This charter is cross-cutting: measurement is owned by Analytics; cuts are owned by Sutra-OS (protocol design) + Engineering (hook implementation); runtime discipline is owned by Operations.

---

## 2. Key Result Areas (KRAs)

| # | KRA | Scope |
|---|---|---|
| 1 | **Measurement** | Boot context size, per-task token cost, waste ratio, per-company delta |
| 2 | **Reduction** | Data-backed cuts to the highest-waste context items |
| 3 | **Enforcement** | Per-session and per-task budgets, real-time alerts, protocol gates |
| 4 | **Propagation** | Ship charter + mechanisms to all Tier 1–3 client companies (requires `upgrade-clients.sh` extension — see TODO) |

---

## 3. KPIs (always-on) — with exact formulas

**"Tokens" unit definition**: Claude API usage reported by the harness (input + output + cache-read) per session/task, pulled from `.claude/session-stats/` or equivalent. When unavailable, fall back to **byte-derived proxy** = `file_bytes / 4` (rough 4 bytes/token English heuristic) clearly labeled `proxy=true` in the JSONL.

### North Star (the one number we're reducing)

| Tier | Metric | Formula | Source | Current | Target | Warn | Breach |
|---|---|---|---|---|---|---|---|
| ★ NORTH STAR | **`tokens_per_task_median`** | `median(actuals.tokens_total)` over last 50 ESTIMATION-LOG entries | Analytics dept — `holding/departments/analytics/collect.sh` §4 Cost (line 154); rendered in `holding/ANALYTICS-PULSE.md` | **44,000 tok** GRN (2026-04-21) | ≤22,000 tok (50% cut) | >100k | >150k |

**Already wired** — no new collection needed. The metric lives in `holding/departments/analytics/METRICS.md` §4 Cost; emitted every 3h via the analytics-collect LaunchAgent + on-demand via `bash holding/departments/analytics/collect.sh`. Observability dept cross-validates per-company via `Tokens p50` / `Tokens total` panels in `holding/OBSERVABILITY-PULSE.md` §"Per-Task Speed + Tokens" (source: `LATENCY-LOG.jsonl`, 3h window).

**Target 22k rationale**: 50% cut from the 2026-04-21 baseline of 44k, mapping to KR2 "boot P50 reduced ≥30% from baseline by Jun 30" but applied at the task-unit granularity that actually decides $/day. `publish.sh` threshold (currently target=50k, warn=150k, breach=500k) should be retuned to match — queued, not shipped here to keep MVP scope.

### Drivers (demoted from prior flat table; still tracked, not KPIs)

| Metric | Target (Q2) | Status | Note |
|---|---|---|---|
| Boot context P50 (rolling 7d) | ≤15k | insufficient-data (n=3, pre-C5a 25.6k) | Blocked on Phase 0 Step 3-6 telemetry stream. Partial proxy via CONTEXT-READING-PROTOCOL manual capture. |
| Boot context P95 | ≤25k | insufficient-data (n=3, pre-C5a 39.9k) | Same block. |
| Governance overhead % | <15% | unknown | Blocked on Step 4 task_end events. |
| Waste ratio | <10% | unknown | Blocked on Step 4. Measurement-only KPI. |
| Per-task estimate error (lives in Estimation charter, cross-linked) | ≤30% | live via ESTIMATION-LOG `accuracy.tokens_pct` | Cross-charter — owned by Estimation, not Tokens. |

### Guardrails (do-not-cut)

| Metric | Source | Rule |
|---|---|---|
| `override_count_total` | `.enforcement/routing-misses.log` | Must not rise after any cut lands. Currently live in ANALYTICS-PULSE. |
| `triage_correct_pct` | `TRIAGE-LOG.jsonl` | ≥90%. Currently 96% GRN. |

### Per-company fan-out

`Per-company delta = max(company_P50) / min(company_P50)` rendered as a table row in OBSERVABILITY-PULSE per-company panel, not as a flagship KPI. Drop cos with <10 sessions.

**Current readings** (2026-04-21):
- **North star live**: `tokens_per_task_median = 44,000 tok` (p50 last 50). Target 22k. Status GRN vs. loose target, YLW vs. 50%-cut stretch.
- C5a estimator delta (boot, pre/post plugin disable): 53,759 → 26,870 (−50%). Real boot measurement queued on Phase 0 Step 3-6.
- Governance overhead %, waste ratio: BLOCKED on telemetry stream (Step 3-6).

---

## 4. OKRs — Q2 2026

```
OBJECTIVE: Every session spends tokens on value, not ceremony.

  KR1: Baseline token telemetry captured for 6 companies × 10+ sessions each,
       published at holding/research/2026-04-26-token-baseline.md — Score: 0.0
  KR2: Boot context P50 reduced ≥30% from baseline by Jun 30, 2026 — Score: 0.0
  KR3: Governance overhead <15% on tracked sessions by Jun 30, 2026 — Score: 0.0
  KR4: Charter + telemetry mechanism deployed to ≥3 downstream companies
       (requires `upgrade-clients.sh` extension first; target: Asawa-holding,
       DayFlow, one more) by Jun 30, 2026 — Score: 0.0

  Overall: 0.0
  Status: ON_TRACK (just created — baseline not yet measured)
```

Scoring key: 0.0 = no progress, 0.3 = behind, 0.5 = on pace, 0.7 = target, 1.0 = exceeded.

---

## 5. Roadmap

**Ordering principle**: schema before emitters. Freeze the telemetry contract first so all 6 companies emit compatible events; otherwise W1 risks rework.

| # | Action | OKR | Owner | Due | Status |
|---|---|---|---|---|---|
| 1 | Reconcile Tokens local schema with Analytics `TELEMETRY-CONTRACT.md` (allow detailed local jsonl; plugin transport obeys privacy rules — no company names, no raw paths, install_id hash only). Publish reconciled contract. | KR1 | Analytics + Sutra-OS | 2026-04-22 | ✅ DONE (`research/2026-04-20-token-telemetry-schema-reconciliation.md`) |
| 1b | Add `compaction_count` field to v1 Layer A schema (surfaced by i2-spike hyp #11 — Smart Compaction needs fire-count signal) | KR1 | Sutra-OS | 2026-04-21 | ✅ DONE (2026-04-21 — baked into Step 2 schema before freeze) |
| 2 | Freeze `token-telemetry.jsonl` schema (local layer) and plugin transport shape (per Analytics contract). JSON Schema + tests. | KR1 | Analytics | 2026-04-23 | ✅ DONE 2026-04-21 (`holding/departments/analytics/token-telemetry.schema.json` + `tests/token-telemetry-schema.test.sh`) |
| 3 | Write `holding/hooks/session-token-snapshot.sh` (SessionStart) emitting to frozen schema | KR1 | Engineering | 2026-04-24 | TODO |
| 4 | Extend `holding/hooks/dispatcher-stop.sh` to emit `task_end` events with governance-vs-work categorization | KR1 | Engineering | 2026-04-24 | TODO |
| 5 | Deploy hooks to 6 companies via god mode (Sutra, Asawa, DayFlow, Maze, PPR, Billu) | KR1 | Sutra-OS | 2026-04-25 | TODO |
| 6 | Collect 10+ sessions per company; publish baseline report | KR1 | Analytics | 2026-04-26 | TODO |
| 7 | Rank the 7 hypothesis cuts against data; select top 3 | KR2 | Sutra-OS | 2026-04-29 | TODO |
| 7a | Pilot token-optimizer-mcp (deronin #7) — caches repeated bash outputs; addresses hyp #9. Independent of schema freeze; can run pre-baseline. Measure delta via RTK comparison + session-stats. **BUNDLED 2026-04-21 as the first concrete leaf under cost-component-deepening §6 Week-2 C1f MCP-audit track** (see `holding/research/2026-04-21-token-techniques-cost-component-deepening.md` §6). Run order: C7 cache-verification FIRST, then this pilot — MCP installs can break Anthropic prompt caching (5-min TTL, 4k min cacheable on Opus 4.7). | KR2 | Engineering + Sutra-OS | 2026-04-25 | TODO |
| 8 | Draft TOKEN-BUDGET-PROTOCOL (candidate PROTO-019); add to `state/system.yaml` | KR2, KR3 | Sutra-OS | 2026-05-01 | TODO |
| 9 | Ship cut #1 (MEMORY.md indexed retrieval) — pilot on DayFlow | KR2 | Engineering | 2026-05-07 | TODO |
| 10 | Ship cuts #2–3 (block compression for L1; CLAUDE.md split) | KR2 | Engineering | 2026-05-21 | TODO |
| 11 | Add per-session + per-task budget alerts to Analytics Pulse | KR3 | Analytics | 2026-05-28 | TODO |
| 12 | Extend `upgrade-clients.sh` to be charter-aware (propagate `os/charters/` + `departments/`); deploy to CLIENT-REGISTRY Tier 2 clients | KR4 | Sutra-OS | 2026-06-10 | TODO |
| 13 | Q2 review: score KRs, decide on Q3 continuation | — | Sutra-OS | 2026-06-30 | TODO |

---

## 6. Practice Contributions

| Practice / Unit | Role | Specific responsibilities |
|---|---|---|
| **Sutra-OS** | DRI | Charter ownership, protocol design (TOKEN-BUDGET-PROTOCOL), `state/system.yaml` schema changes, cut prioritization, quarterly scoring, `upgrade-clients.sh` extension |
| **Analytics** | Contributor | Contract reconciliation, schema freeze, `token-telemetry.jsonl` collection, baseline report, Pulse integration, per-company roll-up, alerts |
| **Engineering** | Contributor | Hook implementations, log rotation, cut ships |
| **Operations** | Contributor | Log rotation cadence, runtime monitoring, alert triage, budget enforcement discipline |

---

## 7. Telemetry contract (two-layer)

Reconciles with existing Analytics `TELEMETRY-CONTRACT.md` which forbids company names + raw paths in plugin transport. Tokens charter operates in TWO layers; same event stream, different sinks and privacy rules.

### Layer A — Local (detailed, on-machine only)

**Sink**: `holding/departments/analytics/token-telemetry.jsonl` (machine-local; never transmitted as-is)
**Allowed fields**: timestamp, `company` name, `session_id`, `task_id`, `depth`, `files_loaded` (relative paths), `files_sizes_bytes`, `tokens_est`, `tokens_actual`, `category`, `path` (origin of the load: hook name, block type)
**Why local can be detailed**: single-CEO machine, no PII risk; needed for debugging which files waste tokens.

### Layer B — Plugin transport (sanitized, when plugin ships)

Must obey `holding/departments/analytics/TELEMETRY-CONTRACT.md`:
- Allowed: metric values, install_id hash, sutra_version, tier, event counts, timestamps
- Forbidden: company names, raw file paths, prompt content, task descriptions, commit messages

**Mapping Layer A → Layer B**: emitter aggregates local events into metric-shaped rows before POST. Company names hashed; file paths bucketized to categories (e.g., `category=boot-memory` instead of `path=CLAUDE.md`). See Analytics contract for full mapping.

**Collection principle** (inherits from Analytics Charter Principle 1): machine > LLM. Bash-only. Measuring tokens must not cost tokens.

---

## 8. Cut hypotheses (ranked, for W2 prioritization)

| # | Suspect | Hypothesis | Risk | Expected boot delta |
|---|---|---|---|---|
| 1 | MEMORY.md auto-load | 50+ lines; <20% referenced per session | Low | −15 to −25% |
| 2 | INPUT ROUTING + DEPTH blocks (L1 tasks) | ~25 lines emitted per task — all tasks, not weighted | Med — enforcement visibility drops | −10 to −20% per-task |
| 3 | CLAUDE.md boot | Full file loaded; many rare sections | Low | −5 to −15% |
| 4 | Agent dispatch preamble (subagent-os-contract) | Repeats in every Task call | Med — contract enforcement critical | −5 to −15% per-dispatch |
| 5 | Log growth (ESTIMATION-LOG, TRIAGE-LOG, hook-log) | Unbounded; loaded when analytics run | Low | −3 to −8% when touched |
| 6 | READABILITY + Execution-Trace rules | Full rule text in CLAUDE.md | Med | −5 to −10% |
| 7 | Company CLAUDE.md duplication | Common rules repeat across companies | Low | −5 to −10% per company |
| 8 | Terminal output bloat | Bash outputs (git status, find, ls) account for >10% of session tokens | Low | −5 to −15% per session — **ADDRESSED via RTK Mode A** (shipped 2026-04-20; cumulative 2.85K saved at 42-75% efficiency) |
| 9 | Repeated identical tool calls | Same `ls sutra/`, `cat CLAUDE.md`, `git status` repeated across tasks burns tokens | Med (MCP overhead) | −10 to −20% per session — **CANDIDATE: token-optimizer-mcp pilot** (deronin #7), independent of schema freeze |
| 10 | Ghost context | Files loaded but not used; survives compaction. This IS the waste-ratio KPI (§3) | Low (measurement) | measurement-only; **token-optimizer (alexgreensh)** addresses but PolyForm-Noncommercial license blocks production. Personal-eval installed; commercial license decision pending |
| 11 | **Compaction loss** | Each auto-compact wipes 60-70% of conversation; fresh context post-compact lacks load-bearing state. Surfaced by i2-spike. | Med (state restoration logic) | −60 to −70% recovery on auto-compact events. Smart Compaction installed via token-optimizer plugin SessionEnd hook 2026-04-20; needs measurement of how often compaction fires + whether restoration succeeds. New Layer A field `compaction_count` added to v1 schema. |
| 12 | **Verbose plugin skill descriptions** | 34 gstack plugin skills with >120-char descriptions × ~100 tokens/skill = ~3,400 fixed-cost tokens loaded every session, regardless of usage. Surfaced by token-optimizer baseline scan. | Low — third-party plugin (gstack); local override or upstream PR | −3,400 tokens fixed (small but free). Requires local override mechanism OR PR upstream. Defer to W3 unless mechanism is trivial. |

Ranking finalized in W2 after baseline data. **Already-shipped or in-flight: #8 (RTK), #11 (Smart Compaction install). In-flight personal eval: #10. Top unstarted: #9 (token-optimizer-mcp).**

---

## 9. Cross-charter & cross-Rock links

| Link | Direction |
|---|---|
| **Big Rock 2** (Estimation Loop — `sutra/OKRs.md`) | Tokens charter SUPPLIES token measurement; Big Rock 2 calibration accuracy depends on Tokens KPI #5 |
| **Big Rock 3** (Simplify Through Contraction) | Tokens charter SUPPLIES file-usage data (waste ratio); contraction decisions read from Tokens telemetry |
| **Speed charter** (future) | Tokens reduction feeds Speed (less context = faster boot); co-track governance overhead % |
| **Simplicity charter** (future) | Cognitive Load Index shares waste-ratio signal |
| **Quality charter** (future) | Tokens cuts gated on override rate NOT rising — enforcement integrity first |
| **CLIENT-REGISTRY** (`sutra/CURRENT-VERSION.md` §Client Registry) | KR4 propagation targets the 7 registered tiers; `upgrade-clients.sh` extension must respect tier gating (Tier 1 = no charter schema, Tier 2+ gets full mechanism) |

---

## 10. Guardrails (what we will NOT cut)

- PROTO-000 (every change ships with implementation) text — cutting this erodes the safety net
- Boundary enforcement (enforce-boundaries.sh) preamble — cross-company safety
- POLICY-COVERAGE markers — drift detection
- Evidence requirements in COVERAGE-ENGINE — the "no-mock claims" rule
- Override rate must not rise after any cut (measured via existing Analytics dimension 5)

If any cut proposal touches these, it escalates to founder.

---

## 11. Lifecycle

| Phase | Gate | Action |
|---|---|---|
| **Create** | Founder direction 2026-04-20 | Done — this file |
| **Active** | Baseline published (KR1) | Weekly roadmap review; KPI pulse |
| **Retire** | Sustained <15% governance overhead for 2 consecutive quarters OR priority shift | Archive with final scores; keep KPIs running under Speed charter |

---

## 12. Tradeoffs explicit

| Tradeoff | Call |
|---|---|
| Measurement costs tokens | Mitigated: bash-only. Measurement overhead must be ≤1% of total session tokens |
| Less visible enforcement = drift risk | Counter-measured: TRIAGE-LOG class misses + override rate; if drift up when cuts land, revert cuts |
| Company-specific needs differ | Target = governance overhead %, not absolute bytes. Companies can have different boot sizes |
| Indexed memory = retrieval latency | Accepted: one-time retrieval cost beats every-session load cost |
| Two-layer telemetry = duplication | Accepted: local needs detail for debugging; transport needs privacy. Aggregation bridges |

---

---

## 15. Operationalization (added 2026-04-20 per D30)

### 1. Measurement mechanism
Charter progress tracked via `token-telemetry.jsonl` (Layer A local) aggregated into Analytics Pulse. KPI formulas from §3. Null handling: <10 sessions → `insufficient-data`.

### 2. Adoption mechanism
Charter lives at `sutra/os/charters/TOKENS.md`; enforcement via dispatcher-pretool snapshots + Stop-event telemetry collector. Downstream propagation queued on `upgrade-clients.sh` charter-aware extension (KR4 gated dep).

### 3. Monitoring / escalation
Analytics Dept owns collection (`collect.sh` §9); Sutra-OS owns escalation. Weekly roadmap meeting reviews boot P50, governance %, waste ratio. Warn at table §3 thresholds; breach → revert last cut.

### 4. Iteration trigger
Any KPI hits breach threshold for 2 consecutive weeks → revise cut ranking (§8 hypotheses). Any new founder token-direction → re-baseline. Override rate rise after any cut lands → revert that cut.

### 5. DRI
Sutra-OS (Sankalp through Q2 2026; reassigned at first quarterly review). Analytics contributes measurement; Engineering contributes cut implementation.

### 6. Decommission criteria
(a) Governance overhead <15% for 2 consecutive quarters → charter retires, KPIs merge into Speed charter; or (b) founder direction supersedes the charter → archive with final scores.

---

## 13. Related files

- Pattern: `sutra/layer2-operating-system/a-company-architecture/CHARTERS.md`
- Placement doc: `sutra/os/charters/README.md`
- Measurement engine (existing): `sutra/os/engines/ESTIMATION-ENGINE.md`
- Measurement engine (existing): `sutra/os/engines/estimation-log.jsonl`
- Analytics dept: `holding/departments/analytics/CHARTER.md`
- Analytics telemetry contract (governs plugin transport): `holding/departments/analytics/TELEMETRY-CONTRACT.md`
- OKRs index: `sutra/OKRs.md` (appended pointer to this charter)
- TODO: `sutra/TODO.md` (W1 items queued, plus `upgrade-clients.sh` extension + PROTO-019 formalization)
- Client registry (KR4 propagation targets): `sutra/CURRENT-VERSION.md` §Client Registry
- Big Rock 2 & 3 (`sutra/OKRs.md`): Tokens charter supplies their measurement substrate

---

## 14. Codex review record (2026-04-20)

Codex review returned FLAG verdict with 5 issues; all addressed in this version:

| # | Codex issue | Fix applied |
|---|---|---|
| 1 | Propagation path overstated (`upgrade-clients.sh` not charter-aware) | Rephrased Applies to + added roadmap step 12 + KR4 note |
| 2 | Telemetry schema conflicts with Analytics privacy contract | Section 7 split into Layer A (local) and Layer B (transport) with explicit mapping |
| 3 | KPIs lacked precise formulas; "accuracy" misnamed | Section 3 adds formula column, null handling, unit definition; renamed to "error rate" |
| 4 | Roadmap: hook impl before schema was backwards | Steps 1–2 now reconcile + freeze schema; emitters follow |
| 5 | Missing links to CLIENT-REGISTRY and Big Rock structure | Added to header (Governs:), section 9, section 13 |
