"""Blank the INPUTS of the tool calls in a node's run record when the run ends (R11, D345): J2 keeps, for each builder call, the tool calls the model program made, with their inputs cut to a few hundred
characters (`tools.calls[*].input` in `calls.jsonl`, and the same record in `snapshot.json`). An input can be a command or a URL that holds something private, and nothing scrubs it. For a run that is a
node of a project (flag on only) the host replaces each input with an empty text at the end and keeps the number, the name and the result of the call. The vendored engine is not touched: this is done by the
host, on the files, after J2 has finished with them. Best effort: a file that cannot be read or written is left as it was and the run still ends."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sutra_app import oslayer

__all__ = ["blank_tool_inputs"]


def _blank(record: Any) -> int:
    """Empty the `input` of every call of one call record (`record["tools"]["calls"]`); returns how many were emptied."""
    tools = record.get("tools") if isinstance(record, dict) else None
    calls = tools.get("calls") if isinstance(tools, dict) else None
    done = 0
    for call in calls if isinstance(calls, list) else []:
        if isinstance(call, dict) and call.get("input") not in (None, ""):
            call["input"] = ""
            done += 1
    return done


def _replace(path: Path, text: str) -> None:
    temp = oslayer.temp_path(path)
    fd = os.open(temp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    oslayer.replace(temp, path)


def blank_tool_inputs(run_dir: Path | str) -> int:
    """Blank the tool inputs in `calls.jsonl` and `snapshot.json` of `run_dir`; returns how many were blanked (0 when there were none or a file could not be handled)."""
    root = Path(run_dir)
    total = 0
    calls = root / "calls.jsonl"
    try:
        if calls.is_file() and not calls.is_symlink():
            out: list[str] = []
            changed = 0
            with open(calls, encoding="utf-8") as handle:
                for line in handle:
                    if '"tools"' in line and '"input"' in line:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            out.append(line)
                            continue
                        n = _blank(record)
                        if n:
                            changed += n
                            line = json.dumps(record, ensure_ascii=False) + "\n"
                    out.append(line)
            if changed:
                _replace(calls, "".join(out))
                total += changed
    except (OSError, UnicodeError):
        pass
    snap = root / "snapshot.json"
    try:
        if snap.is_file() and not snap.is_symlink():
            document = json.loads(snap.read_text(encoding="utf-8"))
            changed = sum(_blank(record) for record in (document.get("call_log") if isinstance(document, dict) else None) or [])
            if changed:
                _replace(snap, json.dumps(document, ensure_ascii=False))
                total += changed
    except (OSError, ValueError, UnicodeError):
        pass
    return total
