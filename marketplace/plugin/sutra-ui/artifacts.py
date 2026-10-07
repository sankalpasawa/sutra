"""artifacts.py -- artifact templates: the Library's shelf for what a department files, and the apps it uses.

Founder, 2026-09-28: "I want artifacts to be operable artifacts... which has various checks and balances within those
artifacts and templates"; "operational artifacts also mean that they can do some actions right on their own";
"artifacts can be apps as well, which can be reused".

A template (artifact-templates/<slug>.json) says, once, what a thing holds (files), its checks, who writes it, when a
version counts (at filing, or after a stamp), whether it may be put back, and its operations: the engines that run on
a new version of it. Nothing acts but an engine, so an artifact's own actions are engines its template names,
started by the artifact's version like every other engine. A department grows instances: versions, in its own folder
(versions.py). An app (kind app) is a template too: what it reads and the screen it opens; no versions of its own.

The checks here take files, nothing else: a template's check runs when a version is filed (website_dept.add_version),
beside the engine's, and a version that fails is filed and never read as passed.
"""
import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "artifact-templates"
KINDS = ("text", "plan", "pages", "build", "site", "record", "app")
_CACHE = {}


def _load(p):
    try:
        t = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and t.get("id") and t.get("name") and t.get("kind") in KINDS else None


def templates():
    """Every template, by name, Library order."""
    if "t" not in _CACHE:
        out = {}
        for p in sorted(ROOT.glob("*.json")):
            t = _load(p)
            if t:
                out[t["name"]] = t
        _CACHE["t"] = out
    return _CACHE["t"]


def get(name):
    """One template by the artifact's name (Brief, Site plan, ...), or None."""
    return templates().get(name)


def default_template():
    """The Default: text checked as text, for an artifact a department names that the Library has no template of its
    own for (TPL-1, founder 2026-09-29: "there is a default one for artifacts also"). Never for a department's internal
    records (a table, a ladder), which are no artifact."""
    return templates().get("Default")


def apps():
    return [t for t in templates().values() if t["kind"] == "app"]


# ---- checks: each takes the files of one version -------------------------------------------------------------------
def _matches(files, patterns):
    return [f for f in files if any(fnmatch.fnmatch(f, p) for p in patterns)]


def c_is_text(files):
    body = "".join(str(v) for v in files.values())
    return _ok(bool(body.strip()) and len(body.strip()) >= 3, "it holds text", "it holds no text")


def c_plan_has_pages(files):
    try:
        plan = json.loads(files.get("site-plan.json", "{}"))
        pages = plan.get("pages") or []
        ok = bool(pages) and all(isinstance(p, dict) and p.get("slug") for p in pages)
    except Exception:  # noqa: BLE001
        ok = False
    return _ok(ok, "every page has a slug", "no page, or a page without a slug")


def c_pages_have_html(files):
    htmls = _matches(files, ["*.html"])
    return _ok(bool(htmls) and all(str(files[f]).strip() for f in htmls), "every page has a body", "no page, or an empty one")


def c_has_index_html(files):
    return _ok("index.html" in files and bool(str(files["index.html"]).strip()), "the home page is there", "no home page")


def c_names_a_ref(files):
    text = files.get("department.md", "")
    return _ok("ref: dref-" in text and "goal:" in text, "it names the department and its goal", "it names no department")


def _ok(ok, yes, no):
    return {"ok": bool(ok), "notes": [yes if ok else no]}


CHECKS = {"is_text": c_is_text, "plan_has_pages": c_plan_has_pages, "pages_have_html": c_pages_have_html,
          "has_index_html": c_has_index_html, "names_a_ref": c_names_a_ref}


def check(name, files, default=False):
    """The artifact's own verdict on one version's files; with `default`, the Default's when the Library has no template
    of its own for the name (an artifact the department names); None when there is no template to check by."""
    t = get(name) or (default_template() if default else None)
    if not t or not t.get("checks"):
        return None
    notes, ok = [], True
    for c in t["checks"]:
        fn = CHECKS.get(c)
        if fn is None:
            ok, notes = False, notes + ["no check named %s ships with the app" % c]
            continue
        v = fn(files or {})
        ok = ok and v["ok"]
        notes += v["notes"]
    return {"ok": ok, "notes": notes}


def faults(defs):
    """What the definitions get wrong against the Library: an artifact with no template, a check that does not exist,
    an engine that runs on a version its artifact's template does not name as an operation."""
    out = []
    names = set(templates())
    for t in templates().values():
        for c in t.get("checks") or []:
            if c not in CHECKS:
                out.append("artifact %s: no check named %s ships with the app" % (t["name"], c))
    default = "Default" in names                          # with a Default on the shelf an unnamed artifact is text, not a fault
    for kind, k in (defs.get("kinds") or {}).items():
        for a in k.get("artifacts") or []:
            if a not in names and not default:
                out.append("kinds, %s: the Library has no artifact template named %s" % (kind, a))
    for name, e in (defs.get("engines") or {}).items():
        for key in ("reads", "writes"):
            a = e.get(key)
            if a and a not in names and not default:
                out.append("%s: %s %s, which the Library has no template for" % (name, key, a))
        for trig in (e.get("start") or {}).get("on") or []:
            if trig.get("kind") == "version" and trig.get("of") in names:
                # an engine born from an idea on the owner's stamp (made_by) runs on the Brief by that stamp; the
                # Library's operations list is the Library's word for its own engines
                if name not in (get(trig["of"]).get("operations") or []) and not e.get("made_by"):
                    out.append("%s: runs on a new %s, but that template does not name it as an operation" % (name, trig["of"]))
    return out


def view(name):
    """What a screen shows of a template: the artifact's own, or the Default an unnamed artifact is filed under."""
    t = get(name) or default_template()
    if not t:
        return None
    return {"id": t["id"], "name": t["name"], "kind": t["kind"], "use_case": t.get("use_case") or "", "files": t.get("files") or [],
            "checks": t.get("checks") or [], "written_by": t.get("written_by") or [], "counts_after": t.get("counts_after") or "filing",
            "put_back": bool(t.get("put_back")), "operations": t.get("operations") or []}
