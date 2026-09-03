"""evidence.py — Step 2: the evidence cards. The honest substitute for STORM (11-storm).

STORM is a vendored research engine with its own virtual environment and cannot ship inside this
package. What it produced for the pipeline was a pile of grounded facts, each traceable to a scraped
page. This module produces the same unit, the CARD, by a plainer route:

    search the primary and up to EVIDENCE_MAX_SECONDARY secondary keywords (a live SERP each, depth 10)
    → read the organic pages for free (httpx + BeautifulSoup), cut into PASSAGE_CHARS passages, at most
      PASSAGES_PER_PAGE per page, the way the original retriever fed STORM
    → one LLM harvest per page (prompts/research/harvest-evidence.md, adapted from 13's harvest-storm.md)
    → every verbatim is checked as an exact substring of the passage text (harvest_storm._norm) and a
      card that fails the check is dropped. Never invented.

It is narrower than STORM (no interviews, no outline, one pass) and says so in the run notes. The
gap check runs the same routine again on its own questions.

Reads: keywords, company. Returns {"cards": [...], "pages": [...], "cost": float, "skipped": [...]}.
"""
import json
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from ..tools import dfs
from . import _common as _c
from . import web

_SKIP_SUFFIXES = (".pdf", ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".zip")


def _serp_urls(keyword, company, depth=_c.EVIDENCE_SERP_DEPTH):
    got = dfs.serp_advanced(keyword, depth=depth, paa_click_depth=None, ai_overview=False,
                            location_name=company.get("location_name") or "United States",
                            language_code=company.get("language_code") or "en")
    urls = [r.get("url") for r in ((got.get("extract") or {}).get("top_organic") or []) if r.get("url")]
    return urls, got.get("cost") or 0.0, bool(got.get("demo"))


def plan_pages(keywords, company, own_domain="", exclude=(), max_pages=_c.EVIDENCE_MAX_PAGES, say=None):
    """The ordered, deduped list of pages to read: [(url, keyword)], plus the SERP cost."""
    seen = {u.rstrip("/").lower() for u in exclude}
    if own_domain:
        own_domain = _c.bare_domain(own_domain)
    planned, cost, demo = [], 0.0, False
    for kw in keywords:
        if len(planned) >= max_pages:
            break
        urls, c, d = _serp_urls(kw, company)
        cost += c
        demo = demo or d
        fresh = 0
        for u in urls:
            k = u.rstrip("/").lower()
            if k in seen or k.endswith(_SKIP_SUFFIXES):
                continue
            if own_domain and _c.bare_domain(u) == own_domain:
                continue                      # our own pages come through the page index, not as outside evidence
            seen.add(k)
            planned.append((u, kw))
            fresh += 1
            if len(planned) >= max_pages:
                break
        if say:
            say("Searched '%s'" % kw, "%d new pages to read" % fresh)
    return planned, round(cost, 6), demo


def _harvest_page(page, keyword):
    """Cards out of one page. Re-run up to HARVEST_RETRIES extra times if it yields nothing.
    Verbatims that are not in the text are dropped: the count is returned so the run can say so."""
    text = "\n\n".join(web.passages(page.get("text") or ""))
    if not text.strip():
        return [], 0
    p = _c.prompt("harvest-evidence", page_title=page.get("title") or page.get("url") or "",
                  page_url=page.get("url") or "", page_text=text)
    norm_text = _c.norm(text)
    for _ in range(_c.HARVEST_RETRIES + 1):
        try:
            out = llm.json_call(p)
        except Exception:  # noqa: BLE001 — retried, then reported as a page with no cards
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
            if _c.norm(vb) not in norm_text:            # anti-fabrication: it must really be there
                dropped += 1
                continue
            cards.append({"gloss": gloss, "verbatim": vb, "source_urls": [page["url"]],
                          "internal_link": None, "tag": "evidence",
                          "heading": (page.get("title") or "")[:120],
                          "origin": "evidence/%s/%s" % (keyword[:40], _c.bare_domain(page["url"]))})
        if cards:
            return cards, dropped
    return [], 0


def gather(keywords, company, own_domain="", exclude=(), max_pages=_c.EVIDENCE_MAX_PAGES, demo=False, say=None):
    """Search → read → harvest. Returns {"cards", "pages", "cost", "skipped", "dropped_verbatims"}."""
    keywords = [k for k in _c.strings(keywords) if k]
    planned, cost, demo_serp = plan_pages(keywords, company, own_domain, exclude, max_pages, say)
    demo = demo or demo_serp
    if say:
        say("Reading %s" % _plural(len(planned), "page"), "Free page reads, three tries each")

    def _read(item):
        u, kw = item
        if demo:
            return u, kw, web.demo_page(u, kw), None
        try:
            return u, kw, web.fetch(u), None
        except Exception as e:  # noqa: BLE001 — a page that will not open is skipped and named
            return u, kw, None, str(e)[:80]

    with ThreadPoolExecutor(max_workers=_c.PAGE_FETCH_WORKERS) as ex:
        read = list(ex.map(_read, planned))
    pages, skipped = [], []
    for u, kw, page, err in read:
        if page:
            page["url"] = u
            pages.append((page, kw))
        else:
            skipped.append({"url": u, "error": err})

    if say:
        say("Pulling the facts out of %s" % _plural(len(pages), "page"),
            "One card per distinct fact, quoted word for word; anything not in the page is thrown out")
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        harvested = list(ex.map(lambda pk: _harvest_page(pk[0], pk[1]), pages))
    cards, dropped, report = [], 0, []
    for (page, kw), (cs, d) in zip(pages, harvested):
        cards += cs
        dropped += d
        report.append({"url": page["url"], "title": page.get("title") or "", "keyword": kw,
                       "word_count": page.get("word_count"), "cards": len(cs), "demo": bool(page.get("_demo"))})
    return {"cards": cards, "pages": report, "cost": cost, "skipped": skipped,
            "dropped_verbatims": dropped, "demo": demo}


def dossier_text(cards):
    """The cards as one dossier the coverage judge and the triage read: [id] gloss — "verbatim" (source)."""
    lines = []
    for c in cards:
        src = (c.get("source_urls") or [c.get("internal_link") or ""])[0]
        lines.append("[%s] %s\n\"%s\"\n(%s)" % (c.get("id", "?"), c.get("gloss", ""), c.get("verbatim", ""), src))
    return "\n\n".join(lines) if lines else "(no evidence gathered yet)"


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")
