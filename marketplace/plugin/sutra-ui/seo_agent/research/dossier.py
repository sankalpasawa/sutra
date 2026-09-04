"""dossier.py — turn the research conversation into the cited dossier the harvest reads.

STORM's second half: outline the material, then write each section from the retrieved passages
with inline citations (`outline_generation.py`, `article_generation.py::WriteSection`). The
original then harvested cards out of THAT prose, which is the whole reason a card can be a
cross-source claim rather than a sentence copied off one page.

The numbering is the contract. Every source gets one index for the whole dossier, so `[7]` means
the same page in every section, and `sources()` hands the harvest the mapping. That is the port of
`url_to_info.json`.

Reads: the curate.run() result. Returns {"md", "sections", "sources", "words"}.
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c

MAX_SECTIONS = 8
PASSAGES_PER_SOURCE = 6      # per section, per source, best first
SECTION_SOURCES = 10         # sources shown to one section write


def _turn_lines(turns):
    out = []
    for i, t in enumerate(turns, start=1):
        out.append("%d. [%s] %s\n   %s" % (i, t.get("persona", ""), t.get("question", ""),
                                           (t.get("answer") or "").replace("\n", " ")[:600]))
    return "\n".join(out)


def outline(turns, article):
    """Group the questions into sections. Every question lands in exactly one."""
    data = llm.json_call(_c.prompt("dossier-outline", ARTICLE=article, TURNS=_turn_lines(turns))) or {}
    secs, placed = [], set()
    for s in (data.get("sections") or [])[:MAX_SECTIONS]:
        if not isinstance(s, dict) or not (s.get("title") or "").strip():
            continue
        idx = [int(n) for n in (s.get("questions") or [])
               if isinstance(n, (int, float)) and 1 <= int(n) <= len(turns) and int(n) not in placed]
        placed.update(idx)
        if idx:
            secs.append({"title": s["title"].strip(), "turns": idx})
    left = [i for i in range(1, len(turns) + 1) if i not in placed]
    if left:
        # nothing is dropped: the original's leftover pass, kept
        secs.append({"title": "Everything else the research found", "turns": left})
    return secs


def _info_block(section, turns, index, ranked):
    """The passages this section is written from, numbered by the dossier-wide source index."""
    urls, seen = [], set()
    for n in section["turns"]:
        for u in (turns[n - 1].get("urls") or []):
            if u not in seen:
                seen.add(u)
                urls.append(u)
    blocks = []
    for u in urls[:SECTION_SOURCES]:
        passages = (ranked.get(u) or [])[:PASSAGES_PER_SOURCE]
        if not passages:
            continue
        blocks.append("\n".join("[%d]: %s" % (index[u], p) for p in passages))
    return "\n\n".join(blocks), [u for u in urls[:SECTION_SOURCES] if ranked.get(u)]


def build(curated, article, say=None):
    """The dossier. One model call per section, run together."""
    turns = curated.get("turns") or []
    pages = {p["url"]: p for p in (curated.get("pages") or [])}
    if not turns:
        return {"md": "", "sections": [], "sources": [], "words": 0}

    # one index per source, for the whole dossier, so [7] means the same page everywhere
    order = []
    for t in turns:
        for u in (t.get("urls") or []):
            if u in pages and u not in order:
                order.append(u)
    index = {u: i for i, u in enumerate(order, start=1)}
    ranked = {u: (pages[u].get("passages") or []) for u in order}

    secs = outline(turns, article)
    if say:
        say("Grouped the research into %d sections" % len(secs),
            "; ".join(s["title"][:44] for s in secs[:4]))

    def one(s):
        info, used = _info_block(s, turns, index, ranked)
        if not info.strip():
            return {"title": s["title"], "md": "", "sources": []}
        md = llm.text(_c.prompt("write-dossier-section", ARTICLE=article,
                                SECTION=s["title"], INFO=info), timeout=llm.LONG_TIMEOUT) or ""
        return {"title": s["title"], "md": md.strip(), "sources": used}

    with ThreadPoolExecutor(max_workers=3) as pool:
        written = list(pool.map(one, secs))
    body = "\n\n".join(w["md"] for w in written if w["md"])
    words = len(body.split())
    if say:
        say("Dossier written", "%d words across %d sections, %d sources cited"
            % (words, sum(1 for w in written if w["md"]), len(order)))
    return {"md": body, "sections": written, "words": words,
            "sources": [{"n": index[u], "url": u, "title": pages[u].get("title", "")} for u in order]}


def sources_block(sources):
    """The numbered source list, for the harvest and for the run's saved dossier."""
    return "\n".join("[%d] %s — %s" % (s["n"], s.get("title") or "", s["url"]) for s in sources)


# ---- the harvest: dossier prose -> cards, citations resolved back to real URLs ----------------

_CITE = None


def harvest(doc, say=None):
    """Cards out of the dossier, one parallel call per section, the way harvest_storm.py does.

    Every verbatim is checked as a real substring of the section it claims to come from, and its
    [n] markers are resolved through the dossier's own source index. A card whose quote is not
    really there is dropped and counted; a card with no resolvable citation keeps its section's
    sources, so a cross-source claim never loses its provenance.
    """
    import re
    global _CITE
    if _CITE is None:
        _CITE = re.compile(r"\[(\d+)\]")
    by_n = {s["n"]: s["url"] for s in (doc.get("sources") or [])}
    sections = [s for s in (doc.get("sections") or []) if s.get("md")]
    if not sections:
        return {"cards": [], "dropped_verbatims": 0}

    def one(sec):
        text = sec["md"]
        norm_text = _c.norm(text)
        p = _c.prompt("harvest-dossier", section_title=sec["title"], section_text=text)
        for _ in range(_c.HARVEST_RETRIES + 1):
            try:
                out = llm.json_call(p)
            except Exception:  # noqa: BLE001
                out = []
            if isinstance(out, dict):
                out = out.get("cards") or []
            cards, dropped = [], 0
            for c in (out or []):
                if not isinstance(c, dict):
                    continue
                vb = str(c.get("verbatim") or "").strip()
                gloss = str(c.get("gloss") or "").strip()
                if not vb or not gloss:
                    continue
                if _c.norm(vb) not in norm_text:        # anti-fabrication: it must really be there
                    dropped += 1
                    continue
                urls = [by_n[int(n)] for n in _CITE.findall(vb) if int(n) in by_n]
                if not urls:
                    urls = list(sec.get("sources") or [])   # a cross-source claim keeps its section's
                cards.append({"gloss": gloss, "verbatim": vb, "source_urls": urls,
                              "internal_link": None, "tag": "evidence",
                              "heading": sec["title"][:120],
                              "origin": "dossier/%s" % sec["title"][:60]})
            if cards:
                return cards, dropped
        return [], 0

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, sections))
    cards = [c for rows, _ in results for c in rows]
    dropped = sum(d for _, d in results)
    if say:
        say("Pulled %d fact%s out of the dossier" % (len(cards), "" if len(cards) == 1 else "s"),
            "One card per distinct fact, quoted word for word"
            + ("; %d quotes did not match and were thrown out" % dropped if dropped else ""))
    return {"cards": cards, "dropped_verbatims": dropped}
