"""models_api.py -- the routes of the owner's models (PRD amendment A4, A4.6.5).

An owner defines a model as a spec (layer_models/spec.py); this router reads them and changes them. The owner is the actor on the
Models screen, so a change that only tightens is applied and told afterwards, and one that lets in more waits for the owner's stamp
(POST /pending/{id}); there is no ask for either. Everything here goes through layer_models.store, which keeps the file, the
history and the row on Root's runs. Validation and the compile run in the route's worker (a plain def), never on the loop.

Registered before website_api: a department's ref cannot begin with an underscore, so `_models` shadows no ref."""
import random
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

import layer_schema as S
import owner_words
from interface_http import InterfaceRoute
from layer_models import compile as _compile, graph as _graph, impact, owner_rules, registry, rules, spec as SP, store
from layer_models.faults import sentences
from layer_models.schema import export

router = APIRouter(prefix="/api/native/_models", tags=["models"], route_class=InterfaceRoute)

REQUEST_BYTES = SP.LIMITS["request_bytes"]
SAMPLE_DEPTH = SP.LIMITS["sample_depth"]


# ---- answers ------------------------------------------------------------------------------------------------------------
def _ok(body, status=200):
    return JSONResponse(status_code=status, content=body, headers={"Cache-Control": "no-store"})


def _words(text):
    """A sentence the owner reads: through the owner's words (the bargain's inside words never reach a screen)."""
    try:
        return owner_words.plain(text)
    except Exception:  # noqa: BLE001 -- a sentence that cannot be passed is shown as it is
        return text


def _fail(exc):
    raise HTTPException(status_code=exc.status, detail={"code": exc.code, "faults": [_words(f) for f in exc.faults]})


def _limit(content_length: int = Header(default=None)):
    if content_length is not None and content_length > REQUEST_BYTES:
        raise HTTPException(status_code=413, detail={"code": "TOO_BIG", "faults": ["that is more than 128 KB"]})


def _size(body):
    import json
    if len(json.dumps(body, default=str)) > REQUEST_BYTES:
        raise HTTPException(status_code=413, detail={"code": "TOO_BIG", "faults": ["that is more than 128 KB"]})


def _depth(v):
    """How deep a value nests, counted without recursion."""
    deepest, stack = 0, [(v, 1)]
    while stack:
        x, d = stack.pop()
        deepest = max(deepest, d)
        if deepest > SAMPLE_DEPTH:
            return deepest
        if isinstance(x, dict):
            stack += [(y, d + 1) for y in x.values() if isinstance(y, (dict, list))]
        elif isinstance(x, list):
            stack += [(y, d + 1) for y in x if isinstance(y, (dict, list))]
    return deepest


def _shaped(spec_):
    """A spec as model.spec, or the 422 NOT_IN_SCHEMA answer of the interface."""
    got = SP.check(SP.ModelSpec, spec_)
    if got:
        raise S.SchemaFault("model.spec", got)
    return spec_


def _key(raw):
    """A key in a path: 'x.client', or 'x.client@v1' for one version (a slash cannot ride in a path part)."""
    return raw.replace("@", "/")


# ---- read models ----------------------------------------------------------------------------------------------------------
def _latest_keys(reg):
    best = {}
    for fk, s in reg.specs.items():
        if s["name"] not in best or s["version"] > reg.specs[best[s["name"]]]["version"]:
            best[s["name"]] = fk
    return [best[n] for n in sorted(best)]


def _base_label(reg, s):
    return owner_rules._label_of(s.get("base") or "", reg.specs)


def _pending_for(fk):
    row = next((r for r in store.pending() if r["key"] == "x." + fk), None)
    return {"id": row["id"], "says": row["says"], "at": row["at"]} if row else None


def _root_ref():
    try:
        import website_dept as W
        return next((d.get("ref") for d in W.list_depts() if d.get("kind") == "root"), None)
    except Exception:  # noqa: BLE001 -- no records home: no root
        return None


def _entry(reg, fk):
    s = reg.specs[fk]
    key = "x." + fk
    return {"key": "x." + s["name"], "exact": key, "name": s["name"], "label": s["label"], "version": s["version"], "base": s["base"],
            "base_label": _base_label(reg, s), "state": reg.state.get(key, "on"), "why": reg.why.get(key),
            "abstract": bool(s.get("abstract")),
            "children": ["x." + reg.specs[c]["name"] for c in owner_rules.children_of(reg.specs, fk)], "pending": _pending_for(fk)}


def _buildable(reg):
    out = [{"key": "core:" + n, "label": owner_rules.core_label(n), "says": owner_rules.CORE_SAYS.get(n, "")}
           for n in SP.EXTENSIBLE_CORE]
    out += [{"key": "x." + s["name"], "label": s["label"], "says": s.get("about") or ""}
            for fk in _latest_keys(reg) for s in [reg.specs[fk]] if reg.state.get("x." + fk) == "on"]
    return out


def _built_in():
    by = {}
    for name in sorted(registry.DEF_CLASS):
        by.setdefault(name.split(".")[0], []).append({"key": name, "label": owner_rules.core_label(name)})
    return [{"layer": layer, "models": ms} for layer, ms in sorted(by.items())]


def _bound_words(f):
    t = f.get("type")
    if t in ("text", "long_text"):
        hi = f.get("max_len") or (200 if t == "text" else 20000)
        return "up to %d characters" % hi + (", at least %d" % f["min_len"] if f.get("min_len") else "")
    if t in ("whole", "number"):
        lo, hi = f.get("minimum"), f.get("maximum")
        return "between %s and %s" % (lo, hi) if lo is not None and hi is not None else "" if lo is None and hi is None else "from %s" % lo if hi is None else "up to %s" % hi
    if t == "choice":
        return "one of %s" % ", ".join(f.get("choices") or [])
    if t == "words":
        return "up to %d words" % (f.get("max_items") or 20) + (", each once" if f.get("unique") else "")
    return ""


def _core_word(info):
    from layer_models.types import Bool, Enum, Int, Items, Num, Str
    t = rules.type_tree(info)
    leaf = t[1] if t[0] == "leaf" else None
    if t[0] == "items":
        return "list of words"
    return ("text" if isinstance(leaf, Str) else "number" if isinstance(leaf, Num) else "whole number" if isinstance(leaf, Int)
            else "yes or no" if isinstance(leaf, Bool) else "one of" if isinstance(leaf, Enum) else "value")


def _fields(reg, fk):
    """The fields a model holds: its own, then the ones it inherits from its parent version or its base, locked."""
    s = reg.specs[fk]
    out = [{"name": f["name"], "label": f["label"], "type": SP.VOCABULARY_WORDS[f["type"]], "says": _bound_words(f),
            "required": bool(f.get("required")) and not f.get("retired"), "nullable": bool(f.get("nullable")),
            "retired": bool(f.get("retired")), "aliases": list(f.get("aliases") or []), "from": s["label"], "locked": False}
           for f in s.get("fields") or []]
    have = {f["name"] for f in out}
    up = s.get("parent") if s["version"] > 1 else s.get("base")
    if up and up.startswith("x:"):
        pk = owner_rules.ref_key(up, reg.specs)
        if pk:
            for f in _fields(reg, pk):
                if f["name"] not in have:
                    out.append(dict(f, locked=True))
                    have.add(f["name"])
    base_cls = reg.core.get(s["base"]) if s["base"].startswith("core:") else None
    if base_cls is not None and (s["version"] == 1):
        for name, info in base_cls.model_fields.items():
            if name not in have:
                out.append({"name": name, "label": name.replace("_", " ").capitalize(), "type": _core_word(info), "says": "",
                            "required": info.is_required(), "nullable": False, "retired": False, "aliases": [],
                            "from": owner_rules.core_label(s["base"]), "locked": True})
                have.add(name)
    return out


def _chain(reg, fk):
    out, cur, seen = [], reg.specs[fk], set()
    while cur and cur["name"] + str(cur["version"]) not in seen:
        seen.add(cur["name"] + str(cur["version"]))
        base = cur.get("base") or ""
        out.append(owner_rules._label_of(base, reg.specs))
        nk = owner_rules.ref_key(base, reg.specs)
        cur = reg.specs.get(nk) if nk else None
    return out


def _links(reg, fk):
    s = reg.specs[fk]
    out = [{"name": l["name"], "label": l["label"], "mode": l["mode"], "to": l["to"], "to_label": owner_rules._label_of(l["to"], reg.specs),
            "many": bool(l.get("many")), "required": bool(l.get("required")), "enabled": l.get("enabled") is not False}
           for l in s.get("links") or []]
    inbound = [{"from": "x." + o["name"], "from_label": o["label"], "name": l["name"], "mode": l["mode"]}
               for ok, o in sorted(reg.specs.items()) for l in o.get("links") or []
               if owner_rules.ref_key(l["to"], reg.specs) == fk and ok != fk]
    return {"out": out, "in": inbound}


def _used_by(reg, fk):
    key = "x." + fk
    out = [{"kind": "artifact_template", "name": n, "art": n, "v": None, "dept": None} for n in impact.templates_using(key, reg)]
    try:
        out += [dict(u, kind="filed") for u in impact.scan_filed(key, reg=reg)["used_by"]]
    except Exception:  # noqa: BLE001 -- a read of who uses a model never fails for want of the departments
        pass
    return out


def _page(reg, fk):
    s = reg.specs[fk]
    key = "x." + fk
    e = _entry(reg, fk)
    links = _links(reg, fk)
    tail = [{"rev": r["rev"], "at": r["at"], "op": r["op"], "says": r["says"], "class": r.get("class")} for r in store.history(key, 10)]
    return dict(e, about=s.get("about") or "", discriminator=s.get("discriminator"), chain=_chain(reg, fk),
                versions=[{"version": reg.specs[v]["version"], "key": "x." + v, "state": reg.state.get("x." + v)}
                          for v in sorted(reg.specs, key=lambda k: reg.specs[k]["version"]) if reg.specs[v]["name"] == s["name"]],
                fields=_fields(reg, fk), links=links, used_by=_used_by(reg, fk), rev=store.rev(), history_tail=tail,
                faults=[x for _, x in reg.faults.get(key, [])])


def _need(reg, raw):
    k = reg.resolve(_key(raw))
    if k is None:
        raise HTTPException(status_code=404, detail={"code": "UNKNOWN_MODEL", "faults": ["there is no model %s" % raw]})
    return k[2:]


def _example(cls):
    """A value that fits the class, made by the generator the substitution rule uses; {} when it makes none."""
    try:
        v = rules._gen_model(cls, random.Random(1))
        return {} if v is rules._NONE else v
    except Exception:  # noqa: BLE001 -- an example is a courtesy
        return {}


# ---- reads ----------------------------------------------------------------------------------------------------------------
@router.get("")
def models(all: int = 0):
    reg = registry.current()
    body = {"schema_version": 1, "rev": store.rev(), "root": _root_ref(),
            "yours": [{k: v for k, v in _entry(reg, fk).items() if k != "exact"} for fk in _latest_keys(reg)],
            "buildable": _buildable(reg), "built_in": _built_in() if all else None}
    return _ok(body)


@router.get("/graph")
def graph():
    return _ok(_graph.graph())


@router.get("/links")
def links():
    return _ok({"links": registry.links_report()})


@router.get("/{key}")
def one(key: str):
    reg = registry.current()
    return _ok(_page(reg, _need(reg, key)))


@router.get("/{key}/shape")
def shape(key: str):
    reg = registry.current()
    fk = _need(reg, key)
    cls = reg.classes.get("x." + fk)
    if cls is None:
        raise HTTPException(status_code=409, detail={"code": "NEEDS_A_LOOK", "faults": [reg.why.get("x." + fk) or "it needs a look"]})
    return _ok({"schema": export(cls), "example": _example(cls)})


@router.get("/{key}/history")
def history(key: str):
    reg = registry.current()
    fk = _need(reg, key)
    return _ok({"history": [{k: r.get(k) for k in ("rev", "at", "by", "op", "says", "class")} for r in store.history("x." + fk, 500)]})


# ---- writes ---------------------------------------------------------------------------------------------------------------
def _answer(result, fk=None):
    """The 200 body of a change: the page of the model after it, beside the result."""
    if isinstance(result, store.Pending):
        return _ok(dict(result))
    reg = registry.current()
    k = (result.get("key") or "")[2:] or fk
    return _ok(dict(result, model=_page(reg, k) if k in reg.specs else None))


@router.post("/preview", dependencies=[Depends(_limit)])
def preview(body: Dict[str, Any] = Body(...)):
    _size(body)
    if isinstance(body.get("spec"), dict):
        _shaped(body["spec"])
    out = impact.preview(body)
    out["faults"] = [_words(f) for f in out["faults"]]
    return _ok(out)


@router.post("/validate", dependencies=[Depends(_limit)])
def validate(body: Dict[str, Any] = Body(...)):
    """A sample against a model of the owner's, or against a spec that is compiled for this call and kept nowhere."""
    _size(body)
    sample = body.get("sample")
    if _depth(sample) > SAMPLE_DEPTH:
        raise HTTPException(status_code=400, detail={"code": "TOO_DEEP", "faults": ["the sample nests more than %d deep" % SAMPLE_DEPTH]})
    reg = registry.current()
    if isinstance(body.get("spec"), dict):
        spec_ = _shaped(body["spec"])
        specs = dict(reg.specs)
        fk = SP.key_of(spec_)
        specs[fk] = spec_
        throwaway = _compile.compile_all(specs, registry.core_map(), reuse=reg)
        found = throwaway.faults.get("x." + fk)
        if found:
            return _ok({"ok": False, "faults": [_words(s) for _, s in found]})
        reg, key = throwaway, "x." + fk
    else:
        fk = _need(reg, str(body.get("key") or ""))
        key = "x." + fk
    try:
        ad = reg.adapter(key)
    except KeyError:
        return _ok({"ok": False, "faults": [_words(reg.why.get(key) or "it needs a look")]})
    got = sentences(ad, sample)
    return _ok({"ok": not got, "faults": [_words(g) for g in got]})


@router.post("", dependencies=[Depends(_limit)])
def create(body: Dict[str, Any] = Body(...)):
    _size(body)
    spec_ = _shaped(body.get("spec"))
    try:
        result = store.save(spec_, body.get("rev"), create=True)
    except store.ModelFault as e:
        _fail(e)
    return _answer(result)


@router.post("/pending/{pid}", dependencies=[Depends(_limit)])
def stamp(pid: str, body: Dict[str, Any] = Body(...)):
    try:
        result = store.apply_pending(pid, bool(body.get("approve")))
    except store.ModelFault as e:
        _fail(e)
    return _answer(result) if not result.get("dropped") else _ok(result)


@router.post("/{key}", dependencies=[Depends(_limit)])
def edit(key: str, body: Dict[str, Any] = Body(...)):
    _size(body)
    spec_ = _shaped(body.get("spec"))
    named = _key(key)
    if owner_rules.core_locked(named):
        _fail(store.ModelFault("CORE_LOCKED", [s for _, s in owner_rules.core_locked(named)]))
    if spec_["name"] != named.split("/")[0].replace("x.", "", 1):
        _fail(store.ModelFault("UNKNOWN_MODEL", ["that spec is for another model"], 404))
    try:
        result = store.save(spec_, body.get("rev"))
    except store.ModelFault as e:
        _fail(e)
    return _answer(result)


@router.post("/{key}/enabled", dependencies=[Depends(_limit)])
def enabled(key: str, body: Dict[str, Any] = Body(...)):
    try:
        result = store.set_enabled(_key(key), bool(body.get("enabled")), body.get("rev"))
    except store.ModelFault as e:
        _fail(e)
    return _answer(result)


@router.post("/{key}/undo", dependencies=[Depends(_limit)])
def undo(key: str, body: Dict[str, Any] = Body(default={})):
    try:
        result = store.undo(_key(key), body.get("rev"))
    except store.ModelFault as e:
        _fail(e)
    return _answer(result)


@router.post("/{key}/revert", dependencies=[Depends(_limit)])
def revert(key: str, body: Dict[str, Any] = Body(...)):
    try:
        result = store.revert(_key(key), int(body.get("to_rev") or 0), body.get("rev"))
    except store.ModelFault as e:
        _fail(e)
    return _answer(result)
