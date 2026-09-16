"""write_article.py — the write phase, one tool: planner -> architect -> writer, resumable.

Reads:  blueprint.json (the plan the user approved), research.json (the brief), cards.json (the facts).
Writes: article.json, draft.md, links-report.json, write-report.json, plus one work-<step>.json per step
        so a run that stops resumes where it left off (redo=True reruns everything).

This file is PURE SEQUENCING. It calls each step's run() in order and passes outputs along; every
judgment lives in write/<step>.py, every prompt in prompts/write/. The four stations:

  PLANNER    gather -> route -> select -> freeze   (a HARD freeze flag stops the run)
  ARCHITECT  shape -> enrich -> brand_cards -> allocate_words -> section_keywords -> headings
  FIELD      what practitioners say in public, read and filtered into one briefing
  WRITER     write_body -> source_check -> blend -> wrapper -> coherence -> readable -> sentence_pass
             -> slop_pass -> links (editing/links_pass.py) -> clean -> assemble

THE SOURCE CHECK MOVED (2026-09-16). The planner used to run a verify step over every card in the
plan, 600 to 850 of them, about 1,000 model calls and 2.5 to 4 hours a run, and its "not supported"
verdicts were right about 30% of the time. It now runs AFTER the body is written, over only the 60
to 90 claims the article actually carries (write/source_check.py). A run paused before the change
still has work-verify.json and work-freeze.json on disk: the freeze cache is reused as it is, the
verify cache is simply never read, and the run carries on into shape and then the new check.

FIELD SITS BETWEEN THE ARCHITECT AND THE WRITER, which is where the original puts it: run_article.py
sequences planner -> architect -> field -> writer, and the station reads the architect's finished
structure. It is also the one station whose failure does not cost the article, so it is reported and
stepped over, never raised.

Every station now does its own job rather than declaring it skipped. What each one could NOT do is
still recorded, in `skipped`, one line per station, in the words of what actually happened.
Section-keyword lookups run only when DataForSEO is connected and funded.
"""
import re

from .. import store
from ..editing import links_pass
from ..write import (_common as C, allocate_words, assemble, blend, brand_cards, clean, coherence, enrich,
                     field, freeze, gather, headings, plan_select, readable, section_keywords,
                     sentence_pass, shape, slop_pass, source_check, wrapper, write_body)
from . import _shared as sh

STEPS = ["gather", "select", "freeze", "shape", "enrich", "brand_cards", "allocate",
         "section_keywords", "headings", "field", "write_body", "source_check", "blend", "wrapper", "coherence",
         "readable", "sentences", "slop", "links", "clean", "assemble"]


def _merge_brand_cards(idx, used):
    for cid, card in (used or {}).items():
        c = dict(card)
        c["card_id"] = C.nid(cid)
        idx[C.nid(cid)] = c


def _merge_enriched(idx, enriched):
    """The cards enrich bought, added to the index the writer reads. Ids start at 9001, so they
    cannot collide with the research cards or with the brand cards (8001+)."""
    for cid, card in (enriched or {}).items():
        c = dict(card)
        c["card_id"] = C.nid(cid)
        c["id"] = C.nid(cid)
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
    # `skipped` is the run's honest record: one line per station saying what it did and what it could
    # not do. `surfaced` is the shorter list that also reaches the caller's note, for the things a
    # person has to act on. Everything in `surfaced` is also in `skipped`.
    reports, skipped, surfaced = {}, [], []
    # Say it at the top, not in a footnote. Found live 2026-09-04: the draft was written from
    # demo research and read as a finished article; the flag sat in research.json and appeared
    # nowhere in the report, the draft, or the summary.
    demo = bool(research.get("demo_data"))
    if demo:
        say("Writing from demo research",
            "The research for this article carries made-up keyword numbers and made-up ranking "
            "pages, so nothing it cites is a real source. The writing is real; the evidence is not.")
        note = ("The research was demo data, so every number that came from a source page "
                "is fabricated. Do not publish this without a real research run.")
        skipped.append(note)
        surfaced.append(note)

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
    # The format and the length are not decided here. gather.run() reads them off decisions.json
    # (through write/_common.decisions(ctx)); an unknown archetype on an old or resumed run with no
    # decisions file raises ValueError out of the fallback builder, caught the same way the old
    # "route" step's failure used to be.
    try:
        inputs = step("gather", "Gathering the material", lambda: gather.run(ctx, blueprint, research, cards, say))
    except ValueError as e:
        return {"summary": "Could not decide the article's format.", "error": str(e)}
    # The search picture, saved the moment the lists are clean. It does NOT stop the run: the owner
    # reads it while the article is being written, or afterwards, or never (2026-09-09). Re-saved on a
    # resume too, which is free: gather carries the markdown in its own work file.
    if inputs.get("search_picture"):
        store.save_artifact(chat_id, run_id, "search-picture.md", inputs["search_picture"])
        say("The search picture is ready to read",
            "What the search results said, and which questions were kept for this article")
    reports["gather"] = {"sections": len(inputs["group_b"]["sections_menu"]),
                         "table_stakes": inputs["group_a"]["table_stakes"], "word_band": inputs["group_a"]["word_band"],
                         "paa": len(inputs["group_b"]["paa_pool"]), "related": len(inputs["group_b"]["related_searches"]),
                         "format_archetype": inputs["group_a"]["format_archetype"]}

    sel = step("select", "Judging which sections earn their place", lambda: plan_select.run(inputs, ctx_a, say))
    reports["select"] = sel["audit"]["stats"]
    reports["select"]["dead_h2s"] = sel["audit"]["drops"]["dead_h2s"]

    # A work-freeze.json written before 2026-09-16 (verify's plan, same shape) is reused as it is.
    fr = step("freeze", "Freezing the plan", lambda: freeze.run(C.deep(sel["plan"])))
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

    en = step("enrich", "Extra research", lambda: enrich.run(C.deep(st), say, ctx_a))
    st = en["structure"]
    # THE NEW CARDS JOIN THE INDEX. Enrich mints ids from 9001 and attaches them to the structure;
    # without this the writer would be handed ids it cannot look up and the facts would vanish.
    _merge_enriched(idx, en.get("enriched_cards"))
    reports["enrich"] = st.get("enrichment", {})
    reports["enrich"]["empty_subheadings_removed"] = st.get("empty_subheadings_removed", [])
    skipped.append("Enrichment: " + (en.get("note") or ""))

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

    # ---------------- FIELD ----------------
    # Between the architect and the writer, where the original puts it, and never allowed to stop the
    # run: losing some forum quotes must not cost a finished article.
    def _field():
        try:
            return field.run(st, ctx_a, say)
        except Exception as e:  # noqa: BLE001 — a field failure is reported, never fatal
            return {"markdown": "", "block": "",
                    "report": {"note": "the station failed (%s: %s), so the article was written "
                                       "without it" % (type(e).__name__, str(e)[:120]), "findings": 0}}

    fld = step("field", "Reading what practitioners say in public", _field)
    if fld.get("markdown"):
        store.save_artifact(chat_id, run_id, "voices-from-the-field.md", fld["markdown"])
    # The block the body writer is shown. Empty when there was nothing worth showing it.
    st["field_block"] = fld.get("block") or ""
    reports["field"] = fld.get("report") or {}
    skipped.append("Voices from the field: " + (reports["field"].get("note") or ""))

    # ---------------- WRITER ----------------
    body = step("write_body", "Writing the body", lambda: write_body.run(st, idx, ctx_a, say))
    reports["write_body"] = {"sections": [{"heading": s["headline"], "words": s["words"], "target": s["word_target"],
                                           "sourced_claims": len(s["provenance"]), "stray_tags_dropped": s["bad_tags_dropped"]}
                                          for s in body["sections"]],
                             "contract_misses": body.get("contract_misses", []), "contract_leaked": body.get("contract_leaked", [])}

    # THE SOURCE CHECK. Only the claims the body carries, one page and one verdict each, then a capped
    # hunt and a per-section fix of what still fails. ONE line reaches the chat; the detail is the
    # artifact. The step's output is the body with the fixes applied, so `body` is rebound to it and
    # every later pass edits the checked text.
    sc = step("source_check", "Checking the sources behind the facts the body uses",
              lambda: source_check.run(body, idx, say))
    body = sc["body"]
    store.save_artifact(chat_id, run_id, "source-check.json", dict(sc["report"], generated_at=store.now()))
    store.save_artifact(chat_id, run_id, "source-check.md", sc["markdown"])
    reports["source_check"] = sc["report"]["counts"]
    skipped.append("Source check: " + sc["report"]["summary"])

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
                         "enrichment_resolved": (reports.get("enrich") or {}).get("resolved") or 0,
                         "enrichment_cards": (reports.get("enrich") or {}).get("new_cards") or 0,
                         "field_findings": (reports.get("field") or {}).get("findings") or 0,
                         "sources_replaced": (reports.get("source_check") or {}).get("replaced") or 0,
                         "claims_checked": (reports.get("source_check") or {}).get("checked"),
                         "claims_unreadable": (reports.get("source_check") or {}).get("unreadable"),
                         "claims_fixed": sum((reports.get("source_check") or {}).get(k) or 0
                                             for k in ("corrected", "softened", "removed")),
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
    scn = reports.get("source_check") or {}
    if scn.get("checked") and scn.get("unreadable") == scn.get("checked"):
        # 0 of 7 read used to look exactly like 7 of 7. Say it in the summary.
        summary += ". None of the %d facts' source pages could be read, so none was checked" % scn["checked"]
    fixed = sum(scn.get(k) or 0 for k in ("corrected", "softened", "removed"))
    if fixed:
        # A figure that left the article is something the reader of the summary has to know.
        summary += ". The source check changed %s (%d corrected, %d softened, %d removed)" % (
            sh.plural(fixed, "sentence"), scn.get("corrected") or 0, scn.get("softened") or 0, scn.get("removed") or 0)
    enr = reports.get("enrich") or {}
    if enr.get("new_cards"):
        summary += ". Extra research added %s to %s that asked for it" % (
            sh.plural(enr["new_cards"], "fact"), sh.plural(enr.get("resolved") or 0, "section"))
    if enr.get("failed"):
        # A section that asked for research and got none is thinner than it was designed to be. It used
        # to be the only enrichment line here, because nothing ever ran. Now it is the exception.
        summary += ". %s asked for extra research and found none" % sh.plural(enr["failed"], "section")
    fnd = (reports.get("field") or {}).get("findings") or 0
    if fnd:
        summary += ". %s from what practitioners say in public" % sh.plural(fnd, "finding")
    out = {"summary": summary, "artifact": "draft.md"}
    if surfaced:
        out["note"] = " ".join(surfaced)
    return out
