"""Layer 1 — every page the site's own CMS (WordPress REST) knows about.

Reads:  <root>/wp-json/wp/v2/types (the root is wordpress_url from the company record when set,
        else the site itself). No answer = not a WordPress site -> layer skipped, honestly recorded.
Writes: _work/urls-wp.json:
  { "skipped": null | "<reason>", "wordpress_url": "<root>" | "",
    "types":  { <type>: {"rest_base", "total", "collected", "unreadable": [], "withheld"} },
    "unavailable": { <type>: {"rest_base", "reason"} },
    "blocked": [...],
    "urls":   { <link>: {"type","title","description","modified","rest_chars","api_page"} } }

Rules (all measured):
- The type list is DERIVED at runtime from /wp-json/wp/v2/types — never typed in (a hardcoded
  list once made 27% of the site invisible; a recovery list missed a whole type).
- Skip any rest_base containing "(" (one core type ships a literal regex as its rest_base) and
  "media" (the platform's file library — attachments, not site pages).
- per_page=100 exactly (101 -> HTTP 400).
- "No more data" is ONLY rest_post_invalid_page_number; any other failure retries in fetch.
- Pagination is driven by the authoritative X-WP-Total, not by "a short page means the end" —
  after a bisection a page IS legitimately short, and short must never mean the end.
- A CMS that cannot render ONE item answers 5xx for the WHOLE batch that item lands in. Retrying
  it can never succeed and giving up on the type would throw away the healthy items around it, so
  the failing range is BISECTED until the poison is cornered at a single item, recorded in
  `unreadable` by position. One unrenderable item costs itself, never its type.
- More than MAX_UNREADABLE_PER_TYPE items failing individually means the ENDPOINT is failing, not
  its records: stop bisecting and report the whole TYPE as unavailable, its size UNKNOWN (never
  assumed empty), rather than minting one false "gap" per item.
- 401/403 on page 1 = not publicly listable (skipped, not a failure).
- An HTML body where JSON was expected = BLOCKED (loud), never an empty layer.
- collected + unreadable + withheld == X-WP-Total, where withheld is what the CMS counts but
  declines to serve an anonymous client (private/draft/protected). A shortfall WITH errors is
  never read benignly: that reading is only available when every request answered 200.

The rendered bodies stay in fetch's raw cache (api_page says which cached API page holds each
URL's content) — extract.py re-reads them OFFLINE; this file stays light.
"""
import html as _html
import json
import os
import re

from .. import store
from . import settings
from .fetch import host_of, Blocked, RobotsDisallowed

FIELDS = "link,type,title,excerpt,content,modified"


def _strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


class _TypeUnavailable(Exception):
    """The TYPE's endpoint is failing, not one record inside it."""


class _NotListable(Exception):
    """The CMS declares the type but will not list it to an anonymous client."""


def _code(text):
    try:
        return (json.loads(text) or {}).get("code", "")
    except (ValueError, AttributeError):
        return ""


def _largest_proper_divisor(n):
    """The biggest d < n that divides n — the bisection ladder for a page size (100 -> 50 -> 25 ->
    5 -> 1). A DIVISOR keeps every sub-page aligned to the parent's item range, so the `page`
    arithmetic stays exact; halving an odd size would straddle boundaries and silently re-ask the
    wrong items."""
    for d in range(n // 2, 0, -1):
        if n % d == 0:
            return d
    return 1


def _page(fx, slug, base, api, page, state, per_page=None, unreadable=None):
    """One page of a type's results. Returns the item list, or None at the genuine end.

    On a persistent SERVER error this range is re-asked in smaller aligned slices until the item
    the CMS cannot render is cornered alone and recorded in `unreadable` by position. Measured on
    a real site: one unrenderable record 5xx'd its whole 100-item page and would otherwise have
    cost that type's other 150 items.
    """
    per_page = settings.WP_PER_PAGE if per_page is None else per_page
    unreadable = [] if unreadable is None else unreadable
    full = per_page == settings.WP_PER_PAGE          # a full-size page, not a bisection probe
    url = "%s/%s?per_page=%d&page=%d&_fields=%s" % (api, base, per_page, page, FIELDS)
    # The parent range already proved this fails persistently, so a probe does not re-prove it
    # six times over: that turns cornering one bad record into minutes of retries.
    r = fx.get(url, attempts=None if full else settings.BISECT_ATTEMPTS)
    if r.status == 400:
        if _code(r.text) == "rest_post_invalid_page_number":
            return None                              # the one GENUINE end-of-data signal
        raise _TypeUnavailable("unexpected HTTP 400 at page %d: %s" % (page, r.text[:120]))
    if r.status in (401, 403) and page == 1 and full:
        raise _NotListable("not publicly listable (HTTP %d)" % r.status)
    if r.status == 404:
        # A type can be DECLARED in /types while its collection route is never registered. The
        # CMS says so precisely — trust its own error code, don't infer it from the bare 404.
        if _code(r.text) == "rest_no_route" and page == 1 and full:
            raise _NotListable("declared by the CMS but has no collection route")
        raise _TypeUnavailable("HTTP 404 at page %d" % page)
    if r.status == 200:
        body = r.text.strip()
        if body[:1] != "[":
            raise Blocked("HTML where JSON was expected at %s — a challenge page, not an empty result" % url)
        state["saw_200"] = True
        if state["total"] is None and r.headers.get("x-wp-total") is not None:
            try:
                state["total"] = int(r.headers["x-wp-total"])
            except ValueError:
                pass
        items = json.loads(body)
        for it in items:
            it["_api_page"] = url                    # the EXACT cached URL this item came from
        return items
    if r.status == 0:
        # No answer at all (timeout, DNS, reset). NOT the site's data: never recorded as a gap.
        raise _TypeUnavailable("no response from the server at page %d — a network failure, not a "
                               "CMS error (%s)" % (page, r.headers.get("_fetch_error", "")))
    if 500 <= r.status < 600:
        # A persistent server error on a RANGE. Any error here forfeits the benign reading of a
        # later shortfall (run() checks state["errors"]): a server that is failing is not a server
        # that is declining.
        state["errors"] = state.get("errors", 0) + 1
        start = (page - 1) * per_page                # 0-based index of this range's first item
        if per_page == 1:
            unreadable.append(start + 1)
            # A poisoned record is rare and isolated. Many of them in one type means the ENDPOINT
            # is broken, so every further probe just mints another false "gap" — stop and say so.
            if len(unreadable) > settings.MAX_UNREADABLE_PER_TYPE:
                raise _TypeUnavailable("%d items failed individually (HTTP %d) — the endpoint is "
                                       "failing, not its records" % (len(unreadable), r.status))
            return []
        d = _largest_proper_divisor(per_page)
        out = []
        for k in range(per_page // d):
            got = _page(fx, slug, base, api, start // d + k + 1, state, per_page=d,
                        unreadable=unreadable)
            out += got or []                         # None here is a short slice, never the end
        return out
    raise _TypeUnavailable("unexpected HTTP %d at page %d" % (r.status, page))


def _skipped(site, reason, root=""):
    doc = {"domain": site["host"], "skipped": reason, "wordpress_url": root, "types": {},
           "unavailable": {}, "blocked": [], "urls": {}}
    store.write_json(os.path.join(site["work"], "urls-wp.json"), doc)
    return doc


def run(fx, site, say):
    root = (site.get("wordpress_url") or site["root"]).rstrip("/")
    api_root = root + "/wp-json"
    core = api_root + "/wp/v2"                       # the type INDEX always lives in core

    # 1) ask the site what content types it has — never assume.
    #
    # THIS IS A PROBE, NOT A FETCH, so it takes one attempt and no cooldowns (fetch.get's
    # `discovery` argument, and its docstring carries the incident). A site that has moved off
    # WordPress answers 403 or 404 here and always will: that is the ANSWER, not a firewall to
    # sit out. The owner's own site did exactly this and cost six minutes per refresh, then
    # tripped its rate limiter so the sitemap step that follows was refused too.
    try:
        r = fx.get(core + "/types", discovery=True)
    except RobotsDisallowed:
        say("Skipped the content system", "robots.txt does not allow reading its listing")
        return _skipped(site, "robots.txt disallows the REST API")
    except Blocked as e:
        # REPORTED AS "NOT WORDPRESS", NOT AS "BLOCKED", because for this step they are the same
        # outcome: no page list from a CMS. Saying "the site refused the request" sends somebody
        # looking for a firewall problem on a site that simply is not WordPress any more.
        say("No content system to ask",
            "%s did not answer as a WordPress site, so its own page list is not available. "
            "The sitemaps are the source instead." % host_of(core))
        return _skipped(site, "no WordPress REST API: %s" % str(e)[:160])
    body = r.text.strip()
    if r.status != 200 or body[:1] != "{":
        why = ("no WordPress REST API answered at %s (HTTP %d)" % (core + "/types", r.status)
               if r.status else "no response from %s" % (core + "/types"))
        say("No content system to ask", "this is not a WordPress site, so its own page list is not available")
        return _skipped(site, why)
    types_doc = json.loads(body)
    if not isinstance(types_doc, dict):
        return _skipped(site, "the /types answer was not a type map")

    rest_bases = []
    for slug, t in sorted(types_doc.items()):
        t = t or {}
        base = t.get("rest_base") or slug
        if "(" in base:          # one core type ships a literal regex as its rest_base
            continue
        if base == "media":      # the platform's file library — attachments, not site pages
            continue
        # A type declares WHICH namespace serves it (Web Stories uses web-stories/v1). Assuming
        # wp/v2 asks a route that does not exist. Fall back to core only when it declares nothing.
        ns = t.get("rest_namespace") or "wp/v2"
        rest_bases.append((slug, base, "%s/%s" % (api_root, ns)))
    say("Asked the content system", "%d content types listed by the site itself" % len(rest_bases))

    # 2) paginate every type; assert X-WP-Total per type
    urls, per_type, unavailable, blocked = {}, {}, {}, []
    for slug, base, api in rest_bases:
        state, items, unreadable = {"total": None, "saw_200": False}, [], []
        try:
            first = _page(fx, slug, base, api, 1, state, unreadable=unreadable)
            items = first or []
            total = state["total"]
            if total is None:
                raise _TypeUnavailable("answered 200 but sent no X-WP-Total header — its size cannot be verified"
                                       if state["saw_200"] else "no count header was ever served")
            # Drive pagination from the AUTHORITATIVE count, never from "this page looks short" —
            # after a bisection a page is legitimately short.
            for page in range(2, -(-total // settings.WP_PER_PAGE) + 1):
                got = _page(fx, slug, base, api, page, state, unreadable=unreadable)
                if got is None:
                    break
                items += got
        except _NotListable as e:
            say("Skipped a content type", "%s: %s" % (slug, e))
            continue
        except _TypeUnavailable as e:
            # We cannot tell a broken endpoint hiding 0 pages from one hiding 5,000 — the sitemap,
            # archive and traffic layers cross-check it independently. Never silent: reported.
            unavailable[slug] = {"rest_base": base, "reason": str(e)}
            say("A content type could not be counted", "%s: %s" % (slug, str(e)[:140]))
            continue
        except Blocked as e:
            blocked.append(str(e)[:300])
            unavailable[slug] = {"rest_base": base, "reason": "blocked: " + str(e)[:160]}
            say("The site refused part of the listing", "%s: %s" % (slug, str(e)[:120]))
            continue
        except RobotsDisallowed:
            unavailable[slug] = {"rest_base": base, "reason": "robots.txt disallows this listing"}
            continue

        for it in items:
            link = (it or {}).get("link", "")
            if not link:
                continue
            urls[link] = {
                "type": slug,
                "title": _strip_tags(((it.get("title") or {}).get("rendered", ""))),
                "description": _strip_tags(((it.get("excerpt") or {}).get("rendered", ""))),
                "modified": it.get("modified", ""),
                "rest_chars": len(((it.get("content") or {}).get("rendered", "")) or ""),
                "api_page": it.get("_api_page", ""),
            }
        collected = len(items)
        withheld = max(0, total - collected - len(unreadable))
        if withheld and state.get("errors"):
            # A shortfall is this engine's most dangerous symptom (2,000 of 3,623 pages once went
            # missing this way), so it may only be read benignly under a strict condition: every
            # request for this type answered 200. Then the server is not failing, it is DECLINING
            # — its count includes records an anonymous client may not read. With an error in the
            # run that reading is void, and an unexplained shortfall is never called "withheld".
            unavailable[slug] = {"rest_base": base, "reason":
                                 "collected %d + %d unreadable is %d short of the CMS's own count "
                                 "%d, with %d request error(s) — the difference is unexplained, so "
                                 "this type's size is not trusted"
                                 % (collected, len(unreadable), withheld, total, state["errors"])}
            say("A content type does not add up", "%s: %s" % (slug, unavailable[slug]["reason"][:140]))
            continue
        per_type[slug] = {"rest_base": base, "total": total, "collected": collected,
                          "unreadable": unreadable, "withheld": withheld}
        note = "%d of %d" % (collected, total) + ((", %d not served to the public" % withheld) if withheld else "")
        if unreadable:
            note += (", %d the site itself cannot render (item %s) — a known gap, not a lost page"
                     % (len(unreadable), ", ".join(str(i) for i in unreadable[:5])))
        say("Listed %s" % slug, note)

    doc = {"domain": site["host"], "skipped": None, "wordpress_url": root, "types": per_type,
           "unavailable": unavailable, "blocked": blocked, "urls": urls}
    store.write_json(os.path.join(site["work"], "urls-wp.json"), doc)
    say("The site's own list", "%d pages across %d content types%s"
        % (len(urls), len(per_type),
           (", %d type(s) could not be counted" % len(unavailable)) if unavailable else ""))
    return doc
