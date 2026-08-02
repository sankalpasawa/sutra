"""Read-only tail of Sutra governance JSONL logs. Stdlib only.

Single writer rule: this module NEVER writes to a governance file. It only reads.
Base dir is the repo root by default, override with SUTRA_REPO_ROOT for testing
against a fixture (so the real logs stay untouched).
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

# repo root = two levels up from this file (holding/sutra-ui/log_reader.py)
BASE = Path(os.environ.get("SUTRA_REPO_ROOT", Path(__file__).resolve().parents[2]))

# Whitelist: source name -> repo-relative path. NEVER accept a raw path (traversal guard).
SOURCES: Dict[str, str] = {
    "turns": ".sutra/h-sutra.jsonl",
    "violations": ".enforcement/governance-violations.jsonl",
    "audit": ".enforcement/h-sutra-audit.jsonl",
    "hooks": "holding/hooks/hook-log.jsonl",
}


def resolve(source: str) -> Path:
    """Map a whitelisted source name to its absolute path. KeyError if unknown."""
    if source not in SOURCES:
        raise KeyError(source)
    return BASE / SOURCES[source]


def normalize_ts(row: dict) -> dict:
    """Logs mix ISO strings and unix ints — render uniform ISO-UTC."""
    ts = row.get("ts")
    if isinstance(ts, (int, float)):
        row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    return row


def parse(line: str) -> Optional[dict]:
    """Parse one JSONL line. Returns None for blank/partial/corrupt lines (never raises)."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    return normalize_ts(obj) if isinstance(obj, dict) else None


def read_tail(path: Path, n: int = 50) -> List[dict]:
    """Last n parsed rows, read from the END of the file (never loads the whole file).

    hook-log.jsonl is multi-MB, so we seek backward and read only a window.
    """
    if not path.exists():
        return []
    size = path.stat().st_size
    if size == 0:
        return []
    avg = 400  # rough bytes/line; window = (n+buffer) * avg, capped at file size
    block = min(size, (n + 5) * avg)
    with path.open("rb") as f:
        f.seek(max(0, size - block))
        data = f.read()
    parts = data.split(b"\n")
    if size > block and parts:
        parts = parts[1:]  # first slice is likely a partial line — drop it
    rows = []
    for raw in parts:
        row = parse(raw.decode("utf-8", "replace"))
        if row is not None:
            rows.append(row)
    return rows[-n:]
