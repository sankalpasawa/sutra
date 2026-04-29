#!/bin/bash
# Sutra Connectors — /sutra connect <name> entrypoint (v0)
#
# Per LLD §3 + foundational spec §7 scenario 1: registers OAuth on first run,
# prints connector summary, hands token to local store. v0 is placeholder —
# no real OAuth handshake; founder pastes a token.
#
# State boundary (codex 2026-04-30 build-plan verdict):
#   - Tokens are USER-GLOBAL (~/.sutra-connectors/oauth/<name>.token)
#   - Tests must set SUTRA_CONNECTORS_DRY_RUN=1 — no real user-global writes
#   - Production calls (real /sutra connect slack) write the file
#
# Usage:
#   connect.sh <connector-name>
#   SUTRA_CONNECTORS_DRY_RUN=1 connect.sh <connector-name>   # tests

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONNECTORS_ROOT="$(dirname "$SCRIPT_DIR")"
MANIFESTS_DIR="$CONNECTORS_ROOT/manifests"
OAUTH_DIR="${HOME}/.sutra-connectors/oauth"

usage() {
  echo "Usage: connect.sh <connector-name>" >&2
  echo "Example: connect.sh slack" >&2
  exit 2
}

NAME="${1:-}"
if [ -z "$NAME" ]; then
  usage
fi

# Reject path-y args; connector names are lowercase tokens.
case "$NAME" in
  */*|.*|*..*)
    echo "connect.sh: invalid connector name '$NAME'" >&2
    exit 2
    ;;
esac

MANIFEST="$MANIFESTS_DIR/$NAME.yaml"
if [ ! -f "$MANIFEST" ]; then
  echo "connect.sh: manifest not found at $MANIFEST" >&2
  echo "  Available connectors:" >&2
  if [ -d "$MANIFESTS_DIR" ]; then
    for m in "$MANIFESTS_DIR"/*.yaml; do
      [ -f "$m" ] || continue
      echo "    - $(basename "$m" .yaml)" >&2
    done
  fi
  exit 1
fi

# --- Manifest summary (best-effort YAML peek; no yq dependency) -------------
DESCRIPTION="$(grep -E '^description:' "$MANIFEST" | head -n1 | sed 's/^description:[[:space:]]*//; s/^"//; s/"$//')"
CAP_COUNT="$(grep -cE '^[[:space:]]*-[[:space:]]*id:' "$MANIFEST" || true)"
TIER_LINE="$(grep -E '^[[:space:]]*(T1|T2|T3|T4):' "$MANIFEST" | wc -l | tr -d ' ')"

echo "── Sutra connector: $NAME ──────────────────────────────"
echo "  manifest:     $MANIFEST"
echo "  description:  ${DESCRIPTION:-<none>}"
echo "  capabilities: ${CAP_COUNT:-0}"
echo "  tier access:  ${TIER_LINE:-0} tier rule(s)"
echo "────────────────────────────────────────────────────────"

TOKEN_FILE="$OAUTH_DIR/$NAME.token"

if [ "${SUTRA_CONNECTORS_DRY_RUN:-0}" = "1" ]; then
  echo "[dry-run] would check $TOKEN_FILE for existing OAuth state"
  echo "[dry-run] would prompt founder for OAuth token if absent"
  echo "[dry-run] would write token to $TOKEN_FILE (chmod 600)"
  exit 0
fi

if [ -f "$TOKEN_FILE" ]; then
  echo "$NAME already connected (token at $TOKEN_FILE)"
  echo "  remove and re-run to re-register: rm $TOKEN_FILE"
  exit 0
fi

echo
echo "To connect $NAME, register an OAuth app at:"
echo "  <provider OAuth registration URL — see manifest>"
echo
printf "Then paste the token: "
read -r TOKEN

if [ -z "${TOKEN:-}" ]; then
  echo "connect.sh: empty token — aborting" >&2
  exit 1
fi

mkdir -p "$OAUTH_DIR"
chmod 700 "$OAUTH_DIR" 2>/dev/null || true
umask 077
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

echo "✅ $NAME connected — token stored at $TOKEN_FILE"
echo "   Sutra L1 policy gate now governs all $NAME calls."
exit 0
