#!/usr/bin/env bash
# Sutra Connectors — `sutra connect <name>` entrypoint.
# Direct-OAuth path (no Composio dependency). Per-toolkit flow handles the
# credential shape that toolkit needs.
#
# Storage: ~/.sutra-connectors/oauth/<toolkit>.json (chmod 600)
#   Slack: { "type": "slack-bot", "token": "xoxb-..." }
#   Gmail: { "type": "gmail-oauth", "clientId": "...", "clientSecret": "...",
#             "accessToken": "...", "refreshToken": "...", "expiresAt": <unix-ms> }
#
# Dry-run mode (CI / tests): SUTRA_CONNECTORS_DRY_RUN=1 — no fs writes, no
# network. Prints what it would do. The integration tests rely on this.

set -u

usage() {
  cat <<EOF
Usage: connect.sh <connector-name>

Connectors with first-class flows in this script:
  slack    — bot token (xoxb-...) one-shot
  gmail    — OAuth 2.0 (Google Cloud Console one-time setup, then paste creds)

Other connectors with manifests in connectors/manifests/ fall back to a
generic "paste opaque token" flow.

Examples:
  connect.sh slack
  connect.sh gmail
  SUTRA_CONNECTORS_DRY_RUN=1 connect.sh slack    # smoke without writing
EOF
}

if [ $# -lt 1 ]; then
  usage >&2
  exit 2
fi

CONNECTOR="$1"

# Reject path-traversal attempts (codex iter-9 hardening)
case "$CONNECTOR" in
  */*|.*|*..*|"")
    echo "connect.sh: invalid connector name: $CONNECTOR" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONNECTORS_ROOT="$(dirname "$SCRIPT_DIR")"
MANIFEST_PATH="$CONNECTORS_ROOT/manifests/${CONNECTOR}.yaml"

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "connect.sh: manifest not found at $MANIFEST_PATH" >&2
  echo "  Available connectors:" >&2
  if [ -d "$CONNECTORS_ROOT/manifests" ]; then
    for m in "$CONNECTORS_ROOT/manifests"/*.yaml; do
      [ -f "$m" ] && echo "    - $(basename "$m" .yaml)" >&2
    done
  fi
  exit 1
fi

# ── Connector summary ─────────────────────────────────────────────────────────
echo "── Sutra connector: $CONNECTOR ──────────────────────────────"
echo "  manifest:     $MANIFEST_PATH"
DESCR="$(grep '^description:' "$MANIFEST_PATH" | head -1 | cut -d':' -f2- | sed 's/^ //')"
[ -n "$DESCR" ] && echo "  description:  $DESCR"
echo "  capabilities: $(grep -c '^  - id:' "$MANIFEST_PATH")"
echo "  tier access:  $(grep -E '^  T[1-4]:' "$MANIFEST_PATH" | wc -l | tr -d ' ') tier rule(s)"
echo "────────────────────────────────────────────────────────────"

CRED_DIR="${HOME}/.sutra-connectors/oauth"
CRED_FILE="${CRED_DIR}/${CONNECTOR}.json"
DRY_RUN="${SUTRA_CONNECTORS_DRY_RUN:-0}"

if [ -f "$CRED_FILE" ] && [ "$DRY_RUN" != "1" ]; then
  echo "$CONNECTOR is already connected (cred file: $CRED_FILE)"
  echo "  To re-register, delete the file and re-run."
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would check $CRED_FILE for existing OAuth state"
  echo "[dry-run] would prompt founder for credential payload"
  echo "[dry-run] would write JSON cred to $CRED_FILE (chmod 600)"
  exit 0
fi

# ── Per-connector credential collection ──────────────────────────────────────
case "$CONNECTOR" in
  slack)
    cat <<'SLACK_HELP'

To connect Slack, you need a Bot User OAuth Token (xoxb-...).

  1. Go to https://api.slack.com/apps → "Create New App" → "From scratch"
  2. Pick your workspace (Asawa, DayFlow, etc.)
  3. OAuth & Permissions → add Bot Token Scopes:
       channels:history    (read public channel messages)
       channels:read       (list channels)
       chat:write          (post messages)
       users:read          (look up users)
     Add more scopes only if your tier needs them per slack.yaml.
  4. Click "Install to Workspace" → authorize → copy the
     "Bot User OAuth Token" (starts with xoxb-).

SLACK_HELP

    printf "Paste Slack Bot User OAuth Token (xoxb-...): "
    read -r TOKEN
    if [ -z "$TOKEN" ]; then
      echo "connect.sh: empty token; aborting." >&2
      exit 2
    fi

    case "$TOKEN" in
      xoxb-*) ;;
      *)
        printf "Token does not start with 'xoxb-'. Save anyway? [y/N] "
        read -r CONFIRM
        case "$CONFIRM" in y|Y|yes) ;; *) echo "aborted."; exit 2 ;; esac
        ;;
    esac

    umask 077
    mkdir -p "$CRED_DIR"
    chmod 700 "$CRED_DIR"
    cat > "$CRED_FILE" <<JSON
{
  "type": "slack-bot",
  "token": "$TOKEN",
  "savedAt": $(date +%s)
}
JSON
    chmod 600 "$CRED_FILE"
    echo "✔ saved Slack credential to $CRED_FILE"
    echo "  Verify with: sutra connect-test slack"
    ;;

  gmail)
    cat <<'GMAIL_HELP'

To connect Gmail, you need an OAuth 2.0 client + a per-account
access/refresh token pair.

ONE-TIME SETUP (Google Cloud Console):
  1. https://console.cloud.google.com → create / select a project
  2. APIs & Services → Library → enable "Gmail API"
  3. APIs & Services → Credentials → "Create Credentials" → "OAuth client ID"
       Application type: Desktop app   (simplest for personal use)
       Name: anything (e.g. "Sutra Connector — <your-account>")
  4. Download the credentials JSON. It contains client_id + client_secret.
  5. OAuth consent screen → add your Gmail address as a Test user
       (so the unverified app can access your own Gmail).

GET A TOKEN PAIR — easiest route is Google's OAuth playground:
  6. https://developers.google.com/oauthplayground/
       Gear (top-right) → "Use your own OAuth credentials" → paste
       client_id + client_secret from step 4.
       Force-prompt-consent: leave on. Access type: Offline.
  7. Step 1 — pick scopes:
       https://www.googleapis.com/auth/gmail.readonly
       https://www.googleapis.com/auth/gmail.send       (only if T1/T2 send)
       https://www.googleapis.com/auth/gmail.modify     (only if T1 admin)
  8. Authorize APIs → sign in with your Gmail account → allow.
  9. Step 2 — exchange auth code for tokens. Copy access_token,
     refresh_token, and expires_in.

This script will ask for those 5 values. Defer this whole step if you
don't have a Google Cloud project yet — Sutra L1 is unaffected, you just
can't make real Gmail calls until creds are saved.

GMAIL_HELP

    printf "Have all 5 values ready? [y/N] "
    read -r READY
    case "$READY" in y|Y|yes) ;; *) echo "aborted."; exit 0 ;; esac

    printf "client_id: "; read -r CLIENT_ID
    printf "client_secret: "; read -rs CLIENT_SECRET; echo
    printf "access_token: "; read -rs ACCESS_TOKEN; echo
    printf "refresh_token: "; read -rs REFRESH_TOKEN; echo
    printf "expires_in (seconds, e.g. 3600): "; read -r EXPIRES_IN

    if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$ACCESS_TOKEN" ] || [ -z "$REFRESH_TOKEN" ] || [ -z "$EXPIRES_IN" ]; then
      echo "connect.sh: all fields required; aborting." >&2
      exit 2
    fi

    EXPIRES_AT=$(( ($(date +%s) + EXPIRES_IN) * 1000 ))

    umask 077
    mkdir -p "$CRED_DIR"
    chmod 700 "$CRED_DIR"
    cat > "$CRED_FILE" <<JSON
{
  "type": "gmail-oauth",
  "clientId": "$CLIENT_ID",
  "clientSecret": "$CLIENT_SECRET",
  "accessToken": "$ACCESS_TOKEN",
  "refreshToken": "$REFRESH_TOKEN",
  "expiresAt": $EXPIRES_AT,
  "savedAt": $(date +%s)
}
JSON
    chmod 600 "$CRED_FILE"
    echo "✔ saved Gmail credential to $CRED_FILE"
    echo "  Verify with: sutra connect-test gmail"
    ;;

  *)
    cat <<GENERIC_HELP

No first-class flow for '$CONNECTOR'. Falling back to generic
opaque-token mode. The token is saved as plain JSON; you'll need to
write a backend at lib/backends/${CONNECTOR}-direct.ts before this
credential can be used by ConnectorRouter.

GENERIC_HELP
    printf "Paste opaque token: "
    read -r TOKEN
    if [ -z "$TOKEN" ]; then
      echo "connect.sh: empty token; aborting." >&2
      exit 2
    fi

    umask 077
    mkdir -p "$CRED_DIR"
    chmod 700 "$CRED_DIR"
    cat > "$CRED_FILE" <<JSON
{
  "type": "$CONNECTOR-token",
  "token": "$TOKEN",
  "savedAt": $(date +%s)
}
JSON
    chmod 600 "$CRED_FILE"
    echo "✔ saved $CONNECTOR credential to $CRED_FILE"
    echo "  Note: no backend exists yet for $CONNECTOR."
    ;;
esac
