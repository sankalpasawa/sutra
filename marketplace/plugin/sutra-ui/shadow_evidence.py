"""THE ARTIFACT LANE. What the work PRODUCED, read from disk, bounded.

THE FAILURE THIS CLOSES (founder, 2026-09-20, second pass on D-SH-1).
D-SH-1 inverted the tier ladder so `judge` became the default and only taste
and founder-held facts reached a human. Measured on the founder's install the
day after, the inversion did not land: a task asked for "10 lines of MotoGP's
latest news" and the check

    "each line is a real, recent MotoGP news item drawn from current sources
     rather than invented or generic filler, and the file contains only the
     10 items with no headers, numbering or bullets"

still arrived as a Confirm button. The tiering was RIGHT -- `tier_for` returns
`judge` for that string, measured. What failed was one function downstream:
`shadow_judge.evidence_for` builds its blob from `git status`, `git diff` and
`git diff --cached`, and the artifact was a NEW, UNTRACKED file. Both diffs
were empty. The whole of what the judge was shown was:

    FILES TOUCHED (git status --short):
    ?? motogp-news.txt

A filename. No content. The judge answered `cannot_tell` -- correctly, on
that evidence -- and `_run_judges` re-tiered the row to the founder.

THE GENERAL DEFECT, of which MotoGP is one instance: the judge could only
ever see CHANGES TO TRACKED FILES. Every authoring, generation, research and
report task produces an artifact it is structurally blind to. A whole class
of work could not be verified, and the founder signed for all of it.

WHY THIS IS NOT THE THING THE JUDGE MUST NOT SEE. shadow_judge's header draws
the line that makes the judge review rather than attestation: it is shown the
work, never anybody's ACCOUNT of the work. A file the worker wrote is the
work. A sentence the worker typed about the file is the account. Reading
`motogp-news.txt` is the same act as reading `git diff` -- both are the
artifact, and neither asks anyone to be believed. The transcript stays out,
here as there, and there is no parameter in this module through which it
could arrive.

WHY IT IS BOUNDED, AND WHY THE BOUNDS ARE THE DESIGN (founder, 2026-09-20:
"define safe artifact-content boundaries so the new L3 evidence lane doesn't
become unlimited workspace ingestion"). An evidence lane that read whatever it
liked would be a worse defect than the blindness it closes: it would pull the
founder's workspace into a model prompt, crowd the diff out of the evidence
budget, and read files nobody asked about. So every limit below is a refusal,
they are all in this one module so they can be audited in one place, and the
selection rule is mission-scoped rather than a walk of the tree.

WHAT IS SELECTED, and this list is exhaustive:
  * paths NAMED BY THIS MISSION'S OWN PROBES -- the engine passes them
  * paths git reports as UNTRACKED (`??`) -- the blind spot itself

WHAT IS DELIBERATELY NOT SELECTED:
  * modified tracked files. The diff already carries them; reading them again
    would spend the evidence budget on a duplicate.
  * anything else in the tree. There is no glob here, no walk, no directory
    listing. A file nobody named and git did not report does not exist to
    this module.

EVERY OPERATION IS A READ. Nothing here writes, creates, deletes or executes.
"""

import os

#: THE BOUNDARIES (founder, 2026-09-20). Each one is a refusal, and the
#: comment on each says what it is refusing.

#: How many files one judgement may read. A done-when check is a sentence
#: about an artifact, not about a workspace; a check that genuinely needs
#: nine files is a check that should have been several checks.
MAX_FILES = 8

#: Bytes per file, head-anchored. A generated file, a report, a list, a
#: config -- the shapes this lane exists for -- are all far under this. The
#: MotoGP file that started it is about 1 KiB.
MAX_FILE_BYTES = 32 * 1024

#: The whole artifact section, inside shadow_judge's 60 KB EVIDENCE_MAX. The
#: diff MUST NOT be crowded out by artifact content: a judge that can see the
#: new file but not the change is a different kind of blind.
MAX_SECTION_BYTES = 48 * 1024

#: Refuse before opening rather than pull a large file into memory to throw
#: most of it away. A file this big is not something a done-when check is
#: honestly quoting.
MAX_STAT_BYTES = 1024 * 1024

#: A line longer than this is reported by length rather than quoted -- a
#: minified bundle is not evidence, it is a way to spend the budget.
LONG_LINE = 2000

#: What a line has to look like to count as a bullet, a numbered item or a
#: heading. FIXED VOCABULARY, COMPILED HERE, and the reason it is a fixed
#: vocabulary rather than a pattern the model supplies is in shadow_probe's
#: `lines_shape`: nothing in Shadow compiles a model-authored regex.
_BULLET_CHARS = ("-", "*", "+", "•", "‣", "◦", "⁃")
_HEADING_CHARS = ("#", "=")


def is_blank(line):
    return not str(line or "").strip()


def is_bullet(line):
    """`- x`, `* x`, `+ x`, `- x` with a unicode bullet -- a marker then a
    SPACE.

    The space is load-bearing. Without it `-1.017s behind the leader` reads
    as a bullet, and a check about bullets would fail on a line that is
    simply a sentence starting with a minus sign.
    """
    s = str(line or "").strip()
    return bool(s) and s[0] in _BULLET_CHARS and s[1:2] in (" ", "\t")


def is_numbered(line):
    """`1. x`, `2) x`, `10 - x` -- digits, a separator, then a space.

    Deliberately narrow for the same reason as is_bullet: a line that OPENS
    with a number ("2026 was the season that...") is not a numbered list
    item, and treating it as one would make "no numbering" unsatisfiable by
    any honest file about a year.
    """
    s = str(line or "").strip()
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if i == 0 or i > 3:                  # no digits, or not a list ordinal
        return False
    rest = s[i:]
    if rest[:1] in (".", ")", ":") and rest[1:2] in (" ", "\t"):
        return True
    if rest[:3] in (" - ", " – "):
        return True
    return False


def is_heading(line):
    """`# x`, `## x`, `=== x`, or a short ALL-CAPS line with no sentence
    punctuation -- which is how a heading appears in a plain text file that
    has no markdown in it."""
    s = str(line or "").strip()
    if not s:
        return False
    if s[0] in _HEADING_CHARS:
        rest = s.lstrip("".join(_HEADING_CHARS))
        return bool(rest.strip()) or len(s) >= 3
    if len(s) <= 60 and s.upper() == s and any(c.isalpha() for c in s) \
            and not s.endswith((".", "!", "?")):
        return True
    return False


#: The shapes a `lines_shape` probe may name, and the ONLY ones. A name not
#: in this table is refused by shadow_probe rather than interpreted.
SHAPES = {
    "blank": is_blank,
    "bullet": is_bullet,
    "numbered": is_numbered,
    "heading": is_heading,
}


def lines_of(text):
    """The file's lines, with a single trailing newline dropped.

    THE SAME READING shadow_probe._lines uses, and deliberately so: a founder
    who writes "10 lines" means ten lines of content, and the two modules
    must not disagree about what a line is, or a `line_count` probe and the
    facts block beside it would report different numbers for the same file.
    """
    out = str(text or "").split("\n")
    if out and out[-1] == "":
        out.pop()
    return out


def facts_for(text):
    """DETERMINISTIC COUNTS ABOUT ONE FILE, computed here in Python.

    WHY THE JUDGE IS TOLD THE COUNT RATHER THAN ASKED TO COUNT. A model
    reading a file and reporting "it has 10 lines" is a model doing
    arithmetic in prose, which is the one thing they are worst at and the one
    thing a computer is exact at. So the quantities are computed and STATED,
    and the judge's job is reduced to what only a reader can do: deciding
    whether the content supports the claim.

    This is the L2 layer of the verification ladder: deterministic facts,
    carried as evidence rather than as a verdict. It settles nothing on its
    own -- `facts_for` has no opinion about any check -- and it removes the
    need for the judge to guess at anything countable.
    """
    rows = lines_of(text)
    filled = [l for l in rows if l.strip()]
    return {
        "lines": len(rows),
        "non_empty_lines": len(filled),
        "blank_lines": len(rows) - len(filled),
        "distinct_non_empty_lines": len(set(filled)),
        "bullet_lines": sum(1 for l in rows if is_bullet(l)),
        "numbered_lines": sum(1 for l in rows if is_numbered(l)),
        "heading_lines": sum(1 for l in rows if is_heading(l)),
        "longest_line_chars": max((len(l) for l in rows), default=0),
        "characters": len(text or ""),
    }


#: Stable order, so two renderings of the same file are the same string.
_FACT_ORDER = ("lines", "non_empty_lines", "blank_lines",
               "distinct_non_empty_lines", "bullet_lines", "numbered_lines",
               "heading_lines", "longest_line_chars", "characters")


def render_facts(facts):
    """The facts block as the judge reads it. One line, stable order."""
    return ", ".join("%s=%s" % (k, facts[k])
                     for k in _FACT_ORDER if k in facts)


def read_artifact(root, path):
    """(text, note) for one file -- exactly one is None. NEVER RAISES.

    EVERY REFUSAL IS REPORTED, and that is the honesty rule of this module.
    A file skipped silently is evidence loss the judge cannot know about, so
    it would grade a partial picture believing it was whole. A file skipped
    AUDIBLY is a fact the judge can act on: the prompt tells it to answer
    `cannot_tell` when what it can see does not settle the check, and a
    "could not read" note is exactly that situation.

    CONFINEMENT IS shadow_probe.resolve, not a second implementation. That
    function realpaths the candidate and the root and compares once, which
    collapses `..` walks, symlinked leaves and symlinked parents into one
    question. Writing the check again here would be a second answer to that
    question, and the two would drift.
    """
    try:
        import shadow_probe
    except Exception as exc:             # noqa: BLE001 -- unconfined is unsafe
        return None, ("not read (confinement unavailable: %s)"
                      % str(exc)[:60])
    try:
        real = shadow_probe.resolve(root, path)
    except shadow_probe.ProbeUnsafe as exc:
        return None, "not read: %s" % exc
    except Exception as exc:             # noqa: BLE001 -- unknown, so refused
        return None, "not read: %s" % str(exc)[:80]
    try:
        if not os.path.isfile(real):
            return None, "not a file"
        size = os.path.getsize(real)
        if size > MAX_STAT_BYTES:
            return None, ("not read: %d bytes, over the %d byte ceiling"
                          % (size, MAX_STAT_BYTES))
        with open(real, "rb") as fh:
            blob = fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        return None, "not read: %s" % str(exc)[:80]
    if b"\x00" in blob:
        # A NUL byte is the cheap, reliable binary tell. A binary file is not
        # readable evidence, and decoding it would produce replacement
        # characters a judge might read as content.
        return None, "not read: binary file"
    truncated = len(blob) > MAX_FILE_BYTES
    blob = blob[:MAX_FILE_BYTES]
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        if not truncated:
            return None, "not read: not utf-8 text"
        # A cut lands mid-character far more often than a real text file is
        # non-utf-8, so retry lenient and say so rather than report a large
        # text file as binary.
        text = blob.decode("utf-8", "ignore")
    if truncated:
        text += ("\n\n[... truncated at %d bytes. You are seeing the START "
                 "of this file. If the part you can see does not settle the "
                 "check, answer cannot_tell.]" % MAX_FILE_BYTES)
    return text, None


def _quote(text):
    """The file's content, with over-long lines reported rather than quoted.

    A minified bundle or a base64 blob is one line of 400 KB that says
    nothing a judge can use and would eat the section budget on its own.
    """
    out = []
    for line in str(text or "").split("\n"):
        if len(line) > LONG_LINE:
            out.append("[a line of %d characters, not quoted]" % len(line))
        else:
            out.append(line)
    return "\n".join(out)


def render(root, paths):
    """The ARTIFACT section of the evidence blob, or "".

    Order is the caller's, because the caller knows which paths its own
    probes named and those are the ones a check is most likely about. Files
    beyond MAX_FILES and bytes beyond MAX_SECTION_BYTES are DROPPED AUDIBLY,
    for the same reason a refusal is reported: the judge must never be led to
    believe it saw everything.
    """
    seen, chosen = [], []
    for p in (paths or []):
        p = str(p or "").strip()
        if not p or p in seen:
            continue
        seen.append(p)
        chosen.append(p)
    if not chosen:
        return ""
    dropped = len(chosen) - MAX_FILES
    chosen = chosen[:MAX_FILES]
    parts, budget, unreadable = [], MAX_SECTION_BYTES, 0
    for path in chosen:
        text, note = read_artifact(root, path)
        if text is None:
            # A PATH IS ECHOED ONLY ONCE SOMETHING WAS FOUND AT IT, and this
            # is the narrowest form of the rule that keeps the worker's words
            # away from the judge. A candidate that names no file is, by
            # definition, a string whose only content is what the caller
            # typed -- so quoting it back to explain the refusal would be the
            # one route by which prose could enter the evidence blob. It is
            # counted instead. The judge is still TOLD that a named file
            # could not be read, which is what it needs in order to answer
            # `cannot_tell`; it simply is not told a string it cannot trust.
            unreadable += 1
            continue
        facts = facts_for(text)
        body = "--- %s\n[measured: %s]\n%s" % (path, render_facts(facts),
                                               _quote(text))
        if len(body) > budget:
            parts.append("--- %s: not quoted, the evidence budget is full "
                         "(measured: %s)" % (path, render_facts(facts)))
            continue
        budget -= len(body)
        parts.append(body)
    if unreadable:
        parts.append("[%d named file(s) could NOT be read -- missing, "
                     "binary, outside the workdir, or too large. If the "
                     "check is about one of them, answer cannot_tell.]"
                     % unreadable)
    if dropped > 0:
        parts.append("[%d further file(s) were produced and are NOT shown "
                     "here. If the check is about one of them, answer "
                     "cannot_tell.]" % dropped)
    if not parts:
        return ""
    return ("THE ARTIFACT (files the work produced, read from disk). The "
            "`measured:` line on each is COUNTED BY MACHINE, not by anyone's "
            "report -- trust those numbers over your own count:\n\n"
            + "\n\n".join(parts))
