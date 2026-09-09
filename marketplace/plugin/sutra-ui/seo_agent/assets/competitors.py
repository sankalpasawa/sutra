"""assets/competitors.py: builder 1, method 1. What already earns links in this niche, and the
SHAPE that earned it.

The port of `02-asset-engine/1-competitor-study`. Its one idea: look at the pages that already earn
a competitor the most links, and steal the FORMAT, never the topic. A format that pulled hundreds of
linking domains for a rival is proven to work in this niche, so we build our own version of that
shape on a subject we can own. The owner's own finding from the real run is the whole argument for
the method: in his niche a news-style piece earns 136 linking domains against 13 for a landing page.

The original's steps, kept in order, each writing one named file the next step reads:

  A   candidates, then a shortlist of 15, split direct or adjacent   _work/competitors/candidates.json
                                                                     _work/competitors/shortlist.json
  A1b what each candidate says it does, so the shortlist can judge   _work/competitors/candidates-enriched.json
  A4  THE GATE. A person approves the list before anything is spent  _work/competitors/approved.json
  A1c every approved domain resolves, before a penny is spent        _work/competitors/domain-validation.json
  B   each competitor's link-earning pages. PAID.                    _work/competitors/pages/<domain>.json
  C   the top pages filtered down to the replicable ones             _work/competitors/filter-report.json
  D   every kept page tagged by FORMAT, never by topic               _work/competitors/master.json
  F0  the tagger's label variants merged into one canonical set      _work/competitors/format-canonical.json
  E   every kept page read in full, no page faked from its title     _work/competitors/read-tally.json
  F   aggregate by format across every competitor                    _work/competitors/format-summary.json
  G   every row turned into an idea, judged against the brand scope  _work/competitors/ideas-raw.json
  G2.5 the same build written twice merged, by meaning not spelling  _work/competitors/dedup-report.json
  H   deliver                                                        assets/competitors.json

Reads:  assets/scope.md (builder 0, the anchor every method judges against; never rebuilt here)
        knowledge/competitors.json, knowledge/brand/company.json
Writes: assets/competitors.json, plus the working files listed above, plus the approved list back
        into knowledge/competitors.json so the rest of the app reads one list from one place.

BLOCKED ON MONEY, AND IT SAYS SO. Step B is a paid DataForSEO pull, one call per competitor, and
the account balance is currently below zero. Everything free still runs: the candidate list, the
shortlist, the gate, and the approved list saved where the app already reads competitors from.
Step B then refuses BEFORE it spends anything and the builder stops with a plain reason, the same
way learn_brand stops when there is no measured traffic to learn from.

Judgment is not decided here twice. The per-page pass (G2) reads one page and says whether it is
worth an idea at all; the idea's own verdicts come from the two shared tests in `_common`,
`ownability()` and `linkability()`, which all three methods call in the same words. Ranking, the
merge across methods and the reuse verdict belong to `merge.py`, not to this file.
"""
import hashlib
import re
import statistics
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urlsplit

import numpy as np

from .. import llm
from .. import store
from ..tools import _shared as sh
from ..tools import voyage
from . import _common as cm
from . import formats as fmt

try:
    from ..tools import dfs
except ImportError:      # dfs.py is a separate module and may not be installed yet
    dfs = None

# The name this method signs its rows with. It must match the builder key in tools/build_assets.py
# (`FINDERS`), or the driver reports this method as "did not contribute" on a run where it did.
METHOD = "competitors"
OUTPUT = "competitors.json"
WORK = "_work/competitors/"
# The gate's answer file is named in `_common.GATE_FILES` and read through
# `_common.gate_approved("competitors")`. It is written by loop.py when a person answers, never here.

# ---- the paid step's guard ----------------------------------------------------------------------
# Dollars. Below this the paid pull does not go out at all. Copied from write/section_keywords.py's
# dfs_route(), which is the same guard serp_advanced got after a research conversation would have
# fired about 48 requests at a balance of -$0.07 for every one of them to be refused. The first
# version of THAT guard compared against a constant that did not exist, so it raised NameError,
# failed open, and was only caught by running it (HISTORY, release note 21). So this constant is
# defined here, in this file, and the suite asserts a low balance actually refuses.
MIN_DFS_BALANCE = 1.00
COMPETITOR_CALL_COST = 0.035    # roughly what one domain_pages pull costs, for the estimate we print

# ---- step A ----------------------------------------------------------------------------------
CANDIDATE_LIMIT = 200           # how many domains the overlap API returns for the model to judge from
SHORTLIST_N = 15                # the original's number: about 10 direct plus about 5 adjacent

# ---- step A1b, telling the shortlister WHAT each candidate is ------------------------------------
# The overlap API returns `domain · keywords · etv` and nothing else, so a model asked to shortlist
# from it is guessing a company's business from its NAME. Measured on the owner's own run
# (2026-07-20): it missed vervoe.com, criteriacorp.com, eskill.com and testdome.com, four genuine
# direct rivals that were sitting in the candidate list it had read. Nothing was wrong with the
# data; the model simply could not tell what those companies do. So each candidate's homepage is
# read for its <title> and meta description — what the company says it is, in its own words.
# Free (plain HTTP, no API), cached, and never fatal: a candidate that will not load goes to the
# model with no description, exactly as before.
ENRICH_TOP = 80                 # candidates enriched, in the API's own overlap order
ENRICH_WORKERS = 8              # homepages read at once
ENRICH_TIMEOUT = 12             # seconds per homepage, then give up on it

# ---- step A1c, never trust a domain, whoever supplied it -----------------------------------------
# Measured on the owner's run (2026-07-20): three approved competitors came back from the paid pull
# with ZERO pages, and two of them were not small companies — they were dead domains that never
# resolve. `maki.people` is the company Maki People at makipeople.com; `wecp.io` is WeCP at
# wecreateproblems.com. Both were operator-supplied and the engine trusted them, so money went on
# calls for domains that cannot exist. An operator typing a brand name instead of a domain, or a
# slightly wrong TLD, is an ordinary mistake and the engine has to catch it rather than inherit it.
RESOLVE_TIMEOUT = 10            # seconds to wait for any HTTP answer at all
RESOLVE_WORKERS = 8

# ---- step B ----------------------------------------------------------------------------------
PAGES_PER_COMPETITOR = 300      # the original takes the top 300 by referring domains
# Rank on FOLLOW referring domains, not the raw total (the owner, 2026-07-20). Measured on
# testgorilla.com: 17 of the top 100 pages are more than 40% nofollow and four are almost all
# nofollow, including a page that looked like the number two link magnet at 343 domains with 340 of
# them nofollow. Nofollow passes no authority, so it must not decide the ranking. Both are kept.
RANK_KEY = "domains_follow"

# ---- step C, the filter -----------------------------------------------------------------------
# Every rule below matches the URL PATH, never the whole URL. Matching the whole URL made a
# "keep anything with test in it" rule match every page on testgorilla.com, so the brand name in
# the domain silently kept all the login and locale junk.
MIN_FOLLOW_DOMAINS = 1          # drop only pages with zero authority-passing links, nothing more
LOW_KEEP_ALARM = 40             # a competitor collapsing below this is said out loud, not swallowed
DENY_SUB = set("help,docs,support,kb,knowledgebase,knowledge,faq,app,apps,api,status,portal,login,"
               "auth,account,dashboard,admin,my,secure,billing,pay,checkout,cdn,static,assets,img,"
               "images,media,files,download,downloads,mail,email,smtp,ftp,git,dev,test,staging,"
               "stage,qa,sandbox,demo,preview,beta,candidates,candidate,applicant,applicants,jobs,"
               "careers,recruit,hire,partners,partner,community,forum,forums,discuss,chat,shop,"
               "store,invoice,track,link,go,click".split(","))
LOCALES = {"fr", "de", "es", "nl", "ja", "it", "pt", "ru", "zh", "ko", "ar", "pl", "tr", "sv", "da",
           "no", "fi", "cs", "hu", "ro", "el", "he", "hi", "id", "th", "vi", "uk", "bg", "hr", "sk",
           "sl", "et", "lv", "lt", "ms", "fa", "pt-br", "zh-cn", "zh-tw", "en-gb", "en-au", "en-ca"}
PAGINATION_SEGS = {"page", "pages", "p"}
JOB_SEGS = {"jobs", "job", "careers", "career", "vacancies", "vacancy", "hiring", "openings",
            "positions"}
DROP_PATH_SUBSTR = ["/pricing", "/login", "/signin", "/sign-in", "/signup", "/sign-up", "/register",
                    "/checkout", "/cart", "/account", "/dashboard", "/admin", "/legal", "/privacy",
                    "/terms", "/cookie", "/gdpr", "/dpa", "/security-policy", "/sitemap", "/contact",
                    "/demo", "/book-a-demo", "/free-trial", "/trial", "/subscribe", "/unsubscribe",
                    "/thank-you", "/404", "/search", "/tag/", "/tags/", "/category/", "/categories/",
                    "/author/", "/feed", "/rss", "/amp/", "/wp-content", "/wp-admin", "/wp-json",
                    "/cdn-cgi", "/.well-known"]
# Query keys that say where a visitor came FROM, never which page this is. Measured 2026-07-20: one
# competitor article arrived four times and another six times, the same page counted six times with
# its link pull split across the copies.
TRACKING = ("utm_", "ref", "referrer", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "_hsenc",
            "_hsmi", "hsctatracking", "igshid", "src", "source", "campaign")

# ---- step D, format tagging --------------------------------------------------------------------
TAG_BATCH = 25                  # pages per call. Headings only, so they fit comfortably
TAG_WORKERS = 4                 # tagging calls in flight at once

# ---- step E, reading every kept page -------------------------------------------------------------
READ_WORKERS = 6                # page fetches in flight. HTTP, not model calls, so its own number
MIN_BODY_WORDS = 80             # under this the page did not really load: FETCH FAILED, never a title
READ_CHARS = 6000               # of a page's text handed to the reasoning pass, title and headings first
# A SOFT 404 is a "Page Not Found" served with HTTP 200. The fetcher cannot see it, because as far
# as HTTP is concerned the page loaded. Seventy rows in the owner's real run came back this way and
# had to be reclassified BY HAND afterwards; unspotted, each one becomes a content idea built on an
# error page. Two checks catch them, and they are the same two the site catalogue uses:
#   1. the body's own words, read at the top of the page where the message always sits, and
#   2. a repeated body — N pages on one site sharing a byte-identical body is a template, not
#      content, which catches the soft 404s whose wording this list has never seen.
SOFT_404 = re.compile(
    r"\b(page not found|404 error|page you (are|were) looking for (does not|doesn't) exist|"
    r"this page (does not|doesn't) exist|nothing (was )?found|content not available|"
    r"sorry,? (we )?(can'?t|could not|couldn'?t) find)\b", re.I)
SOFT_404_CHARS = 1200           # of the body checked. The message is at the top or it is not the page
DUP_BODY_ALARM = 8              # identical bodies on one competitor before the group is a template

# ---- step F --------------------------------------------------------------------------------------
FORMAT_MIN_COMPETITORS = 3      # a format one competitor happens to own is not a proven format
FORMAT_MIN_PAGES = 5

# ---- step G ----------------------------------------------------------------------------------
# Five rows per reasoning pass, and never more. Handed a big block the model pattern-matches ACROSS
# the batch and goes generic: it stops reading each page and writes one description that fits them
# all. That is trap 3 below, and the batch size is the main thing that prevents it.
G2_BATCH = 5
G2_WORKERS = 6
JUDGE_BATCH = 12                # ideas per ownability or linkability call
SCORE_BATCH = 12                # ideas per beatability and effort call
# Trap 3's tripwires, in code. The original's own check: no single angle gap may cover more than
# GAP_REPEAT_MAX rows, and there must be at least one distinct gap per GAP_PER_ROWS rows. Below
# either line the gaps were templated and the ideas built on them inherit the problem.
GAP_REPEAT_MAX = 10
GAP_PER_ROWS = 5
# An idea backed by pages carrying this many follow domains is never dropped by a model's score.
# The measurement is the evidence; a 2 out of 4 from a judge does not outrank a page that really
# pulled hundreds of linking domains. This is the PROTECT half of the filter, and it exists because
# the load-bearing item is usually the one buried in an unpromising group.
PROTECT_DOMAINS = 100

# ---- step G2.5, the same BUILD under two names -------------------------------------------------
# `_collapse` below is a STRING key and merges only titles that are identical once normalised. The
# owner measured what that misses on his real pool: 97 merges, "Python Skills Test" against "Coding
# Assessment (Python)" — the same thing to build, worded differently, so the key never matched. The
# fix is the textbook entity resolution and it is the same two-part shape the merge across methods
# already uses: an embedding NOMINATES near neighbours, and the model DECIDES on the small cluster
# it nominated. The embedding never merges on its own, because a glossary and a test library can
# sit at 0.75 and merging those two would be wrong.
DEDUP_THRESHOLD = 0.80   # cosine to become a merge CANDIDATE. Measured by the owner on real titles
#                          (voyage-4-large): true twins ~0.83, genuinely different ideas 0.5-0.66,
#                          and a danger band 0.72-0.80 where different builds look close. Set to
#                          gather candidates generously and let the model separate them.
DEDUP_TOPK = 6           # nearest neighbours considered per idea
DEDUP_MAX_CLUSTER = 10   # a cluster is cut into slices of this size before the model sees it


class Blocked(RuntimeError):
    """This method could not finish because something it needs is not there.

    Raised rather than returned on purpose. tools/build_assets.py counts a builder that returns
    normally as one that contributed, so a silent empty pool would make a two-of-three sheet look
    complete. Raising is what makes the engine say out loud which method did not run.
    """


# ---- small shared helpers -----------------------------------------------------------------------

def _fanout(fn, items, workers, say=None, label="", every=25):
    """Run fn(item) over items, `workers` at a time, results in the items' own order.

    Not brand/_common.parallel: that pool is sized for model calls (three at a time) and step E is
    thousands of HTTP fetches. One failure comes back as its error and never kills the batch.
    """
    items = list(items)
    if not items:
        return []
    out = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for n, fut in enumerate(as_completed(futs), 1):
            i = futs[fut]
            try:
                out[i] = (fut.result(), None)
            except Exception as e:      # noqa: BLE001. One bad page must not lose the run
                out[i] = (None, e)
            if say and label and (n % every == 0 or n == len(items)):
                say(label, "%d of %d" % (n, len(items)))
    return [(items[i], out[i][0], out[i][1]) for i in range(len(items))]


def _batches(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _bare(domain):
    d = (domain or "").strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0].split("?")[0]
    return d[4:] if d.startswith("www.") else d


def _path_of(url):
    try:
        return (urlsplit(url).path or "/").lower()
    except ValueError:
        return "/"


def _sub_of(url):
    try:
        parts = urlsplit(url).netloc.lower().split(".")
    except ValueError:
        return ""
    return parts[0] if len(parts) > 2 else ""


# ---- the paid route -------------------------------------------------------------------------------

def paid_route():
    """(usable, reason). The pre-flight, run once before the first paid call of a run.

    An UNKNOWN balance fails open, because the paid call reports its own failure loudly anyway.
    A KNOWN balance under MIN_DFS_BALANCE refuses, and nothing is spent.
    """
    if dfs is None or not dfs.available():
        return False, ("DataForSEO is not connected, so there is no way to see which of a "
                       "competitor's pages earn links")
    bal = dfs.balance()
    if bal is None:
        return True, "DataForSEO balance unknown, going ahead"
    if bal < MIN_DFS_BALANCE:
        return False, ("the DataForSEO balance is $%.2f, under the $%.2f this step needs"
                       % (bal, MIN_DFS_BALANCE))
    return True, "DataForSEO balance $%.2f" % bal


def _dfs_items(data):
    """tasks[0].result[0].items, where any level may be missing. dfs.py owns this shape and this is
    its unwrapper; the two endpoints this file needs have no named function there yet, so the call
    goes through dfs.post(), which is still the one place the credential lives."""
    return dfs._items(data)      # noqa: SLF001. See the docstring; dfs.py should grow the wrappers


# ---- STEP A1: the candidate list ------------------------------------------------------------------

def _candidates(co, say, redo=False):
    """A1. Every domain worth judging, from the cheapest source that can answer.

    Reads:  DataForSEO competitors_domain when there is balance, else knowledge/competitors.json,
            else the brand pack (the same derivation suggest_topics already uses).
    Writes: _work/competitors/candidates.json  {source, at, rows: [{domain, keywords, etv, why}]}

    The overlap API ranks by shared keywords, so it is a candidate GENERATOR and never the answer.
    Measured 2026-07-20 for testlify.com it ranked scribd third, study.com fifth and investopedia
    eighth. That is exactly why A2 is a judgment step and not a "take the top 15" cut.
    """
    name = WORK + "candidates.json"
    if cm.exists(name) and not redo:
        doc = cm.read(name) or {}
        say("Kept the candidate list", "%d domains from %s" % (len(doc.get("rows") or []),
                                                               doc.get("source", "the last run")))
        return doc

    rows, source = [], ""
    can_pay, _why = paid_route()
    domain = _bare(co.get("domain") or "")
    if can_pay and domain:
        try:
            data = dfs.post("/dataforseo_labs/google/competitors_domain/live",
                            [{"target": domain, "location_name": co.get("location_name") or "United States",
                              "language_code": co.get("language_code") or "en",
                              "limit": CANDIDATE_LIMIT, "exclude_top_domains": True,
                              "item_types": ["organic"]}])
            for it in _dfs_items(data):
                m = (it.get("metrics") or {}).get("organic") or {}
                d = _bare(it.get("domain") or "")
                if d and d != domain:            # never list ourselves
                    rows.append({"domain": d, "keywords": m.get("count") or 0,
                                 "etv": round(m.get("etv") or 0), "why": ""})
            source = "DataForSEO competitors_domain"
            say("Found who ranks for the same words", "%d candidate domains" % len(rows))
        except Exception as e:      # noqa: BLE001. A refused pull falls back, it does not stop the run
            say("The competitor lookup did not answer", str(e)[:160])

    if not rows:
        # Free fallbacks, in order of how much they are worth. Names already on file were either
        # given by the team at setup or derived earlier, so they are the better of the two.
        on_file = _known_competitors()
        if on_file:
            rows = [{"domain": r["domain"], "keywords": 0, "etv": 0, "why": r.get("why", "")}
                    for r in on_file]
            source = "knowledge/competitors.json"
            say("Used the competitor list already on file", "%d named" % len(rows))
        else:
            rows = _derive(co, say)
            source = "worked out from the brand pack"

    doc = {"source": source, "at": store.now(), "rows": rows}
    cm.save(name, doc)
    return doc


def _known_competitors():
    """knowledge/competitors.json in every shape it has ever been written: a dict with a
    `competitors` key, a bare list, or a list of plain strings."""
    raw = store.knowledge("competitors.json") or []
    if isinstance(raw, dict):
        raw = raw.get("competitors") or []
    out = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"domain": _bare(item), "why": ""})
        elif isinstance(item, dict) and item.get("domain"):
            out.append({"domain": _bare(item["domain"]), "why": item.get("why", "")})
    return [r for r in out if r["domain"]]


def _derive(co, say):
    """The last free source: ask the model who this company competes with, from what the brand pack
    says it sells. The same prompt suggest_topics uses, so the app has one answer to this question
    and not two."""
    voice = sh.brand_voice()
    if not voice:
        about = " ".join(str(co.get(k) or "") for k in
                         ("brand_oneliner", "niche_definition", "about")).strip()
        if not about:
            return []
        voice = {"company": co.get("brand") or "", "what_they_sell": about}
    say("Working out who you compete with", "no list on file and no balance for the lookup")
    try:
        data = llm.json_call(sh.fill(sh.load_prompt("derive_competitors"),
                                     voice=sh.voice_block(voice)))
    except Exception as e:      # noqa: BLE001
        say("Could not work out a competitor list", str(e)[:160])
        return []
    out = []
    for item in (data.get("competitors") or []):
        d = _bare(item.get("domain") or "")
        if d:
            out.append({"domain": d, "keywords": 0, "etv": 0, "why": item.get("why", "")})
    return out


# ---- STEP A1b: say what each candidate actually IS -------------------------------------------------

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESC_TAG = re.compile(
    r"""<meta[^>]+(?:name|property)=["'](?:description|og:description)["'][^>]+content=["'](.*?)["']""",
    re.I | re.S)
_DESC_TAG_REVERSED = re.compile(
    r"""<meta[^>]+content=["'](.*?)["'][^>]*(?:name|property)=["'](?:description|og:description)["']""",
    re.I | re.S)
_HTML_TAG = re.compile(r"<[^>]+>")
_ENTITIES = (("&amp;", "&"), ("&#39;", "'"), ("&quot;", '"'), ("&nbsp;", " "),
             ("&lt;", "<"), ("&gt;", ">"))


def _clean_meta(text):
    out = _HTML_TAG.sub(" ", text or "")
    for a, b in _ENTITIES:
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", out).strip()[:220]


def _homepage(domain):
    """A candidate's own words about itself: {title, description}. Best effort and never raises.

    Deliberately a plain urllib GET rather than the research fetcher: this reads the first 180KB of
    a homepage for two tags, not a whole article, and it must not be able to pull a browser render
    or a retry ladder into the free half of a paid run.
    """
    for scheme in ("https://", "https://www."):
        try:
            req = urllib.request.Request(scheme + domain, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=ENRICH_TIMEOUT) as r:
                html = r.read(180_000).decode("utf-8", "ignore")
        except Exception:      # noqa: BLE001. A candidate that will not load simply has no description
            continue
        t = _TITLE_TAG.search(html)
        d = _DESC_TAG.search(html) or _DESC_TAG_REVERSED.search(html)
        title = _clean_meta(t.group(1) if t else "")
        desc = _clean_meta(d.group(1) if d else "")
        if title or desc:
            return {"title": title, "description": desc}
    return {"title": "", "description": ""}


def _enrich(cands, say, redo=False):
    """A1b. Every candidate carries what its company says it does, before anyone judges it.

    Reads:  _work/competitors/candidates.json
    Writes: _work/competitors/candidates-enriched.json  the same rows plus title and description

    The shortlist prompt already tells the model to read a candidate's description and trust it over
    the domain name. Until this step existed there were no descriptions to read, so that instruction
    was aimed at a blank. Cached per run and resumable: a homepage already read is not read again.
    """
    name = WORK + "candidates-enriched.json"
    rows = list(cands.get("rows") or [])
    if not rows:
        return cands
    done = {}
    if cm.exists(name) and not redo:
        done = {r["domain"]: r for r in (cm.read(name) or []) if r.get("domain")}
    todo = [r for r in rows[:ENRICH_TOP] if r["domain"] not in done]
    if todo:
        say("Reading what each candidate says it does",
            "%s to read, free and in parallel" % sh.plural(len(todo), "homepage"))
        with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as ex:
            futs = {ex.submit(_homepage, r["domain"]): r for r in todo}
            for fut in as_completed(futs):
                r = futs[fut]
                try:
                    r.update(fut.result())
                except Exception:      # noqa: BLE001. Never fatal; the row just carries no description
                    r.update({"title": "", "description": ""})
                done[r["domain"]] = r
    merged = [done.get(r["domain"], r) for r in rows]        # original order; past ENRICH_TOP, no description
    cm.save(name, merged)
    got = sum(1 for r in merged if r.get("title") or r.get("description"))
    say("Worked out what the candidates are",
        "%d of %d now carry the company's own description" % (got, len(merged)))
    out = dict(cands)
    out["rows"] = merged
    out["enriched"] = got
    return out


# ---- STEP A2 and A3: the shortlist, split direct or adjacent ---------------------------------------

def _shortlist(co, cands, say, redo=False):
    """A2 and A3. Fifteen worth studying, each marked direct or adjacent.

    Reads:  _work/competitors/candidates.json
    Writes: _work/competitors/shortlist.json  {competitors: [{domain, kind, why, from}], excluded, note}

    Direct means the same product to the same buyer: what link bait works in our exact space.
    Adjacent means the same audience with a different product, the authority sites this buyer
    already reads. Adjacent ones are the format goldmines and the original insists on having some.
    """
    name = WORK + "shortlist.json"
    if cm.exists(name) and not redo:
        doc = cm.read(name) or {}
        say("Kept the shortlist", "%d competitors from the last run" % len(doc.get("competitors") or []))
        return doc

    rows = cands.get("rows") or []
    if not rows:
        raise Blocked(
            "I could not work out who you compete with. DataForSEO is not connected or has no "
            "balance, there is no competitor list saved in Knowledge, and there is not enough in "
            "the brand pack to work one out. Add a competitor or two in Knowledge, or connect "
            "DataForSEO, and ask me again.")

    def line(r):
        bits = [r["domain"]]
        if r.get("keywords"):
            bits.append("%s shared keywords" % r["keywords"])
        if r.get("why"):
            bits.append(r["why"])
        # The company's own words, from step A1b. This is the half of the row that lets the model
        # tell a rival from a site that happens to rank for the same phrase; without it the
        # prompt's "read each candidate's description" instruction is aimed at nothing.
        about = " — ".join(x for x in ((r.get("title") or "").strip(),
                                       (r.get("description") or "").strip()) if x)
        if about:
            bits.append(about)
        return " · ".join(bits)

    out = llm.json_call(sh.fill(cm.prompt("competitors-shortlist"),
                                brand=co.get("brand") or "this company",
                                oneliner=co.get("brand_oneliner") or "",
                                niche=co.get("niche_definition") or "",
                                n=str(SHORTLIST_N),
                                candidates="\n".join(line(r) for r in rows))) or {}

    seen, picked = set(), []
    for item in (out.get("competitors") or []):
        d = _bare(item.get("domain") or "")
        if not d or d in seen or d == _bare(co.get("domain") or ""):
            continue
        seen.add(d)
        kind = "direct" if str(item.get("group") or item.get("kind") or "").lower().startswith("d") \
            else "adjacent"
        picked.append({"domain": d, "kind": kind, "why": (item.get("why") or "").strip(),
                       "from": cands.get("source", "")})

    doc = {"competitors": picked, "excluded": out.get("excluded_notable") or [],
           "note": out.get("note") or "", "source": cands.get("source", ""), "at": store.now()}
    cm.save(name, doc)
    d_n = sum(1 for r in picked if r["kind"] == "direct")
    say("Shortlisted the competitors worth studying",
        "%d direct, %d adjacent" % (d_n, len(picked) - d_n))
    return doc


# ---- STEP A4: THE GATE ------------------------------------------------------------------------------

def approved():
    """The list a person signed off, or None when nobody has been asked yet.

    None and [] are different and the difference decides what happens next. None means the gate has
    never been put, so this builder proposes a shortlist and stops. [] means a person looked at the
    proposal and kept nothing, which is an answer, and re-asking would be nagging.

    The file itself belongs to `_common`, which names it and writes it when loop.py files the
    answer. Read tolerantly here, because the answer arrives as whatever the person typed: a list of
    rows, or bare domains they pasted themselves.
    """
    raw = cm.gate_approved(METHOD)
    if raw is None:
        return None
    out = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"domain": _bare(item), "kind": "direct", "why": ""})
        elif isinstance(item, dict) and (item.get("domain") or item.get("name")):
            out.append({"domain": _bare(item.get("domain") or item.get("name")),
                        "kind": (item.get("kind") or item.get("group") or "direct").lower(),
                        "why": item.get("why", "")})
    return [r for r in out if r["domain"]]


def _gate(short, co):
    """The question, in the shape tools/onboard.py established and loop.py already draws.

    This is one of the engine's three human gates and the original calls it a gate in as many
    words. It is not a rubber stamp: fifteen wrong companies means fifteen paid pulls at the wrong
    companies, and every idea after that is modelled on the wrong niche. The builder does not wait
    here; it hands the question up and writes nothing further.
    """
    rows = short.get("competitors") or []
    d_n = sum(1 for r in rows if r["kind"] == "direct")
    return {"kind": METHOD, "builder": METHOD,
            "proposed": [{"domain": r["domain"], "kind": r["kind"], "why": r["why"]} for r in rows],
            "question": ("These are the %d competitors I would study for %s: %d direct and %d "
                         "adjacent. Good to go, or would you change the list?"
                         % (len(rows), co.get("brand") or "you", d_n, len(rows) - d_n)),
            "why": ("I read the pages that earn each of them the most links, and copy the SHAPE "
                    "that earned them. A wrong name here means I model the wrong niche, so it is "
                    "worth ten seconds of your eye first." + (" " + short["note"] if short.get("note") else ""))}


def _save_knowledge_competitors(rows, say):
    """The approved list into knowledge/competitors.json, which is the file the rest of the app
    already reads for competitors. One list, one place, so the Knowledge tab and this engine can
    never disagree. Merged, never replaced: a name already on file was given by the team at setup
    and is not this builder's to throw away."""
    have = _known_competitors()
    seen, out = set(), []
    for r in rows:
        out.append({"domain": r["domain"], "kind": r["kind"],
                    "why": r.get("why") or "approved for the competitor study", "last_used": None})
        seen.add(r["domain"])
    for r in have:
        if r["domain"] not in seen:
            seen.add(r["domain"])
            out.append({"domain": r["domain"], "why": r.get("why", ""), "last_used": None})
    store.save_knowledge("competitors.json", {"competitors": out, "approved_at": store.now()})
    say("Saved the competitor list", "%s, in Knowledge where everything else reads it"
        % sh.plural(len(out), "competitor"))


# ---- STEP A1c: every domain resolves, BEFORE a penny is spent ---------------------------------------

def resolves(domain):
    """Is there anything at all at this domain? Any HTTP answer counts, a 403 included: a real
    server refusing us still proves the domain exists. Only "nothing answered" means dead."""
    for scheme in ("https://", "https://www."):
        try:
            req = urllib.request.Request(scheme + domain, headers={"User-Agent": _UA}, method="HEAD")
            urllib.request.urlopen(req, timeout=RESOLVE_TIMEOUT)
            return True
        except urllib.error.HTTPError:
            return True                      # 403 or 404 from a real server: the domain is live
        except Exception:      # noqa: BLE001. DNS failure, refused connection, timeout: try the next scheme
            continue
    return False


def _repairs(dead):
    """Obvious repairs for a domain that does not resolve, and nothing clever.

    A brand's WORDS can sit either side of the dot, so the odd-looking "TLD" is often part of the
    name: `maki.people` is the company Maki People at makipeople.com. Every repair is only used if
    it actually resolves, so a wrong guess can never enter the study.
    """
    parts = [x for x in (dead or "").split(".") if x]
    out = []
    if len(parts) > 1:
        joined = "".join(parts)                       # maki.people -> makipeople
        out += [joined + ".com", "-".join(parts) + ".com"]
        head = "".join(parts[:-1])                    # or the last part really is the TLD
        out += [head + ".com", head.replace("-", "") + ".com"]
    flat = (dead or "").replace("-", "")
    if flat != dead:
        out.append(flat)
    seen, uniq = set(), []
    for d in out:
        if d and d != dead and d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def _near(dead, candidate_domains):
    """A candidate that is plainly the same company: `maki.people` next to `makipeople.com`. The
    candidate list is real API data, so anything in it demonstrably exists."""
    stem = (dead or "").split(".")[0].replace("-", "")
    flat = (dead or "").replace(".", "").replace("-", "")
    for d in candidate_domains:
        dflat = d.replace(".", "").replace("-", "")
        if dflat.startswith(flat) or (flat and flat.startswith(dflat.split("com")[0])) \
                or (len(stem) >= 4 and dflat.startswith(stem)):
            return d
    return None


def _validate(comps, cands, say):
    """A1c. Every approved domain resolves, or it is swapped for one that does, or it is dropped.

    Reads:  the approved list, and _work/competitors/candidates.json for near-matches
    Writes: _work/competitors/domain-validation.json  every swap and every drop, with its reason

    This runs on the whole approved list, model-picked and person-typed alike, and it runs BEFORE
    the paid pull, because the whole point is not to pay for a domain that cannot exist.

    ONE SAFETY THE ORIGINAL DOES NOT NEED. His script is run by hand, so a machine with no network
    simply fails in front of him. This one runs unattended, and "nothing resolved" would then read
    as "every competitor is dead" and empty the study. So when NOT ONE domain answers, that is
    treated as our network being down rather than as a verdict on the list: everything is kept and
    the run says so.
    """
    if not comps:
        return comps
    with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS) as ex:
        futs = {ex.submit(resolves, r["domain"]): r for r in comps}
        for fut in as_completed(futs):
            try:
                futs[fut]["resolved"] = bool(fut.result())
            except Exception:      # noqa: BLE001
                futs[fut]["resolved"] = False
    if not any(r.get("resolved") for r in comps):
        say("Could not check the competitor domains",
            "not one of %d answered, which is this machine's network rather than %d dead domains, "
            "so the list was kept as approved" % (len(comps), len(comps)))
        cm.save(WORK + "domain-validation.json",
                {"checked": len(comps), "swapped": [], "dropped": [],
                 "note": "no domain answered at all; treated as a network failure, nothing dropped",
                 "at": store.now()})
        for r in comps:
            r.pop("resolved", None)
        return comps

    candidate_domains = [r["domain"] for r in (cands.get("rows") or []) if r.get("domain")]
    kept, swapped, dropped = [], [], []
    for r in comps:
        if r.get("resolved"):
            kept.append(r)
            continue
        dead = r["domain"]
        # In order: an alias the shortlist itself offered, then a near-match in the real candidate
        # list, then an obvious repair. Each is only taken if it too resolves.
        alt = next((a for a in (r.get("aliases") or []) if resolves(a)), None)
        if not alt:
            near = _near(dead, candidate_domains)
            alt = near if (near and resolves(near)) else None
        if not alt:
            alt = next((x for x in _repairs(dead) if resolves(x)), None)
        if alt:
            r["swapped_from"] = dead
            r["domain"] = alt
            r.setdefault("aliases", []).append(dead)
            swapped.append({"from": dead, "to": alt})
            kept.append(r)
        else:
            dropped.append({"domain": dead,
                            "why": "the domain does not resolve and no live alternative was found"})
    for r in kept:
        r.pop("resolved", None)
    cm.save(WORK + "domain-validation.json",
            {"checked": len(comps), "swapped": swapped, "dropped": dropped, "at": store.now()})
    if swapped or dropped:
        say("Checked every competitor domain before spending anything",
            "%d live · %s · %s"
            % (len(kept) - len(swapped),
               ", ".join("%s does not resolve, using %s" % (x["from"], x["to"]) for x in swapped)
               or "nothing swapped",
               ", ".join("%s dropped, dead domain" % x["domain"] for x in dropped) or "nothing dropped"))
    return kept


# ---- STEP B: each competitor's link-earning pages (PAID) ---------------------------------------------

def _pull(rows, say, redo=False):
    """B. One DataForSEO backlinks/domain_pages call per competitor, cached per competitor.

    Reads:  the approved list
    Writes: _work/competitors/pages/<domain>.json, one file per competitor

    Resumable per competitor on purpose: a crash or a credit stop must never make the run pay twice
    for a competitor it already has. The pre-flight happens once, before the first call, so a run
    that cannot pay spends nothing at all rather than firing calls to be refused one by one.
    """
    todo = [r for r in rows if redo or not cm.exists("%spages/%s.json" % (WORK, r["domain"]))]
    if todo:
        ok, why = paid_route()
        if not ok:
            raise Blocked(
                "I stopped before spending anything: %s. This method works by pulling the pages "
                "that earn each competitor the most links, and that pull is the one paid step in "
                "it. Top the account up, or add the DataForSEO login in Connections, and ask me "
                "again. Nothing was spent and the approved competitor list is saved, so the run "
                "picks up where it stopped. The other two methods do not need it and still run."
                % why)
        say("Reading what earns your competitors links",
            "%d to pull, about $%.2f" % (len(todo), len(todo) * COMPETITOR_CALL_COST))

    out, empty = [], []
    for i, r in enumerate(rows, 1):
        name = "%spages/%s.json" % (WORK, r["domain"])
        if cm.exists(name) and not redo:
            pages = cm.read(name) or []
        else:
            pages = _pull_one(r["domain"])
            cm.save(name, pages)
        for p in pages:
            p["kind"] = r["kind"]
        out += pages
        if not pages:
            empty.append(r["domain"])
        say("Read %s" % r["domain"], "%d pages, top page %d follow domains (%d of %d)"
            % (len(pages), (pages[0].get(RANK_KEY, 0) if pages else 0), i, len(rows)))
    if empty:
        # Named, never rolled into a count. A competitor that returned nothing is a fact about the
        # study's coverage and the run log has to carry it.
        say("Some competitors returned nothing", ", ".join(empty))
    return out, empty


def _pull_one(domain):
    data = dfs.post("/backlinks/domain_pages/live",
                    [{"target": domain, "limit": PAGES_PER_COMPETITOR,
                      "order_by": ["page_summary.referring_domains,desc"]}])
    rows = []
    for it in _dfs_items(data):
        ps = it.get("page_summary") or {}
        meta = it.get("meta") or {}
        total = ps.get("referring_domains") or 0
        nofollow = ps.get("referring_domains_nofollow") or 0
        rows.append({
            "competitor": domain,
            # `page`, not `url`. Their field for the page's address on this endpoint is `page`,
            # and reading `url` gives an empty column that looks like no data.
            "url": it.get("page") or "",
            "status_code": it.get("status_code"),
            "domains_total": total,
            "domains_nofollow": nofollow,
            "domains_follow": max(total - nofollow, 0),
            "backlinks": ps.get("backlinks") or 0,
            "first_seen": ps.get("first_seen") or "",
            "title": meta.get("title") or "",
            "words": meta.get("words_count") or 0,
            "images": meta.get("images_count") or 0,
            "ext_links": meta.get("external_links_count") or 0,
            "h1": (meta.get("h1") or [])[:3],
            "h2": (meta.get("h2") or [])[:12],
        })
    rows.sort(key=lambda r: -(r.get(RANK_KEY) or 0))
    return rows


# ---- STEP C: filter down to the pages a person could actually build ------------------------------

def _canon(url):
    """The identity of a page, ignoring how a visitor happened to arrive at it. Only KNOWN tracking
    keys go: plenty of real pages are addressed by query (?p=123), and dropping the whole query
    string would silently merge different pages, which is as unrecoverable as over-dropping."""
    try:
        s = urlsplit(url)
    except ValueError:
        return (url or "").lower()
    host = (s.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    keep = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)
            if not any(k.lower() == t or k.lower().startswith(t) for t in TRACKING)]
    path = (s.path or "/").rstrip("/") or "/"
    return host + path + (("?" + urlencode(sorted(keep))) if keep else "")


def drop_reason(row):
    """A reason to drop this page, or None to keep it.

    The governing rule from the original, and it is a scar: over-dropping is unrecoverable, over-
    keeping is not. An early version of this filter dropped every non-200 row on the theory that
    redirects are homepage duplicates. It quietly destroyed real editorial: one competitor collapsed
    to 38 kept pages and another to 22, because both serve their articles on 301-migrated URLs, and
    two competitors' free test-library pages came back with a blank status because they are
    JavaScript-rendered. The whole study rests on formats RECURRING, so deleting a competitor's
    editorial wrecks the signal. Only root-variant redirects and genuinely dead pages go.
    """
    url = row.get("url") or ""
    if not url:
        return "no address"
    path = _path_of(url)
    segs = [s for s in path.split("/") if s]
    if not segs:
        return "homepage or root variant"          # not a shape anyone can build
    if row.get("status_code") in (404, 410):
        return "dead page"                          # ONLY 404 and 410. A 301 or a blank status stays.
    sub = _sub_of(url)
    if sub and sub in DENY_SUB:
        return "not a content subdomain: " + sub
    if sub and sub in LOCALES:
        return "translated copy on a language subdomain: " + sub
    if segs[0] in LOCALES:
        return "translated copy of an English page"
    if len(segs) >= 2 and segs[-1].isdigit() and segs[-2] in PAGINATION_SEGS:
        return "archive or index page"
    if len(segs) >= 2 and any(s in JOB_SEGS for s in segs[:2]):
        return "job posting"
    for pat in DROP_PATH_SUBSTR:
        if pat in path:
            return "commercial or utility page: " + pat
    if (row.get("domains_follow") or 0) < MIN_FOLLOW_DOMAINS:
        return "no links that pass authority"
    return None


def _filter(pages, say):
    """C. The top pages down to the replicable ones, with every drop recorded.

    Reads:  the step B pulls
    Writes: _work/competitors/filter-report.json  per competitor: in, kept, dropped, reasons

    Free tests, tools and calculators are KEPT even though they are technically product pages: they
    earn real links and they are replicable, and for an assessment company they are usually the
    single most valuable format. Only pages whose whole job is to sell get dropped.
    """
    by_comp = {}
    for p in pages:
        by_comp.setdefault(p["competitor"], []).append(p)

    kept_all, report = [], []
    for domain, rows in by_comp.items():
        kept, reasons = [], {}
        for r in rows:
            why = drop_reason(r)
            if why:
                reasons[why] = reasons.get(why, 0) + 1
            else:
                kept.append(r)
        # The same page under several addresses is ONE page. The survivor is the variant with the
        # most follow domains and its counts are left alone rather than summed: we hold counts, not
        # the referring-domain lists, so adding them would double-count any domain linking to two
        # variants. Inflating a format's apparent link pull is the one error this study cannot
        # survive, because the format table is the answer.
        best = {}
        for r in kept:
            k = _canon(r["url"])
            if k not in best or (r.get(RANK_KEY) or 0) > (best[k].get(RANK_KEY) or 0):
                best[k] = r
        dupes = len(kept) - len(best)
        if dupes:
            reasons["the same page at several addresses"] = dupes
        kept = sorted(best.values(), key=lambda r: -(r.get(RANK_KEY) or 0))
        kept_all += kept
        report.append({"competitor": domain, "in": len(rows), "kept": len(kept),
                       "dropped": len(rows) - len(kept), "reasons": reasons,
                       "alarm": bool(rows) and len(kept) < LOW_KEEP_ALARM})
    cm.save(WORK + "filter-report.json", report)
    alarms = [r["competitor"] for r in report if r["alarm"]]
    say("Filtered to the pages worth copying",
        "%d kept of %d" % (len(kept_all), len(pages)))
    return kept_all, report, alarms


# ---- STEP D: tag every kept page by FORMAT, never by topic --------------------------------------

def _tag(rows, co, say):
    """D. One format per kept page. The shape, not the subject.

    Reads:  the kept pages
    Writes: _work/competitors/master.json  the growing detail sheet, one row per kept page

    This is the most important label in the study. Everything after it groups by format: which
    SHAPES earn links, and therefore what we should build. A wrong tag poisons that answer. Judged
    from the title and the real headings, never from the URL alone.
    """
    if not rows:
        return []
    batches = list(_batches(rows, TAG_BATCH))

    def one(batch):
        block = []
        for r in batch:
            block.append("### %s\nurl: %s\ntitle: %s\nh1: %s\nh2: %s\nwords: %s · images: %s · "
                         "outbound links: %s"
                         % (r["row_id"], r["url"], r.get("title") or "(none)",
                            " | ".join(r.get("h1") or []) or "(none)",
                            " | ".join(r.get("h2") or []) or "(none)",
                            r.get("words") or 0, r.get("images") or 0, r.get("ext_links") or 0))
        out = llm.json_call(sh.fill(cm.prompt("competitors-tag-format"),
                                    brand=co.get("brand") or "this company",
                                    pages="\n\n".join(block))) or {}
        return {str(t.get("id")): t for t in (out.get("tags") or []) if isinstance(t, dict)}

    tags = {}
    for _b, got, err in _fanout(one, batches, TAG_WORKERS, say, "Working out what each page IS", 4):
        if got:
            tags.update(got)
    untagged = 0
    for r in rows:
        t = tags.get(str(r["row_id"])) or {}
        fmt = (t.get("format") or "").strip()
        if not fmt:
            untagged += 1
        r["format"] = fmt or "untagged"
        r["format_why"] = (t.get("why") or "").strip()
        r["format_confidence"] = (t.get("confidence") or "").strip()
    if untagged:
        say("Some pages came back untagged", "%d of %d" % (untagged, len(rows)))
    return rows


# ---- STEP E: read every kept page in full ----------------------------------------------------------

def _kill_soft_404s(rows):
    """Mark the rows that answered 200 with an error page. Returns (soft 404s, duplicate bodies).

    Seventy rows in the owner's real run were "Page Not Found" pages served with HTTP 200. Nothing
    upstream can see them: DataForSEO recorded a 200, the fetcher got a page, and the reasoning
    pass would happily write an idea off "the page you are looking for does not exist". They are
    caught here, after the read and before anything reads a body, and marked FETCH FAILED like any
    other page that did not really load, so the same one rule covers both.

    The duplicate-body check is per competitor and byte-exact on purpose. It is looking for ONE
    template served at many addresses — the site's own 404 page, or a JavaScript shell that renders
    nothing — and a site's real articles are never byte-identical to each other. Below
    DUP_BODY_ALARM the repeat is left alone: two or three pages sharing a body is a content
    problem for `_collapse` to pool, not an error page.
    """
    soft = 0
    for r in rows:
        if r.get("read_status") != "ok":
            continue
        if SOFT_404.search((r.get("body") or "")[:SOFT_404_CHARS]):
            r["read_status"] = "FETCH FAILED"
            r["read_method"] = "soft-404"
            r["read_error"] = "answered HTTP 200 with a Page Not Found body"
            r["body"] = ""
            soft += 1
    by_comp = {}
    for r in rows:
        if r.get("read_status") == "ok":
            key = (r.get("competitor") or "",
                   hashlib.sha256((r.get("body") or "").encode("utf-8")).hexdigest())
            by_comp.setdefault(key, []).append(r)
    dupe = 0
    for group in by_comp.values():
        if len(group) < DUP_BODY_ALARM:
            continue
        for r in group:
            r["read_status"] = "FETCH FAILED"
            r["read_method"] = "duplicate-body x%d" % len(group)
            r["read_error"] = ("%d pages on this site returned one byte-identical body, so it is a "
                               "template rather than content" % len(group))
            r["body"] = ""
            dupe += 1
    return soft, dupe


def _read(rows, say):
    """E. The step that gets skipped. Do not skip it.

    Reads:  the tagged rows
    Writes: _work/competitors/master.json with a `body` per row, and read-tally.json

    Three hard rules from the original, all three enforced here rather than asked for:
      1. Every kept row is fetched. Not the top eighty, not "the magnets". The long tail is where
         the under-served formats hide, which is the whole reason to read it.
      2. A page that will not load is marked FETCH FAILED. Using the title as the description is
         banned: it looks like data, it is not, and it hides the gap. A real failure must be
         visible, so a short body counts as a failure too.
      3. A tally is printed and saved: N rows, X read, Y failed, and X + Y must equal N.
    """
    from ..research import web
    if not rows:
        return rows, {"rows": 0, "read": 0, "failed": 0}

    def one(r):
        got = web.fetch(r["url"])
        text = (got.get("text") or "").strip()
        heads = " · ".join(got.get("headings") or [])
        if len(text.split()) < MIN_BODY_WORDS:
            # An almost empty render still tells you what the page IS through its headings, which is
            # the original's own point, but only when there really are headings.
            if not heads:
                raise RuntimeError("the page came back with almost nothing on it")
            text = heads
        return {"title": got.get("title") or r.get("title") or "", "headings": heads, "body": text}

    read = failed = 0
    for r, got, err in _fanout(one, rows, READ_WORKERS, say, "Reading the competitor pages", 25):
        if got:
            r["body"] = got["body"]
            r["headings"] = got["headings"]
            r["read_status"] = "ok"
            read += 1
        else:
            r["body"] = ""
            r["read_status"] = "FETCH FAILED"
            r["read_error"] = str(err)[:160]
            failed += 1
    soft, dupe = _kill_soft_404s(rows)
    read -= soft + dupe
    failed += soft + dupe
    if soft or dupe:
        say("Threw out the pages that only looked like they loaded",
            "%d said Page Not Found while answering 200, %d were one template served at many "
            "addresses" % (soft, dupe))
    tally = {"rows": len(rows), "read": read, "failed": failed, "soft_404": soft,
             "duplicate_body": dupe, "at": store.now()}
    cm.save(WORK + "read-tally.json", tally)
    # The check the original demands in words, made an assertion so it cannot be quietly untrue.
    assert read + failed == len(rows), "the read tally does not add up: %r" % tally
    say("Read every page that would load",
        "%d rows, %d read, %d would not load" % (len(rows), read, failed))
    return rows, tally


# ---- STEP F: aggregate by format ---------------------------------------------------------------

def _aggregate(rows, say):
    """F. Which SHAPES earn links, across every competitor.

    Reads:  the master sheet
    Writes: _work/competitors/format-summary.json

    This is where the method's answer actually comes from. It is ranked on average follow domains
    per page, which is how much link pull a shape earns, and a format that recurs across several
    competitors is the confident one: a shape one competitor happens to own is that competitor's
    quirk, not a proven format.
    """
    by = {}
    for r in rows:
        by.setdefault(r.get("format") or "untagged", []).append(r)
    out = []
    for fmt, group in by.items():
        follow = [g.get("domains_follow") or 0 for g in group]
        words = [len((g.get("body") or "").split()) for g in group if g.get("read_status") == "ok"]
        out.append({
            "format": fmt,
            "pages": len(group),
            "competitors": len({g["competitor"] for g in group}),
            "total_follow_domains": sum(follow),
            "avg_follow_domains": round(sum(follow) / max(len(group), 1), 1),
            "best_page_follow_domains": max(follow) if follow else 0,
            "total_domains_incl_nofollow": sum(g.get("domains_total") or 0 for g in group),
            # Median, not mean, so one giant pillar page cannot set the length everyone else is
            # measured against. This is the "how long should ours be" number.
            "median_words": int(statistics.median(words)) if words else 0,
            "proven": len({g["competitor"] for g in group}) >= FORMAT_MIN_COMPETITORS
                      and len(group) >= FORMAT_MIN_PAGES,
        })
    out.sort(key=lambda r: -r["avg_follow_domains"])
    cm.save(WORK + "format-summary.json", out)
    top = out[0] if out else {}
    say("Worked out which shapes earn the links",
        "%d formats; best is %s at %s follow domains a page"
        % (len(out), top.get("format", "none"), top.get("avg_follow_domains", 0)))
    return out


# ---- STEP G: every row into an idea ------------------------------------------------------------

def _reason(rows, scope, co, comps, say):
    """G2. One idea per kept page, reasoned against the approved brand scope.

    Reads:  the master sheet and assets/scope.md
    Writes: _work/competitors/ideas-raw.json

    Sharded by format so like pages travel together, and never more than G2_BATCH rows per pass.
    Every row must come back exactly once; rows that did not are re-sent once, and any still
    missing are reported rather than quietly dropped.

    The three traps the original designs this step against, and what stops each here:
      1. TOO GENERIC ("build a glossary because glossaries pull links"): the pass is per page and
         must cite something concrete off that page, so there is no room for a formless idea.
      2. TOO COPYING (their exact topic, so we compete head to head and lose): the format is copied
         and the subject must come from the brand scope, which is why the scope is passed in.
      3. FAKE ANALYSIS, output that looks like hundreds of ideas but is one template filled in
         hundreds of times: the tiny batch keeps the model reading each page, and `_traps()` below
         checks the result in code rather than trusting the prompt.
    """
    shards = {}
    for r in rows:
        shards.setdefault(r.get("format") or "untagged", []).append(r)
    batches = [b for rows_ in shards.values() for b in _batches(rows_, G2_BATCH)]

    def one(batch):
        block = []
        for r in batch:
            body = (r.get("body") or "").strip()
            block.append("### row %s\ncompetitor: %s\nformat: %s\nurl: %s\nfollow domains: %s\n"
                         "title: %s\nheadings: %s\npage text:\n%s"
                         % (r["row_id"], r["competitor"], r.get("format") or "untagged", r["url"],
                            r.get("domains_follow") or 0, r.get("title") or "(none)",
                            r.get("headings") or "(none)",
                            body[:READ_CHARS] if body else "(this page would not load)"))
        out = llm.json_call(sh.fill(cm.prompt("competitors-reason"),
                                    brand=co.get("brand") or "this company",
                                    scope=scope, competitors=_comp_block(comps),
                                    rows="\n\n".join(block))) or {}
        return {str(x.get("row_id")): x for x in (out.get("rows") or []) if isinstance(x, dict)}

    got = {}
    for _b, res, err in _fanout(one, batches, G2_WORKERS, say, "Turning pages into ideas", 10):
        if res:
            got.update(res)

    missing = [r for r in rows if str(r["row_id"]) not in got]
    if missing:
        say("Some rows came back empty", "re-sending %d" % len(missing))
        for _b, res, err in _fanout(one, list(_batches(missing, G2_BATCH)), G2_WORKERS):
            if res:
                got.update(res)

    out, holes = [], 0
    for r in rows:
        x = got.get(str(r["row_id"]))
        if not x:
            holes += 1
            continue
        fit = (x.get("brand_fit") or "").strip().upper()
        if fit == "SKIP":
            continue                    # the model read this page and says it is not our world
        out.append({
            "row_id": r["row_id"], "competitor": r["competitor"], "url": r["url"],
            # The format is the step D tag, copied. G2 may never upgrade an article into a tool to
            # make its idea win: that turned about four of five ideas into tools in a niche where
            # tools barely earn links (the format-honesty fix, 2026-07-22).
            "format": r.get("format") or "untagged",
            "domains_follow": r.get("domains_follow") or 0,
            "domains_total": r.get("domains_total") or 0,
            "backlinks": r.get("backlinks") or 0,
            "page_fit": fit,
            "angle_gap": (x.get("angle_gap") or "").strip(),
            "title": (x.get("asset") or "").strip(),
            "angle": (x.get("distinct_angle") or "").strip(),
            "tool_escalation": (x.get("tool_escalation") or "").strip(),
            "notes": (x.get("notes") or "").strip(),
        })
    out = [r for r in out if r["title"]]
    cm.save(WORK + "ideas-raw.json", out)
    say("Wrote an idea for every page that earned one",
        "%d ideas from %d pages%s" % (len(out), len(rows),
                                      "; %d rows never came back" % holes if holes else ""))
    return out, holes


def _comp_block(comps):
    return "\n".join("- %s (%s)" % (c["domain"], c["kind"]) for c in comps) or "(none on file)"


_STOP = {"the", "a", "an", "for", "of", "and", "with", "to", "in", "on", "your", "our", "free"}


def _key(title):
    """A blunt identity for "the same asset". Lowercase, punctuation and filler words gone, the
    remaining stems sorted. So "Free Python Skills Test" and "Python Skills Test (Free)" collapse
    and "Python Test" and "Java Test" do not. Deliberately blunt: it merges only obvious repeats.
    Merging by meaning belongs to merge.py, which does it across all three methods at once."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    stems = sorted(w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words if w not in _STOP)
    return " ".join(stems)


def _collapse(rows, say):
    """G3's backstop, and nothing more. Rows whose titles are byte-identical once normalised are the
    same build found on several competitors' pages, so they become ONE idea carrying ALL of their
    proof. That is a stronger signal, not a weaker one: several competitors on one idea is
    validation. Deterministic and free; no model, no embeddings.

    What this deliberately does NOT do is squish specific ideas into categories. The first build of
    the original's merge collapsed about 2,100 grounded ideas into about 112 broad categories and a
    blind quality score fell from 4.6 to 3.4, because "free Python test with a live editor, because
    the competitor hides theirs" became "coding test library". Lean to keeping.
    """
    groups = {}
    for r in rows:
        groups.setdefault(_key(r["title"]), []).append(r)
    out = []
    for members in groups.values():
        members.sort(key=lambda r: -(r["domains_follow"] or 0))
        head = dict(members[0])
        head["members"] = members
        head["competitors"] = sorted({m["competitor"] for m in members})
        head["pooled_follow_domains"] = sum(m["domains_follow"] or 0 for m in members)
        head["pooled_backlinks"] = sum(m["backlinks"] or 0 for m in members)
        # Every member's gap is kept whole, tagged with the page it came from. These are the
        # evidence behind the angle, and a reviewer must be able to click through to each one.
        head["gaps"] = [{"url": m["url"], "gap": m["angle_gap"]} for m in members if m["angle_gap"]]
        out.append(head)
    out.sort(key=lambda r: -r["pooled_follow_domains"])
    say("Pooled the repeats", "%d ideas from %d pages" % (len(out), len(rows)))
    return out


def _pool_ideas(survivor, dead):
    """Fold one collapsed idea into another: the survivor takes ALL of the proof, never a subset.

    The whole reason a merge is worth doing is that it makes the evidence stronger. Several
    competitors having built the same thing is validation, so the backing pages, the per-page gaps
    and the pooled link counts accumulate; a merge that kept one row and threw the other's proof
    away would trade the one fact worth having for a shorter list.
    """
    seen = {m["url"] for m in survivor.get("members") or []}
    for m in dead.get("members") or []:
        if m["url"] not in seen:
            survivor.setdefault("members", []).append(m)
            seen.add(m["url"])
    have = {(g.get("url"), g.get("gap")) for g in survivor.get("gaps") or []}
    for g in dead.get("gaps") or []:
        if (g.get("url"), g.get("gap")) not in have:
            survivor.setdefault("gaps", []).append(g)
            have.add((g.get("url"), g.get("gap")))
    survivor["competitors"] = sorted({m["competitor"] for m in survivor.get("members") or []})
    survivor["pooled_follow_domains"] = sum(m.get("domains_follow") or 0
                                            for m in survivor.get("members") or [])
    survivor["pooled_backlinks"] = sum(m.get("backlinks") or 0 for m in survivor.get("members") or [])
    # A build flag survives the merge. It is a property of the ASSET, so if the thing needs
    # software it needs software whichever of the two rows noticed.
    if not str(survivor.get("tool_escalation") or "").strip():
        survivor["tool_escalation"] = dead.get("tool_escalation") or ""
    return survivor


def _clusters(rows, say):
    """Groups of ideas an embedding thinks might be the same build, for the model to decide on.

    What is embedded is the BUILD IDENTITY — the title and the format, not the angle — because two
    near-twins describe one build in different words and it is the words of the angle that pull
    them apart. Union-find over "i and j are within the threshold" edges; an idea with no near twin
    never reaches the model at all.
    """
    texts = [("%s — %s" % (r.get("title") or "", r.get("format") or "")).strip(" —") for r in rows]
    V = np.nan_to_num(np.asarray(voyage.embed(texts, "document"), dtype=np.float32))
    n = len(rows)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = 0
    for i in range(n):
        sims = V @ V[i]
        sims[i] = -1.0
        for j in np.argsort(-sims)[:DEDUP_TOPK]:
            j = int(j)
            if sims[j] < DEDUP_THRESHOLD:
                continue
            a, b = find(i), find(j)
            if a != b:
                parent[a] = b
                edges += 1
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for g in groups.values():
        if len(g) < 2:
            continue
        for k in range(0, len(g), DEDUP_MAX_CLUSTER):
            out.append(g[k:k + DEDUP_MAX_CLUSTER])
    say("Looked for the same build written twice",
        "%s nominated %s to read; the rest have no near twin"
        % (sh.plural(edges, "close pair"), sh.plural(len(out), "cluster")))
    return out


def _dedup(rows, co, say, notes):
    """G2.5. Merge the ideas that are the same BUILD, and leave the rest alone.

    Reads:  the collapsed ideas
    Writes: _work/competitors/dedup-report.json  every cluster the model saw and what it decided

    `_collapse` above is a string key and catches only titles that are identical once normalised.
    That misses the near twins, and the owner measured how many: 97 merges on his real pool, of
    which "Python Skills Test" against "Coding Assessment (Python)" is the shape of every one — the
    same thing to build, different words. So this runs after it, on the same rows, and decides by
    meaning what the key could not decide by spelling.

    Two rules keep it honest, and they are the two the cross-method merge already follows:
      1. THE EMBEDDING ONLY NOMINATES. A model turned loose on every idea at once merges everything
         into vague categories, which is how a pool of grounded ideas once became broad headings and
         a blind quality score fell from 4.6 to 3.4. It only ever sees a handful of ideas together.
      2. SEPARATE IS THE DEFAULT, and a cluster the model cannot answer for stays separate. Keeping
         two ideas that were one is recoverable; merging two that were not is not.
    """
    if len(rows) < 2:
        return rows
    if not voyage.available():
        # No embeddings means no way to nominate a pair, and asking the model about every pair of a
        # few hundred ideas is not a substitute. The string key still ran, so the pool is real; it
        # just still carries the near twins, and it has to say so rather than look deduplicated.
        say("Skipped the near-twin check", "no Voyage key, so nothing could be matched by meaning")
        notes.append("competitors.json: there is no Voyage key, so two ideas that are the same "
                     "build under different names are both still on the sheet. Add a key in "
                     "Connections and redo this method.")
        return rows
    try:
        cls = _clusters(rows, say)
    except Exception as e:      # noqa: BLE001. A failed embedding must not lose the pool
        say("Could not match the ideas by meaning", str(e)[:160])
        notes.append("competitors.json: the near-twin check could not run (%s), so the pool may "
                     "carry the same build under two names." % str(e)[:120])
        return rows
    if not cls:
        cm.save(WORK + "dedup-report.json", {"same": 0, "combined": 0, "kept": len(rows),
                                             "clusters": []})
        return rows

    def one(cl):
        block = "\n".join(
            "- id=%d · %s · [%s] · angle: %s"
            % (i, (rows[i].get("title") or "")[:90], rows[i].get("format") or "?",
               (rows[i].get("angle") or "")[:120]) for i in cl)
        out = llm.json_call(sh.fill(cm.prompt("competitors-dedup"),
                                    brand=co.get("brand") or "this company", cluster=block)) or {}
        groups = out.get("groups") if isinstance(out, dict) else out
        return [g for g in (groups or []) if isinstance(g, dict)]

    report, same_ct, combine_ct = [], 0, 0
    gone = set()
    for cl, groups, err in _fanout(one, cls, G2_WORKERS, say, "Reading the possible twins", 10):
        report.append({"cluster": cl,
                       "titles": [(rows[i].get("title") or "")[:70] for i in cl],
                       "groups": groups or [], "error": str(err)[:120] if err else ""})
        for g in (groups or []):
            ids = []
            for raw_id in (g.get("ids") or []):
                try:
                    i = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(rows) and i not in gone and i not in ids:
                    ids.append(i)
            if len(ids) < 2:
                continue                      # nothing left to merge, or an id the model invented
            action = str(g.get("action") or "").strip().lower()
            if action == "same":
                try:
                    keep = int(g.get("keep"))       # a model that answers "3" means the id 3
                except (TypeError, ValueError):
                    keep = None
                keep = keep if keep in ids else ids[0]
                for other in ids:
                    if other != keep:
                        _pool_ideas(rows[keep], rows[other])
                        gone.add(other)
                        same_ct += 1
            elif action == "combine" and str(g.get("new_title") or "").strip():
                keep = ids[0]
                rows[keep]["title"] = g["new_title"].strip()
                if str(g.get("new_angle") or "").strip():
                    rows[keep]["angle"] = g["new_angle"].strip()
                rows[keep]["combined_from"] = ids
                for other in ids[1:]:
                    _pool_ideas(rows[keep], rows[other])
                    gone.add(other)
                    combine_ct += 1

    kept = [r for i, r in enumerate(rows) if i not in gone]
    kept.sort(key=lambda r: -(r.get("pooled_follow_domains") or 0))
    cm.save(WORK + "dedup-report.json", {"same": same_ct, "combined": combine_ct,
                                         "kept": len(kept), "clusters": report})
    say("Merged the ideas that are the same build",
        "%d ideas became %d; %d were the same thing written twice and %d were combined into a "
        "richer one" % (len(rows), len(kept), same_ct, combine_ct))
    return kept


def _traps(rows, notes):
    """Trap 3 in code. The prompt asks for specific gaps and real titles; this checks it got them.

    Three tells that a sheet is one template filled in hundreds of times: asset names that are just
    "<format> on <topic>" glued together, subjects that are scraps lifted off a URL, and the same
    angle gap repeated across hundreds of rows. The third is the measurable one, so it is the one
    enforced: no gap string may cover more than GAP_REPEAT_MAX rows, and there must be at least one
    distinct gap per GAP_PER_ROWS rows.

    Writes: _work/competitors/trap-report.json
    """
    gaps = [g["gap"].strip().lower() for r in rows for g in r.get("gaps") or [] if g.get("gap")]
    counts = {}
    for g in gaps:
        counts[g] = counts.get(g, 0) + 1
    repeated = sorted(((n, g) for g, n in counts.items() if n > GAP_REPEAT_MAX), reverse=True)
    distinct = len(counts)
    thin = bool(gaps) and distinct < max(1, len(gaps) // GAP_PER_ROWS)
    glued = [r["title"] for r in rows
             if re.match(r"^\s*%s\s+(on|for|about)\s+" % re.escape(r.get("format") or "\0"),
                         r["title"], re.I)]
    report = {"ideas": len(rows), "gaps": len(gaps), "distinct_gaps": distinct,
              "repeated_gaps": [{"count": n, "gap": g} for n, g in repeated[:10]],
              "glued_titles": glued[:10], "thin": thin}
    cm.save(WORK + "trap-report.json", report)
    if repeated:
        notes.append("competitors.json: the same reason for building appears on %d ideas (\"%s\"). "
                     "That is the sign of a template rather than real reading, so treat those ideas "
                     "as weaker than their proof suggests." % (repeated[0][0], repeated[0][1][:90]))
    if thin:
        notes.append("competitors.json: only %d different reasons across %d backing pages. The "
                     "reading behind these ideas was thinner than it should be." % (distinct, len(gaps)))
    if glued:
        notes.append("competitors.json: %d ideas are named after their format rather than what they "
                     "are, for example \"%s\". Those are the ones to rewrite first."
                     % (len(glued), glued[0][:80]))
    return report


def _score(rows, scope, say):
    """G4. Beatability out of three and effort as S, M or L. Decided once, here.

    Beatability comes from the gaps: thin, stale, paywalled or single-format backing pages are an
    easy win; strong, recent, well-resourced ones are not. Effort is how much work our version is.
    """
    for batch in _batches(rows, SCORE_BATCH):
        block = []
        for r in batch:
            block.append("### %s\ntitle: %s\nformat: %s\nour angle: %s\nwhat is thin on the pages "
                         "behind it:\n%s"
                         % (r["id"], r["title"], r["format"], r["angle"],
                            "\n".join("- %s" % g["gap"] for g in (r.get("gaps") or [])[:6])
                            or "- (nothing recorded)"))
        try:
            out = llm.json_call(sh.fill(cm.prompt("competitors-score"), scope=scope,
                                        ideas="\n\n".join(block))) or {}
        except Exception as e:      # noqa: BLE001. An unscored idea is still an idea
            say("Could not score some ideas", str(e)[:160])
            continue
        got = {str(x.get("id")): x for x in (out.get("ideas") or []) if isinstance(x, dict)}
        for r in batch:
            x = got.get(str(r["id"])) or {}
            try:
                b = int(x.get("beatability") or 0)
            except (TypeError, ValueError):
                b = 0
            r["beatability"] = min(3, max(1, b)) if b else None
            e = str(x.get("effort") or "").strip().upper()[:1]
            r["effort"] = e if e in ("S", "M", "L") else ""
    return rows


def _judge(rows, scope, comps, say):
    """The two shared tests, both from `_common`, both handed the scope AND the competitor set.

    A judge asked "is this ours?" without being shown what "ours" means guesses generously: that
    exact failure once fired a uniqueness flag on 14 of 18 sections. The criteria travel with the
    question.

    `brand_fit` is set HERE and nowhere else. The per-page pass has its own read of a page and is
    used only to drop the pages that are not our world at all; the idea's own fit is one value and
    one of these calls owns it.
    """
    if not rows:
        return rows
    by_id = {r["id"]: r for r in rows}
    for batch in _batches(rows, JUDGE_BATCH):
        for v in cm.ownability(batch, scope, comps):
            r = by_id.get(v.get("id"))
            if not r:
                continue
            r["ownability"] = {"verdict": v.get("verdict"), "why": v.get("why", ""),
                               "judged": bool(v.get("judged"))}
            if v.get("judged"):
                r["brand_fit"] = (v.get("brand_fit") or "").strip().upper()
                r["transplant_from"] = (v.get("transplant_from") or "").strip()
    for batch in _batches(rows, JUDGE_BATCH):
        for v in cm.linkability(batch, scope, comps):
            r = by_id.get(v.get("id"))
            if r:
                r["linkability"] = {"score": v.get("score"), "of": v.get("of", cm.LINKABILITY_OF),
                                    "verdict": v.get("verdict"), "why": v.get("why", ""),
                                    "judged": bool(v.get("judged"))}
    # An idea the model forgot comes back judged: False with no score. That is not a zero and it is
    # not a drop, so it is counted and said rather than quietly cut in `_cut` below.
    unjudged = sum(1 for r in rows if not (r.get("linkability") or {}).get("judged")
                   or not (r.get("ownability") or {}).get("judged"))
    say("Judged every idea on the two shared tests",
        "can we own it, and would anyone cite it"
        + ("; %d came back unjudged and were kept" % unjudged if unjudged else ""))
    return rows


def _cut(rows, say):
    """Drop the ideas that failed linkability, and protect the ones the measurement vouches for.

    The original drops below the floor rather than ranking low, so that is what happens here. But
    the cut is paired with a PROTECT rule, because good data hides in unpromising groups: an idea
    whose backing pages really pulled PROTECT_DOMAINS or more linking domains is never dropped by a
    model's score. The measurement is the harder evidence, and a 2 out of 4 does not outrank it.

    Writes: _work/competitors/dropped.json, so every cut is auditable rather than silent.
    """
    keep, dropped = [], []
    for r in rows:
        link = r.get("linkability") or {}
        # `judged` is the field, never the wording of `why`. An idea the pass forgot is unjudged,
        # which is not a score of zero and is not a decision to drop it, so it stays.
        failed = link.get("judged") and link.get("verdict") is False
        if failed and (r.get("pooled_follow_domains") or 0) < PROTECT_DOMAINS:
            dropped.append({"title": r["title"], "score": link.get("score"),
                            "follow_domains": r.get("pooled_follow_domains"),
                            "why": link.get("why", "")})
        else:
            keep.append(r)
    cm.save(WORK + "dropped.json", dropped)
    if dropped:
        say("Dropped the ideas nobody would cite",
            "%d dropped, %d kept; anything with %d or more linking domains was kept whatever its "
            "score" % (len(dropped), len(keep), PROTECT_DOMAINS))
    return keep


# ---- STEP H: deliver ---------------------------------------------------------------------------

def _deliver(rows, say):
    """H. The pool file, one idea row per idea, in the shared schema.

    Pure assembly. Every field is lifted from a step that already decided it, and nothing is
    invented here: title and angle from G2, format from the step D tag, proof from the step B
    counts, brand fit and the two verdicts from the shared tests, beatability and effort from G4.
    """
    out = []
    for r in rows:
        row = cm.blank_idea(r["id"], METHOD)
        row["title"] = r["title"]
        row["angle"] = r["angle"]
        row["format"] = r["format"]
        row["brand_fit"] = r.get("brand_fit", "")
        row["transplant_from"] = r.get("transplant_from", "")
        row["ownability"] = r.get("ownability") or row["ownability"]
        row["linkability"] = r.get("linkability") or row["linkability"]
        row["beatability"] = r.get("beatability")
        row["effort"] = r.get("effort", "")
        # The proof is the real measurement, one entry per backing page, so anyone can click through
        # and check it. `domains` is FOLLOW referring domains, which is the number that decided
        # everything upstream; the raw total is kept beside it so nothing is hidden.
        row["proof"] = [{"url": m["url"], "competitor": m["competitor"],
                         "domains": m["domains_follow"], "domains_total": m["domains_total"],
                         "backlinks": m["backlinks"],
                         "what": next((g["gap"] for g in (r.get("gaps") or [])
                                       if g["url"] == m["url"]), "")}
                        for m in r.get("members") or []]
        # Flagged, never hidden, and never folded into the angle text. The original added this
        # rule after its engine turned 1,143 of 2,213 ideas into calculators: an idea that needs
        # software rather than a document has to say so in a field the merge and the write phase
        # can both read.
        row["tool_escalation"] = bool(r.get("tool_escalation"))
        row["what_it_would_be"] = r.get("tool_escalation") or ""
        out.append(row)
    cm.save(OUTPUT, out)
    say("Wrote the competitor ideas",
        "%d ideas, each with the pages that prove the shape earns links" % len(out))
    return out


# ---- the builder ---------------------------------------------------------------------------------

def run(co, say, redo=False):
    """Method 1, end to end. Returns {"files": [...], "needs_review": [...]} or {"gate": {...}}.

    The gate is the one place this stops. When there is a shortlist and nobody has approved it, it
    hands the question up and writes nothing further; when the approved list is on file it carries
    straight on from there.
    """
    if cm.exists(OUTPUT) and not redo:
        say("Kept the competitor ideas", "already built; ask for a redo to rebuild them")
        return {"files": [OUTPUT], "needs_review": []}

    scope = cm.read("scope.md") or ""
    if not scope.strip():
        raise Blocked("There is no brand scope on file yet (assets/scope.md). Every idea is judged "
                      "against what this company can credibly own, so that has to exist first.")

    notes = []
    # A: candidates, shortlist, and the gate. All free, all before a penny is spent.
    cands = _candidates(co, say, redo)
    # A1b, before anyone judges the list: what each candidate says it does, in its own words. The
    # shortlist prompt is written to read that description and trust it over the domain name, and
    # without this step there was none to read.
    cands = _enrich(cands, say, redo)
    short = _shortlist(co, cands, say, redo)
    comps = approved()
    if comps is None:
        # Nobody has been asked yet. Propose and stop: write nothing further, spend nothing.
        say("Waiting on you", "the competitor list needs your eye before I spend anything")
        return {"gate": _gate(short, co)}
    if not comps:
        # A person looked at the proposal and kept nobody. That is an answer, not a missing one, so
        # it is not re-asked. The two cases are deliberately different.
        raise Blocked("You looked at the competitor list and kept nobody on it, so there is nothing "
                      "to study. Name the companies you would rather I looked at in Knowledge and "
                      "ask me again.")
    # A1c, still free and still before the paid step: a domain that does not resolve is repaired
    # or dropped here, never paid for. This runs on the approved list, so a name a person typed is
    # checked exactly like one the model picked.
    comps = _validate(comps, cands, say)
    validation = cm.read(WORK + "domain-validation.json") or {}
    for swap in validation.get("swapped") or []:
        notes.append("competitors.json: %s does not resolve, so %s was studied instead. If that is "
                     "the wrong company, correct the list in Knowledge and redo this method."
                     % (swap["from"], swap["to"]))
    if validation.get("dropped"):
        notes.append("competitors.json: %s could not be studied because the domain does not "
                     "resolve and no live alternative was found: %s. Nothing was spent on them."
                     % (sh.plural(len(validation["dropped"]), "competitor"),
                        ", ".join(d["domain"] for d in validation["dropped"])))
    if not comps:
        raise Blocked("Not one of the approved competitor domains resolves, so there is nothing to "
                      "study and nothing was spent. Check the spelling of the names in Knowledge — "
                      "a brand name typed where a domain belongs is the usual cause — and ask me "
                      "again.")
    _save_knowledge_competitors(comps, say)

    # B: the paid pull. Refuses before the first call when there is no balance.
    pages, empty = _pull(comps, say, redo)
    if empty:
        notes.append("competitors.json: %s returned no backlink data at all, so nothing they do is "
                     "in this study: %s" % (sh.plural(len(empty), "competitor"), ", ".join(empty)))

    # C, D, E: filter, tag by shape, read every kept page.
    master = cm.read(WORK + "master.json") if not redo else None
    if not master:
        kept, report, alarms = _filter(pages, say)
        for i, r in enumerate(kept, 1):
            r["row_id"] = i
        if alarms:
            notes.append("competitors.json: the filter kept fewer than %d pages for %s, which "
                         "usually means their editorial sits somewhere the rules did not expect. "
                         "Worth a look at _work/competitors/filter-report.json."
                         % (LOW_KEEP_ALARM, ", ".join(alarms)))
        kept = _tag(kept, co, say)
        # F0. The tagger names the same shape differently in each batch, so its labels are merged
        # into one canonical set BEFORE anything groups by format. It also names the shapes that
        # are not content assets at all, and those are skipped rather than fetched: the owner
        # measured 306 of 1,202 pages as junk that was scraped and then thrown away. Deciding the
        # format first makes them free.
        canon = fmt.canonicalise(kept, say)
        cm.save(WORK + "format-canonical.json", canon)
        junk = [r for r in kept if r.get("format_junk")]
        for r in junk:
            r["read_status"] = "SKIPPED (not a content asset)"
            r["body"] = ""
            r["headings"] = ""
        _read_rows, tally = _read([r for r in kept if not r.get("format_junk")], say)
        tally = dict(tally)
        tally["skipped"] = len(junk)         # the counts have to reconcile against the whole sheet
        cm.save(WORK + "read-tally.json", tally)
        if junk:
            notes.append("competitors.json: %s were shapes nobody studies — %s — so they were "
                         "never fetched and no idea was built on them."
                         % (sh.plural(len(junk), "page"), ", ".join(canon["junk"][:4])))
        cm.save(WORK + "master.json", kept)
        master = kept
    else:
        tally = cm.read(WORK + "read-tally.json") or {}
        say("Kept the page sheet", "%d pages read on an earlier run" % len(master))
    if tally.get("failed"):
        notes.append("competitors.json: %d of %d competitor pages would not load and are marked "
                     "FETCH FAILED rather than guessed at, so no idea was built on them."
                     % (tally["failed"], tally["rows"]))

    readable = [r for r in master if r.get("read_status") == "ok"]
    if not readable:
        raise Blocked("Not one competitor page would load, so there is nothing to read a format "
                      "off. This is usually a network problem or every site refusing the fetch. "
                      "Nothing was invented from the page titles.")

    # F: the answer this method exists to produce. The shapes F0 marked as not content assets are
    # out of it: counting a help-centre article as a "format that earns links" is the same split
    # signal F0 exists to remove, from the other direction.
    fmt_summary = _aggregate([r for r in master if not r.get("format_junk")], say)

    # G: rows into ideas, the repeats pooled, the traps checked, then judged and cut.
    raw, holes = _reason(readable, scope, co, comps, say)
    if holes:
        notes.append("competitors.json: %d pages never came back from the reasoning pass and are "
                     "not represented in the ideas." % holes)
    ideas = _collapse(raw, say)
    # G2.5. The string key above catches the identical titles; this catches the same build written
    # differently, which is the 97 merges it misses. It runs BEFORE the ids are minted so the pool
    # still numbers from a1001 with no gaps.
    ideas = _dedup(ideas, co, say, notes)
    # The id is minted once, here, and carried. `new_id` puts it in this method's own band (a1001
    # up) because the three finders never see each other's files and would otherwise all start at
    # a0001, handing the merge three different ideas wearing one id.
    for i, r in enumerate(ideas, 1):
        r["id"] = cm.new_id(i, METHOD)
    _traps(ideas, notes)
    ideas = _score(ideas, scope, say)
    ideas = _judge(ideas, scope, comps, say)
    ideas = _cut(ideas, say)

    # H.
    rows = _deliver(ideas, say)
    thin = [r for r in ideas if len({m["competitor"] for m in r.get("members") or []}) < 2]
    if thin and len(thin) > len(ideas) // 2:
        # Recurrence is the real signal. An idea from one page at one competitor might be a one-off;
        # eight pages across five competitors is a pattern.
        notes.append("competitors.json: %d of %d ideas rest on a single competitor. Prefer the ones "
                     "several competitors have built, which is the stronger evidence."
                     % (len(thin), len(ideas)))
    if not rows:
        notes.append("competitors.json: no idea survived the two shared tests, so this method "
                     "contributed nothing to the sheet this run.")
    return {"files": [OUTPUT], "needs_review": notes,
            "formats": fmt_summary[:10], "ideas": len(rows)}
