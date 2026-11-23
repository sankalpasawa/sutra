"""Small text helpers of the chat agent and the chart rules (orchestrator 2, 5.2, 5.3, 5.4).

    slugify        a name as a lowercase hyphenated word string
    tokens         the words that carry meaning: lowercase `[a-z0-9]{3,}` minus a fixed stop list
    name_key       tokens with a trailing plural `s` stripped (two names are "the same" when their keys are equal)
    jaccard        overlap of two token sets, 0.0 to 1.0
    parse_yes_no   True / False for a message that is only a yes or a no, else None
    one_line_title the owner's request cut to a title: one line, at most N characters, at a word boundary

There is no `plain_check`: nothing a model writes is shown to the owner (S4-fnodes-12).
"""
import re
from collections.abc import Collection, Iterable

__all__ = ["STOP_WORDS", "YES_WORDS", "NO_WORDS", "slugify", "tokens", "stem", "name_key", "jaccard", "parse_yes_no", "one_line_title"]

STOP_WORDS = frozenset(
    "a about all also an and any are as at be been but by can could did do does for from get had has have her his how i if in "
    "into is it its just make me more my new not now of off on one only or our out please she should so some than that the "
    "their them then there these they this those to too up us use want was we were what when which who will with would you "
    "your need needs like".split()
)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
YES_WORDS = frozenset({"yes", "y", "ok", "okay", "sure", "go ahead", "do it", "approve"})
NO_WORDS = frozenset({"no", "n", "nope", "cancel", "leave it", "reject"})


def slugify(text: str, *, max_len: int = 40) -> str:
    """Lowercase letters and digits joined by single hyphens: `"Coffee Shop & Café!"` -> `coffee-shop-caf`. Non-ASCII letters
    are dropped, not transliterated. Cut to `max_len` without a trailing hyphen; may be empty (the caller picks a fallback)."""
    if not isinstance(text, str):
        raise TypeError("slugify needs text")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def tokens(text: str) -> frozenset[str]:
    """The distinct meaningful words of `text`: lowercase `[a-z0-9]{3,}` that are not stop words."""
    if not isinstance(text, str):
        raise TypeError("tokens needs text")
    return frozenset(word for word in _TOKEN_RE.findall(text.lower()) if word not in STOP_WORDS)


def stem(word: str) -> str:
    """Strip one trailing plural `s` (`sales` and `sale` match): only from words longer than 3 letters, never `ss`."""
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def name_key(text: str) -> frozenset[str]:
    """The comparison key of a team name: its tokens with plural `s` stripped."""
    return frozenset(stem(word) for word in tokens(text))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """|A and B| / |A or B|; 0.0 when both are empty (nothing is shared, so nothing is similar)."""
    left = a if isinstance(a, Collection) and not isinstance(a, str) else list(a)
    right = b if isinstance(b, Collection) and not isinstance(b, str) else list(b)
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def parse_yes_no(text: str) -> bool | None:
    """True for a message that is only a yes (yes, y, ok, okay, sure, go ahead, do it, approve), False for only a no (no, n,
    nope, cancel, leave it, reject), else None. Case, surrounding spaces and a trailing `.` `!` or `,` do not matter;
    "yes please" is None because it is not the whole message."""
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.lower().strip().rstrip(".!,").split())
    if cleaned in YES_WORDS:
        return True
    if cleaned in NO_WORDS:
        return False
    return None


_CONNECTOR = re.compile(r"\s+(?:and|then|after|before|or|to|of|in|on|for|with|the|a|an)$", re.I)


def _first_sentence(line: str) -> str:
    """The text up to the first sentence end: a full stop, `!` or `?` followed by a space, unless the word before it holds another dot (e.g., i.e., a.m., v1.2): that is an abbreviation, not an end."""
    for match in re.finditer(r"[.!?](?=\s)", line):
        word = re.search(r"(\S+)$", line[: match.end()]).group(1)
        if "." in word[:-1] and match.group() == ".":
            continue
        return line[: match.start()]
    return line


def _whole_graphemes(line: str, cut: str) -> str:
    """`cut` (the start of `line`) without a half of a glyph at its end: a joiner, a variation selector, a combining mark or a skin tone that belongs to the character before the cut is not left behind, and a
    character whose rest was cut off goes too."""
    import unicodedata

    def joins(ch: str) -> bool:
        return unicodedata.category(ch) in ("Mn", "Me", "Cf") or "\U0001F3FB" <= ch <= "\U0001F3FF"
    while cut and (cut[-1] == "\u200d" or (len(cut) < len(line) and joins(line[len(cut)]))):
        cut = cut[:-1]
    return cut


def project_title(text: str, limit: int = 60) -> str:
    """A short title for a project from the owner's request (D404, r-7): the first sentence when it fits, else the text cut at a word boundary with an ellipsis. Never cut inside a word or a glyph, never ends on
    a dangling "and", "then", "after" and the like (however many), never empty for a request that has words (it falls back to the first characters), never split at "e.g." or "i.e.". The whole request is on
    the project page."""
    line = " ".join(str(text).split())
    if not line:
        return ""
    first = _first_sentence(line).rstrip(".!?:; ")
    if 0 < len(first) <= limit:
        return first
    if len(line) <= limit:
        return line.rstrip(".!?:; ") or line
    cut = line[: limit + 1]
    cut = cut[: cut.rfind(" ")] if " " in cut else _whole_graphemes(line, line[:limit])
    cut = re.sub(r"[\s,;:\-]+$", "", cut)
    while True:
        stripped = _CONNECTOR.sub("", cut)
        if stripped == cut:
            break
        cut = re.sub(r"[\s,;:\-]+$", "", stripped)
    return (cut or _whole_graphemes(line, line[:limit]).strip() or line[:limit]) + "\u2026"


def one_line_title(text: str, limit: int = 60) -> str:
    """The text on one line (runs of whitespace become one space), cut to `limit` characters at a word boundary. A first word
    longer than `limit` is cut hard. No ellipsis is added: this is a title, not an excerpt."""
    line = " ".join(str(text).split())
    if len(line) <= limit:
        return line
    cut = line[:limit]
    if line[limit] != " ":                       # the cut fell inside a word: back up to the space before it
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
    return cut.rstrip()
