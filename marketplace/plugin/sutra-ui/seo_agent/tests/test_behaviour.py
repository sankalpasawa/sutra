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


# ---------------------------------------------------------------------------------------------
# THE ONE QUESTION THE AGENT KEPT GETTING WRONG: "what do I write next?"
#
# Simulated first turns against the real model, 2026-09-10, with a sheet of ranked ideas on file.
# Six near-identical requests produced five different behaviours: one silently started research on
# a re-titled version of the top idea, one ran the superseded suggest_topics path, one showed a
# topic_list pointing at a topics.json no tool had written (the run then sat waiting on an empty
# panel), and two asked the person to think of a topic. The cause was not one missing prohibition.
# It was that the answer lived in four places that disagreed: two table rows, two sections, and an
# article step that said to call suggest_topics whenever no topic was named.
#
# These checks hold the single-answer shape in place: one section in the brief owns it, the state
# block hands over the id and the WHOLE title, and the loop refuses to stop for a file nobody made.
print("\nwhat to write next: one answer, in one place")
_prev_next = os.environ.get("SEO_AGENT_DATA", "")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-next-behaviour-")
store.set_data_dir(os.environ["SEO_AGENT_DATA"])

BRIEF = open(os.path.join(os.path.dirname(os.path.abspath(loop.__file__)), "prompts", "system.md"),
             encoding="utf-8").read()
LONG_TITLE = "The Real Cost of Recruitment in 2026: The Numbers Behind the 2022 Figure Everyone Still Quotes"


def _sheet(*rows):
    store.save_knowledge("assets/ideas.json", [
        {"id": i, "title": t, "angle": "an angle", "format": "News article",
         "method": ["competitor-study"], "rank": n + 1, "status": st,
         "built": {"library_id": "", "run_id": "", "at": "", "how": ""}}
        for n, (i, t, st) in enumerate(rows)])


SITE = {"domain": "example.com", "indexed_at": "2026-09-08",
        "pages": [{"url": "https://example.com/", "title": "Home"}]}
store.save_knowledge("brand/writer-brief.md", "# Writer brief\n\nShort sentences.\n")

_sheet(("a1001", LONG_TITLE, "open"), ("a1002", "A second idea", "open"))
blk = loop._knowledge_block(SITE)
ok("the block names the next idea by id", "a1001" in blk, blk)
ok("and carries its WHOLE title, so the offer is the idea and not a paraphrase of half of it",
   LONG_TITLE in blk, blk)
ok("the block does not also carry the policy: the brief owns that, in one place",
   "build_assets" not in blk.split("- Asset ideas:")[1].split("\n")[0], blk)

_sheet(("a1001", LONG_TITLE, "built"), ("a1002", "A second idea", "built"))
blk_done = loop._knowledge_block(SITE)
ok("a sheet with nothing left says so, and offers no next idea",
   "none left to write" in blk_done and "a1001" not in blk_done, blk_done)

os.remove(os.path.join(store.knowledge_dir(), "assets", "ideas.json"))
blk_none = loop._knowledge_block(SITE)
ok("no sheet at all is still a LINE, never an absence", "Asset ideas: NO sheet" in blk_none, blk_none)

ok("the tail states what is done rather than forbidding what is not",
   "Setup is complete:" in blk_none and "Do NOT run" not in blk_none, blk_none)

ok("the brief answers it in ONE section", BRIEF.count("## What to write next") == 1, BRIEF.count("## What to write next"))
ok("that section forbids the actual complaint: asking for a topic while the sheet holds one",
   "think of a topic while the sheet is holding one" in BRIEF)
ok("the article steps no longer send it to suggest_topics whenever no topic was named",
   "`suggest_topics` and `show_artifact` the list" not in BRIEF)
ok("and the sentence that told it suggest_topics was FOR a company with a sheet is gone",
   "`suggest_topics` is for a company that has a sheet" not in BRIEF)
ok("the brief and the loop agree on where a run stops",
   "TWO stops per article" in BRIEF and "Four stops per article" not in BRIEF
   and loop.WAITING_VIEWS == ("topic_list", "article"), loop.WAITING_VIEWS)

print("\na stop has to have something to look at")
c6 = store.new_chat("phantom")
r8 = store.new_run(c6, "topics")
seen2 = {}


def phantom(system, messages, tools=None, model=None, **kw):
    last = messages[-1]
    if isinstance(last.get("content"), list):
        for b in last["content"]:
            if b.get("type") == "tool_result":
                seen2["result"] = b.get("content")
    seen2["n"] = seen2.get("n", 0) + 1
    if seen2["n"] == 1:
        return {"text": "", "tool_calls": [{"id": "sa1", "name": "show_artifact", "input": {
            "path": "topics.json", "view": "topic_list", "prompt": "Pick one."}}]}
    return {"text": "Nothing to show, so here it is in words.", "tool_calls": []}


llm.call = phantom
s8 = loop.start(c6, r8, "what topics should we cover")
ok("showing a file nobody wrote does NOT strand the run on an empty panel",
   s8["status"] == "done", s8["status"])
ok("the model is told the file does not exist", "error" in (seen2.get("result") or {}), seen2.get("result"))
ok("and told what to do instead", "hint" in (seen2.get("result") or {}))

# the same call, once the file is really there, still stops. The guard must not cost the checkpoint.
c7 = store.new_chat("real artifact")
r9 = store.new_run(c7, "topics")
store.save_artifact(c7, r9, "topics.json", {"topics": [{"id": "t1", "title": "One"}]})
llm.call = script([{"text": "", "tool_calls": [{"id": "sa2", "name": "show_artifact", "input": {
    "path": "topics.json", "view": "topic_list", "prompt": "Pick one."}}]}])
s9 = loop.start(c7, r9, "topics please")
ok("a real topic list still stops for the person", s9["status"] == "waiting", s9["status"])
ok("on the topic checkpoint", (s9.get("waiting_on") or {}).get("view") == "topic_list", s9.get("waiting_on"))
loop.stop(c7, r9)


# ---------------------------------------------------------------------------------------------
# `hi` ON A FINISHED INSTALL, 2026-09-10. He typed two letters and got "Asked question 1 of 4:
# what numbers can Testlify claim that your website does not already publish?", skipped it, got
# question 2, and the run sat on "Waiting for you, 2m 48s".
#
# The line that did it was in the state block: "One thing IS still outstanding: the setup
# questions have never been put to them. Run onboard once, then carry on." The block is rebuilt
# into the system prompt on EVERY turn, so an instruction in it is not advice, it is a chore
# queued against whatever the person happened to type. The whole block is facts now, and these
# checks hold that line: the state that bit him, and no orders anywhere in any state.
print("\nthe state block states facts and never gives an order")
store.save_knowledge("assets/ideas.json", [])
_sheet(("a1001", LONG_TITLE, "open"))
store.save_knowledge("brand/_interview/answers.json", {})       # started? no: never asked at all
os.remove(os.path.join(store.knowledge_dir(), "brand", "_interview", "answers.json"))
his_state = loop._knowledge_block(SITE)
ok("his exact state is described: pack built, questions never put",
   "Brand pack: built" in his_state and "Setup questions: never asked" in his_state, his_state)
ok("and what is lost by that is stated",
   "The brand pack was built without the setup answers." in his_state, his_state)
ok("but nothing tells it to run the interview, which is what fired on `hi`",
   "onboard" not in his_state.lower(), his_state)

ORDERS = ("Run onboard", "Run index_site", "Run learn_brand", "Run build_page_index", "Do NOT run",
          "Do NOT ask", "Ask for the website", "Say that in your first message", "offer it",
          "Go straight to the article")
for label, state_block in (("his state", his_state), ("a fresh install", blk_none),
                           ("a sheet with ideas", blk), ("a finished sheet", blk_done)):
    ok("no instruction survives in the block for %s" % label,
       not any(o in state_block for o in ORDERS),
       [o for o in ORDERS if o in state_block])
ok("and the block says outright that it is not one",
   "Nothing here is an instruction" in his_state, his_state[:200])

# The brief is where the judgement lives, and it has to hold all three of his rules.
ok("the brief puts context before any question", "Context first, then the offer" in BRIEF)
ok("it names exactly two ways to start an article",
   "There are exactly TWO ways an article starts" in BRIEF
   and "the top open idea off the asset sheet, offered BY NAME" in BRIEF
   and "a topic they name themselves" in BRIEF)
ok("anything else outstanding is offered in one line, never started",
   "is one line, offered, never started" in BRIEF)
ok("and passing on an idea is said to cost nothing",
   "Passing on an idea costs them nothing" in BRIEF)

# ---------------------------------------------------------------------------------------------
# THE WORST THING IT SAID, 2026-09-10. Asked "does the research actually read the real google
# results right now, yes or no", it answered "Yes. Reading the live results and the pages that win
# is part of research and doesn't touch DataForSEO." False: research/serp.py goes through
# dfs.serp_advanced, which with no login returns _demo_serp_extract — ten manufactured results,
# an invented snippet, an invented AI Overview. The model reasoned correctly from a false premise
# it was handed in both places: "and everything else still works".
#
# A wrong capability claim is worse than a wrong number. A demo number arrives labelled as demo;
# "yes it reads Google" does not, and somebody acts on it.
print("\nwhat is demo without a DataForSEO login is stated honestly")
ok("the false half of the old sentence is gone from the brief",
   "everything else still works" not in BRIEF)
ok("the brief names the search results themselves as demo, not just the numbers",
   "the search results themselves" in BRIEF and "the AI Overview" in BRIEF)
ok("and answers the question a person actually asks",
   "research does NOT read the live Google results without a login" in BRIEF)
ok("the block says the same thing, as a fact",
   "the search results the research reads are all demo" in loop._knowledge_block(SITE),
   loop._knowledge_block(SITE))
ok("a number nobody gave it is never stated, whatever the hedge",
   "NEVER state a number you were not given" in BRIEF and "a duration, a cost" in BRIEF)
ok("a tool's number stays a fact about the tool",
   "never turn it into a claim about something you have not opened" in BRIEF)
ok("a vague reply does not start a long job",
   "is not permission to start a long job" in BRIEF)
ok("a stopped run does not send them to a button that is gone",
   "there is no panel to approve" in BRIEF)

# ---------------------------------------------------------------------------------------------
# THE OTHER HALF OF OFFERING THE TOP IDEA IN THE CHAT. The chip on the Asset ideas tab starts a
# run with idea_id already on its state, and save_to_library ticks the sheet from that alone. An
# offer accepted in the chat had no id, so the article was written, saved, and the idea stayed
# open, to be offered again on the next turn for ever. Provenance only: the id is read back out
# of the agent's own question, checked against the sheet, and counted when the person takes it.
print("\ntaking the offered idea ties the run to it, so the sheet is ticked once")
from seo_agent.assets import _common as _acm

_sheet(("a1001", LONG_TITLE, "open"), ("a1002", "A second idea", "open"))
OFFER = {"id": "q1", "name": "ask_user", "input": {
    "question": 'Shall I write a1001: "%s"?' % LONG_TITLE,
    "why": "It is the top open idea on your sheet.",
    "options": [{"label": "Write a1001", "recommended": True},
                {"label": "I'll name my own topic"}]}}

c8 = store.new_chat("takes the offer")
r10 = store.new_run(c8, "hi")
llm.call = script([{"text": "Top of the sheet is a1001.", "tool_calls": [OFFER]},
                   {"text": "Starting research.", "tool_calls": []}])
s10 = loop.start(c8, r10, "hi")
ok("the offer is recorded against the idea it names",
   (s10.get("waiting_on") or {}).get("offer_idea") == "a1001", s10.get("waiting_on"))
loop.resume(c8, r10, {"text": "Write a1001"})
ok("accepting it makes this a run that STARTED from that idea",
   store.get_state(c8, r10).get("idea_id") == "a1001", store.get_state(c8, r10).get("idea_id"))
store.save_artifact(c8, r10, "draft.md", "# The real cost of recruitment\n\nBody.")
saved = loop.save_to_library(c8, r10)
ok("so the Library save ticks it off the sheet", _acm.by_id("a1001")["status"] == "done",
   _acm.by_id("a1001"))
ok("and the tick names the run and the article it came from",
   (_acm.by_id("a1001").get("built") or {}).get("run_id") == r10, _acm.by_id("a1001").get("built"))
ok("nothing else on the sheet is touched", _acm.by_id("a1002")["status"] == "open")

# and the other way: passing on it costs nothing, which is what the brief now promises him
_sheet(("a1001", LONG_TITLE, "open"))
c9 = store.new_chat("passes on it")
r11 = store.new_run(c9, "hi")
llm.call = script([{"text": "Top of the sheet is a1001.", "tool_calls": [OFFER]},
                   {"text": "Right, cost per hire it is.", "tool_calls": []}])
loop.start(c9, r11, "hi")
loop.resume(c9, r11, {"text": "I'll name my own topic: pricing pages"})
ok("naming another topic is not accepting the offer",
   not str(store.get_state(c9, r11).get("idea_id") or ""), store.get_state(c9, r11).get("idea_id"))
store.save_artifact(c9, r11, "draft.md", "# Pricing pages\n\nBody.")
loop.save_to_library(c9, r11)
ok("and the idea he passed on is still there, still open", _acm.by_id("a1001")["status"] == "open",
   _acm.by_id("a1001"))

# ---------------------------------------------------------------------------------------------
# A QUESTION IN PROSE USED TO END THE RUN. Across 18 first turns and three models, 11 asked in
# prose with no tool call, and the same model did both in one conversation. The loop filed those
# turns as `done` — the state a finished answer gets — so the question sat on screen with the run
# over behind it, and the person's reply opened a fresh run that had never seen it. The brief now
# says every question goes through ask_user; this is the loop making that true whether it is
# obeyed or not.
print("\na question is a question, however it was asked")
_sheet(("a1001", LONG_TITLE, "open"))
c10 = store.new_chat("asks in prose")
r12 = store.new_run(c10, "hi")
llm.call = script([{"text": "Setup is done and there are 8 ideas waiting.\n\nShall I start on "
                            "a1001, \"%s\"?" % LONG_TITLE, "tool_calls": []},
                   {"text": "Right, starting on it.", "tool_calls": []}])
s12 = loop.start(c10, r12, "hi")
ok("a prose question pauses the run instead of finishing it", s12["status"] == "waiting", s12["status"])
w12 = s12.get("waiting_on") or {}
ok("it is put to the person as the question it is", w12.get("kind") == "question", w12)
ok("and the question is the line they actually asked",
   w12.get("question", "").startswith("Shall I start on a1001"), w12.get("question"))
ok("an offer made in prose still records the idea it names", w12.get("offer_idea") == "a1001", w12)
loop.resume(c10, r12, {"text": "yes"})
ok("accepting it in prose ties the run to the idea too",
   store.get_state(c10, r12).get("idea_id") == "a1001", store.get_state(c10, r12).get("idea_id"))
msgs = store.get_messages(c10)
ok("the answer goes back as an ordinary message, not a tool result with no call behind it",
   msgs[-2] == {"role": "user", "content": "yes"} or msgs[-1] == {"role": "user", "content": "yes"}
   or any(m.get("content") == "yes" for m in msgs), msgs[-2:])
ok("and the run finished on the answer", store.get_state(c10, r12)["status"] == "done")

c11 = store.new_chat("finishes plainly")
r13 = store.new_run(c11, "hi")
llm.call = script([{"text": "Done. The draft is in the Library.", "tool_calls": []}])
ok("an answer that asks nothing still just ends",
   loop.start(c11, r13, "hi")["status"] == "done")

# the three states the brief used to be silent on, where three models did three different things
ok("a domain that cannot be real is caught before the crawl, not after",
   "A domain that cannot be real" in BRIEF and ".invalid" in BRIEF)
ok("a blocked crawl stops setup instead of feeding the next step nothing",
   "A blocked crawl is not a working catalogue" in BRIEF)
ok("a topic they named is said back to them",
   "Say the topic back to them in their own words" in BRIEF)
ok("and every question goes through the tool that pauses",
   "EVERY question to the person goes through `ask_user`" in BRIEF)

# owner, 2026-09-10: he answered "I'll name my own topic" and was handed two options back --
# one that only restated the question, and one that re-offered the idea he had just declined.
# Options are a CHOICE. A question whose answer is typed gets none.
ok("options are only for a real choice, never for a question they must type",
   "Options are for a choice between named alternatives" in BRIEF
   and "send the question with NO options" in BRIEF)
_FLAT = " ".join(BRIEF.split())   # the rule wraps across lines in the file
ok("an option that only restates the question is named as the mistake it is",
   "the question wearing a button" in _FLAT)
ok("a thing they just turned down is never put back in front of them",
   "never re-offer a thing they turned down one turn ago" in _FLAT)
ok("naming their own topic is asked as one open question, not another menu",
   "Ask for it as one open question with NO options" in BRIEF)

# owner, 2026-09-10: "always simple English... the user of this agent is not a software
# developer, but someone who knows very less about tech" and "does not have a lot of time".
ok("the brief says who is actually reading, and that they are not an engineer",
   "A marketing person, not an engineer" in _FLAT)
ok("and that a reply is short by default, not long by default",
   "A normal reply is one to three sentences" in _FLAT)
ok("a failure is three lines, not three paragraphs",
   "Three lines, not three paragraphs" in _FLAT)

_ASK = [t for t in registry.ALL if t["name"] == "ask_user"][0]["description"]
ok("the tool itself no longer orders 2-4 options on every question",
   "Give 2-4 options" not in _ASK and "takes NO options" in _ASK)

for x in (c10, c11):
    shutil.rmtree(store.chat_dir(x), ignore_errors=True)

os.environ["SEO_AGENT_DATA"] = _prev_next
store.set_data_dir(_prev_next or None)
for x in (c6, c7, c8, c9):
    shutil.rmtree(store.chat_dir(x), ignore_errors=True)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all behaviour checks passed")
