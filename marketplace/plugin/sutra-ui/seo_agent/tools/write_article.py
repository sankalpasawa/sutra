"""write_article.py — the write phase, one tool: planner -> architect -> writer, resumable.

Reads:  blueprint.json (the plan the user approved), research.json (the brief), cards.json (the facts).
Writes: article.json, draft.md, links-report.json, write-report.json, plus one work-<step>.json per step
        so a run that stops resumes where it left off (redo=True reruns everything).

This file is PURE SEQUENCING. It calls each step's run() in order and passes outputs along; every
judgment lives in write/<step>.py, every prompt in prompts/write/. The three stations:

  PLANNER    gather -> route -> select -> verify_sources -> freeze   (a HARD freeze flag stops the run)
  ARCHITECT  shape -> enrich -> brand_cards -> allocate_words -> section_keywords -> headings
  WRITER     write_body -> blend -> wrapper -> coherence -> readable -> sentence_pass -> slop_pass
             -> links (editing/links_pass.py) -> clean -> assemble

Three things the original bought from the web are deliberately not run here, and the report says so
each time: the replacement-source hunt (verify_sources), the enrichment search (enrich), and the
voices-from-the-field station. Section-keyword lookups run only when DataForSEO is connected and funded.
"""
import re

from .. import store
from ..editing import links_pass
from ..write import (_common as C, allocate_words, assemble, blend, brand_cards, clean, coherence, enrich,
                     fmt_router, freeze, gather, headings, plan_select, readable, section_keywords,
                     sentence_pass, shape, slop_pass, verify_sources, wrapper, write_body)
from . import _shared as sh

STEPS = ["gather", "route", "select", "verify", "freeze", "shape", "enrich", "brand_cards", "allocate",
         "section_keywords", "headings", "write_body", "blend", "wrapper", "coherence", "readable",
         "sentences", "slop", "links", "clean", "assemble"]

SKIPPED = [
    "Replacement-source hunt (planner): a fact whose source failed keeps its claim and loses the url; "
    "finding a new page needs a DataForSEO web search this agent does not run.",
    "Enrichment (architect): extra research the structure asked for needs a DataForSEO web search; "
    "the requests are recorded and the writer is told those sections are thinner than designed.",
    "Voices from the field: the Reddit/Blind/LinkedIn station is not ported; the body writer's "
    "FILE 2 block is empty.",
]


def _apply_card_fixes(idx, fixes):
    for cid, fx in (fixes or {}).items():
        c = idx.get(C.nid(cid))
        if c is None:
            continue
        c["source_urls"] = list(fx.get("source_urls") or [])
        if fx.get("needs_source"):
            c["needs_source"] = True


def _merge_brand_cards(idx, used):
    for cid, card in (used or {}).items():
        c = dict(card)
        c["card_id"] = C.nid(cid)
        idx[C.nid(cid)] = c


def _article_json(final, asm, st, reports):
    secs = []
    for s in final["sections"]:
        secs.append({"heading": s["heading"], "prose": s["prose"],
                     "h3s": re.findall(r"^###\s+(.+?)\s*$", s.get("prose") or "", re.M)})
    cov = dict(asm["coverage"])
    length = cov.pop("length", {})
    return {"h1": final.get("h1"), "intro": final.get("intro"), "quick_answer": final.get("quick_answer"),
            "sections": secs, "faq": [{"q": f.get("question"), "a": f.get("answer")} for f in final.get("faq") or []],
            "close": final.get("close"), "close_heading": final.get("close_heading"), "cta_link": final.get("cta_link"),
            "sources": asm["sources"],
            "links": {"inline": (final.get("links") or {}).get("inline") or [],
                      "read_more": (final.get("links") or {}).get("read_more") or [],
                      "external_kept": (final.get("links") or {}).get("external_kept") or []},
            "keywords": st.get("keywords") or {},
            "checks": {"coverage": cov, "readable": reports.get("readable", {}).get("checks", []),
                       "blend": {"applied": reports.get("blend", {}).get("applied"),
                                 "guard_failures": reports.get("blend", {}).get("guard_failures", [])},
                       "coherence": {"applied": reports.get("coherence", {}).get("applied"),
                                     "guard_failures": reports.get("coherence", {}).get("guard_failures", [])},
                       "links_integrity_clean": reports.get("links", {}).get("integrity_clean")},
            "length": length}


def run(ctx, redo=False):
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "write_article")

    blueprint = store.load_artifact(chat_id, run_id, "blueprint.json")
    if not blueprint or not isinstance(blueprint, dict):
        return {"summary": "No blueprint to write from.",
                "error": "blueprint.json is missing for this run. Run build_blueprint first."}
    if not blueprint.get("sections"):
        return {"summary": "The blueprint has no sections.", "error": "blueprint.json has an empty sections list. Rebuild it."}
    research = store.load_artifact(chat_id, run_id, "research.json") or {}
    cards = store.load_artifact(chat_id, run_id, "cards.json")
    if not cards:
        return {"summary": "No evidence cards to write from.",
                "error": "cards.json is missing for this run. Run run_research first."}
    idx = C.card_index(cards)
    ctx_a = C.context(blueprint, research)
    reports, skipped = {}, list(SKIPPED)
    # Say it at the top, not in a footnote. Found live 2026-09-04: the draft was written from
    # demo research and read as a finished article; the flag sat in research.json and appeared
    # nowhere in the report, the draft, or the summary.
    demo = bool(research.get("demo_data"))
    if demo:
        say("Writing from demo research",
            "The research for this article carries made-up keyword numbers and made-up ranking "
            "pages, so nothing it cites is a real source. The writing is real; the evidence is not.")
        skipped.append("The research was demo data, so every number that came from a source page "
                       "is fabricated. Do not publish this without a real research run.")

    def step(name, label, fn):
        """Run one step, or reuse its saved output. Every output lands on disk before the next step reads it."""
        cached = None if redo else C.load_work(ctx, name)
        if cached is not None:
            say("Reusing: %s" % label, "already done in an earlier run")
            return cached
        out = fn()
        C.save_work(ctx, name, out)
        return out

    # ---------------- PLANNER ----------------
    inputs = step("gather", "Gathering the material", lambda: gather.run(blueprint, research, cards, say))
    try:
        routed = step("route", "Deciding the article's format", lambda: fmt_router.run(inputs, research, say))
    except ValueError as e:
        return {"summary": "Could not decide the article's format.", "error": str(e)}
    inputs["group_a"]["format_archetype"] = routed["archetype"]
    reports["gather"] = {"sections": len(inputs["group_b"]["sections_menu"]),
                         "table_stakes": inputs["group_a"]["table_stakes"], "word_band": inputs["group_a"]["word_band"],
                         "paa": len(inputs["group_b"]["paa_pool"]), "related": len(inputs["group_b"]["related_searches"])}
    reports["route"] = routed

    sel = step("select", "Judging which sections earn their place", lambda: plan_select.run(inputs, ctx_a, say))
    reports["select"] = sel["audit"]["stats"]
    reports["select"]["dead_h2s"] = sel["audit"]["drops"]["dead_h2s"]

    ver = step("verify", "Checking the sources behind every number",
               lambda: verify_sources.run(C.deep(sel["plan"]), idx, say))
    _apply_card_fixes(idx, ver.get("card_fixes"))
    pol = ver["police"]
    reports["verify"] = {k: (len(v) if isinstance(v, list) else v) for k, v in pol.items() if k != "coverage"}
    reports["verify"]["coverage"] = pol.get("coverage")
    skipped.append("Source hunt: " + pol.get("hunt", ""))

    fr = step("freeze", "Freezing the plan", lambda: freeze.run(C.deep(ver["plan"]), pol))
    reports["freeze"] = {"hard": fr["hard"], "soft": fr["soft"]}
    if fr["hard"]:
        say("The plan cannot be frozen", "; ".join(fr["hard"])[:200])
        store.save_artifact(chat_id, run_id, "write-report.json",
                            {"generated_at": store.now(), "stopped_at": "freeze", "steps": reports, "skipped": skipped})
        return {"summary": "The plan failed its shape checks, so nothing was written.",
                "error": "The plan could not be frozen: " + "; ".join(fr["hard"]) + ". Fix the blueprint and run again.",
                "artifact": "write-report.json"}
    plan = fr["plan"]
    if fr["soft"]:
        say("Plan frozen with notes", "; ".join(fr["soft"])[:200])
    else:
        say("Plan frozen", "%d sections" % len(plan["sections"]))

    # ---------------- ARCHITECT ----------------
    try:
        shp = step("shape", "Designing the article's structure", lambda: shape.run(plan, idx, ctx_a, say))
    except ValueError as e:
        return {"summary": "The structure step returned nothing usable.", "error": str(e)}
    st = shp["structure"]
    reports["shape"] = {"sections": len(st["sections"]), "sub_headings": sum(len(s["h3s"]) for s in st["sections"]),
                        "boxes_unused": len(st["unused_boxes"]), "shared_box_warnings": st["shared_box_warnings"],
                        "coverage": st.get("coverage"), "reopened_holes": st.get("reopened_holes"),
                        "coverage_note": st.get("coverage_note"), "bad_research_destinations": st.get("bad_research_destinations")}

    en = step("enrich", "Extra research", lambda: enrich.run(C.deep(st), say))
    st = en["structure"]
    reports["enrich"] = st.get("enrichment", {})
    reports["enrich"]["empty_subheadings_removed"] = st.get("empty_subheadings_removed", [])

    bc = step("brand_cards", "Placing the company's own material", lambda: brand_cards.run(C.deep(st), idx, ctx_a, say))
    st = bc["structure"]
    _merge_brand_cards(idx, bc.get("used"))
    reports["brand_cards"] = {"placed": len(bc["placement"]["placements"]), "rejected": bc["placement"]["rejected"],
                              "notes": bc["placement"].get("notes")}

    al = step("allocate", "Setting a length for every section", lambda: allocate_words.run(C.deep(st), plan, idx, ctx_a, say))
    st = al["structure"]
    reports["allocate"] = st.get("word_budget")

    skw = step("section_keywords", "Deciding which sections deserve a search keyword",
               lambda: section_keywords.run(st, inputs, ctx_a, idx, say))
    reports["section_keywords"] = {k: v for k, v in skw.items() if k != "sections"}
    if skw.get("hunts_skipped"):
        skipped.append("Section keyword lookups: " + skw["hunts_skipped"])

    hd = step("headings", "Writing the headings", lambda: headings.run(C.deep(st), inputs, ctx_a, idx, skw, plan.get("h1"), say))
    st = hd["structure"]
    hm = hd["heading_map"]
    reports["headings"] = {"h1": st.get("h1"), "rewritten": sum(1 for r in hm["headings"] if r.get("changed")),
                           "cross_section_pass": hm["cross_section_pass"], "over_length": hm["over_length"],
                           "keywords": st.get("keywords")}

    # ---------------- WRITER ----------------
    body = step("write_body", "Writing the body", lambda: write_body.run(st, idx, ctx_a, say))
    reports["write_body"] = {"sections": [{"heading": s["headline"], "words": s["words"], "target": s["word_target"],
                                           "sourced_claims": len(s["provenance"]), "stray_tags_dropped": s["bad_tags_dropped"]}
                                          for s in body["sections"]],
                             "contract_misses": body.get("contract_misses", []), "contract_leaked": body.get("contract_leaked", [])}

    bl = step("blend", "Editing the sections into one piece", lambda: blend.run(body, st, inputs, ctx_a, say))
    reports["blend"] = {k: bl[k] for k in ("edits", "guard_failures", "warnings", "applied", "tag_audit", "keywords_measured",
                                           "counter_before", "counter_after", "length_before", "length_after")}

    wr = step("wrapper", "Writing the intro, quick answer, FAQ and close",
              lambda: wrapper.run(C.deep(bl), plan, st, inputs, ctx_a, say))
    reports["wrapper"] = {"ok": wr["ok"], "cta_link": wr["cta_link"], "cta_problems": wr["cta_problems"],
                          "faq": [{"question": f["question"], "words": f["words"], "over_target": f["over_target"],
                                   "outside_numbers": f["outside_numbers"]} for f in wr["faq"]],
                          "dropped_questions": wr["dropped_questions"], "touch_ups_applied": wr["touch_ups_applied"],
                          "invented_tags_stripped": wr["invented_tags_stripped"]}

    co = step("coherence", "Reading the article whole", lambda: coherence.run(C.deep(wr), ctx_a, plan, say))
    reports["coherence"] = {k: v for k, v in co["report"].items() if k not in ("inventory", "diff")}

    rd = step("readable", "Rewriting it to be read", lambda: readable.run(C.deep(co["article"]), plan, st, say))
    reports["readable"] = rd["report"]

    sp = step("sentences", "Re-shaping the sentences", lambda: sentence_pass.run(C.deep(rd["article"]), plan, say))
    reports["sentences"] = {k: sp["report"][k] for k in ("before", "after", "drift", "drift_ok", "rhythm_ok")}
    reports["sentences"]["rejected"] = [b["block"] for b in sp["report"]["blocks"] if b["verdict"].startswith("REJECTED")]

    sl = step("slop", "Removing the tells of machine writing", lambda: slop_pass.run(C.deep(sp["article"]), say))
    reports["slop"] = {"before": sl["report"]["before"], "after": sl["report"]["after"],
                       "rejected": [b["block"] for b in sl["report"]["blocks"] if b["verdict"].startswith("REJECTED")],
                       "changes": sum(len(b["changes"]) for b in sl["report"]["blocks"])}

    lk = step("links", "Laying in the links", lambda: links_pass.run(C.deep(sl["article"]), st, idx, say))
    store.save_artifact(chat_id, run_id, "links-report.json", lk["report"])
    reports["links"] = {k: lk["report"][k] for k in ("integrity_clean", "notes", "dead_links_dropped", "competitor_urls_blocked",
                                                     "citations_thinned", "wanted_inline", "page_index")}
    reports["links"]["placed"] = len(lk["report"]["placed"])
    reports["links"]["failed"] = lk["report"]["failed"]
    reports["links"]["external_kept"] = len(lk["report"]["external_kept"])
    for n in lk["report"].get("notes") or []:
        skipped.append("Links: " + n)

    cl = step("clean", "Scrubbing stray characters", lambda: clean.run(C.deep(lk["article"]), say))
    reports["clean"] = cl["report"]

    asm = step("assemble", "Assembling the article",
               lambda: assemble.run(cl["article"], idx, st.get("keywords") or {}, plan, say))
    final = cl["article"]
    reports["assemble"] = {"checklist": asm["coverage"]["checklist"], "length": asm["coverage"]["length"],
                           "sources": len(asm["sources"]), "bare_sections": asm.get("bare_sections")}

    article = _article_json(final, asm, st, reports)
    store.save_artifact(chat_id, run_id, "article.json", article)
    store.save_artifact(chat_id, run_id, "draft.md", asm["draft"])
    store.save_artifact(chat_id, run_id, "write-report.json",
                        {"generated_at": store.now(), "archetype": st.get("format_archetype"), "steps": reports,
                         "skipped": skipped, "demo_research": demo,
                         "enrichment_requested": (reports.get("enrich") or {}).get("markers") or 0,
                         "claims_checked": (reports.get("verify") or {}).get("actually_judged"),
                         "claims_to_check": (reports.get("verify") or {}).get("claims_to_check"),
                         "coverage_checklist": asm["coverage"]["checklist"],
                         "length": asm["coverage"]["length"]})
    n = asm["coverage"]["length"]["words"]
    fails = [k for k, v in asm["coverage"]["checklist"].items() if not v]
    summary = "%s words across %s, %s, %s" % (format(n, ","), sh.plural(len(final["sections"]), "section"),
                                              sh.plural(len(final.get("faq") or []), "FAQ answer"),
                                              sh.plural(len(asm["sources"]), "source"))
    if fails:
        summary += ". Keyword checklist missed: " + "; ".join(fails)
    if demo:
        summary = "DEMO RESEARCH, so no cited number is real. " + summary
    ver = reports.get("verify") or {}
    if ver.get("claims_to_check") and not ver.get("actually_judged"):
        # 0 of 7 judged used to read exactly like 7 of 7. Say it in the summary.
        summary += ". None of the %d claims that needed a source could be checked" % ver["claims_to_check"]
    mk = (reports.get("enrich") or {}).get("markers") or 0
    if mk:
        summary += ". %s asked for extra research that did not run" % sh.plural(mk, "section")
    out = {"summary": summary, "artifact": "draft.md"}
    if len(skipped) > len(SKIPPED):
        out["note"] = " ".join(skipped[len(SKIPPED):])
    return out
