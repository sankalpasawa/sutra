"""store.py — the run folder is the truth.

Nothing lives in memory. A run is a folder; its state file says where we are and
its event log says how it got there. Kill the process at any moment and reopening
tells you exactly where it stopped, because every write lands before the next step
starts.

Writes are atomic: temp file in the SAME directory, then rename. A crash mid-write
leaves a stray .tmp, never a half-written state file that resume would trust.
"""
import json
import os
import re
import shutil
import tempfile
import time
import uuid

STATES = ("running", "waiting", "done", "stopped", "failed")

# ---- where the data lives --------------------------------------------------------------
# Never under this folder. The code tree ships read-only inside a signed app, so every path
# is derived, lazily, from data_dir(): the env var if set, else ~/.sutra-ui/agents/seo.
# The layout under that root is unchanged: chats/, knowledge/, library/, memory.jsonl,
# connections.json.

DEFAULT_DATA_DIR = os.path.join("~", ".sutra-ui", "agents", "seo")
_DATA_DIR = None             # set by set_data_dir(); None means "ask the environment"


def root_dir():
    """The PERSON's folder: what data_dir() is before any company has been switched to.

    The first company lives here too, exactly where every install has always kept its data, and
    so do the things that belong to the person rather than to a company: the DataForSEO login,
    the Voyage key, and the list of companies (see seo_agent/companies.py).
    """
    env = os.environ.get("SEO_AGENT_DATA", "").strip()
    return os.path.abspath(os.path.expanduser(env or DEFAULT_DATA_DIR))


def data_dir():
    """The folder the ACTIVE company's knowledge, chats and library live under.

    Resolved on every call, not at import, so a test can point it at a temp folder by
    setting SEO_AGENT_DATA before the first write, or by calling set_data_dir(). Switching
    company is exactly a set_data_dir() to that company's folder.
    """
    if _DATA_DIR:
        return _DATA_DIR
    return root_dir()


def set_data_dir(path):
    """Override the root for this process. None goes back to the environment."""
    global _DATA_DIR
    _DATA_DIR = os.path.abspath(os.path.expanduser(path)) if path else None
    return data_dir()


def chats_dir():
    return os.path.join(data_dir(), "chats")


def library_dir():
    return os.path.join(data_dir(), "library")


def knowledge_dir():
    return os.path.join(data_dir(), "knowledge")


def memory_file():
    return os.path.join(data_dir(), "memory.jsonl")


def connections_file():
    return os.path.join(data_dir(), "connections.json")


# The old module-level names, kept readable for anything that still says store.CHATS.
# Resolved on access (PEP 562), so they follow data_dir() rather than freezing at import.
_LEGACY_PATHS = {"DATA": data_dir, "CHATS": chats_dir, "LIBRARY": library_dir,
                 "KNOWLEDGE": knowledge_dir, "MEMORY_FILE": memory_file,
                 "CONNECTIONS": connections_file}


def __getattr__(name):
    if name in _LEGACY_PATHS:
        return _LEGACY_PATHS[name]()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# ---- atomic writes ---------------------------------------------------------------------

def write_json(path, data, indent=2):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path, since=0):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < since:
                    continue
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return out


def slug(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:limit].rstrip("-")) or "untitled"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- chats -----------------------------------------------------------------------------

def chat_dir(chat_id):
    return os.path.join(chats_dir(), chat_id)


def new_chat(title="New chat"):
    chat_id = "c-" + uuid.uuid4().hex[:8]
    d = chat_dir(chat_id)
    os.makedirs(os.path.join(d, "runs"), exist_ok=True)
    write_json(os.path.join(d, "chat.json"), {
        "id": chat_id, "title": title,
        "created_at": now(), "updated_at": now(),
    })
    write_json(os.path.join(d, "messages.json"), [])
    return chat_id


def list_chats():
    out = []
    if os.path.isdir(chats_dir()):
        for name in os.listdir(chats_dir()):
            c = read_json(os.path.join(chats_dir(), name, "chat.json"))
            if c:
                out.append(c)
    return sorted(out, key=lambda c: c.get("updated_at", ""), reverse=True)


def get_messages(chat_id):
    return read_json(os.path.join(chat_dir(chat_id), "messages.json"), []) or []


def save_messages(chat_id, messages):
    write_json(os.path.join(chat_dir(chat_id), "messages.json"), messages)
    meta = read_json(os.path.join(chat_dir(chat_id), "chat.json"), {}) or {}
    meta["updated_at"] = now()
    write_json(os.path.join(chat_dir(chat_id), "chat.json"), meta)


def delete_chat(chat_id):
    """Throw a chat away: its messages, its runs, and every artifact under it.

    The Library is NOT touched. An article that reached the Library is a finished piece of work
    that happens to have been written in this chat; deleting the conversation must not delete
    the article. The chat's own run folders go, so the milestone strip on any Library row that
    pointed at this chat falls back to the row's saved state, which is what it did before
    `library_start` existed anyway.

    Returns True if a chat was removed, False if there was nothing there.
    """
    d = chat_dir(chat_id)
    # Refuse a chat_id that climbs out of the chats folder. `..` in a path deletes the wrong tree.
    root = os.path.realpath(chats_dir())
    here = os.path.realpath(d)
    if os.path.dirname(here) != root or not os.path.isdir(here):
        return False
    shutil.rmtree(here, ignore_errors=True)
    return not os.path.isdir(here)


def set_chat_title(chat_id, title):
    p = os.path.join(chat_dir(chat_id), "chat.json")
    meta = read_json(p, {}) or {}
    meta["title"] = title
    meta["updated_at"] = now()
    write_json(p, meta)


# ---- runs ------------------------------------------------------------------------------

def run_dir(chat_id, run_id):
    return os.path.join(chat_dir(chat_id), "runs", run_id)


def new_run(chat_id, topic=""):
    run_id = "r-" + time.strftime("%H%M%S") + "-" + slug(topic, 32)
    d = run_dir(chat_id, run_id)
    os.makedirs(os.path.join(d, "artifacts"), exist_ok=True)
    save_state(chat_id, run_id, {
        "run_id": run_id, "chat_id": chat_id, "topic": topic,
        "status": "running", "stage": "", "current_step": None,   # unknown until a tool declares it
        "waiting_on": None, "credits_spent": 0,
        "started_at": now(), "updated_at": now(),
    })
    return run_id


def state_path(chat_id, run_id):
    return os.path.join(run_dir(chat_id, run_id), "state.json")


def get_state(chat_id, run_id):
    return read_json(state_path(chat_id, run_id))


def save_state(chat_id, run_id, state):
    state["updated_at"] = now()
    write_json(state_path(chat_id, run_id), state)


def patch_state(chat_id, run_id, **fields):
    s = get_state(chat_id, run_id) or {}
    s.update(fields)
    save_state(chat_id, run_id, s)
    return s


def list_runs(chat_id):
    d = os.path.join(chat_dir(chat_id), "runs")
    out = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            s = get_state(chat_id, name)
            if s:
                out.append(s)
    return out


# ---- events ----------------------------------------------------------------------------

def events_path(chat_id, run_id):
    return os.path.join(run_dir(chat_id, run_id), "events.jsonl")


def emit(chat_id, run_id, type, **fields):
    ev = {"t": now(), "type": type}
    ev.update(fields)
    append_jsonl(events_path(chat_id, run_id), ev)
    return ev


def get_events(chat_id, run_id, since=0):
    return read_jsonl(events_path(chat_id, run_id), since)


# ---- artifacts -------------------------------------------------------------------------

def artifact_path(chat_id, run_id, name):
    return os.path.join(run_dir(chat_id, run_id), "artifacts", name)


def save_artifact(chat_id, run_id, name, data):
    p = artifact_path(chat_id, run_id, name)
    if isinstance(data, (dict, list)):
        write_json(p, data)
    else:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, p)
    return p


def load_artifact(chat_id, run_id, name):
    p = artifact_path(chat_id, run_id, name)
    if name.endswith(".json"):
        return read_json(p)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


# ---- knowledge / memory / connections ---------------------------------------------------

def knowledge(name, default=None):
    """knowledge/<name>. JSON when the name ends in .json, else the file's text (or default).
    `name` may carry a subfolder: knowledge("brand/writer-brief.md")."""
    p = os.path.join(knowledge_dir(), name)
    if name.endswith(".json"):
        return read_json(p, default)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def save_knowledge(name, data):
    """Atomic. dict/list -> JSON; str -> text. Subfolders are created."""
    p = os.path.join(knowledge_dir(), name)
    if isinstance(data, (dict, list)):
        write_json(p, data)
        return p
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else str(data))
        os.chmod(tmp, 0o644)
        os.replace(tmp, p)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise
    return p


def list_knowledge(sub=""):
    """Names (relative to knowledge/) of the files in a subfolder, sorted."""
    d = os.path.join(knowledge_dir(), sub) if sub else knowledge_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        fp = os.path.join(d, f)
        if os.path.isfile(fp):
            out.append((sub + "/" + f) if sub else f)
    return out


def memory_rules(active_only=True):
    rows = read_jsonl(memory_file())
    return [r for r in rows if r.get("active", True)] if active_only else rows


def add_memory(text, kind="rule", source="user", from_run=None):
    row = {"id": "m-" + uuid.uuid4().hex[:6], "t": now(), "text": text,
           "kind": kind, "source": source, "active": True}
    if from_run:
        row["from_run"] = from_run
    append_jsonl(memory_file(), row)
    return row


def set_memory_active(mem_id, active):
    rows = read_jsonl(memory_file())
    for r in rows:
        if r.get("id") == mem_id:
            r["active"] = active
    d = os.path.dirname(memory_file())
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, memory_file())


# THE PERSON'S KEYS, shared by every company they work for (owner, 2026-09-11: one person doing
# the content for more than one company). A DataForSEO account and a Voyage key belong to the
# person, so they live in the ROOT connections.json and every company reads them from there.
# Everything else in connections.json -- the team workspace above all -- is the company's own,
# because a Supabase workspace is one company's team. With one company both files are the same
# file, and nothing below behaves any differently from before.
PERSON_KEYS = ("dataforseo_login", "dataforseo_password", "voyage_key",
               "anthropic_key", "openai_key")


def _person_connections_file():
    return os.path.join(root_dir(), "connections.json")


def _one_file():
    return os.path.abspath(connections_file()) == os.path.abspath(_person_connections_file())


def connections():
    own = read_json(connections_file(), {}) or {}
    if _one_file():
        return own
    merged = dict(own)
    person = read_json(_person_connections_file(), {}) or {}
    for k in PERSON_KEYS:
        if k in person:
            merged[k] = person[k]
    return merged


def save_connections(data):
    """Save what connections() handed out, each part to the file it belongs in.

    NEVER DELETES A PERSON'S KEY BY OMISSION. A save that simply does not mention the DataForSEO
    login leaves it alone; only a key sent BLANK is cleared. So a caller that writes one workspace
    field cannot take somebody's paid login away with it.
    """
    data = dict(data or {})
    if _one_file():
        for k in PERSON_KEYS:
            if k in data and not str(data[k] or "").strip():
                data.pop(k)
        _write_private(connections_file(), data)
        return
    person = read_json(_person_connections_file(), {}) or {}
    for k in PERSON_KEYS:
        if k in data:
            if str(data[k] or "").strip():
                person[k] = data[k]
            else:
                person.pop(k, None)
    _write_private(_person_connections_file(), person)
    _write_private(connections_file(), {k: v for k, v in data.items() if k not in PERSON_KEYS})


def _write_private(path, data):
    write_json(path, data)
    # Secrets are owner-only, the way ~/.sutra-ui/composio.json is kept.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---- library ---------------------------------------------------------------------------
#
# A Library row used to be born once, at the end, when a draft was approved. The owner asked for
# the opposite (2026-09-09): the row appears when the article STARTS and fills in as the run makes
# things, so he can watch it and open any half-finished piece without the agent stopping to show
# him. That is `library_start` at the top of a run and `library_finish` at the end of it.
#
# The thing that makes it cheap: NOTHING IS COPIED WHILE THE RUN IS LIVE. A run already writes
# every step's file to chats/<chat>/runs/<run>/artifacts/, and a Library row already carries
# chat_id and run_id, so the progress strip is DERIVED from the run's own folder every time it is
# asked for. Nothing can drift from the run, and a run that dies half way leaves a row that
# honestly shows how far it got. The copies into the Library folder still happen, but only once,
# at finish, so a finished article survives its chat being deleted.

# The five things a person watches for, in the order the strip shows them, and the file each one
# is read from. `needs` is a second file that must also be there before the milestone counts.
#
# `edited` reads write-report.json, which is the only file in a run that records what the editing
# passes (coherence, readable, sentences, slop, links, clean) actually changed. It needs draft.md
# too, because write_article ALSO writes write-report.json when the plan fails its freeze check
# and no draft is ever written; without that guard the strip would show "edited" lit above a draft
# that does not exist.
MILESTONES = [
    {"key": "research", "label": "Researched",
     "note": "the brief this article is built on", "file": "research.json"},
    {"key": "plan", "label": "Planned",
     "note": "the headings, the evidence behind each one and the links", "file": "blueprint.json"},
    # AFTER the plan, not before it. The search picture is written at the end of the gather step,
    # and gather is planner step 1 INSIDE write_article, which only runs once the blueprint exists.
    # Listing it earlier would light the strip out of order and read as a step that had been
    # skipped. (Caught on integration, 2026-09-09: the contract and the design doc disagreed about
    # where it is written, and the code settles it.)
    {"key": "picture", "label": "The search picture",
     "note": "what the search results show, and which questions were kept",
     "file": "search-picture.md"},
    {"key": "draft", "label": "Written",
     "note": "the article as the writer left it", "file": "draft.md"},
    {"key": "edited", "label": "Edited",
     "note": "what each editing pass changed", "file": "write-report.json", "needs": "draft.md"},
]

MILESTONE_FILES = {m["key"]: m["file"] for m in MILESTONES}


def library_item_id(chat_id, run_id):
    """The id of the row for this run. Decided in ONE place, and derived only from the run.

    A finished item used to be `<date>-<slug-of-the-title>`. At run start there is no title, and
    the rename at the end must NOT move the row, or the screen loses the thing it was watching.
    So the id is the run's own identity: `run-<chat_id>-<run_id>`.

    Three reasons for that shape and no other:
      * it is a pure function of (chat_id, run_id), so `library_start` is idempotent by
        construction: call it twice and it computes the same id and finds the row already there;
      * it holds nothing that changes, so the rename at finish touches the title and never the id;
      * there is deliberately NO date in it. A date looks tidy in a folder listing, but a run that
        starts at 23:55 and finishes at 00:05 would compute two different ids and leave two rows,
        which is the exact bug this whole change exists to avoid.

    It is lowercase letters, digits and hyphens only, so it is safe as a folder name and safe in a
    URL path, and it stays inside the 80 characters the API's id check allows.
    """
    return ("run-%s-%s" % (chat_id, run_id))[:80]


def _stat(path):
    try:
        return os.stat(path)
    except OSError:
        return None


def _at(st):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)) if st else None


def milestones(chat_id, run_id):
    """What this run has actually produced so far, read from the run's own artifacts folder.

    Derived, never stored. One os.stat per named file (five, and one shared with `needs`), which
    is why this is cheap enough to run for every row of `library_list` on every poll of the
    Library screen: a row already costs one JSON read, and five stats beside it do not register.

    A milestone that is not there yet comes back with `exists: false` so the screen can grey it,
    rather than being left out, because the strip has to show the whole journey from the start.

    An empty list means "we cannot know": the run folder is gone (an old row whose chat was
    deleted). That is deliberately different from five falses, which means "we looked and the run
    never got that far". A finished article whose chat was deleted must not read as a broken one.
    """
    if not chat_id or not run_id:
        return []
    arts = os.path.join(run_dir(chat_id, run_id), "artifacts")
    if not os.path.isdir(arts):
        return []
    cache = {}

    def st(name):
        if name not in cache:
            cache[name] = _stat(os.path.join(arts, name))
        return cache[name]

    out = []
    for m in MILESTONES:
        s = st(m["file"])
        # a zero-byte file is a step that crashed mid-write, not a step that finished
        ok = bool(s) and s.st_size > 0
        if ok and m.get("needs"):
            n = st(m["needs"])
            ok = bool(n) and n.st_size > 0
        out.append({"key": m["key"], "label": m["label"], "note": m["note"], "file": m["file"],
                    "exists": ok, "at": _at(s) if ok else None,
                    "bytes": s.st_size if ok else 0})
    return out


def _copy_into(src, dest):
    """Copy one file, atomically, the way every other save here works: temp file in the SAME
    folder, then rename over the target. A crash mid-copy leaves the old complete file."""
    d = os.path.dirname(dest)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with open(src, "rb") as s, os.fdopen(fd, "wb") as t:
            t.write(s.read())
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _write_text(path, text):
    """Atomic text write. Used for draft.md, which used to be written straight over itself: a
    crash there destroyed the article and left half of a new one in its place."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text or "")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def library_start(chat_id, run_id, request_text=""):
    """Put the row on the Library screen NOW, at the top of the run, and return its id.

    The row is born with the only two things that are true this early: a placeholder name
    ("Writing…") and the state `writing`. Everything else fills itself in, because the strip is
    derived from the run rather than written here.

    Idempotent, and not by luck: the id is a pure function of the run (see `library_item_id`), so
    a second call finds the row already on disk and returns the same id without touching it. Two
    threads racing to start the same run therefore cannot make two rows.
    """
    item_id = library_item_id(chat_id, run_id)
    d = os.path.join(library_dir(), item_id)
    p = os.path.join(d, "meta.json")
    have = read_json(p)
    if have:
        return have.get("id") or item_id
    meta = {"id": item_id, "title": "Writing…", "status": "writing",
            "chat_id": chat_id, "run_id": run_id,
            "request": (request_text or "").strip()[:400],
            "words": 0, "created_at": now(), "started_at": now()}
    write_json(p, meta)
    return item_id


def library_finish(item_id, title, draft_md, meta_extra=None, chat_id=None, run_id=None):
    """Give the row its real name, mark it ready, and write the article into it. Returns the meta.

    The rename is a rename and nothing else: the id the row was born with is the id it keeps, or
    the screen loses the row a person was watching mid-run.

    `item_id` may be None. Old runs exist that never called `library_start`, and the publish route
    can be fired on any run at all, so a finish with no row simply makes one. `chat_id` and
    `run_id` may come as keyword arguments or inside `meta_extra`, whichever the caller finds
    easier; with them the new row gets the run's own id, so a `library_start` fired later for the
    same run still lands on this row instead of making a second one.

    This is also the ONE moment anything is copied. While the run is live the strip is derived
    from the run's folder; at finish the research, the plan and the topic list are copied in
    beside the article so that deleting the chat later does not empty the Library.
    """
    extra = dict(meta_extra or {})
    chat_id = chat_id or extra.get("chat_id")
    run_id = run_id or extra.get("run_id")
    d = os.path.join(library_dir(), item_id) if item_id else None
    meta = read_json(os.path.join(d, "meta.json")) if d else None
    if not meta:
        # an id the caller named is honoured even when the row is not there yet: it may be the id
        # the screen is already holding. Only a finish with no id at all mints one.
        item_id = item_id or (library_item_id(chat_id, run_id) if chat_id and run_id
                              else time.strftime("%Y-%m-%d") + "-" + slug(title))
        d = os.path.join(library_dir(), item_id)
        meta = read_json(os.path.join(d, "meta.json")) or {
            "id": item_id, "chat_id": chat_id, "run_id": run_id, "created_at": now()}
    meta["id"] = item_id                      # never re-minted: the row keeps the id it was born with
    meta["title"] = title
    meta["status"] = "ready"
    meta["words"] = len((draft_md or "").split())
    meta["finished_at"] = now()
    # the row already knows its run when it was started; a finish that names one wins, a finish
    # that names none must not blank what is there
    if chat_id:
        meta["chat_id"] = chat_id
    if run_id:
        meta["run_id"] = run_id
    extra.pop("chat_id", None)
    extra.pop("run_id", None)
    meta.update(extra)
    os.makedirs(d, exist_ok=True)
    _write_text(os.path.join(d, "draft.md"), draft_md or "")
    if meta.get("chat_id") and meta.get("run_id"):
        for name in ("research.json", "blueprint.json", "topics.json"):
            src = artifact_path(meta["chat_id"], meta["run_id"], name)
            if os.path.exists(src):
                _copy_into(src, os.path.join(d, name))
    write_json(os.path.join(d, "meta.json"), meta)
    return meta


def library_save(chat_id, run_id, title, draft_md, meta_extra=None):
    """The old one-shot save, kept because callers and tests still say it. It is now a thin call
    onto `library_finish`, so a run that already has a live row is UPDATED and never doubled."""
    meta = library_finish(library_item_id(chat_id, run_id), title, draft_md, meta_extra,
                          chat_id=chat_id, run_id=run_id)
    return meta["id"]


def library_update(item_id, draft_md, title=None):
    """Write an edited article back over itself, and re-count it.

    A saved article is a document, not a transcript of a run: fixing a sentence should not need a
    live agent. Title and body only. Status has its own route, and everything else in the meta is
    provenance that an edit must not rewrite.

    Restored 2026-09-09. It was built, then lost when a corrupted git store forced a fresh clone,
    which left the Library read-only with the route calling a function that was no longer there.

    The body is written through a temp file in the same folder and renamed over the target, like
    every other save here: a crash mid-write must leave the old complete article, never half of a
    new one.
    """
    d = os.path.join(library_dir(), item_id)
    meta = read_json(os.path.join(d, "meta.json"))
    if not meta:
        return None
    path = os.path.join(d, "draft.md")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(draft_md)
    os.replace(tmp, path)
    meta["words"] = len(draft_md.split())
    if title:
        meta["title"] = title
    meta["edited_at"] = now()
    write_json(os.path.join(d, "meta.json"), meta)
    return meta


def library_list():
    """Every row, newest first, each carrying its own progress strip.

    The strip is on the LIST and not only on the single item, because the Library screen polls
    this route while a run is going and the whole point of the change is watching a row fill in.
    It is affordable: a row already costs one JSON read, and `milestones` adds five os.stat calls
    beside it (one for a row whose run folder is gone, which is the common case for old rows).
    """
    out = []
    if os.path.isdir(library_dir()):
        for name in os.listdir(library_dir()):
            m = read_json(os.path.join(library_dir(), name, "meta.json"))
            if m:
                m.setdefault("status", "draft")
                m["milestones"] = milestones(m.get("chat_id"), m.get("run_id"))
                out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def library_get(item_id):
    d = os.path.join(library_dir(), item_id)
    meta = read_json(os.path.join(d, "meta.json"))
    if not meta:
        return None
    try:
        with open(os.path.join(d, "draft.md"), encoding="utf-8") as f:
            meta["draft"] = f.read()
    except FileNotFoundError:
        meta["draft"] = ""
    meta["research"] = read_json(os.path.join(d, "research.json"))
    meta["blueprint"] = read_json(os.path.join(d, "blueprint.json"))
    meta.setdefault("status", "draft")
    meta["milestones"] = milestones(meta.get("chat_id"), meta.get("run_id"))
    return meta


def library_artifact(item_id, name):
    """One milestone's file, read out of the RUN, for the panel to show. None when there is none.

    `name` is a milestone key ("plan") or the file it stands for ("blueprint.json"); the key is
    what the screen should send, the filename is accepted because the strip already carries it.

    This is a file-serving path, so it is gated twice, in this order:
      1. containment — the resolved real path must sit inside this run's own artifacts folder, so
         a name like "../../../etc/passwd" gets nothing even if it slipped past the route's regex;
      2. an allow-list — only the five milestone files are servable. The run folder holds keys,
         state and every work file, and none of that is this route's business.
    Order matters: containment is checked first so that it is the rule doing the work, rather than
    the allow-list quietly hiding a traversal hole.
    """
    meta = read_json(os.path.join(library_dir(), item_id, "meta.json"))
    if not meta or not meta.get("chat_id") or not meta.get("run_id"):
        return None
    fname = MILESTONE_FILES.get(name, name)
    arts = os.path.realpath(os.path.join(run_dir(meta["chat_id"], meta["run_id"]), "artifacts"))
    p = os.path.realpath(os.path.join(arts, fname))
    if p != arts and not p.startswith(arts + os.sep):
        return None
    if os.path.basename(p) not in set(MILESTONE_FILES.values()):
        return None
    st = _stat(p)
    if not st or not st.st_size:
        return None
    spec = next(m for m in MILESTONES if m["file"] == os.path.basename(p))
    row = {"key": spec["key"], "label": spec["label"], "note": spec["note"],
           "file": spec["file"], "bytes": st.st_size, "at": _at(st)}
    if spec["file"].endswith(".json"):
        row["data"] = read_json(p)
    else:
        with open(p, encoding="utf-8") as f:
            row["text"] = f.read()
    return row


def library_delete(item_id):
    import shutil
    d = os.path.join(library_dir(), item_id)
    if os.path.isdir(d):
        shutil.rmtree(d)
        return True
    return False


def library_set_status(item_id, status):
    p = os.path.join(library_dir(), item_id, "meta.json")
    m = read_json(p)
    if m:
        m["status"] = status
        write_json(p, m)
    return m
