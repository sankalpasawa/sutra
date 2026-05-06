#!/usr/bin/env bash
# sutra/marketplace/native/hooks/per-turn-h-sutra.sh
#
# Native-edition H-Sutra producer hook (D49 Native v1.4 standalone wave).
#
# Standalone install: when only native@sutra is installed (no core@sutra),
# this hook is the SOLE H-Sutra producer. It classifies every UserPromptSubmit
# turn and writes a JSONL row that Native's HSutraConnector tails.
#
# Co-install: when both core@sutra + native@sutra are installed, both hooks
# fire on UserPromptSubmit. Arbitration is INTRINSIC to the shared library
# h_sutra_classify_and_write — first producer to mkdir the per-turn lock
# wins; the other returns 0 silently. No plugin-precedence assumption.
#
# Single env break-glass: SUTRA_HSUTRA_FORCE_DISABLE=1 — skips with stderr
# log line. No file toggles. Per founder direction "very, very strictly"
# (D49); honors [Never bypass governance]; loud-logged on use.
#
# Failures are SILENT (telemetry-only via stderr) so a broken H-Sutra never
# blocks Claude Code session input. Per [Customer Focus First].

set -uo pipefail

# Single env break-glass — loud-logged
if [ -n "${SUTRA_HSUTRA_FORCE_DISABLE:-}" ]; then
  NATIVE_HOME="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native}"
  mkdir -p "$NATIVE_HOME" 2>/dev/null || true
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '[%s] [h-sutra-native] DISABLED via SUTRA_HSUTRA_FORCE_DISABLE=1\n' "$TS" >> "$NATIVE_HOME/native.log" 2>/dev/null || true
  printf '[h-sutra-native] disabled via SUTRA_HSUTRA_FORCE_DISABLE=1\n' >&2
  exit 0
fi

NATIVE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$NATIVE_PLUGIN_ROOT" ]; then
  NATIVE_PLUGIN_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

# Shared lib — vendored from canonical via sutra/scripts/sync-h-sutra.sh.
HSUTRA_LIB="$NATIVE_PLUGIN_ROOT/lib/h-sutra-classify-and-write.sh"
if [ ! -r "$HSUTRA_LIB" ]; then
  printf '[h-sutra-native] lib missing at %s — row skipped.\n' "$HSUTRA_LIB" >&2
  exit 0
fi
# shellcheck source=../lib/h-sutra-classify-and-write.sh
. "$HSUTRA_LIB"

# Stdin JSON parse
HSUTRA_INPUT_JSON=""
if [ ! -t 0 ]; then
  HSUTRA_INPUT_JSON=$(cat 2>/dev/null || true)
fi
HSUTRA_PROMPT=""
HSUTRA_SESSION_ID=""
if [ -n "$HSUTRA_INPUT_JSON" ] && command -v jq >/dev/null 2>&1; then
  HSUTRA_PROMPT=$(printf '%s' "$HSUTRA_INPUT_JSON" | jq -r '.prompt // empty' 2>/dev/null || true)
  HSUTRA_SESSION_ID=$(printf '%s' "$HSUTRA_INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || true)
fi
[ -z "$HSUTRA_PROMPT" ] && exit 0

# Vendored classifier
HSUTRA_CLASSIFIER="$NATIVE_PLUGIN_ROOT/scripts/classify.sh"
if [ ! -r "$HSUTRA_CLASSIFIER" ]; then
  printf '[h-sutra-native] classifier missing at %s — row skipped.\n' "$HSUTRA_CLASSIFIER" >&2
  exit 0
fi

# Log path resolution — env override > Asawa override > default
# Same precedence chain as Native's HSutraConnector consumer (round-3 P1-2 fold)
if [ -n "${SUTRA_HSUTRA_LOG_PATH:-}" ]; then
  HSUTRA_LOG="$SUTRA_HSUTRA_LOG_PATH"
elif [ -f "$REPO_ROOT/holding/state/interaction/log.jsonl" ]; then
  HSUTRA_LOG="$REPO_ROOT/holding/state/interaction/log.jsonl"
else
  HSUTRA_LOG="$REPO_ROOT/.sutra/h-sutra.jsonl"
fi

h_sutra_classify_and_write "$HSUTRA_PROMPT" "$HSUTRA_CLASSIFIER" "$HSUTRA_LOG" "$HSUTRA_SESSION_ID" || true

exit 0
