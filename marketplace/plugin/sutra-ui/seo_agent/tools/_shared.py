"""_shared.py — the bits all four tools need, kept in one place.

Not a tool. The leading underscore says so: registry.py never points at this file.

Three jobs. It reads the Knowledge files tolerantly, because index_site and learn_voice
write them and their exact shape can change without every tool breaking. It loads prompt
files so no prompt is ever built inline in code. And it holds the substep emitter, because
these tools take minutes and a silent minute looks like a hang.
"""
import json
import os

from .. import store

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PROMPTS = os.path.join(APP, "prompts")


# ---- progress --------------------------------------------------------------------------

def reporter(ctx, tool=""):
    """Hand back a say(label, note) for one tool.

    The loop names the step it started but does not put that id in ctx, so the tool name
    is the fallback parent. Without a parent the substeps float free of the step they
    belong to and the UI cannot group them.
    """
    parent = ctx.get("step_id") or tool or None

    def say(label, note=""):
        try:
            ctx["emit"](type="substep_finished", parent=parent, label=label, note=note or "")
        except Exception:
            # A broken emitter must never take down real work that already succeeded.
            pass
    return say


def substep(ctx, label, note=""):
    """One-off progress line, for a tool that does not want to hold a reporter."""
    reporter(ctx)(label, note)


def dfs_mode(dfs):
    """live, demo or off. Demo data is real-shaped and fake, so callers must say so."""
    if dfs is None:
        return "off"
    try:
        if dfs.available():
            return "live"
        return "demo" if getattr(dfs, "demo_mode", lambda: False)() else "off"
    except Exception:
        return "off"


def num(v):
    """DataForSEO writes 0 where it means "not known". Treat that as missing for display,
    so a blank field never reads as a measured zero."""
    return None if v in (None, 0, 0.0, "") else v


# ---- prompts ---------------------------------------------------------------------------

def load_prompt(name):
    """Read prompts/<name>.md and fold in the shared writing rules, so the ban list is
    written once and every prompt that needs it gets the same copy."""
    with open(os.path.join(PROMPTS, name + ".md"), encoding="utf-8") as f:
        tpl = f.read()
    if "{{WRITING_RULES}}" in tpl:
        with open(os.path.join(PROMPTS, "_writing_rules.md"), encoding="utf-8") as f:
            tpl = tpl.replace("{{WRITING_RULES}}", f.read().strip())
    return tpl


def fill(tpl, **tokens):
    for k, v in tokens.items():
        tpl = tpl.replace("{{%s}}" % k.upper(), "" if v is None else str(v))
    return tpl


def plural(n, word, many=None):
    """These notes are read by a person, and "1 keywords" reads like a bug."""
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def bullets(items, empty="(nothing on file)"):
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    return "\n".join("- " + i for i in items) if items else empty


# ---- knowledge -------------------------------------------------------------------------

def brand_voice():
    return store.knowledge("brand_voice.json") or {}


def voice_block(voice=None, limit=2500):
    """The voice profile as prompt text. Dumped whole rather than field by field, because
    learn_voice owns that shape and this file should not have an opinion about it."""
    voice = brand_voice() if voice is None else voice
    if not voice:
        return "(no voice profile on file, so write plainly and make no claims about them)"
    out = json.dumps(voice, indent=2, ensure_ascii=False)
    return out[:limit] + ("\n... (truncated)" if len(out) > limit else "")


def company_name():
    v = brand_voice()
    idx = store.knowledge("site_index.json") or {}
    if isinstance(idx, dict):
        dom = idx.get("domain") or ""
    else:
        dom = ""
    return v.get("company") or dom or "this company"


def site_index():
    """Normalise the site index to {"domain": str, "pages": [page]}.

    Accepts a bare list of pages too, so an older or simpler index_site still works.
    """
    raw = store.knowledge("site_index.json")
    if isinstance(raw, list):
        return {"domain": "", "pages": [p for p in raw if isinstance(p, dict)]}
    if isinstance(raw, dict):
        pages = raw.get("pages") or raw.get("urls") or []
        return {"domain": raw.get("domain", ""),
                "pages": [p for p in pages if isinstance(p, dict)]}
    return {"domain": "", "pages": []}


def _page_keywords(page):
    """Pull [(keyword, position)] out of a page.

    index_site writes one best keyword per page as top_keyword plus position. The list
    form is accepted too, so a richer index later does not break this.
    """
    out = []
    if page.get("top_keyword"):
        out.append((page["top_keyword"], page.get("position")))
    for kw in (page.get("keywords") or page.get("ranks_for") or []):
        if isinstance(kw, str):
            out.append((kw, None))
        elif isinstance(kw, dict):
            term = kw.get("keyword") or kw.get("term") or ""
            if term:
                out.append((term, kw.get("position")))
    return out


def page_summary(page):
    return (page.get("covers") or page.get("summary") or page.get("description")
            or page.get("title") or "")


def page_url(page):
    return page.get("url") or page.get("loc") or ""


def normalise_url(url):
    """Compare URLs without tripping over scheme or a trailing slash."""
    u = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
            break
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def already_ranking(index=None, max_position=20):
    """The keywords this site already holds a top-20 spot for. Used as a hard filter, not
    as advice to the model: a rule the code enforces is a rule."""
    index = site_index() if index is None else index
    held = {}
    for page in index.get("pages", []):
        for term, pos in _page_keywords(page):
            # 0 is index_site's "not known", not a number-one spot.
            if not pos or pos > max_position:
                continue
            key = term.strip().lower()
            if key and (key not in held or pos < held[key][0]):
                held[key] = (pos, page_url(page))
    return held


def covered_topics(index=None, limit=60):
    """One line per existing page, for "do not propose what we already have"."""
    index = site_index() if index is None else index
    lines = []
    for page in index.get("pages", [])[:limit]:
        title = page.get("title") or page_url(page)
        if not title:
            continue
        summary = page_summary(page)
        lines.append("%s%s" % (title, (": " + summary[:120]) if summary and summary != title else ""))
    return lines


def link_candidates(index=None, topic="", limit=40):
    """Real internal-link targets, most relevant first.

    Relevance is plain word overlap with the topic. Crude on purpose: its only job is to
    decide which 40 of 300 pages the model sees, and the model still picks from real URLs.
    """
    index = site_index() if index is None else index
    words = {w for w in (topic or "").lower().replace("-", " ").split() if len(w) > 3}
    scored = []
    for page in index.get("pages", []):
        url = page_url(page)
        if not url:
            continue
        title = page.get("title") or url
        blob = (title + " " + page_summary(page)).lower()
        score = sum(1 for w in words if w in blob)
        scored.append((score, {"url": url, "title": title,
                               "covers": page_summary(page)[:160]}))
    scored.sort(key=lambda s: -s[0])
    return [p for _, p in scored[:limit]]
