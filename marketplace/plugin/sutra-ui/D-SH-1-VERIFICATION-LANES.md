# D-SH-1 — Shadow settles its own checks

| field | value |
|---|---|
| **status** | IMPLEMENTED — extended by §7 (second pass, same day) |
| **decided** | 2026-09-20, founder |
| **supersedes** | the `FALLBACK_TIER = "founder_confirm"` rule (2026-09-11 / 2026-09-15 / 2026-09-17) |
| **touches** | `shadow_probe.py` · `shadow_judge.py` (new) · `shadow_protocol.py` · `mission_engine.py` · `shadow_runner.py` · `app.py` · `SHADOW.md` · `shadow_evidence.py` (new, §7) |
| **tests** | `test_shadow_verification_lanes.py` (57) · `test_shadow_artifact_evidence.py` (44, §7) |

## 1. The measurement

Across every mission on the founder's install, **9 done-when checks out of 9
were `founder_confirm`**, and every one carried `proposed_tier: None` — Shadow
named no tier at all and the fallback did the rest. Shadow had never once
settled a check by itself.

Three of those nine, verbatim from `m-e34460ddcafa`:

| check | what would actually answer it |
|---|---|
| typing a long message holds focus, no keystrokes dropped | run the shell suite |
| the fix addresses the root cause, not a refocus-on-blur hack | read the diff |
| no other input, panel or behaviour changed as a side effect | run the suite |

None is taste. None is a fact only the founder holds. All three were signed by
hand.

## 2. Why it happened

Not distrust. **Vocabulary.** The only machine lane Shadow had could read one
file. Every question about whether working software works fell off the end of
that vocabulary, and `tier_for` sent anything it could not classify to the
founder.

That default was correct when it was written, because demotion was a **one-way
door**: a check sent to the founder had no way back, and the alternative —
`_shadow_verifier` — is a substring test over the worker's own words, which
let `m-245777cf1467` close a check by writing *"Committed as f96c3ade. The task
reaches DONE."*

## 3. What changed

### Two new lanes

| lane | settles | how |
|---|---|---|
| **command probe** (`command_succeeds`) | "tests pass", "nothing else broke", "it builds" | `argv` list, `shell=False`, floor-screened, confined cwd, bounded clock + output |
| **evidence judge** (`judge` tier) | "root cause, not a workaround", "nothing unrelated touched" | a one-shot process reads `git diff` + probe output and returns met / unmet / **cannot_tell** |

### The inversion

`FALLBACK_TIER` moved from `founder_confirm` to `judge`. The ladder is now:

1. `contains_artifact` + a literal-shaped string → kept
2. `verify` + a valid probe → kept (it was being thrown away; see §5)
3. the check is **taste, or a fact only the founder holds** → the founder
4. everything else → the judge

A bare `founder_confirm` proposal is **not** enough on its own. All 9 live
checks reached the founder exactly that way, so a check routed to a signature
has to look like a founder's question.

### The ask gate

The same sentence, applied mid-mission. `ask_founder` is admitted only for
`floor` / `founder_fact` / `taste`, **and the question is screened against the
label** — writing `ask_kind: "taste"` over "do the tests pass" does not get
through. A refused ask becomes a `continue` telling the worker to go and
establish it. After `ASK_REFUSAL_LIMIT` (2) refusals the next ask is admitted
regardless, so the gate cannot ping-pong a mission to death.

## 4. Why this is safe — `cannot_tell`

**It is no longer a one-way door.** The judge has three verdicts, and the third
returns the row to the founder with its wording untouched. A wrong routing now
costs one model call instead of a check nobody ever answers. That single
property is what makes the aggressive default acceptable.

The other half: **the judge never sees the worker's prose.** `evidence_for`
builds its blob from `git` and from probe results, and has no transcript
parameter to pass one through. Grading a diff you did not write is review;
grading the worker's *account* of the diff would be the `m-245777cf1467`
failure wearing a new label.

## 5. The objections this overrules, and the answers

| objection, as the code stated it | answer |
|---|---|
| *"command execution would hand a model-authored string to a shell; its absence is the point"* (`shadow_probe`) | The delegate already runs anything it likes in that same workdir at the founder's permission mode. The probe adds no capability — it adds a reading of the result the worker cannot author. And it is argv, never a shell string. |
| *"No model is asked whether the work is good — that would make Shadow the grader of its own delegate"* (`app.py`) | The decider and the worker are separate processes with separate context, and the decider has no shell in the repo. It reads the artifact, never the account of it. |
| *"`verify` is deliberately absent: NO production caller passes a verifier"* (`shadow_protocol`) | Stale since 2026-09-17. `app.py` passes `_shadow_verifier` at four call sites and probes settle against the real filesystem. |

## 6. What still reaches the founder

1. **The three floors** — destructive git, external client repos, irreversible
   external sends. Unchanged, still above every autonomy level, and they now
   screen command probes too.
2. **Facts only they hold** — a credential, a budget ceiling, which region.
3. **Taste** — where there is no correct answer, only theirs.

Everything else is Shadow's own work, and it has full access to do it.

## 7. Second pass — the judge could not see the artifact (2026-09-20)

### 7.1 The measurement

The inversion in §3 did not land. The day it shipped, a task asked for "10
lines of MotoGP's latest news" and this check still arrived as a Confirm:

> each line is a real, recent MotoGP news item drawn from current sources
> rather than invented or generic filler, and the file contains only the 10
> items with no headers, numbering or bullets

**The tiering was never the bug.** Measured on the live code:

```
is_founder_only(check)      -> False
tier_for(check, *, *)       -> "judge"     for every proposed tier
```

The failure was one function downstream. `evidence_for` built its blob from
`git status --short`, `git diff` and `git diff --cached`. The artifact was a
NEW, UNTRACKED file, so both diffs were empty and the entire evidence was:

```
FILES TOUCHED (git status --short):
?? motogp-news.txt
```

A filename. The judge answered `cannot_tell` — correctly, on that evidence —
and `_run_judges` re-tiered the row to the founder.

**The general defect**: the judge could only see CHANGES TO TRACKED FILES.
Every authoring, generation, research and report task produced an artifact it
was structurally blind to. MotoGP is one instance, not the problem.

### 7.2 The ladder, made explicit

| layer | answers | mechanism | authority |
|---|---|---|---|
| L1 probe | mechanically decidable | `shadow_probe` kinds, `lines_shape` added | deterministic |
| L2 facts | quantities about the artifact | `shadow_evidence.facts_for`, carried as evidence | deterministic |
| L3 judge | does the artifact support the claim | model over artifact + facts + diff + probe output | review |
| L4 founder | taste, founder-held fact | `is_founder_only` | human |

`cannot_tell` remains the ONLY route from L3 to L4.

### 7.3 What changed

1. **The artifact lane** (`shadow_evidence.py`). The judge is shown the
   CONTENT of files the work produced: paths this mission's own probes name,
   plus untracked paths from `git status`. Modified tracked files are
   excluded — the diff already carries them.
2. **`lines_shape`** — a probe kind for "no headers, numbering or bullets",
   from a FIXED shape table (`blank` / `bullet` / `numbered` / `heading`).
   Never a model-authored regex: nothing in Shadow compiles a pattern a model
   wrote, and a backtracking engine would be a way to hang a turn.
3. **Compound rows carry `probes` (plural)**. A criterion stating four things
   keeps the founder's wording as one row and attaches a probe per decidable
   clause. **Probes are a PRECONDITION, never a substitute**: every probe must
   pass before the row's tier is consulted, so a vague clause is never
   reported as verified because a countable one beside it was.
4. **The prompt** now says difficulty is not the same as needing a human,
   answers compound checks part by part, and prefers the machine-counted
   `measured:` line over its own count.

### 7.4 Why the artifact lane is not the thing the judge must not see

A file the worker wrote is the WORK. A sentence the worker typed about the
file is the ACCOUNT. Reading `motogp-news.txt` is the same act as reading
`git diff`. The transcript stays out, and `evidence_for`'s parameter names are
screened by test so a future source has to be something read from disk rather
than a string handed in.

Two rules close the one new door, and **both** are needed —
`test_9b` caught the gap when only the first existed:

1. an entry that is not a path SHAPE is dropped, via `shadow_probe`'s own
   validator (`..`, `~`, NUL, over-length)
2. a path that names no file is COUNTED, never echoed — a candidate with no
   file behind it is nothing but the caller's string

### 7.5 The boundaries

| limit | value |
|---|---|
| confinement | `shadow_probe.resolve` (realpath, one comparison) |
| selection | probe-named paths + untracked paths; no walk, no glob |
| max files | 8 |
| bytes per file | 32 KiB, head-anchored, announced |
| section total | 48 KiB, inside the 60 KB `EVIDENCE_MAX` |
| stat ceiling | 1 MiB — refused before opening |
| binary | NUL byte → refused |
| long lines | over 2000 chars reported by length, not quoted |
| every refusal | REPORTED, so the judge can answer `cannot_tell` |

### 7.6 What still reaches the founder

Unchanged from §6: the three floors, facts only they hold, and taste. A
mission whose checks are all machine-settled now reaches `done` with no
founder_confirm row, so no Confirm control is rendered — the UI was already
correct (`16-shadow-home.js:755`); only the classification was wrong.
