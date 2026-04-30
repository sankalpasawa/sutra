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

Ordering is documented in SKILL.md description (`AFTER input-routing`); explicit hook wiring in settings.json deferred to v1.1 if auto-discovery proves insufficient.

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
