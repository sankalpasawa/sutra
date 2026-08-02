#!/usr/bin/env bash
# placement-eval.sh — F3.12: measured classifier precision (ADR-028 / OQ-028-2).
#
#   bash tests/placement-eval.sh [target-tree]
#
# Two tiers, labelled honestly for what each can and cannot claim:
#
#   TIER 1 — path evidence (CONSISTENCY, partly circular). The registry was
#   derived from directory structure and the query carries the file path, so
#   this cannot prove semantic understanding. It DOES catch regressions in the
#   adjacency signal, path normalisation, and floor behaviour — the exact
#   mechanisms that broke twice during dogfooding.
#
#   TIER 2 — utterance only (GENUINE generalisation). 20 hand-labelled natural
#   utterances that describe work without quoting a file path. This is the
#   number that answers deepseek's "expect 50-65% top-1" prediction.
#
# Exit 0 always (this measures; it does not gate). Prints both figures.
set -u

PLUGIN="$(cd "$(dirname "$0")/.." && pwd)"
ENG="$PLUGIN/lib/placement_engine.py"
TARGET="${1:-$PLUGIN}"

SB=$(mktemp -d); trap 'rm -rf "$SB"' EXIT
export SUTRA_NATIVE_HOME="$SB/user-kit"
export PLACEMENT_ROOT_NAME="Asawa Inc."

python3 "$ENG" scan "$TARGET" > "$SB/scan.json" 2>&1
DOMAINS=$(python3 "$ENG" stats | jq -r '.domains')
printf '\n=== PLACEMENT CLASSIFIER EVAL (registry: %s domains from %s) ===\n' "$DOMAINS" "$TARGET"

# ---- TIER 1: path-evidence consistency over every scanned file -------------
python3 - "$ENG" "$TARGET" <<'PY'
import json, os, subprocess, sys
eng, root = sys.argv[1], sys.argv[2]
SKIP = {".git","node_modules",".claude",".enforcement","__pycache__"}
cases = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
    rel = os.path.relpath(dirpath, root)
    if rel == ".":
        continue                      # root-level files have no area label
    parts = rel.split(os.sep)[:2]
    expected = parts[-1].replace("-", " ").replace("_", " ").title()
    for fn in filenames:
        if not fn.startswith("."):
            cases.append((os.path.join(rel, fn), expected))
cases = cases[:200]                   # cap runtime; deterministic order
hit = floor = miss = 0
for relpath, expected in cases:
    out = subprocess.run(
        ["python3", eng, "classify", "edit this file", relpath],
        capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
    except ValueError:
        miss += 1; continue
    if not d.get("resolved"):
        miss += 1; continue
    leaf = (d.get("chain") or [{}])[-1].get("name", "")
    chain_names = [c.get("name","") for c in (d.get("chain") or [])]
    if leaf == expected or expected in chain_names:
        hit += 1
    elif d.get("mode") == "floor":
        floor += 1
    else:
        miss += 1
n = len(cases)
print("TIER 1 — path evidence (consistency, partly circular):")
print("  cases=%d  correct=%d (%.1f%%)  floor-held=%d (%.1f%%)  wrong=%d (%.1f%%)"
      % (n, hit, 100.0*hit/n, floor, 100.0*floor/n, miss, 100.0*miss/n))
PY

# ---- TIER 2: utterance-only, hand-labelled ---------------------------------
python3 - "$ENG" <<'PY'
import json, subprocess, sys
eng = sys.argv[1]
# Natural phrasings that do NOT quote a path. Expected = domain name in chain.
CASES = [
    ("run the unit test suite",                        "Unit"),
    ("add an integration test for onboarding",         "Integration"),
    ("write a new pretool hook for depth checking",    "Hooks"),
    ("the stop hook is firing twice",                  "Hooks"),
    ("update the flow skill instructions",             "Flow"),
    ("teach the caveman skill new words",              "Caveman"),
    ("the deepseek reviewer needs a longer timeout",   "Deepseek"),
    ("tune the blueprint skill wording",               "Blueprint"),
    ("refactor the render library helper",             "Lib"),
    ("bump the connector manifest version",            "Connectors"),
    ("fix the slack connector script",                 "Connectors"),
    ("the engines directory needs a new engine doc",   "Engines"),
    ("update the os config",                           "Os"),
    ("add a command for status",                       "Commands"),
    ("ship a new bin utility",                         "Bin"),
    ("polish the sutra ui static assets",              "Sutra Ui"),
    ("archive an old script",                          "Scripts"),
    ("improve the lens skill axes",                    "Lens"),
    ("document the human sutra header",                "Human Sutra"),
    ("adjust readability gate formatting rules",       "Readability Gate"),
]
hit = floor = wrong = unresolved = 0
rows = []
for utt, expected in CASES:
    out = subprocess.run(["python3", eng, "classify", utt],
                         capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
    except ValueError:
        unresolved += 1; rows.append((utt, expected, "PARSE-ERR", "-")); continue
    if not d.get("resolved"):
        unresolved += 1; rows.append((utt, expected, "[no-match]", "-")); continue
    chain = [c.get("name","") for c in (d.get("chain") or [])]
    leaf = chain[-1] if chain else ""
    conf = d.get("confidence")
    if expected in chain:
        if d.get("mode") == "floor" and leaf != expected:
            floor += 1; rows.append((utt, expected, "floor@"+leaf, conf))
        else:
            hit += 1;  rows.append((utt, expected, "OK "+leaf, conf))
    else:
        if d.get("mode") == "floor":
            floor += 1; rows.append((utt, expected, "floor@"+leaf, conf))
        else:
            wrong += 1; rows.append((utt, expected, "WRONG "+leaf, conf))
n = len(CASES)
print("\nTIER 2 — utterance only (genuine generalisation, hand-labelled):")
for utt, exp, res, conf in rows:
    print("  %-46s want=%-16s got=%-22s conf=%s" % ('"'+utt+'"', exp, res, conf))
print("  cases=%d  correct=%d (%.1f%%)  floor-held=%d  wrong=%d  unresolved=%d"
      % (n, hit, 100.0*hit/n, floor, wrong, unresolved))
print("\n  (deepseek predicted 50-65%% top-1 for bag-of-words; the figure above is the measurement)")
PY
