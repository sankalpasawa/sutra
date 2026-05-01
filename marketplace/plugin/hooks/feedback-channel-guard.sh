#!/usr/bin/env bash
# feedback-channel-guard.sh — PreToolUse:Bash hook
#
# Closes the governance bypass that allowed an LLM to fall back to direct
# `gh issue create --repo sankalpasawa/sutra` when the sanctioned binary
# (`sutra feedback --public`) failed. Documented incident: 2026-04-27 issue
# #15 was filed via this exact bypass after the binary's --label flag failed
# on a non-existent repo label.
#
# THREAT MODEL — IMPORTANT
#   Advisory guard against ACCIDENTAL fallback by an LLM agent that just
#   "wants to help finish" after a binary failure. NOT a security boundary
#   against adversarial obfuscation (variable indirection like `GH=gh; $GH`,
#   command substitution `$(echo gh)`, base64+eval, hub, curl, etc.). The
#   textual rule (feedback-routing-rule.sh) and the binary fix carry that
#   load. If you need a hard boundary, build a real shell-parser-based
#   gate; raw-text matching is not enough.
#
# CONTRACT
#   Input: JSON on stdin with .tool_input.command (Claude Code PreToolUse:Bash
#          hook payload).
#   Block: exit 2 + stderr explanation when the command attempts to create
#          new public artifacts (issues / PRs / issue comments / mutating
#          gh api calls) on any sankalpasawa/sutra* repository — including
#          when the user is inside a sankalpasawa/sutra* checkout and the
#          gh call infers the repo from `git remote`.
#   Allow: read/list/view/close/delete; non-sutra-repo gh calls; the
#          sanctioned binary itself is not caught here because it runs in
#          a child process tree, not through this PreToolUse:Bash gate.
#
# DESIGN
#   The rule is asymmetric on purpose: closing/commenting on cleanup is
#   fine, but creating a public artifact (or reposting feedback as a
#   comment) is exactly the leak the routing rule is meant to prevent.
#
# KILL-SWITCHES (any one — for legitimate plugin maintenance work):
#   SUTRA_FEEDBACK_GUARD_DISABLED=1 (env)
#   ~/.sutra-feedback-guard-disabled (file)
#
# EXIT CODES
#   0  no block (command allowed or hook not applicable)
#   2  blocked (Claude Code shows stderr as a blocking error)

set -u

# Kill-switches (memory: Infra default strict — opt-out, not opt-in)
[ -n "${SUTRA_FEEDBACK_GUARD_DISABLED:-}" ] && exit 0
[ -f "$HOME/.sutra-feedback-guard-disabled" ] && exit 0

# Read the PreToolUse payload. If jq is missing, we can't inspect — fall back
# to no-op (this hook is advisory; the binary path remains canonical).
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

PAYLOAD=$(cat)
[ -z "$PAYLOAD" ] && exit 0

CMD=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

CMD_LOWER=$(printf '%s' "$CMD" | tr '[:upper:]' '[:lower:]')

# Quick-exit: no `gh` invocation, no concern.
case "$CMD_LOWER" in
  *gh\ *|*\ gh\ *|*\;gh\ *|*\&\&gh\ *|*\|gh\ *|gh\ *) ;;
  *) exit 0 ;;
esac

# Strip everything from the first quoted value onward — flag bodies cannot
# influence target or action matching. Lifted out of the action-match block
# (was at line 122 in v2.10.x) so the SUTRA_TARGET literal-substring check
# also benefits. v2.11.1 fix for false-positive trigger when body text
# referenced sankalpasawa/sutra URLs (e.g., gh issue create --repo other/repo
# --body '... see https://github.com/sankalpasawa/sutra/issues/N ...' was
# blocked because the body string matched).
CMD_HEAD=$(printf '%s' "$CMD_LOWER" | sed -E "s/[[:space:]]['\"].*$//")

# Determine "Sutra-targeted":
#   Path A: literal `sankalpasawa/sutra` substring in CMD_HEAD (covers
#           --repo flag, OWNER/REPO positional, gh api repos/.../...).
#           CMD_HEAD excludes quoted body content so URLs in --title/--body
#           don't cause false-positive blocks.
#   Path B: command lacks an explicit --repo flag AND we're inside a
#           sankalpasawa/sutra* checkout (gh infers from git remote — this
#           is the most realistic LLM-bypass path codex flagged 2026-04-27).
SUTRA_TARGET=0
case "$CMD_HEAD" in
  *sankalpasawa/sutra*) SUTRA_TARGET=1 ;;
esac

if [ "$SUTRA_TARGET" -eq 0 ]; then
  # Only consult `git remote` if the command doesn't already specify --repo
  # (no need; it would already be path A or pointing somewhere else).
  # v2.8.8 — also recognize the short form `-R` / `-r` which gh treats
  # equivalently to --repo. Without this, `gh issue create -R other/repo`
  # inside a sutra checkout falls through to git-remote inference and gets
  # blocked despite the explicit non-sutra target.
  case "$CMD_LOWER" in
    *--repo*|*\ -r\ *|*\ -r=*) ;;  # explicit repo, but didn't match Sutra → not our target
    *)
      REMOTE_URL=$(git remote get-url origin 2>/dev/null | tr '[:upper:]' '[:lower:]')
      case "$REMOTE_URL" in
        *sankalpasawa/sutra*) SUTRA_TARGET=1 ;;
      esac
      ;;
  esac
fi

[ "$SUTRA_TARGET" -eq 0 ] && exit 0

# Action match: block writes only.
#   gh issue create|comment
#   gh pr create|comment|review
#   gh api ... (issues|pulls|comments) with mutating method (-X POST|PUT|PATCH|DELETE
#                                       or --method POST|PUT|PATCH|DELETE)
#
# v2.8.8 (vinit#17 second-encounter, 2026-04-28) — extract the actual gh
# subcommand+action by parsing tokens up to the first quoted flag value.
# Prior implementation grep'd the whole command line, including --comment
# "..." body content, producing false positives when message text mentioned
# "gh issue create" or "gh issue comment" as concepts. Now we look at the
# command structure: gh <noun> <verb> ... and only match on <noun> <verb>.
# v2.11.1 — CMD_HEAD now computed earlier (above SUTRA_TARGET check);
# this section reuses it.
BLOCK=0

# Parse tokens; find 'gh' position; capture next two tokens (noun + verb).
# shellcheck disable=SC2206
TOKENS=( $CMD_HEAD )
GH_NOUN=""
GH_VERB=""
for i in "${!TOKENS[@]}"; do
  if [ "${TOKENS[$i]}" = "gh" ]; then
    GH_NOUN="${TOKENS[$((i+1))]:-}"
    GH_VERB="${TOKENS[$((i+2))]:-}"
    break
  fi
done

case "$GH_NOUN $GH_VERB" in
  "issue create"|"issue comment") BLOCK=1 ;;
  "pr create"|"pr comment"|"pr review") BLOCK=1 ;;
esac

# Mutating gh api calls — this we still scan whole command since gh api
# parameters live unquoted on the line. The pattern is specific enough
# that false-positives in message bodies are extremely unlikely.
if [ "$BLOCK" -eq 0 ] && [ "$GH_NOUN" = "api" ]; then
  if printf '%s' "$CMD_LOWER" | grep -E -q '(issues|pulls|comments)' && \
     printf '%s' "$CMD_LOWER" | grep -E -q -- '(-x|--method)[[:space:]]+["'"'"']?(post|put|patch|delete)'; then
    BLOCK=1
  fi
fi

[ "$BLOCK" -eq 0 ] && exit 0

cat >&2 <<'MSG'
sutra-feedback-channel-guard: BLOCKED

This command would create or modify a public artifact in a Sutra-owned
repository (matched by literal repo string, by `git remote` inside a
sutra checkout, or by mutating `gh api` against issues/pulls).

The Sutra feedback channel is not direct `gh` calls — it is the sanctioned
binary at `sutra feedback --public` (or `/core:feedback --public`), which
scrubs the body and asks for explicit user confirmation.

If the sanctioned binary failed for you, that is an INFRA bug to fix, not
a signal to fall back to direct gh. Capture content locally at
~/.sutra/feedback/pending/<timestamp>.md and report the binary failure.

This guard is advisory against accidental fallback. Adversarial obfuscation
(variable indirection, command substitution, base64+eval, hub, curl) is
not in scope — it is also outside the LLM "help the user finish" path.

Bypass (for legitimate plugin maintenance — code commits, automation, etc.):
  SUTRA_FEEDBACK_GUARD_DISABLED=1 <your command>
  touch ~/.sutra-feedback-guard-disabled

Background: incident 2026-04-27 (sankalpasawa/sutra#15, since closed).
Codex review 2026-04-27: hardened to add repo-context (git remote) detection
and mutating `gh api` detection.
MSG

exit 2
