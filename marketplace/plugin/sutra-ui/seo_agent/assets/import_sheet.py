"""assets/import_sheet.py — load a sheet of ideas the workflow already produced.

The engine builds its own sheet. This reads one that already exists, from a run of the original
`02-asset-engine` outside Sutra, so a person who has done the work by hand does not have to pay for
it twice. Same job as `foundation/traffic_import.py` does for a DataForSEO pull.

The file is the original's own `clubbed-ideas.csv`: the merged, deduped, reuse-checked sheet that
comes out of `4-merge` and `5-reuse-check`. Its columns are read by NAME, never by position, so a
sheet with the columns in a different order still loads and a sheet missing one says which.

Two fields the original never records, and this will not invent:
  - the linkability score. The merged sheet carries no numeric score, so a row loads unscored
    rather than with a number nobody measured. `judged` is False and the screen shows a dash.
  - the ownability verdict as a sentence. `Brand fit` IS the outcome of that test, so the verdict
    is taken as true (the row survived the filter) and the fit is carried as the reason.

Reads:  a clubbed-ideas.csv. Writes: knowledge/assets/ideas.json
"""
import csv
import io
import os
import re

from . import _common as cm

# The original's `Sources` column, in its own shorthand, to the method names the sheet uses.
SOURCES = {"M1": "competitor-study", "M2": "model-other-niches", "M3": "study-trends"}
BAND_OF = {"competitor-study": "competitors", "model-other-niches": "formats",
           "study-trends": "trends"}

# Every column this reads, and whether a sheet without it is still usable.
REQUIRED = ("Asset",)
OPTIONAL = ("Sources", "Brand fit", "Format", "Distinct angle", "Tool escalation", "What it'd be",
            "Total domains", "# pages", "# comps", "# posts", "Beatability", "Effort",
            "Proof URLs", "Reuse verdict", "Chosen links", "Why")

_LINKS = re.compile(r"https?://[^\s;,]+")


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _methods(v):
    """"M2 + M1" -> both, in the sheet's own order. An unknown token is kept verbatim rather than
    dropped: a sheet from a later version of the workflow may name a method this does not know,
    and losing it silently would understate how many methods found the idea."""
    out = []
    for tok in re.split(r"[+,/]", str(v or "")):
        t = tok.strip().upper()
        if not t:
            continue
        out.append(SOURCES.get(t, tok.strip()))
    return out


def parse(text):
    """(rows, report). Every row that has a title becomes an idea; the rest are counted and said."""
    rdr = csv.DictReader(io.StringIO(text))
    cols = rdr.fieldnames or []
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        raise ValueError("This does not look like a clubbed-ideas sheet: no %s column. It has: %s"
                         % (", ".join(missing), ", ".join(cols[:10])))

    rows, dropped, per_band = [], 0, {}
    for i, r in enumerate(rdr, start=1):
        title = (r.get("Asset") or "").strip()
        if not title:
            dropped += 1
            continue
        methods = _methods(r.get("Sources"))
        band = BAND_OF.get(methods[0], "") if methods else ""
        # Ids stay inside the method's own band, exactly as a built sheet does, so an imported
        # sheet and a built one can never collide if someone later runs the engine on top.
        per_band[band] = per_band.get(band, 0) + 1
        idea = cm.blank_idea(cm.new_id(per_band[band], band) if band else "a%04d" % i,
                             methods or ["imported"])
        idea["title"] = title
        idea["angle"] = (r.get("Distinct angle") or "").strip()
        idea["format"] = (r.get("Format") or "").strip()
        fit = (r.get("Brand fit") or "").strip().upper()
        idea["brand_fit"] = fit if fit in ("CORE", "TRANSPLANT", "ADJACENT") else ""
        # The row survived the original's own ownability filter, which is what Brand fit records.
        idea["ownability"] = {"verdict": True, "judged": True,
                              "why": "Kept by the original run's ownability test, tagged %s."
                                     % (fit or "untagged")}
        # No score exists in the merged sheet. An unscored row is not a zero-scored one.
        idea["linkability"] = {"score": None, "of": cm.LINKABILITY_OF, "verdict": None,
                               "judged": False,
                               "why": "The merged sheet carries no linkability score, so none is "
                                      "shown. Rebuild the ideas to score them."}
        esc = (r.get("Tool escalation") or "").strip()
        idea["tool_escalation"] = bool(esc)
        idea["what_it_would_be"] = (r.get("What it'd be") or "").strip() or esc
        idea["beatability"] = _int(r.get("Beatability"))
        idea["effort"] = (r.get("Effort") or "").strip()

        proof = []
        for u in _LINKS.findall(r.get("Proof URLs") or "")[:6]:
            proof.append({"url": u, "domains": None, "what": ""})
        if proof:
            proof[0]["domains"] = _int(r.get("Total domains"))
            bits = [("%s pages" % _int(r.get("# pages"))) if _int(r.get("# pages")) else "",
                    ("across %s competitors" % _int(r.get("# comps"))) if _int(r.get("# comps")) else "",
                    ("%s posts" % _int(r.get("# posts"))) if _int(r.get("# posts")) else ""]
            proof[0]["what"] = " ".join(b for b in bits if b) or "from the original run"
        idea["proof"] = proof

        verdict = (r.get("Reuse verdict") or "").strip().lower()
        idea["reuse"] = {"verdict": verdict if verdict in cm.REUSE_VERDICTS else "",
                         "links": _LINKS.findall(r.get("Chosen links") or "")[:5],
                         "why": (r.get("Why") or "").strip()}
        idea["rank"] = i                    # the sheet arrives ranked; keep its order
        rows.append(idea)

    seen = {}
    for r in rows:                          # ids must be unique or the chip can address two rows
        if r["id"] in seen:
            r["id"] = "%s-%d" % (r["id"], seen[r["id"]] + 1)
        seen[r["id"]] = seen.get(r["id"], 0) + 1

    methods_seen = sorted({m for r in rows for m in (r.get("method") or [])})
    return rows, {"read": len(rows), "dropped": dropped, "methods": methods_seen,
                  "unscored": sum(1 for r in rows if not r["linkability"]["judged"])}


def apply(path, say=None):
    """Read the file at `path` and make it the sheet. Never merges: an import replaces, because
    two sheets from two different runs would double every idea that both runs found."""
    if not os.path.exists(path):
        raise FileNotFoundError("There is no file at %s" % path)
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        rows, report = parse(f.read())
    if not rows:
        raise ValueError("That sheet has no ideas in it: every row was missing its Asset column.")
    cm.save_ideas(rows)
    # The screen asks the merge for which methods contributed. An imported sheet has no merge, so
    # it writes the same record, saying plainly where the ideas came from.
    cm.save("_work/merge/methods.json", {
        "methods": {m: "ran" for m in report["methods"]},
        "line": "Loaded from a sheet you produced earlier: %s ideas from %s."
                % (format(report["read"], ","),
                   cm.method_list(report["methods"]) or "an unnamed method"),
        "imported_from": os.path.basename(path)})
    if say:
        say("Loaded the idea sheet",
            "%d ideas, %d with no linkability score" % (report["read"], report["unscored"]))
    return report
