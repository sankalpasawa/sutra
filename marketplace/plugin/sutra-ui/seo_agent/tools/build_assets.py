"""build_assets.py — work out what is worth writing about, from evidence rather than a hunch.

The port of the workflow's Layer 02 (asset engine). Six builders run in order, each a module in
assets/, each writing its file before the next one reads it:

     0 scope         assets/scope.md          what this company can and cannot own
     1 competitors   assets/competitors.json  who earns links, and the FORMAT that earned them
     2 formats       assets/formats.json      formats proven elsewhere, transplanted
     3 trends        assets/trends.json       what the audience argues about, as tensions
     4 merge         assets/ideas.json        stack, dedup by meaning, pool the proof, rank
     5 reuse         (fills each row in place) do we already have this

The three finders never see each other's output. That is deliberate and it is the original's own
design: one method finds one kind of idea, and letting them talk before the merge would collapse
three independent signals into one. They meet exactly once, at step 4, where an idea that all three
found arrives carrying three kinds of evidence instead of one.

TWO HUMAN GATES live inside builders 1 and 3: the competitor shortlist and the subreddit list. A
builder that needs one returns {"gate": {...}} and writes nothing further. This driver hands that
straight up to loop.py, which asks it through the same checkpoint every approval already uses. The
driver never asks anything itself and never invents an answer.

Resumable in the ordinary way: a builder whose files exist is skipped unless `redo` is set or
`only` names it. One builder failing is said and the rest still run, because two methods out of
three is a real sheet and losing them to a third's bad day is not a trade worth making.

Reads:  knowledge/brand/** (the pack), knowledge/site_index.json, knowledge/competitors.json
Writes: knowledge/assets/{scope.md, competitors.json, formats.json, trends.json, ideas.json}
"""
from .. import store
import importlib

from ..assets import _common as cm
from . import _shared as sh

# (key, module name, the files that mark it done), in the original's run order. Imported one at a
# time, on the way past, the way loop.py resolves a tool: a builder that is missing or that will
# not import is reported as that one builder failing, and the other five still run.
BUILDERS = [
    ("scope", "scope", ["scope.md"]),
    ("competitors", "competitors", ["competitors.json"]),
    ("formats", "formats", ["formats.json"]),
    ("trends", "trends", ["trends.json"]),
    ("merge", "merge", ["ideas.json"]),
    ("reuse", "reuse", []),          # fills ideas.json in place, so it has no file of its own
]
KEYS = [k for k, _m, _f in BUILDERS]


def _module(name):
    return importlib.import_module("..assets." + name, __package__)
FINDERS = ("competitors", "formats", "trends")


def _only(only):
    if not only:
        return set()
    if isinstance(only, str):
        only = only.replace(";", ",").split(",")
    wanted = {str(o).strip().lower().replace("_", "-") for o in only if str(o).strip()}
    unknown = sorted(wanted - set(KEYS))
    if unknown:
        raise ValueError("Unknown builder name(s): %s. Known: %s" % (", ".join(unknown), ", ".join(KEYS)))
    return wanted


def status():
    """What the model is told about the sheet, and what the screen shows. Cheap: no model calls."""
    rows = cm.ideas()
    nxt = cm.next_open(rows)
    return {"built": bool(rows), "counts": cm.counts(rows), "total": len(rows),
            "methods_run": sorted({m for r in rows for m in (r.get("method") or [])}),
            "next": {"id": nxt["id"], "title": nxt.get("title", "")} if nxt else None}


def run(ctx, redo=False, only=None):
    say = sh.reporter(ctx, "build_assets")
    index = store.knowledge("site_index.json")
    if not index or not (index.get("pages") if isinstance(index, dict) else index):
        raise RuntimeError("There is no site index yet. Run index_site first.")
    co = sh.company()

    # Say it once, at the top. Every one of the three finders judges its ideas against the brand
    # scope, and the scope is distilled from the brand pack. With no pack there is nothing to judge
    # against, and all three would approve everything. Same shape of refusal as learn_brand's when
    # there is no measured traffic: name the problem and both ways out, never guess.
    from ..brand import _common as bcm
    if not bcm.exists("features.md"):
        return {"summary": "The asset engine did not run: there is no brand pack yet.",
                "error": ("Every idea is judged against what this company can credibly own, and "
                          "that is worked out from the brand pack. There is none on file. Run the "
                          "brand pack first, then ask me for asset ideas again.")}

    wanted = _only(only)
    redo = bool(redo)
    built, skipped, failed, notes, files = [], [], [], [], []

    for key, modname, outputs in BUILDERS:
        if wanted and key not in wanted:
            continue
        force = redo or key in wanted
        if not force and outputs and all(cm.exists(f) for f in outputs):
            say("Already built: %s" % key, ", ".join(outputs))
            files += outputs
            skipped.append(key)
            continue
        say("Building %s" % key, "")
        try:
            out = _module(modname).run(co, say, redo=force) or {}
        except Exception as e:      # noqa: BLE001 — one method failing must not lose the others
            say("%s did not finish" % key, str(e)[:200])
            failed.append(key)
            notes.append("%s: did not finish (%s)" % (key, str(e)[:160]))
            continue
        # A builder that needs a human stops the WHOLE engine here and hands the question up. It
        # does not skip on: the two later finders are independent, but merge is not, and a sheet
        # merged before a gate was answered would have to be thrown away and rebuilt.
        if out.get("gate"):
            g = dict(out["gate"])
            g["builder"] = key
            say("Waiting on you", g.get("why", "")[:160])
            return {"gate": g, "summary": "The asset engine is waiting on your answer.",
                    "done_so_far": built}
        files += out.get("files") or outputs
        notes += out.get("needs_review") or []
        built.append(key)

    rows = cm.ideas()
    ran = sorted({m for r in rows for m in (r.get("method") or [])})
    blocked = [f for f in FINDERS if f not in ran and f not in built]
    parts = []
    if built:
        parts.append("built %s" % ", ".join(built))
    if skipped:
        parts.append("kept %d already built" % len(skipped))
    if failed:
        parts.append("%s did not finish" % ", ".join(failed))
    summary = "Asset ideas: %s. %d ideas on the sheet." % ("; ".join(parts) or "nothing to do", len(rows))
    # An engine that ran two methods of three must SAY it ran two of three. A partial sheet
    # presented as a whole one is the same failure as a 400-page catalogue passing its gates.
    if blocked:
        summary += " %d of 3 methods contributed; %s did not." % (3 - len(blocked), ", ".join(blocked))
    if notes:
        summary += " %d things need your review." % len(notes)
    return {"summary": summary, "files": sorted(set(files)), "needs_review": notes,
            "ideas": len(rows), "methods_run": ran, "methods_blocked": blocked,
            "status": status()}
