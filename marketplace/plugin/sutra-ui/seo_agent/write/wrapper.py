"""wrapper.py — Writer step 3: WRAPPER. Write what sits around the finished article.

Reads:  the blended sections, the plan (the researched PAA questions), the structure (the H1, the spine,
        the keywords), the brand's features.md and cta-pages.md, and the three voice files.
Writes: h1, intro (PAS), quick_answer, faq, dropped_questions, close, close_heading, cta_link, and the
        touch-ups already APPLIED to the sections, so the next step reads one finished article.

The intro, the close and the touch-ups are SOURCELESS: they see prose, never cards, so CODE audits every
[c<id>] tag in them and strips any that never existed in the body. A malformed reply leaves the article
untouched and is reported.

THE CLOSE'S LINK AND HEADING ARE CHECKED IN CODE, and re-asked once: exactly one link, on the CTA page
list, declared as cta_link; a heading that is not filler, not a repeat, under 60 characters.

THE FAQ IS MEASURED, NEVER EDITED (_faq_measure): the FAQ is deliberately allowed to answer past the
article, so an outside figure is expected rather than a fault, and a long answer is something to see.
"""
import re

from .. import llm
from . import _common as C
from . import tags

_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_CTA_URL = re.compile(r"^- Page:\s*(\S+)", re.M)
_ANY_URL = re.compile(r"https?://[^\s)\]>\"']+")
_BANNED_CLOSE = ("conclusion", "final thought", "wrapping up", "in summary",
                 "key takeaway", "bottom line", "closing thought", "summary")


def features():
    f = C.sh.brand_file("features.md").strip()
    return f[:C.WRAP_FEATURES_CHARS] if f else "(no features file on record)"


def cta_pages():
    """(the text the writer reads, the set of urls code checks against). Built from brand/cta-pages.md."""
    text = C.sh.brand_file("cta-pages.md").strip()
    if not text:
        return "(no CTA page list on record — do not link the close)", set()
    urls = set(_CTA_URL.findall(text)) or set(u.rstrip(".,") for u in _ANY_URL.findall(text))
    return text[:C.WRAP_CTA_CHARS], urls


def close_heading_check(heading, section_headings):
    h = (heading or "").strip()
    if not h:
        return ['The close has no heading. Return one as "close_heading".']
    bad, low = [], h.lower()
    if any(b in low for b in _BANNED_CLOSE):
        bad.append('"%s" is a filler heading — it says the article is over, not what it is about. '
                   "Name what the reader should do next instead." % h)
    if low in {s.lower().strip() for s in section_headings}:
        bad.append('"%s" repeats a heading already in the article.' % h)
    if len(h) > 60:
        bad.append('"%s" is %d characters. Keep it under 60.' % (h, len(h)))
    return bad


def cta_check(close, declared, allowed):
    """Every way the close's link can be wrong, named in words the retry can act on."""
    found = re.findall(r"\[[^\]\[]+\]\((https?://[^)\s]+)\)", close)
    if not allowed:
        return []                                   # nothing to link to: not the reply's fault
    if not found:
        return ["The close carries NO link. It must link exactly one capability to its page."]
    bad = []
    if len(found) > 1:
        bad.append("The close carries %d links. It must carry exactly one." % len(found))
    for u in found:
        if u not in allowed:
            bad.append("%s is not on the list of pages a close may link to. Pick one that is." % u)
    if declared and declared not in found:
        bad.append('You declared cta_link "%s" but the close does not contain it.' % declared)
    if not declared:
        bad.append('You did not return "cta_link". Return the url you linked to.')
    return bad


def faq_measure(faq, article_text):
    """MEASURE the FAQ. Never touch it. Two measurements per answer, both visible, neither acted on."""
    known = set(_NUM.findall(article_text))
    for f in faq:
        ans = f.get("answer") or ""
        f["words"] = n = len(ans.split())
        f["over_target"] = n > C.WRAP_FAQ_WORDS
        f["outside_numbers"] = sorted(set(_NUM.findall(ans)) - known)
    return faq


def voice():
    parts = []
    for name in C.WRAP_VOICE_FILES:
        t = C.sh.brand_file(name).strip()
        if t:
            parts.append("### %s\n%s" % (name, t[:C.WRAP_VOICE_CHARS]))
    return "\n\n".join(parts) or "(no brand voice files found)"


def run(bl, plan, st, inputs, ctx, say=lambda *a: None):
    brand = C.company()
    kw = st.get("keywords") or {}
    ks = inputs["group_a"].get("keyword_set") or {}
    primary = kw.get("primary") or ks.get("primary") or plan.get("primary_keyword") or "(none)"
    variations = kw.get("variations") if kw else (ks.get("variations") or [])
    h1 = st.get("h1") or plan.get("h1") or ctx["title"] or "(none)"
    secs = bl["sections"]
    block = "\n\n".join("## %s\n\n%s" % (s["heading"], s["prose"]) for s in secs)
    paa = plan.get("paa_pool") or []
    pages_text, allowed = cta_pages()
    prompt = C.prompt("wrapper", brand=brand["brand"], about=brand["about"], h1=h1,
                      angle=ctx["angle"] or "(none)", spine=st.get("spine") or "(none)",
                      persona=C.persona_short({"persona": plan.get("persona")}, {}),
                      primary=primary, variations=", ".join(variations or []) or "(none)",
                      paa="\n".join("  - %s" % q for q in paa)
                      or "  (none researched for this article, so every question is yours to find)",
                      faq_words=C.WRAP_FAQ_WORDS, faq_words_soft=C.WRAP_FAQ_WORDS + 5,
                      features=features(), cta_pages=pages_text, voice=voice(), sections=block,
                      memory=C.sh.memory_block())
    say("Writing the intro, quick answer, FAQ and close", "one call over the whole article")
    with C.long_call():
        out = llm.json_call(prompt) or {}
    return apply(out, secs, h1, allowed, pages_text, brand, say)


def apply(out, secs, h1, allowed, pages_text, brand, say=lambda *a: None):
    heads = [s.get("heading", "") for s in secs]

    def _close_problems(d):
        return (cta_check(str(d.get("close") or ""), str(d.get("cta_link") or ""), allowed)
                + close_heading_check(str(d.get("close_heading") or ""), heads))

    problems = _close_problems(out)
    if problems:
        say("The close needs another pass", "; ".join(problems)[:160])
        try:
            retry = llm.json_call(C.prompt("wrapper-cta-retry", brand=brand["brand"], close=str(out.get("close") or ""),
                                           heading=str(out.get("close_heading") or "(none returned)"),
                                           headings="\n".join("- %s" % h for h in heads),
                                           problems="\n".join("- %s" % w for w in problems), cta_pages=pages_text,
                                           memory=C.sh.memory_block())) or {}
        except Exception:       # noqa: BLE001
            retry = {}
        if retry.get("close"):
            merged = {"close": retry["close"], "cta_link": retry.get("cta_link") or out.get("cta_link"),
                      "close_heading": retry.get("close_heading") or out.get("close_heading")}
            again = _close_problems(merged)
            if not again:
                out.update(merged)
                problems = []
                say("The close was fixed on the retry", "")
            else:
                problems = again
                say("The close is still wrong after the retry", "; ".join(again)[:160])

    known = set()
    for s in secs:
        known |= tags.id_set(s["prose"])
    stripped = [0]

    def clean(text):
        """Drop any [c] tag that was never in the body: the wrapper has no sources of its own."""
        text = str(text or "")
        bad = tags.id_set(text) - known
        if bad:
            text = tags.drop(text, bad)
            stripped[0] += len(bad)
        return text.strip()

    intro, close, quick = clean(out.get("intro")), clean(out.get("close")), clean(out.get("quick_answer"))
    faq = [{"question": clean(f.get("question")), "answer": clean(f.get("answer")),
            "origin": f.get("origin") or "researched"}
           for f in (out.get("faq") or []) if isinstance(f, dict) and str(f.get("question") or "").strip()
           and str(f.get("answer") or "").strip()]
    dropped = [d for d in (out.get("dropped_questions") or []) if isinstance(d, dict)]
    faq = faq_measure(faq, "\n".join(s["prose"] for s in secs))

    by_head = {s["heading"]: s for s in secs}
    applied, ignored = [], []
    for t in (out.get("touch_ups") or []):
        if not isinstance(t, dict):
            continue
        h, prose = t.get("heading"), clean(t.get("prose"))
        if h in by_head and prose:
            by_head[h]["prose"] = prose
            applied.append({"heading": h, "what": t.get("what"), "why": t.get("why")})
        else:
            ignored.append(h)

    ok = bool(intro) and bool(close)
    if not ok:
        say("The wrapper reply was malformed", "no intro or close came back; the article is unchanged")
    final = {"h1": h1, "intro": intro, "quick_answer": quick, "faq": faq, "dropped_questions": dropped,
             "close": close,
             "close_heading": clean(out.get("close_heading")),
             "cta_link": str(out.get("cta_link") or "") if not problems else "",
             "cta_problems": problems, "sections": secs,
             "touch_ups_applied": applied, "touch_ups_ignored": ignored,
             "invented_tags_stripped": stripped[0], "ok": ok}
    if problems:
        # a close whose link failed the check twice keeps its prose but the link is not trusted: strip it
        final["close"] = re.sub(r"\[([^\]\[]+)\]\((https?://[^)\s]+)\)", r"\1", close)
    qw = len(quick.split())
    say("Wrapper written", "intro %d words, quick answer %d words%s, %d FAQ, close %d words%s"
        % (len(intro.split()), qw, "" if C.QUICK_MIN <= qw <= C.QUICK_MAX else " (outside %d-%d)" % (C.QUICK_MIN, C.QUICK_MAX),
           len(faq), len(close.split()), (" under \"%s\"" % final["close_heading"]) if final.get("close_heading") else ""))
    return final
