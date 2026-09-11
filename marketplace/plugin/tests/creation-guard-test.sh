#!/usr/bin/env bash
# creation-guard-test.sh — 7 cases for creation-guard.sh + creation-stop-check.sh (Directory Program phase G).
# Usage: bash creation-guard-test.sh [new-dir|new-file|new-charter|missing-domain|new-kind|bypass|kill-switch]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; HOOKS="$(cd "$HERE/../hooks" && pwd)"
ONLY="${1:-}"; FAIL=0; RUN=0
die(){ echo "FAIL [$1]: $2"; FAIL=1; }
ok(){ echo "ok   [$1]"; }
mk(){ ROOT="$(mktemp -d)"; export CLAUDE_PROJECT_DIR="$ROOT"; export CLAUDE_CODE_SESSION_ID="t-$RANDOM"; SID="$CLAUDE_CODE_SESSION_ID"
  export HOME="$ROOT/home"; mkdir -p "$HOME" "$ROOT/.claude/sessions/$SID" "$ROOT/holding/departments/dispatch"
  ( cd "$ROOT" && git init -q . && git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init )
  printf '# Charter: Dispatch\n\n## Obligations\n- test\n' > "$ROOT/holding/departments/dispatch/CHARTER.md"
  ( cd "$ROOT" && git add -A >/dev/null 2>&1 && git -c user.email=t@t -c user.name=t commit -q -m fixture ); }
payload(){ printf '{"session_id":"%s","tool_name":"Write","tool_input":{"file_path":"%s"}}' "$SID" "$1"; }
guard(){ payload "$1" | bash "$HOOKS/creation-guard.sh" 2>"$ROOT/.claude/err"; echo $?; }
place(){ printf 'DOMAIN_REF=dref-test\nCHARTER_ID=C-test\nSESSION=%s\n' "$SID" > "$ROOT/.claude/sessions/$SID/placement-registered"; }
want(){ [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
if want new-dir; then RUN=$((RUN+1)); mk; rc=$(guard "$ROOT/newdept/notes.md"); grep -q 'missing: placement domain charter' "$ROOT/.claude/err" && [ "$rc" = 0 ] || die new-dir "warn should list all three and exit 0 (rc=$rc): $(head -2 "$ROOT/.claude/err")"
  echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/newdept/notes.md"); [ "$rc" = 2 ] && ok new-dir || die new-dir "hard should exit 2 (rc=$rc)"; fi
if want new-file; then RUN=$((RUN+1)); mk; place; echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/holding/departments/dispatch/RUNBOOK-x.md"); [ "$rc" = 0 ] && ! grep -q missing "$ROOT/.claude/err" && grep -qx 'holding/departments/dispatch/RUNBOOK-x.md' "$ROOT/.claude/sessions/$SID/creation-guard-seen" && ok new-file || die new-file "expected complete (rc=$rc): $(cat "$ROOT/.claude/err")"; fi
if want new-charter; then RUN=$((RUN+1)); mk; place; mkdir -p "$ROOT/holding/departments/brand"; printf '# Brand Department\n' > "$ROOT/holding/departments/brand/README.md"; echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/holding/departments/brand/CHARTER.md"); [ "$rc" = 0 ] && ok new-charter || die new-charter "charter creation should pass (rc=$rc): $(cat "$ROOT/.claude/err")"; fi
if want missing-domain; then RUN=$((RUN+1)); mk; printf 'DOMAIN_REF=unresolved\nSESSION=%s\n' "$SID" > "$ROOT/.claude/sessions/$SID/placement-registered"; echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/somewhere/new.py"); [ "$rc" = 2 ] && grep -q 'domain' "$ROOT/.claude/err" && ok missing-domain || die missing-domain "rc=$rc: $(cat "$ROOT/.claude/err")"; fi
if want new-kind; then RUN=$((RUN+1)); mk; place; rc=$(guard "$ROOT/holding/departments/dispatch/thing.xyz"); grep -q 'NEW KIND DETECTED' "$ROOT/.claude/err" && grep -q 'NEW-THING-PROTOCOL' "$ROOT/.claude/err" && [ "$rc" = 0 ] || die new-kind "warn should print the event and exit 0 (rc=$rc)"
  echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/holding/departments/dispatch/thing.xyz"); [ "$rc" = 2 ] && ok new-kind || die new-kind "hard should exit 2 (rc=$rc)"; fi
if want bypass; then RUN=$((RUN+1)); mk; mkdir -p "$ROOT/rogue"; echo x > "$ROOT/rogue/created-by-bash.md"; ( cd "$ROOT" && bash "$HOOKS/creation-stop-check.sh" 2>"$ROOT/.claude/err" ); rc=$?; grep -q 'rogue/created-by-bash.md' "$ROOT/.claude/err" && [ "$rc" = 0 ] || die bypass "warn should list the file and exit 0 (rc=$rc): $(cat "$ROOT/.claude/err")"
  echo hard > "$ROOT/.claude/creation-guard-mode"; ( cd "$ROOT" && bash "$HOOKS/creation-stop-check.sh" 2>"$ROOT/.claude/err" ); rc=$?; [ "$rc" = 2 ] && ok bypass || die bypass "hard should exit 2 (rc=$rc)"
  echo 'rogue/created-by-bash.md' >> "$ROOT/.claude/sessions/$SID/creation-guard-seen"; ( cd "$ROOT" && bash "$HOOKS/creation-stop-check.sh" 2>"$ROOT/.claude/err" ); rc=$?; [ "$rc" = 0 ] || die bypass "seen file should not block (rc=$rc)"; fi
if want kill-switch; then RUN=$((RUN+1)); mk; touch "$HOME/.creation-guard-disabled"; echo hard > "$ROOT/.claude/creation-guard-mode"; rc=$(guard "$ROOT/anything/new.md"); [ "$rc" = 0 ] && grep -q 'skipped-kill-switch' "$ROOT/.sutra/creation-guard.jsonl" && ok kill-switch || die kill-switch "rc=$rc; audit row missing"; fi
echo "creation-guard-test: $RUN case(s), fail=$FAIL"; exit $FAIL
