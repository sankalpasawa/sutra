#!/usr/bin/env bash
# tier.sh - when the code decides and when it asks an agent (founder conditions
# C7-C9, 2026-09-28: "if there is a program that has a low degree of confidence
# in it, then an agent works on it to figure that out ... the agent can give an
# output to the program itself").
#
# The shape, in one paragraph. Every code step ends with a value and a
# confidence. runtime/rules/tiers.json carries that step's threshold; when the
# confidence is at or above it the code's answer stands and the row records
# source=code. Below it the runtime asks the agent - never on the hot path: the
# ask is detached, its answer lands in the turn's own tier file, and the next
# step that needs the field reads whatever has arrived. An agent answer is
# advice the code records, never a decision the code obeys: it is applied only
# when it RAISES stringency on that step's ladder (C8), and if the agent cannot
# be reached the code's answer stands, marked unresolved, with nothing guessed
# (C9). Every answer carries source, confidence and one line of reason (C7).
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/tier.sh

# sutra_tier_cfg <root> <step> <field> -> the field's value, or "" when absent
sutra_tier_cfg() {
  _tc_f="${1:-}/runtime/rules/tiers.json"
  [ -f "$_tc_f" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  _tc_v="$(jq -r --arg id "$2" --arg k "$3" '.steps[] | select(.id == $id) | .[$k] // empty | if type == "array" then join(",") else tostring end' "$_tc_f" 2>/dev/null)"
  case "$_tc_v" in null) _tc_v="" ;; esac
  printf '%s' "$_tc_v"
}

# sutra_tier_threshold <root> <step> -> the number, or "" when unset (null).
# An unset threshold means the code always stands: the first release measures
# before it sets a number (RUNTIME-ACCEPTANCE-CONDITIONS.md section 4).
sutra_tier_threshold() { sutra_tier_cfg "$1" "$2" threshold; }

# sutra_tier_due <root> <step> <confidence> -> 0 when an ask is due
sutra_tier_due() {
  _td_t="$(sutra_tier_threshold "$1" "$2")"
  [ -n "$_td_t" ] || return 1
  [ -n "${3:-}" ] || return 1
  awk -v c="$3" -v t="$_td_t" 'BEGIN { exit !(c + 0 < t + 0) }'
}

# _sutra_tier_rank <root> <step> <value> -> a stringency rank, or -1 when the
# value is not on that step's ladder (an unknown answer can never be applied).
_sutra_tier_rank() {
  case "$2" in
    depth)
      case "$3" in ''|*[!0-9]*) printf '%s' -1 ;; *) printf '%s' "$3" ;; esac ;;
    placement)
      case "$3" in dref-*) printf '%s' 1 ;; ''|unresolved|none) printf '%s' 0 ;; *) printf '%s' -1 ;; esac ;;
    *)
      _tr_l="$(sutra_tier_cfg "$1" "$2" ladder)"
      [ -n "$_tr_l" ] || { printf '%s' -1; return 0; }
      printf '%s' "$_tr_l" | tr ',' '\n' | awk -v v="$3" '$0 == v { print NR; found = 1; exit } END { if (!found) print -1 }' ;;
  esac
}

# sutra_tier_apply <root> <step> <code-value> <agent-value>
#   prints the value that stands; rc 0 = the agent's answer applied (it raised),
#   rc 1 = refused (the code's value stands). C8: never lower, never sideways.
sutra_tier_apply() {
  _ta_code="$3"; _ta_agent="$4"
  # A step may forbid a class of answer outright (tiers.json never_agent). For
  # placement that class is minting, and the test is the register itself: an
  # address is accepted only when the register already holds it. Checking the
  # register rather than a spelling is what actually stops an invented
  # department, whatever the answer looks like (peer review P1-1).
  case "$(sutra_tier_cfg "$1" "$2" never_agent)" in
    *department*|*mint*)
      case "$_ta_agent" in
        dref-*)
          [ -f "${SUTRA_NATIVE_HOME:-$HOME/.sutra-native/user-kit}/domains/$_ta_agent.json" ] \
            || { printf '%s' "$_ta_code"; return 1; } ;;
      esac ;;
  esac
  _ta_rc="$(_sutra_tier_rank "$1" "$2" "$_ta_code")"
  _ta_ra="$(_sutra_tier_rank "$1" "$2" "$_ta_agent")"
  # a rank that is not a number means the answer is unreadable: refuse it
  # rather than let a numeric comparison fail open (peer review P2)
  case "$_ta_rc" in ''|*[!0-9-]*) printf '%s' "$_ta_code"; return 1 ;; esac
  case "$_ta_ra" in ''|*[!0-9-]*) printf '%s' "$_ta_code"; return 1 ;; esac
  if [ "$_ta_ra" -lt 0 ] || [ "$_ta_ra" -le "$_ta_rc" ]; then printf '%s' "$_ta_code"; return 1; fi
  printf '%s' "$_ta_agent"; return 0
}

# sutra_tier_path <proj> <sid> <turn> -> the turn's own decision file
sutra_tier_path() { printf '%s/.sutra/turn/%s/%s.tier.jsonl' "$1" "$2" "$3"; }

# sutra_tier_record <proj> <sid> <turn> <step> <value> <source> <confidence> <reason> <unresolved>
# One row per decided field. Runtime-owned (the .jsonl rule in _SUTRA_RO_RE),
# so no tool call can write, edit or remove a decision.
sutra_tier_record() {
  command -v jq >/dev/null 2>&1 || return 0
  _tw_f="$(sutra_tier_path "$1" "$2" "$3")"
  mkdir -p "$(dirname "$_tw_f")" 2>/dev/null
  _tw_now="$(date +%s 2>/dev/null)"; case "$_tw_now" in ''|*[!0-9]*) _tw_now=0 ;; esac
  _tw_row="$(jq -nc --arg t "$3" --arg s "$4" --arg v "$5" --arg src "$6" --arg c "$7" \
    --arg r "$8" --arg u "${9:-false}" --argjson ts "$_tw_now" \
    '{kind:"tier_decision", turn_id:$t, step:$s, value:$v, source:$src,
      confidence:$c, reason:$r, unresolved:($u == "true"), ts:$ts}' 2>/dev/null)"
  [ -n "$_tw_row" ] || return 0
  printf '%s\n' "$_tw_row" >> "$_tw_f" 2>/dev/null
  return 0
}

# sutra_tier_last <proj> <sid> <turn> <step> <field> -> the last recorded value
sutra_tier_last() {
  _tl_f="$(sutra_tier_path "$1" "$2" "$3")"
  [ -f "$_tl_f" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  jq -R -r --arg s "$4" --arg k "$5" 'fromjson? // empty | select(.kind == "tier_decision" and .step == $s) | .[$k] | tostring' "$_tl_f" 2>/dev/null | tail -1
}

# sutra_tier_ask_detach <root> <proj> <sid> <turn> <step> <question>
# Starts the ask in the background and returns at once: no agent call ever sits
# on the turn's hot path. The answer lands in <turn>.<step>.ask.json.
sutra_tier_ask_detach() {
  _tad_root="$1"; _tad_p="$2"; _tad_s="$3"; _tad_t="$4"; _tad_id="$5"; _tad_q="$6"
  _tad_cmd="${SUTRA_TIER_AGENT_CMD:-bash $_tad_root/runtime/lib/tier.sh --ask}"
  _tad_dir="$_tad_p/.sutra/turn/$_tad_s"
  mkdir -p "$_tad_dir" 2>/dev/null
  _tad_out="$_tad_dir/$_tad_t.$_tad_id.ask.json"
  [ -f "$_tad_out" ] && return 0            # one ask per step per turn
  case "$_tad_cmd" in '') return 3 ;; esac
  # an interpreter prefix is taken as given; anything else must have a runnable
  # first word (peer review P1-2)
  case "$_tad_cmd" in
    bash\ *|sh\ *) : ;;
    *) command -v "${_tad_cmd%% *}" >/dev/null 2>&1 || [ -x "${_tad_cmd%% *}" ] || return 3 ;;
  esac
  _tad_qf="$_tad_dir/$_tad_t.$_tad_id.ask.txt"
  printf '%s\n' "$_tad_q" > "$_tad_qf" 2>/dev/null
  ( $_tad_cmd "$_tad_qf" "$_tad_out" >/dev/null 2>&1 & ) >/dev/null 2>&1
  return 0
}

# sutra_tier_ask_read <proj> <sid> <turn> <step> -> the agent's answer JSON, or
# rc 3 when nothing has arrived / the answer is unusable (C9: code stands).
sutra_tier_ask_read() {
  _tar_f="$1/.sutra/turn/$2/$3.$4.ask.json"
  [ -s "$_tar_f" ] || return 3
  command -v jq >/dev/null 2>&1 || return 3
  jq -e 'if (.value // "") == "" then null else . end' "$_tar_f" 2>/dev/null || return 3
}

# sutra_tier_settle <root> <proj> <sid> <turn> <step> <code-value> <code-conf>
# Folds in whatever the detached ask has returned by now, once per turn per
# step: applies it only if it raises (C8), records source, confidence and one
# line of reason either way (C7), and when nothing usable came back keeps the
# code's value marked unresolved (C9). Cheap: a file test on the common path.
sutra_tier_settle() {
  _ts_root="$1"; _ts_p="$2"; _ts_s="$3"; _ts_t="$4"; _ts_id="$5"; _ts_v="$6"; _ts_c="${7:-}"
  [ -n "$(sutra_tier_last "$_ts_p" "$_ts_s" "$_ts_t" "$_ts_id" source)" ] && return 0
  sutra_tier_due "$_ts_root" "$_ts_id" "$_ts_c" || return 0   # the code stands, nothing to settle
  if _ts_ans="$(sutra_tier_ask_read "$_ts_p" "$_ts_s" "$_ts_t" "$_ts_id")"; then
    _ts_av="$(printf '%s' "$_ts_ans" | jq -r '.value // ""' 2>/dev/null)"
    _ts_ac="$(printf '%s' "$_ts_ans" | jq -r '.confidence // ""' 2>/dev/null)"
    _ts_ar="$(printf '%s' "$_ts_ans" | jq -r '.reason // ""' 2>/dev/null)"
    if _ts_kept="$(sutra_tier_apply "$_ts_root" "$_ts_id" "$_ts_v" "$_ts_av")"; then
      sutra_tier_record "$_ts_p" "$_ts_s" "$_ts_t" "$_ts_id" "$_ts_kept" agent "$_ts_ac" "$_ts_ar" false
    else
      sutra_tier_record "$_ts_p" "$_ts_s" "$_ts_t" "$_ts_id" "$_ts_kept" code "$_ts_c" \
        "the agent answered $_ts_av, which does not raise stringency; refused by the raise-only rule" false
    fi
  else
    # An ask that is still in flight is NOT unreachable: the settle that runs in
    # the same event that started it would otherwise always write "unreachable"
    # milliseconds later, and the real answer would arrive too late to count
    # (found live on 2026-09-28, 2.306.5). Leave it unsettled until the ask has
    # had its own timeout, then record the code's value as the one that stands.
    _ts_qf="$_ts_p/.sutra/turn/$_ts_s/$_ts_t.$_ts_id.ask.txt"
    if [ -f "$_ts_qf" ]; then
      _ts_mt="$(stat -f %m "$_ts_qf" 2>/dev/null || stat -c %Y "$_ts_qf" 2>/dev/null)"
      case "$_ts_mt" in ''|*[!0-9]*) _ts_mt=0 ;; esac
      _ts_now="$(date +%s 2>/dev/null)"; case "$_ts_now" in ''|*[!0-9]*) _ts_now=0 ;; esac
      [ "$((_ts_now - _ts_mt))" -lt "$(( ${SUTRA_TIER_TIMEOUT:-25} + 5 ))" ] && return 0
      _ts_why="below threshold and the agent did not answer within its timeout; the code's own value stands"
    else
      _ts_why="below threshold but no ask could be made on this box; the code's own value stands"
    fi
    sutra_tier_record "$_ts_p" "$_ts_s" "$_ts_t" "$_ts_id" "$_ts_v" code "$_ts_c" "$_ts_why" true
  fi
  return 0
}

# ---------------------------------------------------------------------------
# THE AGENT ITSELF: `tier.sh --ask <question-file> <out-file>`.
# The call goes through the review lane's own caller, so the key resolution and
# the fail-closed egress scrub live in one place and are never repeated here.
# The answer is one JSON line; anything else - unreachable, refused, garbled -
# leaves no out-file, and the code's own answer stands (C9). Sourcing this file
# never triggers this block.
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--ask" ] && [ "$(basename -- "${0:-}")" = "tier.sh" ]; then
  set -u
  _ask_q="${2:-}"; _ask_out="${3:-}"
  [ -f "$_ask_q" ] && [ -n "$_ask_out" ] || { echo "usage: tier.sh --ask <question-file> <out-file>" >&2; exit 2; }
  _ask_root="$(cd "$(dirname -- "$0")/../.." && pwd)"
  _ask_caller="$_ask_root/runtime/lib/deepseek-review.sh"
  [ -x "$_ask_caller" ] || [ -f "$_ask_caller" ] || exit 3
  _ask_raw="$(mktemp "${TMPDIR:-/tmp}/tierask.XXXXXX")" || exit 4
  # macOS ships no `timeout`, and a missing binary made EVERY ask look
  # unreachable on the founder's box (found by running 2.306.4 live on
  # 2026-09-28, not by the suite, which always injected a stub). Bound the call
  # with the runtime's own watchdog instead, the way blueprint_progress.sh does.
  DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-pro}" bash "$_ask_caller" "$_ask_q" "$_ask_raw" >/dev/null 2>&1 &
  _ask_pid=$!
  _ask_n=0
  while kill -0 "$_ask_pid" 2>/dev/null && [ "$_ask_n" -lt "${SUTRA_TIER_TIMEOUT:-25}" ]; do
    sleep 1; _ask_n=$((_ask_n + 1))
  done
  if kill -0 "$_ask_pid" 2>/dev/null; then
    pkill -P "$_ask_pid" 2>/dev/null
    kill "$_ask_pid" 2>/dev/null
  fi
  wait "$_ask_pid" 2>/dev/null
  # the caller's own exit code only reports its verdict contract; what decides
  # here is whether one usable JSON object came back
  grep -o '{.*}' "$_ask_raw" 2>/dev/null | head -1 \
    | jq -c 'if (.value // "") == "" then empty
             else {value:(.value|tostring),
                   confidence:((.confidence // "")|tostring),
                   reason:((.reason // "")|tostring|.[0:160]),
                   source:"agent"} end' > "$_ask_out" 2>/dev/null
  rm -f "$_ask_raw"
  [ -s "$_ask_out" ] || { rm -f "$_ask_out"; exit 3; }
  exit 0
fi
