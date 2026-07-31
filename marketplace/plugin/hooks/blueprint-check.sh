#!/bin/bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/blueprint-check.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-07-27
#
# blueprint-check.sh — BLUEPRINT enforcement, TEXT-FIRST (v3, 2026-07-27)
#
# Charter: sutra/os/engines/BLUEPRINT-ENGINE.md
# Skill:   sutra/marketplace/plugin/skills/blueprint/SKILL.md
# Event:   PreToolUse on Edit|Write
#
# WHAT CHANGED IN v3 (#68 + the 2026-07-08 Testlify field incident)
# -----------------------------------------------------------------
# v1/v2 read ONLY the .claude/blueprint-registered marker. A model could emit a
# perfect, complete BLUEPRINT in the response the USER reads and still be
# HARD-blocked, because the gate was never looking at the response. Three field
# incidents came out of that single divergence:
#   #68  (2026-05-23) "HARD-blocks every Edit"      — the tax, unfixed
#   #80  (2026-07-08) Testlify: model re-emitted a correct block twice, was
#                     blocked twice, then routed the write through Bash with
#                     BLUEPRINT_ACK — a full gate bypass the error text taught
#   (2026-07-27)      same loop, third occurrence
# #80 patched the *reminder* so the model would know to print the receipt. This
# hook instead removes the receipt from the contract:
#
#   1. TEXT-FIRST — validates the BLUEPRINT block in the CURRENT TURN'S TEXT
#      (the block the user actually sees). Same source of truth the D63 Stop
#      floor (per-turn-hard-gate.sh) already uses for Input Routing + Depth.
#      Validator ported from PR #73 (Manoranjan Baral) — credit retained.
#   2. MARKER IS NOW A CACHE, NOT A CONTRACT — this hook writes
#      .claude/blueprint-registered itself after a passing validation, so a
#      multi-Edit turn pays one transcript walk, not N. The model is never
#      asked to write it. reset-turn-markers.sh still wipes it per turn.
#      Best-effort: a failed cache write costs a re-validation, never a block.
#      2026-07-30 (marker-race fix): the cache is read AND written via
#      marker-lib — session dir .claude/sessions/<sid>/, self-only adoption,
#      SESSION-stamped on write — so one session's cache (or depth marker) can
#      no longer satisfy or corrupt a concurrent session's gate. Legacy path
#      fallback only when the lib is unavailable.
#   3. PRETOOL SCOPE = FOUNDATIONAL ONLY — restores the codex round-5 scoping
#      that the 2026-05-10 blanket SOFT->HARD flip erased. Ordinary files are
#      floored at Stop by per-turn-hard-gate.sh (one redo, loop-safe), the same
#      guarantee D63 already accepts for the other Class-A blocks. Supersedes
#      #78's depth gate: no gate at all on ordinary files beats a gated tax.
#   4. FOUNDATIONAL LIST IS CONFIGURABLE — it used to be six hardcoded paths
#      from the Asawa repo layout (sutra/os/charters/**, holding/FOUNDER-
#      DIRECTIONS.md, ...). No fleet client has those paths, so for every
#      install except Asawa's the "important documents" set was empty. Now:
#        .claude/sutra-project.json  .blueprint_foundational_paths[]   (project)
#        sutra-defaults.json         .per_turn_blocks.blueprint
#                                      .foundational_paths[]           (plugin)
#        hardcoded list                                                (fallback)
#
# Enforcement:
#   - FOUNDATIONAL paths: HARD. Requires a valid BLUEPRINT in the turn text with
#     a non-empty Doing:, a concrete 'Output looks like:', a runnable
#     'Verified by:', and (at DEPTH>=3) an inline 'Verify:' on every numbered
#     Step. Unchanged in substance from D48 + V2.2 — only the source moved from
#     marker flags to the emitted text.
#   - Non-foundational paths: this hook exits 0. per-turn-hard-gate.sh floors
#     BLUEPRINT at Stop for any turn that mutated a governed file.
#
# Degradation: if the transcript cannot be read (no python3 / no jq / no
# transcript_path), the gate falls back to the LEGACY marker check on
# foundational paths rather than failing open — a HARD gate on governing
# documents should not evaporate because a host lacks python3.
#
# Override:    BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool-call>
# Kill-switch: BLUEPRINT_DISABLED=1  |  ~/.blueprint-disabled

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

# ── Parse target file_path + transcript_path from PreToolUse stdin JSON ──
PAYLOAD=$(cat 2>/dev/null || true)
FILE_PATH=""
TRANSCRIPT_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  TRANSCRIPT_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="$TOOL_INPUT_file_path"
[ -z "$FILE_PATH" ] && exit 0

# ── Session-scoped marker resolution (2026-07-30 marker-race fix) ──
# Sourced defensively (flow-gate.sh pattern): on lib failure degrade to the
# legacy path — the gate must never block because its infrastructure errored.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  . "$_MARKER_LIB" 2>/dev/null || true
  command -v sutra_sid_from_stdin >/dev/null 2>&1 && { sutra_sid_from_stdin "$PAYLOAD" || true; }
fi
_bp_marker_read() {
  if command -v sutra_marker_read >/dev/null 2>&1; then
    sutra_marker_read "$1" 2>/dev/null; return $?
  fi
  # lib missing: legacy global (fail-open on infrastructure, not on discipline)
  cat "$REPO_ROOT/.claude/$1" 2>/dev/null
}

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

# ── Whitelist (exempt regardless of foundational class) ──
case "$REL_PATH" in
  *.lock|*.log|*.jsonl) exit 0 ;;
  .claude/*|.enforcement/*|.analytics/*) exit 0 ;;
  */TODO.md|*/BACKLOG.md|*/CHANGELOG.md|*/MEMORY.md) exit 0 ;;
  holding/checkpoints/*) exit 0 ;;
  sutra/archive/*) exit 0 ;;
esac

# ── FOUNDATIONAL path set (config-driven; see header note 4) ──
# Precedence: project config > plugin defaults > hardcoded fallback.
# One glob per entry — `|` alternation is NOT re-parsed out of a variable in a
# case pattern, so each alternative must be its own array element.
DEFAULT_FOUNDATIONAL='sutra/os/charters/*.md
sutra/layer2-operating-system/protocols/*.md
sutra/layer2-operating-system/PROTOCOLS.md
holding/FOUNDER-DIRECTIONS.md
holding/research/*-design.md
holding/research/*-plan.md
sutra/os/engines/*.md'

FOUNDATIONAL_PATTERNS=""
if command -v jq >/dev/null 2>&1; then
  PROJECT_JSON="$REPO_ROOT/.claude/sutra-project.json"
  if [ -f "$PROJECT_JSON" ]; then
    FOUNDATIONAL_PATTERNS=$(jq -r '.blueprint_foundational_paths // [] | .[]' "$PROJECT_JSON" 2>/dev/null)
  fi
  if [ -z "$FOUNDATIONAL_PATTERNS" ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] \
     && [ -f "$CLAUDE_PLUGIN_ROOT/sutra-defaults.json" ]; then
    FOUNDATIONAL_PATTERNS=$(jq -r '.per_turn_blocks.blueprint.foundational_paths // [] | .[]' \
      "$CLAUDE_PLUGIN_ROOT/sutra-defaults.json" 2>/dev/null)
  fi
fi
[ -z "$FOUNDATIONAL_PATTERNS" ] && FOUNDATIONAL_PATTERNS="$DEFAULT_FOUNDATIONAL"

is_foundational=0
while IFS= read -r _pat; do
  [ -z "$_pat" ] && continue
  case "$REL_PATH" in
    $_pat) is_foundational=1; break ;;
  esac
done <<EOF
$FOUNDATIONAL_PATTERNS
EOF

# ── Ordinary files: this hook is done. Stop floor owns them. ──
# per-turn-hard-gate.sh (Stop, D63) requires a BLUEPRINT in the turn text on any
# turn that mutated a governed file, and forces exactly one redo if it is
# missing. Keeping a second PreToolUse block here would double-gate the same
# contract — the exact shape #73-alongside-#78 would have shipped.
[ "$is_foundational" = "1" ] || exit 0

MARKER="$REPO_ROOT/.claude/blueprint-registered"

# ── Depth (fail-closed to 5 — unchanged from v2, codex R2/R3 folds) ──
# Two accepted shapes, both end-anchored, no trailing junk:
#   Form A: `DEPTH=N TASK=<slug> TS=<unix>`   Form B: `DEPTH=N`
# Anything else -> DEPTH=5 (strictest). A malformed marker must never be a
# fail-open bypass. Read session-scoped via marker-lib: a FOREIGN session's
# depth marker is a miss -> DEPTH=5, same fail-closed branch as a missing file.
DEPTH_CONTENT="$(_bp_marker_read depth-registered)" || DEPTH_CONTENT=""
DEPTH=""
if [ -n "$DEPTH_CONTENT" ]; then
  _A=$(printf '%s\n' "$DEPTH_CONTENT" | grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' 2>/dev/null | head -1)
  if [ -n "$_A" ]; then
    DEPTH=$(printf '%s' "$_A" | sed -E 's/^DEPTH=([0-9]+).*$/\1/')
  else
    _B=$(printf '%s\n' "$DEPTH_CONTENT" | grep -E '^DEPTH=[0-9]+$' 2>/dev/null | head -1)
    [ -n "$_B" ] && DEPTH=$(printf '%s' "$_B" | sed -E 's/^DEPTH=([0-9]+)$/\1/')
  fi
fi
case "$DEPTH" in ''|*[!0-9]*) DEPTH=5 ;; esac

# ── Per-turn cache read (session-scoped) + cache hit ──
BP_CACHE=""
BP_CACHE_PRESENT=0
if BP_CACHE="$(_bp_marker_read blueprint-registered)"; then
  BP_CACHE_PRESENT=1
fi
if [ "$BP_CACHE_PRESENT" = "1" ] && printf '%s\n' "$BP_CACHE" | grep -q '^VALIDATED_FROM=text$' 2>/dev/null; then
  exit 0
fi

legacy_marker_check() {
  # Degradation path only (no transcript / no python3). Pre-v3 semantics.
  if [ "$BP_CACHE_PRESENT" != "1" ]; then
    {
      echo "BLUEPRINT-CHECK: foundational artifact edit requires a BLUEPRINT block."
      echo "  File: $REL_PATH"
      echo "  (Degraded mode: transcript unreadable, falling back to the marker check.)"
      echo "  Emit a BLUEPRINT with 'Output looks like:' + 'Verified by:', then write"
      echo "  .claude/blueprint-registered with HAS_OUTPUT=1 / HAS_VERIFY=1."
      echo "  Format: the core:blueprint skill (SKILL.md) / SUTRA-DEFAULTS.md."
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
  HAS_OUTPUT=0; HAS_VERIFY=0
  printf '%s\n' "$BP_CACHE" | grep -q '^HAS_OUTPUT=1$' 2>/dev/null && HAS_OUTPUT=1
  printf '%s\n' "$BP_CACHE" | grep -q '^HAS_VERIFY=1$' 2>/dev/null && HAS_VERIFY=1
  if [ "$HAS_OUTPUT" = "0" ] || [ "$HAS_VERIFY" = "0" ]; then
    {
      echo "BLUEPRINT-CHECK: foundational edit requires 'Output looks like:' AND"
      echo "  'Verified by:' (D48). Marker flags: HAS_OUTPUT=$HAS_OUTPUT HAS_VERIFY=$HAS_VERIFY"
      echo "  File: $REL_PATH  (degraded mode: transcript unreadable)"
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
  if [ "$DEPTH" -ge 3 ] && ! printf '%s\n' "$BP_CACHE" | grep -q '^HAS_PER_STEP_VERIFY=1$' 2>/dev/null; then
    {
      echo "BLUEPRINT-CHECK: D${DEPTH} requires an inline 'Verify:' on every Step."
      echo "  File: $REL_PATH  (degraded mode: transcript unreadable)"
      echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
    } >&2
    exit 2
  fi
  exit 0
}

if ! command -v python3 >/dev/null 2>&1 \
   || [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  legacy_marker_check
fi

# ── TEXT validation of the BLUEPRINT the user sees ──
# Ported from PR #73 (Manoranjan Baral), blueprint-text-validate.sh. Turn-text
# extraction matches per-turn-hard-gate.sh: everything
# after the last HUMAN user row (isMeta and tool_result rows are not human).
VERDICT=$(TRANSCRIPT_FOR_PY="$TRANSCRIPT_PATH" BP_DEPTH="$DEPTH" python3 -c '
import os, sys, json, re

p = os.environ["TRANSCRIPT_FOR_PY"]
depth = int(os.environ.get("BP_DEPTH", "5") or "5")

TRIVIAL = {"", "works", "passes", "done", "no errors", "it runs",
           "looks good", "tested", "verified", "na", "n/a", "tbd", "todo", "-"}

rows = []
try:
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except Exception: pass
except Exception:
    print("skip\tno_transcript"); sys.exit(0)

def is_human_user(r):
    if r.get("role") != "user" and r.get("type") != "user":
        return False
    if r.get("isMeta") is True:
        return False
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, str): return True
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                return False
        return True
    return False

last_user = -1
for i, r in enumerate(rows):
    if is_human_user(r):
        last_user = i

texts = []
for r in rows[last_user+1:]:
    if r.get("role") != "assistant" and r.get("type") != "assistant":
        continue
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                texts.append(b["text"])
    elif isinstance(content, str) and content:
        texts.append(content)
turn_text = "\n".join(texts)

if not turn_text.strip():
    print("skip\tno_text_in_turn"); sys.exit(0)

def declutter(line):
    # Strip ASCII-box pipes AND markdown list markers. The canonical emitted
    # shape in CLAUDE.md / SKILL.md is a bulleted list ("- Doing: ..."), which
    # the pre-v3 field regexes (anchored at ^Doing) never matched.
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    s = re.sub(r"\s*\|\s*$", "", s)
    s = s.strip()
    s = re.sub(r"^[-*•]\s+", "", s)     # "- Doing:" -> "Doing:" ("+---+" untouched)
    s = re.sub(r"^\*\*(.+?)\*\*", r"\1", s)  # "**Doing**: x" -> "Doing: x"
    return s.strip()

src = turn_text.splitlines()

def _heading_is_blueprint(raw):
    s = re.sub(r"[#*|>_`\s-]", "", raw).upper()
    return s == "BLUEPRINT"

# Detection is deliberately tolerant of three shapes — ASCII box, markdown
# heading, or bare field-set — because v2 false-blocked valid variants.
start = None
for i, raw in enumerate(src):
    if "BLUEPRINT" in raw and "+--" in raw:
        start = i; break
if start is None:
    for i, raw in enumerate(src):
        if "BLUEPRINT" in raw.upper() and _heading_is_blueprint(raw):
            start = i; break
if start is None:
    doing_idx = None
    has_out = False
    for i, raw in enumerate(src):
        d = declutter(raw)
        if doing_idx is None and re.match(r"^Doing\b[^:]*:", d, re.IGNORECASE):
            doing_idx = i
        if re.match(r"^(Output looks like|Verified by)\b[^:]*:", d, re.IGNORECASE):
            has_out = True
    if doing_idx is not None and has_out:
        start = doing_idx

if start is None:
    print("missing\tno BLUEPRINT block found in this turn'"'"'s response text"); sys.exit(0)

end = len(src)
for j in range(start+1, len(src)):
    if re.match(r"^\s*\+-{3,}\+?\s*$", src[j]):
        end = j; break
block = [declutter(l) for l in src[start:end+1]]

def field(name):
    pat = re.compile(r"^%s\b[^:]*:\s*(.*)$" % re.escape(name), re.IGNORECASE)
    for l in block:
        m = pat.match(l)
        if m: return m.group(1).strip()
    return None

def is_trivial(v):
    if v is None: return True
    norm = re.sub(r"[^a-z0-9 /]", "", v.lower()).strip()
    if norm in TRIVIAL: return True
    if len(norm) < 4: return True
    return False

doing = field("Doing")
if doing is None or len(doing.strip()) == 0:
    print("bad_doing\tBLUEPRINT block has no non-empty Doing: line"); sys.exit(0)

out = field("Output looks like")
if out is None:
    print("missing_output\tBLUEPRINT block missing an Output looks like: field"); sys.exit(0)
if is_trivial(out):
    print("trivial_output\tOutput looks like: is empty or trivial (\"%s\")" % out[:60]); sys.exit(0)

vby = field("Verified by")
if vby is None:
    print("missing_verify\tBLUEPRINT block missing a Verified by: field"); sys.exit(0)
if is_trivial(vby):
    print("trivial_verify\tVerified by: is trivial (\"%s\") -- name a runnable check" % vby[:60]); sys.exit(0)

if depth >= 3:
    # Steps come in two shapes: one "Steps: 1) a 2) b" line, or one line per
    # step. Segment both, then require an inline Verify: on each.
    segs = []
    for l in block:
        m = re.match(r"^Steps\b[^:]*:\s*(.*)$", l, re.IGNORECASE)
        if m and m.group(1).strip():
            for part in re.split(r"(?=\b\d+\))", m.group(1)):
                part = part.strip()
                if re.match(r"^\d+\)", part): segs.append(part)
            break
    for l in block:
        if re.match(r"^\d+\)", l): segs.append(l)
    if segs:
        bad = [s for s in segs if not re.search(r"\bVerify:\s*\S", s, re.IGNORECASE)]
        if bad:
            print("missing_step_verify\tD%d: a Step carries no inline Verify: -> \"%s\"" % (depth, bad[0][:60])); sys.exit(0)

print("ok\tvalid"); sys.exit(0)
' 2>/dev/null)

STATUS="${VERDICT%%	*}"
MESSAGE="${VERDICT#*	}"

case "$STATUS" in
  ok)
    # Cache the pass for the rest of this turn (best-effort; wiped by
    # reset-turn-markers.sh on the next UserPromptSubmit). A failed write costs
    # one extra transcript walk on the next Edit — never a block.
    # 2026-07-30: written via sutra_marker_write (session dir + SESSION stamp +
    # dual-written legacy twin while migration flags are on) so a concurrent
    # session can neither consume nor clobber this session's cache.
    mkdir -p "$REPO_ROOT/.claude" 2>/dev/null
    _BP_BODY=$(
      printf 'VALIDATED_FROM=text\n'
      printf 'HAS_OUTPUT=1\nHAS_VERIFY=1\n'
      [ "$DEPTH" -ge 3 ] && printf 'HAS_PER_STEP_VERIFY=1\n'
      printf 'DEPTH=%s\nTS=%s' "$DEPTH" "$(date +%s)"
    )
    if command -v sutra_marker_write >/dev/null 2>&1; then
      sutra_marker_write blueprint-registered "$_BP_BODY" 2>/dev/null || true
    else
      printf '%s\n' "$_BP_BODY" > "$MARKER" 2>/dev/null
    fi
    exit 0
    ;;
  skip|"")
    # Could not identify the turn's text (compaction, empty transcript). Do not
    # invent a violation out of a parsing gap — fall back to the marker.
    legacy_marker_check
    ;;
esac

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
printf '{"ts":"%s","violation":"blueprint_text_invalid","reason_code":"%s","layer":"blueprint-check-v3","file":"%s","action":"pretool_blocked"}\n' \
  "$NOW" "$STATUS" "$REL_PATH" >> "$REPO_ROOT/.enforcement/governance-violations.jsonl" 2>/dev/null

{
  echo "BLUEPRINT-CHECK: foundational edit — the BLUEPRINT in this turn's response"
  echo "  did not validate. This reads the block the USER sees, not a marker file."
  echo "  File: $REL_PATH"
  echo "  Problem: $MESSAGE"
  echo "  Fix: re-emit the BLUEPRINT with a non-empty 'Doing:', a concrete"
  echo "       'Output looks like:', and a 'Verified by:' naming a RUNNABLE check"
  echo "       (shell test / typecheck / grep / file-exists / curl) — not 'works'."
  echo "       At D3+, every numbered Step needs an inline 'Verify:'."
  echo "  Format: the core:blueprint skill (SKILL.md) / SUTRA-DEFAULTS.md."
  echo "  Or override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
} >&2
exit 2

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Overrides -> .enforcement/blueprint-ledger.jsonl.
# Text-validation failures -> .enforcement/governance-violations.jsonl with a
# reason_code, so the failure MODE (missing block vs trivial Verified-by vs
# missing per-step Verify) is countable — v1/v2 logged only overrides, which is
# why no data existed to defend or retire the gate.
#
# ### 2. Adoption mechanism
# Registered in hooks.json under PreToolUse Edit|Write. Ships L0, fleet-wide.
#
# ### 3. Monitoring / escalation
# Weekly: override rate + reason_code histogram. >30% override rate over 7d, or
# a reason_code dominated by one false-positive shape = narrow or soften.
#
# ### 4. Iteration trigger
# A founder correction on a missed-block fire, an override-rate breach, or any
# repeat of the bypass-teaching incident class (#80).
#
# ### 5. DRI
# Sutra-OS (Asawa-CEO). Operator: any session running with the plugin.
#
# ### 6. Decommission criteria
# The reason_code histogram shows the gate catching nothing real over 30d, OR
# BLUEPRINT is subsumed into a different engine.
