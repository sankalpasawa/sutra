"""Versions, as a platform product.

Founder, 2026-09-28: "versioning is with respect to those particular artifacts... It's not a centralized thing; it's
dependent on a verticalized feature." A version belongs to the thing that has versions, and lives in that thing's own
folder. This module is the common part: the shape of a version and the operations on it. It knows no artifact by name.
A vertical thing deploys it by handing over its folder.

A version row: v, at, made_from (the versions it was made from), run (or the stamp, or the owner), check, note.
Its files sit beside the row, under v<n>/.
"""
from pathlib import Path

import record


def rows(base):
    """Every version of the thing whose folder this is, oldest first."""
    return record.read(Path(base) / "versions.json", [])


def latest(base, passed=False):
    out = rows(base)
    if passed:
        out = [r for r in out if (r.get("check") or {}).get("ok")]
    return out[-1] if out else None


def vdir(base, v):
    return Path(base) / ("v%d" % int(v))


def files(base, v):
    """The files of one version, by their relative path."""
    root = vdir(base, v)
    out = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
    return out


def add(base, files_, made_from, run, check, at, note="", lock=None):
    """The next version of the thing: its files written under v<n>/, then its row appended, under the thing's lock."""
    def _do():
        out = rows(base)
        v = (out[-1]["v"] + 1) if out else 1
        root = vdir(base, v)
        root.mkdir(parents=True, exist_ok=True)
        for name, text in files_.items():
            p = (root / name).resolve()
            if not str(p).startswith(str(root.resolve())):
                raise ValueError("a file outside its version: %r" % name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        row = {"v": v, "at": at, "made_from": made_from, "run": run, "check": check, "note": note}
        out.append(row)
        record.write(Path(base) / "versions.json", out)
        return row
    if lock is None:
        return _do()
    with lock:
        return _do()
