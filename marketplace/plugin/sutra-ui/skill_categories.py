"""What a skill DOES, not only where it came from.

The catalogue (skills_catalog.py) answers where a skill lives: its kind,
its source, its provider. None of those says what invoking it would do for
you, so 120 skills read as one alphabetical list.

This module adds the two fields the framework defines
(holding/plans/skills-program/FRAMEWORK.md):

    category  one of the seven, by PRIMARY EFFECT -- what would be missing
              if the skill were not invoked
    moment    when it may be invoked

    +---------+------------------------------------------+
    | Judge   | can it say no?                           |
    | Shape   | a plan, and no artifact of the final kind|
    | Make    | does something exist afterwards?         |
    | Say     | words only, never records?               |
    | Run     | needs a credential, a process, a browser?|
    | Know    | informs, decides nothing?                |
    | Mend    | does it start from a failure?            |
    +---------+------------------------------------------+

HOW A SKILL GETS ITS CATEGORY, in order:

    1. NAMED     an explicit entry below. Every skill Sutra ships is named,
                 because we know what ours do and a guess about our own
                 catalogue would be indefensible.
    2. RULED     a rule over the skill's own description, applied in a fixed
                 order, first match wins. Every rule is one readable line.
    3. KNOW      the fallback. A skill that names no effect informs; calling
                 it anything else would claim an effect nobody declared.

The fallback is deliberately the weakest category. A miscategorised skill
should read as "we do not know what this does", never as "this one judges".

The rules are ordered strongest-effect-first: a description that mentions
both running a browser and knowing a platform is Run, because the credential
is the thing that makes it different from a document.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

CATEGORIES = ("Judge", "Shape", "Make", "Say", "Run", "Know", "Mend")
MOMENTS = ("every-turn", "at-resolve", "before-mutation", "at-close", "on-ask")

#: The seven, each with the test a person can run against a description.
CATEGORY_TEST = {
    "Judge": "Can it say no?",
    "Shape": "Does it output a plan, and no artifact of the final kind?",
    "Make": "Does a file or change exist afterwards that did not before?",
    "Say": "Does it change words only, never records?",
    "Run": "Does it need a credential, a process or a browser?",
    "Know": "Does it decide nothing, and only inform?",
    "Mend": "Does it start from a failure?",
}

# ── 1. NAMED ────────────────────────────────────────────────────────────────
# Everything Sutra ships, plus the third-party skills whose primary effect the
# description understates. Keyed by the skill's own name, lower-cased.

NAMED: Dict[str, Tuple[str, str]] = {
    # ours: the per-turn governance floor
    "input-routing": ("Judge", "every-turn"),
    "depth-estimation": ("Judge", "every-turn"),
    "human-sutra": ("Judge", "every-turn"),
    "blueprint": ("Judge", "before-mutation"),
    "cynefin": ("Judge", "at-resolve"),
    "skill-resolution": ("Judge", "at-resolve"),
    "sutra-capability": ("Judge", "on-ask"),
    "prd-discipline": ("Judge", "before-mutation"),
    # ours: the spine that decides the shape of the work
    "flow": ("Shape", "at-resolve"),
    "lens": ("Shape", "at-resolve"),
    "workflow-type-resolve": ("Shape", "at-resolve"),
    "workflow": ("Shape", "at-resolve"),
    "architect": ("Shape", "at-resolve"),
    "incremental-architect": ("Shape", "at-resolve"),
    "test-strategy": ("Shape", "at-resolve"),
    "updating-canon": ("Shape", "before-mutation"),
    # ours: the ones that leave a file behind
    "writing-adr": ("Make", "on-ask"),
    "writing-engine-charter": ("Make", "on-ask"),
    "writing-llm-md": ("Make", "before-mutation"),
    "native-author-part": ("Make", "on-ask"),
    "deterministic-testing": ("Make", "on-ask"),
    # ours: words only
    "writing-style": ("Say", "every-turn"),
    "output-trace": ("Say", "at-close"),
    "skill-explain": ("Say", "on-ask"),
    "caveman": ("Say", "every-turn"),
    "anti-glaze-tone": ("Say", "every-turn"),
    "readability-gate": ("Say", "every-turn"),
    # ours: the two review lanes -- they can refuse a diff, so they judge
    "codex-sutra": ("Judge", "before-mutation"),
    "deepseek": ("Judge", "before-mutation"),
    # ours: informs
    "domains": ("Know", "on-ask"),
    "founder-360-review": ("Know", "on-ask"),
    "sutra-learn": ("Know", "on-ask"),
    # third party whose description hides the effect
    "brainstorming": ("Shape", "at-resolve"),
    "writing-plans": ("Shape", "at-resolve"),
    "executing-plans": ("Shape", "at-resolve"),
    "subagent-driven-development": ("Shape", "at-resolve"),
    "dispatching-parallel-agents": ("Shape", "at-resolve"),
    "using-superpowers": ("Shape", "every-turn"),
    "test-driven-development": ("Make", "before-mutation"),
    "writing-skills": ("Make", "on-ask"),
    "skill-creator": ("Make", "on-ask"),
    "plugin-creator": ("Make", "on-ask"),
    "writing-hookify-rules": ("Make", "on-ask"),
    "verification-before-completion": ("Judge", "at-close"),
    "requesting-code-review": ("Judge", "at-close"),
    "receiving-code-review": ("Judge", "at-close"),
    "code-review": ("Judge", "at-close"),
    "security-review": ("Judge", "at-close"),
    "review-agent": ("Judge", "at-close"),
    "react-best-practices": ("Judge", "at-close"),
    "systematic-debugging": ("Mend", "at-resolve"),
    "diagnosing-superpowers": ("Mend", "on-ask"),
    "finishing-a-development-branch": ("Mend", "at-close"),
    "next-upgrade": ("Mend", "on-ask"),
    "using-git-worktrees": ("Run", "before-mutation"),
    "claude-in-chrome": ("Run", "on-ask"),
    "run": ("Run", "at-close"),
    "schedule": ("Run", "on-ask"),
    "loop": ("Run", "on-ask"),
    "frontend-design": ("Shape", "at-resolve"),
    "dataviz": ("Shape", "before-mutation"),
    "artifact-design": ("Shape", "before-mutation"),
    "artifact-diagramming": ("Shape", "before-mutation"),
    "artifact-capabilities": ("Know", "before-mutation"),
    "workflow-authoring": ("Know", "before-mutation"),
    "claude-api": ("Know", "before-mutation"),
    "openai-docs": ("Know", "on-ask"),
    "knowledge-update": ("Know", "every-turn"),
    "imagegen": ("Make", "on-ask"),
    "docx": ("Make", "on-ask"),
    "pdf": ("Make", "on-ask"),
    "pptx": ("Make", "on-ask"),
    "xlsx": ("Make", "on-ask"),
    "init": ("Make", "on-ask"),
    "skill-installer": ("Run", "on-ask"),
}

# ── 2. RULED ────────────────────────────────────────────────────────────────
# Ordered strongest-effect-first; first match wins. Each entry is
# (category, moment, a compiled test over the description).
# Keep every pattern to one readable line: a rule nobody can read is a guess.

_RULES = [
    # Mend: it starts from something already broken
    ("Mend", "at-resolve",
     r"\b(incident|postmortem|post-mortem|rollback|recover|root cause|troubleshoot|"
     r"debug|diagnos|repair|restore|fix a|failing|flaky|regression)\b"),
    # Run: a credential, a process, a browser, a deployment
    ("Run", "on-ask",
     r"\b(deploy|deployment|cli|browser|playwright|screenshot|credential|token|"
     r"oauth|environment variable|install|uninstall|launch|run the|git (commit|branch|push)|"
     r"provision|sandbox|server|dashboard)\b"),
    # Judge: it can refuse
    ("Judge", "at-close",
     r"\b(review|refus|reject|gate|verif|validate|audit|lint|approve|pass/fail|"
     r"before (you|any) (commit|merg)|check that)\b"),
    # Make: something exists afterwards
    ("Make", "on-ask",
     r"\b(create|creates|generate|generates|scaffold|author|writes? (a|an|the)|"
     r"produce|build a|render|export|draft)\b"),
    # Shape: a plan and nothing else
    ("Shape", "at-resolve",
     r"\b(plan|planning|strategy|design (a|the|guidance)|architect|decide how|"
     r"break (it|the work) down|prioriti|roadmap|brainstorm)\b"),
    # Say: words only
    ("Say", "on-ask",
     r"\b(tone|phrasing|style|wording|write the (message|update|comms)|"
     r"summariz|summaris|explain to|communicat)\b"),
]

_COMPILED = [(c, m, re.compile(p, re.I)) for c, m, p in _RULES]


def classify(entry) -> Tuple[str, str, str]:
    """(category, moment, how) for one catalogue entry.

    `how` is "named", "ruled:<category>" or "fallback", so a screen or a test
    can tell a decision from a guess. Nothing here mutates the entry.
    """
    name = str((entry or {}).get("name") or "").strip().lower()
    if name in NAMED:
        cat, moment = NAMED[name]
        return cat, moment, "named"
    desc = str((entry or {}).get("description") or "")
    for cat, moment, rx in _COMPILED:
        if rx.search(desc):
            return cat, moment, "ruled"
    return "Know", "on-ask", "fallback"


def annotate(items):
    """Add category/moment/how to every row, in place, and return the counts.

    Returns {"by_category": {...}, "by_moment": {...}, "by_how": {...}}.
    """
    by_cat, by_moment, by_how = {}, {}, {}
    for e in items or []:
        cat, moment, how = classify(e)
        e["category"] = cat
        e["moment"] = moment
        e["category_how"] = how
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_moment[moment] = by_moment.get(moment, 0) + 1
        by_how[how] = by_how.get(how, 0) + 1
    return {"by_category": by_cat, "by_moment": by_moment, "by_how": by_how}
