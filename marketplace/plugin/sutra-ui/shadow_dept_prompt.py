"""shadow_dept_prompt.py -- the words of the create-or-reuse question (PRD amendment A5, A5.3.1).

Text and card builders only; shadow_dept builds the facts and parses the answer. Nothing here names a kind of department: the
kinds and their use cases are data the caller passes in."""

VERSION = "1"

RULES = """Decide whether this task belongs to a department the organisation already has, needs a new one, or needs none.

- Reuse the best candidate when its goal covers the task ("use").
- Create a department only when no candidate's goal covers the task ("create"), and choose its kind by the use case listed
  for it below.
- Answer "none" when the task needs no department.
- A department that is Off or blocked is still a candidate; say so in your reason if you choose it.
- Give one sentence of reason, and how sure you are (low, medium or high).

Reply with ONE JSON object and nothing else:
{"action": "use" | "create" | "none",
 "ref": <the candidate's ref when action is use, else null>,
 "kind": <a kind from the list when action is create, else null>,
 "name": <a short name when action is create, else null>,
 "goal": <what the new department is for, in the owner's words, when action is create, else null>,
 "done_items": [<up to a few lines saying when it is done; only when action is create>],
 "reason": <one sentence>,
 "confidence": "low" | "medium" | "high"}
"""


def card(c):
    """One candidate as the lines the model reads."""
    flags = [w for w, on in (("Off", c.get("stopped")), ("blocked", c.get("blocked"))) if on]
    head = "- ref %s | %s | kind %s | %s%s" % (c.get("ref"), c.get("name"), c.get("kind"), c.get("state"),
                                              (" | " + ", ".join(flags)) if flags else "")
    lines = [head, "  goal: %s" % (c.get("goal") or "(none)")]
    if c.get("done"):
        lines.append("  done when: %s" % c["done"])
    if c.get("last_activity"):
        lines.append("  last active: %s" % c["last_activity"])
    return "\n".join(lines)


def render(facts):
    """The whole question: the instructions, then the task, the candidate cards, the kinds with their use cases, and the rules."""
    cands = facts.get("candidates") or []
    kinds = facts.get("kinds") or {}
    rules = facts.get("rules") or []
    out = [RULES, "TASK", facts.get("words") or "(no words)", "", "DEPARTMENTS THIS ORGANISATION HAS"]
    out += [card(c) for c in cands] or ["(none)"]
    out += ["", "KINDS A NEW DEPARTMENT MAY BE"]
    out += ["- %s: %s" % (k, u) for k, u in kinds.items()] or ["(none)"]
    out += ["", "THE OWNER'S RULES"]
    out += ["- (%s) %s" % (r.get("tag"), r.get("line")) for r in rules] or ["(none)"]
    return "\n".join(out)
