#!/bin/bash
# sutra/marketplace/plugin/scripts/feedback.sh
# Sutra feedback channel (PROTO-024).
#   default          — local capture + push to Sutra team's private git
#                      (sankalpasawa/sutra-data clients/<id>/feedback/<ts>.md)
#   --public (v2.1)  — opt-in GitHub issue post via gh CLI (world-visible)
#   --no-fanout      — local-only, skip git push (manual fanout disable)
#
# v2.2.0 PROTO-024 V1: feedback content fans out to Sutra team via existing
#   sutra-data git rail. Scrubbed locally first (lib/privacy-sanitize.sh).
#   Disclosure (PRIVACY.md): for V1, scrubbed feedback is collaborator-visible
#   inside sutra-data — NOT a private team-only channel. V2 will add client-
#   side encryption to close that gap.
#
# Kill-switches (any one):
#   SUTRA_FEEDBACK_FANOUT=0
#   ~/.sutra-feedback-fanout-disabled  (file presence)
#   --no-fanout flag

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || { echo "sutra feedback: privacy lib not found at $LIB" >&2; exit 1; }
source "$LIB"

# v2.2.0 PROTO-024: decoupled from SUTRA_TELEMETRY. Manual feedback works
# even when telemetry is fully off — codex L17 finding closed.
# (SUTRA_TELEMETRY only gates AUTO-CAPTURE signals via privacy_gate.)

PUBLIC=0
NO_FANOUT=0
while [ $# -gt 0 ]; do
  case "${1:-}" in
    --public) PUBLIC=1; shift ;;
    --no-fanout) NO_FANOUT=1; shift ;;
    --) shift; break ;;
    *) break ;;
  esac
done

MSG="$*"
if [ -z "$MSG" ] && [ ! -t 0 ]; then
  MSG=$(cat)
fi

# v2.8.10 — detect zsh/bash $N expansion artifacts in user input.
# Symptom: "$0.14" or "$1,000" gets expanded by the user's shell before
# reaching this script, becoming "/bin/zsh.14" / "/bin/bash.14" / etc.
# This silently corrupts dollar figures in published feedback (we saw it
# in Vinit's #19/#21/#23 bodies). Detect and refuse so the user re-files
# with proper single-quote protection.
if printf '%s' "$MSG" | grep -E -q '/bin/(zsh|bash)\.[0-9]'; then
  cat >&2 <<'ARTEFACT'
-- feedback aborted: detected shell-expansion artifact in your message.

   Patterns like "/bin/zsh.14" or "/bin/bash.14" indicate dollar-figures
   in your text (like "$0.14" or "$1,000") were expanded by the shell
   before reaching this command. The post would be silently corrupted.

   Fix: re-run with SINGLE quotes around the body so the shell preserves
   the dollar signs literally:

     sutra feedback --public 'DeepSeek costs $0.14 per token'

   (Note the SINGLE quotes — double quotes still let the shell expand $N.)
ARTEFACT
  exit 2
fi

if [ -z "$MSG" ]; then
  cat <<'EOF'
Usage: sutra feedback "<your thoughts>"

  Stays on your machine at ~/.sutra/feedback/manual/.
  Granting this also enables local consent for auto-capture signals
  (overrides, corrections, abandonment) to persist on disk — see
  ~/.sutra/PRIVACY.md for what's captured and retention policy.

  Nothing is ever transmitted without your explicit command.

Flags:
  --public   Post as a GitHub issue at sankalpasawa/sutra via `gh` CLI.
             Requires gh installed + authenticated. Scrubbed before posting.
             Asks for 'yes' confirmation (issue is PUBLIC + permanent).
             Falls back to local-only capture if gh missing / not authed /
             user cancels.
EOF
  # v2.8.9 — empty-input is not a failure; printing usage IS the action.
  # Per vinit#16: prior `exit 1` made the slash-command invocation report
  # error in pipelines and broke /core:feedback with no args.
  exit 0
fi

if [ "$PUBLIC" = "1" ]; then
  # v2.1: wire --public to gh CLI with confirmation + scrub.
  if ! command -v gh >/dev/null 2>&1; then
    echo "-- --public requires GitHub CLI (gh). Install: https://cli.github.com/ -- falling back to local capture."
    PUBLIC=0
  else
    if ! gh auth status >/dev/null 2>&1; then
      echo "-- gh CLI installed but not authenticated (gh auth login). Falling back to local capture."
      PUBLIC=0
    fi
  fi
fi

mkdir -p "$SUTRA_HOME/feedback/manual" 2>/dev/null
chmod 0700 "$SUTRA_HOME" "$SUTRA_HOME/feedback" "$SUTRA_HOME/feedback/manual" 2>/dev/null

sutra_grant_consent

SCRUBBED=$(scrub_text "$MSG")

# v2.8.10 — refuse when redactor stripped the body to nothing useful.
# Symptom: bodies dominated by <HOME>/<HIGH-ENTROPY>/<EMAIL>/etc placeholders
# (we saw this in Vinit's #28-#34, #37 — bodies were just paths or hashes
# that the redactor matched whole-input). Without this check, public posts
# would publish unreadable bodies, polluting the inbox.
DESLOTTED=$(printf '%s' "$SCRUBBED" | sed -E 's|<[A-Z][A-Z0-9_-]*>||g')
USEFUL_CHARS=$(printf '%s' "$DESLOTTED" | tr -cd 'a-zA-Z0-9' | wc -c | tr -d ' ')
if [ "${USEFUL_CHARS:-0}" -lt 10 ]; then
  cat >&2 <<USELESS
-- feedback aborted: redactor stripped your message to nothing useful.

   Original length:  ${#MSG} chars
   After scrubbing:  $USEFUL_CHARS useful alphanumeric chars
   Scrubbed sample:  $(printf '%s' "$SCRUBBED" | head -c 100)

   Likely cause: your input was dominated by paths, hashes, or other
   high-entropy tokens that the privacy layer redacted in full.

   Fix: re-run with descriptive prose instead of paths/IDs. Example:
     sutra feedback --public 'sutra start refuses .claude/-only dirs'
   (not just a path or filename).
USELESS
  exit 2
fi

TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
FILE="$SUTRA_HOME/feedback/manual/${TS}.md"

PLUGIN_VERSION="unknown"
if command -v jq >/dev/null 2>&1 && [ -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
  PLUGIN_VERSION=$(jq -r '.version' "$PLUGIN_ROOT/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")
fi

CONTENT="---
captured_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
plugin_version: ${PLUGIN_VERSION}
channel: manual
---

${SCRUBBED}
"

if ! sutra_safe_write "$FILE" "$CONTENT"; then
  echo "sutra feedback: write failed" >&2
  exit 1
fi

echo "captured at $FILE"
echo "consent granted -- future auto-capture signals will persist locally"
echo "see ~/.sutra/PRIVACY.md for what's captured and retention policy"

# v2.2.0 PROTO-024 V1: fan-out to Sutra team via existing sutra-data git rail.
# Disabled when --public (different path), --no-fanout, kill-switch env, or
# kill-switch file. Failure-path keeps source unmarked for retry on next
# /core:feedback call (no Stop hook, no cron — user-initiated retry only).
fanout_to_sutra_team() {
  [ "$NO_FANOUT" = "1" ] && return 0
  [ "${SUTRA_FEEDBACK_FANOUT:-1}" = "0" ] && return 0
  [ -f "$HOME/.sutra-feedback-fanout-disabled" ] && return 0
  [ "$PUBLIC" = "1" ] && return 0  # --public path handles its own delivery

  local cache="$SUTRA_HOME/sutra-data-cache"
  local install_id_file="$SUTRA_HOME/install-id"
  local install_id=""
  if [ -f "$install_id_file" ]; then
    install_id=$(head -1 "$install_id_file" 2>/dev/null | tr -d '[:space:]')
  fi
  if [ -z "$install_id" ]; then
    if [ -f "$PLUGIN_ROOT/lib/project-id.sh" ]; then
      # shellcheck source=/dev/null
      source "$PLUGIN_ROOT/lib/project-id.sh" 2>/dev/null
      if declare -f compute_install_id >/dev/null 2>&1; then
        install_id=$(compute_install_id "$PLUGIN_VERSION" 2>/dev/null)
      fi
    fi
  fi
  if [ -z "$install_id" ]; then
    echo "-- fanout skipped: install_id not resolved"
    return 0
  fi

  if [ ! -d "$cache/.git" ]; then
    if ! git clone --depth 1 --single-branch --quiet git@github.com:sankalpasawa/sutra-data.git "$cache" 2>/dev/null; then
      echo "-- fanout deferred: could not clone sutra-data (offline / no auth) — will retry on next /core:feedback"
      return 0
    fi
  else
    git -C "$cache" pull --rebase --quiet 2>/dev/null || true
  fi

  local dest_dir="$cache/clients/$install_id/feedback"
  mkdir -p "$dest_dir" 2>/dev/null
  local pushed=0
  local pending=()

  pending+=("$FILE")

  for f in "$SUTRA_HOME/feedback/manual"/*.md; do
    [ -f "$f" ] || continue
    [ "$f" = "$FILE" ] && continue
    [ -f "$f.uploaded" ] && continue
    if [ -n "$(find "$f" -mtime +7 2>/dev/null)" ]; then
      continue
    fi
    pending+=("$f")
  done

  for src in "${pending[@]}"; do
    local fname; fname=$(basename "$src")
    cp "$src" "$dest_dir/$fname" 2>/dev/null || continue
    if (cd "$cache" && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" \
        add "clients/$install_id/feedback/$fname" >/dev/null 2>&1 && \
        git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" \
        commit --quiet -m "feedback: $install_id $fname" >/dev/null 2>&1 && \
        git push --quiet 2>/dev/null); then
      touch "$src.uploaded" 2>/dev/null
      pushed=$((pushed + 1))
    fi
  done

  if [ "$pushed" -ge 1 ]; then
    if [ "$pushed" -eq 1 ]; then
      echo "-- sent to Sutra team (1 item, scrubbed)"
    else
      echo "-- sent to Sutra team ($pushed items, including prior pending)"
    fi
  else
    echo "-- fanout deferred: push failed — will retry on next /core:feedback"
  fi
}

fanout_to_sutra_team

# v2.1: --public opts into GitHub issue post via gh CLI.
if [ "$PUBLIC" = "1" ]; then
  echo ""
  echo "-- --public: about to open a GitHub issue at sankalpasawa/sutra"
  echo "   title:   [feedback v${PLUGIN_VERSION}] from plugin"
  echo "   body:    <scrubbed content above>"
  echo "   visible: PUBLIC (this is permanent; GitHub issues are public)"
  echo ""
  printf "   confirm with 'yes' (anything else cancels): "
  read -r CONFIRM
  if [ "$CONFIRM" = "yes" ]; then
    # v2.6.1: Title carries plugin version; no --label flag.
    # Why: prior --label "feedback,v${PLUGIN_VERSION}" failed every public post
    # because neither label exists on the repo (gh issue create rejects the
    # whole call when any label is unknown). Title-prefix is sufficient for
    # filterability; downstream label automation (if any) can match by prefix.
    #
    # v2.8.6 — derive title from first content line so the inbox is triageable.
    # Per vinit#25 bug 2 (2026-04-28): every issue titled identically made
    # 16+ filings indistinguishable. We pull the first non-blank, non-frontmatter,
    # non-redacted line and cap at 80 chars; version prefix retained for
    # filterability. Falls back to legacy generic only when body has no usable line.
    DERIVED_TITLE=$(printf '%s\n' "$SCRUBBED" | awk '
      { sub(/^[[:space:]]+/,""); sub(/[[:space:]]+$/,"") }
      /^$/        { next }
      /^---$/     { next }
      /<HIGH-ENTROPY>/ { next }
      { print substr($0, 1, 80); exit }
    ')
    if [ -n "$DERIVED_TITLE" ]; then
      TITLE="[v${PLUGIN_VERSION}] ${DERIVED_TITLE}"
    else
      TITLE="[feedback v${PLUGIN_VERSION}] from plugin"
    fi
    GH_OUT=$(gh issue create \
         --repo sankalpasawa/sutra \
         --title "$TITLE" \
         --body "$SCRUBBED" 2>&1)
    if [ $? -eq 0 ]; then
      echo "-- issue opened on sankalpasawa/sutra"
      echo "   ${GH_OUT}"

      # v2.7.x — Close-Loop Layer V0: record install_id ↔ issue_number mapping
      # so when the fix ships, close-marketplace-feedback.sh can deliver the
      # close-out to THIS user's plugin inbox (not just gh comment).
      # Mapping is private — not embedded in public gh issue body.
      ISSUE_URL=$(printf '%s\n' "$GH_OUT" | grep -oE 'https://github.com/[^[:space:]]+/issues/[0-9]+' | tail -1)
      ISSUE_NUM=$(printf '%s' "$ISSUE_URL" | grep -oE '[0-9]+$')
      if [ -n "$ISSUE_NUM" ]; then
        # 1. Local sent ledger (used by plugin's gh-API fallback to know which issues are "ours")
        SENT_LOG="$SUTRA_HOME/feedback/manual/sent.jsonl"
        mkdir -p "$(dirname "$SENT_LOG")" 2>/dev/null
        chmod 0700 "$SUTRA_HOME/feedback/manual" 2>/dev/null
        printf '{"ts":%s,"issue_number":%s,"title":"%s","plugin_version":"%s","url":"%s"}\n' \
          "$(date +%s)" "$ISSUE_NUM" "$TITLE" "$PLUGIN_VERSION" "$ISSUE_URL" \
          >> "$SENT_LOG" 2>/dev/null

        # 2. Private mapping push to sutra-data (clients/<install_id>/feedback-mapping.jsonl)
        # Reuses the install_id resolution from the fanout block above; falls
        # through silently if cache not initialized (next push will catch up).
        if [ -d "$SUTRA_HOME/sutra-data-cache/.git" ] && [ -n "${install_id:-}" ]; then
          MAP_FILE="$SUTRA_HOME/sutra-data-cache/clients/$install_id/feedback-mapping.jsonl"
          mkdir -p "$(dirname "$MAP_FILE")" 2>/dev/null
          printf '{"ts":%s,"issue_number":%s,"title":"%s","plugin_version":"%s"}\n' \
            "$(date +%s)" "$ISSUE_NUM" "$TITLE" "$PLUGIN_VERSION" \
            >> "$MAP_FILE" 2>/dev/null
          (cd "$SUTRA_HOME/sutra-data-cache" \
            && git add "clients/$install_id/feedback-mapping.jsonl" >/dev/null 2>&1 \
            && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" \
               commit -q -m "feedback-mapping: $install_id issue $ISSUE_NUM" >/dev/null 2>&1 \
            && git push -q 2>/dev/null) || true   # best-effort; will retry on next push
        fi
        echo "-- close-loop mapping recorded (issue #$ISSUE_NUM)"
      fi
    else
      echo "-- gh issue create failed — feedback remains captured locally at $FILE"
      echo "   reason: ${GH_OUT}"
    fi
  else
    echo "-- public post cancelled — feedback kept local only"
  fi
fi

exit 0
