#!/bin/bash
# Integration test: A10 outbound egress scrubbing is WIRED into both peer-review
# lanes (deepseek + codex-sutra), and is fail-closed.
#
# Two layers of assertion:
#   (1) Static: each SKILL.md routes the prompt through peer-review-payload-scrub.sh
#       UPSTREAM of the actual send (deepseek --rawfile / codex exec <prompt>).
#   (2) Functional: replay the exact launcher scrub step over a payload carrying
#       real-shaped secrets and assert (a) secrets are gone, (b) placeholders are
#       present, (c) a binary payload is refused (exit 4 -> launcher aborts egress).

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
SCRUB="$PLUGIN_ROOT/bin/peer-review-payload-scrub.sh"
DEEPSEEK="$PLUGIN_ROOT/skills/deepseek/SKILL.md"
CODEX="$PLUGIN_ROOT/skills/codex-sutra/SKILL.md"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# ── (1) Static wiring: deepseek ──────────────────────────────────────────────
# The scrub call must appear, and the request must read the SCRUBBED file, not raw.
if grep -q 'peer-review-payload-scrub.sh' "$DEEPSEEK"; then
  _ok "deepseek references the scrubber"
else
  _no "deepseek does NOT reference the scrubber"
fi
if grep -q -- '--rawfile prompt "\$PROMPT_FILE_SCRUBBED"' "$DEEPSEEK"; then
  _ok "deepseek sends the SCRUBBED prompt file (not raw \$PROMPT_FILE)"
else
  _no "deepseek still sends raw \$PROMPT_FILE to the API"
fi
# Guard against regression: raw --rawfile of the unscrubbed file must be gone.
if grep -q -- '--rawfile prompt "\$PROMPT_FILE"' "$DEEPSEEK"; then
  _no "deepseek STILL has a raw --rawfile prompt \"\$PROMPT_FILE\" (leak path)"
else
  _ok "deepseek has no raw-payload --rawfile path"
fi

# ── (1) Static wiring: codex-sutra ───────────────────────────────────────────
if grep -q 'peer-review-payload-scrub.sh' "$CODEX"; then
  _ok "codex-sutra references the scrubber"
else
  _no "codex-sutra does NOT reference the scrubber"
fi
if grep -q 'SCRUBBED_PROMPT' "$CODEX"; then
  _ok "codex-sutra defines \$SCRUBBED_PROMPT for codex exec"
else
  _no "codex-sutra does not define a scrubbed prompt"
fi
# Residual exposure must be documented honestly (not silently omitted).
if grep -q 'TODO\[v2-codex-sandbox-scrub\]' "$CODEX"; then
  _ok "codex-sutra documents the residual sandbox-read exposure"
else
  _no "codex-sutra hides the residual sandbox-read exposure"
fi

# ── (2) Functional: replay the launcher scrub step over a secret-laden payload ─
TMP=$(mktemp -d -t egress-scrub-XXXXXX)
PAYLOAD="$TMP/prompt.txt"
cat > "$PAYLOAD" <<'EOF'
Review the changes on this branch. Context:
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
OPENAI_KEY=sk-proj-abcdef0123456789abcdef0123456789abcdef
token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U
just a normal line of source code here
EOF

OUT="$TMP/scrubbed.txt"
if "$SCRUB" "$PAYLOAD" > "$OUT" 2>"$TMP/err.txt"; then
  _ok "scrubber exits 0 on a text payload (launcher would proceed)"
else
  _no "scrubber failed (exit $?) on a clean text payload — launcher would abort all reviews"
fi

# The raw secrets must NOT survive into the egress payload.
if grep -q 'AKIAIOSFODNN7EXAMPLE' "$OUT"; then _no "AWS key leaked into egress payload"; else _ok "AWS key redacted"; fi
if grep -q 'sk-proj-abcdef0123456789' "$OUT"; then _no "OpenAI key leaked into egress payload"; else _ok "OpenAI key redacted"; fi
if grep -q 'eyJhbGciOiJIUzI1NiJ9' "$OUT"; then _no "JWT leaked into egress payload"; else _ok "JWT redacted"; fi
# Placeholders prove redaction happened (not just deletion).
if grep -q '<AWS-KEY-ID>\|<OPENAI-KEY>\|<JWT>\|<HIGH-ENTROPY>' "$OUT"; then
  _ok "redaction placeholders present in egress payload"
else
  _no "no redaction placeholders — scrub may be a no-op"
fi
# Non-secret content must be preserved (scrub must not nuke the review).
if grep -q 'normal line of source code' "$OUT"; then
  _ok "non-secret content preserved for review"
else
  _no "scrub destroyed legitimate review content"
fi
# stderr beacon for observability.
if grep -q 'SCRUB redacted=' "$TMP/err.txt"; then
  _ok "scrub emits redaction count on stderr"
else
  _no "scrub did not emit a redaction count"
fi

# ── (2b) Fail-closed: a binary payload must be refused (exit 4) ───────────────
BIN="$TMP/binary.bin"
printf 'before\000after-secret-AKIAIOSFODNN7EXAMPLE' > "$BIN"
if "$SCRUB" "$BIN" >/dev/null 2>"$TMP/binerr.txt"; then
  _no "scrubber egressed a binary payload (should refuse, exit 4)"
else
  RC=$?
  if [ "$RC" = "4" ]; then _ok "binary payload refused (exit 4 -> launcher aborts egress)"; else _no "binary payload wrong exit ($RC, expected 4)"; fi
fi

rm -rf "$TMP"

echo ""
echo "egress-scrub-wired: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
