"""learn_voice.py — work out how this company writes, once, from their own pages.

Every article the agent writes is written in this voice, so the alternative to running
this is asking the model to invent a tone per article, which drifts between drafts and
reads like a different company each time. Learned once, saved to knowledge, and loaded
into the system prompt by loop.py from then on.

The longest pages are sampled, not the first ones. A nav-heavy landing page or a contact
page tells you almost nothing about how someone writes; a 1200-word guide does. Length
is the cheapest available proxy for "real prose".

The prompt is prompts/learn_voice.md, like every other prompt here, so the wording can
be tuned without touching this file.

The examples field matters more than it looks. Traits like "direct" and "warm" mean
different things to different models, but two real sentences lifted from the site pin
the voice to something concrete that a writer can imitate.
"""
import json

from .. import llm
from .. import store
from . import _shared as sh

SAMPLE_CHARS = 1200          # per page, so eight pages stay inside a comfortable prompt

def _pages_block(pages):
    parts = []
    for i, p in enumerate(pages, 1):
        parts.append(
            "--- Page %d: %s ---\nTitle: %s\nH1: %s\nMeta: %s\nWords: %d\nText: %s"
            % (i, p.get("url", ""), p.get("title", ""), p.get("h1", ""),
               p.get("description", ""), p.get("word_count", 0),
               (p.get("text") or "")[:SAMPLE_CHARS])
        )
    return "\n\n".join(parts)


def _strings(value, limit):
    """The model sometimes returns a comma string where a list was asked for. Normalise
    rather than saving a shape the rest of the app cannot read."""
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def run(ctx, sample_pages=8):
    say = sh.reporter(ctx, "learn_voice")
    sample_pages = max(1, int(sample_pages or 8))

    index = store.knowledge("site_index.json")
    if not index or not index.get("pages"):
        raise RuntimeError(
            "There is no site index yet. Run index_site first, then learn_voice."
        )

    # Sort by real prose, then take the top N. Pages with no text at all are useless here.
    pages = [p for p in index["pages"] if (p.get("text") or "").strip()]
    pages.sort(key=lambda p: p.get("word_count", 0), reverse=True)
    sample = pages[:sample_pages]
    if not sample:
        if index.get("crawl_blocked"):
            raise RuntimeError(
                "The site refused the crawl (%s), so the index has %d pages from search data "
                "but no page text, and a voice cannot be learned from titles. Ask the user to "
                "allow the crawler on their site, or to paste two or three of their pages into "
                "the chat, and try again." % (str(index["crawl_blocked"])[:120], len(index["pages"])))
        raise RuntimeError("The site index has %d pages but none of them carry any text."
                           % len(index["pages"]))

    say("Picked the pages", "%d longest pages, %d to %d words"
        % (len(sample), sample[-1].get("word_count", 0), sample[0].get("word_count", 0)))

    domain = index.get("domain") or "this site"
    prompt = sh.fill(sh.load_prompt("learn_voice"),
                     count=len(sample), domain=domain, pages=_pages_block(sample))

    data = llm.json_call(prompt)
    if not isinstance(data, dict) or not data.get("summary"):
        raise RuntimeError("The model did not return a usable voice profile:\n"
                           + json.dumps(data)[:400])

    voice = {
        "company": (data.get("company") or domain).strip(),
        "what_they_sell": (data.get("what_they_sell") or "").strip(),
        "who_buys": (data.get("who_buys") or "").strip(),
        "summary": data["summary"].strip(),
        "traits": _strings(data.get("traits"), 8),
        "avoid": _strings(data.get("avoid"), 20),
        "examples": _strings(data.get("examples"), 3),
        "domain": domain,
        "sampled_urls": [p.get("url") for p in sample],
        "learned_at": store.now(),
    }
    say("Heard the voice",
        "%s: %s" % (voice["company"], ", ".join(voice["traits"]) or "no traits given"))

    store.save_knowledge("brand_voice.json", voice)
    return {"summary": "Learned the voice from %d pages" % len(sample)}
