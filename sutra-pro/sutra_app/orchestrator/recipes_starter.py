"""The starter recipes (DV-3): four read-only recipes that ship with the app, in code. They are not rows: nobody can change or delete them, a copy is an ordinary recipe of the owner's, and with
the switch off they do not exist. Words are plain; every one of them only reads unless it says it writes a new file."""
from __future__ import annotations

from typing import Any

__all__ = ["STARTERS", "starter_id"]

NEVER_CHANGE = ["Do not change, create or delete any file in the folder.", "Do not run anything that changes the folder."]


def starter_id(slug: str) -> str:
    return f"starter-{slug}"


STARTERS: dict[str, dict[str, Any]] = {
    starter_id("review-my-last-commits"): {
        "title": "Review my last commits",
        "body": {
            "overview": "Read the most recent commits in your folder and say what looks wrong or risky. Nothing is changed.",
            "procedure": ["Look at the last $1 commits in the folder (read only).", "For each one, say in a sentence what it changed.",
                          "List anything that looks like a bug, a risk or a missing test, with the file and the line.", "Give the list with the most serious first."],
            "specifications": ["Read only: this recipe never changes a file."],
            "advice": ["If a commit is too big to follow, say so instead of guessing."],
            "forbidden": list(NEVER_CHANGE),
            "needs": [{"label": "How many commits to look at (a number, for example 10)"}],
        },
    },
    starter_id("weekly-folder-health"): {
        "title": "Weekly folder health",
        "body": {
            "overview": "A short report on how your folder is doing: what changed this week and anything odd.",
            "procedure": ["List what changed in the last 7 days (read only).", "Point out very big files, folders nobody has touched for a long time, and files whose purpose is not clear.",
                          "Give three things that would be worth tidying, with the reason for each."],
            "specifications": ["Keep it to one page."],
            "advice": ["Say what is fine too, not only what is wrong."],
            "forbidden": list(NEVER_CHANGE),
            "needs": [],
        },
    },
    starter_id("write-release-notes"): {
        "title": "Write release notes",
        "body": {
            "overview": "Turn recent work into short release notes for the people who use the app.",
            "procedure": ["Read the commits since $1.", "Group the changes under New, Better and Fixed.", "Write each change as one plain sentence with no jargon and no file names.",
                          "Put the notes in a new file called release-notes-draft.md in the folder."],
            "specifications": ["Write for someone who has never seen the code."],
            "advice": ["Leave out changes nobody outside the team would notice."],
            "forbidden": ["Do not change any existing file.", "Do not overwrite release-notes-draft.md if it is already there: ask first."],
            "needs": [{"label": "Where to start from (a version, a date or a commit)"}],
        },
    },
    starter_id("explain-this-folder"): {
        "title": "Explain this folder",
        "body": {
            "overview": "A plain guide to what is in your folder and how its parts fit together.",
            "procedure": ["List the main parts of the folder and say in a sentence what each one is for.", "Say how the parts depend on each other.",
                          "Say how to start it, test it and build it, if the folder says so.", "Name the three files someone new should read first."],
            "specifications": ["Every claim names the file it came from."],
            "advice": ["If something is not clear from the files, say so instead of guessing."],
            "forbidden": list(NEVER_CHANGE),
            "needs": [],
        },
    },
}
