#!/bin/bash
# Sutra update check — runs on SessionStart.
# Compares installed version against latest on GitHub; prints update notice if newer.
# Caches last-check timestamp so we don't hit GitHub more than once every 6 hours.
# Silent on success (no network) or when already up-to-date.

set -u
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CURRENT_VERSION_FILE="$PROJECT_ROOT/.claude/sutra-version"
LAST_CHECK_FILE="$PROJECT_ROOT/.claude/sutra-update-last-check"
CHECK_INTERVAL=21600   # 6 hours in seconds

# If version pin absent, Sutra isn't installed here — silent exit.
[ -f "$CURRENT_VERSION_FILE" ] || exit 0

# Rate-limit: skip if we've checked recently.
NOW=$(date +%s)
if [ -f "$LAST_CHECK_FILE" ]; then
  LAST=$(cat "$LAST_CHECK_FILE" 2>/dev/null || echo 0)
  DIFF=$((NOW - LAST))
  if [ "$DIFF" -lt "$CHECK_INTERVAL" ]; then
    exit 0
  fi
fi

# Get current version (first line of sutra-version is the number).
CURRENT=$(head -1 "$CURRENT_VERSION_FILE" | tr -d '[:space:]')
[ -n "$CURRENT" ] || exit 0

# Fetch latest version string from package.json on main.
# 3-second timeout — must not slow session start.
LATEST=$(curl -fsSL --max-time 3 \
  https://raw.githubusercontent.com/sankalpasawa/sutra-os/main/package.json 2>/dev/null \
  | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

# Always update the check timestamp, even if fetch failed.
echo "$NOW" > "$LAST_CHECK_FILE"

# Fetch failed (offline, rate-limited, etc.) — stay silent.
[ -n "$LATEST" ] || exit 0

# Simple string compare (semver-lite). Better than nothing for v0.2.x.
if [ "$CURRENT" != "$LATEST" ]; then
  cat <<EOF

🧭 Sutra update available: v${CURRENT} → v${LATEST}

   To update:  /sutra-update
   Or manually: npx -y github:sankalpasawa/sutra-os init

EOF
fi

exit 0

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# Retirement commit. File being archived in the next commit as part of the
# package -> archive/package-v1.2.1-retired/ directory move (founder directive
# 2026-04-23 "decommission the package"). No metric applies post-archive;
# pre-archive behavior frozen at this commit.
#
# ### 2. Adoption mechanism
# Retired. Consumers migrate to marketplace/plugin/hooks/ equivalent when one
# exists, or surface the gap via BUILD-LAYER L1 staging path (PROTO-021,
# pending sign-off 2026-04-23).
#
# ### 3. Monitoring / escalation
# N/A after archive. Pre-archive: existing dispatcher logs under
# holding/hooks/hook-log.jsonl remained authoritative.
#
# ### 4. Iteration trigger
# Frozen. Revival only via BUILD-LAYER L1 resurrection ceremony: promote to
# marketplace/plugin/hooks/ with owner + acceptance criteria.
#
# ### 5. DRI
# Sutra Forge (authoring team, historical). No active DRI post-archive.
#
# ### 6. Decommission criteria
# DECOMMISSIONED 2026-04-23. Archived to archive/package-v1.2.1-retired/ in
# the commit immediately following this one.
# ================================================================================
