#!/bin/sh
# flags.sh - resolves the MVP-1 per-box flag for the runtime marker steps
# (Sutra Runtime, D1). Sourced by sh AND bash alike - POSIX sh only, no
# bashisms, no GNU coreutils.
#
# WHY A SEPARATE FILE. Two native steps (markers_write, markers_diff) need
# the identical precedence chain. Duplicating it would let the two drift.
#
# PRECEDENCE (highest wins), per D1:
#   1. HOME unset or empty     -> off, source=no-home (checked FIRST: no
#      filesystem read happens at all on this branch - see below)
#   2. ~/.sutra-runtime-markers-disabled exists -> off, source=disabled
#   3. SUTRA_RUNTIME_MARKERS env (on|shadow|off) -> that value, source=env
#      (anything else -> off, source=invalid)
#   4. ~/.sutra-runtime-markers file, first line (on|shadow|off)
#      -> that value, source=file (anything else -> off, source=invalid)
#   5. absent everywhere -> off, source=default
#
# HOME-UNSET IS CHECKED BEFORE ANYTHING ELSE READS A FILE. Building the flag
# paths as "$HOME/.sutra-runtime-markers" (never "~/.sutra-runtime-markers")
# is what makes this safe in the first place - tilde expansion with HOME
# unset falls back to the password-db home and would read the REAL user's
# flag inside a hermetic/CI run. Checking HOME first means that fallback
# path is never even constructed, let alone stat'd.
#
# The runtime kill-switch (SUTRA_RUNTIME_DISABLED / ~/.sutra-runtime-disabled)
# is a SEPARATE mechanism owned by bin/sutra-turn step 0; a native step is
# never spawned at all when it is set, so this file has nothing to say about
# it (D1).
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/flags.sh

# sutra_flag_markers -> sets SUTRA_MARKERS_MODE (on|shadow|off) and
# SUTRA_MARKERS_SOURCE (no-home|disabled|env|file|invalid|default). Always
# returns 0; never reads a file when HOME is unset or empty.
sutra_flag_markers() {
  SUTRA_MARKERS_MODE=off
  SUTRA_MARKERS_SOURCE=default

  if [ -z "${HOME:-}" ]; then
    SUTRA_MARKERS_MODE=off
    SUTRA_MARKERS_SOURCE=no-home
    return 0
  fi

  _sfm_disabled="$HOME/.sutra-runtime-markers-disabled"
  if [ -f "$_sfm_disabled" ]; then
    SUTRA_MARKERS_MODE=off
    SUTRA_MARKERS_SOURCE=disabled
    return 0
  fi

  if [ -n "${SUTRA_RUNTIME_MARKERS:-}" ]; then
    case "$SUTRA_RUNTIME_MARKERS" in
      on)     SUTRA_MARKERS_MODE=on;     SUTRA_MARKERS_SOURCE=env ;;
      shadow) SUTRA_MARKERS_MODE=shadow; SUTRA_MARKERS_SOURCE=env ;;
      off)    SUTRA_MARKERS_MODE=off;    SUTRA_MARKERS_SOURCE=env ;;
      *)      SUTRA_MARKERS_MODE=off;    SUTRA_MARKERS_SOURCE=invalid ;;
    esac
    return 0
  fi

  _sfm_file="$HOME/.sutra-runtime-markers"
  if [ -f "$_sfm_file" ]; then
    _sfm_val="$(head -1 "$_sfm_file" 2>/dev/null | tr -d '[:space:]')"
    case "$_sfm_val" in
      on)     SUTRA_MARKERS_MODE=on;     SUTRA_MARKERS_SOURCE=file ;;
      shadow) SUTRA_MARKERS_MODE=shadow; SUTRA_MARKERS_SOURCE=file ;;
      off)    SUTRA_MARKERS_MODE=off;    SUTRA_MARKERS_SOURCE=file ;;
      *)      SUTRA_MARKERS_MODE=off;    SUTRA_MARKERS_SOURCE=invalid ;;
    esac
    return 0
  fi

  SUTRA_MARKERS_MODE=off
  SUTRA_MARKERS_SOURCE=default
  return 0
}
