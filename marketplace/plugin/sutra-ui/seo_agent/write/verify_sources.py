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
  4. THE HUNT IS SKIPPED. The original went out and bought replacement pages through DataForSEO's search
     queue. That is a paid web search this agent does not run, and the report says so. So a card whose
     source is proven wrong loses that url and is marked needs_source; it is CUT only when it is numeric
     and has no other source left, because a number with no page behind it cannot be published.
  5. Every url proven wrong is remembered; every other used card citing it loses that url too (a bad
     page is bad for every card that cites it). A prose card keeps its claim and loses the source.
  6. An H3 that loses all its cards dies with them; a section that loses all its H3s dies too.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import llm
from . import _common as C

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
    are treated as NOT worthy (kept unverified, never deleted unjudged)."""
    worthy, failed_batches = set(), 0
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

    # --- phase 2: the hunt is not run here -----------------------------------
    bad_urls = {u for _c, _v, wrong, _u in bad for u in wrong}
    cut, needs_source, fixes = [], [], {}

    def _record(c, note):
        fixes[c["card_id"]] = {"source_urls": list(c.get("source_urls") or []),
                               "needs_source": bool(c.get("needs_source")), "note": note}

    for c, verdict, wrong, unloadable in bad:
        keep = [u for u in (c.get("source_urls") or []) if u not in bad_urls]
        c["source_urls"] = keep
        if keep:                                     # an unloadable url remains: unproven, not wrong
            c["needs_source"] = True
            needs_source.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                                 "why": "its loaded source(s) did not support it; the remaining url could not be read"})
            _record(c, "source proven wrong, one unreadable url kept, no replacement hunted")
        else:
            cut.append({"card_id": c["card_id"], "claim": (c.get("gloss") or "")[:140],
                        "old": (wrong or [None])[0],
                        "why": ("no source url" if verdict == "no-url" else "source did not support the claim")
                               + "; a numeric fact with no page behind it is not published (replacement hunt not run)"})
            _record(c, "cut")

    # --- phase 2b: PROPAGATE. A url proven wrong is wrong for EVERY card citing it. --------------
    judged = {c["card_id"] for c, *_ in bad}
    unsourced, propagated = [], []
    for cid in used_ids:
        c = idx.get(cid)
        if c is None or cid in judged or not any(u in bad_urls for u in (c.get("source_urls") or [])):
            continue
        keep = [u for u in (c.get("source_urls") or []) if u not in bad_urls]
        c["source_urls"] = keep
        if keep:
            propagated.append({"card_id": cid, "replaced": False, "kept_other_url": True})
            _record(c, "lost a url proven wrong elsewhere; another source remains")
        elif C.has_number(c.get("verbatim", "")):
            cut.append({"card_id": cid, "claim": (c.get("gloss") or "")[:140], "old": None,
                        "why": "cites a url proven wrong; numeric, and no other source"})
            propagated.append({"card_id": cid, "replaced": False, "cut": True})
            _record(c, "cut (propagated)")
        else:
            c["needs_source"] = True
            unsourced.append({"card_id": cid, "claim": (c.get("gloss") or "")[:140],
                              "why": "cited a url proven wrong elsewhere; no number to verify by, so the claim is "
                                     "KEPT and the source stripped rather than deleted unjudged"})
            _record(c, "source stripped, claim kept")

    # --- phase 3: apply the cuts to the plan (H3s/sections die with their last card) ---
    cut_ids = {C.nid(x["card_id"]) for x in cut}
    dropped_h3s, dropped_secs = [], []
    for sec in plan["sections"]:
        for h in sec["h3s"]:
            h["card_ids"] = [cid for cid in h["card_ids"] if C.nid(cid) not in cut_ids]
        for h in [h for h in sec["h3s"] if not h["card_ids"]]:
            dropped_h3s.append({"h3": h["h3"], "from_h2": sec["h2"], "why": "all cards cut by source verification"})
        sec["h3s"] = [h for h in sec["h3s"] if h["card_ids"]]
    for sec in [s for s in plan["sections"] if not s["h3s"]]:
        dropped_secs.append(sec["h2"])
    plan["sections"] = [sec for sec in plan["sections"] if sec["h3s"]]

    police = {
        "kept_ok": [c["card_id"] for c in kept_ok],
        "unverifiable_kept": [c["card_id"] for c in unverifiable],
        "needs_source": needs_source, "cut": cut, "kept_unsourced": unsourced,
        "bad_urls": sorted(bad_urls), "propagated": propagated,
        "dropped_h3s": dropped_h3s, "dropped_sections": dropped_secs,
        "hunt": "skipped: replacing a bad source needs a DataForSEO web search, which this agent does not run. "
                "A fact whose source failed keeps its claim and loses the url; a number with no source left is cut.",
        "failed_worthy_batches": failed_batches,
        "coverage": {"claims_to_check": len(todo),
                     "actually_judged": len(kept_ok) + len(bad),
                     "unloadable": len(unverifiable)},
    }
    say("Source check done", "%d confirmed, %d could not be read (kept), %d need a new source, %d cut"
        % (len(kept_ok), len(unverifiable), len(needs_source) + len(unsourced), len(cut)))
    return {"plan": plan, "card_fixes": fixes, "police": police}
