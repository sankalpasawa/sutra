"""brand/cta.py — the call-to-action page list: its one parser and its one writer.

The close of an article may link to exactly one page, and only to a page on this list. Two very
different things write the list — the features builder, from the crawl, and a person, by hand on
the Knowledge screen — and two things downstream read it back (write/wrapper.py::cta_pages, which
regexes `^- Page: <url>`, and editing/links_pass.py::product_paths, which regexes every url in the
file). So the format is defined HERE, once, and both writers call this module. A second copy of
the format in an HTTP handler would be a second thing to keep in step, and it would not stay in
step.

A row a PERSON put there is marked `<!--mine-->` on its Page line, after a space so the wrapper's
`\\S+` still captures the bare url. That mark is the whole point of the file having a format at
all: `build_cta_pages` used to overwrite the file wholesale, so a page the owner added by hand
disappeared the next time the features builder ran. Marked rows are lifted off the old file and
re-emitted above the generated ones, and a generated row for a url a person already listed is
dropped rather than written twice.

EVERY URL ON THE LIST RESOLVES, and the file says so in its own words. The original builds this
from the crawl and states it at the top ("Every URL here was fetched and is live"); this copy has
to earn it rather than inherit it, because a person can type a url in by hand and because a crawl
ages. `rebuild` probes every row before it writes (see the knobs below), a proven-dead generated
row goes into the dropped list with its reason, and a url that could not be checked is marked and
kept. The top line of the file is written from the rows' own verdicts, so it can only ever claim a
check that actually happened.

Reads:  knowledge/brand/cta-pages.md · knowledge/site_index.json (page titles only)
Writes: knowledge/brand/cta-pages.md
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
# Named explicitly: before Python 3.11 concurrent.futures.TimeoutError is its OWN class and not
# the builtin, so `except TimeoutError` here would sail straight past the budget and never fire.
from concurrent.futures import TimeoutError as _BudgetSpent

from .. import store
from ..foundation import urls as U
from . import _common as cm

OUTPUT = "cta-pages.md"
MINE = "<!--mine-->"
DROPPED_SHOWN = 60          # the foot of the file lists this many dropped candidates, then a count

# ---- the liveness check's knobs -----------------------------------------------------------------
# The original builds this file from the crawl and prints "Every URL here was fetched and is live"
# at the top of it (01-brand-context/3-features/scripts/build_cta_pages.py). Sutra's list is not
# only the crawl's any more — a person adds rows by hand on the Knowledge screen, and the crawl
# itself ages — so the guarantee has to be checked rather than inherited, or a dead link ends up in
# the close of a published article. It is checked CHEAPLY: a HEAD, a handful at a time, on a clock.
LIVE_WORKERS = 8            # probes in flight at once
LIVE_TIMEOUT = 8.0          # seconds for one probe
LIVE_BUDGET = 60.0          # seconds for the WHOLE check. The brand pack must never hang on this;
#                             whatever has not answered by then is reported unchecked, not dropped.

# The three answers a probe can give. A url is only ever removed on GONE — a proven 404 or 410.
# UNCHECKED is a fact about the check, not about the page: a timeout, a refused connection, a bot
# wall. Treating it as dead would delete a live product page because a CDN was slow for a second.
LIVE, GONE, UNCHECKED = "live", "gone", "unchecked"

_PAGE = re.compile(r"^- Page:\s*(\S+)\s*(.*)$")
_KIND = re.compile(r"^- Kind:\s*(.*?)\s*(?:·.*)?$")
_NOTE = re.compile(r"^- Note:\s*(.*)$")
_CHECKED = re.compile(r"^- Checked:\s*(live|gone|unchecked)\b\s*(?:—\s*(.*))?$", re.I)
_TRAFFIC = re.compile(r"·\s*([\d,]+)\s*visits")


# ---- reading -----------------------------------------------------------------------------------

def _norm(url):
    return (url or "").strip().rstrip("/")


def titles():
    """{url without its trailing slash: title} from the catalogue.

    The light rows only. The bodies live in a separate file and this is called on every read of the
    screen, so pulling 12,318 page bodies into memory to find a title would be the wrong trade.
    """
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    out = {}
    for p in pages or []:
        if isinstance(p, dict) and p.get("url"):
            out[_norm(p["url"])] = p.get("title") or ""
    return out


def parse(text):
    """(rows, dropped) out of the file's text.

    A row is {url, note, title, mine, kind, traffic, features, live, live_why}. `title` is the
    heading the file carries, which is only what was known when it was written; the catalogue is the
    authority and rows() looks it up fresh. `live` is the last liveness verdict, "" for a row that
    has never been checked. Everything below the `---` rule is the dropped list and is never a row.
    """
    rows, dropped, cur = [], [], None
    body = (text or "").split("\n---\n", 1)
    head = body[0]
    tail = body[1] if len(body) > 1 else ""
    for ln in head.splitlines():
        t = ln.strip()
        if t.startswith("## "):
            cur = {"url": "", "note": "", "title": t[3:].strip(), "mine": False,
                   "kind": "", "traffic": 0, "features": [], "live": "", "live_why": ""}
            rows.append(cur)
            continue
        if cur is None:
            continue
        m = _PAGE.match(t)
        if m:
            cur["url"] = m.group(1)
            cur["mine"] = MINE in m.group(2)
            continue
        m = _NOTE.match(t)
        if m:
            cur["note"] = m.group(1).strip()
            continue
        m = _CHECKED.match(t)
        if m:
            # BEFORE the Kind line and before the catch-all: a "- Checked: ..." line is a verdict,
            # not one of the free-text product facts, and the catch-all below would swallow it into
            # `features` and re-emit it as a bullet under the page. Read back so a verdict survives
            # a save from the Knowledge screen, which rewrites the file without re-probing.
            cur["live"] = m.group(1).lower()
            cur["live_why"] = (m.group(2) or "").strip()
            continue
        m = _KIND.match(t)
        if m:
            cur["kind"] = m.group(1).strip()
            tr = _TRAFFIC.search(t)
            cur["traffic"] = int(tr.group(1).replace(",", "")) if tr else 0
            continue
        if t.startswith("- "):
            cur["features"].append(t[2:].strip())
    for ln in tail.splitlines():
        t = ln.strip()
        if t.startswith("- ") and "—" in t:
            u, _sep, why = t[2:].partition("—")
            dropped.append((u.strip(), why.strip()))
    return [r for r in rows if r["url"]], dropped


def rows():
    """The list as the screen shows it: {url, note, title, mine} per row, in file order.

    `title` comes from the catalogue and is "" for a page the catalogue has never seen — a page
    published since the last crawl, say. That is allowed on purpose; the screen says so rather than
    treating it as a failure. `note` falls back to the row's kind, so a generated row is not blank.
    """
    parsed, _dropped = parse(cm.read(OUTPUT))
    known = titles()
    return [{"url": r["url"], "note": r["note"] or r["kind"], "mine": r["mine"],
             "title": known.get(_norm(r["url"]), "")} for r in parsed]


def count():
    return len(rows())


# ---- is it live? ---------------------------------------------------------------------------------

def _probe_once(url):
    """One cheap liveness probe: (LIVE | GONE | UNCHECKED, why).

    HEAD first, because the answer is a status code and nobody here wants the body. Some hosts
    refuse HEAD and serve the identical url to a GET, so a 405 (and a 404, which several CDNs
    return for a HEAD they do not implement) is asked again properly before it is believed.

    Only 404 and 410 mean GONE. A 401/403/429 is a bot wall, a 5xx is the site having a bad
    minute, and a connection that never opened is the network: all of those are UNCHECKED, and an
    UNCHECKED url is reported, never dropped. The same line write/_common.py draws for an article's
    sources, drawn once more here for the same reason: "I could not read it" is not "it is gone".
    """
    import httpx
    try:
        with httpx.Client(follow_redirects=True, timeout=LIVE_TIMEOUT) as c:
            r = c.head(url)
            if r.status_code in (404, 405):
                r = c.get(url)
            if r.status_code in (404, 410):
                return GONE, "the page answered %d" % r.status_code
            if r.status_code >= 500:
                return UNCHECKED, "the site answered %d, so it could not be checked" % r.status_code
            return LIVE, ""
    except Exception as e:      # noqa: BLE001 — a timeout, a refused connection, a bad certificate
        return UNCHECKED, "could not reach it (%s)" % type(e).__name__


PROBE = _probe_once     # the one name tests swap out, the way write/_common.ALIVE is swapped


def verify(urls):
    """{url: (state, why)} for every url handed in. Bounded, and on a clock.

    LIVE_BUDGET is the whole check's ceiling, not each probe's: a brand pack that stalls for four
    minutes on a slow host is a brand pack nobody waits for. Whatever has not answered when the
    budget runs out is UNCHECKED with that as its reason, so the file still says something true
    about every row.
    """
    urls = [u for u in dict.fromkeys(urls) if u]
    if not urls:
        return {}
    out = {}
    ex = ThreadPoolExecutor(max_workers=LIVE_WORKERS)
    try:
        futs = {ex.submit(PROBE, u): u for u in urls}
        try:
            for f in as_completed(futs, timeout=LIVE_BUDGET):
                try:
                    out[futs[f]] = f.result()
                except Exception as e:      # noqa: BLE001 — one bad url never ends the check
                    out[futs[f]] = (UNCHECKED, "the check itself failed (%s)" % type(e).__name__)
        except _BudgetSpent:
            pass
        for u in urls:
            out.setdefault(u, (UNCHECKED, "the %ds check ran out of time before this one answered"
                               % int(LIVE_BUDGET)))
    finally:
        # wait=False: the budget is the point. A probe still in flight writes to nothing that
        # matters and the interpreter waits for it at exit, not the brand pack.
        ex.shutdown(wait=False)
    return out


# ---- writing -----------------------------------------------------------------------------------

def _live_line(page_rows):
    """The one sentence at the top that says what the liveness check found.

    Written from the rows and from nothing else, so it can never claim a check that did not run.
    A file whose rows carry no verdict says so plainly rather than repeating the original's
    "every URL here is live", which would be a promise this copy had not kept.
    """
    seen = [(r.get("live") or "") for r in page_rows]
    checked = [v for v in seen if v]
    if not checked:
        return "None of these have been checked for a live page yet."
    gone = sum(1 for v in checked if v == GONE)
    unknown = sum(1 for v in checked if v == UNCHECKED)
    live = sum(1 for v in checked if v == LIVE)
    parts = ["%d of these answered when they were last checked" % live]
    if gone:
        parts.append("%d did NOT and are marked dead — do not link to those" % gone)
    if unknown:
        parts.append("%d could not be checked and are marked so, not removed" % unknown)
    if len(checked) < len(page_rows):
        parts.append("%d have never been checked" % (len(page_rows) - len(checked)))
    return "; ".join(parts) + "."


def render(brand, page_rows, dropped):
    """The file, from the rows. Pure assembly: every line here comes off a row it was handed."""
    mine = sum(1 for r in page_rows if r.get("mine"))
    out = ["# %s — pages a call to action may link to" % brand, "",
           "The short list an article's close may link to. The close links to ONE of these and",
           "nothing else. Pages you added yourself come first and are never removed by a rebuild.", "",
           _live_line(page_rows), "",
           "%d pages%s. %d candidates were dropped; the reasons are at the foot."
           % (len(page_rows), (", %d of them yours" % mine) if mine else "", len(dropped)), ""]
    for r in page_rows:
        out.append("## %s" % (r.get("title") or r["url"]))
        out.append("- Page: %s%s" % (r["url"], (" " + MINE) if r.get("mine") else ""))
        if r.get("live"):
            why = (r.get("live_why") or "").strip()
            out.append("- Checked: %s%s" % (r["live"], (" — " + why) if why else ""))
        if r.get("kind"):
            out.append("- Kind: %s  ·  %s visits a month" % (r["kind"], format(int(r.get("traffic") or 0), ",")))
        note = (r.get("note") or "").strip()
        if note and note != r.get("kind"):
            out.append("- Note: %s" % note)
        for x in r.get("features") or []:
            out.append("- %s" % x)
        out.append("")
    out += ["---", "", "## Dropped, and why", ""]
    out += ["- %s  — %s" % (u, w) for u, w in dropped[:DROPPED_SHOWN]]
    if len(dropped) > DROPPED_SHOWN:
        out.append("- ... and %d more" % (len(dropped) - DROPPED_SHOWN))
    cm.save(OUTPUT, "\n".join(out) + "\n")
    return page_rows, dropped


def rebuild(brand, generated, dropped, check_live=True):
    """The features builder's write. Person-authored rows are lifted off the existing file and
    re-emitted first; a generated row for a url one of them already covers is skipped, or the same
    page would be listed twice with two different notes.

    THIS IS WHERE THE LIVE CHECK RUNS, and it is the only place it runs. It is the rebuild that
    corresponds to the original's `build_cta_pages.build()`, the one that prints "Every URL here
    was fetched and is live" — and unlike the original's, this list can hold a url no crawl ever
    fetched, because a person may type one in. A dead url in this file becomes a dead link in the
    close of a published article, which is the one link in an article a reader is most likely to
    click.

    What a verdict does:
      GONE      a generated row is dropped, with the reason in the dropped list at the foot.
                A row a PERSON added is NOT dropped — this file's other promise is that their
                rows survive a rebuild — it is kept and marked dead, so they can see it and fix it.
      UNCHECKED kept, marked, and counted in the line at the top. Never dropped: "I could not
                reach it" is a fact about the check, not about the page.

    check_live=False skips the network entirely, for a caller that only wants the file rewritten.
    """
    kept, _old_dropped = parse(cm.read(OUTPUT))
    mine = [r for r in kept if r["mine"]]
    have = {_norm(r["url"]) for r in mine}
    fresh = [dict(g, mine=False) for g in generated if _norm(g["url"]) not in have]
    page_rows, dropped = mine + fresh, list(dropped)
    if check_live:
        seen = verify([r["url"] for r in page_rows])
        live_rows = []
        for r in page_rows:
            state, why = seen.get(r["url"], (UNCHECKED, "it was not checked"))
            r["live"], r["live_why"] = state, why
            if state == GONE and not r.get("mine"):
                dropped.append((r["url"], why or "the page is gone"))
                continue
            live_rows.append(r)
        page_rows = live_rows
    return render(brand, page_rows, dropped)


def save(brand, wanted):
    """The person's write: `wanted` is the WHOLE list, in the order they want it, as {url, note}.

    Every row saved this way is theirs from then on. What the crawl already knew about a url it had
    found — its kind, its traffic, the three product facts under it — is carried across rather than
    dropped, because that text is what the writer reads when it picks a close; losing it on a
    reorder would quietly make every article's ending worse.
    """
    known_rows, dropped = parse(cm.read(OUTPUT))
    old = {_norm(r["url"]): r for r in known_rows}
    known = titles()
    out = []
    for w in wanted:
        url = (w.get("url") or "").strip()
        prev = old.get(_norm(url), {})
        out.append({"url": url, "note": (w.get("note") or "").strip(), "mine": True,
                    "title": known.get(_norm(url)) or prev.get("title") or "",
                    "kind": prev.get("kind", ""), "traffic": prev.get("traffic", 0),
                    "features": prev.get("features") or [],
                    # The liveness verdict rides across a reorder like the rest of what the crawl
                    # knew. A url this write has never seen has no verdict, which renders as "never
                    # checked" — honest, and the next rebuild fills it in.
                    "live": prev.get("live", ""), "live_why": prev.get("live_why", "")})
    render(brand, out, dropped)
    return rows()


# ---- validation ---------------------------------------------------------------------------------

def check(url, domain):
    """Why this url may not go on the list, or "" when it may.

    A url the catalogue has never seen is allowed: the owner may be linking to a page published
    since the last crawl, and refusing it would make him re-crawl to add a link he already knows
    is live. A url on somebody else's domain is not, because the close is a link to the company's
    own product and nothing else.
    """
    u = (url or "").strip()
    if not u:
        return "A row with no address cannot be linked to."
    if not re.match(r"^https?://", u, re.I):
        return "%s is not a web address. It needs to start with http:// or https://." % u
    if not U.host_of(u):
        return "%s is not a web address I can read." % u
    if domain and not U.own_host(u, domain):
        return ("%s is not on %s. The close links to one of your own pages, never somebody else's."
                % (u, U.bare_host(domain)))
    return ""
