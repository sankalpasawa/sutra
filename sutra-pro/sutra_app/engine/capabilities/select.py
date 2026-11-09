"""The engine chooses the output for a brief itself (engine design 2.4, D129): a pure rule table, so there is no model call, no new J2
prompt and no waiting. The host decides once, before J2 is imported, when the owner left the output on `auto`:

    1 owner     the owner chose an output (the start page, the team's engine.json, data/engine.json): that one
    2 project   words that can only mean a project (repository, codebase, git, branch, commit, pull request, CLAUDE.md, the folder, refactor)
                -> project work, even when the brief continues an earlier run: a team whose first run was a website intake it never needed
                must not stay a website team for good
    3 followup  `seed_output`: the brief continues a finished run, so the run keeps its output ("fix the bug in the form" on a website
                follow-up stays a website run: "bug" and "source" are weak words, looked at after this rule)
    3b weak     the weak project words (bug, source) -> project work
    4 deliver   a make-a-deliverable phrase (write, draft, build, design ... a PRD, HLD, LLD, website or landing page, or "a website for ...") -> website,
                J2's default; J2's own `detect_documents` still plans the documents exactly as it does today
    5 folder    a working folder is set and nothing above matched ("check the app and update the J2 prototype") -> project
    6 default   website: what a team with no folder and no project words has always got

`choose_output(brief, has_folder, seed_output, choice)` returns a `Selection(output, rule, reason)`. `reason` is a clause of plain words:
it goes into `<run>/output.json` and, for project work, into the run's chat ("... (you asked about a repository; choose another kind of
result in the start page if that is wrong)"). The vocabulary of the first fix's route (the repository, code, folder, document and site
words) lives here, moved and not routed: it picks an output, it never sends a message anywhere else.
"""
import re
from typing import Optional

from .base import Selection

__all__ = ["choose_output", "RULES", "STRONG_PROJECT_WORDS", "chat_line"]

RULES = ("owner", "project", "followup", "weak", "deliver", "folder", "default")
WEAK_REASONS = ("a bug", "the source")           # words that name a project only when nothing continues an earlier run

# (pattern, what the owner is told they asked about). Whole words only, any case. The first one that matches names the reason.
STRONG_PROJECT_WORDS = (
    (r"repositor(?:y|ies)|repos?", "a repository"),
    (r"code\s?bases?|source\s+code", "the codebase"),
    (r"pull\s+requests?|merge\s+requests?", "a pull request"),
    (r"git|branch(?:es)?|commits?|committ?ed|diffs?", "git"),
    (r"CLAUDE\.md|AGENTS\.md", "the project's instructions file"),
    (r"(?:the|my|our|this)\s+(?:working\s+|project\s+)?folder|working\s+folder", "your folder"),
    (r"(?:the|my|our)\s+(?:app|application|project|site|website|product)(?:'s|s'?)?\s+(?:code|source)", "the app's code"),
    (r"source", "the source"),
    (r"refactor(?:s|ed|ing)?", "a refactor"),
    (r"bugs?", "a bug"),
)
_STRONG = tuple((re.compile(rf"(?<![\w.])(?:{pattern})(?![\w])", re.I), why) for pattern, why in STRONG_PROJECT_WORDS)

_VERBS = r"(?:write|draft|create|make|produce|generate|build|design)"
_THINGS = r"(?:PRDs?|HLDs?|LLDs?|web\s?sites?|sites?|landing\s+pages?|web\s?pages?)"
# "build a florist site" and also the noun phrase the start page's own examples use: "A website for my cafe", "a PRD for a clinic app"
_DELIVER = re.compile(rf"\b{_VERBS}\b[^.!?\n]{{0,60}}?\b{_THINGS}\b|\b(?:a|an|the|my|our)\s+(?:[\w'-]+\s+){{0,3}}?{_THINGS}\s+(?:for|about|of)\b", re.I)


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
        return Selection("project", "project", f"you asked about {why}")
    if seed_output:
        return Selection(seed_output, "followup", f"this continues an earlier {seed_output} run")
    why = _project_word(text, weak=True)
    if why:
        return Selection("project", "weak", f"you asked about {why}")
    if _DELIVER.search(text):
        return Selection("website", "deliver", "you asked for a document or a site to be made")
    if has_folder:
        return Selection("project", "folder", "a working folder is set and the request is about it")
    return Selection("website", "default", "no working folder is set and the request names no project")


def chat_line(selection: Selection, has_folder: bool) -> Optional[str]:
    """The one `system` line for the run's chat, only when the result is project work (a website selection posts nothing, so every
    existing run keeps its events)."""
    if selection.output != "project":
        return None
    if selection.rule == "owner":
        return "Working on this as project work (you chose it in the start page or the settings)."
    if not has_folder:
        return (f"Treating this as project work ({selection.reason}), but no working folder is set yet. Choose one in Settings, under "
                "Connectors, in Working folder, or pick another kind of result in the start page.")
    return (f"Working on this as project work in your folder ({selection.reason}; choose another kind of result in the start page "
            "if that is wrong).")
