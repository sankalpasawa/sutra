#!/usr/bin/env bash
# test-shim.sh - runtime/shim.sh runs a legacy hook exactly as a direct call.
#
# THE CLAIM UNDER TEST. sutra-turn's whole safety argument in wave 0 is "the
# same bash still runs, the same way". So: take a real registered hook
# (hooks/reset-turn-markers.sh - it branches on stdin four different ways and
# writes files), feed it five stdin fixtures, and compare a direct invocation
# against sutra_shim_run on stdout bytes, stderr bytes, exit code AND the
# forensic record the hook itself writes. Two identical fresh project roots are
# used, one per invocation, so neither run can see the other's files.
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-shim.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"
plugin="$(cd "$runtime/.." && pwd -P)"
hook="$plugin/hooks/reset-turn-markers.sh"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }

[ -x "$hook" ] || { printf 'test-shim: %s not executable\nfailed=1\n' "$hook"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-shim.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# shellcheck source=../ledger.sh
. "$runtime/ledger.sh"
# shellcheck source=../shim.sh
. "$runtime/shim.sh"

sid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

mkfix() {  # <n> <prompt-json-string>
  printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","prompt":%s}\n' \
    "$sid" "$2" > "$tmp/fix$1.json"
}
mkfix 1 '""'                                             # empty prompt
mkfix 2 '"<system-reminder>synthetic turn</system-reminder>"'  # synthetic
mkfix 3 '"build the runtime"'                            # a real prompt
mkfix 4 '"quote \" backslash \\\\ unicode é 中"' # awkward bytes
printf 'not json at all\n' > "$tmp/fix5.json"            # malformed stdin

seed() {  # <root>: an identical fresh project root for both invocations
  rm -rf "$1"; mkdir -p "$1/.claude/sessions/$sid" "$1/.enforcement"
  printf 'DEPTH=5 TASK=t SESSION=%s TS=1\n' "$sid" > "$1/.claude/sessions/$sid/depth-registered"
  printf 'SESSION=%s\n' "$sid" > "$1/.claude/input-routed"
}

# The hook records wall-clock stamps; compare the shape of its forensic rows,
# not the timestamps.
events_of() { sed -n 's/.*"event":"\([a-z-]*\)".*/\1/p' "$1" 2>/dev/null | tr '\n' ',' ; }

for n in 1 2 3 4 5; do
  fix="$tmp/fix$n.json"

  a="$tmp/a$n"; seed "$a"
  ( cd "$a" && export CLAUDE_PROJECT_DIR="$a" CLAUDE_CODE_SESSION_ID="$sid" \
      && "$hook" < "$fix" > "$tmp/a$n.out" 2> "$tmp/a$n.err" )
  a_rc=$?

  b="$tmp/b$n"; seed "$b"
  set -- $( cd "$b" && export CLAUDE_PROJECT_DIR="$b" CLAUDE_CODE_SESSION_ID="$sid" \
      && sutra_shim_run "$hook" "$fix" "$tmp/b$n.out" "$tmp/b$n.err" 5000 )
  b_rc="${1:-x}"; b_dur="${2:-x}"

  if cmp -s "$tmp/a$n.out" "$tmp/b$n.out"; then ok; else
    fail "fixture $n stdout differs"; diff -u "$tmp/a$n.out" "$tmp/b$n.out" | sed -n '1,10p' >&2
  fi
  if cmp -s "$tmp/a$n.err" "$tmp/b$n.err"; then ok; else
    fail "fixture $n stderr differs"; diff -u "$tmp/a$n.err" "$tmp/b$n.err" | sed -n '1,10p' >&2
  fi
  if [ "$a_rc" = "$b_rc" ]; then ok; else fail "fixture $n exit: direct=$a_rc shim=$b_rc"; fi

  ae="$(events_of "$a/.enforcement/marker-resets.jsonl")"
  be="$(events_of "$b/.enforcement/marker-resets.jsonl")"
  if [ "$ae" = "$be" ]; then ok; else fail "fixture $n hook forensics differ: [$ae] vs [$be]"; fi

  case "$b_dur" in
    ''|*[!0-9]*) fail "fixture $n duration not a number: [$b_dur]" ;;
    *) ok ;;
  esac
done

# The timeout path: a hook that never returns is killed and reported as 124,
# not as a silent success.
cat > "$tmp/sleeper.sh" <<'SLEEP'
#!/bin/sh
sleep 30
SLEEP
chmod 0755 "$tmp/sleeper.sh"
set -- $(sutra_shim_run "$tmp/sleeper.sh" "$tmp/fix3.json" "$tmp/s.out" "$tmp/s.err" 300)
if [ "${1:-}" = "124" ]; then ok; else fail "timeout: expected exit 124, got [${1:-}]"; fi

# A registration that points at nothing is reported, not crashed on.
set -- $(sutra_shim_run "$tmp/no-such-hook.sh" "$tmp/fix3.json" "$tmp/m.out" "$tmp/m.err" 1000)
if [ "${1:-}" = "127" ]; then ok; else fail "missing hook: expected exit 127, got [${1:-}]"; fi
grep -q 'missing hook' "$tmp/m.err" && ok || fail "missing hook: no note on stderr"

printf 'test-shim: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
