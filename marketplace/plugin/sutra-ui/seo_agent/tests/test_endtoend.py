"""tests/test_endtoend.py — the whole stack, the way a host app drives it.

Model and DataForSEO are stubbed. What this proves is the wiring: a message starts a run,
the loop calls real tools, the tools write real artifacts, the gates stop for approval, an
answer resumes it, and the events a screen would poll arrive in the right order.

The HTTP layer is not in this package (the host app owns it), so this drives loop.start
and loop.resume directly, which is exactly what the old /send and /answer endpoints did
underneath. Everything the old suite checked through the API is checked here through the
store, minus the two checks that were about the API itself (the health route and the
never-leak-a-key response shape).
"""
import json
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, loop, registry, store

# stub the model before the loop calls anything
llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text

SCRIPT = [
    {"text": "", "tool_calls": [
        {"id": "a1", "name": "log_step", "input": {"message": "Reading your site index"}},
        {"id": "a2", "name": "suggest_topics", "input": {}}]},
    {"text": "", "tool_calls": [
        {"id": "a3", "name": "show_artifact",
         "input": {"path": "topics.json", "view": "topic_list",
                   "prompt": "Six ideas. Which one?"}}]},
    {"text": "", "tool_calls": [
        {"id": "a4", "name": "run_research",
         "input": {"topic": "executive education for CHROs"}}]},
    {"text": "", "tool_calls": [
        {"id": "a5", "name": "show_artifact",
         "input": {"path": "research.json", "view": "research_brief",
                   "prompt": "Check the keyword before I build on it."}}]},
    {"text": "", "tool_calls": [
        {"id": "a6", "name": "build_blueprint", "input": {"target_words": 1500}}]},
    {"text": "", "tool_calls": [
        {"id": "a7", "name": "show_artifact",
         "input": {"path": "blueprint.json", "view": "blueprint",
                   "prompt": "The structure. Happy?"}}]},
    {"text": "", "tool_calls": [{"id": "a8", "name": "write_article", "input": {}}]},
    {"text": "", "tool_calls": [
        {"id": "a9", "name": "show_artifact",
         "input": {"path": "draft.md", "view": "article", "prompt": "Here it is."}}]},
    {"text": "Done. The draft is in the Library when you want it.", "tool_calls": []},
]
i = {"n": 0}
def fake_call(system, messages, tools=None, model=None, **kw):
    r = SCRIPT[min(i["n"], len(SCRIPT) - 1)]
    i["n"] += 1
    return r
llm.call = fake_call

passed = failed = 0
def ok(label, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS  " + label)
    else:
        failed += 1
        print("  FAIL  " + label + ((" — " + str(extra)) if extra else ""))


print("\ntools")
tools = registry.WORK_TOOLS
ok("seven work tools", len(tools) == 7, len(tools))
ok("no credit gates: every work tool runs when called", all(t["gate"] == "auto" and not t.get("cost_credits") for t in tools))
ok("every work tool carries a plain-English row for the Tools screen",
   all(all(k in (t.get("plain") or {}) for k in ("does", "when", "needs", "takes")) for t in tools))
ok("gates exposed", all("gate" in t for t in tools))
ok("the model never sees costs or gates",
   all("gate" not in t and "cost_credits" not in t and "module" not in t
       for t in registry.for_model()))

print("\nconnections live in the data dir, not the code tree")
store.save_connections({"anthropic_key": "sk-secret-value"})
code_tree = os.path.dirname(os.path.dirname(os.path.abspath(store.__file__)))
ok("the key round-trips", store.connections().get("anthropic_key") == "sk-secret-value")
ok("connections.json sits under data_dir()",
   store.connections_file().startswith(store.data_dir()))
ok("and not under the package", not store.connections_file().startswith(code_tree),
   store.connections_file())
os.environ["SEO_AGENT_NO_CLI"] = "1"
ok("with the CLI off, the saved key picks the anthropic provider",
   llm.provider() == "anthropic", llm.provider())

print("\nstart a chat and send")
chat = store.new_chat()
run = store.new_run(chat, "write me an article")
ok("a run was created", bool(run))
s = loop.start(chat, run, "write me an article")

# Walk the run to the end, answering whatever kind of stop it reaches. Record the sequence,
# because the ORDER of stops is the thing worth asserting, not any single one.
seen = []
for _ in range(16):
    if s["status"] in ("done", "failed"):
        break
    w = s.get("waiting_on") or {}
    seen.append((w.get("kind"), w.get("view") or w.get("tool")))
    if w.get("view") == "blueprint":
        # The write phase reads the CONTRACTS-shaped inputs. Until research and the blueprint tools
        # write that shape, the fixture plants them at the moment the user approves the blueprint.
        _fixture.plant_write_inputs(chat, run, keep_research=True)
        _fixture.plant_brand_files()
    s = loop.resume(chat, run, {"approved": True, "picked": "t1"})

print("\nthe sequence of stops")
for kind, what in seen:
    print("   %-9s %s" % (kind, what))

artifacts = [w for k, w in seen if k == "artifact"]
approvals = [w for k, w in seen if k == "approval"]
ok("four artifact stops, not five", len(artifacts) == 4, artifacts)
ok("in the right order",
   artifacts == ["topic_list", "research_brief", "blueprint", "article"], artifacts)
ok("nothing stopped for approval (no credit gates)", approvals == [], approvals)
ok("the run finished", s["status"] == "done", s.get("error"))

print("\nthe artifacts it actually produced")
t = store.load_artifact(chat, run, "topics.json") or {}
ok("six topics", len(t.get("topics", [])) == 6, len(t.get("topics", [])))
rs = store.load_artifact(chat, run, "research.json") or {}
ok("research has a primary keyword", bool(rs.get("primary_keyword")))
ok("research has People Also Ask", isinstance(rs.get("people_also_ask"), list))
bp = store.load_artifact(chat, run, "blueprint.json") or {}
ok("blueprint has sections", len(bp.get("sections", [])) > 0)
d = store.load_artifact(chat, run, "draft.md") or ""
ok("draft is a real length", len(d.split()) > 100, len(d.split()))
a = store.load_artifact(chat, run, "article.json") or {}
ok("article.json has sections, sources and a close", bool(a.get("sections")) and "sources" in a and a.get("close"))
ok("the write report says what was skipped", bool((store.load_artifact(chat, run, "write-report.json") or {}).get("skipped")))

print("\nthe log the screen reads")
evs = store.get_events(chat, run)
types = [e["type"] for e in evs]
ok("a human log line", "note" in types)
ok("steps started and finished", "step_started" in types and "step_finished" in types)
subs = [e for e in evs if e["type"] == "substep_finished"]
ok("substeps were emitted", len(subs) > 5, len(subs))
ok("every substep has a parent", all(e.get("parent") for e in subs))
ok("no credits counted (there are none)", (s.get("credits_spent") or 0) == 0, s.get("credits_spent"))
ok("the run folder is under data_dir()", store.run_dir(chat, run).startswith(store.data_dir()))

print("\nfile it in the library")
# What the old /publish route did: save the draft plus the research and blueprint behind it.
title = bp.get("title") or (store.get_state(chat, run) or {}).get("topic") or "Untitled"
item_id = store.library_save(chat, run, title, d, {
    "primary_keyword": (rs.get("primary_keyword") or {}).get("keyword", "")})
store.emit(chat, run, "saved_to_library", item_id=item_id, title=title)
ok("saved to the library", bool(item_id))
lib = store.library_list()
ok("library lists it", len(lib) >= 1)
if lib:
    item = store.library_get(lib[0]["id"]) or {}
    ok("the item carries the draft", len(item.get("draft", "")) > 100)
    ok("the item carries its research", bool(item.get("research")))

print("\nmemory")
store.add_memory("Never write about pricing", "rule", source="user")
ok("a rule was saved", len(store.memory_rules()) >= 1)

# clean up everything this test created
shutil.rmtree(store.chat_dir(chat), ignore_errors=True)
for it in store.library_list():
    store.library_delete(it["id"])
store.save_connections({})
if os.path.exists(store.memory_file()):
    os.remove(store.memory_file())

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
