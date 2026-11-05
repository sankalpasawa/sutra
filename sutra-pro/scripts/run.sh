#!/bin/sh
# Run Sutra Pro from a checkout (D12, GAP-OPS-1): scripts/run.sh [serve flags | command ...]
#
#   scripts/run.sh                       check the setup offline (doctor), then start the server and open the browser
#   scripts/run.sh --port 9000 --no-browser
#   scripts/run.sh status | stop | doctor | config show      an operator command is passed straight through
#   scripts/run.sh --help                the server's help (no checks, nothing is started)
#
# It needs a virtualenv. It looks for .venv in this checkout, then in the main checkout this one is a worktree of; when there is none
# it creates one here with `uv venv --python 3.11` and installs the project (`-e ".[dev]"`) and says so. Nothing else is installed.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)

find_python() {
  if [ -x "$HERE/.venv/bin/python" ]; then
    echo "$HERE/.venv/bin/python"
    return 0
  fi
  prefix=$(git -C "$HERE" rev-parse --show-prefix 2>/dev/null || true)
  common=$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  if [ -n "$common" ] && [ -x "$(dirname "$common")/${prefix%/}/.venv/bin/python" ]; then
    echo "$(dirname "$common")/${prefix%/}/.venv/bin/python"
    return 0
  fi
  return 1
}

if ! PY=$(find_python); then
  if ! command -v uv >/dev/null 2>&1; then
    echo "run.sh: there is no .venv and 'uv' is not installed. Install uv (https://docs.astral.sh/uv/) or create $HERE/.venv yourself with Python 3.11." >&2
    exit 1
  fi
  echo "run.sh: no .venv found. Creating $HERE/.venv with uv (Python 3.11) and installing this project into it (-e \".[dev]\")..."
  uv venv --python 3.11 "$HERE/.venv"
  uv pip install --python "$HERE/.venv/bin/python" -e "$HERE[dev]"
  PY="$HERE/.venv/bin/python"
fi

# this checkout's code wins over any other install of sutra_app (a worktree shares the main checkout's virtualenv)
PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

# a preflight only before the server starts: no arguments, a leading flag, or `serve`; never for --help or another command
serving=0
case "${1-}" in
  "" | serve | -*) serving=1 ;;
esac
for arg in "$@"; do
  case "$arg" in
    -h | --help) serving=0 ;;
  esac
done

if [ "$serving" = 1 ]; then
  data_dir=""
  prev=""
  for arg in "$@"; do
    [ "$prev" = "--data-dir" ] && data_dir="$arg"
    case "$arg" in --data-dir=*) data_dir="${arg#--data-dir=}" ;; esac
    prev="$arg"
  done
  echo "run.sh: checking the setup (sutra-pro doctor --offline)..."
  if [ -n "$data_dir" ]; then
    "$PY" -m sutra_app doctor --offline --data-dir "$data_dir" || { echo "run.sh: fix the failed checks above, then run it again." >&2; exit 1; }
  else
    "$PY" -m sutra_app doctor --offline || { echo "run.sh: fix the failed checks above, then run it again." >&2; exit 1; }
  fi
fi

exec "$PY" -m sutra_app "$@"
