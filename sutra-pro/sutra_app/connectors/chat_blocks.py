"""`BlockAccumulator`: the single owner of a chat turn's block structure (streaming design D218, work package STR-5).

A provider turn is a sequence of content blocks (text, thinking, tool calls). Three places used to need that structure and were about to each keep
their own: `ChatPort` (the typed blocks stored with a reply), the live turn (the events a page draws), and the fold of a long turn. This module is the
one implementation. It is pure: no IO, no clock, no threads of its own; the caller feeds it `ConnectorEvent`s and gets `BlockEvent`s back.

    acc = BlockAccumulator(folder=..., provider="claude", redact=services.redact, text_filter=holdback_factory(services.redact))
    for event in connector_events:
        for out in acc.feed(event):            # BlockEvent(kind, block_id, data): start | delta | update | end
            publish(out)
    acc.restart(reason, provider)              # the router began another attempt: the blocks so far are an earlier try
    acc.freeze()                               # Stop was requested: nothing more is accumulated or emitted
    acc.finalize("interrupted")                # the turn ended: open blocks are closed (events returned)
    acc.stored_blocks(ordered=True)            # the ChatBlock dicts of the final attempt, text included, call and result paired, folded
    acc.stored_order()                         # live block id of each stored block (the settle map)

Rules (each is tested):
  * Blocks are keyed by (message ordinal, index): a provider restarts block indexes in every assistant message, so two messages that both have an
    index 0 never collide. The ordinal moves on `message_boundary`.
  * `text_delta` applies to the block the latest `block_start` opened; without one (a provider that sends no block events) the first delta opens a text block.
  * The whole `text` event of a message is dropped when deltas of that same message were seen; otherwise it becomes a text block that never streamed
    (`end` carries the text). The state is per message, not per turn.
  * A `tool_call` event is matched to an open block by `tool_id` and fills in its title and target; it creates a block only when none is open for that id.
    Claude's complete `assistant` message arrives BEFORE the block's stop event (capture notes), so the title is known at the `tool_call`; `block_stop`
    only completes the input, and the tool stays open (running) until its `tool_result`.
  * `tool_result` ends the matching tool block; a result for an id nobody opened is kept as a stored result and shown live as nothing.
  * `restart` moves the blocks so far to `earlier_attempts()` and starts a new list; block ids keep counting up, so a live id is never reused.
  * Text passes through the per-block `text_filter` (the hold-back redactor); what is emitted is what is stored. Titles and targets pass `redact`.
  * The fold: a tool call and its result are one unit of two elements, never separated. When the next unit would take the list past `MAX_ELEMENTS`, further
    tool units only raise the count of one closing block ("N more tool calls not listed"); further text is appended to the last text block.
  * `freeze()` makes the accumulator inert: no more deltas or starts. `finalize(status)` ends the blocks still open with that status.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import ConnectorEvent
from .tool_kinds import LIVE_TEXT_MAX, classify, describe, title_of

__all__ = ["BlockAccumulator", "BlockEvent", "MAX_ELEMENTS", "BLOCK_TEXT_MAX", "TEXT_TOTAL_MAX", "FOLD_NAME"]

MAX_ELEMENTS = 400                 # stored elements of the final attempt before tool units fold (a tool call and its result are two)
BLOCK_TEXT_MAX = 100_000           # a stored text block holds at most this (library.chat.ChatBlock); a longer text is cut into several blocks
TEXT_TOTAL_MAX = 200_000           # all the text of a message (direct_turns.MAX_TEXT)
RESULT_TEXT_MAX = 2000             # the longest tool output kept with a result block (the connectors cut there already)
FOLD_NAME = "more tool calls"
EARLIER_LINES_MAX = 20             # the lines of one earlier attempt's summary (D219)


@dataclass
class BlockEvent:
    kind: str                      # start | delta | update | end | restart
    block_id: Optional[str]
    data: dict = field(default_factory=dict)


@dataclass
class _Block:
    block_id: str
    type: str                      # text | thinking | tool_use
    message: int
    index: Optional[int]
    tool_id: Optional[str] = None
    kind: str = "other"
    name: str = ""
    title: str = ""
    target: str = ""
    filt: Any = None               # the per-block text filter (text blocks)
    parts: list = field(default_factory=list)
    emitted: int = 0
    status: str = "open"           # open | ok | error | interrupted
    whole: bool = False            # a text block that never streamed
    is_error: bool = False
    truncated: bool = False
    result: Optional[str] = None   # the tool output kept for the stored result block
    result_seen: bool = False
    input_done: bool = False


def _identity(text: str) -> str:
    return text


def _cut(text: str, limit: int = LIVE_TEXT_MAX) -> str:
    return text if len(text) <= limit else text[:limit]


class BlockAccumulator:
    def __init__(self, *, folder: str = "", provider: str = "claude", redact: Optional[Callable[[str], str]] = None,
                 text_filter: Optional[Callable[[], Any]] = None, max_elements: int = MAX_ELEMENTS) -> None:
        self.folder = str(folder or "")
        self.provider = provider
        self._redact = redact or _identity
        self._text_filter = text_filter
        self._max = max(4, int(max_elements))
        self._seq = 0                                   # live block ids b1, b2, ... for the whole turn (never reset by a restart)
        self._message = 0
        self._saw_delta: set[int] = set()              # message ordinals in which a text delta was seen
        self._blocks: list[_Block] = []                # the current attempt, in the order the blocks started
        self._by_tool: dict[str, _Block] = {}
        self._current: Optional[_Block] = None         # the block the latest block_start opened and nothing has stopped
        self._legacy: list[dict] = []                  # the blocks as ChatPort stored them before streaming existed (arrival order, text only when it never streamed)
        self._legacy_kinds: dict[Any, tuple[str, str]] = {}
        self._earlier: list[dict] = []
        self._frozen = False
        self._elements = 0                             # stored elements counted so far (a tool use reserves two)
        self._fold: Optional[_Block] = None
        self._folded = 0
        self._folded_ids: set[str] = set()
        self._last_text: Optional[_Block] = None

    # ---- state -------------------------------------------------------------------------------------------------------------------
    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def message_ordinal(self) -> int:
        return self._message

    def freeze(self) -> None:
        """Stop accumulating: later events are ignored (the held tail of a text filter is dropped, never shown). Idempotent."""
        self._frozen = True

    def open_blocks(self) -> list[str]:
        return [b.block_id for b in self._blocks if b.status == "open"]

    def legacy_count(self) -> int:
        return len(self._legacy)

    def legacy_since(self, n: int) -> list[dict]:
        """The blocks `ChatPort` has always yielded as `block` events, added since the list had `n` entries."""
        return [dict(b) for b in self._legacy[n:]]

    def streamed_in_message(self) -> bool:
        """Text deltas of the current assistant message were seen (the whole `text` event that follows them is then not a new block)."""
        return self._message in self._saw_delta

    def text(self) -> str:
        """The text of the final attempt as it was emitted (what a stored reply's `text` is built from when the provider's own result is not used)."""
        return "".join("".join(b.parts) for b in self._blocks if b.type == "text")

    # ---- feeding -----------------------------------------------------------------------------------------------------------------
    def feed(self, event: ConnectorEvent) -> list[BlockEvent]:
        if self._frozen:
            return []
        handler = getattr(self, "_on_" + event.kind, None)
        return handler(event.data) if handler is not None else []

    def _new_id(self) -> str:
        self._seq += 1
        return f"b{self._seq}"

    def _on_message_boundary(self, data: dict) -> list[BlockEvent]:
        self._message += 1
        self._current = None
        return []

    def _on_block_start(self, data: dict) -> list[BlockEvent]:
        kind = data.get("type")
        if kind == "text":
            return self._open_text(index=data.get("index"))
        if kind == "thinking":
            block = _Block(self._new_id(), "thinking", self._message, data.get("index"))
            self._blocks.append(block)
            self._current = block
            self._count(1)
            return [BlockEvent("start", block.block_id, {"type": "thinking", "kind": "other", "name": ""})]
        if kind == "tool_use":
            return self._open_tool(data.get("tool_id"), str(data.get("name") or ""), data.get("input"), index=data.get("index"))
        return []

    def _open_text(self, index: Any = None, whole_text: Optional[str] = None) -> list[BlockEvent]:
        if self._over_cap():
            target = self._last_text
            if target is not None:                      # text past the cap is appended to the last text block: same block id, no new element
                self._current = target
                return []
        block = _Block(self._new_id(), "text", self._message, index if isinstance(index, int) else None, kind="other")
        block.filt = self._text_filter() if self._text_filter is not None else None
        self._blocks.append(block)
        self._current = block
        self._last_text = block
        self._count(1)
        return [BlockEvent("start", block.block_id, {"type": "text", "kind": "other", "name": ""})]

    def _open_tool(self, tool_id: Any, name: str, tool_input: Any, index: Any = None) -> list[BlockEvent]:
        tid = tool_id if isinstance(tool_id, str) and tool_id else None
        if tid is not None and tid in self._by_tool:
            return self._update_tool(self._by_tool[tid], name, tool_input)
        if tid is not None and tid in self._folded_ids:
            return []                                   # a call that was folded already: its later `tool_call` is the same unit
        if self._over_cap(units=2):
            self._fold_one(tid)
            return self._fold_events()
        kind, title, target = describe(name, tool_input, self.folder, self.provider)
        block = _Block(self._new_id(), "tool_use", self._message, index if isinstance(index, int) else None, tool_id=tid, kind=kind, name=name[:200])
        block.title, block.target = self._clean(title), self._clean(target)
        self._blocks.append(block)
        self._count(2)
        if tid is not None:
            self._by_tool[tid] = block
        self._current = block if index is not None else self._current
        events = [BlockEvent("start", block.block_id, {"type": "tool_use", "kind": kind, "name": name[:200]})]
        if tool_input is not None and (block.title or block.target) and tool_input != {}:        # input already complete (Codex command, a whole `tool_call`)
            block.input_done = True
            events.append(BlockEvent("update", block.block_id, {"title": block.title, "target": block.target}))
        return events

    def _update_tool(self, block: _Block, name: str, tool_input: Any) -> list[BlockEvent]:
        if not block.name and name:
            block.name = name[:200]
        if tool_input is None or (tool_input == {} and block.input_done):
            return []
        kind, title, target = describe(block.name or name, tool_input, self.folder, self.provider)
        title, target = self._clean(title), self._clean(target)
        if not (title or target) or (title, target) == (block.title, block.target):
            return []
        block.kind = kind if block.kind == "other" else block.kind
        block.title, block.target, block.input_done = title, target, True
        return [BlockEvent("update", block.block_id, {"title": title, "target": target})]

    def _clean(self, text: str) -> str:
        return _cut(self._redact(text or ""))

    def _on_text_delta(self, data: dict) -> list[BlockEvent]:
        if data.get("kind", "text") != "text":
            return []                                    # a tool's streamed input is the parser's business, never a page's
        text = str(data.get("text") or "")
        events: list[BlockEvent] = []
        block = self._current
        if block is None or block.type != "text" or block.status != "open":
            events += self._open_text()
            block = self._current
            if block is None or block.type != "text":
                return events
        self._saw_delta.add(self._message)
        if not text:
            return events
        piece = block.filt.push(text) if block.filt is not None else text
        if piece:
            events.append(self._emit_text(block, piece))
        return events

    def _emit_text(self, block: _Block, piece: str) -> BlockEvent:
        offset = block.emitted
        block.parts.append(piece)
        block.emitted += len(piece)
        return BlockEvent("delta", block.block_id, {"delta": piece, "offset": offset})

    def _on_text(self, data: dict) -> list[BlockEvent]:
        text = str(data.get("text") or "")
        legacy = None
        if self._message not in self._saw_delta:
            legacy = {"type": "text", "kind": "other", "text": text}
        if legacy is not None:
            self._legacy.append(legacy)
        if self._message in self._saw_delta or not text:
            return []                                    # the deltas of this message already carried it
        current = self._current
        if current is not None and current.type == "text" and current.status == "open" and not current.parts:
            events, block = [], current                  # the block a `block_start` opened and no delta filled: the whole message goes into it
        else:
            events = self._open_text()
            block = self._current
        if block is None or block.type != "text":
            return events
        shown = block.filt.push(text) + block.filt.finish() if block.filt is not None else text
        block.parts.append(shown)
        block.emitted += len(shown)
        block.whole = True
        block.status = "ok"
        events.append(BlockEvent("end", block.block_id, {"status": "ok", "is_error": False, "truncated": False, "text": shown}))
        self._current = None
        return events

    def _on_tool_call(self, data: dict) -> list[BlockEvent]:
        name = str(data.get("name") or data.get("type") or "")
        tid = data.get("id")
        provider_kind = classify(name, data.get("input"), self.provider)
        self._legacy_kinds[tid] = (provider_kind, name)
        self._legacy.append({"type": "tool_use", "kind": provider_kind, "name": name, "text": title_of(name, data.get("input"))})
        return self._open_tool(tid, name, data.get("input"))

    def _on_block_stop(self, data: dict) -> list[BlockEvent]:
        tid = data.get("tool_id")
        block = self._by_tool.get(tid) if isinstance(tid, str) else None
        if block is None and data.get("index") is not None:
            block = self._current if self._current is not None and self._current.index == data.get("index") else None
        if block is None:
            return []
        if block.type == "text":
            return self._close_text(block)
        if block.type == "thinking":
            return self._end(block, "ok")
        events: list[BlockEvent] = []
        if data.get("input") is not None and not block.input_done:
            events += self._update_tool(block, block.name, data.get("input"))
        block.input_done = True
        if data.get("completed"):                         # a provider whose tool item is finished by this event (Codex): the result rides along
            code = data.get("exit_code")
            failed = isinstance(code, int) and code != 0
            block.result = self._redact(str(data.get("output") or ""))[:RESULT_TEXT_MAX]
            block.truncated = bool(data.get("truncated"))
            block.is_error = failed
            block.result_seen = bool(block.result) or code is not None
            events += self._end(block, "error" if failed else "ok")
        if self._current is block:
            self._current = None
        return events

    def _close_text(self, block: _Block) -> list[BlockEvent]:
        events: list[BlockEvent] = []
        if block.filt is not None:
            rest = block.filt.finish()
            if rest:
                events.append(self._emit_text(block, rest))
        events += self._end(block, "ok")
        if self._current is block:
            self._current = None
        return events

    def _on_tool_result(self, data: dict) -> list[BlockEvent]:
        tid = data.get("tool_use_id")
        text = str(data.get("content") or "")
        kind, name = self._legacy_kinds.get(tid, ("other", ""))
        legacy = {"type": "tool_result", "kind": kind, "name": name, "text": text, "is_error": bool(data.get("is_error"))}
        if data.get("truncated"):
            legacy["truncated"] = True
        self._legacy.append(legacy)
        block = self._by_tool.get(tid) if isinstance(tid, str) else None
        if block is None:
            return []
        block.result = self._redact(text)[:RESULT_TEXT_MAX]
        block.result_seen = True
        block.is_error = bool(data.get("is_error"))
        block.truncated = bool(data.get("truncated"))
        return self._end(block, "error" if block.is_error else "ok")

    def _end(self, block: _Block, status: str) -> list[BlockEvent]:
        if block.status != "open":
            return []
        block.status = status
        payload: dict[str, Any] = {"status": status, "is_error": block.is_error, "truncated": block.truncated}
        if block.type == "tool_use":
            payload["kind"] = block.kind
        return [BlockEvent("end", block.block_id, payload)]

    # ---- the fold ----------------------------------------------------------------------------------------------------------------
    def _count(self, elements: int) -> None:
        self._elements += elements

    def _over_cap(self, units: int = 1) -> bool:
        """Would one more unit (a text block is one element, a tool use with its result two) take the list past the cap, leaving room for the fold block?"""
        return self._elements + units > self._max - 2

    def _fold_one(self, tool_id: Optional[str]) -> None:
        self._folded += 1
        if tool_id is not None:
            self._folded_ids.add(tool_id)

    def _fold_events(self) -> list[BlockEvent]:
        text = f"{self._folded} more tool calls not listed"
        if self._fold is None:
            block = _Block(self._new_id(), "tool_use", self._message, None, kind="other", name=FOLD_NAME, title=text, target="")
            block.truncated, block.status, block.input_done = True, "ok", True
            self._fold = block
            self._blocks.append(block)
            self._count(2)
            return [BlockEvent("start", block.block_id, {"type": "tool_use", "kind": "other", "name": FOLD_NAME}),
                    BlockEvent("update", block.block_id, {"title": text, "target": ""}),
                    BlockEvent("end", block.block_id, {"status": "ok", "is_error": False, "truncated": True, "kind": "other"})]
        self._fold.title = text
        return [BlockEvent("update", self._fold.block_id, {"title": text, "target": ""})]

    # ---- ending ------------------------------------------------------------------------------------------------------------------
    def finalize(self, status: str = "ok") -> list[BlockEvent]:
        """End every block that is still open. Text blocks end `ok` (their filter's held tail is released unless frozen); a tool whose result never came
        ends `interrupted` for a stopped or failed turn, and `ok` for a finished one (the model went on, so the call was resolved)."""
        events: list[BlockEvent] = []
        for block in self._blocks:
            if block.status != "open":
                continue
            if block.type == "text":
                if block.filt is not None and not self._frozen:
                    rest = block.filt.finish()
                    if rest:
                        events.append(self._emit_text(block, rest))
                events += self._end(block, "ok")         # text that was written stays text, whatever ended the turn
            elif block.type == "thinking":
                events += self._end(block, "ok")
            else:
                events += self._end(block, "interrupted" if status == "interrupted" else "ok")
        self._current = None
        return events

    def restart(self, reason: str = "", provider: str = "") -> list[BlockEvent]:
        """A new attempt of the same turn began: the blocks so far become an earlier try (kept as a summary), the list starts again. Block ids keep counting."""
        earlier_provider = self.provider
        if self._blocks or self._legacy:
            side_effects = any(b.type == "tool_use" and b.kind in ("edit", "run") for b in self._blocks)
            self._earlier.append({"provider": earlier_provider, "reason": reason, "after_side_effects": side_effects,
                                  "lines": self._summary_lines(), "blocks": self.stored_blocks(ordered=True)})
        else:
            side_effects = False
        self._blocks, self._by_tool, self._legacy, self._legacy_kinds = [], {}, [], {}
        self._current = None
        self._message = 0
        self._saw_delta = set()
        self._elements = 0
        self._fold, self._folded, self._folded_ids, self._last_text = None, 0, set(), None
        if provider:
            self.provider = provider
        return [BlockEvent("restart", None, {"provider": self.provider, "reason": reason, "after_side_effects": side_effects})]

    def earlier_attempts(self) -> list[dict]:
        return list(self._earlier)

    def _summary_lines(self) -> list[str]:
        lines = [b.title or f"Using {b.name}" for b in self._blocks if b.type == "tool_use" and b.name != FOLD_NAME]
        return [_cut(line) for line in lines[:EARLIER_LINES_MAX]]

    # ---- the stored shape --------------------------------------------------------------------------------------------------------
    def stored_blocks(self, ordered: bool = False) -> list[dict]:
        """The blocks of the final attempt as `library.chat.ChatBlock` dicts. `ordered=False` is what `ChatPort` always returned (tool calls and results in the order
        they arrived, a text block only for a whole message that never streamed). `ordered=True` is the whole turn in order: text, thinking and tool blocks as they
        started, each tool call followed by its result, long text cut into blocks of at most `BLOCK_TEXT_MAX`, all the text at most `TEXT_TOTAL_MAX`."""
        if not ordered:
            return [dict(b) for b in self._legacy]
        out: list[dict] = []
        budget = TEXT_TOTAL_MAX
        for block in self._blocks:
            if block.type == "text":
                text = "".join(block.parts)
                cut = False
                if len(text) > budget:
                    text, cut = text[:budget], True
                if not text:
                    continue
                budget -= len(text)
                for n in range(0, len(text), BLOCK_TEXT_MAX):
                    piece = {"type": "text", "kind": "other", "text": text[n:n + BLOCK_TEXT_MAX]}
                    if cut and n + BLOCK_TEXT_MAX >= len(text):
                        piece["truncated"] = True
                    out.append(piece)
            elif block.type == "thinking":
                out.append({"type": "thinking", "kind": "other", "text": ""})
            else:
                use = {"type": "tool_use", "kind": block.kind, "name": block.name, "text": block.title or block.name}
                if block.name == FOLD_NAME:
                    use["truncated"] = True
                out.append(use)
                if block.result_seen:
                    result = {"type": "tool_result", "kind": block.kind, "name": block.name, "text": block.result or "", "is_error": block.is_error}
                    if block.truncated:
                        result["truncated"] = True
                    out.append(result)
        return out

    def stored_order(self) -> list[str]:
        """The live block id of each element `stored_blocks(ordered=True)` returns, in the same order (a tool call and its result share one id): the client
        remaps its keys with this at settle."""
        out: list[str] = []
        budget = TEXT_TOTAL_MAX
        for block in self._blocks:
            if block.type == "text":
                text = "".join(block.parts)[:budget]
                if not text:
                    continue
                budget -= len(text)
                out.extend([block.block_id] * max(1, -(-len(text) // BLOCK_TEXT_MAX)))
            elif block.type == "thinking":
                out.append(block.block_id)
            else:
                out.append(block.block_id)
                if block.result_seen:
                    out.append(block.block_id)
        return out

    def snapshot(self) -> list[dict]:
        """The blocks of the current attempt as a page needs them to catch up: id, type, kind, name, title, target, status, the text emitted so far."""
        out = []
        for block in self._blocks:
            row: dict[str, Any] = {"block_id": block.block_id, "type": block.type, "kind": block.kind, "name": block.name, "status": block.status}
            if block.type == "text":
                row["text"] = "".join(block.parts)
            if block.type == "tool_use":
                row.update({"title": block.title, "target": block.target, "is_error": block.is_error, "truncated": block.truncated})
            out.append(row)
        return out
