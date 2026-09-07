"""gap_check.py — Step 3: does the evidence cover what the brief says matters?

Ported from 12-gap-check/scripts (checklist.py, judge.py, triage.py, report.py). The checklist is
built in PURE CODE from the winners lists and the AI Overview: three types, gap_we_own · winner_h2 ·
aio_subtopic. One judge call PER ITEM, the whole dossier in each call, a verbatim quoted sentence as
proof. Then one triage call over the misses AND the dossier, capped at GAP_MAX_QUERIES research
questions. The extra evidence rounds for those questions are run by the tool (evidence.gather).

A verdict outside {covered, partial, no} is never read as "covered": it is counted as a miss and
kept on record with its raw text (the original refused to triage on one; the agent stays honest and
keeps going).

Reads: the article context, the winners lists, the AI Overview text, the cards.
Writes (via the tool): _work/gap-check.json {items, queries}.
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c
from . import evidence


def checklist(lists, aio_text):
    """{id, type, item} rows: gaps we can own, the winners' common H2s, the AI Overview skeleton."""
    items = []

    def add(typ, text):
        text = str(text or "").strip()
        if text:
            items.append({"id": "%s-%d" % (typ, sum(1 for i in items if i["type"] == typ) + 1),
                          "type": typ, "item": text})

    for g in (lists.get("gaps_to_own") or []):
        add("gap_we_own", g)
    for h in (lists.get("common_h2s") or []):
        add("winner_h2", h)
    if (aio_text or "").strip():
        add("aio_subtopic", aio_text.strip())
    return items


def _judge_one(item, meta, dossier):
    p = _c.prompt("coverage-judge", asset_title=meta["title"], distinct_angle=meta["angle"],
                  spine=_c.na(meta.get("spine")), about=_c.na(meta.get("about")),
                  not_about=_c.na(meta.get("not_about")), item_type=item["type"], item_text=item["item"],
                  dossier_text=dossier)
    try:
        v = llm.json_call(p) or {}
    except Exception as e:  # noqa: BLE001 — a judge that fails is a miss on record, never a silent "covered"
        v = {"verdict": "no", "reason": "the judge did not answer (%s)" % str(e)[:60], "evidence": ""}
    v = v if isinstance(v, dict) else {}
    raw = str(v.get("verdict") or "").strip().lower()
    verdict = raw if raw in _c.VALID_VERDICTS else "no"
    out = {"id": item["id"], "type": item["type"], "item": item["item"], "verdict": verdict,
           "why": str(v.get("reason") or "").strip(), "evidence": str(v.get("evidence") or "").strip()}
    if raw != verdict:
        out["verdict_raw"] = raw                      # unrecognised: counted as a miss, kept on record
    return out


def judge(items, meta, cards, say=None):
    items = [i for i in items if i["type"] in _c.JUDGED_TYPES]
    if not items:
        return []
    dossier = evidence.dossier_text(cards)
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        verdicts = list(ex.map(lambda it: _judge_one(it, meta, dossier), items))
    if say:
        counts = {}
        for v in verdicts:
            counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        say("Judged %s" % _plural(len(verdicts), "item"),
            ", ".join("%d %s" % (n, k) for k, n in sorted(counts.items())))
    return verdicts


def triage(verdicts, meta, cards):
    """At most GAP_MAX_QUERIES research questions. Runs even with zero misses: the triage also reads
    the dossier for under-researched AREAS (own_find)."""
    misses = [v for v in verdicts if v["verdict"] in _c.MISS_VERDICTS]
    lines = (["- [%s] (%s) %s — judge: %s" % (v["verdict"], v["type"], v["item"], v["why"]) for v in misses]
             or ["(none — every checklist item was judged covered)"])
    p = _c.prompt("gap-triage", asset_title=meta["title"], distinct_angle=meta["angle"],
                  spine=_c.na(meta.get("spine")), about=_c.na(meta.get("about")),
                  not_about=_c.na(meta.get("not_about")), no_and_partial_items="\n".join(lines),
                  dossier_text=evidence.dossier_text(cards))
    try:
        got = llm.json_call(p) or {}
    except Exception:  # noqa: BLE001 — no triage means no extra spend, and the report says so
        got = {}
    queries = []
    for q in ((got.get("queries") if isinstance(got, dict) else None) or []):
        if isinstance(q, dict) and str(q.get("query") or "").strip():
            queries.append({"query": str(q["query"]).strip(), "fills": _c.strings(q.get("fills")),
                            "source": q.get("source") if q.get("source") in ("flagged", "own_find") else "flagged",
                            "why": str(q.get("why") or "").strip()})
        if len(queries) >= _c.GAP_MAX_QUERIES:                # hard cap at 3
            break
    return queries


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")
