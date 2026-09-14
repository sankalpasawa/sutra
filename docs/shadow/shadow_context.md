# Shadow Context

> **Canonical Shadow-only source of truth**
>
> This document contains everything currently relevant to understanding,
> designing, implementing, testing, and improving **Shadow**.
>
> It intentionally excludes general Sutra context unless that context
> directly affects Shadow.
>
> **Date:** 2026-09-14

------------------------------------------------------------------------

# 1. Shadow --- Core Definition

**Shadow is a persistent delegate that acts on behalf of a human to get
work done.**

The human gives Shadow an intended outcome.

Shadow is responsible for figuring out how to achieve that outcome,
driving the underlying AI worker, supervising its progress, intervening
when necessary, verifying completion, and involving the human only when
genuinely required.

The core promise is:

> **The human should describe what they want done, not operate the
> machinery required to get it done.**

Shadow therefore sits between the human and the underlying worker AI.

``` text
Human
  ↓
Shadow
  ↓
Worker AI / Chat
  ↓
Work
```

But the relationship is not one-way.

``` text
Human
  ↓
Delegate outcome
  ↓
Shadow
  ↓
Worker works
  ↓
Shadow observes
  ↓
Shadow judges
  ↓
Shadow intervenes when necessary
  ↓
Worker continues
  ↓
Shadow verifies
  ↓
Done / Escalate
```

------------------------------------------------------------------------

# 2. Why Shadow Exists

The problem Shadow is trying to solve is **human supervision overhead**.

Without Shadow:

``` text
Human
  ↓
Ask AI to do something
  ↓
Watch AI
  ↓
Notice problem
  ↓
Correct AI
  ↓
Watch again
  ↓
Correct again
  ↓
Verify result
```

The human becomes the supervisor.

Shadow should take over much of that role:

``` text
Human
  ↓
State desired outcome
  ↓
Shadow supervises
  ↓
Human is involved only when needed
```

The success condition is therefore not simply "Shadow can run an AI."

It is:

> **Does Shadow reduce the amount of human supervision required to
> reliably achieve an outcome?**

------------------------------------------------------------------------

# 3. Shadow's Most Important Distinction

Shadow is **not just a task launcher**.

Shadow is **not just a retry mechanism**.

Shadow is **not just another chat interface**.

The worker's job is:

> **Do the task.**

Shadow's job is:

> **Make sure the task actually gets done.**

A worker may produce lots of activity without making meaningful
progress.

Shadow needs to recognize that difference.

------------------------------------------------------------------------

# 4. The Supervisory Loop

The core Shadow loop is:

``` text
DELEGATE
   ↓
WORK
   ↓
OBSERVE
   ↓
JUDGE
   ↓
INTERVENE
   ↓
WORK
   ↓
VERIFY
   ↓
FINISH / ESCALATE
```

Each stage matters.

## 4.1 Delegate

Human provides:

-   desired outcome
-   optional completion criteria
-   potentially type/context

Shadow creates/drives the underlying mission.

## 4.2 Work

The worker AI performs the task.

It may:

-   reason
-   plan
-   search
-   use tools
-   write code
-   create artifacts
-   investigate
-   execute actions
-   produce a deliverable

## 4.3 Observe

Shadow receives/observes the worker's activity.

Shadow needs visibility into enough of the worker's behavior to judge
whether the task is progressing.

## 4.4 Judge

Shadow evaluates the worker.

Possible judgments include:

-   progressing normally
-   stuck
-   looping
-   over-planning
-   misunderstanding the goal
-   producing low-quality/incomplete output
-   missing required capability
-   needs human input
-   complete

## 4.5 Intervene

When necessary, Shadow sends a useful correction.

The intervention should be **specific to the observed failure**, rather
than blindly restarting the worker.

## 4.6 Verify

Shadow should determine whether the intended outcome has actually been
achieved.

This is different from:

> "The worker says it is done."

The relevant question is:

> "Is it actually done?"

## 4.7 Finish / Escalate

If complete:

-   finish the mission.

If blocked or requiring human authority:

-   surface a clear `NEEDS YOU` state / escalation.

------------------------------------------------------------------------

# 5. Outcome-Based Delegation

A central Shadow primitive is the distinction between **procedure** and
**outcome**.

The human should primarily provide the outcome.

Example:

``` text
Outcome:
Create the requested feature.

Done when:
The feature works and the relevant tests pass.
```

The human should not have to micromanage:

``` text
Step 1...
Step 2...
Step 3...
```

Shadow should determine the appropriate execution path.

------------------------------------------------------------------------

# 6. `Done When`

`Done when` is one of the most important concepts in Shadow.

It provides an explicit completion condition.

Without it, Shadow may have to infer completion from a worker's
language.

With it, Shadow has a concrete target to verify.

Conceptually:

``` text
Mission outcome
      +
Completion criteria
      ↓
Shadow verification
```

A good `Done when` condition should be observable and testable where
possible.

Example:

``` text
Outcome:
Fix the login bug.

Done when:
The failing test passes and the login flow works.
```

The product should avoid treating a worker's statement such as "done" as
sufficient evidence by itself.

------------------------------------------------------------------------

# 7. Current Delegation UX

The current Shadow interface includes a `+ Delegate` flow.

Observed concepts include:

## What should Shadow get done?

The mission/outcome.

## Done when

Optional completion criteria.

## Work type

Current options include:

-   fix
-   feature
-   research
-   watch
-   add/custom

The UI describes Shadow as starting a new chat for the task and driving
it itself.

This is the current product surface; implementation should be verified
against the codebase.

------------------------------------------------------------------------

# 8. Mission / Task Model

The current product exposes a mission/task concept.

A mission has concepts such as:

-   outcome
-   completion criteria
-   work type
-   worker chat
-   budget / turn count
-   current state
-   retry
-   open worker chat

Current visible states include:

-   `READY`
-   `NEEDS YOU`
-   `PAUSED`
-   `FAILED`

A successful/completed state also exists conceptually, but the exact
implementation/state naming must be verified in code.

------------------------------------------------------------------------

# 9. `NEEDS YOU`

`NEEDS YOU` should mean more than "the AI got stuck."

It should represent a situation where human involvement is genuinely
required.

Examples may include:

-   a consequential decision only the human can make
-   permission/approval
-   missing information that Shadow cannot infer safely
-   an action crossing an authority/safety boundary
-   repeated failure where autonomous recovery is no longer productive

The desired behavior is:

``` text
Worker blocked
   ↓
Shadow diagnoses why
   ↓
Can Shadow resolve it safely?
   ├── Yes → intervene / continue
   └── No  → NEEDS YOU
```

The system should avoid escalating simply because the worker encountered
an ordinary obstacle that Shadow could reasonably resolve.

------------------------------------------------------------------------

# 10. Worker Relationship

Shadow and the worker have different responsibilities.

## Worker

Optimizes for solving the delegated task.

## Shadow

Optimizes for successful completion of the delegated outcome.

This creates a supervisor/worker relationship:

``` text
Shadow
  │
  ├── mission understanding
  ├── progress evaluation
  ├── intervention
  ├── completion verification
  └── escalation
       │
       ↓
Worker
  ├── planning
  ├── execution
  ├── tool use
  └── deliverable
```

Shadow should not unnecessarily duplicate all worker reasoning.

Its reasoning should be focused on **supervision**.

------------------------------------------------------------------------

# 11. Intervention

A good intervention is:

-   grounded in what the worker just did,
-   directed toward the mission outcome,
-   concise enough to be actionable,
-   proportional to the problem,
-   followed by continued observation.

Observed behavior already demonstrates this concept.

Example pattern:

``` text
Worker:
Creates another planning/scaffolding artifact.

Shadow:
Recognizes that sufficient planning already exists.

Shadow intervention:
Stop planning and produce the actual deliverable.

Worker:
Continues execution.
```

This is the behavior Shadow should become increasingly good at.

------------------------------------------------------------------------

# 12. Important Worker Failure Modes

Shadow should be able to detect at least these classes of failure.

## A. Over-planning

The worker continues planning after it has enough information to
execute.

## B. Stuckness

The worker repeatedly fails to make progress.

## C. Loops

The worker repeats essentially the same actions/reasoning.

## D. Goal drift

The worker starts doing work that is not meaningfully connected to the
mission.

## E. Misunderstanding

The worker interpreted the requested outcome incorrectly.

## F. Premature completion

The worker claims completion without satisfying the actual outcome.

## G. Low-quality completion

The worker produces something technically complete-looking but does not
meet the intended quality/criteria.

## H. Missing capability

The worker lacks the tool, permission, context, or capability needed.

## I. Human dependency

The task genuinely requires a human decision or authority.

These should become a useful taxonomy for dogfooding and future metrics.

------------------------------------------------------------------------

# 13. Completion Verification

A central Shadow responsibility is:

> **Verify, don't merely trust.**

Potential evidence for completion can include:

-   explicit `Done when` criteria
-   tests
-   files/artifacts existing
-   expected outputs
-   tool results
-   observable system state
-   worker output

The exact verification mechanism depends on the task.

The important product principle is:

``` text
Worker says done
        ≠
Shadow knows done
```

------------------------------------------------------------------------

# 14. Autonomy

Autonomy is a central Shadow dimension.

The long-term goal is for Shadow to act on the user's behalf without
asking permission for every small decision.

However:

> **Autonomy must be bounded by authority and safety.**

The current UI contains autonomy levels:

-   L0 --- Watch
-   L1 --- Suggest
-   L2 --- Draft
-   L3 --- Act

There is also a confirmation concept around the highest tier and hard
safety floors.

These labels should currently be treated as **current product design**,
not necessarily as Sankalp's exact terminology.

The deeper product question is:

> **What authority does Shadow have, and where must it stop?**

------------------------------------------------------------------------

# 15. Safety Floors

Some actions should remain confirmation-first even when Shadow is
otherwise highly autonomous.

Examples currently represented include:

-   destructive Git operations
-   external/client repositories
-   irreversible external sends

These are examples of hard floors.

The principle is:

``` text
Normal work
    → Shadow acts

Consequential / irreversible action
    → Shadow asks / escalates
```

The exact enforcement mechanism should be verified in implementation.

------------------------------------------------------------------------

# 16. Shadow Memory

The vision implies that Shadow should have continuity rather than
behaving like a brand-new delegate for every interaction.

Relevant forms of continuity may include:

-   confirmed user instructions
-   preferences
-   Shadow behavior
-   prior mission context
-   ongoing work
-   organizational/capability context

The current UI contains a Memory area with learned/confirmed
instructions.

However, the meeting does **not** establish a complete memory
architecture.

Do not assume details such as:

-   exact storage format
-   retrieval architecture
-   automatic learning policy
-   memory ranking
-   forgetting policy

unless verified elsewhere.

------------------------------------------------------------------------

# 17. Shadow Personality / Behavioral Identity

The broader vision includes Shadow having a consistent way of behaving
on behalf of the human.

This should be understood as **behavioral identity**, not merely tone of
voice.

Potential dimensions include:

-   how aggressively it acts
-   how much it verifies
-   when it asks for help
-   how persistent it is
-   what it prioritizes
-   how it communicates decisions

These are product hypotheses unless explicitly implemented or specified.

------------------------------------------------------------------------

# 18. Persistence

For Shadow to become a true delegate, continuity across sessions
matters.

Potential persistence areas include:

-   missions
-   mission state
-   Shadow instructions
-   memory
-   authority settings
-   worker relationships
-   ongoing work
-   reusable capabilities

The exact persistence currently implemented must be established through
code inspection.

Do not assume that UI persistence implies backend persistence.

------------------------------------------------------------------------

# 19. Presence

The current Shadow settings UI includes a Presence concept.

Observed controls include:

-   corner card on every screen
-   quiet hours
-   nudges per hour
-   hide for this app

The broader idea is that Shadow is not necessarily confined to a single
chat.

However, the exact Presence behavior and whether all controls are
implemented must be verified.

------------------------------------------------------------------------

# 20. Attention

The current settings UI includes an Attention concept.

Observed areas include:

-   Watching
-   Goals
-   Conversations

The UI also shows watched/off/waiting concepts.

The underlying product hypothesis is that Shadow should be able to
maintain attention on things that matter to the user instead of only
reacting to a manually opened chat.

Exact implementation and intended behavior need verification.

------------------------------------------------------------------------

# 21. Watch / Recurring Work

`watch` appears as a current delegation type.

This connects to the longer-term idea that Shadow can remain responsible
for a condition or recurring piece of work.

Potential pattern:

``` text
User delegates:
"Keep an eye on X."

Shadow:
observes X
    ↓
detects meaningful change
    ↓
acts / informs user
```

The exact current watch implementation must be verified.

The product should avoid unnecessary notifications.

A useful Shadow should surface **meaningful events**, not generate
noise.

------------------------------------------------------------------------

# 22. Task Budgets and Concurrency

The current UI exposes concepts including:

-   maximum running tasks
-   per-task turn budget

An observed example uses a budget such as 20 turns.

These are important controls because autonomy without resource bounds
can lead to:

-   runaway loops
-   wasted computation
-   long unproductive missions
-   delayed escalation

A budget should therefore be treated as a **supervision boundary**, not
merely a technical quota.

------------------------------------------------------------------------

# 23. Human Escalation

Shadow should escalate when:

1.  human authority is required,
2.  required information cannot be safely inferred,
3.  safety boundaries are reached,
4.  autonomous recovery is no longer productive,
5.  the mission is ambiguous in a way that materially affects the
    outcome.

A good escalation should explain:

-   what happened,
-   what Shadow tried,
-   what is blocked,
-   what decision/action is needed from the human.

Bad escalation:

> "I need help."

Better:

> "The implementation is complete, but deploying it requires approval
> for the production repository. Should I proceed?"

The goal is to minimize the cognitive load of the human even when
escalation is unavoidable.

------------------------------------------------------------------------

# 24. Future Shadow Orchestration

The long-term vision extends Shadow beyond one worker chat.

Conceptually:

``` text
Human
  ↓
Shadow
  ↓
Department / Capability
  ↓
Agents / Worker Chats
  ↓
Work
```

Shadow could eventually determine:

-   which capability is needed,
-   whether it already exists,
-   whether a new capability should be created,
-   which agents should participate,
-   how work should be coordinated,
-   how the final result should be verified.

This is future direction, not the immediate implementation requirement.

------------------------------------------------------------------------

# 25. Shadow Creating Capabilities

An important future idea is that Shadow should not only **use**
capabilities.

It may eventually create them when the user's desired outcome requires
something that does not yet exist.

Example:

``` text
Human:
"I want ongoing product usage analytics."

Shadow:
No suitable capability exists.

→ creates/orchestrates analytics capability
→ produces initial result
→ capability becomes reusable
```

The next time:

``` text
Human:
"Give me the latest product usage."

Shadow:
Recognizes existing analytics capability
→ reuses it
→ produces updated result
```

This is a key distinction between:

**AI that answers requests**

and

**AI that builds persistent organizational capability.**

------------------------------------------------------------------------

# 26. Reuse and Continuity

Shadow should eventually understand that previous work can be valuable
infrastructure for future work.

Instead of:

``` text
Request 1 → build from scratch
Request 2 → build from scratch
Request 3 → build from scratch
```

The desired model is:

``` text
Request 1
  ↓
Create capability
  ↓
Request 2
  ↓
Reuse capability
  ↓
Request 3
  ↓
Improve capability
```

This makes Shadow increasingly valuable over time.

------------------------------------------------------------------------

# 27. Repeated Work → Apps / Artifacts

If a workflow becomes sufficiently valuable or recurring, it may
eventually become a persistent:

-   app
-   dashboard
-   artifact
-   workflow
-   routine
-   reusable capability

For Shadow, the important idea is not the UI format.

The important idea is:

> **Shadow should help turn repeated intent into persistent
> capability.**

Potential progression:

``` text
One-off task
    ↓
Repeated task
    ↓
Reusable workflow
    ↓
Persistent capability
    ↓
App / artifact / routine
```

------------------------------------------------------------------------

# 28. Shadow Maintenance

If Shadow creates or manages persistent capabilities, it may eventually
also be responsible for their ongoing health.

Potential responsibilities:

-   monitor
-   detect failures
-   maintain
-   refresh
-   improve
-   escalate

This is future scope unless current implementation demonstrates it.

------------------------------------------------------------------------

# 29. Hardening Shadow

Shadow itself should evolve from flexible AI behavior toward reliable
system behavior.

Early:

``` text
Prompt
+
Reasoning
+
Context
+
Memory
```

Later:

``` text
Observed successful behavior
        ↓
Reliable pattern
        ↓
Deterministic mechanism
        ↓
Hardened workflow/code
```

The team should not prematurely hard-code behavior before understanding
it.

Dogfooding should reveal which behaviors are worth hardening.

------------------------------------------------------------------------

# 30. Dogfooding Shadow

Shadow should be used to do actual work.

The learning loop is:

``` text
Real mission
   ↓
Shadow behavior
   ↓
Success / failure
   ↓
Classify what happened
   ↓
Identify missing capability
   ↓
Improve
   ↓
Run another real mission
```

This is more valuable than designing Shadow entirely from theory.

Every real mission can be treated as a product experiment.

------------------------------------------------------------------------

# 31. What We Should Observe During Dogfooding

For every meaningful mission, look for:

### Delegation

-   Did the user know what to tell Shadow?
-   Was the outcome clear?
-   Was `Done when` useful?

### Worker behavior

-   Did the worker understand the mission?
-   Did it make progress?
-   Did it over-plan?
-   Did it loop?
-   Did it drift?

### Shadow behavior

-   Did Shadow notice the problem?
-   Did Shadow intervene at the right time?
-   Was the intervention correct?
-   Was it too aggressive?
-   Was it too passive?

### Verification

-   Did Shadow correctly determine completion?
-   Did it accept a false completion?
-   Did it unnecessarily continue?

### Escalation

-   Did it ask the human when necessary?
-   Did it ask too early?
-   Did it ask too late?
-   Was the request clear?

### Overall

-   How much human intervention was required?
-   Would the user trust Shadow with the same class of task again?

------------------------------------------------------------------------

# 32. Success Criteria

Shadow should ultimately improve measurable properties such as:

## Completion reliability

How often delegated missions reach the intended outcome.

## Human intervention

How many times the human needs to step in.

## Intervention quality

Whether Shadow's interventions actually improve worker behavior.

## False completion rate

How often Shadow incorrectly considers an incomplete task finished.

## False escalation rate

How often Shadow asks the human unnecessarily.

## Recovery rate

How often Shadow can recover a struggling worker without human help.

## Time / turn efficiency

Whether Shadow gets outcomes without unnecessary work.

## User trust

Whether users become comfortable delegating increasingly important
tasks.

These should be validated experimentally rather than assumed.

------------------------------------------------------------------------

# 33. Important Product Hypotheses

These are hypotheses, not facts:

### H1

Users prefer delegating outcomes to Shadow over manually operating
worker AI.

### H2

A dedicated supervisory layer materially improves task completion
reliability.

### H3

`Done when` significantly improves Shadow's ability to verify
completion.

### H4

Reasoned intervention is more valuable than automatic retry.

### H5

Persistent Shadow context makes repeated delegation substantially
better.

### H6

Safe autonomy can reduce supervision without reducing user control.

### H7

Successful repeated missions should eventually become reusable
capabilities.

These hypotheses should be tested through real usage.

------------------------------------------------------------------------

# 34. What Not to Build Prematurely

Do not let the future vision cause the current POC to become
unnecessarily complex.

Do not start by trying to fully implement:

-   recursive Shadow hierarchies,
-   every possible department,
-   a complete organization simulator,
-   elaborate memory architecture,
-   every autonomy level,
-   a full marketplace integration,
-   every possible app-generation workflow.

The immediate question is simpler:

> **Can Shadow reliably supervise a worker and get a real task done with
> less human intervention?**

------------------------------------------------------------------------

# 35. Current vs Future

## Current / visibly represented

-   delegation
-   mission/outcome
-   optional `Done when`
-   worker chat
-   Shadow supervision
-   intervention
-   task states
-   budgets
-   retry
-   open worker chat
-   autonomy concepts
-   memory concepts
-   Presence concepts
-   Attention concepts
-   watch/task types
-   safety-floor concepts

## Future / vision

-   persistent human proxy at full maturity
-   deeper long-term memory
-   mature behavioral identity
-   broad autonomous authority
-   multi-department orchestration
-   department Shadows
-   agent-to-agent supervision
-   creation of reusable capabilities
-   automatic reuse of capabilities
-   repeated work becoming apps/artifacts
-   ongoing maintenance of created capabilities

The actual codebase should determine which "current" items are truly
implemented versus UI-only or partial.

------------------------------------------------------------------------

# 36. Source Discipline

When updating this document or discussing Shadow, use four labels:

### FACT --- Vision

Directly supported by Sankalp's stated direction.

### FACT --- Current

Observed or verified in the current product/code.

### INFERENCE

Reasonable interpretation, but not explicitly specified.

### PROPOSAL

A new recommendation/design idea.

Also use:

### UNKNOWN

When something requires code inspection, research, or product
clarification.

Never silently convert:

``` text
INFERENCE → FACT
```

or:

``` text
UI concept → implemented behavior
```

------------------------------------------------------------------------

# 37. Shadow-Specific Open Questions

These should be resolved through code inspection, research, and
dogfooding.

## Supervision

1.  Exactly what does Shadow observe?
2.  How frequently does it observe?
3.  What context does it receive?
4.  How does it know what the worker is currently doing?
5.  What makes Shadow decide to intervene?

## Judgment

6.  How does Shadow detect stuckness?
7.  How does it detect over-planning?
8.  How does it detect loops?
9.  How does it detect goal drift?
10. How does it detect misunderstanding?
11. How does it detect premature completion?

## Verification

12. How is `Done when` represented?
13. How is it evaluated?
14. Can Shadow verify completion independently of worker claims?
15. What happens when completion criteria are ambiguous?

## Intervention

16. How are interventions sent?
17. Can Shadow observe the result of its intervention?
18. Does Shadow learn whether an intervention worked?
19. How many interventions are allowed before escalation?

## Escalation

20. What causes `NEEDS YOU`?
21. How is the human request generated?
22. Can Shadow recover from ordinary failures without escalating?

## Autonomy

23. Which autonomy levels are actually enforced?
24. What actions belong to each level?
25. How are safety floors enforced?
26. Can authority vary by task?

## Memory / identity

27. What does Shadow currently remember?
28. What is persistent?
29. How are confirmed instructions stored?
30. How is memory retrieved?
31. How does Shadow maintain behavioral continuity?

## Mission lifecycle

32. What exactly causes READY?
33. What exactly causes PAUSED?
34. What exactly causes FAILED?
35. What exactly causes completion?
36. What happens when the budget is exhausted?
37. What happens after repeated failure?

## Watch / attention

38. How does `watch` work?
39. What does Shadow continuously watch?
40. What qualifies as a meaningful change?
41. How are notifications/nudges controlled?

## Persistence

42. What survives app restart?
43. What survives model changes?
44. What survives mission completion?
45. How are ongoing missions recovered?

## Future orchestration

46. How will Shadow select existing capabilities?
47. How will it decide to create a new capability?
48. How will it coordinate multiple workers?
49. How will department-level Shadow relationships work?

------------------------------------------------------------------------

# 38. Immediate Next Step

**Inspect the actual Shadow implementation before making broad product
changes.**

Use Claude Code in read-only mode to map Shadow end-to-end.

Claude Code should identify:

-   Shadow UI entry points
-   delegation flow
-   mission/task model
-   worker-chat creation
-   worker/Shadow communication
-   observation mechanism
-   intervention mechanism
-   completion logic
-   `Done when`
-   task states
-   budgets
-   autonomy enforcement
-   safety floors
-   memory
-   Presence
-   Attention
-   watch
-   persistence
-   escalation
-   tests

For every area, explicitly classify:

``` text
IMPLEMENTED
PARTIAL
UI-ONLY / MOCK
UNCLEAR
```

Do not refactor during this investigation.

------------------------------------------------------------------------

# 39. Recommended Improvement Process

The Shadow development loop should be:

``` text
1. Understand Sankalp's intent
             ↓
2. Inspect actual implementation
             ↓
3. Dogfood Shadow
             ↓
4. Research relevant external patterns
             ↓
5. Identify the biggest Shadow failure
             ↓
6. Define one improvement
             ↓
7. Implement
             ↓
8. Test
             ↓
9. Dogfood again
             ↓
10. Harden what works
```

Avoid trying to solve every future Shadow problem at once.

------------------------------------------------------------------------

# 40. Tool Roles for Shadow Work

## ChatGPT

Use ChatGPT for:

-   Shadow product reasoning
-   synthesizing context
-   comparing vision vs implementation
-   identifying gaps
-   prioritizing improvements
-   defining experiments
-   turning dogfooding observations into product decisions
-   maintaining this context

## Claude Web

Use Claude Web for:

-   research into supervisory agents
-   worker/critic patterns
-   agent orchestration
-   persistent delegate designs
-   autonomy/safety patterns
-   completion verification
-   known failure modes
-   competitive/prior-art research

Claude Web should **inform** Shadow design, not replace product
judgment.

## Claude Code

Use Claude Code for:

-   reading the real Sutra codebase
-   tracing Shadow implementation
-   making approved changes
-   testing
-   debugging
-   validating behavior

------------------------------------------------------------------------

# 41. The Core Product Question

Everything should ultimately come back to:

> **How do we make the supervisory loop reliable enough that a user
> genuinely prefers delegating work to Shadow rather than directly
> operating the underlying AI?**

The loop to optimize is:

``` text
DELEGATE
   ↓
WORK
   ↓
OBSERVE
   ↓
JUDGE
   ↓
INTERVENE
   ↓
VERIFY
   ↓
FINISH / ESCALATE
```

------------------------------------------------------------------------

# 42. Shadow North Star

> **Shadow should make delegating to Sutra feel less like operating an
> AI system and more like handing a capable delegate a desired outcome
> and trusting it to get the job done.**
