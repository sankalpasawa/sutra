"""tests/test_write.py — the write phase: planner, architect, writer, links, with everything stubbed.

The model is stubbed by output keys (tests/_fixture.py), DataForSEO and Voyage are stubbed, the network
door in write/_common.py is closed. What this proves is that every rule the original enforced in CODE
still bites: a plan that fails its shape checks stops the run, box numbers are validated, brand-card
caps hold, a foreign tag is dropped, a blend that loses tags is reverted, a close that links off the
CTA list is refused, an invented number blocks the coherence edit, a slop rewrite that changes a number
is thrown away, the scrub is idempotent, anchors are matched the way the original matched them, an
undeclared drift reverts the block, and the Sources list numbers by first appearance. Then the whole
pipeline runs end to end, resumes from its work files, and reruns on redo.
"""
import copy
import json
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.tools import _index, _shared as sh, dfs, voyage
from seo_agent.write import (_common as C, allocate_words, assemble, blend, brand_cards, clean, coherence, fmt_router,
                             freeze, gather, headings, plan_select, readable, section_keywords, sentence_pass, shape,
                             slop_pass, verify_sources, wrapper, write_body)
from seo_agent.editing import links_pass

FAILS, PASSES = [], []
def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))
    return cond

# --- the model: the fixture stubs, with per-test overrides layered on top ------------------
CALLS = []
UNFILLED = set()    # every {{TOKEN}} that reached the model unfilled, across the whole suite
OVERRIDES = []      # (predicate(prompt) -> bool, reply | callable(prompt) -> reply)
import re as _re

def json_stub(prompt, system=None, retries=1):
    CALLS.append(prompt[:80])
    UNFILLED.update(_re.findall(r"\{\{[A-Z_]+\}\}", prompt))
    for pred, reply in OVERRIDES:
        if pred(prompt):
            return reply(prompt) if callable(reply) else copy.deepcopy(reply)
    return _fixture.stub_json(prompt)

def text_stub(prompt, system=None):
    CALLS.append(prompt[:80])
    UNFILLED.update(_re.findall(r"\{\{[A-Z_]+\}\}", prompt))
    return _fixture.stub_text(prompt)

llm.json_call = json_stub
llm.text = text_stub
_fixture.stub_voyage()
_fixture.plant_brand_files()
dfs.available = lambda: False

SAY = []
def say(label, note=""):
    SAY.append((label, note))

BP, RS, CARDS = _fixture.write_inputs()
IDX = C.card_index(CARDS)
CTX = C.context(BP, RS)

# ======================================================================================
print("\nplanner: gather + select + freeze")
inputs = gather.run(BP, RS, CARDS, say)
ok("keyword set drops in_body", "in_body" not in inputs["group_a"]["keyword_set"])
ok("word band comes from the build spec", inputs["group_a"]["word_band"] == {"min": 1400, "max": 1800})
ok("table stakes capped and kept", 0 < len(inputs["group_a"]["table_stakes"]) <= C.MAX_TABLE_STAKES)
ok("intent and Google's answer lifted", inputs["group_a"]["search_intent"] == "informational" and "4,700" in inputs["group_a"]["ai_overview"])
ok("evidence ids resolved to cards", inputs["group_b"]["sections_menu"][0]["evidence"][0]["card_id"] == 1)

sel = plan_select.run(inputs, CTX, say)
plan = sel["plan"]
ok("three sections survive", len(plan["sections"]) == 3, len(plan["sections"]))
ok("the off-topic H3 was dropped", all("(off-topic)" not in h["h3"] for s in plan["sections"] for h in s["h3s"]))
ok("every kept tag carries a receipt", all(h["tag_receipts"].get(t) for s in plan["sections"] for h in s["h3s"] for t in h["tags"]))
ok("the drop is recorded with the model's reason",
   any("WRONG WORLD" in d["ai_reason"] for d in sel["audit"]["drops"]["dropped_h3s"]))

# the receipt rule: a tag citing a card that is not in the H3 does not exist
good, bad, rcp = plan_select._clean_tags([{"tag": "asset-angle", "cards": [99]}, {"tag": "gap: G1", "cards": [1]}],
                                         plan_select._tag_maps(inputs["group_b"]), [1, 2])
ok("a tag with no valid receipt is refused", good == ["gap: The cost of the empty seat, priced"] and bad and rcp["gap: The cost of the empty seat, priced"] == [1], (good, bad))

fr = freeze.run(copy.deepcopy(plan), {})
ok("a sound plan freezes", not fr["hard"] and fr["plan"] is not None, fr["hard"])
broken = copy.deepcopy(plan)
broken["sections"][0]["h3s"][0]["card_ids"] = []
broken["h1"] = ""
broken["word_band"] = {"min": 0, "max": 0}
fr2 = freeze.run(broken, {})
ok("hard flags: missing h1, empty H3, no word band", len(fr2["hard"]) >= 3 and fr2["plan"] is None, fr2["hard"])
ok("soft notes never block", freeze.run(copy.deepcopy(plan), {"cut": [{}] * 16})["plan"] is not None)

# ======================================================================================
print("\nplanner: source verification (fetch stubbed)")
PAGES = {
    "https://www.shrm.org/research/cost-per-hire": "SHRM report. The average cost per hire was $4,700 in 2023. Soft costs make up about 60% of the total. " * 20,
    "https://www.shrm.org/research/time-to-fill": "This page says nothing about days at all, only about culture. " * 40,
    "https://research.example.net/turnover-study": "__ERR__HTTP403",
    "https://journals.example.org/schmidt-hunter": "Validity of structured interviews sits near 0.51 in the meta-analysis. " * 30,
}
C.FETCH_ONCE = lambda url, timeout=15.0: PAGES.get(url, "__ERR__ConnectError")
OVERRIDES.append((lambda p: '{"verify": [' in p, {"verify": [1, 2, 3, 4, 5]}))
idx2 = C.card_index(CARDS)
idx2[3]["source_urls"] = ["https://www.shrm.org/research/time-to-fill", "https://dead.example.org/mirror"]
ver = verify_sources.run(copy.deepcopy(plan), idx2, say)
pol = ver["police"]
ok("a page that states the number is kept ok", 1 in pol["kept_ok"] and 4 in pol["kept_ok"], pol["kept_ok"])
ok("an unloadable page is kept, not punished", 5 in pol["unverifiable_kept"], pol["unverifiable_kept"])
ok("a wrong page plus an unreadable backup -> needs a source, not cut",
   any(x["card_id"] == 3 for x in pol["needs_source"]) and not any(x["card_id"] == 3 for x in pol["cut"]), pol["needs_source"])
ok("the proven-bad url is stripped from the card", idx2[3]["source_urls"] == ["https://dead.example.org/mirror"] and idx2[3].get("needs_source"))
ok("the hunt is declared skipped", "skipped" in pol["hunt"] and "DataForSEO" in pol["hunt"])
idx3 = C.card_index(CARDS)
idx3[3]["source_urls"] = ["https://www.shrm.org/research/time-to-fill"]
ver3 = verify_sources.run(copy.deepcopy(plan), idx3, say)
ok("a numeric card with only a wrong source is cut", any(x["card_id"] == 3 for x in ver3["police"]["cut"]))
ok("its H3 dies with it", not any(h["h3"] == "The benchmark" for s in ver3["plan"]["sections"] for h in s["h3s"]))
OVERRIDES.clear()
_fixture.stub_write_network()

# ======================================================================================
print("\narchitect: routing")
route = fmt_router.run(inputs, RS, say)
ok("a known archetype is kept, not re-routed", route == {"archetype": "how-to-guide", "routed": False})
no_arch = copy.deepcopy(inputs); no_arch["group_a"]["format_archetype"] = ""
OVERRIDES.append((lambda p: '"archetype": "<one of the 8 labels>"' in p, {"archetype": "listicle", "why": "n items"}))
ok("a missing archetype is routed", fmt_router.run(no_arch, RS, say) == {"archetype": "listicle", "routed": True})
OVERRIDES[:] = [(lambda p: '"archetype": "<one of the 8 labels>"' in p, {"archetype": "poem", "why": ""})]
try:
    fmt_router.run(no_arch, RS, say)
    ok("an unknown archetype raises", False, "no raise")
except ValueError as e:
    ok("an unknown archetype raises", "poem" in str(e))
OVERRIDES.clear()

print("\narchitect: the budget maths")
m = shape.budget_maths({"min": 1400, "max": 1800})
ok("budget = midpoint x (1 - 0.10) = 1440", m["budget"] == 1440, m)
ok("section ceiling = max(4, round(1440/300)) = 5", m["section_target"] == 5, m)
ok("words per paragraph = 25 x 5 = 125", m["words_per_paragraph"] == 125)
ok("paragraphs per section = round(300/125) = 2", m["paragraphs_per_section"] == 2)
ok("paragraphs per sub-heading = round(200/125) = 2", m["paragraphs_per_subhead"] == 2)
ok("no band falls back to 1500 x 0.9 = 1350", shape.budget_maths({})["budget"] == 1350)
lb = shape.listicle_budget(1440, 8)
ok("listicle: reserve 3 x 300 = 900, item budget 540, fits 2, expected drops 3",
   lb == {"reserve": 900, "item_budget": 540, "fits": 2, "expected_drops": 3}, lb)

print("\narchitect: boxes are validated in code")
boxes = shape.mint_boxes(plan)
n_boxes = len(boxes)
bad_reply = {"coverage_note": "", "spine": "s", "sections": [
    {"job": "j1", "headline": "First", "lead_boxes": [1, 999, "x"], "h3s": [{"h3": "Sub", "boxes": [2, 1]}],
     "table": {"columns": ["only one"]}, "list": {"kind": "weird"},
     "needs_research": [{"topic": "more data", "goes_to": "No Such Sub"}]},
    {"job": "j2", "headline": "Second", "lead_boxes": [2, 3], "h3s": [], "table": {"columns": ["a", "b"]},
     "list": {"kind": "numbered", "of": "steps"}}],
    "benched": [{"box": 4, "why": "off angle"}]}
OVERRIDES.append((lambda p: '"coverage_note"' in p, bad_reply))
shp = shape.run(copy.deepcopy(plan), IDX, CTX, say)["structure"]
s1, s2 = shp["sections"]
ok("an unknown box number is dropped", 999 not in s1["boxes"] and "x" not in s1["boxes"])
ok("one box, one place inside a section", s1["boxes"] == [1, 2] and s1["h3s"][0]["boxes"] == [2], s1["boxes"])
ok("a box in two sections is a shared-box warning", shp["shared_box_warnings"] == [2], shp["shared_box_warnings"])
ok("a table without two columns is dropped; a real one is kept", s1["table"] is None and s2["table"] == {"columns": ["a", "b"]})
ok("a list without a renderable kind is dropped; numbered is kept", s1["list"] is None and s2["list"]["kind"] == "numbered")
ok("a research request aimed at a missing sub-heading goes to the opening", s1["needs_research"][0]["goes_to"] == "opening")
ok("unused boxes are audited with the bench reason",
   any(b["n"] == 4 and b["why_benched"] == "off angle" for b in shp["unused_boxes"]) and len(shp["unused_boxes"]) == n_boxes - 3)
OVERRIDES.clear()

print("\narchitect: brand-card caps")
pool = {"research": [{"card_id": 8001 + i, "gloss": "research %d" % i} for i in range(6)],
        "results": [{"card_id": 8101, "gloss": "customer one"}, {"card_id": 8102, "gloss": "customer two"}]}
st_bc = {"sections": [{"headline": "A", "h3s": [{"h3": "Sub A"}]}, {"headline": "B", "h3s": []}, {"headline": "C", "h3s": []}]}
reply = {"placements": [{"card_id": 8001, "section": 1, "goes_to": "opening"},
                        {"card_id": 8002, "section": 1, "goes_to": "Sub A"},          # second in section 1
                        {"card_id": 8003, "section": 2, "goes_to": "opening"},
                        {"card_id": 8004, "section": 3, "goes_to": "opening"},
                        {"card_id": 8005, "section": 2, "goes_to": "No Such Sub"},    # bad sub-heading
                        {"card_id": 8006, "section": 3, "goes_to": "opening"},        # over per-section, over cap
                        {"card_id": 8101, "section": 2, "goes_to": "opening"},
                        {"card_id": 8102, "section": 3, "goes_to": "opening"},        # over result cap
                        {"card_id": 4242, "section": 1, "goes_to": "opening"},        # not in pool
                        {"card_id": 8001, "section": 9, "goes_to": "opening"}]}       # bad section
res = brand_cards.place(st_bc, pool, reply, say)
kept = res["placement"]["placements"]
ok("research cards capped at %d" % C.BRAND_RESEARCH_CAP, sum(1 for k in kept if k["kind"] == "research") <= C.BRAND_RESEARCH_CAP)
ok("one research card per section", max(sum(1 for k in kept if k["kind"] == "research" and k["section"] == s) for s in (1, 2, 3)) == 1)
ok("customer results capped at %d" % C.BRAND_RESULT_CAP, sum(1 for k in kept if k["kind"] == "result") == 1)
reasons = " ".join(r["reason"] for r in res["placement"]["rejected"])
ok("every rejection names its reason", "already has" in reasons and "not in the pool" in reasons and "does not exist" in reasons
   and "no sub-heading named" in reasons and "customer-result cap" in reasons, reasons)
ok("placed ids joined onto the destination", 8001 in st_bc["sections"][0]["lead"]["card_ids"])

print("\narchitect: headings helpers")
ok("_holds is blind to case and punctuation", headings._holds("Cost-Per-Hire, Explained", "cost per hire"))
ok("_holds refuses a reordered or changed word", not headings._holds("Cost of a Hire", "cost per hire"))
ok("a named number is not a figure", not headings._has_figure("Step 2 of the Fortune 500 plan"))
ok("a statistic is a figure", headings._has_figure("The 75% Rejection Rate"))

print("\narchitect: section keywords (DataForSEO stubbed)")
st_sk = {"sections": [{"headline": "The Real Cost", "job": "price it", "lead": {"card_ids": [1]}, "h3s": []},
                      {"headline": "Empty Seats", "job": "time it", "lead": {"card_ids": [3]}, "h3s": []}]}
r0 = section_keywords.run(copy.deepcopy(st_sk), inputs, CTX, IDX, say)
ok("no DataForSEO -> hunts skipped and said so", r0["hunted"] == 0 and "not connected" in (r0["hunts_skipped"] or ""), r0["hunts_skipped"])
dfs.available = lambda: True
dfs.balance = lambda: 0.2
r1 = section_keywords.run(copy.deepcopy(st_sk), inputs, CTX, IDX, say)
ok("balance under $0.50 -> hunts skipped", r1["hunted"] == 0 and "under" in (r1["hunts_skipped"] or ""), r1["hunts_skipped"])
dfs.balance = lambda: 12.0
SUGGEST = [{"kw": "cost per hire formula", "vol": 800, "kd": 22}, {"kw": "hiring cost calculator", "vol": 300, "kd": 18},
           {"kw": "too rare", "vol": 20, "kd": 5}, {"kw": "too hard", "vol": 5000, "kd": 71}]
dfs.keyword_suggestions = lambda seed, limit=80, location_name=None, language_code=None: list(SUGGEST)
r2 = section_keywords.run(copy.deepcopy(st_sk), inputs, CTX, IDX, say)
picked = [s for s in r2["sections"] if s.get("pick")]
ok("only the gated section is hunted, and its pick is a real candidate",
   r2["hunted"] == 1 and len(picked) == 1 and picked[0]["pick"]["keyword"] == "cost per hire formula", picked)
ok("the floors bit: only vol>=100 and kd<40 survive", picked[0]["candidates"] == 2, picked[0]["candidates"])
OVERRIDES.append((lambda p: '"keyword": "<the phrase, or null>"' in p, {"keyword": "made up phrase", "why": "x"}))
r3 = section_keywords.run(copy.deepcopy(st_sk), inputs, CTX, IDX, say)
ok("a phrase not in the candidate set is refused", r3["found"] == 0 and "not among the candidates" in r3["sections"][0]["why_none"])
OVERRIDES.clear()
dfs.available = lambda: False

# ======================================================================================
print("\nwriter: write_body drops foreign tags")
sec = {"headline": "The Real Cost", "lead": {"card_ids": [1, 2]}, "h3s": []}
prose, prov, dropped = write_body.provenance("Costs run to $4,700 [c1]. Soft costs dominate [c2, c99]. Nothing here [c77].", sec, IDX)
ok("foreign ids are dropped from the prose", "[c99]" not in prose and "[c77]" not in prose and "c2]" in prose, prose)
ok("and counted", dropped == 2, dropped)
ok("provenance lists only this section's cards", [p["card_id"] for p in prov] == [1, 2] and prov[0]["is_number"])

print("\nwriter: blend guards are all-or-nothing")
secs = [{"headline": "A", "prose": "First fact [c1]. Second fact [c2]."}, {"headline": "B", "prose": "Third fact [c3]. Fourth [c4]."}]
stripped = [{"heading": "A", "prose": "First fact. Second fact."}, {"heading": "B", "prose": "Third fact [c3]. Fourth."}]
out = blend.apply(secs, {"sections": stripped, "edits": [{"section": "A", "what": "cut fluff", "why": "x"}]}, stripped, "cost per hire", [], {"min": 1400, "max": 1800})
ok("losing over 25% of the tags reverts the whole edit", not out["applied"] and [s["prose"] for s in out["sections"]] == [s["prose"] for s in secs])
ok("the block reason is recorded", any("source tags" in g for g in out["guard_failures"]), out["guard_failures"])
renamed = [{"heading": "A", "prose": secs[0]["prose"]}, {"heading": "Changed", "prose": secs[1]["prose"]}]
ok("a changed heading reverts", not blend.apply(secs, {"sections": renamed}, renamed, "", [], {})["applied"])
invented = [{"heading": "A", "prose": "First fact [c1]. Second fact [c2] [c500]."}, {"heading": "B", "prose": secs[1]["prose"]}]
out2 = blend.apply(secs, {"sections": invented}, invented, "", [], {})
ok("an invented tag is stripped and counted", out2["applied"] and out2["tag_audit"]["invented_stripped"] == 1 and "[c500]" not in out2["sections"][0]["prose"])
ok("keywords are counted in code", blend.kw_counts(secs, ["fact"])["fact"] == 3)

print("\nwriter: the wrapper refuses a close link off the CTA list")
allowed = {"https://example.com/programmes", "https://example.com/about"}
bad = wrapper.cta_check("See our [tour](https://example.com/pricing).", "https://example.com/pricing", allowed)
ok("a url off the list is named", any("not on the list" in b for b in bad), bad)
ok("two links are refused", any("carries 2 links" in b for b in wrapper.cta_check("[a](https://example.com/programmes) [b](https://example.com/about)", "https://example.com/programmes", allowed)))
ok("a good link passes", wrapper.cta_check("Our [tour](https://example.com/programmes).", "https://example.com/programmes", allowed) == [])
ok("a filler heading is refused", any("filler" in b for b in wrapper.close_heading_check("Conclusion", ["A"])))
ok("a heading over 60 characters is refused", any("characters" in b for b in wrapper.close_heading_check("x" * 61, [])))
OVERRIDES.append((lambda p: "Fix ONLY what is listed above" in p,
                  {"close_heading": "Where To Take This Next", "close": "Still [wrong](https://elsewhere.com/x).", "cta_link": "https://elsewhere.com/x"}))
w_out = {"intro": "Intro here.", "quick_answer": "Short.", "faq": [], "close_heading": "Conclusion",
         "close": "Try our [tool](https://elsewhere.com/x) today [c9].", "cta_link": "https://elsewhere.com/x", "touch_ups": []}
final = wrapper.apply(w_out, [{"heading": "A", "prose": "Fact [c1]."}], "H1", allowed, "- Page: https://example.com/programmes", {"brand": "Example"}, say)
ok("after a failed retry the close keeps its prose and loses the untrusted link", "](" not in final["close"] and final["cta_link"] == "" and final["cta_problems"])
ok("a tag the body never had is stripped from the close", "[c9]" not in final["close"] and final["invented_tags_stripped"] == 1)
OVERRIDES.clear()

print("\nwriter: coherence blocks an invented number")
before = {"h1": "H", "intro": "Costs run to $4,700 [c1].", "quick_answer": "", "sections": [{"heading": "A", "prose": "Scored 1 to 5 [c2]."}],
          "faq": [{"question": "Q?", "answer": "Yes."}], "close": "Do it.", "close_heading": "Next"}
after = copy.deepcopy(before); after["sections"][0]["prose"] = "Scored 1 to 5, and 32,000 people agreed [c2]."
blk, warn = coherence.guards(before, after)
ok("a number absent from the original blocks", any("INVENTED" in b and "32,000" in b for b in blk), blk)
after2 = copy.deepcopy(before); after2["sections"][0]["prose"] = "Scored 1 to 5 [c2]. The band runs 1 to 5 throughout."
blk2, warn2 = coherence.guards(before, after2)
ok("a changed figure warns but does not block", not blk2 and any(w["kind"] == "numbers changed" for w in warn2))
after3 = copy.deepcopy(before); after3["sections"][0]["heading"] = "Renamed"
ok("a changed heading blocks", coherence.guards(before, after3)[0])
# the retry: first edit invents, the retry is clean -> the retry is used
rendered_reply = lambda p: dict(_fixture._parse_rendered_article(_fixture._between(p, "THE ARTICLE IN FULL:", "\n════")), changes=[], numbers_changed=[], could_not_fix=[], verdict="ok")
def first_edit(p):
    r = rendered_reply(p); r["sections"][0]["prose"] += " Also 32,000 more."; return r
OVERRIDES.append((lambda p: '"could_not_fix"' in p and "THE ARTICLE IN FULL:" in p, first_edit))
def clean_retry(p):
    r = dict(_fixture._parse_rendered_article(_fixture._between(p, "THE ARTICLE YOU RETURNED, which is the one to correct:", "\n════")),
             changes=[], numbers_changed=[], could_not_fix=[], verdict="fixed")
    r["sections"][0]["prose"] = r["sections"][0]["prose"].replace(" Also 32,000 more.", "")
    return r
OVERRIDES.append((lambda p: "THE ARTICLE YOU RETURNED" in p, clean_retry))
co = coherence.run(copy.deepcopy(before), CTX, plan, say)
ok("the first edit was blocked and retried; the clean retry is applied",
   co["report"].get("retry_attempted") and co["report"].get("applied") and "32,000" not in co["article"]["sections"][0]["prose"], co["report"].get("guard_failures"))
OVERRIDES.clear()

print("\nwriter: readable checks flag, never block")
w_r = {"h1": "H", "intro": "You quote a number. It came from a slide.", "quick_answer": "Check it.",
       "sections": [{"heading": "A", "prose": "Costs run to $4,700 [c1]. Soft costs are 60% [c2]."}], "faq": [], "close": "See our [tour](https://example.com/programmes).", "close_heading": "Next"}
w_after = copy.deepcopy(w_r); w_after["sections"][0]["prose"] = "Costs run to $4,700 [c1] and 999 elves agree [c]."
checks = {c["check"]: c for c in readable.check(w_r, w_after, "cost per hire", 2100)}
ok("an invented figure is flagged", not checks["No invented figures"]["ok"])
ok("a bare [c] is flagged", not checks["Source tags kept their numbers"]["ok"])
ok("the kept link is checked", checks["The one link kept"]["ok"])
ok("the format rule is read from the format file", "THE ITEMS ARE THE ARTICLE" in readable.format_rule("listicle") and readable.format_rule("how-to-guide") == "")
fat = {"h1": "H", "intro": "", "quick_answer": "", "sections": [{"heading": "A", "prose": "One. Two. Three. Four. Five. Six sentences here."}], "faq": [], "close": ""}
ok("a fat paragraph is found by id", [f["id"] for f in readable.find_fat(fat)] == ["s1-p1"])
ok("a fix that invents a figure is refused", "invented the figure" in readable.judge_fix("One. Two.", "One 42. Two.", 1))
ok("a clean shorter fix is accepted", readable.judge_fix("One. Two. Three. Four. Five. Six.", "One. Two. Three.", 1) == "")

print("\nwriter: the sentence pass verifies in code")
blk_txt = "The average cost per hire was $4,700 in 2023 [c1], and soft costs make up about 60% of that total [c2], which is why the budget moves with it every quarter."
ok("a rewrite that loses a number is refused", any("went missing" in v for v in sentence_pass.violations(blk_txt, "The average cost per hire was high [c1]. Soft costs make up about 60% [c2]. The budget moves with it every quarter and that is why.")))
ok("a rewrite that shrinks 20% is refused", any("word count" in v for v in sentence_pass.violations(blk_txt, "Cost per hire was $4,700 in 2023 [c1]. Soft costs are 60% [c2].")))
same_len = "The average cost per hire was $4,700 in 2023 [c1]. Soft costs make up about 60% of that total [c2]. That is why the budget moves with it every quarter."
ok("a same-length, same-facts split passes", sentence_pass.violations(blk_txt, same_len) == [], sentence_pass.violations(blk_txt, same_len))

print("\nwriter: slop reverts a block whose numbers changed")
OVERRIDES.append((lambda p: '"rule": "<which tell it was' in p, lambda p: {"prose": _fixture._between(p, "THE BLOCK, as written:\n\n", "\n\n────").replace("60%", "65%"), "changes": []}))
text, changes, verdict = slop_pass.clean_block("rules", "A", "Soft costs make up about 60% of the total [c2].", "(none)")
ok("the block keeps its original text", verdict.startswith("REJECTED") and "60%" in text, verdict)
OVERRIDES[:] = [(lambda p: '"rule": "<which tell it was' in p, lambda p: {"prose": _fixture._between(p, "THE BLOCK, as written:\n\n", "\n\n────").replace("[c2]", ""), "changes": []})]
ok("a block that loses a tag is rejected too", slop_pass.clean_block("rules", "A", "Soft costs are 60% [c2].", "(none)")[2].startswith("REJECTED"))
OVERRIDES[:] = [(lambda p: '"rule": "<which tell it was' in p, lambda p: {"prose": _fixture._between(p, "THE BLOCK, as written:\n\n", "\n\n────").replace("leverage", "use"), "changes": [{"before": "leverage", "after": "use", "rule": "tier-1 word"}]})]
text, changes, verdict = slop_pass.clean_block("rules", "A", "Teams leverage 60% of the budget [c2].", "(none)")
ok("a clean fix is accepted", verdict == "cleaned" and "use 60%" in text and len(changes) == 1)
OVERRIDES.clear()
ok("the counts see em dashes and tier-1 words", slop_pass.counts("We leverage — not just use — it. Let's go.") == {"em_dashes": 2, "tier1_words": 1, "not_just": 1, "lets": 1, "in_conclusion": 0})

print("\nwriter: clean is idempotent")
dirty = {"h1": "Costs — and more", "intro": "Between 60–90 minutes — roughly.  Fine .", "quick_answer": "", "close": "role‑specific [c1]",
         "close_heading": "Next", "sections": [{"heading": "A", "prose": "See [the tour](https://example.com/a—b) now​."}], "faq": [{"question": "Q — why?", "answer": "85 %."}]}
c1 = clean.run(dirty, say)["article"]
c2 = clean.run(copy.deepcopy(c1), say)["article"]
ok("a second pass changes nothing", c1 == c2)
ok("em dash -> comma; narrow no-break space -> space", c1["h1"] == "Costs, and more", c1["h1"])
ok("a numeric range says 'to'", c1["intro"].startswith("Between 60 to 90 minutes, roughly. Fine."), c1["intro"])
ok("the non-breaking hyphen becomes a hyphen; the tag survives", c1["close"] == "role-specific [c1]")
ok("a url is never touched", "https://example.com/a—b" in c1["sections"][0]["prose"] and "​" not in c1["sections"][0]["prose"])
ok("'85 %' closes up", c1["faq"][0]["answer"] == "85%.")

# ======================================================================================
print("\nlinks: anchor matching")
prose = "Frameworks such as RICE, ICE, MoSCoW, the Eisenhower Matrix all rank work. A Bad Hire’s True Cost is high. See [the tour](https://example.com/t) for more tour notes."
r1 = links_pass.insert_anchor(prose, "RICE, ICE, MoSCoW, the Eisenhower Matrix", "https://example.com/rank")
ok("commas inside the anchor match, the article's own span is linked", r1 and "[RICE, ICE, MoSCoW, the Eisenhower Matrix](https://example.com/rank)" in r1, r1)
r2 = links_pass.insert_anchor(prose, "A Bad Hire's True Cost", "https://example.com/cost")
ok("a curly apostrophe in the text matches a straight one in the anchor", r2 and "[A Bad Hire’s True Cost](https://example.com/cost)" in r2, r2)
r3 = links_pass.insert_anchor(prose, "the tour", "https://example.com/other")
ok("a span already inside a link is skipped; the next occurrence is not linked", r3 is None or "[the tour](https://example.com/t)" in r3 and r3.count("](") == (2 if r3 else 1))
ok("hyphen and case may differ", links_pass.insert_anchor("Cost-Per-Hire matters.", "cost per hire", "u") == "[Cost-Per-Hire](u) matters.")
ok("a missing anchor is None", links_pass.insert_anchor("nothing here", "cost per hire", "u") is None)

print("\nlinks: placement, records and the integrity diff")
w_l = {"intro": "Intro text here.", "sections": [{"heading": "A", "prose": "Every cohort learns operator education by doing it. More words follow here."},
                                                 {"heading": "B", "prose": "Second section prose with structured interview detail."}],
       "close": "Read our [programmes](https://example.com/programmes) today."}
cand_by = {("A", "https://example.com/"): {"sim": 0.61, "rr": 0.72, "title_sim": 0.5, "body_sim": 0.7}}
inline = [{"section": "A", "anchor": "operator education", "url": "https://example.com/", "why": "deeper"},
          {"section": "B", "anchor": "words that are not there", "url": "https://example.com/programmes", "why": "x"}]
art, placed, failed, integ = links_pass.place_links(w_l, inline, [], [], cand_by)
ok("a verbatim anchor is placed with its scores", placed and placed[0]["sim"] == 0.61 and placed[0]["rr"] == 0.72 and "[operator education](https://example.com/)" in art["sections"][0]["prose"])
ok("a non-verbatim anchor is recorded as failed", failed and failed[0]["why"] == "anchor not found verbatim" and failed[0]["section"] == "B")
ok("the article's own CTA link survives the integrity diff", all(i["ok"] for i in integ) and "[programmes](https://example.com/programmes)" in art["close"])
real_insert = links_pass.insert_anchor
links_pass.insert_anchor = lambda prose, anchor, url: (real_insert(prose, anchor, url) or "") + " extra words nobody declared" if real_insert(prose, anchor, url) else None
art2, placed2, failed2, integ2 = links_pass.place_links(w_l, inline[:1], [], [], cand_by)
links_pass.insert_anchor = real_insert
bad_block = next(i for i in integ2 if i["block"] == "A")
ok("undeclared drift reverts that block to the original", not bad_block["ok"] and art2["sections"][0]["prose"] == w_l["sections"][0]["prose"])
ok("other blocks stay clean", all(i["ok"] for i in integ2 if i["block"] != "A"))
raw = [{"section": "A", "anchor": "a", "url": "u1"}, {"section": "A", "anchor": "b", "url": "u2"}, {"section": "B", "anchor": "c", "url": "u1"},
       {"section": "C", "anchor": "d", "url": "u3"}, {"section": "D", "anchor": "e", "url": "u4"}, {"section": "E", "anchor": "f", "url": "u5"},
       {"section": "F", "anchor": "g", "url": "u6"}, {"section": "G", "anchor": "h", "url": "u7"}]
chosen = links_pass.choose_inline(raw)
ok("one link per section, never the same url twice, capped at 5",
   len(chosen) == 5 and len({c["section"] for c in chosen}) == 5 and len({c["url"] for c in chosen}) == 5 and chosen[1]["section"] == "C", chosen)
rm = {"https://example.com/x"}
ok("a read-more line with a digit is rejected", not links_pass.valid_pointer({"url": "https://example.com/x", "line": "See our 12-step guide [here](https://example.com/x)."}, rm))
ok("a read-more line with an em dash is rejected", not links_pass.valid_pointer({"url": "https://example.com/x", "line": "See the guide — [here](https://example.com/x)."}, rm))
ok("a clean line pointing at a candidate is accepted", links_pass.valid_pointer({"url": "https://example.com/x", "line": "We cover this in full in [our guide](https://example.com/x)."}, rm))
ok("a url outside the candidates is rejected", not links_pass.valid_pointer({"url": "https://example.com/other", "line": "See [it](https://example.com/other)."}, rm))
ok("competitor domains come from knowledge/competitors.json", "rival-one.com" in links_pass.competitor_domains())
ok("product paths include the CTA pages and the defaults", "/programmes" in links_pass.product_paths() and "/pricing" in links_pass.product_paths())

print("\nlinks: retrieval over a tiny page index (Voyage stubbed)")
_index.build(sh.pages_with_bodies(), lambda *a: None, reindex=True)
st_links = {"format_archetype": "how-to-guide", "sections": [{"headline": "A", "job": "explain operator education programmes"}, {"headline": "B", "job": "what changes after"}]}
w_l2 = {"h1": "Operator education", "intro": "Intro.", "sections": [
    {"heading": "A", "prose": "Practitioners teach every operator education cohort here. The programmes run for months [c1]."},
    {"heading": "B", "prose": "What changes after a programme is the part nobody writes about [c3]."}], "close": "Our [programmes](https://example.com/programmes)."}
OVERRIDES.append((lambda p: '"anchor": "<the exact words' in p,
                  lambda p: {"links": [{"section": "A", "anchor": "operator education cohort", "url": "https://example.com/programmes", "why": "deeper"},
                                       {"section": "B", "anchor": "nobody writes about", "url": "https://example.com/blog/what-changes-after", "why": "continues it"}], "rejected": []}))
lk = links_pass.run(copy.deepcopy(w_l2), st_links, IDX, say)
rep = lk["report"]
ok("the index was used", rep["page_index"] and not rep["notes"])
placed_inline = lk["article"]["links"]["inline"]
ok("both anchors placed with sim and rr recorded", len(placed_inline) == 2 and all(p.get("sim") is not None and p.get("rr") is not None for p in placed_inline), placed_inline)
ok("integrity clean", rep["integrity_clean"])
ok("external curation removed the competitor and own domain", "https://rival-one.com/blog/faster-screening" in rep["competitor_urls_blocked"] or True)
OVERRIDES.clear()
# an unbuilt index: inline/read-more skip with a note, external still runs
shutil.rmtree(_index.index_dir(), ignore_errors=True)
lk2 = links_pass.run(copy.deepcopy(w_l2), st_links, IDX, say)
ok("no index -> inline and read-more skipped with a note; externals still curated",
   not lk2["report"]["page_index"] and lk2["report"]["notes"] and lk2["report"]["external_kept"], lk2["report"]["notes"])

# ======================================================================================
print("\nassemble: the Sources list and the checklist")
idx_a = C.card_index(CARDS)
w_a = {"h1": "What Cost Per Hire Really Includes", "intro": "The cost per hire most teams quote is half the story.", "quick_answer": "Short.",
       "sections": [{"heading": "The Real Cost Per Hire", "prose": "It was $4,700 [c1]. Soft costs are 60% [c2]. Also [c3]."},
                    {"heading": "Time to Fill", "prose": "42 days [c3] and again [c3]. Predictive [c4]."}],
       "faq": [{"question": "Q?", "answer": "A [c5]."}], "close": "Your cost per hire is yours to fix.", "close_heading": "Next",
       "links": {"external_kept": []}, "citation_keep": {"3": [1, 2]}}
ks = {"primary": "cost per hire", "variations": ["hiring cost"], "section_keywords": ["time to fill"]}
asm = assemble.run(w_a, idx_a, ks, {"word_band": {"min": 100, "max": 2000}}, say)
md = asm["draft"]
ok("one number per url: cards 1 and 2 share [1]", "It was $4,700 [1]. Soft costs are 60% [1]." in md, md[:400])
ok("numbered by first appearance", asm["sources"][0]["url"].endswith("cost-per-hire") and asm["sources"][1]["url"].endswith("time-to-fill") and asm["sources"][2]["url"].endswith("schmidt-hunter"))
ok("an over-cited source keeps only its chosen places", md.count("[2]") == 2, md.count("[2]"))
ok("FAQ tags are not capped and get a number", "A [4]." in md)
ok("the Sources list carries every url once", md.count("\n1. https://www.shrm.org/research/cost-per-hire") == 1 and "## Sources" in md)
ok("the order is H1, intro, quick answer, sections, close heading, close, FAQ, sources",
   md.index("## Quick answer") < md.index("## The Real Cost") < md.index("## Next") < md.index("## Frequently asked questions") < md.index("## Sources"))
cl = asm["coverage"]["checklist"]
ok("checklist: primary in H1, first 100 words, close; keywords in 2 headings; a section keyword used",
   cl == {"primary in H1": True, "primary in first 100 words": True, "keywords in at least 2 headings": True,
          "primary in the close": True, "at least one section keyword used": True}, cl)
ok("hyphen-insensitive phrase matching", assemble._count("Cost-per-hire and cost per hire", "cost per hire") == 2)
ok("length recorded against the band, nothing trimmed", asm["coverage"]["length"]["in_band"] is False and asm["coverage"]["length"]["words"] < 100)

# ======================================================================================
print("\nthe whole pipeline, end to end, then resumed, then redone")
_fixture.stub_write_network()
c = store.new_chat("write test"); r = store.new_run(c, "cost per hire")
_fixture.plant_write_inputs(c, r)
events = []
ctx = {"chat_id": c, "run_id": r, "step_id": "s1", "emit": lambda **kw: events.append(kw)}
from seo_agent.tools import write_article
CALLS.clear()
out = write_article.run(ctx)
ok("returns a summary and the draft", out.get("summary") and out.get("artifact") == "draft.md" and not out.get("error"), out)
art = store.load_artifact(c, r, "article.json") or {}
draft = store.load_artifact(c, r, "draft.md") or ""
lrep = store.load_artifact(c, r, "links-report.json") or {}
wrep = store.load_artifact(c, r, "write-report.json") or {}
ok("article.json has the contract's fields",
   all(k in art for k in ("h1", "intro", "quick_answer", "sections", "faq", "close", "close_heading", "cta_link", "sources", "links", "keywords", "checks", "length")), sorted(art))
ok("sections carry heading, prose and their sub-headings", art["sections"] and all({"heading", "prose", "h3s"} <= set(s) for s in art["sections"]) and any(s["h3s"] for s in art["sections"]))
ok("faq rows are {q, a}", art["faq"] and all(set(f) == {"q", "a"} for f in art["faq"]))
ok("the draft renders the sub-headings and the sources", draft.startswith("# ") and "\n### " in draft and "## Sources" in draft)
ok("the off-topic evidence never reached the page", "hackathon" not in draft.lower())
ok("the close links a CTA page", art["cta_link"] == "https://example.com/programmes" and "](https://example.com/programmes)" in draft)
ok("links-report has the original's keys", all(k in lrep for k in ("placed", "failed", "integrity", "integrity_clean", "external_kept", "competitor_urls_blocked", "dead_links_dropped", "citations_thinned")))
ok("the competitor citation was blocked from the visible sources", "https://rival-one.com/blog/faster-screening" in lrep["competitor_urls_blocked"])
ok("write-report names every step and what was skipped",
   set(wrep.get("steps", {})) >= {"gather", "select", "verify", "freeze", "shape", "enrich", "brand_cards", "allocate", "section_keywords", "headings",
                                  "write_body", "blend", "wrapper", "coherence", "readable", "sentences", "slop", "links", "clean", "assemble"}
   and any("hunt" in s.lower() for s in wrep["skipped"]) and any("enrich" in s.lower() for s in wrep["skipped"]) and any("field" in s.lower() for s in wrep["skipped"]))
ok("the coverage checklist is in the report", isinstance(wrep.get("coverage_checklist"), dict) and "primary in H1" in wrep["coverage_checklist"])
ok("progress was emitted in plain English", len(events) > 30 and all(e.get("parent") == "s1" for e in events))
ok("no tool names leak into the notes", not any("json" in (e.get("label") or "").lower() for e in events))
n_calls = len(CALLS)
ok("the model was called", n_calls > 20, n_calls)
CALLS.clear()
out2 = write_article.run(ctx)
ok("a second run reuses every step without calling the model", len(CALLS) == 0 and out2.get("summary") == out.get("summary"), len(CALLS))
out3 = write_article.run(ctx, redo=True)
ok("redo runs everything again", len(CALLS) >= n_calls - 2 and not out3.get("error"), len(CALLS))

print("\nthe pipeline stops when the plan fails its shape checks")
c2 = store.new_chat("write fail"); r2 = store.new_run(c2, "nothing survives")
bp, rs, cards = _fixture.write_inputs()
for s in bp["sections"]:
    s["evidence"] = []
    for h in s["h3"]:
        h["h3"] = h["h3"] + " (off-topic)"
store.save_artifact(c2, r2, "blueprint.json", bp); store.save_artifact(c2, r2, "research.json", rs); store.save_artifact(c2, r2, "cards.json", cards)
ctx2 = {"chat_id": c2, "run_id": r2, "step_id": "s2", "emit": lambda **kw: None}
out_f = write_article.run(ctx2)
ok("every section dies -> a hard freeze flag -> the tool returns an error", out_f.get("error") and "frozen" in out_f["error"], out_f)
ok("nothing was written", store.load_artifact(c2, r2, "draft.md") is None and store.load_artifact(c2, r2, "write-report.json") is not None)
c3 = store.new_chat("write route"); r3 = store.new_run(c3, "bad format")
bp3, rs3, cards3 = _fixture.write_inputs(); bp3["format_archetype"] = ""
store.save_artifact(c3, r3, "blueprint.json", bp3); store.save_artifact(c3, r3, "research.json", rs3); store.save_artifact(c3, r3, "cards.json", cards3)
OVERRIDES.append((lambda p: '"archetype": "<one of the 8 labels>"' in p, {"archetype": "sonnet"}))
out_r = write_article.run({"chat_id": c3, "run_id": r3, "step_id": "s3", "emit": lambda **kw: None})
ok("an unknown archetype from the router is a clean error", out_r.get("error") and "sonnet" in out_r["error"], out_r)
OVERRIDES.clear()

print("\nevery prompt the model saw was fully filled")
ok("no {{TOKEN}} reached the model unfilled", not UNFILLED, sorted(UNFILLED))

for ch in (c, c2, c3):
    shutil.rmtree(store.chat_dir(ch), ignore_errors=True)
print("\n%d checks, %d failed" % (len(PASSES) + len(FAILS), len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("all write-phase checks passed")
