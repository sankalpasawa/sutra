"""Streaming must not break (PRD amendment A4.7, package A4-STREAM).

T1  what the streams do today: goldens recorded from unchanged main (STR-5)
T3  the frames as models          T4  the readers            T5  adapters once, registry pinned
T6  the `models` event            T7  the opt-in streaming call for agent steps
T8  the benchmark's tests (STR-6, STR-8, STR-10)

The goldens in test_fixtures/stream/ are compared in a normal run and rewritten only by `pytest --a4-write-goldens`
(a pytest option, never an environment variable). Nothing here is weakened to pass: a change in a golden is a change in
what the owner's screen receives."""
import asyncio
import json
import os
import platform
import statistics
import time
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIX = HERE / "test_fixtures" / "stream"


@pytest.fixture
def write_goldens(request):
    return request.config.getoption("--a4-write-goldens")


def _check(path, text, write):
    """Compare `text` with the golden at `path`, or write it under --a4-write-goldens."""
    if write:
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), "%s is missing: record it from unchanged main with --a4-write-goldens" % path.name
    assert text == path.read_text(encoding="utf-8"), "%s: the bytes of the frames changed" % path.name


# ---------------------------------------------------------------------------------------------------------------- the drivers
class _Done(Exception):
    """The scripted stream has no more steps."""


def _clock_and_sleep(app, monkeypatch, step=1.5, actions=None):
    """A fake clock that a fake sleep moves, and a sleep that runs the next scripted action (or ends the run)."""
    clock = {"t": 1000.0}
    acts = list(actions or [])

    async def sleep(s):
        clock["t"] += step
        if not acts:
            raise _Done()
        acts.pop(0)()

    monkeypatch.setattr(app, "time", types.SimpleNamespace(time=lambda: clock["t"], monotonic=time.monotonic,
                                                           sleep=time.sleep, strftime=time.strftime, gmtime=time.gmtime))
    monkeypatch.setattr(app.asyncio, "sleep", sleep)
    return clock


def sessions_frames(app, monkeypatch, polls=None, hooks=None):
    """The text of `api_sessions_stream` over a scripted sr.index: sync, changed, vanished, tick. `hooks` maps a poll number
    to a callable run just before that poll's index is read (the T6 test bumps the revision there)."""
    a = {"id1": {"mtime": 100, "size": 10, "agents_bytes": 0, "title": "one"},
         "id2": {"mtime": 100, "size": 20, "agents_bytes": 0, "title": "two"}}
    polls = polls or [
        a,
        {"id1": dict(a["id1"], mtime=101, size=15), "id2": a["id2"]},
        {"id1": dict(a["id1"], mtime=101, size=15)},
        {"id1": dict(a["id1"], mtime=101, size=15)},
    ]
    n = {"i": 0}

    def index():
        n["i"] += 1
        if hooks and n["i"] in hooks:
            hooks[n["i"]]()
        return polls[min(n["i"], len(polls)) - 1]

    monkeypatch.setattr(app.sr, "index", index)
    monkeypatch.setattr(app.sr, "liveness", lambda m: "idle")
    monkeypatch.setattr(app, "SESSION_HEARTBEAT_S", 4.0)       # one tick, on the fourth poll
    _clock_and_sleep(app, monkeypatch, actions=[lambda: None] * (len(polls) - 1))
    out = []

    async def run():
        resp = await app.api_sessions_stream()
        try:
            async for chunk in resp.body_iterator:
                out.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        except _Done:
            pass
        return resp

    resp = asyncio.run(run())
    return "".join(out), resp


def log_tail_frames(app, monkeypatch, tmp_path):
    """The text of `sse`: the backlog, `: backlog-end`, an appended row (and a half line completed later), a truncation."""
    log = tmp_path / "turns.jsonl"
    log.write_text('{"ts": 1, "n": 1}\n{"ts": 2, "n": 2}\n', encoding="utf-8")
    monkeypatch.setattr(app.lr, "resolve", lambda source: log)

    def append(s):
        return lambda: log.open("a", encoding="utf-8").write(s)

    def truncate():
        log.write_text('{"ts": 5, "n": 5}\n', encoding="utf-8")

    actions = [append('{"ts": 3, "n": 3}\n{"ts": 4, "n"'), append(': 4}\n'), append("not json\n"), truncate]
    _clock_and_sleep(app, monkeypatch, actions=actions)
    out = []

    async def run():
        resp = await app.sse("turns")
        try:
            async for chunk in resp.body_iterator:
                out.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        except _Done:
            pass

    asyncio.run(run())
    return "".join(out)


class _Stdout:
    """A fake `proc.stdout`: one recorded line per readline(), then EOF."""

    def __init__(self, lines):
        self.lines = [l.encode() if isinstance(l, str) else l for l in lines]

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""


def chat_frames(fixture):
    """The frames `Runtime.demux_turn` emits for a recorded stream-json turn, and what it returns."""
    import session_runtime as sr
    rt = sr.SessionRuntime()
    rt.proc = types.SimpleNamespace(stdout=_Stdout((FIX / fixture).read_text(encoding="utf-8").splitlines(True)))
    frames = []

    async def emit(f):
        frames.append(f)

    out = asyncio.run(rt.demux_turn(emit, None))
    return {"frames": frames, "returned": list(out)}


# --------------------------------------------------------------------------------------------------------------------- T1
def test_str5_frames_are_byte_identical(monkeypatch, tmp_path, write_goldens):
    """STR-5: the sessions stream, the log tail and the chat's frames are the bytes they were on main before A4."""
    import app
    text, resp = sessions_frames(app, monkeypatch)
    _check(FIX / "sessions.golden.txt", text, write_goldens)
    assert resp.media_type == "text/event-stream"
    _check(FIX / "log_tail.golden.txt", log_tail_frames(app, monkeypatch, tmp_path), write_goldens)
    chat = {"partial": chat_frames("turn.jsonl"), "plain": chat_frames("turn_plain.jsonl")}
    _check(FIX / "chat.golden.json", json.dumps(chat, indent=1, sort_keys=False) + "\n", write_goldens)


def test_the_goldens_hold_every_kind_of_frame():
    """The goldens are only a proof if they cover the vocabulary the spec names."""
    sess = (FIX / "sessions.golden.txt").read_text(encoding="utf-8")
    for ev in ("sync", "changed", "vanished", "tick"):
        assert "event: %s\n" % ev in sess
    tail = (FIX / "log_tail.golden.txt").read_text(encoding="utf-8")
    assert ": backlog-end" in tail and tail.count("data: ") >= 5
    chat = json.loads((FIX / "chat.golden.json").read_text(encoding="utf-8"))
    for variant in ("partial", "plain"):
        types_ = [f["type"] for f in chat[variant]["frames"]]
        for t in ("session", "sysinit", "token", "thinking", "tool", "done"):
            assert t in types_, (variant, t)
    assert chat["partial"]["frames"] != chat["plain"]["frames"]


def _measure_minimal(monkeypatch):
    """The numbers of the minimal measurement T1 records; qa/stream_bench.py (T8) replaces the file with its own, same keys."""
    import app
    big = {"s%03d" % i: {"mtime": 100, "size": 10, "agents_bytes": 0, "title": "t%d" % i} for i in range(200)}
    monkeypatch.setattr(app.sr, "index", lambda: big)
    monkeypatch.setattr(app.sr, "liveness", lambda m: "idle")
    gaps, stop = [], {"v": False}

    async def run():
        async def ticker():
            last = time.perf_counter()
            while not stop["v"]:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append((now - last - 0.01) * 1000)
                last = now
        t = asyncio.create_task(ticker())
        resp = await app.api_sessions_stream()
        t0 = time.perf_counter()
        it = resp.body_iterator
        await it.__anext__()
        first = (time.perf_counter() - t0) * 1000
        await it.aclose()
        stop["v"] = True
        await t
        return first

    first = asyncio.run(run())
    return {"first_byte_ms": round(first, 3), "gap_p99_ms": round(sorted(gaps)[int(len(gaps) * .99) - 1], 3) if gaps else 0.0}


def test_the_baseline_carries_the_machine(write_goldens, monkeypatch):
    path = FIX / "baseline.json"
    if write_goldens:
        base = {"node": platform.node(), "cores": os.cpu_count(), "recorded_from": "main before A4-STREAM"}
        base.update(_measure_minimal(monkeypatch))
        path.write_text(json.dumps(base, indent=1) + "\n", encoding="utf-8")
    base = json.loads(path.read_text(encoding="utf-8"))
    assert base["node"] and base["cores"] and "first_byte_ms" in base


# --------------------------------------------------------------------------------------------------------------------------- T3
import ast
import copy  # noqa: E402,F401
from pydantic import ValidationError  # noqa: E402


def test_every_chat_frame_fits_chatframe():
    """The frames of the chat golden (both variants) and of a turn the fake agent answers fit ChatFrame."""
    from layer_models.frames import CHAT_ADAPTER
    chat = json.loads((FIX / "chat.golden.json").read_text(encoding="utf-8"))
    seen = 0
    for variant in chat.values():
        for f in variant["frames"]:
            CHAT_ADAPTER.validate_python(f)
            seen += 1
    assert seen >= 14
    # the fake agent's own turn (qa/fake_claude_agent.py): init, a text block, a result
    import session_runtime as sr
    lines = [json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": "stub-model", "tools": [], "mcp_servers": []}),
             json.dumps({"type": "assistant", "session_id": "s", "message": {"role": "assistant", "content": [{"type": "text", "text": "ack"}]}}),
             json.dumps({"type": "result", "subtype": "success", "session_id": "s", "is_error": False, "duration_ms": 1,
                         "num_turns": 1, "total_cost_usd": 0.0, "result": "ack"})]
    rt = sr.SessionRuntime()
    rt.proc = types.SimpleNamespace(stdout=_Stdout([l + "\n" for l in lines]))
    got = []

    async def emit(f):
        got.append(f)

    asyncio.run(rt.demux_turn(emit, None))
    assert [f["type"] for f in got] == ["session", "sysinit", "token", "done"]
    for f in got:
        CHAT_ADAPTER.validate_python(f)
    with pytest.raises(ValidationError):
        CHAT_ADAPTER.validate_python({"type": "no-such-frame"})
    with pytest.raises(ValidationError):
        CHAT_ADAPTER.validate_python({"type": "token"})      # a token without its text


_EMITTERS = {"emit", "send_json", "_emit", "send", "_send"}
_SOURCES = ["app.py", "session_runtime.py", "codex_runtime.py", "acp_runtime.py", "provider_adapters.py"]


def _emitted_types():
    """Every frame `type` that is a constant in an argument of an emit/send_json call: a dict literal's "type", or a `type=` keyword
    of dict(...). Types that begin with an underscore are internal to the observers and never reach the client."""
    found = {}
    for name in _SOURCES:
        tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and (getattr(n.func, "id", None) in _EMITTERS or getattr(n.func, "attr", None) in _EMITTERS)):
                continue
            for arg in n.args:
                for m in ast.walk(arg):
                    if isinstance(m, ast.Dict):
                        for k, v in zip(m.keys, m.values):
                            if isinstance(k, ast.Constant) and k.value == "type" and isinstance(v, ast.Constant) and isinstance(v.value, str):
                                found.setdefault(v.value, []).append(name)
                    elif isinstance(m, ast.Call) and getattr(m.func, "id", None) == "dict":
                        for kw in m.keywords:
                            if kw.arg == "type" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                found.setdefault(kw.value.value, []).append(name)
    return {t: s for t, s in found.items() if not t.startswith("_")}


def test_every_emitted_type_has_a_model():
    from layer_models.frames import CHAT_TYPES, CHAT_ADAPTER
    emitted = _emitted_types()
    assert len(emitted) >= 14, "the scan found too little: %s" % sorted(emitted)
    assert "mode_note" in emitted, "the dict(note, type=...) form is scanned"
    missing = sorted(t for t in emitted if t not in CHAT_TYPES)
    assert missing == [], "frame types in no model: %s (from %s)" % (missing, [emitted[t][0] for t in missing])
    # and the union holds exactly the types it names: each type validates as the frame it names
    for t in CHAT_TYPES:
        body = {"type": t, "text": "x"} if t in ("token", "notice") else {"type": t}
        assert CHAT_ADAPTER.validate_python(body).type == t


def test_the_frames_file_is_what_the_models_generate():
    from layer_models import frames
    on_disk = frames.SCHEMA_PATH.read_text(encoding="utf-8")
    assert on_disk == frames.schema_text(), "run `python -m layer_models.frames --write`; never edit the file by hand"
    doc = json.loads(on_disk)
    assert set(doc) == {"title", "chat", "sessions", "log_tail", "added"}
    assert set(doc["added"]) == {"models", "progress"}
    assert frames.SCHEMA_PATH.parent.name == "models" and "layers" not in str(frames.SCHEMA_PATH)


def test_str3_a_new_frame_is_made_once_and_dumped():
    """Building a Models validates it; dumping it does not (a frame that was never validated dumps without a ValidationError)."""
    from layer_models.frames import FRAME_ADAPTER, Models, Progress, frame_json
    with pytest.raises(ValidationError):
        Models(rev="x", keys=[])
    with pytest.raises(ValidationError):
        Models(rev=1, keys=[], extra_key=1)
    m = Models(rev=15, keys=["x.client"])
    assert json.loads(frame_json(m)) == {"rev": 15, "keys": ["x.client"]}
    never = Models.model_construct(rev="x", keys=[])
    assert FRAME_ADAPTER.dump_json(never, warnings=False)          # no validation on the way out
    p = Progress(arrived=["engines"], counts={"engines": 2}, faults=[], pending=["deliverable"], done=False, bytes=10)
    assert json.loads(frame_json(p))["counts"] == {"engines": 2}
    # the adapter is the one built at import
    from layer_models import frames
    assert frames.FRAME_ADAPTER is FRAME_ADAPTER


# --------------------------------------------------------------------------------------------------------------------------- T4
import random  # noqa: E402
from typing import Annotated, Any  # noqa: E402

from pydantic import TypeAdapter  # noqa: E402

from layer_models import stream as ST  # noqa: E402
from layer_models.base import Closed  # noqa: E402
from layer_models.types import Bool, Enum, Int, Items, Num, Str  # noqa: E402


class _Eng(Closed):
    name: Annotated[str, Str(40, 1)]
    reads: Annotated[str, Str(40, 1)]
    writes: Annotated[str, Str(40, 1)]
    does: Annotated[str, Str(400)] = None
    level: Annotated[Any, Enum(1, 2)] = None
    confidence: Annotated[float, Num()] = None
    covers: Annotated[list[Annotated[str, Str(8)]], Items(10)] = None
    internet: Annotated[bool, Bool()] = None


class _Flow(Closed):
    schema_version: Annotated[int, Int(1, 1)]
    source: Annotated[Any, Enum("shaped", "adapted")]
    kind: Annotated[str, Str(40, 1)]
    engines: Annotated[list[_Eng], Items(12, 1)]
    deliverable: Annotated[str, Str(40, 1)]
    covers_by: Annotated[Any, Enum("adaptation", "owner")]
    why: Annotated[str, Str(200)] = None
    at: Annotated[str, Str(40)] = None
    by: Annotated[str, Str(40)] = None


_FLOW = TypeAdapter(_Flow)
_ENGS = TypeAdapter(list[_Eng])


def _flow(level=1):
    return {"schema_version": 1, "source": "shaped", "kind": "website",
            "engines": [{"name": "Plan", "reads": "Brief", "writes": "Site plan", "does": "Plan the pages the brief asks for. " * 6,
                         "covers": ["D1", "D2"], "internet": False},
                        {"name": "Write", "reads": "Site plan", "writes": "Pages", "does": "Write every page in the voice. " * 6,
                         "covers": ["D3"], "level": level, "confidence": 0.9},
                        {"name": "Check", "reads": "Pages", "writes": "Check report", "does": "Check links, titles and words. " * 6,
                         "covers": ["D4"]}],
            "deliverable": "Check report", "covers_by": "adaptation", "why": "three engines, one for each stage",
            "at": "2026-10-27T12:00:00", "by": "Adaptation"}


def _answer(value, indent=1):
    return "Here is the line:\n```json\n" + json.dumps(value, indent=indent) + "\n```\nThat is all."


def _chunks(text, n):
    return [text[i:i + n] for i in range(0, len(text), n)]


def _run_object(text, n, reader=None):
    r = reader or ST.ObjectReader(_FLOW, throttle=0)
    trail = []
    for c in _chunks(text, n):
        trail.append((r.scanner.n + len(c), ST.Progress(**{k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                                                           for k, v in vars(r.feed(c)).items()})))
    return r, trail


def test_list_reader_reports_each_whole_item():
    text = json.dumps(_flow()["engines"], indent=1)
    r = ST.ListReader(_ENGS, throttle=0)
    seen = {}
    for i, ch in enumerate(text, 1):
        items = r.feed(ch)
        seen.setdefault(len(items), i)
    assert sorted(seen) == [0, 1, 2, 3]
    ends = [m for m in range(len(text)) if text[m] == "}" and text[:m + 1].count("{") == text[:m + 1].count("}")]
    assert ends == [e for e in ends] and len(ends) == 3
    for n, at in ((1, ends[0] + 1), (2, ends[1] + 1)):
        assert seen[n] <= at + 2, "item %d arrived whole near its closing brace (%d vs %d)" % (n, seen[n], at)
    assert seen[1] >= ends[0] and seen[2] >= ends[1], "no item arrives before it is whole"
    assert [e.name for e in r.feed("")] == ["Plan", "Write", "Check"] and r.progress.done


def test_list_reader_reports_a_bad_item_one_element_late():
    eng = _flow(level=7)["engines"]                        # element 1 has a level it cannot have
    text = json.dumps(eng, indent=1)
    r = ST.ListReader(_ENGS, throttle=0)
    second_end = text.index("\n },", text.index('"Write"')) + 4          # the comma after element 1
    third_start = text.index("{", second_end)
    for ch in text[:third_start]:
        r.feed(ch)
    assert r.faults == [], "pydantic ignores every error in the last element, so the fault is not yet known"
    assert [e.name for e in r.items] == ["Plan"], "the bad element is whole as text but is not handed back as a good item"
    r.feed("{")
    assert r.faults == ["$[1].level: is not one of 1, 2"], "one element late, when element 2 begins"
    r.feed(text[third_start + 1:])
    assert r.progress.done and r.faults == ["$[1].level: is not one of 1, 2"]
    ok, found = ST.final(_ENGS, "x " + text)
    assert not ok and found == r.faults


def test_object_reader_progress_early_fault_and_final_agree():
    wf = _flow(level=7)
    text = _answer(wf)
    sc = ST.Scanner()
    sc.feed(text)
    r, trail = _run_object(text, 24)
    first_arrival = {}
    for at, p in trail:
        for k in p.arrived:
            first_arrival.setdefault(k, at)
    assert list(first_arrival)[:3] == ["schema_version", "source", "kind"], first_arrival
    early = next((at for at, p in trail if p.faults), None)
    assert early is not None and early < sc.end - 100, "the fault is found long before the end (%s of %s)" % (early, sc.end)
    assert r.progress.faults == ["$.engines[1].level: is not one of 1, 2"]
    assert r.progress.done and r.progress.arrived[-1] == "by" and r.progress.counts["engines"] == 3
    ok, found = ST.final(_FLOW, text)
    assert not ok and found == r.progress.faults


def test_a_good_stream_never_shows_a_fault():
    text = _answer(_flow())
    for n in (1, 7, 24, 200):
        r, trail = _run_object(text, n)
        assert all(p.faults == [] for _, p in trail), n
        assert r.progress.done
    ok, found = ST.final(_FLOW, text)
    assert ok and found == []
    # the pending sentences describe what has not arrived, and are gone at the end
    r, trail = _run_object(text, 24)
    assert any(p.pending for _, p in trail) and trail[-1][1].pending == []
    assert any("is missing" in s for _, p in trail for s in p.pending)


def test_an_early_fault_is_never_withdrawn_by_the_final():
    rng = random.Random(4)
    for seed in range(200):
        wf = _flow()
        if rng.random() < 0.6:
            e = wf["engines"][rng.randrange(3)]
            e[rng.choice(["level", "internet", "confidence", "name", "covers"])] = rng.choice([7, "x" * 90, [1], None, 2.5, True])
        if rng.random() < 0.2:
            wf["source"] = "elsewhere"
        text = _answer(wf, indent=rng.choice([None, 1, 2]))
        n = rng.choice([1, 5, 24, 61, 300])
        r, trail = _run_object(text, n)
        ok, found = ST.final(_FLOW, text)
        shown = set()
        for _, p in trail:
            assert shown <= set(p.faults), "seed %d: a fault was withdrawn along the way" % seed
            shown |= set(p.faults)
        assert shown <= set(found), "seed %d: an early fault the final does not give: %s vs %s" % (seed, shown, found)
        assert ok == (found == []) and (not ok or not shown)


def test_the_scanner_finds_the_end_through_a_fence_and_a_string_with_braces():
    value = {"a": "close } and ] and \" quote \\ and { open", "b": [1, {"c": "]"}], "d": "x"}
    body = json.dumps(value)
    text = "Prose here.\n```json\n" + body + "\n```\ntrailing } ] text"
    for n in (1, 3, 11, len(text)):
        sc = ST.Scanner()
        for c in _chunks(text, n):
            sc.feed(c)
        assert text[sc.start:sc.end] == body, n
    sc = ST.Scanner()
    sc.feed("[1, [2, 3], \"]\"]")
    assert sc.start == 0 and sc.end == len("[1, [2, 3], \"]\"]") and sc.depth == 0 and sc.elements == 2
    sc = ST.Scanner()
    sc.feed("no json at all")
    assert sc.start is None and sc.end is None


def test_a_cut_off_stream_is_a_final_fault():
    text = _answer(_flow())
    cut = text[:len(text) // 2]
    assert ST.final(_FLOW, cut) == (False, ["the answer stopped before it was whole"])
    assert ST.final(_FLOW, "no json here") == (False, ["the answer stopped before it was whole"])
    assert ST.final(_FLOW, "{not: json}") == (False, ["the answer is not valid JSON"])
    r, trail = _run_object(cut, 24)
    assert not r.progress.done


def test_str9_the_reader_is_bounded():
    big = "{" + ",".join('"k%d": "%s"' % (i, "x" * 1000) for i in range(5200))      # about 5 MB, never closed
    assert len(big) > 5_000_000
    r = ST.ObjectReader(_FLOW, throttle=0)
    peak = 0
    for c in _chunks(big, 64 * 1024):
        r.feed(c)
        peak = max(peak, r.kept)
    assert peak <= ST.CAP and r.kept == ST.CAP and r.over
    assert len(r.text()) == ST.CAP
    assert r.bytes >= 5_000_000, "the byte count still counts what was not kept"
    before = r.progress
    r.feed("more")
    assert r.progress is before or r.progress == before, "past the cap there is no more progress"
    # the caller's final check on the whole text it holds still happens
    ok, found = ST.final(_FLOW, big + "}")
    assert not ok and found


def test_validate_off_loop_slices_a_big_list():
    item = TypeAdapter(_Eng)
    good = {"name": "n", "reads": "r", "writes": "w"}
    items = [dict(good) for _ in range(2600)]
    items[1700] = dict(good, level=7)
    assert ST.size_of(items) > ST.BIG
    beats = {"n": 0}

    async def beat():
        while True:
            await asyncio.sleep(0)
            beats["n"] += 1

    async def run():
        t = asyncio.create_task(beat())
        out = await ST.validate_off_loop(_ENGS, items, item_adapter=item)
        t.cancel()
        return out

    ok, found = asyncio.run(run())
    assert not ok and found == ["$[1700].level: is not one of 1, 2"]
    assert beats["n"] >= 2600 // ST.SLICE, "the loop ran between the slices (%d beats)" % beats["n"]
    # a small value is validated in place; a big one without an item adapter goes to a thread and says the same
    assert asyncio.run(ST.validate_off_loop(_ENGS, items[:3])) == (True, [])
    assert asyncio.run(ST.validate_off_loop(_ENGS, items)) == (False, found)
    assert asyncio.run(ST.validate_off_loop(_ENGS, items[:3], size=ST.BIG + 1)) == (True, [])


# --------------------------------------------------------------------------------------------------------------------------- T5
def test_str7_no_adapter_is_built_per_chunk(monkeypatch):
    """The reader's adapter is built before the first chunk and not again: 1,000 chunks and a final build none."""
    text = _answer(_flow(), indent=None)                        # one answer, fed as 1,000 one-character chunks
    made = {"n": 0}
    real = TypeAdapter.__init__

    def counting(self, *a, **k):
        made["n"] += 1
        return real(self, *a, **k)

    reader = ST.ObjectReader(_FLOW, throttle=0)
    lreader = ST.ListReader(_ENGS, throttle=0)
    monkeypatch.setattr(TypeAdapter, "__init__", counting)
    assert len(text) >= 1000
    for c in _chunks(text, 1)[:1000]:
        reader.feed(c)
    for c in _chunks(json.dumps(_flow()["engines"]), 1)[:1000]:
        lreader.feed(c)
    ST.final(_FLOW, text)
    ST.final(_ENGS, json.dumps(_flow()["engines"]))
    asyncio.run(ST.validate_off_loop(_ENGS, _flow()["engines"]))
    assert made["n"] == 0, "%d adapters were built while streaming" % made["n"]


def test_str7_an_edit_does_not_change_a_stream_in_flight():
    """A stream takes its adapter when it starts: a registry edit between chunks changes its next stream, not this one."""
    from layer_models import registry
    registry.register("t5.flow", _Flow)
    try:
        mine = registry.adapter("t5.flow")                      # taken once, at the start
        r = ST.ObjectReader(mine, throttle=0)
        text = _answer(_flow(level=7))
        verdicts = []
        for i, c in enumerate(_chunks(text, 24)):
            if i == 5:                                          # an edit swaps the definition for new streams
                class _Looser(Closed):
                    schema_version: Annotated[int, Int(1, 1)] = None
                registry.register("t5.flow", _Looser)
                assert registry.adapter("t5.flow") is not mine
            verdicts.append(tuple(r.feed(c).faults))
        assert r.progress.faults == ["$.engines[1].level: is not one of 1, 2"], "the stream kept its own rules"
        assert ST.final(mine, text)[1] == r.progress.faults
        assert ST.final(registry.adapter("t5.flow"), text)[0] is False         # a new stream sees the new rules (extra keys refused)
    finally:
        registry.DEF_CLASS.pop("t5.flow", None)
        registry._ADAPTERS.pop("t5.flow", None)


# --------------------------------------------------------------------------------------------------------------------------- T6
def test_str5_with_an_edit_the_only_difference_is_one_models_frame(monkeypatch):
    """The sessions stream with a bump during poll 3: the golden's bytes plus one `models` frame, in that poll and nowhere else."""
    import app
    from layer_models import bus
    golden = (FIX / "sessions.golden.txt").read_text(encoding="utf-8")
    before = bus.revision()
    box = {}
    text, _ = sessions_frames(app, monkeypatch, hooks={3: lambda: box.setdefault("rev", bus.bump(["x.client", "x.line"]))})
    assert box["rev"] == before + 1
    frame = 'event: models\ndata: {"rev":%d,"keys":["x.client","x.line"]}\n\n' % box["rev"]
    assert frame in text and text.count("event: models") == 1
    assert text.replace(frame, "") == golden, "nothing else in the stream changed"
    assert text.index(frame) > text.index("event: changed") and text.index(frame) < text.index("event: tick")
    # a client that connects after the edit is told nothing of it
    late, _ = sessions_frames(app, monkeypatch)
    assert late == golden


# --------------------------------------------------------------------------------------------------------------------------- T7
import stat  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import textwrap  # noqa: E402

_FAKE_CLAUDE = r'''#!{py}
"""A claude -p that answers the same text whether it is asked for json or stream-json (the test's stand-in)."""
import json, os, sys
argv = sys.argv[1:]
fmt = argv[argv.index("--output-format") + 1]
answer = open(os.environ["FAKE_ANSWER"]).read()
cost = 0.0421
if os.environ.get("FAKE_MODE") == "garbage" and fmt == "stream-json":
    print("this CLI does not stream"); sys.exit(0)
if fmt == "json":
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": answer, "total_cost_usd": cost}}))
else:
    assert "--verbose" in argv and "--include-partial-messages" in argv
    print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s"}}), flush=True)
    for i in range(0, len(answer), 17):
        print(json.dumps({{"type": "stream_event", "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": answer[i:i + 17]}}}}}}), flush=True)
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": answer, "total_cost_usd": cost}}), flush=True)
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    import website_dept as W
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(_FAKE_CLAUDE.format(py=sys.executable), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    ans = tmp_path / "answer.txt"
    monkeypatch.setenv("FAKE_ANSWER", str(ans))
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "dept"))          # never the live records home
    monkeypatch.setattr(W, "_login_path", lambda: str(exe.parent) + os.pathsep + os.environ.get("PATH", ""))

    def say(text):
        ans.write_text(text, encoding="utf-8")
    return W, say


def test_model_json_without_a_callback_is_unchanged(fake_cli, monkeypatch):
    """With on_progress=None the call is the blocking one it has always been: one subprocess.run, the JSON output format, and
    the streaming arm is never entered."""
    W, say = fake_cli
    say(_answer(_flow()))
    entered = []
    monkeypatch.setattr(W, "_stream_run", lambda *a, **k: entered.append(1))
    popen = []
    real_popen = subprocess.Popen

    def popen_spy(args, **k):
        if "stream-json" in args:
            popen.append(1)
        return real_popen(args, **k)

    monkeypatch.setattr(W.subprocess, "Popen", popen_spy)
    seen = {}
    real = subprocess.run

    def spy(args, **kw):
        seen["args"] = list(args)
        return real(args, **kw)

    monkeypatch.setattr(W.subprocess, "run", spy)
    out, usd, why = W.model_json("say ok", timeout=20)
    assert (why, usd) == ("model", 0.0421) and out["engines"][1]["name"] == "Write"
    assert not entered and not popen
    a = seen["args"]
    assert a[a.index("--output-format") + 1] == "json" and "--include-partial-messages" not in a and "--verbose" not in a


def test_model_json_with_a_callback_reports_progress_and_returns_the_same_object(fake_cli):
    W, say = fake_cli
    say(_answer(_flow()))
    plain = W.model_json("say ok", timeout=20)
    got = []
    streamed = W.model_json("say ok", timeout=20, on_progress=got.append, adapter=_FLOW)
    assert streamed == plain and streamed[2] == "model"
    assert len(got) >= 4 and got[-1].done and got[-1].faults == []
    names = [k for p in got for k in p.arrived]
    assert names.index("schema_version") < names.index("kind") and "engines" in names
    assert any(p.counts.get("engines") == 2 for p in got)
    assert all(a.key() != b.key() for a, b in zip(got, got[1:])), "the callback is told only when the progress changes"
    # a list root is read by the list reader
    lg = []
    say("Engines:\n" + json.dumps(_flow()["engines"][:1]))          # today's extraction takes one {...}: an array of one
    out, usd, why = W.model_json("say ok", timeout=20, on_progress=lg.append, root="list", adapter=_ENGS)
    assert out is not None and lg and lg[-1].done


def test_a_bad_final_answer_has_the_same_why(fake_cli):
    W, say = fake_cli
    for text in ("I could not do that.", "{not: json}", "```json\n{\"a\": \n```"):
        say(text)
        plain = W.model_json("x", timeout=20)
        got = []
        assert W.model_json("x", timeout=20, on_progress=got.append) == plain and plain[0] is None, text
    # an answer of the wrong shape is returned as the blocking call returns it, and the final check says so to the callback
    say(_answer(_flow(level=7)))
    got = []
    out, usd, why = W.model_json("x", timeout=20, on_progress=got.append, adapter=_FLOW)
    assert why == "model" and out["engines"][1]["level"] == 7
    assert got[-1].done and got[-1].faults == ["$.engines[1].level: is not one of 1, 2"]
    assert any(p.faults for p in got[:-1]), "and it was found before the end"


def test_the_stream_falls_back_once(fake_cli, monkeypatch):
    W, say = fake_cli
    say(_answer(_flow()))
    monkeypatch.setenv("FAKE_MODE", "garbage")
    calls = []
    real_run, real_popen = subprocess.run, subprocess.Popen
    monkeypatch.setattr(W.subprocess, "run", lambda *a, **k: (calls.append("run"), real_run(*a, **k))[1])
    monkeypatch.setattr(W.subprocess, "Popen", lambda args, **k: ((calls.append("popen") if "stream-json" in args else None), real_popen(args, **k))[1])
    got = []
    out, usd, why = W.model_json("x", timeout=20, on_progress=got.append)
    assert calls == ["popen", "run"], "one streamed attempt, then the blocking call once"
    assert why == "model" and out["kind"] == "website" and got == []


def test_a_slow_stream_times_out_with_the_blocking_words(fake_cli, monkeypatch):
    W, say = fake_cli
    say(_answer(_flow()))
    real = subprocess.Popen

    def slow(args, **kw):
        return real([sys.executable, "-c", "import time; time.sleep(30)"], **kw)

    monkeypatch.setattr(W.subprocess, "Popen", slow)
    out, usd, why = W.model_json("x", timeout=1, on_progress=lambda p: None)
    assert out is None and why.startswith("model call failed:") and "timed out after 1" in why


def test_no_function_step_passes_on_progress():
    """A4-30: the wire is built and wired to nothing. No file of the plugin folder passes on_progress to model_json."""
    hits = []
    for path in sorted(HERE.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if "model_json" not in src:
            continue
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                if name in ("model_json", "_stream_run") and any(k.arg in ("on_progress", None) for k in n.keywords):
                    if path.name != "website_dept.py" or name == "model_json":
                        hits.append("%s:%d" % (path.name, n.lineno))
    assert hits == [], "a call site passes on_progress: %s" % hits
    assert (HERE / "engine_runtime.py").read_text(encoding="utf-8").count("W.model_json(") == 1
    import inspect
    import website_dept as W
    sig = inspect.signature(W.model_json)
    assert sig.parameters["on_progress"].default is None and sig.parameters["abort_on_fault"].default is False
