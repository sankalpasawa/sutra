"""Recipes (Devin parity DV-3, docs/design/devin-parity.md; SUTRA_RECIPES_V1): a way of working the owner saves and starts again.

A recipe has a title and a body of six parts, in the owner's words:

    overview        what it is for (one short paragraph)
    procedure       the steps, in order (up to 30 lines)
    specifications  what the result must be like (up to 20 lines)
    advice          things worth knowing (up to 20 lines)
    forbidden       what must never be done (up to 20 lines)
    needs           the blanks the owner fills when starting: `$1` .. `$9` in any text stand for them, in order

It is a recipe, not a script: starting one writes a REQUEST in plain words, and the request goes the way any request goes (the chat agent plans it again, the plan gate asks what it asks, the owner's access
caps what a step may touch). Nothing is frozen and nothing skips a question. Only the owner writes, changes or imports a recipe: a model never saves one (a draft from a finished project is made by code and
is only a draft), and an imported file comes back as a draft the owner reads before saving. Every line passes the note gate (`owner_words.refusal`): no key, token or password is ever kept.

The words of a recipe only ever grow: each change is a new row of `recipe_versions` (the triggers forbid update and delete), a revert is a new version that copies an old one. One `db.tx()` per write.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from typing import Any

from sutra_app.library.practice import clean_text
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.owner_words import refusal
from sutra_app.orchestrator.recipes_starter import STARTERS

__all__ = ["RecipeService", "clean_body", "parse_markdown", "to_markdown", "TITLE_MAX", "LINE_MAX", "OVERVIEW_MAX", "REQUEST_MAX", "SECTION_LIMITS"]

TITLE_MAX = 80
LINE_MAX = 300
OVERVIEW_MAX = 600
BLANK_MAX = 9
BLANK_VALUE_MAX = 300
REQUEST_MAX = 7900                       # a chat line holds 8000 characters
SECTION_LIMITS = {"procedure": 30, "specifications": 20, "advice": 20, "forbidden": 20}
_BLANK = re.compile(r"\$([1-9])")
_ID = re.compile(r"^rcp_[0-9a-f]{12}$")
_STARTER = re.compile(r"^starter-[a-z0-9-]{1,60}$")


def _line(text: Any, limit: int, redact: Callable[[str], str] | None, what: str) -> str:
    if not isinstance(text, str):
        raise AppError("validation", f"{what} is text")
    line = clean_text(text)
    why = refusal(line, redact, limit=limit)
    if why is not None:
        raise AppError("validation", f"{what}: {why}")
    return line


def clean_body(raw: Any, redact: Callable[[str], str] | None = None) -> dict[str, Any]:
    """The body of a recipe, checked and cleaned (white space collapsed, every line through the note gate), or an AppError `validation` in plain words. A blank `$n` that names a need the recipe does not
    have is refused. Nothing is silently dropped: a line that is too long or looks like a secret is the owner's to fix."""
    if not isinstance(raw, dict):
        raise AppError("validation", "A recipe is made of its parts")
    unknown = set(raw) - {"overview", "procedure", "specifications", "advice", "forbidden", "needs"}
    if unknown:
        raise AppError("validation", "A recipe has an overview, a procedure, specifications, advice, things never to do and what it needs from you, and nothing else")
    body: dict[str, Any] = {"overview": _line(raw.get("overview", ""), OVERVIEW_MAX, redact, "The overview") if raw.get("overview", "") else ""}
    for part, limit in SECTION_LIMITS.items():
        items = raw.get(part, [])
        if not isinstance(items, list) or len(items) > limit:
            raise AppError("validation", f"“{part}” is a list of at most {limit} lines")
        body[part] = [_line(item, LINE_MAX, redact, f"A line of {part}") for item in items]
    needs = raw.get("needs", [])
    if not isinstance(needs, list) or len(needs) > BLANK_MAX:
        raise AppError("validation", f"A recipe can ask you for at most {BLANK_MAX} things")
    body["needs"] = []
    for item in needs:
        label = item.get("label") if isinstance(item, dict) and set(item) == {"label"} else None
        body["needs"].append({"label": _line(label, 80, redact, "What it asks you for")})
    if not body["procedure"]:
        raise AppError("validation", "A recipe needs at least one step in its procedure")
    for text in [body["overview"], *body["procedure"], *body["specifications"], *body["advice"], *body["forbidden"]]:
        for number in _BLANK.findall(text):
            if int(number) > len(body["needs"]):
                raise AppError("validation", f"${number} stands for something the recipe asks you for, but it asks for only {len(body['needs'])}")
    return body


def clean_title(raw: Any, redact: Callable[[str], str] | None = None) -> str:
    return _line(raw, TITLE_MAX, redact, "The title")


# ---- Markdown (by the owner's own action) ---------------------------------------------------------------------------------------------------------
_HEADINGS = {"overview": "Overview", "procedure": "Procedure", "specifications": "Specifications", "advice": "Advice", "forbidden": "Forbidden", "needs": "Needs from you"}


def to_markdown(title: str, body: dict[str, Any]) -> str:
    out = [f"# {title}", ""]
    out += [f"## {_HEADINGS['overview']}", body.get("overview", ""), ""]
    for part in ("procedure", "specifications", "advice", "forbidden"):
        out.append(f"## {_HEADINGS[part]}")
        out += [f"{i}. {line}" if part == "procedure" else f"- {line}" for i, line in enumerate(body.get(part, []), 1)]
        out.append("")
    out.append(f"## {_HEADINGS['needs']}")
    out += [f"{i}. {n['label']}" for i, n in enumerate(body.get("needs", []), 1)]
    return "\n".join(out).rstrip() + "\n"


def parse_markdown(text: str) -> dict[str, Any]:
    """`{title, body}` from a recipe written as Markdown (`# Title`, then `## Overview`, `## Procedure`, ...). Lines of lists lose their `1.`, `-` or `*`. It only reads the shape: what it returns is a DRAFT that
    still has to pass `clean_body` and be saved by the owner. Anything above 30 KB is refused."""
    if not isinstance(text, str) or len(text) > 30_000:
        raise AppError("validation", "That file is too long for a recipe")
    title, section, found = "", "", {}
    names = {v.lower(): k for k, v in _HEADINGS.items()}
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            section = names.get(line[3:].strip().lower(), "")
            if section:
                found.setdefault(section, [])
        elif section and line:
            found[section].append(re.sub(r"^(?:\d+[.)]|[-*•])\s+", "", line))
    if not title or "procedure" not in found:
        raise AppError("validation", "A recipe file starts with a title line (# Title) and has a Procedure part")
    return {"title": title, "body": {"overview": " ".join(found.get("overview", [])), "procedure": found.get("procedure", []), "specifications": found.get("specifications", []),
                                      "advice": found.get("advice", []), "forbidden": found.get("forbidden", []), "needs": [{"label": label} for label in found.get("needs", [])]}}


class RecipeService:
    def __init__(self, db: Database, *, redact: Callable[[str], str] | None = None, projects: bool = False) -> None:
        self.db = db
        self.redact = redact
        self.projects = projects                # the multi-agent nodes are on: a project can be saved as a recipe

    # ---- reading -----------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _starter(recipe_id: str) -> dict[str, Any]:
        found = STARTERS.get(recipe_id)
        if found is None:
            raise NotFound("that recipe")
        return {"id": recipe_id, "title": found["title"], "kind": "starter", "status": "active", "version": 1, "body": found["body"], "versions": [], "updated_at": None}

    def list(self, *, archived: bool = False) -> list[dict[str, Any]]:
        """The owner's recipes (newest change first) then the starters. `archived` lists the archived ones instead of the active ones; starters are always active."""
        rows = self.db.conn().execute("SELECT * FROM recipes WHERE status = ? ORDER BY updated_at DESC, id", ("archived" if archived else "active",)).fetchall()
        own = [{"id": r["id"], "title": r["title"], "kind": "own", "status": r["status"], "version": r["current_version"], "overview": self._body(r["id"], r["current_version"]).get("overview", ""),
                "updated_at": iso_z(r["updated_at"])} for r in rows]
        starters = [] if archived else [{"id": k, "title": v["title"], "kind": "starter", "status": "active", "version": 1, "overview": v["body"]["overview"], "updated_at": None} for k, v in STARTERS.items()]
        return own + starters

    def _body(self, recipe_id: str, version: int) -> dict[str, Any]:
        row = self.db.conn().execute("SELECT body_json FROM recipe_versions WHERE recipe_id = ? AND version = ?", (recipe_id, version)).fetchone()
        if row is None:
            raise NotFound("that version")
        return json.loads(row["body_json"])

    def get(self, recipe_id: str, version: int | None = None) -> dict[str, Any]:
        if _STARTER.match(recipe_id):
            return self._starter(recipe_id)
        if not _ID.match(recipe_id):
            raise NotFound("that recipe")
        conn = self.db.conn()
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            raise NotFound("that recipe")
        shown = row["current_version"] if version is None else int(version)
        versions = [{"version": v["version"], "note": v["note"], "created_at": iso_z(v["created_at"]), "sha256": v["sha256"]}
                    for v in conn.execute("SELECT version, note, created_at, sha256 FROM recipe_versions WHERE recipe_id = ? ORDER BY version DESC", (recipe_id,))]
        return {"id": recipe_id, "title": row["title"], "kind": "own", "status": row["status"], "version": shown, "current_version": row["current_version"], "body": self._body(recipe_id, shown),
                "versions": versions, "updated_at": iso_z(row["updated_at"])}

    # ---- writing (one transaction each) --------------------------------------------------------------------------------------------

    def create(self, title: Any, body: Any, note: str = "") -> dict[str, Any]:
        title, body = clean_title(title, self.redact), clean_body(body, self.redact)
        recipe_id = f"rcp_{secrets.token_hex(6)}"
        with self.db.tx() as tx:
            now = tx.now()
            tx.conn.execute("INSERT INTO recipes(id, title, status, current_version, created_at, updated_at) VALUES (?,?,?,?,?,?)", (recipe_id, title, "active", 1, now, now))
            self._version(tx, recipe_id, 1, body, clean_text(note)[:120] or "first version", now)
        return {"id": recipe_id, "version": 1}

    @staticmethod
    def _version(tx: Any, recipe_id: str, version: int, body: dict[str, Any], note: str, now: int) -> None:
        text = json.dumps(body, sort_keys=True, ensure_ascii=False)
        tx.conn.execute("INSERT INTO recipe_versions(recipe_id, version, body_json, sha256, note, created_at) VALUES (?,?,?,?,?,?)",
                        (recipe_id, version, text, hashlib.sha256(text.encode("utf-8")).hexdigest(), note, now))

    def update(self, recipe_id: str, title: Any, body: Any, note: str = "") -> dict[str, Any]:
        """A new version with the owner's words (and a new title when given). A starter cannot be changed: copy it first."""
        if _STARTER.match(recipe_id):
            raise AppError("validation", "A starter recipe cannot be changed. Make a copy of it and change the copy")
        body = clean_body(body, self.redact)
        title = clean_title(title, self.redact) if title is not None else None
        with self.db.tx() as tx:
            row = tx.conn.execute("SELECT current_version FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            if row is None:
                raise NotFound("that recipe")
            version = int(row["current_version"]) + 1
            now = tx.now()
            self._version(tx, recipe_id, version, body, clean_text(note)[:120] or "changed", now)
            tx.conn.execute("UPDATE recipes SET current_version = ?, updated_at = ?" + (", title = ?" if title is not None else "") + " WHERE id = ?",
                            (version, now, *( (title,) if title is not None else ()), recipe_id))
        return {"id": recipe_id, "version": version}

    def revert(self, recipe_id: str, version: int) -> dict[str, Any]:
        """Go back to an earlier version by making a NEW version with its words: nothing is lost, and the way back can itself be undone."""
        if _STARTER.match(recipe_id):
            raise AppError("validation", "A starter recipe has only one version")
        with self.db.tx() as tx:
            row = tx.conn.execute("SELECT current_version FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            if row is None:
                raise NotFound("that recipe")
            old = tx.conn.execute("SELECT body_json FROM recipe_versions WHERE recipe_id = ? AND version = ?", (recipe_id, int(version))).fetchone()
            if old is None:
                raise NotFound("that version")
            new = int(row["current_version"]) + 1
            now = tx.now()
            self._version(tx, recipe_id, new, json.loads(old["body_json"]), f"back to version {int(version)}", now)
            tx.conn.execute("UPDATE recipes SET current_version = ?, updated_at = ? WHERE id = ?", (new, now, recipe_id))
        return {"id": recipe_id, "version": new}

    def archive(self, recipe_id: str, archived: bool) -> dict[str, Any]:
        if _STARTER.match(recipe_id):
            raise AppError("validation", "A starter recipe is always there")
        with self.db.tx() as tx:
            changed = tx.conn.execute("UPDATE recipes SET status = ?, updated_at = ? WHERE id = ?", ("archived" if archived else "active", tx.now(), recipe_id)).rowcount
        if not changed:
            raise NotFound("that recipe")
        return {"id": recipe_id, "status": "archived" if archived else "active"}

    def copy_of(self, recipe_id: str) -> dict[str, Any]:
        """An ordinary recipe of the owner's with the words of a starter (or of one of their own): the way to change a starter."""
        found = self.get(recipe_id)
        return self.create(f"{found['title']} (mine)"[:TITLE_MAX], found["body"], "copied")

    # ---- starting ----------------------------------------------------------------------------------------------------------------

    def request_text(self, recipe_id: str, blanks: Any) -> tuple[str, str]:
        """`(title, request)`: the recipe written as a request in plain words, with the blanks filled. The number of blanks must be the number the recipe asks for; each is one short line through the note gate.
        The request is what the chat agent plans from: nothing in it is a command, and the plan gate runs on it as on any request."""
        found = self.get(recipe_id)
        if found["status"] != "active":
            raise AppError("busy", "That recipe is put away. Bring it back first")
        body = found["body"]
        if not isinstance(blanks, list) or len(blanks) != len(body["needs"]):
            raise AppError("validation", f"This recipe asks you for {len(body['needs'])} thing{'s' if len(body['needs']) != 1 else ''}")
        values = [_line(v, BLANK_VALUE_MAX, self.redact, f"“{n['label'][:40]}”") for v, n in zip(blanks, body["needs"])]

        def fill(text: str) -> str:
            return _BLANK.sub(lambda m: values[int(m.group(1)) - 1], text)
        parts = [f"Use my recipe “{found['title']}”. {fill(body['overview'])}".strip(), "Do these steps in order:"]
        parts += [f"{i}. {fill(line)}" for i, line in enumerate(body["procedure"], 1)]
        for part, head in (("specifications", "The result must be like this:"), ("advice", "Good to know:"), ("forbidden", "Never do these:")):
            if body[part]:
                parts.append(head)
                parts += [f"- {fill(line)}" for line in body[part]]
        text = "\n".join(parts)
        if len(text) > REQUEST_MAX:
            raise AppError("validation", "With those answers the request is too long. Shorten the recipe or the answers")
        return found["title"], text

    # ---- from a finished project (a draft, by code) -----------------------------------------------------------------------------------

    def draft_from_project(self, project_id: str) -> dict[str, Any]:
        """A DRAFT recipe from a project: its title, and the titles of its steps in order as the procedure. Made by code from rows that exist; nothing is saved, the owner edits it and saves it."""
        if not self.projects:
            raise NotFound("that project")
        conn = self.db.conn()
        project = conn.execute("SELECT title FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise NotFound("that project")
        steps = [clean_text(r["title"])[:LINE_MAX] for r in conn.execute(
            "SELECT t.title FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.role = 'worker' ORDER BY n.created_at, n.rowid", (project_id,)) if clean_text(r["title"])]
        return {"title": clean_text(project["title"])[:TITLE_MAX] or "My recipe",
                "body": {"overview": f"Saved from the project “{clean_text(project['title'])[:100]}”. Change anything before you save it.", "procedure": steps or ["Describe the first step here."],
                         "specifications": [], "advice": [], "forbidden": [], "needs": []}, "draft": True}

    def export(self, recipe_id: str) -> tuple[str, str]:
        found = self.get(recipe_id)
        return found["title"], to_markdown(found["title"], found["body"])
