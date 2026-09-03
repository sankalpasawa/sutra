"""blend.py — Writer step 2: BLEND. The editor that reads the whole article and cuts what did not earn
its place.

  Step 1  COUNT in code: every sentence over BLEND_SENTENCE_WORDS, every paragraph over
          BLEND_PARA_SENTENCES, the body total against the article's word band. Exact, free, no AI.
  Step 2  EDIT (blend.md): the article, each section's JOB, and that list. Returns the whole article.
  Step 3  MEASURE in code: diff every block, and count the keywords in the finished text. We do not
          trust what it says it did; there is a diff.
  Step 4  GUARDS in code, ALL-OR-NOTHING: section count, headings, an emptied section, catastrophic tag
          loss. Any failure and the ORIGINAL body publishes unchanged, loudly logged.
The editor sees ONLY the prose, never the cards, so it cannot invent a fact. Code then audits the [c]
tags: a tag present after blending that never existed in the body is stripped and logged.
"""
import difflib
import re

from .. import llm
from . import _common as C
from . import tags

_SENT = re.compile(r"(?<=[.!?])\s+")
_LIST_ITEM = re.compile(r"^(?:[-*+]\s|\d+[.)]\s)")


def _prose_lines(text):
    """The lines a reader reads. Headings and table rows are not editable prose, so they never count."""
    out = []
    for ln in str(text or "").split("\n"):
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("|") or set(s) <= set("-| :"):
            continue
        out.append(s)
    return out


def _paragraphs(text):
    """Blank-line separated blocks, headings and tables removed. Returns (text, is_list): a list is not a
    paragraph, so its sentence count is never called fat, though its items are still read for length."""
    out = []
    for block in str(text or "").split("\n\n"):
        lines = _prose_lines(block)
        if not lines:
            continue
        listy = sum(1 for ln in lines if _LIST_ITEM.match(ln)) >= max(2, len(lines) // 2)
        out.append((" ".join(lines), listy))
    return out


def _sentences(para):
    return [s for s in _SENT.split(para.strip()) if s.strip()]


def count(secs):
    """Everything the counter finds, per section. Returns (long_sentences, fat_paragraphs, totals)."""
    longs, fats, n_sent = [], [], 0
    for s in secs:
        head = s.get("headline") or s.get("heading") or "?"
        for para, listy in _paragraphs(s.get("prose")):
            sents = _sentences(para)
            n_sent += len(sents)
            if not listy and len(sents) > C.BLEND_PARA_SENTENCES:
                fats.append({"section": head, "sentences": len(sents), "opens": " ".join(sents[0].split()[:12])})
            for sent in sents:
                w = len(sent.split())
                if w > C.BLEND_SENTENCE_WORDS:
                    longs.append({"section": head, "words": w, "text": sent})
    return longs, fats, {"sentences": n_sent}


def _flags_block(longs, fats, totals):
    if not longs and not fats:
        return ("Nothing to report. Every sentence is at or under %d words and every paragraph at or under "
                "%d sentences.\nSpend your effort on faults 1 to 8 and 11 instead."
                % (C.BLEND_SENTENCE_WORDS, C.BLEND_PARA_SENTENCES))
    L = []
    n = totals.get("sentences") or 0
    pct = " (%d%% of all sentences)" % round(100 * len(longs) / n) if n else ""
    L.append("SENTENCES OVER %d WORDS — %d of %d%s" % (C.BLEND_SENTENCE_WORDS, len(longs), n, pct))
    by_sec = {}
    for x in longs:
        by_sec.setdefault(x["section"], []).append(x)
    for head, items in by_sec.items():
        L.append("  [%s] %d of them" % (head, len(items)))
        for x in sorted(items, key=lambda y: -y["words"])[:C.BLEND_FLAG_SAMPLE]:
            L.append('    %dw  "%s"' % (x["words"], x["text"][:150]))
        if len(items) > C.BLEND_FLAG_SAMPLE:
            L.append("    ... and %d more in this section" % (len(items) - C.BLEND_FLAG_SAMPLE))
    L.append("")
    L.append("PARAGRAPHS OVER %d SENTENCES — %d" % (C.BLEND_PARA_SENTENCES, len(fats)))
    for x in fats:
        L.append('  [%s] %d sentences, opens "%s..."' % (x["section"], x["sentences"], x["opens"]))
    return "\n".join(L)


def _length_facts(secs, band):
    words = sum(len(str(s.get("prose") or "").split()) for s in secs)
    lo, hi = (band or {}).get("min"), (band or {}).get("max")
    if not (lo and hi):
        return {"words": words}
    reserve = C.BLEND_WRAPPER_WORDS
    aim_lo, aim_hi = max(0, lo - reserve), max(0, hi - reserve)
    return {"words": words, "band_min": lo, "band_max": hi, "wrapper_reserve": reserve,
            "aim_min": aim_lo, "aim_max": aim_hi, "over_by": max(0, words - aim_hi), "under_by": max(0, aim_lo - words)}


def _length_line(secs, band):
    words = sum(len(str(s.get("prose") or "").split()) for s in secs)
    lo, hi = (band or {}).get("min"), (band or {}).get("max")
    if not (lo and hi):
        return "the sections below total {:,} words. No band was set for this article.".format(words)
    reserve = C.BLEND_WRAPPER_WORDS
    aim_lo, aim_hi = max(0, lo - reserve), max(0, hi - reserve)
    verdict = ("over that aim by about {:,} words".format(words - aim_hi) if words > aim_hi
               else "under that aim by about {:,} words".format(aim_lo - words) if words < aim_lo
               else "inside that aim")
    return ("the sections below total {:,} words. The finished article should land between {:,} and {:,}. "
            "An intro, five FAQ answers and a close are written AFTER you and add roughly {} words, so the "
            "sections need to come in around {:,} to {:,}. Right now they are {}."
            .format(words, lo, hi, reserve, aim_lo, aim_hi, verdict))


def _jobs_block(st, secs):
    by_head = {str(s.get("headline") or ""): s for s in (st.get("sections") or [])}
    L = []
    for i, s in enumerate(secs, 1):
        head = s.get("headline") or "?"
        plan = by_head.get(head) or {}
        target, wrote = plan.get("word_target"), len(str(s.get("prose") or "").split())
        t = "  [target %sw, written %dw]" % (target, wrote) if target else "  [written %dw]" % wrote
        L.append("%d. %s%s\n   JOB: %s" % (i, head, t, str(plan.get("job") or "(no job on file)").strip()))
    return "\n".join(L)


def kw_counts(secs, phrases):
    """Count each phrase in the finished text ourselves. The editor's own report does not add up."""
    text = " ".join(str(s.get("prose") or "") for s in secs).lower()
    return {p: len(re.findall(r"\b" + re.escape(p.lower()) + r"\b", text)) for p in phrases if p}


def diff(before, after):
    """MEASURE what changed, per section. Not what it claims: what it did."""
    out, bmap = [], {s["headline"]: str(s.get("prose") or "") for s in before}
    for b in after:
        old, new = bmap.get(b["heading"]), str(b.get("prose") or "")
        if old is None or old == new:
            continue
        sm = difflib.SequenceMatcher(None, old.split(), new.split())
        edits = [{"was": " ".join(old.split()[i1:i2]) or "(nothing)", "now": " ".join(new.split()[j1:j2]) or "(cut)"}
                 for tag_, i1, i2, j1, j2 in sm.get_opcodes() if tag_ != "equal"]
        out.append({"section": b["heading"], "similarity": round(sm.ratio(), 3), "edits": edits})
    return out


def guards(secs, result):
    """TIERED. BLOCKING discards the whole edit; WARN is surfaced but the edit still applies."""
    block, warn = [], []
    hb = [s.get("headline") for s in secs]
    ha = [s.get("heading") for s in result]
    if len(hb) != len(ha):
        block.append("section count changed (%d -> %d)" % (len(hb), len(ha)))
    elif hb != ha:
        block.append("headings changed; they belong to the architect")
    empty = [b.get("heading") for b in result if not str(b.get("prose") or "").strip()]
    if empty:
        block.append("%d section(s) left empty: %s" % (len(empty), ", ".join(str(x)[:40] for x in empty[:3])))
    tb = set()
    for s in secs:
        tb |= tags.id_set(s["prose"])
    ta = set()
    for b in result:
        ta |= tags.id_set(str(b.get("prose") or ""))
    lost = tb - ta
    if tb and len(lost) / len(tb) > C.BLEND_TAG_LOSS_BLOCK:
        block.append("stripped %d of %d source tags (%d%%); that is not editing"
                     % (len(lost), len(tb), round(100 * len(lost) / len(tb))))
    elif lost:
        warn.append({"kind": "source tags lost", "detail": sorted(str(x) for x in lost),
                     "note": "correct if those claims were cut; a fault if the claim survived"})
    return block, warn


def run(body, st, inputs, ctx, say=lambda *a: None):
    brand = C.company()
    ga = inputs["group_a"]
    kw = st.get("keywords") or {}
    ks = ga.get("keyword_set") or {}
    primary = kw.get("primary") or ks.get("primary") or ""
    variations = kw.get("variations") if kw else (ks.get("variations") or [])
    secs = body["sections"]

    longs, fats, totals = count(secs)
    say("Counted the long sentences and fat paragraphs",
        "%d sentences over %d words, %d paragraphs over %d sentences" % (len(longs), C.BLEND_SENTENCE_WORDS, len(fats), C.BLEND_PARA_SENTENCES))

    block = "\n\n".join("## %s\n\n%s" % (s["headline"], s["prose"]) for s in secs)
    prompt = C.prompt("blend", brand=brand["brand"], about=brand["about"], title=ctx["title"] or "(none)",
                      angle=ctx["angle"] or "(none)", spine=body.get("spine") or st.get("spine") or "(none)",
                      length=_length_line(secs, ga.get("word_band")), primary=primary or "(none)",
                      variations=", ".join(variations or []) or "(none)", jobs=_jobs_block(st, secs),
                      flags=_flags_block(longs, fats, totals), sections=block, memory=C.sh.memory_block())
    say("Editing the whole article as one piece", "one call over %d sections" % len(secs))
    with C.long_call():
        out = llm.json_call(prompt) or {}
    blended = [b for b in (out.get("sections") or []) if isinstance(b, dict)]
    return apply(secs, out, blended, primary, variations, ga.get("word_band"), say)


def apply(secs, out, blended, primary, variations, band, say=lambda *a: None):
    """The guards, the tag audit and the measurement, separated so a test can drive them."""
    def keep_original(reason):
        say("Keeping the body as written", reason)
        return [{"heading": s["headline"], "prose": s["prose"]} for s in secs], \
               [{"section": "(all)", "what": "none", "why": reason}]

    edits = [e for e in (out.get("edits") or []) if isinstance(e, dict)]
    guard_failures, warnings = [], []
    if not blended:
        blended, edits = keep_original("the editor returned no sections")
    else:
        guard_failures, warnings = guards(secs, blended)
        if guard_failures:
            blended, edits = keep_original("guards failed: " + "; ".join(guard_failures))
            warnings = []

    before = set()
    for s in secs:
        before |= tags.id_set(s["prose"])
    invented, result = 0, []
    for i, b in enumerate(blended):
        prose = str(b.get("prose") or "")
        bad = tags.id_set(prose) - before
        if bad:
            prose = tags.drop(prose, bad)
            invented += len(bad)
        result.append({"heading": secs[i]["headline"], "prose": prose})
    after = set()
    for b in result:
        after |= tags.id_set(b["prose"])
    gone = sorted(before - after)

    d = diff(secs, result)
    n_passages = sum(len(x["edits"]) for x in d)
    phrases = [p for p in ([primary] + list(variations or [])) if p]
    kw_before, kw_after = kw_counts(secs, phrases), kw_counts(result, phrases)
    kw_measured = [{"keyword": p, "before": kw_before.get(p, 0), "after": kw_after.get(p, 0)} for p in phrases]
    longs_after, fats_after, totals_after = count([{"headline": b["heading"], "prose": b["prose"]} for b in result])
    longs, fats, totals = count(secs)
    if not guard_failures and not n_passages:
        warnings.append({"kind": "no edit made", "detail": ["%d sections, zero text changed" % len(secs)],
                         "note": "twelve blind writers always leave something; this is a non-result"})
    final = {"sections": result, "edits": edits,
             "keywords": {"primary": primary, "variations": variations}, "keywords_measured": kw_measured,
             "keywords_used": [k for k in (out.get("keywords_used") or []) if isinstance(k, dict) and k.get("keyword")],
             "keywords_skipped": [k for k in (out.get("keywords_skipped") or []) if isinstance(k, dict) and k.get("keyword")],
             "length_before": _length_facts(secs, band),
             "length_after": _length_facts([{"prose": b["prose"]} for b in result], band),
             "counter_before": {"long_sentences": len(longs), "fat_paragraphs": len(fats), "sentences": totals["sentences"]},
             "counter_after": {"long_sentences": len(longs_after), "fat_paragraphs": len(fats_after),
                               "sentences": totals_after["sentences"]},
             "diff": d, "guard_failures": guard_failures, "warnings": warnings, "applied": not guard_failures,
             "tag_audit": {"tags_before": len(before), "tags_after": len(after), "invented_stripped": invented,
                           "cut_with_content": gone}}
    say("Blend done", "%d passages changed; long sentences %d -> %d; keywords present %d of %d"
        % (n_passages, len(longs), len(longs_after), sum(1 for k in kw_measured if k["after"] > 0), len(phrases))
        + ("; stripped %d invented tag(s)" % invented if invented else ""))
    return final
