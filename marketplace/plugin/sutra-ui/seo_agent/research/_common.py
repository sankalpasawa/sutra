"""_common.py — what every research step shares: the original engine's knobs, the resume helper,
the prompt filler, and the small parsers the steps lean on.

Not a step. The leading underscore says so. The knobs are kept with the original's comments so a
reader of 10-dataforseo/12-gap-check/13-research-structure/14-research-conductor config files finds
the same names and the same numbers here.
"""
import os
import re

from .. import store
from ..tools import _shared as sh

# ---- 10-dataforseo/scripts/config.py -------------------------------------------------------------
# Engine method knobs — NOT company facts. One constant pair everywhere: volume >= 100, KD <= 40
# (13-research-structure uses the same pair).
VOL_FLOOR = 100              # Step 2: keep keywords with monthly volume >= this
KD_CEIL = 40                 # Step 2: keep keywords with keyword_difficulty <= this
TIGHT_LIMIT = 200            # Step 1 — TIGHT net (keyword_suggestions, one call per seed): phrases per seed
SCORE_BATCH_KW = 60          # Step 3: keywords per scorer call (BATCH in s3_score.py)
SERP_DEPTH = 20              # Step 4 — SERP on the primary
PAA_CLICK_DEPTH = 3
PAGES_TO_READ = 3            # Step 5: how many top URLs to free-fetch
HEADINGS_PER_PAGE = 15       # Step 5: h1-h3 kept per page (the original's cap)
# Credit guard (pre-flight): below this balance the paid run does not start. The original used $1;
# the agent contract sets $0.50.
MIN_CREDITS = 0.50
# Spoke ranking (Step 3 judge): score = W_REL*(relevance/10) + W_VOL*volume(log-normalized) + W_KD*((100-KD)/100).
SPOKE_W_RELEVANCE = 0.5      # same-cluster relevance from the judge (0-10) — dominates, so big-but-generic heads lose
SPOKE_W_VOLUME = 0.25        # search volume, log-normalized (heavy-tailed, so raw min-max would over-reward one giant)
SPOKE_W_KD = 0.25            # ease = (100-KD)/100 (lower difficulty = higher score)
SPOKE_MIN_RELEVANCE = 3      # HARD FLOOR: keep only spokes with relevance >= this (0-2 = off-cluster → dropped)
MAX_SPOKES = 3               # 14-research-conductor: spokes kept per hub

# ---- 14-research-conductor/scripts/config.py -----------------------------------------------------
CANNIB_RANK_MAX = 10         # flag only if we rank in the top N (page 1): that is where a second page splits our traffic

# ---- the evidence engine (the honest substitute for 11-storm, which is vendored and cannot ship) --
EVIDENCE_SERP_DEPTH = 10     # organic results read per evidence keyword
EVIDENCE_MAX_SECONDARY = 6   # secondary keywords searched besides the primary
EVIDENCE_MAX_PAGES = 24      # cap on pages fetched per evidence round
PASSAGE_CHARS = 1200         # the original retriever's passage size ...
PASSAGES_PER_PAGE = 14       # ... and its cap per page
HARVEST_RETRIES = 2          # 13: re-run a page that yields 0 cards this many extra times
PAGE_FETCH_WORKERS = 4       # parallel page reads (free)

# ---- 12-gap-check/scripts/config.py --------------------------------------------------------------
JUDGED_TYPES = ("gap_we_own",     # competitor-read -> gaps_to_own (THE priority — the differentiator)
                "winner_h2",      # competitor-read -> winners_common_h2s (table stakes)
                "aio_subtopic")   # SERP extract -> AI Overview "what it covers" (the answer skeleton)
VALID_VERDICTS = ("covered", "no", "partial")
MISS_VERDICTS = ("no", "partial")
GAP_MAX_QUERIES = 3          # hard cap at 3

# ---- own pages via the Voyage index (02-asset-engine/5-reuse-check + 14/reuse_one.py) -----------
N_RETRIEVE = 40              # dense candidates before the reranker
RERANK_DOC_CHARS = 4000      # chars of each page the reranker reads (title[:200] + body)
TOPK = 7                     # pages kept after reranking
ALPHA = 0.5                  # title weight in the blended score
JUDGE_DOC_CHARS = 3000       # chars of each page the reuse judge reads (reuse_one.DOC_CHARS)
REUSE_VERDICTS = ("Already have it", "Improve existing", "Build from parts", "Brand new")
LOCALES = {"de", "fr", "es", "it", "pt", "nl", "pl", "ru", "ja", "zh", "ko", "ar", "tr", "sv", "da",
           "fi", "no", "cs", "hu", "ro", "el", "he", "id", "th", "vi", "uk", "hi", "ms"}

# ---- 13-research-structure/scripts/config.py -----------------------------------------------------
SCORE_BATCH = 30             # cards per scoring call
SCORE_KEEP_THRESH = 1        # DROP a card if relevance <= this AND not protected (0=conservative, 1=default)
SCORE_FLAG_PCT = 60          # flag loudly if >this% of cards get dropped (something's likely wrong)
CLUSTER_SINGLE_MAX = 200     # <= this many cards -> one clustering call; more -> batched two-level
CLUSTER_BATCH = 120          # cards per batch in the two-level path
HIGH_VOL = 300               # orphan check: a keyword at or over this volume is "high-demand"
ORPHAN_POOL = 40             # orphan check: the top N high-demand keywords shown

NOT_AVAILABLE = "(not available for this run)"


# ---- resume ---------------------------------------------------------------------------------------

def work_name(name):
    """Every step's output lives under artifacts/_work/<name>.json, so the run folder shows the chain."""
    return "_work/%s.json" % name


def load_work(ctx, name):
    return store.load_artifact(ctx["chat_id"], ctx["run_id"], work_name(name))


def save_work(ctx, name, data):
    return store.save_artifact(ctx["chat_id"], ctx["run_id"], work_name(name), data)


def cached(ctx, name, redo, produce):
    """Reuse _work/<name>.json unless redo; else run produce(), save it, return it.
    Returns (data, reused)."""
    if not redo:
        got = load_work(ctx, name)
        if got is not None:
            return got, True
    out = produce()
    save_work(ctx, name, out)
    return out, False


# ---- prompts --------------------------------------------------------------------------------------

def prompt(name, **tokens):
    """prompts/research/<name>.md with its tokens filled. {{MEMORY}} is filled for every prompt."""
    tokens.setdefault("memory", sh.memory_block())
    return sh.fill(sh.load_prompt("research/" + name), **tokens)


def na(v):
    """A prompt slot never goes in empty: the original filled it with '(not available for this run)'."""
    v = (v or "").strip() if isinstance(v, str) else v
    return v if v else NOT_AVAILABLE


def render(items):
    """The conductor's list renderer: '  - item' lines, or '(none listed)'."""
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    return "\n".join("  - %s" % i for i in items) if items else "  (none listed)"


def world_tokens(world):
    world = world or {}
    return {"about": na(world.get("about")), "not_about": na(world.get("not_about"))}


def company_tokens(company=None):
    c = company or sh.company()
    return {"brand": c.get("brand") or "this company",
            "domain": c.get("domain") or "(no domain on file)",
            "brand_oneliner": c.get("brand_oneliner") or "(no one-line description on file)",
            "niche_definition": c.get("niche_definition") or "(no niche definition on file)",
            "about_brand": c.get("about") or c.get("brand_oneliner") or "(no description on file)"}


def strings(items, limit=None):
    out = []
    for x in (items or []):
        if isinstance(x, dict):
            x = x.get("keyword") or x.get("text") or ""
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out[:limit] if limit else out


# ---- text helpers --------------------------------------------------------------------------------

def norm(s):
    """Normalise for the verbatim-exists check: collapse whitespace, unify quotes (harvest_storm._norm)."""
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def md_section(md, heading_pattern):
    """One **bold-headed** block out of a snapshot, without its heading (topic_gate._section).
    heading_pattern is a regex matched right after the opening **."""
    m = re.search(r"^\*\*" + heading_pattern + r"[^\n]*\n(.*?)(?=^\*\*|\Z)", md or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def md_items(block):
    """The '- item' lines of a block, minus a bare 'none'."""
    out = []
    for ln in (block or "").splitlines():
        ln = ln.strip()
        if not ln.startswith("- "):
            continue
        item = ln[2:].strip()
        if item and item.strip('"*').lower().rstrip(".") not in ("none", "(none)"):
            out.append(item)
    return out


def query_text(title):
    """The retrieval query = the title with parenthetical qualifier detail stripped (the reuse-check rule)."""
    a = re.sub(r"\([^)]*\)", " ", title or "")
    a = re.sub(r"\s+", " ", a).strip()
    return a or "untitled"


def is_foreign(url):
    """True for a translation duplicate: the URL's FIRST path segment is an ISO language code."""
    from urllib.parse import urlparse
    seg = urlparse(url or "").path.strip("/").split("/", 1)[0].lower()
    return seg in LOCALES


def bare_domain(url):
    from urllib.parse import urlparse
    d = (urlparse(url or "").netloc or url or "").lower()
    return d[4:] if d.startswith("www.") else d


# ---- personas (13-research-structure/scripts/personas.py + score_cards.persona_str) ---------------

_PERSONA_FALLBACK = "- A practitioner making a real decision about what the brand offers (not an academic)."


def personas_block():
    """One line per persona from knowledge/brand/persona.md: '- Name — who they are'. The persona
    doc is a markdown table whose rows start '| **Name** | who |'. Falls back to a generic reader
    line if the file is missing or the table cannot be parsed (never crashes a run over a display block)."""
    doc = sh.brand_file("persona.md")
    if not doc:
        return _PERSONA_FALLBACK
    lines = []
    for row in doc.splitlines():
        m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|([^|]+)\|", row)
        if m:
            lines.append("- %s — %s" % (m.group(1).strip(), " ".join(m.group(2).split()).strip()))
    return "\n".join(lines) if lines else _PERSONA_FALLBACK


def persona_str(persona):
    """The picked persona as one prompt line; a generic reader if the pick failed."""
    if isinstance(persona, dict) and (persona.get("name") or persona.get("lens")):
        name = (persona.get("name") or "").strip()
        lens = (persona.get("lens") or "").strip()
        return "%s — %s" % (name, lens) if name and lens else (name or lens)
    return "A practitioner making a real decision about what the brand offers (not an academic)."


def as_int(v):
    """A clean integer or None. A non-integer must not slip past an isinstance(int) guard."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default
