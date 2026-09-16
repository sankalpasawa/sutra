#!/usr/bin/env python3
"""The two markdown edits release-desktop.sh cannot do safely in shell.

WHY A FILE AND NOT A HEREDOC. Both edits splice a block into a document at a
position found by reading it, which sed cannot express and which a shell
heredoc inside a shell script quotes badly. Keeping them here also makes them
testable on their own (scripts/test-release-desktop.sh).

NEITHER EDIT INVENTS PROSE. `changelog` writes the notes file it is given,
verbatim, under a heading; `current` moves the HEAD marker and leaves a pointer
to the CHANGELOG. Anything a human should have written stays a human's.
"""
import io
import sys


def changelog(path, ver, day, notes):
    """Splice a new entry above the newest existing one."""
    s = io.open(path, encoding="utf-8").read()
    if "\n## %s " % ver in s:
        return 0                       # already there; nothing to do
    body = io.open(notes, encoding="utf-8").read().strip()
    if not body:
        sys.stderr.write("notes file is empty; refusing to write a blank entry\n")
        return 2
    i = s.index("\n## ")               # the newest existing entry
    entry = "## %s (%s)\n\n%s\n\n" % (ver, day, body)
    io.open(path, "w", encoding="utf-8").write(s[:i + 1] + entry + s[i + 1:])
    return 0


def current(path, frm, to, day):
    """Move the single HEAD marker onto a new heading for `to`."""
    s = io.open(path, encoding="utf-8").read()
    if "## v%s (" % to in s:
        return 0
    marker = "## v%s (" % frm
    if marker not in s:
        sys.stderr.write("no '## v%s (' heading in %s\n" % (frm, path))
        return 2
    i = s.index(marker)
    j = s.index(")", i) + 1
    head = s[i:j]
    s = s[:i] + head.replace(", HEAD", "") + s[j:]
    entry = ("## v%s (%s, HEAD)\n\n"
             "See marketplace/plugin/CHANGELOG.md for this release's entry.\n\n"
             % (to, day))
    io.open(path, "w", encoding="utf-8").write(s[:i] + entry + s[i:])
    return 0


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: _release_edit.py changelog|current ...\n")
        return 2
    what = argv[1]
    if what == "changelog":
        return changelog(*argv[2:6])
    if what == "current":
        return current(*argv[2:6])
    sys.stderr.write("unknown mode: %s\n" % what)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
