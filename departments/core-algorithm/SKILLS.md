# Core Algorithm — Skills and extension ownership

| Skill / extension type | Contract | Current proof |
|---|---|---|
| Goal semantics and condition derivation | Rule head, alternatives, source, scope, approval, version | Authored JSON refinement |
| Scoped evidence evaluation | `(tenant, domain, predicate, truth, source, version, dependencies)` | Three-valued local evidence; tenant test |
| Recursive Method planning | Preconditions, effects, shared dependencies, complete-plan cost | Deterministic method tree/plan scenarios |
| Provider and policy admission | Finite offers, grants, vector budgets and preference | Synthetic rejection/choice tests |
| Action/receipt boundary | Allowlisted action, independent effect check, immutable event | `LOCAL_MODEL_ONLY` only |
| Adaptation and capability candidates | Missing Method goal, composable candidates, governed registration | Candidate contract, not runnable code synthesis |
| Reflection and structural reuse | Evidence-backed pattern/reuse proposals | `PROPOSED_ONLY` |
| J2 projection | Read-only `atom/1`-shaped plan projection | Not a live J2 adapter |
| Implementation generation | Plan + state to workflow shape (`W-<goal>.json`), atoms, scaffold (done-when lines, go/ask/refuse/always rules, five functions), page | `PROPOSED_ONLY`; deterministic; 3 unit tests + 2 independent checks (0.3.0) |
| Standards as rules | A checklist over a workflow JSON becomes verified evidence rows (an evidence adapter); the standard is an approved rule | Cases 25 to 27 (0.5.0) |
| Action kinds | A registered kind owns an effect and may carry hooks (check, plan, settle); the kernel keeps the gate and the receipt | Constructor and artifact handlers with byte-identical receipts (0.7.0); hooks (0.8.0) |
| Human ask | A step asks a named party and the run waits; waiting is a plan; the stamp is bound to the issued receipt; a decision is final | Case 29 and the `ask_events` record (0.8.0) |
| Recorded stop | A step that cannot run or fails ends the run as an outcome on the record; a stopped step is never paid; what a handler returns is rebuilt as plain data before it becomes a receipt | Case 30 (0.9.0) |
| Additive versions | A version that only adds is a set of new files in seven named places, applied all or nothing. The points claim three things and no more: a delivery edits no existing file unless it is an edit version, which says so in its manifest, is recorded as one with the hashes of what it changed, and is reviewed as every kernel version is; what earlier versions recorded stays byte-identical, pinned by id, except what an edit version declares as moved; every added part is in the record and is checked like the built-in ones. Added code is reviewed code that runs with the lab's rights; the guards stop mistakes and are no sandbox | Add-on points: checks S200 to S204 and `lab/tests/test_added.py` (0.10.0) |
| Evidence conflict (must-cohere) | A verified FALSE row that is no decision, on a goal under a branch that evidence closes, ends the run as `EVIDENCE_CONFLICT`: no plan, no action, no cost (a decision on the goal is a refusal); six stated limits | Case 50 and checks S210, S211 (0.10.0) |

A skill or domain rule is a versioned extension. It cannot change core authorization or proof semantics by changing its own JSON.
