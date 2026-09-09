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

print("\nthe setup interview never blocks, whatever the user does with it")
# Its own data dir: this writes real brand files and every suite in one run shares SEO_AGENT_DATA.
import tempfile
_prev_data = os.environ.get("SEO_AGENT_DATA", "")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-onboard-behaviour-")
store.set_data_dir(os.environ["SEO_AGENT_DATA"])
_fixture.setup()
from seo_agent.brand import _common as cm, brand_facts
from seo_agent.tools import _shared as sh, onboard

llm.json_call = lambda prompt, system=None, retries=1, **kw: _fixture.stub_json(prompt, system, retries)
llm.text = lambda prompt, system=None, **kw: _fixture.stub_text(prompt, system)

c4 = store.new_chat("skips everything")
r5 = store.new_run(c4, "setup")
llm.call = script([{"text": "", "tool_calls": [{"id": "ob", "name": "onboard", "input": {}}]},
                   {"text": "Nothing to note then.", "tool_calls": []}])
s = loop.start(c4, r5, "set me up")
asked = []
while s["status"] == "waiting" and (s.get("waiting_on") or {}).get("interview"):
    asked.append(s["waiting_on"]["interview"])
    s = loop.resume(c4, r5, {"choice": onboard.SKIP_LABEL})
ok("every question was still put, one at a time", asked == onboard.IDS, asked)
ok("skipping the lot does not stall the run", s["status"] == "done", s["status"])
led = onboard.ledger().get("answers") or {}
ok("all four are on record as skipped, none as an empty answer",
   len(led) == 4 and all(a["state"] == "skipped" and a["text"] == "" for a in led.values()), led)
ok("no competitor list was invented from an empty answer",
   store.knowledge("competitors.json") is None, store.knowledge("competitors.json"))

# The point of the whole design: answering (or skipping) must not cost the machine draft. If the
# block looked like a confirmed row, brand-facts would skip drafting the numbers the site DOES
# publish and the user would be worse off for having been asked.
stats_before = store.knowledge("brand/stats.md") or ""
ok("the file records that it asked and got nothing", "Not answered" in stats_before)
ok("but nothing in the block reads as a confirmed row",
   not brand_facts.human_confirmed(stats_before) and not brand_facts.already_drafted(stats_before))
out = brand_facts.run(sh.company(), lambda a, b="": None)
stats_after = store.knowledge("brand/stats.md") or ""
ok("so the brand pack still builds over the top", "stats.md" in (out.get("files") or []), out)
ok("the machine still drafted the numbers the site does publish",
   brand_facts.already_drafted(stats_after), stats_after[:400])
ok("and the record of what was asked survived it",
   "<!-- setup-interview:start -->" in stats_after)
print("\nan interview that was abandoned picks up where it stopped")
store.save_knowledge("brand/_interview/answers.json", {})
for f in ("stats.md", "stories.md"):
    p = cm.path(f)
    if os.path.exists(p):
        os.remove(p)
c5 = store.new_chat("abandoned")
r6 = store.new_run(c5, "setup")
llm.call = script([{"text": "", "tool_calls": [{"id": "ob", "name": "onboard", "input": {}}]},
                   {"text": "ok", "tool_calls": []}])
loop.start(c5, r6, "set me up")
loop.resume(c5, r6, {"text": "About 1,500 teams."})
loop.stop(c5, r6)                     # they close the app halfway through
ok("what they already said is on disk, not held in a run that is gone",
   "About 1,500 teams." in (store.knowledge("brand/stats.md") or ""))
ok("the interview is not marked as asked", onboard.status()["asked"] is False, onboard.status())
r7 = store.new_run(c5, "setup, later")
llm.call = script([{"text": "", "tool_calls": [{"id": "ob2", "name": "onboard", "input": {}}]},
                   {"text": "ok", "tool_calls": []}])
s = loop.start(c5, r7, "carry on")
ok("a later run resumes at the next unanswered question, not the first",
   (s.get("waiting_on") or {}).get("interview") == "origin-story", s.get("waiting_on"))
s = loop.resume(c5, r7, {"text": "skip"})
ok("a typed \"skip\" is read as a skip, not filed as the word skip",
   (onboard.ledger()["answers"]["origin-story"]) == {"state": "skipped", "text": "",
                                                     "at": onboard.ledger()["answers"]["origin-story"]["at"]},
   onboard.ledger()["answers"]["origin-story"])
loop.stop(c5, r7)

os.environ["SEO_AGENT_DATA"] = _prev_data
store.set_data_dir(_prev_data or None)

for x in (c, c2, c3, c4, c5):
    shutil.rmtree(store.chat_dir(x), ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all behaviour checks passed")
