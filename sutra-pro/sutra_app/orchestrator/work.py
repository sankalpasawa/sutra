"""The Work list, tags and "How did it go?" (Devin parity DV-2, docs/design/devin-parity.md; SUTRA_WORK_V1).

    work = WorkService(db, redact=redact.scrub, projects=True)
    work.items(tag="cafe", q="menu", status="done")      one list of everything Sutra did: tasks, and projects when the multi-agent nodes are on
    work.set_tags("task", "tsk_...", ["cafe", "weekly"])  the owner's own words, replaced as a set
    work.summary("prj_...")                                what a project cost and where it got stuck, in plain words

Everything here is computed by code from rows that are already there (tasks, the usage ledger, the node tables, the audit). A model writes none of it and no sentence here is a model's guess. The
tags are the owner's: a plain word of at most 30 characters, at most 8 for an item, and a line that looks like a key, a token or a password is refused as it is for a note (`owner_words.refusal`).
Reads use the connection of the caller's thread; the one write (`set_tags`) is one `db.tx()`.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from typing import Any

from sutra_app.orchestrator.budgets import chain_spend, project_spend
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.owner_words import hidden_text_refusal, refusal

__all__ = ["WorkService", "TAG_MAX", "TAGS_PER_ITEM", "STATUS_WORDS", "clean_tags"]

NODE_STATE_WORDS = {"planned": "Waiting its turn", "awaiting_approval": "Waiting for your answer", "awaiting_system": "Waiting for your computer to allow it", "ready": "Ready to start", "queued": "Waiting to start",
                    "leased": "Starting", "running": "Working", "handing_off": "Handing in its work", "done": "Done", "failed": "Did not finish", "cancelled": "Cancelled", "expired": "Ran out of time"}
TAG_MAX = 30
TAGS_PER_ITEM = 8
LIMIT_MAX = 1000
STATUS_WORDS = {
    "blocked": "Waiting for another step", "queued": "Waiting to start", "starting": "Starting", "running": "Working", "waiting_user": "Waiting for your answer", "done": "Done",
    "done_with_open_items": "Done, with some things left open", "stopped": "Stopped", "crashed": "Did not finish", "cancelled": "Cancelled",
    "planning": "Planning", "awaiting_approval": "Waiting for your answer", "reviewing": "Being checked", "failed": "Could not finish",
}


def clean_tags(raw: Any, redact: Callable[[str], str] | None = None) -> list[str]:
    """The owner's tags as a clean, sorted, unique list. A tag is lower case, spaces collapsed, letters and digits with spaces, `_` and `-` inside, 1 to 30 characters; at most 8. Anything else is
    refused with a plain sentence (AppError `validation`) that NEVER repeats the tag: a tag that looks like a key, a token or a password (checked on what was typed, before it is lower-cased, because
    the shapes of keys depend on capital letters), or that holds a hidden character, is refused and never kept or shown back."""
    if not isinstance(raw, list):
        raise AppError("validation", "Tags are a list of words")
    found: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise AppError("validation", "A tag is a word")
        typed = " ".join(item.split())
        why = hidden_text_refusal(item) or (refusal(typed, redact, limit=300) if typed else None)
        if why is not None and typed:
            raise AppError("validation", why)
        tag = typed.lower()
        if not tag or len(tag) > TAG_MAX or not tag[0].isalnum() or not all(ch.isalnum() or ch in " _-\u200c\u200d" for ch in tag):
            raise AppError("validation", f"A tag is 1 to {TAG_MAX} letters, digits, spaces, dashes or underscores")
        if tag not in found:
            found.append(tag)
    if len(found) > TAGS_PER_ITEM:
        raise AppError("validation", f"An item can have at most {TAGS_PER_ITEM} tags")
    return sorted(found)


class WorkService:
    def __init__(self, db: Database, *, redact: Callable[[str], str] | None = None, projects: bool = False) -> None:
        self.db = db
        self.redact = redact
        self.projects = projects                # the multi-agent nodes are on: projects are in the list and have a summary

    # ---- the list -----------------------------------------------------------------------------------------------------------------

    def items(self, *, tag: str = "", q: str = "", status: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Everything Sutra did, newest first: each `{kind, id, title, status, status_word, team, created_at, ended_at, tags, link}`. `tag` keeps items with that tag, `q` keeps items whose title or request
        holds the words (every word, any case), `status` one raw status. A task that is any attempt of a project's step is not listed on its own (the whole chain of a retried step is hidden, not
        only its current task): it is under its project. The filtering and the paging are done by the database; only the page's own tags are read afterwards."""
        conn = self.db.conn()
        tag = " ".join(tag.lower().split())
        words = [w for w in re.split(r"\s+", q.strip().lower()) if w][:8]
        want = max(0, int(offset)) + max(1, min(int(limit), LIMIT_MAX))
        rows: list[dict[str, Any]] = []

        def like(column: str) -> tuple[str, list[str]]:
            escaped = [w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for w in words]
            return " AND ".join(f"lower({column}) LIKE ? ESCAPE '\\'" for _ in words), [f"%{w}%" for w in escaped]

        def tagged(kind: str, column: str) -> tuple[str, list[str]]:
            if not tag:
                return "", []
            return f" AND EXISTS (SELECT 1 FROM work_tags w WHERE w.item_kind = '{kind}' AND w.item_id = {column} AND w.tag = ?)", [tag]
        where: list[str] = []
        args: list[str] = []
        if self.projects:
            where.append("t.id NOT IN (SELECT id FROM chain)")
        if status:
            where.append("t.status = ?")
            args.append(status)
        if words:
            clause, more = like("(t.title || ' ' || t.user_text)")
            where.append(clause)
            args += more
        extra, targs = tagged("task", "t.id")
        prefix = ("WITH RECURSIVE chain(id) AS (SELECT task_id FROM agent_nodes WHERE task_id IS NOT NULL UNION SELECT t2.parent_task_id FROM tasks t2 JOIN chain c ON t2.id = c.id "
                  "WHERE t2.parent_task_id IS NOT NULL) ") if self.projects else ""
        sql = (prefix + "SELECT t.id AS id, t.title AS title, t.status AS status, t.created_at AS created_at, t.ended_at AS ended_at, COALESCE(o.name, t.dept_id) AS team, t.dept_id AS dept "
               "FROM tasks t LEFT JOIN org_nodes o ON o.id = t.dept_id WHERE 1 = 1" + "".join(f" AND {w}" for w in where) + extra + " ORDER BY t.created_at DESC, t.id LIMIT ?")
        for r in conn.execute(sql, (*args, *targs, want)):
            rows.append({"kind": "task", "id": r["id"], "title": r["title"], "status": r["status"], "created_at": r["created_at"], "ended_at": r["ended_at"], "team": r["team"], "link": f"/d/{r['dept']}/"})
        if self.projects:
            pwhere: list[str] = []
            pargs: list[str] = []
            if status:
                pwhere.append("p.status = ?")
                pargs.append(status)
            if words:
                clause, more = like("p.title")
                pwhere.append(clause)
                pargs += more
            pextra, ptargs = tagged("project", "p.id")
            psql = ("SELECT p.id AS id, p.title AS title, p.status AS status, p.created_at AS created_at, p.ended_at AS ended_at FROM projects p WHERE 1 = 1" + "".join(f" AND {w}" for w in pwhere)
                    + pextra + " ORDER BY p.created_at DESC, p.id LIMIT ?")
            for r in conn.execute(psql, (*pargs, *ptargs, want)):
                rows.append({"kind": "project", "id": r["id"], "title": r["title"], "status": r["status"], "created_at": r["created_at"], "ended_at": r["ended_at"], "team": "", "link": f"/p/{r['id']}"})
        rows.sort(key=lambda r: (-int(r["created_at"]), r["id"]))
        page = rows[max(0, int(offset)): want]
        tags: dict[tuple[str, str], list[str]] = {}
        ids = [r["id"] for r in page]
        for start in range(0, len(ids), 400):
            chunk = ids[start:start + 400]
            for t in conn.execute(f"SELECT item_kind, item_id, tag FROM work_tags WHERE item_id IN ({','.join('?' * len(chunk))}) ORDER BY tag", chunk):
                tags.setdefault((t["item_kind"], t["item_id"]), []).append(t["tag"])
        return [{"kind": r["kind"], "id": r["id"], "title": r["title"], "status": r["status"], "status_word": STATUS_WORDS.get(r["status"], r["status"]), "team": r["team"], "created_at": iso_z(r["created_at"]),
                 "ended_at": iso_z(r["ended_at"]) if r["ended_at"] is not None else None, "tags": tags.get((r["kind"], r["id"]), []), "link": r["link"]} for r in page]

    def all_tags(self) -> list[dict[str, Any]]:
        """Every tag in use with how many items carry it, most used first (for the page's filter)."""
        return [{"tag": r["tag"], "count": r["n"]} for r in self.db.conn().execute("SELECT tag, count(*) AS n FROM work_tags GROUP BY tag ORDER BY n DESC, tag")]

    # ---- tags ---------------------------------------------------------------------------------------------------------------------

    def set_tags(self, kind: str, item_id: str, raw: Any) -> list[str]:
        """Replace an item's tags with `raw` (validated by `clean_tags`) in one transaction. NotFound for a task or project that does not exist (a project only with the nodes on)."""
        if kind not in ("task", "project") or (kind == "project" and not self.projects):
            raise NotFound("that item")
        tags = clean_tags(raw, self.redact)
        with self.db.tx() as tx:
            table = "tasks" if kind == "task" else "projects"
            if tx.conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (item_id,)).fetchone() is None:
                raise NotFound("that item")
            tx.conn.execute("DELETE FROM work_tags WHERE item_kind = ? AND item_id = ?", (kind, item_id))
            now = tx.now()
            for tag in tags:
                tx.conn.execute("INSERT INTO work_tags(item_kind, item_id, tag, created_at) VALUES (?,?,?,?)", (kind, item_id, tag, now))
        return tags

    # ---- "How did it go?" ---------------------------------------------------------------------------------------------------------

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a project cost and where it got stuck, by code: `{status, status_word, calls, usd, minutes, steps: [...], questions, scope_notices, retries, stop_reason, lines}`. `lines` are
        plain sentences, in the order the owner wants them: how it ended, what it used, what was tried again, what it asked, what could not be checked, why it stopped. Credits are model calls
        (D324: one call, one credit) and dollars are what the providers reported (none when they reported none). Minutes run from the FIRST start (the first attempt of any step) to the end and
        include any time the computer was asleep or Sutra was closed. A step is named by its task's title; "tried again" counts real retries only (the audit's `node.retry`), a step started again
        because Sutra was closed or sent back by the reviewer is said apart."""
        if not self.projects:
            raise NotFound("that project")
        conn = self.db.conn()
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise NotFound("that project")
        calls, usd = project_spend(conn, project_id)
        chain = ("WITH RECURSIVE chain(id) AS (SELECT task_id FROM agent_nodes WHERE project_id = ? AND task_id IS NOT NULL UNION SELECT t.parent_task_id FROM tasks t JOIN chain c ON t.id = c.id "
                 "WHERE t.parent_task_id IS NOT NULL) ")
        started = conn.execute(chain + "SELECT MIN(started_at) FROM tasks WHERE id IN (SELECT id FROM chain) AND started_at IS NOT NULL", (project_id,)).fetchone()[0]
        end = project["ended_at"]
        minutes = None
        if started is not None:
            last = end if end is not None else conn.execute("SELECT COALESCE(MAX(at), ?) FROM node_audit WHERE project_id = ?", (started, project_id)).fetchone()[0]
            minutes = max(0, int(round((int(last) - int(started)) / 60)))
        by_action: dict[tuple[str, str], int] = {}
        for r in conn.execute("SELECT node_id, action, count(*) AS n FROM node_audit WHERE project_id = ? AND action IN ('node.retry','node.restarted','node.rework') AND node_id IS NOT NULL GROUP BY node_id, action", (project_id,)):
            by_action[(r["node_id"], r["action"])] = r["n"]
        steps = []
        retries = restarted = sent_back = 0
        for n in conn.execute("SELECT n.*, t.title AS task_title FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.role <> 'planner' ORDER BY n.created_at, n.rowid", (project_id,)):
            step_calls, step_usd = chain_spend(conn, n["task_id"])
            tried, again, back = by_action.get((n["id"], "node.retry"), 0), by_action.get((n["id"], "node.restarted"), 0), by_action.get((n["id"], "node.rework"), 0)
            retries, restarted, sent_back = retries + tried, restarted + again, sent_back + back
            title = " ".join(str(n["task_title"] or "").split())[:80]
            name = "The reviewer" if n["role"] == "reviewer" else (title or (f"Step {n['plan_ref']}" if n["plan_ref"] else "A step"))
            steps.append({"name": name, "role": n["role"], "state": n["state"], "state_word": NODE_STATE_WORDS.get(n["state"], ""), "tries": 1 + tried, "calls": step_calls,
                          "usd": round(step_usd, 6) if step_calls and step_usd else None, "why": n["failure_reason"] or ""})
        asked = conn.execute("SELECT count(*) AS n, SUM(decided_by = 'rule:decide_for_me') AS by_rule, SUM(status = 'denied') AS no FROM approvals WHERE project_id = ?", (project_id,)).fetchone()
        scope = {r["action"]: r["n"] for r in conn.execute("SELECT action, count(*) AS n FROM node_audit WHERE project_id = ? AND action IN ('scope.violation','scope.unchecked') GROUP BY action", (project_id,))}
        status = project["status"]
        lines = [f"It {'finished' if status == 'done' else 'finished, but some steps did not' if status == 'done_with_open_items' else 'stopped' if status == 'stopped' else 'could not finish' if status == 'failed' else 'is still going'}."]
        used = f"It used {calls} credit{'s' if calls != 1 else ''}" + (f" and about ${usd:.2f}" if usd else "")
        if minutes is not None:
            used += f", over about {minutes} minute{'s' if minutes != 1 else ''} from the first start to the end (any time the computer slept or Sutra was closed is in that)"
        lines.append(used + ".")
        if retries:
            tried_steps = [s["name"] for s in steps if s["tries"] > 1]
            lines.append(f"{', '.join(tried_steps)} {'was' if len(tried_steps) == 1 else 'were'} tried again after a failure ({retries} extra {'try' if retries == 1 else 'tries'}).")
        if restarted:
            lines.append(f"{restarted} step{'s were' if restarted != 1 else ' was'} started again because Sutra was closed.")
        if sent_back:
            lines.append(f"{sent_back} step{'s were' if sent_back != 1 else ' was'} sent back for changes.")
        if asked["n"]:
            by_rule = int(asked["by_rule"] or 0)
            lines.append(f"You were asked {asked['n']} question{'s' if asked['n'] != 1 else ''}" + (f" and Sutra answered {by_rule} for you." if by_rule else "."))
        if scope.get("scope.violation"):
            lines.append(f"A step changed files that were not its own ({scope['scope.violation']} time{'s' if scope['scope.violation'] != 1 else ''}).")
        if scope.get("scope.unchecked"):
            lines.append(f"Sutra could not check which files a step changed ({scope['scope.unchecked']} time{'s' if scope['scope.unchecked'] != 1 else ''}).")
        stuck = [s for s in steps if s["state"] in ("failed", "cancelled", "expired") and s["why"]]
        for s in stuck[:3]:
            lines.append(f"{s['name']} got stuck: {s['why']}")
        if project["stop_reason"] and status in ("stopped", "failed", "done_with_open_items", "done"):
            lines.append(f"Why: {project['stop_reason']}")
        return {"project_id": project_id, "title": project["title"], "status": status, "status_word": STATUS_WORDS.get(status, status), "calls": calls, "usd": round(usd, 6) if calls and usd else None,
                "minutes": minutes, "steps": steps, "questions": int(asked["n"] or 0), "answered_by_sutra": int(asked["by_rule"] or 0), "scope_notices": int(sum(scope.values())), "retries": retries,
                "stop_reason": project["stop_reason"] or "", "lines": lines}
