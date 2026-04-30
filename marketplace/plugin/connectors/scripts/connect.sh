#!/usr/bin/env bash
# Sutra Connectors — `sutra connect <name>` entrypoint.
# Direct-OAuth path (no Composio dependency). Per-toolkit flow handles the
# credential shape that toolkit needs.
#
# Storage (Wave 5 / M1.10):
#   ~/.sutra-connectors/oauth/<toolkit>.age   (encrypted via age, primary)
#   ~/.sutra-connectors/oauth/<toolkit>.json  (plaintext shadow, migration window)
#   Both written via scripts/save-credential.mjs → CredentialLoader.save(),
#   which uses sutra_safe_write semantics (atomic rename, EXCL+NOFOLLOW, chmod 600).
#
# Bundle shapes:
#   Slack: { "type": "slack-bot", "token": "xoxb-...", "obtained_at": <unix-ms> }
#   Gmail: { "type": "gmail-oauth", "clientId": "...", "clientSecret": "...",
#             "accessToken": "...", "refreshToken": "...", "expiresAt": <unix-ms>,
#             "obtained_at": <unix-ms> }
#
# Bootstrap: requires an age keypair at ~/.sutra-connectors/keys/. If missing,
# script prints install instructions and bails before collecting any token.
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
KEY_DIR="${HOME}/.sutra-connectors/keys"
IDENTITY_FILE="${KEY_DIR}/sutra-identity.key"
RECIPIENT_FILE="${KEY_DIR}/sutra-recipient.txt"
CRED_FILE="${CRED_DIR}/${CONNECTOR}.json"
CRED_AGE_FILE="${CRED_DIR}/${CONNECTOR}.age"
SAVE_CREDENTIAL_JS="${SCRIPT_DIR}/save-credential.mjs"
DRY_RUN="${SUTRA_CONNECTORS_DRY_RUN:-0}"

# Already-connected fast exit (Wave 5: check both .age and .json so users who
# completed a Wave 5 save aren't told they're unconnected).
if { [ -f "$CRED_AGE_FILE" ] || [ -f "$CRED_FILE" ]; } && [ "$DRY_RUN" != "1" ]; then
  if [ -f "$CRED_AGE_FILE" ]; then
    echo "$CONNECTOR is already connected (encrypted: $CRED_AGE_FILE)"
  else
    echo "$CONNECTOR is already connected (cred file: $CRED_FILE)"
  fi
  echo "  To re-register, delete the file(s) and re-run."
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would check $CRED_AGE_FILE / $CRED_FILE for existing OAuth state"
  echo "[dry-run] would prompt founder for credential payload"
  echo "[dry-run] would write encrypted cred via save-credential.mjs (.age + .json shadow, chmod 600)"
  exit 0
fi

# ── Wave 5 (M1.10) — age keypair bootstrap check ─────────────────────────────
# CredentialLoader.save() encrypts to .age via SecretStoreAge, which requires
# an age identity + recipient pair. If missing, print install instructions and
# bail before we collect a token (so we don't lose the founder's input).
if [ ! -f "$IDENTITY_FILE" ] || [ ! -f "$RECIPIENT_FILE" ]; then
  cat <<EOF >&2
First-run setup required: age keypair missing.

Sutra Connectors stores credentials encrypted at rest under
$KEY_DIR via the 'age' tool. Generate a keypair once:

  mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR"
  age-keygen -o "$IDENTITY_FILE"
  grep '^# public key:' "$IDENTITY_FILE" | sed 's/^# public key: //' > "$RECIPIENT_FILE"
  chmod 600 "$IDENTITY_FILE"
  chmod 644 "$RECIPIENT_FILE"

If 'age' isn't installed:
  brew install age          # macOS
  apt install age           # Debian/Ubuntu

Then re-run: sutra connect $CONNECTOR
EOF
  exit 1
fi

# Sanity check: save-credential.mjs bridge must be present.
if [ ! -f "$SAVE_CREDENTIAL_JS" ]; then
  echo "connect.sh: missing $SAVE_CREDENTIAL_JS — plugin install corrupt?" >&2
  exit 1
fi

# Helper: write a bundle JSON via mktemp, hand off to save-credential.mjs,
# always rm the temp on the way out.
save_via_loader() {
  local _bundle_json="$1"
  local _tmp
  _tmp="$(mktemp -t sutra-bundle.XXXXXX)" || {
    echo "connect.sh: mktemp failed" >&2
    return 1
  }
  printf '%s' "$_bundle_json" > "$_tmp" || {
    rm -f "$_tmp"
    echo "connect.sh: failed to write temp bundle" >&2
    return 1
  }
  if ! node "$SAVE_CREDENTIAL_JS" "$CONNECTOR" "$_tmp"; then
    rm -f "$_tmp"
    echo "connect.sh: failed to save credential via loader" >&2
    return 1
  fi
  rm -f "$_tmp"
  return 0
}

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
    # Wave 5 (M1.10): write through CredentialLoader.save() via the bridge.
    # Bundle shape matches CredentialLoader's SlackBotBundle (type+token+obtained_at).
    NOW_MS=$(($(date +%s) * 1000))
    BUNDLE_JSON=$(printf '{"type":"slack-bot","token":"%s","obtained_at":%s}' \
      "$TOKEN" "$NOW_MS")
    if ! save_via_loader "$BUNDLE_JSON"; then
      exit 1
    fi
    echo "✔ saved Slack credential (encrypted: $CRED_AGE_FILE; shadow: $CRED_FILE)"
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
    # Wave 5 (M1.10): write through CredentialLoader.save() via the bridge.
    # Bundle shape matches CredentialLoader's GmailOAuthBundle.
    NOW_MS=$(($(date +%s) * 1000))
    BUNDLE_JSON=$(printf '{"type":"gmail-oauth","clientId":"%s","clientSecret":"%s","accessToken":"%s","refreshToken":"%s","expiresAt":%s,"obtained_at":%s}' \
      "$CLIENT_ID" "$CLIENT_SECRET" "$ACCESS_TOKEN" "$REFRESH_TOKEN" "$EXPIRES_AT" "$NOW_MS")
    if ! save_via_loader "$BUNDLE_JSON"; then
      exit 1
    fi
    echo "✔ saved Gmail credential (encrypted: $CRED_AGE_FILE; shadow: $CRED_FILE)"
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
    # Wave 5 (M1.10): write through CredentialLoader.save() via the bridge.
    # Generic opaque-token shape — type tag matches the legacy "<connector>-token"
    # convention. CredentialLoader currently types the discriminator as a
    # closed union; this passes through `bundle.type` as a string, so the
    # loader's runtime check (typeof bundle.type === 'string') accepts it.
    # Note: no first-class TS narrowing yet for generic connectors — that's
    # tracked separately for the generic-backend M2 polish.
    NOW_MS=$(($(date +%s) * 1000))
    BUNDLE_JSON=$(printf '{"type":"%s-token","token":"%s","obtained_at":%s}' \
      "$CONNECTOR" "$TOKEN" "$NOW_MS")
    if ! save_via_loader "$BUNDLE_JSON"; then
      exit 1
    fi
    echo "✔ saved $CONNECTOR credential (encrypted: $CRED_AGE_FILE; shadow: $CRED_FILE)"
    echo "  Note: no backend exists yet for $CONNECTOR."
    ;;
esac
