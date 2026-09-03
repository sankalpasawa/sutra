"""build_blueprint.py — turn the research into the article's structure, the way 13-research-structure did.

Content-first, then keywords. Every section is built from the cards, nothing invented; every kept
card lands in exactly one section (MECE, verified in code). The steps, in the original's order:

    1b  filter    score every card against the spine through the persona's eyes; drop the off-spine
                  tail; PROTECT hard data; a scorer that fails aborts (fail closed)
    2-3 cluster   group the kept cards by meaning; MECE guaranteed in code
    4   name      one H2 (+ H3s) per cluster, in the shape the title implies
    5   attach    evidence ids, internal links (own pages), external links (sources), by card id
    7   orphan    any high-demand keyword no section covers
    8   faq+order FAQ = the People Also Ask questions; the order accepted only as a valid permutation
    8b  keyword set  primary + variations + secondaries + in-body, pure code

No paid calls here. The persona comes from the research and is never re-picked.
"""
from .. import store
from ..research import _common as _c
from ..research import attach, cluster, faq_order, keyword_set, name_clusters, orphan, score_cards
from . import _shared as sh

# 13-research-structure/scripts/render.py, unchanged
WRITE_GUIDANCE = {
    "note": "This is a RESEARCH menu, not the final article. The writer selects sections and does the wording.",
    "seo_spec (from seo-aeo-geo-guidelines.md 3.2)": [
        "H1 = the asset title, primary keyword near the start, <=60 chars, benefit-focused.",
        "4-7 H2s in the final article (select from this menu); only 2-3 carry a keyword variation.",
        ">=50% of H2s phrased as questions; 40-60 word answer-first under question H2s.",
        "Primary keyword in: H1, first 100 words, 2-3 H2s, conclusion.",
        "Intro (answer-first), TL;DR block, FAQ (5), forward-looking close are written at the write phase.",
    ],
}

_GENERIC_PERSONA = {"name": "", "lens": "a practitioner making a real decision about what the brand offers "
                                        "(choose / evaluate / use it), not an academic", "why": ""}


def run(ctx, redo=False, **_ignored):
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "build_blueprint")
    research = store.load_artifact(chat_id, run_id, "research.json")
    if not research or not (research.get("keywords") or {}).get("primary"):
        return {"summary": "No research to build from.",
                "error": "research.json is missing (or has no primary keyword) for this run. Run run_research first."}
    cards = store.load_artifact(chat_id, run_id, "cards.json") or []
    if not cards:
        return {"summary": "No evidence cards to build from.",
                "error": "cards.json is empty for this run. Run run_research again; the evidence step found nothing."}
    topic = research.get("topic") or ""
    angle = research.get("angle") or ""
    company = sh.company()
    brand_oneliner = company.get("brand_oneliner") or company.get("brand") or "this company"
    persona = research.get("persona") or _GENERIC_PERSONA
    spine_ctx = {"spine": research.get("spine"), **(research.get("world") or {})}
    say("Read the research", "%s, %s" % (sh.plural(len(cards), "card"), "reader: " + (persona.get("name") or "a practitioner")))

    # ---- 1b. the spine-relevance filter (fail closed) ----------------------------------------------
    def _score():
        kept, report = score_cards.run(cards, topic, angle, persona, spine_ctx, brand_oneliner)
        return {"kept_ids": [c["id"] for c in kept], "report": report,
                "scores": {str(c["id"]): {"relevance": c.get("relevance"), "protected": c.get("protected")} for c in cards}}
    try:
        scored, reused = _c.cached(ctx, "scored-cards", redo, _score)
    except Exception as e:  # noqa: BLE001 — a crashed scorer must not default its cards to keep
        return {"summary": "The card filter failed, so no blueprint was built.",
                "error": "The relevance scorer failed (%s). Nothing was dropped or kept by guesswork; retry." % str(e)[:200]}
    for c in cards:
        s = scored["scores"].get(str(c["id"])) or {}
        c["relevance"], c["protected"] = s.get("relevance"), s.get("protected")
    store.save_artifact(chat_id, run_id, "cards.json", cards)
    kept_ids = set(scored["kept_ids"])
    kept = [c for c in cards if c["id"] in kept_ids]
    rep = scored["report"]
    say("Kept %s of %s" % (sh.plural(rep["kept_count"], "card"), rep["total_cards"]) + (" (kept from last time)" if reused else ""),
        "%s dropped as off the spine; hard numbers were protected" % rep["dropped_count"]
        + ("; that is a lot, worth a look" if rep.get("FLAG") else ""))
    if not kept:
        return {"summary": "Every card was judged off the spine.",
                "error": "The filter dropped all %d cards. Check the spine and the world statement, then rerun." % len(cards)}

    # ---- 2-3. cluster (MECE in code) ---------------------------------------------------------------
    clusters, _ = _c.cached(ctx, "clusters", redo, lambda: {"clusters": cluster.run(
        kept, topic, angle, persona, spine_ctx, brand_oneliner)})
    clusters = clusters["clusters"]
    say("Grouped them into %s" % sh.plural(len(clusters), "section"), "Every kept card sits in exactly one")

    # ---- 4. name + split ----------------------------------------------------------------------------
    named, _ = _c.cached(ctx, "sections", redo, lambda: {"sections": name_clusters.run(
        clusters, kept, topic, angle, spine_ctx)})
    named = named["sections"]
    say("Named the sections", "; ".join(s["h2"][:40] for s in named[:5]))

    # ---- 5. attach ------------------------------------------------------------------------------------
    sections = attach.run(named, kept)

    # ---- 7. orphan check ------------------------------------------------------------------------------
    metrics = (_c.load_work(ctx, "metrics") or {}).get("rows") or []
    orphans, _ = _c.cached(ctx, "orphans", redo, lambda: {"orphans": orphan.run(sections, metrics)})
    orphans = orphans["orphans"]
    if orphans:
        say("%s no section covers" % sh.plural(len(orphans), "searched keyword"),
            ", ".join(o["keyword"] for o in orphans[:4]))

    # ---- 8. FAQ + order -------------------------------------------------------------------------------
    paa = (research.get("serp") or {}).get("paa") or []
    faq = faq_order.faq_from_paa(paa)
    order, _ = _c.cached(ctx, "order", redo, lambda: {
        "h2s": [s["h2"] for s in faq_order.order_sections(sections)]})
    by_h2 = {s["h2"]: s for s in sections}
    if sorted(order["h2s"]) == sorted(by_h2):
        sections = [by_h2[h] for h in order["h2s"]]
    say("Ordered the sections, %s" % sh.plural(len(faq), "FAQ question"), "FAQ comes straight from People Also Ask")

    # ---- 8b. keyword set --------------------------------------------------------------------------------
    kset = keyword_set.run(research.get("keywords") or {})

    # ---- render ------------------------------------------------------------------------------------------
    for i, s in enumerate(sections, 1):
        s["id"] = "s%d" % i
        s["heading"] = s["h2"]           # older readers of this file look for heading/covers
        s["covers"] = s.get("job") or ""
    blueprint = {
        "h1": topic,
        "keyword_set": kset,
        "sections": sections,
        "faq": faq,
        "orphan_keywords": orphans,
        "persona": persona,
        "format_archetype": (research.get("winners") or {}).get("format") or "",
        "word_band": (research.get("build_spec") or {}).get("word_band"),
        "angle_filter": {"kept": rep["kept_count"], "dropped": rep["dropped_count"],
                         "dropped_pct": rep["dropped_pct_of_cards"], "flag": bool(rep.get("FLAG"))},
        "write_guidance": WRITE_GUIDANCE,
        # aliases for older readers of this file
        "title": topic, "primary_keyword": kset["primary"], "secondary_keywords": kset["secondaries"],
        "generated_at": store.now(),
    }
    store.save_artifact(chat_id, run_id, "blueprint.json", blueprint)
    linked = sum(len(s["internal_links"]) for s in sections)
    say("Blueprint ready", "%s, %s, %s" % (sh.plural(len(sections), "section"), sh.plural(linked, "internal link"),
                                          sh.plural(len(faq), "FAQ question")))
    return {"summary": "%s from %s cards (%s dropped as off the spine), %s, %s" % (
        sh.plural(len(sections), "section"), rep["kept_count"], rep["dropped_count"],
        sh.plural(linked, "internal link"), sh.plural(len(faq), "FAQ question")),
        "artifact": "blueprint.json"}
