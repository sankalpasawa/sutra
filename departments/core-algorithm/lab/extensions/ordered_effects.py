"""Ordered side effects (0.16.0-ordered, matrix row R73): the sanitizer, code OUTSIDE the kernel.

The row: a person's words are scrubbed, written locally and then sent, in that order, and a sanitizer error stops
everything after it. The order needs no code: it is what the methods require (pack 120: the write requires the scrub
and the words, the send requires the write, the scrub and the words). What a pack cannot say is that a step FAILED
while it ran. That takes a step whose effect is real code: the action kind `scrub_text`, declared in its own file,
`kinds/scrub_text.py`, which registers it with the kernel's register. Its handler calls the sanitizer kept here.

  scrub(text)   the sanitizer. It redacts a home path, an e-mail address and a long opaque string (three detectors of
                the deployed scrub library, in its order) and refuses, with SanitizerError, a text it cannot make
                safe: no text at all, or fewer than ten ASCII letters and digits left once the marks are taken out
                (the rule of the deployed feedback script for a message that was only a path or a hash).

Each detector reads a text in time that grows with its length, not with its square: the e-mail detector starts only at
the first character of a run that could be the part before the @ (a look-behind; what it matches is unchanged).

This file registers nothing and touches no State: it is a function over a text."""
from __future__ import annotations
import re

MARKS = (('<HOME>', re.compile(r'/(?:Users|home)/[^/\s]+')),
         ('<EMAIL>', re.compile(r'(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')),
         ('<OPAQUE>', re.compile(r'[A-Za-z0-9+/=_-]{40,}')))
USEFUL = 10   # ASCII letters and digits a text must keep after redaction; below that it says nothing and is refused


class SanitizerError(ValueError):
    """The sanitizer could not make the text safe. Nothing may be written or sent on its account."""


def scrub(text) -> tuple:
    """-> (the clean text, how many redactions). Raises SanitizerError instead of returning a text it cannot vouch for."""
    if type(text) is not str or not text.strip():
        raise SanitizerError('no text to scrub')
    redactions = 0
    for mark, pattern in MARKS:
        text, n = pattern.subn(mark, text)
        redactions += n
    left = sum(ch.isascii() and ch.isalnum() for ch in re.sub(r'<[A-Z]+>', '', text))
    if left < USEFUL:
        raise SanitizerError(f'nothing useful is left after redaction ({left} letters and digits, {USEFUL} needed)')
    return text, redactions
