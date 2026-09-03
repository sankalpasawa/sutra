"""build_blueprint.py — turn approved research into a structure a writer can follow.

The two things that go wrong here, both handled in code rather than asked of the model.
Invented internal links: the model is given the real URL list and every link it returns is
checked against that list, with anything else dropped. And a word budget that does not add
up: the section targets are rescaled to hit the requested total, so "1500 words" means 1500.
"""
from .. import store
from .. import llm
from . import _shared as sh

LINK_CANDIDATES = 40     # pages the model may choose links from
MIN_SECTIONS = 4
MAX_SECTIONS = 9
BUDGET_TOLERANCE = 0.15  # rescale the section words if the total is further off than this


def _sections_hint(target_words):
    """Roughly 250 words a section, kept inside sane bounds."""
    n = max(MIN_SECTIONS, min(MAX_SECTIONS, round(target_words / 250.0)))
    return "%d to %d" % (max(MIN_SECTIONS, n - 1), min(MAX_SECTIONS, n + 1))


def _clean_links(raw, valid_by_norm):
    """Keep only links that point at a page the site index actually has."""
    kept, dropped = [], []
    for link in (raw or []):
        if not isinstance(link, dict):
            continue
        url = (link.get("url") or "").strip()
        real = valid_by_norm.get(sh.normalise_url(url))
        if real:
            kept.append({"url": real, "anchor": link.get("anchor") or ""})
        elif url:
            dropped.append(url)
    return kept, dropped


def _rebalance(sections, target_words):
    total = sum(s["words"] for s in sections)
    if not total or abs(total - target_words) <= target_words * BUDGET_TOLERANCE:
        return total, False
    scale = float(target_words) / total
    for s in sections:
        s["words"] = max(80, int(round(s["words"] * scale / 10.0)) * 10)
    return sum(s["words"] for s in sections), True


def run(ctx, target_words=1500):
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "build_blueprint")
    try:
        target_words = int(target_words or 1500)
    except (TypeError, ValueError):
        target_words = 1500

    research = store.load_artifact(chat_id, run_id, "research.json")
    if not research:
        return {"summary": "No research to build from.",
                "error": "research.json is missing for this run. Run run_research first."}

    primary = (research.get("primary_keyword") or {}).get("keyword", "")
    topic = research.get("topic", "") or primary
    say("Read the research", "Primary keyword: %s" % (primary or "none"))

    index = sh.site_index()
    candidates = sh.link_candidates(index, topic, LINK_CANDIDATES)
    valid_by_norm = {sh.normalise_url(p["url"]): p["url"] for p in candidates}
    say("Found " + sh.plural(len(candidates), "page") + " worth linking to",
        "From your site index" if candidates
        else "No site index, so this article gets no internal links")

    prompt = sh.fill(
        sh.load_prompt("blueprint"),
        topic=topic, primary=primary or "(none chosen)",
        secondary=", ".join(research.get("secondary_keywords") or []) or "(none)",
        paa=sh.bullets(research.get("people_also_ask"), empty="(none)"),
        covered=sh.bullets(research.get("what_they_all_cover"), empty="(not analysed)"),
        gap=research.get("the_gap") or "(no gap analysis, so use your judgement)",
        angle=research.get("recommended_angle") or "(none given, so choose one and say why)",
        voice=sh.voice_block(),
        link_candidates=sh.bullets(
            ["%s | %s%s" % (p["url"], p["title"], (" | " + p["covers"]) if p["covers"] else "")
             for p in candidates],
            empty="(no pages on file, so every internal_links list must be empty)"),
        sections_hint=_sections_hint(target_words),
        target_words=target_words,
    )
    try:
        data = llm.json_call(prompt)
    except Exception as e:
        return {"summary": "Blueprint failed.",
                "error": "The model did not return a usable structure: %s" % str(e)[:300]}

    sections, dropped_all = [], []
    for i, s in enumerate(data.get("sections") or [], start=1):
        if not isinstance(s, dict) or not s.get("heading"):
            continue
        try:
            words = int(s.get("words") or 0)
        except (TypeError, ValueError):
            words = 0
        links, dropped = _clean_links(s.get("internal_links"), valid_by_norm)
        dropped_all += dropped
        sections.append({
            "id": s.get("id") or "s%d" % i,
            "heading": s["heading"],
            "covers": s.get("covers", ""),
            "words": words or max(80, target_words // max(1, len(data.get("sections") or [1]))),
            "internal_links": links,
        })

    if not sections:
        return {"summary": "No usable sections came back.",
                "error": "The model replied but no entry had a heading. Worth retrying."}

    if dropped_all:
        say("Dropped " + sh.plural(len(dropped_all), "invented link"),
            "Not in your site index: " + ", ".join(dropped_all[:3]))

    total, rescaled = _rebalance(sections, target_words)
    if rescaled:
        say("Rebalanced the word budget",
            "Now %d words across %s" % (total, sh.plural(len(sections), "section")))

    blueprint = {
        "title": data.get("title") or topic,
        "meta_description": data.get("meta_description", ""),
        "primary_keyword": primary,
        "secondary_keywords": research.get("secondary_keywords") or [],
        "keyword_placement": data.get("keyword_placement", ""),
        "target_words": target_words,
        "planned_words": total,
        "sections": sections,
        "internal_links_dropped": dropped_all,
        "generated_at": store.now(),
    }
    store.save_artifact(chat_id, run_id, "blueprint.json", blueprint)
    linked = sum(len(s["internal_links"]) for s in sections)
    say("Structure ready", "%s, %s" % (blueprint["title"],
                                       sh.plural(linked, "internal link")))
    return {"summary": "%s, %s words" % (sh.plural(len(sections), "section"),
                                         format(total, ",")),
            "artifact": "blueprint.json"}
