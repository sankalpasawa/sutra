#!/usr/bin/env bash
#
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/commands/assistant-decommission
#   Acceptance: archives events + profile to sutra/archive/; unregisters Stop
#     hook from .claude/settings.json; prints summary; supports --dry-run.
#
# Direction: founder 2026-04-25 "Have a kill switch also if you want to
#   decommission this product"; memory [Archive, never delete]
# Spec: holding/research/2026-04-24-assistant-layer-design.md §18 decommission criteria
#
# PURPOSE
# The "kill the product" switch — distinct from per-hook disable.
# Unregisters the assistant layer permanently, archives all state.
# Use for: pivot, client-requested teardown, superseded by newer primitive.
#
# USAGE
#   bash holding/scripts/assistant-decommission.sh --dry-run   # preview
#   bash holding/scripts/assistant-decommission.sh --confirm   # do it
#   bash holding/scripts/assistant-decommission.sh --help
#
# What it does (in order):
#   1. Archive events.jsonl + profile.json → sutra/archive/assistants/<client_id>/<ts>/
#   2. Remove the Stop hook entry for assistant-kill-switch.sh from .claude/settings.json
#   3. Archive the plugin-side hook registration reminder as a cascade TODO
#   4. Print summary of what was archived + what was removed
#   5. Exit 0 on success; non-zero on any failure (nothing partial)
#
# What it does NOT do (manual follow-ups printed at the end):
#   - Delete the holding/hooks/assistant-*.sh scripts (left in place; idempotent)
#   - Modify sutra/marketplace/plugin/hooks/hooks.json (requires Sutra session)
#   - Bump plugin version (requires Sutra session)
#   - Touch ~/Claude/<client>/ directories (D33 firewall)

set -uo pipefail

command -v jq >/dev/null 2>&1 || { printf 'jq required\n' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { printf 'python3 required for settings.json edit\n' >&2; exit 1; }

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CLIENT_ID="${SUTRA_CLIENT_ID:-holding}"
STATE_DIR="${SUTRA_ASSISTANT_STATE_DIR:-$REPO_ROOT/holding/state/assistants/$CLIENT_ID}"
SETTINGS="$REPO_ROOT/.claude/settings.json"
ARCHIVE_ROOT="${SUTRA_ARCHIVE_ROOT:-$REPO_ROOT/sutra/archive/assistants}"

MODE=""
case "${1:-}" in
  --dry-run) MODE="dry" ;;
  --confirm) MODE="confirm" ;;
  -h|--help|"") sed -n '/^# USAGE/,/^# What it does NOT/p' "$0" | sed 's/^# //; s/^#$//'; exit 0 ;;
  *) printf 'unknown arg: %s\n' "$1" >&2; exit 2 ;;
esac

TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
ARCHIVE_DIR="$ARCHIVE_ROOT/$CLIENT_ID/$TS"

printf '\n╔═════════════════════════════════════════════════════════╗\n'
printf '║  ASSISTANT DECOMMISSION — client_id=%s  mode=%s\n' "$CLIENT_ID" "$MODE"
printf '╚═════════════════════════════════════════════════════════╝\n\n'

# Codex R1 MODIFY fix: REORDER steps — settings.json FIRST (atomic via
# tmp+os.replace), then archive. If archive fails after settings are
# updated, observer is already stopped → no partial-state corruption.

# ── Step 1 (pre-flight): inspect state + hook ──────────────────────────
printf 'Step 1: Inspect\n'
events_count=0
profile_exists=no
[ -f "$STATE_DIR/events.jsonl" ] && events_count=$(wc -l < "$STATE_DIR/events.jsonl" | tr -d ' ')
[ -f "$STATE_DIR/profile.json" ] && profile_exists=yes
printf '  source       : %s\n' "$STATE_DIR"
printf '  events.jsonl : %s lines\n' "$events_count"
printf '  profile.json : %s\n' "$profile_exists"
printf '  archive to   : %s\n' "$ARCHIVE_DIR"
hook_present=$(python3 -c "
import json
with open('$SETTINGS') as f: d = json.load(f)
stop = d.get('hooks', {}).get('Stop', [])
match = sum(1 for entry in stop for h in entry.get('hooks', []) if 'assistant-kill-switch.sh' in h.get('command',''))
print(match)
")
printf '  Stop-hook matches in settings.json: %s\n\n' "$hook_present"

# ── Step 2: Unregister Stop hook (atomic write via tmp + os.replace) ───
printf 'Step 2: Unregister Stop hook (atomic)\n'
if [ "$MODE" = "confirm" ] && [ "$hook_present" -gt 0 ]; then
  python3 - "$SETTINGS" <<'PYEOF' || { printf '  FAIL: atomic settings write failed — NOTHING archived yet (safe)\n' >&2; exit 1; }
import json, os, sys, tempfile
path = sys.argv[1]
with open(path) as f: d = json.load(f)
stop = d.get('hooks', {}).get('Stop', [])
stop2 = []
for entry in stop:
    hooks = entry.get('hooks', [])
    hooks2 = [h for h in hooks if 'assistant-kill-switch.sh' not in h.get('command','')]
    if hooks2:
        entry['hooks'] = hooks2
        stop2.append(entry)
d['hooks']['Stop'] = stop2
d_dir = os.path.dirname(os.path.abspath(path))
fd, tmp = tempfile.mkstemp(prefix='settings.', suffix='.tmp', dir=d_dir)
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    print('  → removed (atomic replace).')
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
PYEOF
elif [ "$MODE" = "confirm" ]; then
  printf '  (nothing to remove)\n'
else
  [ "$hook_present" -eq 0 ] && printf '  (nothing to remove)\n' || printf '  (dry-run) would remove %s entries.\n' "$hook_present"
fi
printf '\n'

# ── Step 3: Archive state (settings already updated — safe to archive) ─
printf 'Step 3: Archive state\n'
if [ "$MODE" = "confirm" ]; then
  mkdir -p "$ARCHIVE_DIR" || { printf '  FAIL: cannot create archive dir (settings already updated; observer stopped; re-run for archive)\n' >&2; exit 1; }
  for f in events.jsonl profile.json hook-log.cursor; do
    [ -f "$STATE_DIR/$f" ] && mv "$STATE_DIR/$f" "$ARCHIVE_DIR/$f"
  done
  for f in "$STATE_DIR"/events-*.jsonl.gz; do
    [ -f "$f" ] && mv "$f" "$ARCHIVE_DIR/"
  done
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — decommissioned client_id=$CLIENT_ID from $REPO_ROOT" > "$ARCHIVE_DIR/DECOMMISSION-NOTE.txt"
  printf '  → archived.\n\n'
else
  printf '  (dry-run) would archive.\n\n'
fi

# ── Step 3: Manual follow-up reminders ────────────────────────────────
printf 'Step 3: Manual follow-ups (NOT done by this script)\n'
printf '  □ Sutra session: remove assistant-kill-switch registration from sutra/marketplace/plugin/hooks/hooks.json\n'
printf '  □ Sutra session: bump sutra/CURRENT-VERSION.md noting decommission\n'
printf '  □ Optionally delete holding/hooks/assistant-*.sh (scripts are idempotent; safe to leave)\n'
printf '  □ Plugin update propagates decommission to all clients (T2/T3/T4) on next /plugin install\n\n'

# ── Summary ───────────────────────────────────────────────────────────
printf 'Summary\n'
if [ "$MODE" = "confirm" ]; then
  printf '  Status      : DECOMMISSIONED (client=%s, session=%s)\n' "$CLIENT_ID" "$TS"
  printf '  Archived to : %s\n' "$ARCHIVE_DIR"
  printf '  Hook        : removed from .claude/settings.json\n'
  printf '  Reversal    : restore files from archive; re-register Stop hook; profile auto-bootstraps on next --ask\n'
else
  printf '  Status      : DRY-RUN (no changes made)\n'
  printf '  Run with    : --confirm to actually decommission\n'
fi
printf '\n'

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (D30a)
#
# ### 1. Measurement mechanism
# Count of DECOMMISSION-NOTE.txt files under sutra/archive/assistants/ =
# total decommission events. Compare against plugin install count to see
# decommission rate.
#
# ### 2. Adoption mechanism
# Promoted with P5 to sutra/marketplace/plugin/commands/.
#
# ### 3. Monitoring / escalation
# Any decommission = CEO of Asawa notice (archive dir timestamp fires a
# pulse event in Observability dept). Spike in decommission rate = product
# quality signal.
#
# ### 4. Iteration trigger
# Founder reviews archive dir quarterly. Any repeated reason in
# DECOMMISSION-NOTE.txt across clients = revisit spec.
#
# ### 5. DRI
# Sutra-OS owner (founder during P1-P6).
#
# ### 6. Decommission criteria
# This IS the decommission mechanism. No self-decommission path; replaced
# by a successor script when the product retires.
# ═══════════════════════════════════════════════════════════════════════════
