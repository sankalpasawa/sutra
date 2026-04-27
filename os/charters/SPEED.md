# Charter: Speed

**Objective**: Every task executes at the speed the work actually requires — no governance bloat, no unexamined waits, no invisible time sinks.
**DRI**: Sutra-OS
**Contributors**: Analytics (data pipeline), Engineering (instrumentation), Operations (runtime discipline), Product (UX of slow-path alerts)
**Status**: ACTIVE
**Applies to**: Sutra (self) first, then DayFlow + Billu as Tier-1 validators. Portfolio-wide propagation queued behind charter-aware `upgrade-clients.sh` (see Tokens charter step 12 — same dependency).
**Created**: 2026-04-20
**Review cadence**: Weekly (Roadmap Meeting), scored quarterly (OKR Review)
**Source plan**: this file
**Governs**: Big Rock "Speed is core" (memory), OKR #1 (Speed). Sibling to Tokens (cost lens) — Tokens asks "how much?", Speed asks "how long and where?". Both share the Analytics Dept pipeline.

---

## 1. Why this charter exists

**Founder direction (2026-04-20)**: "Tasks take a lot of time. I want profiling of each task, right analytics paired with observability, RCA of where time goes, and based on data figure out improvements. Less building, more real-time understanding grounded in data and real findings."

Current state:
- `ESTIMATION-LOG.jsonl` captures `duration_min` per task — but only at task level. We know a task took 45 min. We don't know: was it 40 min in 20 sub-agent calls, or 40 min in Bash retries, or 40 min in governance overhead?
- Hooks fire on every tool call. Nobody has measured hook overhead.
- CLAUDE.md + SYSTEM-MAP + TODO + memory load on every session start. Boot wall-time is unknown.
- Claude's own LLM think time vs. tool dispatch time vs. stream time — all invisible.
- Optimization proposals today are guesses. The "Speed is core" memo is ≥3 months old with zero measurement behind it.

**Iron Rule**: No Speed improvement ships without a cited time-sink baseline from this charter's data. Guess-driven cuts are blocked.

---

## 2. Key Result Areas (KRAs)

| # | KRA | Scope |
|---|---|---|
| 1 | **Observability** | Instrument phase-level timing per task: boot, routing, depth, each tool call, each hook, sub-agent dispatch, LLM think, LLM stream, output gate |
| 2 | **Real-time understanding** | Live view — per-task breakdown visible in ANALYTICS-PULSE; top time sinks ranked daily; anomaly flags |
| 3 | **Root-cause analysis** | Correlate latency against: task type, depth, company, tool type, hook chain, time-of-day, context size |
| 4 | **Reduction** | Data-backed cuts to top-3 time sinks per quarter. Each cut has baseline + target + measured delta |
| 5 | **Propagation** | Ship instrumentation + pulse to all Tier 1-3 companies via charter-aware upgrade pipeline |

---

## 3. KPIs (always-on) — with exact formulas

**"Time" unit definition**: Wall-clock milliseconds measured by the harness, captured via hook timestamps + session JSONL parsing. All measurements stored as integer milliseconds. When unavailable (pre-instrumentation session), row marked `partial=true`.

| Metric | Formula | Null handling | Current | Target (Q2) | Warn | Breach |
|---|---|---|---|---|---|---|
| Task wall-time P50 | 50th percentile of `task_end_ts − task_start_ts` across tasks in rolling 7d | ≥20 tasks required | unknown | ≤120s | >180s | >300s |
| Task wall-time P95 | 95th percentile (same) | same | unknown | ≤600s | >900s | >1500s |
| Governance overhead % (time) | `sum(time in phases [input-routing, depth-block, estimation-block, hook-pretool, hook-stop, boot-load]) / sum(task_wall_time)` per session | denominator <10s excludes | unknown | <15% | ≥20% | ≥30% |
| Top-1 time sink concentration | `time_in_top_1_phase / total_task_time` averaged across tasks | — | unknown | <40% | ≥50% | ≥65% |
| Hook chain overhead P95 | P95 of `sum(per-hook duration)` per tool call | per-hook ms required | unknown | ≤300ms | >500ms | >1000ms |
| Sub-agent round-trip P95 | P95 of `Agent tool dispatch → result` wall time | — | unknown | ≤4min | >5min | >8min (hard chunk limit per D29) |
| Boot load time P50 | P50 of `session_start → first user-facing output` | ≥10 sessions | unknown | ≤8s | >15s | >25s |
| Per-company delta | `max(company_P50_task_time) / min(company_P50_task_time)` | drop companies <10 tasks | unknown | <2× | ≥2× | ≥3× |

Current = "unknown" until W1 baseline lands.

---

## 4. OKRs — Q2 2026

```
OBJECTIVE: Every task executes at the speed the work requires.

  KR1: Phase-level latency telemetry live for 3 companies × 50+ tasks each,
       published at holding/research/2026-05-04-speed-baseline.md — Score: 0.0
  KR2: Top-3 time sinks identified with ≥100-sample baselines per sink,
       RCA doc landed at holding/research/2026-05-18-speed-rca.md — Score: 0.0
  KR3: At least 1 data-backed Speed cut shipped with measured delta ≥20%
       on its baseline, documented in SPEED charter log — Score: 0.0
  KR4: Governance overhead %-of-time reduced to <15% on Sutra self — Score: 0.0
```

Anti-pattern block: KR3 does NOT activate until KR1 and KR2 are ≥0.7. No building before data.

---

## 5. Roadmap (6 waves)

| Wave | Dates | Owner | Output | OKR |
|---|---|---|---|---|
| **W0 Discovery** | 2026-04-20 → 2026-04-22 | Sutra-OS | Enumerate all existing time signals (hook logs, estimation-log, session JSONL paths). Draft phase taxonomy (what counts as "input-routing" time, "hook" time, etc.). Land phase-taxonomy.md. | — |
| **W1 Instrumentation (minimal)** | 2026-04-23 → 2026-04-27 | Engineering | Add `_ts_start`/`_ts_end` to dispatcher-pretool + dispatcher-stop. Emit `LATENCY: phase=<name> ms=<N>` to `.enforcement/latency.log`. Parse session JSONL in `latency-collector.sh`. Append to `holding/LATENCY-LOG.jsonl`. **No new hooks. No new frameworks. Timestamps only.** | KR1 |
| **W2 Collection** | 2026-04-28 → 2026-05-11 | Operations | Real usage for 2 weeks. No interpretation, no changes. Just run and collect. Per "wait for data before optimizing" memory. Target: ≥50 tasks per live company (Sutra self, DayFlow, Billu). | KR1 |
| **W3 RCA** | 2026-05-12 → 2026-05-18 | Sutra-OS + Analytics | Read the 2 weeks of data. Write RCA doc: top-3 time sinks per company, correlation tables (depth × latency, tool × latency, company × latency), outlier tasks, anomaly clusters. No fixes proposed yet. | KR2 |
| **W4 Proposal** | 2026-05-19 → 2026-05-25 | Sutra-OS | For each top-3 sink, propose 1-2 cuts. Each proposal = baseline citation + target + rollout plan + verification test. Codex consult per "codex everywhere" memory. Founder approves or rejects each cut individually. | KR3 (prep) |
| **W5 Ship + Measure** | 2026-05-26 → 2026-06-22 | Engineering | Implement approved cuts one at a time. Each cut atomically committed. Before/after measurement on same live pipeline. Log delta to `SPEED-CUTS.jsonl`. | KR3, KR4 |
| **W6 Propagation** | 2026-06-23 → 2026-06-30 | Sutra-OS | Port charter + instrumentation to Tier-2/3 clients via charter-aware upgrade-clients.sh (shared dependency with Tokens). | — |

Gate protocol: each wave produces an artifact; next wave cannot begin until the artifact lands in the committed repo.

---

## 6. Phase taxonomy (W0 output, stub here — finalize in W0)

Every task decomposes into these phases. Each phase's time is captured independently.

```
TASK
├── boot-load          (CLAUDE.md, SYSTEM-MAP, TODO, memory — one-time per session)
├── input-routing      (TYPE/HOME/ROUTE/FIT classification LLM turn)
├── depth-estimation   (DEPTH/EFFORT/COST/IMPACT block)
├── execution
│   ├── tool-call N    (Read, Edit, Write, Bash, Grep, Glob, WebFetch, Agent)
│   │   ├── hook-pretool  (dispatcher-pretool.sh chain duration)
│   │   ├── tool-dispatch (harness → tool provider)
│   │   └── hook-posttool (cascade-check, enforce-boundaries, etc.)
│   ├── llm-think      (extended thinking budget consumed)
│   └── llm-stream     (output token generation to user)
├── output-gate        (readability + trace formatting)
└── session-stop       (dispatcher-stop.sh, collectors, log-writers)
```

**Unit: integer milliseconds. Signed aggregation.** Governance-overhead KPI sums `boot-load + input-routing + depth-estimation + hook-pretool + hook-posttool + output-gate + session-stop`.

Tool-specific sub-phases (Bash = exec vs. wait, Agent = dispatch vs. round-trip) finalize in W0.

---

## 7. Principles (non-negotiable)

1. **Data > hypotheses.** No optimization ships without ≥100 samples of its baseline.
2. **Observation > instrumentation.** Prefer parsing existing logs (dispatcher, session JSONL, estimation-log) over adding new hooks. Only instrument what cannot be derived.
3. **Measure before cut.** W1-W3 produce zero behavior changes. If W3 finds nothing bad, we ship nothing and the charter closes satisfied.
4. **Per-phase > per-task.** Task-level duration hides the signal. Phase-level is the minimum resolution.
5. **Real-time > retro.** ANALYTICS-PULSE shows latency live, not weekly.
6. **Correlate, don't guess.** RCA must correlate against ≥2 dimensions (e.g., depth × phase, not just phase).
7. **Grounded findings > elegant theories.** Ship what the data says. Park elegant hypotheses that aren't supported.
8. **Propagate only when stable.** Don't push instrumentation to 5 companies until it's stable on 1.

---

## 8. Ownership model

| Function | Owner | Why |
|---|---|---|
| Charter DRI | **Sutra-OS** | Cross-cutting; needs one owner |
| Data pipeline (collect, publish, pulse) | **Analytics Dept** | Already owns pipeline shape per Dept charter; Speed becomes 9th flagship metric added to METRICS.md |
| Instrumentation (hooks, parsers) | **Engineering (hooks + harness)** | Implements the timestamps + collector scripts |
| Runtime discipline (re-run policy, sample size, outlier review) | **Operations** | Gate: Ops decides when ≥100 samples = "enough" per sink |
| Cut proposals (protocols, UX, structural changes) | **Product + Sutra-OS** | Proposal authorship + product-side tradeoff review |
| Approval gate | **Founder (CEO of Asawa)** | Each W4 cut individually approved, not batched |

No new department needed. Analytics Dept absorbs the data work as its 9th dimension: **Latency** (flagship metric: `task_wall_time_p50`).

---

## 9. Integration with existing systems

| System | Integration | New artifact |
|---|---|---|
| **Analytics Dept** (`holding/departments/analytics/`) | Add `compute_latency()` to `collect.sh` §N. Add Latency row to METRICS.md. Add Speed panel to ANALYTICS-PULSE via `publish.sh`. | METRICS.md edit, collect.sh extension, pulse panel |
| **Estimation Engine** (`sutra/layer2-operating-system/d-engines/ESTIMATION-ENGINE.md`) | Cross-reference: ESTIMATION-ENGINE estimates time pre-task; Speed charter measures time post-task. Actuals feed calibration. | bi-directional pointer |
| **Tokens charter** (`sutra/os/charters/TOKENS.md`) | Sibling. Both share Analytics pipeline. Tokens KPI = cost-unit; Speed KPI = time-unit. Same session JSONL parser used by both. | mention in both charters' §1 |
| **Hooks** (`holding/hooks/dispatcher-pretool.sh`, `dispatcher-stop.sh`) | Add `_now_ms()` timestamps at start/end. Emit LATENCY lines. Zero logic change. | hook edits in W1 |
| **Session transcripts** (`~/.claude/projects/<cwd-hash>/`) | Parse tool_use/tool_result pairs for per-tool latency. Read-only. | new parser `latency-collector.sh` |
| **upgrade-clients.sh** (PROTO-018) | Same dependency as Tokens charter: needs charter-aware extension to propagate. Until then, manual god-mode deploy for Sutra self. | no change, queued |

---

## 10. Anti-patterns (logged here so they cannot be re-invented)

| Anti-pattern | Why banned | Evidence / memory |
|---|---|---|
| "Tasks feel slow, let's add caching" | No baseline, no data. Feelings aren't measurements. | Founder direction 2026-04-20 ("grounded in data and real findings") |
| Optimize one smoke-test run | Single run ≠ real load distribution. | `feedback_wait_for_data_before_optimize` memory — 3-4h of real session data required |
| Add another framework to solve it | "less of building but more of real-time understanding" | Founder direction 2026-04-20 verbatim |
| Per-company optimization before cross-company data | Premature generalization from one sample. | Tokens charter §7 — same rule |
| Kill governance to buy speed | Governance has a measured overhead budget (15%), not zero | Memory `feedback_speed_is_core` — "<15% governance overhead" target |
| Skip codex review on cut proposals | Design-phase decisions require independent review | `feedback_codex_everywhere` memory |

---

## 11. Success & termination conditions

**Success (by Jun 30, 2026)**:
- All 4 KRs ≥0.7
- Governance overhead ≤15% on Sutra self
- ≥1 propagated cut with measured delta on DayFlow or Billu
- ANALYTICS-PULSE shows Speed panel live with p50/p95 per company per phase

**Satisfied-closure (valid outcome)**:
- If W3 RCA finds no time sink >20% of total task time on any company, charter closes at KR2=1.0 with "no cuts needed" state. This is SUCCESS, not failure — it means the system is already fast.

**Failure**:
- W2 collection reveals instrumentation gap (<50 tasks in 2 weeks per company) — extend W2 2 more weeks before W3.
- W4 proposal rejected 3× by founder — charter pauses, Sutra-OS rewrites proposal framework.
- Governance overhead measured ≥30% (breach) — this becomes the #1 cut automatically.

---

## 12. Propagation decision

**Applies to**:
- Sutra (self) — first instance, Tier-1
- DayFlow — Tier-1 validator, instrumentation lands W1
- Billu — Tier-1 validator, instrumentation lands W1
- Maze/PPR/Paisa — deferred (Q2 deprioritized per `project_q2_focus` memory)
- External clients (Dharmik) — deferred to W6 post-stability

**Propagation mechanism**: shared dependency with Tokens — both charters wait on charter-aware `upgrade-clients.sh`. Until ship, manual god-mode deploy on activation day.

---

## 13. Charter log (append-only)

| Date | Event | Owner | Artifact |
|---|---|---|---|
| 2026-04-20 | Charter created | CEO of Asawa | this file |

Each milestone (waves W0-W6) appends one row.

---

## 14. Operationalization

### 1. Measurement mechanism
KPIs in §3 (task wall-time P50/P95, governance overhead %, top-1 sink concentration, hook chain P95, sub-agent round-trip, boot load, per-company delta). Source: `holding/LATENCY-LOG.jsonl` once W1 instrumentation ships. Until then: presence-only — charter is referenceable, KRs at 0.0.

### 2. Adoption mechanism
W1 instruments Sutra self via `_now_ms` in dispatcher hooks + `latency-collector.sh` parsing session JSONL. W2 collects 2 weeks real usage (zero behavior change). W6 propagates to DayFlow + Billu via charter-aware `upgrade-clients.sh` (shared dep with Tokens KR4).

### 3. Monitoring / escalation
Live ANALYTICS-PULSE Speed panel (when W1 ships). Weekly review at Roadmap Meeting; quarterly OKR Review. Wave gate protocol — each wave artifact must land in committed repo before next wave begins. Breach thresholds in §3 fire alerts; governance overhead ≥30% (breach) becomes the automatic #1 cut per §11.

### 4. Iteration trigger
W2 collection <50 tasks per company in 2 weeks → extend W2 by 2 more weeks before W3 (per §11 failure mode). W4 proposal rejected 3× by founder → Sutra-OS rewrites proposal framework + charter pauses. Governance overhead measured ≥30% → automatic top-priority cut (§11). New tool surface added to harness → §6 phase taxonomy review (cascades to SPEED-phase-taxonomy.md §4).

### 5. DRI
CEO of Sutra (charter DRI). Analytics dept (data pipeline, 9th flagship metric `task_wall_time_p50`). Engineering (hook timestamps + collector). Operations (sample-size gate, "≥100 samples = enough"). Founder (W4 cut approval, individually per cut not batched).

### 6. Decommission criteria
**Satisfied closure** (valid SUCCESS): W3 RCA finds no time sink >20% on any company → KR2=1.0, charter closes "no cuts needed." Otherwise: when all 4 KRs ≥0.7 + propagation complete by Jun 30, 2026, charter transitions to maintenance-mode (quarterly health pulse only; reactivates if any KPI re-breaches Warn threshold for 2+ consecutive quarters).

## 15. Pointers

- Sibling charter: [TOKENS.md](TOKENS.md)
- Analytics Dept: `holding/departments/analytics/CHARTER.md`
- Estimation Engine: `sutra/layer2-operating-system/d-engines/ESTIMATION-ENGINE.md`
- Existing time data: `holding/ESTIMATION-LOG.jsonl` (task-level duration_min; feeds W0 seed analysis)
- Telemetry contract (for eventual plugin push): `holding/departments/analytics/TELEMETRY-CONTRACT.md`
- Readability gate (applies to SPEED pulse output): `holding/READABILITY-STANDARD.md`
- Founder memory: `feedback_speed_is_core.md`, `feedback_wait_for_data_before_optimize.md`
