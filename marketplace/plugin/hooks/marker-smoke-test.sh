#!/usr/bin/env bash
# marker-smoke-test.sh — proves session-scoped markers isolate concurrent sessions.
# Standalone: bash hooks/marker-smoke-test.sh   (exit 0 = PASS)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; . "$HERE/marker-lib.sh"
T="$(mktemp -d)"; export CLAUDE_PROJECT_DIR="$T"; mkdir -p "$T/.claude"
fail(){ echo "SMOKE-FAIL: $1"; rm -rf "$T"; exit 1; }
CLAUDE_CODE_SESSION_ID=alpha sutra_marker_set depth-registered "DEPTH=5 alpha"
CLAUDE_CODE_SESSION_ID=beta  sutra_marker_set depth-registered "DEPTH=3 beta"
CLAUDE_CODE_SESSION_ID=beta  sutra_marker_reset
CLAUDE_CODE_SESSION_ID=alpha sutra_marker_has depth-registered || fail "alpha wiped by beta reset (the bug)"
# Contract: caller body is line 1; sutra_marker_set APPENDS SESSION=/TS= stamps
# (never prepends). Assert the first line exactly + the auto-stamp presence.
[ "$(CLAUDE_CODE_SESSION_ID=alpha sutra_marker_read depth-registered | head -1)" = "DEPTH=5 alpha" ] || fail "alpha value corrupted"
CLAUDE_CODE_SESSION_ID=alpha sutra_marker_read depth-registered | grep -q '^SESSION=alpha$' || fail "alpha marker missing SESSION= auto-stamp"
CLAUDE_CODE_SESSION_ID=beta  sutra_marker_has depth-registered && fail "beta marker survived its own reset"
CLAUDE_CODE_SESSION_ID=alpha sutra_marker_gc
CLAUDE_CODE_SESSION_ID=alpha sutra_marker_has depth-registered || fail "GC deleted the current session"
( unset CLAUDE_CODE_SESSION_ID CLAUDE_SESSION_ID; d1=$(CLAUDE_PID=111 sutra_marker_dir); d2=$(CLAUDE_PID=222 sutra_marker_dir); [ "$d1" != "$d2" ] || exit 7 ) || fail "var-less sessions shared a dir"
rm -rf "$T"; echo "SMOKE-PASS: isolation + reset-safety + GC-safety + no-default-collision"
