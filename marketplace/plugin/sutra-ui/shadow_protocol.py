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

Blocks are stripped from the displayed reply. remember rows land UNCONFIRMED
(inert until the founder taps Confirm). SHADOW.md documents the same protocol
to the model; the fake claude in tests emits these blocks.

A `goal` block is a PROPOSAL, never a creation (slice 8): unlike `mission`,
nothing is written when it arrives. It is echoed back to the surface, the
founder reads and edits it in a confirmation card, and only their Confirm
POSTs to /api/shadow/goals. `done_when` is deliberately OPTIONAL here --
Shadow is told not to invent completion criteria it cannot honestly derive,
and the card makes the founder supply them rather than fabricating.
"""
import json
import re

_BLOCK = re.compile(r"```(mission|goal|chips|remember)\s*\n(.*?)```", re.S)


def parse_reply(text):
    """Returns (display_text, {mission?, goal?, chips?, remember?}).
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
                    checks.append({
                        "tier": c.get("tier") or "contains_artifact",
                        "check": str(c["check"]).strip()[:300]})
            out["goal"] = {"outcome": str(val["outcome"]).strip()[:500],
                           "done_when": checks,
                           "target_session": val.get("target_session") or None}
        elif kind == "chips" and isinstance(val, list) and val:
            out["chips"] = [str(c) for c in val][:3]
        elif kind == "remember" and isinstance(val, dict) \
                and val.get("text") and val.get("precedence") in \
                ("session", "project", "d_ledger", "taste", "history"):
            out["remember"] = val
        else:
            return match.group(0)
        return ""

    display = _BLOCK.sub(_eat, text or "").strip()
    display = _strip_governance_noise(display)
    return display, out


_NOISE = re.compile(
    r"^(\[[A-Z][A-Z0-9\u00b7\-]*\u00b7[^\]]*\]"      # H-Sutra headers
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
