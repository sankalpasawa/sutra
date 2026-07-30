#!/usr/bin/env bash
# workflow-type-match.sh — ADR-026 deterministic matching function v0
#
# Given an intent (all args joined), scan candidate workflow types in CHILD
# scope (company-local skills/commands/playbooks) then PLATFORM scope (the
# plugin skill catalog), score by token overlap, and emit EXACTLY ONE line:
#
#   RESOLUTION=FOLLOW:<name> SCOPE=<child|platform> SCORE=<n>
#   RESOLUTION=CONSTRUCT SCOPE=none SCORE=0
#
# Scoring: lowercase-tokenize intent; drop tokens <= 3 chars;
#   score = 3 * (# distinct intent tokens appearing in candidate name)
#         + 1 * (# distinct intent tokens appearing in candidate description)
# Threshold: score >= 2 -> match. Ties: child scope beats platform, then
# LC_ALL=C alphabetical by name. Deterministic: no network, no date, sorted
# iteration, LC_ALL=C. This is the deterministic FLOOR for the
# workflow-type-resolve skill — skill judgment may override with a reason.
set -euo pipefail
export LC_ALL=C

INTENT="$*"
CHILD_ROOT="${CLAUDE_PROJECT_DIR:-.}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"

python3 - "$INTENT" "$CHILD_ROOT" "$PLUGIN_ROOT" <<'PYEOF'
import glob, os, re, sys

intent, child_root, plugin_root = sys.argv[1], sys.argv[2], sys.argv[3]

def toks(s):
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]

intent_tokens = sorted(set(t for t in toks(intent) if len(t) > 3))

# (glob-pattern, name-kind) — 'dir' = parent dir name, 'file' = basename sans .md
CHILD_PATTERNS = [
    (".claude/skills/*/SKILL.md", "dir"),
    ("skills/*.md", "file"),
    ("holding/skills/*.md", "file"),
    (".claude/commands/*.md", "file"),
    ("commands/*.md", "file"),
]

def candidates():
    out = []
    for pat, kind in CHILD_PATTERNS:
        for p in sorted(glob.glob(os.path.join(child_root, pat))):
            out.append(("child", p, kind))
    if plugin_root:
        plat_glob = os.path.join(plugin_root, "skills/*/SKILL.md")
    else:
        plat_glob = os.path.join(
            child_root, "sutra/marketplace/plugin/skills/*/SKILL.md"
        )
    for p in sorted(glob.glob(plat_glob)):
        out.append(("platform", p, "dir"))
    return out

def name_of(path, kind):
    if kind == "dir":
        return os.path.basename(os.path.dirname(path))
    return os.path.basename(path)[:-3]

def description_of(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    desc_lines = []
    fm_end = 0
    if lines and lines[0].strip() == "---":
        i = 1
        in_desc = False
        while i < len(lines):
            ln = lines[i]
            if ln.strip() == "---":
                fm_end = i + 1
                break
            if in_desc:
                if re.match(r"^\s+\S", ln) and not re.match(
                    r"^[A-Za-z0-9_-]+\s*:", ln
                ):
                    desc_lines.append(ln.strip())
                    i += 1
                    continue
                in_desc = False
            m = re.match(r"^description\s*:\s*(.*)$", ln)
            if m:
                val = m.group(1).strip()
                if val and val not in ("|", ">", "|-", ">-"):
                    desc_lines.append(val)
                else:
                    in_desc = True
            i += 1
    if desc_lines:
        return " ".join(desc_lines)
    # Fallback: first paragraph of body (skip headings + blanks).
    para = []
    for ln in lines[fm_end:]:
        s = ln.strip()
        if not s or s.startswith("#"):
            if para:
                break
            continue
        para.append(s)
    return " ".join(para)

results = []
for scope, path, kind in candidates():
    name = name_of(path, kind)
    ntoks = set(toks(name))
    dtoks = set(toks(description_of(path)))
    score = 0
    for t in intent_tokens:
        if t in ntoks:
            score += 3
        if t in dtoks:
            score += 1
    results.append((score, 0 if scope == "child" else 1, name, scope))

# Highest score; ties -> child first, then LC_ALL=C alphabetical by name.
results.sort(key=lambda r: (-r[0], r[1], r[2]))

if results and results[0][0] >= 2:
    score, _, name, scope = results[0]
    print("RESOLUTION=FOLLOW:%s SCOPE=%s SCORE=%d" % (name, scope, score))
else:
    print("RESOLUTION=CONSTRUCT SCOPE=none SCORE=0")
PYEOF
