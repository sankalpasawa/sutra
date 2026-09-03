"""coherence.py — Writer step 4: COHERENCE. The first step that reads the finished article WHOLE.

Every section is written by a different call, none able to see the others. Faults that live BETWEEN
sections cannot be caught earlier: a rule stated in section 7 and broken in section 5, one thing scored
on 1-5 here and 0-2-4 there.

  Step 1  INVENTORY (coherence-inventory.md): pure transcription, no judgement. Every rule, scale and
          quantity, with where each appears and how often.
  Step 2  EDIT (coherence-edit.md): the article plus that list; returns the WHOLE article edited.
  Step 3  DIFF in code: we MEASURE what changed rather than trusting it to report.
  Step 4  GUARDS in code, ALL-OR-NOTHING: headings, the H1, section survival, an INVENTED number that
          appears nowhere in the original, a catastrophic tag strip. Any failure and the original
          publishes unchanged. Changed figures and a few lost tags WARN; they can be the repair.
  Step 5  ONE RETRY, naming exactly what failed. A retry has no partial state: a whole clean article
          or the original, untouched.
"""
import difflib
import json
import re

from .. import llm
from . import _common as C
from . import tags

_NUMS = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_LEAD_HEADING = re.compile(r"\A\s*#{1,4}\s+[^\n]+\n+")


def strip_heading(text):
    """Drop a heading the model wrote into the top of a block it does not own."""
    return _LEAD_HEADING.sub("", str(text or "")).strip()


def render(w):
    """The whole article as the editor sees it, in the order the reader gets."""
    L = ["# %s" % (w.get("h1") or ""), "", w.get("intro") or ""]
    if w.get("quick_answer"):
        L += ["", "## Quick answer", "", w["quick_answer"]]
    for s in w.get("sections") or []:
        L += ["", "## %s" % s["heading"], "", s.get("prose") or ""]
    if w.get("faq"):
        L += ["", "## Frequently asked questions"]
        for f in w["faq"]:
            L += ["", "**%s**" % f.get("question", ""), "", f.get("answer") or ""]
    if w.get("close_heading"):
        L += ["", '(the close sits under the heading "%s")' % w["close_heading"]]
    L += ["", w.get("close") or ""]
    return "\n".join(L)


def prose_blocks(w):
    out = [("intro", w.get("intro") or ""), ("quick answer", w.get("quick_answer") or "")]
    out += [(s.get("heading", "?"), s.get("prose") or "") for s in w.get("sections") or []]
    out += [("FAQ: %s" % f.get("question", "")[:50], f.get("answer") or "") for f in w.get("faq") or []]
    out.append(("close", w.get("close") or ""))
    return out


def _all_prose(w):
    return "\n\n".join(t for _, t in prose_blocks(w))


def guards(before, after):
    """Returns (blocking_reasons, warnings)."""
    block, warn = [], []
    ob, oa = _all_prose(before), _all_prose(after)
    hb = [s.get("heading") for s in before.get("sections") or []]
    ha = [s.get("heading") for s in after.get("sections") or []]
    if hb != ha:
        block.append("headings changed (%d -> %d); they belong to the architect" % (len(hb), len(ha)))
    if (before.get("h1") or "") != (after.get("h1") or ""):
        block.append("the H1 was changed")
    empty = [s.get("heading") for s in after.get("sections") or [] if not (s.get("prose") or "").strip()]
    if empty:
        block.append("%d section(s) left empty: %s" % (len(empty), ", ".join(str(x)[:40] for x in empty[:3])))
    nb, na = set(_NUMS.findall(ob)), set(_NUMS.findall(oa))
    invented = na - nb
    if invented:
        block.append("INVENTED %d number(s) absent from the original: %s" % (len(invented), ", ".join(sorted(invented)[:6])))
    tb, ta = set(tags.ids(ob)), set(tags.ids(oa))
    lost_tags = tb - ta
    if tb and len(lost_tags) / len(tb) > C.COHERENCE_TAG_LOSS_BLOCK:
        block.append("stripped %d of %d source tags (%d%%); that is not editing"
                     % (len(lost_tags), len(tb), round(100 * len(lost_tags) / len(tb))))
    elif lost_tags:
        warn.append({"kind": "source tags lost", "detail": sorted(str(x) for x in lost_tags),
                     "note": "acceptable if those claims were cut; a problem if the claim survived"})
    fb, fa = _NUMS.findall(ob), _NUMS.findall(oa)
    moved = sorted({n for n in set(fb) | set(fa) if fb.count(n) != fa.count(n)})
    if moved:
        warn.append({"kind": "numbers changed", "detail": moved,
                     "note": "a rating band changing is the repair; a statistic changing is a fact change"})
    wb, wa = len(ob.split()), len(oa.split())
    if wb and abs(wa - wb) * 100 / wb > C.COHERENCE_WORD_TOLERANCE:
        warn.append({"kind": "length moved", "detail": ["%d -> %d words" % (wb, wa), "%+d%%" % round((wa - wb) * 100 / wb)],
                     "note": "over the usual tolerance"})
    return block, warn


def diff(before, after):
    out, bmap = [], dict(prose_blocks(before))
    for label, new in prose_blocks(after):
        old = bmap.get(label)
        if old is None or old == new:
            continue
        sm = difflib.SequenceMatcher(None, old.split(), new.split())
        edits = [{"was": " ".join(old.split()[i1:i2]) or "(nothing)", "now": " ".join(new.split()[j1:j2]) or "(cut)"}
                 for tag_, i1, i2, j1, j2 in sm.get_opcodes() if tag_ != "equal"]
        out.append({"block": label, "similarity": round(sm.ratio(), 3), "edits": edits})
    return out


def apply_reply(w, reply):
    """The reply, folded back into the wrapper's shape, keeping every field it does not own."""
    n = C.deep(w)
    n["intro"] = strip_heading(str(reply.get("intro") or w.get("intro") or ""))
    if reply.get("quick_answer"):
        n["quick_answer"] = strip_heading(str(reply["quick_answer"]))
    n["close"] = strip_heading(str(reply.get("close") or w.get("close") or ""))
    by_head = {str(s.get("heading", "")): str(s.get("prose") or "")
               for s in reply.get("sections") or [] if isinstance(s, dict)}
    for s in n.get("sections") or []:
        if s["heading"] in by_head and by_head[s["heading"]].strip():
            s["prose"] = by_head[s["heading"]]
    ans = {str(f.get("question", "")): str(f.get("answer") or "") for f in (reply.get("faq") or []) if isinstance(f, dict)}
    for f in n.get("faq") or []:
        if f.get("question") in ans and ans[f["question"]].strip():
            f["answer"] = ans[f["question"]]
    return n


def run(w, ctx, plan, say=lambda *a: None):
    brand = C.company()
    persona = C.persona_short({"persona": plan.get("persona")}, {})
    article = render(w)
    report = {}

    def bail(msg, **extra):
        say("Coherence pass left the article unchanged", msg)
        return {"article": w, "report": dict(report, applied=False, reason=msg, **extra)}

    say("Listing every rule, scale and quantity in the article", "")
    try:
        with C.long_call():
            inv = llm.json_call(C.prompt("coherence-inventory", article=article)) or {}
    except Exception as e:      # noqa: BLE001
        return bail("inventory call failed (%s)" % type(e).__name__)
    report["inventory"] = inv
    counts = {k: len(inv.get(k) or []) for k in ("rules", "scales", "quantities")}
    say("Inventory done", "%d rules, %d scale mentions, %d quantities" % (counts["rules"], counts["scales"], counts["quantities"]))

    def _edit(prompt_name, **kw):
        with C.long_call():
            return llm.json_call(C.prompt(prompt_name, **kw)) or {}

    try:
        out = _edit("coherence-edit", brand=brand["brand"], about=brand["about"], h1=w.get("h1") or "",
                    angle=C.or_na(ctx, "angle"), spine=C.or_na(ctx, "spine"), world_about=C.or_na(ctx, "about"),
                    world_not_about=C.or_na(ctx, "not_about"), persona=persona,
                    word_tolerance=C.COHERENCE_WORD_TOLERANCE, inventory=json.dumps(inv, indent=2), article=article,
                    memory=C.sh.memory_block())
    except Exception as e:      # noqa: BLE001
        return bail("edit call failed (%s)" % type(e).__name__)
    report.update(verdict=str(out.get("verdict") or "").strip(),
                  changes_claimed=[c for c in (out.get("changes") or []) if isinstance(c, dict)],
                  could_not_fix=[c for c in (out.get("could_not_fix") or []) if isinstance(c, dict)])
    if not out.get("sections"):
        return bail("the edit returned no sections")
    new = apply_reply(w, out)
    d = diff(w, new)
    failures, warnings = guards(w, new)
    report.update(diff=d, guard_failures=failures, warnings=warnings,
                  numbers_changed_claimed=[c for c in (out.get("numbers_changed") or []) if isinstance(c, dict)])
    say("Read the article whole", "%d blocks touched, %d fixes claimed" % (len(d), len(report["changes_claimed"])))

    if failures:
        say("The edit was blocked", "; ".join(failures)[:160] + ". Retrying once.")
        try:
            retry = _edit("coherence-retry", failures="\n".join("- %s" % f for f in failures), edited=render(new),
                          memory=C.sh.memory_block())
        except Exception:       # noqa: BLE001
            retry = {}
        report["retry_attempted"] = True
        if retry.get("sections"):
            new2 = apply_reply(w, retry)
            f2, w2 = guards(w, new2)
            report["retry_failures"] = f2
            if not f2:
                new, failures, warnings = new2, [], w2
                report.update(diff=diff(w, new), guard_failures=[], warnings=warnings, retry_worked=True,
                              changes_claimed=[c for c in (retry.get("changes") or []) if isinstance(c, dict)],
                              could_not_fix=[c for c in (retry.get("could_not_fix") or []) if isinstance(c, dict)],
                              verdict=str(retry.get("verdict") or "").strip())
    if failures:
        return bail("guards failed twice; keeping the original", verdict=report.get("verdict"))
    report["applied"] = True
    say("Coherence pass applied", report.get("verdict", "")[:100])
    return {"article": new, "report": report}
