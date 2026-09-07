"""attach.py — Blueprint step 5: evidence + links under each H2/H3. Pure code, by card id.

Ported from 13-research-structure/scripts/attach.py. Evidence = the member cards (by id; the writer
reads cards.json). Internal links = the member ownpage URLs. External = genuine OUTSIDE sources only,
never a card's own page URL (that is an internal link, not a source).
"""


def _collect(card_ids, by_id):
    evidence, internal, external = [], [], []
    for i in card_ids:
        c = by_id.get(i)
        if not c:
            continue
        if c.get("verbatim"):
            evidence.append(i)
        if c.get("internal_link"):
            internal.append(c["internal_link"])
        external += [u for u in (c.get("source_urls") or []) if u != c.get("internal_link")]
    return evidence, list(dict.fromkeys(internal)), list(dict.fromkeys(external))


def run(sections, cards):
    by_id = {c["id"]: c for c in cards}
    out = []
    for s in sections:
        ev, itn, ext = _collect(s["card_ids"], by_id)
        h3s = []
        for h in s.get("h3", []):
            hev, hitn, hext = _collect(h["card_ids"], by_id)
            h3s.append({"h3": h["h3"], "evidence": hev, "internal_links": hitn, "external_links": hext})
        # section-level rollup (union across the H2's own cards + its H3s)
        all_int = list(dict.fromkeys(itn + [u for h in h3s for u in h["internal_links"]]))
        all_ext = list(dict.fromkeys(ext + [u for h in h3s for u in h["external_links"]]))
        out.append({"h2": s["h2"], "job": s.get("job") or "", "target_keyword": None,
                    "evidence": ev, "internal_links": all_int, "external_links": all_ext, "h3": h3s})
    return out
