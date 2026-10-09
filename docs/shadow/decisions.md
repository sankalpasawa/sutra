# Shadow — Decisions

> Product and engineering decisions made specifically for Shadow.

---

## Status: NO DECISIONS RECORDED YET

This log starts empty on purpose. Nothing is recorded here until a decision is
actually made and can be stated in the decider's own terms.

**Do not backfill this log by inferring decisions from code.** Code shows what
was built, not what was chosen or why — and an inferred decision recorded as a
real one is worse than no record at all. If the reason a thing was built that
way is unknown, that belongs in `current_state.md` under **Open Implementation
Questions**.

### Scope

| In scope | Out of scope |
|----------|--------------|
| Choices specific to Shadow — supervision model, mission states, autonomy floors, escalation rules, worker interface | General Sutra protocol decisions (those live in `RELEASES.md` / `layer2-operating-system/`) |
| Decisions that constrain future implementation | Implementation details with no decision behind them |
| Reversals — record the new decision, mark the old one `Superseded` | Observations from usage (those belong in `experiments.md`) |

### Relationship to the other documents

| Document | Answers |
|----------|---------|
| `shadow_context.md` | What we believe Shadow is supposed to be |
| `current_state.md` | What the code actually does |
| `decisions.md` (this file) | What we have explicitly decided |
| `experiments.md` | What we learned from using Shadow |
| `prompts/` | Reusable instructions for Claude Code |

---

## Decision Log

Newest first. One entry per decision, using this shape:

```markdown
### [YYYY-MM-DD] — [Short decision title]

**Date:** YYYY-MM-DD

**Decision:**
What was decided, stated as a rule someone could follow.

**Why:**
The problem this solves, and the evidence behind it. Link the experiment in
`experiments.md` or the finding in `current_state.md` if one drove this.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| ... | ... |

**Consequences:**
What this now constrains, costs, or forecloses — including the bad parts.

**Status:** Proposed | Accepted | Implemented | Superseded | Reversed
```

### Status values

| Status | Meaning |
|--------|---------|
| `Proposed` | Written down, not yet agreed |
| `Accepted` | Agreed, not yet built |
| `Implemented` | Agreed and reflected in the code — `current_state.md` should show it |
| `Superseded` | Replaced by a later entry; link it |
| `Reversed` | Undone; record why it did not hold |

---

### [2026-10-07] — A task with nothing to do asks to be closed; Shadow still cannot end one

**Date:** 2026-10-07

**Decision:**
When the worker's own output shows the outcome does not apply (no typo to fix,
a bug that does not reproduce, a change already made), Shadow stops driving and
asks with a fourth ask kind, `nothing_to_do`, using a fixed Close / Keep going
form. "Close" ends the task through the founder's own stop and marks it
`end_reason: nothing_to_do` (shown as NOTHING TO DO, not STOPPED). "Keep going"
resumes with what to look for. The decision vocabulary stays
("continue", "ask_founder"): Shadow still cannot end work by itself.

**Why:**
m-62ab83be8a42 ("fix a typo in README.md"): no typo existed, the only check
could never be met, every ask was refused as "an answer on the machine", and
the worker searched the disk for .git folders until stopped.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| A `nothing_to_do` decision that ends the task | Breaks the pinned rule that only the verifier and the founder end work; reversing it is the Shadow owner's call (Sankalp) |
| Let the decider rewrite the check to "no typo, or one corrected" | Shadow editing its own bar after the fact is the false-completion path |
| Rely on the turn budget | 20 wasted turns and a FAILED label for a task that was simply already true |

**Consequences:**
- ASK_KINDS grows to four; the screen admits `nothing_to_do` only with a
  stated finding.
- The founder taps once to close. Open: whether Sankalp wants Shadow to close
  such tasks itself.
- Not done: recording a repo's *location* in memory (the second half of the
  original issue); the worker still has to find "the sutra repo" each time.

**Status:** Implemented

### [2026-10-07] — Shadow learns its own memory and personality, and re-uses them

**Date:** 2026-10-07

**Decision:**
"What Shadow knows" has two sections, filled in by the system rather than
the founder. **Memory** = what is true (identity, people, projects, current
focus, preferences, vocabulary, tools). **Personality** = how Shadow should
act (autonomy, verification, interruptions, persistence, communication,
priorities). Both are re-used in every later Shadow chat, task chat and
decision. The founder may edit them and ideally never needs to.

Rows come from: what the founder says outright (binds at once), the
founder's answers to Shadow's own questions (binds when stated as a standing
rule, otherwise a one-tap suggestion), and Shadow's own reading of a pattern
(always a suggestion). A dropped suggestion is never re-proposed. A full
section refuses instead of evicting. Credentials are refused. Dated facts stop
binding when their date passes and are flagged for the founder.

**Why:**
Founder direction (2026-10-07): "System should fill these but user can edit
them if they want (ideally they won't)", "those things should be re-used by
shadow in later chats, that's the purpose of it", and "the things shadow asks
the user, we should take into account". Before this, both boxes were
founder-typed free text: empty on the founder's own install, with Shadow's
writes silently evicting the oldest line when full.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| Founder-authored boxes only (status quo) | Nobody fills settings up front; both boxes were empty |
| Everything Shadow infers binds at once | A wrong behaviour costs an action nobody asked for; guesses wait for a Keep |
| Inject raw past Q&A into every boot | The MotoGP leak (2026-09-21): one task's details reaching another's brief |
| Personality as settings dials now | Reverses the 2026-09-17 cut from eight sections to two; deferred until a dial maps to an engine knob |

**Consequences:**
- New append-only store `ledger/knows.jsonl` (`shadow_knows.py`).
- `shadow_remember` writes the learned list, no longer the founder's box (the
  boxes stay as "In your own words" and rank first).
- The decider may carry `remember` on any decision; its prompt asks only on
  turns where the founder has just spoken, so every other prompt is unchanged.
- Personality and memory are Shadow's own. Nothing hands them to the worker
  wholesale: the brief writer and the decider pass on only the lines that
  change how THIS work is done (amended 2026-10-07 after testing showed a
  personality line copied into a brief).
- The first message is triaged before anything starts: only work gets a
  worker; questions, things to remember, settings and greetings are
  handled in the chat. The long-lived Now chat re-reads what it knows when
  that changes, instead of only at boot.
- Not yet built: lessons proposed at mission end, wiring personality lines to
  engine settings (autonomy, quiet hours), project-scoped memory, selective
  loading past ~50 lines per section.
- The older `remember` fence (instruction ledger, precedence ranks) still
  exists alongside; consolidating it is open.

**Status:** Implemented


---

### [2026-10-08] — A task that cannot start says why; a quiet worker is flagged before the 4-minute end

**Date:** 2026-10-08

**Decision:**
Two patterns taken from Paperclip (github.com/paperclipai/paperclip), chosen by
the founder from a ranked comparison.

1. **Can't start.** A start that fails before any worker exists is still
   retried three times (10s / 30s / 90s). When every retry has failed, the task
   carries `start_blocked` (a plain reason) and shows CAN'T START under WAITING
   ON YOU, with the reason and one action, Try again. A start that is certain
   to fail (Claude not the AI selected, Claude not on disk, the work folder
   gone) is blocked at once with that reason and spends no retry. The task
   stays `brief_confirm`; the transition table is unchanged.
2. **Quiet worker.** The 4-minute stall end (`STALL_SECS = 240`) is kept as is.
   From 2 minutes of silence *while Shadow waits on the worker's turn*, the
   task says "No new output for N min" and when the step will end. It changes
   nothing and has no control.

**Why:**
m-d98864130150: "Connection lost" during the worker spawn left the task at
READY with a Start button and no reason; the founder had said "Start the task"
should never appear for work Shadow took on. And a worker running one long
command produces no output, so the 4-minute end arrived with no warning.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| Warn at 5/15 min and end only after 30 min of silence (Paperclip's "flag, never kill") | Founder chose to keep the 4-minute end |
| Warn only, never end on silence | Same |
| A new `cant_start` mission state | A fact beside the state (like `start_requested_at`, `pause_reason`) needs no change to the pinned transition table |

**Consequences:**
- A long silent command (tests, an install) still ends its step at 4 minutes;
  the founder now sees it coming. Revisit if that keeps happening.
- Open: whether a CAN'T START task should be retried once automatically after
  an app restart (today it waits for Try again).

**Status:** Implemented

---

### [2026-10-08] — The founder taps answers; Shadow tracks what work costs against a monthly limit

**Date:** 2026-10-08

**Decision:**
Two more patterns from Paperclip, chosen by the founder.

1. **Tap to answer.** The decider is told to send a tap form (`boolean`,
   `choice`, `multi_choice`) whenever the answer is yes/no or one of a few, and
   never to ask the founder to type "yes". A question with ONE pick-one or
   yes/no field is sent on the tap (No still opens "What should I change?").
   A new field type, `verdicts`, lets the founder mark each of several items
   approve / reject / later.
2. **Cost and a monthly spending limit.** Every Claude turn Shadow runs is
   counted from the result's `total_cost_usd` (cumulative per process,
   measured): the worker it made, the task's Shadow chat, one-off
   decide/judge calls, the Now chat. A task shows what it cost; settings take
   a monthly limit (none by default). At 80% the task list says so; at 100%
   new tasks show CAN'T START and running tasks pause before their next step
   (NEEDS YOU, Continue).

**Why:**
Founder: "Do #1 and #4" from the Paperclip comparison. The form system already
existed; what was missing was using it by default and one-tap answers.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| Costs as a ledger kind | Shadow's sessions can append any ledger kind through sutra_mcp; a spend figure Shadow can write to is not a limit. Own file, `costs.jsonl` |
| Pause with a one-use approval (`_hold_say`) | That approves one instruction; a spent limit is not about a specific instruction |
| Count the founder's own chats when Shadow drives them | That spend is the founder's chat, not Shadow's work |

**Consequences:**
- A turn that ends in an error IS counted (the runtime hook sees every
  result); the figure is still "about" -- one-off processes killed before a
  result report nothing.
- "Budget per task" in settings still means TURNS; the new one is named
  "Monthly spending limit" to keep them apart.

**Status:** Implemented

---

### [2026-10-08] — A regression gate for Shadow, run one file at a time against a per-machine baseline

**Date:** 2026-10-08

**Decision:**
`marketplace/plugin/sutra-ui/shadow_regress.py` runs every Shadow test file
(test_shadow*, plus tests that import Shadow's modules or load its screens),
Python and JS, one file at a time, and compares failures with a baseline
recorded on the same machine before the change. Exit 1 on any new failure,
or on any failure in a test file that is new since the baseline.

**Why:**
Founder: "I'm making loads of changes on this shadow feature, we gotta make
sure stuff isn't regressing". CI runs the Shadow JS tests but none of the
Shadow Python tests, and on a given machine some tests fail for reasons that
are not the change (Windows event loops, CRLF checkouts), so a raw failure
count says nothing. A whole-suite run was also killed for memory.

**Consequences:**
- Record before changing: `python shadow_regress.py --record` (or `--root`
  a clean checkout). Check after: `python shadow_regress.py`.
- Open: a CI job for the Shadow Python tests (needs its own Linux baseline).

**Status:** Implemented

---

### [2026-10-08] — Each task works in its own copy of the project; a finished task is added automatically

**Date:** 2026-10-08

**Decision:**
Option B, chosen by the founder ("Let's do B"). When a task's worker starts and
the project is a git repo, `shadow_workspace` snapshots the founder's folder as
it is (`git stash create` for uncommitted edits, plus untracked non-ignored
files) into a git worktree under the shadow home, on branch `shadow/<task>`.
The worker runs there and is told so; the task's checks read there
(`mission["workdir"]`). When the task ends:

| How it ended | What happens |
|---|---|
| Finished (checks passed) | Changes applied to the founder's folder automatically; copy removed |
| Finished, but the same lines changed in the founder's folder | Nothing applied; KEEP? under WAITING ON YOU: Try again / Throw away |
| Stopped or failed with changes | KEEP?: Keep / Throw away |
| No changes | Copy removed silently |

**Why:**
Shadow's main use is improving Sutra itself, so workers were editing the repo
the app runs from: tasks at once collided, a half-done step could break the
running app, work mixed with the founder's uncommitted edits, and checks could
read a different folder from the one the worker wrote to.

**Alternatives considered:**
| Alternative | Why not |
|-------------|---------|
| A. Always ask before adding | Founder chose B: keep today's "it just lands" feel when checks pass |
| Copy from the last commit only | Would miss the founder's uncommitted work, which is most of what is in flight |
| `git apply --3way` into the founder's folder | Stages into the founder's index and can leave conflict markers in their files; all-or-nothing apply is safer |

**Consequences:**
- Measured: making a copy of the Sutra repo took ~100s (18.6k files, while the
  test suite was also running). Every task start is that much slower. A
  ready spare copy would remove it; not built.
- A plain `git apply` fails on CRLF files in the founder's checkout;
  `--ignore-whitespace` is used.
- Off switch: task-limits key `task_copies: false`, or
  `SUTRA_SHADOW_TASK_COPIES=0`. Not a git folder -> shared folder as before.

**Status:** Implemented

---

### [2026-10-09] — "What it made": each task lists its files, each one openable

**Date:** 2026-10-09

**Decision:**
From Paperclip's per-task results tab, chosen by the founder. Each started task
has a "What it made" section; Show loads the list on demand (a copy's list
runs git). The list is never a guess: the files changed in the task's own copy
(before Keep), the files added to the project (after Keep), or -- with no copy
-- the files the task's checks named. Open serves only a listed file, only
inside the task's folder: text (even .html) as plain text, images and PDFs as
themselves, anything else as a download, up to 5 MB.

**Also, same day:** the server now keeps Shadow conversations (the founder's
line with its screenshots, a "still working" mark, and the reply), because a
refresh during a long answer lost the reply; a Shadow conversation uses the
whole pane (an old 280px cap); SHADOW.md no longer tells Shadow the founder
presses Start. 28 files under sutra-ui/static were converted from CRLF to LF
on disk (identical to git's copy) so the source-reading tests pass here.

**Status:** Implemented

---

### [2026-10-09] — A task's own Shadow chat runs on Sonnet and reads a slimmer manual

**Date:** 2026-10-09

**Decision:**
Founder: "yes do A + B" after a 3-line file task cost $0.47. Measured on
m-d0246c95379c: the task's Shadow chat was $0.33 (boot $0.16, brief $0.10,
decide + final $0.07), the worker $0.14; both on the CLI default (Opus).

- **A.** A task's own Shadow chat (start and resume) runs `--model sonnet`
  and `--disable-slash-commands` (`app._task_shadow_args`). The Now chat and
  workers keep their argv. Task-limits key `shadow_model` ("default" = CLI
  default) or `SUTRA_SHADOW_MODEL` overrides.
- **B.** SHADOW.md marks what only the Now chat uses (`<!-- now-only -->`):
  delegation, goals, apps, chips, run limit, presence, restart. A task chat
  boots without it (22% smaller manual). The Now chat reads the file exactly
  as before.

**Measured, and what was NOT done:**
- A bare Claude Code session that only replies "OK" is ~29k tokens of the
  CLI's own instructions and tools; that base dominates every Shadow turn.
  The skills catalog was ~900 of it. `--bare` would cut more but fails to
  sign in on a subscription.
- Shadow also runs at `--effort xhigh`; left as is (a quality setting).
- Removing built-in tools from the task chat (`--tools ""`, as the retired
  decider lane did: 94% of its tokens were scaffolding) would be the next big
  saving; not done -- it changes what the task chat can do.

**Status:** Implemented; to be measured on the same task.
