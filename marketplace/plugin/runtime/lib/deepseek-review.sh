#!/usr/bin/env bash
# deepseek-review.sh <prompt-file> <out-file> - the default second review lane
# (adherence row 2). Non-streaming call to DeepSeek's Anthropic-compatible
# endpoint, thinking disabled (the verdict shape is deterministic enough), the
# payload scrubbed by the plugin's egress scrubber first. Key: the canonical
# connector file, then the legacy token file. Exit 0 with a verdict in the
# out-file, or non-zero with the reason on the first line of the out-file.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/deepseek-review.sh
set -u
PROMPT_FILE="${1:-}"; OUT="${2:-}"
[ -f "$PROMPT_FILE" ] && [ -n "$OUT" ] || { echo "usage: deepseek-review.sh <prompt-file> <out-file>" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
TOKEN=""
if [ -n "${DEEPSEEK_TOKEN_FILE:-}" ] && [ -r "$DEEPSEEK_TOKEN_FILE" ]; then
  case "$DEEPSEEK_TOKEN_FILE" in *.json) TOKEN="$(jq -r '.token // .api_key // .key // empty' "$DEEPSEEK_TOKEN_FILE" 2>/dev/null)" ;; *) TOKEN="$(cat "$DEEPSEEK_TOKEN_FILE")" ;; esac
elif [ -r "$HOME/.sutra-connectors/oauth/deepseek.json" ]; then
  TOKEN="$(jq -r '.token // .api_key // .key // empty' "$HOME/.sutra-connectors/oauth/deepseek.json" 2>/dev/null)"
elif [ -r "$HOME/.config/deepseek/auth.token" ]; then
  TOKEN="$(cat "$HOME/.config/deepseek/auth.token")"
fi
[ -n "$TOKEN" ] || { echo "SKIPPED: no DeepSeek key on this box" > "$OUT"; exit 3; }
SCRUB="$ROOT/bin/peer-review-payload-scrub.sh"
SCRUBBED="$(mktemp "${TMPDIR:-/tmp}/dsreview.XXXXXX")"
# Egress is fail-CLOSED: no scrubber, no send.
[ -x "$SCRUB" ] || { echo "SKIPPED: egress scrubber missing at $SCRUB" > "$OUT"; rm -f "$SCRUBBED"; exit 4; }
"$SCRUB" "$PROMPT_FILE" > "$SCRUBBED" 2>/dev/null || { echo "SKIPPED: egress scrub refused the payload" > "$OUT"; rm -f "$SCRUBBED"; exit 4; }
REQF="$(mktemp "${TMPDIR:-/tmp}/dsreq.XXXXXX")"
jq -nc --arg model "${DEEPSEEK_MODEL:-deepseek-v4-pro}" --rawfile p "$SCRUBBED" \
  '{model:$model, max_tokens:8192, thinking:{type:"disabled"}, messages:[{role:"user",content:$p}], stream:false}' > "$REQF"
RESP="$(mktemp "${TMPDIR:-/tmp}/dsresp.XXXXXX")"
# request body from a file (a 400 KB argv string trips Linux MAX_ARG_STRLEN); --fail surfaces HTTP errors
curl -sS --fail --max-time 900 -H "x-api-key: $TOKEN" -H "Content-Type: application/json" -H "anthropic-version: 2023-06-01" \
  -d "@$REQF" https://api.deepseek.com/anthropic/v1/messages > "$RESP" 2>"$RESP.err"
RC=$?
rm -f "$REQF"
{
  echo "# DeepSeek review lane (runtime-run)"
  echo
  echo "model_requested=${DEEPSEEK_MODEL:-deepseek-v4-pro} model_returned=$(jq -r '.model // "absent"' "$RESP" 2>/dev/null) curl_rc=$RC ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  jq -r '.content[]? | select(.type=="text") | .text' "$RESP" 2>/dev/null || cat "$RESP"
} > "$OUT"
rm -f "$SCRUBBED" "$RESP" "$RESP.err"
[ "$RC" -eq 0 ] && grep -q 'VERDICT:' "$OUT"
