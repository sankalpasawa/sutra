"""run_research.py — everything the writer needs to know, before a word is written.

Five stages, each one feeding the next: candidate keywords, real numbers for the best of
them, one primary keyword chosen, the SERP for it, then what the whole first page misses.

The rule that keywords we already rank top 20 for are off limits is enforced here, in an
if-statement, before the model ever sees the candidate list. A model asked not to pick
something will eventually pick it. A candidate that was never in the list cannot be picked.
"""
from .. import store
from .. import llm
from . import _shared as sh

try:
    from . import dfs
except ImportError:  # dfs.py is a separate module and may not be installed yet
    dfs = None

IDEA_LIMIT = 100        # candidates pulled from DataForSEO
METRIC_LIMIT = 30       # how many of them we pay to measure properly
SERP_DEPTH = 10         # top results we analyse
MAX_SECONDARY = 8


def _merge_metrics(candidates, metrics):
    """Measured numbers win over the estimates that came with the ideas."""
    by_kw = {m.get("keyword", "").strip().lower(): m for m in (metrics or []) if m.get("keyword")}
    out = []
    for c in candidates:
        term = (c.get("keyword") or "").strip()
        if not term:
            continue
        row = dict(c)
        m = by_kw.get(term.lower())
        if m:
            for field in ("volume", "difficulty", "cpc"):
                if m.get(field) is not None:
                    row[field] = m[field]
        out.append(row)
    return out


def _candidate_lines(rows):
    lines = []
    for r in rows:
        bits = []
        for field in ("volume", "difficulty", "cpc"):
            if sh.num(r.get(field)) is not None:
                bits.append("%s %s" % (field, r[field]))
        lines.append("%s (%s)" % (r["keyword"], ", ".join(bits)) if bits
                     else "%s (no numbers)" % r["keyword"])
    return lines


def _result_lines(results):
    lines = []
    for r in results:
        lines.append("%s. %s\n   %s\n   %s" % (
            r.get("position", "?"), r.get("title", "(no title)"),
            r.get("url", ""), (r.get("description") or "")[:300]))
    return lines


def run(ctx, topic, intent="mixed"):
    if not (topic or "").strip():
        return {"summary": "No topic given.", "error": "run_research needs a topic."}
    topic = topic.strip()
    say = sh.reporter(ctx, "run_research")

    mode = sh.dfs_mode(dfs)
    if mode == "off":
        return {"summary": "No keyword data available.",
                "error": ("DataForSEO is not connected, so there are no real volumes, "
                          "difficulties or SERPs to research with. Add the login in Connections.")}
    if mode == "demo":
        say("Using demo search data", "No DataForSEO login, so none of these numbers are real")

    index = sh.site_index()
    held = sh.already_ranking(index)

    # --- 1. candidates -------------------------------------------------------------------
    try:
        candidates = dfs.keyword_ideas(topic, limit=IDEA_LIMIT) or []
    except Exception as e:
        return {"summary": "Keyword lookup failed.",
                "error": "DataForSEO failed on keyword_ideas: %s" % str(e)[:300]}
    candidates = [c for c in candidates if c.get("keyword")]
    say("Found " + sh.plural(len(candidates), "keyword candidate"), "Seed: %s" % topic)

    if not candidates:
        # Still worth continuing on the topic itself rather than failing the whole run.
        candidates = [{"keyword": topic}]
        say("No candidates came back", "Carrying on with the topic phrase itself")

    # --- 2. real numbers for the best of them --------------------------------------------
    candidates.sort(key=lambda c: -(c.get("volume") or 0))
    shortlist = candidates[:METRIC_LIMIT]
    try:
        metrics = dfs.keyword_metrics([c["keyword"] for c in shortlist]) or []
    except Exception as e:
        metrics = []
        say("Could not measure keywords", str(e)[:160])
    measured = _merge_metrics(shortlist, metrics)
    with_volume = [m for m in measured if sh.num(m.get("volume"))]
    say("Measured " + sh.plural(len(measured), "keyword"),
        "%d of them have real search volume" % len(with_volume))

    # --- 3. the primary keyword ----------------------------------------------------------
    allowed = [m for m in measured if m["keyword"].strip().lower() not in held]
    skipped = len(measured) - len(allowed)
    if skipped:
        say("Skipped " + sh.plural(skipped, "keyword") + " you already rank for",
            "Top 20 already, so a new page would only compete with your own")
    if not allowed:
        allowed = measured  # everything is already ours; let the model pick the least bad

    allowed.sort(key=lambda m: -(m.get("volume") or 0))
    prompt = sh.fill(
        sh.load_prompt("pick_keyword"), topic=topic, intent=intent or "mixed",
        candidates=sh.bullets(_candidate_lines(allowed)),
        own_rankings=sh.bullets(
            ["%s (position %s)" % (k, v[0]) for k, v in sorted(held.items())[:40]],
            empty="(no site index, so nothing is known to be ranking)"),
    )
    primary_row, why, secondary = None, "", []
    try:
        pick = llm.json_call(prompt)
        wanted = (pick.get("primary_keyword") or "").strip().lower()
        primary_row = next((m for m in allowed if m["keyword"].strip().lower() == wanted), None)
        why = pick.get("why", "")
        wanted_secondary = [s.strip().lower() for s in (pick.get("secondary_keywords") or [])]
        secondary = [m["keyword"] for m in allowed
                     if m["keyword"].strip().lower() in wanted_secondary][:MAX_SECONDARY]
    except Exception as e:
        say("Keyword choice fell back to the numbers", str(e)[:160])

    if primary_row is None:
        # The model went off-list or failed. Highest volume among the allowed wins.
        primary_row = allowed[0]
        why = why or "Chosen on volume, because the model did not return a keyword from the list."
    if not secondary:
        secondary = [m["keyword"] for m in allowed if m["keyword"] != primary_row["keyword"]][:MAX_SECONDARY]

    primary = {"keyword": primary_row["keyword"], "volume": primary_row.get("volume"),
               "difficulty": primary_row.get("difficulty"), "cpc": primary_row.get("cpc")}
    vol, diff = sh.num(primary["volume"]), sh.num(primary["difficulty"])
    say("Primary keyword: %s" % primary["keyword"],
        "%s a month, difficulty %s" % (vol if vol is not None else "volume unknown",
                                       diff if diff is not None else "unknown"))

    # --- 4. the SERP ---------------------------------------------------------------------
    top_results, paa = [], []
    try:
        serp = dfs.serp(primary["keyword"]) or {}
        top_results = (serp.get("top_results") or [])[:SERP_DEPTH]
        paa = serp.get("people_also_ask") or []
    except Exception as e:
        say("SERP lookup failed", str(e)[:160])
    say("Read the top " + sh.plural(len(top_results), "result"),
        sh.plural(len(paa), "People Also Ask question"))

    # --- 5. the gap ----------------------------------------------------------------------
    covered, gap, angle = [], "", ""
    if top_results:
        gap_prompt = sh.fill(
            sh.load_prompt("find_gap"), keyword=primary["keyword"], topic=topic,
            company=sh.company_name(), voice=sh.voice_block(),
            top_results="\n".join(_result_lines(top_results)),
            paa=sh.bullets(paa, empty="(none returned)"),
        )
        try:
            found = llm.json_call(gap_prompt)
            covered = [c for c in (found.get("what_they_all_cover") or []) if c]
            gap = found.get("the_gap", "")
            angle = found.get("recommended_angle", "")
            say("Found the gap", gap[:160])
        except Exception as e:
            say("Gap analysis failed", str(e)[:160])
    else:
        say("No SERP to analyse",
            "The gap and the angle are empty, so decide the angle yourself")

    research = {
        "topic": topic,
        "intent": intent or "mixed",
        "primary_keyword": primary,
        "primary_keyword_why": why,
        "secondary_keywords": secondary,
        "people_also_ask": paa,
        "top_results": top_results,
        "what_they_all_cover": covered,
        "the_gap": gap,
        "recommended_angle": angle,
        "candidates_considered": len(candidates),
        "skipped_already_ranking": skipped,
        "demo_data": mode == "demo",
        "generated_at": store.now(),
    }
    store.save_artifact(ctx["chat_id"], ctx["run_id"], "research.json", research)

    summary = "Primary: '%s', %s, difficulty %s" % (
        primary["keyword"],
        ("%s/mo" % vol) if vol is not None else "volume unknown",
        diff if diff is not None else "unknown")
    if mode == "demo":
        summary += " (demo data, no DataForSEO login, so the numbers are not real)"
    if not top_results:
        summary += ". No SERP data, so there is no gap analysis."
    elif not gap:
        summary += ". The gap analysis failed, so there is no recommended angle yet."
    return {"summary": summary, "artifact": "research.json"}
