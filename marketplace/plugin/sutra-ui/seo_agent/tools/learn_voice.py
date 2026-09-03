"""learn_voice.py — a thin alias for the brand-voice builder, kept so older callers still work.

The voice used to be an eight-page sample and one model call. It is now built by the brand-voice
builder (brand/brand_voice.py, the port of the workflow's 1-brand-voice): a shortlist of the
company's real voice pages, one evidence row per page, the brand-voice.md document assembled from
that evidence, and a quality gate. This file runs that builder and ALSO writes the flat profile the
rest of the app reads, knowledge/brand_voice.json {company, summary, traits, avoid, examples,
what_they_sell, who_buys}, derived by code from brand-voice.md, so loop._system_prompt and
_shared.voice_block keep working unchanged.

`sample_pages` is accepted for the old callers and ignored: the builder picks its own pages.
"""
from .. import store
from ..brand import brand_voice
from . import _shared as sh


def run(ctx, sample_pages=8, redo=False):
    say = sh.reporter(ctx, "learn_voice")
    index = store.knowledge("site_index.json")
    if not index or not index.get("pages"):
        raise RuntimeError("There is no site index yet. Run index_site first, then learn_voice.")
    bodies = sh.page_bodies()
    has_text = any((p.get("text") or p.get("body") or bodies.get((p.get("url") or "").rstrip("/")) or "").strip()
                   for p in index["pages"])
    if not has_text:
        if index.get("crawl_blocked"):
            raise RuntimeError(
                "The site refused the crawl (%s), so the index has %d pages from search data "
                "but no page text, and a voice cannot be learned from titles. Ask the user to "
                "allow the crawler on their site, or to paste two or three of their pages into "
                "the chat, and try again." % (str(index["crawl_blocked"])[:120], len(index["pages"])))
        raise RuntimeError("The site index has %d pages but none of them carry any text." % len(index["pages"]))

    co = sh.company()
    out = brand_voice.run(co, say, redo=bool(redo))
    co = sh.company()                      # the builder may have filled the one-liner and niche
    voice = brand_voice.profile(co)
    store.save_knowledge("brand_voice.json", voice)
    say("Heard the voice", "%s: %s" % (voice["company"], ", ".join(voice["traits"]) or "no pillars named"))
    return {"summary": "Learned the voice from the company's own pages (brand/brand-voice.md)",
            "files": ["brand-voice.md", "page-shortlist.md", "brand_voice.json"],
            "needs_review": out.get("needs_review") or [], "artifact": None}
