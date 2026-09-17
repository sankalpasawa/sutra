"""source_check.py — Writer step 2: SOURCE CHECK. Every fact the body actually uses gets its page read.

Reads:  write_body's output (sections with tagged prose and a provenance list) + the card index.
Writes: the SAME body shape, with the sentences that failed corrected, softened or removed and the
        provenance rebuilt to match; plus a report (source-check.json / source-check.md).

It replaces the planner's old verify step (2026-09-16). That one checked every card in the plan,
600 to 850 a run, about 1,000 model calls and 2.5 to 4 hours, and its "not supported" verdicts
were right about 30% of the time. Two bugs did most of the damage: a citation marker like `[11]`
inside a card's text was read as the claim's number, so the page was rejected for lacking an
"11"; and one failing claim marked its url bad for every other card citing it, which flagged
cards that were fine (20 of 20 sampled). Checking after the body is written means checking only
the 60 to 90 claims the article carries, one page read and one judge call each.

  a. FILTER, in code. A claim is a sentence carrying a [c<id>] tag. Markers ([11]) and tags are
     stripped before anything looks for a number. A claim is checked when it carries a real
     statistic (checks/digit_guard's idea of one: not a year, not a label, not a small number in
     passing) or names a source ("a 2025 SHRM survey found"). The writer's own analysis, a figure
     that is in none of the tagged cards or a sentence that compares or combines two cards, is
     `derived`: it is never judged against a page. Where the number can be recomputed from the
     cards (a sum, a difference, a ratio) code does that; otherwise it is left alone. A sentence
     about the research itself ("no collected source gives X") is skipped.
  b. CHECK each claim on its own. The card's page is fetched once (write/_common.fetch, the write
     phase's one door to the network), the judge (source-judge.md) reads the page's opening plus
     the passages around the claim's numbers. supported / not_supported / unreadable. Unreadable
     (the page will not load, or is under MIN_PAGE_CHARS) is "could not check" and is KEPT. There
     is NO url-wide spread: a verdict is about one claim and one page.
  c. HUNT a replacement for at most HUNT_CAP not_supported claims, most important first. Same
     queries prompt, same queued search as enrich, same judge. A hit swaps the url on the card and
     in the provenance.
  d. FIX what still fails, one model call per affected section (source-fix.md), in this order:
     correct the figure to what the page says, else soften (drop the exact figure, keep what the
     page supports), else remove the sentence and bridge the paragraph. Code enforces the rules:
     only the listed sentences and their paragraph may change, no new digit, no new tag; a
     rejected answer is retried once with the fault named, then the sentence is removed in code.
  e. REPORT. source-check.json and source-check.md carry every verdict, its reason and every
     before/after. The chat gets ONE line.
  f. RIVAL PERCENTAGES (Aparna's review, 2026-09-17), one pass after the per-claim check. When the
     body carries at least PCT_MIN_FIGURES literal percentages, ONE model call reads every tagged
     percentage sentence and flags pairs that would read as rival headline answers to the same
     question, even though they may be different survey questions, samples or dates. At most
     PCT_PAIR_CAP flagged pairs each get ONE fix call, which adds a distinguishing clause (what was
     asked, of whom, when) to whichever sentence is weaker, built only from that sentence's own
     card. Code rejects any answer that drops or changes a number, invents one the card does not
     carry, or touches a source tag. Its count rides on the same summary line as the rest.
"""
import difflib
import re

from .. import llm
from ..checks import digit_guard
from . import _common as C
from . import enrich, tags

# ---- the knobs, all named, all here ---------------------------------------------------------------
HUNT_CAP = 10                 # claims hunted per article; the hunt found a source for 8 of 30 in the
#                               experiment and the tail past ten costs 100+ calls for almost nothing
HUNT_QUERIES_PER_CLAIM = 3    # queries planned per claim (source-queries.md)
HUNT_PAGES_PER_CLAIM = 4      # candidate pages opened and judged before a claim is given up on
MIN_PAGE_CHARS = enrich.MIN_PAGE_CHARS   # under this a "page" is a wall or an error, not a source
FIX_RETRIES = 1               # a rejected fix is retried this many times before code removes the sentence
BRIDGE_RATIO = 0.8            # an unlisted sentence may move this little (connective words) and no more
PCT_MIN_FIGURES = 2           # fewer literal percentages than this in the whole body and the pass is
#                               skipped outright (Aparna's review, 2026-09-17): with one number there
#                               is no rival figure it could be read against, so there is nothing to check
PCT_PAIR_CAP = 5              # at most this many flagged pairs get a fix call. Her real fault was ONE
#                               pair in a whole article; a flood past a handful is the detector guessing

# A citation marker the research left inside a card's text: [11], [17]. Never a number of the claim's.
MARKER = re.compile(r"\[\d{1,3}\]")
# The sentence boundary the body writer's own provenance parse uses.
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_LIST_ITEM = re.compile(r"^(?:[-*+]\s|\d+[.)]\s)")
# "a 2025 SHRM survey found", "according to Gartner", "per LinkedIn data"
_ATTRIBUTION = re.compile(r"\b(according to|survey|study|studies|report|research|analysis|census|"
                          r"found that|found|estimates?|data from|per)\b", re.I)
_PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b(?:[A-Z][A-Za-z&]+|[A-Z]{2,})\b")
# The writer combining or comparing facts: analysis, not a sourced claim.
_COMPARISON = re.compile(r"\b(combined|together|in total|adds? up|sum|difference|gap|ratio|versus|vs\.?|"
                         r"compared (?:with|to)|twice|half|double|triple|percentage points?|points? higher|"
                         r"points? lower|times (?:more|less|higher|lower|the)|more than (?:double|twice)|"
                         r"the (?:same|difference) between)\b", re.I)
# A sentence about the research itself. No page can support it and none should be asked to.
_RESEARCH_NOTE = re.compile(r"\b(no|none of the|not one|neither)\b[^.]{0,60}\b(source|study|survey|dataset|page|"
                            r"material|report|figure)s?\b[^.]{0,40}\b(give|gives|state|states|report|reports|"
                            r"provide|provides|name|names|cite|cites|carry|carries|include|includes|say|says|"
                            r"break|breaks|publish|publishes|appear|appears)\b|"
                            r"\b(collected (?:source|material|page|study)s?|the sources collected|"
                            r"in the (?:collected|gathered) material|the research (?:collected|gathered)|"
                            r"text is cut off|not reconcilable)\b", re.I)
# A literal percentage, for the conflicting-percentages pass. Not every figure() is a percentage
# (a dollar amount, a day count), and this pass only ever cares about the ones that are.
_PCT = re.compile(r"\d+(?:\.\d+)?\s?%")


# ---- text helpers ---------------------------------------------------------------------------------

def strip_markers(text):
    """The claim as a reader sees it: no [11] citation markers, no [c<id>] tags."""
    t = MARKER.sub("", tags.BLOCK.sub("", text or ""))
    t = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", t))
    return t.strip()


def _norm_fig(fig):
    return digit_guard._norm(fig).lstrip("$£€").strip()


def figures(text):
    """Every figure in the text, as written, in order."""
    return digit_guard._figures(text or "")


def _is_label(text, fig):
    """A number glued to letters or brackets is part of a name: DS14, Type 2, 401(k), H1, Q3."""
    for m in re.finditer(r"(?<!\d)" + re.escape(fig) + r"(?!\d)", text):
        before = text[max(0, m.start() - 1):m.start()]
        after = text[m.end():m.end() + 1]
        if (before.isalpha() or after.isalpha() or after == "(" or before in "#-/"):
            continue
        return False
    return True


def stat_figures(clean):
    """The figures in a claim the argument leans on, digit_guard's rules first, then any two-or-more
    digit measurement that is not a year and not part of a label.

    digit_guard's shape test is built for the fabrication guard and is deliberately narrow (a bare
    "42 days" is not a statistic to it). A source check has to be a little wider: a reader who
    sees "42 days" wants it to be true just as much as "4,700 dollars". So: digit_guard's shapes,
    plus a bare integer of two or more digits, minus years and labels.
    """
    out = []
    for fig in figures(clean):
        if digit_guard.YEAR.match(fig):
            continue
        if digit_guard._is_statistic(clean, fig):
            out.append(fig)
            continue
        if len(re.sub(r"\D", "", fig)) >= 2 and not _is_label(clean, fig):
            out.append(fig)
    return list(dict.fromkeys(out))


def _named_source(clean):
    """A sentence that attributes its claim to a named body, with or without a number."""
    if not _ATTRIBUTION.search(clean or ""):
        return False
    return bool(_PROPER.search(clean or ""))


def _card_text(card):
    return strip_markers((card or {}).get("verbatim", "")) + " " + strip_markers((card or {}).get("gloss", ""))


def _card_figs(card):
    return {_norm_fig(f) for f in figures(_card_text(card))}


def _to_float(fig):
    try:
        return float(_norm_fig(fig).rstrip("%"))
    except ValueError:
        return None


def follows_from(fig, card_figs):
    """Does a figure the writer wrote follow from the cards' figures by a sum, a difference, a ratio
    or a percentage? Rounding to the written precision is allowed. This is the only "check" a
    derived claim gets, because no page states the writer's own arithmetic."""
    want = _to_float(fig)
    if want is None:
        return False
    vals = [v for v in (_to_float(f) for f in card_figs) if v is not None]
    decimals = len(fig.split(".")[1]) if "." in fig else 0

    def close(x):
        return abs(round(x, decimals) - want) < 10 ** (-decimals) / 2 + 1e-9

    if any(close(v) for v in vals):
        return True
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            cands = [a + b, abs(a - b)]
            if b:
                cands += [a / b, 100.0 * a / b, 100.0 * (a - b) / b]
            if a:
                cands += [b / a, 100.0 * b / a, 100.0 * (b - a) / a]
            if any(close(x) for x in cands):
                return True
    return False


# ---- reading the body ------------------------------------------------------------------------------

def _blocks(prose):
    return (prose or "").split("\n\n")


def _is_heading(block):
    return block.strip().startswith("#")


def _units(block):
    """The editable units of a block: sentences of a paragraph, or the lines of a list or table.
    Returns (units, joiner)."""
    lines = [ln for ln in block.split("\n") if ln.strip()]
    if not lines:
        return [], " "
    table = any(ln.strip().startswith("|") for ln in lines)
    listy = sum(1 for ln in lines if _LIST_ITEM.match(ln.strip())) >= max(1, (len(lines) + 1) // 2)
    if table or listy:
        return lines, "\n"
    return [s for s in _SENT_END.split(" ".join(lines).strip()) if s.strip()], " "


def claims_in(prose):
    """Every tagged unit in a section: {block, unit, sentence, clean, card_ids}. One entry per unit,
    even when the unit carries several tags: the sentence is the claim."""
    out = []
    for bi, block in enumerate(_blocks(prose)):
        if _is_heading(block):
            continue
        units, _joiner = _units(block)
        for ui, unit in enumerate(units):
            ids = list(dict.fromkeys(tags.ids(unit)))
            if not ids:
                continue
            # a list item's own number ("10. ...") is structure, never a statistic of the claim's
            out.append({"block": bi, "unit": ui, "sentence": unit.strip(),
                        "clean": strip_markers(_LIST_ITEM.sub("", unit.strip())), "card_ids": ids})
    return out


def _headings_text(body):
    heads = []
    for s in body.get("sections") or []:
        heads.append(s.get("headline") or "")
        heads += re.findall(r"^###\s+(.+?)\s*$", s.get("prose") or "", re.M)
    return " ".join(heads)


def _is_brand(card):
    cid = C.nid((card or {}).get("card_id"))
    return str((card or {}).get("tag", "")).startswith("brand") or (isinstance(cid, int) and 8001 <= cid < 9001)


# ---- a. the filter --------------------------------------------------------------------------------

def classify(body, idx):
    """Every tagged claim in the body, classified: check / derived / research_note / skip.

    `check` claims carry the one card they are judged against (the card whose text carries the
    claim's figures, or the only card when the claim has no figure and names a source).
    """
    heads = {_norm_fig(f) for f in figures(_headings_text(body))}
    claims = []
    n = 0
    for si, sec in enumerate(body.get("sections") or []):
        for c in claims_in(sec.get("prose") or ""):
            n += 1
            clean = c["clean"]
            cards = [idx.get(cid) for cid in c["card_ids"]]
            cards = [k for k in cards if k]
            rec = dict(c, id=n, section=si, section_heading=sec.get("headline") or "", card_id=None,
                       source_url=None, figures=stat_figures(clean), kind="skip", why="", verdict=None,
                       priority=(1, si, c["block"], c["unit"]))
            claims.append(rec)
            if not cards:
                rec["why"] = "its tag names no card in the index"
                continue
            if all(_is_brand(k) for k in cards):
                rec["why"] = "the company's own material is not checked against the web"
                continue
            cards = [k for k in cards if not _is_brand(k)]
            if _RESEARCH_NOTE.search(clean):
                rec["kind"], rec["why"] = "research_note", "a sentence about the research itself; no page can support it"
                continue
            figs = rec["figures"]
            if not figs:
                if _named_source(clean) and len(cards) == 1:
                    rec["kind"], rec["why"] = "check", "names a source and is cited to one card"
                    rec["card_id"], rec["source_url"] = cards[0]["card_id"], (cards[0].get("source_urls") or [None])[0]
                elif _named_source(clean):
                    rec["kind"], rec["why"] = "derived", "names a source but draws on %d cards" % len(cards)
                else:
                    rec["why"] = "no statistic and no named source; ordinary writing that carries a tag"
                continue
            if any(_norm_fig(f) in heads for f in figs):
                rec["priority"] = (0, si, c["block"], c["unit"])
            want = {_norm_fig(f) for f in figs}
            carriers = [k for k in cards if want <= _card_figs(k)]
            if carriers and (len(cards) == 1 or not _COMPARISON.search(clean)):
                k = carriers[0]
                rec["kind"], rec["card_id"] = "check", k["card_id"]
                rec["source_url"] = (k.get("source_urls") or [None])[0]
                rec["why"] = "carries a statistic the card states"
                continue
            union = set()
            for k in cards:
                union |= _card_figs(k)
            rec["kind"] = "derived"
            missing = [f for f in figs if _norm_fig(f) not in union]
            if not missing:
                rec["why"] = "the writer's own comparison of figures that are all in the tagged cards"
                rec["derived_ok"] = True
            else:
                ok_ = all(follows_from(f, union) for f in missing)
                rec["derived_ok"] = ok_
                rec["why"] = ("a figure the writer worked out from the tagged cards (%s); it follows from them"
                              if ok_ else
                              "a figure in none of the tagged cards (%s) that code could not derive from them; "
                              "left as written") % ", ".join(missing)
    return claims


# ---- b. the judge ---------------------------------------------------------------------------------

def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"(\d),(\d)", r"\1\2", s)
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def page_window(claim_text, page):
    """What the judge reads: the page's opening (title + abstract, which carry the SUBJECT) plus the
    neighbourhood of each number the claim depends on. The first N raw characters of a heavy site
    is its nav menu, so a claim there was always judged unsupported."""
    text = " ".join(page.split())
    if len(text) <= C.PAGE_CHARS:
        return text
    head = text[:C.PAGE_CHARS // 4]
    budget, low = C.PAGE_CHARS - len(head), text.lower()
    nums = [n for n in re.findall(r"\d[\d,.]*%?", _norm(claim_text)) if len(re.sub(r"[^\d]", "", n)) >= 2]
    words = {w for w in re.findall(r"[a-z]{5,}", (claim_text or "").lower())}
    hits = []
    for n in dict.fromkeys(nums):
        for m in re.finditer(r"(?<!\d)" + re.escape(n.lower()) + r"(?!\d)", low):
            at = m.start()
            near = low[max(0, at - 700):at + 700]
            hits.append((sum(1 for w in words if w in near), at))
    hits.sort(reverse=True)
    windows, taken, used = [], 0, []
    for _score, at in hits:
        span = min(3000, budget - taken)
        if span < 600:
            break
        s = max(0, at - span // 2)
        if any(abs(s - p) < span for p in used):
            continue
        used.append(s)
        windows.append(text[s:s + span])
        taken += span
    return head + ("\n…\n" + "\n…\n".join(windows) if windows else text[len(head):len(head) + budget])


def judge(card, claim_text, url, page):
    """Does THIS page support THIS claim, about the same subject? (supports, quote, note).
    Markers are stripped from everything the judge reads, so `[11]` is never the claim's number."""
    verbatim = strip_markers(card.get("verbatim", ""))
    r = llm.json_call(C.prompt("source-judge", gloss=strip_markers(card.get("gloss", "")), verbatim=verbatim,
                               claim=claim_text, url=url, page=page_window(claim_text + " " + verbatim, page)),
                      timeout=C.LONG_CALL_TIMEOUT) or {}
    return bool(r.get("supports")), str(r.get("quote") or "")[:400], str(r.get("note") or "")[:200]


class _Pages:
    """Each url fetched once per run, however many claims cite it."""

    def __init__(self):
        import threading
        self._lock, self._got = threading.Lock(), {}

    def get(self, url):
        with self._lock:
            if url in self._got:
                return self._got[url]
        page = C.fetch(url)
        with self._lock:
            self._got[url] = page
        return page


def readable(page):
    return not page.startswith("__ERR__") and len(page.strip()) >= MIN_PAGE_CHARS


def check_one(claim, card, pages):
    """One claim, one page, one verdict. Writes verdict / reason / evidence onto the claim."""
    url = claim.get("source_url")
    if not url:
        claim.update(verdict="not_supported", reason="the card carries no source url", evidence="")
        return claim
    page = pages.get(url)
    if not readable(page):
        claim.update(verdict="unreadable", evidence="",
                     reason=("the page would not load (%s)" % page[7:] if page.startswith("__ERR__")
                             else "the page has under %d characters, a wall or an error, not a source" % MIN_PAGE_CHARS))
        return claim
    try:
        ok_, quote, note = judge(card, claim["clean"], url, page)
    except Exception as e:  # noqa: BLE001 — a judge that fails is a claim we could not check, never a wrong one
        claim.update(verdict="unreadable", evidence="", reason="the judge could not answer (%s)" % type(e).__name__)
        return claim
    claim.update(verdict="supported" if ok_ else "not_supported", evidence=quote,
                 reason=(note or ("the page states it" if ok_ else "the page does not state this about this subject")))
    return claim


def check_all(claims, idx, pages):
    todo = [c for c in claims if c["kind"] == "check"]
    with llm.pool() as ex:
        list(ex.map(lambda c: check_one(c, idx[c["card_id"]], pages), todo))
    return todo


# ---- c. the hunt ----------------------------------------------------------------------------------

def _plan_queries(card, claim_text):
    try:
        q = llm.json_call(C.prompt("source-queries", gloss=strip_markers(card.get("gloss", "")),
                                   verbatim=strip_markers(card.get("verbatim", "")) or claim_text,
                                   n=HUNT_QUERIES_PER_CLAIM), timeout=C.LONG_CALL_TIMEOUT) or {}
    except Exception:  # noqa: BLE001 — a failed plan is a claim left as it was, never a crash
        return []
    return [str(x).strip() for x in (q.get("queries") or []) if str(x).strip()][:HUNT_QUERIES_PER_CLAIM]


def hunt(claims, idx, pages, cap=HUNT_CAP):
    """Find a new page for up to `cap` not_supported claims, most important first. Every claim's
    queries are planned first and bought in ONE queued batch (enrich.search_many), deduped across
    claims. The first page the judge confirms wins: it becomes the card's source and the claim's.
    Returns the hunt log."""
    failed = sorted([c for c in claims if c["verdict"] == "not_supported"], key=lambda c: c["priority"])
    picked, seen = [], set()
    for c in failed:
        if c["card_id"] in seen:
            continue
        seen.add(c["card_id"])
        picked.append(c)
        if len(picked) >= cap:
            break
    if not picked:
        return []
    route_name, route_note = enrich.route()
    quiet = lambda *a, **k: None  # noqa: E731 — the chat gets one line from this step, not one per search
    with llm.pool() as ex:
        plans = list(ex.map(lambda c: _plan_queries(idx[c["card_id"]], c["clean"]), picked))
    every = [q for qs in plans for q in qs]
    exclude = {u for c in picked for u in (idx[c["card_id"]].get("source_urls") or []) if u}
    found, _cost, missing = enrich.search_many(every, route_name, quiet, exclude=exclude)
    missing = set(missing)

    def finish(i):
        c, qs = picked[i], plans[i]
        card = idx[c["card_id"]]
        e = {"claim_id": c["id"], "card_id": c["card_id"], "claim": c["clean"][:160], "queries": qs,
             "route": route_name, "searched": False, "pages_read": 0, "new_url": None, "quote": ""}
        if not qs:
            e["outcome"] = "no queries could be planned"
            return e
        if all(q in missing or q not in found for q in qs):
            e["outcome"] = "the search did not come back (" + route_note + ")"
            return e
        e["searched"] = True
        urls = enrich._interleave([found.get(q) or [] for q in qs])
        for u in urls:
            if e["pages_read"] >= HUNT_PAGES_PER_CLAIM:
                break
            page = pages.get(u)
            if not readable(page):
                continue
            e["pages_read"] += 1
            try:
                ok_, quote, _note = judge(card, c["clean"], u, page)
            except Exception:  # noqa: BLE001 — one page that blows up is one page skipped
                continue
            if ok_:
                e["new_url"], e["quote"] = u, quote
                break
        e["outcome"] = "a page that supports it was found" if e["new_url"] else \
            ("%d pages read, none supports it" % e["pages_read"] if e["pages_read"] else "no candidate page would load")
        return e

    with llm.pool() as ex:
        log = list(ex.map(finish, range(len(picked))))
    for e in log:
        if not e["new_url"]:
            continue
        card = idx[e["card_id"]]
        old = list(card.get("source_urls") or [])
        # THE NEW PAGE IS THE SOURCE. The url that was judged and failed (the first, the one the
        # claim was checked against) does not ride along behind it; any unjudged backup does.
        card["source_urls"] = [e["new_url"]] + [u for u in old[1:] if u != e["new_url"]]
        card.pop("needs_source", None)
        e["old_url"] = old[0] if old else None
        for c in claims:
            if c["card_id"] == e["card_id"] and c["verdict"] == "not_supported":
                c.update(verdict="supported", replaced=True, source_url=e["new_url"], evidence=e["quote"],
                         reason="the original page did not support it; a new page that does was found")
    return log


# ---- d. the fix -----------------------------------------------------------------------------------

def _fig_set(text):
    """The figures of a piece of prose, tags and markers removed first: the 9 in [c9] is an id."""
    return {_norm_fig(f) for f in figures(strip_markers(text))}


def _plain(text):
    return re.sub(r"[^a-z0-9%$ ]+", "", " ".join(strip_markers(text).lower().split()))


def _unit_ok(old_unit, new_block, new_units):
    """An unlisted sentence must still be there: word for word inside the new paragraph (a bridge
    may join it to its neighbour with a connective), or as one sentence moved by connective words
    only."""
    a = _plain(old_unit)
    if not a or a in _plain(new_block):
        return True
    for nu in new_units:
        if difflib.SequenceMatcher(None, a, _plain(nu)).ratio() >= BRIDGE_RATIO:
            return True
    return False


def validate_block(old_block, new_block, listed_units, allowed_figs):
    """The code gate on one rewritten paragraph. Returns "" when it passes, else the fault, named.
    listed_units: the sentences the model was allowed to change. allowed_figs: figures it may
    introduce (normalised), which are only the ones the source page states for a correction."""
    old_units, _j = _units(old_block)
    new_units, _j2 = _units(new_block)
    new_figs = _fig_set(new_block) - _fig_set(old_block) - set(allowed_figs)
    if new_figs:
        return "it introduced a figure that is neither in the paragraph nor on the source page: %s" % ", ".join(sorted(new_figs))
    new_tags = tags.id_set(new_block) - tags.id_set(old_block)
    if new_tags:
        return "it introduced a source tag that was not in the paragraph: %s" % sorted(new_tags)[:3]
    if len(new_units) > len(old_units):
        return "it added a sentence; only the listed sentences may change, and a bridge uses the words already there"
    listed = {" ".join(u.split()) for u in listed_units}
    for u in old_units:
        if " ".join(u.split()) in listed:
            continue
        if not _unit_ok(u, new_block, new_units):
            return "it changed a sentence that was not on the list: \"%s\"" % strip_markers(u)[:90]
    return ""


def _remove_units(block, drop):
    """Code's own fallback: the listed sentences taken out, nothing else touched."""
    units, joiner = _units(block)
    drop = {" ".join(u.split()) for u in drop}
    keep = [u for u in units if " ".join(u.split()) not in drop]
    if joiner == "\n":
        # a table left with only its header and separator row, or a list left with nothing, is gone
        real = [u for u in keep if not (u.strip().startswith("|") and set(u.strip()) <= set("-| :"))]
        if not real or (all(u.strip().startswith("|") for u in real) and len(real) <= 1):
            return ""
    return joiner.join(keep).strip()


def _fix_prompt(sec, blocks, todo_by_block, failure=""):
    paras, lines = [], []
    for bi in sorted(todo_by_block):
        paras.append("PARAGRAPH %d:\n%s" % (bi, blocks[bi]))
        for c in todo_by_block[bi]:
            said = ("The page says: \"%s\"" % c["evidence"]) if c.get("evidence") else "The page does not state this."
            lines.append("- paragraph %d: \"%s\"\n  Figure(s) in question: %s. %s %s"
                         % (bi, c["sentence"], ", ".join(c["figures"]) or "(none; the attribution itself)",
                            said, ("(" + c.get("reason", "") + ")") if c.get("reason") else ""))
    return C.prompt("source-fix", heading=sec.get("headline") or "", paragraphs="\n\n".join(paras),
                    sentences="\n".join(lines),
                    failure=("\nYOUR LAST ANSWER WAS REJECTED: %s. Fix that and answer again.\n" % failure) if failure else "")


def fix_section(sec, claims, say=lambda *a: None):
    """Correct, soften or remove the failing sentences of ONE section. Mutates sec['prose'].
    Returns the list of changes made ({claim_id, action, before, after, by})."""
    blocks = _blocks(sec.get("prose") or "")
    todo_by_block = {}
    for c in claims:
        todo_by_block.setdefault(c["block"], []).append(c)
    allowed = {bi: {_norm_fig(f) for c in cs for f in figures(c.get("evidence") or "")} for bi, cs in todo_by_block.items()}
    listed = {bi: [c["sentence"] for c in cs] for bi, cs in todo_by_block.items()}
    changes, failure, new_blocks, actions = [], "", {}, {}
    for attempt in range(FIX_RETRIES + 1):
        try:
            r = llm.json_call(_fix_prompt(sec, blocks, todo_by_block, failure), timeout=C.LONG_CALL_TIMEOUT) or {}
        except Exception as e:  # noqa: BLE001 — a model that fails is a fix that falls back to code
            failure = "the model returned nothing usable (%s)" % type(e).__name__
            new_blocks = {}
            continue
        got = {}
        for p in (r.get("paragraphs") or []):
            try:
                bi = int(p.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            if bi in todo_by_block:
                got[bi] = str(p.get("text") or "").strip()
        acts = {}
        for s in (r.get("sentences") or []):
            if isinstance(s, dict):
                acts[" ".join(str(s.get("sentence") or "").split())] = str(s.get("action") or "").strip().lower()
        faults = []
        for bi in todo_by_block:
            if bi not in got:
                faults.append("paragraph %d was not returned" % bi)
                continue
            why = validate_block(blocks[bi], got[bi], listed[bi], allowed[bi])
            if why:
                faults.append("paragraph %d: %s" % (bi, why))
        if not faults:
            new_blocks, actions = got, acts
            break
        failure = "; ".join(faults)
        new_blocks = {}
    for bi, cs in sorted(todo_by_block.items()):
        if bi in new_blocks:
            new_units, _j = _units(new_blocks[bi])
            for c in cs:
                act = actions.get(" ".join(c["sentence"].split()), "")
                after, score = _after_of(c, new_units)
                # WHAT HAPPENED IS READ FROM THE TEXT, not from what the model says it did: a
                # sentence that is gone was removed whatever the label, and a sentence that is
                # still there was not.
                if after is None or (act == "remove" and score < 0.75):
                    act, after = "removed", None
                elif _fig_set(after) - _fig_set(c["sentence"]):
                    act = "corrected"
                elif act == "correct" and _fig_set(after) != _fig_set(c["sentence"]):
                    act = "corrected"
                else:
                    act = "softened"
                changes.append({"claim_id": c["id"], "card_id": c["card_id"], "section": sec.get("headline") or "",
                                "action": act, "before": c["sentence"], "after": after or "", "by": "model"})
            blocks[bi] = new_blocks[bi]
        else:
            blocks[bi] = _remove_units(blocks[bi], listed[bi])
            for c in cs:
                changes.append({"claim_id": c["id"], "card_id": c["card_id"], "section": sec.get("headline") or "",
                                "action": "removed", "before": c["sentence"], "after": "", "by": "code",
                                "why": "the model's rewrite was rejected twice: " + failure})
    sec["prose"] = "\n\n".join(b for b in blocks if b.strip()).strip()
    sec["words"] = len(sec["prose"].split())
    return changes


def _after_of(claim, new_units):
    """Which new sentence the listed one became, if any: (the closest by text above a low bar, its
    similarity). (None, 0.0) when nothing in the paragraph is recognisably the same sentence."""
    a = " ".join(strip_markers(claim["sentence"]).split())
    best, score = None, 0.0
    for nu in new_units:
        b = " ".join(strip_markers(nu).split())
        r = difflib.SequenceMatcher(None, a, b).ratio()
        if r > score:
            best, score = nu, r
    if best is None or score < 0.45:
        return None, 0.0
    return best.strip(), score


# ---- f. the conflicting-percentages pass ------------------------------------------------------------
#
# Aparna's review, 2026-09-17: blog 3 said "TestGorilla's 2025 report says 53% of employers have
# ditched degree rules," and, in a different section, "The one adoption figure you can cite with any
# confidence is narrower. It's 76%." Both read as the headline answer to the same question, and
# nothing told the reader the two numbers were not actually rivals: different survey questions,
# wearing the same headline. This pass looks for that shape, once, after the per-claim check has
# already run, and fixes it by ADDING what the weaker sentence is missing (what was asked, of whom,
# when), never by touching a number. It runs on claims_in the same way the filter above does, so the
# sentence split and the tag read are the one definition every pass in this file shares.

def pct_claims(body):
    """Every TAGGED sentence in the body, as it stands after the per-claim fix, that carries a
    literal percentage. A sentence with no [c...] tag is not eligible: without a card behind it
    there is no source to build the distinguishing clause from, and this pass never invents one."""
    out = []
    for si, sec in enumerate(body.get("sections") or []):
        for c in claims_in(sec.get("prose") or ""):
            pcts = _PCT.findall(c["clean"])
            if pcts:
                out.append(dict(c, section=si, heading=sec.get("headline") or "", percentages=pcts))
    return out


def _pct_prompt_lines(claims):
    return "\n".join("%d. [%s] %s" % (i + 1, c["heading"], c["clean"]) for i, c in enumerate(claims))


def find_pct_pairs(claims):
    """ONE model call over the WHOLE body: which sentence numbers read as rival headline answers to
    the same question. A malformed or missing reply is no pairs found, never a crash. Pairs are
    validated against the real sentence numbers, deduped, and capped at PCT_PAIR_CAP."""
    if len(claims) < 2:
        return []
    try:
        r = llm.json_call(C.prompt("pct-pairs", sentences=_pct_prompt_lines(claims)),
                          timeout=C.LONG_CALL_TIMEOUT) or {}
    except Exception:  # noqa: BLE001, a call that fails found no pairs, it did not crash the check
        return []
    n = len(claims)
    seen, pairs = set(), []
    for p in (r.get("pairs") or []):
        if not isinstance(p, dict):
            continue
        try:
            a, b = int(p.get("a")), int(p.get("b"))
        except (TypeError, ValueError):
            continue
        if not (1 <= a <= n and 1 <= b <= n) or a == b:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((claims[a - 1], claims[b - 1], str(p.get("why") or "")))
        if len(pairs) >= PCT_PAIR_CAP:
            break
    return pairs


def _pct_fix_fault(old_sentence, new_sentence, card):
    """The fix's own code gate: no number lost or changed, no number introduced that is not on the
    card's own text, no source tag added or dropped. "" when the edit is safe to apply."""
    old_figs, new_figs = _fig_set(old_sentence), _fig_set(new_sentence)
    if not old_figs <= new_figs:
        return "it dropped or changed a number that was already there"
    added = new_figs - old_figs
    allowed = {_norm_fig(f) for f in figures(_card_text(card))}
    if not added <= allowed:
        return "it introduced a number that is not on its own source (%s)" % ", ".join(sorted(added - allowed))
    if tags.id_set(new_sentence) != tags.id_set(old_sentence):
        return "it changed the source tag"
    return ""


def fix_pct_pair(a, b, why, idx):
    """ONE fix call for one flagged pair. The model decides which of the two sentences is weaker and
    returns only that one, edited. Returns (claim, new sentence, "") on a safe edit, or
    (None, None, reason) when nothing could be safely applied. The article is left exactly as it
    was, and the reason is there to report, never to raise."""
    card_a = idx.get(a["card_ids"][0]) if a["card_ids"] else None
    card_b = idx.get(b["card_ids"][0]) if b["card_ids"] else None
    if not card_a or not card_b:
        return None, None, "one of the two carries no card to build the clause from"
    try:
        r = llm.json_call(C.prompt("pct-fix", sentence_a=a["clean"], card_a=_card_text(card_a),
                                   sentence_b=b["clean"], card_b=_card_text(card_b), why=why),
                          timeout=C.LONG_CALL_TIMEOUT) or {}
    except Exception as e:  # noqa: BLE001, a fix call that fails leaves both sentences exactly as written
        return None, None, "the fix call failed (%s)" % type(e).__name__
    pick = {"a": (a, card_a), "b": (b, card_b)}.get(str(r.get("edit") or "").strip().lower())
    if not pick:
        return None, None, "the model did not say which of the two sentences to edit"
    claim, card = pick
    new_sentence = str(r.get("sentence") or "").strip()
    if not new_sentence:
        return None, None, "no replacement sentence came back"
    fault = _pct_fix_fault(claim["sentence"], new_sentence, card)
    if fault:
        return None, None, fault
    return claim, new_sentence, ""


def _apply_pct_fix(body, claim, new_sentence):
    """Swap the one sentence inside its section's prose, found by exact text match, and nothing
    else. False when the sentence has already moved (a second pair naming the same sentence, or a
    block that no longer exists). The edit is skipped rather than guessed at."""
    secs = body.get("sections") or []
    if claim["section"] >= len(secs):
        return False
    sec = secs[claim["section"]]
    blocks = _blocks(sec.get("prose") or "")
    if claim["block"] >= len(blocks):
        return False
    units, joiner = _units(blocks[claim["block"]])
    old = claim["sentence"].strip()
    for i, u in enumerate(units):
        if u.strip() == old:
            units[i] = new_sentence
            blocks[claim["block"]] = joiner.join(units).strip()
            sec["prose"] = "\n\n".join(bl for bl in blocks if bl.strip()).strip()
            return True
    return False


def pct_pass(body, idx):
    """The whole pass: filter, find pairs, fix. Never raises; any failure leaves the body exactly as
    the per-claim check left it. Returns the counts and details the report and the summary line read."""
    claims = pct_claims(body)
    total_figs = sum(len(c["percentages"]) for c in claims)
    if total_figs < PCT_MIN_FIGURES:
        return {"skipped": True, "total_percentages": total_figs, "pairs_found": 0, "fixed": [], "rejected": []}
    pairs = find_pct_pairs(claims)
    fixed, rejected = [], []
    for a, b, why in pairs:
        claim, new_sentence, fault = fix_pct_pair(a, b, why, idx)
        if fault:
            rejected.append({"a": a["clean"][:140], "b": b["clean"][:140], "why": why, "reason": fault})
            continue
        other = b if claim is a else a
        if _apply_pct_fix(body, claim, new_sentence):
            fixed.append({"section": claim["heading"], "before": claim["sentence"], "after": new_sentence,
                          "other": other["sentence"], "why": why})
        else:
            rejected.append({"a": a["clean"][:140], "b": b["clean"][:140], "why": why,
                             "reason": "the sentence had already changed by the time the fix was applied"})
    return {"skipped": False, "total_percentages": total_figs, "pairs_found": len(pairs),
            "fixed": fixed, "rejected": rejected}


# ---- provenance, rebuilt ----------------------------------------------------------------------------

def provenance(prose, idx):
    """The same shape write_body builds: one row per card cited, in order of first appearance,
    read from the prose as it now stands so a swapped url or a removed sentence is reflected."""
    seen, prov = set(), []
    for m in tags.BLOCK.finditer(prose or ""):
        for cid in tags._block_ids(m.group(0)):
            if cid in seen:
                continue
            seen.add(cid)
            c = idx.get(cid) or {}
            claim = re.split(r"(?<=[.!?])\s", prose[:m.start()])[-1].strip()[-160:]
            prov.append({"card_id": cid, "source_url": (c.get("source_urls") or [None])[0],
                         "is_number": C.has_number(strip_markers(c.get("verbatim", ""))), "claim": claim})
    return prov


# ---- e. the report ---------------------------------------------------------------------------------

def _counts(claims, hunt_log, changes):
    checked = [c for c in claims if c["kind"] == "check"]
    return {"claims_tagged": len(claims),
            "checked": len(checked),
            "supported": sum(1 for c in checked if c["verdict"] == "supported" and not c.get("replaced")),
            "unreadable": sum(1 for c in checked if c["verdict"] == "unreadable"),
            "not_supported": sum(1 for c in checked if c["verdict"] == "not_supported"),
            "replaced": sum(1 for c in checked if c.get("replaced")),
            "hunted": len(hunt_log),
            "corrected": sum(1 for x in changes if x["action"] == "corrected"),
            "softened": sum(1 for x in changes if x["action"] == "softened"),
            "removed": sum(1 for x in changes if x["action"] == "removed"),
            "derived": sum(1 for c in claims if c["kind"] == "derived"),
            "derived_ok": sum(1 for c in claims if c["kind"] == "derived" and c.get("derived_ok")),
            "research_notes": sum(1 for c in claims if c["kind"] == "research_note"),
            "skipped": sum(1 for c in claims if c["kind"] == "skip")}


def summary_line(n, pct=None):
    """The ONE line the chat shows. Zero counts are left out, so it reads as a sentence, not a form.
    pct is pct_pass's own return value; omitted or a skip adds nothing to the line."""
    if not n["checked"]:
        base = "Checked 0 facts: the body cites no statistic that a page could confirm"
    else:
        parts = ["%d fine" % n["supported"]]
        if n["unreadable"]:
            parts.append("%d could not be read (kept)" % n["unreadable"])
        if n["replaced"]:
            parts.append(C.sh.plural(n["replaced"], "new source"))
        if n["corrected"]:
            parts.append("%d corrected" % n["corrected"])
        if n["softened"]:
            parts.append("%d softened" % n["softened"])
        if n["removed"]:
            parts.append("%d removed" % n["removed"])
        base = "Checked %s: %s" % (C.sh.plural(n["checked"], "fact"), ", ".join(parts))
    if pct and pct.get("fixed"):
        base += "; " + C.sh.plural(len(pct["fixed"]), "rival percentage pair") + " clarified"
    return base


def render_md(n, claims, hunt_log, changes, pct=None):
    L = ["# Source check", "",
         "Every fact the body cites, checked against the page it cites. One verdict per claim; a page "
         "that would not load counts as unchecked and the claim is kept. Nothing here spreads one bad "
         "url to other claims.", "",
         "## The counts", "",
         "| What | Count |", "|---|---|",
         "| Claims carrying a source tag | %d |" % n["claims_tagged"],
         "| Checked against their page | %d |" % n["checked"],
         "| Supported by the page | %d |" % n["supported"],
         "| Page could not be read (kept) | %d |" % n["unreadable"],
         "| Given a new source by the hunt | %d |" % n["replaced"],
         "| Hunted (cap %d) | %d |" % (HUNT_CAP, n["hunted"]),
         "| Corrected to the page's figure | %d |" % n["corrected"],
         "| Softened (figure removed) | %d |" % n["softened"],
         "| Removed | %d |" % n["removed"],
         "| The writer's own analysis (not judged against a page) | %d, %d of them recomputed from the cards |" % (n["derived"], n["derived_ok"]),
         "| Notes about the research itself (skipped) | %d |" % n["research_notes"],
         "| Ordinary sentences with a tag (skipped) | %d |" % n["skipped"], ""]
    if changes:
        L += ["## What changed", ""]
        for x in changes:
            L += ["**%s** in \"%s\" (%s)" % (x["action"].capitalize(), x["section"], x["by"]), "",
                  "- Before: %s" % strip_markers(x["before"]),
                  "- After: %s" % (strip_markers(x["after"]) if x["after"] else "(sentence removed)")]
            if x.get("why"):
                L.append("- Why: %s" % x["why"])
            L.append("")
    if hunt_log:
        L += ["## The hunt", ""]
        for e in hunt_log:
            L.append("- %s: %s%s" % (e["claim"][:120], e["outcome"], (" -> " + e["new_url"]) if e["new_url"] else ""))
        L.append("")
    if pct and not pct.get("skipped") and (pct.get("fixed") or pct.get("rejected")):
        L += ["## Rival percentages", "",
             "Sentences that carry different percentages but would read as rival answers to the same "
             "question. The weaker one gets a clause naming what was asked, of whom, and when; no "
             "number is ever changed.", ""]
        for x in pct.get("fixed") or []:
            L += ['**Clarified** in "%s"' % x["section"], "",
                 "- Before: %s" % strip_markers(x["before"]), "- After: %s" % strip_markers(x["after"]),
                 "- Read against: %s" % strip_markers(x["other"]), ""]
        for x in pct.get("rejected") or []:
            L.append("- Flagged but not fixed: \"%s\" vs \"%s\" (%s)" % (x["a"], x["b"], x["reason"]))
        if pct.get("rejected"):
            L.append("")
    L += ["## Every verdict", ""]
    for c in claims:
        if c["kind"] == "check":
            v = c.get("verdict") or "?"
            L.append("- [%s] %s (card %s, %s): %s" % (v.upper().replace("_", " "), c["clean"][:140], c["card_id"],
                                                     c.get("source_url") or "no url", c.get("reason", "")))
        elif c["kind"] in ("derived", "research_note"):
            L.append("- [%s] %s: %s" % (c["kind"].upper().replace("_", " "), c["clean"][:140], c["why"]))
    return "\n".join(L).strip() + "\n"


# ---- the step -------------------------------------------------------------------------------------

def run(body, idx, say=lambda *a: None):
    """Filter, check, hunt, fix, report. Returns the body with the fixes applied plus the report.

    ONE say() for the whole step. Every other step in the write phase talks as it goes; this one
    used to flood the chat with a line per claim, per search and per page, and the owner asked
    for a single row with the detail a click away.
    """
    body = C.deep(body)
    claims = classify(body, idx)
    pages = _Pages()
    check_all(claims, idx, pages)
    hunt_log = hunt(claims, idx, pages)
    changes = []
    for si, sec in enumerate(body["sections"]):
        failing = [c for c in claims if c["section"] == si and c["kind"] == "check" and c["verdict"] == "not_supported"]
        if failing:
            changes += fix_section(sec, failing)
    # THE CONFLICTING-PERCENTAGES PASS runs after the per-claim fix, on the body as it now stands, so
    # it reads a corrected or removed sentence as it now is, never as it was (Aparna's review,
    # 2026-09-17). See "f. the conflicting-percentages pass" above for what it does and why.
    pct = pct_pass(body, idx)
    for sec in body["sections"]:
        sec["provenance"] = provenance(sec.get("prose") or "", idx)
    n = _counts(claims, hunt_log, changes)
    report = {"counts": n, "summary": summary_line(n, pct),
              "claims": [{k: v for k, v in c.items() if k not in ("priority",)} for c in claims],
              "hunt": hunt_log, "changes": changes, "pct_conflicts": pct,
              "corrections": [{"claim_id": x["claim_id"], "after": strip_markers(x["after"]),
                               "evidence": next((c.get("evidence", "") for c in claims if c["id"] == x["claim_id"]), "")}
                              for x in changes if x["action"] == "corrected"]}
    note = "the verdicts and every before and after are in source-check.md"
    try:
        # `artifact` rides on the event so the chat row can open the report (see 17-agents.js).
        say(report["summary"], note, artifact="source-check.md", view="article")
    except TypeError:       # a plain two-argument say, as the step tests hand in
        say(report["summary"], note)
    return {"body": body, "report": report, "markdown": render_md(n, claims, hunt_log, changes, pct)}
