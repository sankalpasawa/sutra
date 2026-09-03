"""web.py — the free page read: one HTTP GET, then the text, the h1-h3 headings and a word count.

Ported from 10-dataforseo/scripts/s5_pages.py (headings + word count, three tries with a
browser-like User-Agent, certificate errors ignored) and widened to keep the page TEXT too,
because the evidence engine reads the same pages for their facts. No paid call anywhere here.

Demo mode returns a synthetic page (flagged "_demo") so a demo run never touches the network.
"""
import re

import httpx
from bs4 import BeautifulSoup

from . import _common as _c

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
TIMEOUT = 25.0
TRIES = 3                    # retry transient blocks at least twice before giving up
MAX_TEXT_CHARS = 60000       # the original capped a page body at 60k before splitting it
_DROP_TAGS = ("script", "style", "noscript", "nav", "footer", "aside", "form", "svg", "iframe")


def parse(html):
    """{title, headings, text, word_count} out of raw HTML. Boilerplate tags are dropped before
    the text is read; the LLM harvest skips whatever boilerplate survives."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for t in soup(_DROP_TAGS):
        t.decompose()
    heads = [h.get_text(" ", strip=True)[:80] for h in soup.find_all(["h1", "h2", "h3"])]
    heads = [h for h in heads if h][:_c.HEADINGS_PER_PAGE]
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()[:MAX_TEXT_CHARS]
    return {"title": title[:200], "headings": heads, "text": text, "word_count": len(text.split())}


def fetch(url, tries=TRIES):
    """Read one page. Raises RuntimeError after `tries` failed attempts (caller decides to skip)."""
    last = None
    for attempt in range(tries):
        try:
            r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
                          timeout=TIMEOUT, follow_redirects=True, verify=False)
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "html" not in ctype and "text" not in ctype and ctype:
                raise RuntimeError("not an HTML page (%s)" % ctype[:40])
            page = parse(r.text)
            if page["word_count"] > 0:
                page["attempts"] = attempt + 1
                page["url"] = url
                return page
            last = "empty body"
        except Exception as e:  # noqa: BLE001 — network weather of every kind, then retry
            last = str(e)[:80]
    raise RuntimeError("failed after %d tries: %s" % (tries, last))


def passages(text, size=_c.PASSAGE_CHARS, cap=_c.PASSAGES_PER_PAGE):
    """The page text as a run of ~size-char passages, cut at paragraph boundaries where it can be,
    capped per page like the original retriever. What the harvest prompt reads."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = (buf + "\n" + p).strip()
            continue
        if buf:
            out.append(buf)
        while len(p) > size:                   # one paragraph longer than a passage: hard-cut it
            out.append(p[:size])
            p = p[size:]
        buf = p
        if len(out) >= cap:
            break
    if buf and len(out) < cap:
        out.append(buf)
    return out[:cap]


def demo_page(url, keyword=""):
    """A synthetic page for demo mode. Flagged, never mistaken for a real read."""
    kw = (keyword or "the topic").strip()
    host = _c.bare_domain(url) or "example.com"
    text = ("%s is a set of practices teams adopt to get a measurable result.\n\n"
            "According to a 2024 survey by %s, 62%% of teams that adopted %s reported a faster decision cycle.\n\n"
            "The typical cost of %s ranges from 400 to 1,200 dollars a month for a small team.\n\n"
            "Most guides agree that %s works best when it is measured weekly against a fixed baseline."
            % (kw.capitalize(), host, kw, kw, kw))
    return {"title": "%s guide (%s)" % (kw.title(), host), "url": url,
            "headings": ["What is %s" % kw, "How %s works" % kw, "What %s costs" % kw],
            "text": text, "word_count": len(text.split()), "attempts": 1, "_demo": True}
