"""transcript_ir.py -- one provider-neutral, FULL-FIDELITY reading of a
provider's own transcript, in chat_store's block vocabulary.

WHY THIS IS NOT session_reader's PARSER
session_reader already turns both trees into a common {cwd, branch, messages}
shape (`_parse_transcript` for Claude, `_gemini_transcript` for DeepSeek), and
this module deliberately does not call either. Those two are RENDER parsers and
they are lossy on purpose:

  - `_tool_input_summary` keeps ONE key of a tool's input, capped at 600 chars
    (session_reader.py:593)
  - `_result_text` / `_ds_tool_result_text` cap each tool result at
    _RESULT_CAP = 8000 chars (session_reader.py:590)

Those caps are correct for a panel that has to draw a transcript in a browser.
They are wrong for a replay: the median Claude turn carries 21.9 KB of content
and 93.6% of it is tool I/O, so an 8000-char cap silently drops the substance
of the work while reporting success. A replay that quietly truncates is worse
than one that refuses, because the receiving model cannot tell it happened.

So: same trees, same hard-won parsing rules, no caps. What IS shared is the
knowledge, restated here where it applies:

  - Claude pairs tool_use with a tool_result that arrives LATER, on a
    user-role record, keyed by tool_use_id -- so results are collected across
    the whole file and attached at the end.
  - DeepSeek rewrites a turn's record IN PLACE as its tool calls run (the same
    message id reappears with a longer `toolCalls` array), so LAST WRITE WINS
    by id, and a `$set` line carries a whole snapshot of `messages`.
  - A DeepSeek toolCall carries its own result INLINE (`resultDisplay`, with
    the `result` functionResponse envelope as fallback) -- no id matching.
  - A user record whose text begins with "<" is a synthetic injection
    (session_context), not something the operator typed.

WHAT `thoughts` ACTUALLY IS (measured 2026-09-02, 33 transcripts)
DeepSeek stores reasoning as a LIST OF PER-TOKEN FRAGMENTS, each one a
{subject, description, timestamp} dict whose `description` is a single token.
Every fragment repeats a full ISO timestamp, so 91.2% of that field is
scaffolding: 4.20 MB stored holds 368 KB of text. The fragments are joined
into ONE thinking block per turn here -- storing them per-token would carry
that 11x inflation into every replay and into every budget calculation.

Corrected composition of replayable TEXT, both providers:

    Claude    tool I/O 93.6%   conversation  6.4%   thinking ~0%
    DeepSeek  tool I/O 65.2%   conversation 16.5%   reasoning 18.3%

Both are tool-I/O dominated. An earlier reading of this module's own header
called them "near mirror-images" on the strength of stored bytes; that was
wrong and is corrected here.

Reads:  ~/.claude/projects/**/*.jsonl and ~/.gemini/tmp/*/chats/*.jsonl
Writes: nothing. This module is read-only by contract.
"""
import json
import re
from pathlib import Path

import chat_store
import session_reader

#: Our own replay framing, as it appears when read back OUT of a provider's
#: transcript. A replay is delivered as an ordinary user message, so the
#: receiving provider records it as one -- and the next switch then reads that
#: message as though the operator had typed it.
#:
#: MEASURED IN LIVE TESTING 2026-09-02: claude -> deepseek -> claude -> deepseek
#: produced payloads of 2,936 then 5,644 then 9,928 characters for a
#: four-turn conversation, carrying 2, 4 and 6 fence markers respectively. Each
#: hop wrapped the previous recording whole, framing and all, so by the third
#: the receiving model was told three times that it was taking over and was
#: looking at three fences, two of them dead. Two harms: the payload compounds
#: ~1.8x per hop, and stale closing markers sit INSIDE the live fence, which is
#: exactly the confusion the nonce exists to prevent.
_REPLAY_FENCE = re.compile(r"</?transcript-[0-9a-f]{8,}>")
_REPLAY_PREAMBLE = "You are taking over an in-progress working session"

#: Text this long or longer in a single tool result is kept anyway. There is no
#: cap in this module -- the constant exists so a caller can ASK for the size
#: (see stats) and decide to shed, which is piece 5's job. Shedding a whole
#: block is auditable; truncating one is not.
NO_CAP = None


def _empty(provider):
    return {"provider": provider, "cwd": "", "branch": "", "turns": []}


# ------------------------------------------------------------------ claude --

def _claude_blocks_from_content(content):
    """Every block of one Claude message.content, typed, in order, uncapped.

    `content` is a bare string on simple turns and a block list otherwise.
    tool_result blocks are NOT emitted here: they arrive on a user-role record
    that is not itself a turn, and are attached to the assistant turn that
    called them (see from_claude_file).
    """
    if isinstance(content, str):
        return [chat_store.block_text(content)] if content else []
    out = []
    for b in content if isinstance(content, list) else []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            out.append(chat_store.block_text(b.get("text") or ""))
        elif t == "thinking":
            out.append(chat_store.block_thinking(b.get("thinking") or ""))
        elif t == "tool_use":
            out.append(chat_store.block_tool_use(
                b.get("name") or "", b.get("input"), b.get("id")))
    return out


def _result_text_full(content):
    """A tool_result's text, uncapped. Mirrors session_reader._result_text
    minus the cap, and keeps its "[image]" placeholder so an image result is
    visible as a fact rather than vanishing."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text"):
                parts.append(str(b["text"]))
            elif b.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return ""


def from_claude_file(path):
    """One Claude transcript -> IR. Read-only, never raises on a bad file."""
    ir = _empty("claude")
    results = {}   # tool_use_id -> block_tool_result
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                ir["cwd"] = ir["cwd"] or d.get("cwd", "")
                ir["branch"] = ir["branch"] or d.get("gitBranch", "")
                if d.get("type") not in ("user", "assistant"):
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                ts = d.get("timestamp", "")

                if d.get("type") == "user":
                    # Collect results first: this record may be ONLY results.
                    carried = False
                    for b in content if isinstance(content, list) else []:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            carried = True
                            results[b.get("tool_use_id")] = chat_store.block_tool_result(
                                _result_text_full(b.get("content")),
                                b.get("tool_use_id"), b.get("is_error"))
                    if carried:
                        continue   # a results-only record is not a turn
                    blocks = _claude_blocks_from_content(content)
                    text = "".join(b.get("text", "") for b in blocks
                                   if b["type"] == "text").strip()
                    if not text or text.startswith("<"):
                        continue   # synthetic injection, not an operator turn
                    blocks = _strip_preamble(blocks)
                    ir["turns"].append({"role": "user", "ts": ts, "blocks": blocks})
                else:
                    blocks = _claude_blocks_from_content(content)
                    if blocks:
                        ir["turns"].append({"role": "assistant", "ts": ts,
                                            "blocks": blocks})
    except OSError:
        return ir

    # Results follow their calls, so splice them in only once the file is read.
    # Inserted immediately after the tool_use they answer, which is what the
    # renderer needs to say "this call returned this" without a second lookup.
    for turn in ir["turns"]:
        spliced = []
        for b in turn["blocks"]:
            spliced.append(b)
            if b["type"] == "tool_use":
                r = results.get(b.get("id"))
                if r:
                    spliced.append(r)
        turn["blocks"] = spliced
    return ir


def _strip_preamble(blocks):
    """Drop Sutra's own routing preamble from an operator turn.

    panel.html prepends a PLACEMENT block and joins it to the real message with
    a blank line (session_reader.py:64 documents the same shape for titles).
    That is Sutra's bookkeeping about the turn, not part of the conversation,
    and replaying it to a second vendor's model would present our governance
    scaffolding as something the operator said.
    """
    out = []
    for b in blocks:
        if b["type"] != "text":
            out.append(b)
            continue
        out.append(chat_store.block_text(session_reader._strip_injected(b["text"])))
    return out


# ---------------------------------------------------------------- deepseek --

def _ds_content_text(content):
    """Text of a DeepSeek message.content -- a plain string on model turns, or
    a list of {"text": ...} blocks with NO "type" key on user turns."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def _ds_thoughts_text(thoughts):
    """Per-token reasoning fragments joined into one string.

    `subject` is non-empty on only 18 of 186 thought-bearing turns measured, so
    it is emitted only when present and never used as a separator -- a joiner
    keyed on it would insert noise into 90% of turns.
    """
    if not isinstance(thoughts, list):
        return ""
    parts = []
    for t in thoughts:
        if not isinstance(t, dict):
            continue
        d = t.get("description")
        if isinstance(d, str):
            parts.append(d)
    return "".join(parts)


def _ds_tool_result_full(tc):
    """One toolCalls entry's outcome, uncapped. Same fallback chain as
    session_reader._ds_tool_result_text (resultDisplay string, then its
    fileDiff/output, then the functionResponse envelope) with no cap."""
    rd = tc.get("resultDisplay")
    if isinstance(rd, str) and rd.strip():
        return rd
    if isinstance(rd, dict):
        text = rd.get("fileDiff") or rd.get("output")
        if isinstance(text, str) and text.strip():
            return text
    parts = []
    for r in tc.get("result") or []:
        if not isinstance(r, dict):
            continue
        resp = (r.get("functionResponse") or {}).get("response")
        if not isinstance(resp, dict):
            continue
        val = resp.get("output", resp.get("error", resp.get("result")))
        if isinstance(val, str):
            parts.append(val)
        elif val is not None:
            try:
                parts.append(json.dumps(val))
            except (TypeError, ValueError):
                parts.append(str(val))
    return "\n".join(parts)


def _ds_records(path):
    """Every message record in file order, last write winning per id."""
    order, by_id = [], {}
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if "$set" in d:
                    msgs = d["$set"].get("messages")
                    records = msgs if isinstance(msgs, list) else []
                elif d.get("type") is not None and "content" in d:
                    records = [d]
                else:
                    records = []
                for m in records:
                    if not isinstance(m, dict):
                        continue
                    mid = m.get("id")
                    if mid is None:
                        continue
                    if mid not in by_id:
                        order.append(mid)
                    by_id[mid] = m
    except OSError:
        pass
    return [by_id[i] for i in order]


def from_deepseek_file(path, project_cwd=None):
    """One DeepSeek transcript -> IR. Read-only, never raises on a bad file."""
    ir = _empty("deepseek")
    for m in _ds_records(path):
        mtype = m.get("type")
        ts = m.get("timestamp", "")
        if mtype == "user":
            text = _ds_content_text(m.get("content")).strip()
            if not text or text.startswith("<"):
                continue
            ir["turns"].append({
                "role": "user", "ts": ts,
                "blocks": _strip_preamble([chat_store.block_text(text)])})
        elif mtype == "gemini":
            blocks = []
            think = _ds_thoughts_text(m.get("thoughts"))
            if think:
                blocks.append(chat_store.block_thinking(think))
            text = _ds_content_text(m.get("content"))
            if text.strip():
                blocks.append(chat_store.block_text(text))
            for tc in m.get("toolCalls") or []:
                if not isinstance(tc, dict):
                    continue
                blocks.append(chat_store.block_tool_use(
                    tc.get("name") or "", tc.get("args"), tc.get("id")))
                blocks.append(chat_store.block_tool_result(
                    _ds_tool_result_full(tc), tc.get("id"),
                    tc.get("status") == "error"))
            if blocks:
                ir["turns"].append({"role": "assistant", "ts": ts, "blocks": blocks})

    p = Path(path)
    project = p.parent.parent.name
    ir["cwd"] = (project_cwd or {}).get(project, "")
    return ir


# ------------------------------------------------------------------ facade --

def load(session_id):
    """IR for one provider-native session id, whichever tree it lives in.

    Resolution is delegated to session_reader.resolve_path, which already
    checks Claude's tree by filename and DeepSeek's by header id (the DeepSeek
    filename stem and its session id diverged -- session_reader.py:535). The
    tree the file was found in decides the parser, not the id's shape.
    """
    p = session_reader.resolve_path(session_id)
    if p is None:
        return None
    try:
        rel = Path(p).resolve()
    except OSError:
        return None
    if str(rel).startswith(str(session_reader.GEMINI_ROOT.resolve())):
        return from_deepseek_file(rel, session_reader._gemini_project_cwd_map())
    return from_claude_file(rel)


# ------------------------------------------------------------------- stats --

def is_replay_turn(turn):
    """True when this turn is a replay WE sent, not something the operator said.

    Detected by the framing rather than by any stored flag: the provider's
    transcript is written by the provider, so there is nowhere for us to put a
    flag. Both signals must be present -- a fence marker AND the preamble --
    because either alone could plausibly appear in a conversation that is
    ABOUT this feature (this repo's own design doc quotes both), and dropping a
    genuine operator turn is worse than keeping a stale frame.
    """
    if not isinstance(turn, dict) or turn.get("role") != "user":
        return False
    text = "".join(b.get("text") or "" for b in (turn.get("blocks") or [])
                   if b.get("type") == "text")
    return bool(_REPLAY_FENCE.search(text)) and _REPLAY_PREAMBLE in text


def strip_replays(ir):
    """`ir` without the replay turns previous switches injected into it.

    The history those turns carried is NOT lost: combine() rebuilds it from
    every segment's own transcript instead, which is where it lives natively.
    """
    if not ir:
        return ir
    out = dict(ir)
    out["turns"] = [t for t in (ir.get("turns") or []) if not is_replay_turn(t)]
    return out


def combine(irs, provider=None):
    """Several sessions' IRs merged into one chronological history.

    THIS IS WHAT A SWITCH SHOULD REPLAY. Reading only the immediately-previous
    session was the original design and it was wrong twice over: everything
    older than the last hop existed only inside that session's replay turn (so
    dropping the nesting would have lost it), and a provider that RESUMES its
    own session -- which Claude does, verified live: two segments shared native
    id 7de87ca0 -- had its history delivered twice, once natively and once
    inside the replay.

    Ordered by timestamp, not by segment. A resumed session contributes turns
    from BOTH of its stretches, so segment order would put its later turns
    before another provider's earlier ones. Turns with no timestamp keep their
    relative position via a stable sort.
    """
    turns, seen_cwd, seen_branch = [], "", ""
    for ir in irs or []:
        if not ir:
            continue
        seen_cwd = seen_cwd or ir.get("cwd") or ""
        seen_branch = seen_branch or ir.get("branch") or ""
        turns.extend(strip_replays(ir).get("turns") or [])
    turns.sort(key=lambda t: t.get("ts") or "")
    return {"provider": provider or "", "cwd": seen_cwd,
            "branch": seen_branch, "turns": turns}


def stats(ir):
    """Size and composition of an IR, in characters and blocks.

    Lives here rather than in a caller because three consumers need the same
    arithmetic and must not disagree: piece 5's budget check, the switch's
    cost estimate, and the measurements quoted in
    design/GAME-PLAN-provider-switch.md. Characters, not tokens -- a token
    count needs a tokenizer this module does not own; callers divide.
    """
    chars = {t: 0 for t in chat_store.BLOCK_TYPES}
    counts = {t: 0 for t in chat_store.BLOCK_TYPES}
    for turn in ir.get("turns") or []:
        for b in turn.get("blocks") or []:
            t = b.get("type")
            if t not in chars:
                continue
            counts[t] += 1
            if t == "tool_use":
                try:
                    chars[t] += len(json.dumps(b.get("input") or {}))
                except (TypeError, ValueError):
                    chars[t] += len(str(b.get("input")))
            else:
                chars[t] += len(b.get("text") or "")
    total = sum(chars.values())
    user_turns = sum(1 for t in ir.get("turns") or [] if t.get("role") == "user")
    return {
        "provider": ir.get("provider", ""),
        "turns": len(ir.get("turns") or []),
        "user_turns": user_turns,
        "chars": chars,
        "blocks": counts,
        "total_chars": total,
        "tool_chars": chars["tool_use"] + chars["tool_result"],
        "conversation_chars": chars["text"],
        "reasoning_chars": chars["thinking"],
        "chars_per_user_turn": (total / user_turns) if user_turns else 0,
    }
