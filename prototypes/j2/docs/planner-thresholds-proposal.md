# Planner thresholds: a proposal for Rubak

Branch `remove-group-c`, batch 5 (2026-11-14). No code changes. For each fixed number the planner works under, this
says what it does, what the saved runs show, and the options. The founder's rule for the options: no new fixed numbers,
word lists or per-type rules in code. Each number can only become one of three things:

- **a guardrail setting:** in `.env`, with today's value as the default;
- **data the planner sees;**
- **the planner's own decision.**

**Evidence base:** the 43 live `realization.json` files in `runs/` (mock runs left out), 234 judged workflows, and
`memory/lessons.jsonl` and `memory/playbooks.jsonl`. Figures are counted from those files (high confidence). Reasons
given for them are a reading of the runs (moderate confidence).

## Summary

| Number | Today | Recommendation |
|---|---|---|
| `THRESHOLD` | 0.80 gate | Guardrail setting |
| `MAX_ROUNDS` | 3 revision rounds | Guardrail setting as the ceiling; the planner may stop earlier |
| Judge's scoring numbers | Fixed in `j2_realization.py` | Data (one judge file) |
| `MAX_LESSONS` | 5, picked by shared words | Planner picks from an index; size as a guardrail setting |
| `MAX_PLAYBOOKS` | 2, picked by business type and shared words | Same as lessons |

## 1. `THRESHOLD` = 0.80 (`j2_realization.py:25`)

**What it does:** the judge's gate. A workflow scored below it is revised. If it is still below after the last round,
it is `not_ready`: it isn't funded, and everything that depends on it is held. `_register` uses the same gate for late
proposals (`j2.py:8354`, `8489`).

**What the runs show:**
- At the first judgement, a median of 12.5% of a plan's workflows were below the gate.
- 40 times a below-gate workflow was revised; 38 of those reached the gate.
- Only 1 of the 234 workflows ended below it: Sudoku `j2-20261106-184848`, `grid-board`.

**Options:**

| Option | Effect |
|---|---|
| Guardrail setting (`J2_JUDGE_GATE`, default 0.80) | Same behavior, and visible and changeable per deployment. **Recommended.** |
| Data the planner sees | The gate is already stated in the planner's revision task. Moving it into a data file changes nothing the planner can act on. |
| Planner decides | Not advised. The gate is the check on the planner; letting the planner set it removes the check. |

## 2. `MAX_ROUNDS` = 3 (`j2_realization.py:26`)

**What it does:** the most revision rounds after the first judgement. Each round is one Adaptation call to revise and
one judge call, plus a second look for scores near the gate.

**What the runs show:**
- Revision rounds used across the 43 plans: none 15, one 20, two 7, three 1.
- The one plan that used all three is Sudoku `j2-20261106-184848`: 4 judgements, 14 calls, 1,034 s. It ended with
  `grid-board` not ready.
  - `grid-board` scored 0.85, 0.85, 0.85, 0.70. It never rose, and the last round made it worse.
  - Workflows that weren't below the gate moved too: `number-pad` 0.85, 0.60, 0.95, 0.95; `timer` 0.95, 0.95, 0.70,
    0.95; `selection-highlights` 0.95, 0.95, 0.70, 0.95.
  - So the later rounds rewrote parts of the plan they weren't asked about.
- The second round did help elsewhere. Sudoku `j2-20261026-174314`: `build-puzzle-engine` scored 0.70, 0.60, 0.95.

**Options:**

| Option | Effect |
|---|---|
| Guardrail setting (`J2_PLAN_ROUNDS`, default 3) | A cost ceiling that can be changed per deployment. **Recommended as the ceiling.** |
| Planner decides, within the ceiling | Adaptation's revision reply says whether another round can help (for example: the gap is a fact only the Requester has, or the method is settled). Code stops when it says no. **Recommended together with the setting.** This would have saved Sudoku 184848's last round. |
| Data | Nothing in the type data makes a better round count. |

## 3. The judge's scoring numbers (`j2_realization.py:332-366`, `settle` 469-494)

**What they do:**
- Every workflow starts at 0.95 (`BASE`).
- Each failed question takes off its weight: 0.25, 0.15, 0.10, 0.08 or 0.06.
- A weight of 0.25 or more is critical (`CRITICAL`). One critical "no", or 0.15 lost on one check, marks that check
  "no". A "no" caps the score just under the gate (0.79).
- A score within 0.05 of the gate (`BORDER`) gets a second look, and the lower of the two results counts.

**What the runs show:**
- Scores fall on a few fixed steps. Across all judged rounds: 0.95 (319 times), 0.85 (63), 0.89 (43), 0.87 (18),
  0.79 (13, the cap), 0.75 (10), 0.70 (8), 0.54 (3).
- 87 second looks were taken. Each is an extra judge call.
- The numbers are tied to the gate: one critical "no" takes 0.95 to 0.70, under 0.80. Changing a weight, `BASE`,
  `CRITICAL` or the gate alone changes what passes.

**Options:**

| Option | Effect |
|---|---|
| Data | Move the questions, their weights, `BASE`, `CRITICAL`, the 0.15 line and `BORDER` into one judge file next to `agents/j2/confidence-judge.md`, which code reads. Same values, one place, and a change to one is visible next to the others. **Recommended.** |
| Guardrail setting | Only `BORDER` is a cost choice (extra calls), so it could be `J2_JUDGE_SECOND_LOOK`. The weights are not deployment settings. |
| Planner decides | Not advised. The judge's scale is what holds the planner to account. |

## 4. `MAX_LESSONS` = 5 (`j2.py:83`), picked by shared words (`relevant_lessons`, `j2.py:3149`)

**What it does:** Adaptation reads at most 5 lessons from earlier runs. Code picks them by the most shared words of 4
or more letters between the lesson and the current gap (`WORD`).

**What the runs show:**
- `memory/lessons.jsonl` has 14 lessons: 7 website, 6 PRD, 1 HLD.
- Lessons were offered in 30 Adaptation calls across 5 live runs, and Adaptation named the lesson it used in 24 of
  them.
- The cap of 5 rarely bites with 14 lessons. Which 5 are shown is decided by word overlap, which is word matching.

**Options:**

| Option | Effect |
|---|---|
| Planner decides | Adaptation sees an index (lesson id, output type, one-line problem) and asks for the ones it wants; code gives it those in full. No word matching. **Recommended.** |
| Guardrail setting (`J2_MAX_LESSONS`, default 5) | Bounds how many full lessons one prompt carries. **Recommended with the above.** |
| Data | The index itself is the data. |

## 5. `MAX_PLAYBOOKS` = 2 (`j2.py:85`), picked by business type and shared words (`relevant_playbooks`, `j2.py:3133`)

**What it does:** at its first plan for a brief, Adaptation reads at most 2 playbooks from earlier runs of the same
business type, ranked by words shared with the brief.

**What the runs show:**
- `memory/playbooks.jsonl` has 1 playbook, whose business type is "business".
- No live Adaptation call in `runs/` was offered one. The cap has never mattered so far.

**Options:** the same as for lessons. Adaptation sees an index (id, business type, one-line outcome) and picks; the
count becomes a guardrail setting (`J2_MAX_PLAYBOOKS`, default 2). The business type is still compared whole, as the
charter records it (this already holds since the library cleanup).

## Not proposed

- A rule such as "stop when a round brings no gain". It would be a new fixed rule in code; the planner's own stop
  (section 2) covers it.
- Per-type gates or round counts. These would be per-type rules.
