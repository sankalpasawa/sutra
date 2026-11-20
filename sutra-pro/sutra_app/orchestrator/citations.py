"""Citations of a cited answer (DV-1, flag SUTRA_ASK_V1): which sources an answer names, and which of them code could check.

    parse_marks(answer)              -> [Mark]       the `[path:line-line]` marks of the answer, in order, each once (marks in a fenced code block are not marks)
    check_mark(mark, folder)         -> Source       one mark checked against the owner's folder: label "checked" or "could not find", and why
    check_answer(answer, folder)     -> Report       every mark checked; the counts the card shows

The marks:

    [src/app.py:12-18]                  lines 12 to 18 of src/app.py (the path is relative to the owner's folder)
    [src/app.py:12]                     the one line 12
    [src/app.py:12-18 "exact words"]    the same, and the words must be on those lines

The label belongs to CODE alone. A model writes a mark; it never writes a label, and nothing it writes (a word like "checked", a made-up list of sources)
can change one. "checked" says exactly this: the file is there, it is inside the folder, those lines exist, and, when exact words were given, the words are
on those lines (white space does not matter, case does). It does NOT say the lines support what the answer claims: the card says so in words.

A path is refused (label "could not find", with the reason) when it could reach anything but a plain file inside the folder, whatever the machine, and the first group of rules
looks at the TEXT only, before any file-system call (D351): a backslash, a colon, a leading `//`, `~`, a control character, an absolute path that does not start with the folder as text.
The rest: an absolute path outside the folder, a `..` part, a path starting with `~`, a backslash (a Windows spelling), a drive letter or a colon (`C:x`, `file:stream`),
a part that Windows reads differently (a trailing dot or space, a device name such as `CON` or `NUL`), a control character, or a character a path never needs
(`<>|?*`). Then the path is resolved with the real file system (`realpath`): a link that leads out of the folder is outside, a folder, a device or a pipe is
not a file, and a file that is large, not text or too short for the range is not checked. Nothing is ever written, and no file is opened before those steps.

Pure in the sense that matters here: it reads local files and nothing else (no network, no database, no model, no clock but a deadline), the file contents never leave
this module (only labels and the owner's own quote do), and the same answer and folder give the same report.
"""
from __future__ import annotations

import os
import re
import stat
import time
from dataclasses import dataclass
from typing import Iterable

__all__ = ["Mark", "Source", "Report", "parse_marks", "check_mark", "check_answer", "clean_relative", "spelling_problem", "absolute_parts", "CHECKED", "MISSING", "MAX_MARKS", "MAX_SPAN",
           "MAX_FILE_BYTES", "MAX_QUOTE", "MIN_QUOTE", "MAX_LINE_NUMBER", "BUDGET_S"]

CHECKED = "checked"
MISSING = "could not find"
MAX_MARKS = 30                       # marks checked in one answer; the rest are counted, not checked
MAX_SPAN = 400                       # the most lines one mark may point at: a source is a few lines, not a file
MAX_FILE_BYTES = 4 * 1024 * 1024     # a file larger than this is not read for a check
MAX_QUOTE = 300                      # the longest quote that is checked
MIN_QUOTE = 4                        # a quote shorter than this (after white space is squeezed) proves nothing and is not used
MAX_LINE_NUMBER = 10_000_000
MAX_PATH_CHARS = 300
BUDGET_S = 5.0                       # all the checks of one answer together

# `[`, a path, `:`, a line or a range, optionally a quote in double quotes, `]`. The path may hold a colon (it is refused later, in words, not skipped here).
_MARK = re.compile(r'\[([^\[\]\n"“”]{1,%d}?):(\d{1,9})(?:\s*[-–]\s*(\d{1,9}))?(?:\s+["“]([^"”\n]{1,1000})["”])?\s*\]' % MAX_PATH_CHARS)
_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)")
_DEVICE = re.compile(r"^(con|prn|aux|nul|conin\$|conout\$|com[0-9¹²³]|lpt[0-9¹²³])$", re.IGNORECASE)
_NOT_A_PATH = set('<>|?*')


@dataclass(frozen=True)
class Mark:
    """One mark as the answer wrote it. `end` equals `start` for a single line. `quote` is None when none was given."""
    path: str
    start: int
    end: int
    quote: str | None = None


@dataclass(frozen=True)
class Source:
    """A mark and what code found. `label` is CHECKED or MISSING; `how` says what was checked when it is CHECKED (`lines`: the file and the lines are there,
    `quote`: and the words are on them); `reason` says what was wrong when it is MISSING, in words the owner reads."""
    path: str
    start: int
    end: int
    quote: str | None
    label: str
    how: str
    reason: str


@dataclass(frozen=True)
class Report:
    """`sources` in the order of the answer (at most MAX_MARKS); `checked` and `missing` count them; `more` is how many marks came after the limit."""
    sources: tuple[Source, ...]
    checked: int
    missing: int
    more: int


# ---- reading the marks ------------------------------------------------------------------------------------------------------------

def _outside_fences(text: str) -> str:
    """The answer without its fenced code blocks (an example in code, such as `a[1:2]`, is not a citation). An unclosed fence runs to the end."""
    kept: list[str] = []
    fence = ""
    for line in text.splitlines():
        found = _FENCE.match(line)
        if fence:
            if found and found.group(1)[0] == fence[0] and len(found.group(1)) >= len(fence) and line.strip().strip(fence[0]) == "":
                fence = ""
            continue
        if found:
            fence = found.group(1)
            continue
        kept.append(line)
    return "\n".join(kept)


def parse_marks(answer: str) -> list[Mark]:
    """Every `[path:line-line]` mark of the answer, in order, the same mark once. Never raises: text that is not a string has no marks."""
    if not isinstance(answer, str) or not answer:
        return []
    seen: set[Mark] = set()
    out: list[Mark] = []
    for found in _MARK.finditer(_outside_fences(answer)):
        path = " ".join(found.group(1).split())
        if not path:
            continue
        start = int(found.group(2))
        end = int(found.group(3)) if found.group(3) is not None else start
        mark = Mark(path=path, start=start, end=end, quote=found.group(4))
        if mark not in seen:
            seen.add(mark)
            out.append(mark)
    return out


# ---- the path ---------------------------------------------------------------------------------------------------------------------

def spelling_problem(path: str) -> str:
    """The reason a path cannot be a plain path inside the folder, from its spelling alone, or "". It looks at the text and nothing else: no file system is asked, so a UNC path
    (`\\\\host\\share`, `//host/share`), a device path (`\\\\.\\pipe\\x`), a drive (`C:x`), an alternate stream (`file:stream`) or a backslash can never reach `realpath`, `stat` or `open`
    (on Windows the file system would connect to the host or open the pipe just to answer). The same text is refused on every machine, so a test on one machine says what all do."""
    if not isinstance(path, str) or not path.strip():
        return "the path is empty"
    if len(path) > MAX_PATH_CHARS:
        return "the path is too long"
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return "the path has a character a path cannot have"
    if "\\" in path or ":" in path or path.startswith("//"):
        return "the path is not written as a path inside the folder (use / and no drive letter)"
    if path.startswith("~"):
        return "the path starts with ~, which is not inside the folder"
    if any(c in _NOT_A_PATH for c in path):
        return "the path has a character a path cannot have"
    return ""


def clean_relative(path: str) -> tuple[list[str] | None, str]:
    """`(the parts of the path below the folder, "")` for a path written the way a path inside the folder is written; `(None, the reason)` for any other.
    Only the spelling is looked at here (no file system): it is what keeps `..`, a Windows spelling or a device name from ever reaching `open`."""
    bad = spelling_problem(path)
    if bad:
        return None, bad
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts:
        return None, "the path is empty"
    for part in parts:
        if part == "..":
            return None, "the path goes up out of the folder"
        if part != part.rstrip(" .") or part != part.lstrip(" "):
            return None, "a part of the path ends or starts with a space or a dot, which is not a plain name"
        if _DEVICE.match(part.split(".", 1)[0]):
            return None, "a part of the path is a reserved device name, not a file"
    return parts, ""


def _inside(real: str, root: str) -> bool:
    a, b = os.path.normcase(real), os.path.normcase(root)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def absolute_parts(path: str, folder: str) -> list[str] | None:
    """The parts below `folder` of an absolute path (it starts with one `/`), compared as TEXT with the folder: no file system is asked here. A path that does not start with the folder's
    own spelling is not inside it (None); the parts then go through the same spelling rules as a relative path and `realpath` decides the rest. A folder written with a drive or
    backslashes (Windows) never matches a `/` path, so on Windows only relative marks are accepted: the prompt asks for relative ones."""
    if not path.startswith("/") or path.startswith("//") or not isinstance(folder, str) or not folder:
        return None
    root = folder.rstrip("/")
    if root == "" or not path.startswith(root + "/"):
        return None
    return [p for p in path[len(root) + 1:].split("/") if p not in ("", ".")] or None


# ---- one mark ---------------------------------------------------------------------------------------------------------------------

def _no(mark: Mark, reason: str) -> Source:
    return Source(path=mark.path, start=mark.start, end=mark.end, quote=mark.quote, label=MISSING, how="", reason=reason)


def _squeeze(text: str) -> str:
    return " ".join(text.split())


def check_mark(mark: Mark, folder: str) -> Source:
    """One mark against the owner's folder (a real path). Never raises and never writes: any error of the file system is a reason."""
    try:
        return _check(mark, folder)
    except (OSError, ValueError, UnicodeError, MemoryError):
        return _no(mark, "the file could not be read")


def _check(mark: Mark, folder: str) -> Source:
    if not isinstance(folder, str) or not folder:
        return _no(mark, "no working folder is set")
    if mark.start < 1 or mark.end < mark.start:
        return _no(mark, "the lines are not a valid range")
    if mark.end > MAX_LINE_NUMBER:
        return _no(mark, "that line number is too big")
    if mark.end - mark.start + 1 > MAX_SPAN:
        return _no(mark, f"the range is wider than {MAX_SPAN} lines, too wide to be a source")
    path = mark.path
    bad = spelling_problem(path)                             # FIRST, and from the text alone: nothing below touches the file system for a path that fails it
    if bad:
        return _no(mark, bad)
    parts: list[str] | None
    if path.startswith("/"):
        if ".." in path.split("/"):
            return _no(mark, "the path goes up out of the folder")
        parts = absolute_parts(path, folder)                 # compared with the folder as text; the file system is asked only for a path that starts with it
        if parts is None:
            return _no(mark, "the path is not inside the folder")
        reason = ""
    else:
        parts, reason = clean_relative(path)
    if parts is None:
        return _no(mark, reason)
    checked_parts, reason = clean_relative("/".join(parts))      # the parts of an absolute path pass the same spelling rules
    if checked_parts is None:
        return _no(mark, reason)
    root = os.path.realpath(folder)
    real = os.path.realpath(os.path.join(root, *checked_parts))
    if not _inside(real, root) or os.path.normcase(real) == os.path.normcase(root):
        return _no(mark, "the path leads outside the folder")
    try:
        # one descriptor for the type check and the read; a pipe or a device cannot make the open wait, and a link at the last step is refused
        fd = os.open(real, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    except (FileNotFoundError, NotADirectoryError):
        return _no(mark, "there is no such file")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            return _no(mark, "that is not a file")
        handle = os.fdopen(fd, "rb")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    with handle:
        return _read_and_check(mark, handle, info.st_size)


def _read_and_check(mark: Mark, handle, size: int) -> Source:
    if size > MAX_FILE_BYTES:
        return _no(mark, "the file is too large to check")
    quote = None
    if mark.quote is not None:
        squeezed = _squeeze(mark.quote)
        if len(squeezed) > MAX_QUOTE:
            return _no(mark, f"the quoted words are longer than {MAX_QUOTE} characters; quote a shorter piece")
        quote = squeezed if len(squeezed) >= MIN_QUOTE else None
    lines: list[str] = []
    count = 0
    head = handle.read(8192)
    if b"\0" in head:
        return _no(mark, "the file is not text")
    handle.seek(0)
    for raw in handle:
        count += 1
        if count >= mark.start:
            lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        if count >= mark.end:
            break
    if count < mark.end:
        return _no(mark, f"the file has only {count} line{'' if count == 1 else 's'}")
    if quote is not None and quote not in _squeeze(" ".join(lines)):
        return _no(mark, "the quoted words are not on those lines")
    return Source(path=mark.path, start=mark.start, end=mark.end, quote=mark.quote, label=CHECKED, how="quote" if quote is not None else "lines", reason="")


# ---- the whole answer -------------------------------------------------------------------------------------------------------------

def check_answer(answer: str, folder: str, *, budget_s: float = BUDGET_S, marks: Iterable[Mark] | None = None) -> Report:
    """Every mark of the answer checked against `folder` (at most MAX_MARKS; `more` counts the rest). A mark that is still waiting when `budget_s` seconds
    have passed is MISSING with the reason "ran out of time", never silently dropped and never checked."""
    found = list(parse_marks(answer) if marks is None else marks)
    shown, more = found[:MAX_MARKS], max(0, len(found) - MAX_MARKS)
    deadline = time.monotonic() + max(0.0, budget_s)
    out: list[Source] = []
    for mark in shown:
        out.append(_no(mark, "ran out of time while checking") if time.monotonic() > deadline else check_mark(mark, folder))
    checked = sum(1 for s in out if s.label == CHECKED)
    return Report(sources=tuple(out), checked=checked, missing=len(out) - checked, more=more)
