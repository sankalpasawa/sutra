"""_common.py — the settings hub and the helpers every write step shares.

The write phase's config.py held every tunable in one place, with the comment that explained why the
number is what it is. Those constants live here now, same names, same values, same comments where the
comment stops a real mistake. Every step imports this module and nothing else re-declares a number.

Also here: the card index (cards.json -> {id: card}), the article context (title, angle, spine, the
world, the persona, from research.json and blueprint.json), prompt filling, the "long call" guard for
whole-article model calls, and the one door to the network (fetch / alive) so tests can close it.
"""
import contextlib
import json
import os
import re
import threading

from .. import llm, store
from ..tools import _shared as sh

# ---- the paragraph maths (architect + writer both design on these) --------------------------------
WORDS_PER_SENTENCE = 25             # the house sentence cap
SENTENCES_PER_PARAGRAPH = 5         # -> a paragraph is ~125w. 4 -> 5: the human articles run 3-5 a paragraph
PARAGRAPHS_PER_SECTION = 4          # -> a section is ~400w; also the budget the fat-paragraph fixer spends
MIN_WORDS_PER_SUBHEAD = 200         # the floor under a sub-heading; below it an H3 is a label on a paragraph
WORDS_PER_SECTION = 300             # the architect is TOLD this, never held to it: budget/300 = section count
ARCH_BAND_SHRINK = 0.10             # aim low: every section of the last run overshot, so allocate under the middle
SHAPE_MIN_YARDSTICK_PCT = 60        # a comparison option needs info for >= this % of yardsticks to keep its section
LISTICLE_MAX_ITEMS = 12             # the hard ceiling on how many items a listicle may carry
LISTICLE_SUPPORTING_SECTIONS = 3    # supporting sections reserved BEFORE dividing words among the items
LISTICLE_MIN_ITEM_WORDS = 200       # below this an item is a stub
LISTICLE_MIN_ITEMS = 5              # fewer than this and it has stopped being a list

# ---- the planner ----------------------------------------------------------------------------------
SELECT_H3_COVERAGE = 0.45           # an H2 survives at >= this fraction of tagged H3s
MAX_TABLE_STAKES = 7                # how many "every ranking page covers this" topics reach the architect
PAGE_CHARS = 8000                   # how much of a source page the judge reads
VERIFY_BATCH = 80                   # cards per verify-worthy AI call
FETCH_TIMEOUT = 15.0

# ---- the company's own material -------------------------------------------------------------------
BRAND_RESEARCH_CAP = 4              # per article
BRAND_RESEARCH_PER_SECTION = 1
BRAND_RESULT_CAP = 1                # per article; usually 0
BRAND_FACTS_SHOWN = 12              # existing facts per group shown to the placement judge

# ---- word allocation ------------------------------------------------------------------------------
ALLOC_CARDS_PER_SECTION = 60        # facts shown per section (a display cap, not a tuning knob)
ALLOC_GLOSS_CHARS = 200
OVER_PCT = 0                        # the overwrite buffer. Measured: blending trims nothing, so it is 0

# ---- section keywords -----------------------------------------------------------------------------
SUGGEST_LIMIT = 80                  # phrases pulled per seed
CAND_SHOWN = 25                     # candidates shown to the picker, best-by-volume
VOL_FLOOR = 100                     # a section keyword needs >= this monthly volume
KD_CEIL = 40                        # ... and difficulty below this
MIN_DFS_BALANCE = 0.5               # below this DataForSEO balance, paid lookups are skipped and said so

# ---- headings -------------------------------------------------------------------------------------
MAX_HEADINGS_PER_KEYWORD = 2        # at most N asked for, AT LEAST N enforced in code
FIGURE_HEADING_SHARE = 0.34         # 1 in 3 headings may carry a figure; floor 1
MAX_HEADING_CHARS = 60              # a soft target: over-length is RECORDED, never rejected

# ---- the writer -----------------------------------------------------------------------------------
BODY_CARD_CHARS = 10000000          # per-card verbatim shown to the writer (uncapped)
BODY_MAX_STATS = 3                  # statistics per SECTION (prompt + flag)
BLEND_SENTENCE_WORDS = 25           # flag a sentence longer
BLEND_PARA_SENTENCES = 4            # flag a paragraph longer
BLEND_FLAG_SAMPLE = 6               # flagged lines shown per section
BLEND_WRAPPER_WORDS = 600           # the intro, FAQ and close are written after blend; aim below the band
BLEND_TAG_LOSS_BLOCK = 0.25         # losing a quarter of the tags is not editing
COHERENCE_WORD_TOLERANCE = 5        # % the length may move; a WARNING, never a block
COHERENCE_TAG_LOSS_BLOCK = 0.25
WRAP_FAQ_WORDS = 40                 # an FAQ answer is what a search engine lifts
WRAP_FAQ_COUNT = 5                  # a ceiling, not a target
WRAP_VOICE_FILES = ("brand-voice.md", "style-guide.md", "writing-examples.md")
WRAP_VOICE_CHARS = 6000             # per file, into the wrapper prompt
WRAP_FEATURES_CHARS = 8000
WRAP_CTA_CHARS = 6000
QUICK_MIN = 60
QUICK_MAX = 110
READABLE_EASE = 45.0                # Flesch band floor; the human articles score 28-35, so no chasing 60
READABLE_EASE_MAX = 72.0            # above this the prose went clipped, not clear
READABLE_WORDS_PER_FACT = 110       # how much room each kept fact gets
READABLE_CEILING = 2100             # at most this, and never longer than it came in
READABLE_EXAMPLES_CHARS = 6000      # of brand/writing-examples.md shown to the rewrite as the bar
CITATION_MAX_REPEATS = 3            # times ONE source may be marked
EXTERNAL_LINKS_MAX = 4              # visible outbound links per article

# ---- links ----------------------------------------------------------------------------------------
LINK_ALPHA = 0.5                    # title weight in the blend; 1-ALPHA is body
LINK_N_RETRIEVE = 40                # dense candidates handed to the reranker
LINK_PER_SECTION = 8                # shortlist size shown to the judge
LINK_RERANK_DOC_CHARS = 4000        # per-page text sent to rerank
LINK_EXCERPT_CHARS = 800            # per-page opening shown to the judge
LINK_MIN_SCORE = 0.0                # the floor. 0.0 = OFF, deliberately: pick it from measured scores
LINK_WEAK_SCORE = 0.45              # display only: a placed link under this is flagged weak
WORDS_PER_INTERNAL_LINK = 400
MIN_INTERNAL_LINKS = 3
INLINE_LINKS_CAP = 5

# ---- model calls ----------------------------------------------------------------------------------
LONG_CALL_TIMEOUT = 2400.0          # a whole-article round trip needs more than one section's timeout

ARCHETYPES = {
    "answer-bait-definitional", "how-to-guide", "listicle", "comparison-rankings", "glossary",
    "data-benchmark-report", "template-resource", "common-spine",
}
SIMPLE_ROAD = {"answer-bait-definitional", "how-to-guide", "common-spine", "data-benchmark-report", "glossary"}

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS = os.path.join(os.path.dirname(HERE), "prompts", "write", "formats")

_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?%?")
_MDLINK = re.compile(r"\[([^\]\[]+)\]\((https?://[^)\s]+)\)")


# ---- prompts --------------------------------------------------------------------------------------

def prompt(name, **kw):
    """prompts/write/<name>.md, filled. Keys are upper-cased by sh.fill."""
    return sh.fill(sh.load_prompt("write/" + name), **kw)


def format_path(archetype):
    return os.path.join(FORMATS, archetype + ".md")


def format_rules(archetype):
    """The format rulebook, minus its developer header: everything from the first '##' heading on."""
    try:
        text = open(format_path(archetype), encoding="utf-8").read()
    except OSError:
        return "(no format rules on file)"
    i = text.find("\n## ")
    return (text[i + 1:] if i >= 0 else text).strip()


@contextlib.contextmanager
def long_call():
    """Whole-article calls (blend, coherence, readable) send the article and get it back. One section's
    timeout kills that mid-thought, so it is raised for the duration and put back afterwards."""
    old = llm.CLI_TIMEOUT
    llm.CLI_TIMEOUT = max(old, LONG_CALL_TIMEOUT)
    try:
        yield
    finally:
        llm.CLI_TIMEOUT = old


# ---- ids, numbers, text ---------------------------------------------------------------------------

def nid(x):
    """Normalise a card id — 'id1', 'c1', ' 1 ', 1 all become the int 1."""
    if isinstance(x, int):
        return x
    s = str(x).strip().lower()
    if s.startswith("id"):
        s = s[2:]
    elif s.startswith("c") and s[1:].strip().isdigit():
        s = s[1:]
    try:
        return int(s)
    except ValueError:
        return x


def has_number(t):
    """A real number: two or more digits somewhere in a numeric token."""
    return any(len(re.sub(r"[^\d]", "", m)) >= 2 for m in _NUM.findall(t or ""))


def plain_links(text):
    """Markdown links reduced to their anchor text."""
    return _MDLINK.sub(lambda m: m.group(1), text or "")


def company():
    c = sh.company()
    return {"brand": c["brand"], "about": c.get("brand_oneliner") or c.get("about") or "(no description on file)",
            "domain": c.get("domain") or ""}


# ---- the cards ------------------------------------------------------------------------------------

def card_index(cards):
    """cards.json -> {int id: card}. Every card also carries card_id, the key the ported steps read."""
    idx = {}
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        cid = nid(c.get("id", c.get("card_id")))
        if not isinstance(cid, int):
            continue
        c = dict(c)
        c["card_id"] = cid
        c.setdefault("gloss", "")
        c.setdefault("verbatim", "")
        c.setdefault("source_urls", [])
        idx[cid] = c
    return idx


def cards_of(idx, ids_):
    return [idx[nid(i)] for i in ids_ if nid(i) in idx]


# ---- the article context ---------------------------------------------------------------------------

def context(blueprint, research):
    """title, angle, spine, about, not_about, persona: plain strings, never None."""
    world = (research or {}).get("world") or {}
    return {"title": str((research or {}).get("topic") or (blueprint or {}).get("h1") or "").strip(),
            "angle": str((research or {}).get("angle") or "").strip(),
            "spine": str((research or {}).get("spine") or "").strip(),
            "about": str(world.get("about") or "").strip(),
            "not_about": str(world.get("not_about") or "").strip(),
            "persona": persona(blueprint, research)}


def or_na(ctx, key):
    return ctx.get(key) or "(not available for this run)"


def persona(blueprint, research):
    """WHO the article is for, prompt-ready: the chosen persona plus its row in brand/persona.md."""
    p = (blueprint or {}).get("persona") or (research or {}).get("persona") or {}
    if isinstance(p, dict):
        name, lens = str(p.get("name") or "").strip(), str(p.get("lens") or "").strip()
    else:
        name, lens = str(p).strip(), ""
    row = ""
    pf = sh.brand_file("persona.md")
    if name and pf:
        for line in pf.splitlines():
            if line.strip().startswith("|") and name.lower() in line.lower():
                row = line.strip()
                break
    return "\n".join(x for x in [("%s — %s" % (name, lens)) if lens else name, row] if x) \
        or "(general professional reader)"


def persona_short(blueprint, research):
    p = (blueprint or {}).get("persona") or (research or {}).get("persona") or {}
    if isinstance(p, dict):
        return ("%s — %s" % (p.get("name", ""), p.get("lens", ""))).strip(" —") or "(no persona on file)"
    return str(p) or "(no persona on file)"


# ---- the network, behind one door -----------------------------------------------------------------
# Tests replace these two names and nothing in the write phase ever reaches the network. The source
# verifier reads a page; the links pass asks whether a page answers. Nothing else here fetches.

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_HOST_LOCKS, _HOST_LAST, _LOCKS_GUARD = {}, {}, threading.Lock()
FETCH_GAP = 1.5           # seconds between hits on the SAME host
FETCH_RETRIES = 2         # a throttled 200 reads as "wrong" -> retry


def _fetch_once(url, timeout=FETCH_TIMEOUT):
    import html as _html
    import httpx
    if url.lower().split("?")[0].endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")):
        return "__ERR__NotHTML"
    try:
        r = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
        if r.status_code >= 400:
            return "__ERR__HTTP%d" % r.status_code
        ctype = (r.headers.get("content-type") or "").lower()
        if ctype and "html" not in ctype and "text/plain" not in ctype:
            return "__ERR__NotHTML"
        raw = r.text[:3_000_000]
        if raw.lstrip()[:5] == "%PDF-":
            return "__ERR__NotHTML"
        raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
        return _html.unescape(re.sub(r"<[^>]+>", " ", raw))
    except Exception as e:      # noqa: BLE001 — network weather of every kind reads as unloadable
        return "__ERR__%s" % type(e).__name__


def fetch(url, timeout=FETCH_TIMEOUT, retries=None):
    """The page as plain text, or an __ERR__ marker. One request at a time per HOST, with a gap and a
    retry: bursting a host makes it serve a wall page (a 200 with no content), which used to read as
    'the claim is wrong' and delete a correct source."""
    import time
    retries = FETCH_RETRIES if retries is None else retries
    host = url.split("/")[2].lower() if "://" in url else url
    with _LOCKS_GUARD:
        lock = _HOST_LOCKS.setdefault(host, threading.Lock())
    with lock:
        out = "__ERR__none"
        for attempt in range(retries + 1):
            gap = FETCH_GAP - (time.time() - _HOST_LAST.get(host, 0))
            if gap > 0:
                time.sleep(gap)
            out = FETCH_ONCE(url, timeout)
            _HOST_LAST[host] = time.time()
            if not out.startswith("__ERR__") and len(out.strip()) >= 500:
                return out
            if attempt < retries:
                time.sleep(2.0 * (attempt + 1))
        return out


# Codes that mean "you are a bot", NOT "this page is gone". Academic publishers and news sites answer
# a scripted request with 403 while serving the identical url to a browser. Only a genuine "not there"
# (404/410) or a failure to connect at all counts as dead.
BOT_BLOCKED = {401, 403, 405, 406, 429, 451}


def _alive_once(url):
    import httpx
    try:
        r = httpx.head(url, headers={"User-Agent": _UA}, timeout=12.0, follow_redirects=True)
        if r.status_code in (405, 404) or r.status_code >= 500:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=12.0, follow_redirects=True)
        if r.status_code in (404, 410):
            return False
        return True                      # anything else, bot blocks included, is a page that exists
    except Exception:                    # noqa: BLE001 — could not connect at all
        return False


# The two names tests swap out. Every fetch in the write phase goes through them.
FETCH_ONCE = _fetch_once
ALIVE = _alive_once


def alive(url):
    return ALIVE(url)


# ---- the run's work files -------------------------------------------------------------------------

def work_name(step):
    return "work-%s.json" % step


def load_work(ctx, step):
    return store.load_artifact(ctx["chat_id"], ctx["run_id"], work_name(step))


def save_work(ctx, step, data):
    store.save_artifact(ctx["chat_id"], ctx["run_id"], work_name(step), data)
    return data


def deep(obj):
    return json.loads(json.dumps(obj))
