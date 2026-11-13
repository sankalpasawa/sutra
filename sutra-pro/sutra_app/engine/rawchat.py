"""The Raw AI chat of a run: Sutra's own reader of `calls.jsonl` and `agent_live.json` for the debugger view (not a J2 file).

    call_list(run_dir, offset=0, limit=DEFAULT_LIMIT, q="")   {total, matched, offset, limit, calls: [row]}: every AI call of the run in
                                 file order, each row the call's metadata and a short preview of its prompt and reply, never the full text
                                 (the full call is `/api/call?id=`). `q` keeps the calls whose function, model, system prompt, prompt or
                                 raw reply hold it (case-insensitive); `matched` counts them, `total` counts every call.
    live_tail(run_dir)           {at, agents: {name: {call, since, text, tool, tools}}}: what each working agent has written so far
                                 (`agent_live.json`, D133), the text capped to LIVE_TEXT_CHARS; {} agents when there is no live file.

Both read the folder only; a missing folder, a torn line or a file that is not ours reads as empty. The route adapter
(`api/rawchat.py`) redacts what these return, as every engine route does.
"""
import json
import os
from typing import Any, Optional

__all__ = ["call_list", "live_tail", "row_of", "DEFAULT_LIMIT", "MAX_LIMIT", "PREVIEW_CHARS", "LIVE_TEXT_CHARS", "Q_CHARS"]

DEFAULT_LIMIT = 200       # rows per page when the client does not ask
MAX_LIMIT = 500           # the most rows one answer carries
PREVIEW_CHARS = 160       # the prompt and reply previews of a row
REASON_CHARS = 240        # the call's own reason line, cut
LIVE_TEXT_CHARS = 20000   # the most of one agent's live text sent
Q_CHARS = 200             # the longest search text taken
CALLS_FILE = "calls.jsonl"
LIVE_FILE = "agent_live.json"
LIVE_SCHEMA = "agent-live/1"


def _short(value: Any, n: int) -> str:
    text = value if isinstance(value, str) else ""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _num(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def row_of(rec: dict) -> dict:
    """One call as a list row: metadata and previews, no full text."""
    tokens = rec.get("tokens") if isinstance(rec.get("tokens"), dict) else None
    chars = rec.get("chars") if isinstance(rec.get("chars"), dict) else {}
    system, prompt, raw = (rec.get(k) if isinstance(rec.get(k), str) else "" for k in ("system", "prompt", "raw"))
    return {
        "id": rec.get("id"),
        "t": rec.get("t") if isinstance(rec.get("t"), str) else None,
        "seconds": _num(rec.get("seconds")),
        "fn": rec.get("fn") if isinstance(rec.get("fn"), str) else "",
        "step": rec.get("step"),
        "cycle": rec.get("cycle"),
        "atom": rec.get("atom") if isinstance(rec.get("atom"), str) else None,
        "model": rec.get("model") if isinstance(rec.get("model"), str) else None,
        "provider": rec.get("provider") if isinstance(rec.get("provider"), str) else None,
        "usd": _num(rec.get("usd")),
        "tokens": {"input": _num(tokens.get("input")), "output": _num(tokens.get("output"))} if tokens else None,
        "chars": {"system": len(system), "prompt": len(prompt), "reply": len(raw),
                  "total": _num(chars.get("prompt")) or len(system) + len(prompt)},
        "reason": _short(rec.get("reason"), REASON_CHARS) or None,
        "prompt_preview": _short(prompt, PREVIEW_CHARS),
        "reply_preview": _short(raw, PREVIEW_CHARS),
    }


def _matches(rec: dict, needle: str) -> bool:
    for k in ("fn", "model", "atom", "system", "prompt", "raw"):
        v = rec.get(k)
        if isinstance(v, str) and needle in v.lower():
            return True
    return False


def _clamp(value: Any, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def call_list(run_dir: Optional[str], offset: Any = 0, limit: Any = DEFAULT_LIMIT, q: Any = "") -> dict:
    offset = _clamp(offset, 0, 0, 10 ** 9)
    limit = _clamp(limit, DEFAULT_LIMIT, 1, MAX_LIMIT)
    needle = (q if isinstance(q, str) else "").strip().lower()[:Q_CHARS]
    total = matched = 0
    rows: list = []
    path = os.path.join(run_dir, CALLS_FILE) if run_dir else None
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                total += 1
                if needle and not _matches(rec, needle):
                    continue
                if offset <= matched < offset + limit:
                    rows.append(row_of(rec))
                matched += 1
    return {"total": total, "matched": matched, "offset": offset, "limit": limit, "q": needle, "calls": rows}


def live_tail(run_dir: Optional[str]) -> dict:
    empty = {"at": None, "agents": {}}
    if not run_dir:
        return empty
    try:
        with open(os.path.join(run_dir, LIVE_FILE), encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return empty
    if not isinstance(doc, dict) or doc.get("schema") != LIVE_SCHEMA or not isinstance(doc.get("agents"), dict):
        return empty
    agents = {}
    for name, entry in list(doc["agents"].items())[:64]:
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        text = entry.get("text") if isinstance(entry.get("text"), str) else ""
        agents[name] = {"call": entry.get("call"), "since": _num(entry.get("since")),
                        "text": text[-LIVE_TEXT_CHARS:], "tool": entry.get("tool") if isinstance(entry.get("tool"), str) else "",
                        "tools": _num(entry.get("tools")) or 0}
    return {"at": _num(doc.get("at")), "agents": agents}
