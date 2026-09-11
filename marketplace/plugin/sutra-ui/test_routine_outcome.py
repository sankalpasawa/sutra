#!/usr/bin/env python3
"""Outcome-classifier tests for the routine runner.

WHY THIS EXISTS. `claude -p` exits 0 when a tool call is DENIED: refusing a
tool is normal model operation, so the envelope carries is_error=False and
subtype="success" alongside a full prose turn explaining the refusal. The
runner used to read exit 0 as task success, which is how 250 routine runs
across 8 scripts reported success while doing nothing -- one routine's ledger
held 116 "ok" rows that were every one of them denials.

The classifier under test therefore keys off the structured
`permission_denials` list, NOT off an empty result (a denied run's result is
not empty, so an emptiness test catches none of these cases).

The test extracts the branch straight out of the `_RUNNER` string literal in
routines.py, so it exercises the code that actually ships rather than a
re-typed copy that can drift from it.

Run: python3 test_routine_outcome.py
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTINES = os.path.join(HERE, "routines.py")

# Indentation of the classifier block inside the _RUNNER literal.
_BLOCK_INDENT = 20


def load_classifier_block():
    """Return the classifier source, dedented to module level."""
    src = open(ROUTINES).read()
    m = re.search(r"_RUNNER = r'''(.*?)'''", src, re.S)
    if not m:
        raise AssertionError("could not locate the _RUNNER literal")
    runner = m.group(1)
    marker = " " * _BLOCK_INDENT + '_pd = [d for d in'
    if marker not in runner:
        raise AssertionError(
            "classifier block not found in _RUNNER -- if the permission "
            "handling moved, update this test rather than deleting it")
    start = runner.index(marker)
    end = runner.index(" " * 16 + "except ValueError as e:")
    block = runner[start:end]
    pad = " " * _BLOCK_INDENT
    return "\n".join(l[_BLOCK_INDENT:] if l.startswith(pad) else l
                     for l in block.splitlines())


BLOCK = load_classifier_block()
CODE = compile(BLOCK, "<routine-classifier>", "exec")


def classify(envelope, opts):
    """Run the shipped branch with the variable names it expects."""
    ns = {"j": envelope, "o": opts, "outcome": "ok", "detail": None}
    exec(CODE, ns, ns)
    return ns["outcome"], ns["detail"]


DENIED_BASH = {
    "is_error": False, "subtype": "success", "result": "a full prose turn",
    "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1"}],
}
CLEAN = {
    "is_error": False, "subtype": "success", "result": "a full prose turn",
    "permission_denials": [],
}
ERRORED = {
    "is_error": True, "subtype": "error_during_execution", "result": "",
}

CASES = [
    # label, envelope, opts, expected outcome
    ("denied Bash, empty allow-list", DENIED_BASH, {}, "failed"),
    ("denied Bash, Bash bare-allowed", DENIED_BASH,
     {"allowed_tools": ["Bash"]}, "failed"),
    ("denied Bash, Bash scope-allowed", DENIED_BASH,
     {"allowed_tools": ["Bash(git status)"]}, "failed"),
    # Overreach: the routine never declared Bash, so its required work may
    # still have completed through allowed means. Recorded, not fatal.
    ("denied Bash, only Write allowed (overreach)", DENIED_BASH,
     {"allowed_tools": ["Write"]}, "ok"),
    ("no denials, allow-list present", CLEAN,
     {"allowed_tools": ["Write"]}, "ok"),
    ("no denials, no allow-list", CLEAN, {}, "ok"),
    ("is_error wins over denials", ERRORED, {}, "failed"),
]


def newest_denied_capture():
    """A real denied envelope from this machine's run history, if present."""
    pattern = os.path.expanduser("~/.sutra-ui/runs/*/*.out")
    for path in sorted(glob.glob(pattern), reverse=True):
        try:
            cand = json.loads(open(path, errors="replace").read())
        except Exception:
            continue
        if isinstance(cand, dict) and cand.get("permission_denials"):
            return os.path.basename(path), cand
    return None, None


def main():
    passed = failed = 0

    name, real = newest_denied_capture()
    if real is not None:
        cases = [("REAL capture %s" % name, real, {}, "failed")] + CASES
    else:
        print("  note: no real denied capture on this machine "
              "-- synthetic cases only")
        cases = CASES

    for label, envelope, opts, want in cases:
        got, detail = classify(envelope, opts)
        if got == want:
            passed += 1
            print("  PASS %-46s -> %-7s %s" % (label, got, (detail or "")[:40]))
        else:
            failed += 1
            print("  FAIL %-46s -> %-7s (want %s)" % (label, got, want))

    print("  ---- %d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
