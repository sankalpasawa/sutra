"""verify_sources.py — Planner step 3: every citable number in the plan gets a checked source.

Reads:  the tagged plan + the card index.
Writes: the SAME plan shape, sources verified; the card fixes (corrected source_urls, needs_source);
        the police log: kept-ok / unloadable-kept / needs-source / cut.

  1. CODE finds every used card whose text carries a real number (2+ digit pattern).
  2. ONE AI pass (batched) picks which of those genuinely NEED verification (verify-worthy.md). A failed
     batch = those cards kept unverified, never deleted unjudged.
  3. Per worthy card: fetch its claimed page(s), an AI judge (source-judge.md) reads the page OPENING plus
     the passages around the claim's numbers and answers whether it supports the claim ABOUT THE SAME
     SUBJECT. A page that will not load is NOT a wrong page: the card is kept unverified.
  4. THE HUNT (2026-09-09). A card whose source is proven wrong now goes and looks for a replacement,
     the way the original did: source-queries.md plans the queries from the gloss AND the verbatim, so
     the subject is in the query; the search and the page reads are the same ones enrich uses; and the
     same source-judge decides. The FIRST page that supports the claim wins and becomes the card's
     source.
  5. A FAILED HUNT NEVER DESTROYS EVIDENCE (2026-09-10). When the hunt comes back empty the card
     loses the url that was proven wrong, is stamped `needs_source`, and STAYS IN THE PLAN. It used
     to be deleted outright whenever it was numeric and had nothing left, which meant a fact the
     research paid for disappeared with no trace in the article and nothing on screen to say a fact
     had gone. Losing a card silently is worse than shipping a flagged one: a flagged card is a
     question a person can answer, a deleted one is a hole nobody knows about. Every kept-and-flagged
     card is listed in the police log, counted in freeze's soft notes, and re-checked by the draft's
     digit guard before the article is called finished.
  6. Every url proven wrong is remembered; every other used card citing it loses that url too (a bad
     page is bad for every card that cites it). A prose card keeps its claim and loses the source; a
     numeric one is re-hunted, because for a number the hunt actually works.
  7. Nothing here removes an H3 or a section any more, because nothing here removes a card.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import llm
from . import _common as C
from . import enrich

# ---- the replacement hunt's knobs ------------------------------------------------------------------
HUNT_QUERIES_PER_CLAIM = 3    # queries planned per claim (the original's QUERIES_PER_CLAIM)
HUNT_PAGES_PER_CLAIM = 4      # pages actually opened and judged before a claim is given up on
HUNT_MAX = 250                # claims hunted per article, an unattended-run safety cap
HUNT_WORKERS = 4              # claims hunted at once

_NUM = C._NUM


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"(\d),(\d)", r"\1\2", s)          # 4,683 -> 4683
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def _number_present(verbatim, text):
    """Cheap pre-filter: is the card's distinctive number anywhere in the page at all?"""
    vn, tn = _norm(verbatim), _norm(text)
    nums = [n for n in re.findall(r"\d[\d]*%?", vn) if len(re.sub(r"[^\d]", "", n)) >= 2]
    return bool(nums) and any(n in tn for n in nums)


def _page_window(verbatim, page):
    """What the judge reads: the page's opening (title + abstract, which carry the SUBJECT) plus the
    neighbourhood of each number the claim depends on. Taking the first N raw characters showed the
    site's nav menu and nothing else, so every claim on a heavy site was judged unsupported."""
    text = " ".join(page.split())
    if len(text) <= C.PAGE_CHARS:
        return text
    head = text[:C.PAGE_CHARS // 4]
    budget, low = C.PAGE_CHARS - len(head), text.lower()
    nums = [n for n in re.findall(r"\d[\d,.]*%?", _norm(verbatim)) if len(re.sub(r"[^\d]", "", n)) >= 2]
    words = {w for w in re.findall(r"[a-z]{5,}", (verbatim or "").lower())}
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


def _judge(card, url, page):
    """AI verdict: does THIS page support THIS claim, about the same subject? (gloss carries the subject)"""
    if not _number_present(card.get("verbatim", ""), page):
        return False, ""
    try:
        r = llm.json_call(C.prompt("source-judge", gloss=card.get("gloss", ""), verbatim=card.get("verbatim", ""),
                                   url=url, page=_page_window(card.get("verbatim", ""), page))) or {}
        return bool(r.get("supports")), str(r.get("quote") or "")
    except Exception:       # noqa: BLE001
        return False, ""


def _worthy_ids(cards):
    """The AI pass: which numeric cards genuinely need a verified source. Batched; a failed batch's cards
    are treated as NOT worthy (kept unverified, never deleted unjudged).

    A card the research already stamped `needs_source` skips the judgment entirely and is worthy by
    construction. The stamp means the research could not find the page that carried the figure, so
    there is nothing for the AI to weigh: it is the one kind of card that is KNOWN to be unsourced,
    and asking whether it is worth checking would sometimes answer no and let it through unexamined.
    """
    worthy = {C.nid(c.get("card_id")) for c in cards if c.get("needs_source")}
    failed_batches = 0
    batches = [cards[i:i + C.VERIFY_BATCH] for i in range(0, len(cards), C.VERIFY_BATCH)]

    def _one(batch):
        block = "\n".join("- id%s: %s" % (c["card_id"], (c.get("verbatim") or c.get("gloss") or "")[:400])
                          for c in batch)
        r = llm.json_call(C.prompt("verify-worthy", cards=block)) or {}
        return {C.nid(x) for x in (r.get("verify") or [])}

    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        futs = {ex.submit(_one, b): b for b in batches}
        for f in as_completed(futs):
            try:
                worthy |= f.result()
            except Exception:       # noqa: BLE001
                failed_batches += 1
    return worthy, failed_batches


def _hunt_one(card, route_name):
    """Find a page that really supports ONE claim. (url, quote, queries, searched).

    Same machinery as enrich: plan the queries, search, read the pages, judge. The judge is the one
    already used above, so a hunted source has to clear exactly the bar the original source failed.
    """
    try:
        q = llm.json_call(C.prompt("source-queries", gloss=card.get("gloss", ""),
                                   verbatim=card.get("verbatim", ""), n=HUNT_QUERIES_PER_CLAIM)) or {}
    except Exception:  # noqa: BLE001 — a failed plan is a claim left unverified, never a crash
        return None, "", [], False
    queries = [str(x).strip() for x in (q.get("queries") or []) if str(x).strip()][:HUNT_QUERIES_PER_CLAIM]
    if not queries:
        return None, "", [], False
    urls, _cost = enrich.search(queries, route_name, exclude=card.get("source_urls") or ())
    if not urls:
        return None, "", queries, False
    checked = 0
    for u in urls:
        if checked >= HUNT_PAGES_PER_CLAIM:
            break
        page = C.fetch(u)
        if page.startswith("__ERR__"):
            continue
        checked += 1
        ok, quote = _judge(card, u, page)
        if ok:
            return u, quote, queries, True
    return None, "", queries, True


def _hunt_many(cards, route_name, say, what):
    """Hunt a batch of claims in parallel. {card_id: (url, quote, queries, searched)}."""
    cards = list(cards)[:HUNT_MAX]
    if not cards:
        return {}
    say("Hunting a replacement source for %s" % C.sh.plural(len(cards), what),
        "planning the search from the claim itself, then reading the pages that come back")
    out = {}
    with ThreadPoolExecutor(max_workers=HUNT_WORKERS) as ex:
        futs = {ex.submit(_hunt_one, c, route_name): c for c in cards}
        for f in as_completed(futs):
            c = futs[f]
            try:
                res = f.result()
            except Exception:  # noqa: BLE001
                res = (None, "", [], False)
            out[C.nid(c["card_id"])] = res
            if res[0]:
                say("New source found for a claim", "%s -> %s" % ((c.get("gloss") or "")[:70], res[0]))
            else:
                say("No replacement source for a claim", (c.get("gloss") or "")[:90])
    return out


def run(plan, idx, say=lambda *a: None):
    used_ids = []
    for sec in plan["sections"]:
        for h in sec["h3s"]:
            for cid in h["card_ids"]:
                cid = C.nid(cid)
                if cid not in used_ids:
                    used_ids.append(cid)
    numeric = [idx[c] for c in used_ids if c in idx and C.has_number(idx[c].get("verbatim", ""))]
    say("Finding the facts that carry a number", "%d facts used, %d with a number" % (len(used_ids), len(numeric)))

    worthy, failed_batches = _worthy_ids(numeric)
    todo = [c for c in numeric if C.nid(c.get("card_id")) in worthy]
    say("Decided which numbers need a checked source", "%d of %d" % (len(todo), len(numeric))
        + (" (%d batch(es) failed; those stay unverified)" % failed_batches if failed_batches else ""))

    # --- phase 1: fetch-verify the claimed sources, in parallel -------------
    kept_ok, unverifiable, bad = [], [], []

    def _check(c):
        """Try EVERY url the card carries (a good backup should not die with a bad primary)."""
        urls = [u for u in (c.get("source_urls") or []) if u]
        if not urls:
            return c, "no-url", [], []
        unloadable, wrong = [], []
        for u in urls:
            page = C.fetch(u)
            if page.startswith("__ERR__"):
                unloadable.append(u)
                continue
            ok, _q = _judge(c, u, page)
            if ok:
                if u != urls[0]:
                    c["source_urls"] = [u] + [x for x in urls if x != u]   # promote the one that worked
                return c, "ok", [], []
            wrong.append(u)
        return c, ("unloadable" if len(unloadable) == len(urls) else "wrong"), wrong, unloadable

    if todo:
        say("Reading each claimed source page", "%d pages" % len(todo))
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(_check, c) for c in todo]):
            c, verdict, wrong, unloadable = f.result()
            if verdict == "ok":
                kept_ok.append(c)
            elif verdict == "unloadable":
                unverifiable.append(c)               # paywalled etc.: kept as-is, not punished
            else:
                bad.append((c, verdict, wrong, unloadable))

    # --- phase 2: HUNT a replacement for every claim whose source failed -------
    bad_urls = {u for _c, _v, wrong, _u in bad for u in wrong}
    cut, needs_source, fixes, replaced = [], [], {}, []
    route_name, route_note = enrich.route()

    def _record(c, note):
        fixes[c["card_id"]] = {"source_urls": list(c.get("source_urls") or []),
                               "needs_source": bool(c.get("needs_source")), "note": note}

    hunted = _hunt_many([c for c, *_ in bad], route_name, say, "claim") if bad else {}
    searched = sum(1 for _cid, (_u, _q, _qs, ok) in hunted.items() if ok)

    for c, verdict, wrong, unloadable in bad:
        hit, quote, queries, ok_search = hunted.get(C.nid(c["card_id"]), (None, "", [], False))
        keep = [u for u in (c.get("source_urls") or []) if u not in bad_urls]
        if hit:
            # THE NEW PAGE IS THE SOURCE, and the proven-wrong ones do not ride along behind it.
            c["source_urls"] = [hit] + [u for u in keep if u != hit]
            c.pop("needs_source", None)
            replaced.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                             "old": (wrong or [None])[0], "new": hit, "quote": quote[:200],
                             "queries": queries})
            _record(c, "source replaced by the hunt")
            continue
        c["source_urls"] = keep
        c["needs_source"] = True
        why_hunt = ("the replacement hunt found no page that supports it" if ok_search
                    else "the replacement hunt could not search (" + route_note + ")")
        if keep:                                     # an unloadable url remains: unproven, not wrong
            needs_source.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                                 "why": "its loaded source(s) did not support it, the remaining url could not "
                                        "be read, and " + why_hunt})
            _record(c, "source proven wrong, one unreadable url kept, no replacement found")
        else:
            # KEPT AND FLAGGED, never deleted. The claim itself was never disproved — only the page
            # behind it was — so the evidence stays and the missing source becomes a visible question.
            needs_source.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                                 "why": ("no source url" if verdict == "no-url" else "source did not support the claim")
                                        + ", " + why_hunt
                                        + "; the fact is KEPT with no source attached and flagged, "
                                          "because deleting it would lose it with nothing on screen to say so"})
            _record(c, "source proven wrong, no replacement found, kept and flagged")

    # --- phase 2b: PROPAGATE. A url proven wrong is wrong for EVERY card citing it. --------------
    judged = {c["card_id"] for c, *_ in bad}
    unsourced, propagated = [], []
    contaminated = []
    for cid in used_ids:
        c = idx.get(cid)
        if c is None or cid in judged or not any(u in bad_urls for u in (c.get("source_urls") or [])):
            continue
        contaminated.append(c)
    # A CONTAMINATED NUMERIC CARD WITH NOTHING LEFT IS HUNTED TOO, and for the same reason as above:
    # the claim may well be true and published somewhere else, and cutting it unhunted throws away a
    # fact over one bad page. A card with NO number is not hunted: there is no distinctive figure to
    # search for, so the hunt cannot work; its claim is kept and its source stripped.
    rehunt = [c for c in contaminated
              if not [u for u in (c.get("source_urls") or []) if u not in bad_urls]
              and C.has_number(c.get("verbatim", ""))]
    hunted2 = _hunt_many(rehunt, route_name, say, "claim left without a source") if rehunt else {}
    searched += sum(1 for _cid, (_u, _q, _qs, ok) in hunted2.items() if ok)
    for c in contaminated:
        cid = C.nid(c["card_id"])
        keep = [u for u in (c.get("source_urls") or []) if u not in bad_urls]
        hit, quote, queries, _ok = hunted2.get(cid, (None, "", [], False))
        if hit:
            c["source_urls"] = [hit]
            c.pop("needs_source", None)
            replaced.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                             "old": None, "new": hit, "quote": quote[:200], "queries": queries})
            propagated.append({"card_id": cid, "replaced": True})
            _record(c, "cited a url proven wrong elsewhere; the hunt found a page that does support it")
            continue
        c["source_urls"] = keep
        if keep:
            propagated.append({"card_id": cid, "replaced": False, "kept_other_url": True})
            _record(c, "lost a url proven wrong elsewhere; another source remains")
        elif C.has_number(c.get("verbatim", "")):
            # Same rule as above: a bad page is a reason to strip the source, never to delete the fact.
            c["needs_source"] = True
            needs_source.append({"card_id": cid, "claim": (c.get("gloss") or "")[:140],
                                 "why": "cites a url proven wrong; numeric, no other source, and the hunt "
                                        "found no replacement — KEPT with no source attached and flagged"})
            propagated.append({"card_id": cid, "replaced": False, "kept_unsourced": True})
            _record(c, "source stripped, claim kept and flagged")
        else:
            c["needs_source"] = True
            unsourced.append({"card_id": cid, "claim": (c.get("gloss") or "")[:140],
                              "why": "cited a url proven wrong elsewhere; no number to verify by, so the claim is "
                                     "KEPT and the source stripped rather than deleted unjudged"})
            _record(c, "source stripped, claim kept")

    # --- phase 3: nothing to apply. Source verification no longer removes a card, so it cannot take
    # an H3 or a section down with it. The keys stay so the run report and freeze keep their shape,
    # and `cut` stays as the empty list it now always is: a reader of a run from before 2026-09-10
    # will find entries there, and a reader of one after will find the same facts under needs_source.
    dropped_h3s, dropped_secs = [], []
    assert not cut, "source verification must never delete a card; see the module docstring, rule 5"

    police = {
        "kept_ok": [c["card_id"] for c in kept_ok],
        "unverifiable_kept": [c["card_id"] for c in unverifiable],
        "needs_source": needs_source, "cut": cut, "kept_unsourced": unsourced,
        "bad_urls": sorted(bad_urls), "propagated": propagated,
        "dropped_h3s": dropped_h3s, "dropped_sections": dropped_secs,
        "replaced": replaced,
        # ONE SENTENCE THAT SAYS WHAT REALLY HAPPENED. A run that could not search at all must not
        # read like a run that searched and found nothing, so the route is named either way.
        "hunt": (("no source failed, so no replacement was needed. Route available: " + route_note + ".")
                 if not (bad or rehunt) else
                 ("%d of %d claim(s) whose source failed found a replacement page. Route: %s."
                  % (len(replaced), len(bad) + len(rehunt), route_note))),
        "hunt_route": route_name, "hunt_searched": searched,
        "failed_worthy_batches": failed_batches,
        "coverage": {"claims_to_check": len(todo),
                     "actually_judged": len(kept_ok) + len(bad),
                     "unloadable": len(unverifiable)},
    }
    say("Source check done", "%d confirmed, %d could not be read (kept), %d given a new source, "
                             "%d kept and flagged as still needing one. Nothing was deleted."
        % (len(kept_ok), len(unverifiable), len(replaced), len(needs_source) + len(unsourced)))
    return {"plan": plan, "card_fixes": fixes, "police": police}
