---
issue: 21
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T07:48:52Z
updated: 2026-04-28T07:48:52Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/21
comments: []
---

# #21 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T07:48:52Z  |  **Updated:** 2026-04-28T07:48:52Z
**URL:** https://github.com/sankalpasawa/sutra/issues/21

---

Feature: Cognitive Checkpoints — force users to think at key decision points, not just at the end

## The Problem

The core failure mode is not bad AI output. It is premature delegation — users hand off an underspecified task, AI makes 20 silent assumptions, runs for 5 minutes, returns something that technically answers the prompt but misses the intent. The user redoes it.

The fix is not better AI. It is better human engagement at the right moments.

User's words: 'AI is thinking on behalf of user and taking too much time — sometimes sutra provides output which is not desirable. A checkpoint which forces users to think — either to confirm if sutra is going in the right direction if the token exceeds a certain threshold, then give choice to users what direction to go in — inculcate the user to really think about the task so that the result is satisfactory.'

---

## Feature Suite

### 1. Intent Lock — Before Execution (P0)
Before any DEPTH 3+ task, Sutra surfaces its interpretation and asks for a lock:

  You asked: 'refactor the auth module'
  I am interpreting this as:
  A) Clean up code structure, keep all current behavior
  B) Simplify + consolidate, some interface changes OK
  C) Full rewrite, backwards compatibility not required
  Which best matches your intent? [A / B / C / describe]

5 seconds of user attention now prevents 30 minutes of wrong output.

---

### 2. Option Fork — A vs B at Decision Points (P0)
When execution hits a genuine branch:

  I can handle error logging two ways:
  A) Centralize into one logging service — cleaner, requires new abstraction
  B) Keep inline per module — no new files, some repetition
  Your call: [A] [B] [explain more]

---

### 3. Confidence Budget Model with Auto-Trigger (P0)
Each autonomous decision costs confidence points. Checkpoint fires when budget runs low.
  Read a file = 0 pts
  Edit a known file per explicit instruction = 1 pt
  Choose between 2 valid implementations = 4 pts
  Interpret ambiguous user intent = 6 pts
  Create a new file not mentioned = 7 pts
  Delete or restructure = 9 pts
  Budget per task = 20 pts (configurable). Checkpoint fires when remaining budget < 5.
  Sutra never burns a full budget on silent assumptions — it checkpoints before the mistake.

---

### 4. Trigger System — Smart, Not Constant (P0)
Triggers (not on every turn — avoids fatigue):
  Token threshold: >15k tokens consumed
  Tool call count: >12 tool calls
  Ambiguity score: >2 valid interpretations detected
  Depth minimum: DEPTH 4+ tasks always get a checkpoint
  Branching point: 2+ materially different paths ahead
  Time elapsed: >4 min of execution (user has mentally disconnected)

---

### 5. Midpoint Review with Good Enough / Finish Choice (P1)
At 50% completion:
  Done: auth service split (4 files changed)
  Remaining: token refresh logic, session cleanup
  Result quality if I stop here: USABLE BUT INCOMPLETE
  Estimated remaining: ~8 min, ~12k tokens
  [FINISH IT] [CHANGE DIRECTION] [STOP HERE — GOOD ENOUGH]

---

### 6. Assumption Surface — Checkbox List (P1)
  Before I proceed, I am assuming:
  1. You want TypeScript not JavaScript     [confirm / correct]
  2. Tests should be updated to match      [confirm / correct]
  3. Existing API surface stays the same   [confirm / correct]

---

### 7. Rework Cost Display at Every Checkpoint (P1)
  If this direction is wrong:
    Rework time: ~25 min
    Token waste: ~/bin/zsh.18
    Files affected: 14
  5 seconds now saves all of that.

This reframes the checkpoint as high-ROI, not an interruption.

---

### 8. Progressive Commitment Arc for Long Tasks (P2)
Every DEPTH 4+ task:
[Intent Lock] → [Execute 25%] → [Assumption Check] → [Execute 50%]
  → [Midpoint Review] → [Execute 75%] → [Final Preview] → [Commit]
User is engaged 4x. Each engagement is under 10 seconds.

---

### 9. Configuration (P2)
  sutra.checkpoint.enabled: true
  sutra.checkpoint.token_threshold: 15000
  sutra.checkpoint.tool_call_threshold: 12
  sutra.checkpoint.depth_minimum: 3
  sutra.checkpoint.confidence_budget: 20
  sutra.checkpoint.style: compact | full | silent
Power users can set style:silent — but they see token waste stat at session end.

---

### 10. Engagement Score (P3)
  You co-piloted 4 of 5 checkpoints this session — result quality: HIGH
Shows users that engagement correlates with output satisfaction.

---

## Priority Stack
P0: Intent Lock, Option Fork (A vs B), Confidence Budget model, Smart triggers
P1: Midpoint review, Assumption surface, Rework cost display
P2: Progressive commitment arc, Configurable thresholds
P3: Engagement score

## Design Principle
Never ask for an essay. Present concrete options. Show cost of getting it wrong. Make engagement feel like a pit stop, not a roadblock.
