"""build_page_index.py — embed every page we own, once, so links are found by meaning.

The tool wrapper around _index.build(). Reads the page bodies the crawl saved, hands
them to Voyage, and writes the two-vector index into knowledge/content-index. Rebuild
only when the site changes; a re-run with nothing new embeds nothing.

Without this index the internal-link pass cannot run: it would be back to matching a
section heading against page titles by shared words, which is exactly the failure the
workflow measured and threw out ("work sample test" linked to a job-simulation page).
"""
from .. import store
from . import _index
from . import _shared as sh
from . import voyage


def run(ctx, rebuild=False):
    say = sh.reporter(ctx, "build_page_index")
    if not voyage.available():
        return {"summary": "No Voyage key, so the page index was not built.",
                "error": ("A Voyage API key is needed to embed the pages (free tier at "
                          "voyageai.com). Ask the user to add it in Connections, then run "
                          "this again. Internal links are placed by title-word overlap until then.")}
    pages = sh.pages_with_bodies()
    if not pages:
        idx = store.knowledge("site_index.json") or {}
        if idx.get("crawl_blocked"):
            return {"summary": "The site refused the crawl, so there is no page text to embed.",
                    "error": ("The index has %d pages from search data but none of their text, "
                              "and an embedding of a title alone is what this replaces. Ask the "
                              "user to allow the crawler, then re-run index_site and this."
                              % len(idx.get("pages") or []))}
        return {"summary": "No page text on file.",
                "error": "Run index_site first; this embeds the pages it read."}
    before = _index.status()
    say("Reading the site catalogue", "%d pages with text" % len(pages))
    stamp = _index.build(pages, say=say, reindex=bool(rebuild))
    say("Page index ready", "%d pages, %d passages" % (stamp["pages"], stamp["chunks"]))
    fresh = stamp["chunks"] - (before.get("chunks") or 0) if before.get("built") and not rebuild else stamp["chunks"]
    return {"summary": "%d pages embedded (%d passages%s)"
                       % (stamp["pages"], stamp["chunks"],
                          ", %d new" % fresh if before.get("built") and not rebuild else ""),
            "pages": stamp["pages"], "chunks": stamp["chunks"]}
