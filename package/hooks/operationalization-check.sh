#!/usr/bin/env bash
# operationalization-check.sh — D30 enforcement hook (submodule-aware v2)
#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Writes decisions to .analytics/ops-enforcement.jsonl — every check logged with
# {ts, commit, file, decision, reason, repo}. Aggregated weekly for charter KPIs §3.
#
# ### 2. Adoption mechanism
# Wired at 4 trigger points per repo (PostToolUse warn, pre-commit block, pre-push block, CI block).
# Installed via holding/hooks/install-git-hooks.sh in each repo.
#
# ### 3. Monitoring / escalation
# Sutra-OS watches compliance % weekly. Warn <95%. Breach <80% → revert.
#
# ### 4. Iteration trigger
# FP block rate >10% after 14 days → adjust semantic-change heuristic.
#
# ### 5. DRI
# Sutra-OS. Engineering contributes implementation changes.
#
# ### 6. Decommission criteria
# Retires when charter retires (see sutra/os/charters/OPERATIONALIZATION.md §11).

set -euo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && { echo "operationalization-check: not in a git repo" >&2; exit 0; }
cd "$REPO_ROOT"

MODE="${1:-auto}"
CURRENT_REPO_NAME=$(basename "$REPO_ROOT")

# ─── Locate state/system.yaml ───────────────────────────────────────────────
STATE_FILE=""
for candidate in "$REPO_ROOT/sutra/state/system.yaml" "$REPO_ROOT/state/system.yaml"; do
  if [ -f "$candidate" ]; then
    STATE_FILE="$candidate"
    break
  fi
done

if [ -z "$STATE_FILE" ]; then
  # No state file reachable — hook inactive
  exit 0
fi

# ─── Read per-repo cutover SHA ──────────────────────────────────────────────
# cutover_commits: { parent: "sha", sutra: "sha", ... }
# Determine which key to use based on current repo
case "$CURRENT_REPO_NAME" in
  asawa-holding) CUTOVER_KEY="parent" ;;
  sutra)         CUTOVER_KEY="sutra" ;;
  dayflow)       CUTOVER_KEY="dayflow" ;;
  billu)         CUTOVER_KEY="billu" ;;
  *)             CUTOVER_KEY="parent" ;;  # safe fallback
esac

# Parse cutover_commits.<key> from yaml
CUTOVER_SHA=$(awk -v key="$CUTOVER_KEY" '
  BEGIN { in_ops=0; in_commits=0 }
  /^operationalization:/ { in_ops=1; next }
  in_ops && /^  cutover_commits:/ { in_commits=1; next }
  in_commits && /^    [a-zA-Z_]+:/ {
    split($1, a, ":")
    k = a[1]
    gsub(/"/, "", $2)
    gsub(/#.*/, "", $2)
    gsub(/[[:space:]]/, "", $2)
    if (k == key) { print $2; exit }
  }
  in_commits && /^  [a-zA-Z_]/ && !/^  cutover_commits:/ { in_commits=0 }
  in_ops && /^[a-zA-Z_]/ && !/^operationalization:/ { in_ops=0 }
' "$STATE_FILE")

# Backward-compat: if no cutover_commits block, fall back to legacy cutover_commit
if [ -z "$CUTOVER_SHA" ]; then
  CUTOVER_SHA=$(awk '/^operationalization:/{f=1} f && /^  cutover_commit:/{gsub(/^[[:space:]]+|[[:space:]]*#.*|["\047]/,"",$2); print $2; exit}' "$STATE_FILE")
fi

# If cutover not set, hook inactive
if [ -z "$CUTOVER_SHA" ] || [ "$CUTOVER_SHA" = "pending" ]; then
  exit 0
fi

# ─── Known submodules list (for submodule-aware path handling) ──────────────
# Discover submodules in current repo via `git submodule status`
SUBMODULE_NAMES=$(git submodule status 2>/dev/null | awk '{print $2}' | tr '\n' ' ')

# Is this path rooted in a submodule of the current repo?
# Returns: submodule name (if yes), empty (if no)
submodule_owner() {
  local f="$1"
  local first="${f%%/*}"
  [ "$first" = "$f" ] && return
  for sm in $SUBMODULE_NAMES; do
    if [ "$first" = "$sm" ]; then
      echo "$sm"
      return
    fi
  done
}

# ─── Enforced path patterns (Tier A + Tier B) ────────────────────────────────
is_enforced() {
  local f="$1"
  case "$f" in
    sutra/os/charters/*.md) return 0 ;;
    sutra/*/protocols/PROTO-*.md) return 0 ;;
    sutra/*/d-engines/*.md|sutra/*/engines/*.md) return 0 ;;
    holding/departments/*/CHARTER.md) return 0 ;;
    sutra/os/SUTRA-CONFIG.md|*/os/SUTRA-CONFIG.md) return 0 ;;
    holding/hooks/*.sh|sutra/package/hooks/*.sh) return 0 ;;
    sutra/layer4-practice-skills/*/*.md) return 0 ;;
    sutra/package/bin/*.sh|sutra/package/bin/*.mjs) return 0 ;;
    .claude/commands/*.md) return 0 ;;
    holding/departments/*/*.sh) return 0 ;;
    # Inside-submodule context (when current repo IS sutra)
    os/charters/*.md) return 0 ;;
    os/protocols/PROTO-*.md|layer2-operating-system/protocols/PROTO-*.md) return 0 ;;
    os/engines/*.md|os/d-engines/*.md|layer2-operating-system/d-engines/*.md) return 0 ;;
    package/hooks/*.sh) return 0 ;;
    layer4-practice-skills/*/*.md) return 0 ;;
    package/bin/*.sh|package/bin/*.mjs) return 0 ;;
  esac
  return 1
}

# ─── Grandfathered at cutover? (submodule-aware) ────────────────────────────
is_grandfathered() {
  local f="$1"
  local sm=$(submodule_owner "$f")
  if [ -n "$sm" ]; then
    # File is in a submodule — check against submodule's cutover SHA + context
    local sm_cutover=$(awk -v key="$sm" '
      BEGIN { in_ops=0; in_commits=0 }
      /^operationalization:/ { in_ops=1; next }
      in_ops && /^  cutover_commits:/ { in_commits=1; next }
      in_commits && /^    [a-zA-Z_]+:/ {
        split($1, a, ":"); k = a[1]
        gsub(/"/, "", $2); gsub(/#.*/, "", $2); gsub(/[[:space:]]/, "", $2)
        if (k == key) { print $2; exit }
      }
      in_commits && /^  [a-zA-Z_]/ && !/^  cutover_commits:/ { in_commits=0 }
    ' "$STATE_FILE")
    [ -z "$sm_cutover" ] && return 1  # submodule has no registered cutover; treat as non-grandfathered (post-V1)
    local rel="${f#${sm}/}"
    git -C "$sm" cat-file -e "${sm_cutover}:${rel}" 2>/dev/null
  else
    git cat-file -e "${CUTOVER_SHA}:${f}" 2>/dev/null
  fi
}

# ─── Semantic change detection ──────────────────────────────────────────────
is_semantic_change() {
  local f="$1"
  local sm=$(submodule_owner "$f")
  local diff_out
  if [ -n "$sm" ]; then
    local sm_cutover=$(awk -v key="$sm" '
      BEGIN { in_ops=0; in_commits=0 }
      /^operationalization:/ { in_ops=1; next }
      in_ops && /^  cutover_commits:/ { in_commits=1; next }
      in_commits && /^    [a-zA-Z_]+:/ {
        split($1, a, ":"); k = a[1]
        gsub(/"/, "", $2); gsub(/#.*/, "", $2); gsub(/[[:space:]]/, "", $2)
        if (k == key) { print $2; exit }
      }
      in_commits && /^  [a-zA-Z_]/ && !/^  cutover_commits:/ { in_commits=0 }
    ' "$STATE_FILE")
    local rel="${f#${sm}/}"
    diff_out=$(git -C "$sm" diff --find-renames "${sm_cutover}" -- "$rel" 2>/dev/null || true)
  else
    diff_out=$(git diff --find-renames "${CUTOVER_SHA}" -- "$f" 2>/dev/null || true)
  fi

  [ -z "$diff_out" ] && return 1

  if echo "$diff_out" | head -5 | grep -qE "^similarity index 100%"; then
    return 1
  fi

  local changed
  changed=$(echo "$diff_out" | grep -cE "^[+-][^+-]" || true)
  [ -z "$changed" ] && changed=0
  if [ "$changed" -ge 5 ]; then return 0; fi
  if echo "$diff_out" | grep -qE "^[+-]#+[[:space:]]"; then return 0; fi
  if echo "$diff_out" | grep -qE "^[+-]\|.*\|"; then return 0; fi

  return 1
}

# ─── Ops section presence check ─────────────────────────────────────────────
has_ops_section() {
  local f="$1"
  [ -f "$f" ] || return 1
  grep -qE '^(#[[:space:]]*)?##[[:space:]]+([0-9]+\.[[:space:]]+)?Operationalization' "$f" || return 1
  local count=0
  for pat in 'Measurement' 'Adoption' 'Monitoring' 'Iteration' 'DRI' 'Decommission'; do
    if grep -qE "^(#[[:space:]]*)?###[[:space:]]+[1-6]\.[[:space:]]*${pat}" "$f"; then
      count=$((count + 1))
    fi
  done
  [ "$count" -ge 6 ]
}

# ─── Log decision ────────────────────────────────────────────────────────────
log_decision() {
  local file="$1" decision="$2" reason="$3"
  local log_dir="$REPO_ROOT/.analytics"
  mkdir -p "$log_dir" 2>/dev/null
  local commit
  commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  printf '{"ts":%s,"commit":"%s","repo":"%s","file":"%s","decision":"%s","reason":"%s","mode":"%s"}\n' \
    "$(date +%s)" "$commit" "$CURRENT_REPO_NAME" "$file" "$decision" "$reason" "$MODE" \
    >> "$log_dir/ops-enforcement.jsonl"
}

# ─── Get file list based on mode ────────────────────────────────────────────
get_files() {
  case "$MODE" in
    pre-commit) git diff --cached --name-only --diff-filter=ACMR 2>/dev/null ;;
    pre-push)
      local upstream
      upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || upstream=""
      if [ -n "$upstream" ]; then git diff --name-only "$upstream"...HEAD 2>/dev/null
      else git diff --name-only HEAD~1..HEAD 2>/dev/null || true; fi ;;
    ci) local base="${GITHUB_BASE_REF:-main}"; git diff --name-only "origin/$base"...HEAD 2>/dev/null ;;
    posttool) echo "${TOOL_INPUT_file_path:-${2:-}}" ;;
    test) echo "${2:-}" ;;
    *) git diff --cached --name-only --diff-filter=ACMR 2>/dev/null ;;
  esac
}

# ─── Main loop ──────────────────────────────────────────────────────────────
VIOLATIONS=()
FILES=$(get_files "$@")

for f in $FILES; do
  [ -z "$f" ] && continue
  if ! is_enforced "$f"; then continue; fi

  if is_grandfathered "$f"; then
    if ! is_semantic_change "$f"; then
      log_decision "$f" "grandfathered" "exempt at cutover, non-semantic change"
      continue
    fi
    if has_ops_section "$f"; then
      log_decision "$f" "allowed" "grandfather revoked; ops section present"
      continue
    fi
    log_decision "$f" "blocked" "grandfather revoked by semantic change; ops section missing"
    VIOLATIONS+=("$f (grandfather revoked — add ## Operationalization)")
  else
    if has_ops_section "$f"; then
      log_decision "$f" "allowed" "post-cutover; ops section present"
      continue
    fi
    log_decision "$f" "blocked" "post-cutover; ops section missing"
    VIOLATIONS+=("$f (new enforced artifact — add ## Operationalization)")
  fi
done

if [ ${#VIOLATIONS[@]} -eq 0 ]; then exit 0; fi

echo "" >&2
echo "BLOCKED — operationalization section missing (D30)" >&2
echo "" >&2
echo "  Mode: $MODE | Repo: $CURRENT_REPO_NAME | Cutover: $CUTOVER_SHA" >&2
echo "  Files needing ## Operationalization section:" >&2
for v in "${VIOLATIONS[@]}"; do echo "    - $v" >&2; done
echo "" >&2
echo "  Template: holding/OPERATIONALIZATION-STANDARD.md §2" >&2
echo "  Charter:  sutra/os/charters/OPERATIONALIZATION.md" >&2
echo "" >&2

if [ "$MODE" = "posttool" ]; then
  echo "  (PostToolUse: WARN ONLY — commit will be blocked by pre-commit hook)" >&2
  exit 0
fi

exit 1
