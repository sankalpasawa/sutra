"""Names, not paths: the words Sutra writes for the owner say 'tools.py', never this machine's folders (gap package chart-insight).

    shorten(text, roots=None)     the text with each path of THIS machine in it shortened to its file name; anything else as it is
    machine_roots(extra=())       the folders of this machine, longest first: the home, the temp folder, the folder the app is installed
                                  in (each as the program names it and as the disk resolves it: /var is /private/var on a Mac), the
                                  Mac's /private/var/folders and /Volumes, and `extra` (the data folder)
    compile_rule(roots)           the pattern `shorten` uses over those folders
    short_path(match)             the replacement of one match

A crash puts up to 2 KB of a team process's error output into the card the owner reads, and that output names real folders (the home,
the install location of the app). The owner reads the file's name instead. The rule is careful, because the same words also carry the
owner's own pages and dates, which must reach the page as they were said:

  * a path is this machine's only when it sits under one of its folders (at least one name below it), or starts with `~`, or is a Windows
    drive path under Users, Windows, ProgramData or Documents; '/home/about', '/private/members' and '/etc/terms' are pages of a site
  * a folder alone is a page too ('/home', '/tmp', '/Volumes'); the one exception is a deeper folder of this machine itself ('/Users/me')
  * a relative path ('build/v1/index.html'), a date ('5/6/2026') and a URL are never paths of this machine and are never touched
  * `~` and a drive letter count only where a path would start (the start of the text, or after a space, a quote or a bracket), and a
    drive letter followed by a slash only with a Windows folder after it ('Plan B:/pricing' is a plan and a page, not a drive)
  * the punctuation that ended the sentence stays ('wrote /Users/me/a/z.txt.' becomes 'wrote z.txt.')

Pure: it reads the environment only to find the folders of the moment (`machine_roots`), and it writes nothing. The callers shorten the
text that goes to the owner and leave the log files whole. Ported from the old app's machine_paths.py with the roots injected.
"""
import os
import re
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

__all__ = ["shorten", "machine_roots", "compile_rule", "short_path"]

_SEG = r"[\\/][\w.@%+=~-]+"
_START = r"(?<![^\s\"'(\[{<=])"
_FIXED_ROOTS = ("/private/var/folders", "/var/folders", "/Volumes")
_WINDOWS = r"(?:Users|Windows|ProgramData|Documents)"
_HOME_PATH = (_START + r"(?:~|[A-Za-z]:(?=\\|[\\/]" + _WINDOWS + r"\b))(?:" + _SEG + r")+[\\/]?")
_TAIL_PUNCT = ".,;:!?"


def _both(path: str) -> set[str]:
    """`path` as named and as the disk resolves it."""
    return {path, os.path.realpath(path)}


def machine_roots(extra: Iterable[str | os.PathLike[str]] = (), *, home: str | os.PathLike[str] | None = None,
                  temp: str | os.PathLike[str] | None = None, install: str | os.PathLike[str] | None = None) -> tuple[str, ...]:
    """The folders of this machine, longest first, as absolute paths with no trailing slash. `home`, `temp` and `install` default to
    the real ones (Path.home(), the temp folder, the folder that holds the `sutra_app` package and the interpreter's prefix when that
    is at least two names deep); `extra` adds more (the data folder). A folder that cannot be found is one folder fewer, never an error."""
    found: set[str] = set(_FIXED_ROOTS)
    sources: list = []
    sources.append(home if home is not None else _safe(Path.home))
    sources.append(temp if temp is not None else _safe(tempfile.gettempdir))
    if install is not None:
        sources.append(install)
    else:
        for folder in (_safe(lambda: Path(__file__).resolve().parents[2]), _safe(lambda: sys.prefix)):      # where sutra_app and the interpreter live
            if folder is not None and str(folder).count("/") > 1:                      # '/usr' or '/opt' alone would call every '/usr/...' page a path
                sources.append(folder)
    sources.extend(extra)
    for source in sources:
        if source is None or str(source) == "":                 # realpath("") is the current folder: never a root
            continue
        try:
            found.update(_both(str(source)))
        except (OSError, ValueError):
            continue
    cleaned = {r.rstrip("/") for r in found if r.startswith("/") and len(r.rstrip("/")) > 1}
    return tuple(sorted(cleaned, key=lambda r: (-len(r), r)))


def _safe(get):
    try:
        return get()
    except Exception:                                                                  # noqa: BLE001  (a home that is not there is one folder fewer)
        return None


def compile_rule(roots: Iterable[str]) -> re.Pattern[str]:
    """The path rule over these folders: a path under one (at least one name below it), the folder itself only when it is this machine's
    own and deeper than one name (/Users/me, not /tmp, /Volumes or /var/folders), and a home path (~/..., a drive path)."""
    listed = [r for r in roots if isinstance(r, str) and r.startswith("/") and len(r.rstrip("/")) > 1]
    cleaned = sorted({r.rstrip("/") for r in listed} | set(_FIXED_ROOTS), key=lambda r: (-len(r), r))
    alt = "|".join(re.escape(r) for r in cleaned)
    deep = "|".join(re.escape(r) for r in cleaned if r.count("/") > 1 and r not in _FIXED_ROOTS)
    under = r"(?<![\w./~-])(?:" + alt + r")(?:" + _SEG + r")+[\\/]?"
    alone = r"(?<![\w./~-])(?:" + deep + r")[\\/]?(?![\w@%+=~-]|\.\w)" if deep else None
    return re.compile("|".join(x for x in (under, alone, _HOME_PATH) if x))


def short_path(match: re.Match[str]) -> str:
    """The replacement for one match of the rule: the path's file name, with the punctuation that ended the sentence kept."""
    path = match.group(0)
    tail = ""
    while path and path[-1] in _TAIL_PUNCT:
        tail, path = path[-1] + tail, path[:-1]
    name = re.split(r"[\\/]", path.rstrip("\\/"))[-1]
    return (name or path) + tail


def shorten(text: str, roots: Iterable[str] | None = None) -> str:
    """`text` with each path of this machine shortened to its file name; anything else (and anything that is not text) as it is.
    `roots` are the folders to treat as this machine's (default `machine_roots()`); the Mac's temp and volume folders always are."""
    if not isinstance(text, str) or text == "":
        return text
    folders = machine_roots() if roots is None else list(roots)
    return compile_rule(folders).sub(short_path, text)
