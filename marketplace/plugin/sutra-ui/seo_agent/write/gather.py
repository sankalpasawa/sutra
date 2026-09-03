"""gather.py — Planner step 1: GATHER the raw material for one article into one dict.

Reads:  blueprint.json (the sections menu, h1, keyword set, persona, format), research.json (the world,
        the spine, the keywords, the SERP lists, the winners study, the build spec) and cards.json.
Writes: {"group_a": the article's settings, "group_b": the selection raw material, "vet": the audit}.

Everything is a clean lift except ONE model call, vet-lists.md, which keeps only the People-Also-Ask
questions, related searches and table-stakes topics a reader of THIS article would care about. The
original also lifted the winners lists and the word band out of prose with two more calls; here the
research brief already carries them as data, so those two calls have nothing left to do.

TABLE STAKES ride the same vetting call: they need exactly the same world test, and the architect reads
them to decide what an article covers early, so an off-angle topic every competitor happens to share
would push the article toward being the tenth copy of a page that already ranks. Kept most-missed
first; that order is used downstream. Capped at MAX_TABLE_STAKES.
"""
from .. import llm
from . import _common as C


def _vet_kept(kept, originals):
    """Match a keep-list back against the originals (verbatim), dedupe, never wipe a list to zero."""
    if kept is None:
        return list(dict.fromkeys(originals))
    ks, seen = set(kept), set()
    out = [q for q in originals if q in ks and not (q in seen or seen.add(q))]
    return out or list(dict.fromkeys(originals))


def _vet_lists(ctx, brand, paa, related, table_stakes, say):
    """ONE AI call vets all three Google lists against the article's title, angle and WORLD."""
    if not paa and not related and not table_stakes:
        return paa, related, table_stakes, {"skipped": "nothing to vet"}
    try:
        r = llm.json_call(C.prompt(
            "vet-lists", brand=brand["brand"], about=brand["about"],
            title=ctx["title"] or "(none given)", angle=ctx["angle"] or "(none given)",
            world_about=C.or_na(ctx, "about"), world_not_about=C.or_na(ctx, "not_about"),
            questions="\n".join("- " + q for q in paa) or "(none)",
            related="\n".join("- " + q for q in related) or "(none)",
            table_stakes="\n".join("- " + q for q in table_stakes) or "(none)",
            max_table_stakes=C.MAX_TABLE_STAKES)) or {}
    except Exception as e:      # noqa: BLE001
        # SAY SO. A silent fallback is a silent downgrade: three articles once shipped with unfiltered
        # lists before anyone noticed.
        say("Could not vet the search lists", "The lists go through unfiltered: %s" % str(e)[:90])
        return paa, related, table_stakes, {"failed": str(e)[:120]}
    kept_q = _vet_kept(r.get("keep_questions"), paa)
    kept_r = _vet_kept(r.get("keep_related"), related)
    # NOT _vet_kept for the table stakes: that helper restores the ORIGINAL order, and here the order
    # the model returned IS the answer, most-missed first.
    ks = [str(x).strip() for x in (r.get("keep_table_stakes") or []) if str(x).strip()]
    kept_t = [x for x in ks if x in set(table_stakes)][:C.MAX_TABLE_STAKES] or table_stakes[:C.MAX_TABLE_STAKES]
    return kept_q, kept_r, kept_t, {"paa_raw": paa, "related_raw": related, "table_stakes_raw": table_stakes,
                                    "paa_kept": kept_q, "related_kept": kept_r, "table_stakes_kept": kept_t}


def _keyword_set(blueprint, research):
    ks = dict((blueprint or {}).get("keyword_set") or {})
    rk = (research or {}).get("keywords") or {}
    if not ks.get("primary"):
        prim = rk.get("primary") or {}
        ks["primary"] = prim.get("keyword", "") if isinstance(prim, dict) else str(prim or "")
    ks.setdefault("variations", [v if isinstance(v, str) else (v.get("keyword") or "")
                                 for v in (rk.get("variations") or [])])
    ks.setdefault("secondaries", [v if isinstance(v, str) else (v.get("keyword") or "")
                                  for v in (rk.get("secondary") or [])])
    ks["variations"] = [v for v in ks.get("variations") or [] if v]
    ks["secondaries"] = [v for v in ks.get("secondaries") or [] if v]
    ks.pop("in_body", None)                       # below the volume floor: not carried
    return ks


def _word_band(blueprint, research):
    for src in ((research or {}).get("build_spec") or {}, blueprint or {}):
        wb = src.get("word_band") or {}
        try:
            lo, hi = int(wb.get("min") or 0), int(wb.get("max") or 0)
        except (TypeError, ValueError):
            continue
        if lo > 0 and hi >= lo:
            return {"min": lo, "max": hi}
        if lo > 0:
            return {"min": lo, "max": round(lo * 1.2)}
    return {"min": 0, "max": 0}


def _signals(research):
    rk = (research or {}).get("keywords") or {}
    prim = rk.get("primary") if isinstance(rk.get("primary"), dict) else {}
    intent = (((research or {}).get("build_spec") or {}).get("search_intent")
              or prim.get("intent") or ((research or {}).get("serp") or {}).get("intent") or "")
    aio = ((research or {}).get("serp") or {}).get("ai_overview") or ""
    if isinstance(aio, dict):
        aio = aio.get("text") or ""
    return str(intent).strip(), str(aio).strip()


def _menu(blueprint, idx):
    """The blueprint's sections with every evidence id resolved to its card."""
    out = []
    for s in (blueprint or {}).get("sections") or []:
        h3s = []
        for h in s.get("h3") or []:
            h3s.append({"h3": h.get("h3", ""), "evidence": C.cards_of(idx, h.get("evidence") or []),
                        "internal_links": h.get("internal_links") or []})
        out.append({"h2": s.get("h2", ""), "job": s.get("job", ""),
                    "target_keyword": s.get("target_keyword"),
                    "evidence": C.cards_of(idx, s.get("evidence") or []), "h3": h3s,
                    "internal_links": s.get("internal_links") or []})
    return out


def run(blueprint, research, cards, say=lambda *a: None):
    idx = C.card_index(cards)
    ctx = C.context(blueprint, research)
    brand = C.company()
    serp = (research or {}).get("serp") or {}
    winners = (research or {}).get("winners") or {}

    paa = [str(x) for x in (serp.get("paa_on") or serp.get("paa") or []) if str(x).strip()]
    related = [str(x) for x in (serp.get("related_on") or serp.get("related_searches") or []) if str(x).strip()]
    common = [str(x) for x in (winners.get("common_h2s") or []) if str(x).strip()]
    say("Checking the search lists against this article",
        "%d questions, %d related searches, %d shared topics" % (len(paa), len(related), len(common)))
    paa_k, related_k, stakes, vet = _vet_lists(ctx, brand, paa, related, common, say)
    say("Kept what a reader of this article would care about",
        "%d questions, %d related searches, %d expected topics" % (len(paa_k), len(related_k), len(stakes)))

    ks = _keyword_set(blueprint, research)
    intent, ai_overview = _signals(research)
    menu = _menu(blueprint, idx)
    internal_pool = []
    for s in menu:
        internal_pool += s.get("internal_links") or []
    group_a = {
        "h1": (blueprint or {}).get("h1") or "",
        "title": ctx["title"], "angle": ctx["angle"],
        "internal_link_pool": list(dict.fromkeys(internal_pool)),
        "format_archetype": (blueprint or {}).get("format_archetype") or "",
        "format_label": str(winners.get("format") or "").strip(),
        "primary_keyword": ks.get("primary", ""),
        "keyword_set": ks,
        "persona": (blueprint or {}).get("persona") or (research or {}).get("persona") or {},
        "word_band": _word_band(blueprint, research),
        "search_intent": intent,
        "ai_overview": ai_overview,
        "table_stakes": stakes,
    }
    group_b = {
        "sections_menu": menu,
        "gaps_to_own": [str(x) for x in (winners.get("gaps_to_own") or [])],
        "winners_common_h2s": common,
        "winners_drift": [str(x) for x in (winners.get("drift") or [])],
        "paa_pool": paa_k,
        "related_searches": related_k,
    }
    n_cards = sum(len(s["evidence"]) + sum(len(h["evidence"]) for h in s["h3"]) for s in menu)
    say("Gathered the material", "%d sections, %d facts, word band %d to %d"
        % (len(menu), n_cards, group_a["word_band"]["min"], group_a["word_band"]["max"]))
    return {"group_a": group_a, "group_b": group_b, "vet": vet}
