# DayFlow Operating Model — The Source of Truth

> One document. Replaces everything in org/, PROCESSES.md, and the scattered process docs.
> If it is not in this file, it is not how we operate.

**Last updated**: 2026-04-02
**Owner**: Sankalp (founder, sole DRI until org scales)
**Review cadence**: Quarterly, or when a principle is proven wrong

---

## 1. Identity Layer

This layer changes yearly at most. It is loaded into every agent session (Ring 1 context, ~500 tokens).

### 1.1 Mission

Build a cognitive architecture for daily life — a system that thinks with you about your time, not just tracks it.

### 1.2 Vision

DayFlow becomes the default way solo knowledge workers organize their day. Not a calendar. Not a todo list. A thinking partner that understands time, energy, and intention.

### 1.3 Values

| Value | Meaning | Test |
|-------|---------|------|
| **Craft over speed** | Ship less, ship better. One polished feature beats three half-done ones. | Would you show this to a designer you respect? |
| **Simplicity as strength** | Every feature must justify its complexity. The default answer is "no." | Can a new user understand this in 5 seconds? |
| **Taste is non-negotiable** | The founder's aesthetic judgment is the final arbiter for product and design decisions. Data informs but does not override taste. | Does this feel right, not just test right? |
| **Offline-first, always** | The app works without internet. Network is an enhancement, not a dependency. | Does this work in airplane mode? |
| **Schema drives capability** | Expand the data schema, expand what the AI can do. The schema IS the API. | Can the AI reason about this without special code? |

### 1.4 Universal Principles

These are machine-readable. Each has a trigger condition. P0 overrides all others.

```yaml
principles:
  - id: P0
    name: Customer focus first
    rule: "Every output, label, metric, and process exists to serve the customer. If the customer doesn't understand it without explanation, fix it. When customer experience conflicts with system design, customer wins. This supersedes all other principles."
    when_to_apply: "Always. Before presenting any output, naming any concept, designing any process. When choosing between internal consistency and external clarity, choose clarity."
    violation_signal: "Terminology requires a glossary. Output requires a training session. A label was chosen for system reasons, not customer reasons. Jargon that was never explained."
    origin: "Founding Doctrine Principle 0, 2026-04-06. 'Gear' renamed to 'Depth' because customers understand depth without explanation."

  - id: P1
    name: Make work visible and explicit
    rule: "Every task, decision, and dependency must exist in a written artifact. If it is not written down, it does not exist for agents."
    when_to_apply: "Always. Before starting any work, verify the task is captured in a node. Before making a decision, verify the options are written out."
    violation_signal: "An agent says 'I assumed...' or 'I think the intent was...'"

  - id: P2
    name: Constrain to accelerate
    rule: "Limit scope, context, and WIP. One task at a time. Load only relevant context. Say no to most things."
    when_to_apply: "When scoping work, loading context, or deciding what to build next. When an agent's output quality drops (too much context loaded)."
    violation_signal: "Agent produces generic or unfocused output. Multiple tasks in flight simultaneously."

  - id: P3
    name: Feedback loops determine health
    rule: "Every action must produce a measurable signal. The tighter the loop, the faster we learn. Match loop speed to decision reversibility."
    when_to_apply: "When designing a process, writing a spec, or choosing between approaches. When something shipped but we do not know if it worked."
    violation_signal: "A feature ships with no way to measure its impact. A process runs for weeks with no check."

  - id: P4
    name: Separate things that change at different rates
    rule: "Consult the 8 shearing layers (Section 2.3). Things in the same layer can couple. Things in different layers must decouple through contracts."
    when_to_apply: "When adding a dependency, importing from another module, or changing a file that other files depend on."
    violation_signal: "A UI component change requires a data model change. A fast layer depends on a faster layer."

  - id: P5
    name: Start simple, earn complexity
    rule: "Build the simplest thing that works. Add complexity only when the simple version is proven insufficient through real use."
    when_to_apply: "When designing a new feature, process, or system. When tempted to build for hypothetical future needs."
    violation_signal: "Building an abstraction before there are 3 concrete uses. Adding a coordination mechanism before coordination fails."

  - id: P6
    name: Align by intent, not instruction
    rule: "Tell agents WHAT and WHY. Leave HOW open. Provide examples and constraints, not step-by-step scripts."
    when_to_apply: "When writing prompts, specs, or task descriptions. When an agent asks for detailed steps instead of understanding the goal."
    violation_signal: "A prompt has 20 numbered steps. An agent cannot handle a novel situation within the same domain."

  - id: P7
    name: Decisions need an owner
    rule: "Every decision has exactly one DRI. 'The team decided' is not allowed. Name the person."
    when_to_apply: "When a decision is being made. When reviewing a decision log entry. When something goes wrong and we need to understand the chain of responsibility."
    violation_signal: "A decision log entry has no owner. Two agents made conflicting decisions about the same thing."

  - id: P8
    name: Never bypass a running process
    rule: "When a process is in flight (parallel agents, data collection, review pipeline), wait for it to complete. Impatience is not a reason to skip steps. Speed matters at execution time, not at the cost of process integrity. If agents are gathering data, the synthesis waits for all agents — it does not proceed with partial data or substitute its own work."
    when_to_apply: "When parallel agents are running and results are pending. When a review pipeline is in progress. When tempted to skip a step because it's 'taking too long.' When the orchestrator could do the work itself instead of waiting for the delegated agent."
    violation_signal: "An orchestrator writes a report while delegated agents are still running. A synthesis step uses partial data. A process step is skipped with the rationale 'I already know the answer.' An agent duplicates work that was delegated to another agent."
    origin: "Maze onboarding 2026-04-04. HOD meeting agents were running in parallel. Orchestrator got impatient and wrote the report itself, bypassing the agents. Founder corrected: 'Just because you have to wait on something, you cannot bypass those things.'"

  - id: P9
    name: Structure adapts, content is configurable
    rule: "There is always structure — the system always scores, selects a gear, learns. But the structure itself evolves through use. Never hardcode content (parameters, gates, protocols, departments) that varies by company, task type, or context. Content is configured per company. Structure adapts through the learning loop. Hardcoding content into structure makes the system brittle. Freezing structure prevents evolution."
    when_to_apply: "When building any system, engine, or process. When adding a gate, parameter, protocol, or department. When the same logic needs to work across multiple companies. When the structure itself needs to change based on what was learned."
    violation_signal: "A gate says 'auth, payments, PII' instead of reading from a company config. A department list is written inline instead of loaded from company state. A pipeline has fixed steps instead of steps configured by gear. The structure cannot accommodate a new company's needs without rewriting the engine."
    origin: "Adaptive Protocol Engine review 2026-04-06. Gate triggers, parameter lists, department names, and pipeline steps were all hardcoded in the engine doc. Founder corrected: 'Don't hardcode — reusability of the architecture is a core principle.' Then refined: 'Structure is not fixed — it is adaptable. But there is structure.'"
```

### 1.5 The Six Tension Resolution Frameworks

These are genuine trade-offs, not problems to solve. Apply the right side based on the situation.

```yaml
tensions:
  - id: T1
    name: Standardize vs. Remove Controls
    apply_standardize_when: "Work is repetitive, variance is costly (data schemas, deployment pipelines, ID formats, API contracts)"
    apply_remove_controls_when: "Work is creative, conformity is costly (product strategy, design exploration, feature brainstorming)"
    dayflow_example: "Virtual ID format (_YYYY-MM-DD) is standardized. How a screen renders activities is creative."

  - id: T2
    name: Plan Thoroughly vs. Experiment Rapidly
    apply_plan_when: "Cost of failure is high, decision is irreversible (new product, data model change, core architecture)"
    apply_experiment_when: "Cost of failure is low, decision is reversible (UI copy, feature variation, color choice)"
    dayflow_example: "Changing Activity type schema gets a design doc. Changing pill border radius gets a quick test."

  - id: T3
    name: Deep Expertise vs. Cross-Functional Breadth
    apply_depth_when: "Quality is the competitive advantage (design system, data model integrity, AI command layer)"
    apply_breadth_when: "Speed is the competitive advantage (shipping a new screen, fixing a user-reported bug)"
    dayflow_example: "Design system token definitions need deep design expertise. Building QuickAdd screen needs breadth across parser, store, and UI."

  - id: T4
    name: Autonomy vs. Alignment
    resolution: "Bounded autonomy: clear on WHAT and WHY (alignment), free on HOW (autonomy), with explicit boundaries."
    dayflow_example: "Agent is told 'make the task bar feel lighter' (intent) with the constraint 'use glass morphism from theme.ts' (boundary). Agent chooses the specific blur, opacity, and shadow values (autonomy)."

  - id: T5
    name: Document Everything vs. Keep It Lean
    apply_document_when: "The artifact improves agent output when loaded into context. Decisions and their reasoning. Boundary contracts."
    apply_lean_when: "The artifact exists for completeness, not utility. Process docs nobody reads. Exhaustive checklists."
    test: "If I put this in an agent's context window, does the agent's output improve? If I delete this, does anything break?"

  - id: T6
    name: Meritocracy of Ideas vs. Founder Taste
    apply_meritocracy_when: "Technical decisions where data and track records can be evaluated (architecture, performance, library choice)"
    apply_taste_when: "Product and aesthetic decisions where coherence of vision matters (design, UX, brand, product direction)"
    dayflow_example: "Whether to use SQLite or Postgres is meritocratic (benchmark, evaluate). Whether the bg should be cream or white is taste."
```

---

## 2. Operating System Layer

This layer changes monthly to quarterly. Loaded per-role (Ring 2, ~2000 tokens).

### 2.1 The Idea Flow

```
SENSE ────> SHAPE ────> DECIDE ────> SPECIFY ────> EXECUTE ────> LEARN
  │                                                                 │
  └─────────────────── FEEDBACK LOOP ───────────────────────────────┘
```

#### Stage 1: SENSE

**What happens**: Identify signals worth acting on. Three input channels:
- **Pull** (outside-in): User feedback, app store reviews, analytics anomalies, support requests
- **Push** (inside-out): Founder vision, technical capability unlock, competitive insight
- **Pain** (failure-driven): Bugs, production incidents, things that annoy the founder during daily use

**Who does it**: Founder (daily dogfooding), plus an agent scanning analytics if configured.

**Artifact produced**: Signal entry in the pain/ideas log.
```yaml
signal:
  source: pull | push | pain
  date: 2026-04-02
  description: "Tasks without time feel lost — no visual home on the canvas"
  strength: high | medium | low
  related_signals: ["2026-03-28: user asked about untimed tasks", "2026-03-15: watermark confusion"]
```

**Gate to next stage**: Signal appears 3+ times OR founder judges it high-strength.

**Operating intensity**:
- Small change: Signal is a known issue with an obvious fix. Skip to EXECUTE.
- Medium change: Signal points to a feature gap. Proceed to SHAPE.
- Large change: Signal challenges the data model or architecture. Full flow.

**LLM context**: Ring 1 (identity) only. Sensing is mostly a human activity.

---

#### Stage 2: SHAPE

**What happens**: Turn a signal into a concrete proposal. Write a 1-page brief with five components:
1. **Customer intent**: Who benefits and how
2. **Hypothesis**: "We believe [X] will happen because [Y]"
3. **Boundary conditions**: What success looks like (quantitative if possible)
4. **Risks and unknowns**: What could go wrong, what we do not know
5. **Impact map**: Which shearing layers, which bounded contexts, which value stream stages

**Who does it**: Founder writes the draft. An agent stress-tests it adversarially (asks hard questions, finds flaws).

**Artifact produced**: 1-page brief (stored in `org/decisions/briefs/`).
```
BRIEF: Natural Language Quick-Add
DATE: 2026-04-02
OWNER: Sankalp

INTENT: Users can type "Meeting with Bob at 3pm tomorrow" and get a correctly
parsed time block without touching any form fields.

HYPOTHESIS: NL input will increase quick-add usage by 3x because the current
form has 4 fields that feel heavy for a quick thought.

BOUNDARY CONDITIONS:
- Parse accuracy > 90% for English time expressions
- Latency < 500ms (local) or < 2s (API fallback)
- Graceful degradation: if parse fails, drop to manual form

RISKS:
- Ambiguous inputs ("next Friday" — which Friday?)
- Non-English time formats
- Users expect full NLP but we only parse time + title

IMPACT:
- Layer 2 (Business Logic): parseActivity.ts, commandLayer.ts
- Layer 3 (Product Features): QuickAddScreen
- Layer 5 (UI Components): input field, suggestion chips
- Domain: Product, Engineering
- No data model change (Layer 1 safe)
```

**Gate to next stage**: Brief is stress-tested. Risks have mitigations or are explicitly accepted.

**Operating intensity**:
- Small: Brief is 3 sentences. Shape takes 10 minutes.
- Medium: Full 1-page brief. Shape takes 1 session.
- Large: Brief plus technical feasibility spike. Shape takes 2-3 sessions.

**LLM context**: Ring 1 + Ring 2 (role context for the adversarial reviewer). Load ARCHITECTURE.md and PRODUCT-KNOWLEDGE-SYSTEM.md for impact assessment.

---

#### Stage 3: DECIDE

**What happens**: Apply the decision matrix based on two dimensions:

| | High Reversibility | Low Reversibility |
|---|---|---|
| **Data-rich** | Experiment: ship behind flag, measure | Meritocratic debate: design doc, adversarial review |
| **Data-poor** | Informed captain: founder decides fast | Founder taste: intuition + principles |

**Who does it**: Founder is the decision maker for all decisions at current scale.

**Artifact produced**: Decision record.
```yaml
decision:
  id: D-2026-04-02-001
  brief: "Natural Language Quick-Add"
  decision: approved
  method: informed_captain  # data-poor, high reversibility
  reasoning: "NL input is a two-way door. We can ship it and revert if parse quality is bad. Low risk, high potential."
  scope: P1 (core NL parsing), P2 (suggestion chips), P3 (multi-language — deferred)
  owner: Sankalp
  date: 2026-04-02
```

**Gate to next stage**: Decision is recorded. Scope is defined with P1/P2/P3 tiers.

**Operating intensity**: Same for all sizes. The decision itself is fast. The brief quality determines decision quality.

**LLM context**: Ring 1 + brief + any relevant past decisions (search by topic).

---

#### Stage 4: SPECIFY

**What happens**: Turn the approved brief into three parallel specs:

1. **Product spec**: What the user experiences
   - User flow (step by step)
   - Edge cases and error states
   - What it looks like (reference DESIGN.md)

2. **Technical spec**: What the system does
   - Which files change (consult Change Flow Map in PRODUCT-KNOWLEDGE-SYSTEM.md)
   - Data flow (consult Data Flow Map)
   - Boundary contracts crossed
   - New types or schema changes

3. **Verification spec**: How we know it works
   - Acceptance criteria (testable)
   - Sensor checks that must pass
   - Manual QA steps

**Who does it**: Agent drafts all three specs. Founder reviews and confirms alignment (the "backbrief" — Art of Action).

**Artifact produced**: Feature spec appended to `FEATURE-SPECS.md` or standalone spec file for large features.

**Gate to next stage**: Founder confirms the backbrief. "Yes, that is what I meant." Specs are internally consistent (product spec matches technical spec matches verification spec).

**Operating intensity**:
- Small: Product spec is 3 bullets. Tech spec is "change these 2 files." Verification is "check it renders."
- Medium: Full three-part spec, 1-2 pages total.
- Large: Multi-page spec with diagrams, migration plan, rollback strategy.

**LLM context**: Ring 1 + Ring 2 + Ring 3 (brief, decision). Load PRODUCT-KNOWLEDGE-SYSTEM.md (flow maps), DESIGN.md (visual rules), relevant source files.

---

#### Stage 5: EXECUTE

**What happens**: Build it. One file at a time. Layer by layer.

Execution protocol:
1. Read the Change Flow Map for affected files
2. Check boundary contracts for any layer crossings
3. Build the slowest-changing layer first (data model before business logic before UI)
4. Run sensors after each file change
5. Commit per logical unit (one commit per layer crossing)

**Who does it**: Agent executes. Founder reviews output.

**Artifact produced**: Code changes, committed to the repo.

**Gate to next stage**: All sensors pass. Acceptance criteria from verification spec are met. Founder approves the output.

**Operating intensity**:
- Small: 1-3 files changed. One commit. Done in a single session.
- Medium: 5-15 files changed. Multiple commits. Done in 1-3 sessions.
- Large: 15+ files. Feature branch. Done in 3-10 sessions.

**LLM context**: Ring 1 + Ring 3 (task details, spec). Load only the specific files being changed plus their 1-hop dependencies. Do NOT load the entire codebase. One file at a time.

---

#### Stage 6: LEARN

**What happens**: After execution, capture what happened.

Three outputs:
1. **Decision update**: Did the hypothesis hold? Pivot, persevere, or kill.
2. **Process update**: Did something in the process fail? Update the relevant section of this operating model.
3. **Knowledge update**: Archive the decision, reasoning, and outcome for future reference.

**Who does it**: Founder reflects. Agent can assist by analyzing metrics or comparing expected vs. actual.

**Artifact produced**: Updated decision record with outcome. Process changes if needed. New sensors if a new class of bug was discovered.

**Gate to next stage**: Learnings are written down. Feedback loop closes: insights feed back to SENSE.

**LLM context**: Ring 1 + decision record + metrics/analytics if available.

---

### 2.2 Node Types

Three levels. Every piece of work lives at exactly one level.

#### Mission (Level 1 — slow)

**Changes**: Monthly to quarterly
**Contains**: Strategic intent for a product area
**Properties**:
```yaml
mission:
  id: M-001
  title: "Natural, intelligent time management"
  intent: "Users should feel like DayFlow thinks WITH them about their day, not just displays a schedule."
  owner: Sankalp
  status: active | paused | completed | killed
  success_criteria: "Users open the app 5+ times daily by choice, not obligation."
  commitments: [C-001, C-002, C-003]  # children
  created: 2025-01-01
  updated: 2026-04-02
```

**Maps to code**: `ARCHITECTURE.md` (vision), bounded contexts in the product (e.g., "time management," "AI assistance," "goal tracking")

**Current missions**:
- M-001: Natural, intelligent time management (CanvasScreen, activities, recurrence)
- M-002: AI as thinking partner (commandLayer, edge functions, NL parsing)
- M-003: Goal-driven life design (goals feature, progress tracking)

---

#### Commitment (Level 2 — medium)

**Changes**: Weekly to monthly
**Contains**: A scoped piece of work that delivers user value
**Properties**:
```yaml
commitment:
  id: C-007
  title: "Natural language quick-add"
  mission: M-002  # parent
  intent: "Reduce friction of capturing a thought to near-zero."
  owner: Sankalp
  status: active
  scope:
    p1: "Parse time + title from English text"
    p2: "Suggestion chips for ambiguous input"
    p3: "Multi-language support"
  spec: "FEATURE-SPECS.md#quick-add-nl"
  tasks: [T-041, T-042, T-043]  # children
  dependencies: ["parseActivity.ts must handle new input format"]
  created: 2026-03-15
  updated: 2026-04-01
```

**Maps to code**: Feature directories (`src/features/`), spec sections in `FEATURE-SPECS.md`, design sections in `DESIGN.md`

---

#### Task (Level 3 — fast)

**Changes**: Daily to hourly
**Contains**: A single executable unit of work
**Properties**:
```yaml
task:
  id: T-042
  title: "Implement parseActivity time extraction for NL input"
  commitment: C-007  # parent
  intent: "Given a string like 'Meeting at 3pm', extract {title: 'Meeting', start_time: '15:00'}"
  owner: engineering-agent
  status: active | blocked | completed | killed
  files: ["src/lib/parseActivity.ts", "src/lib/__tests__/parseActivity.test.ts"]
  layers: [2]  # Business Logic
  boundary_crossings: []  # none for this task
  acceptance_criteria:
    - "parseActivity('Meeting at 3pm') returns {title: 'Meeting', start_time: '15:00'}"
    - "parseActivity('Lunch') returns {title: 'Lunch', start_time: null}"
    - "All existing parseActivity tests still pass"
  decisions: []
  created: 2026-04-01
  updated: 2026-04-02
```

**Maps to code**: Specific files. Each task touches 1-5 files ideally.

---

#### How They Relate

```
Mission (M-001)
  └── Commitment (C-007)
        ├── Task (T-041): Write parseActivity NL tests
        ├── Task (T-042): Implement parseActivity NL extraction
        └── Task (T-043): Update QuickAddScreen to use NL input
```

Rules:
- Every task belongs to exactly one commitment
- Every commitment belongs to exactly one mission
- Missions are independent (no cross-mission dependencies if possible)
- Cross-commitment dependencies are declared explicitly
- Tasks within a commitment can depend on each other (ordered execution)

---

### 2.3 Impact Model (Three-Dimensional)

When a change is proposed, assess impact across all three dimensions.

#### Dimension 1: Shearing Layers (rate of change)

| Layer | Rate | What Lives Here | DayFlow Files | Change Risk |
|-------|------|-----------------|---------------|-------------|
| 0. Vision | Yearly | Why this exists, cognitive architecture | ARCHITECTURE.md | Existential — changes everything below |
| 1. Data Model | Quarterly | Activity schema, ID conventions, DB tables | types/index.ts, recurrence.ts, migrations | High — cascades to all layers |
| 2. Business Logic | Monthly | Store functions, rendering rules, AI commands | activitiesStore.ts, commandLayer.ts, actionEngine.ts, parseActivity.ts | Medium — affects features and UI |
| 3. Product Features | Weekly | Screens, user flows, navigation | CanvasScreen, ActivityForm, PlayScreen, SearchScreen, QuickAdd | Medium — self-contained if within layer |
| 4. Design System | Biweekly | Theme tokens, component specs, glass morphism | theme.ts, DESIGN.md, FEATURE-SPECS.md | Medium — affects all UI components |
| 5. UI Components | Daily | Component rendering, styles, layout | ActivityCard, BottomTaskBar, DateStrip | Low — localized impact |
| 6. Content | Anytime | Labels, placeholders, error messages, prompts | Inline strings, mindsetGenerator.ts | Low — localized |
| 7. Ops/Config | On deploy | Env vars, API keys, edge functions, flags | .env, supabase/functions/, Supabase dashboard | Variable — depends on what changes |

**The Rule**: You can freely change within your layer. When you cross a layer boundary, consult the Change Flow Map in `PRODUCT-KNOWLEDGE-SYSTEM.md`. Fast layers depend on slow layers (fine). Slow layers depending on fast layers is an architecture bug.

#### Dimension 2: Bounded Contexts (product domains)

| Domain | What It Covers | Key Files | Owner |
|--------|---------------|-----------|-------|
| Product | Features, UX, user flows | FEATURE-SPECS.md, screen components | Sankalp |
| Engineering | Code, infrastructure, performance | src/**, CLAUDE.md | Sankalp |
| Design | Visual system, components, interactions | DESIGN.md, theme.ts, DESIGN-QA-CHECKLIST.md | Sankalp |
| Data | Analytics, metrics | (future: analytics module) | Sankalp |
| Support | Documentation, help content | (future: in-app help) | Sankalp |
| Marketing | Positioning, App Store listing | (future: marketing assets) | Sankalp |
| Legal | Privacy, terms, compliance | (future: legal docs) | Sankalp |
| Growth | Acquisition, retention, activation | (future: growth experiments) | Sankalp |

At current scale, Sankalp owns all domains. As the company grows, each domain gets its own DRI. Cross-domain impacts are assessed using the impact template below.

#### Dimension 3: Value Stream (idea to user)

```
Sense → Shape → Decide → Specify → Execute → Ship → Monitor → Learn
```

Each stage can be affected by a change. A data model change (Layer 1) affects Specify (new specs), Execute (more work), Ship (migration), and Monitor (new things to track).

#### Impact Assessment Template

For any proposed change, fill this out before starting work:

```
CHANGE: [one-line description]

LAYER IMPACT:
  Primary layer:    [0-7]
  Crossed layers:   [list]
  Direction:        upward (DANGEROUS) | downward (normal) | same (safe)

DOMAIN IMPACT:
  Primary domain:   [Product/Engineering/Design/etc.]
  Affected domains: [list with brief note on how]

VALUE STREAM IMPACT:
  Stages affected:  [which stages of the idea flow]
  Downstream:       [what changes after this ships]

RISK LEVEL: low | medium | high | critical
REQUIRES FOUNDER REVIEW: yes | no
```

**Risk escalation rules**:
- Any upward layer crossing → high risk minimum → founder review required
- Layer 0 or Layer 1 change → critical → full brief + design doc required
- Cross-domain impact on 3+ domains → high risk → founder review required
- Same-layer, single-domain change → low risk → agent can proceed autonomously

---

### 2.4 Decision Framework

#### What Agents Decide Autonomously

Agents make decisions without founder input when ALL of these are true:
- The change is within a single shearing layer
- The change affects only one bounded context
- The risk level is "low"
- The change is consistent with existing patterns (past decisions, current code style)
- The change is reversible (can be undone in < 1 hour)

Concrete examples of autonomous agent decisions:
- Fix a bug within a single component
- Refactor code within a single file
- Update content strings
- Add a test for existing functionality
- Apply a design token that already exists in theme.ts

#### What Needs Founder Input

- Any layer boundary crossing
- Any new design token or visual pattern
- Any change to the data model (types/index.ts, DB schema)
- Any new dependency (npm package, API integration)
- Any change to rendering rules (what becomes a pill vs. watermark vs. task)
- Any change that affects the ID system (real IDs, virtual IDs)
- Any change scoped as P2 or P3 (scope expansion beyond approved P1)
- Killing a task or commitment

#### Believability / Confidence Scoring

When an agent makes a recommendation, it provides a confidence score:

```yaml
recommendation:
  action: "Use date-fns instead of moment.js for time parsing"
  confidence: 0.85  # 0.0 to 1.0
  reasoning: "date-fns is tree-shakeable, moment is deprecated, our bundle size matters for mobile"
  evidence: ["moment.js deprecation notice", "date-fns bundle size comparison", "3 existing uses of date-fns in codebase"]
  risk_if_wrong: "low — can swap libraries with adapter pattern"
  alternatives_considered: ["moment.js (deprecated)", "luxon (heavier)", "native Date (too limited)"]
```

Rules:
- Confidence < 0.5 → agent must present alternatives, founder decides
- Confidence 0.5-0.8 → agent recommends, founder can override
- Confidence > 0.8 AND low risk → agent proceeds, logs the decision
- Confidence > 0.8 AND high risk → agent recommends, founder decides (risk trumps confidence)

#### Decision Records

Every non-trivial decision is recorded. Stored alongside the relevant commitment or in `org/decisions/`.

```yaml
decision:
  id: D-YYYY-MM-DD-NNN
  context: "What situation prompted this decision"
  decision: "What was decided"
  alternatives: ["What else was considered"]
  reasoning: "Why this option was chosen"
  owner: "Who made the call"
  confidence: 0.0-1.0
  reversibility: "easy | medium | hard"
  outcome: "Filled in later — did it work?"
  date: YYYY-MM-DD
```

---

### 2.5 Cadences

#### Daily: Automated + Founder Review

**Automated** (runs on every agent session):
- Load Ring 1 context (identity)
- Read TODO.md for current priorities
- Pick the top unchecked task
- Execute using the Idea Flow (Stage 5)
- Run sensors after changes
- Commit with meaningful messages
- Update task status

**Founder review** (end of day, 10 minutes):
- Review agent output for taste alignment
- Check that nothing unexpected was changed
- Reprioritize TODO.md if needed
- Log any pain points from daily use (dogfooding)

#### Weekly: Commitment Review

**Every Monday** (30 minutes):
- Review all active commitments: on track, blocked, or stale?
- Review the week's decision log: any patterns? any bad calls?
- Review pain log: any signal appearing 3+ times?
- Reprioritize commitments for the coming week
- Kill anything that is not progressing and not critical
- Update PLAN.md with current priorities

#### Per-Feature Lifecycle

```
Signal → Brief → Decision → Spec → [Execute → Sensor Check → Commit] × N → Ship → Learn
                                     └──── one session loop ────┘
```

Small feature: 1-2 sessions total, signal-to-shipped
Medium feature: 3-7 sessions, with spec review checkpoint
Large feature: 7-20 sessions, with weekly check-ins on progress

#### On Incident: Emergency Protocol

When something is broken in production:

```
1. STOP: Do not ship new features. WIP limit drops to 0 for features.
2. ASSESS: What is broken? Which shearing layer? Which bounded context?
3. TRACE: Use the Failure Flow Map (PRODUCT-KNOWLEDGE-SYSTEM.md Flow Map C).
         Find the boundary where the failure originates.
4. FIX: Fix at the boundary, not deep inside a layer.
5. VERIFY: Run all sensors. Manually verify the fix on device.
6. LEARN: Write an incident record:
   - What broke
   - Why it broke (root cause, not symptom)
   - What we changed to fix it
   - What sensor should have caught this (add one if none exists)
   - What process change prevents recurrence (if any)
7. RESUME: Return to normal operations.
```

Incident record format:
```yaml
incident:
  id: I-YYYY-MM-DD-NNN
  severity: critical | high | medium
  description: "Virtual IDs were being passed to editActivity, causing silent no-op on DB write"
  root_cause: "CanvasScreen was not resolving virtual ID before calling store"
  layer: 2-3 boundary (Business Logic to Product Features)
  fix: "Added resolveVirtualId() call in CanvasScreen before editActivity call"
  sensor_added: "Sensor 3 (Virtual ID Safety) now checks CanvasScreen callers"
  date: 2026-04-02
```

---

## 3. Execution Layer

Concrete protocols for different types of changes.

### 3.1 For Code Changes

**Before writing any code:**

1. **Identify the layer.** Which shearing layer does each affected file belong to?
2. **Read the Change Flow Map.** In `PRODUCT-KNOWLEDGE-SYSTEM.md`, find the "IF YOU CHANGE" entry for each file. Note all downstream effects.
3. **Check boundary contracts.** If crossing a layer boundary, read the contract in `PRODUCT-KNOWLEDGE-SYSTEM.md` Part 3.
4. **Assess impact.** Fill out the impact assessment template (Section 2.3). If high/critical risk, get founder review.

**While writing code:**

5. **Build layer by layer.** Start with the slowest-changing layer affected. Data model changes first. Then business logic. Then features. Then UI.
6. **One file at a time.** For LLMs: load the target file + its 1-hop dependencies. Make the change. Run sensors. Move to the next file. Do not batch changes across multiple files into one mental context.
7. **Respect ID conventions.** Real IDs: `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx` (hyphens only). Virtual IDs: `realId_YYYY-MM-DD` (underscore + date suffix). Virtual ID resolution happens at the CALLER (screen), never in the store.
8. **Use theme tokens.** No hardcoded hex values. Import from theme.ts. Glass morphism from `colors.glass.*`. Shadows from `shadows.*`.

**After writing code:**

9. **Run all sensors** (Section 3.5).
10. **Commit per logical unit.** One commit per layer crossing. Meaningful commit messages with type prefix.
11. **Verify on device.** For UI changes, check rendering on the actual app (Expo Go), not just web.

**File change checklist by layer:**

| If you change... | Also check... |
|-------------------|--------------|
| `types/index.ts` | activitiesStore.ts, activities.ts (DB), every screen rendering Activity fields, recurrence.ts, seed.ts |
| `activitiesStore.ts` | Every screen calling editActivity, quickToggleComplete (grep for function names) |
| `recurrence.ts` | activitiesStore.ts (loadDay), CanvasScreen (navigateToActivity), every function receiving an activity ID |
| `theme.ts` | DESIGN.md (spec matches?), DESIGN-QA-CHECKLIST.md, every component using the changed token |
| `CanvasScreen` rendering rules | DESIGN.md (rendering rules section), ARCHITECTURE.md, seed.ts (test data coverage) |
| `AppNavigator.tsx` | Every screen's Props interface, deep links |
| `supabase/functions/*` | lib/ai.ts, PlayScreen, SearchScreen, QuickAddScreen, .env, Supabase secrets |

---

### 3.2 For Design Changes

**Protocol:**

1. **Read DESIGN.md** — understand the current visual system (warm minimal, cream bg, forest green primary, glass morphism).
2. **Create mockup or describe visually** — show, do not tell. Sankalp is visual-first. Present 2-3 options, not text descriptions.
3. **Review against the design system:**
   - Does it use existing tokens from theme.ts?
   - Does it follow the typography scale?
   - Does it respect the glass morphism rules (blur, opacity, tint)?
   - Does it match the rendering rules (timed → pill, untimed+recurring → watermark, untimed → task bar)?
4. **Update DESIGN.md** if new patterns are introduced.
5. **Update FEATURE-SPECS.md** with component specs for new or changed components.
6. **Update DESIGN-QA-CHECKLIST.md** with expected values for new visual elements.

**Design decision ownership**: Founder taste is the final arbiter (Tension T6). Agents propose, founder approves. No design change ships without founder sign-off.

---

### 3.3 For Product Changes

**Protocol:**

1. **Write a 1-page brief** (see Stage 2: SHAPE format above).
   - Customer intent: who benefits and how
   - Hypothesis: what we believe will happen
   - Boundary conditions: measurable success criteria
2. **Define P1/P2/P3 scope:**
   - P1: The minimum that delivers the core value. Ship this first.
   - P2: Enhancements that make it delightful. Ship after P1 is validated.
   - P3: Nice-to-haves. Only if P1+P2 succeed and there is time.
3. **Cross-feature task identification:**
   - Which existing features are affected? (Consult the Change Flow Map)
   - Which screens need updates?
   - Is there a data model change? (If yes: high risk, full spec required)
4. **Run through the Idea Flow** (Section 2.1) from SHAPE onward.

---

### 3.4 For Business/Ops/Legal/Growth Changes

**Protocol:**

1. **Impact assessment across all domains:**
   Fill out the full impact assessment template (Section 2.3), paying special attention to:
   - Legal: Does this change affect privacy policy, terms of service, data handling?
   - Growth: Does this change affect onboarding, retention, or conversion?
   - Marketing: Does this change affect App Store listing, screenshots, or messaging?
   - Finance: Does this change affect costs (API usage, infrastructure)?

2. **Which departments need to act:**
   At current scale (solo founder), this is a checklist:
   - [ ] Product: Feature spec updated?
   - [ ] Engineering: Code changes identified?
   - [ ] Design: Visual changes spec'd?
   - [ ] Legal: Privacy/compliance implications reviewed?
   - [ ] Marketing: External messaging needs update?
   - [ ] Support: Help content needs update?
   - [ ] Ops: Infrastructure/deployment changes needed?

3. **Compliance check:**
   - App Store guidelines: Does this change violate any Apple or Google policy?
   - Data privacy: Does this change how user data is collected, stored, or transmitted?
   - Accessibility: Does this change affect screen reader compatibility or minimum tap targets?

---

### 3.5 Sensors (Automated Checks)

Run these before every commit. Any failure blocks the commit until resolved.

#### Sensor 1: Design Token Compliance

**What it checks**: No hardcoded color values in component files.
**When it runs**: Before every commit that touches .tsx files.
**How to run**:
```bash
grep -r "#[0-9A-Fa-f]\{6\}" mobile/src/features/**/*.tsx mobile/src/components/**/*.tsx --include="*.tsx" | grep -v "theme\|Theme\|//"
```
**Pass**: Zero results.
**Failure means**: A component has a hardcoded hex color instead of using a theme token. Fix: replace with the appropriate token from theme.ts.

#### Sensor 2: Theme Values Match Spec

**What it checks**: theme.ts values match DESIGN.md specification.
**When it runs**: Before every commit that touches theme.ts or DESIGN.md.
**How to run**: Read theme.ts and verify:
- `colors.bg` = `#F5F0E8`
- `colors.text` = `#1A1714`
- `colors.primary` = `#2D5A3E`
- `colors.muted` = `#8C857D`
- `colors.categoryTint` = `0.12`
**Pass**: All values match.
**Failure means**: theme.ts and DESIGN.md are out of sync. Fix: determine which is the source of truth (usually DESIGN.md for intent, theme.ts for implementation) and reconcile.

#### Sensor 3: Virtual ID Safety

**What it checks**: Store functions do not manipulate IDs. Callers resolve virtual IDs before passing to the store.
**When it runs**: Before every commit that touches activitiesStore.ts or any screen that calls edit/toggle functions.
**How to run**:
```bash
# Check store does not manipulate IDs
grep -n "split\|replace\|substring" mobile/src/store/activitiesStore.ts | grep -i "id"

# Check callers resolve virtual IDs
grep -n "editActivity\|quickToggleComplete" mobile/src/features/**/*.tsx
```
**Pass**: No ID manipulation in store. Every caller that might receive a virtual ID has a resolution step visible in the grep output.
**Failure means**: The virtual ID → real ID boundary contract is violated. This is the most dangerous failure mode (silent no-op on DB writes). Fix immediately.

#### Sensor 4: Rendering Rule Consistency

**What it checks**: CanvasScreen rendering filters match DESIGN.md rendering rules.
**When it runs**: Before every commit that touches CanvasScreen.tsx, DESIGN.md, or activitiesStore.ts.
**How to run**: Read CanvasScreen.tsx and verify:
- `start_time` + `duration > 0` + type `TIME_BLOCK` → renders as pill on canvas
- `start_time` + `duration 0` + type `TASK` → renders as watermark at time position
- No `start_time` + recurring → renders as watermark distributed across the day
- No `start_time` + not recurring → renders as task in bottom task bar
Cross-check against DESIGN.md rendering rules section.
**Pass**: Code filters match spec.
**Failure means**: What users see does not match what the design spec says they should see. Layer 2→3→4 boundary violation.

#### Sensor 5: Seed Data Safety

**What it checks**: Seed data does not use INSERT OR REPLACE for user-editable data.
**When it runs**: Before every commit that touches seed.ts.
**How to run**:
```bash
grep -n "INSERT OR REPLACE" mobile/src/lib/db/seed.ts
```
**Pass**: INSERT OR REPLACE only for schema/meta, never for activity data.
**Failure means**: Hot-reload will overwrite user edits. This is a data integrity violation.

#### Sensor 6: Type Safety

**What it checks**: TypeScript compiles without errors.
**When it runs**: Before every commit.
**How to run**:
```bash
cd mobile && npx tsc --noEmit
```
**Pass**: Zero errors.
**Failure means**: Type contract is broken. Fix before committing. Do not suppress with `// @ts-ignore`.

---

## 4. Learning Layer

How the system improves itself.

### 4.1 How Incidents Update the System

Every incident produces at least one of:
1. **A new sensor** — if no sensor caught the issue, add one that would have
2. **An updated Change Flow Map entry** — if the dependency was not documented, add it to PRODUCT-KNOWLEDGE-SYSTEM.md
3. **An updated boundary contract** — if the contract was unclear or missing, clarify it
4. **A decision record** — documenting the root cause, fix, and prevention

The incident is not closed until at least one systemic improvement is made. Fixing the symptom without improving detection is not learning.

### 4.2 How Analytics Feed Back Into Ideas

Currently (pre-launch): dogfooding is the primary feedback loop.
Post-launch: analytics → sensing channel → pain/ideas log.

Analytics to track (input metrics only):
- **Actions per session**: Are users doing things, or just looking?
- **Quick-add usage rate**: Is the NL input reducing friction?
- **Recurrence creation rate**: Are users setting up habits?
- **Time-to-first-action**: How fast can a new user capture a thought?
- **Session length**: Are sessions getting shorter (efficient) or longer (engaged)?

Each metric has a hypothesis. If the metric moves in an unexpected direction, that is a signal for the SENSE stage.

### 4.3 How Decision Quality Is Tracked

Decision records include an `outcome` field that is filled in 2-4 weeks after the decision:

```yaml
outcome:
  date: 2026-04-30
  result: "NL parsing adoption at 60% of quick-add usage. Hypothesis confirmed."
  surprise: "Users type emojis in NL input — parser chokes. Not anticipated."
  quality: good | neutral | bad
  would_decide_differently: no
  follow_up: "Add emoji stripping to parseActivity.ts"
```

Quarterly review: look at all decision outcomes. What patterns emerge?
- Decisions where confidence was high but outcome was bad → our models are wrong
- Decisions where confidence was low but outcome was good → we are too cautious
- Decisions that were never evaluated → we are not closing the loop

### 4.4 How This Model Evolves

This operating model is itself subject to the principles it contains:

- **P3 (Feedback loops)**: Review this model quarterly. Is it helping or just adding overhead?
- **P4 (Separate by rate of change)**: The Identity Layer (Section 1) should change yearly. The Operating System Layer (Section 2) quarterly. The Execution Layer (Section 3) monthly.
- **P5 (Start simple, earn complexity)**: If a section of this model is never referenced by agents, delete it. Apply the deletion test.
- **T5 (Document vs. Lean)**: Every section must pass the agent test: "Does loading this into context improve agent output?"

Evolution mechanism:
1. **Pain accumulation**: When the same process failure happens 3+ times, update the relevant section.
2. **Quarterly review**: Re-read this entire model. Delete what is unused. Update what is stale. Add what is missing.
3. **Post-incident**: After every incident, ask "Does the operating model need to change?"

---

## 5. LLM Compatibility

How to structure agent context based on this model.

### 5.1 CLAUDE.md Structure

`CLAUDE.md` is the Ring 1 + Ring 2 context for every agent session. It should contain:

```
1. Setup instructions (how to run the project)
2. Architecture summary (5 lines, not 50)
3. Key concepts (data model, rendering rules, ID format)
4. Important files (the 10 files that matter most)
5. Current priorities (from TODO.md or PLAN.md)
6. Rules that prevent common mistakes (virtual ID resolution, theme token usage, seed safety)
```

What CLAUDE.md should NOT contain:
- Full design specs (those go in DESIGN.md, loaded on demand)
- Full feature specs (those go in FEATURE-SPECS.md, loaded on demand)
- Complete process documentation (that is this document, loaded when needed)
- Historical decisions (those go in org/decisions/, searched when relevant)

### 5.2 Context Loading Per Stage

| Idea Flow Stage | Ring 1 (always) | Ring 2 (per-role) | Ring 3 (per-task) | Ring 4 (on demand) |
|-----------------|-----------------|-------------------|-------------------|--------------------|
| SENSE | Identity (Section 1) | - | - | Analytics, pain log |
| SHAPE | Identity | ARCHITECTURE.md | Signal details | Competitor analysis, past briefs |
| DECIDE | Identity | Decision framework (Section 2.4) | Brief | Past decisions on similar topics |
| SPECIFY | Identity | PRODUCT-KNOWLEDGE-SYSTEM.md | Brief + decision | DESIGN.md, FEATURE-SPECS.md, relevant source files |
| EXECUTE | Identity | CLAUDE.md (setup + rules) | Task details + spec | Specific source files (1-hop only) |
| LEARN | Identity | Decision framework | Decision record + metrics | Past outcomes for pattern matching |

### 5.3 Ring-Based Context Loading

```
┌─────────────────────────────────────────────┐
│ Ring 4: Reference Material (on demand)      │
│   Full specs, design docs, source files     │
│   Load only when actively needed            │
│ ┌─────────────────────────────────────────┐ │
│ │ Ring 3: Task Context (~5000 tokens)     │ │
│ │   Current task, spec, recent decisions  │ │
│ │   Changes per session                   │ │
│ │ ┌─────────────────────────────────────┐ │ │
│ │ │ Ring 2: Role Context (~2000 tokens) │ │ │
│ │ │   Responsibilities, standards       │ │ │
│ │ │   Changes monthly                   │ │ │
│ │ │ ┌─────────────────────────────┐     │ │ │
│ │ │ │ Ring 1: Identity (~500 tok) │     │ │ │
│ │ │ │   Mission, principles       │     │ │ │
│ │ │ │   Changes yearly            │     │ │ │
│ │ │ └─────────────────────────────┘     │ │ │
│ │ └─────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**Loading rules**:
- Always load Ring 1 and Ring 2
- Load Ring 3 based on current task
- Load Ring 4 only when the agent needs to reference a specific file or spec
- Recency bias: load Ring 3 and Ring 4 content LAST so it has the most influence
- 2-3 hops maximum: from the current task, load the parent commitment, the mission, sibling tasks, and direct dependencies. Not the entire graph.

### 5.4 Templates for Common Operations

#### Template: Bug Fix

```
CONTEXT TO LOAD:
- CLAUDE.md (Ring 2)
- The file where the bug manifests
- The Failure Flow Map entry for that failure type (PRODUCT-KNOWLEDGE-SYSTEM.md)
- 1-hop dependency files

PROTOCOL:
1. Reproduce the bug (describe the steps that trigger it)
2. Trace using Failure Flow Map — find the boundary where it breaks
3. Fix AT the boundary, not deep inside a layer
4. Add a test that would have caught this
5. Run sensors
6. Write incident record if severity >= medium
```

#### Template: New UI Component

```
CONTEXT TO LOAD:
- CLAUDE.md (Ring 2)
- DESIGN.md (the relevant section)
- theme.ts (tokens)
- A similar existing component (for pattern matching)

PROTOCOL:
1. Read DESIGN.md for the component spec
2. Create the component using tokens from theme.ts exclusively
3. Run Sensor 1 (Design Token Compliance)
4. Verify rendering on device
5. Update FEATURE-SPECS.md with the component spec
```

#### Template: Data Model Change

```
CONTEXT TO LOAD:
- CLAUDE.md (Ring 2)
- types/index.ts
- PRODUCT-KNOWLEDGE-SYSTEM.md (full Change Flow Map for types/index.ts)
- activitiesStore.ts
- recurrence.ts
- seed.ts

PROTOCOL:
1. Write brief (this is a Layer 1 change — high risk, full flow required)
2. Get founder approval
3. Update types/index.ts first
4. Update DB schema / migrations
5. Update activitiesStore.ts
6. Update recurrence.ts (if virtual instances affected)
7. Update seed.ts
8. Update every screen that renders the changed fields (grep for field names)
9. Run ALL sensors
10. Manually verify on device
```

#### Template: Feature Addition

```
CONTEXT TO LOAD:
- CLAUDE.md (Ring 2)
- FEATURE-SPECS.md (relevant section)
- DESIGN.md (relevant section)
- PRODUCT-KNOWLEDGE-SYSTEM.md (Change Flow Map for affected files)

PROTOCOL:
1. Confirm spec exists and is approved (Stage 4: SPECIFY must be complete)
2. Assess impact (Section 2.3 template)
3. Build layer by layer (slowest first)
4. One file at a time
5. Run sensors after each file
6. Commit per layer crossing
7. Final verification on device
```

---

## 6. What This Replaces

This operating model supersedes all of the following. These documents are now archived — do not reference them for operational guidance.

### Superseded Documents

| Document | Status | What Moved Where |
|----------|--------|-----------------|
| `org/CHARTER.md` | **Archived** | Identity → Section 1 |
| `org/PROCESSES.md` | **Archived** | Cadences → Section 2.5, Execution → Section 3 |
| `org/ROUTING.md` | **Archived** | Decision routing → Section 2.4 |
| `org/STANDUP-PROTOCOL.md` | **Archived** | Daily cadence → Section 2.5 |
| `org/processes/DAILY-STANDUP.md` | **Archived** | Daily cadence → Section 2.5 |
| `org/processes/WEEKLY-PLANNING.md` | **Archived** | Weekly cadence → Section 2.5 |
| `org/processes/DECISION-MAKING.md` | **Archived** | Decision framework → Section 2.4 |
| `org/processes/FEATURE-LIFECYCLE.md` | **Archived** | Idea Flow → Section 2.1 |
| `org/processes/INCIDENT-RESPONSE.md` | **Archived** | Emergency protocol → Section 2.5 |
| `org/departments/*` | **Archived** | Domain model → Section 2.3 Dimension 2 (we use domains, not departments) |
| `org/RESEARCH-SYNTHESIS.md` | **Archived** | Synthesized into Phase 2 → synthesized into this model |
| `org/RESEARCH-PHASE1-SUMMARY.md` | **Archived** | Research input, preserved for reference only |
| `org/PHASE2-SYNTHESIS.md` | **Archived** | Fully instantiated into this model |
| `org/COMPLICATIONS.md` | **Archived** | Tension frameworks → Section 1.5 |
| `org/CROSS-FUNCTIONAL-OPS-RESEARCH.md` | **Archived** | Impact model → Section 2.3 |
| `ORG-ROADMAP.md` | **Archived** | Agent architecture roadmap → subsumed by phased approach (Gall's Law: earn complexity) |

### Documents That Remain Active

| Document | Purpose | Relationship to Operating Model |
|----------|---------|-------------------------------|
| `CLAUDE.md` | Agent session instructions | Ring 2 context. Should conform to Section 5.1 |
| `ARCHITECTURE.md` | Technical vision | Layer 0 (Vision) of the shearing layers |
| `DESIGN.md` | Visual design system | Layer 4 (Design System). Referenced by Section 3.2 |
| `FEATURE-SPECS.md` | Component and feature specs | Ring 4 reference material. Updated per Section 3.2 |
| `DESIGN-QA-CHECKLIST.md` | Design verification values | Sensor support. Referenced by Sensor 2 |
| `PRODUCT-KNOWLEDGE-SYSTEM.md` | Flow maps and boundary contracts | The technical core of Section 2.3 Dimension 1. Remains the definitive source for code-level dependency tracking |
| `TODO.md` / `TODOS.md` | Current task list | Ring 3 context. The active task backlog |
| `PLAN.md` | Current priorities | Ring 2/3 context. Updated weekly |
| `SECURITY-INFRA.md` | Security posture | Ops/Config layer reference |
| `TEST-PLAN.md` / `TESTING-FRAMEWORK.md` | Test strategy | Verification spec support |

### Relationship Between This Model and PRODUCT-KNOWLEDGE-SYSTEM.md

`PRODUCT-KNOWLEDGE-SYSTEM.md` is NOT superseded. It is the technical instantiation of Section 2.3 Dimension 1 (Shearing Layers) applied specifically to code. This operating model provides the strategic and organizational context. PRODUCT-KNOWLEDGE-SYSTEM.md provides the tactical code-level dependency maps.

When they overlap, this operating model is the higher authority (it sets principles and frameworks). PRODUCT-KNOWLEDGE-SYSTEM.md is the implementation detail (it maps specific files and functions).

---

## Appendix A: Quick Reference Card

For agents: load this section as a cheat sheet when context is limited.

```
BEFORE ANY CHANGE:
  1. What layer? (0-7)
  2. Crossing boundaries? → Read Change Flow Map
  3. Risk level? → low/medium/high/critical
  4. Need founder review? → yes if high/critical risk or design/product decision

DURING CHANGE:
  5. Slowest layer first
  6. One file at a time
  7. Theme tokens only (no hardcoded hex)
  8. Virtual IDs resolved at caller, never in store

AFTER CHANGE:
  9. Run sensors (all 6)
  10. Commit per layer crossing
  11. Update task status

RENDERING RULES:
  - start_time + duration > 0 + TIME_BLOCK → pill
  - start_time + duration 0 + TASK → watermark at time
  - no start_time + recurring → watermark distributed
  - no start_time + not recurring → task bar

ID FORMAT:
  - Real: UUID with hyphens
  - Virtual: realId_YYYY-MM-DD (underscore)
  - Resolution: at the screen, before store calls
```

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **DRI** | Directly Responsible Individual. One person who owns a decision or outcome. Never "the team." |
| **Shearing Layer** | A component that changes at a specific rate. Components at different rates must be decoupled. (Stewart Brand) |
| **Bounded Context** | A domain with its own model and language. Changes within a context are safe. Changes crossing contexts need contracts. (DDD) |
| **Virtual ID** | A runtime-only ID for recurring activity instances. Format: `realId_YYYY-MM-DD`. Never written to the database. |
| **Sensor** | An automated check that detects when a dependency or contract is violated. Runs before commits. |
| **Ring** | A layer of context loaded into an agent's context window. Ring 1 (identity) is always loaded. Ring 4 (reference) is loaded on demand. |
| **Brief** | A 1-page proposal with intent, hypothesis, boundary conditions, risks, and impact. The artifact of the SHAPE stage. |
| **Backbrief** | The agent summarizes its understanding of a spec. The founder confirms or corrects. Catches misalignment before execution. (Art of Action) |
| **Pain Log** | A running list of frustrations, bugs, and surprises. Signals that appear 3+ times get promoted to the SHAPE stage. |
| **P1/P2/P3** | Priority tiers for scope. P1: must ship. P2: should ship if P1 works. P3: nice to have. |
| **Two-way door** | A reversible decision. Can be undone cheaply. Ship fast, learn fast. (Jeff Bezos) |
| **One-way door** | An irreversible decision. Requires thorough planning and review. (Jeff Bezos) |

---

*This is the definitive operating model for DayFlow / Asawa Inc.*
*It replaces all documents listed in Section 6.*
*Review quarterly. Delete what is unused. Update what is stale.*
