"""refresh_site.py — bring the catalogue up to date without re-reading the whole site.

A first read of a site the size of testlify.com takes about three hours, because every page is
fetched. Nobody will do that to pick up nine new blog posts, so in practice the catalogue goes
stale and every later step quietly works from last month's site.

This does the cheap part properly:

    1. Ask the finders again for the site's CURRENT list of addresses. This costs no page fetches:
       the CMS answers in a few calls and a sitemap is one file per sitemap.
    2. Compare that list against the catalogue we hold. Four piles fall out.
         NEW   in the site now, not in the catalogue, and never judged before
         GONE  in the catalogue, and every source that found it was asked again and dropped it
         CHANGED  in both, but the site says the page moved on since we read it
         JUDGED  in the site's list, but the last full read looked at it and threw it away (a
                 dead page, an empty template, a duplicate address, a machine path). Not new.
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

**What GONE is allowed to mean.** Only this: every source that found the page was asked again,
each of those answers was complete, and none of them lists it now. Two ways that goes wrong, both
of which delete real pages, so both are refused. A source we did not ask (usually the web archive,
or the link crawl, which a refresh never runs) proves nothing by its silence. And a source that
FAILED — a sitemap that answered HTTP 500, a challenge page, a content type whose endpoint broke —
is not a source that said "gone", it is a source that said nothing; on a site with a dozen child
sitemaps one of them failing would otherwise report hundreds of live pages as deleted.

The web archive is skipped by default. It exists to find pages that USED to exist, which is a
first-read problem, and its liveness probing is the slowest part of a full read.

Reads: the catalogue and the fetch cache. Writes: the updated catalogue, and a change report.
"""
import os
import time
import urllib.parse as _up

from bs4 import BeautifulSoup

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


def _moved_since_we_judged(fx, url, lastmod_raw):
    """Does the site say this address changed since we last fetched it?

    The one way an address the last read judged and dropped may come back: the sitemap gives it a
    last-changed date NEWER than the moment we fetched it and threw it away. Same test `changed`
    uses, so a dropped page and a kept page are judged by the same evidence. An address we never
    fetched (a machine path, a robots-disallowed page) has no fetch time and can never re-enter
    this way — being listed again is not news about it.
    """
    lm = _parse_lastmod(lastmod_raw)
    if lm is None:
        return False
    got = _fetched_at(fx, url) or _fetched_at(fx, url + "/")
    return got is not None and lm > got


# What the last full read looked at and threw away, and why — in the person's words. `unread` is
# deliberately NOT here: those are real pages a page cap stopped us reading, so a refresh SHOULD
# read them. Everything else in this list is a verdict, not a gap.
JUDGED_BUCKETS = (("dead", "the page was gone when we read it"),
                  ("soft_404", "an empty template, not a page"),
                  ("offsite", "it leads off the site"),
                  ("robots", "robots.txt does not allow reading it"),
                  ("non_content", "a machine path, not a page"))


def _already_judged(work):
    """{address: why} for every address the last full read dropped. Empty when there is no
    reconciled.json (an older catalogue, or one built by the search-data fallback)."""
    rec = store.read_json(os.path.join(work, "reconciled.json")) or {}
    dropped = rec.get("dropped") or {}
    judged = {}
    for bucket, why in JUDGED_BUCKETS:
        for u in dropped.get(bucket) or []:
            judged.setdefault(_norm(u), why)
    for u, target in (dropped.get("collapsed") or {}).items():
        judged.setdefault(_norm(u), "the same page as %s, under another address" % target)
    return judged


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
    # The FULL read's sitemap answer: which sitemap file listed each URL when the catalogue was
    # built. That is what lets a page be judged against the one file that is supposed to list it,
    # rather than against "the sitemaps" as a lump. It is only ever read here, never written: a
    # refresh writes its own listings to _work/refresh/ so that a survey — which can catch the
    # site on a bad day — can never overwrite what the full read established.
    sm_before = store.read_json(os.path.join(work, "urls-sitemap.json")) or {}
    swork = os.path.join(work, "refresh")
    os.makedirs(swork, exist_ok=True)
    fx = fetchmod.Fetcher(work, raw, on_event=say)
    # Every listing this survey reads must come from the SITE, not from the copy the first read
    # saved. A sitemap served from the cache is last week's sitemap: it carries last week's URLs
    # and last week's lastmod dates, so the comparison below is the catalogue against itself and
    # the honest answer is always "nothing has changed". Found 2026-09-10. The listings are a
    # handful of files, which is the whole reason a refresh is cheap.
    fx.always_refetch = True
    site = {"root": root, "host": host, "work": swork, "raw": raw, "max_pages": 0,
            "force_crawl": False, "wordpress_url": sh.company().get("wordpress_url") or ""}

    say("Asking the site for its current list", "no pages are read yet, only their addresses")
    # `asked` is the sources this check actually put a question to. Being in here is necessary for
    # a "gone" verdict and not sufficient: whether a source answered FOR A GIVEN PAGE is decided
    # per page, further down. A source that answered only in part still ADDS everything it did
    # find — finding a page needs one source to see it; losing a page needs every source that
    # found it to have looked again and not seen it.
    current, lastmod, asked, partial = {}, {}, set(), {}
    wp = enumerate_wp.run(fx, site, say)
    if not wp.get("skipped"):
        asked.add("wp")
        for u in (wp.get("urls") or {}):
            current[_norm(u)] = "the site's own list"
        broke = sorted(wp.get("unavailable") or {})
        if broke or wp.get("blocked"):
            partial["wp"] = ("the content system did not answer for %s"
                             % (", ".join(broke[:3]) if broke else "part of its listing"))
    sm = enumerate_sitemap.run(fx, site, say)
    if sm.get("urls"):
        asked.add("sitemap")
    for u, meta in (sm.get("urls") or {}).items():
        current.setdefault(_norm(u), "the sitemap")
        if isinstance(meta, dict) and meta.get("lastmod"):
            lastmod[_norm(u)] = meta["lastmod"]
    newly_blocked = ({b.get("sitemap") for b in (sm.get("blocked") or [])}
                     - {b.get("sitemap") for b in (sm_before.get("blocked") or [])})
    if newly_blocked:
        partial["sitemap"] = ("%d sitemap file(s) did not answer this time (%s)"
                              % (len(newly_blocked), "; ".join(sorted(newly_blocked)[:3])))
    if use_archive:
        from ..foundation import enumerate_archive
        ar = enumerate_archive.run(fx, site, say)
        for u in (ar.get("urls") or {}):
            current.setdefault(_norm(u), "the web archive")
        if ar.get("error"):
            partial["archive"] = "the web archive did not answer: %s" % str(ar["error"])[:80]
        elif ar.get("urls"):
            asked.add("archive")
    for src, why in sorted(partial.items()):
        say("One source answered only in part",
            "%s. Nothing it should have listed is judged gone this time — a source that failed "
            "has not said a page is deleted, it has said nothing." % why)
    say("The site lists %s now" % sh.plural(len(current), "page"),
        "%d of them carry a last-changed date" % len(lastmod))

    known = {_norm(p.get("url")): p for p in known_pages if p.get("url")}
    # An address the last read looked at and threw away is not a new page. Found 2026-09-10:
    # every soft 404, robots-disallowed page, machine path and duplicate address the sitemap still
    # lists was counted NEW on every refresh, re-fetched every time, and the duplicate addresses
    # walked back into the catalogue as second copies of pages already in it.
    judged_before = _already_judged(work)              # the full read's verdicts, in _work
    new, judged = [], []
    for u in current:
        if u in known:
            continue
        if u in judged_before and not _moved_since_we_judged(fx, u, lastmod.get(u)):
            judged.append(u)
        else:
            new.append(u)
    if judged:
        say("Left %s out of the new list" % sh.plural(len(judged), "address", "addresses"),
            "the last full read judged each of them and dropped it; being listed again is not "
            "news. One whose last-changed date moves is read again like any other page.")

    # A page is only "gone" when EVERY source that found it was asked again, ANSWERED FOR IT, and
    # no longer lists it. Two ways that goes wrong, and both delete live pages:
    #   - a source we did not ask. Found 2026-09-09 on the first live preview: 662 pages were
    #     reported gone and every one had come from the web archive alone. They are live and
    #     readable; the sitemap simply never listed them. That would have cut 662 real pages out
    #     of Knowledge. The link crawl is the same: a refresh never runs it.
    #   - a source that failed. A sitemap file answering HTTP 500 lists nothing, and a content
    #     type whose endpoint broke lists nothing. Silence is not a deletion. This is decided per
    #     PAGE, not per site: the sitemap layer is asked whether the one file that used to list
    #     THIS page answered, so one broken child sitemap out of a dozen costs only its own pages,
    #     and a sitemap that was already unreadable at the last read changes nothing.
    listed_by = {_norm(u): (m or {}).get("sitemap") for u, m in (sm_before.get("urls") or {}).items()
                 if isinstance(m, dict)}
    parsed_now = set(sm.get("sitemaps_parsed") or [])
    unavailable_types = set(wp.get("unavailable") or {})

    def _answered_for(src, u, p):
        if src not in asked:
            return False                              # never asked: the crawl, usually the archive
        if src == "sitemap":
            f = listed_by.get(u)
            # the exact file that listed it must have answered; with no record of which file it
            # was, only when nothing that used to answer has started failing
            return f in parsed_now if f else not newly_blocked
        if src == "wp":
            return not (wp.get("blocked") or []) and (p.get("type") or "") not in unavailable_types
        return True

    gone, unjudged = [], []
    for u, p in known.items():
        if u in current:
            continue
        srcs = {x.strip() for x in (p.get("source") or "").replace("+", " ").split() if x.strip()}
        if srcs and all(_answered_for(src, u, p) for src in srcs):
            gone.append(u)
        else:
            unjudged.append(u)
    if unjudged:
        say("Left %s alone" % sh.plural(len(unjudged), "page"),
            "each was found by a source this check did not ask or could not read in full (the web "
            "archive, the link crawl, a sitemap that failed), so its absence proves nothing")

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
            "partial": partial, "new": sorted(new), "gone": sorted(gone), "changed": sorted(changed),
            "unchecked": sorted(unchecked), "unjudged": sorted(unjudged), "known_count": len(known),
            "judged": sorted(judged), "judged_why": {u: judged_before[u] for u in judged[:SAMPLE]},
            "titles": {u: (known[u].get("title") or "") for u in gone[:SAMPLE]}}


def _real_address(fx, url):
    """The address this page actually lives at: where the fetch ended up, and then what the page
    itself declares as canonical. The same two signals reconcile collapses aliases on."""
    hit = fx.cached(url)
    if hit is None:
        return _norm(url)
    final = hit.final_url or url
    if hit.content and "html" in (hit.content_type or "").lower():
        try:
            soup = BeautifulSoup(hit.content, "html.parser")
        except Exception:  # noqa: BLE001 — a page we cannot parse is simply not an alias
            soup = None
        canon = ((reconcile.head_canonical(soup) if soup is not None else "")
                 or reconcile.link_header_canonical(hit.headers))
        if canon:
            return _norm(_up.urljoin(final, canon))
    return _norm(final)


def _drop_aliases(fx, rows, known, say):
    """Keep only the rows that are their own page. Returns (kept rows, {alias: real address}).

    reconcile collapses redirect and canonical aliases on a full read; a refresh never runs it, so
    an address that is really a page we already hold under another name went straight into the
    catalogue as a second row of the same page — and the sitemap lists both forms, so every
    refresh added it again (found 2026-09-10, alongside the drop-bucket bug).

    A page we ALREADY hold is never judged here: a refresh re-reads it, and deciding that an
    existing row is a duplicate is a full read's job, not a refresh's.
    """
    target = {_norm(r["url"]): _real_address(fx, r["url"]) for r in rows}
    kept, aliases = [], {}
    for r in rows:
        u = _norm(r["url"])
        t = target.get(u, u)
        # An alias only when the real address is a page that exists: one already in the catalogue,
        # or one in this batch that is its own page. Never collapse onto an address nobody holds.
        if t != u and u not in known and (t in known or target.get(t) == t):
            aliases[u] = t
            continue
        kept.append(r)
    if aliases:
        say("Left %s out" % sh.plural(len(aliases), "duplicate address", "duplicate addresses"),
            "each one is a page already in the catalogue under its real address, not a new page")
    return kept, aliases


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
        if did.get("duplicates"):
            parts.append("%s turned out to be another address for a page already in the catalogue, "
                         "and %s left out."
                         % (sh.plural(did["duplicates"], "address", "addresses"),
                            "was" if did["duplicates"] == 1 else "were"))
    else:
        parts.append("Nothing has been changed yet. This is what a refresh would do.")
    parts += ["", "## New pages (%d)" % len(s["new"]), names(s["new"]),
              "", "## Pages that are gone (%d)" % len(s["gone"]), names(s["gone"]),
              "", "## Pages that changed since we read them (%d)" % len(s["changed"]), names(s["changed"])]
    if s.get("judged"):
        parts += ["", "## Addresses the last full read already judged (%d)" % len(s["judged"]),
                  "The site still lists these, but the last full read fetched each one and dropped "
                  "it: a dead page, an empty template, a duplicate address, or a machine path. "
                  "They are not new pages and are not read again. One whose last-changed date "
                  "moves is read again like any other page.", ""]
        parts += ["- %s — %s" % (u, s.get("judged_why", {}).get(u, "dropped by the last read"))
                  for u in s["judged"][:SAMPLE]]
        if len(s["judged"]) > SAMPLE:
            parts.append("- and %d more" % (len(s["judged"]) - SAMPLE))
    if s.get("partial"):
        parts += ["", "## Sources that answered only in part (%d)" % len(s["partial"]),
                  "Nothing these sources should have listed is judged gone this time. A source "
                  "that failed has not said a page is deleted; it has said nothing.", ""]
        parts += ["- %s: %s" % (k, v) for k, v in sorted(s["partial"].items())]
    if s.get("unjudged"):
        parts += ["", "## Left alone (%d)" % len(s["unjudged"]),
                  "In the catalogue, not in this check's lists, and not judged either way: each "
                  "was found by a source this check did not ask (the web archive, the link crawl) "
                  "or by one that could not answer in full. They stay exactly as they are."]
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
        return {"summary": "%d new, %d gone, %d changed%s%s. Nothing has been changed yet."
                           % (len(s["new"]), len(s["gone"]), len(s["changed"]),
                              ", %d unchecked" % len(s["unchecked"]) if s["unchecked"] else "",
                              ", %d already judged and dropped by the last read" % len(s["judged"])
                              if s["judged"] else ""),
                "preview": True, "new": len(s["new"]), "gone": len(s["gone"]),
                "changed": len(s["changed"]), "unchecked": len(s["unchecked"]),
                "judged": len(s["judged"]), "left_alone": len(s["unjudged"]),
                "report": _report(s)}

    if not todo and not s["gone"]:
        store.save_knowledge("catalogue-changes.md", _report(s, {"added": 0, "removed": 0, "rebuilt": 0}))
        return {"summary": "Nothing has changed since the last read.", "added": 0, "removed": 0,
                "rebuilt": 0, "artifact": "catalogue-changes.md"}

    work = os.path.join(store.knowledge_dir(), "_work")
    raw = os.path.join(store.knowledge_dir(), "_raw")
    swork = os.path.join(work, "refresh")            # a refresh never writes over a full read's files
    os.makedirs(swork, exist_ok=True)
    fx = fetchmod.Fetcher(work, raw, on_event=say)
    site = {"root": s["root"], "host": s["host"], "work": swork, "raw": raw, "max_pages": 0,
            "force_crawl": False, "wordpress_url": sh.company().get("wordpress_url") or ""}

    idx = store.knowledge("site_index.json") or {}
    known = {_norm(p.get("url")): p for p in (idx.get("pages") or []) if p.get("url")}
    # A page we already hold is only "re-read" if it comes off the WIRE again. The saved copy is
    # by definition the version we are trying to replace, so these go through with force.
    force = {u for u in todo if u in known}

    rows, verdict, aliases = [], {}, {}
    if todo:
        say("Reading %s" % sh.plural(len(todo), "page"),
            "only the ones that are new or have changed; the other %d are left alone"
            % max(0, s["known_count"] - len(todo)))
        # extract works offline from the saved copies, so the new pages have to be fetched first.
        # This is the only expensive part of a refresh, and it is exactly len(todo) fetches.
        pages = {u: {"url": u, "sources": {"sitemap"}} for u in todo}
        verdict = reconcile._fetch_pass(fx, site, pages, say, force=force)
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
        rows, aliases = _drop_aliases(fx, good, known, say)

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
    # "Re-read" may only ever mean "came off the site again". The fetch pass counts what it
    # provably refetched, so the number in the report is that count, never the number of rows
    # merged. Before 2026-09-10 the two were the same number and both were wrong: nothing was
    # refetched at all.
    read_again = verdict.get("refetched", rebuilt)
    if rebuilt > read_again:
        say("Fewer pages were re-read than the merge suggests",
            "%d changed pages were merged back but only %d came off the site; the report counts "
            "the %d" % (rebuilt, read_again, read_again))
        rebuilt = read_again
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
    report = _report(s, {"added": added, "removed": removed, "rebuilt": rebuilt,
                         "duplicates": len(aliases), "traffic": traffic_note})
    store.save_knowledge("catalogue-changes.md", report)

    out = {"summary": "%s added, %s removed, %s re-read. The catalogue is %s."
                      % (sh.plural(added, "page"), sh.plural(removed, "page"),
                         sh.plural(rebuilt, "page"), sh.plural(len(pages), "page")),
           "added": added, "removed": removed, "rebuilt": rebuilt, "pages": len(pages),
           "unchecked": len(s["unchecked"]), "judged": len(s["judged"]), "duplicates": len(aliases),
           "artifact": "catalogue-changes.md"}
    if traffic_note:
        out["note"] = traffic_note
    if added or rebuilt or removed:
        out["note"] = (out.get("note", "") + " The page index needs rebuilding so the new pages can "
                       "be found by meaning; run build_page_index.").strip()
    return out
