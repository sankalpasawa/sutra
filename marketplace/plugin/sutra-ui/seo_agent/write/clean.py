"""clean.py — Writer step 9: CLEAN. The mechanical scrub. Pure code, ZERO judgment, no AI, no cost.

CODE touches characters and spacing, the AI touches meaning. This step NEVER rewrites a word.
  1. INVISIBLES  — drop every Unicode format/control character; turn exotic spaces into a normal space.
  2. DASHES      — em AND en dash. A numeric range ("60-90 minutes") becomes "to", never a comma.
  3. WHITESPACE  — runs of spaces mid-line, spaces before punctuation, trailing spaces, 3+ blank lines.
  4. IDEMPOTENT  — running twice changes nothing. Asserted in code.
Curly quotes are LEFT ALONE: they are normal in finished prose. Urls, markdown links and [c] tags are
protected so no rule can touch their insides.
"""
import re
import unicodedata

from . import _common as C

_SPACES = dict.fromkeys(
    [0x00A0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
     0x2008, 0x2009, 0x200A, 0x202F, 0x205F, 0x3000], " ")
_KEEP_CONTROL = {"\n", "\t"}
_LOOKALIKE = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2212: "-", 0x2044: "/"}

_MDLINK = re.compile(r"\[([^\]]*)\]\((\S+?)\)")
_TAG = re.compile(r"\[\s*c\s*\d+(?:\s*[-,]\s*c?\s*\d+)*\s*\]", re.I)
_URL = re.compile(r"https?://\S+")


def _protect(text):
    box = []

    def keep(m):
        box.append(m.group(0))
        return "\x00%d\x00" % (len(box) - 1)

    for pat in (_MDLINK, _URL, _TAG):
        text = pat.sub(keep, text)
    return text, box


def _restore(text, box):
    for i, original in enumerate(box):
        text = text.replace("\x00%d\x00" % i, original)
    return text


def scrub(text, tally=None):
    """The whole scrub for one string. `tally` (a dict) accumulates counts per rule."""
    if not text:
        return text
    t, box = _protect(text)

    def bump(rule, n=1):
        if tally is not None and n:
            tally[rule] = tally.get(rule, 0) + n

    out = []
    for ch in t:
        if ord(ch) in _SPACES:
            bump("invisible space U+%04X -> normal space" % ord(ch))
            out.append(" ")
            continue
        if ord(ch) in _LOOKALIKE:
            bump("lookalike U+%04X -> '%s'" % (ord(ch), _LOOKALIKE[ord(ch)]))
            out.append(_LOOKALIKE[ord(ch)])
            continue
        if ch not in _KEEP_CONTROL and ch != "\x00" and unicodedata.category(ch) in ("Cf", "Cc", "Co", "Cs"):
            bump("invisible U+%04X removed" % ord(ch))
            continue
        out.append(ch)
    t = "".join(out)

    t, n = re.subn(r"(?<=\d)\s*[–—]\s*(?=\d)", " to ", t)
    bump("dash in a number range -> 'to'", n)
    t, n = re.subn(r"\s*—\s*", ", ", t)
    bump("em dash -> comma", n)
    t, n = re.subn(r"\s*–\s*", "-", t)
    bump("en dash -> hyphen", n)

    t, n = re.subn(r"(?<=\S)[ \t]{2,}(?=\S)", " ", t)
    bump("repeated spaces collapsed", n)
    t, n = re.subn(r"[ \t]+([.,;:!?])(?!\d)", r"\1", t)
    bump("space before punctuation removed", n)
    t, n = re.subn(r"(?<=\d)[ \t]+(?=%)", "", t)
    bump("space before % removed", n)
    t, n = re.subn(r"[ \t]+$", "", t, flags=re.M)
    bump("trailing space removed", n)
    t, n = re.subn(r"\n{3,}", "\n\n", t)
    bump("blank lines capped at 2", n)
    t, n = re.subn(r",\s*,", ",", t)
    bump("doubled comma fixed", n)
    return _restore(t.strip("\n") if text.strip("\n") != text else t, box)


def clean_article(w, tally_by_field):
    out = C.deep(w)

    def do(field, value):
        t = tally_by_field.setdefault(field, {})
        return scrub(value, t)

    for k in ("h1", "intro", "quick_answer", "close", "close_heading"):
        if isinstance(out.get(k), str):
            out[k] = do(k, out[k])
    for f in out.get("faq") or []:
        f["question"] = do("faq", f.get("question") or "")
        f["answer"] = do("faq", f.get("answer") or "")
    for s in out.get("sections") or []:
        s["heading"] = do("headings", s.get("heading") or "")
        s["prose"] = do("section: %s" % (s.get("heading") or "?")[:44], s.get("prose") or "")
    return out


def run(w, say=lambda *a: None):
    by_field = {}
    cleaned = clean_article(w, by_field)
    again = {}
    twice = clean_article(cleaned, again)
    assert twice == cleaned, "scrub is not idempotent — a rule is fighting another rule"
    rules_, total = {}, 0
    for field, t in by_field.items():
        for rule, n in t.items():
            rules_[rule] = rules_.get(rule, 0) + n
            total += n
    report = {"total_fixes": total, "by_rule": dict(sorted(rules_.items(), key=lambda kv: -kv[1])),
              "by_field": {f: dict(sorted(t.items(), key=lambda kv: -kv[1])) for f, t in sorted(by_field.items()) if t}}
    say("Scrubbed stray characters and spacing", "%d mechanical fixes" % total)
    return {"article": cleaned, "report": report}
