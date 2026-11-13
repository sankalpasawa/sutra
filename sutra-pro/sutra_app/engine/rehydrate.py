"""Continue a finished run in a new process: `J2Run.rehydrate(src_dir)` (engine design 4.8, patch P11, S1-contracts-12).

A follow-up after Done is a NEW task with a new run id, folder and process; the old folder is read-only history. When the
earlier run was a finished website run or a finished document chain (PRD, HLD, LLD, then perhaps the website), this module
brings its state back into a fresh `J2Run`, so the team keeps its charter, workflows, findings, documents and site and treats
the next message as a change request. Otherwise it raises
`RehydrateRefused(reason)` and the host starts a fresh run with the old files under `upstream/<old run id>/` (a refusal is
not an error). Nothing is written until the source has been read and checked, and a copy that fails half-way is undone.

Allowed (all four, or the run is refused): the source `summary.json` says `done` or `done_with_open_items`; its `chat.jsonl`
header says output `website` (a document chain is exempt: the header holds the output of the first message, the chain's
state comes from `summary.json`, `documents.json` and `stage-*.json`); a document chain, if there is one, is complete (below);
`goal.json` and `workflows.json` exist and can be read. Realization on or off is NOT a condition: the pause once seen with realization on was
J2's mock reply without `estimated_resources` (the validator found every workflow free and refused it), not a defect here.

What happens, in this order:
  1. `check_source(src_dir)` reads and checks the source (writes nothing);
  2. the source's JSON and JSONL files (not the host's own: task, settings, events, trace, inbox, snapshot, live) and its
     `site/` and `artifacts/` trees are copied into the new run folder, so the files J2 appends to (chat, calls, receipts)
     continue where the old run stopped;
  3. these `J2Run` attributes are set, and no others: chat (the copied `chat.jsonl` without its header), goal, stamped,
     workflows, conflicts, audits, sections, style, sites, request, calls, cycle, spent, budget, receipts, decisions, done,
     status, outcome and, when `realization.json` exists, real, real_base, real_summary and real_asked; and `auto_pick`, set to
     `{}` (RESTORED_REUSE, D187: the run counts as having decided about auto-reuse, so a follow-up never scores the run templates again;
     `run_tpl` is deliberately left as it is, None: NOT_RESTORED_REUSE).

A document chain (E1-b, GAP-E1B) is recognised by `documents.json` or `stage-*.json`. Its `summary.json` must hold
`design_documents` (requested, stages) and `documents.json` every requested document, or the run is refused. Then also
restored, as J2 holds them after Done: docset, stages, stage_i (the last index), docs, chain (each document's agent_output),
stage_archive (the `stage-<stage>.json` files, in stage order), past_workflows (the workflows of the earlier stages and the
send deeds; `workflows` keeps the last stage's), site_tag, stage_calls0, lld_revisions, the output of the last document or
website stage (so `doc`, `out`, the workflow formats and the rate card are the last stage's) and, when that stage is the
website and an LLD with sections was written, the LLD blueprint. The document files named in `documents.json` (`prd.md`,
`prd.docx`, ...) are copied with the rest, and `sites` are the last stage's versions (`site/<stage>-vN.md` for a document,
`site/vN.html` for the website). The change request then continues the last stage (a new workflow, a new version of its
document or site), not a new chain.

The first message then gets J2's change-request handling (`user_says` marks it `change` because `done` is true). The host
calls `rehydrate` BEFORE it posts any line of its own (framing, the upstream list): the copied `chat.jsonl` must be the
folder's first. Not restored (off by default or not needed for a change): the message board, the template-library state, the
J2_CHANGE state, `call_log` (the old calls stay readable by id through calls.jsonl) and board re-checks in audits.json.
"""
import copy
import json
import os
import re
import shutil
from pathlib import Path

from . import forms
from .events import END_STATUSES

__all__ = ["RehydrateRefused", "check_source", "rehydrate", "continuing_line", "fresh_line", "HOST_FILES", "RUN_TREES",
           "RESTORED", "RESTORED_REALIZATION", "RESTORED_CHAIN", "RESTORED_TYPE", "RESTORED_REUSE", "NOT_RESTORED_REUSE"]

HOST_FILES = ("task.json", "settings.json", "snapshot.json", "live.json", "events.jsonl", "trace.jsonl", "inbox.jsonl",
              "choices.json", "node_context.json",           # the server's notes to a run's agents (D131, D132): plumbing, never a follow-up's seed
              "deliverable.json")                             # what the host recorded at the end of a run for the team's chat (D135)
RUN_TREES = ("site", "artifacts")
RESTORED = ("chat", "goal", "stamped", "workflows", "conflicts", "audits", "sections", "style", "sites", "request", "calls",
            "cycle", "spent", "budget", "receipts", "decisions", "done", "status", "outcome")
RESTORED_REALIZATION = ("real", "real_base", "real_summary", "real_asked")
RESTORED_CHAIN = ("docset", "stages", "stage_i", "docs", "chain", "stage_archive", "past_workflows", "site_tag", "stage_calls0",
                  "lld_revisions", "output", "out", "doc", "WF_FMT", "GRANT_FMT", "ATOM_RULES", "blueprint")
# J2 sync 6 (D187): a follow-up is a change request on finished work, so it never re-fires auto-reuse and does not take the earlier run's run template.
# `auto_pick = {}` is J2's own "already decided" marker (`_auto_reuse_pick` returns at once when it is not None); `run_tpl` stays None, because the
# earlier run's template shaped its FIRST plan and its rows and per-workflow state would steer stages that are already done.
RESTORED_REUSE = ("auto_pick",)
NOT_RESTORED_REUSE = ("run_tpl",)
RESTORED_TYPE = ("output", "out", "doc")              # a single page stage when nothing was chosen for the new run: the earlier run's type (no default exists)
BLUEPRINT_KEYS = ("id", "anchor", "implements")      # what a section of a blueprint says (J2's own `lld` sections: S1, its anchor, what it implements)
SITE_VERSION = re.compile(r"v(\d+)\.(?:html|md)")
ENDED = END_STATUSES[:2]                # `done`, `done_with_open_items`: a run that finished its work (the statuses are events.py's)

CONTINUING = ("Continuing from run {run_id}: the team keeps its charter, workflows, findings and site and treats your "
              "message as a change request.")
FRESH = "Starting a new run. Your earlier files from run {run_id} are in upstream/{run_id}/ for reference. Reason: {reason}."


class RehydrateRefused(Exception):
    """The earlier run cannot be continued. `reason` is plain words for the system line, with no final full stop."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def continuing_line(run_id: str) -> str:
    """The system line of a continued run (fixed wording, engine design 4.8)."""
    return CONTINUING.format(run_id=run_id)


def fresh_line(run_id: str, reason: str) -> str:
    """The system line of a follow-up that starts fresh with the old files as upstream (fixed wording, engine design 4.8)."""
    return FRESH.format(run_id=run_id, reason=str(reason).rstrip(". "))


# ---- the types: data, read through J2 (D167) -----------------------------------------------------------------------
# What is a document, what is a page and what is neither is J2's `artifacts/types.json` (and the user's local types, and the types a
# capability registers); this module names no type. J2 is imported when a run is read, not when this module loads.
def _types():
    from . import j2, j2_types
    return j2, j2_types


def _form(kind, src: Path | None = None):
    """The form of an output type (`forms.PAGE` or `forms.DOCUMENT`), or None when `kind` is no output type: a name in the data, else a document
    type the run itself recorded (a local type deleted after the run: J2's `recorded`, so the run still opens)."""
    j2, j2_types = _types()
    if kind in j2_types.names():
        return j2_types.info(kind)["form"]
    if src is not None and kind in j2_types.recorded(str(src)):
        return forms.DOCUMENT
    return None


def _blueprint_of(run, page_kind):
    """The chain document that is the page's blueprint, as `J2Run._begin_stage` sets it: the first of the page type's `depends_on` whose
    record has sections of the blueprint's shape (a non-empty list of objects with an id, an anchor and what they implement). J2 names its
    own `lld` there; this reads the shape, so a custom chain is carried on the same way. None when no record has it."""
    _, j2_types = _types()
    entry = next((e for e in j2_types.entries() if e.get("kind") == "type" and e.get("name") == page_kind), {})
    for dep in entry.get("depends_on") or []:
        record = (run.chain or {}).get(dep)
        sections = record.get("sections") if isinstance(record, dict) else None
        if isinstance(sections, list) and sections and all(isinstance(s, dict) and all(k in s for k in BLUEPRINT_KEYS) for s in sections):
            return copy.deepcopy(record)
    return None


# ---- reading the source ---------------------------------------------------------------------------------------------
def _json(src: Path, name: str, missing: str, kind):
    """The parsed file, which must exist and hold a `kind` (dict or list)."""
    path = src / name
    if not path.is_file() or path.is_symlink():
        raise RehydrateRefused(missing)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RehydrateRefused(f"{name} cannot be read") from None
    if not isinstance(value, kind):
        raise RehydrateRefused(f"{name} does not hold a {'list' if kind is list else 'JSON object'}")
    return value


def _optional(src: Path, name: str, default, kind):
    return _json(src, name, "", kind) if (src / name).is_file() else default


def _jsonl(src: Path, name: str) -> list:
    """The lines of a JSONL file that parse as objects (J2 skips the others); no file is no lines."""
    path = src / name
    if not path.is_file() or path.is_symlink():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise RehydrateRefused(f"{name} cannot be read") from None
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _files(src: Path) -> list:
    """Paths (relative, POSIX) to copy: top-level JSON and JSONL files that are not the host's, and the files of the trees."""
    found = []
    for entry in sorted(os.scandir(src), key=lambda e: e.name):
        if entry.is_file(follow_symlinks=False) and entry.name.endswith((".json", ".jsonl")) \
                and entry.name not in HOST_FILES and not entry.name.startswith("."):
            found.append(entry.name)
    for tree in RUN_TREES:
        base = src / tree
        if base.is_dir() and not base.is_symlink():
            for root, dirs, names in os.walk(base, followlinks=False):
                dirs.sort()
                found += [Path(root, n).relative_to(src).as_posix() for n in sorted(names)
                          if not Path(root, n).is_symlink()]
    return found


def _sites(src: Path, tag: str = "") -> list:
    """The texts of the last stage's versions in order: `site/v<n>.html|md`, or `site/<tag>v<n>.md` for a document stage."""
    folder = src / "site"
    if not folder.is_dir():
        return []
    pattern = SITE_VERSION if not tag else re.compile(re.escape(tag) + SITE_VERSION.pattern)
    versions = sorted((int(m[1]), f.name) for f in folder.iterdir()
                      if f.is_file() and not f.is_symlink() and (m := pattern.fullmatch(f.name)))
    try:
        return [(folder / name).read_text(encoding="utf-8") for _, name in versions]
    except (OSError, UnicodeDecodeError):
        raise RehydrateRefused("a site version of the earlier run cannot be read") from None


def _plain_name(value) -> bool:
    return isinstance(value, str) and bool(value) and value == os.path.basename(value) and value not in (".", "..")


def _is_deed_workflow(w) -> bool:
    return any(isinstance(v, dict) and v.get("type") == "deed-send" for a in w.get("atoms") or [] if isinstance(a, dict)
               for v in a.get("verification") or [])


def _chain(src: Path, summary: dict, workflows: list) -> dict:
    """The document chain of a finished run, checked and split into what `rehydrate` sets. Raises `RehydrateRefused` when
    `summary.json`, `documents.json` or a `stage-<stage>.json` does not describe a chain J2 could carry on."""
    record = summary.get("design_documents")
    if not isinstance(record, dict) or not isinstance(record.get("requested"), list) or not record["requested"] \
            or not isinstance(record.get("stages"), list):
        raise RehydrateRefused("the earlier run's document chain cannot be read (summary.json has no design_documents)")
    docset, stages = list(record["requested"]), list(record["stages"])
    if any(_form(k, src) != forms.DOCUMENT for k in docset) or not all(isinstance(k, str) and re.fullmatch(r"\w+", k) for k in stages) \
            or not set(docset) <= set(stages):
        raise RehydrateRefused("the earlier run's document chain cannot be read (summary.json names unknown stages)")
    docs = _json(src, "documents.json", "the earlier run's document chain has no documents.json", dict)
    for kind in docset:
        rec = docs.get(kind)
        if not isinstance(rec, dict) or not isinstance(rec.get("agent_output"), dict):
            raise RehydrateRefused(f"documents.json has no {kind.upper()} (the document chain is incomplete)")
    archive = []
    for kind in stages:
        if (src / f"stage-{kind}.json").exists():
            archive.append(_json(src, f"stage-{kind}.json", "", dict))
    stage_kinds = [k for k in stages if _form(k, src) is not None]                   # the others are send deeds: no output
    last = stage_kinds[-1] if stage_kinds else docset[-1]
    earlier = {i for k, r in docs.items() if k != last for i in r.get("workflows") or []}
    rows = [w for w in workflows if isinstance(w, dict)]
    past = [w for w in rows if w.get("id") in earlier or _is_deed_workflow(w)]
    files = []
    for kind in docset:
        for name in (docs[kind].get("file"), docs[kind].get("docx")):
            if _plain_name(name) and (src / name).is_file() and not (src / name).is_symlink():
                files.append(name)
    done_calls = [int((r.get("calls") or {}).get("to") or 0) for r in docs.values() if isinstance(r, dict)]
    if last in docs:
        calls0 = max(int((docs[last].get("calls") or {}).get("from") or 1) - 1, 0)
    else:
        calls0 = max(done_calls, default=0)
    revisions = record.get("lld_revisions")
    return {"docset": docset, "stages": stages, "docs": docs, "archive": archive, "last": last, "doc_stage": _form(last, src) == forms.DOCUMENT,
            "site_tag": f"{last}-" if len(stages) > 1 else "", "past": past,
            "current": [w for w in rows if w not in past], "files": files, "calls0": calls0,
            "lld_revisions": revisions if isinstance(revisions, list) else []}


def check_source(src_dir) -> dict:
    """Read and check the earlier run's folder. Returns the records `rehydrate` needs; raises `RehydrateRefused` otherwise.
    Writes nothing."""
    src = Path(src_dir)
    if not src.is_dir() or src.is_symlink():
        raise RehydrateRefused("the earlier run's folder is not there")
    summary = _json(src, "summary.json", "the earlier run left no summary, so it never finished", dict)
    status = summary.get("status")
    if status not in ENDED:
        raise RehydrateRefused({"stopped": "the earlier run was stopped before it finished",
                                "crashed": "the earlier run crashed"}.get(status, f"the earlier run did not finish ({status or 'no status'})"))
    chat = _jsonl(src, "chat.jsonl")
    if not chat or not chat[0].get("meta"):
        raise RehydrateRefused("the earlier run's chat.jsonl has no header")
    has_chain = (src / "documents.json").exists() or any(src.glob("stage-*.json"))
    if not has_chain:                       # a single stage: it must be a page (a document run leaves a chain; a run with no type leaves neither)
        j2, _ = _types()
        if not j2.is_page(j2.saved_output(str(src))):
            raise RehydrateRefused("the earlier run has no page and no document chain")
    goal = _json(src, "goal.json", "the earlier run has no charter (goal.json)", dict)
    workflows = _json(src, "workflows.json", "the earlier run has no workflows (workflows.json)", list)
    chain = _chain(src, summary, workflows) if has_chain else None
    files = _files(src)
    if chain:
        files += [f for f in chain["files"] if f not in files]
    audits = _optional(src, "audits.json", [], list)
    return {
        "summary": summary, "chat": [m for m in chat if not m.get("meta")], "goal": goal, "workflows": workflows,
        "conflicts": _optional(src, "conflicts.json", [], list),
        "audits": [a for a in audits if isinstance(a, dict) and a.get("kind") != "recheck"],      # a board re-check is no audit
        "sections": _optional(src, "sections.json", {}, dict), "style": _optional(src, "style.json", None, dict),
        "sites": _sites(src, chain["site_tag"] if chain and chain["doc_stage"] else ""), "chain": chain, "receipts": _jsonl(src, "receipts.jsonl"), "calls_logged": _jsonl(src, "calls.jsonl"),
        "realization": _optional(src, "realization.json", None, dict), "files": files,
    }


# ---- bringing it back -------------------------------------------------------------------------------------------------
def _copy(src: Path, dst: Path, files: list) -> None:
    """Copy the files into the new run folder; on a failure undo what was copied (a half-restored folder would mislead a
    fresh start) and refuse."""
    copied = []
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for rel in files:
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, target)
            copied.append(target)
    except OSError as exc:
        for target in reversed(copied):
            try:
                target.unlink()
            except OSError:
                pass
        for tree in RUN_TREES:                      # folders made for the copy, deepest first
            for root, _, _ in sorted(os.walk(dst / tree), reverse=True):
                try:
                    os.rmdir(root)
                except OSError:
                    pass
        raise RehydrateRefused(f"the earlier files could not be copied ({exc.strerror or type(exc).__name__})") from None


def _restore_chain(run, chain: dict) -> None:
    """Set the document-chain attributes (RESTORED_CHAIN) as J2 holds them after the last stage's Done."""
    run.docset, run.stages, run.stage_i = chain["docset"], chain["stages"], len(chain["stages"]) - 1
    run.docs = chain["docs"]
    run.chain = {k: r["agent_output"] for k, r in chain["docs"].items() if isinstance(r, dict) and "agent_output" in r}
    run.stage_archive = chain["archive"]
    run.past_workflows, run.workflows = chain["past"], chain["current"]
    run.site_tag = chain["site_tag"]
    run.stage_calls0 = chain["calls0"]
    run.lld_revisions = chain["lld_revisions"]
    run._apply_output(chain["last"])
    j2, _ = _types()
    blueprint = _blueprint_of(run, chain["last"]) if j2.is_page(chain["last"]) else None
    if blueprint is not None:
        # the page stage's blueprint, as J2Run._begin_stage sets it (the text is J2's; the state test compares it with a live run)
        run.blueprint = blueprint
        run.WF_FMT = run.WF_FMT.replace('"covers": [int]', '"lld_sections": [str] (the LLD section ids this '
                                        'workflow implements, e.g. "S1"), "covers": [int]')
        run.GRANT_FMT = run.GRANT_FMT.replace('"covers": [int]', '"lld_sections": [str], "covers": [int]')


def rehydrate(run, src_dir) -> dict:
    """Continue the finished run in `src_dir` inside `run`, a fresh `J2Run` whose folder is the new run's. See the module
    docstring. Returns {"source", "files", "messages", "workflows", "sites", "realization"}; raises `RehydrateRefused`
    (nothing changed) when the earlier run cannot be continued, and ValueError when `run` has already started."""
    if run.chat or run.status != "idle" or run.goal or os.path.exists(os.path.join(run.dir, "chat.jsonl")):
        raise ValueError("rehydrate continues a run that has not started: this one already holds a chat")
    rec = check_source(src_dir)
    src, summary = Path(src_dir), rec["summary"]
    _copy(src, Path(run.dir), rec["files"])
    budget = summary.get("budget") if isinstance(summary.get("budget"), dict) else {}
    first_user = next((m.get("text") for m in rec["chat"] if m.get("who") == "user"), "")
    run.chat = rec["chat"]
    run.goal, run.stamped = rec["goal"], True
    run.workflows, run.conflicts, run.audits = rec["workflows"], rec["conflicts"], rec["audits"]
    run.sections, run.style, run.sites = rec["sections"], rec["style"], rec["sites"]
    run.request = summary.get("brief") or first_user or ""
    run.calls = max(int(summary.get("ai_calls") or 0), max((int(c.get("id") or 0) for c in rec["calls_logged"]), default=0))
    run.cycle = int(summary.get("cycles") or 0)
    run.spent, run.budget = int(budget.get("used") or 0), int(budget.get("granted") or run.budget)
    run.receipts, run.decisions = rec["receipts"], list(summary.get("questions_to_user") or [])
    run.done, run.status, run.outcome = True, "waiting", summary.get("outcome")
    run.auto_pick = {}                      # D187: J2's own "already decided" marker; `run_tpl` stays None (NOT_RESTORED_REUSE)
    if rec["realization"] is not None:
        planned = summary.get("realization") if isinstance(summary.get("realization"), dict) else {}
        run.real, run.real_base = rec["realization"], copy.deepcopy(run.goal)
        run.real_summary = {k: v for k, v in planned.items() if k != "applied"}
        run.real_asked = True           # the plan's blocking facts were asked in the earlier run (needed for J2_CHANGE=1)
    if rec["chain"]:
        _restore_chain(run, rec["chain"])
    elif run.out is None:                   # a single page stage: the run is the earlier run's type (nothing is chosen for it: there is no default type)
        j2, _ = _types()
        run._apply_output(j2.saved_output(str(src)))
    return {"source": Path(src_dir).name, "files": len(rec["files"]), "messages": len(run.chat),
            "workflows": len(run.past_workflows) + len(run.workflows), "sites": len(run.sites), "realization": rec["realization"] is not None}
