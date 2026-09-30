"""sync.py — what to fetch, how often, and how it becomes rows in db.py.

Three independent pulls, run on the cadence the design settled on:
  daily()    Position Tracking landing-pages rollup: the scheduled, keyword-tracked
             view of each blog URL. Cheapest per-call, run most often.
  weekly()   url_organic per blog: catches keywords a post has newly started ranking
             for that are not yet in the Position Tracking campaign's keyword list.
  monthly()  backlinks per blog: link velocity is slow, so this is the one pull that
             does not need daily or weekly freshness.

Every pull is READ Semrush THEN WRITE db.py, one blog at a time, and a failure on one
blog (a 404, a redirected URL, a temporarily unreachable API) is caught and recorded
rather than aborting the whole run -- see _run_one. Idempotent throughout: db.insert_snapshot
upserts on (blog_id, date, source), so a sync that is re-run for a day it already
covered corrects that day's numbers instead of adding a second row.
"""
import time
import traceback

from . import client, db
from .. import store

SOURCE_POSITION_TRACKING = "position_tracking"
SOURCE_URL_ORGANIC = "url_organic"
SOURCE_BACKLINKS = "backlinks"

TESTLIFY_DOMAIN = "testlify.com"


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


# ---- onboarding: populate blog rows from what the app already knows -------------------
# Semrush has no idea which URLs on testlify.com are blogs, or which of those the SEO
# Writer produced. Two sources, both already in this app:
#   * knowledge/site_index.json  -- every crawled page, including every blog path.
#   * store.library_list()       -- every article the SEO Writer itself finished.
# A URL is classified SEO_WRITER only when it can be tied to a Library item; that tie
# is a HEURISTIC (slug match between the Library title and the URL's last path
# segment), because nothing today records "this Library item became THIS live URL"
# (see the repo inspection this integration's design ran on: no publish-to-URL field
# exists anywhere yet). A heuristic match is a starting classification, not a proof --
# the caller can always override it by hand via db.upsert_blog with an explicit
# generated_by_seo_writer value, and this function never re-classifies a blog that
# already has one (it only fills in blogs it has not seen before).

def _slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _blog_pages_from_site_index():
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    out = []
    for p in pages or []:
        url = p.get("url") or ""
        if TESTLIFY_DOMAIN not in url:
            continue
        if p.get("type") == "blog" or "/blog/" in url:
            out.append(p)
    return out


def discover_blogs():
    """Upsert one blog row per crawled blog page not already tracked, classifying by
    the slug heuristic above. Returns {"added": n, "skipped_existing": n}."""
    pages = _blog_pages_from_site_index()
    library = {item["id"]: item for item in store.library_list()}
    slug_to_item = {_slug(item.get("title", "")): item for item in library.values()
                    if item.get("title") and item.get("status") == "ready"}

    added = skipped = 0
    for p in pages:
        url = (p.get("url") or "").strip()
        if not url:
            continue
        if db.get_blog_by_url(url):
            skipped += 1
            continue
        path_slug = _slug(url.rstrip("/").rsplit("/", 1)[-1])
        matched = slug_to_item.get(path_slug)
        fields = {
            "url": url, "title": p.get("title") or "",
            "published_at": (p.get("modified") or "")[:10] or None,
            "word_count": p.get("word_count"),
            "generated_by_seo_writer": 1 if matched else 0,
            "status": "active",
        }
        if matched:
            fields["library_item_id"] = matched["id"]
            fields["seo_writer_version"] = ""
        db.upsert_blog(fields)
        added += 1
    return {"added": added, "skipped_existing": skipped}


# ---- the three pulls --------------------------------------------------------------------

def _run_one(fn, blog, errors):
    try:
        fn(blog)
    except client.NoCredentials:
        raise               # no point continuing the loop with no key at all
    except Exception as e:  # noqa: BLE001 -- one blog's failure (404, redirect, timeout)
        errors.append({"blog_id": blog["id"], "url": blog["url"],
                       "error": str(e)[:300], "trace": traceback.format_exc()[-800:]})


def daily():
    """Position Tracking landing-pages rollup, joined back onto our own blog rows by
    URL. A landing page Semrush reports that we do not track is skipped, not
    invented into a new row -- discover_blogs() is the only door that creates blogs."""
    blogs = {b["url"]: b for b in db.list_blogs(limit=100000)}
    errors = []
    by_project = {}
    for b in blogs.values():
        by_project.setdefault(b.get("pt_project_id"), []).append(b)
    for project_id, project_blogs in by_project.items():
        if not project_id:
            continue
        try:
            rows = client.pt_landing_pages(project_id)
        except client.NoCredentials:
            return {"ok": False, "reason": "no_credentials"}
        except Exception as e:  # noqa: BLE001
            errors.append({"project_id": project_id, "error": str(e)[:300]})
            continue
        d = today()
        for row in rows:
            blog = blogs.get(row.get("url"))
            if not blog:
                continue
            db.insert_snapshot(blog["id"], d, SOURCE_POSITION_TRACKING,
                              organic_keywords=row["keywords_count"],
                              top3_keywords=row["top3"], top10_keywords=row["top10"],
                              top20_keywords=row["top20"],
                              average_position=row["average_position"],
                              estimated_traffic=row["estimated_traffic"],
                              visibility=row["visibility"])
    return {"ok": True, "errors": errors}


def weekly():
    """url_organic per blog: what each blog ranks for right now, independent of
    whether it is in a Position Tracking campaign's keyword list yet."""
    blogs = db.list_blogs(limit=100000)
    errors = []
    d = today()

    def pull(blog):
        rows = client.url_organic(blog["url"])
        top3 = sum(1 for r in rows if r["position"] and r["position"] <= 3)
        top10 = sum(1 for r in rows if r["position"] and r["position"] <= 10)
        top20 = sum(1 for r in rows if r["position"] and r["position"] <= 20)
        positions = [r["position"] for r in rows if r["position"]]
        avg_pos = round(sum(positions) / len(positions), 1) if positions else None
        db.insert_snapshot(blog["id"], d, SOURCE_URL_ORGANIC,
                          organic_keywords=len(rows), top3_keywords=top3,
                          top10_keywords=top10, top20_keywords=top20,
                          average_position=avg_pos)

    for blog in blogs:
        _run_one(pull, blog, errors)
        if errors and errors[-1].get("error") == "no_credentials":
            break
    return {"ok": True, "count": len(blogs), "errors": errors}


def monthly():
    """Backlinks per blog. Slowest-moving metric, cheapest to under-poll."""
    blogs = db.list_blogs(limit=100000)
    errors = []
    d = today()

    def pull(blog):
        bl = client.backlinks_for_url(blog["url"])
        db.insert_snapshot(blog["id"], d, SOURCE_BACKLINKS,
                          backlinks=bl["backlinks"], referring_domains=bl["referring_domains"])

    for blog in blogs:
        _run_one(pull, blog, errors)
    return {"ok": True, "count": len(blogs), "errors": errors}


MODES = {"daily": daily, "weekly": weekly, "monthly": monthly, "discover": discover_blogs}


def run(mode):
    db.init_db()
    fn = MODES.get(mode)
    if not fn:
        raise ValueError("unknown sync mode %r -- one of: %s" % (mode, ", ".join(MODES)))
    return fn()
