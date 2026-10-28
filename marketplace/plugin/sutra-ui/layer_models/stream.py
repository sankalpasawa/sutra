"""Validating a streamed answer as it arrives (A4.7.5), and keeping a large value from holding the loop (STR-6).

A model's answer is prose, a code fence and JSON. `Scanner` finds the first `{` or `[` and the end of its value, one structural
character at a time. Two readers watch what has arrived and report names and counts, never half a value:

    ListReader(adapter)    an answer that is an array. pydantic's own `experimental_allow_partial` drops the incomplete last
                           item and validates the whole ones; an error in an earlier item shows one element late.
    ObjectReader(adapter)  an answer that is an object. BaseModel does not support partial validation, so the text so far is
                           read with pydantic_core.from_json(allow_partial=True), the right-most spine (the last key of each
                           object, the last item of each list on the path to the cut, which may still be growing) is trimmed,
                           and what is left is validated with the full adapter. 'is missing' and 'fewer than N items' are
                           pending (the rest has not arrived); every other sentence is a fault in a completed part, and so
                           certain: it is kept and never withdrawn.

A fault found early is advice; `final` decides, with the same adapter, on the value's whole span. Nothing here builds an adapter:
the caller hands one in, built once (STR-7). The text a reader keeps is capped at CAP (STR-9); past it the reader reports no more
progress, and the caller's final check on the whole text still happens. Faults are written as faults.py writes them."""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError
from pydantic_core import from_json

from . import faults as _faults

CAP = 256 * 1024          # the most text a reader keeps for progress
THROTTLE_S = 0.1          # at most one validation in this many seconds, but always at a chunk that closes a value
BIG = 64 * 1024           # a value over this many characters is validated off the loop
SLICE = 500               # the items of one slice of a big list

STOPPED = 'the answer stopped before it was whole'
NOT_JSON = 'the answer is not valid JSON'

_OUT = re.compile(r'["{}\[\],]')
_IN = re.compile(r'["\\]')


class Scanner:
    """Finds the first JSON object or array in a stream of text and the end of it, string- and escape-aware. `feed` jumps from one
    structural character to the next, so its cost follows the structure, not the length. `start` is the index (in the whole text
    fed) of the first `{` or `[`, `end` the index after the character that returns the depth to 0, `depth` the nesting now.
    `closed` says the last chunk closed a value: a `}` or `]`, or a `,` at depth 1 or 2. `elements` counts the elements of the
    outer value that are certainly whole (an object or array that closed at depth 2, a scalar that a comma at depth 1 followed):
    pydantic's partial validation hands back a last item that validates with what has arrived, so a list reader trusts this
    count and not the length of the list it is given."""

    def __init__(self):
        self.start = None
        self.end = None
        self.depth = 0
        self.closed = False
        self.n = 0                  # characters fed
        self.elements = 0
        self._scalar = True         # the element in progress, if any, is a scalar so far
        self._in_string = False
        self._escape = False

    def feed(self, chunk):
        self.closed = False
        base, i, size = self.n, 0, len(chunk)
        self.n += size
        if self.end is not None:
            return
        while i < size:
            if self._in_string:
                if self._escape:
                    self._escape = False
                    i += 1
                    continue
                m = _IN.search(chunk, i)
                if m is None:
                    return
                i = m.end()
                if m.group() == '\\':
                    self._escape = True
                else:
                    self._in_string = False
                continue
            m = _OUT.search(chunk, i)
            if m is None:
                return
            ch, i = m.group(), m.end()
            if self.start is None:
                if ch in '{[':
                    self.start, self.depth = base + m.start(), 1
                continue
            if ch == '"':
                self._in_string = True
            elif ch in '{[':
                self.depth += 1
                if self.depth == 2:
                    self._scalar = False
            elif ch in '}]':
                self.depth -= 1
                self.closed = True
                if self.depth == 1:
                    self.elements += 1
                elif self.depth == 0:
                    self.end = base + i
                    return
            else:                       # a comma
                if self.depth == 1:
                    if self._scalar:
                        self.elements += 1
                    self._scalar = True
                if self.depth <= 2:
                    self.closed = True


@dataclass
class Progress:
    """What has arrived: names and counts. `bytes` is the number of bytes fed to the reader, kept or not."""
    arrived: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    faults: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    done: bool = False
    bytes: int = 0

    def key(self):
        """Everything but `bytes`: two progresses with the same key say the same thing to a screen."""
        return (tuple(self.arrived), tuple(sorted(self.counts.items())), tuple(self.faults), tuple(self.pending), self.done)

    def as_frame(self):
        """The frame for a consumer to send (frames.Progress), validated once, here."""
        from .frames import Progress as Frame
        return Frame(arrived=list(self.arrived), counts=dict(self.counts), faults=list(self.faults), pending=list(self.pending),
                     done=self.done, bytes=self.bytes)


def _sentences(errors, value):
    return ['%s: %s' % (_faults.path(loc), s) for loc, s in _faults.explain(errors, value)]


def _errors(e):
    return e.errors(include_url=False, include_input=False, include_context=True)


def closed_part(raw):
    """`raw` with its right-most spine trimmed: what has certainly arrived whole. A dict loses its last key, a list its last item;
    the value that was last is kept, trimmed in turn, when it is a dict or list, and dropped when it is a scalar."""
    if isinstance(raw, dict):
        keys = list(raw)
        out = {k: raw[k] for k in keys[:-1]}
        if keys:
            last = raw[keys[-1]]
            if isinstance(last, (dict, list)):
                out[keys[-1]] = closed_part(last)
        return out
    if isinstance(raw, list):
        out = list(raw[:-1])
        if raw and isinstance(raw[-1], (dict, list)):
            out.append(closed_part(raw[-1]))
        return out
    return raw


def is_pending(sentence):
    """The sentences that only say the rest has not arrived."""
    return (sentence == 'is missing' or sentence.startswith('fewer than')
            or (sentence.startswith('fits none of its shapes (') and sentence[len('fits none of its shapes ('):-1] == 'is missing'))


class _Reader:
    """What both readers share: the scanner, the capped text, the throttle."""

    def __init__(self, adapter, throttle=THROTTLE_S, clock=time.monotonic, cap=CAP):
        self.adapter = adapter
        self.scanner = Scanner()
        self.throttle, self.clock, self.cap = throttle, clock, cap
        self._parts = []            # the text kept, as chunks
        self.kept = 0               # characters kept (never more than cap)
        self.over = False           # text past the cap was not kept
        self.bytes = 0
        self._last = None           # clock at the last validation
        self._text = None
        self.faults = []            # certain, kept, never withdrawn
        self.progress = Progress()

    def _take(self, chunk):
        self.bytes += len(chunk.encode('utf-8', 'replace'))
        room = self.cap - self.kept
        if room <= 0:
            self.over = True
            return
        if len(chunk) > room:
            chunk, self.over = chunk[:room], True
        self._parts.append(chunk)
        self.kept += len(chunk)
        self._text = None

    def text(self):
        """The text kept so far, from the first character fed."""
        if self._text is None:
            self._text = ''.join(self._parts)
            self._parts = [self._text]
        return self._text

    def _due(self):
        """True when a validation is worth doing now: the chunk closed a value, or the throttle has passed."""
        now = self.clock()
        if self.scanner.closed or self._last is None or now - self._last >= self.throttle:
            self._last = now
            return True
        return False

    def _body(self):
        """The text from the first `{` or `[`, up to the end of the value when it has ended."""
        s = self.scanner
        t = self.text()
        return t[s.start:s.end] if s.end is not None else t[s.start:]

    def _remember(self, found):
        for f in found:
            if f not in self.faults:
                self.faults.append(f)


class ListReader(_Reader):
    """An answer that is an array. `feed(text)` takes the next chunk and returns the whole items so far (validated objects)."""

    def __init__(self, adapter, **kw):
        super().__init__(adapter, **kw)
        self.items = []

    def feed(self, text):
        self.scanner.feed(text)
        self._take(text)
        self.progress.bytes = self.bytes
        if self.scanner.start is None or self.over and self.scanner.end is None:
            return list(self.items)
        ended = self.scanner.end is not None
        if not ended and not self._due():
            return list(self.items)
        if ended and self.progress.done:
            return list(self.items)
        body = self._body()
        try:
            got = list(self.adapter.validate_json(body, experimental_allow_partial=not ended))
            self.items = got if ended else got[:self.scanner.elements]
            if ended:
                self.progress.done = True
        except ValidationError as e:
            try:
                value = from_json(body.encode('utf-8'), allow_partial=not ended)
            except ValueError:
                value = None
            if value is not None:
                self._remember(_sentences(_errors(e), value))
            if ended:
                self.progress.done = True
        self.progress.arrived = []
        self.progress.counts = {'': len(self.items)}
        self.progress.faults = list(self.faults)
        return list(self.items)


class ObjectReader(_Reader):
    """An answer that is an object. `feed(text)` takes the next chunk and returns a Progress."""

    def feed(self, text):
        s = self.scanner
        s.feed(text)
        self._take(text)
        self.progress.bytes = self.bytes
        if s.start is None or (self.over and s.end is None):
            return self.progress
        ended = s.end is not None
        if ended and self.progress.done:
            return self.progress
        if not ended and not self._due():
            return self.progress
        try:
            raw = from_json(self._body().encode('utf-8'), allow_partial=True)
        except ValueError:
            return self.progress
        if not isinstance(raw, dict):
            return self.progress
        closed = raw if ended else closed_part(raw)
        pending, found = [], []
        try:
            self.adapter.validate_python(closed)
        except ValidationError as e:
            for loc, sentence in _faults.explain(_errors(e), closed):
                line = '%s: %s' % (_faults.path(loc), sentence)
                (pending if is_pending(sentence) and not ended else found).append(line)
        self._remember(found)
        keys = list(raw)
        arrived = keys if ended else keys[:-1]
        counts = {k: (len(v) if ended else max(len(v) - 1, 0)) for k, v in raw.items() if isinstance(v, list)}
        self.progress = Progress(arrived=arrived, counts=counts, faults=list(self.faults), pending=[] if ended else pending,
                                 done=ended, bytes=self.bytes)
        return self.progress


def final(adapter, text):
    """The verdict on a whole answer: (ok, faults). The value is the first `{...}` or `[...]` of `text`, validated whole with
    `validate_json`; no end found is the one fault 'the answer stopped before it was whole'."""
    sc = Scanner()
    sc.feed(text)
    if sc.start is None or sc.end is None:
        return False, [STOPPED]
    span = text[sc.start:sc.end]
    try:
        value = json.loads(span)
    except ValueError:
        return False, [NOT_JSON]
    try:
        adapter.validate_json(span)
    except ValidationError as e:
        return False, _sentences(_errors(e), value)
    return True, []


# ---- a large value does not hold the loop (STR-6) --------------------------------------------------------------------------
def size_of(value):
    """A cheap estimate of how many characters `value` is as JSON: its length for text, an item or two measured and scaled for a
    list or dict. It never walks the value."""
    if isinstance(value, (str, bytes, bytearray)):
        return len(value)
    if isinstance(value, (list, tuple)) and value:
        step = max(len(value) // 3, 1)
        sample = value[::step][:3]
        return len(value) * (sum(len(json.dumps(v, default=str)) for v in sample) // len(sample) + 2)
    if isinstance(value, dict) and value:
        keys = list(value)[:3]
        return len(value) * (sum(len(str(k)) + len(json.dumps(value[k], default=str)) for k in keys) // len(keys) + 4)
    return 0


def _check(adapter, value):
    try:
        adapter.validate_python(value)
    except ValidationError as e:
        return _sentences(_errors(e), value)
    return []


async def validate_off_loop(adapter, value, size=None, item_adapter=None):
    """(ok, faults) for `value` against `adapter`, without holding the event loop for long. A value over BIG goes to a worker
    thread (`anyio.to_thread.run_sync`); a big list whose item adapter is given is checked in slices of SLICE items with
    `await asyncio.sleep(0)` between, which stalls the loop least; anything else is checked in place. `size` overrides the estimate."""
    n = size_of(value) if size is None else size
    if n <= BIG:
        found = _check(adapter, value)
        return not found, found
    if item_adapter is not None and isinstance(value, list):
        found = []
        for at in range(0, len(value), SLICE):
            for off, v in enumerate(value[at:at + SLICE]):
                for line in _check(item_adapter, v):
                    found.append('$[%d]%s' % (at + off, line[1:]))
            await asyncio.sleep(0)
        return not found, found
    import anyio.to_thread
    found = await anyio.to_thread.run_sync(_check, adapter, value)
    return not found, found
