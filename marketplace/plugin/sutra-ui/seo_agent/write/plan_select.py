"""plan_select.py — Planner step 2: SELECT. Judge every H3, keep sections by arithmetic, place orphans.

Reads:  the gathered inputs (group_a + group_b) and the article context.
Writes: the lean tagged plan, plus the audit (tags, drops, placements, stats).

  0. NORMALISE — cards sitting directly on an H2 become one pseudo-H3 titled after the H2, so every card
                 lives under exactly one H3 and every H3 under exactly one H2.
  1. TAG       — one AI call per H2 (parallel): each H3 tagged asset-angle / gap / common-h2 / paa /
                 related (by minted ID), or untagged. winners_drift = the avoid list. The tagger also
                 gets the SPINE + the world (about / not_about) and each card's SOURCE, and applies a
                 WORLD TEST first. EVERY TAG NAMES ITS PROOF: a tag is kept only when it cites at least
                 one card that really belongs to THIS H3 (the receipt rule, enforced in code).
  2. SCORE     — pure arithmetic: an H2 survives at >= SELECT_H3_COVERAGE tagged H3s and keeps ONLY its
                 tagged H3s; below the bar the H2 dies and its tagged H3s become orphans.
  3. PLACE     — one AI call force-fits every orphan into the best surviving H2 (code fallback: the
                 survivor sharing the most tag targets).
  4. ASSEMBLE  — the lean plan. The tags are the only authority. Everything dropped is recorded.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import llm
from . import _common as C

TAG_KINDS = ("gap", "common-h2", "paa", "related")
_ID_PREFIX = {"gap": "G", "common-h2": "T", "paa": "Q", "related": "R"}


def _norm_txt(s):
    return " ".join((s or "").strip().lower().split())


def _normalise_sections(menu):
    """Step 0: section-level cards -> one pseudo-H3; every H3 carries its cards."""
    out = []
    for sec in menu:
        h3s = []
        sec_cards = list(sec.get("evidence", []))
        if sec_cards:
            h3s.append({"h3": sec.get("h2", ""), "cards": sec_cards})
        for h in sec.get("h3", []):
            h3s.append({"h3": h.get("h3", ""), "cards": list(h.get("evidence", []))})
        tk = sec.get("target_keyword")
        tko = ({"keyword": tk["keyword"], "volume": tk.get("volume")}
               if isinstance(tk, dict) and tk.get("keyword") else
               ({"keyword": tk, "volume": None} if isinstance(tk, str) and tk.strip() else None))
        out.append({"h2": sec.get("h2", ""), "job": sec.get("job", ""), "target_keyword": tko, "h3s": h3s})
    return out


def _render_h3_block(h3s):
    lines = []
    for i, h in enumerate(h3s):
        lines.append("[index %d] H3: %s" % (i, h["h3"]))
        for c in h["cards"]:
            g = (c.get("gloss") or "").strip()
            v = (c.get("verbatim") or "").strip().replace("\n", " ")
            src = (c.get("source_urls") or [None])[0] or "-"       # the world test reads this
            lines.append("  - id%s [%s] %s: %s" % (c.get("card_id"), c.get("tag", ""), src, g)
                         + (" — " + v if v else ""))
        if not h["cards"]:
            lines.append("  (no cards)")
    return "\n".join(lines)


def _tag_maps(b):
    """Mint per-article IDs: kind -> {id: original text} (G1.., T1.., Q1.., R1..)."""
    lists = {"gap": b.get("gaps_to_own", []), "common-h2": b.get("winners_common_h2s", []),
             "paa": b.get("paa_pool", []), "related": b.get("related_searches", [])}
    return {kind: {"%s%d" % (_ID_PREFIX[kind], i + 1): x for i, x in enumerate(items)}
            for kind, items in lists.items()}


def _id_block(maps, kind):
    return "\n".join("- %s: %s" % (i, x) for i, x in maps[kind].items()) or "(none)"


def _clean_tags(raw, maps, h3_card_ids=None):
    """Validate one H3's tags. Each entry is {"tag": "kind: ID", "cards": [ids]} (a bare string is still
    accepted). A tag is kept only when it cites at least one card that really belongs to THIS H3, the
    receipt rule. 'asset-angle' passes on its kind; 'kind: <ID>' decodes via the minted map; a tag
    carrying the item's full text still matches verbatim. Anything else -> bad."""
    text_maps = {k: {_norm_txt(x): x for x in m.values()} for k, m in maps.items()}
    allowed = {C.nid(c) for c in (h3_card_ids or [])}
    good, bad, receipts = [], [], {}
    for entry in raw or []:
        if isinstance(entry, dict):
            t = str(entry.get("tag") or "").strip()
            cited = [C.nid(c) for c in (entry.get("cards") or [])]
            cited = [c for c in cited if c in allowed] if allowed else cited
            if allowed and not cited:                      # no valid receipt -> the tag does not exist
                bad.append("%s (no valid card cited)" % t)
                continue
        else:
            t, cited = str(entry).strip(), []
        if _norm_txt(t) == "asset-angle":
            if "asset-angle" not in good:
                good.append("asset-angle")
                receipts["asset-angle"] = cited
            continue
        matched = False
        for kind in TAG_KINDS:
            if t.lower().startswith(kind + ":"):
                val = t.split(":", 1)[1].strip()
                hit = maps[kind].get(val.upper()) or text_maps[kind].get(_norm_txt(val))
                if hit:
                    canon = "%s: %s" % (kind, hit)
                    if canon not in good:
                        good.append(canon)
                        receipts[canon] = cited
                    matched = True
                break
        if not matched:
            bad.append(t)
    return good, bad, receipts


def run(inputs, ctx, say=lambda *a: None):
    a, b = inputs["group_a"], inputs["group_b"]
    brand = C.company()
    sections = _normalise_sections(b["sections_menu"])
    maps = _tag_maps(b)

    base = C.prompt("tag-h3s", brand=brand["brand"], about=brand["about"],
                    title=ctx["title"] or "(none)", angle=ctx["angle"] or "(none)",
                    h1=a.get("h1", ""), primary_keyword=a.get("primary_keyword", ""),
                    spine=C.or_na(ctx, "spine"), world_about=C.or_na(ctx, "about"),
                    world_not_about=C.or_na(ctx, "not_about"),
                    gaps=_id_block(maps, "gap"), common_h2s=_id_block(maps, "common-h2"),
                    paa=_id_block(maps, "paa"), related=_id_block(maps, "related"),
                    drift="\n".join("- " + x for x in b.get("winners_drift", [])) or "(none)")

    # --- Step 1: TAG (one call per H2, parallel) -----------------------------
    def _tag(i):
        sec = sections[i]
        p = base.replace("{{H2}}", sec["h2"]).replace("{{H3S}}", _render_h3_block(sec["h3s"]))
        r = llm.json_call(p) or {}
        return i, r.get("h3s") or []

    say("Judging every sub-section", "%d sections, one call each" % len(sections))
    tag_log, invalid_log = {}, {}
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        for fut in as_completed([ex.submit(_tag, i) for i in range(len(sections))]):
            i, entries = fut.result()
            got = {}
            for e in entries:
                if not isinstance(e, dict):
                    continue
                try:
                    idx_ = int(e.get("index"))
                except (TypeError, ValueError):
                    continue
                if 0 <= idx_ < len(sections[i]["h3s"]):
                    h3_cards = [c.get("card_id") for c in sections[i]["h3s"][idx_]["cards"]]
                    good, bad, rcp = _clean_tags(e.get("tags"), maps, h3_cards)
                    got[idx_] = good
                    sections[i]["h3s"][idx_]["tag_receipts"] = rcp
                    why = (e.get("why_untagged") or "").strip()
                    if why and not good:
                        sections[i]["h3s"][idx_]["why_untagged"] = why
                    if bad:
                        invalid_log.setdefault(sections[i]["h2"], []).extend(bad)
            for j, h in enumerate(sections[i]["h3s"]):
                h["tags"] = got.get(j, [])
                if j not in got:
                    h["ai_missed"] = True
            tagged = sum(1 for h in sections[i]["h3s"] if h["tags"])
            say("Judged: %s" % sections[i]["h2"][:56], "%d of %d sub-sections earn a place" % (tagged, len(sections[i]["h3s"])))
            tag_log[sections[i]["h2"]] = [{"h3": h["h3"], "tags": h["tags"]} for h in sections[i]["h3s"]]

    # --- Step 2: SCORE + SPLIT (pure arithmetic) -----------------------------
    thr = C.SELECT_H3_COVERAGE
    survivors, dead, drops, stats_rows = [], [], [], []
    for sec in sections:
        total = len(sec["h3s"])
        tagged = [h for h in sec["h3s"] if h["tags"]]
        cov = (len(tagged) / total) if total else 0.0
        verdict = "keep" if cov >= thr and tagged else "cut"
        stats_rows.append({"h2": sec["h2"], "h3s": total, "tagged": len(tagged),
                           "coverage": round(cov, 2), "verdict": verdict})
        for h in sec["h3s"]:
            if not h["tags"]:
                drops.append({"h3": h["h3"], "from_h2": sec["h2"],
                              "why": "untagged in %s section" % ("surviving" if verdict == "keep" else "dead"),
                              "ai_reason": h.get("why_untagged", "")})
        if verdict == "keep":
            survivors.append({"h2": sec["h2"], "job": sec.get("job", ""),
                              "target_keyword": sec["target_keyword"], "h3s": tagged})
        else:
            dead.append(sec)
    orphans = [{"h3": h, "from_h2": sec["h2"]} for sec in dead for h in sec["h3s"] if h["tags"]]
    say("Kept the sections that earn their place",
        "%d kept, %d cut, %d sub-sections to re-home" % (len(survivors), len(dead), len(orphans)))

    # --- Step 3: PLACE the orphans -------------------------------------------
    placements = []
    if orphans and survivors:
        surv_block = "\n".join(
            "[index %d] %s — kept H3s: " % (i, s["h2"]) + ("; ".join(h["h3"] for h in s["h3s"]) or "(none)")
            for i, s in enumerate(survivors))
        orph_block = "\n".join(
            "[index %d] %s | tags: %s | from cut section: %s | evidence: " % (
                j, o["h3"]["h3"], ", ".join(o["h3"]["tags"]), o["from_h2"])
            + "; ".join((c.get("gloss") or "")[:80] for c in o["h3"]["cards"][:3])
            for j, o in enumerate(orphans))
        try:
            r = llm.json_call(C.prompt("place-orphans", title=ctx["title"], angle=ctx["angle"],
                                       spine=C.or_na(ctx, "spine"), world_not_about=C.or_na(ctx, "not_about"),
                                       survivors=surv_block, orphans=orph_block)) or {}
        except Exception:       # noqa: BLE001 — the code fallback places every orphan anyway
            r = {}
        chosen = {}
        for p in r.get("placements") or []:
            try:
                chosen[int(p["orphan"])] = int(p["into"])
            except (TypeError, ValueError, KeyError):
                continue
        for j, o in enumerate(orphans):
            k = chosen.get(j)
            fb = not (isinstance(k, int) and 0 <= k < len(survivors))
            if fb:                                          # fallback: the survivor sharing the most tag targets
                tags_ = set(o["h3"]["tags"])
                k = max(range(len(survivors)),
                        key=lambda i2: len({t for h in survivors[i2]["h3s"] for t in h["tags"]} & tags_))
            h = dict(o["h3"])
            h["placed_from"] = o["from_h2"]
            survivors[k]["h3s"].append(h)
            placements.append({"h3": o["h3"]["h3"], "from": o["from_h2"], "into": survivors[k]["h2"],
                               "fallback": fb})

    # --- Step 4: ASSEMBLE ----------------------------------------------------
    def _out_h3(h):
        o = {"h3": h["h3"], "tags": h["tags"], "tag_receipts": h.get("tag_receipts", {}), "card_ids": []}
        for c in h["cards"]:
            cid = C.nid(c.get("card_id"))
            if cid not in o["card_ids"]:
                o["card_ids"].append(cid)
        if h.get("placed_from"):
            o["placed_from"] = h["placed_from"]
        return o

    plan = {
        "h1": a.get("h1", ""), "format_archetype": a.get("format_archetype", ""),
        "primary_keyword": a.get("primary_keyword", ""), "word_band": a.get("word_band", {}),
        "persona": a.get("persona", {}),
        "gaps_to_own": b.get("gaps_to_own", []), "winners_common_h2s": b.get("winners_common_h2s", []),
        "winners_drift": b.get("winners_drift", []), "paa_pool": b.get("paa_pool", []),
        "related_searches": b.get("related_searches", []),
        "search_intent": a.get("search_intent", ""), "ai_overview": a.get("ai_overview", ""),
        "table_stakes": a.get("table_stakes", []),
        "sections": [{"h2": s["h2"], "job": s.get("job", ""), "target_keyword": s["target_keyword"],
                      "h3s": [_out_h3(h) for h in s["h3s"]]} for s in survivors],
    }
    audit = {"ids": maps, "tags": {"by_h2": tag_log, "invalid_tags": invalid_log},
             "drops": {"dead_h2s": [s["h2"] for s in dead], "dropped_h3s": drops},
             "placements": placements,
             "stats": {"threshold": thr, "candidates": len(sections), "survivors": len(survivors),
                       "dead": len(dead), "orphans_placed": len(placements), "h3s_dropped": len(drops),
                       "per_h2": stats_rows}}
    return {"plan": plan, "audit": audit}
