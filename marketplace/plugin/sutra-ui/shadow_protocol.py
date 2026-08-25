"""The structured-reply protocol (GAP-AUDIT row 4; R6/R18/R19).

Shadow's replies may carry fenced blocks the app parses DETERMINISTICALLY:

    ```mission
    {"objective": "...", "template": "fix", "target_session": "s-1"}
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
"""
import json
import re

_BLOCK = re.compile(r"```(mission|chips|remember)\s*\n(.*?)```", re.S)


def parse_reply(text):
    """Returns (display_text, {mission?, chips?, remember?}). Malformed json
    in a block drops THAT block (kept in display so nothing is lost) and
    never raises."""
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
