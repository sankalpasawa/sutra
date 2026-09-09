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

Reads:  knowledge/brand/cta-pages.md · knowledge/site_index.json (page titles only)
Writes: knowledge/brand/cta-pages.md
"""
import re

from .. import store
from ..foundation import urls as U
from . import _common as cm

OUTPUT = "cta-pages.md"
MINE = "<!--mine-->"
DROPPED_SHOWN = 60          # the foot of the file lists this many dropped candidates, then a count

_PAGE = re.compile(r"^- Page:\s*(\S+)\s*(.*)$")
_KIND = re.compile(r"^- Kind:\s*(.*?)\s*(?:·.*)?$")
_NOTE = re.compile(r"^- Note:\s*(.*)$")
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

    A row is {url, note, title, mine, kind, traffic, features}. `title` is the heading the file
    carries, which is only what was known when it was written; the catalogue is the authority and
    rows() looks it up fresh. Everything below the `---` rule is the dropped list and is never a row.
    """
    rows, dropped, cur = [], [], None
    body = (text or "").split("\n---\n", 1)
    head = body[0]
    tail = body[1] if len(body) > 1 else ""
    for ln in head.splitlines():
        t = ln.strip()
        if t.startswith("## "):
            cur = {"url": "", "note": "", "title": t[3:].strip(), "mine": False,
                   "kind": "", "traffic": 0, "features": []}
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


# ---- writing -----------------------------------------------------------------------------------

def render(brand, page_rows, dropped):
    """The file, from the rows. Pure assembly: every line here comes off a row it was handed."""
    mine = sum(1 for r in page_rows if r.get("mine"))
    out = ["# %s — pages a call to action may link to" % brand, "",
           "The short list an article's close may link to. The close links to ONE of these and",
           "nothing else. Pages you added yourself come first and are never removed by a rebuild.", "",
           "%d pages%s. %d candidates were dropped; the reasons are at the foot."
           % (len(page_rows), (", %d of them yours" % mine) if mine else "", len(dropped)), ""]
    for r in page_rows:
        out.append("## %s" % (r.get("title") or r["url"]))
        out.append("- Page: %s%s" % (r["url"], (" " + MINE) if r.get("mine") else ""))
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


def rebuild(brand, generated, dropped):
    """The features builder's write. Person-authored rows are lifted off the existing file and
    re-emitted first; a generated row for a url one of them already covers is skipped, or the same
    page would be listed twice with two different notes."""
    kept, _old_dropped = parse(cm.read(OUTPUT))
    mine = [r for r in kept if r["mine"]]
    have = {_norm(r["url"]) for r in mine}
    fresh = [dict(g, mine=False) for g in generated if _norm(g["url"]) not in have]
    return render(brand, mine + fresh, dropped)


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
                    "features": prev.get("features") or []})
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
