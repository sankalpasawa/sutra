# Phase 2 Synthesis: Unified Operating Model for an AI-Agent-Driven Company

> 23 sources. 10 books. 5 LLM practice domains. 8 company case studies.
> This document is the bridge between Phase 1 (raw research) and Phase 3 (detailed design).

---

## Table of Contents

1. Where All Sources Agree (Universal Principles)
2. Where Sources Disagree (Tensions and Trade-offs)
3. The Node Types (What Is the Right Abstraction?)
4. How Ideas Form and Flow
5. Cross-Functional Impact (Beyond Files)
6. The LLM-Compatible Operating Model
7. What NOT to Build (Warnings from Research)
8. The Proposed Operating Model (High Level)

---

## 1. Where All Sources Agree (Universal Principles)

After cross-referencing all 23 sources, seven principles emerge that appear across books,
LLM practices, AND company case studies. These are not "nice ideas." They are convergent
discoveries made independently by theorists, practitioners, and engineers working in
completely different domains.

### Universal Principle 1: Make Work Visible and Explicit

**Books**: Phoenix Project (the four types of work — features, infrastructure, changes,
unplanned — must all be visible or unplanned work eats everything). Thinking in Systems
(you cannot manage what you cannot see; stocks and flows must be mapped). The Goal
(bottlenecks are invisible until you track WIP at every station).

**LLM Practices**: Context engineering (every token in the context window biases output;
if the work is not in context, the LLM cannot reason about it). Knowledge graphs (explicit
structural context beats implicit assumptions). Error reduction (TypeScript's strict mode
makes invisible type assumptions visible and checkable).

**Companies**: Amazon (6-page memos force complete thinking into visible form; "if you can't
write it down clearly, you haven't thought it through"). Stripe (writing culture as operating
system; decision archival so future teams understand the why). Toyota (visual management
boards; andon cord makes problems immediately visible to everyone). Bridgewater (radical
transparency; every meeting recorded; all reasoning explicit). Linear (everything is an
issue with a status; no hidden backlogs).

**The convergence**: Whether you are managing a factory floor (Goldratt), a software pipeline
(Kim), a context window (LLM engineering), or a payments company (Stripe), the same
principle holds: invisible work is unmanageable work. The medium of visibility differs
(kanban boards, 6-page memos, context windows, issue trackers), but the principle is
identical.

**For an AI-agent company**: This is doubly important because AI agents have zero persistent
memory between sessions. Everything that is not written down literally does not exist for
the agent. Visibility is not a management preference — it is a physical constraint of the
architecture.

---

### Universal Principle 2: Constrain to Accelerate

**Books**: The Goal (the bottleneck determines throughput; everything subordinates to the
constraint). Art of Action (directed opportunism — tell people WHAT and WHY, leave HOW
open; constraints on intent enable speed of execution). Team Topologies (team boundaries
and interaction modes constrain communication to accelerate flow). DDD (bounded contexts
create clear boundaries that enable independent evolution). How Buildings Learn (shearing
layers — things that change at different rates MUST be separated).

**LLM Practices**: Context engineering (smaller, more precise context produces better output
than massive dumps). Multi-agent coordination (one good agent with structured self-review
beats five unguarded ones; constraints on agent behavior improve quality). Error reduction
(TypeScript strict mode constrains what you can write, catching errors at compile time).

**Companies**: Amazon (two-pizza teams with API boundaries; single-threaded leadership —
one person, one mission). Apple (work on very few things; boundary conditions as non-
negotiable contracts). Stripe (API review board constrains what ships; stakeholder
checkboxes constrain process). Netflix (context not control — but the context IS the
constraint; high talent density constrains who gets in). Toyota (standardized work is the
baseline that enables kaizen; andon cord constrains the line to stop on defect). Linear
(say no to most things; small team by design).

**The convergence**: Every high-performing system — mechanical, biological, computational,
organizational — achieves speed through constraint, not through freedom. The specific
constraints differ (API boundaries, bounded contexts, shearing layers, team types, strict
typing, small context windows), but the mechanism is the same: by limiting what CAN happen,
you accelerate what SHOULD happen.

**For an AI-agent company**: The context window IS the constraint. An LLM with 200k tokens
of unfocused context performs worse than one with 4k tokens of focused context. Every
architectural decision should ask: "Does this help the agent focus, or does this add noise?"

---

### Universal Principle 3: Feedback Loops Determine System Health

**Books**: Thinking in Systems (reinforcing and balancing loops are the fundamental
mechanisms of all system behavior; delays in feedback loops cause oscillation). The Goal
(Drum-Buffer-Rope is a feedback mechanism from constraint back to release). Lean Startup
(Build-Measure-Learn is an explicit feedback loop; the speed of the loop determines the
speed of learning). Phoenix Project (the Three Ways — flow, feedback, continuous learning).
Art of Action (the three gaps — knowledge, alignment, effects — are all feedback failures).

**LLM Practices**: Context engineering (the output of one prompt becomes input to the next;
prompt chains are feedback loops). Multi-agent coordination (Writer + Critic pattern is a
tight feedback loop). Error reduction (type errors are immediate feedback; test failures
are delayed feedback; production errors are very delayed feedback — earlier is better).

**Companies**: Amazon (input metrics as leading indicators; weekly business reviews as
feedback cadence). Apple (Monday executive review — weekly feedback on every product).
Spotify (A/B testing is a formal feedback loop: hypothesis to measurement to decision;
tens of thousands of experiments per year). Toyota (andon cord — immediate feedback;
kaizen — continuous improvement feedback; A3 thinking — structured problem-solving
feedback). Bridgewater (pain + reflection = progress; every mistake is a data point).
Netflix (keeper test is a feedback mechanism for team composition). Linear (dogfooding —
using your own product is the tightest feedback loop).

**The convergence**: The speed and quality of feedback loops determine the rate of
adaptation. Every source agrees: tighter loops are better. Where they differ is in what
constitutes "tight" — Toyota's andon cord is real-time (seconds), Spotify's A/B tests are
days to weeks, Amazon's PR/FAQ feedback cycle is weeks to months. The universal principle
is not "make loops fast" but "make loops appropriate to the decision's reversibility."

**For an AI-agent company**: LLMs enable feedback loops that were previously impossible.
An agent can write code, run tests, see failures, and fix issues in a single session —
a feedback loop measured in seconds. The operating model should exploit this by structuring
work into small, testable increments with immediate validation.

---

### Universal Principle 4: Separate Things That Change at Different Rates

**Books**: How Buildings Learn (shearing layers — site, structure, skin, services, space
plan, stuff — each changes at a different rate; coupling them is architectural debt). DDD
(bounded contexts separate business domains that evolve independently). Team Topologies
(team types and interaction modes separate concerns that evolve at different rates).
Systemantics (complex systems evolve from simple systems; premature coupling kills
evolution).

**LLM Practices**: Context engineering (system prompt, conversation history, and current
task change at different rates and should be structured accordingly). Knowledge graphs
(stable structural context vs. volatile runtime context — 2-3 hops, not the whole repo).
Multi-agent coordination (orchestrator changes rarely, worker agents change frequently;
separating them enables independent evolution).

**Companies**: Amazon (platform services change rarely; product features change constantly;
API boundaries separate them). Apple (hardware platform evolves on yearly cycles; software
on quarterly; apps on weekly — each has its own development cadence). Stripe (core payment
rails change rarely and carefully; API surface changes more frequently; documentation
changes constantly). Spotify (Encore design tokens change slowly; squad implementations
change fast; tokens are the stable layer that enables independent UI evolution).

**The convergence**: This is Brand's shearing layers applied universally. Goldratt implies
it (the constraint changes slowly; work in process changes constantly). Bungay implies it
(strategic intent is slow; tactical action is fast). Every company case study implements
it, even if they don't use Brand's language. The universal form: identify the rate of
change of every component. Group by rate. Couple within groups. Decouple across groups.

**For an AI-agent company**: The operating model itself has shearing layers. Vision changes
yearly. Principles change quarterly. Processes change monthly. Individual tasks change
daily. Context windows change per-session. The system must be structured so that changing a
process does not require rewriting the vision, and updating a task does not require
restructuring a process.

---

### Universal Principle 5: Start Simple, Earn Complexity

**Books**: Systemantics / Gall's Law ("A complex system that works is invariably found to
have evolved from a simple system that worked. The direct corollary: a complex system
designed from scratch never works and cannot be patched up to make it work."). Lean Startup
(MVP — the smallest thing that generates validated learning). Thinking in Systems (the
simplest model that captures the essential dynamics is the best model).

**LLM Practices**: Context engineering (start with minimal context; add only what improves
output). Multi-agent coordination (one agent with self-review beats a complex multi-agent
swarm for most tasks). Knowledge graphs (2-3 hops of structural context beats dumping the
whole repository).

**Companies**: Amazon (start with a PR/FAQ — one page — before building anything). Toyota
(start with the simplest standardized process; improve through kaizen, not through
redesign). Linear (deliberately small team; "say no" to features that add complexity
without proportional value; ship what matters). Netflix (fewer controls, not more; trust
high-density talent to self-organize). Bridgewater (principles started as a simple list and
grew organically over decades).

**The convergence**: This is the single strongest consensus across all 23 sources. Not one
source advocates designing a complex system from scratch. Every source — from Gall's
theoretical warning to Toyota's practical evolution of TPS over 50 years to Linear's
product philosophy — converges on the same insight: start with one thing that works. Then
improve it. Then connect it. Then let complexity emerge.

**For an AI-agent company**: This is especially critical because the temptation to "design
the perfect AI org" is enormous. The research says: don't. Start with one agent doing one
thing well. Add a second agent when the first is working. Add a coordination mechanism when
two agents need to talk. Never build the coordination layer before you have agents that
need to coordinate.

---

### Universal Principle 6: Align by Intent, Not Instruction

**Books**: Art of Action (directed opportunism — brief subordinates with WHAT and WHY,
leave HOW open; the three gaps close when intent flows clearly). The Goal (the goal itself
— throughput — is the aligning intent; HOW to achieve it emerges from constraint analysis).
Lean Startup (the hypothesis is the intent; the experiment design is the HOW left to the
team). Working Backwards (the PR/FAQ captures the customer intent; execution is delegated).

**LLM Practices**: Context engineering (system prompts work best when they convey intent
and constraints, not step-by-step instructions; LLMs are better at figuring out HOW when
they understand WHY). Multi-agent coordination (agents perform better with clear objectives
and guardrails than with detailed scripts).

**Companies**: Amazon (the PR/FAQ is intent; the single-threaded team determines HOW).
Apple (DRI owns the outcome, not the method; boundary conditions define constraints, not
procedures). Netflix (context not control — leaders set context, individuals make
decisions). Toyota (production targets are intent; workers on the line determine the best
way to meet them and improve through kaizen). Bridgewater (principles are intent;
individuals apply them to specific situations). Spotify (aligned autonomy — squads know the
problem to solve, choose how to solve it).

**The convergence**: Bungay's framing is the clearest, but every source arrives at the same
place. Detailed instructions create fragile execution (any deviation requires re-
authorization). Intent-based direction creates adaptive execution (deviations within intent
are innovations, not failures). The mechanism is the same whether you are directing human
teams (Netflix, Apple), factory workers (Toyota), AI agents (LLM practices), or startup
experiments (Lean Startup).

**For an AI-agent company**: This maps directly to how LLMs should be prompted. A system
prompt that says "You are the design agent. Your goal is to ensure visual consistency and
user delight. Here are the design principles..." will outperform one that says "Step 1: check
the color values. Step 2: verify spacing. Step 3: review typography." The agent with intent
can handle novel situations. The agent with instructions cannot.

---

### Universal Principle 7: Decisions Need an Owner, Not a Committee

**Books**: Art of Action (the commander makes the decision and issues the directive; clarity
of command enables distributed execution). Working Backwards (the single-threaded leader
owns the decision end-to-end). The Goal (someone must decide where the constraint is and
subordinate everything to it).

**LLM Practices**: Multi-agent coordination (every task needs one agent responsible for the
output; committee-style multi-agent voting produces mediocre consensus, not quality
decisions). Error reduction (one source of truth for types; when multiple files can
independently define the same thing, they diverge).

**Companies**: Apple (DRI — Directly Responsible Individual — for every decision and
project; this is the defining mechanism of Apple's operating model). Amazon (single-
threaded leader — one person, 100% dedicated, full ownership). Netflix (the "informed
captain" — one person makes the call after gathering input, not consensus). Toyota (the
team leader owns the cell; decisions don't require escalation for routine improvements).
Bridgewater (the "believability-weighted" decision maker — not consensus, but the person
with the most relevant track record). Linear (small team where ownership is clear by
default).

**The convergence**: No source advocates committee decisions for execution. Bridgewater
comes closest with "idea meritocracy," but even there, the system weights individual
credibility, not equal votes. The universal insight: decisions need a name attached, not a
group label. "The team decided" means nobody decided. "Sarah decided, after consulting
John, Mark, and the data" means Sarah owns it.

**For an AI-agent company**: Every task, every document, every decision needs exactly one
owner — whether human or agent. When an agent generates a design, one agent (or human) is
the DRI who approves or rejects it. The DRI model maps perfectly to AI agents because
agents, like individuals, can be held to an explicit standard.

---

### Summary Table: The Seven Universal Principles

| # | Principle | Books | LLM Practices | Companies |
|---|-----------|-------|---------------|-----------|
| 1 | Make work visible and explicit | Phoenix, Systems, Goal | Context eng, Knowledge graphs | Amazon, Stripe, Toyota, Bridgewater |
| 2 | Constrain to accelerate | Goal, Art of Action, Topologies, DDD, Brand | Context eng, Multi-agent, Error reduction | Amazon, Apple, Stripe, Netflix, Toyota, Linear |
| 3 | Feedback loops determine health | Systems, Goal, Lean, Phoenix, Art of Action | Context eng, Multi-agent, Error reduction | Amazon, Apple, Spotify, Toyota, Bridgewater, Linear |
| 4 | Separate by rate of change | Brand, DDD, Topologies, Gall | Context eng, Knowledge graphs, Multi-agent | Amazon, Apple, Stripe, Spotify |
| 5 | Start simple, earn complexity | Gall, Lean, Systems | Context eng, Multi-agent, Knowledge graphs | Amazon, Toyota, Linear, Netflix, Bridgewater |
| 6 | Align by intent, not instruction | Art of Action, Goal, Lean, Working Backwards | Context eng, Multi-agent | Amazon, Apple, Netflix, Toyota, Bridgewater, Spotify |
| 7 | Decisions need an owner | Art of Action, Working Backwards, Goal | Multi-agent, Error reduction | Apple, Amazon, Netflix, Toyota, Bridgewater, Linear |

---

## 2. Where Sources Disagree (Tensions and Trade-offs)

The seven universal principles above are areas of agreement. But the 23 sources also
contain genuine disagreements — not just differences in emphasis, but contradictory
prescriptions. These tensions are not resolvable by picking a winner. They are trade-offs
that must be navigated situationally.

### Tension 1: Standardize Everything vs. Remove All Controls

**Toyota says**: Standardized work is the foundation. Without a standard, there can be no
improvement (kaizen). Every process must be documented, followed, and then improved through
disciplined deviation. The standard is the baseline from which all progress is measured.

**Netflix says**: Context, not control. Hire the best people, set the context, remove the
rules. Vacation policy? None. Expense policy? "Act in Netflix's best interest." Travel
policy? "Travel as if it were your own money." When you hire A-players and give them
context, controls are waste.

**Gall says**: Don't build systems at all. Systems that are designed from scratch don't
work. The best systems are evolved, not designed. Adding more controls to a broken system
makes it worse.

**The resolution**: These are not actually contradictory — they apply to different
conditions.

- **Standardize when**: The work is repetitive and the cost of variance is high (factory
  floor, API contracts, data schemas, deployment pipelines). Toyota standardizes because
  manufacturing variance kills quality.
- **Remove controls when**: The work is creative and the cost of conformity is high
  (product strategy, design exploration, engineering problem-solving). Netflix removes
  controls because creative talent atrophies under bureaucracy.
- **Don't build systems when**: You are starting something new and don't yet understand the
  domain well enough to standardize. Gall warns against premature systematization.

**For an AI-agent company**: The data model should be standardized (Toyota). The agent
prompts should convey intent without rigid instructions (Netflix). The operating model
should start simple and evolve (Gall). Different layers, different approaches.

---

### Tension 2: Plan Thoroughly vs. Experiment Rapidly

**Amazon says**: Write the PR/FAQ. Spend weeks refining it. Get it approved by senior
leadership. Then build. Most PR/FAQs are rejected — and that's the point. Planning saves
execution resources.

**Lean Startup says**: Build the MVP. Ship it to real users. Measure. Learn. Pivot or
persevere. Speed of learning beats quality of planning. Every hour spent planning is an
hour not spent learning from real users.

**Working Backwards says**: Start from the customer press release and work backward to the
minimum needed to deliver that experience. This is planning, but it's planning from the
customer's perspective.

**Spotify says**: Run the experiment. Hypothesis, feature flag, A/B test. Let the data
decide. Tens of thousands of experiments per year.

**Toyota says**: Plan-Do-Check-Act (PDCA). Plan carefully, but quickly. Execute. Measure.
Adjust. The cycle is fast, but planning is never skipped.

**The resolution**: The disagreement is about the COST of the planning cycle, not whether
to plan.

- **Plan thoroughly when**: The cost of failure is high and irreversible (launching a new
  company, changing the data model, rewriting core infrastructure, entering a new market).
  Amazon's PR/FAQ is for big, expensive, hard-to-reverse decisions.
- **Experiment rapidly when**: The cost of failure is low and reversible (UI changes,
  pricing experiments, feature variations, copy testing). Spotify's A/B tests are for
  cheap, reversible decisions.
- **PDCA always**: Toyota's insight is that the cycle itself is universal — the duration
  varies. A PR/FAQ is a 6-week PDCA cycle. An A/B test is a 2-week PDCA cycle. A type
  check is a 2-second PDCA cycle. Match the cycle time to the decision's reversibility.

**For an AI-agent company**: PR/FAQ for new products and major features (high cost of
failure). Experiment for UI, copy, and feature variations (low cost of failure). Type
checking for every code change (near-zero cost of failure detection). The operating model
must support all three cycle times simultaneously.

---

### Tension 3: Deep Expertise vs. Cross-Functional Breadth

**Apple says**: Experts lead experts. The VP of Hardware Engineering must be a hardware
expert. Deep domain knowledge is the currency of credibility. Functional organization
preserves and deepens expertise.

**Amazon says**: Single-threaded teams with all functions embedded. The two-pizza team has
its own engineer, PM, designer, tester. Breadth within the team, depth within the
individual.

**Team Topologies says**: Four team types (stream-aligned, enabling, complicated subsystem,
platform) with three interaction modes (collaboration, X-as-a-service, facilitating). The
team structure should match the system architecture (Conway's Law, applied deliberately).

**Spotify says**: Squads are cross-functional (breadth), but Chapters maintain functional
expertise across squads (depth). In practice, the Chapter structure underperformed — breadth
won over depth.

**The resolution**: This depends on what you are optimizing for.

- **Deep expertise when**: The quality of the work is the primary competitive advantage
  (Apple's hardware design, Toyota's manufacturing precision, Stripe's API design). You
  need experts to produce expert-quality output.
- **Cross-functional breadth when**: Speed of delivery is the primary competitive advantage
  (Amazon's product launches, Spotify's feature experiments). You need all functions
  present to avoid handoff delays.

**For an AI-agent company**: This tension dissolves partially because AI agents can be both
deep and broad — an agent can have deep knowledge of design principles AND understand the
engineering constraints, loaded into the same context window. The key is not organizing
agents by function (a "design agent" and an "engineering agent") but by mission, with
relevant cross-functional context loaded for each mission.

---

### Tension 4: Autonomy vs. Alignment

**Netflix says**: Maximum autonomy. Context not control. Trust people to make good
decisions.

**Bridgewater says**: Maximum transparency. Every decision is recorded, every meeting
transcribed, every person rated on believability. Autonomy within a framework of radical
accountability.

**Spotify says**: Aligned autonomy. But the "alignment" part was never fully implemented,
and the result was fragmentation.

**Amazon says**: Autonomy within API boundaries. Teams can do whatever they want inside
their service. But the interface is a contract.

**Toyota says**: Autonomy within standards. Workers can improve the process (kaizen) but
must follow the current standard until it is officially changed.

**The resolution**: Pure autonomy without alignment produces chaos (Spotify's lesson). Pure
alignment without autonomy produces bureaucracy (the failure mode of every large
corporation). The resolution is **bounded autonomy** — clear on WHAT and WHY (alignment),
free on HOW (autonomy), with explicit boundaries (API contracts, standards, principles).

**For an AI-agent company**: Agents need clear boundaries (what they can and cannot do),
clear intent (what they are trying to achieve), and freedom within those bounds. This is
exactly how well-structured LLM prompts work: system prompt (boundaries + intent) plus
user prompt (specific task) produces better output than either alone.

---

### Tension 5: Document Everything vs. Keep It Lean

**Stripe says**: Write everything down. 20-page design docs. Decision archival. Pre-meeting
memos. The writing IS the thinking.

**Linear says**: Ship, don't document. Small team, high output, minimal process. The
product IS the documentation.

**Gall says**: Documentation about the system is not the system. The map is not the
territory. Excessive documentation creates a false sense of understanding.

**Amazon says**: Write it down, but only what matters. The PR/FAQ is 1 page. The 6-pager
is 6 pages. Brevity forces clarity.

**The resolution**: The disagreement is about what constitutes "everything."

- **Document decisions and their reasoning**: Always. This is Stripe's insight. Future
  you has no context.
- **Document processes minimally**: Only what someone needs to know to execute. Toyota's
  standardized work fits on one page per station.
- **Don't document for documentation's sake**: Gall's warning. A 50-page process document
  that nobody reads is worse than no document because it creates false confidence.
- **Let the artifact speak**: Linear's approach. If the code is clean, the issue tracker is
  current, and the product works, you need less documentation.

**For an AI-agent company**: Document what agents need in context to do their work. Nothing
more. Every document should pass the test: "If I put this in an agent's context window,
will it improve the agent's output?" If not, it's documentation for humans, not for the
operating model.

---

### Tension 6: Meritocracy of Ideas vs. Taste of the Founder

**Bridgewater says**: Idea meritocracy. The best idea wins, regardless of who proposes it.
Believability-weighted decision making. Data and track records trump authority.

**Apple says**: The CEO's taste is the final arbiter. Steve Jobs overruled data, experts,
and consensus when his intuition said otherwise. Tim Cook continues to be the sole
integration point. "Taste" is not democratic.

**Netflix says**: The informed captain. One person makes the call after gathering input. Not
consensus, not the boss — the person closest to the decision with the most context.

**Linear says**: The founder's taste defines the product. Karri Saarinen's design
sensibility is Linear's competitive advantage. You cannot A/B test taste.

**The resolution**: This depends on the type of decision.

- **Meritocracy for technical and analytical decisions**: Where data, expertise, and track
  records can be objectively evaluated (architecture choices, metric definitions,
  experiment interpretation). Bridgewater's approach works here.
- **Founder taste for product and aesthetic decisions**: Where the quality depends on
  coherence of vision, not optimization of parts (product design, brand, user experience).
  Apple and Linear's approach works here.
- **Informed captain for operational decisions**: Where context and speed matter more than
  either data or taste (incident response, customer escalations, release decisions).
  Netflix's approach works here.

**For an AI-agent company**: The founder sets taste (vision, product direction, design
principles). Agents execute within that taste using meritocratic methods (data, testing,
structured analysis). When the two conflict, taste wins for product decisions and data wins
for technical decisions.

---

### Summary: When to Apply Which

| Situation | Apply | Not |
|-----------|-------|-----|
| Repetitive, high-variance-cost work | Toyota (standardize) | Netflix (remove controls) |
| Creative, high-conformity-cost work | Netflix (remove controls) | Toyota (standardize) |
| New, poorly understood domain | Gall (start simple) | Amazon (plan thoroughly) |
| High-cost irreversible decisions | Amazon (PR/FAQ) | Lean Startup (experiment) |
| Low-cost reversible decisions | Lean Startup (experiment) | Amazon (PR/FAQ) |
| Quality is the advantage | Apple (deep expertise) | Amazon (cross-functional) |
| Speed is the advantage | Amazon (cross-functional) | Apple (deep expertise) |
| Technical decisions | Bridgewater (meritocracy) | Apple (taste) |
| Aesthetic decisions | Apple (taste) | Bridgewater (meritocracy) |

---

## 3. The Node Types (What Is the Right Abstraction?)

Different sources use different fundamental units of work. This is not accidental — each
unit reflects the source's worldview about what matters most.

### The Competing Node Types

| Source | Node Type | What It Captures |
|--------|-----------|-----------------|
| Lean Startup | Experiment | Hypothesis + test + metric + learning |
| Bridgewater | Decision | Options + reasoning + owner + outcome |
| Linear | Issue | Problem + status + owner + priority |
| The Goal | Constraint | Bottleneck + subordination rules |
| DDD | Bounded Context | Domain + language + boundary + interface |
| How Buildings Learn | Layer | Rate of change + coupling rules |
| Art of Action | Mission | Intent + boundaries + main effort |
| Amazon | PR/FAQ | Customer need + solution + business case |
| Apple | DRI Assignment | Owner + outcome + boundary conditions |
| Spotify | Feature Flag | Hypothesis + flag + rollout + metric |
| Toyota | Standard | Current best practice + improvement opportunity |
| Netflix | Context Memo | Situation + strategy + guardrails |
| Stripe | Design Doc | Problem + solution + tradeoffs + stakeholder sign-offs |

### Why No Single Node Type Works

Each node type is optimized for a specific phase of work:

- **PR/FAQ** and **Context Memo** are for FORMATION (deciding what to do)
- **Mission** and **DRI Assignment** are for COMMITMENT (deciding who owns it)
- **Design Doc** and **Bounded Context** are for SPECIFICATION (deciding how it works)
- **Issue** and **Feature Flag** are for EXECUTION (tracking the work)
- **Standard** and **Constraint** are for OPERATION (running the system)
- **Experiment** and **Decision** are for LEARNING (capturing what happened)

An AI-agent company needs all of these, but not as separate systems. It needs a UNIFIED
node that can express any of them, with metadata that indicates which phase it belongs to.

### The Proposed Node Hierarchy

After analyzing all 13 node types, the right abstraction is a three-level hierarchy:

```
Level 1: MISSION (slow-changing, intent-level)
  "Make task management delightful for solo knowledge workers"
  Contains: intent, boundaries, success criteria, owner
  Changes: monthly to quarterly
  Maps to: Art of Action mission, Amazon PR/FAQ, Netflix context memo

Level 2: COMMITMENT (medium-changing, scope-level)
  "Build a natural language quick-add feature"
  Contains: scope, DRI, constraints, dependencies, spec
  Changes: weekly to monthly
  Maps to: DRI assignment, design doc, bounded context, standard

Level 3: TASK (fast-changing, execution-level)
  "Implement parseActivity function to extract time from natural language"
  Contains: status, owner, priority, links to commitment
  Changes: daily to hourly
  Maps to: Linear issue, feature flag, experiment, constraint
```

### Why Three Levels

**Two levels is too few**: You lose the distinction between "what we're trying to achieve"
(mission) and "what we're building this week" (task). Every source that has only two levels
(issues and epics, stories and sprints) eventually invents a third (themes, initiatives,
objectives).

**Four levels is too many**: Gall's Law. More levels means more coupling points, more
coordination overhead, more places where information must be kept in sync. The fourth level
(often "vision" or "strategy") changes so rarely that it belongs in a document, not in a
tracking system.

**Three levels match the natural cadences**: Monthly strategy (mission), weekly planning
(commitment), daily execution (task). This also matches Brand's shearing layers — three
distinct rates of change that should be loosely coupled.

### Node Properties

Every node at every level has:

```
id:           Unique identifier
type:         mission | commitment | task
title:        What this is (human-readable, one line)
intent:       WHY this matters (the Bungay directive)
owner:        DRI (one name, never "the team")
status:       active | paused | completed | killed
created:      When it was created
updated:      Last modification timestamp
parent:       Link to parent node (task -> commitment -> mission)
dependencies: What this blocks or is blocked by
context:      What an agent needs to know to work on this
decisions:    Log of decisions made about this node, with reasoning
metrics:      How we measure success (input metrics preferred)
```

### How This Maps to LLM Context

When an agent begins work, it loads:
1. The MISSION (why are we doing this — stable, changes rarely)
2. The COMMITMENT (what specifically are we building — refreshed weekly)
3. The TASK (what am I doing right now — refreshed per session)
4. The DECISIONS log for this task (what has been tried, what worked)

This naturally structures the context window from slow-changing (top) to fast-changing
(bottom), matching both Brand's shearing layers and LLM context engineering best practices.

---

## 4. How Ideas Form and Flow

Every source has a model for how ideas go from spark to shipped product. Synthesizing
across all of them reveals a six-stage flow that every source touches, even if they
emphasize different stages.

### Stage 1: SENSING (Where Do Ideas Come From?)

| Source | Sensing Mechanism |
|--------|-------------------|
| Amazon | Customer obsession: work backwards from what users need |
| Toyota | Gemba: go to the factory floor, observe reality |
| Lean Startup | Customer development interviews, analytics, pain points |
| Netflix | A-player intuition + market observation |
| Spotify | Data analytics + user research + internal experimentation |
| Linear | Dogfooding: use your own product obsessively |
| Bridgewater | Pain: every mistake is a signal. Systematize the collection of pain. |
| Apple | Deep domain expertise: experts sense what's possible before users ask |
| Stripe | User support tickets, API usage patterns, developer feedback |
| LLM research | Pattern recognition across large corpora; anomaly detection |

**The unified sensing model**: Ideas come from three sources:
1. **Pull** (outside-in): Customer feedback, support tickets, analytics, market gaps
2. **Push** (inside-out): Domain expertise, founder vision, technical capability
3. **Pain** (failure-driven): Bugs, complaints, production incidents, competitive losses

All three channels must be active. Companies that only sense pull become reactive (building
what users ask for, not what they need). Companies that only sense push become detached
(building what's technically interesting, not what's valuable). Companies that only sense
pain become firefighters (always fixing, never creating).

### Stage 2: SHAPING (How Do Ideas Become Proposals?)

| Source | Shaping Mechanism |
|--------|-------------------|
| Amazon | PR/FAQ: write the press release from the future |
| Stripe | Kickoff memo: problem, solution, risks, success metrics |
| Bridgewater | Stress testing: encourage disagreement, find flaws early |
| Toyota | A3 thinking: problem, analysis, countermeasures on one page |
| Lean Startup | Hypothesis formulation: "I believe [X] because [Y]" |
| Art of Action | Mission analysis: intent, main effort, boundaries |
| Apple | Design exploration: 10 concepts to 3 to 1 |
| Netflix | Informed captain gathers context, forms a proposal |
| Spotify | Experiment design: hypothesis, metric, success threshold |
| DDD | Context mapping: where does this fit in the domain model? |

**The unified shaping model**: A shaped idea has five components:
1. **Customer intent**: Who benefits and why (Amazon's PR/FAQ)
2. **Hypothesis**: What we believe will happen and why (Lean Startup)
3. **Boundary conditions**: What success looks like quantitatively (Apple's contracts)
4. **Risks and unknowns**: What could go wrong (Stripe's kickoff memo)
5. **Impact map**: What else this touches (DDD's context map, Brand's layer analysis)

The critical insight from Bridgewater: shaping must include ADVERSARIAL input. Amazon's
internal FAQ serves this function (what would legal worry about? what would operations
flag?). Toyota's A3 requires root cause analysis. Bridgewater explicitly encourages
disagreement. Ideas that are only shaped by advocates are ideas that haven't been stress-
tested.

### Stage 3: DECIDING (Who Approves and How?)

| Source | Decision Mechanism |
|--------|-------------------|
| Amazon | Narrative review meeting: silent reading + truth-seeking discussion |
| Apple | Monday executive review: CEO as integration point |
| Bridgewater | Believability-weighted: those with best track records carry more weight |
| Netflix | Informed captain: one person decides after gathering input |
| Toyota | Consensus-building (nemawashi) then rapid execution |
| Linear | Founder decides: taste + speed |
| Lean Startup | The experiment decides: data, not opinion |
| Stripe | Stakeholder checkboxes: all affected parties must review |
| Art of Action | Commander's decision after backbrief from subordinates |

**The unified decision model**: Decisions vary along two dimensions:
- **Reversibility**: Can we undo this cheaply? (Jeff Bezos's "one-way door" vs. "two-way door")
- **Information richness**: Do we have enough data to decide analytically?

| | High Reversibility | Low Reversibility |
|---|---|---|
| **Data-rich** | Experiment (Spotify, Lean Startup) | Meritocratic debate (Bridgewater, Amazon) |
| **Data-poor** | Informed captain (Netflix, Linear) | Founder taste (Apple, Linear) |

The key insight: the decision mechanism should match the decision type. Using Amazon's
6-week PR/FAQ process for a reversible UI change is waste. Using Spotify's quick A/B test
for a fundamental architecture decision is reckless.

### Stage 4: SPECIFYING (How Is the Decision Made Buildable?)

| Source | Specification Mechanism |
|--------|------------------------|
| Amazon | BRD (Business Requirements Document) from approved PR/FAQ |
| Apple | ANPP document: every stage, every owner, every milestone |
| Stripe | 20-page design doc with stakeholder checkboxes |
| DDD | Bounded context specification: domain model, language, interfaces |
| Team Topologies | Team API: what the team provides, how to interact with it |
| Toyota | Standardized work documentation: steps, timing, quality checks |
| Art of Action | Orders: task, intent, main effort, boundaries |

**The unified specification model**: A buildable spec has three parallel tracks:
1. **Product spec**: What the user experiences (Amazon BRD, Apple ANPP)
2. **Technical spec**: What the system does (Stripe design doc, DDD bounded context)
3. **Verification spec**: How we know it works (Toyota quality checks, Stripe API review)

These three specs should be written in parallel, not sequentially, with a negotiation round
between them. The Art of Action's "backbrief" process is key: after receiving orders,
subordinates brief BACK their understanding to the commander. This catches misalignment
before execution begins.

### Stage 5: EXECUTING (How Is the Spec Turned Into Reality?)

| Source | Execution Mechanism |
|--------|---------------------|
| Amazon | Agile sprints with PR/FAQ as North Star |
| Apple | Cross-functional development coordinated by EPM |
| Stripe | Implementation with gradual rollout |
| Toyota | Pull-based production, andon cord for defects |
| Lean Startup | Build the minimum to test the hypothesis |
| Phoenix Project | Flow: reduce WIP, eliminate handoffs, automate |
| Spotify | Build behind feature flag, run A/B test |
| Linear | Ship small increments, dogfood constantly |

**The unified execution model**: Execution has four principles:
1. **Small batches**: Every source agrees. Smaller work items flow faster (The Goal, Phoenix
   Project, Lean Startup, Linear).
2. **Continuous validation**: Check as you go, not at the end (Toyota's andon, TypeScript's
   type checking, Stripe's gradual rollout).
3. **Reversibility by default**: Feature flags (Spotify), gradual rollout (Stripe), canary
   deployments. Make every change reversible.
4. **WIP limits**: Do fewer things at once (The Goal's constraint focus, Apple's "very few
   products," Linear's "say no").

### Stage 6: LEARNING (How Do We Capture What Happened?)

| Source | Learning Mechanism |
|--------|-------------------|
| Lean Startup | Pivot or persevere: did the hypothesis hold? |
| Bridgewater | Pain + reflection = progress; update the principles |
| Toyota | Kaizen: continuous improvement; hansei: reflection |
| Spotify | Experiment results in Confidence platform |
| Amazon | Input metric tracking; iterate the metric itself |
| Stripe | Decision archival with full reasoning |
| Netflix | Keeper test: does this person/project still deserve resources? |
| Art of Action | After-action review: what happened vs. what we expected |
| Systemantics | The system itself teaches you what works if you listen |

**The unified learning model**: Learning has three outputs:
1. **Decision update**: Pivot, persevere, or kill (Lean Startup, Netflix)
2. **Process update**: Improve the standard, update the practice (Toyota, Bridgewater)
3. **Knowledge update**: Archive the decision and reasoning for future reference (Stripe,
   Amazon)

The critical insight from Bridgewater: learning must be SYSTEMATIZED, not left to chance.
Every failure, every surprise, every pain point is a data point. The operating model must
have an explicit mechanism for capturing these and feeding them back into the sensing stage.

### The Complete Idea Flow

```
SENSING ──────> SHAPING ──────> DECIDING ──────> SPECIFYING ──────> EXECUTING ──────> LEARNING
  │                │                │                 │                  │                │
  │ Pull/Push/Pain │ PR/FAQ +       │ Decision        │ Product +        │ Small batches + │ Pivot/
  │ channels       │ Hypothesis +   │ matrix          │ Technical +      │ Validation +    │ Improve/
  │                │ Stress test    │ (reversibility  │ Verification     │ Reversibility + │ Archive
  │                │                │  x data)        │ specs in         │ WIP limits      │
  │                │                │                 │ parallel         │                  │
  └────────────────┴────────────────┴─────────────────┴──────────────────┴──────────────────┘
                                       FEEDBACK LOOP
```

The feedback loop from LEARNING back to SENSING is what makes this a system, not a
pipeline. Without it, you have a waterfall. With it, you have a learning organization.

---

## 5. Cross-Functional Impact (Beyond Files)

Most developer tools model impact within code (file dependencies, import graphs, test
coverage). But a real change — especially in a product company — impacts everything:
marketing, support, legal, data, design, user experience, documentation, and more.

### The Problem: Impact Is Cross-Functional

When you change the data model, the impact is not just:
- Which files need updating (code-level)

It is also:
- Which screens render differently (product-level)
- Which analytics events change shape (data-level)
- Which help docs become inaccurate (support-level)
- Which API contracts break (integration-level)
- Which design specs need revision (design-level)
- Which marketing claims become false (business-level)
- Which compliance certifications need re-evaluation (legal-level)

The existing Product Knowledge System (PRODUCT-KNOWLEDGE-SYSTEM.md) captures the first few
of these through four flow maps (Data, Decision, Failure, Change). But it is scoped to code
and product, not to the full business.

### What the Sources Say About Cross-Functional Impact

**DDD's Bounded Contexts**: Each business domain has its own model, its own language, and
its own boundaries. Impact crosses boundaries through CONTEXT MAPS — explicit mappings
between bounded contexts. Types of relationships:
- **Shared Kernel**: Two contexts share a common model (tightly coupled)
- **Customer-Supplier**: One context consumes another's output (upstream/downstream)
- **Anti-Corruption Layer**: One context translates another's model (loosely coupled)
- **Published Language**: A shared schema that all contexts understand

**Team Topologies' Interaction Modes**: Teams interact in exactly three ways:
- **Collaboration**: Two teams work closely together (high bandwidth, high cost)
- **X-as-a-Service**: One team consumes another's output through a defined interface
- **Facilitating**: One team helps another acquire a new capability

**Brand's Shearing Layers**: Impact propagates DOWNWARD through layers. A slow-layer change
(data model) forces fast-layer changes (UI components). A fast-layer change should NEVER
force a slow-layer change (if it does, the architecture has a coupling bug).

**Amazon's Input Metrics**: Impact is tracked through METRICS, not through dependency
graphs. If you change the checkout flow, you don't trace file dependencies — you watch the
input metrics (conversion rate, cart abandonment, page load time) to see if the change
helped or hurt.

**Toyota's Value Stream**: Impact flows along the VALUE STREAM — the sequence of steps that
transforms raw material into a delivered product. Every step adds value or adds waste.
Impact analysis means asking: "Where in the value stream does this change land, and what
downstream steps are affected?"

### The Unified Impact Model

Combining all five perspectives, impact in an AI-agent company should be modeled across
three dimensions:

**Dimension 1: Layers (Brand / Shearing Layers)**
What rate-of-change layer does this impact?

```
Layer 0: Vision (yearly)        — Does this change why we exist?
Layer 1: Data Model (quarterly) — Does this change what we store?
Layer 2: Business Logic (monthly) — Does this change what we compute?
Layer 3: Product Features (weekly) — Does this change what users can do?
Layer 4: Design System (biweekly) — Does this change how things look?
Layer 5: UI Components (daily)  — Does this change specific screens?
Layer 6: Content (anytime)      — Does this change what we say?
Layer 7: Ops/Config (on deploy) — Does this change how we run?
```

**Dimension 2: Domains (DDD / Bounded Contexts)**
What business domains does this impact?

```
Product     — Features, UX, user flows
Engineering — Code, infrastructure, performance
Design      — Visual system, components, interactions
Data        — Analytics, metrics, reporting
Support     — Documentation, help content, known issues
Marketing   — Positioning, messaging, claims
Legal       — Compliance, privacy, terms
Finance     — Pricing, costs, revenue model
Growth      — Acquisition, retention, activation
```

**Dimension 3: Flow (Toyota / Value Stream)**
Where in the value stream does this land?

```
Sensing     — How we learn about user needs
Shaping     — How we form proposals
Deciding    — How we choose what to build
Specifying  — How we define what to build
Executing   — How we build it
Shipping    — How we deliver it
Monitoring  — How we track its performance
Learning    — How we improve from results
```

### The Impact Matrix

For any change, the assessment is:

```
CHANGE: [description]

LAYER IMPACT:
  Primary layer:    [which layer]
  Crossed layers:   [which boundaries]
  Direction:        [upward (dangerous) or downward (normal)]

DOMAIN IMPACT:
  Primary domain:   [which domain]
  Affected domains: [which other domains, and how]
  Interface type:   [shared kernel / customer-supplier / anti-corruption]

FLOW IMPACT:
  Stage affected:   [which stage of the idea flow]
  Upstream effect:  [does this change what comes before?]
  Downstream effect:[does this change what comes after?]
  Metric impact:    [which input metrics does this affect?]
```

### How This Extends the Product Knowledge System

The existing four flow maps (Data, Decision, Failure, Change) in PRODUCT-KNOWLEDGE-
SYSTEM.md are Dimension 1 applied to code. The unified impact model extends this to:

1. **Domain Flow Maps**: For each business domain, what changes in that domain affect what
   in other domains? (e.g., a pricing change affects marketing claims, support docs, legal
   terms, and analytics dashboards)

2. **Cross-Domain Boundary Contracts**: DDD's context mapping applied to business functions.
   When engineering changes the API, what is the contract with documentation? When design
   changes the component library, what is the contract with marketing's brand guidelines?

3. **Value Stream Metrics**: For each stage of the idea flow, what input metrics indicate
   health? (e.g., sensing: number of user signals captured per week; executing: cycle time
   from spec to shipped; learning: time from shipped to data-informed decision)

---

## 6. The LLM-Compatible Operating Model

The operating model must work not just for humans, but for AI agents that have specific
constraints and capabilities. This section applies context engineering principles to
organizational design.

### LLM Constraints That Shape the Operating Model

**Constraint 1: No persistent memory between sessions.**
An LLM agent starts every session with a blank slate. Everything it knows must be loaded
into context. Implication: every piece of operational knowledge must be written down and
loadable. Tribal knowledge literally does not exist for agents.

**Constraint 2: Context window is finite.**
Even a 1M-token context window has limits. Loading the entire operating model into every
agent session is wasteful and counterproductive (more noise = worse output). Implication:
the operating model must be structured for SELECTIVE loading. Agents should load only what
they need for their current task.

**Constraint 3: LLMs are pattern matchers, not reasoners.**
LLMs find patterns in their training data and context. They do not reason from first
principles (despite appearances). Implication: the operating model should provide PATTERNS
(examples, templates, past decisions) rather than abstract rules. "Here are five past
PR/FAQs" is more useful than "Write a PR/FAQ according to these 10 rules."

**Constraint 4: Recency bias.**
Content later in the context window has more influence on output than content earlier.
Implication: the most important information (current task, immediate constraints, recent
decisions) should be loaded LAST, not first.

**Constraint 5: LLMs are excellent at structured transformation.**
Given clear input format and desired output format, LLMs reliably transform one into the
other. Implication: the operating model should define clear INPUT/OUTPUT formats for every
process. "Given a shaped idea in this format, produce a specification in that format."

**Constraint 6: LLMs struggle with consistency across sessions.**
Without explicit state, an LLM will make different decisions about the same question in
different sessions. Implication: the operating model must externalize state. Every decision,
every standard, every principle must be written down so agents produce consistent behavior.

### Design Principles for an LLM-Compatible Operating Model

**Principle 1: Layered Context Loading**

Structure the operating model as concentric rings of context that are loaded based on task:

```
Ring 1 (Always loaded, ~500 tokens): Identity
  Company purpose, core principles, current priorities

Ring 2 (Loaded per role, ~2000 tokens): Role Context
  Agent's specific role, responsibilities, decision authority,
  relevant standards and patterns

Ring 3 (Loaded per task, ~5000 tokens): Task Context
  Current mission, commitment, task details, relevant decisions,
  dependency information, recent changes

Ring 4 (Loaded on demand, variable): Reference Material
  Full specs, design docs, code files, past examples
  Only loaded when the agent needs to reference them
```

This mirrors Brand's shearing layers: Ring 1 changes yearly, Ring 2 changes monthly, Ring 3
changes daily, Ring 4 changes per-query.

**Principle 2: Structured Artifacts Over Prose**

Every operational artifact should have a consistent structure that agents can parse:

```yaml
# Bad (prose that's hard to extract structure from):
"We decided to use Zustand for state management because it's simpler than Redux
and works well with our React Native setup. We considered MobX but it was too magical."

# Good (structured, parseable, context-efficient):
decision:
  what: State management library
  chose: Zustand
  why: Simpler API, React Native compatible, minimal boilerplate
  rejected: [MobX (too implicit), Redux (too verbose)]
  date: 2025-01-15
  owner: Sankalp
  reversibility: medium (migration effort ~2 days)
```

**Principle 3: Decision Logs as First-Class Artifacts**

For LLMs, decision logs are the most valuable operational artifact. They provide:
- **Consistency**: The agent can check if a similar decision was already made
- **Patterns**: The agent can learn the decision-making style from examples
- **Context**: The agent understands WHY things are the way they are, not just WHAT

Decision logs should be:
- Indexed by topic (design decisions, architecture decisions, process decisions)
- Searchable by keyword
- Structured consistently (decision, alternatives, reasoning, outcome)

**Principle 4: Templates Over Rules**

Instead of abstract rules ("Write clear commit messages"), provide templates:

```
COMMIT MESSAGE TEMPLATE:
  [type]: [what changed]

  Why: [why this change was needed]
  Impact: [what other parts of the system are affected]

  Types: feat, fix, refactor, docs, test, chore

  EXAMPLE:
  feat: Add natural language parsing to quick-add

  Why: Users asked for the ability to type "Meeting with Bob at 3pm tomorrow"
  and have it automatically parsed into a time block.
  Impact: parseActivity.ts (new), commandLayer.ts (updated), QuickAddScreen (updated)
```

Templates are more LLM-compatible than rules because they are concrete patterns that can be
matched and extended, rather than abstract principles that must be interpreted.

**Principle 5: Explicit State Machines for Processes**

Processes should be expressed as state machines, not as prose descriptions:

```
PR/FAQ PROCESS:
  DRAFT -> REVIEW -> REVISE -> APPROVE | KILL

  DRAFT:
    owner: proposer
    output: 1-page PR/FAQ document
    exit criteria: all five sections completed

  REVIEW:
    owner: designated reviewer(s)
    input: completed PR/FAQ
    output: annotated PR/FAQ with questions and concerns
    exit criteria: all reviewers have commented

  REVISE:
    owner: proposer
    input: annotated PR/FAQ
    output: revised PR/FAQ addressing all concerns
    exit criteria: all concerns addressed or explicitly deferred

  APPROVE:
    owner: decision maker (founder)
    input: revised PR/FAQ
    output: approved PR/FAQ + assigned DRI + resource allocation

  KILL:
    owner: decision maker
    input: reviewed PR/FAQ
    output: kill decision with reasoning archived
```

State machines are maximally LLM-compatible because the agent always knows: what state am
I in, what are my valid next actions, what is required to transition.

**Principle 6: 2-3 Hops, Not the Whole Graph**

From knowledge graph research: focused structural context (2-3 hops from the current node)
outperforms loading the entire dependency graph. Applied to the operating model:

When an agent works on a task, it needs:
- The task itself (0 hops)
- The commitment this task belongs to (1 hop up)
- The mission the commitment serves (2 hops up)
- Sibling tasks that might conflict (1 hop lateral)
- Downstream tasks that depend on this one (1 hop down)

It does NOT need:
- All tasks across all missions
- The complete history of all decisions
- Every standard and every process

Loading less produces better output. This is counterintuitive but consistently demonstrated
in LLM research.

### The LLM-Compatible Document Structure

Based on these principles, every document in the operating model should follow this
structure:

```markdown
# [Title]

## Context (what an agent needs to know to use this document)
[2-3 sentences of essential context]

## Current State
[What is true RIGHT NOW — not history, not aspirations]

## Rules (structured, not prose)
- Rule 1: [concrete, testable]
- Rule 2: [concrete, testable]

## Templates (show, don't tell)
[Concrete examples of expected artifacts]

## Decisions (what has been decided and why)
[Structured decision log entries]

## Links (2-3 hops only)
- Parent: [link to parent document]
- Dependencies: [links to directly related documents]
- DO NOT link to everything tangentially related
```

---

## 7. What NOT to Build (Warnings from Research)

The 23 sources contain as many warnings as prescriptions. Several sources exist primarily
to warn against common failure modes. This section catalogs what the operating model should
explicitly NOT include.

### Warning 1: Do Not Design a Complex System from Scratch

**Source**: Gall's Law (Systemantics)

> "A complex system that works is invariably found to have evolved from a simple system
> that worked. A complex system designed from scratch never works and cannot be patched up
> to make it work. You have to start over with a working simple system."

**Applied**: Do not design a 12-department AI org structure on paper and then try to
implement it. Start with one agent doing one thing. When it works, add a second. When two
agents need to coordinate, add the simplest possible coordination mechanism. Let the
org structure emerge from working practice, not from theory.

**What this means concretely**:
- Do not build an orchestration layer before you have agents that need orchestrating
- Do not define interaction modes before you have teams that need to interact
- Do not create decision frameworks before you have decisions that need making
- Do not write process documents before you have processes that need documenting

---

### Warning 2: Do Not Add Process to Fix People Problems

**Source**: Netflix (context not control), Bridgewater (principles, not rules)

When something goes wrong, the instinct is to add a process to prevent recurrence. Netflix
and Bridgewater both warn: if the problem is that the wrong person is in the role, no
amount of process will fix it.

**Applied**: If an AI agent consistently produces poor output, the fix is not "add a review
step." The fix is: improve the agent's context, improve the agent's prompt, or change the
model. Process is a bandage on a capability problem.

**The test**: Before adding any process, ask: "Would this be necessary if the agent/person
were excellent at their job?" If the answer is no, fix the capability, not the process.

---

### Warning 3: Do Not Copy Vocabulary Without Copying Culture

**Source**: Spotify (the model was aspirational, not real; companies copied the labels
without the practices)

Renaming agents to "squads" does not create autonomous, cross-functional teams. Calling a
document a "PR/FAQ" does not create Amazon's culture of truth-seeking review. Labels are
the cheapest part of any operating model. The expensive parts are the behaviors, the
habits, the norms.

**Applied**: When adopting a practice from the research, implement the BEHAVIOR, not the
LABEL. Don't create a "Braintrust" — create a practice of adversarial review where the
reviewer has no authority over the creator. Don't create "single-threaded teams" — create
a practice where one entity owns one thing end-to-end.

---

### Warning 4: Do Not Optimize for Documentation Completeness

**Source**: Gall (the map is not the territory), Linear (ship, don't document)

A perfectly documented system that doesn't work is worse than a working system with no
documentation. Documentation creates the ILLUSION of understanding. The operating model
should be as small as possible while still being useful.

**Applied**: Every document in the operating model must pass two tests:
1. **The agent test**: "Does putting this in an agent's context improve the agent's output?"
2. **The deletion test**: "If I deleted this, would anything break?"

If a document fails both tests, delete it.

---

### Warning 5: Do Not Build Coordination Mechanisms Before You Need Them

**Source**: Gall (start simple), Team Topologies (team interaction modes should evolve),
The Goal (don't optimize non-constraints)

Pre-building coordination mechanisms (approval workflows, review boards, synchronization
rituals) for interactions that don't yet exist is pure waste. Worse, these mechanisms
create work that makes people feel productive without producing value.

**Applied**:
- No standup meetings until there are multiple agents that need to sync
- No approval workflows until there are decisions that need approval gates
- No review boards until there are artifacts that need cross-functional review
- No knowledge bases until there is knowledge that agents repeatedly need

Build coordination mechanisms in response to EXPERIENCED coordination failures, not in
anticipation of hypothetical ones.

---

### Warning 6: Do Not Track Output Metrics

**Source**: Amazon (input metrics over output metrics), The Goal (throughput at the
constraint is the only metric that matters), Lean Startup (vanity metrics vs. actionable
metrics)

Revenue, user count, and app store ratings are OUTPUT metrics. You cannot directly control
them. Tracking them creates anxiety without providing actionable information.

**Applied**: Track only input metrics — things you can directly control and act on:
- Features shipped per week (not revenue per feature)
- Time from idea to shipped (not time to revenue)
- Test coverage of critical paths (not bug count)
- User actions per session (not user satisfaction score)
- Context quality score for agents (not agent output quality)

Output metrics are for investors. Input metrics are for operators.

---

### Warning 7: Do Not Pursue Autonomy Without Accountability

**Source**: Spotify (the accountability half never shipped, and the result was
fragmentation), Art of Action (the three gaps — knowledge, alignment, effects — all
require feedback)

Autonomy is the easy half. Everyone wants autonomy. Accountability is the hard half.
Nobody wants to be measured.

**Applied**: Every autonomous agent or process must have:
- A clear OWNER (DRI)
- A clear METRIC (how we know it's working)
- A clear CADENCE (when we review whether it's working)
- A clear KILL CRITERIA (when we stop doing it)

Without these four, autonomy is just neglect with a better name.

---

### The "Do Not Build" List

| Do Not Build | Instead | Source |
|-------------|---------|--------|
| Complex org structure on paper | Start with 1 working agent, add incrementally | Gall |
| Process to fix capability gaps | Fix the capability (better context, better model) | Netflix |
| Vocabulary without behavior | Implement behaviors, name them later | Spotify |
| Documentation for its own sake | Only docs that improve agent output | Gall, Linear |
| Pre-emptive coordination | Build coordination after coordination failures | Gall, Team Topologies |
| Output metric dashboards | Input metric dashboards | Amazon, Goal |
| Autonomy without accountability | Four elements: owner, metric, cadence, kill criteria | Spotify, Art of Action |
| Multi-agent swarms before single agents work | One excellent agent first | LLM multi-agent research |
| Approval workflows before trust is calibrated | Start with advice process, earn trust incrementally | Netflix, Bridgewater |
| Grand unified knowledge base | 2-3 hops of relevant context per task | Knowledge graph research |

---

## 8. The Proposed Operating Model (High Level)

This section synthesizes everything above into a concrete operating model. It is the input
for Phase 3 (detailed design).

### Core Architecture: Three Layers

The operating model has three layers, mirroring the node hierarchy (Section 3) and Brand's
shearing layers:

```
LAYER A: IDENTITY (changes yearly)
  What: Purpose, vision, principles, taste
  Format: Single document (IDENTITY.md), always loaded in Ring 1 context
  Owner: Founder
  Review: Annually, or when a principle is proven wrong

LAYER B: OPERATING SYSTEM (changes quarterly-monthly)
  What: Processes, standards, decision frameworks, domain definitions
  Format: Structured documents, loaded per-role in Ring 2 context
  Owner: Founder, with agent input
  Review: Monthly, or when a process consistently fails

LAYER C: EXECUTION (changes daily-hourly)
  What: Missions, commitments, tasks, decisions, metrics
  Format: Structured nodes (see Section 3), loaded per-task in Ring 3 context
  Owner: DRI for each node
  Review: Weekly (missions), daily (commitments), per-session (tasks)
```

### The Idea Flow (Instantiated)

From Section 4, instantiated for a 1-person AI-agent company:

**SENSING (continuous)**
- Founder uses the product daily (Linear's dogfooding)
- Analytics track input metrics (Amazon)
- Pain log captures every frustration, bug, and surprise (Bridgewater)
- One agent periodically scans competitive landscape (Amazon System 4)

**SHAPING (when a signal is strong enough)**
- Founder writes a 1-page PR/FAQ (Amazon, adapted for solo scale)
- The PR/FAQ includes: customer intent, hypothesis, boundary conditions, risks
- One agent stress-tests the PR/FAQ adversarially (Bridgewater's disagreement)
- Result: shaped proposal with known risks

**DECIDING (within 1-2 sessions)**
- Decision matrix applied: reversibility x information richness (Section 4)
- High-cost irreversible: founder decides after adversarial review
- Low-cost reversible: experiment (ship behind flag, measure)
- Decision archived with reasoning (Stripe)

**SPECIFYING (1-2 sessions)**
- Three parallel specs: product, technical, verification
- Backbrief: agent summarizes understanding, founder confirms alignment (Art of Action)
- Impact assessment: layers, domains, flow stages (Section 5)
- Result: buildable spec with known dependencies

**EXECUTING (daily)**
- Agent loads: mission (Ring 1), commitment (Ring 2), task + spec (Ring 3)
- Small batches, continuous validation (TypeScript, tests)
- WIP limit: 1 task at a time per agent (The Goal)
- Reversibility by default: feature flags, incremental commits

**LEARNING (after every execution cycle)**
- Did the hypothesis hold? (Lean Startup: pivot / persevere / kill)
- What surprised us? (Bridgewater: pain + reflection)
- Update decision log (Stripe: archive with reasoning)
- Update process if needed (Toyota: kaizen)
- Feed insights back to sensing

### Agent Architecture

Based on LLM multi-agent research ("one good agent beats five unguarded ones") and Gall's
Law ("start simple"):

**Phase 0 (Current)**: One agent, one context window, founder as DRI for everything.
The agent loads the appropriate context ring for each task. No orchestration needed.

**Phase 1 (When one agent is not enough)**: Specialized agents for distinct domains, each
with a clear bounded context:
- Product Agent: owns feature specs, user flows, impact assessment
- Engineering Agent: owns code, tests, deployment, technical specs
- Design Agent: owns visual system, component specs, interaction patterns

Each agent has:
- A role document (Ring 2 context) defining its responsibilities and decision authority
- Access to shared mission and commitment context (Ring 1 and Ring 3)
- A Writer + Critic self-review loop before producing output
- Clear API contracts with other agents (DDD bounded contexts)

**Phase 2 (When agents need coordination)**: Add the MINIMUM coordination mechanism:
- Shared task board (make work visible — Principle 1)
- Dependency declarations on tasks (so agents know what blocks what)
- Decision log that all agents read (consistency across sessions)
- NO orchestrator agent — the founder is the orchestrator

**Phase 3 (When the founder becomes the bottleneck)**: Add an orchestrator:
- Reads missions and commitments
- Routes tasks to appropriate agents
- Monitors for blocking dependencies
- Escalates only what cannot be auto-resolved

Each phase is earned, not planned. Move to the next phase only when the current phase's
limitations are actively causing problems.

### Decision Framework

From Section 2 (tensions), instantiated:

| Decision Type | Method | Owner | Artifact |
|--------------|--------|-------|----------|
| New product / major feature | PR/FAQ + adversarial review | Founder | Archived PR/FAQ |
| Feature variation / UI change | Experiment (flag + A/B test) | Agent DRI | Experiment log |
| Architecture / data model | Design doc + tech review | Founder (with agent input) | Archived design doc |
| Design / aesthetic | Founder taste | Founder | Design decision in DESIGN.md |
| Bug fix | Root cause analysis | Engineering agent | Fix + decision log entry |
| Process change | Pain accumulation + retrospective | Founder | Updated process doc |

### Cadences

From the company case studies, adapted for a 1-person + agents structure:

| Cadence | What | Who | Output |
|---------|------|-----|--------|
| Per-session | Task execution + learning | Agent + founder | Completed task + decision log entry |
| Daily | Review task progress, unblock | Founder reviews agent output | Updated task statuses |
| Weekly | Review commitments, reprioritize | Founder | Updated commitment priorities |
| Monthly | Review missions, evaluate experiments | Founder | Mission updates, kill decisions |
| Quarterly | Review identity layer, update principles | Founder | Updated IDENTITY.md |

### Metrics (Input Only)

Following Amazon's input metrics and The Goal's constraint focus:

**Sensing metrics**:
- Pain points logged per week (are we noticing problems?)
- User signals captured per week (are we listening?)

**Shaping metrics**:
- PR/FAQs written per month (are we generating enough options?)
- PR/FAQs killed per month (is the filter working?)

**Executing metrics**:
- Tasks completed per week (are we shipping?)
- Cycle time: spec to shipped (are we fast?)
- Rework rate: tasks that need re-doing (is our spec quality good?)

**Learning metrics**:
- Decisions logged per week (are we capturing knowledge?)
- Experiments concluded per month (are we learning?)
- Process changes per quarter (are we improving?)

### What This Model Inherits from Each Source

| Source | What We Take | How It Appears in the Model |
|--------|-------------|----------------------------|
| The Goal | Constraint focus, WIP limits | 1 task at a time, bottleneck = founder attention |
| Phoenix Project | Make work visible, four work types | All tasks in structured nodes, typed |
| Thinking in Systems | Feedback loops, leverage points | Learning stage feeds sensing stage |
| Art of Action | Directed opportunism, backbrief | Intent-based agent prompts, spec confirmation |
| Team Topologies | Team APIs, interaction modes | Agent bounded contexts, clear interfaces |
| DDD | Bounded contexts, context mapping | Agent domains, cross-domain contracts |
| How Buildings Learn | Shearing layers | Three-layer operating model (identity/OS/execution) |
| Systemantics | Gall's Law, start simple | Phased agent architecture, earn complexity |
| Lean Startup | Build-Measure-Learn, MVP | Experiment as decision method, small batches |
| Working Backwards | PR/FAQ, customer obsession | PR/FAQ for major features |
| LLM reasoning | Pattern matching, context bias | Templates over rules, structured artifacts |
| Context engineering | Selective loading, precision | Ring-based context loading |
| Multi-agent | Writer + Critic, one good agent | Self-review loop, phase 0 = one agent |
| Knowledge graphs | 2-3 hops, focused context | Task-local context, not global dumps |
| Error reduction | Types first, early feedback | TypeScript strict, continuous validation |
| Amazon | PR/FAQ, STL, input metrics | Idea shaping, DRI, input-only metrics |
| Apple | DRI, Monday review, few products | DRI for everything, weekly review, WIP limits |
| Stripe | Writing culture, API review, craft | Decision archival, quality gates, detail care |
| Spotify | Experiments, feature flags, Encore | Experiment as decision method, design tokens |
| Netflix | Context not control, keeper test | Intent-based direction, kill criteria |
| Toyota | Standardized work, kaizen, andon | Process baselines, continuous improvement, stop-on-defect |
| Bridgewater | Idea meritocracy, pain + reflection | Adversarial review, pain log, decision transparency |
| Linear | Small team, say no, ship | WIP limits, deletion test, craft over process |

---

## Summary: The Five Key Takeaways for Phase 3

1. **The operating model has three layers** (Identity, Operating System, Execution) that
   change at different rates and must be loosely coupled. This is Brand's shearing layers
   applied to org design.

2. **Ideas flow through six stages** (Sensing, Shaping, Deciding, Specifying, Executing,
   Learning) with a feedback loop from Learning back to Sensing. The decision method varies
   by stage and by the reversibility of the decision.

3. **The node hierarchy is three levels** (Mission, Commitment, Task) which map to monthly,
   weekly, and daily cadences. Every node has an owner, a status, and a decision log.

4. **The agent architecture is phased** (single agent -> specialized agents -> coordinated
   agents -> orchestrated agents). Each phase is earned by hitting the limitations of the
   previous phase. Gall's Law is the governing constraint.

5. **The model is LLM-compatible by design**: layered context loading, structured artifacts,
   decision logs as first-class data, templates over rules, state machines for processes,
   and 2-3 hops of context per task.

Phase 3 will take each of these five elements and produce detailed specifications:
document templates, agent prompts, process definitions, metric dashboards, and the actual
file structure that implements this operating model.

---

## Appendix: Source Cross-Reference Matrix

For each of the 23 sources, which sections of this document reference it:

| Source | Sec 1 | Sec 2 | Sec 3 | Sec 4 | Sec 5 | Sec 6 | Sec 7 | Sec 8 |
|--------|-------|-------|-------|-------|-------|-------|-------|-------|
| The Goal | P1,P2,P3 | T2 | - | S5 | D2 | - | W6 | Y |
| Phoenix Project | P1,P3 | - | - | S5 | - | - | - | Y |
| Thinking in Systems | P1,P3,P4,P5 | - | - | S1 | - | - | - | Y |
| Art of Action | P2,P3,P6,P7 | T4 | N | S2,S3,S4 | - | - | W7 | Y |
| Team Topologies | P2,P4 | T3 | - | - | D2 | - | W5 | Y |
| DDD | P2,P4 | T3 | N | S2 | D1,D2 | - | - | Y |
| How Buildings Learn | P4 | - | N | - | D1 | P1,P4 | - | Y |
| Systemantics | P5 | T1 | - | - | - | - | W1,W4,W5 | Y |
| Lean Startup | P3,P5,P6 | T2 | N | S1,S2,S3,S5,S6 | - | - | - | Y |
| Working Backwards | P6,P7 | T2 | N | S2,S3 | - | - | - | Y |
| LLM reasoning | P1,P2 | - | - | - | - | P3,P4,P5 | - | Y |
| Context engineering | P1,P2,P3,P4,P5,P6 | - | - | - | - | P1,P2,P6 | - | Y |
| Multi-agent | P2,P3,P5,P7 | - | - | - | - | - | W1 | Y |
| Knowledge graphs | P1,P4,P5 | - | - | - | - | P6 | W5 | Y |
| Error reduction | P1,P2,P3 | - | - | S5 | - | - | - | Y |
| Amazon | P1,P2,P3,P4,P6,P7 | T2,T3 | N | S1-S6 | D1,D2,D3 | - | W6 | Y |
| Apple | P2,P3,P6,P7 | T3,T6 | N | S1,S3,S4,S5 | - | - | - | Y |
| Stripe | P1,P2,P3,P4 | T5 | N | S1-S6 | D2 | P2 | - | Y |
| Spotify | P3,P4 | T3,T4 | N | S1-S6 | - | - | W3,W7 | Y |
| Netflix | P2,P3,P5,P6,P7 | T1,T4,T6 | N | S1,S3,S6 | - | - | W2,W7 | Y |
| Toyota | P1,P2,P3,P4,P6 | T1 | N | S1-S6 | D3 | - | - | Y |
| Bridgewater | P1,P5,P6,P7 | T4,T6 | N | S1-S4,S6 | - | - | - | Y |
| Linear | P1,P2,P5,P7 | T5,T6 | N | S1,S5 | - | - | W4 | Y |

Legend: P=Principle, T=Tension, N=Node type, S=Stage, D=Dimension, W=Warning, Y=Yes (Section 8)

---

*Phase 2 complete. This document feeds Phase 3: Detailed Design.*
*Generated from 23 sources across 10 books, 5 LLM practice domains, and 8 company case studies.*
