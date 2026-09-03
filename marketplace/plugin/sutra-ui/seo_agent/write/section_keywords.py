"""section_keywords.py — Architect step 5: which sections deserve a search keyword, and which one.

  5a GATE   one AI call over the whole article: would a person type this section's subject into Google
            as its own search? Most sections should be NO. Free. Nothing is bought for a section the
            gate rejects. A section the gate never mentioned is NOT hunted: silence never means spend.
  5b HUNT   for each gated-YES section, in parallel: seeds (from that section's CARDS; the heading can
            lie, the evidence cannot) -> DataForSEO keyword_suggestions, SUGGEST_LIMIT per seed ->
            filter vol >= VOL_FLOOR, KD < KD_CEIL -> pick ONE, or none. Code refuses a phrase that was
            never among the candidates.

THE HUNT IS PAID, so it runs only when DataForSEO is connected and the balance is at least
MIN_DFS_BALANCE. Otherwise every hunt is skipped and the report says so; the headings step then writes
headings without a researched section keyword, which is a valid outcome.
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from ..tools import dfs
from . import _common as C
from . import shape


def render_cards(sec, idx, limit=None):
    """One line per card under this section. limit=None means ALL of them."""
    lines = []
    for h in shape.groups(sec):
        for cid in h.get("card_ids", []):
            c = idx.get(C.nid(cid)) or {}
            text = (c.get("verbatim") or c.get("gloss") or "").strip().replace("\n", " ")[:C.BODY_CARD_CHARS]
            if text:
                lines.append("- %s" % text)
            if limit and len(lines) >= limit:
                return "\n".join(lines)
    return "\n".join(lines) or "(this section holds no research facts)"


def _gate(secs, ctx, primary):
    block = "\n".join("  %d. %s\n     job: %s" % (i + 1, s.get("headline"), s.get("job") or "(none)")
                      for i, s in enumerate(secs))
    out = llm.json_call(C.prompt("keyword-gate", title=ctx["title"] or "(untitled)",
                                 angle=ctx["angle"] or "(none recorded)", spine=ctx["spine"] or "(not available)",
                                 about=ctx["about"] or "(not available)", not_about=ctx["not_about"] or "(not available)",
                                 primary=primary or "(none)", persona=ctx["persona"], sections=block)) or {}
    verdicts = {}
    for r in out.get("sections") or []:
        if not isinstance(r, dict):
            continue
        try:
            verdicts[int(r["n"])] = {"hunt": bool(r.get("hunt")), "why": str(r.get("why") or "").strip()}
        except (KeyError, TypeError, ValueError):
            continue
    return [verdicts.get(i + 1, {"hunt": False, "why": "gate returned no verdict for this section"})
            for i in range(len(secs))]


def dfs_route():
    """(usable, note). Paid lookups run only when connected and the balance clears MIN_DFS_BALANCE.
    An UNKNOWN balance (the check itself failed) fails open: the paid call errors loudly on its own."""
    if not dfs.available():
        return False, "DataForSEO is not connected, so no section keywords were looked up"
    bal = dfs.balance()
    if bal is None:
        return True, "DataForSEO balance unknown; going ahead"
    if bal < C.MIN_DFS_BALANCE:
        return False, "DataForSEO balance $%.2f is under $%.2f, so no section keywords were looked up" % (bal, C.MIN_DFS_BALANCE)
    return True, "DataForSEO balance $%.2f" % bal


def _hunt_one(n, sec, ctx, primary, idx, company):
    """seeds -> DataForSEO -> pick. Returns the record for this section (pick may be None)."""
    head, job = sec.get("headline") or "", sec.get("job") or "(none)"
    rec = {"n": n, "heading": head, "seeds": [], "why_seeds": "", "candidates": 0, "pick": None}
    try:
        s = llm.json_call(C.prompt("section-seeds", title=ctx["title"] or "(untitled)",
                                   spine=ctx["spine"] or "(not available)", about=ctx["about"] or "(not available)",
                                   not_about=ctx["not_about"] or "(not available)", primary=primary or "(none)",
                                   persona=ctx["persona"], heading=head, job=job, cards=render_cards(sec, idx))) or {}
    except Exception as e:      # noqa: BLE001
        rec["error"] = "seeds failed: %s" % str(e)[:90]
        return rec
    rec["seeds"] = [str(x).strip() for x in (s.get("seeds") or []) if str(x).strip()][:3]
    rec["why_seeds"] = str(s.get("why") or "").strip()
    if not rec["seeds"]:
        rec["error"] = "no seeds returned"
        return rec

    cands = []
    for seed in rec["seeds"]:
        try:
            cands += dfs.keyword_suggestions(seed, limit=C.SUGGEST_LIMIT,
                                             location_name=company.get("location_name"),
                                             language_code=company.get("language_code"))
        except Exception as e:      # noqa: BLE001 — one failed seed never sinks the section
            rec.setdefault("suggest_errors", []).append("%s: %s" % (seed[:34], str(e)[:70]))
    best = {}
    for c in cands:
        if (c["vol"] or 0) >= C.VOL_FLOOR and c["kd"] is not None and c["kd"] < C.KD_CEIL:
            if c["kw"] not in best or (c["vol"] or 0) > (best[c["kw"]]["vol"] or 0):
                best[c["kw"]] = c
    survivors = sorted(best.values(), key=lambda x: -(x["vol"] or 0))[:C.CAND_SHOWN]
    rec["candidates"] = len(survivors)
    if not survivors:
        rec["why_none"] = "no candidate cleared vol>=%d / KD<%d" % (C.VOL_FLOOR, C.KD_CEIL)
        return rec
    try:
        r = llm.json_call(C.prompt("pick-section-keyword", heading=head, job=job,
                                   why=rec["why_seeds"] or "(not stated)", spine=ctx["spine"] or "(not available)",
                                   not_about=ctx["not_about"] or "(not available)", primary=primary or "(none)",
                                   persona=ctx["persona"],
                                   candidates="\n".join("%s | %s | %s" % (c["kw"], c["vol"], c["kd"]) for c in survivors))) or {}
    except Exception as e:      # noqa: BLE001
        rec["error"] = "pick failed: %s" % str(e)[:90]
        return rec
    kw = str(r.get("keyword") or "").strip()
    if not kw or kw.lower() == "null":
        rec["why_none"] = str(r.get("why") or "picker chose none").strip()
        return rec
    if kw not in best:                       # never accept a phrase we did not show it
        rec["why_none"] = "picker returned %r, which was not among the candidates; rejected" % kw
        return rec
    rec["pick"] = {"keyword": kw, "volume": best[kw]["vol"], "kd": best[kw]["kd"],
                   "why": str(r.get("why") or "").strip()}
    return rec


def run(st, inputs, ctx, idx, say=lambda *a: None):
    secs = st.get("sections") or []
    ks = inputs["group_a"].get("keyword_set") or {}
    primary = ks.get("primary") or ""
    say("Deciding which sections deserve their own search keyword", "%d sections" % len(secs))
    gate = _gate(secs, ctx, primary)
    hunt_ns = [i + 1 for i, g in enumerate(gate) if g["hunt"]]
    say("Gate decided", "%d of %d sections deserve a keyword" % (len(hunt_ns), len(secs)))

    usable, note = dfs_route()
    records = []
    if hunt_ns and usable:
        say("Looking up real search phrases", "%d sections, %s" % (len(hunt_ns), note))
        company = C.sh.company()
        with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
            records = list(ex.map(lambda n: _hunt_one(n, secs[n - 1], ctx, primary, idx, company), hunt_ns))
    elif hunt_ns:
        say("Keyword lookups skipped", note)
    by_n = {r["n"]: r for r in records}
    found = sum(1 for r in records if r.get("pick"))
    empty = [{"n": r["n"], "heading": r["heading"], "why": r.get("why_none") or r.get("error") or "no pick",
              "seeds": r.get("seeds") or [], "candidates": r.get("candidates", 0)}
             for r in records if not r.get("pick")]
    result = {"primary": primary, "hunted": len(hunt_ns) if usable else 0, "found": found, "empty_hunts": empty,
              "hunts_skipped": (None if usable else note) if hunt_ns else None,
              "sections": [{"n": i + 1, "heading": s.get("headline") or "", "gate": gate[i],
                            **{k: v for k, v in (by_n.get(i + 1) or {}).items() if k != "n"}}
                           for i, s in enumerate(secs)]}
    if usable and hunt_ns:
        say("Section keywords found", "%d across %d lookups" % (found, len(hunt_ns)))
    return result
