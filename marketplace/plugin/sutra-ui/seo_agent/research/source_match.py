"""source_match.py — recover the real source URL for a numeric card whose sentence lost its [n] marker.

Ported from `13-research-structure/scripts/source_match.py`, which the original calls from two places
(harvest_storm.py, to fix it at the origin, and reattach_sources.py, to patch bundles already built).

The hole it fills. The dossier is written from retrieved passages and cites them by number. A model
does not always carry the [n] through into the sentence it writes, and when the sentence carries a
figure the harvest is left with a number and nowhere it came from. Sutra's harvest used to hand that
card the WHOLE SECTION's source list, which reads as an attribution and is not one: the number gets
credited to pages that never said it. That is fabrication in a shipped article, so it is treated as
one here.

The method is offline, free and honest. A URL is attached ONLY when a specific retrieved passage
genuinely contains the fact — a shared lifted phrase that INCLUDES the number. Nothing is fetched,
nothing is asked of a model, and a card that cannot be matched is stamped `needs_source` rather than
given a source it did not earn.

Public API (the original's, name for name):
    build_index(pages)                        -> index: [(url, passage, shingles)]
    has_number(text)                          -> bool
    recover(verbatim, index, min_overlap=3)   -> (url, evidence_phrase) or (None, None)
"""
import re

MIN_OVERLAP = 3        # 3-grams a card must share with a passage before signal A will believe it
WINDOW_PAD = 16        # chars either side of a figure that make up a number-window (signal B)


# --- normalization: make "$4,683" == "$4 683", "impact: 40%" == "Impact 40%" -----------------

def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"(\d),(\d)", r"\1\2", s)       # 4,683 -> 4683  (kill thousands separators)
    s = re.sub(r"[^a-z0-9%]+", " ", s)          # punctuation -> space, keep digits + %
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s):
    return _norm(s).split()


def _shingles(s, n=3):
    w = _tokens(s)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


_NUMTOK = re.compile(r"\d")


def _is_num_token(tok):
    # one-digit noise ("1 of 3", "step 2") is not a statistic, so it never counts as the number
    return bool(_NUMTOK.search(tok)) and len(re.sub(r"[^\d]", "", tok)) >= 2


_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?%?")


def has_number(text):
    """True when the text carries a real figure (2+ digits), the same test the write phase uses."""
    return any(len(re.sub(r"[^\d]", "", m)) >= 2 for m in _NUM.findall(text or ""))


def build_index(pages):
    """Every passage the research conversation actually retrieved, as (url, passage, shingles).

    The original read STORM's `url_to_info.json`; this package keeps the same material on the
    curated pages (`web.passages` cut them), so the index is built from those instead. A page with
    no passages contributes nothing rather than an empty entry that would match everything.
    """
    index = []
    for p in (pages or []):
        if not isinstance(p, dict):
            continue
        url = p.get("url")
        if not url:
            continue
        for s in (p.get("passages") or []):
            if isinstance(s, str) and s.strip():
                index.append((url, s, _shingles(s)))
    return index


def _num_windows(cn, pad=WINDOW_PAD):
    """~32-char windows of the normalized card centred on each number — the figure plus its context.
    Kept only if the window carries >= 2 alphabetic tokens (so it is a real phrase, not a bare figure)."""
    for m in re.finditer(r"\d[\d]*%?", cn):
        w = cn[max(0, m.start() - pad):min(len(cn), m.end() + pad)].strip()
        if len([t for t in w.split() if t.isalpha()]) >= 2:
            yield w


def recover(verbatim, index, min_overlap=MIN_OVERLAP):
    """Attach a source ONLY when a specific passage proves the fact. Two honest signals, either suffices:

      (A) the card shares >= min_overlap 3-grams with a passage, and at least one shared 3-gram carries
          the number (handles long, paraphrased-but-lifted sentences);
      (B) a number-centred window of the card (the figure plus its surrounding words) appears verbatim
          inside a passage (handles short table/list rows like "| Non-executive | ~$4,683 |" that cannot
          reach three 3-grams).

    Returns (url, evidence_phrase) or (None, None).
    """
    cs = _shingles(verbatim)
    if not cs or not index:
        return None, None

    # --- signal A: 3-gram overlap that includes the number ---
    best_url, best_ov, best_shared = None, 0, None
    for url, _passage, ss in index:
        shared = cs & ss
        if len(shared) > best_ov:
            best_url, best_ov, best_shared = url, len(shared), shared
    if best_ov >= min_overlap and any(any(_is_num_token(t) for t in g) for g in best_shared):
        phrase = " ".join(sorted(best_shared, key=lambda g: -sum(_is_num_token(t) for t in g))[0])
        return best_url, phrase

    # --- signal B: a number-window appears verbatim in a passage (for short high-value rows) ---
    cn = _norm(verbatim)
    windows = list(_num_windows(cn))
    for url, passage, _ss in index:
        pn = _norm(passage)
        for w in windows:
            if w in pn:
                return url, w
    return None, None
