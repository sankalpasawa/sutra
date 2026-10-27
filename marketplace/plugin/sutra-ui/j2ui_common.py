"""j2ui_common.py -- the J2 view's scope, its one read of a department, and the shapes it never leaves empty-handed.

The department's UI is the J2 prototype's page, drawn from an adapter built on Sutra's own records (UI port, package
j2ui-core). This module is the adapter's ground, and every other j2ui module stands on it:

    scope        is_j2_kind / need: the one place that decides which departments the J2 view is for (a website team)
    shapes       STATE_KEYS and the EMPTY_* shapes: a wrong shape blanks the page, so a builder that fails returns one
    clean        no private key and no absolute machine path in anything the adapter sends
    journals     JournalTail / LedgerTail: an append-only file read once, then only what was appended since
    one read     get_ctx(ref): a Ctx, one read of the department per file signature, shared by every endpoint of a poll

The adapter only reads. It writes no record and no file of its own (the chat's ids live in memory), speaks as no
function, and calls the records' public readers; the owner's words reach the record through the existing writers (see
j2ui_say). Every cache here is keyed by (records home, ref), never the ref alone: tests reuse a ref against fresh homes,
and the Beta channel has a home of its own.
"""
import bisect
import copy
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import engine_runtime as R
import functions_view as F
import j2_runtime as J
import layers
import owner_words
import website_dept as W

KINDS_SUPPORTED = ("website",)           # departments of any other kind keep the classic screens (a mapping is not designed)
MIN_REBUILD_S = 1.0                      # the page polls every 700 ms; a running engine changes steps.jsonl on every step
TICK_S = 10                              # a read is never older than this many seconds, whatever the files say
FUNCS = tuple(R.FUNCTIONS)               # Identity, Adaptation, Priority, Coordination, Audit
STATE_CAP = 30                           # max_turns: the page does not read it


# ---- scope: the one place that decides who the J2 view is for -----------------------------------------------------------
class NotJ2(Exception):
    """The department does not exist here, or is not one the J2 view is for."""


def is_j2_kind(kind):
    return kind in KINDS_SUPPORTED


REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


def need(ref):
    """The department's record when the J2 view is for it: on the engine runtime, of a supported kind, not a Root.
    Anything else (an unknown ref, a ref with path characters, a runtime-1 department, a Root, a kind with no mapping)
    is NotJ2, which every route answers as 404 'no such department'."""
    if not isinstance(ref, str) or not REF.fullmatch(ref):
        raise NotJ2(str(ref))
    try:
        d = W.dept(ref)
    except (ValueError, OSError) as exc:
        raise NotJ2(str(ref)) from exc
    if not isinstance(d, dict) or d.get("runtime") != 2 or not is_j2_kind(d.get("kind")):
        raise NotJ2(ref)
    return d


# ---- the shapes the page reads ---------------------------------------------------------------------------------------
class _Shape(dict):
    """An empty shape that is both the value and a maker of fresh copies: EMPTY_BOARD == {...} and EMPTY_BOARD() is its own."""

    def __call__(self):
        return copy.deepcopy(dict(self))


#: the 56 keys of api/state: the prototype's snapshot (48) + output_info (7 more; rubric is in both) + saved (j2_server)
EMPTY_DEFAULTS = (("chat", []), ("total", 0), ("status", "idle"), ("thinking", None), ("step", 0), ("steps", {}), ("goal", None),
                  ("stamped", False), ("workflows", []), ("budget", 0), ("spent", 0), ("conflicts", []), ("audits", []),
                  ("versions", 0), ("cycle", 0), ("calls", 0), ("error", None), ("done", False), ("atoms_v1", {}),
                  ("turn", None), ("cycle_turns", 0), ("max_turns", STATE_CAP), ("paused", None), ("outcome", None),
                  ("style", None), ("rubric", []), ("playbooks", []), ("playbooks_used", []), ("playbook_saved", None),
                  ("mock", False), ("model", "not recorded"), ("fixes", 1), ("force_audit_fail", None),
                  ("test_lessons", False), ("force_question", None), ("has_board", False), ("placeholders", []),
                  ("report", None), ("sections", []), ("write_lock", None), ("agents", {}), ("lanes", []), ("call_log", []),
                  ("workable", None), ("memory", False), ("lessons", []), ("lessons_used", []), ("lessons_saved", []),
                  ("output", "website"), ("output_label", "Website"), ("doc", False), ("conditions", None), ("files", []),
                  ("docset", []), ("docset_files", []), ("saved", None))
STATE_KEYS = tuple(k for k, _ in EMPTY_DEFAULTS)
#: the keys j2ui_work.build fills (exactly these 13); every other key of the state is j2ui_state's
WORK_KEYS = ("workflows", "atoms_v1", "sections", "agents", "lanes", "style", "conflicts", "audits", "conditions", "rubric",
             "workable", "call_log", "report")
EMPTY_STATE = _Shape(EMPTY_DEFAULTS)

#: the prototype's j2_map.LEGEND at the pinned commit (the Map's key); 14 rows
LEGEND = [{"key": k, "label": label, "drawn": True} for k, label in (
    ("function", "function"), ("engine", "engine"), ("work", "work with its version"), ("filed", "filed and checked"),
    ("done_unchecked", "done · checks did not pass"), ("running", "running now"), ("left_open", "left open"),
    ("waiting_on_you", "waiting on you"), ("fault", "fault"), ("not_made", "not made"), ("handoff", "hand-off"),
    ("speaks_to", "speaks to"), ("asks", "asks (board)"), ("uses", "uses (board)"))]


def EMPTY_MAP(why="nothing to draw yet"):
    """The prototype's j2_map.empty(): the Map of a department with nothing to draw, and why."""
    return {"schema": "map/1", "run": None, "live": False,
            "status": {"state": "not started", "state_status": "idle", "checks": {"passed": 0, "run": 0}},
            "nodes": [], "edges": [], "legend": copy.deepcopy(LEGEND), "built_from": [], "not_recorded": [str(why)]}


_DOC = {"asked": False, "text": None, "workflows": []}
EMPTY_BOARD = _Shape({"schema": "board/1", "entries": []})
EMPTY_ARTIFACTS = _Shape({"deliverables": [], "records": []})
EMPTY_DOCS = _Shape({"prd": dict(_DOC), "hld": dict(_DOC), "lld": dict(_DOC)})
EMPTY_REFS = _Shape({"conditions": {}, "rubric": {}})
EMPTY_PREVIEW = _Shape({"anchor": None, "html": None})


# ---- nothing private, no path of this machine --------------------------------------------------------------------------
#: A path of THIS machine is one under a folder this machine has: the user's home, the records' home, the temp folder and
#: the app's own folder (each as the program names it and as the disk resolves it: /var is /private/var on a Mac), the
#: Mac's /private/var/folders and /Volumes, `~/...`, and a Windows drive path. A folder name alone says nothing: '/home/about',
#: '/private/members', '/etc/terms' and '/var/news' are the pages of a site unless they sit under one of those folders, and
#: the owner quotes pages in rules, in done-when and in answers, so a path is shortened only when it is this machine's.
#: A root alone is a page too (/home, /tmp, /Volumes, /opt-in); a relative path (build/v1/index.html), a date (5/6/2026) and
#: a URL are not paths of this machine, and none of these is ever touched. `~` and a drive letter count only where a path
#: would start (the start of the text or after a space, a quote or a bracket), and a drive letter followed by a slash only
#: with a folder of Windows after it ('Plan B:/pricing' is a plan and a page, not a drive).
_SEG = r"[\\/][\w.@%+=~-]+"
_START = r"(?<![^\s\"'(\[{<=])"
_FIXED_ROOTS = ("/private/var/folders", "/var/folders", "/Volumes")
_WINDOWS = r"(?:Users|Windows|ProgramData|Documents)"
_HOME_PATH = (_START + r"(?:~|[A-Za-z]:(?=\\|[\\/]" + _WINDOWS + r"\b))(?:" + _SEG + r")+[\\/]?")
_TAIL_PUNCT = ".,;:!?"
#: the key of the owner's goal, rules and done-when: the owner's words, which are never rewritten (rule 4e)
OWNER_KEYS = ("goal",)


def _machine_roots():
    """The folders of this machine, longest first, as absolute paths with no trailing slash."""
    found = set(_FIXED_ROOTS)
    here = Path(__file__).resolve().parent
    for get in (Path.home, W.home, tempfile.gettempdir, lambda: here):
        try:
            path = str(get())
            found.update((path, os.path.realpath(path)))
        except Exception:  # noqa: BLE001 -- a home that cannot be found is one folder fewer, never a failed response
            continue
    return tuple(sorted({r.rstrip("/") for r in found if r.startswith("/") and len(r.rstrip("/")) > 1}, key=lambda r: (-len(r), r)))


def _compile(roots):
    """The path rule over these folders: a path under one (at least one name below it), the folder itself only when it is
    this machine's own and deeper than one name (/Users/me, not /tmp, /Volumes or /var/folders), and a home path (~/..., a
    drive path)."""
    alt = "|".join(re.escape(r) for r in roots)
    deep = "|".join(re.escape(r) for r in roots if r.count("/") > 1 and r not in _FIXED_ROOTS)
    under = r"(?<![\w./~-])(?:" + alt + r")(?:" + _SEG + r")+[\\/]?" if alt else None
    alone = r"(?<![\w./~-])(?:" + deep + r")[\\/]?(?![\w@%+=~-]|\.\w)" if deep else None
    return re.compile("|".join(x for x in (under, alone, _HOME_PATH) if x))


_RULE = {"key": None, "re": None}
_RULE_LOCK = threading.Lock()


def _rule():
    """The compiled path rule for this machine as it stands: made again whenever the home, the records' home or the temp
    folder changes (a test binds them to a folder of its own, and the Beta channel has a records home of its own)."""
    key = (os.environ.get("HOME"), os.environ.get("USERPROFILE"), os.environ.get("SUTRA_NATIVE_DEPT_HOME"), os.environ.get("TMPDIR"),
           tempfile.tempdir)
    with _RULE_LOCK:
        if _RULE["key"] != key:
            _RULE["key"], _RULE["re"] = key, _compile(_machine_roots())
        return _RULE["re"]


class _PathRule:
    """ABS_PATH: the path rule of this machine, as a compiled pattern's search/sub/finditer (the pattern itself is made from
    the folders of the moment, see _rule)."""

    def search(self, text, *a):
        return _rule().search(text, *a)

    def sub(self, repl, text, *a, **k):
        return _rule().sub(repl, text, *a, **k)

    def finditer(self, text, *a):
        return _rule().finditer(text, *a)

    @property
    def pattern(self):
        return _rule().pattern


ABS_PATH = _PathRule()


def _short_path(m):
    path = m.group(0)
    tail = ""
    while path and path[-1] in _TAIL_PUNCT:
        tail, path = path[-1] + tail, path[:-1]
    name = re.split(r"[\\/]", path.rstrip("\\/"))[-1]
    return (name or path) + tail


def shorten(text):
    """One string with each path of this machine in it shortened to its file name; anything else as it is."""
    return _rule().sub(_short_path, text) if isinstance(text, str) else text


class Said(str):
    """A line that carries the owner's own words (an ask's or a run's `words`, said as the owner said them) and whose lead,
    the machine's, has passed the path rule already (see said): clean() sends it exactly as it is."""


def said(line, words=None):
    """owner_words.kept(line, words) for a line that goes to the page: the lead the machine wrote is said plainly and passes
    the path rule, the owner's words after it are never rewritten, and the result is a Said that clean() leaves alone. A
    line that does not end with the owner's words is all the machine's: said plainly, and left to clean()."""
    if not isinstance(line, str):
        return line
    if isinstance(words, str) and words and line.endswith(words):
        return Said(shorten(owner_words.plain(line[:-len(words)])) + words)
    return owner_words.plain(line)


def keep_said(source, text):
    """`text` as a Said when `source` was one: a line cut or re-spelled from the owner's words (a lane's, a Map node's) stays
    the owner's words, whole as far as it goes, and clean() leaves it as it is."""
    return Said(text) if isinstance(source, Said) else text


def _private_only(value):
    """The value with the ledger's private keys dropped at any depth and every string left exactly as it is."""
    if isinstance(value, dict):
        return {k: _private_only(v) for k, v in value.items() if str(k).lower() not in J.PRIVATE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_private_only(v) for v in value]
    return value


def _clean(value, rule):
    if isinstance(value, Said):
        return value
    if isinstance(value, dict):
        own_text = value.get("who") == "user"
        return {k: _private_only(v) if k in OWNER_KEYS or (own_text and k == "text") else _clean(v, rule)
                for k, v in value.items() if str(k).lower() not in J.PRIVATE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_clean(v, rule) for v in value]
    if isinstance(value, str):
        return rule.sub(_short_path, value)
    return value


def clean(value):
    """The value as the adapter sends it: no key of the ledger's private set at any depth (j2_runtime.PRIVATE_KEYS), and
    a path of this machine shortened to its file name. The owner's own words are never rewritten: the text of a chat
    message of the owner's (who 'user'), the goal (its statement, rules and done-when) and a Said line lose their private
    keys and nothing else; a page of the owner's site that looks like a path ('/home/about') is not this machine's and is
    left alone wherever it stands. NOT functions_view._clean: its path rule rewrites any /a/b (build/v1/index.html would
    become buildindex.html, and the owner's 5/6/2026 would become 52026)."""
    return _clean(value, _rule())


def _dt(iso):
    try:
        return datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def hhmmss(iso):
    """HH:MM:SS of a recorded time, as it was recorded; '' for anything that is not a time."""
    dt = _dt(iso)
    return dt.strftime("%H:%M:%S") if dt else ""


def epoch(iso):
    """Seconds since the epoch of a recorded time; 0.0 for anything that is not a time."""
    dt = _dt(iso)
    if dt is None:
        return 0.0
    try:
        return dt.timestamp()
    except (OverflowError, OSError, ValueError):
        return 0.0


# ---- journals: read once, then only what was appended ------------------------------------------------------------------
class JournalTail:
    """An append-only journal (board.jsonl, steps.jsonl) read incrementally: the rows are parsed once, and each call
    reads only the complete lines appended since the last. A line torn by a closed app is skipped, as record.lines
    skips it; a journal that shrinks or is replaced (another inode) is read again whole. `bytes_read` totals what was
    read from disk and `last_read` is what the latest call read: tests assert a poll reads nothing."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._reset()
        self.bytes_read = 0
        self.last_read = 0

    def _reset(self):
        self._ino, self._pos, self._rows = None, 0, []

    def rows(self):
        """A snapshot of the parsed rows, oldest first (the rows themselves are shared: read only)."""
        with self._lock:
            self.last_read = 0
            try:
                st = self.path.stat()
            except OSError:
                self._reset()
                return []
            if st.st_ino != self._ino or st.st_size < self._pos:
                self._reset()
                self._ino = st.st_ino
            if st.st_size > self._pos:
                try:
                    with open(self.path, "rb") as f:
                        f.seek(self._pos)
                        data = f.read(st.st_size - self._pos)
                except OSError:
                    return list(self._rows)
                self.last_read = len(data)
                self.bytes_read += len(data)
                cut = data.rfind(b"\n") + 1
                tail = data[cut:]
                if tail.strip():
                    try:                                    # a last line with no newline yet: complete only if it parses
                        json.loads(tail.decode("utf-8"))
                        cut = len(data)
                    except ValueError:
                        pass
                for raw in data[:cut].split(b"\n"):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        self._rows.append(json.loads(raw.decode("utf-8")))
                    except ValueError:                      # a torn line is skipped
                        pass
                self._pos += cut
            return list(self._rows)


class LedgerTail:
    """The department's J2 ledger (all cycles), read through j2_runtime.events_after from the last seq. The count is
    asked first (an index read, no journal), so a ledger that did not grow costs nothing; a ledger that got shorter is
    read again whole."""

    def __init__(self, ref):
        self.ref = ref
        self._lock = threading.Lock()
        self.rows, self.ts, self.cursor = [], [], 0

    def read(self):
        with self._lock:
            count = J.event_count(self.ref)
            if count < len(self.rows):
                self.rows, self.ts, self.cursor = [], [], 0
            if count > len(self.rows):
                for row in J.events_after(self.ref, self.cursor):
                    if isinstance(row, dict):
                        self.rows.append(row)
                        self.ts.append(epoch(row.get("occurred_at")))
                if self.rows:
                    self.cursor = int(self.rows[-1].get("seq") or len(self.rows))
            return self.rows, self.ts


_GUARD = threading.Lock()
_CTX, _LOCKS, _TAILS, _LEDGERS, _DIRTY = {}, {}, {}, {}, set()


def _key(ref):
    return (str(W.home()), str(ref))


def _lock_of(key):
    with _GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.RLock()
        return _LOCKS[key]


def _tail(path):
    with _GUARD:
        return _TAILS.setdefault(str(path), JournalTail(path))


def _ledger(key, ref):
    with _GUARD:
        if key not in _LEDGERS:
            _LEDGERS[key] = LedgerTail(ref)
        return _LEDGERS[key]


def reset_caches():
    """Forget every cache of the adapter (contexts, chat registries, journal tails, locks): for tests."""
    with _GUARD:
        for c in (_CTX, _TAILS, _LEDGERS):
            c.clear()
        _DIRTY.clear()
    for name, fn in (("j2ui_chat", "reset"), ("j2ui_say", "forget")):
        try:
            getattr(__import__(name), fn)()
        except ImportError:
            pass


def _now():
    return time.time()


# ---- the one read ---------------------------------------------------------------------------------------------------
SIGNED = ("dept.json", "runs.json", "asks.json", "board.jsonl", "steps.jsonl", "j2-state.json", "j2-events.jsonl",
          "exchanges.json", "coordination.json", "questions.json")


def _stat(p):
    try:
        st = Path(p).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def signature(ref, root_ref=None):
    """What a read of the department depends on: the (mtime_ns, size) of its record files, of Root's board and record,
    of every artifact's versions, and the ten-second tick. Stat calls only."""
    base = W.ddir(ref)
    parts = [_stat(base / n) for n in SIGNED]
    if root_ref:
        rbase = W.ddir(root_ref)
        parts += [_stat(rbase / "board.jsonl"), _stat(rbase / "dept.json")]
    try:
        parts += [(p.parent.name, _stat(p)) for p in sorted((base / "artifacts").glob("*/versions.json"))]
    except OSError:
        pass
    parts.append(int(_now() / TICK_S))
    return tuple(parts)


class Ctx:
    """One read of the department (the contract is in the UI port's package spec): everything the J2 view needs, read
    once. Never mutate a record through it; every attribute is always present, empty when its read failed (the reason
    is in `reasons`). `memo` is this read's scratch space: build_state and the other packages' builders keep what they build
    there, so one rebuild is shared by api/state, api/map and api/artifacts of a poll and the next poll builds nothing."""

    def __init__(self, ref):
        self.ref, self.kind = ref, "website"
        self.d, self.root_ref, self.doc, self.stopped = {}, None, False, False
        self.fv, self.cur, self.state = None, {}, "not_started"
        self.runs, self.asks, self.posts, self.root_posts, self.steps, self.events = [], [], [], [], [], []
        self.engines, self.planned, self.arts = [], False, []
        self.chat, self.msg_of, self.ask_msg, self.ask_opts, self.paused_ask = [], {}, {}, {}, None
        self.reasons, self.memo = [], {}
        self.sig, self.built_at = None, 0.0
        self._wid, self._ev_t = {}, []

    # who said it, in the page's words: user, a function's lower-case name, or W-k
    def wid(self, name):
        return self._wid.get(name)

    def who(self, src):
        if src == R.OWNER:
            return "user"
        if str(src).title() in FUNCS:
            return str(src).lower()
        return self.wid(src)

    def fn_id(self, name):
        return "fn:" + str(name).lower() if str(name).title() in FUNCS else None

    def dest(self, name):
        return self.who(name)

    def step_at(self, iso):
        """The step of the latest ledger event not after `iso`, or None."""
        i = bisect.bisect_right(self._ev_t, epoch(iso)) - 1
        if i < 0:
            return None
        try:
            return int(self.events[i].get("step"))
        except (TypeError, ValueError):
            return None


def _numbered(planned, mv_engines):
    """W-k for the engines of the registered line, in line order, then the engines the plan left out; none before a plan."""
    if not planned:
        return {}
    names = [e["name"] for e in mv_engines]
    inside = [e["name"] for e in mv_engines if e.get("in_line")]
    return {n: "W-%d" % (i + 1) for i, n in enumerate(inside + [n for n in names if n not in inside])}


def _engines(c, mv_engines):
    c._wid = _numbered(c.planned, mv_engines)
    out = []
    for e in mv_engines:
        name = e["name"]
        wid = c._wid.get(name)
        try:
            view = owner_words.steps(R.steps_view(c.ref, name))
        except Exception as exc:  # noqa: BLE001 -- a card the record cannot read leaves the engine without its steps
            view = None
            c.reasons.append("steps of %s: %s" % (name, type(exc).__name__))
        out.append({"k": int(wid[2:]) if wid else None, "wid": wid, "name": name, "reads": e.get("reads"), "writes": e.get("writes"),
                    "runs_as": e.get("runs_as"), "in_line": bool(e.get("in_line")), "state": e.get("state"),
                    "env": e.get("envelope") or {}, "window_min": e.get("window_min"), "last": e.get("last"),
                    "timetable": e.get("timetable"), "steps_view": view,
                    "runs": [r for r in c.runs if r.get("engine") == name]})
    return out


def _engines_by_hand(c):
    """What website_dept.map_view makes of the engines ({'engines', 'planned'}), made from the same public readers, for when
    map_view itself raises: its status() reads ask['engine'] of every pending ask, and Identity's open question has no such
    key, so in the page's most common first state the Map's reader fails and the engines would be empty, unnumbered and
    unplanned. The rows are map_view's own: engine_view, the last run, 'Waits' for a pending ask, in_line, 'Left out', the slot."""
    ref, d = c.ref, c.d
    table = R.coordination(ref) or {}
    line = set(table.get("line") or [])
    left = {r.get("engine") for r in table.get("left_out") or [] if isinstance(r, dict)}
    slots = {r.get("engine"): r for r in table.get("timetable") or [] if isinstance(r, dict)}
    waiting = {a.get("engine") for a in c.asks if a.get("status") == "pending"}
    engines = []
    for name in (e[0] for e in W.engines_of(d)):
        e = W.engine_view(ref, name)
        if not e:
            continue
        e.pop("runs", None)
        last = next((r for r in reversed(c.runs) if r.get("engine") == name), None)
        e["last"] = last and {"status": last.get("status"), "at": last.get("started"), "what": last.get("what"), "words": last.get("words")}
        if name in waiting:
            e["state"] = "Waits"
        e["in_line"] = name in line
        if name in left and e["state"] not in ("Running", "Missing"):
            e["state"] = "Left out"
        e["timetable"] = slots.get(name)
        engines.append(owner_words.engine(e))
    return {"engines": engines, "planned": not F.no_plan(ref, d, table)}


def _asked(c):
    """The ask Identity's line is made of, picked as functions_view picks it: the cycle's open question, else a finding, else
    the oldest pending ask."""
    pending = [a for a in c.asks if isinstance(a, dict) and a.get("status") == "pending"]
    open_id = c.cur.get("open_ask") if isinstance(c.cur, dict) else None
    question = next((a for a in pending if open_id and a.get("id") == open_id), None)
    finding = next((a for a in pending if a.get("kind") == "finding"), None)
    return question or finding or (pending[0] if pending else None)


def _owner_lines(c):
    """The line Identity waits on the owner with, in the owner's words. functions_view scrubs every string of its read with a
    path rule of its own (to it any /a/b is a path), so the ask it quotes comes out with the owner's routes cut to their last
    name: 'Never link /private/area from the menu' says 'Never link area from the menu' on the Identity lane and on the Map,
    and the owner stamps a rule that reads differently from the one recorded (finding N1). The line is made again here from
    the ask itself, as the pause and the chat say it (said): the lead the machine wrote passes this module's path rule, the
    owner's own words after it are never rewritten, and it is cut to the same line (functions_view._short). Only a line
    functions_view made from an ask is made again: a plan dropped, or an ask with no text, keeps the words it has."""
    ask = _asked(c)
    if c.state == "blocked" or not ask:
        return
    text = said(str(ask.get("text") or ""), ask.get("words"))
    if not str(text).strip():
        return
    for node in (c.fv or {}).get("functions") or []:
        if node.get("fn") == "identity" and node.get("state") == "waiting_on_you":
            node["line"] = keep_said(text, F._short(text))


def _build(ref, key):
    c = Ctx(ref)

    def read(what, fn, default):
        try:
            got = fn()
            return default if got is None else got
        except Exception as exc:  # noqa: BLE001 -- a failed read leaves its attribute empty and says why; the ctx is still a ctx
            c.reasons.append("%s: %s" % (what, type(exc).__name__))
            return default

    base = None
    try:
        base = W.ddir(ref)
    except ValueError:
        c.reasons.append("department: not a ref")
    c.d = read("department", lambda: W.dept(ref), {})
    c.stopped = bool(c.d.get("stopped"))
    root = c.d.get("root")
    c.root_ref = root if root and read("root", lambda: W.dept(root), None) else None
    c.fv = read("functions", lambda: F.functions(ref), None)
    c.cur = read("cycle", lambda: J._state(ref), {})
    c.runs = read("runs", lambda: W.runs(ref), [])
    c.asks = read("asks", lambda: W.asks(ref), [])
    if base is not None:
        c.posts = read("board", lambda: _tail(base / "board.jsonl").rows(), [])
        c.steps = read("steps", lambda: _tail(base / "steps.jsonl").rows(), [])
        if c.root_ref:
            c.root_posts = read("root board", lambda: _tail(W.ddir(c.root_ref) / "board.jsonl").rows(), [])
    rows, ts = read("ledger", lambda: _ledger(key, ref).read(), ([], []))
    cid = c.cur.get("cycle_id")
    keep = [i for i, e in enumerate(rows) if cid and e.get("cycle_id") == cid]
    c.events, c._ev_t = [rows[i] for i in keep], []
    peak = 0.0
    for i in keep:                                  # a clock that stepped back must not break the search by time
        peak = max(peak, ts[i])
        c._ev_t.append(peak)
    state = str(((c.fv or {}).get("cycle") or {}).get("state") or c.cur.get("state") or "not_started")
    c.state = "not_started" if state == "not_ready" else state
    try:
        _owner_lines(c)
    except Exception as exc:  # noqa: BLE001 -- the lanes and the Map keep the line functions_view made
        c.reasons.append("owner line: %s" % type(exc).__name__)
    try:
        mv = owner_words.map_view(W.map_view(ref))
    except Exception as exc:  # noqa: BLE001 -- map_view fails on a pending ask with no engine; the engines are made again by hand
        mv = None
        try:
            mv = _engines_by_hand(c)
        except Exception:  # noqa: BLE001
            c.reasons.append("map: %s" % type(exc).__name__)
    c.planned = bool((mv or {}).get("planned"))
    c.engines = _engines(c, (mv or {}).get("engines") or [])
    for name in read("artifacts", lambda: W.artifacts_of(c.d), ()):
        vs = read("versions of %s" % name, lambda: W.versions(ref, name), [])
        c.arts.append({"name": name, "slug": W.slug(name), "versions": vs, "latest": vs[-1] if vs else None})
    try:                                            # the chat, then the one ask the state shows (j2ui_chat, j2ui_state)
        import j2ui_chat
        c.chat, c.msg_of, c.ask_msg, c.ask_opts = j2ui_chat.build(c)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        c.reasons.append("chat: %s" % type(exc).__name__)
    try:
        import j2ui_state
        c.paused_ask = j2ui_state.pick_paused(c)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        c.reasons.append("paused: %s" % type(exc).__name__)
    return c


def get_ctx(ref):
    """One read of the department, shared by every endpoint of a poll. It rebuilds when a file of the record changed, but
    never more often than MIN_REBUILD_S per ref (touch(ref) lifts that wait), and never raises."""
    ref = str(ref)
    key = _key(ref)
    with _lock_of(key):
        prev = _CTX.get(key)
        try:
            sig = signature(ref, prev.root_ref if prev else None)
        except Exception:  # noqa: BLE001 -- a ref that has no folder reads as a department with nothing in it
            sig = None
        if prev is not None and key not in _DIRTY:
            if sig is not None and prev.sig == sig:
                return prev
            if _now() - prev.built_at < MIN_REBUILD_S:
                return prev
        _DIRTY.discard(key)
        try:
            with layers.reading():                  # the one read of the department tells no pin in the record: the tick does (rule 4(g))
                c = _build(ref, key)
        except Exception as exc:  # noqa: BLE001
            c = Ctx(ref)
            c.reasons.append("build: %s" % type(exc).__name__)
        c.sig, c.built_at = sig, _now()
        _CTX[key] = c
        return c


def touch(ref):
    """The next get_ctx(ref) rebuilds at once: called after every write of this adapter, so the owner's own words show."""
    with _GUARD:
        _DIRTY.add(_key(ref))
