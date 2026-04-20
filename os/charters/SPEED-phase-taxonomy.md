# Speed — Phase Taxonomy (W0 artifact)

**Parent**: `sutra/os/charters/SPEED.md`
**Purpose**: define the boundaries between phases so latency can be attributed to the right bucket. Without shared boundaries, two measurers disagree on where "input-routing" ends and "execution" begins, and the data becomes un-aggregatable.
**Status**: v1 DRAFT — codex review queued for W1 design
**Unit**: integer milliseconds throughout. Signed aggregation: `sum(phase_ms) == task_wall_ms ± 2%` tolerance.

---

## 1. Taxonomy tree

```
SESSION
├── boot-load                          [once per session, not per task]
│   ├── claude-md-load                 CLAUDE.md + CLAUDE.local.md
│   ├── memory-load                    MEMORY.md + referenced memory files
│   ├── system-reminder-load           hooks SessionStart reminders
│   └── system-map-todo-load           SYSTEM-MAP lines 1-45 + TODO lines 1-15
│
└── TASK (repeated N per session)
    ├── input-routing                  TYPE/HOME/ROUTE/FIT/ACTION block emission
    ├── depth-estimation               DEPTH/EFFORT/COST/IMPACT block + marker write
    ├── execution
    │   ├── tool-call-N                one bucket per tool invocation, includes:
    │   │   ├── hook-pretool           dispatcher-pretool.sh chain (all hooks)
    │   │   ├── tool-dispatch          harness → tool provider → result
    │   │   └── hook-posttool          dispatcher-stop / cascade-check / enforce-boundaries
    │   ├── llm-think                  extended-thinking budget consumed (if enabled)
    │   └── llm-stream                 token generation time from `start_turn` → `end_turn`
    ├── output-gate                    readability + trace formatting (output-side)
    └── task-stop                      estimation-collector, triage-collector, coverage-log append
```

---

## 2. Phase boundary rules (the hard part)

Each phase's **start event** and **end event** must be unambiguous in the session transcript. Below is the authoritative boundary rule per phase.

| Phase | Starts at | Ends at | Source |
|---|---|---|---|
| `boot-load` | Session first message timestamp | First `tool_use` OR first user-facing text, whichever is earlier | session JSONL header |
| `claude-md-load` (sub) | Boot-load start | First `system-reminder` block in messages | JSONL parse |
| `input-routing` | User prompt received | `INPUT:` / `TYPE:` / `ROUTE:` block emitted in model output | output parse (regex on trace) |
| `depth-estimation` | input-routing end | `TASK: … DEPTH: N/5` block emitted | output parse |
| `tool-call-N` | `tool_use` event | Matching `tool_result` event | JSONL pair |
| `hook-pretool` (sub) | Timestamp in dispatcher-pretool entry | Timestamp in dispatcher-pretool exit | dispatcher log (W1 adds) |
| `hook-posttool` (sub) | Timestamp in dispatcher-stop entry | Timestamp in dispatcher-stop exit | dispatcher log (W1 adds) |
| `tool-dispatch` (sub) | `tool_use` ts | `tool_result` ts | JSONL pair, minus hook-pretool and hook-posttool durations |
| `llm-think` | `thinking` block start | `thinking` block end | JSONL thinking event |
| `llm-stream` | First `text` event after last `tool_result` | `stop_reason` event | JSONL |
| `output-gate` | `stop_reason` event | Next user prompt OR session_stop | derived |
| `task-stop` | `stop_reason` (when last output of task) | `dispatcher-stop.sh` exit (captured in enforcement log) | enforcement log + dispatcher ts |

---

## 3. What counts as "governance overhead"

The governance-overhead-% KPI (charter §3) sums these phases divided by total task wall time:

```
governance_ms = boot-load (amortized per-task)
              + input-routing
              + depth-estimation
              + hook-pretool (summed across tool-calls)
              + hook-posttool (summed across tool-calls)
              + output-gate
              + task-stop
```

**Boot-load amortization**: boot happens once per session but we attribute it to tasks. Two valid models:

| Model | Formula | Use case |
|---|---|---|
| **Per-session-first-task** | Boot-load charged entirely to task #1 | Simple; matches user perception ("first response is slow") |
| **Amortized** | Boot-load / N_tasks, distributed evenly | Cleaner aggregates; better for P50/P95 across tasks |

**Decision**: use amortized for KPIs; also emit `first_task_boot_charge_ms` for observability. Both values stored.

---

## 4. Tool-specific sub-phases (open questions → W1 will finalize)

Some tools have internal structure worth breaking out. Flagged for W1 design:

| Tool | Candidate sub-phases | Risk of overreach |
|---|---|---|
| `Bash` | spawn-shell, exec, wait, capture-output | Low — timestamps easy |
| `Agent` (Task) | dispatch, child-boot, child-work, child-return | HIGH — child has its own SESSION phases; may double-count |
| `Read` | stat, read-bytes, encode | Low — but probably not worth splitting |
| `Edit` / `Write` | validate, write, post-write-hook | Medium |
| `Grep` / `Glob` | scan, filter, format | Low |
| `WebFetch` / `WebSearch` | dispatch, network-wait, parse | Medium — network dominates |

**W1 decision rule**: only split a tool's sub-phases if W0/W1 data shows that tool is ≥15% of total task time. Otherwise treat as opaque `tool-dispatch`.

---

## 5. Aggregation invariants (for collector)

The collector MUST enforce:

| # | Invariant | Check |
|---|---|---|
| I1 | `sum(all_phase_ms) ∈ [0.98 × task_wall_ms, 1.02 × task_wall_ms]` | ±2% tolerance |
| I2 | No phase_ms < 0 | reject row |
| I3 | `tool-dispatch = tool-call-N − hook-pretool − hook-posttool − llm-think (if inside)` | identity |
| I4 | `boot-load` appears in at most one task per session (or amortized model, evenly split) | SQL check |
| I5 | Every `tool_use` has a matching `tool_result` within the same task | JSONL pair |
| I6 | Every emitted phase has a non-null `company` field | analytics dep |
| I7 | Phase `ts_start` < `ts_end` strictly | no zero-duration phases except no-op hooks |
| I8 | Session-level sum of tasks' wall-ms == session wall-ms ± 5% | consistency |

Violations emit `partial=true` on the row AND increment `.enforcement/latency-parse-errors.log`.

---

## 6. Data shape (what each LATENCY-LOG.jsonl row looks like)

```json
{
  "id": "<uuid>",
  "ts": "2026-05-01T10:15:32.412Z",
  "session_id": "<session-hash>",
  "task_id": "<derived-from-user-prompt-hash>",
  "company": "sutra|asawa|dayflow|billu",
  "depth": 3,
  "task_type": "governance|research|implementation|…",
  "wall_ms": 184320,
  "phases": {
    "boot_load_ms": 7200,
    "boot_load_amortized_ms": 1800,
    "input_routing_ms": 1200,
    "depth_estimation_ms": 800,
    "tool_calls": [
      {
        "tool": "Read",
        "idx": 0,
        "hook_pretool_ms": 42,
        "tool_dispatch_ms": 18,
        "hook_posttool_ms": 91,
        "total_ms": 151
      },
      {
        "tool": "Agent",
        "idx": 3,
        "subagent_type": "Explore",
        "hook_pretool_ms": 38,
        "tool_dispatch_ms": 240000,
        "hook_posttool_ms": 110,
        "total_ms": 240148
      }
    ],
    "llm_think_ms": 4200,
    "llm_stream_ms": 9800,
    "output_gate_ms": 220,
    "task_stop_ms": 180
  },
  "governance_pct": 0.11,
  "partial": false,
  "source_version": "v1"
}
```

---

## 7. Known ambiguities (finalize in W1)

| # | Ambiguity | Tentative resolution |
|---|---|---|
| A1 | Interrupted tasks (user sends new prompt mid-task) | Emit row with `partial=true`, mark `reason=interrupted` |
| A2 | Tool errors that abort task | Include phases up to error, set `wall_ms` at error ts |
| A3 | Parallel tool calls (multiple in one message) | Each gets own entry in `tool_calls[]`; wall-time counts overlap once |
| A4 | Nested Agent calls (Agent dispatches Agent) | Child session is its own SESSION in LATENCY-LOG; parent's `tool_dispatch_ms` covers round-trip |
| A5 | Compaction events inside a task | Count as `system-overhead` (new bucket); W1 add if measured |
| A6 | Cache hit/miss for boot-load | Emit `cache_hit_bool` — data for Tokens charter correlation |

---

## 8. Open questions for W1 design review

1. Should `boot-load` be further decomposed (claude-md, memory, system-map, etc.) or stay opaque? Tokens charter wants decomposition; Speed charter can piggyback.
2. Is amortized boot-load the right KPI default, or should per-session-first-task be co-primary?
3. For Agent sub-phases (A4), do we persist child session's phase breakdown in parent's LATENCY-LOG row, or cross-reference by child session_id?
4. Does `tool-dispatch` need a further split for Bash (which has observably high variance — spawn vs exec vs wait)?
5. How do we handle subagent dispatch where the subagent writes to its own LATENCY-LOG — dedupe, or accept both with linking field?

These route to W1 design doc (`holding/research/2026-04-21-speed-w1-design.md` when W0 lands and W1 starts).

---

## 9. Codex review (DEFERRED to W1 design)

Per `feedback_codex_everywhere` memory: codex consult on this taxonomy before W1 implementation begins. Specifically ask:
- Are there phases I'm missing that matter for correlation?
- Are the boundary rules unambiguous (testable against transcript samples)?
- Is the invariant set sufficient, or are there aggregation pitfalls?
- Does the taxonomy generalize if tool surface changes (new tool added)?

Codex session ID to be logged in this file's §9 after review lands.

---

## 10. Versioning

v1 (2026-04-20): initial taxonomy, this file.
Amendments require SPEED charter §13 log entry + this file bumped to v2.
