"""The engine chooses the output for a brief itself (engine design 2.4, D129): a pure rule table, so there is no model call, no new J2
prompt and no waiting. The host decides once, before J2 is imported, when the owner left the output on `auto`:

    1 owner     the owner chose an output (the start page, the team's engine.json, data/engine.json): that one
    2 followup  `seed_output`: the brief continues a finished run, so the run keeps its output ("fix the bug in the form" on a website
                follow-up stays a website run)
    3 folder    a working folder is set and nothing above matched ("check the app and update the J2 prototype") -> project
    4 planner   nothing above matched: no output (None); J2's planner chooses the type from the brief (D165). There is no default type and no
                phrase list that names deliverables: "agents decide, code validates"

No word of the brief decides (D253): the project word table of D129 and D188 ("repository", "git", "source", "bug" and the like, once
`data/project.words.json`) is gone. It read "the source of truth" in a brief that asked for a whole agent as "edit my code", pinned the run to
project work, and so skipped the planner and every stage the brief deserved. Project work is reached by the owner's choice, by a follow-up of
a project run, or by a working folder; a brief with none of those goes to the planner, which can choose project work itself (D165).

`choose_output(brief, has_folder, seed_output, choice)` returns a `Selection(output, rule, reason)`. `reason` is a clause of plain words:
it goes into `<run>/output.json` and, for project work, into the run's chat ("... (a working folder is set and the request is about it;
choose another kind of result in the start page if that is wrong)"). `brief` is read by nobody here: it stays in the signature so every
caller and record keeps its shape, and so a later rule that reads it has its place.
"""
from typing import Optional

from .base import Selection
from .project import TYPE

__all__ = ["choose_output", "RULES", "chat_line"]

RULES = ("owner", "followup", "folder", "planner")


def choose_output(brief: str, has_folder: bool, seed_output: Optional[str] = None, choice: str = "auto") -> Selection:
    """The output for this brief. `choice` is what the settings say (`auto` leaves the decision to the table); `seed_output` is the
    output of the finished run this one continues, when there is one. The brief's words decide nothing (D253)."""
    if choice and choice != "auto":
        return Selection(choice, "owner", "you chose it")
    if seed_output:
        return Selection(seed_output, "followup", f"this continues an earlier {seed_output} run")
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
