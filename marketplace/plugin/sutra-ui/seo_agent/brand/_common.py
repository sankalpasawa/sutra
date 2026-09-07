"""brand/_common.py — what every brand builder needs, in one place.

Not a builder. The builders read the catalogue the same way (site_index.json light rows plus the
page bodies in content-database.jsonl), write under knowledge/brand/ the same way, load their
prompts and verbatim templates from prompts/brand/, and run their per-page model calls through the
same bounded thread pool. All of that lives here so no builder drifts from the others.
"""
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import llm
from .. import store
from ..tools import _shared as sh

TEMPLATES = os.path.join(sh.PROMPTS, "brand", "templates")


# ---- files under knowledge/brand/ -----------------------------------------------------------

def path(name):
    return os.path.join(store.knowledge_dir(), "brand", name)


def exists(name):
    return os.path.exists(path(name))


def read(name, default=None):
    """knowledge/brand/<name>: JSON when the name ends .json, else text ("" when missing)."""
    v = store.knowledge("brand/" + name, default)
    if v is None and not name.endswith(".json"):
        return ""
    return v


def save(name, data):
    return store.save_knowledge("brand/" + name, data)


def template(name):
    """A template lifted verbatim from the original recipe, prompts/brand/templates/<name>.md."""
    with open(os.path.join(TEMPLATES, name + ".md"), encoding="utf-8") as f:
        return f.read()


def prompt(name):
    return sh.load_prompt("brand/" + name)


fill = sh.fill


# ---- the catalogue ----------------------------------------------------------------------------

def _norm(url):
    return (url or "").strip().rstrip("/")


def pages():
    """One dict per page, light row + body: {url, type, title, traffic, lang, body_status, body,
    top_keyword, word_count}. The body comes from content-database.jsonl; a light row that carries
    its own body (an older index) is accepted too. body_status defaults to "ok" when the body is
    there, because an index that never wrote the field is not an index of broken pages."""
    idx = sh.site_index()
    bodies = sh.page_bodies()
    titles = {_norm(u): t for u, t, _b in sh.pages_with_bodies()}
    out, seen = [], set()
    for p in idx.get("pages", []):
        url = sh.page_url(p)
        if not url or _norm(url) in seen:
            continue
        seen.add(_norm(url))
        body = bodies.get(_norm(url)) or p.get("body") or ""
        status = p.get("body_status") or ("ok" if body.strip() else "missing")
        tr = p.get("traffic_clean")
        if tr in (None, ""):
            tr = p.get("traffic") or 0
        out.append({"url": url, "type": p.get("type") or "", "title": p.get("title") or titles.get(_norm(url), ""),
                    "traffic": _num(tr), "lang": p.get("lang") or "", "body_status": status,
                    "body": body, "top_keyword": p.get("top_keyword") or "",
                    "word_count": p.get("word_count") or len(body.split())})
    return out


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def ok_pages(language=None):
    """Pages with a readable body, in the primary language (a row with no lang counts as primary)."""
    lang = (language or "en")[:2]
    return [p for p in pages()
            if p["body_status"] == "ok" and p["body"].strip()
            and (p["lang"] or lang)[:2] == lang]


def traffic_map():
    """{url: traffic} from knowledge/top-pages.json (traffic_clean when present, else traffic).
    Empty when the file is not there; callers then fall back to the index's own traffic column."""
    rows = store.knowledge("top-pages.json") or []
    if isinstance(rows, dict):
        rows = rows.get("pages") or rows.get("rows") or []
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("url"):
            continue
        tr = r.get("traffic_clean")
        if tr in (None, ""):
            tr = r.get("traffic")
        out[_norm(r["url"])] = _num(tr)
    return out


def top_pages():
    """The top-pages rows in their own order (traffic order), [] when the file is missing."""
    rows = store.knowledge("top-pages.json") or []
    if isinstance(rows, dict):
        rows = rows.get("pages") or rows.get("rows") or []
    return [r for r in rows if isinstance(r, dict) and r.get("url")]


def traffic_of(page, tmap=None):
    if tmap:
        v = tmap.get(_norm(page["url"]))
        if v is not None:
            return v
    return page.get("traffic") or 0.0


def is_home(url, domain):
    """The homepage: scheme + optional www + the domain, nothing else."""
    u = _norm(url).lower()
    d = (domain or "").lower().strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    if u.startswith("www."):
        u = u[4:]
    if d.startswith("www."):
        d = d[4:]
    return bool(d) and u == d


def depth1(url):
    return len(urllib.parse.urlsplit(url).path.strip("/").split("/")) == 1


def slug(url):
    part = _norm(url).split("/")[-1] or "homepage"
    return re.sub(r"[^a-z0-9-]", "", part.lower())[:50] or "page"


def roles():
    """brand/type-roles.json, or {} when the type step has not run (callers say so)."""
    r = read("type-roles.json")
    return r if isinstance(r, dict) else {}


# ---- model calls, several at once -------------------------------------------------------------

def parallel(fn, items, say=None, label="", every=5):
    """Run fn(item) for every item, llm.PARALLEL at a time. Returns [(item, result, error)] in the
    items' own order, so a caller can keep source order rather than completion order. One failure
    never kills the batch; it comes back as the error and the caller says so."""
    results = {}
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for n, fut in enumerate(as_completed(futs), 1):
            i = futs[fut]
            try:
                results[i] = (fut.result(), None)
            except Exception as e:      # noqa: BLE001 - one bad page must not kill the draft
                results[i] = (None, e)
            if say and label and (n % every == 0 or n == len(items)):
                say(label, "%d of %d done" % (n, len(items)))
    return [(items[i], results[i][0], results[i][1]) for i in range(len(items))]


def strip_fence(text):
    """A fence around the whole document sneaks in sometimes."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-z]*\n|\n```$", "", t)
    return t.strip() + "\n"


def words(text):
    return len((text or "").split())


def count_lines(text, marker):
    return sum(1 for ln in (text or "").splitlines() if marker in ln)


def today():
    return store.now()[:10]
