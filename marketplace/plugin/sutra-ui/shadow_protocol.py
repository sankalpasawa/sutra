"""The structured-reply protocol (GAP-AUDIT row 4; R6/R18/R19).

Shadow's replies may carry fenced blocks the app parses DETERMINISTICALLY:

    ```mission
    {"objective": "...", "template": "fix", "target_session": "s-1"}
    ```
    ```goal
    {"outcome": "...", "done_when": [{"tier": "contains_artifact", "check": "..."}]}
    ```
    ```chips
    ["Review the brief", "Stop mission"]
    ```
    ```remember
    {"text": "...", "precedence": "taste"}
    ```
    ```module
    {"name": "...", "kind": "chat"}
    ```

Blocks are stripped from the displayed reply. remember rows land UNCONFIRMED
(inert until the founder taps Confirm). SHADOW.md documents the same protocol
to the model; the fake claude in tests emits these blocks.

A `goal` block is a PROPOSAL, never a creation (slice 8): unlike `mission`,
nothing is written when it arrives. It is echoed back to the surface, the
founder reads and edits it in a confirmation card, and only their Confirm
POSTs to /api/shadow/goals. `done_when` is deliberately OPTIONAL here --
Shadow is told not to invent completion criteria it cannot honestly derive,
and the card makes the founder supply them rather than fabricating.

A `module` fence creates an app (Org > Apps) immediately as a draft -- see
the D-M10 note in parse_reply.

HISTORY, so this merge is not undone again: the goal fence and the tier
contract landed in 051b130 (2026-09-11); the module fence landed the same day
from a working copy that predated that commit and replaced the file, which
dropped both (test_proposal_tiers, test_goal_creation went red while app.py
kept handling `blocks["goal"]`). Both fences are load-bearing; keep both.
"""
import json
import re

_BLOCK = re.compile(r"```(mission|goal|chips|remember|module)\s*\n(.*?)```", re.S)

# A `module` fence creates a module (Org > Modules). Kinds mirror
# modules_api.KINDS; kept literal here so the parser stays import-free.
_MODULE_KINDS = ("chat", "page", "link")


# ---------------------------------------------------- the tier contract ---
# WHY THIS EXISTS (live flight, goal g-d804849d1400, 2026-09-11). Shadow
# proposed two checks under `contains_artifact`:
#
#   "An explicit winner named as the final choice -- the word 'Python' or
#    'Go' stated as the pick, not a 'depends' or 'both work' hedge"
#   "Three distinct concrete reasons listed for that pick, each tied to a
#    specific tradeoff ... rather than generic praise"
#
# `contains_artifact` is a LITERAL SUBSTRING TEST (mission_engine:284) and
# always will be -- it is the one tier with no judgement in it. A criterion
# DESCRIPTION can never appear verbatim in a transcript, so both checks were
# structurally unsatisfiable. The chat answered perfectly ("## Winner:
# **Python**", three reasons); both checks still read False, the unmet list
# never changed, the follow-up say repeated itself and the ping-pong guard
# correctly stopped the attempt. Nothing was broken except the contract.
#
# SHADOW.md already says contains_artifact is "a string that must appear in
# the chat". The model had the right instruction and produced the wrong
# thing, so the boundary enforces it rather than asking again.
#
# THE RULE: a proposal's tier is ADVISORY. What decides is the SHAPE of the
# check, and a check that is not literal-shaped becomes founder_confirm --
# kept, never dropped, and answerable by the one party who can judge it.

#: what a Shadow PROPOSAL may end up carrying. `verify` is deliberately
#: absent: evaluate_done_when scores it with an injected verifier, and NO
#: production caller passes one (_start_goal_attempt omits it), so a
#: `verify` check is unsatisfiable by anyone. Proposing it would be the same
#: bug wearing a different label. Restore it here when a verifier is wired.
PROPOSAL_TIERS = ("contains_artifact", "founder_confirm")

#: when machine-checking is not available, the founder is
FALLBACK_TIER = "founder_confirm"

#: a literal artifact is a MARKER, not a sentence: short, few words, and
#: free of the punctuation and vocabulary that only appear when someone is
#: DESCRIBING a requirement rather than quoting one.
_ARTIFACT_MAX_CHARS = 60
_ARTIFACT_MAX_WORDS = 8
_CRITERION_MARKER = re.compile(
    "(—|–"              # em/en dash: introduces an aside
    "|\\b(?:not|rather|instead|each|either|such as|e\\.g\\.|etc"
    "|distinct|concrete|explicit(?:ly)?|genuine|generic|appropriate"
    "|relevant|valid|reasonable|must|should|listed|stated|named"
    "|tied|hedge|at least|no more than)\\b)", re.I)


def is_literal_artifact(check):
    """Could this string plausibly appear VERBATIM in a transcript?

    Deterministic and deliberately conservative: every false negative costs
    one founder sign-off, while a false positive is the unsatisfiable check
    this whole function exists to prevent. Erring toward the founder is the
    cheap direction.
    """
    s = str(check or "").strip()
    if not s or len(s) > _ARTIFACT_MAX_CHARS:
        return False
    if len(s.split()) > _ARTIFACT_MAX_WORDS:
        return False
    return _CRITERION_MARKER.search(s) is None


def tier_for(check, proposed=None):
    """The tier a proposed check ACTUALLY gets.

    `proposed` is what Shadow asked for and is never trusted on its own: an
    unknown tier, `verify`, or a missing tier all resolve deterministically
    rather than being passed through. Only `contains_artifact` on a
    literal-shaped string survives as machine-checkable; everything else
    keeps its wording and becomes the founder's to confirm.
    """
    want = str(proposed or "").strip()
    if want == "contains_artifact" and is_literal_artifact(check):
        return "contains_artifact"
    if want == FALLBACK_TIER:
        return FALLBACK_TIER
    # missing, `verify`, unknown, or a semantic string under
    # contains_artifact -- all one answer, and it is never "drop the check"
    return FALLBACK_TIER


def parse_reply(text):
    """Returns (display_text, {mission?, goal?, chips?, remember?, module?}).
    Malformed json in a block drops THAT block (kept in display so nothing
    is lost) and never raises."""
    out = {}

    def _eat(match):
        kind, body = match.group(1), match.group(2)
        try:
            val = json.loads(body)
        except ValueError:
            return match.group(0)      # malformed: leave visible, honest
        # STRICT validation (deepseek fold): a block that does not meet its
        # shape stays VISIBLE in the reply -- an invalid instruction must
        # never become an invisible side effect.
        if kind == "mission" and isinstance(val, dict) \
                and val.get("objective") and val.get("template") in \
                ("feature", "fix", "research", "watch"):
            out["mission"] = val
        elif kind == "goal" and isinstance(val, dict) \
                and str(val.get("outcome") or "").strip():
            # An OUTCOME is the only hard requirement. done_when is kept
            # only when it is a list of usable check rows -- anything else
            # is dropped rather than coerced, so the card can say "Shadow
            # could not determine completion criteria" instead of showing
            # something Shadow did not actually mean.
            checks = []
            for c in (val.get("done_when") or []):
                if isinstance(c, dict) and str(c.get("check") or "").strip():
                    text = str(c["check"]).strip()[:300]
                    tier = tier_for(text, c.get("tier"))
                    row = {"tier": tier, "check": text}
                    if tier != c.get("tier"):
                        # what the card tells the founder, so a re-tier is
                        # visible rather than a silent correction
                        row["proposed_tier"] = c.get("tier") or None
                    checks.append(row)
            out["goal"] = {"outcome": str(val["outcome"]).strip()[:500],
                           "done_when": checks,
                           "target_session": val.get("target_session") or None}
        elif kind == "chips" and isinstance(val, list) and val:
            out["chips"] = [str(c) for c in val][:3]
        elif kind == "remember" and isinstance(val, dict) \
                and val.get("text") and val.get("precedence") in \
                ("session", "project", "d_ledger", "taste", "history"):
            out["remember"] = val
        elif kind == "module" and isinstance(val, dict) \
                and isinstance(val.get("name"), str) and val.get("name").strip() \
                and (val.get("kind") or "chat") in _MODULE_KINDS:
            # D-M10 (2026-09-08): the app creates the module IMMEDIATELY as a
            # draft -- stronger than mission (brief_confirm) and remember
            # (unconfirmed). Deliberate: a draft module runs nothing until the
            # operator opens it, and archive is one click.
            out["module"] = val
        else:
            return match.group(0)
        return ""

    display = _BLOCK.sub(_eat, text or "").strip()
    display = _strip_governance_noise(display)
    return display, out


_NOISE = re.compile(
    r"^(\[[A-Z][A-Z0-9·\-]*·[^\]]*\]"      # H-Sutra headers
    r"|(INPUT|TYPE|EXISTING HOME|ROUTE|FIT CHECK|ACTION|TASK|DEPTH"
    r"|EFFORT|COST|IMPACT|PLACEMENT|FLOW|TRIAGE|ESTIMATE|ACTUAL|OS):.*"
    r")\s*$", re.M)


def _strip_governance_noise(text):
    """Belt to SHADOW.md's braces: the user-scope CLAUDE.md trains the model
    to emit per-turn governance blocks in every workdir. The persona forbids
    them; anything that leaks is stripped line-wise so the founder reads an
    answer, not scaffolding."""
    lines = [l for l in (text or "").splitlines()
             if not _NOISE.match(l.strip())]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
