#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/blueprint-text-validate.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-06-26
# VERSION=v1 (2026-06-26: A4 slice 1 — validate the EMITTED BLUEPRINT block TEXT,
#            not the self-asserted .claude/blueprint-registered marker.)
#
# blueprint-text-validate.sh — PreToolUse hook on Edit|Write.
#
# WHY (A4, the doc's #1 reliability hole): blueprint-check.sh validates only the
# marker FILE (HAS_OUTPUT=1 / HAS_VERIFY=1 / HAS_PER_STEP_VERIFY=1). A model can
# write a perfect marker and emit a garbled, empty, or trivially-verified
# BLUEPRINT block — or none at all — in the text the USER actually sees, and the
# marker gate waves it through. This hook reads the transcript, finds the
# BLUEPRINT block the user sees, and validates its CONTENT. On malformation it
# blocks (exit 2) with a field-specific repair message BEFORE the mutation runs.
#
# Complements (does NOT replace) blueprint-check.sh: that gate ensures a block
# was claimed (marker); this gate ensures the claimed block is real and non-trivial.
# Registered AFTER blueprint-check.sh so the marker existence is already assured.
#
# Scope (slice 1): foundational paths only (same set blueprint-check.sh HARD-blocks
# with HAS_OUTPUT/HAS_VERIFY), where the Output/Verified-by fields are already
# mandated. Broaden to all Edit/Write via BLUEPRINT_TEXT_VALIDATE_SCOPE=all.
#
# Exit: 0 = pass/skip ; 2 = block with repair message on stderr.
# Fail-open: any internal error (no jq, no python3, no transcript) -> exit 0.
#   Rationale (D40): a guardrail must never break a session. A text validator
#   that hard-fails on a parsing edge would be worse than the gap it closes.
#
# Kill-switches (honors the parent Blueprint switches + its own):
#   BLUEPRINT_DISABLED=1 / ~/.blueprint-disabled            (parent, disables all)
#   BLUEPRINT_TEXT_VALIDATE_DISABLED=1 / ~/.blueprint-text-validate-disabled (this)
# Override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>  (same as parent)

set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8 2>/dev/null || true

# ── Kill-switches ──
[ -n "${BLUEPRINT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.blueprint-disabled" ] && exit 0
[ "${BLUEPRINT_TEXT_VALIDATE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.blueprint-text-validate-disabled" ] && exit 0
# ── Override (shared with parent gate) ──
[ "${BLUEPRINT_ACK:-0}" = "1" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

PAYLOAD=$(cat 2>/dev/null || true)
[ -z "$PAYLOAD" ] && exit 0

FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE_PATH" ] && FILE_PATH="${TOOL_INPUT_file_path:-}"
[ -z "$FILE_PATH" ] && exit 0
REL_PATH="${FILE_PATH#"$REPO_ROOT"/}"

# ── Whitelist (mirror blueprint-check.sh) ──
case "$REL_PATH" in
  *.lock|*.log|*.jsonl) exit 0 ;;
  .claude/*|.enforcement/*|.analytics/*) exit 0 ;;
  */TODO.md|*/BACKLOG.md|*/CHANGELOG.md|*/MEMORY.md) exit 0 ;;
  holding/checkpoints/*) exit 0 ;;
  sutra/archive/*) exit 0 ;;
esac

# ── Scope (slice 1 = foundational only; mirror blueprint-check.sh set) ──
SCOPE="${BLUEPRINT_TEXT_VALIDATE_SCOPE:-foundational}"
is_foundational=0
case "$REL_PATH" in
  sutra/os/charters/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/protocols/*.md) is_foundational=1 ;;
  sutra/layer2-operating-system/PROTOCOLS.md) is_foundational=1 ;;
  holding/FOUNDER-DIRECTIONS.md) is_foundational=1 ;;
  holding/research/*-design.md|holding/research/*-plan.md) is_foundational=1 ;;
  sutra/os/engines/*.md) is_foundational=1 ;;
esac
if [ "$SCOPE" != "all" ] && [ "$is_foundational" != "1" ]; then
  exit 0
fi

# ── Transcript path (PreToolUse provides it) ──
TRANSCRIPT_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -z "$TRANSCRIPT_PATH" ] && exit 0
[ ! -f "$TRANSCRIPT_PATH" ] && exit 0

# ── Depth (fail-closed to 5, mirror blueprint-check.sh) ──
DEPTH_FILE="$REPO_ROOT/.claude/depth-registered"
DEPTH=""
if [ -f "$DEPTH_FILE" ]; then
  _A=$(grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' "$DEPTH_FILE" 2>/dev/null | head -1)
  if [ -n "$_A" ]; then DEPTH=$(printf '%s' "$_A" | sed -E 's/^DEPTH=([0-9]+).*$/\1/');
  else
    _B=$(grep -E '^DEPTH=[0-9]+$' "$DEPTH_FILE" 2>/dev/null | head -1)
    [ -n "$_B" ] && DEPTH=$(printf '%s' "$_B" | sed -E 's/^DEPTH=([0-9]+)$/\1/')
  fi
fi
case "$DEPTH" in ''|*[!0-9]*) DEPTH=5 ;; esac

# ── Extract + validate the BLUEPRINT block text from the current turn ──
# Python: walk transcript, gather current-turn assistant text (after last HUMAN
# user row, filtering tool_result + isMeta rows), locate the BLUEPRINT block,
# validate content. Prints "STATUS<TAB>MESSAGE".
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
            except: pass
except SystemExit: raise
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

# Gather ALL assistant text emitted in the current turn.
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

# Strip ASCII box pipes/padding so "| Doing: x |" -> "Doing: x".
def declutter(line):
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    s = re.sub(r"\s*\|\s*$", "", s)
    return s.strip()

lines = [declutter(l) for l in turn_text.splitlines()]

# Locate the BLUEPRINT block: the region from a line containing BLUEPRINT inside
# an ASCII box header (+-- BLUEPRINT) to the next box-closing line (+---...).
start = None
for i, raw in enumerate(turn_text.splitlines()):
    if "BLUEPRINT" in raw and "+--" in raw:
        start = i; break
if start is None:
    # No box header found. Marker said a block exists -> the visible text lacks it.
    print("missing\tno_blueprint_block_found"); sys.exit(0)

src = turn_text.splitlines()
end = len(src)
for j in range(start+1, len(src)):
    if re.match(r"^\s*\+-{3,}\+?\s*$", src[j]):
        end = j; break
block = [declutter(l) for l in src[start:end+1]]

def field(name):
    # case-insensitive "Name: value" ; tolerate "(overall)" suffix on the key.
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
    print("missing_output\tBLUEPRINT block missing Output looks like: field"); sys.exit(0)
if is_trivial(out):
    print("trivial_output\tOutput looks like: is empty/trivial (\"%s\")" % out[:60]); sys.exit(0)

vby = field("Verified by")
if vby is None:
    print("missing_verify\tBLUEPRINT block missing Verified by: field"); sys.exit(0)
if is_trivial(vby):
    print("trivial_verify\tVerified by: is trivial/blocklisted (\"%s\") -- needs a runnable check" % vby[:60]); sys.exit(0)

# D3+ : every numbered step must carry an inline Verify:
if depth >= 3:
    step_lines = [l for l in block if re.match(r"^\d+\)", l)]
    if step_lines:
        bad = [l for l in step_lines if not re.search(r"\bVerify:\s*\S", l, re.IGNORECASE)]
        if bad:
            print("missing_step_verify\tD%d: step without inline Verify: -> \"%s\"" % (depth, bad[0][:60])); sys.exit(0)

print("ok\tvalid"); sys.exit(0)
' 2>/dev/null)

STATUS="${VERDICT%%	*}"
MESSAGE="${VERDICT#*	}"

# Fail-open on any non-decisive status.
case "$STATUS" in
  ok|skip|"") exit 0 ;;
esac

# ── Block branch (exit 2) with repair guidance ──
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
VLOG="$REPO_ROOT/.enforcement/governance-violations.jsonl"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
printf '{"ts":"%s","violation":"blueprint_text_invalid","reason_code":"%s","layer":"blueprint-text","file":"%s","action":"pretool_blocked"}\n' \
  "$NOW" "$STATUS" "$REL_PATH" >> "$VLOG" 2>/dev/null

{
  echo "BLUEPRINT-TEXT-VALIDATE: the emitted BLUEPRINT block failed text validation."
  echo "  File: $REL_PATH"
  echo "  Problem: $MESSAGE"
  echo "  This checks the block the USER sees, not the .claude/blueprint-registered marker."
  echo "  Fix: re-emit a complete BLUEPRINT block with a non-empty Doing:, a concrete"
  echo "       'Output looks like:', and a 'Verified by (overall):' that names a RUNNABLE"
  echo "       check (shell test / typecheck / grep / file-exists / curl) — not 'works'/'done'."
  echo "       At D3+, every numbered Step must carry an inline 'Verify:'."
  echo "  Override: BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>"
  echo "  Kill: BLUEPRINT_TEXT_VALIDATE_DISABLED=1"
} >&2
exit 2
