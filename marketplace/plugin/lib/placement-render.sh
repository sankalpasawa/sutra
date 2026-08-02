#!/usr/bin/env bash
# placement-render.sh — render the per-turn PLACEMENT block (ADR-028).
#
# Pure function: reads one placement JSON on stdin (or $1) and writes the block
# to stdout. Does NOT touch the Domain registry — the caller resolves the
# ancestor chain and passes it in. That is deliberate: the compact path is the
# common path and must never walk a tree (deepseek P1, 2026-07-29).
#
# Shape selection (sutra-defaults.json .per_turn_blocks.placement.shape_rule):
#   units > bulk_threshold ................. summary
#   created.domains|charters non-empty ..... expanded
#   otherwise .............................. compact   <- the default
#
# Input schema (only `chain` and `charter` are required for compact):
# {
#   "chain":   [ {"path":"D0","name":"Asawa Inc.","is_new":false}, ... ],
#   "charter": {"id":"C-4f8a","title":"Native Canon Integrity",
#               "promise":"...","scope_in":"...","scope_out":"...","is_new":false},
#   "created": {"domains":[],"charters":[]},
#   "units":   1
# }
#
# ASCII only per D-UX-1. No unicode box drawing.
set -euo pipefail

BULK_THRESHOLD="${PLACEMENT_BULK_THRESHOLD:-20}"

_in=$(cat "${1:-/dev/stdin}")
command -v jq >/dev/null 2>&1 || { echo "placement-render: jq required" >&2; exit 1; }
printf '%s' "$_in" | jq -e . >/dev/null 2>&1 || { echo "placement-render: invalid JSON input" >&2; exit 1; }

j() { printf '%s' "$_in" | jq -r "$1"; }

units=$(j '.units // 1')
n_dom=$(j '.created.domains // [] | length')
n_cha=$(j '.created.charters // [] | length')
chain_len=$(j '.chain // [] | length')
[ "$chain_len" -gt 0 ] || { echo "placement-render: empty chain" >&2; exit 1; }

# ---- shape selection -------------------------------------------------------
if [ "$units" -gt "$BULK_THRESHOLD" ]; then
  shape=summary
elif [ "$n_dom" -gt 0 ] || [ "$n_cha" -gt 0 ]; then
  shape=expanded
else
  shape=compact
fi
[ -n "${PLACEMENT_FORCE_SHAPE:-}" ] && shape="$PLACEMENT_FORCE_SHAPE"

ct=$(j '.charter.title // ""')
cid=$(j '.charter.id // ""')

case "$shape" in

compact)
  # PLACEMENT: D0 > D3 Sutra OS > D3.D2 Native | "Native Canon Integrity"
  line=$(printf '%s' "$_in" | jq -r '
    [ .chain[] | if .name == null or .name == "" then .path else "\(.path) \(.name)" end ]
    | join(" > ")')
  if [ -n "$ct" ]; then
    printf 'PLACEMENT: %s | "%s"\n' "$line" "$ct"
  else
    printf 'PLACEMENT: %s\n' "$line"
  fi
  ;;

summary)
  deepest=$(j '.chain | last | "\(.path) \(.name // "")"')
  printf 'PLACEMENT: %s units placed | %s domain(s), %s charter(s) created | deepest %s\n' \
    "$units" "$n_dom" "$n_cha" "$(printf '%s' "$deepest" | sed 's/ *$//')"
  ;;

expanded)
  W=63
  bar() { printf '+-- PLACEMENT %s+\n' "$(printf '%*s' $((W - 13)) '' | tr ' ' '-')"; }
  end() { printf '+%s+\n' "$(printf '%*s' "$W" '' | tr ' ' '-')"; }
  row() { printf '| %-*s |\n' "$((W - 2))" "$1"; }

  bar
  # ancestor chain, indented two spaces per level
  i=0
  while [ "$i" -lt "$chain_len" ]; do
    p=$(j ".chain[$i].path")
    n=$(j ".chain[$i].name // \"\"")
    new=$(j ".chain[$i].is_new // false")
    indent=$(printf '%*s' $((i * 2)) '')
    [ "$i" -gt 0 ] && prefix="${indent}|__ " || prefix=""
    tag=""; [ "$new" = "true" ] && tag="   [NEW]"
    row "$(printf '%s%-12s %s%s' "$prefix" "$p" "$n" "$tag")"
    i=$((i + 1))
  done

  if [ -n "$ct" ]; then
    row ""
    cnew=$(j '.charter.is_new // false')
    ctag=""; [ "$cnew" = "true" ] && ctag="   [NEW]"
    row "$(printf 'CHARTER  %s  "%s"%s' "$cid" "$ct" "$ctag")"
    cp=$(j '.charter.promise // ""'); [ -n "$cp" ] && row "  Promises: $cp"
    si=$(j '.charter.scope_in // ""'); [ -n "$si" ] && row "  In:  $si"
    so=$(j '.charter.scope_out // ""'); [ -n "$so" ] && row "  Out: $so"
  fi

  row ""
  row "$(printf 'CREATED THIS TURN: %s domain(s), %s charter(s)' "$n_dom" "$n_cha")"
  end
  ;;

*)
  echo "placement-render: unknown shape '$shape'" >&2; exit 1 ;;
esac
