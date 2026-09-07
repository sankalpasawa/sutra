"""The extractor ladder — turns cached pages into catalogue rows. OFFLINE by design.

Reads:  reconciled.json + the raw cache (and the cached WP API pages for CMS bodies).
Writes: _work/extracted.json — a list of rows:
  {url, type, title, description, h1, body, canonical, word_count, modified, lang, source,
   extractor, body_status, og_site_name}

Two stages:

1. EXTRACT each page, keeping everything the page holds. The ladder is triggered by MEASURED
   OUTCOME only, never by a framework marker:
     rung 1  CMS body (WordPress REST) — used only when it is a fair SHARE of the live page
     rung 2  the DOM text of the noise-stripped live page — longest wins, ties to the CMS body
     rung 3  JSON-LD articleBody / <article> baseline
     floor   the whole document's text, last resort only
     else    body_status = failed  (NEVER silently blank)
   No browser render: a page whose HTML holds no text is recorded as failed, and the gate says so.

2. DE-BOILERPLATE across the whole site, per language. A line that appears on >= DEBOILER_FRAC of
   a language's pages is site chrome (menu / header / footer) — a UNIQUE article sentence appears
   on one page only, so this can never delete real content. Per-language so a TRANSLATED menu is
   caught too. This is the whole cleaning step: extract keeps too much, then repetition, a fact
   and not a guess, decides what is chrome.
"""
import collections
import copy
import json
import os
import re
import statistics

from bs4 import BeautifulSoup, NavigableString
from bs4.element import Comment, Declaration, Doctype, ProcessingInstruction

from .. import store
from . import settings
from .urls import store_norm

# Semantic tags that never carry body text — skipped while serialising the DOM.
DROP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "header", "footer",
             "template"}
# Block-level tags that force a line break when serialising (so headings/paragraphs stay separate).
_BLOCK_EL = {"p", "div", "section", "article", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3",
             "h4", "h5", "h6", "br", "blockquote", "figcaption", "dt", "dd", "main", "aside",
             "pre", "figure"}
# Stripped BEFORE any text measurement — Next.js embeds huge JSON blobs in <script> that would
# otherwise be counted as page text.
_NOISE_TAGS = {"script", "style", "noscript", "template"}
_SKIP_STRINGS = (Comment, Declaration, Doctype, ProcessingInstruction)


# ---- text / DOM plumbing ----------------------------------------------------------------------

def _lines(text):
    return [ln.strip() for ln in (text or "").split("\n") if ln.strip()]


def strip_noise(soup):
    """Remove what a READER never sees: tags that hold no prose, and elements the page itself
    marks as not displayed. The second half matters — a page builder ships conditional blocks in
    the HTML and hides them, so an extractor that reads the markup picks up text no visitor ever
    sees. Measured 2026-07-19: 2,241 rows (21% of the sheet) carried the hidden editorial note
    'Conditional Psychometric Logo Section (Only shown for specific test)'. Hidden is a statement
    by the page about its own content, so honouring it is reading the page correctly."""
    for el in list(soup.find_all(True)):
        if el.decomposed:
            continue
        if el.name in _NOISE_TAGS:
            el.decompose()
            continue
        style = str(el.get("style") or "").replace(" ", "").lower()
        if ("display:none" in style or "visibility:hidden" in style
                or el.has_attr("hidden")
                or str(el.get("aria-hidden") or "").lower() == "true"):
            el.decompose()
    return soup


def mark_headings(node):
    """h1/h2/h3 -> inline '# ' / '## ' / '### ' markers INSIDE the element. Downstream splits on these."""
    for level, tag in ((1, "h1"), (2, "h2"), (3, "h3")):
        for el in node.find_all(tag):
            if not el.decomposed:
                el.insert(0, NavigableString("#" * level + " "))
    return node


def dom_text(node, drop=DROP_TAGS):
    """Serialise a (marked) tree to text with block breaks and '- ' list bullets."""
    out = []

    def walk(n):
        if isinstance(n, NavigableString):
            if not isinstance(n, _SKIP_STRINGS):
                out.append(str(n))
            return
        tag = n.name or ""
        if tag in drop:
            return
        if tag == "li":
            out.append("\n- ")
        elif tag in _BLOCK_EL:
            out.append("\n")
        for c in n.contents:
            walk(c)
        if tag in _BLOCK_EL:
            out.append("\n")

    walk(node)
    text = "".join(out)
    text = re.sub(r"[ \t\r\xa0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def scope(soup):
    return (soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
            or soup.body or soup)


def _text_len(soup):
    return len(" ".join(soup.get_text(" ").split()))


def extract_dom(clean):
    """DOM serialiser: focus on the main region, keep everything it holds. Chrome is removed later
    by the de-boilerplate pass, not here — so no content is ever cut by a guess at this stage."""
    return dom_text(mark_headings(copy.deepcopy(scope(clean))))


def _jsonld_body(soup):
    best = ""

    def dig(o):
        nonlocal best
        if isinstance(o, dict):
            b = o.get("articleBody")
            if isinstance(b, str) and len(b) > len(best):
                best = b
            for v in o.values():
                dig(v)
        elif isinstance(o, list):
            for v in o:
                dig(v)

    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            dig(json.loads(s.string or s.get_text() or ""))
        except (ValueError, TypeError):
            continue
    return best.strip()


def _meta(soup, rec):
    title = rec.get("title") or ""
    if not title:
        title = soup.title.get_text(strip=True) if soup.title else ""
    desc = rec.get("description") or ""
    if not desc:
        m = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        desc = (m.get("content") or "").strip() if m else ""
    lang = ((soup.html.get("lang") if soup.html else "") or "").strip()[:5]
    h1 = soup.find("h1")
    h1 = " ".join(h1.get_text(" ").split()) if h1 else ""
    og = soup.find("meta", attrs={"property": "og:site_name"})
    og = (og.get("content") or "").strip() if og else ""
    return title, desc, lang, h1, og


# ---- body tidy (text-level, applied to every extractor's output) ------------------------------
# Rubbish that survives EVERY extractor because it is real text in the rendered page, not markup:
# page-builder placeholder tokens, bare CSS selectors, and the "Skip to content" skip-link that
# always sits immediately before a site's nav. None of it can be a sentence, so removing it by
# shape is safe.
_TEMPLATE_TOKEN_RE = re.compile(r"^\s*(?:\[/?element-\d+\]|\[/?et_pb_\w+\]|\.[a-z][\w-]{2,}"
                                r"|#[a-z][\w-]{2,}|\{[^}]*\}|/\*.*\*/)\s*$", re.I)
_SKIPLINK_RE = re.compile(r"^\s*skip to (?:content|main)", re.I)


def tidy(text):
    if not text:
        return text
    lines = [ln.replace("\t", " ").rstrip() for ln in text.split("\n")]
    lines = [ln for ln in lines if not _TEMPLATE_TOKEN_RE.match(ln)]
    for i, ln in enumerate(lines[:80]):                   # cut a leading skip-link nav block
        if _SKIPLINK_RE.match(ln):
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s.startswith("#") or len(s) > 60:
                    lines = lines[j:]
                    break
            break
    out, blank = [], 0
    for ln in lines:                                      # collapse whitespace runs
        if not ln.strip():
            blank += 1
            if blank > 1 or not out:
                continue
            out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip()


def status_of(body, extractor):
    if extractor in ("", "none") or extractor.startswith("error:"):
        return "failed" if len(body) < settings.EXTRACT_FAIL_CHARS else "ok"
    if len(body) < settings.EXTRACT_FAIL_CHARS:
        return "failed"
    if len(body) < settings.EXTRACT_STUB_CHARS:
        return "stub"
    return "ok"


def _plain_words(body):
    return len(re.sub(r"^#{1,3} ", "", body, flags=re.M).split())


def _row(url, rec, body, extractor, title, desc, lang, h1="", og=""):
    body = tidy(body)
    return {
        "url": url, "type": rec.get("type", ""), "title": title, "description": desc, "h1": h1,
        "body": body, "canonical": rec.get("canonical_declared", ""),
        "word_count": _plain_words(body), "modified": rec.get("modified", ""), "lang": lang,
        "source": "+".join(rec.get("sources", [])), "extractor": extractor,
        "body_status": status_of(body, extractor), "og_site_name": og,
    }


def extract_one(url, rec, live_html, rest_html):
    soup = None
    title = desc = lang = h1 = og = ""
    if live_html:
        try:
            soup = BeautifulSoup(live_html, "html.parser")
        except Exception:
            soup = None
    if soup is not None:
        title, desc, lang, h1, og = _meta(soup, rec)
    else:
        title, desc = rec.get("title", ""), rec.get("description", "")

    # rung 1 — the CMS body. PREFERRED but never trusted blindly: on a page-builder site the CMS
    # field often holds only a FRAGMENT (commonly just the FAQ) while the real page is assembled at
    # render time. Keep it only when it is a fair SHARE of what the live page holds; else fall
    # through. Ties go to the CMS body — it is cleaner by construction.
    rest_body = ""
    if rest_html and rest_html.strip():
        try:
            rest_body = dom_text(mark_headings(BeautifulSoup(rest_html, "html.parser")))
        except Exception:
            rest_body = ""
        if len(rest_body) >= settings.EXTRACT_FAIL_CHARS and (
                soup is None or len(rest_body) >= settings.REST_MIN_SHARE * _text_len(soup)):
            return _row(url, rec, rest_body, "rest", title, desc, lang, h1, og)

    # rung 2 — the DOM text of the noise-stripped page; the CMS body stays in the running as a floor.
    best, best_name = (rest_body, "rest") if len(rest_body) >= settings.EXTRACT_FAIL_CHARS else ("", "")
    if soup is not None:
        clean = strip_noise(soup)
        text = extract_dom(clean)
        if len(text) > len(best):
            best, best_name = text, "dom"

        # rung 3 — JSON-LD articleBody / bare <article> baseline
        if len(best) < settings.EXTRACT_FAIL_CHARS:
            jb = _jsonld_body(clean)
            if len(jb) > len(best):
                best, best_name = jb, "jsonld"
            art = clean.find("article")
            if art is not None:
                at = dom_text(mark_headings(copy.deepcopy(art)))
                if len(at) > len(best):
                    best, best_name = at, "article"

        # floor — the whole document's text, last resort only
        if len(best) < settings.EXTRACT_FAIL_CHARS:
            h = dom_text(mark_headings(copy.deepcopy(clean)), drop=_NOISE_TAGS)
            if len(h) > len(best):
                best, best_name = h, "html2txt"

    return _row(url, rec, best, best_name or "none", title, desc, lang, h1, og)


# ---- the CMS bodies, re-read OFFLINE from the cached API pages ---------------------------------

def rest_bodies(fx, pages):
    """stored link -> content.rendered, from the cached WP API pages. Zero network."""
    api_pages = sorted({rec.get("api_page") for rec in pages.values() if rec.get("api_page")})
    bodies = {}
    for ap in api_pages:
        r = fx.cached(ap)
        if r is None:
            continue
        try:
            items = json.loads(r.text)
        except ValueError:
            continue
        for it in items if isinstance(items, list) else []:
            link = store_norm((it or {}).get("link", ""))
            body = (((it or {}).get("content") or {}).get("rendered", "")) or ""
            if link and body:
                bodies[link] = body
    return bodies


# ---- de-boilerplate ----------------------------------------------------------------------------
# The concatenated language-switcher line (a run of language names glued together) and a lone
# language-code line ("EN", "ES") vary page to page, so line-frequency misses them — dropped by shape.
_SWITCHER_RE = re.compile(r"^(?:Dansk|Deutsch|English|Españ|Franç|Italiano|日本語|"
                          r"Nederlands|Norsk|Polski|Portugu|Svenska){2,}", re.U)


def _is_switcher(line):
    return (len(line) <= 3 and line.isupper()) or (" " not in line and bool(_SWITCHER_RE.match(line)))


def _lang_key(row):
    la = (row.get("lang") or "").strip().lower()[:2]
    if la:
        return la
    m = re.match(r"https?://[^/]+/([a-z]{2})/", row["url"])
    return m.group(1) if m else "en"


def deboilerplate(rows, say=None):
    """Remove site chrome by REPETITION, per language. Mutates each row's body, then re-derives
    word_count and body_status from the result. Returns the number of chrome lines removed."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[_lang_key(r)].append(r)
    total_removed = 0
    for la, grp in sorted(groups.items()):
        if len(grp) < settings.DEBOILER_MIN_PAGES:
            continue
        freq = collections.Counter()
        for r in grp:
            for ln in set(_lines(r["body"])):
                freq[ln] += 1
        cutoff = max(5, int(settings.DEBOILER_FRAC * len(grp)))
        boiler = frozenset(ln for ln, c in freq.items() if c >= cutoff)
        for r in grp:
            kept = [ln for ln in _lines(r["body"]) if ln not in boiler and not _is_switcher(ln)]
            r["body"] = tidy("\n".join(kept))
        total_removed += len(boiler)
        if say and boiler:
            say("Removed the repeated menu and footer lines", "%d lines shared by the %s pages" % (len(boiler), la))
    for r in rows:                                        # re-derive from the cleaned body
        r["word_count"] = _plain_words(r["body"])
        if r["body_status"] in ("ok", "stub", "flagged"):
            r["body_status"] = status_of(r["body"], r["extractor"])
    return total_removed


def run(fx, site, say, reconciled):
    pages = reconciled["pages"]
    rest = rest_bodies(fx, pages)
    say("Extracting the text", "%d pages, offline from the saved copies; the site's own text for %d of them"
        % (len(pages), len(rest)))

    rows = []
    for i, (url, rec) in enumerate(pages.items(), 1):
        # OFFLINE by contract — reconcile already fetched every page into the raw cache, so read the
        # CACHE, never the network. A page absent from the cache is one reconcile could not get; its
        # body_status records that.
        r = fx.cached(url)
        live = (r.content if r and r.status == 200 and "html" in (r.content_type or "").lower() else None)
        try:
            row = extract_one(url, rec, live, rest.get(url))
        except Exception as e:                        # a broken page must not kill the run
            row = _row(url, rec, "", "error:%s" % type(e).__name__, rec.get("title", ""),
                       rec.get("description", ""), "")
        rows.append(row)
        if i % 200 == 0:
            say("Still extracting", "%d of %d pages" % (i, len(pages)))

    # STAGE 2 — de-boilerplate the whole site, per language (the one cleaning step)
    deboilerplate(rows, say)

    # flag pages whose body is far below their type's median (a single global % hides this)
    lens = {}
    for row in rows:
        if row["body_status"] in ("ok", "stub"):
            lens.setdefault(row["type"], []).append(len(row["body"]))
    med = {t: (statistics.median(v) if v else 0) for t, v in lens.items()}
    for row in rows:
        m = med.get(row["type"], 0)
        if row["body_status"] == "ok" and m and len(row["body"]) < settings.FLAG_MEDIAN_FRAC * m:
            row["body_status"] = "flagged"

    rows.sort(key=lambda r: r["url"])
    store.write_json(os.path.join(site["work"], "extracted.json"), {"domain": site["host"], "rows": rows})
    n = collections.Counter(r["body_status"] for r in rows)
    say("Extracted the text", "%d pages read well, %d short, %d flagged as thin, %d with no readable text"
        % (n.get("ok", 0), n.get("stub", 0), n.get("flagged", 0), n.get("failed", 0)))
    return rows
