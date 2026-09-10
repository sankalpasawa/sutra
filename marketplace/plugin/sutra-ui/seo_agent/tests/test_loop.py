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
CHECKS = [0]
def ok(label, cond, extra=""):
    CHECKS[0] += 1
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
ok("knowledge block says the brand pack is missing", "Brand pack: not built" in kb and "Setup is not finished" in kb)
store.save_knowledge("brand/writer-brief.md", had_brief or "# Writer brief\n\nA test brief.")
kb = loop._knowledge_block(site)
ok("with the brief on file it says setup is complete", "Setup is complete:" in kb)
# The block states facts and NOTHING else. An instruction in here is a chore queued against
# whatever the person typed: on 2026-09-10 the tail said "Run onboard once, then carry on", the
# owner typed `hi`, and the agent opened a four-question interview on him.
ok("and it gives no orders: what to do about each state lives in the brief",
   not any(w in kb for w in ("Run onboard", "Run index_site", "Run learn_brand", "Run build_page_index",
                             "Do NOT run", "Say that in your first message")), kb)
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

# --- the setup interview -------------------------------------------------------------------
# Its own data dir. This writes real brand files (stats.md, stories.md) and every
# suite in one run shares SEO_AGENT_DATA, so left where it is it would hand test_brand a set of
# files a person had already half-filled in.
import tempfile
_prev_data = os.environ.get("SEO_AGENT_DATA", "")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-onboard-loop-")
store.set_data_dir(os.environ["SEO_AGENT_DATA"])
_fixture.setup()
from seo_agent.tools import onboard

def one_call(name, args=None):
    """A model that calls one tool and then says a sentence."""
    seq = [{"text": "", "tool_calls": [{"id": "ob1", "name": name, "input": args or {}}]},
           {"text": "Noted, thank you.", "tool_calls": []}]
    i = {"n": 0}
    def call(system, messages, tools=None, model=None, **kw):
        r = seq[min(i["n"], len(seq) - 1)]; i["n"] += 1; return r
    return call

print("\nthe setup interview")
llm.call = one_call("onboard")
c4 = store.new_chat("interview"); r4 = store.new_run(c4, "setup")
s = loop.start(c4, r4, "set me up")
ok("the interview asks its first question and stops",
   s["status"] == "waiting" and (s.get("waiting_on") or {}).get("interview") == "numbers", s.get("waiting_on"))
ok("it waits as an ordinary question, so the screen already knows how to draw it",
   s["waiting_on"]["kind"] == "question" and s["waiting_on"]["question"].strip().endswith("?"))
ok("every question offers a skip",
   any(o.get("label") == onboard.SKIP_LABEL for o in s["waiting_on"]["options"]))
ok("it says which question this is", s["waiting_on"]["step"] == 1 and s["waiting_on"]["of"] == 4,
   (s["waiting_on"].get("step"), s["waiting_on"].get("of")))

s = loop.resume(c4, r4, {"text": "1,200 companies in 40 countries."})
ok("the answer lands in the file that wanted it, verbatim",
   "1,200 companies in 40 countries." in (store.knowledge("brand/stats.md") or ""))
ok("and it moves straight on to the next question",
   (s.get("waiting_on") or {}).get("interview") == "origin-story", s.get("waiting_on"))

s = loop.resume(c4, r4, {"choice": onboard.SKIP_LABEL})
led = onboard.ledger().get("answers") or {}
ok("a skip is recorded as a skip, not as an empty answer",
   led.get("origin-story", {}).get("state") == "skipped"
   and led.get("origin-story", {}).get("text") == ""
   and led.get("numbers", {}).get("state") == "answered", led)
ok("and the skip is visible in the file, not only in the ledger",
   "Not answered" in (store.knowledge("brand/stories.md") or ""))

for said in ("We shipped a video interview nobody used, and cut it.",
             "rival-one.com and https://www.rival-two.com/pricing"):
    s = loop.resume(c4, r4, {"text": said})

ok("the run carries on by itself once the questions are done", s["status"] == "done", s["status"])
results = [b for m in store.get_messages(c4) if isinstance(m.get("content"), list)
           for b in m["content"] if b.get("type") == "tool_result"]
ok("four questions, ONE tool result: the model never sees a half-finished interview",
   len(results) == 1, len(results))
ok("the answer the model finally sees says what was answered and what was passed over",
   "3 of 4 answered" in str(results[0]["content"].get("summary", "")), results[0]["content"])
ok("the competitor answer went to competitors.json, addresses only",
   [r["domain"] for r in (store.knowledge("competitors.json") or {}).get("competitors", [])]
   == ["rival-one.com", "rival-two.com"], store.knowledge("competitors.json"))
ok("the interview is closed", onboard.status()["asked"] is True and onboard.status()["skipped"] == 1,
   onboard.status())
ok("the block now records that all four were put to them",
   "all four have been put to them" in loop._knowledge_block(store.knowledge("site_index.json") or {}))

llm.call = one_call("onboard")
c5 = store.new_chat("asked already"); r5 = store.new_run(c5, "setup again")
s = loop.start(c5, r5, "set me up")
ok("a second run does not ask again", s["status"] == "done", s.get("waiting_on"))
ok("it says so rather than saying nothing",
   any("already put to them" in str((e.get("summary") or "")) for e in store.get_events(c5, r5)))

llm.call = one_call("onboard", {"redo": True})
c6 = store.new_chat("ask me again"); r6 = store.new_run(c6, "redo")
s = loop.start(c6, r6, "go through the setup questions again")
ok("but it does ask again when the user asks it to",
   s["status"] == "waiting" and (s.get("waiting_on") or {}).get("interview") == "numbers", s.get("waiting_on"))
loop.stop(c6, r6)

for x in (c4, c5, c6):
    shutil.rmtree(store.chat_dir(x), ignore_errors=True)
os.environ["SEO_AGENT_DATA"] = _prev_data
store.set_data_dir(_prev_data or None)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
