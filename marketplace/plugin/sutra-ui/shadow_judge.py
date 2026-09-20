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


def evidence_for(root, probe_lines=None):
    """The blob a judge is shown: what the work DID, never what it SAID.

    Sources, and this list is exhaustive on purpose:
      * `git status --short`   -- which files moved at all
      * `git diff` (unstaged)  -- the change itself
      * `git diff --cached`    -- the staged half, when there is one
      * probe_lines            -- reason lines from command probes already run

    THE TRANSCRIPT IS NOT A SOURCE AND MUST NEVER BECOME ONE. Adding it would
    take one line and would silently convert this module from review into
    attestation; the header explains why that is the failure this exists to
    prevent. A future edit that threads the transcript in here should fail
    test_shadow_judge's `test_evidence_never_carries_worker_prose`.

    Returns "" when there is nothing to show, which the caller reads as
    `cannot_tell` rather than as `unmet`: no evidence is not counter-evidence.
    """
    root = os.path.expanduser(str(root or ""))
    parts = []
    if root and os.path.isdir(root) and _git(root, ["rev-parse", "--git-dir"]):
        status = _git(root, ["status", "--short"])
        if status.strip():
            parts.append("FILES TOUCHED (git status --short):\n"
                         + _clip(status))
        unstaged = _git(root, ["diff"])
        if unstaged.strip():
            parts.append("THE CHANGE (git diff):\n" + _clip(unstaged))
        staged = _git(root, ["diff", "--cached"])
        if staged.strip():
            parts.append("THE CHANGE, STAGED (git diff --cached):\n"
                         + _clip(staged))
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

THE EVIDENCE. This is the work itself -- a diff, and the output of commands
that were actually run. It is deliberately NOT anybody's description of the
work, so there is nothing here to take anyone's word for:

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
    the check needs a human's taste, or the evidence is truncated at the
    part that mattered, or it is about something no diff can show. Saying
    "cannot_tell" sends the check to the founder, which is right when you
    genuinely cannot tell. GUESSING IS THE ONLY WRONG ANSWER HERE.

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
