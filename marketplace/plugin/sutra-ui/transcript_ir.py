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

Reads:  ~/.claude/projects/**/*.jsonl, ~/.gemini/tmp/*/chats/*.jsonl, and
        $CODEX_HOME/sessions/**/rollout-*.jsonl (added 2026-09-09; the codex
        section below carries its own measurements, and it is the one tree
        whose own truncation policy bounds the no-caps promise above)
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


# ------------------------------------------------------------------- codex --
#
# MEASURED 2026-09-09 against the 13 rollouts in the founder's own
# $CODEX_HOME/sessions (311 records, 0 unparseable lines), written by codex-cli
# 0.153.2.
#
# ONE FILE PER THREAD, APPEND-ONLY, AND THAT IS WHY THIS IS THE SIMPLEST OF THE
# THREE PARSERS. A resumed thread APPENDS to the file it started in -- verified:
# one rollout carries two `task_started` events, one `session_meta`, and the
# second turn writes ONLY its new records. So there is no last-write-wins to do
# (DeepSeek), no cross-file merge, and no re-emission of earlier turns.
#
# THE FILE CARRIES THE CONVERSATION TWICE, AND ONLY ONE COPY IS READ HERE:
#
#   response_item   the API-level history -- message / reasoning /
#                   custom_tool_call / custom_tool_call_output, and the
#                   function_call / web_search_call / tool_search_call
#                   shapes (the full set is _CODEX_ITEM_TYPES)
#   event_msg       a UI-level mirror -- item_completed carrying UserMessage /
#                   AgentMessage / Reasoning / CommandExecution / Extension
#
# `response_item` is a STRICT SUPERSET and is the only stream read. Verified
# per file: custom_tool_call >= CommandExecution in all three tool-bearing
# rollouts (3>=1, 2>=1, 10>=9) and assistant messages == AgentMessage exactly
# (2==2, 2==2, 3==3). The `Extension` items that look like a gap are not one --
# a web search is a custom_tool_call whose script calls `tools.web__run(...)`,
# so it is already in the stream this parser reads. Reading both would
# double-render every message, which is the one bug this comment prevents.
#
# `aggregated_output`, the field the event stream carries tool output in, was
# also MEASURED LOSSY (codex_runtime.py:392 -- a command printing line1/line2/
# line3 came back missing line1). custom_tool_call_output does not go through
# it.
#
# COMPOSITION of replayable text, this provider against the other two:
#
#     Claude    tool I/O 93.6%   conversation  6.4%   thinking   ~0%
#     DeepSeek  tool I/O 65.2%   conversation 16.5%   reasoning 18.3%
#     Codex     tool I/O 98.2%   conversation  1.8%   reasoning   0.0%
#
# Codex is the most tool-dominated of the three, and its reasoning is 0.0%
# because none of it is readable (see _CODEX_ITEM_TYPES).
#
# ONE FIDELITY LIMIT THAT IS NOT THIS MODULE'S TO FIX, stated because the
# module header promises no caps: codex declares
# `truncation_policy {mode: "tokens", limit: 10000}` for every model in its own
# models_cache.json, so tool output is capped BEFORE it is written to the
# rollout. Nothing is truncated here -- the source already was. Largest output
# observed is 40,152 chars.

#: The `payload.type` values on a `response_item` this build TRANSLATES.
#: Everything else is dropped, and the test suite has a canary that fails if a
#: real rollout on this machine ever carries a type outside this set -- because
#: the failure mode of a silent drop here is a replay with NO tool activity in
#: it that still reports success, and tool activity is 98.2% of the content.
#:
#: `reasoning` is recognised and deliberately EMITS NOTHING. Its `summary` is
#: [] in 16/16 records measured, and the only other field is
#: `encrypted_content` -- an opaque base64 blob, not readable thought. There is
#: no Codex analogue of DeepSeek's `thoughts`, so a Codex IR carries no
#: thinking blocks at all.
_CODEX_ITEM_TYPES = ("message", "reasoning",
                     "custom_tool_call", "custom_tool_call_output",
                     # ADDED 2026-09-12, when the canary fired against the 626
                     # rollouts then on disk: the classic function shapes
                     # (4,321 call/output pairs -- the largest rollout on this
                     # machine is all of them and parsed to tool_chars 0), a
                     # web search (94, no call_id) and a tool search (one
                     # pair). Each shape is stated at its branch below.
                     "function_call", "function_call_output",
                     "web_search_call",
                     "tool_search_call", "tool_search_output")

#: Content-item types that carry text, across all three roles. `input_text` on
#: user/developer messages and on tool output, `output_text` on assistant
#: messages; `text` is accepted because it is the cheaper shape a later build
#: is most likely to move to.
_CODEX_TEXT_TYPES = ("input_text", "output_text", "text")


def _codex_text(content):
    """Text of one codex `content` list, uncapped.

    Keeps an "[image]" placeholder for the same reason _result_text_full does:
    an image that vanishes silently is a fact the receiving model cannot know
    it is missing.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for c in content:
        if not isinstance(c, dict):
            continue
        t = c.get("type")
        if t in _CODEX_TEXT_TYPES and isinstance(c.get("text"), str):
            parts.append(c["text"])
        elif t in ("input_image", "output_image", "image"):
            parts.append("[image]")
    return "\n".join(parts)


def _codex_tool_input(raw):
    """A codex tool `input` as the dict the IR's tool_use block requires.

    NOT A COSMETIC CONVERSION. `custom_tool_call.input` is a STRING in 15/15
    records measured -- the source of a small JavaScript program, e.g.

        const r = await tools.exec_command({"cmd":"sed -n '1,240p' …"});

    and chat_store.block_tool_use replaces any non-dict input with `{}`
    (chat_store.py:118). Passing it through raw would therefore drop every tool
    input in the transcript -- 7,118 characters on one measured rollout -- with
    the replay still reporting success. chat_store is NOT relaxed to accept a
    string: it is the durable store shared with Claude and DeepSeek, and the
    narrow fix belongs on the one provider that needs it.

    json.loads is tried FIRST so that a tool whose input is a JSON object (the
    classic `function_call.arguments` shape) keeps its real keys rather than
    being buried under one. When it is not JSON -- which is every case measured
    so far -- the raw string is preserved under the wire field's own name, so a
    reader can trace the value back to the record it came from and this
    function asserts nothing about what the string contains.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        return {"input": raw}
    return {} if raw is None else {"input": raw}


def from_codex_file(path):
    """One Codex rollout -> IR. Read-only, never raises on a bad file."""
    ir = _empty("codex")
    results = {}    # call_id -> block_tool_result
    open_reply = None   # the assistant turn currently accumulating blocks

    def _reply(ts):
        """The open assistant turn, opening one if there is none.

        ASSISTANT ITEMS ARE FOLDED into one turn per operator turn, which is a
        DELIBERATE DIVERGENCE from from_claude_file (one turn per record).
        Codex's response_item stream is per-API-item -- a message, then a tool
        call, then another message -- so one reply that ran ten commands
        arrives as fourteen separate records. Unfolded, replay.py would print
        fourteen "assistant" turn headers for a single answer. Folded, the
        measured shape of a real rollout is [user, assistant] with blocks
        [text, tool_use, tool_result, ..., text, ...] -- which is exactly the
        shape a Claude turn has.
        """
        nonlocal open_reply
        if open_reply is None:
            open_reply = {"role": "assistant", "ts": ts, "blocks": []}
            ir["turns"].append(open_reply)
        return open_reply

    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                payload = d.get("payload")
                if not isinstance(payload, dict):
                    continue
                rec_type, ts = d.get("type"), d.get("timestamp", "")

                if rec_type == "session_meta":
                    # The only place cwd and branch appear. `git` is absent
                    # when the thread ran outside a repository, which is an
                    # ordinary case (3 of 13 measured) and not an error.
                    ir["cwd"] = ir["cwd"] or (payload.get("cwd") or "")
                    git = payload.get("git")
                    if isinstance(git, dict):
                        ir["branch"] = ir["branch"] or (git.get("branch") or "")
                    continue

                if rec_type != "response_item":
                    continue    # event_msg and the rest -- see the section header
                item = payload.get("type")
                if item not in _CODEX_ITEM_TYPES:
                    continue
                if item == "reasoning":
                    continue    # nothing readable in it; never encrypted_content

                if item == "message":
                    role = payload.get("role")
                    if role == "user":
                        # An operator turn ENDS the assistant turn before it,
                        # so the next reply cannot absorb blocks from this one.
                        open_reply = None
                        text = _codex_text(payload.get("content")).strip()
                        if not text or text.startswith("<"):
                            continue   # synthetic injection, not typed input
                        ir["turns"].append({
                            "role": "user", "ts": ts,
                            "blocks": _strip_preamble(
                                [chat_store.block_text(text)])})
                    elif role == "assistant":
                        # `phase` is final_answer or commentary; both are real
                        # assistant text and neither is treated specially.
                        text = _codex_text(payload.get("content"))
                        if text.strip():
                            _reply(ts)["blocks"].append(
                                chat_store.block_text(text))
                    # role == "developer" IS DROPPED BY ROLE, and the role test
                    # is why -- the `<`-prefix rule the two other parsers use
                    # is NOT sufficient here. Codex writes its own system
                    # instructions as developer messages (34 of them measured),
                    # and while most open with a tag like <skills_instructions>,
                    # one measured record begins:
                    #
                    #     You are `/root`, the primary agent in a team of …
                    #
                    # A parser that treated every non-assistant message as an
                    # operator turn would replay CODEX'S OWN SYSTEM PROMPT to
                    # the next vendor's model as something the operator said.
                    continue

                if item in ("custom_tool_call", "function_call",
                            "tool_search_call"):
                    # Three call shapes, one block. custom_tool_call carries
                    # its program in `input`; function_call carries `name` and
                    # `arguments` (a JSON string, 4,321/4,321 measured);
                    # tool_search_call carries `arguments` and no name, so it
                    # is named by its type. All three pair with an output
                    # record by call_id.
                    if item == "custom_tool_call":
                        name, raw = payload.get("name"), payload.get("input")
                    elif item == "function_call":
                        name, raw = payload.get("name"), payload.get("arguments")
                    else:
                        name, raw = "tool_search", payload.get("arguments")
                    _reply(ts)["blocks"].append(chat_store.block_tool_use(
                        name or "", _codex_tool_input(raw),
                        payload.get("call_id")))
                    continue

                if item == "web_search_call":
                    # {status, action: {type: "search", query, queries}} and
                    # NO call_id (94/94 measured): there is no output record
                    # to pair, so this is a tool_use with id None and nothing
                    # is ever spliced after it -- see the id guard below.
                    action = payload.get("action")
                    _reply(ts)["blocks"].append(chat_store.block_tool_use(
                        "web_search",
                        action if isinstance(action, dict) else {}, None))
                    continue

                # custom_tool_call_output. Collected rather than appended: the
                # output arrives on its own later record, exactly as a Claude
                # tool_result does, and is spliced after its call once the
                # whole file is read. 15/15 measured calls paired cleanly by
                # call_id, with 0 orphans in either direction.
                #
                # TESTED EXPLICITLY RATHER THAN BY ELIMINATION, and that is the
                # whole point of this guard. This used to be the bare tail of
                # the chain -- "anything recognised that got this far is an
                # output" -- which is true of the four types in
                # _CODEX_ITEM_TYPES today and false of the next one added to
                # it. And the next one WILL be added: the canary in
                # test_transcript_ir tells whoever hits an unmeasured type to
                # put it in that tuple. Doing so without a branch here sent the
                # record down this path, where `results[call_id] = ...`
                # OVERWROTE the real tool result for that call -- measured, a
                # `web_search` record replaced a command's output with an empty
                # string. Silent, and in the 98.2%-of-content path.
                if item in ("custom_tool_call_output", "function_call_output",
                            "tool_search_output"):
                    cid = payload.get("call_id")
                    if not cid:
                        # An output with no call cannot be spliced anywhere.
                        # NEVER results[None]: the splice below looks results
                        # up by the call's id, and a web_search_call's id IS
                        # None, so a None key would attach this output after
                        # every search in the file.
                        continue
                    if item == "tool_search_output":
                        # {tools: [...]} -- a list of namespaces, not text.
                        text = json.dumps(payload.get("tools"), ensure_ascii=False)
                    else:
                        # a content list (custom) or a plain string (function)
                        text = _codex_text(payload.get("output"))
                    results[cid] = chat_store.block_tool_result(
                        text, cid,
                        # ALWAYS False, and this is a measurement rather than
                        # an oversight: custom_tool_call_output carries NO
                        # status field at all (15/15 -- its keys are exactly
                        # call_id, id, output, type and the passthrough
                        # envelope). The call's own `status` is "completed" for
                        # every record including the ones whose command failed,
                        # so it says nothing about the outcome either. A failed
                        # command is therefore indistinguishable from a
                        # successful one at the record level, and replay.py
                        # will render it "-> returned:". The failure is still
                        # visible in the output TEXT; inferring it from that
                        # prose would be guessing, which is what the rest of
                        # this codebase refuses to do about a provider's wire
                        # format.
                        False)
    except OSError:
        return ir

    # Results follow their calls, so splice them in only once the file is read
    # -- identical policy to from_claude_file, for the identical reason. The
    # id guard is codex-only: a web_search_call is a tool_use with id None.
    for turn in ir["turns"]:
        spliced = []
        for b in turn["blocks"]:
            spliced.append(b)
            if b["type"] == "tool_use" and b.get("id"):
                r = results.get(b["id"])
                if r:
                    spliced.append(r)
        turn["blocks"] = spliced
    return ir


# ------------------------------------------------------------------ facade --

def load(session_id):
    """IR for one provider-native session id, whichever tree it lives in.

    Resolution is delegated to session_reader.resolve_path, which already
    checks Claude's tree by filename and DeepSeek's by header id (the DeepSeek
    filename stem and its session id diverged -- session_reader.py:535). The
    tree the file was found in decides the parser, not the id's shape.

    CODEX IS TRIED ONLY AFTER BOTH OF THOSE MISS, and the ordering is the whole
    safety argument for this function. resolve_path is called first and
    unmodified, so any id that resolves today takes byte-identical code and
    neither existing provider's resolution changes shape; the codex lookup sits
    on the branch that used to `return None` outright. It is also a separate
    function rather than a third arm of resolve_path, because resolve_path is
    shared with append_title and relocate -- see session_reader.
    codex_resolve_path for what folding it in would have done to a rollout.
    """
    p = session_reader.resolve_path(session_id)
    codex = None
    if p is None:
        codex = session_reader.codex_resolve_path(session_id)
        if codex is None:
            return None
        p = codex
    try:
        rel = Path(p).resolve()
    except OSError:
        return None
    if codex is not None:
        return from_codex_file(rel)
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
