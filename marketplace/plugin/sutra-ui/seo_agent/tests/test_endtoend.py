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
# the loop really runs run_research, which really reads pages; without these it reaches
# the network for hosts that do not exist
_fixture.stub_web()
_fixture.stub_voyage()

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
# NAMES, NOT A COUNT. This assertion has been a hand-typed number three times now, and each time a
# tool was added the failure said "12 != 11", which tells you nothing about which one arrived or
# whether it was meant to. The set says what is missing and what is unexpected, by name.
EXPECTED_WORK_TOOLS = {
    # import_traffic went on 2026-09-12: traffic comes from DataForSEO and from nowhere else.
    "index_site", "build_page_index", "refresh_site",                     # Knowledge
    "onboard", "learn_brand",                                             # the setup interview and the brand pack
    "build_assets", "suggest_topics",                                     # working out what is worth writing
    "run_research", "build_blueprint", "write_article",                   # making one article
    "find_prompt",                                                        # which prompt owns a complaint
}
ok("the work tools are exactly the ones we mean to ship",
   {t["name"] for t in tools} == EXPECTED_WORK_TOOLS,
   {"missing": sorted(EXPECTED_WORK_TOOLS - {t["name"] for t in tools}),
    "unexpected": sorted({t["name"] for t in tools} - EXPECTED_WORK_TOOLS)})
ok("refreshing the catalogue, asking the setup questions and building the asset ideas are tools, "
   "not hidden buttons",
   {"refresh_site", "onboard", "build_assets"} <= {t["name"] for t in tools})
ok("and there is no way to hand the agent a traffic file: DataForSEO or nothing",
   "import_traffic" not in {t["name"] for t in tools})
# The engine stops twice for a person, so the registry has to say it pauses. A tool the loop will
# stop on that claims it does not is how a run looks hung to everyone watching it.
# A MISSING LABEL IS INVISIBLE WITHOUT THIS. registry.label() falls back to the function name with
# its underscores removed, which looks like a name and is not one: three tools shipped to the Tools
# tab as "Refresh site", "Import traffic" and "Build assets" for months (owner finding 1.6). The
# fallback can never be the answer for a tool we ship.
ok("every work tool has a plain human name, not its function name",
   all(t["name"] in registry.LABELS for t in tools),
   [t["name"] for t in tools if t["name"] not in registry.LABELS])
ok("and no name on the Tools screen is a function name wearing a capital letter",
   not [r for r in registry.for_screen()
        if r["label"] == r["name"].replace("_", " ").capitalize()],
   [r["label"] for r in registry.for_screen()
    if r["label"] == r["name"].replace("_", " ").capitalize()])
ok("the asset engine declares that it pauses, because it stops twice for the user",
   next(t for t in tools if t["name"] == "build_assets")["pauses"] is True)
ok("no credit gates: every work tool runs when called", all(t["gate"] == "auto" and not t.get("cost_credits") for t in tools))
ok("every work tool carries a plain-English row for the Tools screen",
   all(all(k in (t.get("plain") or {}) for k in ("does", "when", "needs", "takes")) for t in tools))
ok("gates exposed", all("gate" in t for t in tools))
ok("the model never sees costs or gates",
   all("gate" not in t and "cost_credits" not in t and "module" not in t
       for t in registry.for_model()))

print("\nno description promises a checkpoint that was removed")
# The descriptions are ALL the model reads to decide when to run a tool. Three of them still said
# "run after the user approves…" months after those three checkpoints stopped waiting (owner's
# call, 2026-09-09, the same one that cut WAITING_VIEWS to two). A tool told to wait for an
# approval that will never arrive either hangs the run or asks a question it was told not to ask,
# which is exactly what show_artifact's own description forbids. So this is tied to WAITING_VIEWS
# rather than to a list of words: whatever stops waiting, the tool after it must stop claiming it.
BY = {t["name"]: t for t in tools}
AFTER_VIEW = {"brand_pack": "build_assets", "research_brief": "build_blueprint",
              "blueprint": "write_article", "topic_list": "run_research"}
_shown_only = [v for v in AFTER_VIEW if v not in loop.WAITING_VIEWS]
ok("the run stops at exactly two artifacts, and the rest are shown and passed",
   set(loop.WAITING_VIEWS) == {"topic_list", "article"}, loop.WAITING_VIEWS)
ok("and no tool that follows a shown-and-passed artifact says it waits for an approval",
   not [v for v in _shown_only
        if "approv" in BY[AFTER_VIEW[v]]["description"].lower()
        or "confirms the" in BY[AFTER_VIEW[v]]["description"].lower()],
   [(v, AFTER_VIEW[v]) for v in _shown_only
    if "approv" in BY[AFTER_VIEW[v]]["description"].lower()
    or "confirms the" in BY[AFTER_VIEW[v]]["description"].lower()])

# THE SETUP INTERVIEW LOST TWO QUESTIONS AND THE REGISTRY KEPT SELLING THEM. The two byline
# questions, voices.md and its builder were deleted on 2026-09-09 (tools/onboard.py's own header
# says so), and the description still listed both and still said "Six short questions". The model
# reads that line to decide what onboard is for; a person reads the Tools tab row.
from seo_agent.tools import onboard as _onb  # noqa: E402
_od = BY["onboard"]["description"].lower()
ok("onboard's description does not still sell the deleted byline questions",
   not any(w in _od for w in ("published under", "signs the leadership", "byline questions were asked")),
   _od[:200])
ok("and it says the number of questions the tool actually asks",
   len(_onb.IDS) == 4 and "four short questions" in _od, (len(_onb.IDS), "four short questions" in _od))

# SUGGEST_TOPICS WAS WRITTEN BEFORE THE ASSET SHEET. Its description is the only thing standing
# between a model with 1,900 ranked ideas on file and six fresh competitor guesses, so it has to
# name the condition, and the tool has to enforce it in code as well (tests/test_tools.py).
ok("suggest_topics' description names the asset sheet as the thing that supersedes it",
   "sheet" in BY["suggest_topics"]["description"].lower(),
   BY["suggest_topics"]["description"][:160])
ok("it tells the model not to call it when a sheet exists",
   "do not call this" in BY["suggest_topics"]["description"].lower(),
   BY["suggest_topics"]["description"][:160])
ok("and the Tools row says the same thing to a person",
   "sheet" in (BY["suggest_topics"]["plain"]["when"] or "").lower(),
   BY["suggest_topics"]["plain"]["when"])

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
# TWO stops now, not four. The brand pack, the research and the plan are shown and passed, because
# every output lands in the Library as it is made and a checkpoint that only SAYS "look at this"
# has stopped earning its interruption. What survives is the two that are real decisions: which
# topic, and whether the draft is finished. (The owner's call, 2026-09-09.)
ok("two artifact stops: the ones that are decisions, not reviews", len(artifacts) == 2, artifacts)
ok("in the right order", artifacts == ["topic_list", "article"], artifacts)
ok("the research and the plan were SHOWN, not waited on",
   {"research_brief", "blueprint"} <= {e.get("view") for e in store.get_events(chat, run) if e.get("type") == "artifact_ready"},
   sorted({e.get("view") for e in store.get_events(chat, run) if e.get("type") == "artifact_ready"}))
ok("and the run never stopped for them",
   not ({"research_brief", "blueprint"} & set(artifacts)), artifacts)
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
# every suite in a run shares one data dir, so find OUR item by its id rather than taking the
# first row: another suite's item is not this suite's business
ok("library lists it", any(x.get("id") == item_id for x in lib), [x.get("id") for x in lib])
item = store.library_get(item_id) or {}
ok("the item carries the draft", len(item.get("draft", "")) > 100, len(item.get("draft", "")))
# ONE row for the whole run, born at the first article step and renamed at the end. Two rows here
# would mean a person watching a run fill in loses it the moment it finishes.
_rows = store.library_list()
ok("exactly one library row for the run, not two", len(_rows) == 1, [r["id"] for r in _rows])
ok("the row it filled in is the row it finished", _rows[0]["id"] == item_id, (_rows[0]["id"], item_id))
ok("the row was renamed, not left as Writing", _rows[0]["title"] != "Writing…", _rows[0]["title"])
ok("its id is the run's, so the rename could not have moved it",
   _rows[0]["id"].startswith("run-"), _rows[0]["id"])
ok("a finished run lights every milestone, in the order it produced them",
   [m["key"] for m in _rows[0]["milestones"] if m["exists"]]
   == ["research", "plan", "picture", "draft", "edited"],
   [(m["key"], m["exists"]) for m in _rows[0]["milestones"]])
ok("every milestone is named for a person, not by its file",
   all(m["label"] and m["note"] and not m["label"].endswith(".json")
       for m in _rows[0]["milestones"]))
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
