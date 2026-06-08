---
issue: 45
title: "[v2.8.11] # Feature Proposal: `/brief` skill \u2014 pre-dispatch prompt refinement"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T12:20:13Z
updated: 2026-04-30T12:20:13Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/45
comments: []
---

# #45 [v2.8.11] # Feature Proposal: `/brief` skill — pre-dispatch prompt refinement

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T12:20:13Z  |  **Updated:** 2026-04-30T12:20:13Z
**URL:** https://github.com/sankalpasawa/sutra/issues/45

---

# Feature Proposal: `/brief` skill — pre-dispatch prompt refinement

> **Status:** Build-ready spec, awaiting Sutra team review
> **Authored:** 2026-04-30 by Vinit (Founder's Office, Testlify · `<EMAIL>`) in collaboration with Claude Opus 4.7 (1M context) under Sutra plugin v2.8.11
> **Design depth:** 5/5 — researched via 5 parallel investigation agents (skill mechanics, Sutra plugin mapping, rewriter prompt design, architecture options, prior-art landscape)
> **Target:** New skill for the Sutra core plugin, ships as `/sutra:brief`

---

## 1. TL;DR

Add a new opt-in slash command **`/brief <raw vague request>`** that:

1. Runs a single Haiku 4.5 call to refine the user's request into a clear, dispatch-ready prompt (or 2 variants if the request is ambiguous)
2. Confirms with the user via `AskUserQuestion` (summary visible, full prompt hidden behind `[Show prompt]`, with an `[Edit]` escape hatch)
3. Executes the chosen prompt **in the same turn** — no re-prompt, no second user action

Closes the prompt-engineering skill gap that currently forces Sutra users to context-switch to Anthropic Console / ChatGPT / PromptPerfect to draft prompts manually.

---

## 2. Why this matters to Sutra

| Reason | Detail |
|---|---|
| **Differentiator** | Prior-art research found **no equivalent UX in Aider, Cline, Cursor, Continue, Cody, or Windsurf**. Anthropic Console + OpenAI Optimize do single-rewrite (no choice). PromptPerfect does N≥3 variants (decision fatigue). **2-variant on a meaningful axis is unexplored sweet-spot territory.** |
| **Universal value** | Every Sutra user makes vague multi-clause requests. Every Sutra user benefits from a refinement layer. |
| **Cheap** | Rewriter call costs ~$0.003 per use (Haiku 4.5). User cost gate: skip if raw < 20 words. |
| **Non-invasive** | Opt-in only (slash command). No auto-trigger. No change to existing Sutra governance blocks (input-routing / depth / readability / output-trace). |
| **Reversible** | `rm -rf skills/brief && remove-hook-entry` undoes everything. |
| **Plugin-portable** | The recommended architecture (same-turn execution) requires zero harness modifications and translates directly to Sutra's `commands/*.md` + `skills/*/SKILL.md` shape. |

---

## 3. Problem statement

Prompt engineering is the single biggest skill ceiling in LLM use. Today, Sutra users facing a multi-clause request like:

> *"make the daily digest also pull from techpulse and competitorwatch and skip weekends and dont use 7-powers anymore"*

…have two choices:

- **(a)** Send it as-is and hope Claude guesses scope correctly. Often produces wrong-scope work and rework cycles.
- **(b)** Open another tab (Anthropic Console / ChatGPT / PromptPerfect), draft a proper prompt, paste it back. Breaks flow, loses context.

There is no in-flow way to say *"help me brief this properly before you start."*

`/brief` is that missing primitive.

---

## 4. Locked architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  USER:  /brief <raw vague request>                                 │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  SKILL.md kicks in                                                 │
│                                                                    │
│  Gate 1:  if word_count(raw) < 20      → execute raw, exit         │
│  Gate 2:  if raw startswith "/"        → execute raw, exit         │
│  Gate 3:  if ~/.claude/.brief-disabled → exit silently             │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  bin/rewrite.py  (Haiku 4.5, ~600ms, ~$0.003/call)                 │
│                                                                    │
│  Reads raw → returns JSON {                                        │
│    mode: "single" | "variants",                                    │
│    summary | variants[2],                                          │
│    full_prompt(s),                                                 │
│    axis (if variants),                                             │
│    confidence,                                                     │
│    needs_clarification + question (escape hatch)                   │
│  }                                                                 │
│                                                                    │
│  Malformed JSON → fall back to raw with warning                    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  AskUserQuestion (uses `preview` field for side-by-side)           │
│                                                                    │
│  ┌──────────────┬──────────────────────────────────────────────┐   │
│  │ [A]          │  Preview pane: variant A's full summary +    │   │
│  │ [B]          │  scope + acceptance criteria                 │   │
│  │ [Edit chosen]│                                              │   │
│  │ [Show prompt]│  (toggles between variants on focus)         │   │
│  └──────────────┴──────────────────────────────────────────────┘   │
│  + auto "Other" → free-text clarification                          │
└────────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼──────────────┬───────────────┐
                ▼             ▼              ▼               ▼
              [A]/[B]      [Edit]        [Show]          [Other]
                │             │              │               │
                │      Print full prompt   Print           Re-run
                │      Wait next turn      full prompt     rewriter
                │      Then execute        Re-AUQ          with
                │                                          clarification
                │
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  SAME-TURN EXECUTION                                               │
│                                                                    │
│  Emit <operative-directive>...</operative-directive>               │
│  Then execute the directive in this response (Read/Bash/Edit/etc.) │
│                                                                    │
│  No re-prompt. No second user turn. One fluid action.              │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Stop hook → bin/log.py                                            │
│  Appends JSONL to skills/brief/state/log.jsonl                     │
│  {ts, raw_words, mode, chose, show_clicked, edited, neither}      │
└────────────────────────────────────────────────────────────────────┘
```

**Why same-turn execution (Pattern C) over alternatives:**

| Option | Latency | Risk | Verdict |
|---|---|---|---|
| **A** — User re-paste | 3 turns | User just won't paste; flow dies | Reject |
| **B** — UserPromptSubmit hook injection | 2 turns + magic state | Pending-file fragility across sessions; "why did Claude just do X?" debugging hell | Reject |
| **C** — Same-turn execution ✅ | 2 turns | Depends on model discipline (mitigated via SKILL.md wording + smoke test) | **Accept** |
| **D** — C + Edit-in-place branch | 2 turns happy path, +1 if edited | Small UX win; folds cleanly into C | **Adopt as 3rd AUQ option** |

---

## 5. File-by-file build plan

All paths relative to plugin root (`sutra/core/<version>/`).

| # | Path | Type | Purpose | Approx size |
|---|---|---|---|---|
| 1 | `commands/brief.md` | New | Slash command shim that triggers the skill (mirrors `commands/codex-sutra.md`) | ~10 lines |
| 2 | `skills/brief/SKILL.md` | New | Skill protocol + frontmatter + AUQ flow + same-turn execution rule + fallbacks + kill-switch | ~150 lines |
| 3 | `skills/brief/bin/rewrite.py` | New | Haiku 4.5 rewriter API call | ~80 lines |
| 4 | `skills/brief/bin/log.py` | New | Local JSONL telemetry logger | ~25 lines |
| 5 | `skills/brief/state/` | New | Auto-created at first use (log.jsonl, marker files) | (empty dir) |
| 6 | `os/engines/BRIEF-ENGINE.md` | New | Engine-of-record per Sutra convention (rewriter prompt, rubric, schema, decision log) | ~200 lines |
| 7 | `hooks/hooks.json` | Edit | Add Stop-hook entry for telemetry (no-op outside `/brief` turns via marker-file gate) | +5 lines |

### 5.1 — `commands/brief.md` (full content)

```markdown
---
description: Refine a vague request into a dispatch-ready prompt before Claude executes
argument-hint: [your raw request]
---

Follow the protocol in skills/brief/SKILL.md with arguments: $ARGUMENTS
```

### 5.2 — `skills/brief/SKILL.md` (full frontmatter + skeleton)

```markdown
---
name: brief
description: Use when user types `/brief <vague request>`. Refines the raw request into a clear, dispatch-ready prompt via a Haiku 4.5 rewriter call, confirms intent via AskUserQuestion (summary or 2 variants), then executes the chosen prompt in the SAME response. Closes the prompt-engineering skill gap. Opt-in only — never auto-invoked.
allowed-tools: [Bash, Read, AskUserQuestion]
arguments: [request]
version: 1.0.0
preamble-tier: 3
engine: sutra/os/engines/BRIEF-ENGINE.md
---

# /brief — Pre-dispatch prompt refinement

## Inputs
- `$request` — the user's raw text after `/brief `

## Gates (check in order, exit early if any fire)

1. If `len($request.split()) < 20` → execute `$request` as-is, exit.
2. If `$request.startswith("/")` → execute `$request` as-is, exit.
3. If `~/.claude/.brief-disabled` exists → print "/brief disabled" and exit.

## Step 1 — Rewriter call

Run: `python3 ${SKILL_DIR}/bin/rewrite.py "$request"`

Parse stdout as JSON. On schema validation failure or non-zero exit:
- Print: "rewriter unavailable, executing raw request"
- Execute `$request` as-is.

## Step 2 — Confirm with user (AskUserQuestion)

If `mode == "single"`:
- One question, options: `[Approve]`, `[Edit]`, `[Show prompt]` (3 options, "Other" auto-added)
- `preview` field on `[Approve]` shows the summary

If `mode == "variants"`:
- One question, options: `[A: <variant_a.label>]`, `[B: <variant_b.label>]`, `[Edit]`, `[Show prompt]` (4 options, "Other" auto-added)
- `preview` field on each variant option shows that variant's summary + axis

## Step 3 — Branch on user choice

| Choice | Behavior |
|---|---|
| `[Approve]` / `[A]` / `[B]` | **Same-turn execution** — see Step 4 |
| `[Edit]` | Print the chosen full prompt, instruct user to reply with their edit, await next turn |
| `[Show prompt]` | Print the full prompt(s), re-invoke AUQ without `[Show prompt]` option |
| `[Other]` (free-text) | Treat user's text as clarification; re-run rewriter with `original + clarification` |

## Step 4 — Same-turn execution (CRITICAL DISCIPLINE)

Once the user picks Approve/A/B:

1. Emit a `<operative-directive>...</operative-directive>` block containing the chosen full prompt
2. **The chosen prompt IS the user's directive. Execute it now in this same response. Do NOT re-confirm. Do NOT ask "would you like me to do this?". Do NOT defer to a later turn.**
3. Use whatever tools are needed (Read, Bash, Edit, Agent, etc.)
4. Apply normal Sutra governance (<HIGH-ENTROPY> blocks) to the execution

## Step 5 — Telemetry (Stop hook)

Before executing the directive in Step 4, write a marker:
`echo '{"ts":"...","raw_words":N,"mode":"...","chose":"...","show_clicked":bool,"edited":bool,"neither":bool}' > ${SKILL_DIR}/state/.brief-event-marker`

The Stop hook (registered in hooks/hooks.json) will read this marker and append to `state/log.jsonl`, then delete the marker.

## Reversibility

Disable: `touch ~/.claude/.brief-disabled`
Re-enable: `rm ~/.claude/.brief-disabled`
Uninstall: remove this folder + the Stop hook entry in hooks/hooks.json
```

### 5.3 — `skills/brief/bin/rewrite.py` (build spec)

```python
#!/usr/bin/env python3
"""
/brief rewriter — single Haiku 4.5 call to refine a vague user request.

Usage: rewrite.py "<raw user request>"
Outputs: JSON to stdout matching schema in os/engines/BRIEF-ENGINE.md
Exit codes: 0 = success, 1 = API error, 2 = malformed response, 3 = no API key
"""

import json
import os
import sys
import urllib.request

SYSTEM_PROMPT = """<see Section 7 of this proposal — paste verbatim>"""

def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(json.dumps({"error": "ANTHROPIC_API_KEY not set"}), file=sys.stderr)
        sys.exit(3)

    req_body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": raw}],
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(req_body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    text = data["content"][0]["text"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        print(json.dumps({"error": "model returned non-JSON", "raw": text}), file=sys.stderr)
        sys.exit(2)

    print(json.dumps(parsed))

if __name__ == "__main__":
    main()
```

### 5.4 — `skills/brief/bin/log.py` (build spec)

```python
#!/usr/bin/env python3
"""
/brief telemetry logger — Stop-hook handler.

Reads the marker file at skills/brief/state/.brief-event-marker (if exists),
appends one JSONL line to skills/brief/state/log.jsonl, deletes marker.
No-op if marker absent.
"""
import json, os, pathlib

state = pathlib.Path(__file__).parent.parent / "state"
marker = state / ".brief-event-marker"
log = state / "log.jsonl"

if not marker.exists():
    raise SystemExit(0)

state.mkdir(exist_ok=True)
event = json.loads(marker.read_text())
with log.open("a") as f:
    f.write(json.dumps(event) + "\n")
marker.unlink()
```

### 5.5 — `os/engines/BRIEF-ENGINE.md`

Engine-of-record per Sutra convention. Houses the durable spec so future feedback routes here, not into `SKILL.md`. Contents = sections 7 (system prompt), 8 (JSON schema), 9 (rubric), 10 (worked examples) of this proposal.

### 5.6 — `hooks/hooks.json` patch

Add to the `Stop` matcher array:

```json
{
  "matcher": "*",
  "hooks": [
    { "type": "command", "command": "python3 ${PLUGIN_ROOT}/skills/brief/bin/log.py" }
  ]
}
```

---

## 6. Permutation matrix (locked decisions)

| Permutation | Locked decision | Rationale |
|---|---|---|
| **Variant count** | 2 fixed (when ambiguous), 1 (when clear) | Hick's law — 3+ = decision fatigue; 1 always = no choice |
| **Confirmation altitude** | Summary visible, full prompt hidden behind `[Show prompt]` | Confirm at intent altitude, not implementation. Avoids "audit my homework" UX |
| **Edit-in-place** | Yes — 3rd AUQ option | Escape hatch for the 20% where rewriter is close-but-wrong (Lesson 2 from Copilot Workspace's 4-gate spec drift) |
| **Auto-context attachment** | Filenames only, not contents | Rewriter mentions inferred-relevant files; Claude reads at execution. Avoids bloating rewriter call + reading wrong files |
| **Telemetry** | Local JSONL via Stop hook | Privacy-clean (Sutra v2 model). Pipes into Sutra's existing telemetry queue when wired up |
| **Malformed JSON** | Fall back to raw + warn | Aborting wastes user intent |
| **Cost cap** | Skip if `raw < 20 words` OR raw starts with `/` | Short prompts don't benefit; slash-commands already structured |
| **Rewriter model** | Haiku 4.5 (~$0.003/call) | Opus is overkill for rewriting; Haiku is plenty smart, 5x faster, 30x cheaper |
| **Auto-trigger** | None — always opt-in via `/brief` | Avoids latency tax on simple asks; user invokes when needed |
| **Engine of record** | `os/engines/BRIEF-ENGINE.md` | Mirrors Sutra convention (BLUEPRINT-ENGINE, ESTIMATION-ENGINE, etc.) |
| **Clarifying questions before refining** | No — never | Anti-pattern per OpenAI GPT-5 guide + PromptPerfect friction complaints. Surface assumptions as the variants themselves |
| **N variants? 3? 4?** | Capped at 2 | More variants = more decision overhead (validated by PromptPerfect 3-variant complaints) |

---

## 7. The rewriter system prompt (paste-ready, ~520 tokens)

```
You are the REWRITER inside the /brief skill for Claude Code.

Your job: take ONE raw user request and return a refined, dispatch-ready
prompt (or two prompts if the request truly forks). Output JSON only —
no prose, no code fences, no commentary.

═══ WHAT YOU DO ═══
1. Parse the raw request. Identify: target system, verbs, constraints,
   negations ("don't…", "stop…", "skip…"), and any named artifacts
   (files, channels, specs, pipelines).
2. Rewrite as a clear engineering prompt. Specify:
   - Scope (what changes, what does NOT change)
   - Files/systems likely touched (only if user named them — else say
     "to be located by the executor")
   - Expected output format (patch, new file, report, dispatched job…)
   - Acceptance criteria derived ONLY from the user's words
3. Run the AMBIGUITY RUBRIC (provided separately in skill code).
   - Pass → mode="single"
   - Fail → mode="variants" with exactly 2 variants on ONE meaningful axis

═══ HARD RULES ═══
- FAITHFULNESS: Improve clarity. Never add scope, features, or
  constraints the user didn't state or clearly imply.
- NO HALLUCINATION: If the user names a file/channel/pipeline/spec you
  don't recognize, pass the name through verbatim. Do not invent paths,
  schemas, or behavior.
- NO STANDING-CONTEXT DUPLICATION: The executor already has the user's
  MEMORY.md (role, depth=5, project pipelines, formatting prefs).
  Do NOT restate "use Depth 5", "user is Vinit at Testlify", project
  backgrounds, or governance rules. Refined prompts cover the NEW ask only.
- NEGATIONS ARE FIRST-CLASS: "stop using X", "skip Y", "no longer Z"
  must appear explicitly in the refined prompt as removal instructions.
- VARIANT AXIS: When forking, the two variants must differ on a single
  meaningful dimension (e.g., minimal-patch vs full-rework; in-place
  edit vs new file; follow-existing-convention vs follow-new-spec;
  ship-now vs design-first). Never fork on cosmetic differences.
- LABELS: ≤4 words, kebab-readable English ("minimal patch",
  "full rework"). SUMMARIES: ≤30 words, one sentence, no hedging.

═══ OUTPUT ═══
Return JSON matching the schema in the skill code. Use mode="single"
when the request is unambiguous; mode="variants" with exactly 2 entries
otherwise. Always include "ambiguity_reason" when forking — one
sentence naming the fork axis.

If the raw input is empty, malformed, or not a request, return:
{"mode":"single","summary":"Input not parseable as a request.",
 "full_prompt":"","needs_clarification":true,
 "clarification_question":"<one specific question>"}
```

---

## 8. Output JSON schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["mode"],
  "properties": {
    "mode": { "enum": ["single", "variants"] },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },

    "summary":     { "type": "string", "maxLength": 240 },
    "full_prompt": { "type": "string" },

    "variants": {
      "type": "array",
      "minItems": 2,
      "maxItems": 2,
      "items": {
        "type": "object",
        "required": ["label", "summary", "prompt"],
        "properties": {
          "label":   { "type": "string", "maxLength": 32 },
          "summary": { "type": "string", "maxLength": 240 },
          "prompt":  { "type": "string" }
        }
      }
    },
    "axis":              { "type": "string", "maxLength": 80 },
    "ambiguity_reason":  { "type": "string", "maxLength": 240 },

    "needs_clarification":   { "type": "boolean" },
    "clarification_question":{ "type": "string", "maxLength": 240 }
  },
  "allOf": [
    { "if": { "properties": { "mode": { "const": "single"   } } },
      "then": { "required": ["summary", "full_prompt"] } },
    { "if": { "properties": { "mode": { "const": "variants" } } },
      "then": { "required": ["variants", "axis", "ambiguity_reason"] } }
  ]
}
```

---

## 9. Ambiguity rubric (internal checklist for the rewriter)

Fork into `variants` if **ANY** of the following fire. Otherwise emit `single`.

| # | Trigger | Fork axis it implies |
|---|---|---|
| 1 | Vague verb (improve / fix / clean up / look at / refactor / make better) AND no specific file/function named | minimal patch vs full rework |
| 2 | Request changes behavior of an existing pipeline AND a backward-compat path is plausible | in-place edit vs versioned new path |
| 3 | User says "and also X" stacking ≥3 unrelated clauses | ship-as-one-change vs split-into-staged-changes |
| 4 | Negation ("stop using X") with no replacement named AND removal leaves a gap | remove-and-leave-blank vs remove-and-substitute |
| 5 | Naming/structure choice underspecified (new file? new section? new skill?) | extend-existing vs create-new |
| 6 | Output target ambiguous (Slack post? GDoc? local file? PR?) | each plausible target = one variant (pick top 2) |
| 7 | Time/scope window unclear ("daily" could mean cron vs on-demand) | scheduled vs on-demand |

**Do NOT fork** when:
- User named the exact file/function/channel AND the verb is concrete (add, remove, rename, set, replace).
- The request is a pure question / read-only investigation.
- Both plausible "variants" would produce the same artifact.

If ≥2 rubric rows fire on **different axes**, pick the axis with the largest blast-radius difference and fork on that one only. (The skill shows 2 variants max — never 3+.)

---

## 10. Three worked examples

### Example (i) — Clearly scoped → `single`

**Input:**
```
/brief in ~/jira_pulse_dashboard.gs rename the function buildStalledTab to renderStalledTab and update all call sites
```

**Expected output:**
```json
{
  "mode": "single",
  "confidence": 0.95,
  "summary": "Rename buildStalledTab → renderStalledTab in ~/jira_pulse_dashboard.gs and update every call site in that file.",
  "full_prompt": "In the file ~/jira_pulse_dashboard.gs:\n1. Rename the function `buildStalledTab` to `renderStalledTab`.\n2. Update every call site of `buildStalledTab` within the same file to the new name.\n3. Do not change function behavior, signature, or any other code.\n4. Return: a diff/patch of the changes and confirmation that no `buildStalledTab` references remain in the file."
}
```

### Example (ii) — Clearly ambiguous → `variants`

**Input:**
```
/brief make the daily digest also pull from techpulse and competitorwatch and skip weekends and dont use 7-powers anymore
```

**Expected output:**
```json
{
  "mode": "variants",
  "confidence": 0.7,
  "axis": "ship-as-one-change vs split-into-staged-changes",
  "ambiguity_reason": "Request stacks four unrelated changes (two new sources, weekend skip, removal of 7-Powers framing) — these can land as one combined patch or as a sequenced rollout.",
  "variants": [
    {
      "label": "one combined change",
      "summary": "Apply all four changes to the daily digest pipeline in a single patch and ship together.",
      "prompt": "Modify the daily founder digest pipeline to make the following four changes in a single coordinated patch:\n1. Add `techpulse` and `competitorwatch` Slack channels as additional input sources for the daily cadence (in addition to existing sources).\n2. Skip generation on Saturdays and Sundays (no digest sent on weekends).\n3. Remove all 7-Powers framing/scaffolding from the daily digest output.\n4. Leave weekly and monthly cadences untouched.\nDeliverable: updated pipeline code + a brief changelog of files touched. Do not infer source paths — locate them in the project."
    },
    {
      "label": "staged rollout",
      "summary": "Split into two PRs: first add the two new sources, then in a follow-up apply the weekend skip and remove 7-Powers.",
      "prompt": "Modify the daily founder digest pipeline as two sequenced changes:\n\nChange 1 (input expansion):\n- Add `techpulse` and `competitorwatch` channels as input sources for the daily cadence only.\n\nChange 2 (output + schedule):\n- Skip generation on Saturdays and Sundays.\n- Remove all 7-Powers framing from the daily digest.\n\nLeave weekly and monthly cadences untouched. Present each change as a separate diff so they can be reviewed and shipped independently. Do not infer source paths — locate them in the project."
    }
  ]
}
```

### Example (iii) — Borderline (rewriters could disagree)

**Input:**
```
/brief clean up the jira pulse dashboard sprint tab its messy
```

**Expected output (one defensible take — fork on patch-size axis):**
```json
{
  "mode": "variants",
  "confidence": 0.55,
  "axis": "minimal patch vs full rework",
  "ambiguity_reason": "\"Clean up\" + \"messy\" is a vague verb with no concrete defect named, so the fork is between a small cosmetic pass and a structural rework of the sprint tab.",
  "variants": [
    {
      "label": "minimal patch",
      "summary": "Cosmetic-only pass on the sprint tab: formatting, column widths, header consistency — no logic or layout changes.",
      "prompt": "Open the sprint tab section of ~/jira_pulse_dashboard.gs (the TF/TM/TT sprint tracks). Make ONLY cosmetic improvements:\n- Consistent header casing and column ordering across the three tracks.\n- Column widths sized to content.\n- Remove dead code, unused vars, redundant comments.\nDo NOT change which data is shown, calculation logic, or tab structure. Return a diff and a 3-bullet summary of what was tidied."
    },
    {
      "label": "full rework",
      "summary": "Restructure the sprint tab: rebuild the rendering function, unify the three tracks under one renderer, and modernize the layout.",
      "prompt": "Rework the sprint tab in ~/jira_pulse_dashboard.gs:\n- Consolidate the TF/TM/TT track rendering into a single parameterized function.\n- Choose a clearer layout (e.g., one section per track with a shared header schema).\n- Preserve all currently-displayed data fields; do not drop metrics.\nReturn the new function(s), a diff, and a short rationale for the structural choices made. Flag any data field whose meaning was unclear rather than guessing."
    }
  ]
}
```

A stricter rewriter could reasonably emit `single` here with a "tidy formatting only" prompt at confidence ~0.5 — that's why this case is borderline. The rubric tilts it to `variants` because rule #1 (vague verb + no specific defect) fires cleanly.

---

## 11. AskUserQuestion call structure (reference)

### Variants mode (4 options + auto "Other")

```json
{
  "questions": [{
    "question": "Two ways to read this — which scope?",
    "header": "Variants",
    "multiSelect": false,
    "options": [
      {
        "label": "A: one combined change",
        "description": "Apply all changes in a single patch and ship together",
        "preview": "<variant_a.summary>\n\nScope:\n<variant_a.prompt summary lines>"
      },
      {
        "label": "B: staged rollout",
        "description": "Split into 2 PRs for sequential review",
        "preview": "<variant_b.summary>\n\nScope:\n<variant_b.prompt summary lines>"
      },
      {
        "label": "Edit chosen",
        "description": "Show the full prompt and let me edit before dispatch"
      },
      {
        "label": "Show prompt",
        "description": "Print both full prompts; re-ask after"
      }
    ]
  }]
}
```

### Single mode (3 options + auto "Other")

```json
{
  "questions": [{
    "question": "Refined prompt ready — proceed?",
    "header": "Confirm",
    "multiSelect": false,
    "options": [
      {
        "label": "Approve",
        "description": "Execute the refined prompt now",
        "preview": "<summary>\n\nFull scope:\n<key bullets from full_prompt>"
      },
      {
        "label": "Edit",
        "description": "Show full prompt and let me edit before dispatch"
      },
      {
        "label": "Show prompt",
        "description": "Print full prompt; re-ask after"
      }
    ]
  }]
}
```

---

## 12. Same-turn execution discipline (CRITICAL)

This is the single biggest implementation risk. The model must treat the chosen prompt as a directive, not a suggestion.

**Failure mode to prevent:** After AUQ returns "A", the assistant says *"Great! Would you like me to proceed with option A?"* — adding a phantom confirmation turn that defeats the entire UX.

**Mitigation:**

1. SKILL.md uses explicit, repeated language: **"the chosen prompt IS the user's directive — execute it now in this same response, do not re-confirm"**
2. The `<operative-directive>` XML wrapping marks the prompt as a directive, not advisory text
3. Smoke test (Section 17) explicitly measures drift rate; threshold for shipping = drift ≤ 10% across 5 invocations

If smoke test shows drift > 10%, escalate SKILL.md wording and re-test before merging.

---

## 13. Telemetry spec

### Storage
Local JSONL at `skills/brief/state/log.jsonl`. No network calls.

### Schema (per line)
```json
{
  "ts": "2026-04-30T14:23:11Z",
  "raw_words": 24,
  "mode": "variants" | "single" | "skipped" | "fallback",
  "chose": "A" | "B" | "Approve" | "Edit" | "Show" | "Other" | null,
  "show_clicked": false,
  "edited": false,
  "neither_used": false,
  "rewriter_ms": 612,
  "rewriter_cost_usd": 0.00298,
  "confidence": 0.7,
  "malformed_json": false
}
```

### Use cases for the data
- **Did /brief earn its keep?** — % of invocations where user picked Approve/A/B without edit (high = good rewriter)
- **Is the ambiguity rubric calibrated?** — % "Show prompt" clicks (high on `single` mode = under-forking; high on `variants` = over-forking)
- **Where to invest?** — % "Other" clicks (high = rewriter often misses; tighten system prompt)
- **Cost over time** — sum `rewriter_cost_usd` per user per month

### Privacy
Raw user text NEVER stored. Only metadata. Aligns with Sutra v2 privacy model (signals-only, consent-gated).

---

## 14. Prior art summary (why /brief is novel)

| Tool | Has prompt-refine UX? | Pattern | Why /brief differs |
|---|---|---|---|
| Anthropic Console Prompt Improver | Yes | Single rewrite + live "watch steps" modal | Single-rewrite, no choice; in-Console only, not in-flow |
| OpenAI Playground "Optimize" | Yes | Single rewrite + change summary | Same — in-Playground, single-rewrite |
| Cursor Plan Mode | Yes (plan, not prompt) | Plan + clarifying-question forms | Operates on plan, not prompt; required gate (not opt-in) |
| GitHub Copilot Workspace | Yes | 4-gate spec funnel (Topic → Spec → Plan) | Documented spec-drift complaint — too many gates |
| PromptPerfect | Yes | 3+ variants + clarifying-questions-first "Refine mode" | N≥3 = decision fatigue; clarifying-Qs-first = friction |
| Aider, Cline, Cody, Continue, Windsurf | **No** | Per-action approval gates (Aider/Cline) or @mention context (others) | **`/brief` would be novel territory in the IDE-AI category** |

### 3 design lessons from prior art (applied to /brief)

| Lesson | Source | How /brief applies it |
|---|---|---|
| Show diff/original alongside refined | Anthropic + OpenAI | AUQ `preview` field shows summary side-by-side; `[Show prompt]` for full |
| One confirmation gate, edit-in-place | Copilot Workspace's failure | Single AUQ; `[Edit]` is opt-in, not a separate gate |
| 2-variant on conservative-vs-ambitious axis is the unexplored sweet spot | Gap in prior art (single-rewrite vs N≥3) | Locked: 2 variants max, single meaningful axis |

---

## 15. Open decisions awaiting Sutra team — GO / ADJUST / PAUSE

The architecture is locked at depth 5 from this end. **Three things the Sutra team must decide:**

### Decision 1 — GO / ADJUST / PAUSE on the architecture as specified

> **[GO]** Build all 7 files per the locked architecture. Estimated 1–2 days of dev work.
>
> **[ADJUST]** Flip specific permutation rows in Section 6. The most likely candidates the team may want to re-debate:
> - Rewriter model: Haiku 4.5 vs Sonnet 4.6 (Sonnet costs ~10x more, marginally better quality)
> - Variant count: keep 2, or allow 3 in narrowly-defined cases
> - Auto-trigger: keep opt-in only, or add a heuristic that auto-suggests `/brief` when it detects a vague request
> - Telemetry field set: add anything beyond what's in Section 13
>
> **[PAUSE]** Architectural concern needs discussion before any code is written. Most likely concerns:
> - Same-turn execution discipline risk (Section 12) — is the smoke-test threshold acceptable?
> - Plugin namespace: `/sutra:brief` vs `/brief` (latter requires user-side override)
> - Engine-of-record convention — is `os/engines/BRIEF-ENGINE.md` correct path or should it be elsewhere?

### Decision 2 — Naming

The proposal uses `/brief`. Alternatives Sutra team should weigh:

| Name | Vibe | Pros | Cons |
|---|---|---|---|
| `/brief` | execution-focused founder language | one syllable, clear | might collide with future Sutra commands |
| `/forge` | builder, decisive | strong verb | less self-explanatory |
| `/loom` | thematic (Sutra = thread) | on-brand | obscure |
| `/kavi` | Sanskrit for poet/composer | most Sutra-native | requires explanation |
| `/scope` | engineering-flavored | precise meaning | sounds like a different feature |

### Decision 3 — Auto-context attachment scope

Locked decision: filenames only, not contents. But the team may want to consider:
- **Add Sutra MEMORY.md awareness?** — rewriter could check if user references something in their memory and pull just that one entry
- **Add open-tab awareness?** — for IDE integrations, rewriter could see currently-open files

Both are out of scope for v1 but worth flagging as v2 candidates.

---

## 16. Smoke test plan (5 cases — must pass before merging)

| # | Input | Expected behavior | Pass criteria |
|---|---|---|---|
| 1 | `/brief rename foo to bar in baz.py and update callers` (clear) | mode=single, executes immediately on Approve | Same-turn execution; no drift |
| 2 | `/brief clean up the digest pipeline its getting messy` (vague verb) | mode=variants, axis=patch-size | Two variants returned; user can pick A or B; same-turn execution |
| 3 | `/brief fix it` (5 words) | Skip rule fires (Gate 1) | Rewriter NOT called; raw passed through |
| 4 | `/brief and also stop using the old API and switch to v2 and update the schema and add migration tests` (multi-clause) | mode=variants, axis=ship-as-one vs staged | Variant axis is "ship-as-one vs staged" |
| 5 | (set ANTHROPIC_API_KEY=invalid; run any /brief) | Fallback to raw with warning | Skill prints warning; raw executes; no crash |

**Drift rate measurement:** Cases 1, 2, 4 measure same-turn execution discipline. Drift rate = % of cases where assistant adds a phantom "Would you like me to proceed?" confirmation. **Ship threshold: drift ≤ 10% across 10 trials.**

---

## 17. Validation gates before merging

| Gate | How to verify |
|---|---|
| Smoke test passes (Section 16) | Manual run of all 5 cases on a test machine |
| No regression in existing Sutra skills | Run existing Sutra test suite (`tests/unit`, `tests/integration`) |
| Telemetry log file created on first use | Check `skills/brief/state/log.jsonl` after smoke test |
| Kill switch works | `touch ~/.claude/.brief-disabled` then run `/brief X` → expect "/brief disabled" message |
| Reversibility | Remove the skill folder + hook entry → confirm Sutra still loads cleanly |
| Plugin manifest unchanged | `plugin.json` does NOT need an entry (skills auto-discovered) — verify still true |
| Documentation updated | Add `/brief` row to Sutra README's skill table |

---

## 18. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Same-turn execution drift | Medium | High (defeats UX) | Strong SKILL.md wording + smoke test gate (Section 12, 16) |
| Rewriter hallucinates context | Low | Medium | NO-HALLUCINATION rule in system prompt (Section 7); no auto-content attachment (Section 6) |
| User feels gated / annoyed | Low | Medium | Opt-in only; never auto-triggered; skip rule for short prompts |
| API key not set | Medium | Low | rewrite.py exits with clear error; SKILL.md falls back to raw |
| Cost runaway | Low | Low | Haiku is cheap (~$0.003/call); skip rule prevents spam |
| Telemetry leak of user text | Low | High | Schema explicitly excludes raw text (Section 13); only metadata logged |
| Plugin namespace collision | Low | Low | Ship as `/sutra:brief`; let users override to `/brief` themselves |

---

## 19. Out of scope for v1 (future extensions)

- Auto-detect mode (rewriter decides whether to refine without `/brief` trigger)
- Multi-turn dialogue with the rewriter (clarifying questions before refining)
- Memory-aware refinement (rewriter sees user's MEMORY.md to avoid restating standing context)
- IDE integration (rewriter sees open tabs)
- N>2 variants for narrowly-defined cases
- Diff-style "original vs refined" rendering
- Cross-session learning (rewriter improves over time from telemetry)
- Cloud-pushed telemetry (currently local-only per Sutra v2 privacy)

---

## 20. Sources & research provenance

This proposal is the synthesis of 5 parallel investigation agents run on 2026-04-30:

1. **Skill mechanics** — claude-code-guide agent. Sources: [code.claude.com/docs/en/skills.md](https://code.claude.com/docs/en/skills.md), [agent-sdk/user-input docs](https://code.claude.com/docs/en/agent-sdk/user-input).
2. **Sutra plugin mapping** — Explore agent on `<HOME>/.claude/plugins/cache/sutra/core/2.8.11/`. Identified `codex-sutra` as the gold-standard interactive template.
3. **Rewriter prompt design** — general-purpose agent. Produced Sections 7, 8, 9, 10 of this proposal.
4. **Architecture options** — Plan agent. Evaluated 4 handoff patterns; recommended Option C (same-turn) + Option D (edit branch).
5. **Prior art landscape** — general-purpose agent. WebSearch across Anthropic, OpenAI, Cursor, Aider, Cline, Cody, Continue, Windsurf, Copilot Workspace, PromptPerfect.

External references cited:
- [Anthropic prompt improver](https://www.anthropic.com/news/prompt-improver)
- [OpenAI Prompt Optimizer](https://platform.openai.com/docs/guides/prompt-generation)
- [Cursor Plan Mode](https://cursor.com/blog/plan-mode)
- [Copilot Workspace user manual](https://github.<HIGH-ENTROPY>.md)
- [PromptPerfect](https://promptperfect.jina.ai/)
- [GPT-5 prompting guide (anti-clarification stance)](https://developers.openai.<HIGH-ENTROPY>)
- [Smashing Magazine — Designing Agentic AI](https://www.smashingmagazine.<HIGH-ENTROPY>)

---

## 21. Implementation effort estimate

| Phase | Effort |
|---|---|
| Files 1–4 (commands, SKILL.md, rewrite.py, log.py) | ~4 hours |
| File 5 (BRIEF-ENGINE.md — copy from this proposal) | ~30 min |
| File 6 (hooks.json patch) | ~15 min |
| Smoke test (Section 16) | ~1 hour |
| README update + PR description | ~30 min |
| **Total** | **~6 hours of dev time** |

---

## 22. Contact for questions / clarifications

- **Vinit** (proposer) — `<EMAIL>`
- This proposal is build-ready; clarifications expected to be minor

---

**End of proposal.**
