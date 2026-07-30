#!/usr/bin/env bash
# flow-factors.sh -- deterministic unit-factor extraction for the Flow spine
# (D62 / ADR-029). Stage [4] inner-engine helper: given a one-line unit of
# work, emit the mechanical task factors as JSON.
#
# DETERMINISM CONTRACT (pinned by tests/flow-orchestrator/f6-factors-case.txt):
#   - no clock, no network, no filesystem state, no $RANDOM
#   - LC_ALL=C; JSON serialized with sorted keys + fixed separators
#   - same input -> byte-identical output on every run, exit 0
#
# Input:  the unit statement as a single positional argument (or stdin).
# Output: one JSON object:
#   {
#     "schema": "flow-factors-v1",
#     "unit": "<input>",
#     "unit_factors": {
#       "steps_est":         <int, >=1>   # 1 + coordination joins found
#       "word_count":        <int>,
#       "conjunction_count": <int>,       # and/then/plus joins
#       "mutation_verbs":    <int>,       # write-shaped verbs present
#       "has_cli_flag":      <bool>       # --flag token present
#     }
#   }
#
# steps_est heuristic: a unit is 1 step plus one step per coordination join
# ("and", "then", "plus", ";"). Purely lexical, no model call -- honest
# mechanical floor, not a depth judgment (that stays with core:depth-estimation).

set -u
export LC_ALL=C

if [ $# -gt 1 ]; then
  echo "usage: $(basename "$0") \"<unit statement>\"  (or pipe via stdin)" >&2
  exit 2
fi

if [ $# -eq 1 ]; then
  UNIT="$1"
else
  if [ -t 0 ]; then
    echo "usage: $(basename "$0") \"<unit statement>\"  (or pipe via stdin)" >&2
    exit 2
  fi
  UNIT="$(cat)"
fi

if [ -z "$UNIT" ]; then
  echo "ERROR: empty unit statement" >&2
  exit 2
fi

export UNIT
python3 - <<'PY'
import json, os, re

unit = os.environ["UNIT"]
words = unit.split()
lower = [w.strip(".,;:!?").lower() for w in words]

CONJUNCTIONS = {"and", "then", "plus"}
MUTATION_VERBS = {"add", "write", "edit", "create", "wire", "build", "ship",
                  "fix", "update", "delete", "remove", "append", "rename",
                  "move", "install", "register", "author"}

conjunction_count = sum(1 for w in lower if w in CONJUNCTIONS)
conjunction_count += unit.count(";")
mutation_verbs = sum(1 for w in lower if w in MUTATION_VERBS)
has_cli_flag = bool(re.search(r"(^|\s)--[A-Za-z][A-Za-z0-9-]*", unit))

factors = {
    "schema": "flow-factors-v1",
    "unit": unit,
    "unit_factors": {
        "steps_est": 1 + conjunction_count,
        "word_count": len(words),
        "conjunction_count": conjunction_count,
        "mutation_verbs": mutation_verbs,
        "has_cli_flag": has_cli_flag,
    },
}

print(json.dumps(factors, ensure_ascii=True, sort_keys=True,
                 separators=(",", ":")))
PY
