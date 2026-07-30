---
name: departments
description: >
  On-demand MECE department view (ADR-028 placement data), rendered in-chat.
  Fires on "give me / show me the (various|relevant) departments|domains",
  "departments around <thing>", or /departments. Two modes: whole-tree weight
  view (no anchor) and neighborhood view (anchored on a named thing or the
  current turn's PLACEMENT). LLM-rendered v1 per founder direction 2026-07-30
  ("go LLM-driven, ship, harden later"); deterministic engine renderer is the
  v2 hardening path.
---

# departments — the on-demand MECE view

## What this is

The founder asks in natural language; you render the domain/charter registry
as an org-chart-style block layout, in-chat, terminal-first. Nothing is
always-shown: this fires ONLY when asked (founder 2026-07-30: "you don't need
to show it... if I ask, you can do it on the fly").

## Data source (never invent the data)

All numbers come from the placement engine — LLM draws, engine counts:

```bash
ENG="$(ls -d ~/.claude/plugins/cache/sutra/core/*/ | sort -V | tail -1)lib/placement_engine.py"
python3 "$ENG" tree          # domains: ref, path, name
python3 "$ENG" stats         # totals
python3 "$ENG" mece          # violations count
# work-unit counts: last row per work_ref in $SUTRA_NATIVE_HOME/placements/CURRENT.jsonl
```

If the registry is empty, run a throwaway scan first and SAY SO in the footer
("registry derived live from a scan; persistent registry not yet populated"):

```bash
export SUTRA_NATIVE_HOME=$(mktemp -d)/user-kit
python3 "$ENG" scan "$PWD" >/dev/null
```

Never fabricate a department, a count, or a charter title. If the engine gives
nothing, say so plainly.

## Render contract (both modes)

- Inside ONE code block. ASCII only (D-UX-1) — never unicode box-drawing,
  never a markdown table with HTML entities (founder: "not showing
  beautifully", 2026-07-30).
- MECE discipline: every department appears exactly once; parents show
  SUBTREE totals (children included); sort by weight descending.
- One CLI screen target (~40 lines max). Collapse any group with >6 children
  to its top 3 + "+N more".
- `#` bars scaled to the heaviest department; percentages of total units.

## Mode A — whole tree ("show me the various departments")

Layout: full-width header bar, then department boxes PAIRED TWO-ACROSS
cascading down the screen (founder: "two blocks on top and below, below,
below"), then a full-width footer.

Each box (inner width ~30): line 1 `PATH NAME  <units>  <pct>` ·
line 2 bar · line 3 children summary (or "no children").

## Mode B — neighborhood ("departments around <thing>")

Resolve the anchor via `python3 "$ENG" classify "<thing>" [path...]`; if
nothing is named, anchor on the current turn's PLACEMENT. Render: ancestor
chain with `<== YOU ARE HERE`, siblings at that level, children below.

## v2 hardening (deferred by founder, on record)

Move the drawing into `placement_engine.py orgchart` (pure function +
golden-file test) so all surfaces emit byte-identical output; this SKILL then
presents verbatim instead of drawing. Do that when render drift or fleet
inconsistency is observed — not before.
