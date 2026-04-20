# Sutra — Q2 2026 Big Rocks

**Period**: Q2 2026 (April - June)
**Sutra Version**: v1.6
**Focus**: Validate through use, not through theory
**Review cadence**: Bi-weekly
**Philosophy**: The system has theoretical coverage but low practical validation. Every piece of complexity must prove it's load-bearing through real tasks. Big rocks first — OKR targets set after baselines exist.

---

## Big Rock 1: Run The Engine On Real Tasks

**Objective**: The Adaptive Protocol Engine v3 scores 20+ real tasks and the triage table has real data
**Due**: May 15, 2026
**Status**: Not started

### What Done Looks Like
- 20+ tasks scored with gear selection (across any company)
- Triage table populated with real correct/overtriage/undertriage counts
- At least one parameter proven unnecessary (doesn't change gear) or one gap found (missing parameter)
- At least one refinement made to the engine based on data

### How It Works
Every task in any session gets this before starting:

```yaml
# Gear Assessment (logged to LEARN.md or checkpoint)
task: "description"
gate_triggered: "none" | "auth-pii" | "precedent" | "low-confidence"
problem_type: Clear | Complicated | Complex | Chaotic
gear_selected: 1-5
rationale: "one line why"
```

After completion:

```yaml
# Triage (appended)
gear_correct: 1-5
triage_class: correct | overtriage | undertriage
reason: "what was missed or wasted"
```

### Triage Table (fills as tasks complete)
| Task Category | Tasks | Correct | Over | Under | Accuracy |
|---------------|-------|---------|------|-------|----------|
| | | | | | |

### Targets (from v3 spec)
| Metric | Target |
|--------|--------|
| Undertriage rate | < 5% |
| Overtriage rate | < 30% |
| Correct rate | > 65% |

### Milestones
| # | Action | Status |
|---|--------|--------|
| 1 | Run gear assessment on next 5 tasks (any company) | Not started |
| 2 | After 5 tasks: first triage review — any patterns? | Not started |
| 3 | Run gear assessment on tasks 6-15 | Not started |
| 4 | After 15 tasks: which parameters changed the gear? which didn't? | Not started |
| 5 | Run tasks 16-20. Apply one refinement from the data. | Not started |
| 6 | Compile triage table. Report accuracy. | Not started |

### What This Unlocks
- Know if the 10 parameters are the right 10
- Know if 5 gears is the right number (maybe 3 is enough)
- Know if gates catch what scoring misses (or are redundant)
- Real numbers for the learning loop
- The engine earns its complexity or gets simplified

---

## Big Rock 2: Close The Estimation Loop

**Objective**: Estimate before, measure after, compare — for 20+ tasks
**Due**: May 31, 2026
**Status**: Not started

### What Done Looks Like
- 20+ tasks have estimate vs actual logged
- Accuracy baseline calculated per dimension (tokens, time, files)
- The engine self-corrects on at least one category ("tasks touching X average Y tokens, not Z as estimated")

### Estimation Format (before each task)
```yaml
# Estimate
task: "description"
estimated_tokens: 12K
estimated_time: 25 min
estimated_files: 4
estimated_confidence: 70%
```

### Actuals Format (after each task)
```yaml
# Actuals
actual_tokens: 18K
actual_time: 40 min
actual_files: 7
accuracy_tokens: 67%
accuracy_time: 63%
accuracy_files: 57%
```

### Calibration Table (fills as tasks complete)
| Task Category | Count | Token Accuracy | Time Accuracy | File Accuracy |
|---------------|-------|---------------|--------------|--------------|
| | | | | |

### Milestones
| # | Action | Status |
|---|--------|--------|
| 1 | Add estimation to the first 5 tasks (alongside Big Rock 1) | Not started |
| 2 | After 5 tasks: first calibration check | Not started |
| 3 | Continue for tasks 6-15 | Not started |
| 4 | After 15: identify highest-variance categories | Not started |
| 5 | Apply one calibration fix. Run tasks 16-20. | Not started |
| 6 | Calculate accuracy baselines. Report. | Not started |

### What This Unlocks
- Know what things actually cost (tokens, time) before committing
- Catch scope creep before it happens ("estimated 4 files, already touching 8")
- Historical calibration data for future tasks
- Connect to gear selection: low confidence estimate = higher gear

---

## Big Rock 3: Simplify Through Contraction

**Objective**: After 20 tasks, cut what was never used
**Due**: June 15, 2026
**Status**: Blocked on Big Rock 1 + 2 (needs usage data)

### What Done Looks Like
- Every L2 file has a usage count from the 20-task run
- Files that were never loaded in 20 tasks are archived or merged
- L2 file count reduced (target: based on data, not arbitrary)
- Every remaining file was loaded at least once

### How It Works
During Big Rock 1 and 2, track which Sutra files were actually read or referenced per task:

```yaml
# File usage (tracked per task)
files_loaded:
  - ADAPTIVE-PROTOCOL.md     # gear selection
  - TASK-LIFECYCLE.md         # pipeline reference
  - PROTOCOLS.md              # protocol check
files_not_needed:
  - PARALLELIZATION-ARCHITECTURE.md
  - DEFAULTS-ARCHITECTURE.md
```

After 20 tasks, compile:

### Usage Table (fills from Big Rock 1+2 data)
| L2 File | Times Loaded | Times Needed | Verdict |
|---------|-------------|-------------|---------|
| ADAPTIVE-PROTOCOL.md | | | |
| OPERATING-MODEL.md | | | |
| ENFORCEMENT.md | | | |
| PROTOCOLS.md | | | |
| TASK-LIFECYCLE.md | | | |
| CLIENT-ONBOARDING.md | | | |
| READABILITY-STANDARD.md | | | |
| PERMISSIONS-TEMPLATE.md | | | |
| DEFAULTS-ARCHITECTURE.md | | | |
| PARALLELIZATION-ARCHITECTURE.md | | | |
| VERSION-UPDATES.md | | | |
| a-company-architecture/ (7 files) | | | |
| b-agent-architecture/ (5 files) | | | |
| c-human-agent-interface/ (1 file) | | | |
| d-engines/ (5 files) | | | |
| templates/ (4 files) | | | |

### Milestones
| # | Action | Status |
|---|--------|--------|
| 1 | Track file usage during Big Rock 1+2 tasks | Not started |
| 2 | After 20 tasks: compile usage table | Not started |
| 3 | Identify files with 0 loads — candidates for archive/merge | Not started |
| 4 | Propose contraction plan (which files to cut/merge) | Not started |
| 5 | Execute contraction. Update SYSTEM-MAP. | Not started |
| 6 | Verify: no capability lost, lower token footprint | Not started |

### What This Unlocks
- Earned simplicity — every file proves its value or gets cut
- Lower session startup cost (fewer files to load)
- Cleaner architecture for new sessions/agents
- The system contracts from real evidence, not theory (D7: Expand Then Contract)

---

## Dependencies Between Big Rocks

```
Big Rock 1 (Engine on real tasks)
  |
  |  runs in parallel with
  |
Big Rock 2 (Estimation loop)
  |
  |  both produce usage data for
  |
  v
Big Rock 3 (Simplify through contraction)
```

Rocks 1 and 2 run in parallel on the same 20 tasks. Rock 3 starts after both have enough data (~15 tasks).

---

## Archive: Previous OKR Charters

The following charters existed before the Q2 focus change. They are preserved as reference and will be re-evaluated after the measurement pass.

<details>
<summary>Previous charters (click to expand)</summary>

### Speed
- Lazy loading, fast-path L1, context budgets, hook audit
- Metrics: V_L2, V_L3, governance overhead, startup time

### Simplicity
- L2 contraction, progressive OS loading, protocol merging, doc compression
- Metrics: C index, L2 file count, avg words/file
- Note: Partially absorbed into Big Rock 3

### Accuracy
- Estimation feedback loop, 30+ calibration points, principle regression tests
- Metrics: A_EWMA, A_mean, A_sigma
- Note: Partially absorbed into Big Rock 2

### Efficiency
- Context budget enforcement, smarter agent dispatch, compression, per-level tracking
- Metrics: U_tokens, U_cost

### Human Readability
- Decision highlighting, output formatting, scannability
- Note: Active as ongoing behavior (D1, readability gate)

### Human-LLM Interaction
- Input routing deployment, 7 interaction types, compliance measurement
- Note: Partially absorbed into Asawa Big Rock 2 (direction enforcement)

### First-Time QA
- Automated self-checks, post-deploy smoke tests, rework tracking

### External Research
- Adaptive Protocol research — DONE (v3)
- Human-AI Interaction research — partially done
- Discipline artifact chains — not started

### Revenue/Viability
- INACTIVE — activates when first company launches
</details>

---

## Active Initiative Charters (cross-cutting, horizontal)

| Charter | DRI | Status | Q | KR summary |
|---|---|---|---|---|
| [Tokens](os/charters/TOKENS.md) | Sutra-OS | ACTIVE | Q2 2026 | Baseline (Apr 26) → cut boot P50 30% → gov overhead <15% → propagate to 3+ companies |

See `os/charters/README.md` for the charter model (definition vs initiative), placement rules, and protocol for adding new charters.

