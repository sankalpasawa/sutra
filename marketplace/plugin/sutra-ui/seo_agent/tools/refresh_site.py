"""refresh_site.py — bring the catalogue up to date without re-reading the whole site.

A first read of a site the size of testlify.com takes about three hours, because every page is
fetched. Nobody will do that to pick up nine new blog posts, so in practice the catalogue goes
stale and every later step quietly works from last month's site.

This does the cheap part properly:

    1. Ask the finders again for the site's CURRENT list of addresses. This costs no page fetches:
       the CMS answers in a few calls and a sitemap is one file per sitemap.
    2. Compare that list against the catalogue we hold. Three piles fall out.
         NEW   in the site now, not in the catalogue
         GONE  in the catalogue, not on the site any more
         CHANGED  in both, but the site says the page moved on since we read it
    3. Touch only those. Fetch the new and changed ones, drop the gone ones, pull traffic for the
       new ones in one bulk call, and re-embed only what moved.

**How CHANGED is decided, and what it cannot see.** A list of addresses cannot tell you that
somebody rewrote a page: the address is identical either way. Two signals are used, in order:

    - the sitemap's own last-modified date, compared against when we last fetched that page.
      Exact, free, and available for 5,192 of testlify.com's 11,656 sitemap entries.
    - nothing. For a page with no date there is no cheap way to know, so it is reported as
      UNCHECKED rather than assumed fresh. `include_unchecked=True` re-reads those too, which
      costs a fetch each; the honest default is to say how many there are and let the person
      decide.

The web archive is skipped by default. It exists to find pages that USED to exist, which is a
first-read problem, and its liveness probing is the slowest part of a full read.

Reads: the catalogue and the fetch cache. Writes: the updated catalogue, and a change report.
"""
import os
import time

from .. import store
from ..foundation import (enumerate_sitemap, enumerate_wp, extract, fetch as fetchmod,
                          reconcile, urls)
from ..foundation import traffic as trafficmod
from . import _shared as sh

try:
    from . import dfs
except ImportError:  # noqa: F401 - dfs is optional
    dfs = None

SAMPLE = 12          # how many addresses of each kind the report shows by name


def _norm(u):
    return (u or "").rstrip("/")


def _fetched_at(fx, url):
    """When we last fetched this page, as a unix time, or None."""
    row = fx.db("SELECT fetched_at FROM pages WHERE url=?", (url,), fetch="one")
    return row[0] if row and row[0] else None


def _parse_lastmod(s):
    """A sitemap date to unix time. Sitemaps use ISO 8601, with or without a timezone."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            import datetime as _dt
            d = _dt.datetime.strptime(s.replace("+00:00", "+0000"), fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=_dt.timezone.utc)
            return d.timestamp()
        except ValueError:
            continue
    return None


def survey(ctx, say=None, use_archive=False):
    """What has changed, without changing anything. This is what the preview shows."""
    say = say or sh.reporter(ctx, "refresh_site")
    idx = store.knowledge("site_index.json") or {}
    known_pages = idx.get("pages") or []
    if not known_pages:
        return {"error": "There is no catalogue to refresh yet. Read the site first."}
    host = idx.get("domain") or sh.company().get("domain") or ""
    root = "https://" + host
    work = os.path.join(store.knowledge_dir(), "_work")
    raw = os.path.join(store.knowledge_dir(), "_raw")
    fx = fetchmod.Fetcher(work, raw, on_event=say)
    site = {"root": root, "host": host, "work": work, "raw": raw, "max_pages": 0,
            "force_crawl": False, "wordpress_url": sh.company().get("wordpress_url") or ""}

    say("Asking the site for its current list", "no pages are read yet, only their addresses")
    current, lastmod, asked = {}, {}, set()
    wp = enumerate_wp.run(fx, site, say)
    if not wp.get("skipped"):
        asked.add("wp")
        for u in (wp.get("urls") or {}):
            current[_norm(u)] = "the site's own list"
    sm = enumerate_sitemap.run(fx, site, say)
    if sm.get("urls"):
        asked.add("sitemap")
    for u, meta in (sm.get("urls") or {}).items():
        current.setdefault(_norm(u), "the sitemap")
        if isinstance(meta, dict) and meta.get("lastmod"):
            lastmod[_norm(u)] = meta["lastmod"]
    if use_archive:
        from ..foundation import enumerate_archive
        ar = enumerate_archive.run(fx, site, say)
        if ar.get("urls"):
            asked.add("archive")
        for u in (ar.get("urls") or {}):
            current.setdefault(_norm(u), "the web archive")
    say("The site lists %s now" % sh.plural(len(current), "page"),
        "%d of them carry a last-changed date" % len(lastmod))

    known = {_norm(p.get("url")): p for p in known_pages if p.get("url")}
    new = [u for u in current if u not in known]
    # A page is only "gone" if a source we JUST asked used to list it and no longer does. Found
    # 2026-09-09 on the first live preview: 662 pages were reported gone, and every one of them
    # had come from the web archive alone. They are live and readable; the sitemap simply never
    # listed them. Deleting them would have silently cut 662 real pages out of Knowledge.
    gone, unjudged = [], []
    for u, p in known.items():
        if u in current:
            continue
        srcs = {x.strip() for x in (p.get("source") or "").replace("+", " ").split() if x.strip()}
        if srcs & asked:
            gone.append(u)
        else:
            unjudged.append(u)
    if unjudged:
        say("Left %s alone" % sh.plural(len(unjudged), "page"),
            "they were found by a source this check did not ask (usually the web archive), so "
            "their absence from the sitemap proves nothing")

    changed, unchecked = [], []
    both = [u for u in current if u in known]
    for u in both:
        lm = _parse_lastmod(lastmod.get(u))
        if lm is None:
            unchecked.append(u)
            continue
        got = _fetched_at(fx, u) or _fetched_at(fx, u + "/")
        if got is None or lm > got:
            changed.append(u)
    say("Compared it against what we hold",
        "%d new, %d gone, %d changed, %d we cannot check cheaply"
        % (len(new), len(gone), len(changed), len(unchecked)))
    return {"host": host, "root": root, "current": current, "lastmod": lastmod, "asked": sorted(asked),
            "new": sorted(new), "gone": sorted(gone), "changed": sorted(changed),
            "unchecked": sorted(unchecked), "unjudged": sorted(unjudged), "known_count": len(known),
            "titles": {u: (known[u].get("title") or "") for u in gone[:SAMPLE]}}


def _report(s, did=None):
    """The change summary a person reads. Plain English, real addresses."""
    did = did or {}
    def names(urls, n=SAMPLE):
        rows = ["- %s" % u for u in urls[:n]]
        if len(urls) > n:
            rows.append("- and %d more" % (len(urls) - n))
        return "\n".join(rows) or "- (none)"
    parts = ["# What changed on %s" % s["host"], ""]
    if did:
        parts.append("Checked %s. Read %s, removed %s, re-read %s."
                     % (sh.plural(len(s["current"]), "address", "addresses"), sh.plural(did.get("added", 0), "new page"),
                        sh.plural(did.get("removed", 0), "page"), sh.plural(did.get("rebuilt", 0), "changed page")))
    else:
        parts.append("Nothing has been changed yet. This is what a refresh would do.")
    parts += ["", "## New pages (%d)" % len(s["new"]), names(s["new"]),
              "", "## Pages that are gone (%d)" % len(s["gone"]), names(s["gone"]),
              "", "## Pages that changed since we read them (%d)" % len(s["changed"]), names(s["changed"])]
    if s["unchecked"]:
        parts += ["", "## Could not be checked cheaply (%d)" % len(s["unchecked"]),
                  "These pages give no last-changed date, so the only way to know is to read them "
                  "again. They were left alone. Refresh with \"read the unchecked pages too\" to "
                  "include them."]
    if did.get("traffic"):
        parts += ["", "## Traffic", did["traffic"]]
    return "\n".join(parts)


def run(ctx, preview=False, include_unchecked=False, use_archive=False, redo_traffic=True):
    """Refresh the catalogue. `preview=True` reports what would change and touches nothing."""
    say = sh.reporter(ctx, "refresh_site")
    s = survey(ctx, say=say, use_archive=use_archive)
    if s.get("error"):
        return {"summary": "Nothing to refresh.", "error": s["error"]}

    todo = list(s["new"]) + list(s["changed"]) + (list(s["unchecked"]) if include_unchecked else [])
    if preview:
        store.save_knowledge("_work/refresh-preview.json", s)
        return {"summary": "%d new, %d gone, %d changed%s. Nothing has been changed yet."
                           % (len(s["new"]), len(s["gone"]), len(s["changed"]),
                              ", %d unchecked" % len(s["unchecked"]) if s["unchecked"] else ""),
                "preview": True, "new": len(s["new"]), "gone": len(s["gone"]),
                "changed": len(s["changed"]), "unchecked": len(s["unchecked"]),
                "report": _report(s)}

    if not todo and not s["gone"]:
        store.save_knowledge("catalogue-changes.md", _report(s, {"added": 0, "removed": 0, "rebuilt": 0}))
        return {"summary": "Nothing has changed since the last read.", "added": 0, "removed": 0,
                "rebuilt": 0, "artifact": "catalogue-changes.md"}

    work = os.path.join(store.knowledge_dir(), "_work")
    raw = os.path.join(store.knowledge_dir(), "_raw")
    fx = fetchmod.Fetcher(work, raw, on_event=say)
    site = {"root": s["root"], "host": s["host"], "work": work, "raw": raw, "max_pages": 0,
            "force_crawl": False, "wordpress_url": sh.company().get("wordpress_url") or ""}

    rows = []
    if todo:
        say("Reading %s" % sh.plural(len(todo), "page"),
            "only the ones that are new or have changed; the other %d are left alone"
            % max(0, s["known_count"] - len(todo)))
        # extract works offline from the saved copies, so the new pages have to be fetched first.
        # This is the only expensive part of a refresh, and it is exactly len(todo) fetches.
        pages = {u: {"url": u, "sources": {"sitemap"}} for u in todo}
        verdict = reconcile._fetch_pass(fx, site, pages, say)
        rec = {"domain": s["host"], "pages": pages}
        rows = extract.run(fx, site, say, rec) or []
        # A row exists for every page asked for, whether or not the page could be read. Counting
        # rows and calling it "read" is a lie, and it put 584 empty pages into the catalogue on
        # the first live run (2026-09-09) while reporting "584 of 584 came back with text".
        good = [r for r in rows if (r.get("body") or "").strip() and r.get("body_status") != "failed"]
        say("Read them", "%d of %d came back with text" % (len(good), len(todo)))
        if not good:
            return {"summary": "Nothing was added: not one of the %d pages could be read." % len(todo),
                    "error": ("The site refused every page (%s). Nothing was changed, so the "
                              "catalogue is exactly as it was. Try again in a few minutes."
                              % (verdict.get("site_blocked") or "no page came back with text")),
                    "added": 0, "removed": 0, "rebuilt": 0}
        if len(good) < len(todo) / 2:
            say("Most pages could not be read",
                "%d of %d failed; only the ones that were read are added, the rest stay pending "
                "for the next refresh" % (len(todo) - len(good), len(todo)))
        rows = good

    idx = store.knowledge("site_index.json") or {}
    known = {_norm(p.get("url")): p for p in (idx.get("pages") or []) if p.get("url")}
    from .index_site import _light_row
    added = rebuilt = 0
    for r in rows:
        u = _norm(r.get("url"))
        if not u:
            continue
        light = _light_row(r)
        # a refreshed page keeps the traffic it already had until the next pull replaces it
        if u in known:
            for k in ("traffic", "traffic_clean", "top_keyword", "intent", "position", "keyword_volume"):
                if known[u].get(k) and not light.get(k):
                    light[k] = known[u][k]
            rebuilt += 1
        else:
            added += 1
        known[u] = light
    removed = 0
    for u in s["gone"]:
        if known.pop(u, None) is not None:
            removed += 1

    traffic_note = ""
    if redo_traffic and added and dfs is not None and sh.dfs_mode(dfs) == "live":
        try:
            tr = trafficmod.run(site, say, list(known.values()))
            rows_out = tr.get("top_pages") or []
            # Only replace what is on file if the pull actually returned something. Found
            # 2026-09-09: the pull skipped (balance below the floor), returned an empty list, and
            # this overwrote 2,254 imported rows with nothing.
            if rows_out:
                store.save_knowledge("top-pages.json", rows_out)
                traffic_note = "Pulled fresh traffic for the whole catalogue."
            else:
                traffic_note = ("The traffic pull returned nothing, so the traffic already on file "
                                "was kept: %s" % ((tr.get("meta") or {}).get("skipped") or "no reason given"))
        except Exception as e:  # noqa: BLE001 — a failed pull must not lose the pages we just read
            traffic_note = "The traffic pull did not run: %s" % str(e)[:140]
            say("Traffic was not pulled", traffic_note)
    elif added:
        traffic_note = ("No traffic was pulled: DataForSEO is not connected, so the new pages carry "
                        "no traffic figure until it is.")

    pages = sorted(known.values(), key=lambda p: p.get("url") or "")
    # A refresh fetches and extracts directly, so it never runs reconcile's own inference pass and
    # every page it added arrived with no type at all. Found 2026-09-09 on the first live refresh:
    # 584 untyped pages went into the catalogue, out of reach of every builder that picks pages by
    # type. One call over the merged set, which also repairs any language-typed row already there.
    retyped, _was = reconcile.retype_catalogue(pages)
    if retyped:
        say("Filed the pages by kind", "%d pages had no kind on record, or had a language where "
                                      "their kind should be" % retyped)
    idx["pages"] = pages
    idx["page_count"] = len(pages)
    idx["indexed_at"] = store.now()
    idx["last_refreshed_at"] = store.now()
    store.save_knowledge("site_index.json", idx)

    # the body store the brand builders read
    if rows:
        import json
        existing = {}
        for line in (store.knowledge("content-database.jsonl") or "").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    existing[_norm(d.get("url"))] = d
                except ValueError:
                    continue
        for r in rows:
            existing[_norm(r.get("url"))] = {"url": r["url"], "type": r.get("type", ""),
                                             "title": r.get("title", ""), "body": r.get("body", "")}
        for u in s["gone"]:
            existing.pop(u, None)
        store.save_knowledge("content-database.jsonl", "".join(
            json.dumps(v, ensure_ascii=False) + "\n" for v in existing.values()))

    say("Catalogue updated", "%d added, %d removed, %d re-read; %d pages now"
        % (added, removed, rebuilt, len(pages)))
    report = _report(s, {"added": added, "removed": removed, "rebuilt": rebuilt, "traffic": traffic_note})
    store.save_knowledge("catalogue-changes.md", report)

    out = {"summary": "%s added, %s removed, %s re-read. The catalogue is %s."
                      % (sh.plural(added, "page"), sh.plural(removed, "page"),
                         sh.plural(rebuilt, "page"), sh.plural(len(pages), "page")),
           "added": added, "removed": removed, "rebuilt": rebuilt, "pages": len(pages),
           "unchecked": len(s["unchecked"]), "artifact": "catalogue-changes.md"}
    if traffic_note:
        out["note"] = traffic_note
    if added or rebuilt or removed:
        out["note"] = (out.get("note", "") + " The page index needs rebuilding so the new pages can "
                       "be found by meaning; run build_page_index.").strip()
    return out
