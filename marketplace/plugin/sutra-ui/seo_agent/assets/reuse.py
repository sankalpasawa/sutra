"""assets/reuse.py — builder 5: before we build anything, do we already have it?

Port of `02-asset-engine/5-reuse-check`, and mostly a matter of pointing existing Sutra parts at
the idea sheet. That workflow was ported into this app once already, as the own-pages step of the
research flow, so almost nothing here is new code:

    stage 1, the content index   -> tools/_index.py, the two-vector page index. Sutra builds it
                                    once per company and the internal-link pass already reads it.
                                    On the live install it holds 11,703 pages and 33,039 passages,
                                    the part of the 12,318-page catalogue whose text the crawl
                                    actually saved; a page with no body cannot be a reuse
                                    candidate and is not indexed. This builder READS that index and
                                    never builds a second one. When it is not there the builder
                                    says so and stops: building it is `build_page_index`'s job and
                                    costs a Voyage pass over the whole site.
    stage 2, retrieval           -> tools/voyage.py + _index.score, with research/_common's own
                                    knobs (ALPHA, N_RETRIEVE) and its query rule (`query_text`).
    stage 3, the judgment        -> research/ownpage.reuse_judge and prompts/research/reuse-judge.md,
                                    which IS this workflow's judge prompt, ported verbatim.

Three things in stage 3 are load-bearing and easy to lose, so they are named here even though the
code that enforces them lives in `ownpage.reuse_judge`:

  * the judge never sees a match score. It reads the pages and decides from what it read. The
    scores are real and useful, so they are kept, but they stop at `_work/reuse/candidates.json`
    where a person can look at them and a model cannot be anchored by them.
  * one verdict per idea, taken top-down, first match wins. `_common.REUSE_VERDICTS` holds the four
    in the original's order and that order IS the decision tree. It is never re-sorted.
  * a chosen link must be one of the links retrieval found. The judge picks from what it was shown
    and may not invent a URL.

Reads:  assets/ideas.json · knowledge/content-index/ · knowledge/content-database.jsonl
Writes: assets/ideas.json                        each row's `reuse` block, filled in place
        assets/_work/reuse/candidates.json       the top pages per idea, WITH their scores
"""
import numpy as np

from ..brand import _common as bcm
from ..research import _common as rc
from ..research import ownpage
from ..tools import _index
from ..tools import _shared as sh
from ..tools import voyage
from . import _common as cm

OUTPUT = "ideas.json"
WORK = "_work/reuse/"
CANDIDATES = "candidates.json"

# The reuse check's own numbers. N_RETRIEVE (40 dense candidates) and ALPHA (title weight 0.5) are
# research/_common's, because they are the same retrieval and there should be one copy of each.
# KEEP is this workflow's: dense retrieval is approximate, so cast a wide net and let the reranker
# keep the genuinely relevant ones. It was 7 and was widened to 15 so a reviewer sees more of the
# neighbourhood. The judge still reads only the top rc.TOPK of them, which is the read window the
# original settled on.
KEEP = 15

NO_INDEX = ("There is no page index yet, so nothing could be checked against your existing pages. "
            "Run build_page_index (it embeds the site once), then redo this.")
NO_KEY = ("There is no Voyage key, so your existing pages could not be searched by meaning. Add "
          "one in Connections (it is free at voyageai.com), then redo this.")


# ---- stage 2: retrieval, mechanical, no judgment ------------------------------------------------

def retrieve(rows, say):
    """{idea id: [{url, title, score}]}, best first, at most KEEP each.

    Every idea is scored against the index in ONE pass. `_index.body_best` walks the whole body
    index off disk to answer a query, so asking it once per idea would re-read the entire index a
    hundred times over. It takes a matrix of queries, so it is asked once with all of them. This is
    also why the research flow's `ownpage.retrieve` is not simply called in a loop here: it answers
    one topic at a time, which is right for one article and wrong for a sheet.

    The query is the asset title with any parenthetical stripped, and NOT the angle. The angle is a
    competitor-gap paragraph and it drags the search to tangents; the parenthetical is the same
    noise in miniature, and in the original's testing it pushed the right page from rank 1 to 21.
    """
    queries = [rc.query_text(r.get("title") or "") for r in rows]
    Q = np.asarray(voyage.embed(queries, "query"), dtype=np.float32)
    blend, _T, _B, meta, order = _index.score(Q, alpha=rc.ALPHA)
    bodies = sh.page_bodies()

    def doc(url):
        text = ((meta.get(url) or "")[:200] + "\n" + bodies.get(url.rstrip("/"), ""))
        return text[:rc.RERANK_DOC_CHARS].replace("\x00", " ").strip() or "(no content)"

    def one(i):
        scores = np.asarray(blend[i], dtype=np.float32)
        # Translation duplicates are dropped here rather than after the rerank: a /de/ twin of an
        # English page is never the answer and it would only eat a result slot.
        near = [int(k) for k in np.argsort(scores)[::-1]
                if not rc.is_foreign(order[int(k)])][:rc.N_RETRIEVE]
        urls = [order[k] for k in near]
        if not urls:
            return []
        try:
            ranked = voyage.rerank(queries[i], [doc(u) for u in urls], min(KEEP, len(urls)))
            top = [(urls[j], float(s)) for j, s in ranked]
        except Exception:   # noqa: BLE001 — a rerank hiccup keeps the dense order, minus its scores
            top = [(u, 0.0) for u in urls[:KEEP]]
        return [{"url": u, "title": meta.get(u) or "", "score": round(s, 3)} for u, s in top]

    found = {r["id"]: one(i) for i, r in enumerate(rows)}
    say("Searched your own pages for each idea",
        "%s read against %s of yours, then re-ranked on their full text"
        % (sh.plural(len(rows), "idea"), sh.plural(len(order), "page")))
    return found


# ---- stage 3: the judgment ----------------------------------------------------------------------

def judge(row, pages, co):
    """One verdict for one idea, from `ownpage.reuse_judge`: the ported prompt, unchanged.

    The verdict comes back in the research flow's title case and is written in the asset sheet's
    lower case. `_common.REUSE_VERDICTS` is the sheet's list and it is what the row is checked
    against, so a wording that is not one of the four never reaches the file.
    """
    shown = pages[:rc.TOPK]        # the read window: the judge sees these and cites only these
    out = ownpage.reuse_judge(row.get("title") or "", row.get("angle") or "",
                              shown, co, fmt=row.get("format") or "content asset")
    verdict = (out.get("verdict") or "").strip().lower()
    if verdict not in cm.REUSE_VERDICTS:
        verdict = "brand new"
    # `reuse_judge` already drops a URL that was not among the pages it was handed. Checked again
    # here against the same set, because this is the rule the sheet depends on and it should be
    # readable in the file that writes the sheet, not only in the one that builds the prompt.
    allowed = {p["url"] for p in shown}
    links = [u for u in out.get("chosen_links") or [] if u in allowed]
    return {"verdict": verdict, "links": links, "why": (out.get("why") or "").strip()}


# ---- the builder --------------------------------------------------------------------------------

def run(co, say, redo=False):
    rows = cm.ideas()
    if not rows:
        raise RuntimeError("There is no idea sheet yet. The merge has to run before the reuse "
                           "check has anything to check.")

    todo = [r for r in rows if redo or not (r.get("reuse") or {}).get("verdict")]
    if not todo:
        say("Kept the reuse verdicts", "%s already checked; ask for a redo to run it again"
            % sh.plural(len(rows), "idea"))
        return {"files": [OUTPUT], "needs_review": []}

    if not _index.status().get("built"):
        say("Skipped the reuse check", NO_INDEX)
        return {"files": [], "needs_review": ["ideas.json: " + NO_INDEX]}
    if not voyage.available():
        say("Skipped the reuse check", NO_KEY)
        return {"files": [], "needs_review": ["ideas.json: " + NO_KEY]}

    # Retrieval is the Voyage half and the expensive half, so it is cached whole. The judging that
    # follows is model calls, which are free and are resumed per idea by the row's own verdict.
    found = cm.read(WORK + CANDIDATES) if cm.exists(WORK + CANDIDATES) else None
    if redo or not isinstance(found, dict) or any(r["id"] not in found for r in todo):
        found = retrieve(rows, say)
        cm.save(WORK + CANDIDATES, found)

    judged = bcm.parallel(lambda r: judge(r, found.get(r["id"]) or [], co), todo,
                          say=say, label="Reading your pages against each idea", every=10)
    failed = []
    for row, result, err in judged:
        if err or not result:
            failed.append(row["id"])
            continue
        row["reuse"] = result
    cm.save_ideas(rows)

    counts = {v: 0 for v in cm.REUSE_VERDICTS}
    for r in rows:
        v = (r.get("reuse") or {}).get("verdict")
        if v in counts:
            counts[v] += 1
    notes = []
    if failed:
        # An unjudged row keeps its empty verdict rather than a default. "Brand new" by default
        # would read as a decision somebody made, and it is the answer that costs the most: it
        # sends someone off to build a thing we may already own.
        notes.append("ideas.json: %s could not be judged and have no reuse verdict yet; redo the "
                     "reuse check to try them again." % sh.plural(len(failed), "idea"))
    say("Checked every idea against what you already publish",
        "already have it %d · improve existing %d · build from parts %d · brand new %d"
        % tuple(counts[v] for v in cm.REUSE_VERDICTS))
    return {"files": [OUTPUT], "needs_review": notes, "counts": counts,
            "judged": len(todo) - len(failed)}
