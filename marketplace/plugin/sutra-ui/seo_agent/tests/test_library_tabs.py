"""tests/test_library_tabs.py — the five Library tabs, assembled server-side.

Entirely offline, no model calls. Builds fixture artifact files shaped exactly like the real
producers write them (research.json, work-shape.json, work-allocate.json, work-headings.json,
blueprint.json, write-report.json, source-check.json) and checks each tab's rows against them.

What it proves:
  * a tab whose gating file does not exist yet is None, so the screen greys it out;
  * every row traces to a named field on a named file -- nothing here is invented;
  * old rows and runs missing a field still render (partial data, not a crash);
  * the Architect tab's sections carry the FINAL headings, the working job text, the word target
    and the allocator's "why", and "what was left out" is the real diff against the candidates.
"""
import os
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store, library_tabs as lt          # noqa: E402

FAILS = []
CHECKS = [0]


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


MADE = []
ITEMS = []


def chat_and_run(topic):
    c = store.new_chat("library tabs test")
    r = store.new_run(c, topic)
    MADE.append(c)
    return c, r


# ---- gating: nothing exists yet -----------------------------------------------------------------
print("\na run with nothing written yet: every tab is None, not a half-empty table")

c0, r0 = chat_and_run("nothing yet")
item0 = store.library_start(c0, r0, "req")
ITEMS.append(item0)
meta0 = store.library_get(item0)
tabs0 = lt.all_tabs(meta0)
ok("search_picture is None before search-picture.md exists", tabs0["search_picture"] is None)
ok("research is None before research.json exists", tabs0["research"] is None)
ok("architect is None before work-headings.json exists", tabs0["architect"] is None)
ok("edits is None before write-report.json + draft.md exist", tabs0["edits"] is None)


# ---- tab 1: Search picture ------------------------------------------------------------------
print("\nSearch picture reads research.json, gated on the picture milestone")

c1, r1 = chat_and_run("cost per hire")
item1 = store.library_start(c1, r1, "req")
ITEMS.append(item1)
RESEARCH = {
    "angle": "Cost per hire is a lever, not a scoreboard",
    "spine": "Treat cost per hire as one input into a hiring budget, not the whole story",
    "world": {"about": "How to calculate and use cost per hire",
             "not_about": "General recruiting software comparisons"},
    "persona": {"name": "Heads of talent at 200-2000 person companies", "lens": "budget owner", "why": "x"},
    "evidence": {
        "team": [{"role": "Recruiter", "focus": "sourcing costs"},
                 {"role": "Finance partner", "focus": "budget allocation"},
                 {"role": "Hiring manager", "focus": "time to fill"},
                 {"role": "People analytics", "focus": "benchmarks"}],
        "turns": [{"persona": "Recruiter", "question": "What counts as a sourcing cost?",
                  "queries": [], "sources": 3, "answer": "..."},
                 {"persona": "Finance partner", "question": "How is this budgeted quarterly?",
                  "queries": [], "sources": 2, "answer": "..."}],
    },
    "reuse": {"verdict": "reuse", "why": "an existing page already ranks",
             "chosen_links": [{"url": "https://example.com/cost-per-hire", "title": "Cost per hire"}]},
    "cannibalisation": None,
    "keywords": {
        "primary": {"keyword": "cost per hire", "volume": 2400, "kd": 38, "intent": "informational", "why": "x"},
        "variations": [{"keyword": "cost per hire formula", "volume": 320, "kd": 30, "intent": "informational"}],
        "secondary": [{"keyword": "average cost per hire", "volume": 480, "kd": 34, "intent": "informational",
                       "why": "anchors the benchmark section"}],
        "in_body": ["recruiting costs", "hiring budget"],
    },
    "serp": {
        "who_ranks": [{"rank": i, "title": "Result %d" % i, "url": "https://example%d.com" % i,
                       "domain": "example%d.com" % i} for i in range(1, 11)],
        "ai_overview": {"text": "Cost per hire averages $4,700 in the US.", "cites": ["https://example1.com"]},
        "paa_on": ["What is a good cost per hire?", "How do you reduce cost per hire?"],
    },
    "winners": {"common_h2s": ["What is cost per hire", "How to calculate it"],
               "gaps_to_own": ["A worked example with real numbers"], "drift": ["unrelated ATS comparisons"]},
    "build_spec": {"word_band": {"min": 2400, "max": 3000}},
}
store.save_artifact(c1, r1, "research.json", RESEARCH)
store.save_artifact(c1, r1, "dossier.md", "# Dossier\n\nfull text\n")
store.save_artifact(c1, r1, "voices-from-the-field.md", "# Voices\n\nfull text\n")

meta1 = store.library_get(item1)
ok("still None: research.json exists but the picture milestone has not been reached",
   lt.search_picture(meta1) is None)

store.save_artifact(c1, r1, "search-picture.md", "# The search picture\n\nSummary.\n")
meta1 = store.library_get(item1)
sp = lt.search_picture(meta1)
ok("search_picture fills in once the picture milestone exists", sp is not None)
ok("primary keyword carries volume and difficulty",
   sp["primary"] == {"keyword": "cost per hire", "volume": 2400, "kd": 38}, sp["primary"])
ok("variations carry volume and difficulty",
   sp["variations"] == [{"keyword": "cost per hire formula", "volume": 320, "kd": 30}], sp["variations"])
ok("in-body terms are plain strings, no numbers",
   sp["in_body"] == ["recruiting costs", "hiring budget"], sp["in_body"])
ok("average word count is the midpoint of the measured band", sp["avg_words"] == 2700, sp["avg_words"])
ok("ten ranked results, one row each",
   len(sp["who_ranks"]) == 10 and sp["who_ranks"][0] == {"rank": 1, "title": "Result 1",
                                                          "url": "https://example1.com", "domain": "example1.com"},
   sp["who_ranks"][:1])
ok("Google's own answer carries the text", sp["ai_overview"] == "Cost per hire averages $4,700 in the US.")
ok("questions people ask", sp["paa"] == RESEARCH["serp"]["paa_on"])
ok("what they all cover", sp["common"] == RESEARCH["winners"]["common_h2s"])
ok("what none of them cover", sp["gaps"] == RESEARCH["winners"]["gaps_to_own"])
ok("no ids and no 'why this keyword' leaked onto the tab",
   "why" not in (sp["primary"] or {}) and "id" not in sp)

rs = lt.research(meta1)
ok("Research tab: angle, spine, about, not-about", rs["angle"] == RESEARCH["angle"]
   and rs["spine"] == RESEARCH["spine"] and rs["about"] == RESEARCH["world"]["about"]
   and rs["not_about"] == RESEARCH["world"]["not_about"])
ok("written for is one line built from the persona", "budget owner" in rs["persona"])
ok("four researchers", len(rs["researchers"]) == 4)
recruiter = next(r for r in rs["researchers"] if r["role"] == "Recruiter")
ok("each researcher expands to their own questions",
   recruiter["questions"] == ["What counts as a sourcing cost?"], recruiter["questions"])
finance = next(r for r in rs["researchers"] if r["role"] == "Finance partner")
ok("questions are matched by role, not just dumped on every researcher",
   finance["questions"] == ["How is this budgeted quarterly?"])
ok("do you already have this page: yes, with a link",
   rs["have_it"]["links"][0]["url"] == "https://example.com/cost-per-hire")
ok("the dossier link is available", rs["dossier"] is True)
ok("the voices-from-the-field link is available", rs["voices"] is True)


# ---- tab 3: Architect -----------------------------------------------------------------------
print("\nArchitect reads the architect's OWN output, with final headings and what was left out")

c2, r2 = chat_and_run("architect run")
item2 = store.library_start(c2, r2, "req")
ITEMS.append(item2)
store.save_artifact(c2, r2, "blueprint.json", {"h1": "Cost per hire",
    "sections": [{"h2": "What is cost per hire"}, {"h2": "How to calculate it"},
                {"h2": "Regional differences"}, {"h2": "Vendor comparisons"}],
    "faq": [{"q": "Is cost per hire the same as time to fill?"}, {"q": "What is a good benchmark?"}]})
meta2 = store.library_get(item2)
ok("Architect is None: blueprint.json exists (the plan milestone) but work-headings.json does not",
   lt.architect(meta2) is None)

# shape.py picks its survivors straight off the blueprint's candidate menu, unrewritten -- the
# headline here matches the blueprint h2 exactly, the way the real step leaves it. headings.py is
# the step that renames it, in WORK_HEADINGS below.
WORK_SHAPE = {"structure": {"format_archetype": "how-to-guide", "spine": "The spine",
    "sections": [{"headline": "What is cost per hire", "job": "Define the metric plainly",
                 "boxes": [1, 2], "h3s": []},
                {"headline": "How to calculate it", "job": "Walk through the formula",
                 "boxes": [3], "h3s": ["The formula", "A worked example"]}],
    "dropped_items": ["Vendor comparisons"]}}
WORK_ALLOCATE = {"structure": {"word_budget": {"target": 2200, "band": {"min": 2400, "max": 3000}, "base": 1980},
    "sections": [{"word_target": 500}, {"word_target": 700}]},
    "allocation": {"raw": {"allocation": [{"section": 0, "share": 0.25, "why": "It anchors the definition"},
                                          {"section": 1, "share": 0.35, "why": "It carries the worked example"}]}}}
WORK_HEADINGS = {"structure": {"format_archetype": "how-to-guide", "spine": "The spine",
    "word_budget": {"target": 2200},
    "sections": [{"headline": "What cost per hire actually measures", "h3s": []},
                {"headline": "How to calculate cost per hire, step by step",
                 "h3s": ["The formula", "A worked example"]}]},
    "heading_map": {"h1_final": "Cost per hire: the full formula"}}
store.save_artifact(c2, r2, "work-shape.json", WORK_SHAPE)
store.save_artifact(c2, r2, "work-allocate.json", WORK_ALLOCATE)
store.save_artifact(c2, r2, "work-headings.json", WORK_HEADINGS)

meta2 = store.library_get(item2)
arch = lt.architect(meta2)
ok("Architect fills in once work-headings.json exists", arch is not None)
ok("header: format, target words, section and sub-heading counts",
   arch["format"] == "how-to-guide" and arch["target_words"] == 2200
   and arch["n_sections"] == 2 and arch["n_sub_headings"] == 2, arch)
ok("the spine", arch["spine"] == "The spine")
ok("headings shown are the FINAL ones from work-headings.json, not the working titles",
   [s["headline"] for s in arch["sections"]]
   == ["What cost per hire actually measures", "How to calculate cost per hire, step by step"])
ok("each section carries its word target and fact count from shape/allocate",
   arch["sections"][0]["word_target"] == 500 and arch["sections"][0]["n_facts"] == 2, arch["sections"][0])
ok("each section carries the allocator's one-line reason",
   arch["sections"][0]["why"] == "It anchors the definition"
   and arch["sections"][1]["why"] == "It carries the worked example")
ok("expanding a section shows its sub-headings",
   arch["sections"][1]["h3s"] == ["The formula", "A worked example"])
ok("the job comes from the working shape (Purpose button content)",
   arch["sections"][0]["job"] == "Define the metric plainly")
ok("what was left out: the dropped candidate section and the two FAQ questions",
   set(arch["left_out"]["sections"]) == {"Regional differences", "Vendor comparisons"}
   and arch["left_out"]["faq"] == ["Is cost per hire the same as time to fill?",
                                   "What is a good benchmark?"], arch["left_out"])
ok("the left-out note reads in plain English",
   "2 candidate sections" in arch["left_out"]["note"] and "2 questions" in arch["left_out"]["note"],
   arch["left_out"]["note"])


# ---- tab 5: Edits ---------------------------------------------------------------------------
print("\nEdits reads write-report.json and source-check.json, not a raw JSON dump")

c3, r3 = chat_and_run("edits run")
item3 = store.library_start(c3, r3, "req")
ITEMS.append(item3)
store.save_artifact(c3, r3, "draft.md", "# Cost per hire\n\nbody\n")
meta3 = store.library_get(item3)
ok("Edits is None before write-report.json exists", lt.edits(meta3) is None)

store.save_artifact(c3, r3, "write-report.json",
                    {"steps": {"blend": {}, "wrapper": {}, "readable": {"applied": True}, "links": {}},
                     "length": {"words": 2180}})
store.save_artifact(c3, r3, "source-check.json",
                    {"counts": {"checked": 62, "supported": 54, "corrected": 5, "softened": 2, "removed": 1}})
store.save_artifact(c3, r3, "source-check.md", "# Source check\n\nfull text\n")
store.save_artifact(c3, r3, "research.json", {"build_spec": {"word_band": {"min": 2400, "max": 3000}}})

meta3 = store.library_get(item3)
ed = lt.edits(meta3)
ok("Edits fills in once write-report.json + draft.md exist", ed is not None)
ok("one line per pass that actually ran, in plain English",
   ed["passes"] == ["Joined the sections into one piece",
                    "Wrote the intro, quick answer, FAQ and close",
                    "Rewrote it to be read", "Laid in the links"], ed["passes"])
ok("a pass that never ran (coherence, sentences, slop, clean) is not shown",
   "Read the article whole" not in ed["passes"])
ok("the source check line: checked, fine, corrected, softened, removed",
   ed["source_check"] == {"checked": 62, "fine": 54, "corrected": 5, "softened": 2, "removed": 1})
ok("it links to source-check.md", ed["has_source_check_doc"] is True)
ok("final word count against target", ed["words"] == 2180 and ed["target_words"] == 2700)


# ---- old rows and old runs missing fields still render --------------------------------------
print("\nold rows and runs missing fields still render, nothing crashes")

c4, r4 = chat_and_run("sparse old run")
item4 = store.library_start(c4, r4, "req")
ITEMS.append(item4)
store.save_artifact(c4, r4, "research.json", {"angle": "An angle with nothing else set"})
store.save_artifact(c4, r4, "search-picture.md", "# picture\n")
store.save_artifact(c4, r4, "draft.md", "# T\nbody\n")
store.save_artifact(c4, r4, "write-report.json", {})
meta4 = store.library_get(item4)
sp4 = lt.search_picture(meta4)
ok("a sparse research.json still renders a tab, not a crash",
   sp4 is not None and sp4["primary"] is None and sp4["who_ranks"] == [] and sp4["avg_words"] is None, sp4)
rs4 = lt.research(meta4)
ok("a sparse Research tab still renders", rs4["angle"] == "An angle with nothing else set"
   and rs4["researchers"] == [] and rs4["have_it"] is None and rs4["dossier"] is False)
ed4 = lt.edits(meta4)
ok("an empty write-report.json still renders an Edits tab with no passes shown",
   ed4 is not None and ed4["passes"] == [] and ed4["source_check"] is None)

# a whole missing run: everything comes back None through the tabs route the screen actually calls
#
# importing agents_api activates the person's SAVED company (companies.activate_saved(), run at
# import time), which repins store.data_dir() -- see store.py's own data_dir() docstring on this
# exact hazard. Running after test_companies (run_all.sh's fixed suite order) that pin lands on a
# company OTHER than the one every item above was just written into, and every lookup below would
# 404. So the data dir this file has been using all along is captured BEFORE the import and
# reasserted right after -- "a later SEO_AGENT_DATA wins" applies to set_data_dir calls too, so
# ours, called after the activation, is the one that stands.
_data_dir = store.data_dir()
try:
    import agents_api
    store.set_data_dir(_data_dir)
except Exception as e:                                        # noqa: BLE001
    agents_api = None
    print("  SKIP  the route itself (agents_api would not import: %s)" % str(e)[:120])
if agents_api:
    r = agents_api.api_library_tabs(item1)
    # the four tabs, plus (2026-09-21) where they came from: the run itself, the copy kept with
    # the article, or neither. See tests/test_library_tabs_shared.py for that half.
    ok("the route returns all four tabs in one payload",
       isinstance(r, dict) and set(r) == {"search_picture", "research", "architect", "edits",
                                          "source", "dropped"}, r and list(r))
    ok("assembled from the run, which is still on disk here", r.get("source") == "run", r.get("source"))
    ok("search_picture came through the route intact", r["search_picture"]["primary"]["keyword"] == "cost per hire")
    r404 = agents_api.api_library_tabs("no-such-item")
    ok("an item that does not exist is a 404", getattr(r404, "status_code", None) == 404, r404)
    for bad_id in ("../etc", "..", "has space"):
        rb = agents_api.api_library_tabs(bad_id)
        ok("the route refuses a bad id: %r" % bad_id, getattr(rb, "status_code", None) == 400, rb)


# ---- clean up -------------------------------------------------------------------------------
for i in ITEMS:
    store.library_delete(i)
import shutil
for c in MADE:
    shutil.rmtree(store.chat_dir(c), ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
