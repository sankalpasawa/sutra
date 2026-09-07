"""make_diff.py — before and after, in a shape a browser can render without thinking.

The screen needs to show a user what an edit did, and the honest answer is usually "one
paragraph, and nothing else". Rendering 60 unchanged lines to prove that buries the point,
so a long run of unchanged lines collapses into a single marker carrying its count, which
the screen shows as a folded "42 unchanged lines" row.

Line-based rather than word-based, because the unit the user edits is a block and a
line-level diff lines up with what they are looking at.
"""
import difflib

# Unchanged runs up to this length stay visible as context. Longer ones fold.
CONTEXT_RUN = 3


def make_diff(old, new):
    """Returns a flat list of {"type": "same"|"add"|"remove", "text": str} entries, with
    {"type": "context", "count": N} standing in for a folded run of unchanged lines."""
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    out = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            run = old_lines[i1:i2]
            if len(run) > CONTEXT_RUN:
                out.append({"type": "context", "count": len(run)})
            else:
                out.extend({"type": "same", "text": line} for line in run)
            continue
        if tag in ("delete", "replace"):
            out.extend({"type": "remove", "text": line} for line in old_lines[i1:i2])
        if tag in ("insert", "replace"):
            out.extend({"type": "add", "text": line} for line in new_lines[j1:j2])
    return out
