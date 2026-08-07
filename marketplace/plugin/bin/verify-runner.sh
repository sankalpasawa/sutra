#!/usr/bin/env bash
# LAYER=L1
# SCOPE=single-instance:asawa-holding
# TARGET_PATH=holding/bin/verify-runner.sh
# WHY_NOT_L0_KIND=staging
# WHY_NOT_L0_REASON=stages until parity suite proves it; plugin L0 at eval-program step 51
# PROMOTE_TO=sutra/marketplace/plugin/bin/verify-runner.sh
# PROMOTE_BY=2026-09-15
# OWNER=Governance Hooks charter
# ACCEPTANCE=impl/tests parity suite ALL-PASS vs sutra-atom close semantics
# TS=2026-08-07
#
# verify-runner — shared check executor for Work-Atom verifies (eval-program D-2).
# Reproduces `sutra-atom close` verify semantics so eval replay and close-time
# checks agree: pinned template registry, repo-root cwd, 30s timeout, dotdot
# refusal, envelope containment (when an envelope is declared), named-test
# SHA-256 pin. sutra-atom wiring to call this lib is a later gated step
# (PROGRAM.md amendment 1); until then parity is enforced by the test suite.
#
# Usage:
#   verify-runner.sh --atom-json <path/to/atom.json>
#   verify-runner.sh --template <T> [--arg A]... [--touch P]... [--sha H]
# Exit codes: 0 pass · 1 check failed · 2 structural refusal · 3 timeout · 4 usage/infra
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REPO_SRC="$(git rev-parse --show-toplevel 2>/dev/null || echo "$ROOT")"
_SP="$REPO_SRC/holding/hooks/lib/sutra-paths.sh"
[ -f "$_SP" ] && . "$_SP" || SUTRA_VERIFY="$REPO_SRC/holding/bin/verify-templates"
TPL_DIR="${SUTRA_VERIFY:-$REPO_SRC/holding/bin/verify-templates}"

die_usage() { echo "verify-runner: $*" >&2; exit 4; }
refuse() { echo "verify-runner: REFUSED — $*" >&2; exit 2; }

TEMPLATE="" SHA="" ; ARGS=() ; TOUCHES=()
if [ "${1:-}" = "--atom-json" ]; then
  AJ="${2:-}"; [ -f "$AJ" ] || die_usage "atom.json not found: $AJ"
  command -v jq >/dev/null || die_usage "jq required"
  TEMPLATE=$(jq -r .verify.template "$AJ")
  SHA=$(jq -r '.verify.target_sha256 // empty' "$AJ")
  while IFS= read -r a; do [ -n "$a" ] && ARGS+=("$a"); done < <(jq -r '.verify.args[]?' "$AJ")
  while IFS= read -r t; do [ -n "$t" ] && TOUCHES+=("$t"); done < <(jq -r '(.touches[]? , (.outputs // [])[]?)' "$AJ")
else
  while [ $# -gt 0 ]; do
    case "$1" in
      --template) TEMPLATE="$2"; shift 2 ;;
      --arg) ARGS+=("$2"); shift 2 ;;
      --touch) TOUCHES+=("$2"); shift 2 ;;
      --sha) SHA="$2"; shift 2 ;;
      *) die_usage "unknown flag $1" ;;
    esac
  done
fi
[ -n "$TEMPLATE" ] || die_usage "no template"
[ -x "$TPL_DIR/$TEMPLATE.sh" ] || refuse "template '$TEMPLATE' not in pinned registry ($TPL_DIR)"

# Structural refusals — mirror sutra-atom cmd_close ordering: dotdot first,
# then envelope containment (only when an envelope is declared).
_covered() { # $1=target; TOUCHES entries: trailing-slash dir = strictly-under, else exact
  local p="$1" e
  for e in ${TOUCHES[@]+"${TOUCHES[@]}"}; do
    case "$e" in *..*) continue ;; esac
    if [ "${e%/}" != "$e" ]; then case "$p" in "${e%/}"/*) return 0 ;; esac
    else [ "$p" = "$e" ] && return 0; fi
  done
  return 1
}
_targets=()
case "$TEMPLATE" in
  grep-count) _targets=("${ARGS[1]:-}") ;;
  file-exists) _targets=(${ARGS[@]+"${ARGS[@]}"}) ;;
esac
for _t in ${_targets[@]+"${_targets[@]}"}; do
  [ -z "$_t" ] && continue
  case "$_t" in *..*) refuse "dotdot in verify target '$_t'" ;; esac
  if [ ${#TOUCHES[@]} -gt 0 ]; then
    _covered "$_t" || refuse "verify target '$_t' outside declared envelope"
  fi
done

# named-test SHA pin — tamper-evident refuse, same as close.
if [ "$TEMPLATE" = "named-test" ] && [ -n "$SHA" ]; then
  [ -f "$ROOT/${ARGS[0]:-}" ] || refuse "named-test target missing: ${ARGS[0]:-}"
  now_sha=$(shasum -a 256 "$ROOT/${ARGS[0]}" | cut -d' ' -f1)
  [ "$now_sha" = "$SHA" ] || refuse "hash-pin mismatch on ${ARGS[0]} — target changed since declaration"
fi

# Execute: repo-root cwd, 30s alarm — identical to sutra-atom close.
rc=0
( cd "$ROOT" && perl -e 'alarm 30; exec @ARGV or die "exec: $!"' -- bash "$TPL_DIR/$TEMPLATE.sh" ${ARGS[@]+"${ARGS[@]}"} ) >/dev/null 2>&1 || rc=$?
if [ "$rc" -eq 142 ]; then exit 3; fi
[ "$rc" -eq 0 ] && exit 0 || exit 1
