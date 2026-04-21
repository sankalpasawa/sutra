#!/bin/bash
# Sutra plugin — shell helper installer.
# Appends sutra-go / sutra-uninstall / sutra-reset / sutra-status-global
# to the user's shell rc file. Idempotent.
#
# Usage (one-time, after installing the plugin):
#   bash ~/.claude/plugins/cache/sutra/sutra/*/scripts/install-shell-helpers.sh

set -u

# Detect shell rc file
RC=""
if [ -f "$HOME/.zshrc" ]; then
  RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
  RC="$HOME/.bashrc"
else
  RC="$HOME/.profile"
  touch "$RC"
fi

# Idempotence check
if grep -q "^sutra-go() {" "$RC" 2>/dev/null; then
  echo "Sutra shell helpers already present in $RC"
  echo "(to update: remove the '# ═══ Sutra plugin shell helpers' block and re-run)"
  exit 0
fi

cat >> "$RC" <<'SUTRA_HELPERS_EOF'

# ═══ Sutra plugin shell helpers (auto-installed) ═══
# https://github.com/sankalpasawa/sutra

sutra-go() {
  # Fresh temp project + deploy Sutra + telemetry ON + open Claude. Silent.
  local n="sutra-test-$(date +%Y%m%d-%H%M%S)"
  mkdir -p ~/temp/$n && cd ~/temp/$n
  git init -q
  git remote add origin git@github.com:${USER}/$n.git 2>/dev/null
  { claude plugin marketplace update sutra && claude plugin uninstall core@sutra 2>/dev/null; claude plugin install core@sutra; } >/dev/null 2>&1
  local v=$(ls ~/.claude/plugins/cache/sutra/sutra/ | sort -V | tail -1)
  CLAUDE_PLUGIN_ROOT=~/.claude/plugins/cache/sutra/sutra/$v CLAUDE_PROJECT_DIR=$PWD bash ~/.claude/plugins/cache/sutra/sutra/$v/scripts/go.sh
  claude
}

sutra-uninstall() {
  claude plugin uninstall core@sutra 2>/dev/null
  claude plugin marketplace remove sutra 2>/dev/null
  echo "Sutra plugin + marketplace removed (data in ~/.sutra/ preserved)"
}

sutra-reset() {
  sutra-uninstall
  rm -rf ~/.sutra 2>/dev/null
  rm -rf ~/.claude/plugins/cache/sutra 2>/dev/null
  echo "Sutra fully reset — no plugin, no data, no cache"
}

sutra-status-global() {
  local v=$(ls ~/.claude/plugins/cache/sutra/sutra/ 2>/dev/null | sort -V | tail -1)
  [ -z "$v" ] && echo "Sutra NOT installed" && return 1
  echo "Sutra plugin:    v$v"
  echo "queue:           ~/.sutra/metrics-queue.jsonl ($(wc -l < ~/.sutra/metrics-queue.jsonl 2>/dev/null | tr -d ' ' || echo 0) rows)"
  [ -f ~/.sutra/last-flush.txt ] && echo "---" && cat ~/.sutra/last-flush.txt
}
# ═══ end Sutra helpers ═══
SUTRA_HELPERS_EOF

echo "Sutra shell helpers installed to $RC"
echo ""
echo "Reload your shell:"
echo "  source $RC"
echo ""
echo "Then use any of:"
echo "  sutra-go              # fresh project + deploy + telemetry + open Claude"
echo "  sutra-uninstall       # remove plugin, keep data"
echo "  sutra-reset           # full factory reset"
echo "  sutra-status-global   # check state from any terminal"
