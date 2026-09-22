"""tests/test_stop_resume.py — Stop reaches work in flight, and a message after a user Stop
continues the same run. Written for the two bugs fixed 2026-09-16.

Seen for real in chat c-f1a6e19c: Stop was pressed at 06:27:08 in run r-115458, the research
step ran on to 06:28:13 (a minute of model calls and DataForSEO spend after the person said
stop), and the next message then opened a brand-new, empty run r-115816 -- stranding the
research the stopped run had already finished and saved.

Proves, with a scripted model and fake tools (no real claude process, no network, no real
DataForSEO call anywhere in this file):

  the kill      llm.stop_run reaches a real subprocess blocked mid-answer, ends it fast, and the
                call comes back as llm.Stopped, not a finished result.
  the boundary  dfs._send, web.fetch and research._common.cached all refuse to start once the
                run they belong to is stopped -- check_stop()'s own promise, proved at each site.
  the batch     when a tool the loop is running comes back with llm.Stopped: its step row closes
                (not left spinning), the tool call it answers is closed so the saved turn is
                whole, nothing else the model asked for in the same turn is started, and the
                model is not asked again.
  loop.stop     reaches a registered run's llm gate, not just the state file.
  the resume    a message after a user Stop continues the SAME run id, from its saved steps --
                exactly like the restart-sweep and the failure path already did.
  no dup worker a run already running never gets a second worker for the same key.
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import types

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, registry, store, loop

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agents_api as api  # noqa: E402

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))


# ============================================================================================
print("\nllm.stop_run reaches a real subprocess blocked mid-answer, and is fast")

with llm.run_slot("stopkill", "r1"):
    key = "stopkill/r1"
    holder = {}

    def _slow_call():
        llm._bind(key)   # this thread now belongs to the run, the way llm.pool()'s workers do
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        t0 = time.time()
        try:
            llm._run_process(cmd, "", 30.0)
            holder["result"] = "finished"
        except llm.Stopped:
            holder["result"] = "stopped"
        except subprocess.TimeoutExpired:
            holder["result"] = "timed out"
        holder["elapsed"] = time.time() - t0

    th = threading.Thread(target=_slow_call)
    th.start()
    time.sleep(0.4)   # let the subprocess actually start before killing it
    t_stop = time.time()
    reached = llm.stop_run("stopkill", "r1")
    th.join(10.0)
    stop_elapsed = time.time() - t_stop

ok("stop_run finds the live run and reaches it", reached is True)
ok("the call ends with Stopped, not a finished 5s sleep", holder.get("result") == "stopped", holder)
ok("the kill lands fast -- well under the 5s the process was sleeping for",
   stop_elapsed < 3.0, stop_elapsed)
ok("a stop_run for a run nobody registered is a quiet False, never a crash",
   llm.stop_run("no-such-chat", "no-such-run") is False)


# ============================================================================================
print("\ncheck_stop is wired at every boundary the write-up promises, so a stopped run buys nothing new")
from seo_agent.tools import dfs as _dfs               # noqa: E402
from seo_agent.research import web as _web, _common as _rc   # noqa: E402

with llm.run_slot("boundary-chat", "boundary-run"):
    llm.stop_run("boundary-chat", "boundary-run")

    try:
        _dfs._send("get", "/appendix/user_data")
        ok("dfs._send refuses a stopped run before the paid call", False, "did not raise")
    except llm.Stopped:
        ok("dfs._send refuses a stopped run before the paid call", True)

    try:
        _web.fetch("https://example.invalid/never-reached")
        ok("web.fetch refuses a stopped run before reading a page", False, "did not raise")
    except llm.Stopped:
        ok("web.fetch refuses a stopped run before reading a page", True)

    produced = {"n": 0}
    try:
        _rc.cached({"chat_id": "boundary-chat", "run_id": "boundary-run"}, "x", False,
                  lambda: produced.update(n=produced["n"] + 1) or {"ok": True})
        ok("research._common.cached refuses a stopped run before a research step", False, "did not raise")
    except llm.Stopped:
        ok("research._common.cached refuses a stopped run before a research step", True)
    ok("...and it never even called produce()", produced["n"] == 0, produced)


# ============================================================================================
print("\nStop mid-tool: the batch closes clean, nothing after it starts")

FAKE_PKG = loop.__package__ + ".tools"
STARTED, NEVER_STARTED = [], []


def _register(mod_name, fn):
    mod = types.ModuleType(FAKE_PKG + "." + mod_name)
    mod.run = fn
    sys.modules[mod.__name__] = mod
    registry.BY_NAME[mod_name] = {
        "name": mod_name, "description": "d", "gate": "auto", "cost_credits": 0,
        "est_minutes": 1, "module": "tools." + mod_name, "input_schema": {"type": "object", "properties": {}}}


def _stoppable(ctx, **kw):
    STARTED.append(kw)
    # The real timing: the API's stop route writes "stopped" to disk BEFORE the kill reaches
    # the tool's own model call, which is what then raises Stopped at its next boundary.
    store.patch_state(ctx["chat_id"], ctx["run_id"], status="stopped")
    raise llm.Stopped("test: process killed mid-answer")


def _never(ctx, **kw):
    NEVER_STARTED.append(kw)
    return {"summary": "should never have run"}


_register("stoppable_tool", _stoppable)
_register("never_tool", _never)

SCRIPT = [{"text": "", "tool_calls": [{"id": "t1", "name": "stoppable_tool", "input": {}},
                                      {"id": "t2", "name": "never_tool", "input": {}}]},
          {"text": "should never be reached", "tool_calls": []}]
step_i = {"n": 0}


def fake_call(system, messages, tools=None, model=None, **kw):
    r = SCRIPT[min(step_i["n"], len(SCRIPT) - 1)]; step_i["n"] += 1; return r


llm.call = fake_call

c = store.new_chat("stop mid tool")
r = store.new_run(c, "test topic")
s = loop.start(c, r, "write me an article")

ok("the run ends stopped, not crashed and not carrying on to another model turn",
   s["status"] == "stopped", s["status"])
ok("only the model's first turn was used: nothing after the stop was asked of it",
   step_i["n"] == 1, step_i["n"])
ok("the tool that was running actually ran once", len(STARTED) == 1, len(STARTED))
ok("the second tool call in the SAME batch never started",
   len(NEVER_STARTED) == 0, len(NEVER_STARTED))

evs = store.get_events(c, r)
started_evt = next(e for e in evs if e["type"] == "step_started")
finished_evt = next((e for e in evs if e["type"] == "step_finished" and e.get("id") == started_evt["id"]), None)
ok("the step row is closed, not left spinning forever",
   finished_evt is not None and finished_evt.get("stopped") is True, finished_evt)

msgs = store.get_messages(c)
last = msgs[-1]
ok("the turn is saved whole: every tool_use id from that turn has a tool_result",
   last["role"] == "user" and {b["tool_use_id"] for b in last["content"]} == {"t1", "t2"}, last)
t2_result = next(b for b in last["content"] if b["tool_use_id"] == "t2")
ok("the tool call that never started says so, not a generic error",
   "stopped the run first" in t2_result["content"].get("error", ""), t2_result)

shutil.rmtree(store.chat_dir(c))


# ============================================================================================
print("\nloop.stop reaches a registered run, not just the state file")

with llm.run_slot("regchat", "regrun"):
    key = "regchat/regrun"
    run_obj = llm._GATE.find(key)
    ok("the run is registered while its slot is open", run_obj is not None)
    loop.stop("regchat", "regrun")
    ok("loop.stop flags the registered run stopped", run_obj.is_stopped() is True)


# ============================================================================================
print("\na message after a user Stop continues the SAME run")


def done_call(system, messages, tools=None, model=None, **kw):
    return {"text": "All done.", "tool_calls": []}


def _wait_idle(chat_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with api._lock:
            alive = [t for k, t in api._workers.items() if k.startswith(chat_id) and t.is_alive()]
        if not alive:
            return True
        time.sleep(0.05)
    return False


llm.call = done_call

c2 = store.new_chat("stop then continue")
r2 = store.new_run(c2, "some topic")
store.patch_state(c2, r2, status="running")
store.save_messages(c2, [{"role": "user", "content": "go"}])
loop.stop(c2, r2)

ok("agents_api reads the last stop back as 'user'", api._last_stopped_by(c2, r2) == "user",
   api._last_stopped_by(c2, r2))

res = api.api_send(c2, {"text": "carry on"})
ok("the SAME run id is continued, not a new run", res.get("run_id") == r2 and res.get("continued") is True, res)
ok("no second run was created for this chat", len(store.list_runs(c2)) == 1, store.list_runs(c2))

_wait_idle(c2)
ok("the continued run actually finished", store.get_state(c2, r2).get("status") == "done",
   store.get_state(c2, r2))
note = next((e.get("note") for e in store.get_events(c2, r2) if e["type"] == "resumed"), None)
ok("the resumed note says it carried on after a stop, not after a restart or a failure",
   note == "carrying on after you stopped it, from the steps already saved", note)

shutil.rmtree(store.chat_dir(c2))


# ============================================================================================
print("\nregression: the restart-sweep and failure paths still continue the same run")

llm.call = done_call

c3 = store.new_chat("restart continue")
r3 = store.new_run(c3, "topic")
store.patch_state(c3, r3, status="running")
store.save_messages(c3, [{"role": "user", "content": "go"}])
store.emit(c3, r3, "stopped", by="restart")
store.patch_state(c3, r3, status="stopped", waiting_on=None)
ok("_last_stopped_by reads back 'restart'", api._last_stopped_by(c3, r3) == "restart")
res = api.api_send(c3, {"text": "carry on"})
ok("a restart-stopped run is still continued, not started over",
   res.get("run_id") == r3 and res.get("continued") is True, res)
_wait_idle(c3)
shutil.rmtree(store.chat_dir(c3))

c4 = store.new_chat("failed continue")
r4 = store.new_run(c4, "topic")
store.patch_state(c4, r4, status="failed", error="boom")
store.save_messages(c4, [{"role": "user", "content": "go"}])
res = api.api_send(c4, {"text": "carry on"})
ok("a failed run is still continued, not started over",
   res.get("run_id") == r4 and res.get("continued") is True, res)
_wait_idle(c4)
shutil.rmtree(store.chat_dir(c4))


# ============================================================================================
print("\nno second worker starts for a run already running")

started_evt2, release_evt = threading.Event(), threading.Event()


def _blocking():
    started_evt2.set()
    release_evt.wait(5.0)


dedup_key = "dedup-test-key"
with api._lock:
    api._workers.pop(dedup_key, None)
first = api._spawn(dedup_key, _blocking)
started_evt2.wait(2.0)
second = api._spawn(dedup_key, _blocking)
ok("the first spawn starts a worker", first is True)
ok("a second spawn for the same key while the first is alive is refused",
   second is False)
release_evt.set()
with api._lock:
    t = api._workers.get(dedup_key)
if t:
    t.join(2.0)


# ============================================================================================
print("\nthe events route never hands back a status newer than the events beside it")
# A checkpoint is marked in TWO writes -- loop._wait patches state to "waiting" and only then
# emits the "waiting" event -- and this route reads the two from two files while the engine
# thread is writing them. One side is always allowed to be the older, and which one decides
# what a person sees: state newer than events is a screen saying "waiting for you" with the
# question missing, which is the SustVest report of 2026-09-22. Events newer than state is a
# question that shows up a tick before the footer catches up, which reads as still working.
# So state must be read FIRST. This pins the order, not the wording.
c7 = store.new_chat("read order")
r7 = store.new_run(c7, "topic")
store.patch_state(c7, r7, status="running")
_order = []
_real_state, _real_events = store.get_state, store.get_events
store.get_state = lambda *a, **k: (_order.append("state"), _real_state(*a, **k))[1]
store.get_events = lambda *a, **k: (_order.append("events"), _real_events(*a, **k))[1]
try:
    api.api_events(c7, r7, since=0)
finally:
    store.get_state, store.get_events = _real_state, _real_events
ok("state is read before the events, so it can only ever be the older of the two",
   _order == ["state", "events"], _order)
shutil.rmtree(store.chat_dir(c7))


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all stop/resume checks passed")
