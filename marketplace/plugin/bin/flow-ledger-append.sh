#!/usr/bin/env bash
# flow-ledger-append.sh -- append-only writer for the flow ledger.
#
# Ledger path: <repo-root>/.sutra/flow-ledger.jsonl
#   repo root = git rev-parse --show-toplevel, fallback: cwd
#   Override for tests: FLOW_LEDGER_PATH=<path>
#
# Input: exactly one JSON row, via:
#   flow-ledger-append.sh --json '<json-string>'
#   echo '<json-string>' | flow-ledger-append.sh
#
# Row shape (validated loosely -- extra keys are kept, not rejected):
#   {
#     "unit":  str,
#     "steps": int,
#     "atoms": [{"atom_id": str, "status": str, "verify_result": str}, ...],
#     "agents": int,
#     "close": {"measured": str, "learned": str, "next": str}
#   }
#
# Processing (embedded python3, stdlib only):
#   1. REDACTION -- secret-shaped substrings in ANY string value are
#      replaced with [REDACTED] (sk-/AKIA/ghp_/xox?-/PEM/Bearer patterns).
#   2. CAPS -- every string field is truncated to 2048 chars with the
#      suffix "...[truncated]"; if the serialized row still exceeds
#      8192 bytes, evidence-like optional fields are dropped and string
#      caps re-applied at a smaller size.
#   3. Adds "ts" (ISO-8601 UTC, from date -u) and "schema": "flow-ledger-v1".
#
# CONCURRENCY: append uses plain >> with NO locking. Parallel writers are
# NOT supported -- the orchestrator is the single sequential writer per
# ADR-029. Do not call this from concurrent subagents.
#
# Output on success: "<bytes> bytes (excl. newline) APPENDED -> <ledger-path>"

set -euo pipefail

# --- A7-01: path resolution + mkdir ---------------------------------------
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ledger="${FLOW_LEDGER_PATH:-$repo_root/.sutra/flow-ledger.jsonl}"
mkdir -p "$(dirname "$ledger")"

# --- A7-02: input via --json arg or stdin ---------------------------------
if [ "${1:-}" = "--json" ]; then
  if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
    echo "ERROR: --json requires a non-empty JSON string" >&2
    exit 2
  fi
  if [ $# -gt 2 ]; then
    echo "ERROR: unexpected extra arguments after --json (expected exactly one JSON row)" >&2
    exit 2
  fi
  ROW_JSON="$2"
elif [ $# -gt 0 ]; then
  echo "ERROR: unknown argument '$1' (use --json '<row>' or pipe via stdin)" >&2
  exit 2
else
  ROW_JSON="$(cat)"
  if [ -z "$ROW_JSON" ]; then
    echo "ERROR: empty stdin -- expected one JSON row" >&2
    exit 2
  fi
fi
export ROW_JSON

# --- A7-07 (ts source): ISO-8601 UTC via date -u --------------------------
ROW_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export ROW_TS

# --- A7-03..07: parse, redact, cap, degrade, stamp (python3 stdlib) -------
final_row="$(python3 - <<'PY'
import json, os, re, sys

STRING_CAP = 2048
ROW_CAP_BYTES = 8192
DEGRADED_STRING_CAP = 512
TRUNC_SUFFIX = "...[truncated]"

# A7-04: redaction regexes (applied anywhere inside string values)
REDACT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*KEY-----"),
    re.compile(r"Bearer [A-Za-z0-9._-]{15,}"),
]

# A7-06: evidence-like optional keys, dropped (any nesting level) when the
# serialized row exceeds ROW_CAP_BYTES.
EVIDENCE_KEYS = {"evidence", "verify_output", "log", "logs", "raw", "detail",
                 "details", "output", "stdout", "stderr", "transcript"}

raw = os.environ["ROW_JSON"]
try:
    row = json.loads(raw)
except json.JSONDecodeError as e:
    sys.stderr.write("ERROR: input is not valid JSON: %s\n" % e)
    sys.exit(3)

if not isinstance(row, dict):
    sys.stderr.write("ERROR: row must be a JSON object\n")
    sys.exit(3)

# A7-03: loose validation -- type-check known keys when present; never
# reject extra keys.
def warn(msg):
    sys.stderr.write("WARN: %s\n" % msg)

if not isinstance(row.get("unit", ""), str):
    warn("'unit' should be a string")
if not isinstance(row.get("steps", 0), int):
    warn("'steps' should be an int")
if not isinstance(row.get("agents", 0), int):
    warn("'agents' should be an int")
if not isinstance(row.get("atoms", []), list):
    warn("'atoms' should be a list")
if not isinstance(row.get("close", {}), dict):
    warn("'close' should be an object")

def redact(s):
    for pat in REDACT_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s

def walk(value, str_fn):
    if isinstance(value, str):
        return str_fn(value)
    if isinstance(value, list):
        return [walk(v, str_fn) for v in value]
    if isinstance(value, dict):
        return {k: walk(v, str_fn) for k, v in value.items()}
    return value

def cap_string(s, cap):
    if s.endswith(TRUNC_SUFFIX):
        s = s[:-len(TRUNC_SUFFIX)]
    if len(s) > cap:
        return s[:cap] + TRUNC_SUFFIX
    return s

# A7-04: redact FIRST (before truncation can split a secret).
row = walk(row, redact)
# A7-05: per-string cap.
row = walk(row, lambda s: cap_string(s, STRING_CAP))

# A7-07: stamp ts + schema.
row["ts"] = os.environ["ROW_TS"]
row["schema"] = "flow-ledger-v1"

def serialize(r):
    return json.dumps(r, ensure_ascii=True, separators=(",", ":"))

# A7-06: row cap + degrade.
out = serialize(row)
if len(out.encode("utf-8")) > ROW_CAP_BYTES:
    def drop_evidence(value):
        if isinstance(value, dict):
            return {k: drop_evidence(v) for k, v in value.items()
                    if k not in EVIDENCE_KEYS}
        if isinstance(value, list):
            return [drop_evidence(v) for v in value]
        return value
    row = drop_evidence(row)
    row = walk(row, lambda s: cap_string(s, DEGRADED_STRING_CAP))
    row["degraded"] = True
    out = serialize(row)
    if len(out.encode("utf-8")) > ROW_CAP_BYTES:
        # Last resort: keep only required keys, hard-cap strings at 128.
        minimal = {k: row[k] for k in
                   ("unit", "steps", "agents", "close", "ts", "schema")
                   if k in row}
        minimal["degraded"] = True
        minimal["atoms_dropped"] = len(row.get("atoms", []) or [])
        minimal = walk(minimal, lambda s: cap_string(s, 128))
        out = serialize(minimal)

sys.stdout.write(out)
PY
)"

# --- A7-08: append with >> (single writer; see header) + report -----------
printf '%s\n' "$final_row" >> "$ledger"
bytes="$(printf '%s' "$final_row" | wc -c | tr -d '[:space:]')"
echo "${bytes} bytes (excl. newline) APPENDED -> ${ledger}"
