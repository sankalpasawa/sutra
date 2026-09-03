"""ownpage.py — Step 4: the company's own pages that belong in this article, found by meaning.

This is where embeddings enter the research. Ported from 02-asset-engine/5-reuse-check
(step_1_retrieve.py: the two-vector index → blended dense score → rerank-2.5), the reuse judge
(prompts/reuse-judge.md) and 13-research-structure/harvest_ownpages.py (the LLM judges keep/skip and
writes the gloss; the verbatim is CODE-SLICED by heading section, so it is faithful by construction).

    query = the topic title with its parenthetical stripped → voyage.embed → _index.score (alpha 0.5)
    → top N_RETRIEVE pages → voyage.rerank over title[:200] + body (RERANK_DOC_CHARS) → top TOPK
    → ownpage cards from their bodies → the reuse verdict over the same pages.

Without a built page index it skips with a note and never crashes: own pages are enrichment, the
evidence cards are the article's real content.

Reads: topic, angle, the page index, the catalogue bodies. Writes (via the tool): _work/ownpage.json.
"""
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import llm
from ..tools import _index, voyage
from ..tools import _shared as sh
from . import _common as _c

NO_INDEX_NOTE = "no page index; own pages not attached"
NO_KEY_NOTE = "no Voyage key; own pages not attached"


def split_sections(body):
    """The catalogue body into heading-sections (code). Each = heading + its FULL text until the next
    heading; a leading pre-heading block is kept as an intro. Near-empty sections are dropped."""
    secs, head, buf = [], None, []
    for ln in (body or "").splitlines():
        m = re.match(r"^#{1,6}\s+(.*)", ln.strip())
        if m:
            if (head is not None) or buf:
                secs.append({"heading": head or "(intro)", "text": "\n".join(buf).strip()})
            head, buf = m.group(1).strip(), []
        else:
            buf.append(ln)
    if head is not None or buf:
        secs.append({"heading": head or "(intro)", "text": "\n".join(buf).strip()})
    return [s for s in secs if len(s["text"]) > 40]


def retrieve(topic, say=None):
    """The TOPK closest own pages: [{url, title, score}], or (None, note) when the index is not there."""
    st = _index.status()
    if not st.get("built"):
        return None, NO_INDEX_NOTE
    if not voyage.available():
        return None, NO_KEY_NOTE
    q = _c.query_text(topic)
    Q = voyage.embed([q], "query")
    blend, _T, _B, meta, order = _index.score(np.asarray(Q, dtype=np.float32), alpha=_c.ALPHA)
    scores = np.asarray(blend[0], dtype=np.float32)
    ranking = [int(k) for k in np.argsort(scores)[::-1] if not _c.is_foreign(order[int(k)])][:_c.N_RETRIEVE]
    cand = [order[k] for k in ranking]
    bodies = sh.page_bodies()

    def _doc(u):
        d = ((meta.get(u) or "")[:200] + "\n" + bodies.get(u.rstrip("/"), ""))[:_c.RERANK_DOC_CHARS]
        return d.replace("\x00", " ").strip() or "(no content)"

    try:
        ranked = voyage.rerank(q, [_doc(u) for u in cand], min(_c.TOPK, len(cand)))
        top = [(cand[i], float(sc)) for i, sc in ranked]
    except Exception:  # noqa: BLE001 — a rerank hiccup keeps the dense order, without scores
        top = [(u, 0.0) for u in cand[:_c.TOPK]]
    if say:
        say("Found %s of your own that fit" % _plural(len(top), "page"),
            "Matched by meaning against the page index, then re-ranked on their full text")
    return [{"url": u, "title": meta.get(u) or "", "score": round(sc, 3)} for u, sc in top], None


def harvest(pages, say=None):
    """Ownpage cards. The LLM judges keep/skip + writes the gloss; the verbatim is the full section text."""
    bodies = sh.page_bodies()

    def _one(page):
        secs = split_sections(bodies.get(page["url"].rstrip("/"), ""))
        if not secs:
            return []
        listing = "\n\n".join("[%d] %s\n%s" % (i, s["heading"], s["text"][:1500]) for i, s in enumerate(secs))
        p = _c.prompt("harvest-ownpage", sections=listing)
        for _ in range(_c.HARVEST_RETRIES + 1):
            try:
                out = llm.json_call(p)
            except Exception:  # noqa: BLE001
                out = []
            if isinstance(out, dict):
                out = out.get("sections") or out.get("cards") or []
            cards = []
            for it in (out or []):
                if not isinstance(it, dict):
                    continue
                i, gloss = it.get("index"), str(it.get("gloss") or "").strip()
                if not isinstance(i, int) or isinstance(i, bool) or not (0 <= i < len(secs)) or not gloss:
                    continue
                s = secs[i]
                cards.append({"gloss": gloss, "verbatim": s["text"], "source_urls": [page["url"]],
                              "internal_link": page["url"], "tag": "ownpage",
                              "heading": s["heading"], "origin": "ownpage/%s" % page["url"]})
            if cards:
                return cards
        return []

    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        results = list(ex.map(_one, pages))
    cards, failed = [], []
    for page, res in zip(pages, results):
        cards += res
        if not res:
            failed.append(page["url"])
    if say:
        say("Kept %s from your own pages" % _plural(len(cards), "passage"),
            ("%d pages gave nothing usable" % len(failed)) if failed else "Each one can become an internal link")
    return cards, failed


def reuse_judge(topic, angle, pages, company, fmt="article"):
    """{verdict, chosen_links, why}: should we build this, or do we already have it?"""
    if not pages:
        return {"verdict": "Brand new", "chosen_links": [], "why": "no existing page came close enough to read"}
    bodies = sh.page_bodies()
    block = "\n\n".join("[%d] %s — %s\n%s" % (i + 1, p.get("title") or "", p["url"],
                                            (bodies.get(p["url"].rstrip("/"), "") or "")[:_c.JUDGE_DOC_CHARS]
                                            or "(no text on file)")
                        for i, p in enumerate(pages))
    tok = _c.company_tokens(company)
    p = _c.prompt("reuse-judge", brand=tok["brand"], asset=topic, angle=angle or "", format=fmt, candidates=block)
    raw = llm.text(p) or ""
    v = re.search(r"(?im)^\s*Reuse verdict:\s*(.+)$", raw)
    ch = re.search(r"(?im)^\s*Chosen links:\s*(.+)$", raw)
    why = re.search(r"(?im)^\s*Why:\s*(.+)$", raw)
    verdict = next((x for x in _c.REUSE_VERDICTS if v and x.lower() in v.group(1).lower()), "Brand new")
    allowed = {p["url"].rstrip("/").lower(): p["url"] for p in pages}
    chosen = []
    for u in re.findall(r"https?://[^\s;,)]+", ch.group(1) if ch else ""):
        real = allowed.get(u.rstrip("/").lower())
        if real and real not in chosen:                 # cite ONLY links from the candidates
            chosen.append(real)
    return {"verdict": verdict, "chosen_links": chosen, "why": (why.group(1).strip() if why else "")}


def run(topic, angle, company, say=None):
    pages, note = retrieve(topic, say)
    if pages is None:
        if say:
            say("Own pages skipped", note)
        return {"cards": [], "pages": [], "reuse": None, "note": note}
    cards, failed = harvest(pages, say)
    reuse = reuse_judge(topic, angle, pages, company)
    if say:
        say("Reuse verdict: %s" % reuse["verdict"], reuse["why"][:160])
    return {"cards": cards, "pages": pages, "failed": failed, "reuse": reuse, "note": None}


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")
