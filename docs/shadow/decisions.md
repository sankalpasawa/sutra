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

