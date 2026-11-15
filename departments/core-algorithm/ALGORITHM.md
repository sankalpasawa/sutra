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
| Ordered effects, data before cuts, tier packs | Order steps by what they require, keep the capture as a goal of its own ahead of the send, stop at a step whose code refuses, turn a proposal's measurements into evidence rows whose version is the verdict, give each tier its own alternative and grants | Run a step before its prerequisite, pay for or continue after a stop, hold back the capture of the latest words because the send cannot run (stated limits: a State captures two messages, and an earlier message that was written and not yet sent is replaced by the next), let an approval stand in for missing data, ship a landed cut again because it was measured again, or let one tier's row or grant alone open another tier's way |
| Queue order, decision rows, style cards | Order the standing goals by declared impact before a look; say each gate line of a trace as a granted, denied or escalated row with the line, the receipt, the stop or the answer behind it; give one goal a card per problem style and one declared question for a problem that fits none | Decide which plan a goal gets or what the gate admits at its turn (the kernel does, on the books the order leaves); print a verdict the books do not explain; work a goal in a style no verified row names |
| Hand-off | Hand the work of a step to a named hand and park the run; take a row of the named checker that names the try's receipt as the check of that try; hand the work over again after a failed check, while that check is the row the fact reads from, telling the next try what the earlier checks found; close with one line that says whether the checker confirmed | Make its effect true, take a stamp, say who may write a row (the journal's event door does), remember a failed check once another row stands on the fact, bound the tries by more than the capacity of the hand's provider and the budget of the plan, ask what a check rests on, end a wait, or tell the checker from the hand beyond a name |
| Reader | Read a kept journal and say what repeated across runs (a step that stopped again at one step for one reason, a chain of steps that ran again, a question answered one way), as proposals that name the journal entries they rest on; word one row for a proposal so that a yes that is a step rests on it; look at a way a person wrote and say why it is not the chain it is said to replace | Change a State, write a pack or a way, set a price or the number of repeats, tell that two steps with ids of their own are the same step done for another thing (so work done once for each of several things gives no proposal of a stop or a chain), hold a hand-in to its look, say which source may state which fact, check an axis after an entry, measure whether two runs gave the same output, see whether a proposal was acted on, or take a way back |

## Four linked interpretations

**World:** observed scoped entities, facts, obligations. **Knowledge:** sourced rules and Methods. **Design:** proposed plans and dependency graphs. **Run:** actually observed effects, checks and receipts. A proposed plan edge is neither causal proof nor permission.

## Honest status

The current `lab/` states its build label and its counts of cases, unit tests and independent checks in [lab/README.md](lab/README.md). It is **not** an independently generalizing agent, full condition theorem prover, autonomous code generator, production J2 adapter, real external action service or Native v1–v5 proof. The original Sutra Core v0.2.2 and separate v0.3.0 candidate remain independent historical tracks.

Read [CHARTER.md](CHARTER.md) for boundaries and [lab/README.md](lab/README.md) for an exact reproducible experiment.
