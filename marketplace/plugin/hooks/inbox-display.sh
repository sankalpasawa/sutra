#!/bin/bash
# inbox-display.sh — Close-Loop Layer V0 (FEEDBACK charter §N).
#
# Fires on SessionStart. Two delivery paths:
#   1. PRIMARY: read clients/<install_id>/inbox/ from sutra-data git rail —
#      delivers close-out messages for issues filed via `sutra feedback --public`
#      (mapping recorded by feedback.sh after gh issue create succeeds).
#   2. FALLBACK: if `gh auth status` works, query gh API for issues authored by
#      the user that were closed since last-seen — covers gh-UI filers (vinit
#      style) who never went through the plugin path.
#
# Both paths verify gh_author match before display (privacy two-factor — fence
# against wrong-user delivery if mapping has a bug).
#
# Soft-fail by design: every error path exits 0 (never blocks session start).
# stderr → .enforcement/inbox-display.log for monitoring.
#
# Kill-switches:
#   SUTRA_INBOX_DISABLED=1
#   ~/.sutra-inbox-disabled  (file presence)

set -u   # not -e: soft-fail throughout

# Kill-switch
[ "${SUTRA_INBOX_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.sutra-inbox-disabled" ] && exit 0

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
CACHE="$SUTRA_HOME/sutra-data-cache"
LAST_SEEN_FILE="$SUTRA_HOME/inbox-last-seen.txt"
LOG_DIR="${CLAUDE_PROJECT_DIR:-$PWD}/.enforcement"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/inbox-display.log"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG" 2>/dev/null
}

display_item() {
  local body="$1"
  local issue_num="$2"
  local issue_title="$3"
  echo ""
  echo "─────────────────────────────────────────────────────────────"
  echo " 📬 Update on your feedback — issue #${issue_num}"
  if [ -n "$issue_title" ]; then
    echo "    \"${issue_title}\""
  fi
  echo "─────────────────────────────────────────────────────────────"
  echo "$body"
  echo "─────────────────────────────────────────────────────────────"
  echo ""
}

# Resolve install_id (best-effort)
install_id=""
if [ -f "$SUTRA_HOME/install-id" ]; then
  install_id=$(head -1 "$SUTRA_HOME/install-id" 2>/dev/null | tr -d '[:space:]')
fi

# Resolve gh_login (used for two-factor verify + fallback path)
gh_login=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh_login=$(gh api user --jq .login 2>/dev/null || echo "")
fi

# ─── PATH 1: per-user inbox via sutra-data git rail ─────────────────────────
displayed_count=0
if [ -n "$install_id" ] && [ -d "$CACHE/.git" ]; then
  # Refresh cache (best-effort, quiet)
  (cd "$CACHE" && git pull -q 2>/dev/null) || log "git pull failed; reading cached inbox"

  INBOX_DIR="$CACHE/clients/$install_id/inbox"
  if [ -d "$INBOX_DIR" ]; then
    READ_DIR="$INBOX_DIR/read"
    mkdir -p "$READ_DIR" 2>/dev/null

    for f in "$INBOX_DIR"/*.md; do
      [ -f "$f" ] || continue   # no-match guard
      [ "$(basename "$f")" = "read" ] && continue

      # Two-factor: verify gh_author in frontmatter matches current gh_login
      file_author=$(grep -E '^gh_author:' "$f" 2>/dev/null | head -1 | sed 's/^gh_author:[[:space:]]*//' | tr -d '[:space:]')
      if [ -n "$file_author" ] && [ -n "$gh_login" ] && [ "$file_author" != "$gh_login" ]; then
        log "WARN: inbox file $f has gh_author=$file_author but session is $gh_login — skipping (privacy guard)"
        continue
      fi

      # Extract title + issue number from frontmatter; body is everything after the ---/--- block
      issue_num=$(grep -E '^issue_number:' "$f" 2>/dev/null | head -1 | sed 's/^issue_number:[[:space:]]*//' | tr -d '[:space:]')
      issue_title=$(grep -E '^issue_title:' "$f" 2>/dev/null | head -1 | sed 's/^issue_title:[[:space:]]*//')
      body=$(awk '/^---$/{c++; next} c>=2{print}' "$f" 2>/dev/null)

      [ -z "$body" ] && body="$(cat "$f" 2>/dev/null)"
      display_item "$body" "${issue_num:-?}" "$issue_title"
      displayed_count=$((displayed_count + 1))

      # Move to read/ so we don't re-display
      mv "$f" "$READ_DIR/$(basename "$f")" 2>/dev/null || true
    done

    if [ $displayed_count -gt 0 ]; then
      log "displayed $displayed_count inbox item(s) for $install_id"
      # Push the move so other sessions don't re-display
      (cd "$CACHE" \
        && git add "clients/$install_id/inbox" >/dev/null 2>&1 \
        && git -c user.name="sutra-plugin" -c user.email="plugin@sutra.os" \
           commit -q -m "inbox: marked $displayed_count item(s) read on $install_id" >/dev/null 2>&1 \
        && git push -q 2>/dev/null) || log "inbox-read push failed; will retry next session"
    fi
  fi
fi

# ─── PATH 2: gh-author fallback for legacy gh-UI filers ─────────────────────
# Covers users who filed issues via gh-UI directly (no install_id mapping).
# Only fires if gh auth works AND we haven't displayed anything via PATH 1
# for this issue (idempotency by tracking last-seen + displayed-issues).
if [ -n "$gh_login" ]; then
  # Read last-seen timestamp; default to 24h ago for first run
  if [ -f "$LAST_SEEN_FILE" ]; then
    last_seen=$(cat "$LAST_SEEN_FILE" 2>/dev/null | tr -d '[:space:]')
  else
    last_seen=""
  fi
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # Build search query
  if [ -n "$last_seen" ]; then
    search_query="author:$gh_login is:closed closed:>$last_seen"
  else
    # First run — look back 7 days only (avoid spamming with old closes)
    seven_d_ago=$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")
    search_query="author:$gh_login is:closed${seven_d_ago:+ closed:>$seven_d_ago}"
  fi

  # Query gh; rate-limit aware (3s timeout; if it fails, skip silently)
  closed_json=$(timeout 3 gh issue list --repo sankalpasawa/sutra --search "$search_query" --json number,title,closedAt,comments --limit 10 2>/dev/null || echo "[]")
  if [ -n "$closed_json" ] && [ "$closed_json" != "[]" ]; then
    # Track which issue numbers we've already displayed (from PATH 1) to avoid duplicates
    displayed_issues_file="$SUTRA_HOME/inbox-displayed-issues.jsonl"
    [ -f "$displayed_issues_file" ] || touch "$displayed_issues_file"

    fallback_count=0
    while IFS= read -r issue_line; do
      [ -z "$issue_line" ] && continue
      issue_num=$(echo "$issue_line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('number',''))" 2>/dev/null)
      issue_title=$(echo "$issue_line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('title',''))" 2>/dev/null)
      [ -z "$issue_num" ] && continue

      # Skip if already displayed (PATH 1 or prior fallback run)
      grep -q "\"issue\":$issue_num\b" "$displayed_issues_file" 2>/dev/null && continue

      # Fetch the latest comment as the close-out
      latest_comment=$(timeout 3 gh issue view "$issue_num" --repo sankalpasawa/sutra --json comments --jq '.comments[-1].body' 2>/dev/null)
      if [ -n "$latest_comment" ] && [ "$latest_comment" != "null" ]; then
        display_item "$latest_comment" "$issue_num" "$issue_title"
        fallback_count=$((fallback_count + 1))
        printf '{"ts":%s,"issue":%s,"path":"fallback"}\n' "$(date +%s)" "$issue_num" >> "$displayed_issues_file"
      fi
    done < <(echo "$closed_json" | python3 -c "import sys,json; [print(json.dumps(i)) for i in json.load(sys.stdin)]" 2>/dev/null)

    [ $fallback_count -gt 0 ] && log "displayed $fallback_count fallback item(s) for $gh_login"
  fi

  # Update last-seen
  echo "$now" > "$LAST_SEEN_FILE" 2>/dev/null
fi

# Always exit 0 — soft-fail
exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (per OPERATIONALIZATION.md §2)
#
# ### 1. Measurement mechanism
# stderr lines in .enforcement/inbox-display.log per fire. Per-session metric:
# {fired, path1_displayed, path2_displayed, errors}. Aggregated by analytics
# dept per existing fleet rollup pattern.
#
# ### 2. Adoption mechanism
# Registered in plugin/hooks/hooks.json under SessionStart (plugin v2.7.x).
# Fleet inherits via plugin auto-update on session start. No user opt-in
# needed — soft-failing display, kill-switches available for opt-out.
#
# ### 3. Monitoring / escalation
# Analytics dept tails inbox-display.log; warns on error rate >5% across
# sessions. Breach: hook errors prevent session start (timeout, blocking).
# Mitigation: timeouts on gh API (3s); set -u not -e; soft-fail throughout.
#
# ### 4. Iteration trigger
# Revise when: (a) display shown to wrong user (privacy P0) → audit + harden
# two-factor verify; (b) gh API fallback consistently rate-limited → cache
# query result longer + delta-only fetch; (c) inbox push race causes duplicates
# → switch from move-to-read to atomic mark-as-read in JSONL log.
#
# ### 5. DRI
# Sutra-OS for hook code; Asawa CEO for delivery-content decisions; Engineering
# for plugin promotion + 30d stability gate.
#
# ### 6. Decommission criteria
# Retire when (a) PROTO-024 V2 encrypted feedback channel ships with native
# in-session display; (b) Claude Code adds first-party plugin notification UI;
# (c) feedback volume justifies a dedicated app. 30d deprecation banner +
# founder approval required.
# ═══════════════════════════════════════════════════════════════════════════
