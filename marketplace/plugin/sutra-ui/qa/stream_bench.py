#!/usr/bin/env python3
"""The streaming benchmark (PRD amendment A4.7.7): the sessions stream must not be slower, later or heavier for the pydantic layer.

    python qa/stream_bench.py --check              measure, compare with test_fixtures/stream/baseline.json, print one line, exit 0/1
    python qa/stream_bench.py --capture-baseline   measure and write the baseline (run it on unchanged main: the baseline is what
                                                   the streams did before A4)

What is measured, on this machine, against the app's own generators:

  first byte    a real local server (uvicorn in a thread, sr.index stubbed to 200 sessions), a raw socket, 20 connections: the
                median and p95 of the time to the first `sync` byte
  gap           20 generators on one loop for 3 s with a 100 Hz ticker on the same loop: the ticker's lag, p99
  events        frames one generator yields in a second with its sleeps patched out, the same load
  memory        tracemalloc peak growth over a short run of the same load
  A/B           the same load with `bus.revision` patched to a constant, alternated with the real one: within 5%
  beside        stream A at a 5 ms cadence while B validates a 5 MB value off the loop and then runs a 0.5 s validator off the
                loop: A's gap p99 at most 60 ms; and while 60 models of 40 fields are compiled in a worker: A's lag at most 50 ms

The absolute thresholds (first byte, gap, events, memory) are checked only on the machine the baseline was taken on (same node
name and core count); elsewhere a line says so and the A/B and the two `beside` cases, which need no baseline, still run. A
machine in use by other work makes a number noisy, so a failing case is measured up to three times and passes if any round does.
The lane's budget is 20 s."""
import argparse
import asyncio
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
sys.path.insert(0, str(UI))
BASELINE = UI / "test_fixtures" / "stream" / "baseline.json"
SESSIONS = 200

_real_sleep = asyncio.sleep


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(int(len(xs) * p) - 1, 0))] if xs else 0.0


class Load:
    """The sessions stream over a scripted index of `n` sessions, every poll changing every session (the heaviest frame)."""

    def __init__(self, n=SESSIONS, changing=True):
        import app
        self.app, self.n, self.changing, self.tick = app, n, changing, 0
        self._index, self._live, self._poll, self._beat = app.sr.index, app.sr.liveness, app.SESSION_POLL_S, app.SESSION_HEARTBEAT_S

    def index(self):
        self.tick += 1 if self.changing else 0
        return {"s%04d" % i: {"mtime": self.tick, "size": self.tick, "agents_bytes": 0, "title": "session %d" % i}
                for i in range(self.n)}

    def __enter__(self):
        self.app.sr.index, self.app.sr.liveness = self.index, lambda m: "idle"
        return self

    def __exit__(self, *a):
        self.app.sr.index, self.app.sr.liveness = self._index, self._live
        self.app.SESSION_POLL_S, self.app.SESSION_HEARTBEAT_S = self._poll, self._beat


# ---- first byte -------------------------------------------------------------------------------------------------------------
def first_byte(n=20):
    import uvicorn
    app = __import__("app")
    with Load(changing=False):
        server = uvicorn.Server(uvicorn.Config(app.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
        threading.Thread(target=server.run, daemon=True).start()
        deadline = time.time() + 20
        while not server.started and time.time() < deadline:
            time.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        req = ("GET /api/sessions/stream HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n").encode()
        ms = []
        for i in range(n + 1):
            t0 = time.perf_counter()
            s = socket.create_connection(("127.0.0.1", port), timeout=10)
            s.sendall(req)
            buf = b""
            while b"event: sync" not in buf:
                buf += s.recv(65536)
            if i:                                    # the first connection warms the route
                ms.append((time.perf_counter() - t0) * 1000)
            s.close()
        server.should_exit = True
    return {"first_byte_ms": round(statistics.median(ms), 3), "first_byte_p95_ms": round(pct(ms, 0.95), 3)}


# ---- the loop's lag with streams running ------------------------------------------------------------------------------------
async def _ticker(lags, stop, every=0.01):
    last = time.perf_counter()
    while not stop.is_set():
        await _real_sleep(every)
        now = time.perf_counter()
        lags.append(max((now - last - every) * 1000, 0.0))
        last = now


async def _drain(resp, counter, stop):
    it = resp.body_iterator
    try:
        while not stop.is_set():
            await it.__anext__()
            counter[0] += 1
    finally:
        await it.aclose()


def gap(seconds=3.0, streams=20, poll=0.1):
    app = __import__("app")

    async def run():
        stop, lags, count = asyncio.Event(), [], [0]
        app.SESSION_POLL_S = poll
        gens = [await app.api_sessions_stream() for _ in range(streams)]
        tasks = [asyncio.create_task(_drain(g, count, stop)) for g in gens]
        tick = asyncio.create_task(_ticker(lags, stop))
        await _real_sleep(seconds)
        stop.set()
        await asyncio.gather(tick, *tasks, return_exceptions=True)
        return lags

    with Load():
        lags = asyncio.run(run())
    return {"gap_p99_ms": round(pct(lags, 0.99), 3)}


def events(seconds=0.6):
    """Frames one generator yields in `seconds` with its sleeps patched out."""
    app = __import__("app")

    async def fast(s):
        await _real_sleep(0)

    async def run():
        resp = await app.api_sessions_stream()
        it, n, end = resp.body_iterator, 0, time.perf_counter() + seconds
        while time.perf_counter() < end:
            await it.__anext__()
            n += 1
        await it.aclose()
        return n / seconds

    real = app.asyncio.sleep
    app.asyncio.sleep = fast
    try:
        with Load():
            return asyncio.run(run())
    finally:
        app.asyncio.sleep = real


def memory(seconds=1.0):
    app = __import__("app")
    with Load():
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        try:
            async def run():
                stop, count = asyncio.Event(), [0]
                app.SESSION_POLL_S = 0.05
                gens = [await app.api_sessions_stream() for _ in range(20)]
                tasks = [asyncio.create_task(_drain(g, count, stop)) for g in gens]
                await _real_sleep(seconds)
                stop.set()
                await asyncio.gather(*tasks, return_exceptions=True)
            asyncio.run(run())
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    return {"mem_growth_mb": round((peak - base) / 1e6, 3)}


def ab(rounds=5):
    """Events a second with the real `bus.revision` and with a constant, alternated; the difference of the medians."""
    app = __import__("app")
    from layer_models import bus
    if not hasattr(app, "models_bus"):
        return None
    real, with_bus, without = bus.revision, [], []
    try:
        for _ in range(rounds):
            bus.revision = real
            with_bus.append(events(0.4))
            bus.revision = lambda: 0
            without.append(events(0.4))
    finally:
        bus.revision = real
    a, b = statistics.median(with_bus), statistics.median(without)
    return {"ab_diff_pct": round((b - a) / b * 100, 2), "events_per_s_with": round(a), "events_per_s_without": round(b)}


# ---- a big value beside a stream --------------------------------------------------------------------------------------------
def beside(work, seconds=4.0):
    """The gap p99 (ms) of a stream at a 5 ms cadence while `work()` (an async function) runs beside it."""
    app = __import__("app")
    stamps = []

    async def watch(resp, stop):
        it = resp.body_iterator
        while not stop.is_set():
            await it.__anext__()
            stamps.append(time.perf_counter())
        await it.aclose()

    async def run():
        app.SESSION_POLL_S, app.SESSION_HEARTBEAT_S = 0.005, 0           # a tick every poll: a frame every 5 ms
        stop = asyncio.Event()
        resp = await app.api_sessions_stream()
        w = asyncio.create_task(watch(resp, stop))
        await _real_sleep(0.3)
        mark = len(stamps)
        await work()
        await _real_sleep(0.1)
        stop.set()
        await asyncio.gather(w, return_exceptions=True)
        return [(b - a) * 1000 - 5 for a, b in zip(stamps[mark:], stamps[mark + 1:])]

    with Load(n=20, changing=False):
        gaps = asyncio.run(run())
    return round(pct([max(g, 0.0) for g in gaps], 0.99), 3)


def slow_validators():
    from pydantic import BaseModel, TypeAdapter, field_validator
    from layer_models import stream as ST

    class Row(BaseModel):
        name: str
        note: str

    class Slow(BaseModel):
        n: int

        @field_validator("n")
        @classmethod
        def slow(cls, v):
            end = time.perf_counter() + 0.5
            while time.perf_counter() < end:        # CPU-bound, 0.5 s
                pass
            return v

    big = [{"name": "engine %d" % i, "note": "x" * 100} for i in range(38000)]          # about 5 MB as JSON
    assert 4.5e6 < len(json.dumps(big)) < 6e6
    rows, slow = TypeAdapter(list[Row]), TypeAdapter(Slow)

    async def work():
        ok, found = await ST.validate_off_loop(rows, big)
        assert ok and not found
        ok, found = await ST.validate_off_loop(slow, {"n": 1}, size=ST.BIG + 1)
        assert ok and not found

    return {"slow_validator_gap_p99_ms": beside(work, 4.0)}


def large_compile():
    from pydantic import TypeAdapter, create_model

    def compile_all():
        for m in range(60):
            fields = {"f%d" % i: (str, ...) for i in range(40)}
            TypeAdapter(create_model("Bench%d" % m, **fields))

    async def work():
        import anyio.to_thread
        await anyio.to_thread.run_sync(compile_all)

    return {"compile_lag_ms": beside(work, 3.0)}


# ---- the check --------------------------------------------------------------------------------------------------------------
def machine():
    return {"node": platform.node(), "cores": os.cpu_count()}


def measure_all():
    out = {}
    out.update(first_byte())
    out.update(gap())
    out["events_per_s"] = round(events())
    out.update(memory())
    return out


def judge(m, base, same_machine):
    """[(name, ok, text)] for the numbers in `m`."""
    rows = []
    if same_machine and base:
        rows.append(("first byte", m["first_byte_ms"] <= max(1.5 * base["first_byte_ms"], base["first_byte_ms"] + 15), "median"))
        rows.append(("gap", m["gap_p99_ms"] <= max(1.5 * base["gap_p99_ms"], 25.0), "p99"))
        rows.append(("events", m["events_per_s"] >= 0.9 * base["events_per_s"], "per second"))
        rows.append(("memory", m["mem_growth_mb"] <= base["mem_growth_mb"] + 8.0, "growth"))
    return rows


def check():
    t0 = time.perf_counter()
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
    same = bool(base) and base.get("node") == platform.node() and base.get("cores") == os.cpu_count()
    if not same:
        print("stream bench: the baseline is from another machine (%s, %s cores); the absolute thresholds are skipped, "
              "the A/B and the beside-a-stream cases still run" % (base and base.get("node"), base and base.get("cores")))
    failed, m = [], {}
    for attempt in range(3):
        m = measure_all()
        failed = [n for n, ok, _ in judge(m, base, same) if not ok]
        if not failed:
            break
    ab_result, verdicts = None, []
    for attempt in range(3):
        ab_result = ab()
        if ab_result is None or abs(ab_result["ab_diff_pct"]) <= 5.0:
            break
    sv = lc = None
    for attempt in range(3):
        sv = slow_validators()
        if sv["slow_validator_gap_p99_ms"] <= 60.0:
            break
    for attempt in range(3):
        lc = large_compile()
        if lc["compile_lag_ms"] <= 50.0:
            break
    if ab_result is not None and abs(ab_result["ab_diff_pct"]) > 5.0:
        failed.append("A/B")
    if sv["slow_validator_gap_p99_ms"] > 60.0:
        failed.append("a slow validator beside a stream")
    if lc["compile_lag_ms"] > 50.0:
        failed.append("a large compile beside a stream")
    secs = time.perf_counter() - t0
    print("stream bench: first byte %.1f ms (p95 %.1f), gap p99 %.1f ms, %d events/s, memory +%.1f MB, A/B %s, "
          "slow validator beside a stream p99 %.1f ms, compile beside a stream %.1f ms (%.0f s)%s"
          % (m["first_byte_ms"], m["first_byte_p95_ms"], m["gap_p99_ms"], m["events_per_s"], m["mem_growth_mb"],
             ("%+.1f%%" % ab_result["ab_diff_pct"]) if ab_result else "n/a (no bus in this app)",
             sv["slow_validator_gap_p99_ms"], lc["compile_lag_ms"], secs,
             ("; FAILED: " + ", ".join(failed)) if failed else ""))
    return 1 if failed else 0


def capture(path):
    m = measure_all()
    doc = dict(machine(), recorded_from="main before A4-STREAM (unchanged streams)", **m)
    Path(path).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("stream bench: baseline written to %s: %s" % (path, json.dumps(m)))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--capture-baseline", action="store_true")
    ap.add_argument("--baseline", default=str(BASELINE), help="where --capture-baseline writes")
    a = ap.parse_args(argv)
    import tempfile
    for var in ("SUTRA_NATIVE_HOME", "SUTRA_UI_CHATS", "SEO_AGENT_DATA", "SUTRA_SHADOW_HOME", "SUTRA_NATIVE_DEPT_HOME"):
        os.environ.setdefault(var, tempfile.mkdtemp(prefix="sutra-bench-"))      # a benchmark never touches the live homes
    if a.capture_baseline:
        return capture(a.baseline)
    return check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
