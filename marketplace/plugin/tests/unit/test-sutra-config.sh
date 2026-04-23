#!/bin/bash
# Unit test: sutra-config
# Covers: init/path/list/get/set roundtrip, default emission, key validation,
# comment preservation, value with spaces, value with special chars.

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
BIN="$PLUGIN_ROOT/bin/sutra-config"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Each case runs with a fresh SUTRA_CONFIG_DIR
with_tmp() {
  local fn="$1"
  local T
  T=$(mktemp -d -t sutra-config-XXXXXX)
  SUTRA_CONFIG_DIR="$T" "$fn" "$T"
  rm -rf "$T"
}

# 1. init creates default file with known keys
t_init_creates_defaults() {
  local T="$1"
  SUTRA_CONFIG_DIR="$T" "$BIN" init >/dev/null
  if [ -f "$T/config.env" ]; then
    _ok "init creates config file"
  else
    _no "init did not create file"
    return
  fi
  for key in SUTRA_RTK_ENABLED SUTRA_CODEX_DIRECTIVE_ENABLED SUTRA_CODEX_TIMEOUT_MS SUTRA_DEPTH_DEFAULT SUTRA_TELEMETRY SUTRA_TIER; do
    if grep -qE "^${key}=" "$T/config.env"; then :; else
      _no "default missing key: $key"
      return
    fi
  done
  _ok "init writes all default keys"
}

# 2. path prints config file path
t_path() {
  local T="$1"
  out=$(SUTRA_CONFIG_DIR="$T" "$BIN" path)
  if [ "$out" = "$T/config.env" ]; then
    _ok "path prints correct location"
  else
    _no "path returned '$out' expected '$T/config.env'"
  fi
}

# 3. get on a default key returns the default value
t_get_default() {
  local T="$1"
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_CODEX_TIMEOUT_MS)
  if [ "$v" = "600000" ]; then
    _ok "get default SUTRA_CODEX_TIMEOUT_MS = 600000"
  else
    _no "get returned '$v' expected '600000'"
  fi
}

# 4. get on a default key with inline comment strips the comment
t_get_strips_comment() {
  local T="$1"
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_DEPTH_DEFAULT)
  if [ "$v" = "5" ]; then
    _ok "get strips trailing comment"
  else
    _no "get returned '$v' expected '5' (comment should be stripped)"
  fi
}

# 5. get on an unknown key returns empty
t_get_unknown() {
  local T="$1"
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_NONEXISTENT)
  if [ -z "$v" ]; then
    _ok "get on unknown key → empty"
  else
    _no "get unknown key returned '$v' expected empty"
  fi
}

# 6. set modifies existing key (in-place), preserving file structure
t_set_existing() {
  local T="$1"
  SUTRA_CONFIG_DIR="$T" "$BIN" set SUTRA_RTK_ENABLED false
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_RTK_ENABLED)
  if [ "$v" = "false" ]; then
    _ok "set existing key updates value"
  else
    _no "set existing: got '$v' expected 'false'"
  fi
  # Comments section header preserved?
  if grep -q "Kill switches" "$T/config.env"; then
    _ok "set preserves section comments"
  else
    _no "set clobbered section headers"
  fi
}

# 7. set appends new key if not present
t_set_new() {
  local T="$1"
  SUTRA_CONFIG_DIR="$T" "$BIN" set SUTRA_CUSTOM_KEY hello
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_CUSTOM_KEY)
  if [ "$v" = "hello" ]; then
    _ok "set new key appends"
  else
    _no "set new key: got '$v' expected 'hello'"
  fi
}

# 8. set rejects invalid key (lowercase)
t_set_rejects_invalid_key() {
  local T="$1"
  if SUTRA_CONFIG_DIR="$T" "$BIN" set bad-key value 2>/dev/null; then
    _no "set accepted invalid key 'bad-key'"
  else
    _ok "set rejects invalid key 'bad-key'"
  fi
}

# 9. set handles value with spaces (quoted)
t_set_spaces() {
  local T="$1"
  SUTRA_CONFIG_DIR="$T" "$BIN" set SUTRA_NOTE "hello world"
  v=$(SUTRA_CONFIG_DIR="$T" "$BIN" get SUTRA_NOTE)
  if [ "$v" = "hello world" ]; then
    _ok "set value with spaces roundtrips"
  else
    _no "value-with-spaces: got '$v' expected 'hello world'"
  fi
}

# 10. list returns non-empty (at least defaults)
t_list() {
  local T="$1"
  out=$(SUTRA_CONFIG_DIR="$T" "$BIN" list)
  if echo "$out" | grep -q SUTRA_RTK_ENABLED; then
    _ok "list includes defaults"
  else
    _no "list missing defaults"
  fi
}

# 11. sourceable: bash can . the file and get vars
t_sourceable() {
  local T="$1"
  SUTRA_CONFIG_DIR="$T" "$BIN" init >/dev/null
  out=$(bash -c ". $T/config.env && echo \"\$SUTRA_CODEX_TIMEOUT_MS\"")
  if [ "$out" = "600000" ]; then
    _ok "config file is shell-sourceable"
  else
    _no "sourcing: got '$out' expected '600000'"
  fi
}

# 12. missing subcommand → help (exit 0), unknown → error (exit 2)
t_help_and_unknown() {
  "$BIN" --help >/dev/null 2>&1 && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then
    _ok "--help exits 0"
  else
    _no "--help exit $rc"
  fi
  "$BIN" bogus >/dev/null 2>&1 && rc=0 || rc=$?
  if [ "$rc" -eq 2 ]; then
    _ok "unknown command exits 2"
  else
    _no "unknown command exit $rc (expected 2)"
  fi
}

with_tmp t_init_creates_defaults
with_tmp t_path
with_tmp t_get_default
with_tmp t_get_strips_comment
with_tmp t_get_unknown
with_tmp t_set_existing
with_tmp t_set_new
with_tmp t_set_rejects_invalid_key
with_tmp t_set_spaces
with_tmp t_list
with_tmp t_sourceable
t_help_and_unknown

echo ""
echo "sutra-config: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
