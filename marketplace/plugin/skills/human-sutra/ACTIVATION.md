# H↔Sutra Layer v1.0 — Activation Status

**Date**: 2026-05-01
**Skill**: `human-sutra`
**Charter**: `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (commit f65725a)

## Activation mechanism

This skill auto-discovers via the Claude Code plugin runtime — no `plugin.json` edit required (plugin manifest has no explicit `skills` field per INVENTORY.md). The skill activates when its description matches the user's intent (every UserPromptSubmit).

## Hook ordering

Skill ordering on `UserPromptSubmit`:

1. `input-routing` — emits TYPE/HOME/ROUTE/FIT/ACTION block
2. **`human-sutra`** ← this skill (consumes input-routing's TYPE)
3. `blueprint` — emits per-task plan preview

Explicit ordering ships in `sutra/marketplace/plugin/hooks.json` (top-level) under
`ordering.UserPromptSubmit.human-sutra` with `after: ["input-routing"]` and
`before: ["blueprint"]`. SKILL.md description also documents the constraint as a
secondary signal. Note: the active runtime command-hook registry lives at
`hooks/hooks.json` (PreToolUse / PostToolUse / SessionStart / Stop) — that's a
separate concern from skill ordering.

If a future Claude Code version exposes `settings.json` skill-ordering wiring
that supersedes top-level `hooks.json`, the registry migrates there with an
ADR-NNN. Current shape is the explicit ordering surface for v1.0.

## Smoke verification

```bash
echo "what is X?" | bash sutra/marketplace/plugin/skills/human-sutra/scripts/classify.sh | jq -r .verb
# Expected: QUERY

echo "push to origin" | bash sutra/marketplace/plugin/skills/human-sutra/scripts/classify.sh | jq -r .reversibility
# Expected: irreversible
```

Both smoke checks PASS as of Task 2.3 (commit 7a32af4).

## Known v1.0 limits

- Classifier accuracy ~77% on the 13-fixture regression set (3/6 TDD-red tests fully green; 3 partial). Catalogued for v1.1 ADR-002 fold:
  - Stage-1 gate ordering bug (overrides IR_TYPE-derived verb)
  - DIRECT verb regex too narrow (missing `redesign`, `stimulate`, `simulate`, `remind`)
  - DIRECT regex too wide on auxiliary "do"
  - Mixed-act precedence undertested

These are accuracy refinements; v1.0 ships the architecture + plumbing, not classifier perfection.
