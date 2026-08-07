#!/usr/bin/env bash
# touches-match.sh — WDP W6-T50. THE shared matcher: TOUCHES-CONTRACT v1
# semantics, byte-for-byte the fixtures' law. Floor SOFT logging and gate HARD
# blocking source THIS file — one implementation, so fixture drift (risk #10)
# is closed by construction. Acceptance: fixtures/touches-fixtures.sh passes
# against this function unmodified.
#
# touches_match <target> <atom_open 1|0> <entry>...  -> echoes ALLOW | DENY
# Root prefix for absolute targets: $TOUCHES_MATCH_ROOT (default: git root).

touches_match() {
  local target="$1" atom_open="$2"; shift 2
  local root="${TOUCHES_MATCH_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  [ "$atom_open" = "1" ] || { echo DENY; return; }                    # M4
  # M7: evidence paths deny direct mutation regardless of touches
  case "$target" in
    .sutra/*ledger*|.enforcement/*) echo DENY; return ;;
  esac
  # C3: absolute under root -> relative; else deny
  case "$target" in
    "${root%/}"/*) target="${target#"${root%/}"/}" ;;
    /*) echo DENY; return ;;
  esac
  # M7 again post-relativization (absolute spelling of an evidence path)
  case "$target" in
    .sutra/*ledger*|.enforcement/*) echo DENY; return ;;
  esac
  # C1: lexical normalization (collapse //, resolve . and ..)
  local IFS='/' part; local -a stack=()
  for part in $target; do
    case "$part" in
      ''|'.') ;;
      '..') if [ ${#stack[@]} -gt 0 ]; then unset 'stack[${#stack[@]}-1]'; else echo DENY; return; fi ;;  # C2
      *) stack+=("$part") ;;
    esac
  done
  target=$(IFS=/; echo "${stack[*]-}")
  [ -n "$target" ] || { echo DENY; return; }                          # dir-node / empty
  local entry
  for entry in "$@"; do
    case "$entry" in /*) echo DENY; return ;; esac                    # C3: absolute declared entry -> invalid
    if [ "${entry%/}" != "$entry" ]; then
      local prefix="${entry%/}"
      [ "$target" = "$prefix" ] && { echo DENY; return; }             # M2: dir node itself
      case "$target" in "$prefix"/*) echo ALLOW; return ;; esac       # M2: strictly under
    else
      [ "$target" = "$entry" ] && { echo ALLOW; return; }             # M1 (C5: byte-exact, case-sensitive)
    fi
  done
  echo DENY                                                           # M3/M5
}
