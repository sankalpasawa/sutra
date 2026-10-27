"""machine_paths.py -- which strings name a file of THIS machine, and the one rule that shortens them to the file's name.

Two readers of the department scrub what they send with this rule, and they must scrub alike, or one page says a rule two ways:
functions_view (each function's pane, the Map, the engine card: its _clean) and the J2 view's adapter (j2ui_common.clean). It
is a module of its own so that both stand on it and neither on the other (j2ui_common reads functions_view, so functions_view
cannot read j2ui_common). functions_view used to have a rule of its own, to which any /a/b was a path: the owner's quoted
pages came out cut to their last name ('Never link /private/area from the menu' became 'Never link area from the menu' on the
Audit tab, the Identity lane and the Map) and a relative file or a date came out joined ('build/v1/index.html' became
'buildindex.html', '5/6/2026' became '52026').

The rule is a path of THIS machine: one under a folder this machine has, the user's home, the records' home, the temp folder
and the app's own folder (each as the program names it and as the disk resolves it: /var is /private/var on a Mac), the Mac's
/private/var/folders and /Volumes, `~/...`, and a Windows drive path. A folder name alone says nothing: '/home/about',
'/private/members', '/etc/terms' and '/var/news' are the pages of a site unless they sit under one of those folders, and the
owner quotes pages in rules, in done-when and in answers, so a path is shortened only when it is this machine's. A root alone is
a page too (/home, /tmp, /Volumes, /opt-in); a relative path (build/v1/index.html), a date (5/6/2026) and a URL are not paths of
this machine, and none of these is ever touched. `~` and a drive letter count only where a path would start (the start of the
text or after a space, a quote or a bracket), and a drive letter followed by a slash only with a folder of Windows after it
('Plan B:/pricing' is a plan and a page, not a drive).

This module reads nothing of a department: it asks website_dept for the records' home and the environment for the rest, and it
writes nothing.
"""
import os
import re
import tempfile
import threading
from pathlib import Path

import website_dept as W

_SEG = r"[\\/][\w.@%+=~-]+"
_START = r"(?<![^\s\"'(\[{<=])"
_FIXED_ROOTS = ("/private/var/folders", "/var/folders", "/Volumes")
_WINDOWS = r"(?:Users|Windows|ProgramData|Documents)"
_HOME_PATH = (_START + r"(?:~|[A-Za-z]:(?=\\|[\\/]" + _WINDOWS + r"\b))(?:" + _SEG + r")+[\\/]?")
_TAIL_PUNCT = ".,;:!?"


def machine_roots():
    """The folders of this machine, longest first, as absolute paths with no trailing slash."""
    found = set(_FIXED_ROOTS)
    here = Path(__file__).resolve().parent
    for get in (Path.home, W.home, tempfile.gettempdir, lambda: here):
        try:
            path = str(get())
            found.update((path, os.path.realpath(path)))
        except Exception:  # noqa: BLE001 -- a home that cannot be found is one folder fewer, never a failed response
            continue
    return tuple(sorted({r.rstrip("/") for r in found if r.startswith("/") and len(r.rstrip("/")) > 1}, key=lambda r: (-len(r), r)))


def compile_rule(roots):
    """The path rule over these folders: a path under one (at least one name below it), the folder itself only when it is
    this machine's own and deeper than one name (/Users/me, not /tmp, /Volumes or /var/folders), and a home path (~/..., a
    drive path)."""
    alt = "|".join(re.escape(r) for r in roots)
    deep = "|".join(re.escape(r) for r in roots if r.count("/") > 1 and r not in _FIXED_ROOTS)
    under = r"(?<![\w./~-])(?:" + alt + r")(?:" + _SEG + r")+[\\/]?" if alt else None
    alone = r"(?<![\w./~-])(?:" + deep + r")[\\/]?(?![\w@%+=~-]|\.\w)" if deep else None
    return re.compile("|".join(x for x in (under, alone, _HOME_PATH) if x))


_RULE = {"key": None, "re": None}
_RULE_LOCK = threading.Lock()


def rule():
    """The compiled path rule for this machine as it stands: made again whenever the home, the records' home or the temp
    folder changes (a test binds them to a folder of its own, and the Beta channel has a records home of its own)."""
    key = (os.environ.get("HOME"), os.environ.get("USERPROFILE"), os.environ.get("SUTRA_NATIVE_DEPT_HOME"), os.environ.get("TMPDIR"),
           tempfile.tempdir)
    with _RULE_LOCK:
        if _RULE["key"] != key:
            _RULE["key"], _RULE["re"] = key, compile_rule(machine_roots())
        return _RULE["re"]


class _PathRule:
    """ABS_PATH: the path rule of this machine, as a compiled pattern's search/sub/finditer (the pattern itself is made from
    the folders of the moment, see rule)."""

    def search(self, text, *a):
        return rule().search(text, *a)

    def sub(self, repl, text, *a, **k):
        return rule().sub(repl, text, *a, **k)

    def finditer(self, text, *a):
        return rule().finditer(text, *a)

    @property
    def pattern(self):
        return rule().pattern


ABS_PATH = _PathRule()


def short_path(m):
    """The replacement for one match of the rule: the path's file name, with the punctuation that ended the sentence kept."""
    path = m.group(0)
    tail = ""
    while path and path[-1] in _TAIL_PUNCT:
        tail, path = path[-1] + tail, path[:-1]
    name = re.split(r"[\\/]", path.rstrip("\\/"))[-1]
    return (name or path) + tail


def shorten(text):
    """One string with each path of this machine in it shortened to its file name; anything else as it is."""
    return rule().sub(short_path, text) if isinstance(text, str) else text
