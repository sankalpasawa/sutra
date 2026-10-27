#!/bin/bash
# Does the J2 page still hold against a branch that is about to merge? (UI port, package j2ui-verify, T6)
#   usage: qa/walks/j2ui-against.sh <branch> [base]       base defaults to main
# A temporary worktree of <base> with <branch> merged into it and not committed; there the adapter's contract (the whole app in
# every cycle state), the page rendered on the prototype's own captured runs, the chat and the audit tests run, on a records home
# of their own; then the worktree is removed, whatever happened. The user's checkout and the branches are not touched.
#   exit 0  the four test files pass on the merge
#   exit 1  a test fails, or the merge does not apply (the files in conflict are named)
#   exit 2  nothing was run (no such branch or base, no interpreter)
# The integrator runs it for each branch before its merge and once more after it. A failure names a function the branch moved that
# the adapter calls (a public reader of the records), not the page: the page is the prototype's file and is not edited.
set -u
BR="${1:-}"
BASE="${2:-main}"
if [ -z "$BR" ]; then sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
UI="$(cd "$HERE/../.." && pwd)"
REPO="$(git -C "$UI" rev-parse --show-toplevel 2>/dev/null)" || { echo "j2ui-against: $UI is not in a git checkout"; exit 2; }
PREFIX="$(git -C "$UI" rev-parse --show-prefix)"
for ref in "$BR" "$BASE"; do
  git -C "$REPO" rev-parse --verify -q "$ref^{commit}" >/dev/null || { echo "j2ui-against: no such branch or commit: $ref"; exit 2; }
done
PY="$UI/.venv/bin/python"
[ -x "$PY" ] || { echo "j2ui-against: $PY is not here (the app's venv)"; exit 2; }
WT="$(mktemp -d "${TMPDIR:-/tmp}/j2ui-against-XXXXXX")"
cleanup() { git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$WT"; git -C "$REPO" worktree prune >/dev/null 2>&1; }
trap cleanup EXIT
git -C "$REPO" worktree add --detach "$WT" "$BASE" >/dev/null 2>&1 || { echo "j2ui-against: could not make a worktree of $BASE"; exit 2; }
if ! git -C "$WT" -c user.name=j2ui-against -c user.email=j2ui-against@localhost merge --no-commit --no-ff "$BR" >"$WT/.merge.log" 2>&1; then
  if git -C "$WT" diff --name-only --diff-filter=U | grep -q .; then
    echo "j2ui-against: $BR does not merge into $BASE cleanly; in conflict:"
    git -C "$WT" diff --name-only --diff-filter=U | sed 's/^/  /'
    exit 1
  fi
  if ! grep -q "Already up to date" "$WT/.merge.log"; then cat "$WT/.merge.log"; echo "j2ui-against: the merge failed"; exit 1; fi
fi
rm -f "$WT/.merge.log"
echo "j2ui-against: $BR merged into $BASE ($(git -C "$REPO" rev-parse --short "$BASE")), not committed; running in the worktree"
TUI="$WT/$PREFIX"
ln -s "$UI/.venv" "$TUI/.venv"                       # the venv is not in git: the worktree borrows this checkout's
cd "$TUI" || exit 2
FILES="test_j2ui_contract.py test_j2ui_render.py test_j2ui_chat.py test_j2ui_audit.py"
for f in $FILES; do [ -f "$f" ] || { echo "j2ui-against: $f is not in $BASE plus $BR (merge j2ui-verify first)"; exit 2; }; done
SUTRA_NATIVE_HOME="$(mktemp -d "${TMPDIR:-/tmp}/j2ui-against-home-XXXXXX")" "$TUI/.venv/bin/python" -m pytest -q -p no:cacheprovider -W ignore $FILES
RC=$?
echo "j2ui-against: $BR on $BASE: exit $RC"
exit $RC
