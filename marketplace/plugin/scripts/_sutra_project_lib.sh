#!/bin/bash
# Sutra project-state utility — bash/jq port of _sutra_project_lib.py.
#
# Background — vinit#38 follow-up (filed 2026-04-28, escalation 2026-05-01):
#     v2.8.11 moved python3 from stdin-heredoc to file-form to dodge SIGKILL
#     from macOS sandbox/EDR agents. That fixed the heredoc class, but
#     a second profile surfaced 2026-05-01 (user @abhishekshah on v2.8.10):
#     `python3 -c "print('hello')"` itself exits 137 — the binary is killed
#     regardless of invocation form (quarantine xattr, AV process-name
#     killer, or codesign mismatch). File-form vs heredoc is irrelevant
#     when python3 itself can't survive exec.
#
# Fix v2.13.0: remove python3 from the bootstrap path entirely. jq is
#     widely available, fast, and not subject to the same EDR heuristics.
#     start.sh adds an upfront jq health gate with an actionable install
#     hint, so a missing-jq client gets a clear message rather than a
#     silent half-bootstrap.
#
# Atomic writes: every file mutation goes through `mktemp` in the target
#     directory followed by `mv -f`. mv across the same filesystem is
#     atomic (rename(2)). A SIGKILL between mktemp and mv leaves the
#     prior valid file content untouched.
#
# Subcommands (parity with .py predecessor):
#     patch-profile <profile> <telemetry_default 0|1>
#     write-onboard <install_id> <project_id> <name> <first_seen>
#                   <version> <optin_str> <existing_identity_json>
#     stamp-identity <identity_json>
#     banner

set -u

PROJECT_JSON=".claude/sutra-project.json"

_require_jq() {
  command -v jq >/dev/null 2>&1 && return 0
  cat >&2 <<'EOF'
sutra: jq is required but not found on PATH.

Install:
  macOS:    brew install jq
  Debian:   sudo apt-get install jq
  RHEL:     sudo dnf install jq
  Other:    https://jqlang.org/download/

Then re-run /core:start.
EOF
  return 127
}

# atomic_write <target_path>  (content from stdin)
atomic_write() {
  local target="$1"
  local target_abs target_dir tmp
  target_abs=$(cd "$(dirname "$target")" 2>/dev/null && pwd)/$(basename "$target") || target_abs="$target"
  target_dir=$(dirname "$target_abs")
  [ -d "$target_dir" ] || mkdir -p "$target_dir" || return 1
  tmp=$(mktemp "${target_dir}/.sutra-XXXXXX.tmp") || return 1
  if ! cat > "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  if ! mv -f "$tmp" "$target"; then
    rm -f "$tmp"
    return 1
  fi
}

cmd_patch_profile() {
  local profile="${1:-}" telemetry_default="${2:-}"
  if [ -z "$profile" ] || [ -z "$telemetry_default" ]; then
    echo "usage: patch-profile <profile> <telemetry_default 0|1>" >&2
    return 2
  fi
  if [ ! -f "$PROJECT_JSON" ]; then
    echo "-- $PROJECT_JSON missing; skipping patch" >&2
    return 0
  fi
  _require_jq || return $?
  # Validate before patching — jq treats empty file as null and would silently
  # produce a stale-shaped object, masking corruption.
  if ! jq -e . "$PROJECT_JSON" >/dev/null 2>&1; then
    echo "-- $PROJECT_JSON is empty or corrupt; cannot patch" >&2
    echo "   recover: rm $PROJECT_JSON && /core:start" >&2
    return 2
  fi
  local optin out
  case "$telemetry_default" in
    1|true|TRUE|yes|YES) optin=true ;;
    *) optin=false ;;
  esac
  if ! out=$(jq --arg p "$profile" --argjson t "$optin" \
        '.profile = $p | .telemetry_optin = $t' "$PROJECT_JSON" 2>/dev/null); then
    echo "-- $PROJECT_JSON jq transform failed; not patched" >&2
    return 2
  fi
  printf '%s\n' "$out" | atomic_write "$PROJECT_JSON"
}

cmd_write_onboard() {
  local install_id="${1:-}" project_id="${2:-}" name="${3:-}"
  local first_seen="${4:-}" version="${5:-}" optin_str="${6:-false}"
  local existing_identity="${7:-}"
  if [ -z "$install_id" ] || [ -z "$project_id" ] || [ -z "$name" ]; then
    echo "usage: write-onboard <install_id> <project_id> <name> <first_seen> <version> <optin_str> [identity_json]" >&2
    return 2
  fi
  _require_jq || return $?
  local optin
  case "$optin_str" in
    true|TRUE|1|yes|YES) optin=true ;;
    *) optin=false ;;
  esac

  mkdir -p "$(dirname "$PROJECT_JSON")"

  local out
  if [ -n "$existing_identity" ] && printf '%s' "$existing_identity" | jq -e . >/dev/null 2>&1; then
    out=$(jq -n \
      --arg install_id "$install_id" \
      --arg project_id "$project_id" \
      --arg name "$name" \
      --arg first_seen "$first_seen" \
      --arg version "$version" \
      --argjson optin "$optin" \
      --argjson identity "$existing_identity" \
      '{install_id:$install_id, project_id:$project_id, project_name:$name, first_seen:$first_seen, sutra_version:$version, telemetry_optin:$optin, identity:$identity}')
  else
    out=$(jq -n \
      --arg install_id "$install_id" \
      --arg project_id "$project_id" \
      --arg name "$name" \
      --arg first_seen "$first_seen" \
      --arg version "$version" \
      --argjson optin "$optin" \
      '{install_id:$install_id, project_id:$project_id, project_name:$name, first_seen:$first_seen, sutra_version:$version, telemetry_optin:$optin}')
  fi
  printf '%s\n' "$out" | atomic_write "$PROJECT_JSON"
}

cmd_stamp_identity() {
  # Best-effort per onboard.sh contract — silent failure (return 0).
  local identity_json="${1:-}"
  [ -f "$PROJECT_JSON" ] || return 0
  [ -n "$identity_json" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  printf '%s' "$identity_json" | jq -e . >/dev/null 2>&1 || return 0
  local out
  out=$(jq --argjson identity "$identity_json" '.identity = $identity' "$PROJECT_JSON" 2>/dev/null) || return 0
  printf '%s\n' "$out" | atomic_write "$PROJECT_JSON" 2>/dev/null || return 0
}

cmd_banner() {
  if [ ! -f "$PROJECT_JSON" ]; then
    echo "-- onboard failed — sutra-project.json missing or corrupt" >&2
    return 1
  fi
  _require_jq || return $?
  if ! jq -e . "$PROJECT_JSON" >/dev/null 2>&1; then
    echo "-- onboard failed — sutra-project.json missing or corrupt" >&2
    return 1
  fi

  local version project_name install_id project_id profile optin
  version=$(jq -r '.sutra_version // "unknown"' "$PROJECT_JSON")
  project_name=$(jq -r '.project_name // "<unnamed>"' "$PROJECT_JSON")
  install_id=$(jq -r '.install_id // "<missing>"' "$PROJECT_JSON")
  project_id=$(jq -r '.project_id // "<missing>"' "$PROJECT_JSON")
  profile=$(jq -r '.profile // "project"' "$PROJECT_JSON")
  optin=$(jq -r '.telemetry_optin // false' "$PROJECT_JSON")

  echo "🧭 Sutra active"
  printf '   Version:         %s\n' "$version"
  printf '   Project:         %s\n' "$project_name"
  printf '   Install ID:      %s\n' "$install_id"
  printf '   Project ID:      %s\n' "$project_id"
  printf '   Profile:         %s\n' "$profile"

  # v2.18.0 (2026-05-03): opt-in transport restored. Banner branches on
  # 3 states: kill-switched / enabled / off. Old "local-only — push disabled
  # in v2.0 privacy model" wording removed because it's no longer accurate
  # when telemetry_optin=true.
  local tel
  if [ "${SUTRA_TELEMETRY:-1}" = "0" ]; then
    tel="off (SUTRA_TELEMETRY=0 kill-switch — capture and push disabled)"
  elif [ "$optin" = "true" ] && [ "${SUTRA_LEGACY_TELEMETRY:-}" = "1" ]; then
    tel="on — legacy push active (SUTRA_LEGACY_TELEMETRY=1)"
  elif [ "$optin" = "true" ]; then
    tel="ENABLED — push to sankalpasawa/sutra-data on Stop (SUTRA_TELEMETRY=0 to disable)"
  else
    tel="off"
  fi
  printf '   Telemetry:       %s\n' "$tel"

  local rtk_status="inactive — rtk binary not installed (opt-in; see README)"
  if command -v rtk >/dev/null 2>&1 && [ ! -f "$HOME/.rtk-disabled" ]; then
    rtk_status="active"
  fi
  printf '   RTK rewrite:     %s\n' "$rtk_status"
  echo
  echo "   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace"

  local enforcement="warn-only"
  [ "$profile" = "company" ] && enforcement="HARD — missing depth marker blocks Edit/Write"
  printf '   Enforcement:     %s\n' "$enforcement"
  echo
  echo "You're ready. Ask Claude anything — every task goes through governance."
  echo
  echo "Other commands:"
  echo "   /core:status      — show install / queue / telemetry state"
  echo "   /core:update      — pull the latest plugin version"
  echo "   /core:uninstall   — remove Sutra from this machine"
  echo "   /core:depth-check — manual depth marker for the next task"
  echo "   /core:permissions — paste-ready allowlist snippet"
  if [ "$profile" = "company" ]; then
    echo
    echo "Escape hatch (one-shot): prefix any tool call with SUTRA_BYPASS=1"
  fi
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    patch-profile)   cmd_patch_profile "$@" ;;
    write-onboard)   cmd_write_onboard "$@" ;;
    stamp-identity)  cmd_stamp_identity "$@" ;;
    banner)          cmd_banner "$@" ;;
    ""|-h|--help|help)
      cat >&2 <<EOF
usage: _sutra_project_lib.sh <subcmd> [args...]
  subcmds: patch-profile, write-onboard, stamp-identity, banner
EOF
      return 2
      ;;
    *)
      echo "unknown subcommand: $cmd" >&2
      return 2
      ;;
  esac
}

main "$@"
