"""allocate_words.py — Architect step 4: give every section a word target, judged by importance.

  base   = the MIDPOINT of the word band, cut by ARCH_BAND_SHRINK (every section of a real run overshot).
           The band itself is never rewritten; only the number divided up moves.
  share  = the model decides each section's PERCENTAGE in two passes. Pass 1: IMPORTANCE to the argument
           sets the number. Pass 2: the section's actual FACTS are a ceiling, so evidence can only ever
           take words away, never earn them. Code does the arithmetic so shares total 100.
  target = base * share, then +OVER_PCT (0: measured, blending trims nothing).
A failed or malformed call falls back to an even split; the pipeline never stalls on this step.
Thin sections (fewer than MIN_WORDS_PER_SUBHEAD words per stretch) are REPORTED, not deleted.
"""
from .. import llm
from . import _common as C
from . import shape


def run(st, plan, idx, ctx, say=lambda *a: None):
    brand = C.company()
    wb = plan.get("word_band") or {}
    lo, hi = int(wb.get("min") or 0), int(wb.get("max") or 0)
    true_base = (lo + hi) // 2 if lo and hi else (hi or lo or 2500)
    base = max(1, round(true_base * (1 - C.ARCH_BAND_SHRINK)))
    secs = st["sections"]

    block = []
    for i, s in enumerate(secs):
        facts = []
        for h in shape.groups(s):
            for cid in h.get("card_ids", []):
                c = idx.get(C.nid(cid)) or {}
                g = (c.get("gloss") or c.get("verbatim") or "").strip().replace("\n", " ")
                if g:
                    facts.append(g[:C.ALLOC_GLOSS_CHARS])
        shown, more = facts[:C.ALLOC_CARDS_PER_SECTION], max(0, len(facts) - C.ALLOC_CARDS_PER_SECTION)
        ev = "\n".join("       - %s" % g for g in shown) or "       (this section holds no research facts)"
        if more:
            ev += "\n       ... and %d more fact(s) not shown" % more
        n_h3 = len(s.get("h3s") or [])
        tag = "  [LIST ITEM]" if s.get("is_item") else ""
        block.append("[%d] %s%s\n     JOB: %s\n     COVERS: %s\n     SUB-HEADINGS: %d"
                     % (i, s["headline"], tag, s.get("job") or "(none given)", shape.covers(s), n_h3)
                     + ("  (so %d stretches, needing at least %d words in total)"
                        % (n_h3 + 1, (n_h3 + 1) * C.MIN_WORDS_PER_SUBHEAD) if n_h3 else "")
                     + "\n     THE FACTS IT HOLDS (%d):\n%s" % (len(facts), ev))
    got = {}
    try:
        got = llm.json_call(C.prompt("allocate-words", brand=brand["brand"], about=brand["about"],
                                     title=ctx["title"] or "(none)", angle=ctx["angle"] or "(none)",
                                     spine=st.get("spine") or "(none given)", persona=ctx["persona"],
                                     min_words_per_subhead=C.MIN_WORDS_PER_SUBHEAD, target=base,
                                     card_cap=C.ALLOC_CARDS_PER_SECTION, sections="\n".join(block))) or {}
    except Exception as e:      # noqa: BLE001
        say("Could not get a word split from the model", "falling back to an even split: %s" % str(e)[:80])

    shares = {}
    for a in got.get("allocation") or []:
        if not isinstance(a, dict):
            continue
        try:
            i, sh_ = int(a.get("section")), float(a.get("share"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(secs) and sh_ > 0:
            shares[i] = sh_
    even = not shares
    if even:                                          # crash net: even split
        shares = {i: 100.0 / len(secs) for i in range(len(secs))}
    total = sum(shares.values())
    for i, s in enumerate(secs):                      # normalise, apply, add the overwrite buffer
        sh_ = shares.get(i, 0.0) / total
        s["word_target"] = int(round(base * sh_ * (1 + C.OVER_PCT / 100.0)))

    thin, n_h3_total = [], 0
    for s in secs:
        n = len(s.get("h3s") or [])
        n_h3_total += n
        if s["word_target"] // (n + 1) < C.MIN_WORDS_PER_SUBHEAD:
            thin.append({"section": s["headline"], "words": s["word_target"], "sub_headings": n,
                         "words_per_stretch": s["word_target"] // (n + 1)})
    heads = len(secs) + n_h3_total
    st["word_budget"] = {"band": {"min": lo, "max": hi}, "band_middle": true_base,
                         "aim_low_pct": round(C.ARCH_BAND_SHRINK * 100), "base": base, "overwrite_pct": C.OVER_PCT,
                         "sum_of_targets": sum(s["word_target"] for s in secs), "even_split": even,
                         "headings": {"sections": len(secs), "sub_headings": n_h3_total, "total": heads,
                                      "words_per_heading": base // max(1, heads), "under_floor": thin}}
    say("Set a length for every section", "about %d words across %d sections" % (st["word_budget"]["sum_of_targets"], len(secs))
        + (" (even split: the model gave no usable shares)" if even else ""))
    if thin:
        say("%d section(s) have more sub-headings than their words support" % len(thin),
            "floor %d words per stretch" % C.MIN_WORDS_PER_SUBHEAD)
    return {"structure": st, "allocation": {"base": base, "raw": got,
                                             "applied": {s["headline"][:60]: s["word_target"] for s in secs}}}
