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

# the system prompt tells the model what Knowledge already holds, so setup is never redone
site = store.knowledge("site_index.json") or {}
had_brief = store.knowledge("brand/writer-brief.md")
if had_brief: store.save_knowledge("brand/writer-brief.md", "")
kb = loop._knowledge_block(site)
ok("knowledge block names the catalogue", "Site catalogue: %s" % site.get("domain") in kb and "%d pages" % len(site["pages"]) in kb)
ok("knowledge block says the brand pack is missing", "Brand pack: not built" in kb and "Finish setup first" in kb)
store.save_knowledge("brand/writer-brief.md", had_brief or "# Writer brief\n\nA test brief.")
kb = loop._knowledge_block(site)
ok("with the brief on file it says setup is complete", "Setup is complete. Do NOT run index_site" in kb)
ok("the system prompt carries the block", "## What is already in Knowledge" in loop._system_prompt() and "{{KNOWLEDGE}}" not in loop._system_prompt())
if not had_brief: store.save_knowledge("brand/writer-brief.md", "")

# approving the draft saves it to the Library in code; anything else saves nothing
c3 = store.new_chat("library test"); r3 = store.new_run(c3, "cost per hire")
ok("no draft, nothing to save", loop.save_to_library(c3, r3) is None)
store.save_artifact(c3, r3, "draft.md", "# Cost Per Hire: The Formula\n\nBody text.")
store.save_artifact(c3, r3, "blueprint.json", {"h1": "Cost per hire"})
store.save_artifact(c3, r3, "research.json", {"keywords": {"primary": {"keyword": "cost per hire"}}})
before_lib = len(store.library_list())
ok("asking for changes does not save", loop._save_if_draft_approved(c3, r3, {"view": "article", "artifact": "draft.md"}, {"approved": False, "changes": "shorter"}) is None
   and len(store.library_list()) == before_lib)
ok("approving the brief does not save", loop._save_if_draft_approved(c3, r3, {"view": "research_brief", "artifact": "research.json"}, {"approved": True}) is None)
saved = loop._save_if_draft_approved(c3, r3, {"view": "article", "artifact": "draft.md"}, {"approved": True})
ok("approving the draft saves it, titled from the draft's own H1", saved and saved["title"] == "Cost Per Hire: The Formula" and len(store.library_list()) == before_lib + 1, saved)
item = next((i for i in store.library_list() if i.get("id", i.get("item_id")) == saved["item_id"]), None) or {}
ok("the library row carries the primary keyword", (item.get("primary_keyword") or item.get("meta", {}).get("primary_keyword")) == "cost per hire", item)
ok("the run log says it was saved", any(e["type"] == "saved_to_library" and e.get("title") == saved["title"] for e in store.get_events(c3, r3)))
# the data dir is shared with every other suite, so take this item back out again
import shutil as _sh, os as _os
_sh.rmtree(_os.path.join(store.library_dir(), saved["item_id"]), ignore_errors=True)
shutil.rmtree(store.chat_dir(c3))

print("\nevents in run 1:", evs)
shutil.rmtree(store.chat_dir(c)); shutil.rmtree(store.chat_dir(c2))

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % 24)
