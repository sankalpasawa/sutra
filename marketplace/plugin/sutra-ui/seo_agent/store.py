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


def data_dir():
    """The root everything a user's install creates lives under.

    Resolved on every call, not at import, so a test can point it at a temp folder by
    setting SEO_AGENT_DATA before the first write, or by calling set_data_dir().
    """
    if _DATA_DIR:
        return _DATA_DIR
    env = os.environ.get("SEO_AGENT_DATA", "").strip()
    return os.path.abspath(os.path.expanduser(env or DEFAULT_DATA_DIR))


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
        "status": "running", "stage": "topic", "current_step": None,
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
    return read_json(os.path.join(knowledge_dir(), name), default)


def save_knowledge(name, data):
    write_json(os.path.join(knowledge_dir(), name), data)


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


def connections():
    return read_json(connections_file(), {}) or {}


def save_connections(data):
    write_json(connections_file(), data)
    # Secrets are owner-only, the way ~/.sutra-ui/composio.json is kept.
    try:
        os.chmod(connections_file(), 0o600)
    except OSError:
        pass


# ---- library ---------------------------------------------------------------------------

def library_save(chat_id, run_id, title, draft_md, meta_extra=None):
    item_id = time.strftime("%Y-%m-%d") + "-" + slug(title)
    d = os.path.join(library_dir(), item_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "draft.md"), "w", encoding="utf-8") as f:
        f.write(draft_md or "")
    for name in ("research.json", "blueprint.json", "topics.json"):
        src = artifact_path(chat_id, run_id, name)
        if os.path.exists(src):
            with open(src, encoding="utf-8") as s, open(os.path.join(d, name), "w", encoding="utf-8") as t:
                t.write(s.read())
    meta = {"id": item_id, "title": title, "status": "draft",
            "chat_id": chat_id, "run_id": run_id,
            "words": len((draft_md or "").split()), "created_at": now()}
    meta.update(meta_extra or {})
    write_json(os.path.join(d, "meta.json"), meta)
    return item_id


def library_list():
    out = []
    if os.path.isdir(library_dir()):
        for name in os.listdir(library_dir()):
            m = read_json(os.path.join(library_dir(), name, "meta.json"))
            if m:
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
    return meta


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
