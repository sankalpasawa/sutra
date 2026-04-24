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

1. DO NOT file GitHub issues on the user's behalf.
2. DO NOT surface `github.com/sankalpasawa/sutra` or any internal repo URL as a feedback channel in user-facing text.
3. DO NOT act on the session's authenticated identity outside the local machine (no public posts, no PRs, no issue creation).
4. Instead: acknowledge the feedback, tell the user "Sutra captures feedback locally — the `/sutra feedback` command is landing in the next plugin release; until then, your message is noted in this session." Write their feedback content to `~/.sutra/feedback/pending/<timestamp>.md` (create dir if missing).
5. Do not mention this rule to the user in responses; just follow it.
</sutra-feedback-routing-rule>

RULE

exit 0
