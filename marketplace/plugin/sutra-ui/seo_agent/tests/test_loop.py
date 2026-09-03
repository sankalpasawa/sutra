"""tests/test_loop.py — the lifecycle test. Run it after touching loop.py.

Drives the loop through the full lifecycle with a stubbed model and a stubbed tool.
Proves: tools run, the money gate stops, ask_user stops, resume carries on, state survives."""
import os, sys, shutil, types
from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store, registry, loop, llm

# --- a fake tool module, registered as if it were real -------------------------------
# registry names modules relative to the package; the loop resolves them against it.
FAKE_NAME = loop.__package__ + ".tools.fake_tool"
fake = types.ModuleType(FAKE_NAME)
CALLS = []
def _run(ctx, **kw):
    CALLS.append(kw)
    ctx["emit"](type="substep_finished", parent="x", label="did the inner bit", note="42 rows")
    return {"summary": "fake tool ran", "n": 42}
fake.run = _run
sys.modules[FAKE_NAME] = fake
registry.BY_NAME["fake_tool"] = {
    "name": "fake_tool", "description": "d", "gate": "auto", "cost_credits": 0,
    "est_minutes": 1, "module": "tools.fake_tool", "input_schema": {"type":"object","properties":{}}}
registry.BY_NAME["paid_tool"] = {
    "name": "paid_tool", "description": "d", "gate": "ask_before", "cost_credits": 8,
    "est_minutes": 12, "module": "tools.fake_tool", "input_schema": {"type":"object","properties":{}}}

# --- a scripted model ----------------------------------------------------------------
SCRIPT = [
    {"text": "", "tool_calls": [{"id": "t1", "name": "log_step", "input": {"message": "Reading the site"}},
                                {"id": "t2", "name": "fake_tool", "input": {"a": 1}}]},
    {"text": "", "tool_calls": [{"id": "t3", "name": "paid_tool", "input": {}}]},
    {"text": "", "tool_calls": [{"id": "t5", "name": "ask_user",
                                 "input": {"question": "Which angle?", "why": "It changes the outline.",
                                           "options": [{"label": "A", "recommended": True}, {"label": "B"}]}}]},
    {"text": "All done. Draft is ready.", "tool_calls": []},
]
step_i = {"n": 0}
def fake_call(system, messages, tools=None, model=None, **kw):
    r = SCRIPT[min(step_i["n"], len(SCRIPT)-1)]; step_i["n"] += 1; return r
llm.call = fake_call

# --- drive it ------------------------------------------------------------------------
c = store.new_chat("loop test")
r = store.new_run(c, "test topic")
FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))

s = loop.start(c, r, "write me an article")
ok("stops at the paid gate", s["status"] == "waiting" and s["waiting_on"]["kind"] == "approval")
ok("names the cost", s["waiting_on"]["cost_credits"] == 8)
ok("ran the free tool first", len(CALLS) == 1)
ok("logged a human line", any(e["type"] == "note" for e in store.get_events(c, r)))
ok("emitted a substep", any(e["type"] == "substep_finished" for e in store.get_events(c, r)))

# state survives a "restart": re-read from disk only
s2 = store.get_state(c, r)
ok("state survives on disk", s2["status"] == "waiting" and s2["waiting_on"]["tool"] == "paid_tool")

s = loop.resume(c, r, {"approved": True})
ok("approval runs the tool and moves on to the question",
   s["status"] == "waiting" and s["waiting_on"]["kind"] == "question", s.get("waiting_on"))
ok("the approved tool ran exactly once", len(CALLS) == 2, len(CALLS))
ok("credits were counted", s.get("credits_spent") == 8)
ok("the question came through", s["waiting_on"]["question"] == "Which angle?")

s = loop.resume(c, r, {"choice": "A"})
ok("finishes after the answer", s["status"] == "done")

evs = [e["type"] for e in store.get_events(c, r)]
ok("run_finished emitted", "run_finished" in evs)
ok("event order is sane", evs.index("step_started") < evs.index("run_finished"))

# a declined approval must not run the tool
c2 = store.new_chat("decline test"); r2 = store.new_run(c2, "t")
step_i["n"] = 1; before = len(CALLS)
loop.start(c2, r2, "go")
s = loop.resume(c2, r2, {"approved": False})
ok("declining does not run the paid tool", len(CALLS) == before)

print("\nevents in run 1:", evs)
shutil.rmtree(store.chat_dir(c)); shutil.rmtree(store.chat_dir(c2))

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % 14)
