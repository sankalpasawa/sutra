# Sutra — Readability Standard

**Classification**: Tier 1 Immutable Invariant (Sealed Directive)
**Enforcement**: HARD — all agent output must conform regardless of company, session, or context
**Formal property**: Safety property (Lamport) — "the founder never receives unreadable output"
**Authority**: D6 (Clarity), D13 (Human Readability), D14 (HTML for Executive Docs), D34 (Technical Rigor), P11 (Human Confidence Through Clarity)

---

## 1. Output Format Taxonomy

Every agent output conforms to one of the following format types. No freeform prose responses for operational output.

| Output Type | Format | Max Length | Structure | Reference |
|---|---|---|---|---|
| Status update | Status board: code block, icons, hierarchy | 15 lines | Outputs first (what shipped), then inputs (what's next), then blockers | P11, D13 |
| Estimation | Table: dimension, estimate, actual, accuracy | 1 row per dimension | Numbers only — no prose qualifiers | D23 |
| Decision request | `AskUserQuestion` with enumerated options | 4 options max | Recommendation first, then alternatives ranked by impact | D19, D29 |
| Progress report | Completion table + blocker list | 20 lines | `% complete` per item, not narrative | D17 |
| Architecture doc | Technical spec: pattern names, formal references, invariant definitions | No limit | Proper terminology per D34 — formal methods, design patterns, doctrine references | D34 |
| Executive doc | HTML: stats, badges, cards, visual dashboard | N/A | Browser-renderable, `open` after creation | D14 |
| Error / violation | Alert block: what broke → why → action required | 5 lines | Action-oriented — the fix, not the history | D2 |
| Diff summary | Changed-file list + 1-line per change | 10 lines | File path + what changed — no restating code | D13 |
| Session handoff | YAML checkpoint per Part 6 of HUMAN-AI-INTERACTION.md | Structured | `work_completed`, `open_threads`, `files_modified` | P11 |

### Format Selection Rule

```
OUTPUT TYPE             → FORMAT
operational status      → status board
any comparison          → table
any enumeration         → table
≥3 items                → table or bulleted list
architecture/design     → technical spec with pattern names
executive/strategy      → HTML document
asking founder to choose → AskUserQuestion
```

---

## 2. Signal-to-Noise Ratio Rules

### The Three-Signal Constraint (D13)

Every interaction surfaces at most three signals:

| Signal | Content | Example |
|--------|---------|---------|
| **Shipped** | What's done since last interaction | "DayFlow auth deployed" |
| **Next** | What happens next (1 item, not a roadmap) | "Maze content pipeline" |
| **Broken** | Active blockers or violations | "PPR deploy failing — DNS" |

If nothing is broken, omit the third signal. Do not pad.

### Prohibited Patterns

| Pattern | Violation | Rule |
|---------|-----------|------|
| Process narration | "I'm going to read the file and then..." | Never narrate tool use. Execute silently, report results. |
| Trailing summaries | "In summary, we updated X, Y, Z..." | The output IS the summary. No meta-summary. |
| Adjectives as data | "significant improvement", "moderate cost" | Replace with numbers: "42K tokens", "$0.03", "3.2s → 1.1s" |
| Restating the request | "You asked me to build X. Here's X." | Skip the echo. Deliver the artifact. |
| Hedge phrases | "I think", "it seems like", "probably" | State the fact or state the uncertainty with a confidence level (e.g., "~80% confidence"). |
| Protocol ID soup | "Per D23 and P11 combined with PROTO-004..." | Use plain language. Reference IDs only in specs and audits. |
| Exhaustive lists | Listing everything that works | Flag what's broken. The founder assumes working = fine. |

### Quantification Standard

| Instead of | Write |
|---|---|
| "large file" | "2,400 lines" |
| "took a while" | "47 seconds" |
| "several changes" | "4 files changed" |
| "improved performance" | "latency 3.2s → 1.1s (−66%)" |
| "moderate token usage" | "42K tokens ($0.03)" |
| "most tests passing" | "47/52 tests passing (90%)" |

---

## 3. Visual Hierarchy Specification

### Status Board Format

```
┌─────────────────────────────────┐
│  COMPANY NAME — Status Board    │
├─────────────────────────────────┤
│  ✅ Feature X shipped (v1.2.1)  │
│  ⏳ Feature Y — 70% complete    │
│  🔲 Feature Z — not started     │
│  ⚠️  Deploy blocked — DNS issue  │
└─────────────────────────────────┘
```

### Icon Set (Canonical)

| Icon | Meaning | Usage |
|------|---------|-------|
| ✅ | Done / shipped / passing | Completed items |
| 🔲 | Todo / not started | Queued items |
| ⏳ | In progress | Active work |
| ⚠️ | Warning / blocker / risk | Needs attention |
| 🔺 | Output / result / metric | Shipped outcomes (status boards: outputs-first ordering) |
| ❌ | Failed / error / violation | Broken state |

No other icons. Unauthorized icons introduce ambiguity. This is a **closed set**.

### Structural Elements

| Element | When to use | Specification |
|---------|-------------|---------------|
| Unicode box-drawing (`┌─┐│└─┘`) | Status boards, dashboards | Monospace code block required |
| Tree characters (`├── └──`) | Hierarchy, file structures, inheritance chains | Monospace code block required |
| Markdown tables | Comparisons, enumerations, taxonomies | Header row + alignment row required |
| Code blocks | Architecture diagrams, config examples, structured data | Language tag where applicable |
| Horizontal rule (`---`) | Section separation in specs | Between major sections only |
| Bold | Key terms, column headers | Sparingly — if everything is bold, nothing is |
| Inline code | File paths, command names, config keys | For anything the user would type or reference literally |

### Ordering Rule: Outputs Before Inputs

Every status output follows **output-first ordering** (D17):

```
WRONG                          RIGHT
─────                          ─────
1. What we did                 1. What improved (outcome)
2. What happened               2. What shipped (artifact)
3. What it means               3. What's next (1 item)
```

---

## 4. Tier 1 Classification Rationale

### Blast Radius Test (FMEA)

**Who gets hurt if readability is overridden?**
The founder. Inconsistent output across companies degrades confidence. Confidence is the primary interface between the human and the system. Loss of confidence = loss of system trust = system failure.

This is not a workflow preference (Tier 3). It is a **safety property**: the founder must always be able to parse system output in under 10 seconds. Violation introduces systemic risk to the entire human-AI interaction model.

### Reversibility Test (Amazon)

**One-way door.** Once a founder loses confidence in system output, rebuilding trust is asymmetric — far more expensive than maintaining it. This is not easily reversible.

### Invariant Statement

```
∀ output ∈ AgentOutput:
  conforms_to(output, READABILITY_STANDARD) = TRUE
```

No company, no agent, no session overrides this standard. Only the founder (CEO of Asawa) can modify it via constitutional amendment to this document with cascade impact assessment.

### Enforcement

| Mechanism | Type | Behavior |
|-----------|------|----------|
| Session-start loading | Structural | This file is read at every session start as part of Defaults Architecture |
| Output validation sensor | Soft gate | Post-output check: does this conform to the taxonomy? |
| Principle regression test (D27) | Sensor | Session-end audit: were any anti-patterns produced? |
| Founder feedback | Override | If the founder flags unreadable output, that is an immediate P8 (fix the process) trigger |

---

## 5. Anti-Patterns

### Anti-Pattern Catalog

| ID | Anti-Pattern | Example | Violation | Correct Form |
|---|---|---|---|---|
| AP-1 | Wall of prose | Three paragraphs explaining what was deployed | Signal-to-noise, 3-signal constraint | Status board with ✅ line items |
| AP-2 | Process narration | "Let me read SYSTEM-MAP.md to understand the architecture..." | Prohibited pattern: narrating tool use | *(silence)* → then deliver the result |
| AP-3 | Echo request | "You asked me to deploy the site. I've deployed the site." | Prohibited pattern: restating the request | "✅ Site deployed — https://example.com" |
| AP-4 | Adjective metrics | "The build was significantly faster" | Quantification standard | "Build time 47s → 12s (−74%)" |
| AP-5 | Unbounded list | 15-item status update with every file touched | Max length violation (status: 15 lines) | Top 3 changes + "4 other files updated" |
| AP-6 | Trailing summary | "In summary, this session we accomplished X, Y, Z, and set up A, B, C" | Prohibited pattern: trailing summary | The status board IS the summary |
| AP-7 | Inconsistent icons | Using 🟢 🔴 🟡 🔵 in one session, ✅ ❌ ⏳ in another | Closed icon set violation | Use canonical icon set only |
| AP-8 | Narrative progress | "We're making good progress on the auth system" | Progress report format violation | "Auth system: 3/5 endpoints complete (60%)" |
| AP-9 | Hedge without confidence | "This might take a while and could be complex" | Hedge phrase + adjective-as-data | "Estimated 45min, complexity: 3 files, 1 migration" |
| AP-10 | Inputs-first ordering | "We ran 3 experiments, tried 2 approaches, and landed on X" | Outputs-before-inputs violation | "X shipped. Evaluated 3 approaches, selected for latency." |

---

## 6. Terminal Output Style Guide

Research basis: `holding/research/TERMINAL-READABILITY-RESEARCH.md` (2026-04-06)

### Five Rules

1. **Headline first.** Every output starts with a one-line summary that answers "what do I need to know?"
2. **Structure over style.** Section dividers (`──`), tables, and whitespace create scanability. No heavy borders for data.
3. **Decisions in boxes.** The `╭╮╰╯` rounded box is RESERVED for decisions. Nothing else gets boxed.
4. **Numbers with bars.** OKR scores, completion percentages, and trends get inline visual indicators (`▓░`, sparklines).
5. **25-line budget.** Daily Pulse = 25 lines. Roadmap Meeting = 50 lines per section. OKR summary = 15 lines. If it doesn't fit, use progressive disclosure (headline level only, detail on request).

### Unicode Character Set (Canonical)

| Category | Characters | Usage |
|----------|-----------|-------|
| Document frame | `══` (double line) | Top and bottom of major outputs (Pulse, Meeting, OKR Review) |
| Section divider | `──` (single line) | Between sections within an output |
| Decision box | `╭ ╮ ╰ ╯ │` (rounded corners) | Decision panels ONLY — nothing else gets boxed |
| Tree / hierarchy | `├── └── │` | File trees, org charts |
| Progress bar | `▓░` | OKR scores, completion percentage (10-char bar, each char = 0.1) |
| Sparkline | `▁▂▃▄▅▆▇█` | Trends (TODO count, accuracy, velocity) |

### OKR Score Format

```
Name         ▓▓▓▓▓▓░░░░ 0.6  STATUS
```

- 10-character bar: each `▓` = 0.1 score, remainder `░`
- Score `0.7` renders as `▓▓▓▓▓▓▓░░░` (on target)
- Score `0.3` renders as `▓▓▓░░░░░░░` (behind)
- Charter name + aggregate score + visual bar on ONE line
- KR table immediately below with individual scores

### Decision Box Format

```
  ╭─────────────────────────────────────╮
  │  DECISION: {title}                  │
  │                                     │
  │  Recommendation: {option}           │
  │  Reason: {one sentence}             │
  │                                     │
  │  [1] Option A (recommended)         │
  │  [2] Option B                       │
  │  [3] Option C                       │
  ╰─────────────────────────────────────╯
```

Rules:
- Recommendation is ALWAYS first
- Maximum 4 options
- Reason is one sentence, not a paragraph
- Box width: 40 characters (fits any terminal)
- If multiple decisions, each gets its own box with a blank line between

### Line Budgets

| Output Type | Max Lines | Notes |
|-------------|-----------|-------|
| Daily Pulse | 25 | One screen, no scroll |
| OKR Summary | 15 | Per-charter: headline + KR table |
| Roadmap Meeting | 50 per section | Headline + portfolio + shipped + next + decisions |

### Color Rules

- Green = success/shipped/healthy, Red = blocked/failed, Yellow = warning/in-progress
- Color is semantic ONLY — never decorative
- All output MUST be fully readable with no color (monochrome-safe required)
- Never use blue, cyan, magenta for semantic meaning (poor contrast)
- Never use background colors (unpredictable across terminal themes)
- Color applies ONLY to status words (GREEN/YELLOW/RED) and icons — never body text

---

## Evolution

This document is versioned with Sutra releases. Changes require:
1. CEO of Asawa approval (Tier 1 — constitutional amendment)
2. Cascade impact assessment across all companies
3. Version bump in RELEASES.md

*Standard pattern: Tier 1 Immutable Invariant — Readability as Safety Property*
*Influences: Signal Detection Theory (Tanner & Swets), Information Hierarchy (Tufte), Safety Properties (Lamport), FMEA Blast Radius (NASA), Output-First Reporting (D17)*
