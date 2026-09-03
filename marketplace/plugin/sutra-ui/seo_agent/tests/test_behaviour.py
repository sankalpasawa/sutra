"""tests/test_behaviour.py — the claims the spec makes, checked against the real thing.

Not plumbing. Behaviour: one chat can hold several runs, a broken tool goes amber and the
agent gets told, a crash in a tool never takes the run down silently, and the autonomy cap
actually stops a runaway.
"""
import os
import shutil
import sys
import types

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, loop, registry, store

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))

# a tool that always explodes, and one that always works
PKG = loop.__package__
bad = types.ModuleType(PKG + ".tools.bad_tool")
def _bad(ctx, **kw):
    raise RuntimeError("DataForSEO returned a row without a volume field")
bad.run = _bad
sys.modules[PKG + ".tools.bad_tool"] = bad
good = types.ModuleType(PKG + ".tools.good_tool")
RAN = []
def _good(ctx, **kw):
    RAN.append(1)
    return {"summary": "fine"}
good.run = _good
sys.modules[PKG + ".tools.good_tool"] = good
for n, m in (("bad_tool", "tools.bad_tool"), ("good_tool", "tools.good_tool")):
    registry.BY_NAME[n] = {"name": n, "description": "d", "gate": "auto", "cost_credits": 0,
                           "est_minutes": 1, "module": m,
                           "input_schema": {"type": "object", "properties": {}}}


def script(seq):
    i = {"n": 0}
    def call(system, messages, tools=None, model=None, **kw):
        r = seq[min(i["n"], len(seq) - 1)]
        i["n"] += 1
        return r
    return call


print("\none chat holds several runs")
c = store.new_chat("multi")
llm.call = script([{"text": "", "tool_calls": [{"id": "x1", "name": "good_tool", "input": {}}]},
                   {"text": "first done", "tool_calls": []}])
r1 = store.new_run(c, "first article")
loop.start(c, r1, "write about A")
llm.call = script([{"text": "", "tool_calls": [{"id": "y1", "name": "good_tool", "input": {}}]},
                   {"text": "second done", "tool_calls": []}])
r2 = store.new_run(c, "second article")
loop.start(c, r2, "now write about B")
runs = store.list_runs(c)
ok("two runs in one chat", len(runs) == 2, len(runs))
ok("separate folders", os.path.isdir(store.run_dir(c, r1)) and os.path.isdir(store.run_dir(c, r2)))
ok("separate event logs",
   len(store.get_events(c, r1)) > 0 and len(store.get_events(c, r2)) > 0)
ok("one shared conversation", len(store.get_messages(c)) > 4, len(store.get_messages(c)))
ok("both finished", all(store.get_state(c, x)["status"] == "done" for x in (r1, r2)))

print("\na tool that breaks goes amber, and the agent is told")
c2 = store.new_chat("break")
r3 = store.new_run(c2, "breaks")
seen = {}
def watching(system, messages, tools=None, model=None, **kw):
    # capture what the model was handed after the failure
    last = messages[-1]
    if isinstance(last.get("content"), list):
        for b in last["content"]:
            if b.get("type") == "tool_result":
                seen["result"] = b.get("content")
    if "n" not in seen:
        seen["n"] = 0
    seen["n"] += 1
    if seen["n"] == 1:
        return {"text": "", "tool_calls": [{"id": "b1", "name": "bad_tool", "input": {}}]}
    return {"text": "That failed. Trying another way.", "tool_calls": []}
llm.call = watching
loop.start(c2, r3, "go")
evs = store.get_events(c2, r3)
failed = [e for e in evs if e["type"] == "step_failed"]
ok("a failure was logged", len(failed) == 1, len(failed))
ok("it is marked recovering, so the screen shows amber not red",
   failed and failed[0].get("recovering") is True)
ok("the real reason is kept", failed and "volume field" in (failed[0].get("reason") or ""))
ok("a traceback is kept for debugging", failed and bool(failed[0].get("detail")))
ok("the agent was told what failed",
   "error" in (seen.get("result") or {}), seen.get("result"))
ok("the agent was told to say so",
   "hint" in (seen.get("result") or {}))
ok("the run did NOT die", store.get_state(c2, r3)["status"] == "done")

print("\nthe autonomy cap stops a runaway")
c3 = store.new_chat("runaway")
r4 = store.new_run(c3, "loop forever")
llm.call = script([{"text": "", "tool_calls": [{"id": "z", "name": "good_tool", "input": {}}]}])
before = len(RAN)
s = loop.start(c3, r4, "go")
ok("it stopped itself", s["status"] == "waiting", s["status"])
ok("it asked rather than dying", (s.get("waiting_on") or {}).get("kind") == "question")
ok("it stopped at the cap, not before",
   len(RAN) - before == loop.AUTONOMY_LIMIT, len(RAN) - before)

for x in (c, c2, c3):
    shutil.rmtree(store.chat_dir(x), ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all behaviour checks passed")
