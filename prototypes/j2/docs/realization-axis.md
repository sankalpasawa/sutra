# Realization axis, married to certainty: framework

**Status:** framework for review, no code yet · **Used by:** Adaptation, after Identity has set the goal
**Sources:** Native §3 HOW methodology (`native/platform/how-methodology.html`: §3.2 axes, §3.3 stop rules, §3.4 examples),
Native axes and work atom pages (`native/axes.html`, `native/platform/model/work-atom.html`), `agents/j2/certainty.md`
**Agent instructions:** `agents/j2/realization.md` (Adaptation), `agents/j2/confidence-judge.md` (the judge),
`agents/j2/certainty.md` · **Schema:** `docs/realization-schema.json` · **Picture:** `docs/realization-axis.dot`
**v2:** after review: deciding vs delivering, a separate judge, certainty per workflow, hold and stop rules
**v2.1:** research as the third way to fill an information gap (ask / research / probe); market research as a
research workflow, not a stage (4.5)

**Question this answers:** once Identity gives a goal, how does Adaptation split it into workflows so that the
workflows, taken together, are likely to reach the output in one run?

**Answer in one line:** cut the goal along **realization** (what kinds of thinking turn this idea into a real
thing), read **certainty** for every workflow inside those cuts (how well cause and effect are known there), and
have a **separate judge** score each workflow's confidence. At 80% or above, stop. Below 80%, name the gap and cut
again along whichever of the two axes the gap points to.

## 1. The two axes

Realization and certainty are not alternatives. They are the X and Y of one grid.

| Axis | Question | Splits by | Values | Stops at |
|---|---|---|---|---|
| Realization | What has to become real, and which kind of thinking makes it real? | Kind of thinking (business, product, design, engineering, ...), then abstraction tier inside each | Stages (section 2) | The work atom: one goal, one check that can fail |
| Certainty | Do I have enough information to act? | Known vs unknown cause and effect | `operate`, `analyze`, `experiment`, `stabilize` (`certainty.md`) | The zone's shape |

- Realization is in the **work space**: an idea is only a thought; to exist it needs business thinking, product
  thinking, design thinking, engineering thinking, and someone has to build it and run it.
- Certainty is in the **information space**: every stage of realization meets its own unknowns. The business person
  is unsure users will pay; the product person is unsure users will love the feature; the engineer is unsure the
  architecture will hold. So certainty is read **for every workflow inside every stage**, not once for the goal.
  One stage can mix zones: a known catalogue page and an uncertain conversion question can both be Product work.
- Everything is splitting the task. Realization says *where* to cut; certainty says *what kind* of cut each piece
  gets.

## 2. Realization: the values

### 2.1 The ladder (from §3.2)

Native defines realization as the path from abstract idea to running thing, in eight tiers:

| Tier | What it fixes | Example (§3.4, B1 intake) |
|---|---|---|
| Worldview | What we believe | The operator owns their own work |
| Vision | The future we want | Every operator has a Chief of Staff that classifies what they say |
| Strategy | How we win | Govern above AI; classify before acting |
| Capability | What the system must be able to do | Classify the operator's intent from raw words |
| Architecture | Where it lives and how it is structured | B1 Intent block inside the CoS layer |
| Feature | The thing a user touches | capture → classify → confidence gate → log → route |
| Contract | The exact interface | `intent {type, confidence, routed_to, clarify}` |
| Implementation | The running thing | classifier prompt + `intake_log.jsonl` + emit |

### 2.2 The stages: kinds of thinking that walk the ladder

The tiers say *how concrete* the work is. They don't say *who thinks it*. Companies answer that with departments:
each one brings a different kind of intelligence to the founder's vision. J2 uses these as the realization
values (the **stages**). Each stage owns one kind of thinking and covers a band of tiers.

| Stage | Kind of thinking (its dimension) | Tiers | Decides | Typical artifact | Methods it borrows (§3.4, ex. 5a) |
|---|---|---|---|---|---|
| *(Identity)* | Founder's intent | Worldview, Vision | The goal, constraints, done line | Charter | Given, not a stage |
| Business | Money: revenue, cost, market, edge | Strategy | Why this wins and pays | Business case, one-pager | Lean Canvas, Porter, Wardley, unit economics |
| Compliance | Rules from outside the company: law, regulator, licence, privacy | Strategy → Contract (as constraints) | What is not allowed and what must be filed | Obligation register | Regulator checklists, privacy-by-design |
| Product | Users: who, which jobs, what scope, what first | Capability, Feature | What it must do and in what order | PRD | JTBD, story mapping, MoSCoW, Kano |
| Design | Experience: how it feels and flows | Feature (the surface) | Flows, layout, look, words | Style guide, page map, wireframes | Design thinking, IA, heuristics |
| Engineering | Structure: how it holds together | Architecture, Contract | Components, interfaces, data, scale | HLD, LLD | C4, ADR, arc42 |
| Build | Making | Implementation | The thing itself | Code, site, fit-out | TDD, the builder's checks |
| Operations | Running it every day | Implementation (repeated) | Who does what, supply, support, service levels | SOPs, rotas, runbooks | SOPs, SLAs, queueing |
| Growth | Reaching people | Strategy → Implementation (outward) | Channels, launch, first users | Launch plan | Funnel (AARRR), positioning |

The names are domain-neutral. For a restaurant, Engineering is the kitchen and services layout and Build is the
fit-out. For a website, Operations and Growth are often absent.

**J2 today is already a realization path:** Charter (Identity) → PRD (Product) → HLD (Engineering, architecture) →
LLD (Engineering, contract) → code (Build). The framework makes that path chosen per goal instead of fixed.

### 2.3 Choosing the stages for a goal

Stages are chosen from the **factors**: the things that, if not thought through, make the output unsatisfactory.

1. **List the factors.** These come in three groups:
   - **Requester's constraints** (the charter and the Requester's answers). These are non-negotiable. Examples:
     "10,000 users", "must look premium", "RBI rules", "live by 1 March", "₹40 lakh".
   - **Success factors** for this kind of output (what generally makes a website, a delivery app or a restaurant
     succeed). The LLM's general knowledge is the starting point (`general`). When one of these factors drives a
     decision and memory isn't reliable enough, a research workflow checks it, and the factor becomes `research`
     with a citation (4.5).
   - **Budget factors:** time, money, tokens.

   Each factor gives its name, source (`brief` or `general`), why it is consequential, and a quote for `brief`
   factors.
2. **Place each factor in the stage whose kind of thinking owns it.** Scale goes to Engineering, competitive edge
   to Product and Design, an RBI rule to Compliance, "earthy look" to Design, "pay per order" to Business.
   - Time, money and tokens don't own a stage. They become constraints on every stage's workflows.
   - A factor that fits no stage is **unplaced**. List it; don't hide it inside a stage. An unplaced factor is the
     signal that a perspective is missing (section 6).
3. **Keep a stage only if it owns at least one factor or done-when item**, and only while it still changes what
   gets built or who reads it (the §3.3 decision test). Build is kept whenever something must be made.
4. **Wire the stages.** Each stage names `inputs_from` (the stages whose output it reads). Stages are not strictly
   sequential: business feeds product, product feeds design and engineering, and design and engineering can run side
   by side.
5. **Size to the goal.** A phone-number change is one stage (Build). A site that takes bookings is four or five.
   A delivery business is seven or eight.

### 2.4 Deciding and delivering

Several stages shape one done-when item, but one workflow makes it real. For a booking form:
- Product decides what it asks for.
- Design decides how it looks.
- Compliance decides what consent it needs.
- A Build workflow delivers it.

So every workflow lists `delivers` (the items it makes real) and `informs` (the items its decision shapes). For a
document output (PRD, HLD, LLD), the workflow that writes the section delivers it.

### 2.5 Rules for a stage set

| Id | Rule | Checked by |
|---|---|---|
| R1 | **Complete.** Every done-when item has exactly one delivering workflow, and every `brief` factor is owned by some stage (the 100% rule). | code |
| R2 | **Single delivery.** No item is in two workflows' `delivers`. Any number may list it in `informs`. | code |
| R3 | **One kind of thinking per stage.** No two stages claim the same kind. | code |
| R4 | **Earns its place.** Each stage owns a factor, or delivers or informs an item, and passes the decision test. | code (touches something); LLM (decision test) |
| R5 | **Low coordination cost.** Merge two stages when nearly every item would pass between them and the goal is small. A merged stage names both kinds of thinking. Split it again when the judge marks `size: no` *because* the two kinds pull apart (section 4). | LLM, recorded |
| R6 | **Each stage states** its goal, its done-test and the method it borrows (`null` when none exists). | code (schema) |

### 2.6 Depth inside a stage

Inside a stage, go down the ladder only as far as needed, and stop at work atoms (one goal, one check that can
fail). Examples: Design → page map → section → component; Engineering → components (HLD) → interfaces (LLD).
Possibility is not obligation: a level is added only if it changes what is built or who reads it.

## 3. The grid: certainty for every workflow

Certainty is read exactly as `certainty.md` says. Realization adds no zone rule of its own:
- the five signals for the goal as a whole;
- then a `certainty` zone on **each workflow**, shaped to that zone.

| Workflow zone | Its shape |
|---|---|
| `operate` | Direct build along the obvious seams |
| `analyze` | Options weighed and a choice made (an analysis workflow, or analysis first inside it), then build |
| `experiment` | A probe (hypothesis, signal, fails_if, limit). Work that depends on the result is `deferred` |
| `stabilize` | Fix-only, on the broken part |

- **One workflow, one cell.** Every workflow belongs to one stage and carries one zone. If a piece of work seems to
  need two zones, it is two workflows. They may sit in the same stage.
- **Stage zone is derived, never read.** Code takes the least certain zone among a stage's workflows. It exists only
  so the Map can show where the uncertainty sits.
- **Zones differ across and within stages, and that is the point.** For a delivery app, Compliance (licences) is
  `operate`, Engineering (scale to 10,000 users) is `analyze`, and Product holds an `operate` restaurant catalogue
  next to an `experiment` probe on which cuisines people order.

The result is the plan: **stages × zones → workflows → atoms.**

## 4. Confidence: will this workflow reach its goal?

Every workflow and every stage has a goal. Before anything is built, a **separate judge call**
(`agents/j2/confidence-judge.md`) estimates for each workflow: *if it runs as written, how likely is it to pass its
done-test in one run?*

Adaptation never scores its own plan. This is the same separation Native rules for atoms: the checking engine must
not be the writing engine.
- The judge reads the charter, the proposal and `certainty.md`.
- It writes only scores and what is missing.
- Adaptation revises.
- Code applies the gate and records every round.

### 4.1 The confidence checks

**v2.2, after research on AI judges:** the judge no longer gives a number. It answers small yes/no questions, and code
computes the score.

| Borrowed from | What it changes |
|---|---|
| CheckEval | Fixed binary questions instead of a rating scale; reported to cut disagreement between judges |
| DeepEval DAG | Fixed weights decide the score, not the judge |
| TICK | Item questions written once per charter from its done-when items, and frozen across rounds |
| Comparison | A revision that is no better than before can't score higher |
| Self-consistency | Within 0.05 of the gate, judge twice; the lower counts |

Score = 0.95 minus the weight of each `no`. Any critical `no` (I1, I2, M1, D1, Z1) alone puts the workflow below
0.80. `confidence-judge.md` lists the questions and weights. The six checks below group those questions:

| Id | Check | A `no` usually means |
|---|---|---|
| C1 `inputs` | Everything it needs is given or made by an earlier workflow it reads | A missing Requester fact, a world fact nobody looked up, or a missing upstream stage |
| C2 `method` | A known method or pattern turns those inputs into the output | Open choices, or a question only reactions can answer, or no method known |
| C3 `done_test` | The done-test is observable and pass/fail | A vague goal |
| C4 `factors` | Every factor its stage owns is addressed by some step | Not thorough enough along this stage |
| C5 `zone_fit` | Its shape matches its zone (probe present for `experiment`, analysis for `analyze`) | The certainty reading was skipped or wrong |
| C6 `size` | One kind of thinking and fits one builder's budget | Too big or mixed |

Then it gives `score` (0–1) and names the `weakest` check.
- **Code rule:** any `no` caps the score below 0.80, so a workflow with a known hole can't pass the gate.
- **Stage confidence** is its lowest workflow score. **Plan confidence** is the lowest stage score. Weakest link,
  on purpose: a plan is only as likely as its least likely part.

### 4.2 The gate

- **Score ≥ 0.80:** good enough. Don't go deeper into this workflow. Move to the next one.
- **Score < 0.80:** name the gap from the weakest check and revise along the axis it points to (4.3), then score
  again. The record keeps every round, for example `0.50 → 0.62 → 0.84`.
- **Limit:** three revision rounds per workflow. After that the workflow is **not funded**. It goes into
  `not_ready` with its score, its weakest check, a `stop_reason` and a `route`:
  - `identity`: a fact or a Requester decision would close the gap. It waits.
  - `priority`: the gap is risk, not missing input. Priority may fund it explicitly as `at_risk`.
  - `left_out`: not worth it this cycle.

  Workflows that depend on it are held with it. Budget is real: the aim is fewer failed cycles, not endless
  planning, and never funding work the judge thinks will fail without someone choosing to.

### 4.3 From gap to remedy

| Weakest check and what it shows | Remedy | Axis |
|---|---|---|
| C1: a **Requester fact** is missing (name, price, date, email) | Blocking: hold the branch and ask Identity. Non-blocking: proceed with an `Assumption:` line (4.4). Never a probe. | none: ask |
| C1: a **world fact** is missing (market, competitors, rules, how others solve it, feasibility) | A research workflow in the stage that owns the question; whoever needs the answer reads it through `inputs_from` (4.5) | Research: find |
| C1: needs a **decision from another kind of thinking** (the build needs a layout nobody chose) | Add the missing stage, or a workflow in the stage that owns that thinking, and wire `inputs_from` | Realization: add stage |
| C2: **several valid options**, a wrong pick wastes budget | Put an analysis workflow before it | Certainty: `analyze` |
| C2: success **depends on people's reactions** | Replace it with 1–3 probes; defer what depends on them | Certainty: `experiment` |
| C2: **no known method** at all for this kind of problem | Put a research workflow first: find the industry-standard method for this, then plan from it | Research: method |
| C2: it **already failed** for an unclear cause | One fix-only workflow | Certainty: `stabilize` |
| C3: done-test is vague | Rewrite the done-test. No new workflow. | none: rewrite |
| C4: an owned factor isn't addressed | Add steps for it in the same stage (go further along the axis) | Realization: deepen |
| C5: shape doesn't match the zone | Re-read the stage's certainty signals and reshape | Certainty: re-read |
| C6: too big, or two kinds of thinking in one | Split down one tier, or split the stage along the line between the two kinds of thinking (e.g. Product & design into Product and Design) | Realization: split |

When the gap is unclear, try certainty first, then realization, then the research route.

### 4.4 Missing facts: wait or proceed

A missing fact has one of two effects on dependent work, and the plan says which:

| The gap | Effect |
|---|---|
| **Blocking:** the done-test can't pass without it (the price on a payment page) | The workflow and everything downstream of it (by `inputs_from`) get `hold: waiting_on_identity` and are not funded. Identity asks. When the answer arrives, they go back to the judge. |
| **Non-blocking:** the output is correct without it (an optional phone number) | The workflow proceeds and writes the gap as an `Assumption:` line or "to be confirmed". The judge marks `inputs` as `partly`, not `no`. |

Both are listed in `open_facts` with `blocking: true|false`.

### 4.5 Three ways to fill an information gap, and research workflows

Missing information has three possible sources, and the plan must say which one it is:

| Gap | Who can close it | Route |
|---|---|---|
| **Requester fact:** only the Requester knows it (their price, their date) | The Requester, through Identity | Ask (4.4) |
| **World fact:** it exists and can be looked up (competitors, regulations, how leading products do it, feasibility) | A research workflow | Research |
| **Reaction:** only trying with real people shows it | A probe | `experiment` (`certainty.md`) |

Never ask the Requester for something that can be looked up, and never probe for something already known. In
Cynefin terms, a world fact belongs to the knowable side (Complicated: sense, analyse): evidence settles it, not
experiment.

**Market research is one kind of research workflow, not a stage.** Research is a way of reducing uncertainty, so it
sits with the question's owner and R3 (one kind of thinking per stage) holds:

| Question about | Research workflow sits in |
|---|---|
| Market, competitors, pricing, economics | `business` |
| Users, similar products, what users expect | `product` |
| Regulations, licences, privacy rules | `compliance` |
| Technical feasibility | `engineering` |

**Shape.** A research workflow carries:
- `question`: what to find out;
- `feeds`: the decision or workflow the answer changes;
- `min_sources`: at least 3;
- `output`: its entry in the run's `research.md`.

Its done-test is that entry: the question, the cited sources, the findings, and one line on what changes in the plan.
It delivers no item. It informs the items its answer shapes, and every workflow that needs the answer lists it in
`inputs_from`.

**Only when it changes something.** A research workflow must name a decision it feeds. If the answer would change
nothing, the judge marks it not needed. The decision test applies to research like everything else.

**Without web access.** If the run can't reach outside sources, no research workflow is planned. The factor stays
`general`, is marked `unverified`, and the judge scores `inputs` as `partly`, so the gap stays visible.

**Examples:**
- **Sudoku:** "How do leading Sudoku apps grade difficulty and give hints?" (`product`) feeds the difficulty and
  hint decisions.
- **Food delivery:** "What commission do delivery apps in this city charge restaurants?" (`business`) feeds the fee
  model.
- **The restaurant in Pune:** "What licences does a 40-seat restaurant in Pune need?" (`compliance`) feeds the
  compliance checklist. It is looked up, never asked of the Requester.

## 5. The whole procedure

1. **Goal** from Identity: the charter, done-when items, constraints.
2. **Factors:** the Requester's constraints, then success factors, then budget factors (2.3.1).
3. **Stages:** place the factors, keep the stages that earn their place, wire them.
4. **Workflows:** per stage. Each has a goal, a done-test, `delivers` and `informs`. Down to atoms. Check R1–R6.
5. **Certainty per workflow:** `certainty.md` as it stands (3).
6. **Judge:** a separate call answers six checks, lists what is missing, and scores each workflow. Code derives
   stage and plan confidence (4.1).
7. **Gate:** under 0.80, Adaptation applies the remedy the weakest check points to, and the judge scores again,
   up to three rounds (4.2, 4.3). Blocking facts hold their branch (4.4). After three rounds, `not_ready`.
8. **Propose:** stages, grid, workflows, confidence history, open facts, not-ready workflows, deferred items,
   unplaced factors. Then Priority, Coordination and Audit as today. Priority funds only workflows that passed the
   gate, plus any `not_ready` ones it explicitly accepts `at_risk`.
9. **Each later cycle:** re-read certainty (a probe came back, a fix failed, the Requester answered), re-judge the
   workflows still to run, and apply the reflection in section 6.

## 6. When the output misses: finding the missing piece

When Audit says the output doesn't meet the goal, Adaptation sorts the miss into one of four cases before
proposing rework. Like a Lego set with a piece missing, the shape of the gap says which piece it needs.

| Case | What it means | Next time |
|---|---|---|
| Too shallow | The factor was known and its stage existed, but there were too few steps | Deepen that stage (more workflows or steps along it) |
| Wrong owner | The factor was known but no stage owned it, or the wrong one did | Fix the placement. Record it as a lesson for this kind of goal. |
| Missing perspective | A factor nobody listed (e.g. the site messages someone, but nothing carries their reply back: *external communication* was a factor) | Add the factor. If no stage's kind of thinking fits it, record it as a candidate new stage or axis. |
| Not foreseeable | Real uncertainty: only trying could tell | Nothing was wrong with the plan. Certainty rises now that the signal is in. |

Lessons are recorded per kind of goal ("delivery app: Operations owns rider supply"), so the next run of that kind
starts with a better stage set.

## 7. Worked examples

### 7.1 Change the phone number on the site
- **Factors:** the new number (brief).
- **Stages:** Build only.
- **Certainty:** `operate`.
- **Workflows:** one.
- **Confidence:** 0.95. The gate passes at once.
- The framework adds no cost to simple work.

### 7.2 Coffee shop website: "handle 10,000 visitors a month and stand out from the chains"

| Stage | Owns (factors, items) | Zone | Workflows | Confidence rounds |
|---|---|---|---|---|
| Product | stand out (edge); informs every item | `analyze`: unranked feature list | Page plan | 0.62 → 0.85 (C4: "stand out" had no step; added a signature-drinks section) |
| Design | stand out (look); "warm, local"; informs every item | `analyze`: style words open | Style guide | 0.84 |
| Engineering | 10,000 visitors (scale); informs every item | `operate`: static site, known pattern | Static build plan, image budget | 0.90 |
| Build | delivers every item | `operate` | Menu and drinks; visit and contact | 0.80–0.92 |

Plan confidence is 0.80. The first draft had Product and Design merged as one stage at 0.55, with C6 `no`: one
stage was mixing "what to say" with "how it looks". Splitting it raised both above the gate.

### 7.3 Food delivery for 10,000 users in one city

| Stage | Workflows and their zones | Why |
|---|---|---|
| Business | fee model `analyze` | Commission vs delivery fee: several valid models |
| Compliance | licences and privacy `operate` | Food licence, tax registration, privacy policy: known lists |
| Product | restaurant catalogue `operate`; cuisine probe `experiment` | The catalogue is a known pattern; which cuisines people order only trying shows |
| Design | ordering flow `analyze` | Known patterns, several choices |
| Engineering | architecture for dinner peak `analyze` | At 10,000 users the architecture choice matters |
| Build | app, back end `operate` | Follows the LLD |
| Operations | rider supply `analyze` | Supply per zone, restaurant onboarding |
| Growth | first-channel probe `experiment` | Which channel brings the first 1,000 orders |

Product mixes two zones, and that is allowed. The goal zone under `certainty.md` is `experiment`. The cuisine and
channel probes run first. Items that depend on them (the full menu set, paid campaigns) are deferred.

### 7.4 Open a 40-seat restaurant in Pune in four months on ₹40 lakh (not tech)
- **Factors:** four months and ₹40 lakh are constraints on every stage, not stages.
- **Stages and zones:**
  - Business (`analyze`: menu price vs footfall)
  - Compliance (`operate`: food licence, fire NOC, signage)
  - Product (`analyze`: menu)
  - Design (`analyze`: interior)
  - Engineering (`operate`: kitchen and services layout)
  - Build (`operate`: fit-out)
  - Operations (`analyze`: staff, suppliers)
  - Growth (`experiment`: soft launch to test which dishes pull)
- **The weakest link before revising:** Build at 0.58, C1 `no`, "kitchen equipment lead time unknown". That is a
  blocking fact (the four-month date can't be checked without it), so the fit-out branch is held and Identity asks.
  It is not a probe.

### 7.5 J2 today: PRD → HLD → LLD → code
- **Stages:** Product (PRD), Engineering (HLD, then LLD: two tiers inside one stage) and Build (code).
- **What changes under this framework:** how many workflows each document gets is no longer the LLM's free choice.
  It follows from the stage's zone and from the confidence gate. An `analyze` PRD gets an analysis workflow first.
  A confident HLD gets no extra cutting.

## 8. What the Map will show (for the code step)

- **Stages** are the boxes on the trunk (as the documents are today), each with a kind-of-thinking label.
- **Zone** is a badge on each workflow, and on each stage box the derived (least certain) zone.
- **Confidence** is a number on each workflow with its history (`50 → 62 → 84`), and the stage and plan confidence.
- **Remedies** are shown as the edge that created a workflow ("split from Product & design", "probe added: certainty").
- **Unplaced factors and deferred items** are listed under the map.
- Versions of the map over time (stages merged, split or added) are a later feature.

## 8a. Code: the planning half (built, outside J2's loop)

| File | What it does |
|---|---|
| `j2_realization.py` | `plan_goal(charter)`: Adaptation's plan (realization.md + certainty.md) → code checks → judge (confidence-judge.md) → revise below 0.80, up to 3 rounds → `not_ready`, holds, roll-ups. Writes `trace.json` (every call) and `report.md` |
| `realization_pilot.py` | Runs the briefs in `scenarios/realization_briefs.json` and writes `runs/realization-pilot-<time>/` with one report per brief and `summary.md` |
| `realization_test.py` | Offline checks (mock): every rule, the cap and roll-ups, holds and routes, the realization.md example, whole runs |

What code checks on every plan (`plan_faults`); a plan with faults goes back once with them named:
- **R1, R2:** every item is delivered once, unless deferred.
- **R3:** one kind of thinking per stage.
- **R4 (code part):** each stage owns a factor or touches an item.
- **R6:** each stage gives its goal, done-test and method.
- **Factors:** factor sources, quotes and citations; factor and stage ownership agree.
- **Wiring:** workflow `inputs_from` names exist, with no cycles.
- **Research workflows:** 3+ sources, a `research.md` entry, no delivery, never in build.
- **Open facts:** each names its workflow and whether it blocks.
- **Certainty:** the rule in `certainty.md`, unchanged.

Run it:
- `python realization_pilot.py`: all briefs.
- `python realization_pilot.py sudoku --no-web`: one brief, with research workflows not allowed.
- `python realization_test.py`: the offline checks.

### In J2 (`J2_REALIZATION=1`, off by default)

The first plan of a website run goes through the realization axis (not documents, a blueprint build or a change
request):
1. **Plan:** `plan_goal`, with J2's rules added to the task: no check, review or report workflows, and one section per
   build workflow. Research is off, because J2's model calls have no web access.
2. **Decide:** Adaptation writes the decide workflows' decisions to `decisions.md`, in one call, with code checking
   that each has 2+ options, a choice, why, failure cases and rules for builders.

   Decide workflows are **not funded**: in J2 a function's thinking is free and only building is priced. This keeps
   the validator, the rate card and the builders unchanged. The flip side is that Priority never sees the cost of the
   decisions, only the AI calls they use.
3. **Ask:** if blocking Requester facts are waiting, Adaptation asks Identity once (POLICY_QUESTION). After the answer,
   the workflows waiting on those facts are proposed too.
4. **Propose:** Adaptation's normal J2 proposal is told to propose exactly the plan's deliver workflows:
   - the same names and covers;
   - dependencies taken from the plan;
   - checks that prove each done-test and follow its decisions;
   - held and not-ready items in `left_out` with their reasons.

   The proposal's reply limit rises from 900 to 8,000 tokens. Validator, Priority, Coordination and Audit then run as
   usual.
5. **Build:** each builder's brief has `decisions_to_follow`: the decisions upstream of its workflow, or about the
   items it covers.
6. **Record:** `realization.json`, `realization.md`, `decisions.md`, and `summary.json → realization`. The summary
   includes whether the proposal followed the plan: planned, followed, not proposed and extra workflow names.

Later cycles, after Audit, use J2's normal rework flow. Not covered yet:
- the Map does not draw stages or confidence;
- the start page has no switch;
- the judge is not shown J2's necessary conditions.

## 9. Out of scope here, and open questions

- **Not in this framework:** lens and personas (the kind-of-thinking label is where they will attach); the time,
  money and scale axes (carried as constraints for now); the code itself.
- **Open questions:**
  1. Is weakest-link (minimum) the right roll-up, or a product of the workflow scores?
  2. Is 0.80 right for every zone, or should `experiment` pass lower, since a probe exists to learn?
  3. How stable are the LLM's scores across runs? This should be measured the way the certainty experiment was:
     same brief, three runs, compare.
  4. Should the stage list be fixed (the nine above) or allowed to grow from lessons (section 6)?
  5. Should the judge be its own role or Audit in a plan-review mode? It is its own file for now, so the pilot can
     test it alone.
