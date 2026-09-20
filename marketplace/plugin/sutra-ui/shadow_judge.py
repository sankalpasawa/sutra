"""THE EVIDENCE JUDGE. A check settled by READING THE WORK, not by being told.

WHY THIS EXISTS (founder D-SH-1, 2026-09-20). Across every mission on the
founder's install, 9 done-when checks out of 9 were `founder_confirm`. Not
most of them -- all of them. Shadow had never once settled a check by itself,
and the reason was not distrust. It was that the only lane it had could read a
file, so every check about whether working software actually works fell off
the end of the vocabulary and landed on the founder's desk.

Three of those nine were this, verbatim:

    "typing a long message into the talk-to-shadow box holds focus the whole
     time -- no keystrokes are dropped and the cursor never leaves the field"
    "the fix addresses the identified root cause of the focus loss in the
     live repo source, not a workaround such as a refocus-on-blur hack"
    "no other input, panel or behaviour in the UI changed as a side effect"

The first and third are commands (shadow_probe.command_succeeds, added the
same day). The second is not, and never will be: answering it means reading a
diff and forming a view. That is what this module does.

WHAT THIS IS NOT, AND THE DISTINCTION IS THE WHOLE DESIGN
-----------------------------------------------------------------------------
`app._shadow_verifier` asks: did the WORKER SAY it was done? It is a substring
search over the worker's own output. It is an attestation and the module
header of shadow_probe is right to call it one.

This asks: does the ARTIFACT support the claim? The judge is shown the diff
and the command output. It is NOT shown the worker's prose, its DONE-CHECK
lines, its summary, or any sentence it wrote about its own work. That
exclusion is enforced in `evidence_for`, which builds the blob from `git` and
from probe results and never from the transcript -- so there is no path by
which a worker can talk its way to `met`, and the failure mode that produced
m-245777cf1467 ("Committed as f96c3ade. The task reaches DONE.") is not
reachable from here.

THE OBJECTION THIS OVERRULES, AND THE ANSWER TO IT. app.py said: "No model is
asked whether the work is good -- that would make Shadow the grader of its own
delegate." The guard was right; the scope was wrong. The decider and the
worker are different processes, different sessions, different context, and
the decider has no shell in the founder's repo at all -- a separation this
repo already pins with tests. A reviewer reading a diff they did not write is
not self-certification, it is review. What WOULD be self-certification is
grading the worker's ACCOUNT of the diff, and that is the thing `evidence_for`
makes impossible.

THREE ANSWERS, NOT TWO. `cannot_tell` is a first-class verdict and it is the
honest floor of the whole design: a judge with insufficient evidence must say
so, and the check stays the founder's. A judge that could only say met/unmet
would be a judge that guesses, and a guessing judge is worse than the
founder_confirm it replaced.
"""
import json
import os
import re
import subprocess
from collections import namedtuple

#: The three verdicts. `cannot_tell` is not a failure mode -- see the header.
VERDICTS = ("met", "unmet", "cannot_tell")

#: state is one of VERDICTS; reason is one line, for the ledger and the card.
Verdict = namedtuple("Verdict", "state reason")

#: How much evidence one judgement may carry. A diff longer than this is a
#: change too broad to judge as one check anyway, and the truncation is
#: ANNOUNCED in the blob so the judge can answer `cannot_tell` rather than
#: quietly judging a fragment.
EVIDENCE_MAX = 60000

#: Per-section ceiling, so one enormous file in a diff cannot crowd out the
#: command output that answers the check.
SECTION_MAX = 24000

#: Wall clock for the git reads that build the evidence.
GIT_TIMEOUT = 20

#: One line, for the record. Long enough to cite a hunk, short enough to read.
REASON_MAX = 400


def _git(root, args):
    """One read-only git command in `root`, or "" -- never raises.

    READ-ONLY BY CONSTRUCTION: every caller below passes a subcommand that
    reports. Nothing here writes, and `shell=False` means the argv is never
    parsed by anything.
    """
    try:
        proc = subprocess.run(                      # noqa: S603 -- fixed argv
            ["git"] + list(args), cwd=root, shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT)
    except Exception:                    # noqa: BLE001 -- no evidence, not fatal
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or b"").decode("utf-8", "replace")


def _clip(text, limit=SECTION_MAX):
    """Head-anchored, and the cut is ANNOUNCED. A diff reads top-down and the
    first hunks are the change; a silent truncation would let the judge treat
    a fragment as the whole change, which is exactly the judgement it must
    not make unknowingly."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + (
        "\n\n[... truncated at %d characters. You are seeing PART of this "
        "section. If the part you can see does not settle the check, answer "
        "cannot_tell.]" % limit)


def untracked_paths(status_text):
    """The `??` paths out of `git status --short`, in the order git gave them.

    THE BLIND SPOT, NAMED. A modified tracked file is already in the diff, so
    reading it again would spend the artifact budget on a duplicate. An
    UNTRACKED file appears in no diff at all -- git has nothing to compare it
    to -- so the entire content of a file the work just created is invisible.
    That is the MotoGP failure exactly, and this function is what finds those
    files so `shadow_evidence` can read them.

    A directory entry (`?? build/`) is skipped rather than walked: this lane
    reads files somebody named, never a tree it discovered.
    """
    out = []
    for raw in str(status_text or "").splitlines():
        if not raw.startswith("?? "):
            continue
        path = raw[3:].strip()
        # git quotes paths with unusual characters; an unquoted path is the
        # ordinary case and the quoted one is left alone rather than parsed
        # with a half-implementation of git's own escaping.
        if path.startswith('"') or not path or path.endswith("/"):
            continue
        out.append(path)
    return out


def _path_candidates(raw):
    """The entries of `artifact_paths` that are actually paths.

    THE SCREEN IS shadow_probe's OWN, and that is the point of it rather than
    a convenience. `artifact_paths` is the one new way into this module, so
    the strings it carries are held to exactly the rule a probe path is held
    to -- no `..` segment, no leading `~`, no NUL, within PROBE_PATH_MAX --
    by asking the validator the engine already trusts. A caller cannot widen
    what reaches the filesystem by passing a path through this door instead
    of through a probe.

    A REFUSED ENTRY IS DROPPED SILENTLY, which is the one place this lane does
    not report its refusals, and deliberately: everywhere else the thing
    refused is a FILE the judge might have needed, so silence would be
    evidence loss. Here the thing refused is a STRING THAT IS NOT A PATH, and
    echoing it into the blob to explain itself is the only way the worker's
    words could reach a judge through this parameter. Dropping it closes that
    and costs nothing -- there was no file behind it to lose.
    """
    out = []
    try:
        import shadow_probe
    except Exception:                    # noqa: BLE001 -- unscreened is unsafe
        return out
    for item in (raw or []):
        path = str(item or "").strip()
        if not path or path in out:
            continue
        if shadow_probe.validate_probe({"kind": "file_exists",
                                        "path": path}) is None:
            continue
        out.append(path)
    return out


def evidence_for(root, probe_lines=None, artifact_paths=None):
    """The blob a judge is shown: what the work DID, never what it SAID.

    Sources, and this list is exhaustive on purpose:
      * `git status --short`   -- which files moved at all
      * `git diff` (unstaged)  -- the change itself
      * `git diff --cached`    -- the staged half, when there is one
      * THE ARTIFACT          -- the content of files the work produced
      * probe_lines            -- reason lines from command probes already run

    THE ARTIFACT SOURCE (founder, 2026-09-20, second D-SH-1 pass) AND WHY IT
    IS NOT THE THING THIS MODULE FORBIDS. The three git reads can only show
    CHANGES TO TRACKED FILES. A task that creates a file -- a report, a list,
    a generated document, the whole authoring and research class of work --
    produced an artifact that appeared in no diff, so the judge was shown its
    filename and nothing else and correctly answered `cannot_tell` forever.
    Reading that file is the same act as reading `git diff`: both are the
    work itself. What stays forbidden is the worker's ACCOUNT of the work,
    and that distinction is the whole design, not a technicality.

    `artifact_paths` is what the CALLER names -- in practice the paths this
    mission's own probes point at. Untracked paths are added from git status
    here. Both go through shadow_evidence, which owns every boundary: 8 files,
    32 KiB each, 48 KiB total, no binaries, confinement via
    shadow_probe.resolve, and every refusal reported rather than silent.

    THE TRANSCRIPT IS NOT A SOURCE AND MUST NEVER BECOME ONE. Adding it would
    take one line and would silently convert this module from review into
    attestation; the header explains why that is the failure this exists to
    prevent. A future edit that threads the transcript in here should fail
    test_shadow_verification_lanes's `test_evidence_never_carries_worker_prose`
    -- which screens the PARAMETER NAMES, so a new source has to be a thing
    read from disk rather than a string somebody hands in.

    Returns "" when there is nothing to show, which the caller reads as
    `cannot_tell` rather than as `unmet`: no evidence is not counter-evidence.
    """
    root = os.path.expanduser(str(root or ""))
    parts = []
    paths = _path_candidates(artifact_paths)
    if root and os.path.isdir(root) and _git(root, ["rev-parse", "--git-dir"]):
        status = _git(root, ["status", "--short"])
        if status.strip():
            parts.append("FILES TOUCHED (git status --short):\n"
                         + _clip(status))
            # THE UNTRACKED PATHS ARE NOT ADDED (founder, 2026-09-21).
            # They used to be, and that was a cross-mission leak: git status
            # reports every uncommitted file in a SHARED workdir, so a judge
            # settling one mission's criterion could read another mission's
            # artifacts. `artifact_paths` is now the only way a file's
            # CONTENT reaches this blob, and the caller derives it from
            # shadow_paths.owned_artifacts.
            #
            # The status LISTING stays, because "these files changed" is a
            # genuine fact about the tree and the judge is told it is a
            # listing rather than this mission's output.
        unstaged = _git(root, ["diff"])
        if unstaged.strip():
            parts.append("THE CHANGE (git diff):\n" + _clip(unstaged))
        staged = _git(root, ["diff", "--cached"])
        if staged.strip():
            parts.append("THE CHANGE, STAGED (git diff --cached):\n"
                         + _clip(staged))
    if paths:
        try:
            import shadow_evidence
            artifact = shadow_evidence.render(root, paths)
        except Exception:                # noqa: BLE001 -- no artifact, not fatal
            artifact = ""
        if artifact:
            parts.append(artifact)
    for line in (probe_lines or []):
        text = str(line or "").strip()
        if text:
            parts.append("A CHECK SHADOW RAN:\n" + _clip(text, 2000))
    blob = "\n\n".join(parts)
    return blob[:EVIDENCE_MAX]


_PROMPT = """You are settling ONE completion check by reading evidence.

THE CHECK:
%(check)s

THE OUTCOME THE WORK WAS AIMED AT:
%(outcome)s

THE EVIDENCE. This is the work itself -- a diff, the content of the files the
work produced, and the output of commands that were actually run. It is
deliberately NOT anybody's description of the work, so there is nothing here
to take anyone's word for:

%(evidence)s

ANSWER WITH ONE FENCED JSON BLOCK AND NOTHING ELSE:

```json
{"verdict": "met" | "unmet" | "cannot_tell",
 "reason": "<one line, citing what in the evidence decided it>"}
```

HOW TO DECIDE:
  * "met" -- the evidence SHOWS the check holds. Point at the thing in it
    that shows this: a hunk, a filename, an exit code, a printed line.
  * "unmet" -- the evidence shows it does NOT hold. Also cite what.
  * "cannot_tell" -- the evidence does not settle it either way. This is a
    correct and expected answer and you must use it whenever it is true:
    the check needs a human's TASTE, or asks for a fact that exists only in
    the founder's head, or the evidence is truncated or missing at the part
    that mattered. Saying "cannot_tell" sends the check to the founder,
    which is right when you genuinely cannot tell.
    GUESSING IS THE ONLY WRONG ANSWER HERE.

DIFFICULTY IS NOT THE SAME AS NEEDING A HUMAN, and this is the distinction
the whole design rests on. A check that is long, compound, tedious to work
through, or about a subject you are unsure of is still YOURS to answer as
long as the evidence in front of you answers it. "cannot_tell" is for
questions with no answer in the evidence -- not for questions that are hard
work. Every "cannot_tell" you return becomes a button a human has to press,
so return it because the evidence is absent, never because the reading is
effortful.

A COMPOUND CHECK IS ANSWERED PART BY PART. When a check states several
properties joined by "and", work through them one at a time against the
evidence. If every part is settled by the evidence, answer met or unmet on
the whole. Answer "cannot_tell" ONLY for the parts the evidence genuinely
cannot reach, and say in your reason which part that was -- do not send the
whole check to a human because one clause of it was the hard one.

COUNT WITH THE `measured:` LINE, NOT BY EYE. Where the evidence carries a
`[measured: ...]` line for a file, those numbers were counted by machine.
Use them for anything about how many lines, how many distinct lines, or how
many are bullets, headings or numbered items. Your own count of a quoted
file is the less reliable number; prefer the measured one whenever they
disagree.

DO NOT re-word the check, do not negotiate its scope, do not judge whether it
was a good check, and do not judge anything other than the one check above.
An empty or missing evidence section means cannot_tell -- absence of evidence
is not evidence that the check failed.
"""

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S)


def render_prompt(check, evidence, outcome=""):
    """The judge's whole world. One check, one outcome, one evidence blob."""
    return _PROMPT % {
        "check": str(check or "").strip() or "(none)",
        "outcome": str(outcome or "").strip() or "(not stated)",
        "evidence": (evidence or "").strip()
                    or "(no evidence could be gathered)",
    }


def parse_verdict(text):
    """A Verdict, or None when the reply is not one.

    None IS NOT A VERDICT AND MUST NOT BECOME ONE. A caller that gets None
    leaves the check exactly as it found it -- founder's -- because a judge
    that returned nothing usable has said nothing, and "said nothing" must
    never read as "unmet" (which would drive the worker at a check that may
    already hold) or as "met" (which needs no explanation).
    """
    raw = None
    for body in _FENCE.findall(text or ""):
        try:
            raw = json.loads(body)
            break
        except ValueError:
            continue
    if raw is None:
        blob = (text or "").strip()
        start, end = blob.find("{"), blob.rfind("}")
        if start != -1 and end > start:
            try:
                raw = json.loads(blob[start:end + 1])
            except ValueError:
                return None
    if not isinstance(raw, dict):
        return None
    state = str(raw.get("verdict") or "").strip().lower()
    if state not in VERDICTS:
        return None
    reason = " ".join(str(raw.get("reason") or "").split())[:REASON_MAX]
    return Verdict(state, reason or "(no reason given)")
