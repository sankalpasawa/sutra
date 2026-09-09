"""traffic_import.py — load a traffic file someone already paid for.

Five brand builders choose which pages to learn from by search traffic, and without it they
refuse. That is right, but it should not mean a person with a perfectly good traffic export is
stuck. This reads that export and writes it in as measured traffic.

It accepts the shape the workflow's own catalogue writes (URL, Traffic, Traffic_clean, Top
Keyword, Primary Intent, Market) and is forgiving about the column names, because the same data
comes out of several tools with different headers.

Nothing here invents a number. A row without a URL or without a traffic figure is dropped and
counted, and the run says how many.

Reads: a CSV path or its text. Writes: knowledge/top-pages.json, and folds the figures into
knowledge/site_index.json so the catalogue screen shows them too.
"""
import csv
import io

from .. import store

# header -> our field, lowercased and stripped of spaces and underscores
FIELDS = {
    "url": "url", "page": "url", "address": "url",
    "traffic": "traffic", "organictraffic": "traffic", "visits": "traffic", "sessions": "traffic",
    "trafficclean": "traffic_clean", "cleantraffic": "traffic_clean",
    "topkeyword": "top_keyword", "keyword": "top_keyword", "querry": "top_keyword", "query": "top_keyword",
    "primaryintent": "intent", "intent": "intent",
    "market": "market", "location": "market",
    "position": "position", "rank": "position",
    "volume": "keyword_volume", "searchvolume": "keyword_volume",
}


def _key(h):
    return "".join(ch for ch in (h or "").lower() if ch.isalnum())


def _num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def parse(text):
    """The rows in a traffic export. Returns (rows, dropped, why)."""
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:  # noqa: BLE001 — an unsniffable file is almost always a plain comma CSV
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], 0, "the file has no header row"
    cols = {h: FIELDS.get(_key(h)) for h in reader.fieldnames}
    if "url" not in cols.values():
        return [], 0, ("no column looks like a page address; the header row is: %s"
                       % ", ".join(reader.fieldnames[:8]))
    if "traffic" not in cols.values() and "traffic_clean" not in cols.values():
        return [], 0, ("no column looks like traffic; the header row is: %s"
                       % ", ".join(reader.fieldnames[:8]))
    rows, dropped = [], 0
    for raw in reader:
        rec = {}
        for h, field in cols.items():
            if field and raw.get(h) not in (None, ""):
                rec[field] = raw[h].strip() if isinstance(raw[h], str) else raw[h]
        url = (rec.get("url") or "").strip()
        if not url.startswith("http"):
            dropped += 1
            continue
        t = _num(rec.get("traffic"))
        tc = _num(rec.get("traffic_clean")) or t
        # A page that ranks for a keyword but earns no estimated traffic is still a real
        # measurement, and its keyword is worth keeping. Only a row with neither a figure nor a
        # keyword is nothing at all. (633 of your 2,254 rows are ranked-but-zero.)
        if not t and not tc and not (rec.get("top_keyword") or "").strip():
            dropped += 1
            continue
        rows.append({"url": url, "traffic": t or tc, "traffic_clean": tc,
                     "top_keyword": rec.get("top_keyword", ""), "intent": rec.get("intent", ""),
                     "market": rec.get("market", ""),
                     "position": _num(rec.get("position")) or None,
                     "keyword_volume": _num(rec.get("keyword_volume")) or None})
    rows.sort(key=lambda r: -(r.get("traffic_clean") or r.get("traffic") or 0))
    return rows, dropped, ""


def apply(text, source="an imported file", say=None):
    """Parse, save, and fold the figures into the catalogue. Returns a plain-English report."""
    rows, dropped, why = parse(text)
    if why:
        return {"ok": False, "error": why, "rows": 0}
    if not rows:
        return {"ok": False, "error": "no row in that file had both a page address and a traffic figure",
                "rows": 0}
    store.save_knowledge("top-pages.json", rows)
    if say:
        say("Imported the traffic", "%d pages with measured traffic from %s%s"
            % (len(rows), source, "; %d rows skipped" % dropped if dropped else ""))

    # fold into the catalogue so the Knowledge screen and every later step see it
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else None
    matched = 0
    if pages:
        by_url = {}
        for r in rows:
            by_url[r["url"].rstrip("/")] = r
        for p in pages:
            r = by_url.get((p.get("url") or "").rstrip("/"))
            if not r:
                continue
            matched += 1
            p["traffic"] = r["traffic"]
            p["traffic_clean"] = r["traffic_clean"]
            if r.get("top_keyword"):
                p["top_keyword"] = r["top_keyword"]
            if r.get("intent"):
                p["intent"] = r["intent"]
            if r.get("position"):
                p["position"] = r["position"]
            if r.get("keyword_volume"):
                p["keyword_volume"] = r["keyword_volume"]
        idx["traffic_source"] = source
        store.save_knowledge("site_index.json", idx)
        if say:
            say("Joined it to the catalogue", "%d of %d pages now carry real traffic"
                % (matched, len(pages)))
    return {"ok": True, "rows": len(rows), "dropped": dropped, "matched": matched,
            "summary": "%d pages with measured traffic imported, %d matched to the catalogue"
                       % (len(rows), matched)}
