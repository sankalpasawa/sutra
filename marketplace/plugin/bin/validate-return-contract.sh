#!/usr/bin/env bash
# validate-return-contract.sh -- Work-Atom return-contract validator (D62 / ADR-029).
#
# Contract of record: skills/flow/references/return-contract.schema.json.
# This script hardcodes the same rules (no external schema engine), with two
# deliberate relaxations pinned by the executable fixtures in
# tests/flow-orchestrator/ (f1-good-contract.json is the acceptance case):
#   R1. "verify" may be EITHER a non-empty string (the runnable check command)
#       OR an object {check, result[, detail]} with result in PASS|FAIL|WAIVED.
#   R2. Extra keys are tolerated (f1 carries schema_version/duration_s/learned).
#
# Enforced rules:
#   - input parses as a JSON object
#   - required: atom_id, status, result, verify, confidence, trace_id
#   - status     in {done, failed, blocked, partial}
#   - confidence in {high, moderate, low}
#   - result   string, <= 4000 chars (transcript-shaped walls of prose rejected)
#   - evidence string, <= 2000 chars (when present)
#   - note     string, <=  500 chars (when present)
#   - risks    array,  <=   10 items (when present)
#
# Input: stdin, or a single positional file argument.
# Output: "VALID" (exit 0) or "INVALID: <reasons>" (exit 1).
# Usage errors (no input / unreadable file) exit 2.

set -u
export LC_ALL=C

if [ $# -gt 1 ]; then
  echo "usage: $(basename "$0") [contract.json]  (or pipe JSON via stdin)" >&2
  exit 2
fi

if [ $# -eq 1 ]; then
  [ -r "$1" ] || { echo "ERROR: cannot read file '$1'" >&2; exit 2; }
  PAYLOAD="$(cat "$1")"
else
  if [ -t 0 ]; then
    echo "usage: $(basename "$0") [contract.json]  (or pipe JSON via stdin)" >&2
    exit 2
  fi
  PAYLOAD="$(cat)"
fi

if [ -z "$PAYLOAD" ]; then
  echo "ERROR: empty input -- expected one JSON return contract" >&2
  exit 2
fi

export PAYLOAD
python3 - <<'PY'
import json, os, sys

STATUS_ENUM = {"done", "failed", "blocked", "partial"}
CONFIDENCE_ENUM = {"high", "moderate", "low"}
VERIFY_RESULT_ENUM = {"PASS", "FAIL", "WAIVED"}
REQUIRED = ["atom_id", "status", "result", "verify", "confidence", "trace_id"]

errors = []

try:
    row = json.loads(os.environ["PAYLOAD"])
except json.JSONDecodeError as e:
    print("INVALID: input is not valid JSON (%s)" % e)
    sys.exit(1)

if not isinstance(row, dict):
    print("INVALID: top level must be a JSON object")
    sys.exit(1)

for key in REQUIRED:
    if key not in row:
        errors.append("missing required field '%s'" % key)

if "atom_id" in row and not isinstance(row["atom_id"], str):
    errors.append("'atom_id' must be a string")

if "trace_id" in row and not isinstance(row["trace_id"], str):
    errors.append("'trace_id' must be a string")

if "status" in row:
    if not isinstance(row["status"], str) or row["status"] not in STATUS_ENUM:
        errors.append("'status' must be one of %s (got %r)"
                      % (sorted(STATUS_ENUM), row["status"]))

if "confidence" in row:
    if (not isinstance(row["confidence"], str)
            or row["confidence"] not in CONFIDENCE_ENUM):
        errors.append("'confidence' must be one of %s (got %r)"
                      % (sorted(CONFIDENCE_ENUM), row["confidence"]))

if "result" in row:
    if not isinstance(row["result"], str):
        errors.append("'result' must be a string")
    elif len(row["result"]) > 4000:
        errors.append("'result' exceeds 4000-char cap (%d chars) -- "
                      "bounded summary required, not a transcript"
                      % len(row["result"]))

if "verify" in row:
    v = row["verify"]
    if isinstance(v, str):
        if not v.strip():
            errors.append("'verify' string must be a non-empty runnable check")
    elif isinstance(v, dict):
        if "check" not in v or not isinstance(v.get("check"), str):
            errors.append("'verify.check' (string) is required in object form")
        r = v.get("result")
        if r not in VERIFY_RESULT_ENUM:
            errors.append("'verify.result' must be one of %s (got %r)"
                          % (sorted(VERIFY_RESULT_ENUM), r))
    else:
        errors.append("'verify' must be a string (runnable check) or an "
                      "object {check, result}")

if "evidence" in row:
    if not isinstance(row["evidence"], str):
        errors.append("'evidence' must be a string")
    elif len(row["evidence"]) > 2000:
        errors.append("'evidence' exceeds 2000-char cap (%d chars)"
                      % len(row["evidence"]))

if "note" in row:
    if not isinstance(row["note"], str):
        errors.append("'note' must be a string")
    elif len(row["note"]) > 500:
        errors.append("'note' exceeds 500-char cap (%d chars)"
                      % len(row["note"]))

if "risks" in row:
    if not isinstance(row["risks"], list):
        errors.append("'risks' must be an array")
    elif len(row["risks"]) > 10:
        errors.append("'risks' exceeds 10-item cap (%d items)"
                      % len(row["risks"]))

if "files_touched" in row and not isinstance(row["files_touched"], list):
    errors.append("'files_touched' must be an array")

if errors:
    print("INVALID: " + "; ".join(errors))
    sys.exit(1)

print("VALID")
sys.exit(0)
PY
