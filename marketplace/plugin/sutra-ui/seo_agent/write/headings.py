"""headings.py — Architect step 6: write the final heading for every section, then the H1.

  6a ONE CALL PER SECTION, in parallel. Each call sees that section's full cards, its own researched
     keyword, the leftover pool, the primary + variations, and the searchable-words rule when the
     section covers an expected topic (the covers block is BUILT here: a section that maps to nothing
     gets no block, so there is nothing to invent a match for). It is free to use none of them.
     GUARD: it may only claim a keyword it was actually shown.
  6b THE CROSS-SECTION PASS reads all the headings AS A SET: numbering that does not run, one thing
     called two names, mixed case, eight headings built to one template, too many figures. Code counts
     which phrases are over-used (MAX_HEADINGS_PER_KEYWORD, two-sided: at most N asked for, at least N
     enforced) and how many headings carry a figure (FIGURE_HEADING_SHARE); the model decides which
     copies to keep. Guarded PER HEADING: a heading that drops its locked keyword, or gains a figure it
     did not have, is reverted on its own and the rest of the pass still lands.
  6c THE H1, written against the final list.
Then the keywords block, computed in CODE: only phrases that actually landed in a final heading.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as C
from . import section_keywords as sk

_COVERS = """
════════════════════════════════════════════════════════════════════════
THE WORDS PEOPLE ARE SEARCHING FOR

This section covers a topic almost every ranking page covers:  {topic}

Its heading must carry that topic's own words. Not instead of your angle — as well.

   Topic:      Formula / how to calculate it
   Angle only: "The SHRM Formula, and Where It Stops Counting"
   Words only: "How to Calculate Cost Per Hire"
   Both:       "How to Calculate Cost Per Hire, and Where It Stops"

A reader scanning is hunting the words already in their head. Clever without them means they
never find the section that answers their question, and neither does a search engine.

THE ANGLE IS NOT COMPULSORY. Where the plain words say it best, use the plain words and stop.
"How to Calculate Cost Per Hire" is a good heading. A heading forced to carry an angle it does
not need reads worse than a plain one, and an article whose every heading is built the same way
is exhausting to scan.
"""


def _covers_block(topic):
    topic = (topic or "").strip()
    return _COVERS.format(topic=topic) if topic else ""


def _flat(s):
    """Lowercased, punctuation stripped, single-spaced: the form a locked keyword is checked in."""
    return " ".join(re.findall(r"[a-z0-9]+", str(s or "").lower()))


def _holds(heading, keyword):
    """True when `heading` still carries the keyword's words, in order, next to each other. Blind to
    case and punctuation, and to a trailing plural. What it will NOT allow is a changed or reordered
    word: "Cost of a Hire" does not carry "cost per hire"."""
    k = _flat(keyword)
    return (not k) or k in _flat(heading)


_NAMED_NUMBER = re.compile(
    r"(?:fortune|iso|type|tier|level|section|step|part|chapter|covid|gpt|g)[\s-]*\d+", re.I)
_FIGURE = re.compile(r"\d")


def _has_figure(heading):
    """True when the heading carries a figure a reader reads as a statistic (not "Step 2", "Fortune 500")."""
    return bool(_FIGURE.search(_NAMED_NUMBER.sub("", str(heading or ""))))


def _write_one(n, sec, ctx, ks, found, pool, idx, memory):
    head, job = sec.get("headline") or "", sec.get("job") or "(none)"
    rec = {"n": n, "was": head, "heading": head, "keyword_used": None, "changed": False, "why": ""}
    kw = (found or {}).get("keyword")
    try:
        out = llm.json_call(C.prompt(
            "write-heading", title=ctx["title"] or "(untitled)", angle=ctx["angle"] or "(none recorded)",
            spine=ctx["spine"] or "(not available)", primary=ks.get("primary") or "(none)", persona=ctx["persona"],
            variations=", ".join(ks.get("variations") or []) or "(none)", heading=head, job=job,
            section_keyword=("%s (vol %s, KD %s)" % (kw, found.get("volume"), found.get("kd")) if kw
                             else "(none found for this section)"),
            covers_block=_covers_block(sec.get("covers")),
            pool="\n".join("  - %s" % p for p in pool) or "  (none left)",
            cards=sk.render_cards(sec, idx), memory=memory)) or {}
    except Exception as e:      # noqa: BLE001
        rec["why"] = "heading call failed (%s); draft kept" % str(e)[:80]
        return rec
    new = str(out.get("heading") or "").strip()
    if not new:
        rec["why"] = "empty heading returned; draft kept"
        return rec
    used = str(out.get("keyword_used") or "").strip() or None
    if used and used.lower() == "null":
        used = None
    offered = {p.lower() for p in pool}
    offered |= {(ks.get("primary") or "").lower()} | {v.lower() for v in (ks.get("variations") or [])}
    if kw:
        offered.add(kw.lower())
    if used and used.lower() not in offered:
        rec.update(heading=head, why="claimed keyword %r was never offered; draft kept" % used)
        return rec
    rec.update(heading=new, keyword_used=used, changed=(new != head),
               why=str(out.get("why") or "").strip(), chars=len(new))
    return rec


def pass_all(ctx, ks, secs, recs, memory, say=lambda *a: None):
    """6b: read every heading as a SET and edit them. Returns (applied_count, notes, per-heading log)."""
    cap = C.MAX_HEADINGS_PER_KEYWORD
    counts = {}
    for r in recs:
        if r.get("keyword_used"):
            counts[r["keyword_used"]] = counts.get(r["keyword_used"], 0) + 1
    overused = {k: n for k, n in counts.items() if n > cap}

    lines = []
    for sec, r in zip(secs, recs):
        lines.append("  %d. %s" % (r["n"], r["heading"]))
        lines.append("       job: %s" % (sec.get("job") or "(none)"))
        kw = r.get("keyword_used")
        if kw and kw in overused:
            lines.append('       OVER-USED — "%s" is in %d of these headings. You may take it out of this one.' % (kw, overused[kw]))
        elif kw:
            lines.append('       LOCKED — this phrase must survive: "%s"' % kw)
    if overused:
        block = "\n".join('  · "%s" is in %d headings — keep it in at most %d, strip it from the other %d'
                          % (k, n, cap, n - cap) for k, n in sorted(overused.items(), key=lambda x: -x[1]))
    else:
        block = "  (none — no phrase is in more than %d headings, so every LOCKED phrase is untouchable)" % cap

    fig_cap = max(1, int(len(recs) * C.FIGURE_HEADING_SHARE))
    numbered = [r["n"] for r in recs if _has_figure(r["heading"])]
    if len(numbered) > fig_cap:
        fig_block = ("  · %d of these %d headings carry a figure (headings %s).\n"
                     "  · At most %d may keep one. Take the figure out of at least %d of them."
                     % (len(numbered), len(recs), ", ".join(str(n) for n in numbered), fig_cap, len(numbered) - fig_cap))
    else:
        fig_block = ("  · %d of these %d headings carry a figure, which is within the limit of %d. "
                     "Nothing to strip — do not add one either." % (len(numbered), len(recs), fig_cap))
    try:
        out = llm.json_call(C.prompt("heading-pass", title=ctx["title"] or "(untitled)",
                                     angle=ctx["angle"] or "(none recorded)", spine=ctx["spine"] or "(not available)",
                                     primary=ks.get("primary") or "(none)", persona=ctx["persona"],
                                     keyword_cap=cap, overused=block, figure_cap=fig_cap, figure_heavy=fig_block,
                                     headings="\n".join(lines), memory=memory)) or {}
    except Exception as e:      # noqa: BLE001
        say("The heading pass failed", "every heading kept as written: %s" % str(e)[:70])
        return 0, "", []
    by_n = {}
    for h in (out.get("headings") or []):
        if isinstance(h, dict) and str(h.get("heading") or "").strip():
            try:
                by_n[int(h["n"])] = h
            except (KeyError, TypeError, ValueError):
                pass
    if not by_n:
        return 0, "", []

    # THE FLOOR, checked before anything is applied: for each over-used phrase, count how many headings
    # would STILL carry it after the pass. Below the cap and the whole pass is refused.
    starved = {}
    for kw in overused:
        survives = sum(1 for r in recs if r.get("keyword_used") == kw
                       and _holds(str((by_n.get(r["n"]) or {}).get("heading") or r["heading"]).strip(), kw))
        if survives < cap:
            starved[kw] = survives
    if starved:
        say("The heading pass stripped a bought keyword too far", "every heading kept as written")
        return 0, "", [{"n": 0, "kept": True,
                        "why": "pass refused: %s fell below the floor of %d heading(s)" % (starved, cap)}]

    applied, log = 0, []
    for r in recs:
        h = by_n.get(r["n"])
        if not h:
            continue
        new, was = str(h["heading"]).strip(), r["heading"]
        if new == was:
            continue
        if _has_figure(new) and not _has_figure(was):
            log.append({"n": r["n"], "was": was, "proposed": new, "kept": True,
                        "why": "added a figure to a heading that had none; original put back"})
            continue
        kw = r.get("keyword_used")
        if kw and kw not in overused and not _holds(new, kw):
            log.append({"n": r["n"], "was": was, "proposed": new, "kept": True,
                        "why": "dropped its locked keyword %r; original put back" % kw})
            continue
        if kw and kw in overused and not _holds(new, kw):
            r["keyword_used"] = None          # it genuinely no longer carries it; keep the record honest
        log.append({"n": r["n"], "was": was, "heading": new, "kept": False, "why": str(h.get("why") or "").strip()})
        r["heading"], r["changed"], applied = new, True, applied + 1
    left = [r["n"] for r in recs if _has_figure(r["heading"])]
    if len(left) > fig_cap:
        log.append({"n": 0, "kept": True,
                    "why": "figure-heavy: %d of %d headings still carry a number, cap is %d" % (len(left), len(recs), fig_cap)})
    return applied, str(out.get("notes") or "").strip(), log


def _write_h1(ctx, ks, planned_h1, headings, memory, say):
    try:
        out = llm.json_call(C.prompt("write-h1", h1=planned_h1 or "(none)", angle=ctx["angle"] or "(none recorded)",
                                     spine=ctx["spine"] or "(not available)", primary=ks.get("primary") or "(none)",
                                     variations=", ".join(ks.get("variations") or []) or "(none)",
                                     headings="\n".join("  %d. %s" % (i + 1, h) for i, h in enumerate(headings)),
                                     memory=memory)) or {}
    except Exception as e:      # noqa: BLE001
        say("The H1 call failed", "keeping the planned H1: %s" % str(e)[:70])
        return planned_h1, "H1 call failed"
    h1 = str(out.get("h1") or "").strip()
    return (h1 or planned_h1), str(out.get("why") or "").strip()


def run(st, inputs, ctx, idx, sk_result, planned_h1, say=lambda *a: None):
    secs = st.get("sections") or []
    ks = inputs["group_a"].get("keyword_set") or {}
    memory = C.sh.memory_block()
    found_by_n = {}
    for r in (sk_result or {}).get("sections") or []:
        if r.get("pick"):
            found_by_n[int(r["n"])] = r["pick"]
    pool = [p for p in (ks.get("secondaries") or []) if p]

    say("Writing the headings", "%d sections, %d with a researched keyword" % (len(secs), len(found_by_n)))
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        recs = list(ex.map(lambda t: _write_one(t[0] + 1, t[1], ctx, ks, found_by_n.get(t[0] + 1), pool, idx, memory),
                           list(enumerate(secs))))

    say("Reading the headings as a set", "%d headings" % len(recs))
    n_pass, pass_notes, pass_log = pass_all(ctx, ks, secs, recs, memory, say)

    long_ones = []
    for sec, r in zip(secs, recs):
        sec["headline"] = r["heading"]
        if len(r["heading"]) > C.MAX_HEADING_CHARS:
            long_ones.append({"n": r["n"], "chars": len(r["heading"]), "heading": r["heading"]})

    h1, why_h1 = _write_h1(ctx, ks, planned_h1 or st.get("h1") or "", [r["heading"] for r in recs], memory, say)
    st["h1"] = h1

    used = []
    for r in recs:
        k = r.get("keyword_used")
        if k and k not in used:
            used.append(k)
    st["keywords"] = {"primary": ks.get("primary") or "", "primary_changed": False, "why_primary": "",
                      "variations": ks.get("variations") or [], "section_keywords": used,
                      "unplaced": [{"keyword": p, "why": "no section's heading took it"} for p in pool if p not in used]}
    heading_map = {"context": {k: ctx[k] for k in ("title", "angle", "spine")}, "researched_set": ks,
                   "found_per_section": found_by_n, "headings": recs, "h1_planned": planned_h1, "h1_final": h1,
                   "why_h1": why_h1, "cross_section_pass": {"edited": n_pass, "notes": pass_notes, "changes": pass_log},
                   "over_length": long_ones, "decision": st["keywords"]}
    changed = sum(1 for r in recs if r["changed"])
    say("Headings written", "%d of %d rewritten (%d by the cross-section pass), %d carry a keyword"
        % (changed, len(recs), n_pass, len(used)) + ("; H1: %s" % h1 if h1 else ""))
    return {"structure": st, "heading_map": heading_map}
