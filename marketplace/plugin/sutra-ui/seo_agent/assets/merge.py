"""assets/merge.py — builder 4: stack the three pools into one sheet, dedup across methods, rank.

Port of `02-asset-engine/4-merge`. Two steps in the original and two here: STACK, then DEDUP.
Ranking is folded into the dedup step's write, exactly as the original does it (its step 2 sorts
`kept` before writing the CSV), so the sheet is never handed on unordered.

The dedup is entity resolution, not string matching. Embed each idea, let the embedding NOMINATE
near-neighbours, then let the model decide SAME / COMBINE / SEPARATE on the small cluster it
nominated. On SAME the survivor POOLS the other row's methods and proof rather than discarding
them. That pooling is the whole point of the step: an idea all three methods found independently
has to arrive carrying all three kinds of evidence, because "two methods found this" is the single
strongest signal on the sheet. A dedup that kept one row and dropped the rest would throw away the
one fact worth having.

Any of the three pools may be absent. On 2026-09-09 method 1 was blocked on a DataForSEO balance of
minus seven cents and Reddit refused every check method 3 makes, so a merge of one pool is a real
state, not a broken one. The merge runs on whatever exists and writes `_work/merge/methods.json`
recording, per method, whether it ran, ran and found nothing, or never wrote a file at all. Those
are three different facts and the screen has to be able to tell them apart: `field_sources.py`
draws the same line between "empty" and "unknown" for the same reason.

Reads:  assets/competitors.json · assets/trends.json · assets/formats.json
Writes: assets/ideas.json
        assets/_work/merge/stacked.json    every pool row in one list, before the de-duplication
        assets/_work/merge/methods.json    which methods contributed, for the "2 of 3 ran" line
        assets/_work/merge/dedup.json      every cluster the model saw and what it decided
"""
import numpy as np

from .. import llm
from .. import store
from ..brand import _common as bcm
from ..tools import _shared as sh
from ..tools import voyage
from . import _common as cm

OUTPUT = "ideas.json"
WORK = "_work/merge/"

# The three pools, in the order they are stacked, each as (file, id band key, method name).
#
# The method name is taken from the FILE, never from the row. Which pool a row was read out of IS
# the fact of which method found it; a row that labelled itself differently would be a method
# mislabelling its own output. One value, decided in one place. The names are the three builders'
# own METHOD constants, so the sheet says what each builder says.
#
# The band key is `_common.ID_BASE`'s, which is the file stem and NOT the method name. Only used
# when the ids arrive broken; see `_reidentify`.
POOLS = (("competitors.json", "competitors", "competitors"),
         ("trends.json", "trends", "study-trends"),
         ("formats.json", "formats", "model-other-niches"))

# --- dedup knobs, the original's names and numbers (4-merge/scripts/config.py) -------------------
DEDUP_THRESHOLD = 0.78      # cosine that NOMINATES a pair as a possible repeat. Looser than a
#                             within-method threshold on purpose: a backlink idea and a Reddit
#                             idea for the same asset are worded very differently. The model still
#                             decides; this number only chooses what it is asked about.
DEDUP_TOPK = 6              # nearest neighbours considered per idea
DEDUP_MAX_CLUSTER = 10      # a cluster is cut into slices of this size before the model sees it

# Evidence fields pooled on a merge: the survivor takes the other row's value ONLY where its own is
# blank. Filling a blank is not re-deciding; overwriting a decided value would be, and the row that
# owns each of these is the method that measured it.
POOL_BLANKS = ("format", "angle", "brand_fit", "transplant_from", "beatability", "effort",
               "what_it_would_be")

FIT_ORDER = {"CORE": 0, "TRANSPLANT": 1, "ADJACENT": 2}


# ---- step 1: stack -----------------------------------------------------------------------------

def stack(say):
    """The three pool files as one list of well-shaped rows, plus the per-method record.

    Every row is rebuilt on top of `blank_idea`, so a method that left a field out still produces a
    full row and nothing downstream has to guard for a missing key. Each row KEEPS the id its own
    method gave it: `_common.new_id` bands the three methods apart (competitors 1001+, formats
    2001+, trends 3001+) so an id is unique across pools by construction and its band says where it
    came from. Re-numbering here would throw that away.
    """
    rows, methods = [], []
    for filename, band, method in POOLS:
        pool = cm.read(filename) if cm.exists(filename) else None
        if pool is None:
            state, found = "missing", []
        else:
            found = [r for r in (pool if isinstance(pool, list) else pool.get("ideas") or [])
                     if isinstance(r, dict)]
            state = "ran" if found else "empty"
        methods.append({"method": method, "file": filename, "state": state, "ideas": len(found)})
        for src in found:
            row = cm.blank_idea(src.get("id") or "", method)
            for k, v in src.items():
                if k in row and k not in ("id", "method"):
                    row[k] = v
            row["_from"] = src.get("id") or ""      # the pool's own id, kept so a row is traceable
            row["_pool"] = filename
            row["_band"] = band
            rows.append(row)

    reid = _reidentify(rows, say)
    ran = [m for m in methods if m["state"] == "ran"]
    record = {"of": len(POOLS), "ran": len(ran), "methods": methods, "reidentified": reid,
              "line": _methods_line(methods), "at": store.now()}
    cm.save(WORK + "methods.json", record)
    cm.save(WORK + "stacked.json", rows)
    say("Stacked the idea pools", "%s from %s" % (sh.plural(len(rows), "idea"), record["line"]))
    return rows, record


def _reidentify(rows, say):
    """Guarantee the stack's ids are unique, and say so when they were not.

    Everything after this point looks a row up by its id, so two rows sharing one would quietly
    fold two different ideas into one. `_common.new_id(n, method)` bands the methods apart to stop
    exactly that, but the band only applies when the caller passes it, and the caller has to pass
    the band KEY ("competitors", "trends", "formats") rather than its own METHOD name: pass
    "model-other-niches" and you silently get no band at all. On 2026-09-09 the formats builder was
    still calling `new_id(n)` with nothing, so its ids sat outside every band. Rather than trust an
    invariant three separate files have to remember, check it here.

    When they collide, every row is re-banded off its pool so the whole sheet stays uniform and an
    id still says which method found it. It is recorded here and raised for review, because the
    real fix is in the three builders and this is only a way to keep the sheet honest until then.
    """
    ids = [r["id"] for r in rows]
    if len(set(ids)) == len(ids) and all(ids):
        return None
    per_band = {}
    for r in rows:
        per_band[r["_band"]] = per_band.get(r["_band"], 0) + 1
        r["id"] = cm.new_id(per_band[r["_band"]], r["_band"])
    clashes = sorted({i for i in ids if ids.count(i) > 1})
    say("Re-numbered the ideas",
        "%s arrived on more than one row, so the ids were rebuilt from each method's own band"
        % sh.plural(len(clashes), "id"))
    return {"clashes": clashes[:20], "n": len(clashes)}


def _methods_line(methods):
    """The honest one-liner for the screen. A method that never wrote a file did not run; one that
    wrote an empty file ran and found nothing. Those are not the same thing and must not read as
    the same thing."""
    ran = [m["method"] for m in methods if m["state"] == "ran"]
    empty = [m["method"] for m in methods if m["state"] == "empty"]
    missing = [m["method"] for m in methods if m["state"] == "missing"]
    parts = ["%d of %d methods ran" % (len(ran), len(methods))]
    if empty:
        parts.append("%s ran and found nothing" % ", ".join(empty))
    if missing:
        parts.append("%s did not run" % ", ".join(missing))
    return "; ".join(parts)


# ---- step 2: dedup -----------------------------------------------------------------------------

def clusters(rows, say):
    """Groups of rows an embedding thinks might be the same idea. Cross-method pairs only.

    Each method already de-duplicated its own pool, so a within-method pair here is either a repeat
    that method chose to keep or a pair it already judged distinct. Re-litigating it would be a
    second opinion on a decision that is not this step's to make. The original restricts the
    nomination the same way, for the same reason.
    """
    texts = [("%s — %s" % (r.get("title") or "", r.get("angle") or "")).strip(" —") for r in rows]
    V = np.nan_to_num(np.asarray(voyage.embed(texts, "document"), dtype=np.float32))
    n = len(rows)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sets = [set(r.get("method") or []) for r in rows]
    edges = 0
    for i in range(n):
        sims = V @ V[i]
        sims[i] = -1.0
        for j in np.argsort(-sims)[:DEDUP_TOPK]:
            j = int(j)
            if sims[j] < DEDUP_THRESHOLD or (sets[i] & sets[j]):
                continue                                # same method, or not close enough
            a, b = find(i), find(j)
            if a != b:
                parent[a] = b
                edges += 1
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    raw = [g for g in groups.values() if len(g) > 1]
    out = []
    for g in raw:
        for k in range(0, len(g), DEDUP_MAX_CLUSTER):
            out.append(g[k:k + DEDUP_MAX_CLUSTER])
    say("Looked for the same idea found twice",
        "%s nominated %s to read; the rest have no cross-method match"
        % (sh.plural(edges, "close pair"), sh.plural(len(out), "cluster")))
    return out


def adjudicate(members, brand):
    """SAME / COMBINE / SEPARATE for one cluster. A cluster that fails comes back as no groups,
    which leaves every one of its rows separate: the conservative direction, and the one the
    original also takes when a call errors."""
    block = "\n".join(
        "- id=%s · found by %s · %s · [%s] · angle: %s"
        % (m.get("id"), ", ".join(m.get("method") or []) or "unknown",
           (m.get("title") or "")[:90], m.get("format") or "?", (m.get("angle") or "")[:120])
        for m in members)
    try:
        out = llm.json_call(sh.fill(cm.prompt("merge-dedup"), brand=brand, cluster=block))
    except Exception:       # noqa: BLE001 — one unreadable answer must not lose the other clusters
        return []
    groups = out.get("groups") if isinstance(out, dict) else out
    return [g for g in (groups or []) if isinstance(g, dict)]


def pool(survivor, dead):
    """Fold `dead` into `survivor`: pool the methods and the proof, fill the survivor's blanks.

    Methods and proof ACCUMULATE, because they are evidence and two methods finding one idea is
    the strongest signal the sheet carries. Everything else only fills a blank. The scores stay the
    survivor's: `ownability` and `linkability` were each decided once, by the method that ran them,
    and the merge is not entitled to a second opinion.
    """
    seen = list(survivor.get("method") or [])
    for m in dead.get("method") or []:
        if m not in seen:
            seen.append(m)
    survivor["method"] = [m for _f, _b, m in POOLS if m in seen]        # canonical order, not merge order

    urls = {(p.get("url") or "").rstrip("/") for p in survivor.get("proof") or [] if isinstance(p, dict)}
    for p in dead.get("proof") or []:
        if isinstance(p, dict) and (p.get("url") or "").rstrip("/") not in urls:
            survivor.setdefault("proof", []).append(p)
            urls.add((p.get("url") or "").rstrip("/"))

    for field in POOL_BLANKS:
        if not str(survivor.get(field) or "").strip() and str(dead.get(field) or "").strip():
            survivor[field] = dead[field]
    if survivor.get("beatability") is None and dead.get("beatability") is not None:
        survivor["beatability"] = dead["beatability"]

    # If either side says this asset needs a real build, the merged row says so. The original added
    # the flag on 2026-07-22 after its engine turned 1,143 of 2,213 ideas into calculators, and its
    # rule is that such an idea is flagged and never hidden. Losing the flag here is how the write
    # phase ends up trying to write a calculator as prose.
    #
    # This is not the OR-ratchet the judgment rules warn about. That is one verdict on ONE row
    # accumulated across several passes, where OR can only ever climb. This is two rows describing
    # ONE asset being folded together, and the flag is a property of the asset: if the asset needs
    # a build, it needs a build whichever method noticed.
    if dead.get("tool_escalation"):
        survivor["tool_escalation"] = True
    for judged in ("ownability", "linkability"):
        mine, theirs = survivor.get(judged) or {}, dead.get(judged) or {}
        if mine.get("verdict") is None and theirs.get("verdict") is not None:
            survivor[judged] = theirs                    # a blank filled, never a verdict replaced
    return survivor


def dedup(rows, brand, say):
    """Every cluster adjudicated, the SAME groups folded together, the COMBINE groups fused.
    Returns (kept rows, the report of what the model was asked and what it said)."""
    cls = clusters(rows, say)
    by_id = {r["id"]: r for r in rows}
    if not cls:
        # Still write the report. "The file is not there" and "the file says nothing was merged"
        # read the same to a person looking for it, and only one of them is true.
        cm.save(WORK + "dedup.json", {"same": 0, "combined": 0, "kept": len(rows), "clusters": []})
        return rows, []

    judged = bcm.parallel(lambda cl: adjudicate([rows[i] for i in cl], brand), cls,
                          say=say, label="Reading the possible repeats", every=10)
    report, same_ct, combine_ct = [], 0, 0
    for cl, groups, err in judged:
        report.append({"cluster": [rows[i]["id"] for i in cl],
                       "titles": [(rows[i].get("title") or "")[:70] for i in cl],
                       "groups": groups or [], "error": str(err)[:120] if err else ""})
        for g in (groups or []):
            ids = [str(i) for i in (g.get("ids") or []) if str(i) in by_id]
            ids = [i for i in ids if not by_id[i].get("_gone")]
            if len(ids) < 2:
                continue                                  # nothing to merge, or already merged away
            action = (g.get("action") or "").strip().lower()
            if action == "same":
                keep = g.get("keep") if g.get("keep") in ids else ids[0]
                for other in ids:
                    if other != keep:
                        pool(by_id[keep], by_id[other])
                        by_id[other]["_gone"] = True
                        same_ct += 1
            elif action == "combine" and (g.get("new_title") or "").strip():
                keep = ids[0]
                by_id[keep]["title"] = g["new_title"].strip()
                if (g.get("new_angle") or "").strip():
                    by_id[keep]["angle"] = g["new_angle"].strip()
                for other in ids[1:]:
                    pool(by_id[keep], by_id[other])
                    by_id[other]["_gone"] = True
                    combine_ct += 1

    kept = [r for r in rows if not r.get("_gone")]
    multi = sum(1 for r in kept if len(r.get("method") or []) > 1)
    say("Merged the repeats",
        "%d ideas became %d; %s now carries the evidence of more than one method"
        % (len(rows), len(kept), sh.plural(multi, "idea")))
    cm.save(WORK + "dedup.json", {"same": same_ct, "combined": combine_ct,
                                  "kept": len(kept), "clusters": report})
    return kept, report


# ---- ranking -----------------------------------------------------------------------------------

def rank(rows):
    """Best first, and every row carries its position as `rank`.

    The order, in keys:
      1. an idea a method judged this company CANNOT credibly own goes last, whatever else it
         scores. It is not dropped: the row and its reason stay on the sheet where a person can
         argue with them, and dropping is the finding method's call, not the merge's. An idea
         nobody judged is a different thing and is NOT sent to the bottom here: it ranks normally
         and is counted into a review note instead, because `judged: False` means the question was
         never put, not that the answer was no.
      2. brand fit, CORE before TRANSPLANT before ADJACENT. The original's first key.
      3. the Linkability score. This is where Sutra's ranking parts company with the original,
         which summed follow-domains and Reddit post counts to keep a strong trends idea from
         sinking under a weak competitor one. Those two numbers are not the same unit and adding
         them was a workaround. Here all three methods score every idea with the SAME Linkability
         test out of four, which is the whole reason the pools can be ranked against each other, so
         the shared score does that job properly.
      4. how many methods found it. Two methods agreeing is the sheet's strongest signal.
      5. the weight of its proof, then the id, so the order never wobbles between runs.
    """
    def key(r):
        own = (r.get("ownability") or {}).get("verdict")
        link = (r.get("linkability") or {}).get("score") or 0
        domains = sum(int(p.get("domains") or 0) for p in (r.get("proof") or [])
                      if isinstance(p, dict))
        return (own is False,
                FIT_ORDER.get(str(r.get("brand_fit") or "").strip().upper(), 3),
                -int(link), -len(r.get("method") or []), -domains, -len(r.get("proof") or []),
                str(r.get("id") or ""))

    ordered = sorted(rows, key=key)
    for i, r in enumerate(ordered, 1):
        r["rank"] = i
    return ordered


# ---- the builder -------------------------------------------------------------------------------

def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        rows = cm.ideas()
        say("Kept the idea sheet", "%s already merged; ask for a redo to rebuild it"
            % sh.plural(len(rows), "idea"))
        return {"files": [OUTPUT], "needs_review": []}

    rows, methods = stack(say)
    notes = []
    if not rows:
        raise RuntimeError(
            "None of the three methods produced any ideas, so there is nothing to merge. %s"
            % methods["line"])
    if methods["ran"] < methods["of"]:
        # The sheet is real but partial, and it must say so on its own rather than looking finished.
        notes.append("ideas.json: %s, so this sheet is what those methods found, not the whole "
                     "field." % methods["line"])

    if voyage.available():
        kept, _report = dedup(rows, co.get("brand") or "this company", say)
    else:
        # Without embeddings there is no way to nominate a pair, and asking the model to read every
        # pair of a few hundred ideas is not a substitute. An un-deduplicated sheet is still a
        # usable sheet; a sheet that silently pretends to be deduplicated is not.
        kept = rows
        notes.append("ideas.json: there is no Voyage key, so the same idea found by two methods is "
                     "still on the sheet twice. Add a key in Connections and redo the merge.")
        say("Skipped the duplicate check", "no Voyage key, so nothing could be matched by meaning")

    ordered = rank(kept)
    for r in ordered:
        for private in ("_gone", "_from", "_pool", "_band"):
            r.pop(private, None)     # the trace stays in _work/merge/stacked.json
    cm.save_ideas(ordered)

    if methods.get("reidentified"):
        notes.append("ideas.json: %d ids arrived on more than one row, so every idea was "
                     "re-numbered from its method's own band. The real fix is that the three "
                     "builders pass their method to _common.new_id; until they do, an id here "
                     "will not match the one in that method's own working files."
                     % methods["reidentified"]["n"])
    # An unscored idea sits at the bottom of its brand-fit tier, which is close enough to invisible
    # that it has to be said out loud. It is not a low score: the question was never put.
    unscored = [r["id"] for r in ordered if (r.get("linkability") or {}).get("score") is None]
    if unscored:
        notes.append("ideas.json: %s never got a Linkability score, so they sit at the bottom of "
                     "their tier without having been judged. Redo the method that found them."
                     % sh.plural(len(unscored), "idea"))

    multi = sum(1 for r in ordered if len(r.get("method") or []) > 1)
    say("Wrote the idea sheet",
        "%s, ranked best first; %d found by more than one method; %s"
        % (sh.plural(len(ordered), "idea"), multi, methods["line"]))
    return {"files": [OUTPUT], "needs_review": notes, "methods": methods,
            "count": len(ordered), "multi_method": multi}
