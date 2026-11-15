"""The engine chooses the output for a brief itself (engine design 2.4, D129): a pure rule table, so there is no model call, no new J2
prompt and no waiting. The host decides once, before J2 is imported, when the owner left the output on `auto`:

    1 owner     the owner chose an output (the start page, the team's engine.json, data/engine.json): that one
    2 project   words that can only mean a project (repository, codebase, git, branch, commit, pull request, CLAUDE.md, the folder, refactor)
                -> project work, even when the brief continues an earlier run: a team whose first run was a website intake it never needed
                must not stay a website team for good
    3 followup  `seed_output`: the brief continues a finished run, so the run keeps its output ("fix the bug in the form" on a website
                follow-up stays a website run: "bug" and "source" are weak words, looked at after this rule)
    3b weak     the weak project words (bug, source) -> project work
    4 folder    a working folder is set and nothing above matched ("check the app and update the J2 prototype") -> project
    5 planner   nothing above matched: no output (None); J2's planner chooses the type from the brief (D165). There is no default type and no
                phrase list that names deliverables: "agents decide, code validates"

`choose_output(brief, has_folder, seed_output, choice)` returns a `Selection(output, rule, reason)`. `reason` is a clause of plain words:
it goes into `<run>/output.json` and, for project work, into the run's chat ("... (you asked about a repository; choose another kind of
result in the start page if that is wrong)"). The vocabulary of the first fix's route (the repository, code, folder, document and site
words) is data, `data/project.words.json` (D188, rule R-2: a decision leaves code), moved and not routed: it picks an output, it never sends a message
anywhere else. The file is read and checked once, when this module is imported; a bad file stops the engine by name. Its exit is a planner that can
choose a host type (D165).
"""
import json
import re
from typing import Optional

from .base import Selection
from .project import DATA, TYPE

__all__ = ["choose_output", "RULES", "STRONG_PROJECT_WORDS", "WEAK_REASONS", "WORDS_FILE", "load_words", "chat_line"]

RULE_PROJECT = "project"                         # a rule id of the table below, not an output type: the type is `project.TYPE`
RULES = ("owner", RULE_PROJECT, "followup", "weak", "folder", "planner")
WORDS_FILE = DATA / "project.words.json"
_WORD_KEYS = {"pattern", "reason", "weak"}


def load_words(path=WORDS_FILE) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """`((pattern, reason), ...)` in file order and the reasons of the weak entries, from a words file; ValueError (naming the file) when it is not
    `{"words": [{"pattern", "reason", "weak"?}]}` with patterns that compile and non-empty texts."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name}: cannot be read ({exc})") from None
    rows = data.get("words") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name}: needs a non-empty list `words`")
    words, weak = [], []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not _WORD_KEYS >= set(row) >= {"pattern", "reason"}:
            raise ValueError(f"{path.name}: words[{i}] must have pattern and reason (and may have weak)")
        pattern, reason = row["pattern"], row["reason"]
        if not isinstance(pattern, str) or not pattern.strip() or not isinstance(reason, str) or not reason.strip() \
                or not isinstance(row.get("weak", False), bool):
            raise ValueError(f"{path.name}: words[{i}] needs a pattern and a reason as text, and weak as true or false")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{path.name}: words[{i}].pattern does not compile ({exc})") from None
        words.append((pattern, reason))
        if row.get("weak"):
            weak.append(reason)
    return tuple(words), tuple(weak)


# (pattern, what the owner is told they asked about), in file order: whole words only, any case; the first one that matches names the reason.
STRONG_PROJECT_WORDS, WEAK_REASONS = load_words()        # WEAK_REASONS: words that name a project only when nothing continues an earlier run
_STRONG = tuple((re.compile(rf"(?<![\w.])(?:{pattern})(?![\w])", re.I), why) for pattern, why in STRONG_PROJECT_WORDS)


def _project_word(brief: str, *, weak: bool) -> Optional[str]:
    """The reason of the first project word of the kind asked for (`weak`: only the weak ones, else only the others)."""
    for pattern, why in _STRONG:
        if (why in WEAK_REASONS) == weak and pattern.search(brief):
            return why
    return None


def choose_output(brief: str, has_folder: bool, seed_output: Optional[str] = None, choice: str = "auto") -> Selection:
    """The output for this brief. `choice` is what the settings say (`auto` leaves the decision to the table); `seed_output` is the
    output of the finished run this one continues, when there is one."""
    if choice and choice != "auto":
        return Selection(choice, "owner", "you chose it")
    text = brief or ""
    why = _project_word(text, weak=False)
    if why:
        return Selection(TYPE, RULE_PROJECT, f"you asked about {why}")
    if seed_output:
        return Selection(seed_output, "followup", f"this continues an earlier {seed_output} run")
    why = _project_word(text, weak=True)
    if why:
        return Selection(TYPE, "weak", f"you asked about {why}")
    if has_folder:
        return Selection(TYPE, "folder", "a working folder is set and the request is about it")
    return Selection(None, "planner", "the team's planner chooses")


def chat_line(selection: Selection, has_folder: bool) -> Optional[str]:
    """The one `system` line for the run's chat, only when the result is project work (any other selection posts nothing, so every
    existing run keeps its events)."""
    if selection.output != TYPE:
        return None
    if selection.rule == "owner":
        return "Working on this as project work (you chose it in the start page or the settings)."
    if not has_folder:
        return (f"Treating this as project work ({selection.reason}), but no working folder is set yet. Choose one in Settings, under "
                "Connectors, in Working folder, or pick another kind of result in the start page.")
    return (f"Working on this as project work in your folder ({selection.reason}; choose another kind of result in the start page "
            "if that is wrong).")
