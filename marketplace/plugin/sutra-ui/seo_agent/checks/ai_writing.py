"""ai_writing.py — the machine-writing tells, found locally in milliseconds.

This runs on every draft and again after every targeted edit, so it cannot be a model call.
That would cost credits and seconds each time, and a check people wait for is a check people
switch off. Every rule here is a regex or a count over the text, so a 2,000 word draft is
scanned faster than the screen can repaint.

It only ever warns, and that is deliberate rather than timid. These patterns are more common
in machine text, but people write them too: under deadline, in an unfamiliar genre, in a
second language. The source rules say so themselves, "signals, not proof". A gate that
blocks a draft over the word "comprehensive" is a gate that gets ignored, and then the real
findings go with it.

Nothing here reads from disk. The voice profile arrives as an argument, which keeps the
whole module pure and testable with a string and a dict.
"""
import re
import statistics

from . import item, result

# ---- the word list ------------------------------------------------------------------------
# Tier 1 from the writing rules: words that show up several times more often in machine text
# than human text. The value is the replacement to offer, because a finding with no suggested
# fix just makes the writer stare at their own sentence.

TIER1 = {
    "delve": "explore, dig into, look at",
    "leverage": "use",
    "robust": "strong, reliable, solid",
    "seamless": "smooth, easy, without friction",
    "landscape": "field, space, industry",
    "realm": "area, field, domain",
    "testament": "shows, proves, demonstrates",
    "underscore": "highlights, shows",
    "tapestry": "describe the actual complexity",
    "navigate": "work through, handle, deal with",
    "crucial": "important, key, necessary",
    "vital": "important, necessary",
    "moreover": "and, also, or cut it",
    "furthermore": "and, also, or cut it",
    "notably": "cut it and state the fact",
    "arguably": "cut it, or say who argues it",
    "embark": "start, begin",
    "unlock": "release, enable, or say what it opens",
    "elevate": "improve, raise, strengthen",
    "harness": "use, take advantage of",
    "foster": "encourage, support, build",
    "myriad": "many, or give a number",
    "plethora": "many, a lot of, or give a number",
    "pivotal": "important, key, critical",
    "paramount": "most important, top priority",
    "intricate": "complex, detailed",
    "nuanced": "specific, subtle, or name the actual nuance",
    "comprehensive": "thorough, complete, full",
    "holistic": "complete, full, whole",
}

# Two of those words have honest literal senses. Flagging "navigate to the settings page" or
# "landscape orientation" is a false alarm that costs more trust than the catch is worth, so
# each carries the company it keeps when it is being literal.
LITERAL_CONTEXT = {
    "landscape": {"orientation", "mode", "garden", "gardening", "architect", "architecture",
                  "photography", "photo", "painting", "lawn", "terrain", "rotate", "portrait"},
    "navigate": {"menu", "navigation", "nav", "sidebar", "url", "page", "pages", "site",
                 "website", "map", "browser", "dashboard", "breadcrumb", "tab", "cursor",
                 "keyboard", "arrow", "click", "scroll", "screen", "app", "ship", "boat"},
}

# A particle right after the word belongs in the quote: "delve into" reads as the tell,
# "delve" on its own reads as an accusation about one word.
PARTICLES = r"(?:\s+(?:into|in|on|through|with|up|out|down|from|to|toward|towards|across))?"


def _variants(word):
    """Inflections, generated rather than listed. The rules say to match morphological
    variants, and hand-listing them for thirty words is where a list goes stale."""
    v = {word, word + "s", word + "es", word + "ed", word + "ing", word + "ly", word + "d"}
    if word.endswith("e"):
        stem = word[:-1]
        v |= {stem + "ing", stem + "ed", stem + "es", stem + "ely"}
    if word.endswith("y"):
        v |= {word[:-1] + "ies", word[:-1] + "ied", word[:-1] + "ily"}
    return v


def _word_re(word):
    alts = sorted(_variants(word), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(a) for a in alts) + r")" + PARTICLES + r"\b",
                      re.IGNORECASE)


_TIER1_RES = {w: _word_re(w) for w in TIER1}

# ---- the phrase patterns -------------------------------------------------------------------
# (kind, compiled regex, suggested fix). One tuple per tell, so adding a rule is one line.

APOS = r"['’]"

PHRASES = [
    ("opener", re.compile(r"\bin today" + APOS + r"?s\s+(?:world|landscape|market|economy|"
                          r"digital\s+\w+|fast[- ]paced\s+\w+|business\s+\w+)", re.I),
     "Cut the windup and open with the point."),
    ("opener", re.compile(r"\bin the ever[- ](?:evolving|changing|growing|expanding)\b", re.I),
     "Cut it, or say what actually changed and when."),
    ("opener", re.compile(r"\bin an era (?:where|of|when)\b", re.I),
     "Cut it. Name the specific change instead of the era."),
    ("opener", re.compile(r"\bit" + APOS + r"?s important to note\b|\bit is important to note\b", re.I),
     "Cut the phrase and state the fact."),
    ("opener", re.compile(r"\bit" + APOS + r"?s worth noting\b|\bit is worth noting\b", re.I),
     "Cut the phrase and state the fact."),
    ("hedge_stack", re.compile(r"\b(?:may|might|could|can|will|would|should)\s+"
                               r"(?:potentially|possibly|eventually|ultimately|perhaps|"
                               r"conceivably|arguably)\b", re.I),
     "Pick one. Either the modal or the adverb, never both."),
    ("not_just", re.compile(r"\bnot just\b[^.!?\n]{2,90}?,?\s+but\b", re.I),
     "State the positive directly. Drop the thing it is not."),
]

# "isn't just about X. It's about Y." needs two halves near each other, which is clearer as a
# lookahead in code than as one unreadable regex.
_NOT_ABOUT_OPEN = re.compile(r"\b(?:is\s*n" + APOS + r"?t|is not|are\s*n" + APOS + r"?t|are not|"
                             r"was\s*n" + APOS + r"?t|were\s*n" + APOS + r"?t)\s+just\s+about\b", re.I)
_NOT_ABOUT_CLOSE = re.compile(r"\b(?:it" + APOS + r"?s|this is|that" + APOS + r"?s|they" + APOS +
                              r"?re|it is)\s+about\b", re.I)
_NOT_ABOUT_WINDOW = 200

# An adjective triad: "fast, cheap, and reliable". Single words on all three arms keeps this
# off genuine lists of things, which are usually longer phrases.
TRIAD_RE = re.compile(r"\b([a-z]{3,}),\s+([a-z]{3,}),\s+and\s+([a-z]{3,})\b", re.I)
TRIAD_LIMIT = 2                      # more than twice in one piece is the tell, not once

# The em dash and its typed substitute. Three hyphens is a markdown rule, not punctuation,
# so it is excluded rather than reported every time a table or a front matter block appears.
EM_DASH_RE = re.compile(r"—|–|(?<!-)--(?!-)")

# Rhythm. Only measured on a passage long enough for the number to mean anything: a five
# sentence intro can be uniform by accident, a forty sentence article cannot.
MIN_SENTENCES_FOR_RHYTHM = 12
MIN_WORDS_FOR_RHYTHM = 200
UNIFORM_STDEV = 4.0

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+")


# ---- preparing the text ----------------------------------------------------------------------

def _strip_noise(text):
    """Remove what is not prose before anything is measured.

    Code samples, link targets and image tags are not writing. A slug like /unlock-growth or a
    config key named `robust_retry` is not a word choice anybody made, and flagging it is how a
    detector earns a reputation for crying wolf.
    """
    t = text or ""
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"~~~.*?~~~", " ", t, flags=re.S)
    t = re.sub(r"^(?: {4}|\t).*$", " ", t, flags=re.M)
    t = re.sub(r"`[^`\n]*`", " ", t)
    t = re.sub(r"!\[[^\]\n]*\]\([^)\n]*\)", " ", t)
    t = re.sub(r"\[([^\]\n]*)\]\([^)\n]*\)", r"\1", t)     # keep the anchor, drop the URL
    t = re.sub(r"<https?://[^>\s]+>", " ", t)
    t = re.sub(r"(?<!\S)https?://\S+", " ", t)
    return t


def units(text, unit_label="paragraph"):
    """Split into the addressable units a finding points at.

    Paragraphs for a draft, sections for a blueprint. Numbering is 1-based because the
    finding is read by a person looking at a screen, not by an array index.
    """
    cleaned = _strip_noise(text)
    out = []
    for i, chunk in enumerate(re.split(r"\n\s*\n", cleaned)):
        body = chunk.strip()
        if body:
            out.append(("%s %d" % (unit_label, len(out) + 1), body))
    return out


def sentences(text):
    parts = [s.strip() for s in SENTENCE_SPLIT.split(_strip_noise(text))]
    return [s for s in parts if len(s.split()) >= 2 and not s.lstrip().startswith("#")]


def _quote(text, start, end, pad=0):
    """Quote the offending span, never cutting a word in half. A finding a writer cannot
    search for in their own draft is a finding they cannot act on."""
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    while hi < len(text) and text[hi].isalnum():
        hi += 1
    while lo > 0 and text[lo - 1].isalnum():
        lo -= 1
    span = re.sub(r"\s+", " ", text[lo:hi].strip())
    if len(span) > 70:
        span = span[:67].rstrip() + "..."
    return '"%s"' % span


def _is_literal(word, unit_text):
    """A figurative word gets a pass when its literal companions are in the same paragraph."""
    companions = LITERAL_CONTEXT.get(word)
    if not companions:
        return False
    present = set(re.findall(r"[a-z]+", unit_text.lower()))
    return bool(present & companions)


# ---- the scan ---------------------------------------------------------------------------------

def _banned_words(voice=None):
    """Tier 1 plus whatever this company has said it never says.

    brand_voice.json is written by learn_voice from the site's own pages, so its avoid list is
    the company's real vocabulary rule rather than a generic one. Their words win: a company
    that has banned a word we never listed still gets it flagged.
    """
    banned = dict(TIER1)
    for word in (voice or {}).get("avoid") or []:
        w = str(word).strip().lower()
        if w and w not in banned:
            banned[w] = "a word this company does not use, pick a plainer one"
    return banned


def _findings(text, voice=None, unit_label="paragraph"):
    """Every finding, each carrying the rule that produced it. Internal, because the public
    shape is fixed at three keys."""
    found = []
    banned = _banned_words(voice)
    word_res = dict(_TIER1_RES)
    for word in banned:
        if word not in word_res:
            word_res[word] = _word_re(word)

    unit_list = units(text, unit_label)

    for where, body in unit_list:
        for word, fix in banned.items():
            if _is_literal(word, body):
                continue
            seen = set()
            for m in word_res[word].finditer(body):
                quoted = _quote(body, m.start(), m.end())
                if quoted.lower() in seen:
                    continue
                seen.add(quoted.lower())
                found.append({"kind": "banned_word", "where": where, "what": quoted, "fix": fix})

        for m in EM_DASH_RE.finditer(body):
            found.append({"kind": "em_dash", "where": where,
                          "what": _quote(body, m.start(), m.end(), pad=22),
                          "fix": "Use a comma, a colon or a full stop."})

        for kind, pattern, fix in PHRASES:
            for m in pattern.finditer(body):
                found.append({"kind": kind, "where": where,
                              "what": _quote(body, m.start(), m.end()), "fix": fix})

        for m in _NOT_ABOUT_OPEN.finditer(body):
            tail = body[m.end():m.end() + _NOT_ABOUT_WINDOW]
            if _NOT_ABOUT_CLOSE.search(tail):
                found.append({"kind": "isnt_just_about", "where": where,
                              "what": _quote(body, m.start(), m.end() + 40),
                              "fix": "Say what it is. Drop the half about what it is not."})

    # Rule of three is a whole-piece count. One triad is a sentence, three is a habit, which is
    # why this is measured across the piece rather than flagged wherever it appears.
    triads = []
    for where, body in unit_list:
        for m in TRIAD_RE.finditer(body):
            triads.append((where, _quote(body, m.start(), m.end())))
    if len(triads) > TRIAD_LIMIT:
        found.append({
            "kind": "rule_of_three",
            "where": "whole piece",
            "what": "%d rule-of-three lists: %s" % (len(triads), ", ".join(t[1] for t in triads[:4])),
            "fix": "Vary the groupings. Use two items, four, or a full sentence.",
        })

    sents = sentences(text)
    lengths = [len(s.split()) for s in sents]
    total_words = sum(lengths)
    if len(sents) >= MIN_SENTENCES_FOR_RHYTHM and total_words >= MIN_WORDS_FOR_RHYTHM:
        spread = statistics.pstdev(lengths)
        if spread < UNIFORM_STDEV:
            found.append({
                "kind": "uniform_rhythm",
                "where": "whole piece",
                "what": "%d sentences averaging %.0f words, spread of only %.1f"
                        % (len(sents), statistics.mean(lengths), spread),
                "fix": "Put a short sentence next to a long one. Fragments are fine.",
            })

    return found


def scan(text, voice=None, unit_label="paragraph"):
    """Public finding list: where, what, fix. Nothing else, so the screen can render it raw."""
    return [item(f["where"], f["what"], f["fix"]) for f in _findings(text, voice, unit_label)]


def check(text, voice=None, unit_label="paragraph"):
    """The check result. Never fail, by design. See the module docstring for why."""
    raw = _findings(text, voice, unit_label)
    if not raw:
        return result("ai_writing", "pass", "No AI-writing patterns found.", [])
    counts = {}
    for f in raw:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    summary = ", ".join("%s x%d" % (k.replace("_", " "), v)
                        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    detail = "%d AI-writing signals: %s. Signals, not proof, so this never blocks." % (
        len(raw), summary)
    return result("ai_writing", "warn", detail,
                  [item(f["where"], f["what"], f["fix"]) for f in raw])
