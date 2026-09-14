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

_No entries yet._
