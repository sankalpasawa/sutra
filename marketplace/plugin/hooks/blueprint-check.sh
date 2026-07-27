#!/bin/bash
# blueprint-check.sh — BLUEPRINT block enforcement (codex round-5 narrowed scope)
#
# Charter: sutra/os/engines/BLUEPRINT-ENGINE.md
# Skill:   sutra/marketplace/plugin/skills/blueprint/SKILL.md
# Event:   PreToolUse on Edit|Write
# Enforcement (updated per #68, 2026-07-06 — was stale, claimed SOFT while shipping HARD):
#   - FOUNDATIONAL paths: HARD — require the marker + HAS_OUTPUT=1 + HAS_VERIFY=1 (D48).
#   - Non-foundational paths: HARD at DEPTH>=3 (require the marker); DEPTH<=2 is EXEMPT
#     (#68 D4 — cheap typo/one-line edits carry no pre-spend BLUEPRINT ceremony).
#     Depth unknown/unparseable -> fail-closed to require (D5 default).
#   The 2026-05-10 blanket SOFT->HARD flip (Option A) is real; #68 D4 adds the
#   depth gate so the tax lands only where pre-spend visibility is worth it.
#
# Why narrower than build-layer-check.sh:
#   build-layer-check.sh already HARD-blocks holding/hooks/**,
#   sutra/marketplace/plugin/**, sutra/os/charters/**, holding/departments/**
#   without .claude/build-layer-registered. A second HARD marker on the same
#   paths is redundant friction. BLUEPRINT fires on a NARROWER set: charters,
#   protocols, design docs, founder directions, plans — places where
#   pre-spend visibility (showing the plan before spending tokens) matters
#   most.
#
# Codex round 5 corrections:
#   - Scope narrowed to foundational doc paths only (no overlap with
#     build-layer-check on code paths).
#   - V1 kill-switch is env + fs ONLY — no fake SUTRA-CONFIG.md flag claim.
#   - Soft mode on BUILD-LAYER-hard paths (avoid double-block UX).
#
# Marker: .claude/blueprint-registered (set when emit-blueprint skill fires)
# Override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool-call>
# Kill-switch (2-level V1):
#   - BLUEPRINT_DISABLED=1 (per-shell)
#   - ~/.blueprint-disabled (per-machine)

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

# ── Kill-switches (2-level, per codex round 5; no fake fleet flag) ──
[ -n "${BLUEPRINT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.blueprint-disabled" ] && exit 0

# ── Override path ──
if [ "${BLUEPRINT_ACK:-0}" = "1" ]; then
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  REASON=$(printf '%s' "${BLUEPRINT_ACK_REASON:-no-reason}" | tr -d '\n\r' | head -c 500)
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  printf '{"ts":"%s","event":"blueprint-override","reason":"%s"}\n' \
    "$TS" "$REASON" >> "$REPO_ROOT/.enforcement/blueprint-ledger.jsonl"
  exit 0
fi

# ── Parse target file_path from PreToolUse stdin JSON ──
PAYLOAD=$(cat 2>/dev/null || true)
FILE_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="$TOOL_INPUT_file_path"
[ -z "$FILE_PATH" ] && exit 0

# ── Out-of-repo guard (2026-07-08, Testlify field incident) ──
# Absolute paths OUTSIDE $REPO_ROOT never strip below, so REL_PATH stays
# absolute and NO whitelist/foundational pattern can match — the hook then
# HARD-blocks files it was never scoped to govern (~/.claude/** memory files,
# sibling repos, user documents). Repo governance ends at the repo boundary.
case "$FILE_PATH" in
  "$REPO_ROOT"/*) ;;   # inside repo — governed
  /*) exit 0 ;;        # absolute path outside repo — out of scope
esac
REL_PATH="${FILE_PATH#$REPO_ROOT/}"

# ── FOUNDATIONAL paths (HARD-block without marker) ──
# Narrower than build-layer-check.sh — only doc artifacts where pre-spend
# blueprint visibility matters most.
case "$REL_PATH" in
  sutra/os/charters/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/protocols/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/PROTOCOLS.md) is_foundational=1 ;;
  holding/FOUNDER-DIRECTIONS.md) is_foundational=1 ;;
  holding/research/*-design.md|holding/research/*-plan.md) is_foundational=1 ;;
  sutra/os/engines/*.md) is_foundational=1 ;;
  *) is_foundational=0 ;;
esac

# ── Whitelist (exempt regardless of foundational class) ──
case "$REL_PATH" in
  *.lock|*.log|*.jsonl) exit 0 ;;
  .claude/*|.enforcement/*|.analytics/*) exit 0 ;;
  */TODO.md|*/BACKLOG.md|*/CHANGELOG.md|*/MEMORY.md) exit 0 ;;
  holding/checkpoints/*) exit 0 ;;
  sutra/archive/*) exit 0 ;;
esac

MARKER="$REPO_ROOT/.claude/blueprint-registered"

# ── V2.2 (2026-05-10): D3+ per-step Verify check (L1 of 3-Layer Stack) ──
# Founder direction "force it" — per-step Verify enforced at D3+.
# Marker must declare HAS_PER_STEP_VERIFY=1 (set when model emits BLUEPRINT
# with inline `Verify:` on each step in the Steps list per skill V2.1).
# Composes with existing HAS_OUTPUT/HAS_VERIFY checks. Bootstrap rule:
# marker is wiped per-turn by reset-turn-markers; model must emit BLUEPRINT
# with per-step Verify before first Edit/Write of every D3+ turn.
if [ -f "$MARKER" ]; then
  DEPTH_FILE="$REPO_ROOT/.claude/depth-registered"
  # Fail-closed depth detection (codex P1.1 fold, round-1 CHANGES-REQUIRED 2026-05-10):
  # If depth marker is missing, malformed, or unparseable as integer → default to D5.
  # Rationale: hard enforcement gate cannot silently downgrade on "unknown depth"
  # or every malformed marker becomes a fail-open bypass.
  DEPTH=""
  if [ -f "$DEPTH_FILE" ]; then
    # End-anchored regex (codex R2 P1 fold): require entire line matches
    # DEPTH=<digits> with no trailing junk. Prior `^DEPTH=[0-9]+` matched
    # `DEPTH=3garbage` as `3` — fail-open class. Now `DEPTH=3junk` produces
    # no match → DEPTH="" → integer-shape check below routes to D5 default.
    # Strict full-line shape validation (codex R3 P1 fold):
    # Two accepted forms, both end-anchored — NO trailing junk permitted.
    # Form A (canonical single-line per CLAUDE.md): `DEPTH=N TASK=<slug> TS=<unix>`
    # Form B (multi-line single-token):              `DEPTH=N` on its own line
    # Prior boundary-only regex still parsed `DEPTH=3 junk`, `DEPTH=3 TASK=`,
    # and `DEPTH=3<TAB>garbage` as `3` — same fail-open class. R3 fold rejects
    # anything that does not match one of the two canonical shapes exactly.
    DEPTH=""
    _DEPTH_LINE_A=$(grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' "$DEPTH_FILE" 2>/dev/null | head -1)
    if [ -n "$_DEPTH_LINE_A" ]; then
      DEPTH=$(printf '%s' "$_DEPTH_LINE_A" | sed -E 's/^DEPTH=([0-9]+).*$/\1/')
    else
      _DEPTH_LINE_B=$(grep -E '^DEPTH=[0-9]+$' "$DEPTH_FILE" 2>/dev/null | head -1)
      if [ -n "$_DEPTH_LINE_B" ]; then
        DEPTH=$(printf '%s' "$_DEPTH_LINE_B" | sed -E 's/^DEPTH=([0-9]+)$/\1/')
      fi
    fi
  fi
  # Integer-shape check (no error suppression — explicit)
  case "$DEPTH" in
    ''|*[!0-9]*)
      DEPTH=5  # unparseable / missing / non-integer → strictest default
      echo "blueprint-check V2.2: depth marker unparseable or missing, defaulting to D5 (fail-closed per codex P1.1)" >&2
      ;;
  esac
  if [ "$DEPTH" -ge 3 ]; then
    HAS_PER_STEP=0
    grep -q '^HAS_PER_STEP_VERIFY=1$' "$MARKER" 2>/dev/null && HAS_PER_STEP=1
    if [ "$HAS_PER_STEP" = "0" ]; then
      {
        echo "BLUEPRINT-CHECK V2.2: D${DEPTH} requires per-step Verify in BLUEPRINT Steps."
        echo "  File: $REL_PATH"
        echo "  Emit BLUEPRINT Steps with inline 'Verify:' on each step (V2.1 format)."
        echo "  Then set HAS_PER_STEP_VERIFY=1 in .claude/blueprint-registered marker."
        echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
      } >&2
      exit 2
    fi
  fi
fi

if [ "$is_foundational" = "1" ]; then
  # HARD on foundational paths
  if [ ! -f "$MARKER" ]; then
    {
      echo "BLUEPRINT-CHECK: foundational artifact edit requires a BLUEPRINT block."
      echo "  File: $REL_PATH"
      echo "  Emit a per-task BLUEPRINT block with 'Output looks like' + 'Verified by'."
      echo "  Format: the core:blueprint skill (SKILL.md) / SUTRA-DEFAULTS.md."
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
  # D48 (2026-05-05): foundational edits require Output + Verified-by fields.
  # Marker must declare HAS_OUTPUT=1 + HAS_VERIFY=1 (model writes these when
  # emitting BLUEPRINT with the new lines per skills/blueprint/SKILL.md).
  # Use grep -q (exit-code only) — grep -c with || echo 0 fallback double-emits
  # "0" when no match (grep outputs "0" AND fallback echo runs), making string
  # compare unreliable. Iteration-1 fix during D48 ship (test cases [3] [4]).
  HAS_OUTPUT=0
  HAS_VERIFY=0
  grep -q '^HAS_OUTPUT=1$' "$MARKER" 2>/dev/null && HAS_OUTPUT=1
  grep -q '^HAS_VERIFY=1$' "$MARKER" 2>/dev/null && HAS_VERIFY=1
  if [ "$HAS_OUTPUT" = "0" ] || [ "$HAS_VERIFY" = "0" ]; then
    {
      echo "BLUEPRINT-CHECK: foundational edit requires BLUEPRINT with"
      echo "  'Output looks like:' AND 'Verified by:' fields (D48, 2026-05-05)."
      echo "  File: $REL_PATH"
      echo "  Marker flags: HAS_OUTPUT=$HAS_OUTPUT HAS_VERIFY=$HAS_VERIFY (need both =1)"
      echo "  Re-emit BLUEPRINT with both lines + update marker."
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
else
  # Non-foundational path. HARD only at DEPTH>=3 (#68 D4, 2026-07-06). Cheap
  # D<=2 edits (typo / single-line / config tweak) are EXEMPT — they carry no
  # pre-spend BLUEPRINT ceremony (~4.2k tokens/day of pure tax removed). Depth is
  # read fail-closed (missing/malformed -> D5) so an unknown depth still requires
  # the block. The 2026-05-10 SOFT->HARD flip (Option A) stands; D4 only narrows
  # WHERE the tax lands. Foundational paths (above) always require it, any depth.
  _NFD="$REPO_ROOT/.claude/depth-registered"; NF_DEPTH=""
  if [ -f "$_NFD" ]; then
    _a=$(grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' "$_NFD" 2>/dev/null | head -1)
    if [ -n "$_a" ]; then NF_DEPTH=$(printf '%s' "$_a" | sed -E 's/^DEPTH=([0-9]+).*$/\1/');
    else
      _b=$(grep -E '^DEPTH=[0-9]+$' "$_NFD" 2>/dev/null | head -1)
      [ -n "$_b" ] && NF_DEPTH=$(printf '%s' "$_b" | sed -E 's/^DEPTH=([0-9]+)$/\1/')
    fi
  fi
  case "$NF_DEPTH" in ''|*[!0-9]*) NF_DEPTH=5 ;; esac   # fail-closed to strictest
  if [ "$NF_DEPTH" -le 2 ]; then
    exit 0   # #68 D4: cheap edit — exempt from the BLUEPRINT tax
  fi
  if [ ! -f "$MARKER" ]; then
    {
      echo "BLUEPRINT-CHECK: Edit/Write at D${NF_DEPTH} requires a BLUEPRINT block."
      echo "  File: $REL_PATH"
      echo "  Emit a per-task BLUEPRINT block (Doing / Steps / Scale / Stops-if / Switch)."
      echo "  Format: the core:blueprint skill (SKILL.md) / SUTRA-DEFAULTS.md."
      echo "  (D<=2 edits are exempt; 'Output looks like' + 'Verified by' are required"
      echo "   only on FOUNDATIONAL paths, not here.)"
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
fi

exit 0

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Logged to .enforcement/blueprint-ledger.jsonl on override events.
# Hook fires counted in holding/hooks/hook-log.jsonl (via standard logger).
#
# ### 2. Adoption mechanism
# Registered in .claude/settings.json under PreToolUse Edit|Write.
# Holding-only at L1 staging; promote to plugin after 30d clean operation.
#
# ### 3. Monitoring / escalation
# Override rate from blueprint-ledger.jsonl reviewed weekly.
# >30% override rate over 7d = soften the rule or narrow paths further.
#
# ### 4. Iteration trigger
# Founder correction on a missed-block fire OR override-rate breach.
#
# ### 5. DRI
# Sutra-OS (Asawa-CEO). Operator: any session running in asawa-holding.
#
# ### 6. Decommission criteria
# Replaced by an in-LLM behavioral discipline that emits the block reliably
# without need for hook enforcement. Or: charter retirement (BLUEPRINT
# subsumed into a different engine).
