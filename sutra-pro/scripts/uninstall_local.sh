#!/bin/sh
# Remove the installed Sutra Pro command (GAP-INSTALL, G17): `uv tool uninstall sutra-pro`.
#
#   sh scripts/uninstall_local.sh             stop a running server of the default data folder, then uninstall the tool
#   sh scripts/uninstall_local.sh --dry-run   print what would happen and do nothing
#
# It never deletes data: ~/.sutra-pro (the database, runs, library and logs) stays where it is, and the script says so. Delete
# that folder yourself if you want it gone. Exit 0 fine (also when the tool was not installed), 1 uv failed, 2 usage.
set -eu

DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h | --help)
      sed -n '2,/^set -eu/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "uninstall_local.sh: unknown argument '$arg' (try --help)" >&2
      exit 2
      ;;
  esac
done

say() { echo "uninstall_local.sh: $*"; }
DATA="$HOME/.sutra-pro"

if [ "$DRY" = 1 ]; then
  say "dry run: nothing is stopped or removed. The steps would be:"
  say "  1. sutra-pro stop   (only if a server is running; ends it cleanly)"
  say "  2. uv tool uninstall sutra-pro"
  say "  your data folder $DATA is left in place."
  exit 0
fi

command -v uv >/dev/null 2>&1 || { echo "uninstall_local.sh: FAILED: 'uv' is not installed" >&2; exit 1; }

if ! uv tool list 2>/dev/null | grep -q '^sutra-pro '; then
  say "sutra-pro is not installed as a uv tool; nothing to remove."
else
  SP="$(uv tool dir --bin)/sutra-pro"
  if [ -x "$SP" ] && "$SP" status >/dev/null 2>&1; then
    say "a server is running; stopping it first"
    "$SP" stop || say "warning: it could not be stopped cleanly; uninstalling anyway"
  fi
  uv tool uninstall sutra-pro || { echo "uninstall_local.sh: FAILED: uv tool uninstall" >&2; exit 1; }
  say "sutra-pro was uninstalled."
fi
say "left in place: $DATA (your data: database, runs, library, logs, .env). Delete it yourself if you want it gone."
