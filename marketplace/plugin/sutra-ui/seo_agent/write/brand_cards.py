"""brand_cards.py — Architect step 3: place the company's OWN material, if any of it earns a place.

Reads:  the structure (sections, their sub-headings, their cards) and knowledge/brand/brand-cards.json
        (the pool, built once per company by the brand builders).
Writes: the structure with placed ids joined onto the destination, the placed cards keyed by id, and
        every placement with its reason plus every rejection.

The pool holds two kinds and they are rationed differently. RESEARCH is the company's own study: neutral
data about its market, so it reads as evidence. RESULTS are what a named customer achieved using the
product, so every one is the company arguing for itself. The prompt states the caps; this file is what
makes them true.

Placement copies enrich exactly: a card joins an existing section's opening or one of its existing
sub-headings, by name. Nothing here ever creates a heading.
"""
from .. import llm, store
from . import _common as C
from . import shape

POOL_ID_BASE = 8001     # brand cards without an id are minted from here, so they never collide


def load_pool():
    """{"research": [cards], "results": [cards]} with integer card_ids, or None when there is no pool."""
    d = store.knowledge("brand/brand-cards.json")
    if not isinstance(d, dict):
        return None
    cards = d.get("cards") if isinstance(d.get("cards"), dict) else d
    pool = {"research": list(cards.get("research") or []), "results": list(cards.get("results") or [])}
    nxt = POOL_ID_BASE
    for kind in ("research", "results"):
        clean = []
        for c in pool[kind]:
            if not isinstance(c, dict):
                continue
            c = dict(c)
            cid = C.nid(c.get("card_id", c.get("id")))
            if not isinstance(cid, int):
                cid = nxt
                nxt += 1
            c["card_id"] = cid
            c.setdefault("gloss", c.get("verbatim") or "")
            c.setdefault("verbatim", c.get("gloss") or "")
            c.setdefault("source_urls", [])
            c["tag"] = c.get("tag") or ("brand-research" if kind == "research" else "brand-result")
            clean.append(c)
        pool[kind] = clean
    return pool


def _sections_block(sections, idx):
    """Every section with its heading, its job, its sub-headings, and the facts it ALREADY has."""
    out = []
    for i, sec in enumerate(sections, 1):
        out.append("--- SECTION %d: %s" % (i, sec.get("headline", "")))
        out.append("    JOB: %s" % (sec.get("job") or "(none given)"))
        for grp in shape.groups(sec):
            label = "OPENING (no sub-heading)" if not grp.get("h3") else 'SUB-HEADING: "%s"' % grp["h3"]
            facts = []
            for cid in (grp.get("card_ids") or [])[:C.BRAND_FACTS_SHOWN]:
                c = idx.get(C.nid(cid)) or {}
                g = (c.get("gloss") or c.get("verbatim") or "").strip().replace("\n", " ")
                if g:
                    facts.append("        · %s" % g[:C.ALLOC_GLOSS_CHARS])
            out.append("    " + label)
            out += facts or ["        · (no facts yet)"]
        out.append("")
    return "\n".join(out)


def _pool_block(cards, kind):
    lines = []
    for c in cards:
        extra = ""
        if kind == "result" and c.get("number"):
            extra = " | number: %s" % c["number"]
        topics = c.get("topics") or []
        if topics:
            extra += " | about: %s" % ", ".join(str(t) for t in topics)
        lines.append("  [%s] %s%s" % (c["card_id"], (c.get("gloss") or "").strip(), extra))
    return "\n".join(lines) or "  (none)"


def run(st, idx, ctx, say=lambda *a: None):
    pool = load_pool()
    if not pool or not (pool["research"] or pool["results"]):
        say("No brand material to place", "brand-cards.json is not on file for this company")
        return {"structure": st, "used": {}, "placement": {"placements": [], "rejected": [], "notes": "no pool"}}
    sections = st["sections"]
    reply = llm.json_call(C.prompt(
        "place-brand-cards", title=ctx["title"] or "(none)", angle=ctx["angle"] or "(none)",
        spine=st.get("spine") or C.or_na(ctx, "spine"), persona=ctx["persona"],
        sections=_sections_block(sections, idx),
        research_cards=_pool_block(pool["research"], "research"),
        result_cards=_pool_block(pool["results"], "result"),
        research_cap=C.BRAND_RESEARCH_CAP, research_per_section=C.BRAND_RESEARCH_PER_SECTION,
        result_cap=C.BRAND_RESULT_CAP)) or {}
    return place(st, pool, reply, say)


def place(st, pool, reply, say=lambda *a: None):
    """VALIDATE, THEN CAP. Every rejection is recorded with its reason: a cap that silently trims reads as
    "nothing else qualified", which is the opposite of what happened."""
    sections = st["sections"]
    by_id = {c["card_id"]: ("research", c) for c in pool["research"]}
    by_id.update({c["card_id"]: ("result", c) for c in pool["results"]})
    kept, rejected, per_section, n_res, n_out = [], [], {}, 0, 0
    for p in (reply.get("placements") or []):
        if not isinstance(p, dict):
            continue
        cid = p.get("card_id")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            rejected.append(dict(p, reason="card_id is not a number")); continue
        if cid not in by_id:
            rejected.append(dict(p, reason="card %d is not in the pool" % cid)); continue
        kind, card = by_id[cid]
        si = p.get("section")
        if not isinstance(si, int) or not (1 <= si <= len(sections)):
            rejected.append(dict(p, reason="section %s does not exist" % si)); continue
        sec = sections[si - 1]
        dest = str(p.get("goes_to") or "opening").strip()
        target = None
        if dest.lower() != "opening":
            target = next((h for h in sec.get("h3s") or [] if h.get("h3") == dest), None)
            if target is None:
                rejected.append(dict(p, reason='no sub-heading named "%s" in that section' % dest[:50]))
                continue
        if any(k["card_id"] == cid for k in kept):
            rejected.append(dict(p, reason="already placed")); continue
        if kind == "result":
            if n_out >= C.BRAND_RESULT_CAP:
                rejected.append(dict(p, reason="over the customer-result cap of %d" % C.BRAND_RESULT_CAP))
                continue
            n_out += 1
        else:
            if n_res >= C.BRAND_RESEARCH_CAP:
                rejected.append(dict(p, reason="over the research cap of %d" % C.BRAND_RESEARCH_CAP))
                continue
            if per_section.get(si, 0) >= C.BRAND_RESEARCH_PER_SECTION:
                rejected.append(dict(p, reason="section %d already has %d research card(s)"
                                     % (si, C.BRAND_RESEARCH_PER_SECTION)))
                continue
            per_section[si] = per_section.get(si, 0) + 1
            n_res += 1
        kept.append({"card_id": cid, "kind": kind, "section": si, "headline": sec.get("headline", ""),
                     "goes_to": "opening" if target is None else dest,
                     "why": str(p.get("why") or "").strip(), "gloss": card.get("gloss", "")})
        grp = target if target is not None else sec.setdefault(
            "lead", {"h3": "", "boxes": [], "card_ids": [], "is_lead": True})
        grp.setdefault("card_ids", []).append(cid)
    used = {str(k["card_id"]): by_id[k["card_id"]][1] for k in kept}
    st["brand_cards"] = kept
    placement = {"placements": kept, "rejected": rejected, "notes": str(reply.get("notes") or "").strip()}
    say("Placed the company's own material", "%d placed (%d research, %d customer result), %d rejected"
        % (len(kept), n_res, n_out, len(rejected)) if kept else
        "nothing placed, which is the expected answer for most articles")
    return {"structure": st, "used": used, "placement": placement}
