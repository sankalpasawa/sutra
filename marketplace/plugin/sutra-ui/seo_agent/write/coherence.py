"""coherence.py — Writer step 4: COHERENCE. The first step that reads the finished article WHOLE.

Every section is written by a different call, none able to see the others. Faults that live BETWEEN
sections cannot be caught earlier: a rule stated in section 7 and broken in section 5, one thing scored
on 1-5 here and 0-2-4 there.

  Step 1  INVENTORY (coherence-inventory.md): pure transcription, no judgement. Every rule, scale and
          quantity, with where each appears and how often.
  Step 2  EDIT (coherence-edit.md): the article plus that list; returns FIXES, one entry per fault
          found, never the article. Each fix is one exact `find` (copied from the article) and what
          it `replace`s it with.
  Step 3  APPLY each fix ON ITS OWN, in code: `find` must appear exactly once in the section named;
          the tags in `find` must all survive into `replace`, and none may be added; a number in
          `replace` that is new must already be in the article, or be declared as computed from
          numbers that are; `replace` may not carry a heading line; `replace` may not balloon past
          about 2.5x the words of `find`. A fix that fails ANY of those is skipped, on its own, with
          the reason recorded — the other fixes still land.
  Step 4  ONE RETRY, for the fixes that were skipped only, naming exactly why each one failed.
  Step 5  GUARDS in code, over the finished, composed result, as a last sanity check: headings, the
          H1, section survival, a catastrophic tag strip. Any failure and the original publishes
          unchanged, in full, even the fixes that individually passed step 3.

WHY THIS REPLACED A WHOLE-ARTICLE REWRITE (2026-09-18, Devansh approved, specs/parked-2026-09-18.md
section 1). The old step 2 asked the model to hand back the WHOLE article, edited, and step 4 was an
all-or-nothing guard over that whole reply: any one blocking fault (a heading moved, a tag stripped
past the loss threshold, a number the guard could not explain) threw away every fix in the reply, real
ones included. On 2026-09-18 that lost every real fix on two live articles: a Recruiting Metrics
article whose own numbers ($70,000 value, $90,400 cost) work out to about 23% ROI kept a stated 45%,
because the rewrite that would have fixed it also dropped 52% of the article's [c...] source tags and
was refused whole; a Referral Programs article kept four contradictions the same way, at a 77% tag
loss. Both published with their real errors still in them (`report.applied = False`, "guards failed
twice" — the retry made the identical whole-article mistake a second time). The guard also called "23"
an invented number, though it was the article's own arithmetic; the whole-article shape gave it no way
to tell an honest correction from a fabrication. Patches, applied and judged one at a time, fix both:
a fault that collides with a guard is now the ONE fix that is lost, not the whole pass, and a corrected
number can prove itself by showing the article's own figures it was computed from.
"""
import difflib
import json
import re

from .. import llm
from . import _common as C
from . import tags

_NUMS = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_HEADING_LINE = re.compile(r"(?m)^\s*#{1,6}\s+\S")


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
    """label -> prose, in reading order. The one set of block labels every step here reads and
    writes fixes by: the fix's `section` field is asked to name one of these."""
    out = [("intro", w.get("intro") or ""), ("quick answer", w.get("quick_answer") or "")]
    out += [(s.get("heading", "?"), s.get("prose") or "") for s in w.get("sections") or []]
    out += [("FAQ: %s" % f.get("question", "")[:50], f.get("answer") or "") for f in w.get("faq") or []]
    out.append(("close", w.get("close") or ""))
    return out


def _all_prose(w):
    return "\n\n".join(t for _, t in prose_blocks(w))


def guards(before, after, allowed_numbers=None):
    """Returns (blocking_reasons, warnings). The last sanity check over the FINISHED, composed
    result — after every individual fix already passed its own guard in _apply_fix. `allowed_numbers`
    is the set of "now" figures a fix already proved (via numbers_changed.derived_from) were computed
    from numbers already in the article; without it this would re-flag the article's own honest
    arithmetic as invented, which is the exact bug that lost the 45%-should-be-23% fix on 2026-09-18.
    Existing callers that pass only (before, after) are unaffected — nothing is allowed by default."""
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
    invented = na - nb - (allowed_numbers or set())
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


# ---- applying one fix at a time ---------------------------------------------------------------

def _find_label(blocks, section):
    """Match a fix's stated `section` to one of `blocks`' labels (prose_blocks()' own labels),
    tolerant of case and of the FAQ label's 50-character question truncation — the prompt asks the
    model for the question in full, and the block label only ever carries its first 50 characters."""
    section = str(section or "").strip()
    if not section:
        return None
    low = section.lower()
    for label in blocks:
        if label.lower() == low:
            return label
    if low.startswith("faq"):
        q = section.split(":", 1)[1].strip() if ":" in section else ""
        if q:
            for label in blocks:
                if label.lower().startswith("faq:"):
                    key_q = label.split(":", 1)[1].strip()
                    if key_q and (key_q.lower() == q[:len(key_q)].lower() or q.lower() == key_q[:len(q)].lower()):
                        return label
    return None


def _declared_numbers(fix, article_numbers):
    """The "now" figures this fix's own numbers_changed entries are allowed to introduce — but only
    the ones whose declared derived_from is itself made entirely of numbers already in the article.
    This is what lets 45% become 23% ($70,000 / $90,400, the article's own inputs) without the guard
    calling 23 an invention: the fix has to show its working, in numbers the article already stands
    behind, not just assert a number is fine."""
    allowed = set()
    for nc in fix.get("numbers_changed") or []:
        if not isinstance(nc, dict):
            continue
        derived_nums = set(_NUMS.findall(str(nc.get("derived_from") or "")))
        if derived_nums and derived_nums <= article_numbers:
            allowed |= set(_NUMS.findall(str(nc.get("now") or "")))
    return allowed


def _apply_fix(blocks, fix, article_numbers):
    """Try to land one fix against the running copy `blocks` (label -> text, mutated in place on
    success). Returns None on success, or the one-line reason it was skipped. Every reason here is
    ALSO the reason the retry prompt is told, so a skip is never a dead end and never silent."""
    section = fix.get("section")
    find = str(fix.get("find") or "")
    replace = str(fix.get("replace") or "")
    if not find.strip():
        return "no 'find' text given"
    label = _find_label(blocks, section)
    if label is None:
        return "section %r not found in the article" % str(section or "")[:60]
    text = blocks[label]
    count = text.count(find)
    if count == 0:
        return "'find' does not appear in %s — not copied exactly, character for character" % label
    if count > 1:
        return "'find' appears %d times in %s; too ambiguous to know which one is meant" % (count, label)

    find_ids, replace_ids = set(tags.ids(find)), set(tags.ids(replace))
    if find_ids - replace_ids:
        return "drops source tag(s) %s that 'find' had" % sorted(find_ids - replace_ids)
    if replace_ids - find_ids:
        return "adds source tag(s) %s that were not in 'find'" % sorted(replace_ids - find_ids)

    new_nums = set(_NUMS.findall(replace)) - set(_NUMS.findall(find))
    invented = new_nums - article_numbers - _declared_numbers(fix, article_numbers)
    if invented:
        return ("invents number(s) not already in the article and not declared, with a derived_from "
                 "already in the article, in numbers_changed: %s" % ", ".join(sorted(invented)))

    if _HEADING_LINE.search(replace):
        return "'replace' contains a markdown heading line; headings are not a fix's to touch"

    fw, rw = len(find.split()), len(replace.split())
    if fw and rw > fw * C.COHERENCE_FIX_MAX_RATIO:
        return "'replace' is %.1fx the words of 'find' (max %.1fx)" % (rw / fw, C.COHERENCE_FIX_MAX_RATIO)

    blocks[label] = text.replace(find, replace, 1)
    return None


def _apply_blocks(w, blocks):
    """The edited blocks written back into a copy of `w`, by the same labels prose_blocks() reads
    them out by."""
    n = C.deep(w)
    n["intro"] = blocks.get("intro", n.get("intro") or "")
    n["quick_answer"] = blocks.get("quick answer", n.get("quick_answer") or "")
    for s in n.get("sections") or []:
        if s.get("heading") in blocks:
            s["prose"] = blocks[s["heading"]]
    for f in n.get("faq") or []:
        label = "FAQ: %s" % str(f.get("question", ""))[:50]
        if label in blocks:
            f["answer"] = blocks[label]
    n["close"] = blocks.get("close", n.get("close") or "")
    return n


def _render_fix(fix, why=None):
    lines = ["- kind: %s" % fix.get("kind", ""), "  section: %s" % fix.get("section", ""),
             "  find: %s" % fix.get("find", ""), "  replace: %s" % fix.get("replace", "")]
    if why:
        lines.append("  REJECTED BECAUSE: %s" % why)
    return "\n".join(lines)


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
                    inventory=json.dumps(inv, indent=2), article=article, memory=C.sh.memory_block())
    except Exception as e:      # noqa: BLE001
        return bail("edit call failed (%s)" % type(e).__name__)

    fixes = [f for f in (out.get("fixes") or []) if isinstance(f, dict)]
    report["verdict"] = str(out.get("verdict") or "").strip()
    report["could_not_fix"] = [c for c in (out.get("could_not_fix") or []) if isinstance(c, dict)]

    # Every number already in the article, before any fix touches it. What "already somewhere in
    # the article" means throughout _apply_fix and _declared_numbers.
    article_numbers = set(_NUMS.findall(_all_prose(w)))
    blocks = dict(prose_blocks(w))

    applied, skipped = [], []
    for fix in fixes:
        reason = _apply_fix(blocks, fix, article_numbers)
        if reason is None:
            applied.append(fix)
        else:
            skipped.append({"fix": fix, "why": reason})

    if skipped:
        say("Some fixes were rejected by code", "%d of %d; retrying those once" % (len(skipped), len(fixes)))
        rejected_block = "\n\n".join(_render_fix(s["fix"], s["why"]) for s in skipped)
        try:
            retry = _edit("coherence-retry", rejected=rejected_block, article=render(_apply_blocks(w, blocks)),
                          memory=C.sh.memory_block())
        except Exception:       # noqa: BLE001
            retry = {}
        report["retry_attempted"] = True
        retry_fixes = [f for f in (retry.get("fixes") or []) if isinstance(f, dict)]
        report["could_not_fix"] += [c for c in (retry.get("could_not_fix") or []) if isinstance(c, dict)]
        if retry.get("verdict"):
            report["verdict"] = str(retry.get("verdict") or "").strip()

        # Match the retry's fixes back to the skipped ones IN ORDER (the retry was handed exactly
        # this list and asked to redo it, one for one). A skipped fix the retry did not address at
        # all — dropped silently rather than corrected or moved to could_not_fix — keeps its
        # ORIGINAL reason below, so it still appears in the report. Nothing skipped goes quiet.
        still_skipped = []
        retry_iter = iter(retry_fixes)
        for s in skipped:
            rf = next(retry_iter, None)
            if rf is None:
                still_skipped.append(s)
                continue
            reason2 = _apply_fix(blocks, rf, article_numbers)
            if reason2 is None:
                applied.append(rf)
            else:
                still_skipped.append({"fix": rf, "why": "failed again after the retry: %s" % reason2})
        skipped = still_skipped

    new = _apply_blocks(w, blocks)
    allowed_numbers = set()
    for f in applied:
        allowed_numbers |= _declared_numbers(f, article_numbers)
    failures, warnings = guards(w, new, allowed_numbers)
    report.update(diff=diff(w, new), guard_failures=failures, warnings=warnings,
                  fixes_applied=applied, fixes_skipped=skipped)

    n_a, n_s = len(applied), len(skipped)
    if failures:
        msg = ("%d fix(es) had individually passed but the composed result failed the final "
               "whole-article guard (%s); keeping the original" % (n_a, "; ".join(failures)[:160]))
        return bail(msg)

    report["applied"] = bool(applied)
    if n_a and not n_s:
        detail = "%d fix%s applied" % (n_a, "" if n_a == 1 else "es")
    elif n_a and n_s:
        detail = "%d fix%s applied, %d could not be applied (see the report)" % (n_a, "" if n_a == 1 else "es", n_s)
    elif n_s:
        detail = "0 fixes applied, %d could not be applied (see the report)" % n_s
    else:
        detail = "no fixes needed"
    say("Read the article whole", detail)
    return {"article": new, "report": report}
