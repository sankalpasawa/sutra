"""The record: rows, as a platform product.

Founder, 2026-09-28: "Record is also based on those things. There is a lot of commonality between them, so it's a
platform product getting deployed into each of these things." This module is the common part. It knows no artifact, no
engine and no department by name: a vertical thing (an engine's steps, a department's board, its runs) deploys it by
naming the file its rows live in. Nothing files a row by code of its own.

Two file shapes, both under the thing's own folder:
  a journal   one JSON object a line, appended, never rewritten   (steps.jsonl, board.jsonl)
  a document  one JSON value, written whole and atomically         (runs.json, asks.json, versions.json)
"""
import json
import os
from pathlib import Path


def read(p, default):
    """A document, or the default when it is not there or not readable."""
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:  # noqa: BLE001 -- a torn document reads as absent, never fatal
        return default


def write(p, obj):
    """A document, whole: written beside itself and moved into place, so a reader never sees half of it."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def lines(p):
    """A journal, oldest first. A line torn by a closed app is skipped."""
    try:
        text = Path(p).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return out


def append(p, row, lock=None):
    """One row onto a journal, under the thing's lock when it has one."""
    def _do():
        p2 = Path(p)
        p2.parent.mkdir(parents=True, exist_ok=True)
        with open(p2, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row
    if lock is None:
        return _do()
    with lock:
        return _do()
