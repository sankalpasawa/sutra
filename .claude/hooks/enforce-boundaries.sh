#!/bin/bash
# Sutra Session Isolation — Level 2 Hook (v2)
# ARCHITECTURE: Enforces submodule boundaries based on ACTIVE_ROLE.
#
# Roles:
#   "asawa"          — CEO of Asawa Inc. Full access to everything.
#   "sutra"          — CEO of Sutra. Can access sutra/ and feedback-from-sutra/ dirs.
#   "company-{name}" — CEO of {name}. Can only access {name}/ submodule.
#
# Environment:
#   ACTIVE_ROLE       — set by /asawa, /sutra, /company slash commands
#   TOOL_INPUT_file_path — file path being accessed (set by Claude Code hooks)
#
# Exit codes:
#   0 = allowed
#   2 = blocked (non-zero blocks the tool call)

ACTIVE_ROLE="${ACTIVE_ROLE:-asawa}"
FILE_PATH="${TOOL_INPUT_file_path:-}"

# No file path = nothing to enforce
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Resolve repo root
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"

# Make path relative to repo root for matching
REL_PATH="${FILE_PATH#$REPO_ROOT/}"

# ─── Role: asawa — full access ───────────────────────────────────────────────
if [ "$ACTIVE_ROLE" = "asawa" ]; then
  # Check god mode for cross-company edits from holding
  GOD_MODE_FILE="$REPO_ROOT/.enforcement/god-mode.active"
  if [ -f "$GOD_MODE_FILE" ]; then
    exit 0
  fi
  exit 0
fi

# ─── Submodule boundary check ────────────────────────────────────────────────
# Detect if the target file lives inside a git submodule.
# Company sessions should NOT be able to edit files in other submodules
# (e.g., dayflow session editing ../sutra/ via relative path traversal).
if [ -f "$REPO_ROOT/.gitmodules" ]; then
  while IFS= read -r submodule_path; do
    case "$REL_PATH" in
      ${submodule_path}/*)
        # File is inside a submodule. Check if it matches the active company.
        if [[ "$ACTIVE_ROLE" == company-* ]]; then
          COMPANY_NAME="${ACTIVE_ROLE#company-}"
          if [ "$submodule_path" != "$COMPANY_NAME" ]; then
            echo "BLOCKED: Cannot edit files in submodule '$submodule_path' from role '$ACTIVE_ROLE'"
            echo "This file belongs to a different company/module. Use god mode from holding to override."
            exit 2
          fi
        elif [ "$ACTIVE_ROLE" = "sutra" ]; then
          if [ "$submodule_path" != "sutra" ]; then
            echo "BLOCKED: Role 'sutra' cannot access submodule '$submodule_path'"
            exit 2
          fi
        fi
        ;;
    esac
  done < <(grep 'path = ' "$REPO_ROOT/.gitmodules" 2>/dev/null | sed 's/.*path = //')
fi

# ─── Role: sutra — can access sutra/ and */feedback-from-sutra/ ─────────────
if [ "$ACTIVE_ROLE" = "sutra" ]; then
  case "$REL_PATH" in
    sutra/*|*/feedback-from-sutra/*)
      exit 0
      ;;
    *)
      echo "BLOCKED: Role 'sutra' cannot access $REL_PATH"
      echo "Sutra can only access sutra/ and */feedback-from-sutra/ directories."
      exit 2
      ;;
  esac
fi

# ─── Role: company-{name} — can only access {name}/ ─────────────────────────
if [[ "$ACTIVE_ROLE" == company-* ]]; then
  COMPANY_NAME="${ACTIVE_ROLE#company-}"
  case "$REL_PATH" in
    ${COMPANY_NAME}/*)
      exit 0
      ;;
    *)
      echo "BLOCKED: Role '$ACTIVE_ROLE' cannot access $REL_PATH"
      echo "CEO of $COMPANY_NAME can only access $COMPANY_NAME/ directory."
      exit 2
      ;;
  esac
fi

# Unknown role — block by default
echo "BLOCKED: Unknown role '$ACTIVE_ROLE'"
exit 2
