# Sutra — Charters (Strategy Cascade + Cross-Functional Goal Framework)

ENFORCEMENT: SOFT — charters are recommended for all companies. Mandatory at Tier 3.

---

## Strategy Cascade

Every company (including Asawa) needs a clear line from vision to daily tasks.

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

Each level derives from the one above. If a task doesn't connect to a goal, question it. If a goal doesn't connect to the mission, cut it.

### Per-Company Deployment

```
company/
├── VISION.md (or in CLAUDE.md header)
├── os/GOALS.md (quarterly OKRs)
├── os/ROADMAP.md (phases)
└── TODO.md (daily tasks)
```

### Integration with Sutra Engines

- **Estimation Engine**: estimates effort per task → informs roadmap feasibility
- **Adaptive Protocol**: routes depth per task → simpler tasks get less process
- **Enforcement Review**: checks if tasks connect to goals → flags orphan tasks

### Multi-Agent Execution

After HOD sets direction:
1. Each company gets goals assigned
2. Sub-agents can be launched per company to execute roadmap phases
3. Each agent works within boundary hooks (can only touch their company)
4. Progress rolls up to Asawa's portfolio view

---

## What is a Charter

Practices are vertical — they define **who** does the work (Engineering, Product, Design, etc.).

Charters are horizontal — they define **what outcomes** the company is driving across functions.

A charter is a named strategic priority with measurable goals, owned by one practice but contributed to by many. Charters ensure that cross-cutting concerns (speed, quality, growth) don't fall through the cracks between practices.

```
              Charter: Speed          Charter: Quality        Charter: Growth
              ───────────────         ───────────────         ───────────────
Engineering   │ build time   │        │ test coverage │       │ API perf     │
Product       │ spec speed   │        │ spec clarity  │       │ conversion   │
Design        │ design cycle │        │ pixel QA      │       │ onboarding   │
QA            │ test speed   │        │ bug rate      │       │ smoke tests  │
```

---

## Charter Anatomy

Every charter has seven components:

| Component | Type | Description |
|-----------|------|-------------|
| **Name** | String | Short, memorable (e.g., "Speed", "Quality", "Growth") |
| **Objective** | Qualitative | What we're trying to achieve — inspires, doesn't measure |
| **KRAs** | List | Key Result Areas — domains of responsibility within this charter |
| **KPIs** | Metrics | Always-on measurements — tracked continuously, never "done" |
| **OKRs** | Time-bound | Quarterly goals scored 0.0–1.0 (format from ROADMAP-MEETING.md) |
| **DRI** | Practice | One practice owns the charter — accountable for outcomes |
| **Contributors** | Practices[] | Other practices that contribute work toward the charter |

### OKR Format (from ROADMAP-MEETING.md)

```
OBJECTIVE: [Qualitative — what we're trying to achieve]

  KR1: [Measurable outcome] — Score: X.X
  KR2: [Measurable outcome] — Score: X.X
  KR3: [Measurable outcome] — Score: X.X

  Overall: X.X (average)
  Status: ON_TRACK | AT_RISK | OFF_TRACK
```

Scoring: 0.0 = no progress, 0.3 = behind, 0.5 = on pace, 0.7 = target, 1.0 = exceeded.

### Roadmap

Each charter includes an action plan — the concrete work that moves KPIs and OKR scores. Roadmap items are set during the Roadmap Meeting and link back to the charter's OKRs.

---

## Charter vs Practice

Practices and charters form a matrix:

| | Speed Charter | Quality Charter | Growth Charter |
|---|:---:|:---:|:---:|
| **Engineering** | DRI | Contributor | Contributor |
| **Product** | Contributor | Contributor | DRI |
| **Design** | Contributor | Contributor | Contributor |
| **QA** | Contributor | DRI | — |

### How They Connect

- A **practice** contributes to multiple charters
- A **charter** is contributed to by multiple practices
- Practice files (e.g., `practices/engineering.md`) get a `contributes_to` field listing their charters
- The charter defines what each practice's specific contribution looks like

### Practice File Addition

Add to each `practices/*.md`:

```yaml
contributes_to:
  - charter: Speed
    role: DRI
    kpis: [build_time_min, deploy_frequency]
  - charter: Quality
    role: contributor
    kpis: [test_coverage_pct, regression_rate]
```

---

## Accountability Matrix

Every function has exactly one owner. No shared ownership. No "the team owns it."

For each company, the matrix shows WHO (practice/role) owns WHAT (function):

| Function | Owner | Accountability |
|----------|-------|---------------|
| Product direction | Product (or Founder) | What gets built and why |
| Technical architecture | Engineering | How it's built |
| User experience | Design | How it looks and feels |
| Quality | QA (or Engineering) | Does it work correctly |
| Growth | Growth (or Product) | Are users increasing |
| Revenue | Product (or Founder) | Is it making money |
| Security | Security (or Engineering) | Is it safe |
| Process | Sutra OS | Is the system followed |

Rules:
- One owner per function. Not "Engineering and Product co-own quality."
- The owner can delegate work but not accountability.
- If something breaks, exactly one person/role is responsible.
- From EOS: "The Accountability Chart answers 'who owns this?' — if the answer is 'we all do,' nobody does."

---

## Example Charters

These are common across companies. Not all apply to every company — pick based on stage and strategy.

### Speed / Velocity

| Field | Value |
|-------|-------|
| Objective | Ship faster without breaking things |
| KRAs | Build speed, deploy frequency, governance overhead |
| KPIs | Time-to-ship (min/feature), deploy frequency (deploys/week), spec-to-code latency |
| DRI | Engineering |
| Contributors | Product, Design, Operations |

### Quality

| Field | Value |
|-------|-------|
| Objective | Users trust the product because it works |
| KRAs | Bug prevention, test coverage, estimation accuracy |
| KPIs | Bug escape rate, test coverage (%), estimation accuracy (%), regression count |
| DRI | QA |
| Contributors | Engineering, Product, Design |

### Growth / Revenue

| Field | Value |
|-------|-------|
| Objective | More users getting more value |
| KRAs | Acquisition, activation, retention, monetization |
| KPIs | New users/week, onboarding completion (%), D7 retention (%), conversion rate (%) |
| DRI | Product |
| Contributors | Engineering, Design, Growth, Content |

### Security

| Field | Value |
|-------|-------|
| Objective | Zero breaches, zero data leaks |
| KRAs | Vulnerability management, access control, compliance |
| KPIs | Open vulnerabilities, time-to-patch (hours), compliance score (%) |
| DRI | Security |
| Contributors | Engineering, Operations |

### Simplicity

| Field | Value |
|-------|-------|
| Objective | The system stays small enough to understand |
| KRAs | Cognitive load, documentation clarity, protocol efficiency |
| KPIs | Cognitive Load Index (C from SUTRA-KPI.md), file count, avg words/file |
| DRI | Operations |
| Contributors | Engineering, Product |

---

## Charter Lifecycle

| Phase | Trigger | Action |
|-------|---------|--------|
| **Create** | Strategic priority emerges (new market, recurring failure, founder directive) | Define charter anatomy, assign DRI, set initial OKRs |
| **Active** | Charter has open OKRs and active KPIs | Reviewed in Roadmap Meetings, scored quarterly |
| **Retire** | Goal achieved, priority shifted, or charter absorbed into another | Archive with final scores, remove from active review |

Charters are not permanent. They exist as long as the strategic priority exists.

---

## Charter Count by Complexity Tier

Charter count scales with company stage (per CLIENT-ONBOARDING.md Appendix A):

| Tier | Max Charters | Rationale |
|------|-------------|-----------|
| Tier 1 (Personal) | 1–2 (Rocks format) | Solo founder — focus on one thing. Rocks instead of full OKRs. |
| Tier 2 (Product) | 3–5 | External users — need quality, growth, and security alongside speed. |
| Tier 3 (Company) | Unlimited | Full organization — charter count matches strategic surface area. |

More charters = more coordination overhead. Add only when a cross-cutting concern is actively failing.

---

## Tier 1 Simplified: Rocks

Tier 1 companies (1 founder, no external users yet) use Rocks instead of full OKRs. Rocks come from EOS (Entrepreneurial Operating System) — they are 90-day priorities with binary outcomes. No scoring, no KRAs, no KPIs.

```
ROCKS (this quarter):
1. [Rock] — DONE / NOT DONE
2. [Rock] — DONE / NOT DONE
3. [Rock] — DONE / NOT DONE

Max 5 rocks. Binary outcome. No KRAs, no KPIs, no scoring.
Upgrade to full OKRs when company moves to Tier 2.
```

### Why Rocks for Tier 1
- Full charter anatomy (KRAs, KPIs, OKRs, DRI, Contributors) is designed for cross-functional teams. Tier 1 has one person.
- Scoring 0.0–1.0 adds overhead with no audience. Binary done/not-done is honest and fast.
- 3–5 rocks per quarter forces prioritization without bureaucracy.
- When the company graduates to Tier 2 (external users, multiple contributors), rocks upgrade to full charters with the complete anatomy.

---

## Connection to Existing Systems

| System | How Charters Connect |
|--------|---------------------|
| **SUTRA-KPI.md** | V/C/A/U metrics map directly to charter KPIs (V → Speed, C → Simplicity, A → Quality, U → Speed) |
| **ROADMAP-MEETING.md** | The process that reviews charter progress — Phase 1 (OKR Check) scores charter OKRs |
| **practices/** | Contributors to charters — each practice file lists `contributes_to` |
| **CLIENT-ONBOARDING.md** (Appendix A) | Complexity tiers determine how many charters a company should run |
| **Company Charter** (example in this file) | Company constitution (mission/values) — charters operationalize the mission into measurable goals |
| **OKRs.md** | Company-level OKR file — charters provide the structure for organizing OKRs |

---

## Charter Template

Companies use this in their `os/OKRs.md` or equivalent:

```markdown
# Charter: [Name]

**Objective**: [Qualitative — what we're trying to achieve]
**DRI**: [Practice]
**Contributors**: [Practice, Practice, ...]
**Status**: ACTIVE | RETIRED

## KRAs
1. [Result area]
2. [Result area]
3. [Result area]

## KPIs (always-on)
| Metric | Current | Target | Trend |
|--------|---------|--------|-------|
| [name] | [value] | [value] | ↑↓→ |

## OKRs (Q[N] [Year])

OBJECTIVE: [Same as charter objective, or narrowed for the quarter]

  KR1: [Measurable outcome] — Score: X.X
  KR2: [Measurable outcome] — Score: X.X
  KR3: [Measurable outcome] — Score: X.X

  Overall: X.X
  Status: ON_TRACK | AT_RISK | OFF_TRACK

## Roadmap
| # | Action | OKR Link | Owner | Due | Status |
|---|--------|----------|-------|-----|--------|
| 1 | [action] | KR1 | [dept] | [date] | TODO |

## Practice Contributions
| Practice | Role | What They Own |
|------------|------|---------------|
| [dept] | DRI | [specific responsibilities] |
| [dept] | Contributor | [specific responsibilities] |
```

---

## Example: Company Charter (DayFlow)

A company charter is the constitution of a company. It defines mission, vision, values, operating principles, and governance. Charters (above) operationalize the mission into measurable goals.

### Mission
DayFlow exists to give people their time back. We build the personal operating system that understands what you need to do, when you need to do it, and how to help you do it better.

### Vision
DayFlow becomes the cognitive layer between you and your life. Not just a calendar. Not just a to-do list. A personal OS that knows your patterns, adapts to your energy, automates the tedious, surfaces the important, and learns continuously.

### Core Values
1. **User Time Is Sacred** — Every feature must save time or reduce cognitive load. One tap is better than two. Zero taps is better than one.
2. **Ship Fast, Learn Faster** — Speed of iteration is the competitive advantage. Ship small, measure quickly, iterate relentlessly.
3. **Design Is the Product** — Beautiful software is not a luxury. Every pixel matters. The design system is law.
4. **Data Over Opinions** — When there is a disagreement, data wins. Opinions are hypotheses. Data is evidence.
5. **Trust Through Transparency** — Users trust us with their most personal data. Security-first engineering. Never monetize user data.

### Operating Principles
- **Specs before code**: Product spec, design spec, tech spec before implementation.
- **Quality is non-negotiable**: Tests exist. Design QA happens. Regressions are P0.
- **Architecture is deliberate**: Five-layer model. Every change respects the layers.
- **Founder sets direction**: Vision, strategy, taste decisions from the founder. Agents recommend, founder approves for strategic decisions. Agents decide autonomously for tactical decisions.
- **RICE scoring** for prioritization: Reach x Impact x Confidence / Effort.

### Organizational Structure
Nine practices, each led by an AI agent (CPO, CDO, CTO, CDaO, CISO, CQO, CGO, COO, CCO). Founder acts as CEO. All CXOs report to the founder.

### Governance
Charter can be amended by the founder at any time. Agents may propose amendments via decision records. Violating a core value is a P0 issue.
