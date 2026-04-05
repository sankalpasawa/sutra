# Sutra — Strategy Cascade Protocol

Every company (including Asawa) needs a clear line from vision to daily tasks.

## The Cascade

```
VISION (why we exist — changes yearly at most)
  ↓
MISSION (what we do — changes yearly at most)
  ↓
GOALS / OKRs (what we achieve this quarter — changes quarterly)
  ↓
ROADMAP (how we get there — changes monthly)
  ↓
TASKS (what we do today — changes daily)
```

Each level derives from the one above. If a task doesn't connect to a goal, question it.
If a goal doesn't connect to the mission, cut it.

## The Framework

### Vision (one sentence)
What does the world look like if this company succeeds?

### Mission (one sentence)
What does this company DO to make that vision real?

### Goals (3-5 per quarter)
Each goal has:
- **Objective**: what we want to achieve (qualitative)
- **Key Results**: how we measure it (quantitative, 2-3 per objective)
- **Owner**: who is responsible
- **Timeline**: when it's due

### Roadmap (phases/milestones)
Breaks goals into executable chunks:
- Phase 1: [what] — [when] — [which goal it serves]
- Phase 2: ...

### Tasks (TODO.md)
Daily work items. Each should trace back to a roadmap phase → goal → mission → vision.
Tasks without a goal connection go to backlog or get cut.

## Deployment

### For each company:

```
company/
├── VISION.md (or in CLAUDE.md header)
├── os/GOALS.md (quarterly OKRs)
├── os/ROADMAP.md (phases)
└── TODO.md (daily tasks)
```

### For Asawa (the holding company):

```
holding/
├── VISION.md (portfolio vision)
├── os/GOALS.md (quarterly: which companies to launch, Sutra improvements, etc.)
├── PRIORITIES.md (current roadmap)
└── TODO.md (holding-level tasks)
```

## Integration with Sutra Engines

- **Estimation Engine**: estimates effort per task → informs roadmap feasibility
- **Adaptive Protocol**: routes depth per task → simpler tasks get less process
- **Enforcement Review**: checks if tasks connect to goals → flags orphan tasks

## HOD Meeting Connection

The HOD meeting reviews:
1. Are we on track with quarterly goals?
2. Does the roadmap need adjusting?
3. Any tasks that don't connect to goals? (cut or justify)

## Multi-Agent Execution

After HOD sets direction:
1. Each company gets goals assigned
2. Sub-agents can be launched per company to execute roadmap phases
3. Each agent works within boundary hooks (can only touch their company)
4. Progress rolls up to Asawa's portfolio view

```
HOD Meeting → goals set
  ↓
Parallel sub-agents launched:
  Agent 1: Maze features (from Maze roadmap)
  Agent 2: DayFlow features (from DayFlow roadmap)
  Agent 3: Jarvis features (from Jarvis roadmap)
  ↓
Progress reports roll up to Daily Pulse
  ↓
Next HOD reviews progress → adjusts goals → cycle continues
```
