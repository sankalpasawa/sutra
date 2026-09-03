"""keywords.py — Step 3: metrics + intent (API), then the scorer PANEL and the JUDGE (LLM).

Ported from 10-dataforseo/scripts/s3_metrics.py + s3_score.py. The rule that governs it:
"No pick without a score." The judge never chooses a primary off zero scorer input, and every
number on every keyword it returns is copied back from the metrics table, never from the model.

Reads: the shortlist, topic, angle, world, hygiene, company.
Writes (via the tool): _work/metrics.json, _work/verdicts.json, _work/keywords.json.
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from ..tools import dfs
from . import _common as _c

WANTED_INTENTS = ("informational", "commercial")   # keep intent in {informational, commercial}


class NoKeywordDemand(RuntimeError):
    """DEFINED, non-error outcome: not one informational/commercial keyword cleared the volume floor,
    so there is nothing to score — the topic simply has no keyword demand (an editorial/niche idea)."""


class NoScores(RuntimeError):
    """The scorer produced nothing usable. Refusing to pick a primary keyword with no scores."""


def metrics(shortlist, company):
    """keyword_overview on the shortlist survivors (<=700). {"rows": [{kw, vol, kd, intent}], "cost"}."""
    kws = [v["kw"] for v in (shortlist or []) if v.get("kw")][:700]
    if not kws:
        return {"rows": [], "cost": 0.0}
    got = dfs.keyword_overview(kws, location_name=company.get("location_name") or "United States",
                               language_code=company.get("language_code") or "en")
    return {"rows": got.get("rows") or [], "cost": got.get("cost") or 0.0, "demo": bool(got.get("demo"))}


def _table(rows):
    return "\n".join("%s | %s | %s | %s" % (r["kw"], r.get("vol"), r.get("kd"), r.get("intent") or "")
                     for r in rows)


def _score_batch(batch, topic, angle, world, hygiene, tok):
    """(ok, rows). ok=False marks a real failure, distinct from a legitimately empty result."""
    p = _c.prompt("score-keywords", brand=tok["brand"], asset_topic=topic,
                  distinct_angle=angle or "(none given yet)", brand_oneliner=tok["brand_oneliner"],
                  hygiene=hygiene or "(none flagged)", candidate_table=_table(batch), **_c.world_tokens(world))
    try:
        out = llm.json_call(p)
        rows = out if isinstance(out, list) else (out.get("scores") if isinstance(out, dict) else [])
        return True, [r for r in (rows or []) if isinstance(r, dict) and r.get("keyword")]
    except Exception:  # noqa: BLE001 — a failed batch is recorded, not hidden; run() refuses to judge on none
        return False, []


def _rank_spokes(spokes):
    """Sort spoke candidates best-first: W_REL*(relevance/10) + W_VOL*volume(log min-max) + W_KD*((100-KD)/100).
    HARD FLOOR first: drop off-cluster heads (relevance below SPOKE_MIN_RELEVANCE) whatever their volume."""
    if not spokes:
        return spokes
    spokes = [s for s in spokes if _c.num(s.get("relevance"), 5.0) >= _c.SPOKE_MIN_RELEVANCE]
    if not spokes:
        return spokes
    logs = [math.log10(max(_c.num(s.get("volume")), 1.0)) for s in spokes]
    lo, hi = min(logs), max(logs)
    span = hi - lo
    for s, lv in zip(spokes, logs):
        rel = max(0.0, min(_c.num(s.get("relevance"), 5.0), 10.0)) / 10.0    # default 5 if the judge omitted it
        vol = 0.5 if span == 0 else (lv - lo) / span                          # all-equal volumes → neutral
        kd = max(0.0, min((100.0 - _c.num(s.get("kd"), 50.0)) / 100.0, 1.0))
        s["spoke_score"] = round(_c.SPOKE_W_RELEVANCE * rel + _c.SPOKE_W_VOLUME * vol + _c.SPOKE_W_KD * kd, 3)
    return sorted(spokes, key=lambda s: s.get("spoke_score", 0.0), reverse=True)


def _measured(entry, by_kw):
    """The judge's keyword entry with its numbers taken from the metrics table. None when the
    keyword was never measured: a keyword the judge invented is not a keyword."""
    kw = (entry.get("keyword") if isinstance(entry, dict) else entry) or ""
    row = by_kw.get(str(kw).strip().lower())
    if not row:
        return None
    out = dict(entry) if isinstance(entry, dict) else {}
    out.update({"keyword": row["kw"], "volume": row.get("vol"), "kd": row.get("kd"),
                "intent": row.get("intent")})
    return out


def score_and_judge(rows, topic, angle, world, hygiene, company, say=None):
    """The panel + the judge. Returns {"verdicts": [...batches...], "final": {...}, "scored_rows",
    "failed_batches", "candidates"}. Raises NoKeywordDemand / NoScores (defined outcomes)."""
    tok = _c.company_tokens(company)
    cands = [r for r in (rows or []) if r.get("kw") and (r.get("intent") in WANTED_INTENTS)]
    if not cands:
        raise NoKeywordDemand("no informational or commercial keyword cleared the volume floor (>= %d); "
                              "this topic has no keyword demand" % _c.VOL_FLOOR)
    batches = [cands[i:i + _c.SCORE_BATCH_KW] for i in range(0, len(cands), _c.SCORE_BATCH_KW)]
    if say:
        say("Scoring %s" % _plural(len(cands), "keyword"),
            "%s of about %d, each scored for relevance, distinctness and brand fit"
            % (_plural(len(batches), "batch", "batches"), _c.SCORE_BATCH_KW))
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        results = list(ex.map(lambda b: _score_batch(b, topic, angle, world, hygiene, tok), batches))
    verdicts = [rows_ for _ok, rows_ in results]
    scored_rows = [row for ok, rows_ in results if ok for row in rows_]
    failed = sum(1 for ok, _ in results if not ok)
    if not scored_rows:
        raise NoScores("the scorer produced 0 rows across %d batch(es) (%d failed); refusing to pick a "
                       "primary keyword with no scores" % (len(batches), failed))
    if failed and say:
        say("%s of scores failed" % _plural(failed, "batch", "batches"), "Judging on the survivors only")

    by_kw = {r["kw"].strip().lower(): r for r in cands}
    jp = _c.prompt("judge-keywords", brand=tok["brand"], asset_topic=topic,
                   distinct_angle=angle or "(none given yet)", verdicts=json.dumps(scored_rows),
                   metrics_table=_table(cands), **_c.world_tokens(world))
    final, primary = {}, None
    for attempt in range(2):
        got = llm.json_call(jp if attempt == 0 else
                            jp + "\n\nThe primary keyword MUST be one of the keywords in the numbers table, "
                                 "spelled exactly as it appears there.")
        final = got if isinstance(got, dict) else {}
        primary = _measured(final.get("primary") or {}, by_kw)
        if primary:
            break
    if not primary:
        raise NoScores("the judge picked a keyword that was never measured (%r); refusing to build on it"
                       % ((final.get("primary") or {}).get("keyword") if isinstance(final.get("primary"), dict) else final.get("primary")))
    primary["split_world"] = bool(primary.get("split_world"))
    primary["why"] = str(primary.get("why") or "").strip()

    def _list(key):
        out, seen = [], {primary["keyword"].lower()}
        for e in (final.get(key) or []):
            m = _measured(e, by_kw)
            if m and m["keyword"].lower() not in seen:
                seen.add(m["keyword"].lower())
                out.append(m)
        return out

    final = {
        "primary": primary,
        "variations": _list("variations"),
        "secondary": _list("secondary"),
        "spoke_candidates": _rank_spokes(_list("spoke_candidates")),
        "in_body": _c.strings(final.get("in_body")),
        "notes": str(final.get("notes") or "").strip(),
    }
    return {"final": final, "verdicts": verdicts, "scored_rows": len(scored_rows),
            "failed_batches": failed, "candidates": len(cands)}


def _plural(n, word, many=None):
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))
