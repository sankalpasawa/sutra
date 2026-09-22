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


def pass_all(ctx, ks, secs, recs, memory, say=lambda *a: None, table_stakes=None):
    """6b: read every heading as a SET and edit them. Returns (applied_count, notes, per-heading log).

    AND IT MAY NOW REORDER, AND REWRITE THE JOBS (owner's own design, 2026-09-23). This is the only
    step that ever sees the finished shape, and its prompt has always opened "Nobody has yet read
    the headings as a set. That is your job." It was then forbidden the two things that matter:

        "You may not add, remove or reorder sections -- same headings, same count, same order,
         in and out."

    So on a real article it read a plan whose LAST section was "What pre-employment testing is",
    with five sections above it leaning on that term, and could do nothing. The architect's own
    prompt forbids exactly that, in capitals, and lost: the archetype was `listicle`, whose format
    rule says the body is "the N parallel items", a definition is not an item, so it was pushed out
    to a closer. An advisory rule lost to a structural one, and nothing downstream could correct it.

    The same handcuffs produced the second complaint. This pass is told to BREAK THE TEMPLATE when
    four headings in a row share a construction -- so with four headings about pass scores it varied
    the fifth by changing its AXIS, to "Best for leadership and people-facing roles". The reader
    then cannot compare cognitive against EQ, which is the only reason anyone opens a "types of"
    article.

    It may now reorder and rewrite jobs. It still may NOT add or delete a section: those were
    decided with evidence behind them and this pass holds no cards. Code checks the order it
    returns is a real permutation of the same sections, the same guard faq_order already applies to
    its own ordering call, and a reply that fails it is discarded whole.
    """
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
        # The architect already labelled which expected topic this section answers, and until now
        # nobody read it. On the article that prompted this change it labelled its own LAST section
        # "What is pre-employment testing? (definition)" and placed it sixth regardless.
        if sec.get("covers"):
            lines.append("       covers the expected topic: %s" % sec["covers"])
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
    stakes = [str(x).strip() for x in (table_stakes or []) if str(x).strip()]
    stake_block = ("\n".join("  %d. %s" % (i, x) for i, x in enumerate(stakes, 1))
                   or "  (none measured for this article)")
    try:
        out = llm.json_call(C.prompt("heading-pass", title=ctx["title"] or "(untitled)",
                                     table_stakes=stake_block,
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
    # A REPLY WITH AN ORDER BUT NO HEADING EDITS IS A REAL ANSWER, and until this guard was widened
    # it was thrown away here: the early return fired before the order was ever looked at, so the
    # one reply that fixes the basics-last article and changes nothing else did nothing at all.
    # Caught by test_shape_pass.
    if not by_n and not isinstance(out.get("order"), list):
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

    # THE JOBS, which are what actually steer the writing. A heading is a label; the job is the
    # brief. The five type sections that walked off in five directions each had a differently
    # shaped job -- "settle what managers misread", "how it differs from cognitive", "who they
    # suit" -- and fixing only their headings would have left the prose exactly as it was.
    sec_by_n = {r["n"]: sec for sec, r in zip(secs, recs)}
    for n, h in by_n.items():
        job = str(h.get("job") or "").strip()
        sec = sec_by_n.get(n)
        if not sec or not job or job == (sec.get("job") or "").strip():
            continue
        log.append({"n": n, "was_job": sec.get("job"), "job": job, "kept": False,
                    "why": str(h.get("why_job") or h.get("why") or "").strip()})
        sec["job"] = job
        applied += 1
    # THE ORDER. Validated as a genuine permutation before anything moves: the same section
    # numbers, all of them, once each. Anything else is discarded whole and the original order
    # stands, because a "reorder" that loses a section is a deletion wearing a different hat, and
    # this pass is not allowed to delete. Same guard faq_order applies to its own ordering call.
    want = out.get("order")
    if isinstance(want, list) and want:
        try:
            want = [int(x) for x in want]
        except (TypeError, ValueError):
            want = None
        have = [r["n"] for r in recs]
        if want and sorted(want) == sorted(have) and len(want) == len(have):
            if want != have:
                pos = {n: i for i, n in enumerate(want)}
                pairs = sorted(zip(secs, recs), key=lambda pr: pos[pr[1]["n"]])
                secs[:] = [a for a, _b in pairs]
                recs[:] = [b for _a, b in pairs]
                moved = [{"from": have.index(n) + 1, "to": i + 1,
                          "heading": next(r["heading"] for r in recs if r["n"] == n)}
                         for i, n in enumerate(want) if have[i] != n]
                log.append({"n": 0, "kept": False, "reordered": moved,
                            "why": str(out.get("why_order") or "").strip() or "reordered as a set"})
                say("Reordered the article", "%d of %d sections moved: %s"
                    % (len(moved), len(have), str(out.get("why_order") or "")[:110]))
                applied += 1
        elif want:
            say("The heading pass returned a broken order", "the original order stands")
            log.append({"n": 0, "kept": True,
                        "why": "order refused: not a permutation of the same sections"})

    left = [r["n"] for r in recs if _has_figure(r["heading"])]
    if len(left) > fig_cap:
        log.append({"n": 0, "kept": True,
                    "why": "figure-heavy: %d of %d headings still carry a number, cap is %d" % (len(left), len(recs), fig_cap)})
    return applied, str(out.get("notes") or "").strip(), log


def _rival_stem(domain):
    """A domain's bare stem: "testgorilla.com" -> "testgorilla". The same trick write_body.py's
    `_rivals_block` uses, and for the same reason: a company's real name is not spelled out in its
    domain, so every place that needs to recognise a rival matches on the stem, case-insensitively,
    rather than guessing at a casing ("TestGorilla") that cannot be derived from the domain alone."""
    d = str(domain or "").strip().lower()
    stem = d.split("//")[-1].split("/")[0]
    if stem.startswith("www."):
        stem = stem[4:]
    return stem.split(".")[0]


def _find_rival(text, stems):
    """The first rival stem `text` names as a whole word, case-insensitive; None when it names none.
    "TestGorilla" and "testgorilla" and "TESTGORILLA" all match the stem "testgorilla"; "Test" alone,
    or "TestGorillas" (a different word once the plural runs on), does not."""
    for stem in stems:
        if stem and re.search(r"\b%s\b" % re.escape(stem), text or "", re.I):
            return stem
    return None


def guard_rivals(recs, rivals, memory, say=lambda *a: None):
    """The deterministic backstop, run once every heading's per-section and cross-section pass is
    done and the heading map is otherwise final.

    Aparna's review, 2026-09-17: a published piece ran about 45% TestGorilla, with TestGorilla named
    in two of its H2s. write-heading.md and heading-pass.md both now ask the model not to do that,
    but asking is not enforcing — the whole point of a review like hers is that asking already
    failed once. This checks every FINAL heading against the rival list on file
    (knowledge/competitors.json, via tools/_shared.load_competitors) and, for any that still names
    one, asks for exactly one rewrite. A rewrite that still carries the name is refused and the
    draft heading stays; either way the decision is logged, never silently.
    """
    stems = [s for s in (_rival_stem(r.get("domain") if isinstance(r, dict) else r) for r in (rivals or [])) if s]
    log = []
    if not stems:
        return log
    for r in recs:
        head = r.get("heading") or ""
        stem = _find_rival(head, stems)
        if not stem:
            continue
        try:
            out = llm.json_call(C.prompt("rival-heading", heading=head, rival=stem, memory=memory)) or {}
        except Exception as e:      # noqa: BLE001
            log.append({"n": r.get("n"), "was": head, "kept": True, "rival": stem,
                        "why": "rewrite call failed (%s); original kept" % str(e)[:80]})
            continue
        new = str(out.get("heading") or "").strip()
        if new and not _find_rival(new, stems):
            log.append({"n": r.get("n"), "was": head, "heading": new, "rival": stem, "kept": False,
                        "why": str(out.get("why") or "").strip()})
            r["heading"], r["changed"] = new, True
        else:
            log.append({"n": r.get("n"), "was": head, "kept": True, "rival": stem,
                        "why": "rewrite still named a rival; original kept"})
    if log:
        say("Checked headings for a rival's name", "%d flagged, %d rewritten"
            % (len(log), sum(1 for l in log if not l["kept"])))
    return log


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
    with llm.pool() as ex:
        recs = list(ex.map(lambda t: _write_one(t[0] + 1, t[1], ctx, ks, found_by_n.get(t[0] + 1), pool, idx, memory),
                           list(enumerate(secs))))

    say("Reading the headings as a set", "%d headings" % len(recs))
    n_pass, pass_notes, pass_log = pass_all(ctx, ks, secs, recs, memory, say,
                                            table_stakes=(inputs.get('group_a') or {}).get('table_stakes'))

    # The heading map is otherwise final at this point (per-section pass, then the cross-section
    # pass, both done) — the deterministic point Aparna's review calls for (2026-09-17).
    rival_log = guard_rivals(recs, C.sh.load_competitors(), memory, say)

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
                   "rival_guard": rival_log, "over_length": long_ones, "decision": st["keywords"]}
    changed = sum(1 for r in recs if r["changed"])
    say("Headings written", "%d of %d rewritten (%d by the cross-section pass), %d carry a keyword"
        % (changed, len(recs), n_pass, len(used)) + ("; H1: %s" % h1 if h1 else ""))
    return {"structure": st, "heading_map": heading_map}
