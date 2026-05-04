#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/lib/telemetry-shared-path.sh
# TS=2026-05-04
# ═══════════════════════════════════════════════════════════════════════════════
# telemetry-shared-path.sh — cross-session telemetry fan-in (sourced library)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Promoted L1->L0 in D38 Wave D 2026-05-04 per codex consult 1777875522
# (PASS conditional on plugin/lib/ being added to D38 PLUGIN_RUNTIME — done
# in Wave A, sutra commit 4784cae). Activation contract per codex: source-
# compatible — callers `source` this file, no hooks.json registration.
#
# Purpose: bridge the D33 client firewall (or any multi-tenant Sutra
# deployment) without breaking it.
#
# Shape:
#   - Each plugin-installed client writes its own telemetry to
#     ~/.sutra/telemetry/<client>/<stream>.jsonl (one-way, client → shared).
#   - Aggregator (Asawa Analytics or fleet operator) reads from
#     ~/.sutra/telemetry/*/ — fan-in without cross-repo reads.
#   - No client reads any other client's telemetry.
#   - Bidirectional feedback to clients flows only through plugin update
#     round-trips (out of band from this telemetry pipe).
#
# Functions exposed (source this file):
#   telemetry_root         — prints ~/.sutra/telemetry (override via $SUTRA_TELEMETRY_ROOT)
#   telemetry_client_dir   — given a client name, prints its dir (mkdir -p)
#   telemetry_emit         — emits a JSON line to <client>/<stream>.jsonl
#   telemetry_fleet_list   — lists all clients with telemetry dirs
#   telemetry_stream_glob  — prints find-pattern matching all client streams
#
# Convention: client name is whatever the caller passes; no hardcoded list.
# Common names in Asawa context: billu, paisa, ppr, maze, dayflow, sutra,
# asawa. T4 fleet: any string the client chooses (typically the repo basename).
#
# Exit behavior: library only; do not run directly.
# Ownership: Sutra plugin (canonical here); Asawa Analytics consumes the
# fan-in via separate aggregator scripts in holding/.
# ═══════════════════════════════════════════════════════════════════════════════

set -u

telemetry_root() {
  printf '%s' "${SUTRA_TELEMETRY_ROOT:-$HOME/.sutra/telemetry}"
}

telemetry_client_dir() {
  local client="$1"
  local dir
  dir="$(telemetry_root)/$client"
  mkdir -p "$dir" 2>/dev/null || return 1
  printf '%s' "$dir"
}

telemetry_emit() {
  local client="$1"
  local stream="$2"
  local payload="$3"
  local dir
  dir="$(telemetry_client_dir "$client")" || return 1
  local target="$dir/${stream}.jsonl"
  printf '%s\n' "$payload" >> "$target" 2>/dev/null || return 1
}

telemetry_fleet_list() {
  local root
  root="$(telemetry_root)"
  [ -d "$root" ] || return 0
  ( cd "$root" && ls -1d */ 2>/dev/null | sed 's|/$||' )
}

telemetry_stream_glob() {
  printf '%s/*/*.jsonl' "$(telemetry_root)"
}
