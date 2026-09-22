"""function_templates.py -- the function templates and a department's picks.

Every department has five functions (Identity, Adaptation, Priority, Coordination,
Audit). A template brings one to life; the repository is the folder
`function-templates/` beside this file (its README and test_function_templates.py
are the law: a Default per function, use-case templates derived narrowing-only).

A department runs a function's Default until the owner stamps an `org.template`
ask naming another template for that function (DECISIONS.md DS-9). The pick is
stored in ONE file under the registry home, `function_templates.json`:

    {"<department ref>": {"<function>": {"template": "<function>/<slug>", "at": "<iso>"}}}

WRITERS: exactly one, `write_pick`, called only by org2_apply when an approved
`org.template` ask is applied. Everything else here reads. A missing or broken
file is read as "nothing picked", never as an error.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


def _home():
    """The registry home, read from the engine module loaded NOW: tests
    re-import the engine on a temp SUTRA_NATIVE_HOME, and a module-level alias
    here would keep pointing at the first one."""
    import placement_engine
    return placement_engine.HOME


ROOT = Path(__file__).resolve().parent / "function-templates"
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
LABELS = {"identity": "Identity", "adaptation": "Adaptation", "priority": "Priority",
          "coordination": "Coordination", "audit": "Audit"}
PICKS_FILE = "function_templates.json"


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            t = json.load(fh)
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and t.get("id") and t.get("function") in FUNCTIONS else None


def templates(function=None):
    """Every template, or one function's, Default first then by name."""
    out = []
    for fn in (FUNCTIONS if function is None else (function,)):
        d = ROOT / fn
        if not d.is_dir():
            continue
        rows = [t for t in (_load(p) for p in sorted(d.glob("*.json"))) if t]
        rows.sort(key=lambda t: (t.get("derives_from") is not None, t.get("name") or ""))
        out += rows
    return out


def get(template_id):
    """One template by id (`<function>/<slug>`), or None. The id is checked
    against the five functions and a plain slug, so it can never walk out of
    the folder."""
    fn, _, slug = str(template_id or "").partition("/")
    if fn not in FUNCTIONS or not slug or not slug.replace("-", "").isalnum():
        return None
    return _load(ROOT / fn / (slug + ".json"))


def default_id(function):
    return function + "/default"


def card(t):
    """What a picker row or a card line needs: id, name, use case."""
    return {"id": t["id"], "name": t.get("name") or t["id"], "use_case": t.get("use_case") or ""}


def picks_path():
    return os.path.join(_home(), PICKS_FILE)


def read_picks():
    try:
        with open(picks_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def picked(ref):
    """{function: template id} for one department; the Default where nothing
    was picked, or where the picked template no longer exists."""
    mine = read_picks().get(ref) or {}
    out = {}
    for fn in FUNCTIONS:
        tid = ((mine.get(fn) or {}).get("template") if isinstance(mine.get(fn), dict) else None) or ""
        out[fn] = tid if get(tid) and tid.startswith(fn + "/") else default_id(fn)
    return out


def write_pick(ref, function, template_id):
    """THE one writer (org2_apply, after the owner's stamp). Atomic: a temp
    file in the same folder, then a rename."""
    if function not in FUNCTIONS:
        raise ValueError("a function is one of: %s" % ", ".join(FUNCTIONS))
    t = get(template_id)
    if not t or t["function"] != function:
        raise ValueError("no %s template %s" % (LABELS[function], template_id))
    data = read_picks()
    before = ((data.get(ref) or {}).get(function) or {}).get("template") or default_id(function)
    if before == t["id"]:
        raise ValueError("%s already runs the %s template" % (LABELS[function], t.get("name") or t["id"]))
    data.setdefault(ref, {})[function] = {
        "template": t["id"],
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    home = _home()
    os.makedirs(home, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".function_templates.", dir=home)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, picks_path())
    return {"before": before, "after": t["id"]}
