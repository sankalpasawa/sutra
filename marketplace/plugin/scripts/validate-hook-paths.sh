#!/bin/bash
# validate-hook-paths.sh — pre-release CI guard.
#
# Reads marketplace/plugin/hooks/hooks.json and confirms every `command` path
# referenced (after expanding ${CLAUDE_PLUGIN_ROOT}) exists on disk inside the
# plugin tree, is git-tracked, AND is executable. Catches the
# description-vs-source-tree drift class (v2.10.0 incident: hooks.json
# referenced inbox-display.sh, file existed in working tree but was never
# git add'd → installs from the published tarball saw `No such file or
# directory` on every SessionStart).
#
# EXEC BIT (added with the sutra runtime, W0a). "Exists and is tracked" was
# never the whole promise: a hook shipped 0644 is present, tracked, and still
# dead — the host reports `Permission denied` at exactly the moment the gate
# was supposed to fire, and a 0644 shim makes sutra-turn fail a step mid-turn.
# git carries the mode in its index, so in a checkout the index mode is the
# authority (100755); outside a checkout — an installed plugin, an extracted
# tarball, a fixture — the filesystem x-bit is.
#
# EVERY COMMAND, NOT EVERY REGISTRATION. The extractor reads every
# ${CLAUDE_PLUGIN_ROOT} token in a command instead of only the first, because
# a wrapped registration ("<wrapper> <script>") hid the wrapped script from
# this guard entirely: on the live registry 10 referenced scripts were never
# checked, and one of those shipped 0644.
#
# TOOL FLOOR: bash 3.2 + jq. The extraction used to run inside a python3
# heredoc, which made python3 a hard dependency of the release gate for work
# jq already does — and the runtime this guard protects (sutra-turn, shim.sh,
# ledger.sh, selftest.sh) is POSIX sh + jq by contract. The jq walk below is
# the same walk sutra-turn's legacy_registrations does: command-type entries
# only, every whitespace-separated token, ${CLAUDE_PLUGIN_ROOT}/ prefix
# stripped, sorted and de-duplicated.
#
# TWO REGISTRIES (added with the collapse, W0a). hooks.json now names two
# paths — bin/sutra-turn and bin/sutra-canary — while the legacy scripts it used
# to list are executed by the runtime as pipeline shims and listed in
# hooks/hooks.json.step3. Scanning only the collapsed file would have quietly
# retired this guard the day it was needed most, so both files are scanned with
# the same extraction and the counts are reported separately:
#   validate-hook-paths: runtime 2/2, legacy 88/88 hook paths exist, ...
# Both numbers are DERIVED from the files, never asserted here: the legacy count
# is distinct ${CLAUDE_PLUGIN_ROOT} paths, so it sits below the registration
# count whenever one script is registered under two matchers (today: 92
# registrations, 88 distinct paths). Nothing in this script goes red when either
# number moves — only a path that is missing, untracked or 0644 does.
#
# FIXTURE MODE. `--fixture <dir>` points the whole validator at a fixture
# hooks tree instead of the plugin, so the exec-bit assert can be proven
# against a file that is deliberately 0644 (runtime/tests/mode644/). Without
# that, the assert is untested and the guard is decoration. <dir> may be the
# fixture's plugin root (containing hooks/hooks.json) or the hooks dir itself.
#
# Exit 0: every hook path exists, is tracked, and is executable.
# Exit 1: at least one hook path missing, untracked, or not executable.
# Exit 2: bad usage.
#
# Run pre-commit, in tests/run-all.sh, and as a release-cut acceptance gate.

# Git exports GIT_DIR/GIT_INDEX_FILE to hook subprocesses; in a WORKTREE those
# point at the worktree's private gitdir and break the `cd + git ls-files`
# subshells below (every path reads as untracked: 0/67, 2026-08-18). This
# script only ever inspects git state relative to PLUGIN_ROOT — inherited git
# env is never wanted.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX
set -u

FIXTURE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --fixture)
      FIXTURE="${2:-}"
      if [ -z "$FIXTURE" ]; then
        echo "validate-hook-paths: FAIL — --fixture needs a directory" >&2
        exit 2
      fi
      shift 2
      ;;
    --fixture=*)
      FIXTURE="${1#--fixture=}"
      shift
      ;;
    -h|--help)
      echo "usage: validate-hook-paths.sh [--fixture <dir>]"
      exit 0
      ;;
    *)
      echo "validate-hook-paths: FAIL — unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -n "$FIXTURE" ]; then
  if [ -f "$FIXTURE/hooks/hooks.json" ]; then
    PLUGIN_ROOT="$(cd "$FIXTURE" && pwd)"
  elif [ -f "$FIXTURE/hooks.json" ]; then
    # The hooks dir itself was given; commands are relative to its parent.
    PLUGIN_ROOT="$(cd "$FIXTURE/.." && pwd)"
  else
    echo "validate-hook-paths: FAIL — no hooks.json under fixture $FIXTURE" >&2
    exit 2
  fi
  echo "validate-hook-paths: FIXTURE MODE — root $PLUGIN_ROOT"
else
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
fi
HOOKS_JSON="$PLUGIN_ROOT/hooks/hooks.json"

if [ ! -f "$HOOKS_JSON" ]; then
  echo "validate-hook-paths: FAIL — hooks.json missing at $HOOKS_JSON" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "validate-hook-paths: FAIL — jq required (the runtime's one hard dependency)" >&2
  exit 1
fi
if ! jq -e . "$HOOKS_JSON" >/dev/null 2>&1; then
  echo "validate-hook-paths: FAIL — hooks.json is not valid JSON: $HOOKS_JSON" >&2
  exit 1
fi

MISSING_FS=()
UNTRACKED=()
NOT_EXEC=()
TOTAL=0
OK=0
SUMMARY=""
SCAN_FAILED=0

# Best-effort: detect git status only when run inside a git checkout.
GIT_OK=0
if (cd "$PLUGIN_ROOT" && git rev-parse --git-dir >/dev/null 2>&1); then
  GIT_OK=1
fi

# scan_registry <hooks-json> <label>
#
# Extract every command path from ONE registry file; drop the
# ${CLAUDE_PLUGIN_ROOT}/ prefix; check each path for presence, git-tracking and
# the exec bit. ltrimstr, not a regex: the prefix is a literal, and `${...}`
# inside a jq regex is a quoting trap nobody should have to re-read.
# Counts are accumulated into the global TOTAL/OK and reported per label.
scan_registry() {
  _file="$1"
  _label="$2"
  _ok=0
  _total=0

  if ! jq -e . "$_file" >/dev/null 2>&1; then
    echo "validate-hook-paths: FAIL — $_label registry is not valid JSON: $_file" >&2
    SCAN_FAILED=1
    return 1
  fi

  _paths=$(jq -r --arg P '${CLAUDE_PLUGIN_ROOT}/' '
    [ (.hooks // {}) | to_entries[] | .value[] | (.hooks // [])[]
      | select((.type // "command") == "command")
      | (.command // "")
      | split(" ")[]
      | select(startswith($P))
      | ltrimstr($P)
      | select(length > 0) ]
    | unique | .[]' "$_file")

  if [ -z "$_paths" ]; then
    echo "validate-hook-paths: FAIL — no \${CLAUDE_PLUGIN_ROOT} commands found in $_file" >&2
    SCAN_FAILED=1
    return 1
  fi

  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    _total=$((_total+1))
    abs="$PLUGIN_ROOT/$rel"
    if [ ! -f "$abs" ]; then
      MISSING_FS+=("[$_label] $rel")
      continue
    fi
    if [ "$GIT_OK" = "1" ]; then
      if ! (cd "$PLUGIN_ROOT" && git ls-files --error-unmatch "$rel" >/dev/null 2>&1); then
        UNTRACKED+=("[$_label] $rel")
        continue
      fi
      # In a checkout the INDEX mode is what ships in the tarball, so that is
      # the authority — a local chmod +x on an index-0644 file is still a bug.
      mode="$( (cd "$PLUGIN_ROOT" && git ls-files -s -- "$rel" 2>/dev/null) | awk 'NR==1{print $1}' )"
      if [ "$mode" != "100755" ]; then
        NOT_EXEC+=("[$_label] $rel (git index mode ${mode:-unknown}, want 100755)")
        continue
      fi
    else
      # No checkout (installed plugin, extracted tarball, fixture): the
      # filesystem x-bit is all there is, and all the host will look at.
      if [ ! -x "$abs" ]; then
        NOT_EXEC+=("[$_label] $rel (filesystem mode $(ls -l "$abs" | awk '{print $1}'), not executable)")
        continue
      fi
    fi
    _ok=$((_ok+1))
  done <<< "$_paths"

  OK=$((OK+_ok))
  TOTAL=$((TOTAL+_total))
  if [ -n "$SUMMARY" ]; then
    SUMMARY="$SUMMARY, $_label $_ok/$_total"
  else
    SUMMARY="$_label $_ok/$_total"
  fi
  return 0
}

# TWO REGISTRIES, REPORTED SEPARATELY.
#
# Once hooks.json is collapsed onto the sutra-turn runtime it names exactly two
# paths — bin/sutra-turn and bin/sutra-canary — and this guard, which existed to
# catch a hook that is registered but missing, untracked or 0644, would have
# stopped looking at every legacy script the runtime actually executes. Those
# scripts are still shipped, still fired (as pipeline shims), and still exactly
# as capable of being untracked or 0644 as before; the only thing that changed
# is which file lists them. hooks/hooks.json.step3 is that list, so it is
# scanned with the same extraction and the same three asserts, and the two
# counts are printed separately ("runtime 2/2, legacy 88/88" today) so a release
# reader can see at a glance that neither side went quiet. Both counts are
# derived from the registries at run time; neither is written down here.
STEP3_JSON="$PLUGIN_ROOT/hooks/hooks.json.step3"

COLLAPSED=$(jq -r '
  [ .hooks // {} | to_entries[] | .value[] | (.hooks // [])[]
    | (.command // "") | split(" ")[] | sub(".*/"; "") ]
  | if (index("sutra-turn") != null or index("sutra-canary") != null)
    then "yes" else "no" end' "$HOOKS_JSON" 2>/dev/null || echo "no")

if [ "$COLLAPSED" = "yes" ]; then
  PRIMARY_LABEL="runtime"
else
  PRIMARY_LABEL="hooks.json"
fi

scan_registry "$HOOKS_JSON" "$PRIMARY_LABEL"

if [ -f "$STEP3_JSON" ]; then
  scan_registry "$STEP3_JSON" "legacy"
else
  echo "validate-hook-paths: note — no hooks/hooks.json.step3 snapshot to scan (pre-collapse tree or fixture)"
fi

# The summary states only what was actually asserted: outside a checkout no
# git-tracking claim is made, because none was checked (a guard that reports a
# check it skipped is the failure mode this file exists to prevent).
if [ "$GIT_OK" = "1" ]; then
  echo "validate-hook-paths: $SUMMARY hook paths exist, are git-tracked and are executable"
  echo "validate-hook-paths: $OK/$TOTAL hook paths exist and are git-tracked"
  echo "  exec-bit source: git index mode (100755 required)"
else
  echo "validate-hook-paths: $SUMMARY hook paths exist and are executable"
  echo "validate-hook-paths: $OK/$TOTAL hook paths exist and are executable"
  echo "  (note: not in a git checkout — filesystem presence + x-bit checked, git-tracking NOT checked)"
fi

if [ "${#MISSING_FS[@]}" -gt 0 ]; then
  echo "  MISSING ON DISK:" >&2
  for p in "${MISSING_FS[@]}"; do echo "    - $p" >&2; done
fi
if [ "${#UNTRACKED[@]}" -gt 0 ]; then
  echo "  UNTRACKED IN GIT (will not ship in plugin tarball):" >&2
  for p in "${UNTRACKED[@]}"; do echo "    - $p" >&2; done
fi
if [ "${#NOT_EXEC[@]}" -gt 0 ]; then
  echo "  NOT EXECUTABLE (host will report Permission denied at hook time):" >&2
  for p in "${NOT_EXEC[@]}"; do echo "    - $p" >&2; done
fi

[ "$SCAN_FAILED" -eq 0 ] && [ "${#MISSING_FS[@]}" -eq 0 ] && [ "${#UNTRACKED[@]}" -eq 0 ] \
  && [ "${#NOT_EXEC[@]}" -eq 0 ] && exit 0
exit 1
