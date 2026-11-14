# Sutra — Stable Recursive Kernel and Extensions

**Proposal + finite executable reference**, not a ratified production replacement. Public department-facing specification, 8 Nov 2026.

## The stable question

> What should be true, what is adequately evidenced, what is missing, what authorized Method could close the gap, and did the effect actually occur?

The target model is `Resolve(G, K, S, M, P)`:

- **G**: scoped goals and continuing obligations.
- **K**: applicable accepted domain knowledge, definitions, consequences and rule versions.
- **S**: observed facts with TRUE/FALSE/UNKNOWN, provenance, scope and dependencies.
- **M**: Method effects, prerequisites, interfaces, providers and independent checks.
- **P**: policies, authority grants, nonfungible resources, preferences and limits.

The computation is recursive but *bounded*. A new business requirement should normally change an approved rule, Method or policy pack, **not** this operation. Additional trusted primitives are still possible but require versioned changes and counterexamples.

## Core loop (semantic contract)

1. **Scope and observe.** Match the goal and evidence by tenant, domain, version and validity. Do not confuse execution status with world truth.
2. **Refine the meaning.** Unify the goal with approved rule heads. Each rule yields alternative sufficient AND-condition sets (OR between sets). No approved meaning => explicit missing-semantics outcome.
3. **Identify needs.** A need is a required scoped condition that is not currently evidenced TRUE. UNKNOWN yields an information/evidence need; verified FALSE may require a repair or different path. A new event matters only if it affects a standing goal through relevant dependencies.
4. **Find/construct methods.** Match existing effects to unmet conditions and recursively resolve *method-specific* prerequisites. Where no Method exists, return a missing-capability need; an authorized constructor may produce a candidate with tests, never an approved capability by assertion.
5. **Compare complete plans.** Consider alternative prerequisite trees, share common subgoals safely, detect cycles, and sum resource vectors componentwise. Retain Pareto-feasible plans and apply an authorized preference; do not invent exchange rates between money, compute and attention.
6. **Admit and execute.** Recheck provider offers, scope, grants, resources, readiness and idempotency before every real effect. The current reference supports only allowlisted synthetic local actions.
7. **Independently verify and record.** Accept only independently checked results as achieved; record source versions, decisions, results, event hashes and resource ledgers. Invalidate dependent claims selectively when inputs change.
8. **Reflect and evolve under governance.** Record candidate reuses/structural patterns after terminal attempts. Treat improvement as another bounded goal, but do not let the candidate promote its own source, authority or verifier. Since 0.4.0-shrink this step is an extension over the run record (`lab/extensions/reflection.py`, `Learner`), not a branch of the kernel.

This sequence is a conceptual contract, not proof that all stages are implemented in the current finite lab.

## Minimal pseudocode

```text
RESOLVE(goal, knowledge, evidence, methods, policy, limits):
  if adequately_verified(goal, evidence): return SATISFIED
  branches = derive_from_approved_rules(goal, knowledge)
  if no branches: return SEMANTICS_MISSING
  for branch in branches:
    recursively find/compose eligible methods for unmet conditions
    assess alternatives, shared prerequisites, budgets and authority
  if no eligible plan: return specific WAIT / QUERY / METHOD_ABSENT / BLOCKED
  choose a permitted Pareto-efficient full plan
  dispatch admitted effects only through trusted provider boundary
  independently check effects, update evidence and immutable run
  optionally PROPOSE bounded improvements; never self-promote
  return rechecked goal status and replayable receipts
```

## Why needs can arise without a new human request

Suppose a standing goal is `order_fulfilled(order_7)`. An approved rule provides two alternatives: ship original **OR** ship replacement with applicable approval. A stock-change event invalidates the original path. If replacement customer approval is UNKNOWN, the solver derives an evidence-query need. If reviewed policy adds notification, the planned replacement path gains a notification step. Without the rule, the solver must report missing semantics—it cannot invent business truth from a blank slate.

## Extension slots

| Extension | Can change | Cannot change |
|---|---|---|
| Domain pack | Meaning, AND/OR branches, applicability, source | Automatically become approved legal/business truth |
| Method pack | Candidate effect, preconditions, tools, tests | Grant itself external effects |
| Evidence adapter | New observations and provenance | Treat a failed check as external FALSE |
| Planner preference | Choose among authorized non-dominated plans | Bypass hard resource ceilings |
| Provider adapter | Offer actual capabilities with finite commitments | Assert effect success without separate evidence |
| Learning/formation | Propose reusable Methods, rules or patterns | Promote its own rules, verifier or kernel |
| J2 adapter | Map proposed plan to J2 atom/map contracts | Claim a projection is executed J2 work |
| Implementation generator | Turn a plan into a runnable workflow shape (sutra-native user-kit), atoms, a department scaffold and a page | Execute anything, register itself, or mark a step done |
| Action kind | Perform the effect of a registered kind, check its methods at load, say when its effect is pending, keep its own books after a run | Skip the gate, set the receipt's own fields, or touch grants, budget, providers, rules or methods |
| Ask and stamp | Park a run on a question to a named party; write the answer as a decision | Answer for someone else, reopen a decision with an ordinary row, or count as external proof |
| Recorded stop | End a run at the step that cannot run or fails, saying what ran, what it cost, where it stopped and why | Roll back what a handler already wrote, try the step again by itself, or count a stopped step as paid |
| Added as files | Bring a version's packs, cases, recorded sequences, action kinds, extensions, tests and checks as new files in seven named places | Edit an existing file, unless it is an edit version, which says so in its manifest, is recorded as one with the hashes of what it changed, and is reviewed as every kernel version is; or move what an earlier version recorded, unless an edit version declares the move with its reason (pinned by id in `lab/added.json`; two kinds of lens are about the whole lab and are the exceptions: the reflection summary is over all cases, and the three implementation lenses name every action kind, so they move when a version declares one). Added code is reviewed code that runs with the lab's rights: the build refuses an honest author's mistakes (an earlier pack authored again, a method id or an action kind given a second meaning) and is no sandbox against code written to deceive |
| Journal | Keep what was handed in, asked, decided and ran as hashed entries, and rebuild the State by replaying them through the kernel's own doors | Be believed without replay, take entries from two writers at one keeper or after it was continued, go on under a kernel whose results differ, or be used with a kind that acts outside the model (replay runs every handler again) |
| Numbers adapter | Write a number as a verified row and a comparison as a row with its own source, version and dependencies; take a new reading whole or not at all; state what each step cost from the gate's own row | Make the kernel read a number, let a comparison outlive its number, or state a cost the gate did not charge |
| Clock adapter | State the moment and the windows at a tick, in as many packs as the rows need; close a window for good; take a time-boxed grant away; set an allowance at a new period; report which standing goals are overdue | Give a grant, state another source's row again, move time back, reopen a closed window, or put a word of time into the kernel |
| Page builder | Turn a goal in a person's words into a department folder with one page, from one reviewed domain of a closed catalogue | Guess what a domain means, choose on a tie, approve a draft, call a plan ready or waiting before its whole path ran in the local model as the plan it shows, name another reason for a stop than the kernel's own, or run anything outside it |
| Refusals and standing rules | Put a requested action in classes by its words and refuse a class by one decision; carry a team's always, ask and never lines as a held grant, a question and a decision; name what a child pack would relax and rest a pack's install on the review of exactly that pack | Read what a script or a binary does, let an ordinary row, a rule, a method, a grant or a budget reopen a refused class in its scope (a pack that names another scope leaves the decision behind), or make the kernel itself turn a relaxing pack away |

## Four linked interpretations

**World:** observed scoped entities, facts, obligations. **Knowledge:** sourced rules and Methods. **Design:** proposed plans and dependency graphs. **Run:** actually observed effects, checks and receipts. A proposed plan edge is neither causal proof nor permission.

## Honest status

The current `lab/` states its build label and its counts of cases, unit tests and independent checks in [lab/README.md](lab/README.md). It is **not** an independently generalizing agent, full condition theorem prover, autonomous code generator, production J2 adapter, real external action service or Native v1–v5 proof. The original Sutra Core v0.2.2 and separate v0.3.0 candidate remain independent historical tracks.

Read [CHARTER.md](CHARTER.md) for boundaries and [lab/README.md](lab/README.md) for an exact reproducible experiment.
