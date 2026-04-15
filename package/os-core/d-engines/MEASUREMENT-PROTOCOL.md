# Sutra -- Measurement Protocol

> The definitive list of what the system measures to improve itself. Every version of Sutra should improve these numbers.

**Version**: 1.0
**Date**: 2026-04-06
**Feeds**: SUTRA-KPI.md (V, C, A, U), OKRs.md (all charters), CALIBRATION-STATE.json

---

## How to Read This Document

Each metric follows the same structure:

| Field | Meaning |
|-------|---------|
| **ID** | Stable identifier (e.g., S-01). Use in references. |
| **Name** | Human-readable name |
| **Formula** | How to compute it |
| **Data source** | Which file, hook, or log captures it |
| **Cadence** | Per-task, per-session, per-week, per-version |
| **Target** | What "good" looks like |
| **Breach action** | What happens when the target is missed |
| **Feeds** | Which charter/OKR/KPI this metric supports |
| **Status** | YES (currently captured), PARTIAL (some data exists), NO (not yet captured) |
| **Implementation** | If NO/PARTIAL: what's needed to capture it |
| **Effort** | LOW / MEDIUM / HIGH |
| **Priority** | P1 (high impact, low effort) through P4 (low impact, high effort) |

---

## 1. Speed Metrics

### S-01: Startup Latency

| Field | Value |
|-------|-------|
| **Name** | Time from founder's first message to first useful action |
| **Formula** | `first_action_ts - session_start_ts` (seconds) |
| **Data source** | SessionStart hook timestamp vs first tool-call timestamp |
| **Cadence** | Per-session |
| **Target** | < 10 seconds |
| **Breach action** | If median > 15s over 5 sessions: audit session-start file loading. Defer more files. |
| **Feeds** | Speed charter, OKR "Startup to first action < 10s" |
| **Status** | YES -- `startup_latency_sec` field added to SESSION-CHECKPOINTS.md schema (2026-04-06). |
| **Implementation** | Checkpoint JSON includes `startup_latency_sec` field. Populated by LLM at session end. |
| **Effort** | LOW |
| **Priority** | P1 |

### S-02: Task Duration (per depth level)

| Field | Value |
|-------|-------|
| **Name** | Wall-clock time from task start to task completion |
| **Formula** | `actuals.duration_min` from ESTIMATION-LOG.jsonl, segmented by `thoroughness_level` |
| **Data source** | ESTIMATION-LOG.jsonl |
| **Cadence** | Per-task |
| **Target** | V_L1 < 5 min, V_L2 < 20 min, V_L3 < 60 min, V_L4 < 240 min |
| **Breach action** | If V_L2 > 25 min over 10-task window: investigate. Check if tasks are mis-leveled or if governance overhead is the cause. |
| **Feeds** | Speed charter, KPI V (Velocity) |
| **Status** | YES |
| **Implementation** | Already captured in ESTIMATION-LOG.jsonl `actuals.duration_min`. |
| **Effort** | -- |
| **Priority** | -- |

### S-03: Lifecycle Phase Duration

| Field | Value |
|-------|-------|
| **Name** | Time spent in each lifecycle phase (OBJECTIVE, OBSERVE, SHAPE, PLAN, EXECUTE, MEASURE, LEARN) |
| **Formula** | `phase_end_ts - phase_start_ts` per phase |
| **Data source** | Phase transition timestamps in session log |
| **Cadence** | Per-task |
| **Target** | PLAN < 10% of total task time. MEASURE < 5%. LEARN < 2%. |
| **Breach action** | If PLAN > 20% of total time over 5 tasks: estimation process is too heavy. Review compression eligibility. |
| **Feeds** | Speed charter, Efficiency charter |
| **Status** | NO |
| **Implementation** | Add phase transition timestamps to ESTIMATION-LOG.jsonl as optional `phases` object: `{"plan_start": ts, "plan_end": ts, "execute_start": ts, ...}`. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### S-04: Hook Latency

| Field | Value |
|-------|-------|
| **Name** | Time consumed by each hook per tool call |
| **Formula** | `hook_end_ts - hook_start_ts` per hook invocation |
| **Data source** | Hook execution logs (new: hook timing log) |
| **Cadence** | Per-session (aggregated) |
| **Target** | No single hook > 500ms. Total hook overhead < 5% of session wall-clock. |
| **Breach action** | If any hook consistently > 1s: defer or optimize. If total hook overhead > 10%: run hook audit per Speed charter roadmap. |
| **Feeds** | Speed charter, OKR "Audit all hooks for deferral opportunities" |
| **Status** | NO |
| **Implementation** | Wrap each hook in timing instrumentation. Log to `holding/HOOK-TIMING-LOG.jsonl`. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### S-05: Agent Dispatch Overhead

| Field | Value |
|-------|-------|
| **Name** | Time and tokens to spin up a sub-agent, including context transfer |
| **Formula** | `agent_ready_ts - agent_dispatch_ts` (time). `agent_bootstrap_tokens` (tokens consumed before first productive action). |
| **Data source** | Agent dispatch events (new sensor needed) |
| **Cadence** | Per-agent-dispatch |
| **Target** | Dispatch overhead < 15s and < 5K tokens per agent |
| **Breach action** | If overhead > 25s or > 10K tokens: consider inlining the task instead of dispatching. Flag in Efficiency charter. |
| **Feeds** | Speed charter, Efficiency charter |
| **Status** | NO |
| **Implementation** | Log agent dispatch and ready timestamps. Track tokens consumed in agent bootstrap vs productive work. |
| **Effort** | HIGH |
| **Priority** | P3 |

### S-06: Productive Time Ratio

| Field | Value |
|-------|-------|
| **Name** | Session productive time vs total wall-clock time |
| **Formula** | `(total_session_min - governance_overhead_min - idle_min) / total_session_min` |
| **Data source** | Session timestamps + phase durations |
| **Cadence** | Per-session |
| **Target** | > 80% |
| **Breach action** | If < 70% over 3 sessions: audit what's consuming non-productive time. |
| **Feeds** | Speed charter, Efficiency charter |
| **Status** | NO |
| **Implementation** | Requires S-03 (phase durations) and S-04 (hook latency) to compute. Derived metric. |
| **Effort** | LOW (once S-03 and S-04 exist) |
| **Priority** | P3 |

---

## 2. Token Metrics

### T-01: Governance Overhead Ratio

| Field | Value |
|-------|-------|
| **Name** | Tokens spent loading governance files / total session tokens |
| **Formula** | `governance_tokens / total_session_tokens` |
| **Data source** | TOKEN-AUDIT.md methodology applied per session. Track files read in SessionStart hook. |
| **Cadence** | Per-session |
| **Target** | < 15% (from Speed charter OKR) |
| **Breach action** | If > 20%: trigger lazy-loading review. Defer more governance files. Compress verbose ones. |
| **Feeds** | Speed charter, Efficiency charter, OKR "Enforce context budget" |
| **Status** | YES -- `governance_overhead` object in SESSION-CHECKPOINTS.md schema captures files_loaded, files_used, unused_ratio, token estimates, and overhead_pct (2026-04-06). |
| **Implementation** | Checkpoint JSON `governance_overhead` object populated by LLM at session end. Static baseline from TOKEN-AUDIT.md. |
| **Effort** | MEDIUM |
| **Priority** | P1 |

### T-02: Per-File Token Cost

| Field | Value |
|-------|-------|
| **Name** | Token cost for every file read during a session |
| **Formula** | `file_chars * 1.3` (estimated tokens per file read) |
| **Data source** | File read events tracked via hook or manual log |
| **Cadence** | Per-session (aggregated) |
| **Target** | Informational -- no threshold. Used for optimization targeting. |
| **Breach action** | Identify top-5 costliest files per session. Flag any file > 10K tokens for compression review. |
| **Feeds** | Efficiency charter, Simplicity charter |
| **Status** | PARTIAL -- TOKEN-AUDIT.md has static estimates for governance files. Dynamic per-session tracking absent. |
| **Implementation** | Log file path and character count on each Read tool invocation. Append to session-level tracking structure. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### T-03: Per-Task Token Cost (Estimated vs Actual)

| Field | Value |
|-------|-------|
| **Name** | Token cost for a task, estimated at PRE and measured at POST |
| **Formula** | `estimates.tokens_total` vs `actuals.tokens_total` from ESTIMATION-LOG.jsonl |
| **Data source** | ESTIMATION-LOG.jsonl |
| **Cadence** | Per-task |
| **Target** | Accuracy (T-03a): `accuracy.tokens_pct > 0.70` rolling 20-task average |
| **Breach action** | If accuracy < 0.50 for 2 consecutive weeks: review heuristics per ESTIMATION-ENGINE.md calibration section. |
| **Feeds** | Accuracy charter, KPI A, Efficiency charter, KPI U |
| **Status** | YES |
| **Implementation** | Captured in ESTIMATION-LOG.jsonl. |
| **Effort** | -- |
| **Priority** | -- |

### T-04: Agent Token Cost

| Field | Value |
|-------|-------|
| **Name** | Tokens consumed by sub-agents vs main session |
| **Formula** | `agent_tokens / total_session_tokens` per agent dispatch |
| **Data source** | Agent dispatch log (new sensor) |
| **Cadence** | Per-session |
| **Target** | Agent overhead < 20% of session tokens for L1-L2 tasks. No limit for L3-L4. |
| **Breach action** | If agent overhead > 30% on L1-L2 tasks: inline the work instead of dispatching. |
| **Feeds** | Efficiency charter, OKR "Smarter agent dispatch" |
| **Status** | NO |
| **Implementation** | Track token consumption per agent. Requires agent-level session metadata. |
| **Effort** | HIGH |
| **Priority** | P3 |

### T-05: Wasted Token Ratio

| Field | Value |
|-------|-------|
| **Name** | Files loaded but never referenced in actions |
| **Formula** | `(files_read - files_referenced_in_output) / files_read` |
| **Data source** | Session file-read log cross-referenced with files mentioned in tool calls |
| **Cadence** | Per-session |
| **Target** | < 20% waste |
| **Breach action** | If > 30%: identify the most-wasted files. Move them to deferred loading or remove from mandatory session reads. |
| **Feeds** | Efficiency charter, Simplicity charter |
| **Status** | NO |
| **Implementation** | Log all files read. At session end, compare to files edited/referenced. Compute ratio. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### T-06: Context Window Utilization

| Field | Value |
|-------|-------|
| **Name** | Percentage of available context consumed by governance vs task work |
| **Formula** | `governance_tokens / context_window_size` (governance %). `task_tokens / context_window_size` (task %). |
| **Data source** | T-01 (governance tokens) + total session token tracking |
| **Cadence** | Per-session |
| **Target** | Governance < 15% of context window. Task work > 60%. |
| **Breach action** | If governance > 25% of context window: mandatory compression cycle (C metric contraction trigger). |
| **Feeds** | Efficiency charter, Simplicity charter |
| **Status** | PARTIAL -- static estimate exists from TOKEN-AUDIT.md. |
| **Implementation** | Derived from T-01. Requires per-session governance token tracking. |
| **Effort** | LOW (once T-01 exists) |
| **Priority** | P2 |

### T-07: Compression Savings

| Field | Value |
|-------|-------|
| **Name** | Tokens saved by lazy loading, versioning splits, and file compression |
| **Formula** | `tokens_if_all_loaded - tokens_actually_loaded` per session |
| **Data source** | TOKEN-AUDIT.md baseline (96,471 tokens if all loaded) minus actual loaded |
| **Cadence** | Per-session |
| **Target** | > 70% savings vs full-load baseline |
| **Breach action** | If savings < 50%: too many deferred files are being triggered. Review trigger conditions. |
| **Feeds** | Efficiency charter, Speed charter |
| **Status** | PARTIAL -- TOKEN-AUDIT.md calculates static savings (~88% reduction). Per-session dynamic measurement absent. |
| **Implementation** | Track actual files loaded per session. Compare to full-load baseline. |
| **Effort** | LOW |
| **Priority** | P2 |

---

## 3. Estimation Metrics

### E-01: Estimation Accuracy (EWMA)

| Field | Value |
|-------|-------|
| **Name** | EWMA-based estimation accuracy for tokens, cost, and duration |
| **Formula** | `EWMA_t = 0.3 * accuracy_t + 0.7 * EWMA_{t-1}` per dimension |
| **Data source** | CALIBRATION-STATE.json `global_ewma` + per-category EWMAs |
| **Cadence** | Per-task (updated), per-version (snapshot) |
| **Target** | Global EWMA > 0.85. Per-category EWMA > 0.80 for compression eligibility. |
| **Breach action** | If global EWMA < 0.75: heuristic review. If per-category EWMA < 0.65 for 3 consecutive entries: decompression trigger fires. |
| **Feeds** | Accuracy charter, KPI A (A_estimation = 0.7 weight) |
| **Status** | YES |
| **Implementation** | Captured in CALIBRATION-STATE.json. Updated by MEASURE phase auto-capture. |
| **Effort** | -- |
| **Priority** | -- |

### E-02: Per-Category Calibration Accuracy

| Field | Value |
|-------|-------|
| **Name** | Estimation accuracy segmented by category_key |
| **Formula** | `ewma_tokens[K]`, `ewma_cost[K]`, `ewma_duration[K]` from CALIBRATION-STATE.json |
| **Data source** | CALIBRATION-STATE.json `categories.{K}.ewma_*` |
| **Cadence** | Per-task |
| **Target** | Each category: all three EWMA dimensions > 0.70 |
| **Breach action** | If any dimension < 0.50 for a category over 3 entries: review heuristics for that category. If multiplier hits bounds [0.2, 5.0]: flag for manual review or category splitting. |
| **Feeds** | Accuracy charter, OKR "Reduce A_sigma below 15%" |
| **Status** | YES |
| **Implementation** | Captured in CALIBRATION-STATE.json. |
| **Effort** | -- |
| **Priority** | -- |

### E-03: Estimation Drift

| Field | Value |
|-------|-------|
| **Name** | Trend of estimation accuracy over time -- improving, stable, or degrading |
| **Formula** | `EWMA_current - EWMA_10_tasks_ago`. Improving: > +3%. Degrading: < -3%. Stable: within +/-3%. |
| **Data source** | CALIBRATION-STATE.json EWMA history (requires storing EWMA snapshots) |
| **Cadence** | Per-10-tasks (rolling) |
| **Target** | Stable or improving |
| **Breach action** | If degrading for 20+ tasks: systemic review. Check if codebase complexity changed, task mix shifted, or model behavior changed. |
| **Feeds** | Accuracy charter |
| **Status** | PARTIAL -- current EWMA exists but historical snapshots are not stored. |
| **Implementation** | Add `ewma_history` array to CALIBRATION-STATE.json. Append `{ts, ewma_tokens, n}` on each update. Keep last 50 entries. |
| **Effort** | LOW |
| **Priority** | P2 |

### E-04: Cold-Start Accuracy

| Field | Value |
|-------|-------|
| **Name** | Estimation accuracy for first-time task categories (n < 5, no calibration data) |
| **Formula** | `mean(accuracy.tokens_pct where category == "first_occurrence")` |
| **Data source** | ESTIMATION-LOG.jsonl filtered by `category == "first_occurrence"` |
| **Cadence** | Per-version |
| **Target** | > 0.60 |
| **Breach action** | If < 0.50: review base heuristics in ESTIMATION-ENGINE.md. Cold-start heuristics are systematically biased. |
| **Feeds** | Accuracy charter, OKR "Collect 30+ calibration data points" |
| **Status** | YES |
| **Implementation** | Queryable from ESTIMATION-LOG.jsonl. Current cold-start accuracy: 65.8% (from 11 initial records). |
| **Effort** | -- |
| **Priority** | -- |

### E-05: Compression Eligibility

| Field | Value |
|-------|-------|
| **Name** | Categories eligible for compressed estimation (reduced overhead) |
| **Formula** | Count of categories where `n >= 10 AND all(ewma_d > 0.80)` |
| **Data source** | CALIBRATION-STATE.json |
| **Cadence** | Per-task (checked on POST capture) |
| **Target** | At least 3 categories compressed by end of Q2 2026 |
| **Breach action** | Informational. More compressed categories = less estimation overhead. Track as a progress indicator. |
| **Feeds** | Speed charter, Efficiency charter |
| **Status** | YES |
| **Implementation** | Tracked in CALIBRATION-STATE.json `compressed` field per category. Currently 0 categories compressed (highest is `sutra:build` at n=4). |
| **Effort** | -- |
| **Priority** | -- |

### E-06: Estimation Sigma

| Field | Value |
|-------|-------|
| **Name** | Standard deviation of estimation accuracy across recent tasks |
| **Formula** | `std(accuracy.tokens_pct)` across rolling 20-task window |
| **Data source** | ESTIMATION-LOG.jsonl |
| **Cadence** | Per-version |
| **Target** | sigma < 15% (from Accuracy charter OKR) |
| **Breach action** | If sigma > 20%: identify high-variance categories. Target those categories for calibration work. |
| **Feeds** | Accuracy charter, KPI A (supplementary statistic) |
| **Status** | YES -- computable from ESTIMATION-LOG.jsonl. Sigma computation defined; report at version-bump KPI snapshot (2026-04-06). |
| **Implementation** | Data exists in ESTIMATION-LOG.jsonl. `std(accuracy.tokens_pct)` over rolling 20-task window. |
| **Effort** | LOW |
| **Priority** | P1 |

---

## 4. Quality Metrics

### Q-01: Rework Rate

| Field | Value |
|-------|-------|
| **Name** | Percentage of tasks that require redo or significant correction |
| **Formula** | `tasks_with_rework / total_tasks_completed` |
| **Data source** | LEARN.md entries with `rework: true` flag (new field) |
| **Cadence** | Per-version |
| **Target** | < 10% |
| **Breach action** | If > 15%: review depth routing. Rework usually means undertriage -- tasks getting less process than they need. |
| **Feeds** | First-Time QA charter, Accuracy charter |
| **Status** | NO |
| **Implementation** | Add `rework` boolean to LEARN.md feedback format and ESTIMATION-LOG.jsonl `actuals_meta`. Detect via: subsequent commits touching same files within 24h that aren't part of the same task. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### Q-02: Bug Introduction Rate

| Field | Value |
|-------|-------|
| **Name** | Bugs created per feature shipped |
| **Formula** | `bugs_filed / features_shipped` over a time window |
| **Data source** | TODO.md (bugs tagged) / LEARN.md entries noting bugs |
| **Cadence** | Per-version |
| **Target** | < 0.2 bugs per feature |
| **Breach action** | If > 0.3: review test coverage at depth levels where bugs are introduced. Consider raising depth floor for bug-prone categories. |
| **Feeds** | First-Time QA charter, Accuracy charter |
| **Status** | NO |
| **Implementation** | Tag bugs in TODO.md with `[BUG]` prefix and link to originating feature. Count at version boundary. |
| **Effort** | LOW |
| **Priority** | P2 |

### Q-03: Principle Violation Rate

| Field | Value |
|-------|-------|
| **Name** | How often principle regression tests fire |
| **Formula** | `principle_tests_failed / principle_tests_run` |
| **Data source** | Principle regression test suite output (per Accuracy charter OKR) |
| **Cadence** | Per-task (for L3+), per-session (for compliance checks) |
| **Target** | < 5% violation rate |
| **Breach action** | If > 10%: principles are either being ignored or are unreasonable. Review the specific principles being violated. |
| **Feeds** | Accuracy charter, KPI A (A_compliance = 0.3 weight) |
| **Status** | NO |
| **Implementation** | Requires principle regression test suite (Accuracy charter roadmap item 3, June 2026). |
| **Effort** | HIGH |
| **Priority** | P3 |

### Q-04: Process Skip Rate

| Field | Value |
|-------|-------|
| **Name** | How often lifecycle phases are skipped |
| **Formula** | `phases_skipped / phases_expected` by depth level. Separate legitimate L1 fast-path skips from illegitimate skips. |
| **Data source** | Task lifecycle logs. Compare expected pipeline (per ADAPTIVE-PROTOCOL.md level definitions) to actually executed pipeline. |
| **Cadence** | Per-task |
| **Target** | Illegitimate skip rate: 0%. L1 fast-path skip rate: tracking only (expected to be high). |
| **Breach action** | If illegitimate skips > 5%: enforcement may be too soft. Consider upgrading from SOFT to HARD for the affected phase. |
| **Feeds** | Accuracy charter, Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Log expected vs actual pipeline per task. Flag deviations. |
| **Effort** | MEDIUM |
| **Priority** | P3 |

### Q-05: First-Time QA Pass Rate

| Field | Value |
|-------|-------|
| **Name** | Onboarding self-check findings per deploy |
| **Formula** | `deploys_passing_first_check / total_deploys` |
| **Data source** | Onboarding QA checklist results |
| **Cadence** | Per-onboarding |
| **Target** | 100% first-deploy pass rate (from First-Time QA charter) |
| **Breach action** | Any failure: post-mortem to identify what the self-check missed. Update self-check. |
| **Feeds** | First-Time QA charter, OKR "rework items per onboarding < 2" |
| **Status** | PARTIAL -- manual tracking exists (Paisa onboarding was "relatively clean") but no structured measurement. |
| **Implementation** | Structured QA report per onboarding: pass/fail per check, findings count, rework items. |
| **Effort** | LOW |
| **Priority** | P2 |

---

## 5. Adaptive Protocol Metrics

### A-01: Triage Accuracy

| Field | Value |
|-------|-------|
| **Name** | Undertriage vs overtriage vs correct rate |
| **Formula** | From LEARN.md `triage_class` field: `count(correct) / total`, `count(undertriage) / total`, `count(overtriage) / total` |
| **Data source** | LEARN.md per-task feedback |
| **Cadence** | Per-task (recorded), per-version (aggregated) |
| **Target** | Correct > 65%. Undertriage < 5%. Overtriage < 30%. |
| **Breach action** | Undertriage > 5%: all locked routing rules unlock (per ADAPTIVE-PROTOCOL.md). Overtriage > 30%: review locked rules for most over-triaged categories. |
| **Feeds** | Human-LLM Interaction charter, Accuracy charter |
| **Status** | YES -- Triage check (CORRECT/UNDERTRIAGE/OVERTRIAGE) added to TASK-LIFECYCLE.md Phase 7 LEARN (2026-04-06). |
| **Implementation** | LEARN phase now requires triage check on every task. Feeds A-01 aggregation. |
| **Effort** | LOW |
| **Priority** | P1 |

### A-02: Depth Routing Correctness

| Field | Value |
|-------|-------|
| **Name** | Was the selected depth level correct for the task? |
| **Formula** | `abs(depth_selected - depth_correct)` from LEARN.md |
| **Data source** | LEARN.md `depth_selected` and `depth_correct` fields |
| **Cadence** | Per-task |
| **Target** | Mean absolute delta < 0.5 |
| **Breach action** | If mean delta > 1.0: routing model is significantly miscalibrated. Review parameter weights. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | YES -- Captured via same triage check as A-01 in TASK-LIFECYCLE.md Phase 7 LEARN (2026-04-06). |
| **Implementation** | LEARN phase triage check captures depth_selected vs depth_correct. Same enforcement as A-01. |
| **Effort** | LOW |
| **Priority** | P1 |

### A-03: Pre-Scoring Gate Fire Rate

| Field | Value |
|-------|-------|
| **Name** | How often pre-scoring gates trigger and bypass parameter scoring |
| **Formula** | `tasks_with_gate_triggered / total_tasks` by gate type |
| **Data source** | Adaptive Protocol output log `gate_triggered` field |
| **Cadence** | Per-version |
| **Target** | Informational. Gates should fire when appropriate (not too often, not too rarely). |
| **Breach action** | If auth-pii gate fires > 40% of tasks: either the company handles a lot of sensitive data (expected) or the gate is too sensitive (review). If no gate fires in 50+ tasks: verify gates are actually running. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | PARTIAL -- ADAPTIVE-PROTOCOL.md defines gate logging but no aggregation exists. |
| **Implementation** | Aggregate gate_triggered field from Adaptive Protocol outputs. |
| **Effort** | LOW |
| **Priority** | P2 |

### A-04: Problem-Type Classification Accuracy

| Field | Value |
|-------|-------|
| **Name** | Was the Cynefin classification (Clear/Complicated/Complex/Chaotic) correct? |
| **Formula** | `count(problem_type_correct == problem_type_selected) / total` from LEARN.md |
| **Data source** | LEARN.md `problem_type_selected` and `problem_type_correct` fields |
| **Cadence** | Per-task (recorded), per-version (aggregated) |
| **Target** | > 80% classification accuracy |
| **Breach action** | If < 70%: review classification criteria. The biggest risk is classifying Complex as Clear (missing unknown unknowns). |
| **Feeds** | Human-LLM Interaction charter, Accuracy charter |
| **Status** | YES -- Problem type check (clear/complicated/complex/chaotic) added to TASK-LIFECYCLE.md Phase 7 LEARN (2026-04-06). |
| **Implementation** | LEARN phase now requires problem_type_selected vs problem_type_correct on every task. |
| **Effort** | LOW |
| **Priority** | P1 |

---

## 6. Human-LLM Interaction Metrics

### H-01: Input Classification Compliance

| Field | Value |
|-------|-------|
| **Name** | Percentage of founder inputs classified before action |
| **Formula** | `inputs_classified / total_inputs` |
| **Data source** | Input routing hook (per Human-LLM Interaction charter) |
| **Cadence** | Per-session |
| **Target** | > 90% (from charter OKR) |
| **Breach action** | If < 80%: input routing hook is not firing or is being bypassed. Review hook configuration. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Requires Input Routing Level 2 deployment (Human-LLM Interaction charter roadmap item 1). Count classifications per session. |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### H-02: Classification Accuracy

| Field | Value |
|-------|-------|
| **Name** | Was the input type classification correct? |
| **Formula** | `correct_classifications / total_classifications` (founder confirms or corrects) |
| **Data source** | Input routing hook output + founder correction events |
| **Cadence** | Per-session |
| **Target** | > 95% (from charter KPI "Routing accuracy") |
| **Breach action** | If < 90%: review classification logic. Common failure: confusing "direction" with "task." |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Log each classification. Track founder corrections (explicit "no, I meant..."). |
| **Effort** | MEDIUM |
| **Priority** | P2 |

### H-03: Founder Override Rate

| Field | Value |
|-------|-------|
| **Name** | How often the founder overrides system recommendations |
| **Formula** | `overrides / total_recommendations` segmented by type (depth override, gate override, estimate override) |
| **Data source** | LEARN.md `override: true` entries + Adaptive Protocol override logs |
| **Cadence** | Per-version |
| **Target** | Informational. High override rate means the system's defaults don't match the founder's judgment. |
| **Breach action** | If > 30%: the system is miscalibrated to the founder's preferences. Review the most-overridden defaults. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | PARTIAL -- ADAPTIVE-PROTOCOL.md defines override logging but no aggregation. |
| **Implementation** | Aggregate override events from LEARN.md and protocol logs. |
| **Effort** | LOW |
| **Priority** | P2 |

### H-04: Direction Capture Rate

| Field | Value |
|-------|-------|
| **Name** | Are new founder directions being captured when given? |
| **Formula** | `directions_captured / directions_given` (detected direction-type inputs that result in FOUNDER-DIRECTIONS.md updates) |
| **Data source** | Input routing classification (direction-type) + FOUNDER-DIRECTIONS.md git diff |
| **Cadence** | Per-session |
| **Target** | 100% -- every direction should be captured |
| **Breach action** | Any missed direction: the direction classification is failing or the capture workflow is broken. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Requires input routing + direction detection. Cross-reference direction-classified inputs against FOUNDER-DIRECTIONS.md changes. |
| **Effort** | MEDIUM |
| **Priority** | P3 |

### H-05: Decision Response Time

| Field | Value |
|-------|-------|
| **Name** | Time between system presenting a decision and founder responding |
| **Formula** | `founder_response_ts - decision_presented_ts` |
| **Data source** | Session timestamps for decision presentations and founder responses |
| **Cadence** | Per-decision event |
| **Target** | Informational. Long response times may indicate unclear decision framing. |
| **Breach action** | If median > 60s: decisions may not be presented clearly enough. Review Human Readability charter outputs. |
| **Feeds** | Human Readability charter, Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Track decision presentation events and founder response events in session log. |
| **Effort** | MEDIUM |
| **Priority** | P3 |

---

## 7. Research Metrics

### R-01: Research Freshness

| Field | Value |
|-------|-------|
| **Name** | Days since last refresh per research domain |
| **Formula** | `current_date - last_refresh_date` per domain |
| **Data source** | Research file modification dates + research index (new: RESEARCH-INDEX.md) |
| **Cadence** | Per-week |
| **Target** | AI/tech: < 7 days. Frameworks: < 14 days. Company operations: < 30 days. |
| **Breach action** | If AI/tech > 14 days stale: schedule research session. If frameworks > 30 days: flag in next Roadmap Meeting. |
| **Feeds** | External Research charter |
| **Status** | PARTIAL -- research files exist with dates. No automated freshness tracking. |
| **Implementation** | Create RESEARCH-INDEX.md listing each research domain with last-refresh date. Check freshness weekly. |
| **Effort** | LOW |
| **Priority** | P2 |

### R-02: Patterns Adopted

| Field | Value |
|-------|-------|
| **Name** | Research findings that became protocol changes |
| **Formula** | Count of research-to-protocol adoptions per quarter |
| **Data source** | RELEASES.md (version notes citing research) + research files |
| **Cadence** | Per-quarter |
| **Target** | 5+ per quarter (from External Research charter OKR) |
| **Breach action** | If 0 in a quarter: research is not actionable. Review research selection criteria. |
| **Feeds** | External Research charter |
| **Status** | PARTIAL -- some adoptions noted (Cynefin, Wardley, military ROE in ADAPTIVE-PROTOCOL.md v2) but no formal count. |
| **Implementation** | Tag each RELEASES.md entry with `research_source` when a version change cites research. Count per quarter. |
| **Effort** | LOW |
| **Priority** | P3 |

### R-03: Research ROI

| Field | Value |
|-------|-------|
| **Name** | Did research improve measurable outcomes? |
| **Formula** | For each adopted pattern: compare KPI metrics before and after adoption. `delta_KPI / research_token_cost` |
| **Data source** | SUTRA-KPI-HISTORY.md (before/after version comparison) + research task token costs |
| **Cadence** | Per-quarter |
| **Target** | Positive ROI on > 50% of adopted patterns |
| **Breach action** | If most research shows no KPI improvement: research is not targeting the right problems. Refocus research agenda. |
| **Feeds** | External Research charter, Efficiency charter |
| **Status** | NO |
| **Implementation** | Requires KPI history (SUTRA-KPI-HISTORY.md) with enough data points to isolate research impact. Earliest feasible: Q3 2026. |
| **Effort** | HIGH |
| **Priority** | P4 |

---

## 8. Cost Metrics

### C-01: USD Per Task (by depth level and category)

| Field | Value |
|-------|-------|
| **Name** | Dollar cost per task, segmented by depth level |
| **Formula** | `actuals.cost_usd` from ESTIMATION-LOG.jsonl, grouped by `thoroughness_level` |
| **Data source** | ESTIMATION-LOG.jsonl |
| **Cadence** | Per-task |
| **Target** | U_L1 < $0.30. U_L2 < $1.50. U_L3 < $5.00. U_L4 < $15.00. |
| **Breach action** | If L2 cost > $2.00 over 10-task window: investigate. Check governance overhead and agent dispatch costs. |
| **Feeds** | Efficiency charter, KPI U |
| **Status** | YES |
| **Implementation** | Captured in ESTIMATION-LOG.jsonl. |
| **Effort** | -- |
| **Priority** | -- |

### C-02: USD Per Session

| Field | Value |
|-------|-------|
| **Name** | Total dollar cost per session |
| **Formula** | `sum(actuals.cost_usd)` for all tasks in session + governance overhead token cost |
| **Data source** | ESTIMATION-LOG.jsonl (task costs) + session metadata (governance cost) |
| **Cadence** | Per-session |
| **Target** | Informational. Trend should be decreasing per unit of output. |
| **Breach action** | If session cost > $20 without commensurate output: review what consumed the tokens. |
| **Feeds** | Efficiency charter |
| **Status** | PARTIAL -- task costs captured. Session-level aggregation not automated. |
| **Implementation** | Sum task costs in session. Add governance overhead estimate from T-01. Log in checkpoint JSON. |
| **Effort** | LOW |
| **Priority** | P2 |

### C-03: USD Per Company Per Week

| Field | Value |
|-------|-------|
| **Name** | Weekly cost per company |
| **Formula** | `sum(actuals.cost_usd where company == X and ts within week)` |
| **Data source** | ESTIMATION-LOG.jsonl filtered by company and date |
| **Cadence** | Per-week |
| **Target** | Informational. Used for portfolio-level cost visibility. |
| **Breach action** | If any company's weekly cost > 5x its historical average: investigate whether scope expanded or efficiency degraded. |
| **Feeds** | Efficiency charter |
| **Status** | PARTIAL -- queryable from ESTIMATION-LOG.jsonl but not auto-aggregated. |
| **Implementation** | Weekly query script against ESTIMATION-LOG.jsonl. Add to weekly review template. |
| **Effort** | LOW |
| **Priority** | P2 |

### C-04: Model Pricing Sensitivity

| Field | Value |
|-------|-------|
| **Name** | Cost impact of model switches |
| **Formula** | `cost_at_model_A / cost_at_model_B` for equivalent tasks |
| **Data source** | ESTIMATION-ENGINE.md model pricing table + ESTIMATION-LOG.jsonl |
| **Cadence** | Per-model-change |
| **Target** | Informational. Helps decide when to route tasks to cheaper models. |
| **Breach action** | If Opus cost > 5x Sonnet cost for equivalent task quality: consider model routing for L1-L2 tasks. |
| **Feeds** | Efficiency charter |
| **Status** | NO |
| **Implementation** | When model pricing changes: annotate version boundary in ESTIMATION-LOG.jsonl. Compute cost delta for comparable task categories. |
| **Effort** | LOW |
| **Priority** | P3 |

### C-05: Cost Trend

| Field | Value |
|-------|-------|
| **Name** | Is cost per task decreasing over time? |
| **Formula** | Linear regression slope of `cost_usd` over task sequence, per depth level |
| **Data source** | ESTIMATION-LOG.jsonl |
| **Cadence** | Per-version |
| **Target** | Negative slope (cost decreasing) |
| **Breach action** | If slope positive for 2+ versions: efficiency is degrading. Investigate governance bloat (C metric), agent overhead (T-04), or task-mix shift. |
| **Feeds** | Efficiency charter, KPI U |
| **Status** | PARTIAL -- data exists in ESTIMATION-LOG.jsonl. Trend analysis not automated. |
| **Implementation** | At version bump: compute per-level cost trend. Report in KPI snapshot. |
| **Effort** | LOW |
| **Priority** | P2 |

---

## 9. System Health Metrics

### SH-01: Governance File Count

| Field | Value |
|-------|-------|
| **Name** | Total governance files in sutra/ and holding/ |
| **Formula** | `find sutra/ holding/ -name "*.md" | wc -l` |
| **Data source** | Filesystem scan |
| **Cadence** | Per-version |
| **Target** | L2 file count < 28 (from Simplicity charter). Total file count trending down. |
| **Breach action** | If L2 file count > 35: mandatory contraction cycle (per SUTRA-KPI.md C metric contraction trigger). |
| **Feeds** | Simplicity charter, KPI C |
| **Status** | YES |
| **Implementation** | Measured at version bump per SUTRA-KPI.md protocol. |
| **Effort** | -- |
| **Priority** | -- |

### SH-02: Cognitive Load Index

| Field | Value |
|-------|-------|
| **Name** | Composite index C from SUTRA-KPI.md |
| **Formula** | `C = F * W_avg / P` where F=file count, W_avg=avg words/file, P=active protocol count |
| **Data source** | Filesystem scan (same as SUTRA-KPI.md) |
| **Cadence** | Per-version |
| **Target** | C < 4,000 (from Simplicity charter) |
| **Breach action** | If C > 4,621 (current baseline) or increases >10% version-over-version: mandatory simplification cycle fires. |
| **Feeds** | Simplicity charter, KPI C |
| **Status** | YES |
| **Implementation** | Measured at version bump per SUTRA-KPI.md protocol. Current: 4,621. |
| **Effort** | -- |
| **Priority** | -- |

### SH-03: Hook Count and Latency

| Field | Value |
|-------|-------|
| **Name** | Number of active hooks and their cumulative latency |
| **Formula** | Count of hooks in settings.json + sum of per-hook latencies from S-04 |
| **Data source** | settings.json (hook count) + HOOK-TIMING-LOG.jsonl (latency) |
| **Cadence** | Per-version (count), per-session (latency) |
| **Target** | Hook count trending stable or down. Cumulative latency < 5% of session time. |
| **Breach action** | If hook count increases without corresponding capability: review for consolidation. If latency > 5%: optimize or defer hooks. |
| **Feeds** | Speed charter, Simplicity charter |
| **Status** | PARTIAL -- hook count is observable from settings.json. Latency not measured (see S-04). |
| **Implementation** | Hook count: query settings.json. Latency: requires S-04. |
| **Effort** | LOW (count), MEDIUM (latency) |
| **Priority** | P2 |

### SH-04: Memory/Checkpoint Freshness

| Field | Value |
|-------|-------|
| **Name** | Age of checkpoint and calibration state files |
| **Formula** | `current_date - file.updated` for CALIBRATION-STATE.json, checkpoint JSON |
| **Data source** | File modification dates |
| **Cadence** | Per-session (check on start) |
| **Target** | CALIBRATION-STATE.json: < 7 days stale. Checkpoint: < 1 day stale. |
| **Breach action** | If CALIBRATION-STATE.json > 14 days stale: calibration data may be outdated. Flag for review. |
| **Feeds** | Accuracy charter |
| **Status** | PARTIAL -- files have timestamps but staleness is not checked automatically. |
| **Implementation** | SessionStart hook checks `updated` field in CALIBRATION-STATE.json. Alert if stale. |
| **Effort** | LOW |
| **Priority** | P2 |

### SH-05: Direction Encoding Completeness

| Field | Value |
|-------|-------|
| **Name** | Are all active founder directions encoded in FOUNDER-DIRECTIONS.md? |
| **Formula** | `directions_encoded / directions_given` (requires tracking directions given vs captured) |
| **Data source** | FOUNDER-DIRECTIONS.md + session logs of direction-type inputs |
| **Cadence** | Per-week |
| **Target** | 100% |
| **Breach action** | Any unencoded direction: capture it immediately. Persistent gaps mean the capture mechanism is failing. |
| **Feeds** | Human-LLM Interaction charter |
| **Status** | NO |
| **Implementation** | Depends on H-04 (direction capture rate). Cross-reference direction inputs against FOUNDER-DIRECTIONS.md entries. |
| **Effort** | MEDIUM |
| **Priority** | P3 |

---

## Implementation Priority Matrix

Ranked by impact/effort ratio. P1 = do first.

### P1 -- High Impact, Low-Medium Effort

| ID | Metric | Status | Effort | Reason |
|----|--------|--------|--------|--------|
| S-01 | Startup Latency | YES | LOW | `startup_latency_sec` in checkpoint schema. |
| T-01 | Governance Overhead Ratio | YES | MEDIUM | `governance_overhead` object in checkpoint schema. |
| E-06 | Estimation Sigma | YES | LOW | Computable from ESTIMATION-LOG.jsonl. |
| A-01 | Triage Accuracy | YES | LOW | Triage check added to TASK-LIFECYCLE.md LEARN phase. |
| A-02 | Depth Routing Correctness | YES | LOW | Same triage check as A-01. |
| A-04 | Problem-Type Classification Accuracy | YES | LOW | Problem type check added to LEARN phase. |

### P2 -- Medium Impact, Low-Medium Effort

| ID | Metric | Status | Effort | Reason |
|----|--------|--------|--------|--------|
| S-03 | Lifecycle Phase Duration | NO | MEDIUM | Enables S-06 and efficiency analysis. |
| S-04 | Hook Latency | NO | MEDIUM | Enables SH-03 latency tracking. |
| T-02 | Per-File Token Cost | PARTIAL | MEDIUM | Enables optimization targeting. |
| T-05 | Wasted Token Ratio | NO | MEDIUM | Direct efficiency improvement signal. |
| T-06 | Context Window Utilization | PARTIAL | LOW | Derived from T-01. |
| T-07 | Compression Savings | PARTIAL | LOW | Validates lazy loading investment. |
| E-03 | Estimation Drift | PARTIAL | LOW | Small CALIBRATION-STATE.json extension. |
| Q-01 | Rework Rate | NO | MEDIUM | Quality signal. |
| Q-02 | Bug Introduction Rate | NO | LOW | Simple tagging in TODO.md. |
| Q-05 | First-Time QA Pass Rate | PARTIAL | LOW | Structured report per onboarding. |
| A-03 | Pre-Scoring Gate Fire Rate | PARTIAL | LOW | Aggregate existing data. |
| H-01 | Input Classification Compliance | NO | MEDIUM | Depends on Input Routing Level 2 deployment. |
| H-02 | Classification Accuracy | NO | MEDIUM | Same dependency as H-01. |
| H-03 | Founder Override Rate | PARTIAL | LOW | Aggregate existing logs. |
| R-01 | Research Freshness | PARTIAL | LOW | Simple index file. |
| C-02 | USD Per Session | PARTIAL | LOW | Sum existing task costs. |
| C-03 | USD Per Company Per Week | PARTIAL | LOW | Query ESTIMATION-LOG.jsonl. |
| C-05 | Cost Trend | PARTIAL | LOW | Trend analysis at version bump. |
| SH-03 | Hook Count and Latency | PARTIAL | LOW/MEDIUM | Count is free. Latency needs S-04. |
| SH-04 | Memory/Checkpoint Freshness | PARTIAL | LOW | SessionStart check. |

### P3 -- Lower Impact or Higher Effort

| ID | Metric | Status | Effort | Reason |
|----|--------|--------|--------|--------|
| S-05 | Agent Dispatch Overhead | NO | HIGH | Requires agent-level instrumentation. |
| S-06 | Productive Time Ratio | NO | LOW* | Derived metric, but depends on S-03 and S-04. |
| T-04 | Agent Token Cost | NO | HIGH | Requires agent-level token tracking. |
| Q-04 | Process Skip Rate | NO | MEDIUM | Useful but not urgent. |
| H-04 | Direction Capture Rate | NO | MEDIUM | Depends on input routing. |
| H-05 | Decision Response Time | NO | MEDIUM | Nice-to-have interaction quality signal. |
| R-02 | Patterns Adopted | PARTIAL | LOW | Manual tagging in RELEASES.md. |
| C-04 | Model Pricing Sensitivity | NO | LOW | Only relevant on model changes. |
| SH-05 | Direction Encoding Completeness | NO | MEDIUM | Depends on H-04. |

### P4 -- Long-Term / Requires Significant Data

| ID | Metric | Status | Effort | Reason |
|----|--------|--------|--------|--------|
| Q-03 | Principle Violation Rate | NO | HIGH | Requires regression test suite (Jun 2026). |
| R-03 | Research ROI | NO | HIGH | Requires multi-version KPI history. Earliest Q3 2026. |

---

## Data Flow Diagram

```
SESSION START
    |
    +---> S-01: Startup Latency (timestamp)
    +---> T-01: Governance Overhead (files loaded)
    +---> SH-04: Checkpoint Freshness (staleness check)
    |
TASK ARRIVES
    |
    +---> Adaptive Protocol Engine
    |       +---> A-03: Gate Fire Rate (gate_triggered)
    |       +---> A-04: Problem-Type Classification (problem_type)
    |       +---> Depth level selected
    |
    +---> Estimation Engine (PLAN phase)
    |       +---> E-01: EWMA (reads calibration state)
    |       +---> E-04: Cold-Start Accuracy (first_occurrence flag)
    |       +---> E-05: Compression Eligibility (check compressed state)
    |       +---> S-03: Phase Duration (pre_start_ts)
    |
TASK EXECUTES
    |
    +---> T-02: Per-File Token Cost (files read)
    +---> S-03: Phase Duration (execute_start_ts, execute_end_ts)
    +---> S-04: Hook Latency (per hook invocation)
    +---> H-01: Input Classification (per founder input)
    |
TASK COMPLETES (MEASURE phase)
    |
    +---> ESTIMATION-LOG.jsonl (append)
    |       +---> S-02: Task Duration (actuals.duration_min)
    |       +---> T-03: Token Accuracy (accuracy.tokens_pct)
    |       +---> C-01: USD Per Task (actuals.cost_usd)
    |
    +---> CALIBRATION-STATE.json (update)
    |       +---> E-01: EWMA (global + per-category)
    |       +---> E-02: Per-Category Accuracy
    |       +---> E-05: Compression Check
    |
    +---> LEARN.md (depth evaluation)
    |       +---> A-01: Triage Accuracy
    |       +---> A-02: Depth Routing Correctness
    |       +---> A-04: Problem-Type Accuracy
    |       +---> Q-01: Rework Rate (rework flag)
    |       +---> H-03: Founder Override Rate
    |
SESSION END
    |
    +---> C-02: USD Per Session (sum)
    +---> T-05: Wasted Token Ratio (files read vs referenced)
    +---> S-06: Productive Time Ratio (computed)
    |
VERSION BUMP
    |
    +---> KPI Snapshot: V, C, A, U
    +---> E-03: Estimation Drift (EWMA trend)
    +---> E-06: Estimation Sigma
    +---> C-05: Cost Trend (per-level slope)
    +---> SH-01: Governance File Count
    +---> SH-02: Cognitive Load Index (C)
    +---> Q-02: Bug Introduction Rate
    +---> A-01 Aggregate: Triage Table
    |
WEEKLY
    +---> C-03: USD Per Company Per Week
    +---> R-01: Research Freshness
    +---> SH-05: Direction Encoding Completeness
    |
QUARTERLY
    +---> R-02: Patterns Adopted
    +---> R-03: Research ROI
```

---

## Versioning

This document is versioned with Sutra. When new metrics are added:
1. Assign the next sequential ID within its category.
2. Add it to the priority matrix.
3. Update the data flow diagram.
4. Do NOT remove metrics -- mark as DEPRECATED with rationale if no longer relevant.

When a metric moves from NO to YES:
1. Update its Status field.
2. Record the Sutra version that implemented it.
3. Establish a baseline value.

---

## Connection to KPIs and Charters

| KPI | Primary Metrics | Supporting Metrics |
|-----|----------------|-------------------|
| **V (Velocity)** | S-02 | S-01, S-03, S-06 |
| **C (Cognitive Load)** | SH-02 | SH-01, T-01, T-06 |
| **A (Accuracy)** | E-01, Q-03 | E-02, E-03, E-04, E-06, A-01, A-02, A-04 |
| **U (Unit Cost)** | C-01 | C-02, C-03, C-05, T-03, T-04 |

| Charter | Primary Metrics |
|---------|----------------|
| **Speed** | S-01, S-02, S-03, S-04, S-05, S-06 |
| **Simplicity** | SH-01, SH-02, T-01, T-05, T-06 |
| **Accuracy** | E-01, E-02, E-03, E-04, E-06, Q-01, Q-03 |
| **Efficiency** | C-01, C-02, C-03, C-05, T-01, T-03, T-04, T-07 |
| **Human Readability** | H-05 |
| **Human-LLM Interaction** | H-01, H-02, H-03, H-04, A-01, A-02, A-04 |
| **First-Time QA** | Q-01, Q-02, Q-05 |
| **External Research** | R-01, R-02, R-03 |

---

## Summary

| Category | Metrics | YES | PARTIAL | NO |
|----------|---------|-----|---------|-----|
| Speed (S) | 6 | 1 | 0 | 5 |
| Token (T) | 7 | 1 | 4 | 2 |
| Estimation (E) | 6 | 3 | 2 | 1 |
| Quality (Q) | 5 | 0 | 1 | 4 |
| Adaptive (A) | 4 | 0 | 2 | 2 |
| Human-LLM (H) | 5 | 0 | 1 | 4 |
| Research (R) | 3 | 0 | 2 | 1 |
| Cost (C) | 5 | 1 | 3 | 1 |
| System Health (SH) | 5 | 2 | 2 | 1 |
| **Total** | **46** | **8 (17%)** | **17 (37%)** | **21 (46%)** |

8 metrics are fully captured today. 17 have partial data. 21 need new implementation.

The P1 batch (6 metrics) requires only LOW-MEDIUM effort and covers the highest-impact gaps: startup latency, governance overhead, estimation sigma, and triage accuracy. Implementing these 6 would bring captured metrics from 8 to 14 (30%).
