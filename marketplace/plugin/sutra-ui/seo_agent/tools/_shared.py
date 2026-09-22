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

    def say(label, note="", **extra):
        # `extra` CARRIES FACTS THE SENTENCE ALSO CONTAINS, so a reader never has to parse prose.
        # Added 2026-09-10: the Knowledge screen was telling "waiting on a cooldown" apart from
        # "working" by regexing the words "waiting 120s" out of a note. That worked and was one
        # reworded sentence away from silently turning every cooldown back into something that
        # looks like progress — with no test anywhere able to catch it, because the sentence and
        # the reader live in different packages. A field cannot be reworded by accident.
        try:
            ctx["emit"](type="substep_finished", parent=parent, label=label, note=note or "",
                        **extra)
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


# ---- the keys, asked about BEFORE a tool spends somebody's evening ----------------------
#
# WHY THIS IS HERE AND NOT INSIDE ONE TOOL (owner, 2026-09-22). A friend of his onboarded a new
# company with neither key connected. Nothing said so. Setup ran a long time, the asset engine
# sorted 200 Reddit posts into 151 fragments because it could not embed a single one, and the idea
# sheet came out empty. The only two signals were a "!" on a sidebar item he had no reason to click
# and one line buried mid-log, after the damage was done.
#
# The lesson was already learned and written down. run_research's own refusal note, 2026-09-09:
#
#     "why should it even go further if there is no DataForSEO? It never misfires. It is
#      pointless, a very bad experience."
#
# It was applied to run_research and nowhere else. Measured across tools/ on 2026-09-22:
# run_research checked; build_assets, onboard, learn_brand and suggest_topics did not. So the
# entire first-run path -- every new person's first impression of this agent -- still failed in
# exactly the way that note describes.
#
# THE TWO KEYS FAIL DIFFERENTLY AND MUST NOT BE TREATED ALIKE:
#   * DataForSEO is money. Without it there are no real numbers at all, and a run that carries on
#     produces an article built on placeholders. That is a REFUSAL.
#   * Voyage is meaning. Without it the engine still runs, but it groups by shared words instead
#     of by what things mean, so the result is worse rather than absent. That is a WARNING, said
#     before the work instead of inside its wreckage -- a person may well want to carry on.

def keys_missing():
    """{"dataforseo": bool, "voyage": bool} -- which of the two are not connected right now.

    Asked live, never cached: the Connections tab can be filled in while the app is running, and
    somebody who pastes a key and presses go must not be told about the state before they did.

    Fails OPEN on both. A check that cannot run must not become a refusal of its own: the paid
    calls already fail loudly on their own, and NoVoyageKey is already caught where it matters.
    """
    out = {"dataforseo": False, "voyage": False}
    try:
        from . import dfs
        out["dataforseo"] = not dfs.available()
    except Exception:                      # noqa: BLE001 -- see "fails OPEN" above
        pass
    try:
        from . import voyage
        voyage.get_key()
    except ImportError:
        pass
    except Exception:                      # noqa: BLE001 -- NoVoyageKey, or anything else
        out["voyage"] = True
    return out


# What each missing key COSTS, in the words the person reads. Kept here rather than at each call
# site so the same sentence is said wherever it is said.
KEY_HELP = {
    "dataforseo": ("DataForSEO is not connected, so there are no real search numbers to work from.",
                   "Add dataforseo_login and dataforseo_password in Connections. Or say \"use "
                   "placeholder numbers\" and it runs on demo figures, every one of them flagged."),
    "voyage": ("No Voyage key, so things can only be grouped by the words they share, not by what "
               "they mean. Two people describing the same problem in different words count as two "
               "problems.",
               "It is free at voyageai.com; add it in Connections. Carrying on without it works, "
               "it is just cruder."),
}


def refuse_missing_keys(needs=("dataforseo",), missing=None):
    """The refusal a tool returns when a key it truly needs is absent, or None to carry on.

    The SAME SHAPE run_research has returned since 2026-09-09, and the same shape learn_brand uses
    when there is no measured traffic, so loop.py already knows how to put it on screen: a summary,
    and an error naming what is missing AND both ways out. A refusal that does not say how to fix
    itself is just a wall.
    """
    missing = keys_missing() if missing is None else missing
    gone = [k for k in needs if missing.get(k)]
    if not gone:
        return None
    said = " ".join("%s %s" % KEY_HELP[k] for k in gone)
    return {"summary": "Not started: %s is not connected." % " and ".join(gone),
            "error": said}


def warn_missing_keys(say, warn=("voyage",), missing=None):
    """Say what a missing key will cost, BEFORE the work rather than in its wreckage.

    `say` is the tool's own reporter, so this lands in the chat where the person is already
    looking, which is the entire complaint. Returns what it warned about.
    """
    missing = keys_missing() if missing is None else missing
    gone = [k for k in warn if missing.get(k)]
    for k in gone:
        why, fix = KEY_HELP[k]
        try:
            say(why, fix)
        except Exception:                  # noqa: BLE001 -- a warning must never break a run
            pass
    return gone


def keys_stamp(missing=None):
    """What was connected when something was built, small enough to keep beside its output.

    `build_assets` skips a builder whose files already exist, which is right for an ordinary re-run
    and WRONG the moment a key arrives: the work it skips is precisely the work the new key would
    have fixed. So each builder records what it had, and a later run compares. See build_assets.
    """
    missing = keys_missing() if missing is None else missing
    return {k: not v for k, v in missing.items()}


def keys_improved(then, now=None):
    """True when a key that was NOT connected when something was built is connected now.

    Only ever upwards. Losing a key is not a reason to throw away work that was built properly.
    """
    if not isinstance(then, dict):
        return False
    now = keys_stamp() if now is None else now
    return any(now.get(k) and not then.get(k) for k in now)


def num(v):
    """DataForSEO writes 0 where it means "not known". Treat that as missing for display,
    so a blank field never reads as a measured zero."""
    return None if v in (None, 0, 0.0, "") else v


# ---- prompts ---------------------------------------------------------------------------

def load_prompt(name):
    """Read prompts/<name>.md (name may carry a subfolder, "write/blend") and fold in the
    shared writing rules, so the ban list is written once and every prompt that needs it
    gets the same copy."""
    with open(os.path.join(PROMPTS, *name.split("/")) + ".md", encoding="utf-8") as f:
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

def load_competitors():
    """knowledge/competitors.json, in any of the three shapes it has been saved in: a bare list of
    domain strings (the oldest saves), {"competitors": [...]} of strings, or {"competitors": [...]}
    of {domain, why, last_used} dicts. Returns a list of {"domain": ..., "last_used": ..., "why": ...}.

    Moved here from tools/suggest_topics.py on 2026-09-17 (Aparna's review), which is where this
    parsing was written and where it stayed the ONLY reader of the file. The write phase never saw
    the rival list, so nothing stopped a rival becoming the authority for a headline stat or landing
    in a heading (write/write_body.py `_rivals_block`, write/headings.py `guard_rivals`). Same
    parsing, one place, so suggest_topics and the writer can never read the file two different ways.
    """
    raw = store.knowledge("competitors.json") or []
    if isinstance(raw, dict):
        raw = raw.get("competitors") or []
    rows = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            rows.append({"domain": item.strip(), "last_used": None})
        elif isinstance(item, dict) and item.get("domain"):
            rows.append({"domain": item["domain"].strip(),
                         "last_used": item.get("last_used"),
                         "why": item.get("why", "")})
    return rows


def brand_voice():
    """The voice profile as a dict: {company, summary, traits, avoid, examples, ...}.

    Derived from the brand pack's own brand-voice.md, which is what learn_brand actually
    writes. Found live 2026-09-04: this used to read a legacy knowledge/brand_voice.json
    that the ported setup never writes, so every caller silently got {} and suggest_topics
    failed with "no brand voice profile" on a fully built brand pack.
    """
    legacy = store.knowledge("brand_voice.json")
    if isinstance(legacy, dict) and legacy:
        return legacy
    text = brand_file("brand-voice.md")
    if not text.strip():
        return {}
    try:
        from ..brand import brand_voice as _bv
        return _bv.profile(company(), text) or {}
    except Exception:  # noqa: BLE001 — a derived profile must never break the caller
        return {"company": (company() or {}).get("brand", ""), "summary": " ".join(text.split()[:120])}


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


# ---- the company, the catalogue bodies, the brand files ----------------------------------------

def company():
    """knowledge/brand/company.json, with the fields every prompt expects present."""
    rec = store.knowledge("brand/company.json") or {}
    idx = store.knowledge("site_index.json") or {}
    dom = rec.get("domain") or (idx.get("domain") if isinstance(idx, dict) else "") or ""
    brand = rec.get("brand") or (brand_voice().get("company") if brand_voice() else "") or dom or "this company"
    return {"brand": brand, "domain": dom,
            "wordpress_url": rec.get("wordpress_url") or "",
            "brand_oneliner": rec.get("brand_oneliner") or "",
            "niche_definition": rec.get("niche_definition") or "",
            "location_name": rec.get("location_name") or "United States",
            "language_code": rec.get("language_code") or "en",
            "about": rec.get("about") or ""}


_BODIES = {"mtime": None, "rows": None}


def _content_db_path():
    return os.path.join(store.knowledge_dir(), "content-database.jsonl")


def pages_with_bodies():
    """[(url, title, body)] for every page whose text the crawl saved. Cached per process,
    refreshed when the file changes."""
    p = _content_db_path()
    try:
        m = os.stat(p).st_mtime
    except OSError:
        return []
    if _BODIES["mtime"] != m or _BODIES["rows"] is None:
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("url") and (d.get("body") or "").strip():
                    rows.append((d["url"], d.get("title") or "", d["body"]))
        _BODIES["mtime"], _BODIES["rows"] = m, rows
    return list(_BODIES["rows"])


def page_bodies():
    """{url without trailing slash: body}"""
    return {u.rstrip("/"): b for u, _t, b in pages_with_bodies()}


def brand_file(name):
    """knowledge/brand/<name> as text, or "" when it is not there yet."""
    v = store.knowledge("brand/" + name)
    return v if isinstance(v, str) else ""


def memory_block():
    """The user's standing rules as a bulleted list for a prompt, or "(none)"."""
    rules = store.memory_rules()
    return "\n".join("- " + r["text"] for r in rules) if rules else "(none)"
