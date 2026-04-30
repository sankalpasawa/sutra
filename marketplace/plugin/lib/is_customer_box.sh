#!/usr/bin/env bash
# is_customer_box.sh — detect whether the current $CLAUDE_PROJECT_DIR is a
# customer machine (plugin-only) vs an Asawa-internal repo (the Sutra source).
#
# Usage (sourced):
#   . "$CLAUDE_PLUGIN_ROOT/lib/is_customer_box.sh"
#   if is_customer_box; then exit 0; fi  # log-only hooks: silent return
#
# Heuristic: a "customer box" is anything that doesn't have BOTH the Asawa
# governance directory (holding/hooks/) and is NOT the Sutra source repo
# itself (which has marketplace/plugin/.claude-plugin/ at root). The Sutra
# source repo also doesn't have holding/ — it has marketplace/ and os/ at
# root — so we explicitly exclude it from "customer" too (we still want
# log hooks to fire when we're hacking on Sutra itself).
#
# Override:
#   SUTRA_FORCE_CUSTOMER_MODE=1   force customer mode (testing)
#   SUTRA_FORCE_INTERNAL_MODE=1   force internal mode (testing)
#
# Used by: session-start-rotate.sh, estimation-enforcement.sh,
#          estimation-collector.sh, policy-only-sensor.sh,
#          context-budget-check.sh — all log-only hooks that write to
#          holding/ paths absent on customer machines.

is_customer_box() {
  # Test overrides first
  [ -n "${SUTRA_FORCE_CUSTOMER_MODE:-}" ] && return 0
  [ -n "${SUTRA_FORCE_INTERNAL_MODE:-}" ] && return 1

  local repo_root="${CLAUDE_PROJECT_DIR:-$(pwd)}"

  # Asawa internal: holding/hooks/ exists at repo root
  [ -d "$repo_root/holding/hooks" ] && return 1

  # Sutra source repo itself: has marketplace/plugin/.claude-plugin/ at root
  # (sankalpasawa/sutra repo). Useful when devving on Sutra directly.
  [ -d "$repo_root/marketplace/plugin/.claude-plugin" ] && return 1

  # Otherwise: customer box (plugin-only install)
  return 0
}
