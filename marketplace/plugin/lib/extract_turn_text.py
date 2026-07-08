#!/usr/bin/env python3
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/lib/extract_turn_text.py
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-06-29
# VERSION=v1 (2026-06-29: A4 — single source of truth for "current-turn assistant
#            text". Lifted from the duplicated walkers in h-sutra-enforce.sh and
#            blueprint-text-validate.sh so every governance-block validator shares
#            ONE definition of the turn boundary. Drift between copies = the class
#            of bug h-sutra v4/v5/v6 kept re-fixing.)
#
# extract_turn_text.py — given a Claude Code transcript JSONL path, print the
# assistant text emitted in the CURRENT turn.
#
# Turn boundary (must match h-sutra-enforce.sh exactly):
#   current turn = every row AFTER the last HUMAN user row, where a HUMAN user
#   row is role/type == "user" AND NOT isMeta (skill invocations + stop-hook
#   feedback are role:user/isMeta=True) AND whose content is not a tool_result.
#
# Modes (argv[2], default "all"):
#   all   — print ALL assistant text blocks of the current turn, joined by \n.
#           (BLUEPRINT / Input-Routing / Depth / Output-Trace can appear in any
#            assistant message of the turn, including after tool calls.)
#   first — print ONLY the first assistant text block (h-sutra header semantics:
#           the header must be the literal FIRST text of the turn).
#
# Contract: prints the text to stdout and exits 0. On ANY error (missing file,
# unreadable, no rows, no text) prints nothing and exits 0 — callers are
# governance hooks that MUST fail open (a validator that breaks a session is
# worse than the gap it closes, per D40).

import sys
import json


def _content(row):
    msg = row.get("message")
    if isinstance(msg, dict) and msg.get("content") is not None:
        return msg.get("content")
    return row.get("content")


def is_human_user(row):
    if row.get("role") != "user" and row.get("type") != "user":
        return False
    # Skill invocations AND stop-hook feedback are recorded as role:user rows
    # with isMeta=True — they are NOT human turns (h-sutra v6, 2026-06-11).
    if row.get("isMeta") is True:
        return False
    content = _content(row)
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # tool_result rows are role:user too — not a human turn.
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                return False
        return True
    return False


def assistant_texts(rows):
    """Yield each assistant text block emitted after the last human user row."""
    last_user = -1
    for i, r in enumerate(rows):
        if is_human_user(r):
            last_user = i
    for r in rows[last_user + 1:]:
        if r.get("role") != "assistant" and r.get("type") != "assistant":
            continue
        content = _content(r)
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    yield b["text"]
        elif isinstance(content, str) and content:
            yield content


def main():
    if len(sys.argv) < 2:
        return 0
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return 0
    texts = list(assistant_texts(rows))
    if not texts:
        return 0
    if mode == "first":
        sys.stdout.write(texts[0])
    else:
        sys.stdout.write("\n".join(texts))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolute fail-open backstop.
        sys.exit(0)
