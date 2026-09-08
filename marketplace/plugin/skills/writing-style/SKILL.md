---
name: writing-style
description: >
  The single home for how Sutra writes: MINIMIZE first, then STRUCTURE, COMPRESS,
  CANDOR, GROUND, and the .md FILE-SHAPE rules. Default-on every turn and on any .md
  authored or materially edited. Also fires on: caveman mode, talk like caveman, use
  caveman, less tokens, be brief, token efficiency, anti-glaze, readability, create a
  doc, normal mode, stop caveman, stop anti-glaze, or /writing-style. Replaces the
  caveman, anti-glaze-tone, readability-gate and writing-llm-md skills.
---

# writing-style

Decide what to say, then how to say it, for every surface Sutra writes to.

- **title**: Sutra writing style, single home
- **status**: v1.0 · L0 fleet (D38) · HARD Stop gate `writing-style-gate.sh`
- **scope**: every Asawa, Sutra and plugin-fleet output; customer-facing copy exempt from P2/P3 (Founding Doctrine P0)
- **owner**: Sutra Core
- **updated**: 2026-09-08
- **source inputs**: caveman, anti-glaze-tone, readability-gate, writing-llm-md skills; READABILITY-STANDARD.md; D51, D55, D58, D71; founder 2026-08-17 "too much text"; founder 2026-09-02 "add minimize, one place, followed very strictly"

## 1. Principles <a id="principles"></a>

| Id | Principle | Rule |
|---|---|---|
| P0 | MINIMIZE | Say only what changes what the reader does next. Budgets in §5, rules in §3. |
| P1 | STRUCTURE | Pick the shape before writing: table for 3+ comparable items, numbers not adjectives, one ASCII decision box, Impact + Effort on task tables. |
| P2 | COMPRESS | Of what survives P0: drop articles, filler, pleasantries, hedges; short synonyms; fragments fine in internal register; technical terms and canonical names exact. |
| P3 | CANDOR | Verify, never fabricate, say unknown. Founder wrong: say so now. Counter first, after the outcome line. No capitulation without new evidence. Never apologize. Own numbers first, then the delta. |
| P4 | GROUND | Every actionable claim carries a file:line ref, a typed label (Decision / Assumption / Inference / Open question), or `Confidence: high|moderate|low|unknown`. Model-side; no hook checks presence. |
| P5 | FILE-SHAPE | Every .md follows R1-R12 and C1-C4 (§7). |

Precedence: (1) customer-facing surfaces obey Founding Doctrine P0 first; (2) governance blocks keep their schema, field content one line; (3) MINIMIZE decides what stays; (4) STRUCTURE shapes it; (5) COMPRESS shortens it; (6) CANDOR sets the register. A compressed sentence that should not exist is still a violation. Prose order: outcome line, strongest counter, support. Rules apply at authoring time (D55), not as an output afterthought.

## 2. Scope by surface <a id="scope"></a>

| Surface | ON | OFF |
|---|---|---|
| Chat, founder-facing | P0-P5 | none |
| .md file | P0-P5 | none |
| Customer-facing copy: PRDs, client artifacts, plugin distribution copy, regulated text | P0, P1, P4 | P2, P3; disclaimers stay |
| Commit message, PR description | P1 | P2 |
| Code fence, quoted error, tool or log output, user quotes | none, verbatim | P0-P5 |
| Governance blocks: H-Sutra header, Input Routing, FLOW, Depth, TRIAGE/ESTIMATE/ACTUAL, BLUEPRINT, DISPATCH, PLACEMENT, Build-Layer, OS trace | schema fixed, fields one line | P2 |

Chat uses plain language; governance ids (D-nn, PROTO-nnn, ADR-nnn) appear only in specs, audits and governance blocks. File paths in inline code are refs and always allowed. HTML only when asked. Mid-turn progress lines are allowed but status-shaped (`tests: running, ~90 s`), never first-person intent.

Customer copy authored in chat goes into a file or a fence; file contents are never judged. Otherwise the gate downgrades P2/P3 checks to advisory for the turn when the last user message names customer copy (PRD, client, customer, email, support, regulated) or when `AUDIENCE=customer` is written to `.claude/sessions/<sid>/writing-style-audience` before authoring. Both paths are logged.

## 3. P0 MINIMIZE <a id="minimize"></a>

MINIMIZE chooses WHAT to say: a unit (sentence, row, section, example, block field) stays only if deleting it changes what the reader does, decides, or believes next. COMPRESS chooses HOW to say what survives. Test: remove the unit, re-read; if the next action is unchanged, the unit fails.

| Id | Rule | Gate |
|---|---|---|
| M1 | Outcome first: the first prose line after the governance blocks states the result, decision or answer; at most 5 prose lines before the first table, heading, box or fence. | WS-A2 advisory; narration and echo openers HARD (§4) |
| M2 | One screen: prose lines (fences, inline code, blockquotes, governance blocks excluded; table rows count) 40 or fewer; 41-60 logged; over 60 blocked. Overflow goes to a file or `Top 3 + N other (path)`. | WS-3 HARD, WS-A1 advisory |
| M3 | No echo, no narration, no trailing summary, no filler closer. The turn ends on the last factual line before the OS trace. | WS-1 HARD |
| M4 | Remove-and-diff every unit before emitting. | model-side; filler density WS-A3 is the proxy |
| M5 | Numbers, not adjectives: counts, ranges, durations, percentages. `several changes` becomes `4 files`; `took a while` becomes `47 s`; `most tests` becomes `47/52 (90%)`. | WS-A4 advisory |
| M6 | Flag broken only: status carries at most Shipped, Next (one item), Broken; omit Broken when nothing is broken; never list what works. Evidence is a count line, never a per-item list. | WS-A6 advisory |
| M7 | Detail lives in the artifact: after a file write, chat gives path + what changed in 10 lines or fewer and never restates the file. Governance fields are one line, never padded, never omitted. | WS-A9, WS-A5, WS-A10 advisory |
| M8 | Budgets are contracts (§5). A budget caps a file; it never justifies splitting one decision across files. No character line-length cap. | MD-5 HARD for SKILL.md |

Before and after:

```text
Before: Great question! I'd be happy to help. It seems like the issue is probably in the auth middleware, which might be worth looking into. In summary, the token check is off by one. Hope this helps!
After:  Bug in auth middleware: token expiry check uses `<` not `<=`. Fix below. Confidence: high.
```

## 4. Banned phrases, one machine-read source <a id="banned"></a>

The Stop gate reads this block at runtime. Format: `GROUP H|A regex`, matched case-insensitively on preprocessed prose (fences, inline code, blockquotes, quoted spans, box regions and governance field lines stripped). `^` anchors to line start. H blocks; A logs. NARRATE and ECHO are judged only on the final text block of the turn.

<!-- banned:start -->
```text
GLAZE     H \b(great|excellent|fantastic|fascinating) (question|point|idea|perspective)\b
GLAZE     H (^|[.!?] )\s*good catch\b
GLAZE     H \byou('| a)?re absolutely right\b
APOLOGY   H \b(i apologi[sz]e|apologies,? but|sorry to push back|sorry for the confusion)\b
PLEASANT  H ^\s*(sure|certainly|of course|absolutely)[!,.]
PLEASANT  H \b(happy to help|i'd be happy to|glad to help)\b
CLOSER    H \b(hope (that|this) helps|let me know if|grab a coffee|nice work|standing by for your)\b
SUMMARY   H ^\s*(in summary|to summarize|to recap|in conclusion)\b
ECHO      H ^\s*as (you )?requested\b
ECHO      A \byou asked (me to|for)\b
NARRATE   H ^\s*(let me|i'll now|i will now|i'm going to|now i'll|now let me|first,? let me)\b
FILLER    A \b(just|really|basically|actually|simply)\b
HEDGE     A \b(i think|it seems (like|that)|might be worth considering)\b
VAGUE     A \b(several|a few|a number of|numerous|various|significant(ly)?|a while|most of)\b
ASKRUN    A \b(please|can you|could you|would you|try) run(ning)?\b
```
<!-- banned:end -->

ASKRUN is HARD in pinned projects (`asawa-holding`, `sutra`) and advisory elsewhere. HEDGE is suppressed when a `Confidence:` token is in the same paragraph. FILLER logs only when the count exceeds 3 in a turn.

## 5. Budgets <a id="budgets"></a>

| Artifact | Max | Gate |
|---|---|---|
| Outcome opener (chat) | 5 prose lines | WS-A2 |
| Chat turn prose | 40 lines; 60 hard | WS-A1 / WS-3 |
| Chat after a file write | 10 lines path + change; 25 logged | WS-A9 |
| Error or violation block | 5 lines | model |
| Diff summary | 10 lines | model |
| Status update | 15 lines, 3 signals | model |
| Progress report | 20 lines | model |
| Daily Pulse | 25 lines | model |
| OKR summary per charter | 15 lines | model |
| Roadmap meeting | 50 lines per section | model |
| Decision box | width 40, 4 options, 1-sentence reason | model |
| Governance block | 1 line per field; FLOW 9, BLUEPRINT 16, DISPATCH 9 lines | WS-A5 / WS-A10 |
| Gate block reason | 12 ASCII lines | self-test |
| `skills/*/SKILL.md`, `holding/skills/*.md` | 250 lines | MD-5 |
| Markdown table | 5 columns, 25 words per cell | model |
| Plugin release description | 2 sentences | model |
| CHANGELOG entry | 5 lines | model |
| Release or PR title | 60 chars | model |

Counting rule: prose lines are non-blank lines after stripping code fences, inline code, blockquote lines, box regions and governance field lines; table rows count, separator rows do not. Budgets count chat prose only; file contents written through tools are never counted or judged, so a long architecture doc or executive doc lives in its file and chat carries the path (M7). Numeric thresholds live in `sutra-defaults.json` under `.output_discipline.writing_style`; phrases live only in §4.

## 6. Shapes <a id="shapes"></a>

- **Shape selection**: 3+ comparable items, any comparison or enumeration: table. Decision: ASCII box in chat; table or `>` blockquote in a file. Only decisions get boxed.
- **Decision box** (chat and terminal only; in a file only inside a fence as a template spec):

```text
+--------------------------------------+
| DECISION: <title>                    |
| Recommendation: <option> (first)     |
| Reason: <one sentence>               |
| [1] <option A, recommended>          |
| [2] <option B>                       |
+--------------------------------------+
```

- **Task tables**: header `| # | Area/Task | Impact (who/what changes) | Effort (time, files) |`, required at 3+ task rows; optional Depth, Cost. Relayed subagent or codex output is reshaped first: Why-it-matters or Rationale becomes Impact; Cost S/M/L plus time becomes Effort; inferred values are labelled **Inference**. Severity ranks; it does not frame.
- **Progress bar**: `Name ######.... 0.6 STATUS`, 10 chars, each `#` is 0.1. Structural glyphs are ASCII only: box-drawing and block elements (U+2500-U+259F, rounded corners included) are banned in prose (D-UX-1).
- **Boards and icons**: no emoji in prose. Board markers: `[x]` done, `[ ]` todo, `[.]` in progress with a percentage, `[!]` blocked. Status words GREEN / YELLOW / RED. Outputs before inputs: what improved, what shipped, what is next.
- **Typography**: bold sparingly; inline code for paths, commands and keys; no heavy borders for data; tree characters only inside a fence.

## 7. Files: R1-R12, chunking, provenance <a id="files"></a>

Markdown is read by models first and rendered for humans. Baseline: CommonMark + GFM.

| Id | Rule | Gate |
|---|---|---|
| R1 | Purpose line after the title, then a metadata block: title, status, scope, owner, updated, source inputs | MD-1 HARD new |
| R2 | Narrow tables (5 columns, 25 words per cell) and typed lists; one concept per row | model |
| R3 | Graphs: mermaid fence (conservative syntax, no HTML in participants) plus an adjacent edge list as source of truth; facts as connected tree nodes | MD-A3 advisory |
| R4 | No ASCII or unicode box art in files; a fenced box is allowed only as the spec of a chat template | MD-3 HARD new |
| R5 | Exactly one H1, progressive headings, max H3; typed lists instead of H4+ | MD-4 HARD new |
| R6 | Explicit `<a id="slug"></a>` anchors on linked sections; update inbound links on rename | model |
| R7 | Repo claims carry file:line; unsourceable claims carry a typed label (P4) | model |
| R8 | Evolving docs mark state: **Current rule** / **Historical context** / **Deprecated** / **Migration note** | model |
| R9 | Canonical names: expand on first use, never drift to synonyms | model |
| R10 | Provenance footer, last section, one line (schema below) | MD-2 HARD new |
| R11 | Never jump heading levels | MD-4 |
| R12 | Every fence carries a language tag; text, console, json, yaml, mermaid are valid | MD-A2 advisory; HARD for new files from 2026-10-08 |

Chunking: C1 one decision or domain per file, self-contained; C2 chunk by boundary, not length, never over-chunk; C3 hub files map children without duplicating substance, every row says "read this when"; C4 every child links to its parent hub.

```yaml
provenance: {author: <agent|person>, date: YYYY-MM-DD, inputs: [<sources>], review: <none|codex|dual-lane|founder>, supersedes: <path|none>, confidence: <high|moderate|low|unknown>, gaps: [<known gaps>]}
```

Enforcement: `md-standard-gate.sh` (PostToolUse Edit|Write on .md). New untracked files block on MD-1 metadata, MD-2 provenance, MD-3 box art, MD-4 H1 count, MD-5 SKILL.md over 250 lines. Tracked files log only, except MD-5, which blocks growth past the pre-edit count. Exempt paths are listed in the hook header. A baseline allowlist for tracked files is deferred until ledger data exists.

## 8. Activation and revoke <a id="revoke"></a>

Default ON at L0 for every plugin install once `/core:start` has written `.claude/sutra-project.json`; uniform across tiers T1-T4 (D34). Per-project opt-down: `"writing_style": "advisory"` in `.claude/sutra-project.json`; pinned projects `asawa-holding` and `sutra` ignore it. Retired aliases keep resolving through redirect stubs: `/caveman` (P2), `/anti-glaze-tone` (P3), `/readability-gate` (P1, §5, §6), `/writing-llm-md` (§7).

| Phrase (whole line) | Effect | SCOPE |
|---|---|---|
| `normal mode`, `stop caveman` | COMPRESS off: articles and full sentences return; MINIMIZE and CANDOR stay on | compress |
| `stop anti-glaze`, `drop anti-glaze` | CANDOR off | candor |
| `long form`, `stop minimize` | M2 and M7 budgets off | minimize |
| `stop writing-style` | whole gate advisory | all |
| `strict mode`, `resume writing-style`, `caveman mode` | revoke cleared | none |

A revoke lasts for the rest of the session, as the legacy skills specified; the clear phrases end it early. The marker `.claude/sessions/<sid>/.writing-style-revoked` is written only by `per-turn-discipline-prompt.sh` on a deterministic whole-line phrase match, never by the model; it is a dotfile, so the per-turn marker wipe skips it by design. A permanent change is an edit to this file.

## 9. Enforcement contract <a id="enforcement"></a>

| Check | Hook | Severity |
|---|---|---|
| WS-1 banned phrase, H rows of §4 | writing-style-gate.sh (Stop) | HARD |
| WS-2 box-drawing or block glyph outside a fence | writing-style-gate.sh | HARD |
| WS-3 prose over 60 lines | writing-style-gate.sh | HARD |
| WS-4 task table, 3+ rows, missing Impact or Effort | writing-style-gate.sh | HARD |
| WS-5 ask-to-run in pinned projects | writing-style-gate.sh | HARD |
| WS-A1..A12: 41-60 lines, opener, filler, vague, padding, exhaustive list, ask-to-run, html, restate, field wrap, hedge, unboxed decision | writing-style-gate.sh | advisory |
| MD-1..MD-5, MD-A1..A4 | md-standard-gate.sh (PostToolUse) | per §7 |
| Revoke marker writer, nudge line | per-turn-discipline-prompt.sh (UserPromptSubmit) | none |

Guards: silent until `.claude/sutra-project.json` exists; `stop_hook_active` passes, so at most one redo per turn; fail-open on a missing transcript, python3 or banned block, with a ledger row; empty turn text passes with ledger row `unverifiable_flush_lag`; the block reason is 12 ASCII lines or fewer and passes this gate itself. Ledger: `.enforcement/writing-style.jsonl`. Kill ladder: `WRITING_STYLE_DISABLED=1`; `~/.writing-style-disabled` (founder revoke only); per-project opt-down; per-turn audited ack marker `.claude/sessions/<sid>/writing-style-ack` with a `REASON=` line. Tests: `tests/unit/test-writing-style-gate.sh`, `test-writing-style-skill-selfcheck.sh`, `test-md-standard-gate.sh`.

## 10. Self-audit before emitting <a id="checklist"></a>

1. Outcome in the first 5 prose lines.
2. Prose 40 lines or fewer; overflow to `Top 3 + N other` or a file.
3. No banned phrase, no box-drawing or block glyph.
4. Shape chosen: table, box, bar.
5. Task tables carry Impact + Effort.
6. Numbers, not adjectives; Confidence or a typed label on actionable claims.
7. Code and quotes verbatim; governance schemas untouched, fields one line.
8. Any .md: metadata, one H1, tagged fences, anchors, edge-list twin, provenance, 250 lines or fewer.

## 11. Not adopted <a id="not-adopted"></a>

- Aggressive or argumentative register; insensitivity to propriety; "no disclaimers"; maximize length (anti-glaze source clauses rejected 2026-05-12).
- llms-full.txt and llms-only tags; markdownlint MD013 line-length cap.
- Emoji status sets; unicode bars, sparklines, frames or dividers.
- A long-form escape phrase for the hard budget: use a file (M7) or the audited ack marker.

---

provenance: {author: claude + founder, date: 2026-09-08, inputs: [caveman SKILL (gstack fork 2026-05-12), anti-glaze-tone SKILL (@aiedge_ 2026-05-12), readability-gate SKILL, READABILITY-STANDARD.md (TERMINAL-READABILITY-RESEARCH 2026-04-06), writing-llm-md v1.1, D51, D55, D58, D71, founder feedback 2026-08-17 and 2026-09-02, workflow wf_5cf3e80e (7 readers, 3 sweeps, 3 designs, 2 judges, synth, critic), codex consult thread 01a0807d 2026-09-08], review: codex, supersedes: [skills/caveman, skills/anti-glaze-tone, skills/readability-gate, skills/writing-llm-md, holding/skills/writing-llm-md.md, sutra/layer2-operating-system/READABILITY-STANDARD.md], confidence: high, gaps: [deepseek lane SKIPPED (unfunded); ASCII-only bars replace the unicode bar, founder-reversible; HTML-by-doc-class (D16) parked; baseline allowlist for tracked .md deferred]}
