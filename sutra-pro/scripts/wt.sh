#!/usr/bin/env bash
# Worktree helper for parallel work packages. One package = one branch wp/<id> in its own worktree.
#
#   scripts/wt.sh new <id>      create ../sutra-app-wt/<id> on branch wp/<id> from main, print its path
#   scripts/wt.sh merge <id>    rebase wp/<id> on main, merge it in a clean candidate checkout under a lock, run the
#                               gate there, and fast-forward main only if it passes (main's own uncommitted edits are
#                               never tested or touched). Exit 0 merged, 2 rebase conflict, 3 gate failed, 4 lock
#                               timeout, 5 main could not fast-forward
#   scripts/wt.sh drop <id>     remove the worktree and the branch (only after a merge)
#   scripts/wt.sh status        list worktrees and how far each branch is ahead of main
#
# Local only: nothing here ever pushes.
set -euo pipefail

# RETIRED (D98). The 62 work packages were built and merged in the standalone repository before sutra-pro moved into the Sutra repo,
# and this helper assumed that repository's layout (the project at the git root, merges recorded as `Merge wp/<id>`). From here on
# work happens on ordinary branches of the Sutra repo, gated by the sutra-pro CI. The text above stays as the record of the method.
echo "wt.sh: retired in the Sutra monorepo (decision D98). Use a normal branch and the sutra-pro CI; docs/BUILD-PLAN.md keeps the history." >&2
exit 2

HERE=$(cd "$(dirname "$0")/.." && pwd)
COMMON=$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)
MAIN=$(dirname "$COMMON")
WTROOT="$(dirname "$MAIN")/$(basename "$MAIN")-wt"
# the lock lives in the shared git directory: every worktree and every worker finds the same path, whatever TMPDIR is
LOCK="$COMMON/merge.lock"
GATE_ARGS=${GATE_ARGS:-}
NAME=(-c user.name="${GIT_AUTHOR_NAME:-Claude}" -c user.email="${GIT_AUTHOR_EMAIL:-noreply@anthropic.com}")

nap() { python3 -c "import time; time.sleep($1)"; }

lock() {
  local waited=0
  until mkdir "$LOCK" 2>/dev/null; do
    # a lock older than 30 minutes belongs to a dead process
    if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null || true; fi
    nap 2; waited=$((waited + 2))
    if [ "$waited" -ge 1800 ]; then echo "wt: gave up waiting for the merge lock" >&2; exit 4; fi
  done
}
unlock() { rmdir "$LOCK" 2>/dev/null || true; }

cmd=${1:-}; id=${2:-}
case "$cmd" in
  new)
    [ -n "$id" ] || { echo "usage: wt.sh new <id>" >&2; exit 1; }
    mkdir -p "$WTROOT"
    path="$WTROOT/$id"
    if [ -e "$path" ]; then echo "$path"; exit 0; fi
    git -C "$MAIN" worktree add -q -b "wp/$id" "$path" main
    echo "$path"
    ;;
  merge)
    [ -n "$id" ] || { echo "usage: wt.sh merge <id>" >&2; exit 1; }
    path="$WTROOT/$id"
    [ -d "$path" ] || { echo "wt: no worktree $path" >&2; exit 1; }
    if [ -n "$(git -C "$path" status --porcelain)" ]; then echo "wt: commit your work in $path first" >&2; exit 1; fi
    cand="$WTROOT/_candidate"
    finish() { git -C "$MAIN" worktree remove --force "$cand" >/dev/null 2>&1 || true; unlock; }
    lock; trap finish EXIT
    # A merge candidate is built and gated in a clean throwaway checkout, never in main's working tree: main may hold
    # uncommitted edits (documents being written) that must neither be tested nor touched. Main only moves, by a
    # fast-forward, when the gate has passed.
    git -C "$MAIN" worktree remove --force "$cand" >/dev/null 2>&1 || rm -rf "$cand"
    git -C "$MAIN" worktree prune
    if ! git -C "$path" "${NAME[@]}" rebase main >/tmp/wt-rebase-$$.log 2>&1; then
      git -C "$path" rebase --abort >/dev/null 2>&1 || true
      echo "wt: CONFLICT while rebasing wp/$id on main; resolve in $path (git rebase main), commit, and run merge again" >&2
      cat /tmp/wt-rebase-$$.log >&2; rm -f /tmp/wt-rebase-$$.log; exit 2
    fi
    rm -f /tmp/wt-rebase-$$.log
    before=$(git -C "$MAIN" rev-parse HEAD)
    git -C "$MAIN" worktree add -q --detach "$cand" "$before"
    git -C "$cand" "${NAME[@]}" merge -q --no-ff -m "Merge wp/$id" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" "wp/$id"
    if ! (cd "$cand" && scripts/gate.sh $GATE_ARGS); then
      echo "wt: the gate failed on the candidate merge of wp/$id; main is untouched. Fix in $path and merge again" >&2; exit 3
    fi
    new=$(git -C "$cand" rev-parse HEAD)
    if ! git -C "$MAIN" merge -q --ff-only "$new" >/tmp/wt-ff-$$.log 2>&1; then
      cat /tmp/wt-ff-$$.log >&2; rm -f /tmp/wt-ff-$$.log
      echo "wt: the gate passed but main could not fast-forward (main moved, is not on branch main, or local edits touch files of this merge); run merge again" >&2; exit 5
    fi
    rm -f /tmp/wt-ff-$$.log
    echo "wt: merged wp/$id into main at $(git -C "$MAIN" rev-parse --short HEAD)"
    ;;
  drop)
    [ -n "$id" ] || { echo "usage: wt.sh drop <id>" >&2; exit 1; }
    git -C "$MAIN" worktree remove --force "$WTROOT/$id" 2>/dev/null || true
    git -C "$MAIN" branch -D "wp/$id" >/dev/null 2>&1 || true
    git -C "$MAIN" worktree prune
    ;;
  status)
    git -C "$MAIN" worktree list
    for b in $(git -C "$MAIN" for-each-ref --format='%(refname:short)' 'refs/heads/wp/*'); do
      echo "$b: $(git -C "$MAIN" rev-list --count "main..$b") ahead, $(git -C "$MAIN" rev-list --count "$b..main") behind"
    done
    ;;
  *)
    echo "usage: wt.sh new|merge|drop|status <id>" >&2; exit 1 ;;
esac
