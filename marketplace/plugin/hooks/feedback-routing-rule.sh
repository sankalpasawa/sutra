#!/usr/bin/env bash
# feedback-routing-rule.sh — UserPromptSubmit hook
#
# Stop-the-bleed for the vinitharmalkar incident (2026-04-24): a T4 plugin user
# asked for feedback and Sutra offered to file a GitHub issue on their behalf,
# surfacing the sankalpasawa/sutra repo URL and leaking the auth identity to a
# public system.
#
# When the user prompt contains a feedback-intent keyword, inject a behavioral
# rule into the session context telling Claude what NOT to do.
#
# Payload: JSON on stdin with .prompt
# Output: on match, emits the rule to stdout (treated as additional-context
#         per Claude Code UserPromptSubmit hook contract); silent otherwise
# Exit: always 0 (advisory — never block the prompt)

set -u

# Kill-switches (per D32 + memory [Infra — default strict])
[ -n "${FEEDBACK_ROUTING_RULE_DISABLED:-}" ] && exit 0
[ -f "$HOME/.feedback-routing-rule-disabled" ] && exit 0

PROMPT=$(jq -r '.prompt // empty' 2>/dev/null)
[ -z "$PROMPT" ] && exit 0

PROMPT_LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Match feedback-intent phrasings. Kept tight to avoid false positives.
# Intent markers: verb + ("feedback"|"bug"|"issue"|"report a problem") proximity.
INTENT_PATTERNS=(
  '(give|send|submit|file|report|leave|provide) +(feedback|a +bug|an +issue)'
  'feedback +(command|channel|mechanism|route)'
  'how +(do +i|can +i|to) +(give|send|submit|file|report|leave) +(feedback|a +bug)'
  'report +(a|this) +(bug|issue|problem)'
  'file +(a|an) +(github +)?(issue|bug)'
  "i'?d +like +to +(give|submit|send) +feedback"
)

MATCHED=0
for pat in "${INTENT_PATTERNS[@]}"; do
  if printf '%s' "$PROMPT_LOWER" | grep -E -q "$pat"; then
    MATCHED=1
    break
  fi
done

[ "$MATCHED" -eq 0 ] && exit 0

# Emit rule to stdout — UserPromptSubmit additional-context contract.
cat <<'RULE'

<sutra-feedback-routing-rule>
The user is requesting a feedback/bug-report channel. Apply these rules:

1. DO NOT file GitHub issues on the user's behalf via direct `gh` CLI calls.
2. DO NOT surface `github.com/sankalpasawa/sutra` or any internal repo URL as a feedback channel in user-facing text.
3. DO NOT act on the session's authenticated identity outside the local machine (no public posts, no PRs, no issue creation, no comments).
4. The ONLY sanctioned public feedback channel is `/core:feedback --public` (or `sutra feedback --public`). If that command fails for ANY reason — missing label, missing gh auth, network error, validation error — the response is: capture content locally at `~/.sutra/feedback/pending/<timestamp>.md` and report the failure to the user. NEVER fall back to direct `gh issue create`, `gh pr create`, or any other GitHub API path. The binary's failure means the public path is unavailable; it does NOT graduate the assistant to a manual workaround.
5. The default channel is local. Tell the user: "Sutra captures feedback locally at `~/.sutra/feedback/pending/`. To publish a scrubbed version as a public GitHub issue, run `/core:feedback --public "<message>"` yourself — Sutra will not invoke it on your behalf."
6. This rule applies during error recovery, partial failure, retries, and "let me just help the user finish" moments. There is no exception.
7. Transparency requirement (per vinit#26): briefly acknowledge that Sutra has guided this routing in your reply. One short sentence is enough — e.g., "(Sutra has routed this through the sanctioned `/core:feedback` channel.)" The user should always know when Sutra-injected guidance is shaping the response. Do not be silent about it.
</sutra-feedback-routing-rule>

RULE

exit 0
