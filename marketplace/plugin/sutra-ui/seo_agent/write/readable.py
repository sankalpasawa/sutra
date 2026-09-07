"""readable.py — Writer step 5: READABLE. Rewrite the whole article so a person wants to read it.

The sections it returns REPLACE the ones it was given: it merges, splits, reorders and deletes, so there
is nothing stable to match on. What guards the output is the check list, not the shape. EVERY CHECK
FLAGS. NONE BLOCK: the earlier steps already guard themselves, and what is measured here is only what
THIS step could break.

  5a  the rewrite (readable.md), with the checklist code computed before the call: FACTS_NOW, WORDS_NOW,
      TARGET_WORDS = min(READABLE_CEILING, current), the reading ease, the hard words, the longest
      sentences, the archetype and its format rule (formats/<arch>.md "## The rewrite").
  5b  fix_fat (fat-paragraphs.md): code finds the paragraphs over the sentence ceiling, one call rewrites
      only those, code validates each replacement and swaps it back by id.
  5c  fix_plain (plain-english.md, at most 2 rounds): the worst-scoring blocks go back with their hard
      words named; a round that made the score worse is discarded whole.
  then judge_coverage (readable-coverage.md) and check(): every row protects something an earlier step bought.
"""
import re

from .. import llm
from . import _common as C
from . import tags

MDLINK = C._MDLINK
_REWRITE_SECTION = re.compile(r"^##\s+The rewrite\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
NUM = re.compile(r"\d[\d,]*\.?\d*%?")
_BARE_TAG = re.compile(r"\[c\](?!\d)")
_SENT = re.compile(r"(?<=[.!?])\s+")
_LISTY = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||>|#)")


def format_rule(archetype):
    """The format's own rule for THIS step, or "" when it has none."""
    if not archetype:
        return ""
    try:
        body = open(C.format_path(archetype), encoding="utf-8").read()
    except OSError:
        return ""
    m = _REWRITE_SECTION.search(body)
    if not m:
        return ""
    rule = re.sub(r"\A\s*Injected into[^\n]*(?:\n(?!\s*\n)[^\n]*)*\n\s*\n", "", m.group(1).strip(), count=1)
    return "\n" + rule.strip() + "\n"


# ---------------------------------------------------------------- readability
def _syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)


def texts(w):
    out = [str(w.get("intro") or ""), str(w.get("quick_answer") or "")]
    out += [str(s.get("prose") or "") for s in (w.get("sections") or [])]
    out += [str(f.get("answer") or "") for f in (w.get("faq") or [])]
    out.append(str(w.get("close") or ""))
    return [t for t in out if t.strip()]


def plain(w):
    t = "\n\n".join(texts(w))
    t = tags.sub(t, lambda _found: "")
    return MDLINK.sub(r"\1", t)


def _score(p):
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", p)
    sents = [s for s in _SENT.split(p) if len(s.split()) > 2]
    if not words or not sents:
        return None
    return round(206.835 - 1.015 * (len(words) / len(sents)) - 84.6 * (sum(_syllables(x) for x in words) / len(words)), 1)


def reading_ease(w):
    """Flesch Reading Ease. 60+ is plain English; under 50 is heavy going."""
    s = _score(plain(w))
    return 0.0 if s is None else s


def _block_score(text):
    s = _score(MDLINK.sub(r"\1", tags.sub(str(text or ""), lambda _f: "")))
    return 100.0 if s is None else s


def words(w):
    return len(" ".join(texts(w)).split())


def subheads(w):
    return re.findall(r"^###+\s*(.+?)\s*$", "\n".join(texts(w)), re.M)


def _tag_map(w):
    return {i: tags.id_set(t) for i, t in enumerate(texts(w))}


def fact_ids(w):
    out = set()
    for ids in _tag_map(w).values():
        out |= set(ids)
    return out


def words_per_fact(w):
    n = len(fact_ids(w))
    return (words(w) / n) if n else 999.0


def long_sentences(w):
    return [s for s in _SENT.split(plain(w)) if len(s.split()) > C.WORDS_PER_SENTENCE]


def _hard_words(w, top=22):
    seen = {}
    for x in re.findall(r"[A-Za-z][A-Za-z'-]*", plain(w)):
        if _syllables(x) >= 4:
            k = x.lower()
            seen[k] = seen.get(k, 0) + 1
    return sorted(seen.items(), key=lambda kv: -kv[1])[:top]


def render_hard_words(w):
    rows = _hard_words(w)
    if not rows:
        return "  (none — the vocabulary is already plain. Keep it that way.)"
    return "\n".join("  %-22s appears %dx" % (word, n) for word, n in rows)


def render_long_sentences(w, top=15):
    real = [s for s in long_sentences(w) if "|" not in s and not s.lstrip().startswith(("-", "*"))]
    longs = sorted(real, key=lambda s: -len(s.split()))[:top]
    if not longs:
        return "  (none over %d words — good. Keep it that way.)" % C.WORDS_PER_SENTENCE
    return "\n".join("  %d. (%d words) %s" % (i, len(s.split()), " ".join(s.split())[:150]) for i, s in enumerate(longs, 1))


def fat_paragraphs(w):
    out = []
    for para in re.split(r"\n\s*\n", plain(w)):
        if re.match(r"^\s*(?:[-*+]\s|\d+[.)]\s)", para.strip()):
            continue
        if len([s for s in _SENT.split(para) if s.strip()]) > C.SENTENCES_PER_PARAGRAPH:
            out.append(para)
    return out


def render(w):
    L = ["# %s" % (w.get("h1") or ""), "", "INTRO:", "", str(w.get("intro") or "")]
    if w.get("quick_answer"):
        L += ["", "QUICK ANSWER:", "", str(w.get("quick_answer") or "")]
    for s in w.get("sections") or []:
        L += ["", "## %s" % s.get("heading", ""), "", str(s.get("prose") or "")]
    if w.get("faq"):
        L += ["", "FREQUENTLY ASKED QUESTIONS"]
        for f in w["faq"]:
            L += ["", "**%s**" % f.get("question", ""), "", str(f.get("answer") or "")]
    L += ["", 'CLOSE  (it sits under the heading "%s"):' % (w.get("close_heading") or "(none)"), "", str(w.get("close") or "")]
    return "\n".join(L)


_LEAD_HEADING = re.compile(r"\A\s*#{1,4}\s+[^\n]+\n+")


def _strip_heading(text):
    return _LEAD_HEADING.sub("", str(text or "")).strip()


def apply_reply(w, reply):
    """Fold the reply back in. The sections it returns REPLACE the ones it was given."""
    n = C.deep(w)
    h1_new = str(reply.get("h1") or "").strip()
    if h1_new:
        n["h1"] = _strip_heading(h1_new).lstrip("#").strip() or n.get("h1")
    if str(reply.get("intro") or "").strip():
        n["intro"] = _strip_heading(str(reply["intro"]))
    if str(reply.get("close") or "").strip():
        n["close"] = _strip_heading(str(reply["close"]))
    if str(reply.get("quick_answer") or "").strip():
        n["quick_answer"] = _strip_heading(str(reply["quick_answer"]))
    secs = [s for s in (reply.get("sections") or []) if isinstance(s, dict) and str(s.get("prose") or "").strip()]
    if secs:
        keep = {k: v for k, v in (w.get("sections") or [{}])[0].items() if k not in ("heading", "prose")} if w.get("sections") else {}
        n["sections"] = [dict(keep, heading=str(s.get("heading") or "").strip() or "Section", prose=str(s.get("prose")).strip())
                         for s in secs]
    ans = {str(f.get("question", "")).strip(): str(f.get("answer") or "").strip()
           for f in (reply.get("faq") or []) if isinstance(f, dict)}
    for f in n.get("faq") or []:
        a = ans.get(str(f.get("question", "")).strip())
        if a:
            f["answer"] = a
    return n


# ------------------------------------------------------- 5b: the fat-paragraph fixer
def _paras(text):
    return [p for p in re.split(r"\n\s*\n", str(text or "").strip()) if p.strip()]


def _bare(text):
    return MDLINK.sub(r"\1", tags.sub(str(text or ""), lambda _f: ""))


def _sent_count(para):
    return len([s for s in _SENT.split(_bare(para)) if s.strip()])


def _is_prose(para):
    return bool(para.strip()) and not _LISTY.match(para.strip())


def _nums_in(text):
    return {x.rstrip(".,") for x in NUM.findall(tags.sub(str(text or ""), lambda _f: ""))}


def _urls_in(text):
    return {u for _, u in MDLINK.findall(str(text or ""))}


def _block_text(w, key):
    if key[0] == "s" and key[1:].isdigit():
        return str((w.get("sections") or [])[int(key[1:]) - 1].get("prose") or "")
    return str(w.get(key) or "")


def _set_block(w, key, text):
    if key[0] == "s" and key[1:].isdigit():
        (w.get("sections") or [])[int(key[1:]) - 1]["prose"] = text
    else:
        w[key] = text


def _block_keys(w):
    return (["intro", "quick_answer"] + ["s%d" % (i + 1) for i in range(len(w.get("sections") or []))] + ["close"])


def find_fat(w):
    out = []
    for key in _block_keys(w):
        ps = _paras(_block_text(w, key))
        room = sum(1 for p in ps if _is_prose(p))
        for j, p in enumerate(ps):
            if _is_prose(p) and _sent_count(p) > C.SENTENCES_PER_PARAGRAPH:
                out.append({"id": "%s-p%d" % (key, j + 1), "key": key, "idx": j, "text": p,
                            "sentences": _sent_count(p), "paras_in_section": room})
    return out


def judge_fix(old, new, paras_in_section):
    """"" when the replacement is safe to paste in, otherwise the reason it is refused."""
    ps = _paras(new)
    if not ps:
        return "came back empty"
    if len(ps) > 2:
        return "%d paragraphs — one split is the limit" % len(ps)
    if paras_in_section - 1 + len(ps) > C.PARAGRAPHS_PER_SECTION:
        return ("a split would leave the section with %d paragraphs, over the cap of %d"
                % (paras_in_section - 1 + len(ps), C.PARAGRAPHS_PER_SECTION))
    over = [p for p in ps if _sent_count(p) > C.SENTENCES_PER_PARAGRAPH]
    if over:
        return "still %d sentences" % _sent_count(over[0])
    if tags.id_set(new) - tags.id_set(old):
        return "invented the source tag(s) %s" % sorted(tags.id_set(new) - tags.id_set(old))[:3]
    if _nums_in(new) - _nums_in(old):
        return "invented the figure(s) %s" % sorted(_nums_in(new) - _nums_in(old))[:3]
    if _urls_in(new) != _urls_in(old):
        return "changed a link"
    return ""


def fix_fat(w, say=lambda *a: None):
    fat = find_fat(w)
    if not fat:
        return w, {"found": 0, "applied": 0, "fixes": []}
    say("Fixing paragraphs that run too long", "%d" % len(fat))
    marked = C.deep(w)
    by_block = {}
    for t in fat:
        by_block.setdefault(t["key"], []).append(t)
    for key, ts in by_block.items():
        ps = _paras(_block_text(marked, key))
        for t in ts:
            ps[t["idx"]] = "[[%s]] %s" % (t["id"], ps[t["idx"]])
        _set_block(marked, key, "\n\n".join(ps))
    lines = []
    for t in fat:
        room = C.PARAGRAPHS_PER_SECTION - t["paras_in_section"]
        lines.append("[%s] — %d sentences. Its section has %d paragraph(s), so " % (t["id"], t["sentences"], t["paras_in_section"])
                     + ("splitting would push it over the cap of %d — SHORTEN, do not split." % C.PARAGRAPHS_PER_SECTION
                        if room < 1 else "there is room for one split (cap is %d)." % C.PARAGRAPHS_PER_SECTION))
        lines += [t["text"], ""]
    try:
        with C.long_call():
            reply = llm.json_call(C.prompt("fat-paragraphs", targets="\n".join(lines), article=render(marked),
                                           memory=C.sh.memory_block())) or {}
    except Exception as e:      # noqa: BLE001
        return w, {"found": len(fat), "applied": 0, "fixes": [], "error": str(e)[:120]}
    got = {str(f.get("id") or "").strip(): f for f in (reply.get("fixes") or []) if isinstance(f, dict)}
    n = C.deep(w)
    report, applied = [], 0
    for t in sorted(fat, key=lambda x: (x["key"], -x["idx"])):
        f = got.get(t["id"])
        new = str((f or {}).get("prose") or "").strip()
        if not new:
            report.append({"id": t["id"], "applied": False, "why": "no replacement returned"})
            continue
        why = judge_fix(t["text"], new, t["paras_in_section"])
        if why:
            report.append({"id": t["id"], "applied": False, "why": why, "proposed": new})
            continue
        ps = _paras(_block_text(n, t["key"]))
        ps[t["idx"]] = new
        _set_block(n, t["key"], "\n\n".join(ps))
        applied += 1
        report.append({"id": t["id"], "applied": True, "how": str((f or {}).get("how") or "").strip(),
                       "sentences_before": t["sentences"], "paragraphs_after": len(_paras(new))})
    return n, {"found": len(fat), "applied": applied, "left": len(find_fat(n)), "fixes": report}


# ------------------------------------------------------- 5c: the plain-English retry
def _hard_in(text):
    return [x for x in re.findall(r"[A-Za-z][A-Za-z'-]*", str(text or "")) if _syllables(x) >= 4]


def fix_plain(w, rounds=2, say=lambda *a: None):
    report = {"rounds": [], "ease_before": reading_ease(w)}
    for rnd in range(1, rounds + 1):
        now = reading_ease(w)
        if now >= C.READABLE_EASE:
            break
        cands = []
        for key in _block_keys(w):
            t = _block_text(w, key)
            if len(t.split()) < 25:
                continue
            cands.append((_block_score(t), len(_hard_in(t)), key, t))
        cands = [c for c in cands if c[1] >= 2]
        cands.sort(key=lambda c: (c[0], -c[1]))
        picked = cands[:6]
        if not picked:
            break
        say("Plain-English round %d" % rnd, "reading ease %.0f, needs %.0f; rewriting %d blocks" % (now, C.READABLE_EASE, len(picked)))
        marked = C.deep(w)
        for _sc, _n, key, _t in picked:
            _set_block(marked, key, "[[%s]] " % key + _block_text(marked, key))
        lines = []
        for sc, n, key, t in picked:
            hard = sorted(set(x.lower() for x in _hard_in(t)))[:10]
            lines += ["[%s] — scores %.0f. Hard words in it: %s" % (key, sc, ", ".join(hard)), t, ""]
        try:
            with C.long_call():
                reply = llm.json_call(C.prompt("plain-english", ease_now="%.0f" % now, ease_target="%.0f" % C.READABLE_EASE,
                                               targets="\n".join(lines), article=render(marked),
                                               memory=C.sh.memory_block())) or {}
        except Exception as e:      # noqa: BLE001
            report["rounds"].append({"round": rnd, "error": str(e)[:120]})
            break
        got = {str(f.get("id") or "").strip(): f for f in (reply.get("fixes") or []) if isinstance(f, dict)}
        n = C.deep(w)
        applied, log = 0, []
        for sc, _h, key, old in picked:
            new_t = str((got.get(key) or {}).get("prose") or "").strip()
            if not new_t:
                log.append({"id": key, "applied": False, "why": "no replacement returned"})
                continue
            why = ""
            if tags.id_set(new_t) - tags.id_set(old):
                why = "invented a source tag"
            elif _BARE_TAG.search(new_t):
                why = "wrote a bare [c]"
            elif _nums_in(new_t) - _nums_in(old):
                why = "invented a figure"
            elif _urls_in(new_t) != _urls_in(old):
                why = "changed a link"
            elif len(new_t.split()) > len(old.split()) * 1.15:
                why = "grew the block"
            elif _block_score(new_t) <= sc + 3:
                why = "no real gain (%.0f -> %.0f)" % (sc, _block_score(new_t))
            if why:
                log.append({"id": key, "applied": False, "why": why})
                continue
            _set_block(n, key, new_t)
            applied += 1
            log.append({"id": key, "applied": True, "score_before": sc, "score_after": _block_score(new_t)})
        after = reading_ease(n)
        report["rounds"].append({"round": rnd, "blocks": len(picked), "applied": applied,
                                 "ease_before": now, "ease_after": after, "log": log})
        if after > now:
            w = n
        else:
            break
    report["ease_after"] = reading_ease(w)
    return w, report


# ---------------------------------------------------------------- the checks
def _numbers(w):
    t = tags.sub("\n".join(texts(w)), lambda _f: "")
    return {x.rstrip(".,") for x in NUM.findall(t)}


def judge_coverage(after, stakes, ai_overview, say=lambda *a: None):
    """One AI call: which expected topics, and which of Google's own answer, this article covers.
    Coverage is a judgment about meaning, so it goes to the model. None when the call fails."""
    if not (stakes or ai_overview):
        return None
    try:
        with C.long_call():
            reply = llm.json_call(C.prompt("readable-coverage",
                                           table_stakes="\n".join("   - %s" % x for x in stakes) or "   (none recorded)",
                                           ai_overview=str(ai_overview or "(none captured for this article)"),
                                           article=render(after))) or {}
    except Exception as e:      # noqa: BLE001
        say("The coverage check did not answer", type(e).__name__)
        return None
    ts = [r for r in (reply.get("table_stakes") or []) if isinstance(r, dict)]
    ao = [r for r in (reply.get("ai_overview") or []) if isinstance(r, dict)]
    on_topic = reply.get("ai_overview_on_topic")
    off_topic = on_topic is False
    if off_topic:
        ao = []
    if not ts and not ao and not off_topic:
        return None
    return {"table_stakes": ts, "ai_overview": ao, "ai_overview_off_topic": off_topic,
            "ai_overview_subject": str(reply.get("ai_overview_subject") or "").strip()}


def check(before, after, primary, target=None, stakes=None, judged=None):
    """Every earlier step bought something. Each row here protects one of them. Flags only."""
    out = []
    b, a = words(before), words(after)

    def add(name, ok, detail, protects):
        out.append({"check": name, "ok": bool(ok), "detail": detail, "protects": protects})

    def _row(name, rows, key, protects, allow_missing):
        miss = [str(r.get(key) or "") for r in rows if not r.get("covered")]
        add(name, len(miss) <= allow_missing(len(rows)),
            "%d/%d covered" % (len(rows) - len(miss), len(rows)) + (" — missing: %s" % "; ".join(m[:40] for m in miss[:2]) if miss else ""),
            protects)

    if stakes:
        if judged and judged.get("table_stakes"):
            _row("Expected topics survived", judged["table_stakes"], "topic",
                 "a rebuild must not quietly drop the ground readers came for", lambda n: n // 3)
        else:
            add("Expected topics survived", True, "not checked (the coverage call did not answer)",
                "a rebuild must not quietly drop the ground readers came for")
    if judged and judged.get("ai_overview_off_topic"):
        add("Google's own answer covered", True, "skipped — Google's answer for this keyword is a different subject",
            "the AI Overview is what Google already tells searchers this topic is made of")
    elif judged and judged.get("ai_overview"):
        _row("Google's own answer covered", judged["ai_overview"], "element",
             "the AI Overview is what Google already tells searchers this topic is made of", lambda n: n // 3)

    nb, na = _numbers(before), _numbers(after)
    made_up = na - nb
    add("No invented figures", not made_up,
        "none invented (%d unused figure(s) cut)" % len(nb - na) if not made_up else "INVENTED %s" % sorted(made_up)[:6],
        "a figure that was never in the research would be fabricated")
    tb, ta = _tag_map(before), _tag_map(after)
    all_b = set().union(*tb.values()) if tb else set()
    all_a = set().union(*ta.values()) if ta else set()
    invented, dropped = all_a - all_b, all_b - all_a
    add("No invented sources", not invented,
        "none invented (%d left with the text they proved)" % len(dropped) if not invented else "INVENTED %s" % sorted(invented)[:6],
        "a tag that was never in the research would be a fabricated citation")
    bare = len(_BARE_TAG.findall("\n".join(texts(after))))
    add("Source tags kept their numbers", not bare,
        "every tag still carries its id" if not bare else "%d tag(s) reduced to a bare [c]" % bare,
        "a tag stripped of its number is a claim pretending to be sourced")
    if all_b and b:
        d0, d1 = words_per_fact(before), words_per_fact(after)
        add("Facts have room to breathe (%d+ words each)" % C.READABLE_WORDS_PER_FACT,
            d1 >= min(C.READABLE_WORDS_PER_FACT, d0 * 1.4),
            "%.0f -> %.0f words per fact (%d -> %d facts, %d -> %d words)" % (d0, d1, len(all_b), len(all_a), b, a),
            "a fact with no room to be explained is a fact the reader cannot use")
    hb, ha = subheads(before), subheads(after)
    if hb:
        kept_secs = min(len(after.get("sections") or []), len(before.get("sections") or []))
        allowed = max(0, len(hb) - (len(before.get("sections") or []) - kept_secs) * 3)
        add("Sub-headings survived", len(ha) >= min(len(hb), allowed),
            "%d -> %d" % (len(hb), len(ha)) + ("" if len(ha) >= len(hb) else " — %d flattened into prose" % (len(hb) - len(ha))),
            "in a glossary or a ranking the sub-heading is the entry the reader came for")
    ub = {u for _, u in MDLINK.findall("\n".join(texts(before)))}
    ua = {u for _, u in MDLINK.findall("\n".join(texts(after)))}
    add("The one link kept", ub == ua,
        "%d link(s): %s" % (len(ua), ", ".join(sorted(ua))[:80]) if ub == ua else "was %s, now %s" % (sorted(ub), sorted(ua)),
        "the wrapper chose the page the close points at")
    sb, sa = len(before.get("sections") or []), len(after.get("sections") or [])
    trb = len(re.findall(r"^\|", "\n".join(texts(before)), re.M))
    tra = len(re.findall(r"^\|", "\n".join(texts(after)), re.M))
    add("It rebuilt, not just trimmed", sa != sb or tra > trb, "sections %d -> %d, table rows %d -> %d" % (sb, sa, trb, tra),
        "merging, reordering and tabling is where the words come from")
    primary = (primary or "").lower()
    if primary:
        heads = [str(s.get("heading", "")).lower() for s in after.get("sections") or []]
        in_head = sum(1 for h in heads if primary in h)
        first100 = " ".join(plain(after).split()[:100]).lower()
        add("Primary keyword placed", in_head and primary in first100,
            '"%s" — %d heading(s), first 100 words %s' % (primary, in_head, "yes" if primary in first100 else "NO"),
            "the architect placed the keyword in the headings")
    over = [f for f in (after.get("faq") or []) if len(tags.sub(str(f.get("answer") or ""), lambda _x: "").split()) > C.WRAP_FAQ_WORDS]
    add("FAQ answers short", not over, "%d answers, %d over %d words" % (len(after.get("faq") or []), len(over), C.WRAP_FAQ_WORDS),
        "the wrapper caps an answer at what a snippet shows")
    if target:
        floor = target * 0.85 if b > target else 0
        add("Landed in the word band", floor <= a <= target * 1.1,
            "%d -> %d, asked for %d (%+.0f%%)" % (b, a, target, (a - b) / b * 100 if b else 0)
            + (" — %d words UNDER the floor of %.0f" % (target - a, floor) if floor and a < floor else ""),
            "too long loses the reader; too short throws away what the research bought")
    else:
        add("No longer than before", a <= b, "%d -> %d words" % (b, a), "the architect set a length band and the editor cut to it")
    e0, e1 = reading_ease(before), reading_ease(after)
    add("Reading ease %.0f-%.0f" % (C.READABLE_EASE, C.READABLE_EASE_MAX), C.READABLE_EASE <= e1 <= C.READABLE_EASE_MAX,
        "%s -> %s (band %.0f-%.0f)" % (e0, e1, C.READABLE_EASE, C.READABLE_EASE_MAX)
        + (" — ABOVE the band: the prose has gone clipped, not clear" if e1 > C.READABLE_EASE_MAX else ""),
        "readable is a band; too high means fragments, too low means textbook")
    add("Long sentences", len(long_sentences(after)) <= len(long_sentences(before)),
        "%d -> %d over %d words" % (len(long_sentences(before)), len(long_sentences(after)), C.WORDS_PER_SENTENCE),
        "this step should not add any")
    add("Fat paragraphs", len(fat_paragraphs(after)) <= len(fat_paragraphs(before)),
        "%d -> %d over %d sentences" % (len(fat_paragraphs(before)), len(fat_paragraphs(after)), C.SENTENCES_PER_PARAGRAPH),
        "this step should not add any")
    return out


def _examples():
    ex = C.sh.brand_file("writing-examples.md").strip()
    return ex[:C.READABLE_EXAMPLES_CHARS] if ex else ("(no published examples on file for this brand; hold to the three moves "
                                                        "above: the plain thing first, then the concrete case, then what it means)")


def run(w, plan, st, say=lambda *a: None):
    brand = C.company()
    ks = st.get("keywords") or {}
    prim = ks.get("primary") or "(none)"
    var = ", ".join(ks.get("variations") or []) or "(none)"
    h2 = ", ".join(ks.get("section_keywords") or []) or "(none)"
    now = words(w)
    target = min(C.READABLE_CEILING, now)
    stakes = plan.get("table_stakes") or []
    ai_overview = plan.get("ai_overview") or ""
    archetype = plan.get("format_archetype") or ""
    rule = format_rule(archetype)
    facts = len(fact_ids(w))
    keep = max(6, round(target / max(C.READABLE_WORDS_PER_FACT, 1)))
    say("Rewriting the article to be read", "%d facts in %d words; aiming for about %d words carrying about %d facts"
        % (facts, now, target, min(keep, facts) if facts else keep))
    prompt = C.prompt("readable", brand=brand["brand"], facts_now="{:,}".format(facts), words_now="{:,}".format(now),
                      words_per_fact_now="%.0f" % words_per_fact(w), target_words="{:,}".format(target),
                      facts_keep="{:,}".format(keep), facts_drop="{:,}".format(max(0, facts - keep)),
                      archetype=archetype or "general article", format_rule=rule,
                      table_stakes="\n".join("   - %s" % x for x in stakes) or "   (none recorded)",
                      primary_keyword=prim, variations=var, heading_keywords=h2,
                      ease_now="%.0f" % reading_ease(w), ease_target="%.0f" % C.READABLE_EASE,
                      hard_words=render_hard_words(w), long_sentences=render_long_sentences(w),
                      writing_examples=_examples(), article=render(w), memory=C.sh.memory_block())
    with C.long_call():
        reply = llm.json_call(prompt) or {}
    if not reply.get("sections") and not reply.get("intro"):
        say("The rewrite came back empty", "keeping the text as it is")
        return {"article": w, "report": {"applied": False, "checks": []}}
    new = apply_reply(w, reply)
    new, fat_report = fix_fat(new, say)
    new, plain_report = fix_plain(new, say=say)
    judged = judge_coverage(new, stakes, ai_overview, say)
    checks = check(w, new, ks.get("primary") or "", target, stakes, judged)
    failed = [c for c in checks if not c["ok"]]
    say("Readable rewrite done", "%d -> %d words (asked for %d); reading ease %s -> %s; %d of %d checks clean"
        % (words(w), words(new), target, reading_ease(w), reading_ease(new), len(checks) - len(failed), len(checks)))
    return {"article": new, "report": {"applied": True, "checks": checks, "archetype": archetype,
                                       "format_rule_used": bool(rule), "fat_paragraphs": fat_report,
                                       "plain_english": plain_report, "coverage": judged,
                                       "h1_before": w.get("h1"), "h1_after": new.get("h1"),
                                       "words_before": words(w), "words_after": words(new),
                                       "ease_before": reading_ease(w), "ease_after": reading_ease(new)}}
