# Sutra — Parallelization Architecture

**Classification**: Core Infrastructure (Layer 2 — Operating System)  
**Direction**: D33 (Parallelization While Evolving), D22 (Speed of Building), D34 (Technical Rigor)  
**Model**: Bulk Synchronous Parallel (BSP) adapted for LLM agent orchestration  
**Origin**: Session 2026-04-05 — 15 agents, 4 planned waves, parallelization collapsed after wave 1 due to no structural enforcement

---

## 1. Formal Independence Test (Bernstein Conditions)

Two tasks A and B can execute in parallel **if and only if** they satisfy the Bernstein conditions (Bernstein, 1966):

```
Tasks A, B are independent iff:

  write_set(A) ∩ read_set(B)  = ∅     (no read-after-write hazard)
  write_set(B) ∩ read_set(A)  = ∅     (no read-after-write hazard)
  write_set(A) ∩ write_set(B) = ∅     (no write-write conflict)
```

Equivalently, using set union:

```
  write_set(A) ∩ (read_set(B) ∪ write_set(B)) = ∅
  AND
  write_set(B) ∩ (read_set(A) ∪ write_set(A)) = ∅
```

**What constitutes a "set" in agent context:**

| Set | Contents |
|-----|----------|
| `read_set(T)` | Files the agent reads, APIs it queries, config it loads, protocols it references |
| `write_set(T)` | Files the agent creates/modifies, APIs it calls with side effects, state it mutates |

**Shared external state** (database rows, API endpoints, deployment targets) counts as both read and write sets. Two agents deploying to the same Vercel project have overlapping write sets — they are NOT independent.

### Practical Application

Before dispatching agents, enumerate for each task:
1. Which files will it read?
2. Which files will it create or modify?
3. Does it touch shared infrastructure (deploy targets, databases, config files)?

Build the conflict graph. Tasks with no edges between them form an **independent set** — dispatch them as a wave.

---

## 2. Wave Dispatch Model (BSP)

The execution model is **Bulk Synchronous Parallel** (Valiant, 1990) — the same model used in Google's Pregel graph processing framework and Apache Giraph.

```
┌─────────────────────────────────────────────────────────────┐
│  WAVE 1                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Agent A  │  │ Agent B  │  │ Agent C  │  │ Agent D  │   │
│  │ (task 1) │  │ (task 2) │  │ (task 3) │  │ (task 4) │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       └──────────────┴──────────────┴──────────────┘        │
│                    BARRIER SYNC                              │
│          collect results · resolve conflicts                 │
│          update protocol state · plan next wave              │
├─────────────────────────────────────────────────────────────┤
│  WAVE 2                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Agent E  │  │ Agent F  │  │ Agent G  │                  │
│  │ (task 5) │  │ (task 6) │  │ (task 7) │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       └──────────────┴──────────────┘                       │
│                    BARRIER SYNC                              │
├─────────────────────────────────────────────────────────────┤
│  WAVE N ...                                                 │
└─────────────────────────────────────────────────────────────┘
```

### BSP Properties

| Property | Definition | Agent Application |
|----------|-----------|-------------------|
| **Superstep** | One wave of parallel computation | All agents in a wave execute concurrently |
| **Barrier synchronization** | No agent in wave N+1 starts until ALL agents in wave N complete | Results collected, conflicts resolved, state updated before next dispatch |
| **Local computation** | Each processor works on local data only | Each agent works on its independent file/state set |
| **Communication** | Happens only at barriers | Agent results merged into shared state only at sync points |

### Wave Lifecycle

```
1. ENUMERATE    — list all pending tasks
2. CLASSIFY     — compute read_set/write_set for each task
3. PARTITION    — group into independent sets (waves) using Bernstein conditions
4. ESTIMATE     — sum individual task estimates per wave (D23)
5. DISPATCH     — launch all agents in wave simultaneously
6. BARRIER      — wait for all agents to return
7. MERGE        — integrate results into shared state
8. VALIDATE     — check combined output against current protocols (post-merge validation)
9. REPEAT       — go to step 1 with remaining tasks + any new tasks generated
```

---

## 3. Conflict Resolution Protocol

Despite the independence test, conflicts can occur — agents may touch files not predicted in their write sets (emergent dependencies), or shared infrastructure may have hidden coupling.

### Resolution Hierarchy

```
CONFLICT DETECTED
│
├── Changes in DIFFERENT file sections (non-overlapping hunks)
│   └── GIT MERGE — automatic, no human intervention
│       Strategy: git merge with default recursive strategy
│
├── Changes in SAME file section (overlapping hunks)
│   └── LAST-WRITER-WINS with conflict log
│       The agent that completed later overwrites.
│       Conflict logged to PARALLELIZATION-LOG.jsonl:
│       { wave, agents, file, sections, resolution: "lww", timestamp }
│
└── Changes are SEMANTICALLY CONTRADICTORY
    └── ESCALATE TO FOUNDER (D19)
        Present: what each agent did, why they conflict, options.
        Founder decides. Logged with resolution rationale.
```

### Conflict Types (Distributed Systems Taxonomy)

| Conflict | Definition | Example | Resolution |
|----------|-----------|---------|------------|
| **Write-write** | Both agents modify the same file region | Agent A changes button color to blue, Agent B to red | Last-writer-wins or escalate |
| **Read-write** (stale read) | Agent A reads a file that Agent B concurrently modifies | Agent A builds on old protocol, Agent B updates that protocol | Post-merge validation catches this |
| **Phantom read** | Agent A's output depends on a state that Agent B creates | Agent A imports a module that Agent B is supposed to create | Dependency analysis failure — should not be in same wave |

---

## 4. Safe Parallelization During System Evolution

This is the hard problem unique to Asawa: **the system being built on is simultaneously evolving.** Agent A builds a feature while Agent B changes a protocol that Agent A should follow. This is analogous to:

- **Schema migration during live traffic** (database systems)
- **Hot code reloading** (Erlang/OTP)
- **Configuration drift** (distributed infrastructure)

### Solution: Three-Layer Isolation Model

#### Layer 1: Snapshot Isolation (Berenson et al., 1995)

Each agent receives a **consistent snapshot** of the system state at dispatch time.

```
dispatch_time = T₀

Agent A sees: protocols as of T₀, configs as of T₀, file state as of T₀
Agent B sees: protocols as of T₀, configs as of T₀, file state as of T₀

Even if Agent B modifies protocols during execution,
Agent A continues working against the T₀ snapshot.
```

This is the same isolation level used in PostgreSQL's MVCC (Multi-Version Concurrency Control) and Google Spanner's TrueTime-based snapshot reads.

**Implementation**: At wave dispatch, record the git commit hash. Each agent's instructions reference this hash as the canonical protocol state. Agents do NOT pull protocol changes mid-execution.

#### Layer 2: Version Pinning

Agents pin to the **current Sutra version** (from RELEASES.md), not to live HEAD.

```
Agent dispatch includes:
  sutra_version: "v1.3.1"
  protocol_snapshot: "commit abc123"
  directions_snapshot: [D1..D34]
```

If an agent needs to check a protocol, it reads the pinned version. This prevents **configuration drift** — the distributed systems problem where nodes in a cluster gradually diverge because they read config at different times.

#### Layer 3: Post-Merge Validation

After all agents in a wave return and their results are merged:

```
1. DIFF the merged state against current (possibly updated) protocols
2. For each agent's output:
   a. Does it comply with protocols as they exist NOW?
   b. If protocols changed during the wave, flag stale-read violations
3. Stale-read violations get:
   a. Auto-remediated if the fix is mechanical (rename, restructure)
   b. Queued for next wave if the fix requires re-implementation
   c. Escalated if the violation is in a Tier 1 invariant (DEFAULTS-ARCHITECTURE.md)
```

This is the **optimistic concurrency control** pattern — allow parallel execution, detect conflicts at commit time, remediate.

### Decision Matrix

| Situation | Isolation Strategy | Rationale |
|-----------|-------------------|-----------|
| Protocol-changing agent + feature-building agents in same session | Snapshot isolation — feature agents pin to pre-change state | Feature agents should not see half-applied protocol changes |
| Multiple feature agents across different companies | Full parallelism, no isolation needed | Company boundaries enforce file-set independence |
| Infrastructure agent (hooks, configs) + any other agent | SEQUENTIAL — infrastructure first, then parallel features | Infrastructure changes affect all subsequent agents |
| Multiple agents within same company, different features | Bernstein test — parallel if independent file sets | Standard BSP wave dispatch |

---

## 5. Throughput Optimization

### Optimal Wave Size

| Wave Size | Throughput | Overhead | Recommendation |
|-----------|-----------|----------|----------------|
| 1 agent | Baseline (1x) | Zero merge overhead | Only for dependent tasks |
| 2-3 agents | 2-3x speedup | Low merge overhead | **Default for most work** |
| 4-5 agents | 3.5-4.5x speedup | Moderate merge overhead, context switching at barrier | **Maximum for complex work** |
| 6-10 agents | 4-6x speedup | High merge overhead, conflict probability rises quadratically | Use only for fully independent, cross-company work |
| 10+ agents | Diminishing returns | Merge overhead dominates, context window pressure at barrier | **Anti-pattern** unless tasks are trivially independent |

The conflict probability between N agents scales as **O(N²)** — each pair is a potential conflict. At N=5, there are 10 pairs to check. At N=10, there are 45 pairs. At N=15, there are 105 pairs.

### Estimation Integration (D23)

Before dispatching a wave:

```
wave_estimate = {
  total_tokens: sum(agent_estimates.tokens),
  total_cost: sum(agent_estimates.cost),
  total_time: max(agent_estimates.time),     // parallel = max, not sum
  merge_overhead: estimated_merge_time,       // barrier sync cost
  conflict_probability: f(N, file_overlap)    // quadratic in wave size
}
```

Note: wall-clock time for a wave is `max(individual times) + merge_overhead`, NOT `sum(individual times)`. This is the fundamental speedup of parallelism — latency is bounded by the slowest agent, not the sum.

### Wave-Level Accuracy Tracking

After wave completion, log to ESTIMATION-LOG.jsonl:

```json
{
  "type": "wave",
  "wave_id": "w-2026-04-05-001",
  "planned_agents": 5,
  "actual_agents": 5,
  "planned_cost": 2.50,
  "actual_cost": 3.10,
  "planned_time_parallel": "8 min",
  "actual_time_parallel": "12 min",
  "conflicts": 1,
  "conflict_resolution": "git_merge",
  "accuracy": 0.72
}
```

This feeds the recursive estimation engine — over time, wave estimates improve and estimation overhead compresses (D23 LEARN phase).

---

## 6. Anti-Patterns

### 6.1 Sequential Execution of Independent Tasks (Throughput Violation)

**Pattern**: Results from wave 1 arrive. Agent processes task 5 sequentially. Then task 6. Then task 7. Each could have run in parallel.

**Why it happens**: The default agent behavior is sequential — process one thing, then the next. Without structural enforcement (the Parallelization Gate in TASK-LIFECYCLE.md), agents fall into sequential mode after the first wave.

**Root cause from 2026-04-05**: 15 tasks planned across 4 waves. Wave 1 dispatched 5 agents correctly. When results returned, the orchestrating agent processed them one-by-one and built subsequent tasks sequentially — waves 2-4 collapsed into serial execution.

**Fix**: The Parallelization Gate at EXECUTE phase entry is mandatory. At every decision point where 2+ tasks are pending, apply the Bernstein conditions and dispatch independent tasks as a wave.

### 6.2 Over-Parallelization (Resource Exhaustion)

**Pattern**: Dispatching 10+ agents when many share overlapping file sets.

**Why it's bad**: Conflict probability scales O(N²). Merge overhead at the barrier dominates the speedup. Context window at the barrier sync point overflows — the orchestrator cannot hold 10+ agent results simultaneously.

**Fix**: Cap wave size at 5 for intra-company work. Use 6-10 only for cross-company work with guaranteed file-set independence.

### 6.3 Parallelizing Dependent Tasks (Causality Violation)

**Pattern**: Task B depends on Task A's output, but both are dispatched in the same wave.

**Why it's bad**: Task B reads stale state (the pre-A version). Its output is built on assumptions that A has already invalidated. This is a **causal ordering violation** — events that have a happens-before relationship (Lamport, 1978) must execute in that order.

**Fix**: Build the dependency DAG before partitioning into waves. Tasks with edges between them go in different waves, respecting topological order.

### 6.4 Protocol Changes Mid-Wave Without Isolation (Configuration Drift)

**Pattern**: Agent modifying protocols is dispatched alongside agents that should follow those protocols.

**Why it's bad**: Some agents read old protocols, some read new. Combined output is inconsistent — half the work follows v1.3.1 rules, half follows v1.3.2 rules.

**Fix**: Protocol-modifying tasks execute in their own wave, BEFORE feature waves. Or use snapshot isolation (Section 4) to ensure all agents in a wave see the same protocol state.

### 6.5 No Barrier Sync (Fire-and-Forget Parallelism)

**Pattern**: Dispatch agents and immediately start working on other things without waiting for results.

**Why it's bad**: No merge step means no conflict detection, no validation, no estimation feedback. The system loses its learning loop (D23) and its safety properties (D27 principle regression tests).

**Fix**: Every wave MUST hit the barrier sync. BSP without barriers is just chaos with extra steps.

---

## 7. Integration with Existing Sutra Systems

| System | Integration Point |
|--------|------------------|
| **TASK-LIFECYCLE.md** | Parallelization Gate in EXECUTE phase — this document defines the formal model that gate enforces |
| **DEFAULTS-ARCHITECTURE.md** | Tier 1 invariants apply to ALL agents in ALL waves — no parallelization exemption for safety properties |
| **ESTIMATION-ENGINE** (D23) | Wave-level estimation before dispatch; wave-level accuracy tracking after completion |
| **DIRECTION-ENFORCEMENT** (D28) | Post-merge validation checks direction compliance of combined wave output |
| **FOUNDER-DIRECTIONS.md** | D22 (speed) mandates parallelization; D33 (this project); D34 (formal rigor in this document) |

---

## 8. Depth Integration

Parallelization overhead is only justified at sufficient task depth. The Adaptive Protocol Engine (PROTO-000) depth assessment gates whether parallelization applies.

| Depth | Parallelization Behavior |
|-------|--------------------------|
| 1 (Surface) | Sequential. Single-task execution, no wave dispatch. |
| 2 (Considered) | Sequential. Multi-step but linear — parallelization overhead exceeds benefit. |
| 3 (Thorough) | **Check parallelization gate.** If 2+ independent tasks exist, apply Bernstein conditions and dispatch as wave. |
| 4 (Rigorous) | Mandatory gate check. Wave estimation required before dispatch. Full BSP model. |
| 5 (Exhaustive) | Full model: wave estimation, snapshot isolation, post-merge validation, wave-level accuracy tracking. |

**Rule**: At Depth 1-2, skip Section 1-6 entirely — just execute. At Depth 3+, the Parallelization Gate in TASK-LIFECYCLE.md is active.

---

## 9. Enforcement

| Rule | Level | Behavior |
|------|-------|----------|
| Parallelization Gate at EXECUTE entry | **HARD** | Agent MUST check for parallelizable tasks before sequential execution. Sequential execution of 2+ independent tasks is a throughput violation. |
| Bernstein conditions before dispatch | **HARD** | No wave dispatches without read/write set enumeration. |
| Barrier sync between waves | **HARD** | No fire-and-forget. All agent results collected and merged before next wave. |
| Post-merge validation | **HARD** | Combined output validated against current protocol state. Stale-read violations flagged. |
| Wave size cap (5 intra-company) | **SOFT** | Recommended limit. Can exceed with justification (fully independent cross-company work). |
| Wave estimation before dispatch | **SOFT** | Prompted at Level 2+ thoroughness. Required at Level 3+. |

---

*Architecture pattern: Bulk Synchronous Parallel (BSP) with Snapshot Isolation and Optimistic Concurrency Control*  
*Formal basis: Bernstein Conditions (1966), Lamport's Happens-Before (1978), BSP Model (Valiant, 1990), Snapshot Isolation (Berenson et al., 1995)*  
*Distributed systems patterns: MVCC, barrier synchronization, optimistic concurrency control, configuration drift prevention, causal ordering*  
*Applied context: LLM agent orchestration in Claude Code with concurrent system evolution*
