"""checks — one door for every quality gate, so no caller ever assembles the list itself.

The app runs checks after a stage finishes and again after every targeted edit. Both go
through run_checks() and render whatever comes back, which is why the result shape is fixed
and boring: a name, a status, one line a human can read, and the exact offending items.

A check reports. It never rewrites. Keeping those two apart is what stops a gate from
quietly changing a draft it disagreed with, which would leave the user's approved text
altered by something they never saw run. Fixing is editing/'s job.

What the statuses mean:

    pass    nothing to act on
    warn    worth a human look, shipping it is a judgement call
    fail    wrong, and provably so from data we already hold

Only a check that can point at held data says fail: a link that is not in site_index.json,
a second H1, a paragraph that changed when one was meant to. Anything statistical stays at
warn. That is why the AI-writing detector can never fail a draft.
"""
import json
import os
import re
from urllib.parse import urlparse

from .. import store

# Words that carry no topic signal, so they are dropped before any overlap is measured.
# Left in, two sections about different things score as similar purely on their glue words.
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "what", "how", "why", "you",
    "your", "our", "are", "was", "were", "has", "have", "had", "will", "can", "not",
    "but", "its", "it's", "they", "them", "their", "there", "then", "than", "into",
    "out", "about", "over", "under", "who", "whom", "which", "when", "where", "all",
    "any", "each", "more", "most", "some", "such", "only", "own", "same", "too", "very",
    "one", "two", "get", "got", "make", "makes", "made", "use", "used", "using", "way",
    "ways", "does", "doing", "done", "here", "also", "just", "like", "his", "her",
}

# Query parameters that identify a click, not a page. Two URLs that differ only by these
# are the same page, and failing that difference trains people to ignore the link checks.
TRACKING_PREFIXES = ("utm_", "mc_", "pk_")
TRACKING_PARAMS = {"fbclid", "gclid", "msclkid", "ref", "referrer", "source", "igshid"}


# ---- result shape ----------------------------------------------------------------------

def result(name, status, detail, items=None):
    """The only shape a check may return. The screen renders these directly."""
    return {"name": name, "status": status, "detail": detail, "items": list(items or [])}


def item(where, what, fix):
    """One offending thing. `where` locates it, `what` quotes it, `fix` says what to do."""
    return {"where": where, "what": what, "fix": fix}


def worst(results):
    """The status the run as a whole deserves, so a caller can gate on one word."""
    statuses = {r.get("status") for r in results or []}
    for level in ("fail", "warn"):
        if level in statuses:
            return level
    return "pass"


# ---- text helpers ------------------------------------------------------------------------

def tokens(text):
    """Content words only, lowercased. Used wherever two pieces of text are compared."""
    return [w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(w) > 2 and w not in STOPWORDS]


def overlap(a, b):
    """Jaccard overlap of two token lists, 0.0 to 1.0.

    Jaccard rather than a raw hit count because it is symmetric: a long section and a short
    one that happen to share five words are not the same section, and a count would say
    they were.
    """
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def norm_url(url, base_domain=None):
    """Compare URLs the way a reader would: the same page whatever the scheme, the www or
    the tracking tail. A blueprint link differing from the index only by a trailing slash
    points at the same page, and failing it would be a false alarm every time.
    """
    u = (url or "").strip()
    if not u or u.startswith(("#", "mailto:", "tel:", "javascript:")):
        return ""
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        if not base_domain:
            return u.rstrip("/").lower()
        u = "https://" + base_domain.strip("/") + u
    elif "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", p.path or "")
    keep = []
    for part in (p.query or "").split("&"):
        if not part:
            continue
        key = part.split("=")[0].lower()
        if key in TRACKING_PARAMS or key.startswith(TRACKING_PREFIXES):
            continue
        keep.append(part)
    return host + path + (("?" + "&".join(sorted(keep))) if keep else "")


def is_same_site(url, base_domain):
    """True when a URL points at the company's own site, including root-relative hrefs."""
    if not base_domain:
        return False
    u = (url or "").strip()
    if u.startswith("/") and not u.startswith("//"):
        return True
    host = urlparse(u if "://" in u else "https://" + u).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    base = base_domain.lower()
    if base.startswith("www."):
        base = base[4:]
    return bool(host) and (host == base or host.endswith("." + base))


# ---- what the checks are allowed to read -------------------------------------------------

def site_index(ctx=None):
    """The crawl is the only record of which pages exist. A check that guesses instead is
    worse than no check, so this is the single place it is read."""
    ctx = ctx or {}
    if isinstance(ctx.get("site_index"), dict):
        return ctx["site_index"]
    return store.knowledge("site_index.json") or {}


def site_urls(ctx=None):
    """Returns (set of normalised URLs, bare domain). Empty set means we cannot verify."""
    idx = site_index(ctx)
    domain = (idx.get("domain") or "").strip().lower()
    urls = set()
    for page in idx.get("pages") or []:
        n = norm_url(page.get("url"), domain)
        if n:
            urls.add(n)
    return urls, domain


def brand_voice(ctx=None):
    ctx = ctx or {}
    if isinstance(ctx.get("brand_voice"), dict):
        return ctx["brand_voice"]
    return store.knowledge("brand_voice.json") or {}


def artifact(ctx, name):
    """Read a sibling artifact of the thing being checked.

    Checks need each other's inputs: a draft is judged against its blueprint, a blueprint
    against its research. The caller already passes chat_id and run_id, so the lookup
    happens here rather than every call site loading files first. A test passes the object
    straight in under either 'blueprint' or 'blueprint.json'.
    """
    ctx = ctx or {}
    for key in (name, name.split(".")[0]):
        if isinstance(ctx.get(key), (dict, list)):
            return ctx[key]
    cid, rid = ctx.get("chat_id"), ctx.get("run_id")
    if cid and rid:
        return store.load_artifact(cid, rid, name)
    return None


def primary_keyword(ctx=None, blueprint=None):
    """The one keyword the article is for. research.json holds it as an object, a hand
    written ctx may hold a bare string, and a blueprint may carry a copy. All three work."""
    ctx = ctx or {}
    candidates = [ctx.get("primary_keyword")]
    if isinstance(blueprint, dict):
        candidates.append(blueprint.get("primary_keyword"))
    research = artifact(ctx, "research.json")
    if isinstance(research, dict):
        candidates.append(research.get("primary_keyword"))
    for c in candidates:
        if isinstance(c, dict):
            c = c.get("keyword")
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""


# ---- loading the thing under test --------------------------------------------------------

def _load(value):
    """Accept a path, a JSON string, raw markdown or an already-parsed object.

    The app passes objects, the CLI passes paths, and tests pass literals. Sorting that out
    once here is cheaper than three call sites each getting it slightly wrong.
    """
    if value is None or isinstance(value, (dict, list)):
        return value
    text = str(value)
    looks_like_path = len(text) < 400 and "\n" not in text and os.path.exists(text)
    if looks_like_path:
        with open(text, encoding="utf-8") as f:
            raw = f.read()
        if text.endswith(".json"):
            return json.loads(raw)
        return raw
    return text


def _as_blueprint(value):
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Blueprint is not JSON. Got %d characters of text." % len(value))
        if not isinstance(parsed, dict):
            raise ValueError("Blueprint must be a JSON object, got %s." % type(parsed).__name__)
        return parsed
    raise ValueError("Cannot read a blueprint from %s." % type(value).__name__)


def _as_markdown(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("draft", "markdown", "text", "body", "content"):
            if isinstance(value.get(key), str):
                return value[key]
    return json.dumps(value, indent=2, ensure_ascii=False)


# ---- the entry point ---------------------------------------------------------------------

def run_checks(kind, path_or_text, previous=None, ctx=None):
    """Run every check for `kind` and return the list of results.

    kind is 'blueprint' or 'draft'. path_or_text is a path, an object or the raw text.
    previous is the version before an edit, which is what lets the draft prove that only
    the targeted block moved. ctx carries chat_id and run_id so checks can read the
    blueprint, the research and the site index they judge against.
    """
    ctx = dict(ctx or {})
    doc = _load(path_or_text)
    prev = _load(previous)

    if kind == "blueprint":
        from . import blueprint_checks
        return blueprint_checks.run(_as_blueprint(doc), previous=_as_blueprint(prev), ctx=ctx)
    if kind == "draft":
        from . import draft_checks
        return draft_checks.run(_as_markdown(doc), previous=_as_markdown(prev), ctx=ctx)
    raise ValueError("Unknown check kind %r. Use 'blueprint' or 'draft'." % (kind,))
