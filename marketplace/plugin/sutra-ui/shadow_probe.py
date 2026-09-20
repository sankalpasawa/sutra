"""MACHINE VERIFICATION FOR DONE WHEN CHECKS. WORKER CLAIM != DONE.

THE FAILURE THIS CLOSES (founder, 2026-09-17). Every tier Shadow had was
attestation or judgement, never verification:

    founder_confirm    the founder signs it -- a judgement, and rightly so
    contains_artifact  a substring of what the WORKER SAID
    verify             _shadow_verifier: did the worker emit a DONE-CHECK
                       line quoting this check -- also a fact about what the
                       worker SAID

`_shadow_verifier` makes ZERO filesystem calls. So "a file exists containing
exactly X" was settled by the worker typing a sentence, and the previous fix
-- handing the worker the exact check strings so its claim would match --
made an accidental false claim EASIER, not harder. It closed a wording
mismatch; it did not close the hole.

A PROBE IS THE ENGINE LOOKING FOR ITSELF. When a check carries one, Shadow
reads the real filesystem and the worker's words are not consulted at all.
The claim may stay in the transcript as a report. It is not evidence.

  probe          "is this mechanically true?"   -- answered here
  founder_confirm "is this what I wanted?"      -- answered by the founder

Those are different questions and neither substitutes for the other, so a
probe is accepted on `verify` rows only. Signing-off stays human.

COMMAND EXECUTION, AND WHY IT IS NOW HERE (founder D-SH-1, 2026-09-20).
This module used to end with "command execution of any kind is deliberately
not here, and its absence is the point". That was right while the only thing
it protected was a file read. It stopped being right the moment it became the
reason the founder was signing off "the tests pass" by hand, nine checks out
of nine.

THE ARGUMENT THAT CHANGED IT. The DELEGATE already runs in this same workdir
at the founder's own permission mode -- `bypassPermissions` on this install.
It can already run anything a command probe could run, and it does, every
turn. A probe that runs `pytest` in that directory therefore adds NO
capability to the system that was not already present; what it adds is a
reading of the result that the worker cannot author. Refusing it did not make
the machine safer. It made the FOUNDER the test runner.

WHAT KEEPS IT HONEST, and these are load-bearing rather than decorative:
  * ARGV, NEVER A SHELL STRING. `shell=False`, always, with the argv as a
    list. No model-authored string is ever parsed by a shell, so there is no
    quoting to get wrong and no metacharacter to smuggle.
  * THE FLOORS APPLY. shadow_egress.floor_check screens the rendered argv
    before anything is spawned, so a probe can no more `push --force` than a
    say can. The floors were always the real boundary; this routes through
    them rather than around them.
  * CONFINED CWD, bounded wall clock, bounded captured output, no reuse.
  * THE WORKER NEVER AUTHORS ONE. Same rule as every other probe: only the
    DECIDER writes probes, through validate_decision, and the worker is shown
    the check text alone and never the probe.

WHAT IS STILL DELIBERATELY NOT HERE
  * network access as a FEATURE. A probe is not given one; a command it runs
    may of course reach the network exactly as the worker's own commands do,
    and pretending otherwise would be the dishonest kind of comment.
  * writes, creates, deletes, or anything else that touches the tree. Every
    operation below is a read, so a probe can never change the thing it is
    asked about.
  * tools for the model. Shadow's chat has none and gains none: the engine
    runs the probe, the model only proposes it.

WHO MAY AUTHOR ONE. The DECIDER, through validate_decision ->
validate_done_when. The worker never writes a decision, so it cannot write a
probe; and app._worker_checks_block quotes `check` alone, so the worker is
never even shown one. It is told what is being judged, never how.
"""

import os
import re
from collections import namedtuple

#: The read-only kinds. Small on purpose -- these are what the smoke tests
#: actually assert, and every kind added here is new attack surface.
#: EXTENDED 2026-09-17 (founder). The first two answer "is this file there"
#: and "is it exactly this". Everything else a founder writes -- "10 lines",
#: "each line distinct", "mentions the release date" -- fell off the end of
#: that vocabulary and was demoted to founder_confirm by resolve_verify_tier,
#: so Shadow parked instead of driving. Measured on m-56e8a6ee4f1f: check 1
#: got file_exists and read "Shadow checks this"; check 2 ("10 lines, each a
#: distinct line of random text") got nothing and read "Confirm".
#:
#: The three added kinds are the smallest set that covers the shapes a
#: founder actually writes, and every one is a PURE READ of one file --
#: no globbing, no shell, no regex engine, nothing that can be steered into
#: executing a model-authored string. `command_succeeds` is still not here
#: and still not wanted; see WHAT IS DELIBERATELY NOT HERE above.
#: EXTENDED 2026-09-20 (founder D-SH-1) with `command_succeeds`. The five
#: above answer questions about a FILE. Every question a founder actually
#: writes about working software -- "the tests pass", "nothing else broke",
#: "the build is green", "focus survives 200 keystrokes" -- is a question
#: about what happens when you RUN something, and not one of them could be
#: expressed here. That gap is why 9 of 9 live checks were founder_confirm.
PROBE_KINDS = ("file_exists", "file_equals",
               "line_count", "lines_distinct", "file_contains",
               "command_succeeds")

#: Kinds that name a file. `command_succeeds` does not, so `path` is
#: required for these and refused for that one -- one tuple rather than a
#: branch repeated in the validator and in `run`.
PATH_KINDS = ("file_exists", "file_equals",
              "line_count", "lines_distinct", "file_contains")

#: How long a command probe may run before it is killed and read as unmet.
#: A test suite is the thing this exists for, so the ceiling is generous;
#: the DEFAULT is short enough that a hung command does not eat a turn.
PROBE_COMMAND_TIMEOUT = 180
PROBE_COMMAND_TIMEOUT_MAX = 900

#: argv shape. Small and concrete: a probe runs ONE command, not a pipeline.
PROBE_ARGV_MAX = 24
PROBE_ARG_MAX = 512

#: How much of a command's output is captured and how much of it reaches the
#: reason line. The first bounds memory; the second bounds what a founder
#: reads on a card.
PROBE_OUTPUT_MAX = 1 << 20
PROBE_REASON_TAIL = 300

#: a file with more lines than this is not something a done-when check is
#: honestly counting; refusing beats reading an arbitrarily large file.
PROBE_LINES_MAX = 100000

#: A path is a path, not a payload.
PROBE_PATH_MAX = 512

#: File CONTENTS a check may name. A check is a sentence about the work, not
#: a copy of the artifact.
PROBE_TEXT_MAX = 4096

#: Refuse to read more than this rather than pull an arbitrarily large file
#: into memory to answer a comparison it cannot possibly pass anyway (a file
#: bigger than this cannot equal a <=4 KiB string).
PROBE_READ_MAX = 1 << 20

#: `met` is the answer. `reason` is for the ledger and the founder-facing
#: record -- never for the decision.
ProbeResult = namedtuple("ProbeResult", "met reason")

#: Split on either separator: a probe written with backslashes must not
#: smuggle a `..` segment past the screen below on a posix host.
_SEGMENTS = re.compile(r"[\\/]+")


def _validate_command(raw):
    """A `command_succeeds` probe, or None.

    ARGV IS A LIST OF STRINGS AND NOTHING ELSE. Not a string to be split, not
    a string with a shell in front of it -- a list, validated element by
    element, handed to subprocess with `shell=False`. A model that wants a
    pipeline has to express it as a program it invokes, which is the honest
    shape anyway: `["bash", "-lc", "..."]` is refused below precisely because
    it is the shell wearing an argv costume.

    THE FLOOR SCREEN IS NOT APPLIED HERE. It needs the rendered command and
    belongs at RUN time for the same reason path confinement does: a probe
    validated now may be run after the floors have been edited, and the
    answer that matters is the one at the moment something would happen.
    """
    argv = raw.get("argv")
    if not isinstance(argv, (list, tuple)) or not argv:
        return None
    if len(argv) > PROBE_ARGV_MAX:
        return None
    clean_argv = []
    for item in argv:
        if not isinstance(item, str):
            return None
        if not item or len(item) > PROBE_ARG_MAX or "\x00" in item:
            return None
        clean_argv.append(item)
    # A SHELL INVOKED BY NAME IS STILL A SHELL. Allowing `sh -c "<string>"`
    # would hand a model-authored string to a parser and give back every
    # property the argv list exists to provide, so the interpreters whose
    # whole job is to evaluate a string are refused at the door. This is a
    # NAME check and it is deliberately not clever: it is a guard against the
    # obvious accident, not a sandbox, and the floors below are the boundary.
    program = os.path.basename(clean_argv[0]).lower()
    if program in _SHELL_PROGRAMS and any(
            a in ("-c", "-lc", "-ec", "--command") for a in clean_argv[1:]):
        return None
    out = {"kind": "command_succeeds", "argv": clean_argv}
    exit_code = raw.get("expect_exit")
    if exit_code is None:
        out["expect_exit"] = 0
    elif isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return None
    elif exit_code < 0 or exit_code > 255:
        return None
    else:
        out["expect_exit"] = exit_code
    # OPTIONAL, AND AN *ADDITIONAL* CONDITION -- never a replacement for the
    # exit code. A suite that exits 0 while printing "0 tests ran" is the
    # case this exists for; a suite that exits 1 is unmet whatever it printed.
    contains = raw.get("contains")
    if contains is not None:
        if not isinstance(contains, str) or not contains \
                or len(contains) > PROBE_TEXT_MAX:
            return None
        out["contains"] = contains
        out["ignore_case"] = bool(raw.get("ignore_case"))
    timeout = raw.get("timeout_s")
    if timeout is None:
        out["timeout_s"] = PROBE_COMMAND_TIMEOUT
    elif isinstance(timeout, bool) or not isinstance(timeout, int):
        return None
    elif timeout < 1 or timeout > PROBE_COMMAND_TIMEOUT_MAX:
        return None
    else:
        out["timeout_s"] = timeout
    return out


#: Programs whose argument IS a program. See _validate_command.
_SHELL_PROGRAMS = ("sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish",
                   "python", "python3", "perl", "ruby", "node", "osascript")


def validate_probe(raw):
    """A persistable probe, or None.

    STRICT, AND None MEANS "NO PROBE" -- never "probe that passes". A row
    whose probe is dropped falls back to the attestation behaviour it had
    before this module existed, which is the safe direction: it can only
    make a check harder to satisfy, never easier.

    Shape only. Confinement needs the workdir and is enforced at RUN time by
    `resolve`, so a settings change between writing a check and evaluating it
    cannot leave a probe that was validated against the wrong root. The
    static screen here is belt-and-braces: it keeps obviously hostile paths
    off disk instead of storing them and refusing them later.
    """
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in PROBE_KINDS:
        return None
    if kind == "command_succeeds":
        return _validate_command(raw)
    path = raw.get("path")
    if not isinstance(path, str):
        return None
    path = path.strip()
    if not path or len(path) > PROBE_PATH_MAX or "\x00" in path:
        return None
    # `~` is EXPANDED BY NOBODY here, and a path that starts with one is far
    # more likely to be a model writing "~/repo/x" than a real file named
    # "~". Refusing is the honest answer to an ambiguous string.
    if path.startswith("~"):
        return None
    if any(seg == ".." for seg in _SEGMENTS.split(path)):
        return None
    out = {"kind": kind, "path": path}
    if kind == "file_equals":
        text = raw.get("text")
        if not isinstance(text, str) or len(text) > PROBE_TEXT_MAX:
            return None
        out["text"] = text
        # DEFAULT FALSE. "Exactly X" means exactly X; tolerating a trailing
        # newline is a thing the check has to ASK for, so a probe written
        # without an opinion is the strict one.
        out["allow_trailing_newline"] = bool(raw.get("allow_trailing_newline"))
    elif kind == "line_count":
        # AN INTEGER, AND A REAL ONE. bool is a subclass of int in Python, so
        # True would otherwise sail through as 1 -- a model that answered the
        # wrong question must not accidentally produce a valid probe.
        n = raw.get("count")
        if isinstance(n, bool) or not isinstance(n, int):
            return None
        if n < 0 or n > PROBE_LINES_MAX:
            return None
        out["count"] = n
        # "10 lines" is ambiguous about the newline a text editor leaves at
        # the end. Default TRUE for the same reason file_equals defaults
        # false: here the tolerant reading is what the founder means, and the
        # strict one has to be asked for.
        out["ignore_trailing_blank"] = (
            True if raw.get("ignore_trailing_blank") is None
            else bool(raw.get("ignore_trailing_blank")))
    elif kind == "file_contains":
        text = raw.get("text")
        if not isinstance(text, str) or not text or len(text) > PROBE_TEXT_MAX:
            return None
        out["text"] = text
        # a substring test, never a pattern: nothing here compiles a regex.
        out["ignore_case"] = bool(raw.get("ignore_case"))
    # lines_distinct needs nothing beyond the path
    return out


class ProbeUnsafe(Exception):
    """The path does not resolve inside the workdir, or there is no workdir.

    NOT a verdict on the work. Callers turn it into `met=False` with a
    reason, which leaves the check outstanding and the existing escalation
    path -- another worker turn, then the ordinary budget/ping-pong exits --
    exactly as it was.
    """


def default_root():
    """The worker's own cwd, which is where its work lands.

    SAME SOURCE as app._shadow_workdir_for_delegates: providers.load_settings
    already resolves stored -> SUTRA_UI_WORKDIR -> recent workspace ->
    DEFAULT_WORKDIR and expands the result, so reading it here cannot drift
    from the directory the delegate is actually spawned in. Imported lazily
    because this module is imported by the engine, which imports nothing
    heavy at module scope.
    """
    try:
        import providers
        wd = (providers.load_settings() or {}).get("workdir")
    except Exception:                    # noqa: BLE001 -- unsafe, not fatal
        wd = None
    return os.path.expanduser(str(wd)) if wd else ""


def resolve(root, path):
    """The real path this probe names, or ProbeUnsafe.

    CONFINEMENT IS ONE COMPARISON, AFTER realpath. realpath resolves every
    symlink in the chain -- the final component and every parent -- so a
    symlink pointing out of the workdir, a symlinked parent directory, and a
    `..` walk all collapse into the same question: does the resolved path
    still sit under the resolved root. Answering it after resolution rather
    than before is what makes it one question instead of a list of tricks to
    enumerate.

    The ROOT is realpath'd too, because on macOS the obvious workdirs are
    reached through symlinks (/tmp -> /private/tmp) and comparing a resolved
    path against an unresolved root would refuse every legitimate probe.

    An absolute path is allowed only if it lands inside anyway; a relative
    one is joined to the root. Neither is expanduser'd: a probe path is a
    location in the workdir, not a shell word.
    """
    if not root or not str(root).strip():
        raise ProbeUnsafe("no workdir configured")
    real_root = os.path.realpath(os.path.expanduser(str(root)))
    if not os.path.isdir(real_root):
        raise ProbeUnsafe("workdir does not exist: %s" % real_root)
    if "\x00" in path:
        raise ProbeUnsafe("path contains NUL")
    candidate = path if os.path.isabs(path) else os.path.join(real_root, path)
    try:
        real = os.path.realpath(candidate)
    except OSError as exc:               # pragma: no cover -- ELOOP etc
        raise ProbeUnsafe("unresolvable path: %s" % exc)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise ProbeUnsafe("path escapes the workdir")
    return real


def _run_file_exists(real):
    return (ProbeResult(True, "exists") if os.path.exists(real)
            else ProbeResult(False, "does not exist"))


def _run_file_equals(probe, real):
    if not os.path.isfile(real):
        return ProbeResult(False, "no file there")
    try:
        if os.path.getsize(real) > PROBE_READ_MAX:
            return ProbeResult(False, "file is larger than the compared text")
        with open(real, "rb") as fh:
            blob = fh.read(PROBE_READ_MAX + 1)
    except OSError as exc:
        return ProbeResult(False, "unreadable: %s" % str(exc)[:80])
    try:
        got = blob.decode("utf-8")
    except UnicodeDecodeError:
        return ProbeResult(False, "file is not utf-8 text")
    want = probe.get("text") or ""
    if got == want:
        return ProbeResult(True, "contents match exactly")
    if probe.get("allow_trailing_newline"):
        # ONE trailing newline, and only because the check asked. Editors and
        # `echo` add exactly one; tolerating more would make "exactly X" mean
        # something the founder did not write.
        if got in (want + "\n", want + "\r\n"):
            return ProbeResult(True, "contents match (trailing newline)")
    return ProbeResult(False, "contents differ")


def _read_text(real):
    """(text, ProbeResult) -- exactly one is None. One reader for the three
    kinds below, so "no file there", "too big" and "not utf-8" cannot drift
    into three different answers."""
    if not os.path.isfile(real):
        return None, ProbeResult(False, "no file there")
    try:
        if os.path.getsize(real) > PROBE_READ_MAX:
            return None, ProbeResult(False, "file is too large to check")
        with open(real, "rb") as fh:
            blob = fh.read(PROBE_READ_MAX + 1)
    except OSError as exc:
        return None, ProbeResult(False, "unreadable: %s" % str(exc)[:80])
    try:
        return blob.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, ProbeResult(False, "file is not utf-8 text")


def _lines(text, drop_trailing_blank=True):
    """The file's lines. A single trailing newline is the editor's, not a
    line, so it is dropped by default -- "10 lines" means ten lines of
    content, which is what a founder writing that check means."""
    out = text.split("\n")
    if drop_trailing_blank and out and out[-1] == "":
        out.pop()
    return out


def _run_line_count(probe, real):
    text, bad = _read_text(real)
    if bad is not None:
        return bad
    n = len(_lines(text, probe.get("ignore_trailing_blank", True)))
    want = probe.get("count")
    if n == want:
        return ProbeResult(True, "%d lines" % n)
    return ProbeResult(False, "%d lines, expected %d" % (n, want))


def _run_lines_distinct(real):
    text, bad = _read_text(real)
    if bad is not None:
        return bad
    rows = [l for l in _lines(text) if l.strip()]
    if not rows:
        # AN EMPTY FILE IS NOT "ALL LINES DISTINCT". Vacuous truth is the
        # wrong answer to a founder asking for distinct lines: it would pass
        # a check on a file nobody wrote.
        return ProbeResult(False, "no lines to compare")
    seen, dupe = set(), None
    for l in rows:
        if l in seen:
            dupe = l
            break
        seen.add(l)
    if dupe is None:
        return ProbeResult(True, "%d lines, all distinct" % len(rows))
    return ProbeResult(False, "repeated line: %s" % dupe[:60])


def _run_file_contains(probe, real):
    text, bad = _read_text(real)
    if bad is not None:
        return bad
    want = probe.get("text") or ""
    hay = text.lower() if probe.get("ignore_case") else text
    needle = want.lower() if probe.get("ignore_case") else want
    if needle in hay:
        return ProbeResult(True, "found %s" % want[:60])
    return ProbeResult(False, "does not contain %s" % want[:60])


def _floor_screen(argv):
    """The floor names this command trips, or []. Never raises.

    ONE FLOOR TABLE FOR THE WHOLE OF SHADOW. shadow_egress owns the patterns
    and a say has been screened by them since S52; a command probe is screened
    by the SAME function rather than a second list that would drift from it.
    A probe that trips one is refused, not paused: there is no founder in the
    loop at evaluation time, and "ask before running this" has no meaning for
    a check Shadow is answering on its own. The check simply stays the
    founder's, which is the safe direction and the one every other refusal in
    this module takes.
    """
    try:
        import shadow_egress
        return shadow_egress.floor_check(" ".join(argv))
    except Exception:                    # noqa: BLE001 -- unscreened, so unsafe
        return ["floor screen unavailable"]


def _run_command_succeeds(probe, root):
    """Run one command in the workdir and read its exit code.

    NEVER RAISES -- every failure is met=False with a reason, exactly like
    every other probe in this module, because an exception here would cross
    evaluate_done_when and turn a probe bug into a FAILED mission.

    THE REASON LINE IS THE AUDIT TRAIL. It carries the command, the exit code
    and the tail of what came out, because a founder reading "Shadow ran this
    check and it passed" is entitled to see what was run. That string is
    scrubbed of credential shapes on its way out for the same reason a say is.
    """
    argv = probe["argv"]
    floors = _floor_screen(argv)
    if floors:
        return ProbeResult(False, "probe refused: floor %s" % ", ".join(floors))
    try:
        real_root = resolve(root, ".")
    except ProbeUnsafe as exc:
        return ProbeResult(False, "probe refused: %s" % exc)
    import subprocess
    try:
        proc = subprocess.run(                      # noqa: S603 -- see module
            argv, cwd=real_root, shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=probe.get("timeout_s", PROBE_COMMAND_TIMEOUT))
    except subprocess.TimeoutExpired:
        return ProbeResult(False, "%s timed out after %ss"
                           % (_argv_label(argv), probe.get("timeout_s")))
    except FileNotFoundError:
        return ProbeResult(False, "%s: no such program" % _argv_label(argv))
    except OSError as exc:
        return ProbeResult(False, "%s failed to start: %s"
                           % (_argv_label(argv), str(exc)[:80]))
    out = (proc.stdout or b"")[:PROBE_OUTPUT_MAX]
    text = out.decode("utf-8", "replace")
    want_exit = probe.get("expect_exit", 0)
    label = _argv_label(argv)
    if proc.returncode != want_exit:
        return ProbeResult(False, "%s exited %d (wanted %d)%s"
                           % (label, proc.returncode, want_exit,
                              _output_tail(text)))
    needle = probe.get("contains")
    if needle:
        hay = text.lower() if probe.get("ignore_case") else text
        want = needle.lower() if probe.get("ignore_case") else needle
        if want not in hay:
            return ProbeResult(
                False, "%s exited %d but did not print %s%s"
                % (label, proc.returncode, needle[:60], _output_tail(text)))
    return ProbeResult(True, "%s exited %d%s"
                       % (label, proc.returncode, _output_tail(text)))


def _argv_label(argv):
    """The command as one readable string. FOR DISPLAY ONLY -- nothing ever
    parses this back into an argv, which is the whole reason it is safe to
    make it readable.

    SCRUBBED, because a command can carry a credential in its own arguments
    (`curl -H "Authorization: Bearer ..."`) and this string reaches the
    ledger and the founder's card. Scrubbing only the OUTPUT would have left
    the token in the half of the line Shadow wrote itself.
    """
    line = " ".join(argv)[:200]
    try:
        import shadow_egress
        line, _ = shadow_egress.scrub(line)
    except Exception:                    # noqa: BLE001 -- unscrubbed is unsafe
        return "(command withheld)"
    return line


def _output_tail(text):
    """The end of what the command printed, scrubbed, for the reason line.

    THE TAIL, NOT THE HEAD: a test runner puts the summary last, and the
    summary is what answers the check. Scrubbed through the same egress
    scrubber a say uses, because this string reaches the ledger and the
    founder-facing card and a command may print a token.
    """
    body = " ".join((text or "").split())
    if not body:
        return ""
    try:
        import shadow_egress
        body, _ = shadow_egress.scrub(body)
    except Exception:                    # noqa: BLE001 -- unscrubbed is unsafe
        return " -- output withheld (scrubber unavailable)"
    tail = body[-PROBE_REASON_TAIL:]
    return " -- %s%s" % ("…" if len(body) > len(tail) else "", tail)


def run(probe, root=None):
    """Execute one probe against the real filesystem.

    NEVER RAISES. Every failure -- a bad probe, an escaping path, no
    workdir, an unreadable file -- is `met=False` with a reason, because the
    alternative is an exception crossing evaluate_done_when and landing in
    the engine's `shadow_eval_failed` exit, which would turn a probe bug into
    a FAILED mission. A fault in Shadow is never a verdict on the work: an
    unanswerable probe leaves the check outstanding and the worker is driven
    again.
    """
    clean = validate_probe(probe)
    if clean is None:
        return ProbeResult(False, "unusable probe")
    root = default_root() if root is None else root
    # A COMMAND PROBE NAMES NO FILE. It is confined to the same workdir by
    # the same resolver -- `_run_command_succeeds` resolves "." through
    # `resolve` -- so the confinement question is asked once, in one place,
    # for both shapes.
    if clean["kind"] == "command_succeeds":
        try:
            return _run_command_succeeds(clean, root)
        except Exception as exc:         # noqa: BLE001 -- unknown, not done
            return ProbeResult(False, "probe failed: %s" % str(exc)[:80])
    try:
        real = resolve(root, clean["path"])
    except ProbeUnsafe as exc:
        return ProbeResult(False, "probe refused: %s" % exc)
    except Exception as exc:             # noqa: BLE001 -- unknown, not done
        return ProbeResult(False, "probe failed: %s" % str(exc)[:80])
    try:
        kind = clean["kind"]
        if kind == "file_exists":
            return _run_file_exists(real)
        if kind == "file_equals":
            return _run_file_equals(clean, real)
        if kind == "line_count":
            return _run_line_count(clean, real)
        if kind == "lines_distinct":
            return _run_lines_distinct(real)
        if kind == "file_contains":
            return _run_file_contains(clean, real)
        return ProbeResult(False, "unusable probe")
    except Exception as exc:             # noqa: BLE001 -- unknown, not done
        return ProbeResult(False, "probe failed: %s" % str(exc)[:80])


def met(probe, root=None):
    """Just the answer, for evaluate_done_when."""
    return bool(run(probe, root).met)
