"""assemble.py — Writer step 10: ASSEMBLE. Turn the parts into the finished article.

Reads:  the cleaned article (h1, intro, quick answer, sections, faq, close, close_heading, links,
        citation_keep) + the card index (for the source links) + the keywords block.
Writes: the draft markdown, the keyword coverage COUNTED from the finished text (never AI-reported), the
        numbered Sources list and the length against the word band (recorded; nothing trims).

THE SOURCES LIST is the CURATED external set when the links pass kept one, numbered 1..N in the order a
reader first meets them, one number per URL (two cards sharing a source share one number). A citation
whose source did not make the list is stripped from display; its provenance stays in the work files.
Markers appear only at the places the links pass kept for an over-cited source (citation_keep).

The order: H1, intro, ## Quick answer, sections, ## <close heading>, close, ## Frequently asked
questions, ## Sources. The close comes before the FAQ: it ends the argument; the FAQ is reference.
"""
import re

from . import _common as C
from . import tags


def _plain(text):
    return C.plain_links(text)


def _phrase_re(phrase):
    """A phrase matches however it is punctuated: 'cost per hire' and 'cost-per-hire' are the same keyword."""
    parts = [re.escape(p) for p in re.split(r"[^a-z0-9]+", (phrase or "").lower()) if p]
    if not parts:
        return None
    joiner = r"[\s\-‐-―'‘’\"“”]+"
    return re.compile(r"(?<![a-z0-9])" + joiner.join(parts) + r"(?![a-z0-9])", re.I)


def _count(text, phrase):
    rx = _phrase_re(phrase)
    return len(rx.findall(text or "")) if rx else 0


def coverage(w, ks):
    """Where every target phrase actually landed. Counted, not claimed. ks = the architect's keywords block."""
    primary = ks.get("primary") or ""
    variations = [v for v in (ks.get("variations") or []) if v]
    h2kw = [k for k in (ks.get("section_keywords") or []) if k]
    sections = [dict(s, prose=_plain(s["prose"]), heading=_plain(s["heading"])) for s in w["sections"]]
    body = "\n\n".join(s["prose"] for s in sections)
    opening = " ".join((w.get("intro") or "").split())
    first100 = " ".join((opening + " " + body).split()[:100])
    whole = "\n\n".join([w.get("h1") or "", opening, "\n".join(s_["heading"] for s_ in sections), body,
                         "\n".join("%s %s" % (f["question"], f["answer"]) for f in (w.get("faq") or [])),
                         w.get("close") or ""])

    def where(p):
        return {"phrase": p, "total": _count(whole, p), "in_h1": bool(_count(w.get("h1") or "", p)),
                "in_first_100_words": bool(_count(first100, p)),
                "in_headings": sum(1 for s in sections if _count(s["heading"], p)),
                "in_close": bool(_count(w.get("close") or "", p)),
                "sections": [s["heading"] for s in sections if _count(s["prose"], p)]}

    prim = where(primary)
    var = [where(v) for v in variations]
    return {"primary": prim, "primary_plus_variations_total": prim["total"] + sum(v["total"] for v in var),
            "variations": var, "h2_keywords": [where(k) for k in h2kw],
            "checklist": {
                "primary in H1": prim["in_h1"],
                "primary in first 100 words": prim["in_first_100_words"],
                "keywords in at least 2 headings":
                    2 <= sum(1 for s_ in sections if any(_count(s_["heading"], p) for p in [primary] + variations + h2kw)),
                "primary in the close": prim["in_close"],
                "at least one section keyword used": any(_count(whole, k) for k in h2kw)}}


def render(w, idx):
    """The article as it publishes. Returns (markdown, ordered source urls, {card_id: number}, bare sections)."""
    kept_urls = [k["url"] for k in ((w.get("links") or {}).get("external_kept") or [])]
    curated = bool(kept_urls)
    num_of, order, used = {}, [], {}
    cite_keep = {int(k): set(v) for k, v in (w.get("citation_keep") or {}).items()}
    seen_count = {}

    def refs(text, capped=True):
        def one(found):
            out = []
            for cid in found:
                u = ((idx.get(cid) or {}).get("source_urls") or [None])[0]
                if not u:
                    continue
                if curated and u not in kept_urls:
                    continue
                if capped and cid in cite_keep:
                    seen_count[cid] = seen_count.get(cid, 0) + 1
                    if seen_count[cid] not in cite_keep[cid]:
                        continue
                if u not in num_of:
                    order.append(u)
                    num_of[u] = len(order)
                used[cid] = num_of[u]
                out.append(str(num_of[u]))
            return ("[" + "][".join(dict.fromkeys(out)) + "]") if out else ""
        return re.sub(r" +([.,;:])", r"\1", tags.sub(text, one))

    L = ["# %s" % (w.get("h1") or ""), "", refs(w.get("intro") or ""), ""]
    if w.get("quick_answer"):
        L += ["## Quick answer", "", refs(w["quick_answer"]), ""]
    bare = 0
    for s in w["sections"]:
        body = refs(s["prose"])
        bare += 0 if re.search(r"\[\d+\]", body) else 1
        L += ["## %s" % s["heading"], "", body, ""]
    if w.get("close_heading"):
        L += ["## %s" % w["close_heading"], ""]
    L += [refs(w.get("close") or ""), ""]
    if w.get("faq"):
        L += ["## Frequently asked questions", ""]
        for f in w["faq"]:
            L += ["**%s**" % f["question"], "", refs(f["answer"], capped=False), ""]
    L += ["## Sources", ""]
    for i, u in enumerate(order, 1):
        L.append("%d. %s" % (i, u))
    return "\n".join(L) + "\n", order, used, bare


def run(w, idx, ks, plan, say=lambda *a: None):
    cov = coverage(w, ks)
    md, order, used, bare = render(w, idx)
    wb = plan.get("word_band") or {}
    lo, hi = wb.get("min") or 0, wb.get("max") or 0
    article = md.split("\n## Sources\n")[0]
    n = len(re.sub(r"\[\d+\]", "", _plain(article)).split())
    cov["length"] = {"words": n, "band_min": lo, "band_max": hi, "in_band": bool(lo and hi and lo <= n <= hi),
                     "over_by_pct": round((n - hi) / hi * 100, 1) if hi and n > hi else 0}
    fails = [k for k, v in cov["checklist"].items() if not v]
    say("Article assembled", "%d words, %d sections, %d FAQ, %d sources%s" % (n, len(w["sections"]), len(w.get("faq") or []), len(order),
        ("; %d section(s) carry no visible citation" % bare) if bare and order else ""))
    if lo and hi:
        say("Length against the word band", ("%d words, inside %d to %d" % (n, lo, hi)) if cov["length"]["in_band"]
            else ("%d words, %s the %d to %d band" % (n, "over" if n > hi else "under", lo, hi)))
    say("Keyword checklist", "all pass" if not fails else "missed: " + "; ".join(fails))
    return {"draft": md, "coverage": cov, "sources": [{"n": i + 1, "url": u} for i, u in enumerate(order)],
            "used": {str(k): v for k, v in used.items()}, "bare_sections": bare}
