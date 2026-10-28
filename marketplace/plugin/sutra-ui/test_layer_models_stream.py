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
