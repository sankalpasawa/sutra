#!/bin/bash
# context-scope-audit.sh — grounding rung 4 (canon B4 via Q28 default).
# When a turn placed under domain X touches a file whose CURRENT placement is
# under a DIFFERENT top-level domain, that cross-charter reach is AUDIT-LOGGED.
# Never blocks: crossing is often legitimate; the log is the point.
set -u
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
PAYLOAD=$(cat 2>/dev/null || true)
FILE=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0
# --- B2 marker-race P4: session-first marker reads --------------------
# Root cause: holding/research/2026-07-30-marker-race-root-cause.md (Phase 4,
# context-scope-audit.sh:16). Session dir first via marker-lib;
# foreign-stamped globals ignored. Audit only -- NEVER blocks; legacy global
# path is the fallback when marker-lib is unavailable. Sourced defensively
# (set -u).
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" 2>/dev/null || true
  if command -v sutra_sid_from_stdin >/dev/null 2>&1; then
    sutra_sid_from_stdin "$PAYLOAD" 2>/dev/null || true
  fi
  set -u
fi
_b2_marker_path() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    if sutra_marker_has "$1" 2>/dev/null; then sutra_marker_path "$1"; fi
    return 0
  fi
  [ -f "$REPO_ROOT/.claude/$1" ] && printf '%s' "$REPO_ROOT/.claude/$1"
  return 0
}
TURN_REF=""
_PL_FILE="$(_b2_marker_path placement-registered)"
if [ -n "$_PL_FILE" ]; then
  TURN_REF=$(grep -o 'DOMAIN_REF=[^ ]*' "$_PL_FILE" 2>/dev/null | head -1 | cut -d= -f2)
fi
[ -z "$TURN_REF" ] || [ "$TURN_REF" = "unresolved" ] && exit 0
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
python3 - "$FILE" "$TURN_REF" "$REPO_ROOT" "$PLUGIN_DIR" <<'PY' 2>/dev/null
import sys, os, json, time
f, turn_ref, repo, plug = sys.argv[1:5]
sys.path.insert(0, os.path.join(plug, "lib"))
import placement_engine as E
ds = E.load_domains()
if turn_ref not in ds: sys.exit(0)
latest = {}
for r in E._read_jsonl(E.CURRENT):
    if r.get("work_ref_id"): latest[E._norm_path(r["work_ref_id"])] = r.get("domain_ref")
fref = latest.get(E._norm_path(f))
if not fref or fref not in ds: sys.exit(0)
def top(ref):
    seen=set()
    while ds[ref].get("parent_ref") and ref not in seen:
        seen.add(ref); ref = ds[ref]["parent_ref"]
    return ref
if top(fref) != top(turn_ref):
    row = {"ts": int(time.time()), "event": "cross-charter-reach",
           "turn_domain": ds[turn_ref]["name"], "file_domain": ds[fref]["name"],
           "file": f}
    p = os.path.join(repo, ".enforcement", "placement", "context-scope.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "a").write(json.dumps(row) + "\n")
PY
exit 0
