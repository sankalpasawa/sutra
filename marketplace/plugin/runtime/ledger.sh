#!/bin/sh
# ledger.sh - append-only turn ledger + stage digest for the Sutra runtime.
#
# WHY. sutra-turn replaces ~88 independently-registered bash hooks with one
# program. The only way a reviewer can tell what that program actually did on a
# turn is an append-only row per step. This file owns the row format and the
# stage digest so bin/sutra-turn stays readable and so the tests can exercise
# the ledger without running a turn.
#
# TWO FILES, ONE TRUTH. Every row is appended to both of:
#   canonical  $CLAUDE_PROJECT_DIR/.sutra/turn/<session_id>/<turn_id>.jsonl
#              the per-turn ledger named in the runtime contract; rows carry
#              {turn_id, step_id, family, impl, exit, dur_ms, stdout_sha,
#              stderr_sha} and the final stage_digest row.
#   flat       $CLAUDE_PROJECT_DIR/.sutra/turn/<session_id>.jsonl
#              the per-session parity view consumed by bin/sutra-charcap, which
#              globs *.jsonl DIRECTLY under .sutra/turn/ and reads
#              {"kind":"step","event":E,"seq":N,"script":..,"exit":N,
#              "stdout":..,"stderr":..} plus one {"kind":"emit",...} row.
# Neither file is derivable from the other (the canonical rows carry digests,
# the flat rows carry the raw bytes charcap diffs), so both are written.
#
# NUMBERS ARE STRINGS WHERE THEY COULD BE MISTAKEN FOR A TIMESTAMP. charcap
# normalises the ledger with sed before parsing it; a bare 10- or 13-digit
# number would be rewritten to <TS> and the row would stop being valid JSON.
# Only small integers (exit, seq, dur_ms) are emitted unquoted.
#
# EVERY ROW CARRIES ts AND event. ts is epoch SECONDS as a STRING (see above:
# unquoted it would be rewritten to <TS> and break the row). bin/sutra-overhead
# measures work_ms as "first UserPromptSubmit row -> Stop stage_digest row minus
# governance_ms", which is structurally 0 unless both ends are stamped - so the
# stamp is not decoration, it is the meter's only input. One stamp is taken at
# init and re-taken at digest time: within a single event the rows are
# milliseconds apart, and the cost of a date(1) fork per row is not.
#
# POSIX sh + jq. No bashisms, no GNU coreutils, no python.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/ledger.sh

# ----------------------------------------------------------------- digests --
# sutra_sha256_file <file> -> hex digest, or the empty-string digest if absent.
sutra_sha256_file() {
  if [ ! -f "$1" ]; then printf ''; return 0; fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" 2>/dev/null | awk '{print $NF}'
  else
    printf ''
  fi
}

# sutra_tmp_dir -> the directory this process may scribble in. sutra-turn owns a
# private one and deletes it on the way out (including on ALRM/QUIT); using it
# means a run that is killed mid-hash leaves nothing behind in the SHARED temp
# root. This file is SOURCED, so TMPROOT/TMPOWNED are the caller's globals; a
# standalone caller (runtime/tests/test-ledger.sh, bin/sutra-canary before it
# has a directory) falls back to TMPDIR.
sutra_tmp_dir() {
  if [ "${TMPOWNED:-0}" = "1" ] && [ -n "${TMPROOT:-}" ] && [ -d "${TMPROOT:-}" ]; then
    printf '%s' "$TMPROOT"
  else
    printf '%s' "${TMPDIR:-/tmp}"
  fi
}

# sutra_tmp_usable -> true when sutra_tmp_dir names a directory this process may
# write into. The no-temp-dir path (TMPDIR is a regular file, or 0500) reaches
# this file with TMPOWNED=0, so sutra_tmp_dir hands back the unusable TMPDIR.
# Writing there is not merely futile: the failure is a REDIRECTION failure, and
# the shell prints its own diagnostic ("ledger.sh: line N: .../sutra-digest-...:
# Not a directory") BEFORE any `2>/dev/null` on the same simple command is set
# up - redirections are processed left to right. That line reached the host's
# stderr on every degraded turn, and on Stop / PreToolUse the host shows stderr
# to the user. The runtime's contract on that path is ONE fixed line on stdout
# and nothing else, so every scratch write is asked-then-done: probe here, and
# wrap the write itself in a brace group whose 2>/dev/null is established before
# the inner redirection is attempted.
sutra_tmp_usable() {
  _stu_d="$(sutra_tmp_dir)"
  [ -n "$_stu_d" ] && [ -d "$_stu_d" ] && [ -w "$_stu_d" ]
}

# sutra_sha256_string <string> -> hex digest of the string WITHOUT a trailing
# newline, so callers can hash a concatenation deterministically. With no
# writable scratch directory it returns the empty digest, silently: callers on
# that path (bin/sutra-turn's no-temp-dir branch) use a fixed turn id anyway.
sutra_sha256_string() {
  sutra_tmp_usable || { printf ''; return 0; }
  _sls_t="$(sutra_tmp_dir)/sutra-sha-$$"
  { printf '%s' "$1" > "$_sls_t"; } 2>/dev/null || { printf ''; return 0; }
  _sls_d="$(sutra_sha256_file "$_sls_t")"
  rm -f "$_sls_t" 2>/dev/null || true
  printf '%s' "$_sls_d"
}

# sutra_now_ms -> epoch milliseconds. jq is the only hard dependency of the
# runtime, and `jq -n now` is sub-second everywhere; BSD date is not.
sutra_now_ms() {
  if command -v jq >/dev/null 2>&1; then
    jq -n 'now*1000|floor' 2>/dev/null && return 0
  fi
  _nm="$(date +%s 2>/dev/null || echo 0)"
  printf '%s' "$((_nm * 1000))"
}

# sutra_now_s -> epoch SECONDS. date(1) is enough here and works without jq,
# which matters: the jq_failed row is stamped too.
sutra_now_s() {
  _ns_s="$(date +%s 2>/dev/null)"
  case "${_ns_s:-}" in ''|*[!0-9]*) _ns_s=0 ;; esac
  printf '%s' "$_ns_s"
}

# sutra_ledger_stamp -> the row timestamp, as a string.
sutra_ledger_stamp() {
  [ -n "${SUTRA_LEDGER_TS:-}" ] || SUTRA_LEDGER_TS="$(sutra_now_s)"
  printf '%s' "$SUTRA_LEDGER_TS"
}

# --------------------------------------------------------------- retention --
# The ledger is append-only, so without this it grows without bound: every turn
# of every session, for ever, under .sutra/turn. pipeline.json already DECLARED
# the two budgets (budgets.context.ledger_max_bytes, ledger_retention_days) and
# nothing read them. Both are enforced here, at init, before the turn's first
# row is written.
#
#   size  the flat per-session file is the one that grows inside a long session.
#         Over budget it is ROLLED to "<name>.jsonl.1" - suffix AFTER .jsonl on
#         purpose, so bin/sutra-charcap's "*.jsonl" glob under .sutra/turn/ does
#         not pick the roll-off up as a second parity view - and the next append
#         starts a fresh file.
#   age   turn files older than the budget are removed, then the session
#         directories they emptied. Guarded by a once-a-day marker
#         (.sutra/turn/.retention, no .jsonl suffix so it is likewise invisible
#         to the glob), because a find(1) walk on every hook call is not free.
#
# BSD find only: -mtime +N and -mindepth/-maxdepth, no -printf, no -delete, and
# the current turn's own files are never candidates.
sutra_ledger_retain() {
  command -v find >/dev/null 2>&1 || return 0
  [ -d "${SUTRA_LEDGER_DIR:-}" ] || return 0

  _lrt_max=5242880
  _lrt_days=30
  _lrt_pipe="${PIPELINE:-}"
  [ -n "$_lrt_pipe" ] || _lrt_pipe="${CLAUDE_PLUGIN_ROOT:-}/runtime/pipeline.json"
  if [ -f "$_lrt_pipe" ] && command -v jq >/dev/null 2>&1; then
    _lrt_v="$(jq -r '.budgets.context.ledger_max_bytes // empty' "$_lrt_pipe" 2>/dev/null)"
    case "${_lrt_v:-}" in ''|*[!0-9]*) ;; *) _lrt_max="$_lrt_v" ;; esac
    _lrt_v="$(jq -r '.budgets.context.ledger_retention_days // empty' "$_lrt_pipe" 2>/dev/null)"
    case "${_lrt_v:-}" in ''|*[!0-9]*) ;; *) _lrt_days="$_lrt_v" ;; esac
  fi

  # 1. size: roll the flat parity file when it is over budget.
  if [ -f "${SUTRA_LEDGER_FLAT:-}" ]; then
    _lrt_sz="$(wc -c < "$SUTRA_LEDGER_FLAT" 2>/dev/null | tr -d ' ')"
    case "${_lrt_sz:-}" in ''|*[!0-9]*) _lrt_sz=0 ;; esac
    if [ "$_lrt_sz" -gt "$_lrt_max" ]; then
      mv -f "$SUTRA_LEDGER_FLAT" "${SUTRA_LEDGER_FLAT}.1" 2>/dev/null || true
    fi
  fi

  # 2. age: at most once a day.
  _lrt_mark="$SUTRA_LEDGER_DIR/.retention"
  if [ -e "$_lrt_mark" ] && [ -z "$(find "$_lrt_mark" -mtime +0 2>/dev/null)" ]; then
    return 0
  fi
  { : > "$_lrt_mark"; } 2>/dev/null || return 0

  # Session directories that were ALREADY old are noted BEFORE the file prune,
  # because removing a file inside a directory stamps that directory `now` - so
  # a post-prune age test would never match. A directory a live session has just
  # created (empty and fresh) is therefore never rmdir'd out from under it.
  _lrt_olddirs="$(find "$SUTRA_LEDGER_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$_lrt_days" 2>/dev/null)"

  find "$SUTRA_LEDGER_DIR" -mindepth 2 -type f -mtime "+$_lrt_days" 2>/dev/null \
  | while IFS= read -r _lrt_f; do
      [ -n "$_lrt_f" ] || continue
      [ "$_lrt_f" = "${SUTRA_LEDGER_CANON:-}" ] && continue
      [ "$_lrt_f" = "$SUTRA_LEDGER_DIR/${SUTRA_LEDGER_SID:-}/current" ] && continue
      rm -f "$_lrt_f" 2>/dev/null || true
    done
  # rmdir, not rm -rf: it removes a session directory ONLY if the prune above
  # left it empty, and never the one this turn is writing into.
  printf '%s\n' "$_lrt_olddirs" \
  | while IFS= read -r _lrt_d; do
      [ -n "$_lrt_d" ] || continue
      [ "$_lrt_d" = "$SUTRA_LEDGER_DIR/${SUTRA_LEDGER_SID:-}" ] && continue
      rmdir "$_lrt_d" 2>/dev/null || true
    done
  return 0
}

# ------------------------------------------------------------------- state --
# sutra_ledger_init <project_dir> <session_id> <turn_id> <event>
sutra_ledger_init() {
  SUTRA_LEDGER_PROJ="$1"
  SUTRA_LEDGER_SID="$2"
  SUTRA_LEDGER_TURN="$3"
  SUTRA_LEDGER_EVENT="$4"
  SUTRA_LEDGER_DIR="$SUTRA_LEDGER_PROJ/.sutra/turn"
  mkdir -p "$SUTRA_LEDGER_DIR/$SUTRA_LEDGER_SID" 2>/dev/null || true
  SUTRA_LEDGER_CANON="$SUTRA_LEDGER_DIR/$SUTRA_LEDGER_SID/$SUTRA_LEDGER_TURN.jsonl"
  SUTRA_LEDGER_FLAT="$SUTRA_LEDGER_DIR/$SUTRA_LEDGER_SID.jsonl"
  # The accumulator is OPTIONAL. With no writable scratch directory it is the
  # empty string and every user of it (step, skip, digest) skips it outright -
  # no open attempt, so no shell diagnostic on the host's stderr. The digest
  # then hashes an empty list, which is the honest answer for a turn whose
  # steps were run by the legacy path.
  if sutra_tmp_usable; then
    SUTRA_LEDGER_ACC="$(sutra_tmp_dir)/sutra-digest-$$-$SUTRA_LEDGER_TURN"
  else
    SUTRA_LEDGER_ACC=""
  fi
  SUTRA_LEDGER_TS="$(sutra_now_s)"
  sutra_ledger_retain
  if [ -n "$SUTRA_LEDGER_ACC" ]; then
    { : > "$SUTRA_LEDGER_ACC"; } 2>/dev/null || SUTRA_LEDGER_ACC=""
  fi
  export SUTRA_LEDGER_PROJ SUTRA_LEDGER_SID SUTRA_LEDGER_TURN SUTRA_LEDGER_EVENT
  export SUTRA_LEDGER_CANON SUTRA_LEDGER_FLAT SUTRA_LEDGER_ACC SUTRA_LEDGER_TS
}

# sutra_ledger_write <file> <json-line>: one append, created on demand.
sutra_ledger_write() {
  [ -n "${1:-}" ] || return 0
  # Brace group, not `>> "$1" 2>/dev/null`: on a read-only project directory the
  # OPEN fails, and the shell's diagnostic for a failed redirection is written
  # before a `2>` on the same simple command takes effect.
  { printf '%s\n' "$2" >> "$1"; } 2>/dev/null || true
  return 0
}

# sutra_ledger_acc <line>: one entry of the stage-digest list. A no-op when the
# accumulator could not be created (see sutra_ledger_init).
sutra_ledger_acc() {
  [ -n "${SUTRA_LEDGER_ACC:-}" ] || return 0
  { printf '%s\n' "$1" >> "$SUTRA_LEDGER_ACC"; } 2>/dev/null || true
  return 0
}

# sutra_ledger_canon <json-line>
sutra_ledger_canon() { sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$1"; }
# sutra_ledger_flat <json-line>
sutra_ledger_flat()  { sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$1"; }

# ------------------------------------------------------------------- rows --
# sutra_ledger_step <seq> <step_id> <family> <impl> <script> <exit> <dur_ms> \
#                   <stdout_file> <stderr_file>
# Writes the canonical (digest) row and the flat (raw bytes) row, and records
# "<step_id>:<exit>" for the stage digest.
sutra_ledger_step() {
  _ls_seq="$1"; _ls_id="$2"; _ls_fam="$3"; _ls_impl="$4"; _ls_script="$5"
  _ls_exit="$6"; _ls_dur="$7"; _ls_out="$8"; _ls_err="$9"

  _ls_osha="$(sutra_sha256_file "$_ls_out")"
  _ls_esha="$(sutra_sha256_file "$_ls_err")"

  jq -nc \
    --arg t "$SUTRA_LEDGER_TURN" --arg id "$_ls_id" --arg fam "$_ls_fam" \
    --arg impl "$_ls_impl" --arg os "$_ls_osha" --arg es "$_ls_esha" \
    --arg ev "$SUTRA_LEDGER_EVENT" --arg ts "$(sutra_ledger_stamp)" \
    --argjson ex "$_ls_exit" --argjson d "$_ls_dur" --argjson sq "$_ls_seq" \
    '{kind:"step",turn_id:$t,seq:$sq,step_id:$id,family:$fam,impl:$impl,
      exit:$ex,dur_ms:$d,stdout_sha:$os,stderr_sha:$es,event:$ev,ts:$ts}' \
  | while IFS= read -r _ls_row; do sutra_ledger_canon "$_ls_row"; done

  # Raw bytes for the parity view. $(cat) strips trailing newlines on both
  # sides of the comparison charcap makes, so the round trip is lossless for
  # the diff it performs.
  _ls_otxt="$(cat "$_ls_out" 2>/dev/null)"
  _ls_etxt="$(cat "$_ls_err" 2>/dev/null)"
  jq -nc \
    --arg ev "$SUTRA_LEDGER_EVENT" --arg id "$_ls_id" --arg sc "$_ls_script" \
    --arg o "$_ls_otxt" --arg e "$_ls_etxt" --arg t "$SUTRA_LEDGER_TURN" \
    --arg ts "$(sutra_ledger_stamp)" \
    --argjson sq "$_ls_seq" --argjson ex "$_ls_exit" --argjson d "$_ls_dur" \
    '{kind:"step",event:$ev,seq:$sq,step_id:$id,script:$sc,exit:$ex,
      dur_ms:$d,stdout:$o,stderr:$e,turn_id:$t,ts:$ts}' \
  | while IFS= read -r _ls_row; do sutra_ledger_flat "$_ls_row"; done

  sutra_ledger_acc "$(printf '%s:%s' "$_ls_id" "$_ls_exit")"
}

# sutra_ledger_skip <seq> <step_id> <script> <reason>: a step that was selected
# but not executed (blocked turn, class B/C after a deny). Kind is "skip", NOT
# "step", so a reader never mistakes it for an execution.
sutra_ledger_skip() {
  jq -nc --arg ev "$SUTRA_LEDGER_EVENT" --arg id "$2" --arg sc "$3" \
         --arg r "$4" --arg t "$SUTRA_LEDGER_TURN" --argjson sq "$1" \
         --arg ts "$(sutra_ledger_stamp)" \
    '{kind:"skip",event:$ev,seq:$sq,step_id:$id,script:$sc,reason:$r,turn_id:$t,ts:$ts}' \
  | while IFS= read -r _lk_row; do
      sutra_ledger_canon "$_lk_row"; sutra_ledger_flat "$_lk_row"
    done
  sutra_ledger_acc "$(printf '%s:skip' "$2")"
}

# sutra_ledger_emit <additionalContext> <passthrough> <blocked> <blocked_stderr>
sutra_ledger_emit() {
  jq -nc --arg ev "$SUTRA_LEDGER_EVENT" --arg ac "$1" --arg p "$2" \
         --arg be "$4" --arg t "$SUTRA_LEDGER_TURN" --argjson b "$3" \
         --arg ts "$(sutra_ledger_stamp)" \
    '{kind:"emit",event:$ev,turn_id:$t,additionalContext:$ac,passthrough:$p,
      blocked:$b,blocked_stderr:$be,ts:$ts}' \
  | while IFS= read -r _le_row; do
      sutra_ledger_canon "$_le_row"; sutra_ledger_flat "$_le_row"
    done
}

# sutra_ledger_note <kind> <message> [step_id]: a non-step row (killswitch,
# jq_failed, orphan_turn, legacy_skip, legacy_registry_missing, dropped_json).
# Written with jq when jq works, by hand when it does not - the jq_failed row is
# exactly the row that cannot depend on jq. step_id is carried when the note is
# ABOUT one step, which dropped_json always is.
sutra_ledger_note() {
  _ln_sid="${3:-}"
  if command -v jq >/dev/null 2>&1 && printf '{}' | jq -e . >/dev/null 2>&1; then
    jq -nc --arg k "$1" --arg m "$2" --arg ev "${SUTRA_LEDGER_EVENT:-}" \
           --arg t "${SUTRA_LEDGER_TURN:-}" --arg sid "$_ln_sid" \
           --arg ts "$(sutra_ledger_stamp)" \
      '{kind:$k,event:$ev,turn_id:$t,note:$m,ts:$ts}
       + (if $sid == "" then {} else {step_id:$sid} end)' \
    | while IFS= read -r _ln_row; do
        sutra_ledger_canon "$_ln_row"; sutra_ledger_flat "$_ln_row"
      done
  else
    _ln_m="$(printf '%s' "$2" | tr -d '"\\' | tr '\n' ' ')"
    _ln_row="$(printf '{"kind":"%s","event":"%s","turn_id":"%s","note":"%s","ts":"%s"}' \
      "$1" "${SUTRA_LEDGER_EVENT:-}" "${SUTRA_LEDGER_TURN:-}" "$_ln_m" "$(sutra_ledger_stamp)")"
    sutra_ledger_canon "$_ln_row"; sutra_ledger_flat "$_ln_row"
  fi
}

# sutra_ledger_digest: stage_digest = sha256 of the ordered "<step_id>:<exit>"
# list, newline-joined WITHOUT a trailing newline. Appended as the last row.
sutra_ledger_digest() {
  _ld_list=""
  if [ -n "${SUTRA_LEDGER_ACC:-}" ]; then
    _ld_list="$(cat "$SUTRA_LEDGER_ACC" 2>/dev/null)"
  fi
  _ld_sha="$(sutra_sha256_string "$_ld_list")"
  # grep -c prints 0 AND exits 1 when nothing matched, so `|| echo 0` appends a
  # SECOND line and _ld_n becomes the two-line string "0\n0" - which --argjson
  # rejects, killing the stage_digest row and leaking a jq error to stderr on
  # every zero-step turn (a UserPromptExpansion run selects no steps at all).
  # Take grep's output and validate it instead of guarding on its exit code.
  _ld_n="$(printf '%s\n' "$_ld_list" | grep -c . 2>/dev/null)"
  case "$_ld_n" in ''|*[!0-9]*) _ld_n=0 ;; esac
  # The digest row closes the turn, so it is re-stamped: bin/sutra-overhead uses
  # the Stop digest row's ts as the end of the turn's wall clock.
  SUTRA_LEDGER_TS="$(sutra_now_s)"
  jq -nc --arg ev "${SUTRA_LEDGER_EVENT:-}" --arg t "${SUTRA_LEDGER_TURN:-}" \
         --arg d "$_ld_sha" --argjson n "$_ld_n" --arg ts "$SUTRA_LEDGER_TS" \
    '{kind:"stage_digest",event:$ev,turn_id:$t,steps:$n,stage_digest:$d,ts:$ts}' \
  | while IFS= read -r _ld_row; do
      sutra_ledger_canon "$_ld_row"; sutra_ledger_flat "$_ld_row"
    done
  if [ -n "${SUTRA_LEDGER_ACC:-}" ]; then
    rm -f "$SUTRA_LEDGER_ACC" 2>/dev/null || true
  fi
  printf '%s' "$_ld_sha"
}
