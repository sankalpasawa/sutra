# System Improvement Protocol

## Overview

> **NOTE:** This protocol references `os/improvements/` and `os/improvements/archive/` directories that do not exist in the Sutra OS template. Client companies using this protocol must create these directories in their repo.

The agent notices things. A protocol that fires repeatedly for the same edge case. A step that takes longer than it should. A class of input with no defined route. This protocol gives the agent a structured way to surface those observations as improvement proposals — without self-modifying the operating system.

The core rule: **the agent proposes, the founder decides, the agent applies**. The agent never edits `CLAUDE.md`, `os/` protocols, or Sutra files without explicit approval.

## When It Runs
- Not scheduled — triggered by agent judgment during any session
- Triggers: process gap detected, repeated friction (same workaround used 2+ times), unhandled input class, ambiguous protocol with no clear answer
- Enforcement: SOFT — agent is encouraged to propose, never required

---

## Phase 1: IDENTIFY — Notice the Gap or Friction

The agent recognizes an improvement opportunity when:

**Gap signals:**
- A task required a workaround because no protocol covered it
- Input routing returned "none" for EXISTING HOME and the agent had to improvise
- The same question was answered inconsistently across two sessions
- A step was skipped because it didn't apply — but the protocol had no skip condition

**Friction signals:**
- The agent loaded 4+ files to answer a question that should require 1
- A protocol step produced output that needed immediate reformatting before it was useful
- A founder correction happened that revealed a systematic misunderstanding
- The same clarifying question was needed before proceeding in multiple sessions

**Not an improvement trigger:**
- One-off edge cases that are unlikely to recur
- Subjective preferences ("I think this could be worded better")
- Changes that would increase system complexity without clear payoff
- Anything the founder already decided against (check FOUNDER-DIRECTIONS.md)

When a trigger is detected, the agent does not fix it immediately. It drafts a proposal.

---

## Phase 2: DRAFT — Write the Proposal

Write the proposal to `os/improvements/YYYY-MM-DD-{topic}.md`.

The topic slug is lowercase-hyphenated, 3-5 words: `2026-04-09-input-routing-ambiguity.md`

**Proposal format:**
```markdown
# Improvement Proposal — {topic}

**Date:** YYYY-MM-DD
**Status:** PENDING

## Trigger
{Specific incident that prompted this proposal. Be concrete — what happened, what session, what input.}

Example: "On 2026-04-09, the founder asked to 'do a quick audit of pricing pages.' Input routing classified this as TYPE: task but there was no existing route for cross-page audits. The agent improvised by running standup audit logic, which was 60% correct but missed the pricing-specific checks."

## Proposed Change
{What should change. Be specific — which file, which section, what addition or edit.}

Example: "Add a cross-page audit route to input routing. When input matches 'audit {page type}' or 'review all {X}', route to AUDIT-PROTOCOL.md (create if needed). Add 'audit' to the keyword list in input-routing classification."

## Expected Impact
{What gets better. Who benefits. How it affects session overhead.}

Example: "Eliminates improvisation for audit requests. Reduces time to correct output from ~10 minutes to ~2 minutes. Affects any session where the founder reviews a class of pages or components."

## Evidence
{Supporting data or observations. Minimum 1 concrete example.}

- Session 2026-04-09: audit improvisation took 12 minutes, produced 60% accurate output
- Similar friction observed in session 2026-03-28 for 'review all API endpoints' request
- No existing protocol covers multi-page or multi-component audits

## Risk
{What could go wrong if this change is applied.}

Example: "Low risk — additive change. Does not modify existing routes. Slight increase in protocol complexity."

## Files to Change
- `os/CLAUDE.md` — add audit to input routing keyword list
- Create `os/protocols/AUDIT-PROTOCOL.md`
```

---

## Phase 3: WAIT — Founder Reviews, Agent Does Not Self-Modify

After writing the proposal to `os/improvements/`:

1. Notify the founder at the end of the current session — one line:
   ```
   IMPROVEMENT PROPOSAL filed: os/improvements/2026-04-09-input-routing-ambiguity.md
   Review when convenient — not urgent.
   ```

2. Do not mention it again in subsequent sessions unless the founder asks about pending proposals or types `/improvements`.

3. The agent does not modify any system files while the proposal is PENDING. Even if the agent is confident the change is correct.

**Why:** Self-modification breaks the founder's mental model of the system. The system should only change when the founder decides it changes. Proposals accumulate in `os/improvements/` as a visible queue.

**Viewing pending proposals:**
- `/improvements` command: list all PENDING proposals with one-line summaries
- `/improvements review`: read each proposal and ask for a decision on each

---

## Phase 4: APPLY — If Approved, Make the Change with Provenance

When the founder approves a proposal:

1. Read the proposal file
2. Make the exact changes described in "Files to Change"
3. Add a provenance comment to any modified protocol file:
   ```
   <!-- Changed 2026-04-09 — see os/improvements/archive/2026-04-09-input-routing-ambiguity.md -->
   ```
4. Move the proposal file to `os/improvements/archive/`
5. Update the proposal's status header to `APPLIED`:
   ```markdown
   **Status:** APPLIED — 2026-04-09
   ```
6. Commit with a message that references the proposal:
   ```
   improve: add audit route to input routing [from proposal 2026-04-09-input-routing-ambiguity]
   ```

**If the founder rejects a proposal:**
1. Append to the bottom of the proposal file:
   ```markdown
   ## Decision
   REJECTED — {reason given by founder}
   Date: YYYY-MM-DD
   ```
2. Move to `os/improvements/archive/`
3. Do not re-propose the same change — respect the decision permanently

---

## Proposal Queue Management

`os/improvements/` is a queue. `os/improvements/archive/` is history.

| State | Location | Status field |
|-------|----------|--------------|
| Waiting for review | `os/improvements/` | PENDING |
| Approved and applied | `os/improvements/archive/` | APPLIED |
| Rejected | `os/improvements/archive/` | REJECTED |

**Queue hygiene:**
- Proposals older than 90 days with no decision: surface in the next `/improvements` review — the founder may have forgotten
- No automatic deletion — rejected proposals are permanent record
- Archive directory is append-only — never delete from archive

---

## Implementation Notes

### What the Agent Can and Cannot Propose
**Can propose changes to:**
- Input routing classification rules
- Protocol steps (adding skip conditions, fixing ambiguities)
- File organization within the company's `os/` directory
- New protocols for unhandled process classes
- Trigger keywords and command aliases

**Cannot propose changes to (or self-modify):**
- `CLAUDE.md` (requires founder decision and explicit instruction)
- Sutra OS source files in `sutra/` (only Sutra team can modify)
- Enforcement boundaries or permission scopes
- Anything in `holding/` (Asawa Inc. jurisdiction, not company jurisdiction)

### Proposal Quality Standards
A good proposal is specific, not vague:

| Weak | Strong |
|------|--------|
| "Input routing could be better" | "Add 'audit' keyword to input routing classification — routes to AUDIT-PROTOCOL.md" |
| "The standup takes too long" | "Phase 2 agents (weekly-only) run even on non-Monday sessions — add day-of-week guard" |
| "This protocol is confusing" | "GOAL-TRACKING.md Phase 3 doesn't specify behavior when goal file has no KR scores yet" |

The agent should file proposals that a founder can approve or reject in under 2 minutes of reading.

### Recommended For
- Tier 2-3 companies (ongoing engagements)
- Companies where the OS is actively used and evolving
- Not required for Tier 1 or short-term projects — overhead exceeds benefit

### Integration with Other Protocols
- **Input routing**: any `EXISTING HOME: none` result that required improvisation is a candidate for a proposal
- **WEEKLY-PLANNING.md**: if pending proposals are in the queue, weekly planning can surface them for batch review
- **NEW-THING-PROTOCOL.md**: if a new thing is encountered repeatedly, the improvement proposal is the follow-up mechanism after the first instance is handled ad hoc

### Skipping Conditions
- Agent does not file a proposal for a one-off incident — pattern must recur or be structurally significant
- Agent does not file a proposal during high-urgency sessions (P0 bugs, live incidents)
- Agent does not file duplicate proposals — check `os/improvements/` before drafting to confirm the gap hasn't already been identified
