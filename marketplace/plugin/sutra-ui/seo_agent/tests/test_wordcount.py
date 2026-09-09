"""tests/test_wordcount.py — one length, chosen once by a person, obeyed by every step after it.

THE BUG THIS SUITE EXISTS TO KEEP DEAD, found 2026-09-09. The length of an article used to be
decided TWICE, by two steps that never spoke to each other. Research measured how long the pages
that actually rank run and produced a band. The architect budgeted from that band. Then the
readable rewrite, the very last step to touch the length, threw the band away and took
`min(2100, current)` from a constant that had never seen a competitor. So a topic whose winners run
3,200 words and a topic whose winners run 1,400 words both came out as an article cut to 2,100.
That is the over-concision the owner had been feeling for weeks, and he worked out where it came
from before anyone else did.

The fix is one question, put to a person once per article, between the brief and the research
conversation. After it is answered THE PERSON'S NUMBER IS THE ONLY SOURCE OF TRUTH FOR LENGTH.

The owner's warning about exactly this, in his own words: "you are not going to take the input
which is there from the DataForSEO output file, you are going to take it from what the user has
input. So you need to build those proper placeholders and all of that very properly." A sloppy job
here does not fail loudly. It surfaces three steps later as an article of the wrong length with no
obvious cause. So this suite does not assert the number at the source and call it proved. It walks
the chain and asserts it AT EVERY CONSUMER: the build spec, the blueprint, gather, the architect's
word budget, each section's target, the body writer's prompt, the blend prompt, and the readable
rewrite's prompt. If any one of them quietly went back to the measured band, one of these fails.

It also holds the owner's two rulings:
  * the 2,100 ceiling is deleted from the codebase, name and all. Not a guard, not a max, not a
    comment. This suite greps the whole tree for it.
  * WORDS_PER_FACT is one belief held in two places, write_body and readable, and the fact count
    now FOLLOWS the length instead of being fixed by a cap.
"""
import copy
import os
import shutil
import subprocess
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.research import assemble as research_assemble
from seo_agent.tools import _index, _shared as sh, build_blueprint, run_research
from seo_agent.write import _common as C, allocate_words, blend, gather, readable, shape, write_body

llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text
_fixture.stub_voyage()
_fixture.stub_web()
_fixture.stub_write_network()
_fixture.plant_brand_files()

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def say(*_a, **_k):
    pass


PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # seo_agent/

# Built rather than written out, so this file carries the name once and the grep below cannot match
# its own assertion by accident.
DELETED = "READABLE" + "_CEILING"


# ======================================================================================
# 1. The two rulings, held as facts about the code itself
# ======================================================================================
print("\nthe two rulings the owner made")

# "should go away completely, not some safety limit and shit." So the grep is over the SOURCE, not
# over an import: a constant left behind in a comment, a docstring, a prompt or a dead branch is
# exactly the "safety limit" he ruled out, and an attribute check would not see any of them.
# This file is excluded from its own grep for the obvious reason: it has to name the thing it is
# looking for, and a suite that fails on its own assertion text proves nothing.
hits = subprocess.run(["grep", "-rn", "--include=*.py", "--include=*.md", "--include=*.js",
                       "--exclude=" + os.path.basename(__file__), DELETED, PKG],
                      capture_output=True, text=True).stdout.strip()
ok("%s appears nowhere in the codebase, not even in a comment" % DELETED, hits == "", hits[:400])
ok("and nothing can reach it through the settings hub", not hasattr(C, DELETED))

ok("WORDS_PER_FACT is a shared constant, not readable's private setting",
   getattr(C, "WORDS_PER_FACT", None) == 110 and not hasattr(C, "READABLE_WORDS_PER_FACT"),
   getattr(C, "WORDS_PER_FACT", None))
body_src = open(os.path.join(PKG, "write", "write_body.py"), encoding="utf-8").read()
readable_src = open(os.path.join(PKG, "write", "readable.py"), encoding="utf-8").read()
ok("write_body holds the belief too, not just readable",
   "C.WORDS_PER_FACT" in body_src and "C.WORDS_PER_FACT" in readable_src)


# ======================================================================================
# 2. The question: asked once, and only once
# ======================================================================================
print("\nthe one question, asked once per article")

rec = store.knowledge("brand/company.json") or {}
rec.setdefault("brand", "Example")
rec.setdefault("domain", "example.com")
rec.setdefault("brand_oneliner", "Example — practitioner-led business programmes for founders and senior operators")
rec.setdefault("niche_definition", "executive education — programmes for operators, cohort learning, leadership practice")
rec.setdefault("about", "Practitioner-led programmes for people who already run things.")
store.save_knowledge("brand/company.json", rec)
if not sh.brand_file("persona.md"):
    store.save_knowledge("brand/persona.md",
        "# Personas\n\n| Persona | Who | Reads |\n|---|---|---|\n"
        "| **Founder / CEO** | runs a 50-500 person company | strategy pieces |\n"
        "| **Senior Operator** | COO / VP running a function | how-to and cases |\n\n"
        "## How to pick one per article\nStrategy -> Founder; role how-to -> Operator.\n")
_saved_index = store.knowledge("site_index.json")
store.save_knowledge("site_index.json", _fixture.SITE_INDEX)
_fixture.plant_content_database()
_index.build(sh.pages_with_bodies(), say=lambda *a, **k: None, reindex=True)
_fixture.stub_dfs(balance=12.5)

chat = store.new_chat("word count test")
def ctx_for(run):
    return {"chat_id": chat, "run_id": run, "step_id": "step-1", "emit": lambda **kw: None}

TOPIC = "Operator education (a buyer's guide)"

run1 = store.new_run(chat, "asked once")
ctx1 = ctx_for(run1)
first = run_research.run(ctx1, topic=TOPIC, angle="what changes after")
ask = (first or {}).get("ask_words") or {}
ok("the run stops and asks how long the article should be", bool(ask), first)
ok("it stops BEFORE the research conversation, which is the expensive half",
   store.load_artifact(chat, run1, "_work/curate.json") is None
   and store.load_artifact(chat, run1, "_work/brief.json") is not None)
ok("and before research.json is written", store.load_artifact(chat, run1, "research.json") is None)

# The fixture's ranking pages measure 1,500 to 2,200 words, so the average offered is 1,850.
ok("the question carries the measured band and the average as the suggestion",
   ask.get("band") == {"min": 1500, "max": 2200} and ask.get("suggested") == 1850, ask)
ok("the question is in plain words, with the keyword and both numbers in it",
   "1,500" in ask["question"] and "2,200" in ask["question"] and "1,850" in ask["question"]
   and "operator education" in ask["question"].lower(), ask.get("question"))
ok("it says what happens next and how long it takes",
   "fifteen minutes" in ask["why"] and "1,850" in ask["why"], ask.get("why"))
ok("no em dashes on screen", "—" not in ask["question"] and "—" not in ask["why"])

# The record of the question, written BEFORE it went out, carrying the run's own inputs. Without
# it the answer comes back with a number and nothing else and the run refuses itself.
row = store.load_artifact(chat, run1, "_work/ask-words.json") or {}
ok("the question is filed with the run's inputs, so the answer can find its way back",
   row.get("asked_at") and row.get("topic") == TOPIC and row.get("answer") is None, row)

second = run_research.run(ctx1, word_target=2600)
ok("answering with a number and nothing else finishes the run",
   bool(second.get("summary")) and not second.get("error") and not second.get("ask_words"), second)
ok("the topic survived the round trip, so nothing had to be asked twice",
   (store.load_artifact(chat, run1, "research.json") or {}).get("topic") == TOPIC)

third = run_research.run(ctx1, topic=TOPIC, angle="what changes after")
ok("calling it again never asks a second time", not third.get("ask_words"), third)
ok("and the answer on file is still the person's, not re-decided",
   (store.load_artifact(chat, run1, "_work/ask-words.json") or {}).get("answer") == 2600)


# ======================================================================================
# 3. A typed number beats the measured band AT EVERY CONSUMER
# ======================================================================================
print("\na typed number overrides the measured band, checked at each step that reads it")

# 3,200 is chosen on purpose: it is outside the measured band (1,500 to 2,200) AND above the old
# 2,100 ceiling, so a step that quietly fell back to either one is caught here.
TYPED = 3200
run2 = store.new_run(chat, "typed number")
ctx2 = ctx_for(run2)
asked2 = run_research.run(ctx2, topic=TOPIC, angle="what changes after")
run_research.run(ctx2, word_target=TYPED)
rs2 = store.load_artifact(chat, run2, "research.json") or {}
spec = rs2.get("build_spec") or {}

ok("consumer 1, the build spec: the word band IS the person's number",
   spec.get("word_band") == {"min": TYPED, "max": TYPED}, spec.get("word_band"))
ok("the measured band is kept beside it for the record, under its own name",
   spec.get("word_band_measured") == {"min": 1500, "max": 2200}, spec.get("word_band_measured"))
ok("and the file says where the number came from",
   "person" in (spec.get("word_band_source") or ""), spec.get("word_band_source"))
ok("the brief's own work file still holds the raw measurement, unedited",
   ((store.load_artifact(chat, run2, "_work/brief.json") or {}).get("build_spec") or {}).get("word_band")
   == {"min": 1500, "max": 2200})

bpo = build_blueprint.run(ctx2)
bp2 = store.load_artifact(chat, run2, "blueprint.json") or {}
ok("consumer 2, the blueprint: it carries the person's number, not the measurement",
   bp2.get("word_band") == {"min": TYPED, "max": TYPED}, (bp2.get("word_band"), bpo.get("error")))

cards2 = store.load_artifact(chat, run2, "cards.json") or []
ga = gather.run(bp2, rs2, cards2, say)["group_a"]
ok("consumer 3, gather: group_a hands the writer the person's number",
   ga["word_band"] == {"min": TYPED, "max": TYPED}, ga["word_band"])

# ---- the architect. ARCH_BAND_SHRINK stays: every real run overshot its target, so the split is
# made UNDER the number. What changed is what it shrinks: the person's number, not a band midpoint.
maths = shape.budget_maths({"min": TYPED, "max": TYPED})
ok("consumer 4, shape: WORD_BUDGET is the person's number cut by the 10%% aim-low, %d" % round(TYPED * 0.9),
   maths["budget"] == round(TYPED * (1 - C.ARCH_BAND_SHRINK)), maths["budget"])
ok("and the aim-low shrink is still applied, not quietly dropped",
   C.ARCH_BAND_SHRINK == 0.10 and maths["budget"] < TYPED)

# ---- allocate. The model's share reply is left empty on purpose: an even split still has to add
# up to the same base, and the record it writes is what readable reads back.
PROMPTS = []
def capture_json(prompt, system=None, retries=1, **kw):
    PROMPTS.append(prompt)
    return {}
def capture_text(prompt, system=None, **kw):
    PROMPTS.append(prompt)
    return "## A\n\nOne fact [c1]. Another sentence to give it length."

BP_F, RS_F, CARDS_F = _fixture.write_inputs()
IDX_F = C.card_index(CARDS_F)
CTX_F = C.context(BP_F, RS_F)


def allocate_with(target):
    """allocate_words over a plan carrying `target` as its band, model shares left empty."""
    plan = copy.deepcopy(BP_F)
    plan["word_band"] = {"min": target, "max": target}
    st = {"spine": RS_F["spine"], "sections": [
        {"headline": s["h2"], "job": s["job"], "h3s": [], "lead": {"card_ids": s.get("evidence") or []},
         "is_item": False}
        for s in BP_F["sections"]]}
    real = llm.json_call
    llm.json_call = capture_json
    try:
        out = allocate_words.run(st, plan, IDX_F, CTX_F, say)
    finally:
        llm.json_call = real
    return out["structure"], out["allocation"]

PROMPTS[:] = []
st_big, alloc_big = allocate_with(TYPED)
wb = st_big["word_budget"]
ok("consumer 5, allocate: it divides up the person's number",
   wb["target"] == TYPED, wb)
ok("the base it splits is that number cut by the aim-low, and nothing else",
   wb["base"] == round(TYPED * (1 - C.ARCH_BAND_SHRINK)) == alloc_big["base"], (wb["base"], alloc_big["base"]))
ok("every section's target adds up to that base",
   abs(wb["sum_of_targets"] - wb["base"]) <= len(st_big["sections"]), (wb["sum_of_targets"], wb["base"]))
ok("and the number the model was actually shown is that base, in the prompt",
   any(str(wb["base"]) in p for p in PROMPTS), [p[:0] for p in PROMPTS])

# ---- the body writer. One section, its own target, the same belief about how many facts fit.
sec_big = st_big["sections"][0]
PROMPTS[:] = []
real_text = llm.text
llm.text = capture_text
try:
    write_body.run({"sections": [copy.deepcopy(sec_big)], "spine": RS_F["spine"]}, IDX_F, CTX_F, say)
finally:
    llm.text = real_text
body_prompt = PROMPTS[0] if PROMPTS else ""
ok("consumer 6, write_body: the section prompt carries its own slice of the person's number",
   ("about %s words" % sec_big["word_target"]) in body_prompt or str(sec_big["word_target"]) in body_prompt,
   sec_big.get("word_target"))
ok("and it tells the writer how many facts that length has room for",
   "room to properly explain" in body_prompt and str(C.WORDS_PER_FACT) in body_prompt,
   body_prompt[:0])

# ---- blend
line = blend._length_line([{"prose": "word " * 2000}], {"min": TYPED, "max": TYPED})
ok("consumer 7, blend: LENGTH is stated against the person's number",
   "{:,}".format(TYPED) in line, line)

# ---- readable, the step that used to ignore all of this
PROMPTS[:] = []
art = {"h1": "H", "intro": "Costs run to $4,700 [c1].", "quick_answer": "Short answer.",
       "sections": [{"heading": "A", "prose": "Soft costs are 60% of it [c2]. " * 40}],
       "faq": [], "close": "Do it.", "close_heading": "Next"}
real = llm.json_call
llm.json_call = capture_json
try:
    readable.run(copy.deepcopy(art), {"word_band": {"min": TYPED, "max": TYPED}}, st_big, say)
finally:
    llm.json_call = real
read_prompt = PROMPTS[0] if PROMPTS else ""
ok("consumer 8, readable: TARGET_WORDS is the person's number",
   "{:,}".format(TYPED) in read_prompt, read_prompt[:0])
ok("and it is nowhere near the ceiling that used to decide this",
   "2,100" not in read_prompt)


# ======================================================================================
# 4. Accepting the default uses the average of what actually ranks
# ======================================================================================
print("\naccepting the suggestion uses the average of the pages that rank")

run3 = store.new_run(chat, "kept the suggestion")
ctx3 = ctx_for(run3)
ask3 = run_research.run(ctx3, topic=TOPIC, angle="what changes after")["ask_words"]
# What loop._resume_words does when the person taps the chip instead of typing: the suggestion.
run_research.run(ctx3, word_target=ask3["suggested"])
rs3 = store.load_artifact(chat, run3, "research.json") or {}
ok("the suggestion is the middle of the measured band, unrounded so the sentence stays true",
   ask3["suggested"] == (1500 + 2200) // 2 == 1850, ask3["suggested"])
ok("taking it settles the band on that average",
   (rs3.get("build_spec") or {}).get("word_band") == {"min": 1850, "max": 1850},
   (rs3.get("build_spec") or {}).get("word_band"))
ok("the measurement is still kept beside it",
   (rs3.get("build_spec") or {}).get("word_band_measured") == {"min": 1500, "max": 2200})
ok("and the run records which number it is writing to", rs3.get("word_target") == 1850, rs3.get("word_target"))

ok("a typed number and the suggestion cannot both be right, and the typed one won",
   (store.load_artifact(chat, run2, "research.json") or {})["build_spec"]["word_band"]["max"] == TYPED
   != ask3["suggested"])


# ======================================================================================
# 5. Readable's target tracks the person's number, short article and long
# ======================================================================================
print("\nreadable follows the length it was given, up as well as down")

short_art = {"h1": "H", "intro": "One.", "quick_answer": "", "sections": [{"heading": "A", "prose": "word " * 900}],
             "faq": [], "close": "Close.", "close_heading": "Next"}
long_art = copy.deepcopy(short_art)
long_art["sections"][0]["prose"] = "word " * 3400

ok("a short article asked for 1,400 gets 1,400",
   readable.target_words(short_art, {"word_band": {"min": 1400, "max": 1400}}, None) == 1400)
ok("a long article asked for 3,400 gets 3,400, and is NOT cut to 2,100",
   readable.target_words(long_art, {"word_band": {"min": 3400, "max": 3400}}, None) == 3400,
   readable.target_words(long_art, {"word_band": {"min": 3400, "max": 3400}}, None))
ok("even an article that arrives at 3,400 words keeps a 3,400 target",
   readable.words(long_art) > 3000 and readable.target_words(long_art, {"word_band": {"min": 3400, "max": 3400}}, None) > 3000)
ok("the architect's own record wins, because it is the number it divided up",
   readable.target_words(short_art, {"word_band": {"min": 1400, "max": 1400}}, {"word_budget": {"target": 2900}}) == 2900)
ok("with no length recorded anywhere it leaves the length where it stands, with no cap",
   readable.target_words(long_art, {}, {}) == readable.words(long_art))

# the same two lengths through the real step, reading the prompt the model would have seen
def readable_prompt(article, target):
    PROMPTS[:] = []
    real = llm.json_call
    llm.json_call = capture_json
    try:
        readable.run(copy.deepcopy(article), {"word_band": {"min": target, "max": target}}, {}, say)
    finally:
        llm.json_call = real
    return PROMPTS[0] if PROMPTS else ""

p_short, p_long = readable_prompt(short_art, 1400), readable_prompt(long_art, 3400)
ok("the short article is asked for 1,400 words", "1,400" in p_short, p_short[:0])
ok("the long one is asked for 3,400, which the old ceiling made impossible",
   "3,400" in p_long and "2,100" not in p_long, p_long[:0])


# ======================================================================================
# 6. The fact count follows the length
# ======================================================================================
print("\nthe fact count follows the length instead of a fixed cap")

ok("readable keeps target / WORDS_PER_FACT facts: 1,400 words -> %d" % round(1400 / C.WORDS_PER_FACT),
   ("{:,}".format(max(6, round(1400 / C.WORDS_PER_FACT))) in p_short), p_short[:0])
ok("and a longer article keeps more of them: 3,400 words -> %d" % round(3400 / C.WORDS_PER_FACT),
   ("{:,}".format(max(6, round(3400 / C.WORDS_PER_FACT))) in p_long)
   and round(3400 / C.WORDS_PER_FACT) > round(1400 / C.WORDS_PER_FACT))

ok("write_body works the same room out for a section, from the same constant",
   write_body.facts_room({"word_target": 330}) == 3 and write_body.facts_room({"word_target": 880}) == 8,
   (write_body.facts_room({"word_target": 330}), write_body.facts_room({"word_target": 880})))
ok("a longer section is told it has room for more facts",
   write_body.facts_room({"word_target": 900}) > write_body.facts_room({"word_target": 300}))
ok("and a section with no target still gets an honest number rather than zero",
   write_body.facts_room({}) >= 1)

st_small, _ = allocate_with(1400)
ok("end to end, a shorter article gives every section a smaller target",
   sum(s["word_target"] for s in st_small["sections"]) < sum(s["word_target"] for s in st_big["sections"]),
   (st_small["word_budget"]["base"], st_big["word_budget"]["base"]))
ok("so the body writer is told to carry fewer facts in it",
   write_body.facts_room(st_small["sections"][0]) < write_body.facts_room(st_big["sections"][0]),
   (write_body.facts_room(st_small["sections"][0]), write_body.facts_room(st_big["sections"][0])))


# ======================================================================================
# 7. The parts that are still measurement, and must stay measurement
# ======================================================================================
print("\nwhat is measured stays measured")

ok("assemble still MEASURES a band; it never decides the length",
   research_assemble.settle_word_band({"word_band": {"min": 1000, "max": 2000}}, None)["word_band"]
   == {"min": 1000, "max": 2000})
settled = research_assemble.settle_word_band({"word_band": {"min": 1000, "max": 2000}}, 2500)
ok("settling twice does not overwrite the measurement with the answer",
   research_assemble.settle_word_band(settled, 2500)["word_band_measured"] == {"min": 1000, "max": 2000})
ok("a number nobody could mean is refused, so a stray reply cannot set the length",
   research_assemble.as_words(12) is None and research_assemble.as_words(999999) is None
   and research_assemble.as_words("2,700") == 2700)
ok("with no band measured at all, the question still has something honest to offer",
   research_assemble.suggested_words({}) == research_assemble.DEFAULT_WORDS)
q, why = run_research._ask_block("cost per hire", {}, 2000)
ok("and it says plainly that nothing was measured, rather than dressing a default as a fact",
   "could not measure" in q and "starting point" in q, q)


# clean up what this suite planted
if _saved_index is not None:
    store.save_knowledge("site_index.json", _saved_index)
shutil.rmtree(store.chat_dir(chat), ignore_errors=True)

print("\nStubbed model, wire and web. Proves the length is decided once, by a person, and that "
      "every step downstream reads that one number.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all word-count checks passed")
