"""The coverage gates + the honest report. In the original a failed gate failed the run (exit 1);
here it is REPORTED (the tool's note carries it) so the agent tells the user, never raises.

Reads:  the extracted rows, reconciled.json, urls-wp.json, urls-sitemap.json, urls-archive.json,
        the raw-cache metadata, and the traffic view.
Returns the report dict, written by index_site to knowledge/catalogue-report.json:
  {confidence, gates:[{name, pass, detail}], coverage_by_type, provenance, withheld, unknown,
   gaps, traffic, warnings, found_urls, read_urls}

Gate 1 — enumeration: per type, collected + unreadable + withheld == the CMS's own X-WP-Total;
         and every sitemap URL is ACCOUNTED FOR (in the catalogue, an alias, or an explicit drop
         bucket — never lost). Non-WordPress sites have no count header: the gate weakens to
         sitemap-accounting + the traffic cross-check, and confidence is stamped LOWER.
Gate 2 — response integrity: a cached body shorter than its declared Content-Length (when no
         Content-Encoding) = truncated transfer -> FAIL; documents missing </html> = WARN only.
Gate 3 — extraction coverage PER TYPE (a single global % hides exactly the failure that bit us):
         failed = body_status 'failed'. FAIL below GATE_OVERALL overall or GATE_PER_TYPE per type.
Gate 4 — the honest cross-check: any own-site page the traffic pull says is RANKING that the
         catalogue lacks is a provable gap.
"""
import os

from . import settings
from .urls import match_key, own_host


def _confidence(is_wp, unavailable, fetch):
    if fetch.get("site_blocked") or fetch.get("circuit_broken"):
        return ("low: the site stopped answering part-way through, so only the pages read before "
                "that are in the catalogue")
    if not is_wp:
        return ("lower: the site has no content-system counts to check against, so coverage rests on "
                "sitemap accounting and the traffic cross-check only")
    if unavailable:
        return ("partial: the site's own counts were verified for every content type that answered, "
                "but %d type(s) never did (%s), so total coverage is short by an unknown amount"
                % (len(unavailable), ", ".join(sorted(unavailable))))
    return "full: the site's own page counts were verified for every content type"


def run(fx, site, rows, reconciled, wp, sm, archive, traffic, found_urls, read_urls):
    gates, warnings = [], []
    is_wp = bool(wp.get("types"))
    unavailable = wp.get("unavailable") or {}
    fetch = reconciled.get("fetch") or {}

    # ---- gate 1: enumeration accounting --------------------------------------------------------
    problems, withheld = [], {}
    for t, meta in (wp.get("types") or {}).items():
        bad = meta.get("unreadable") or []
        held = meta.get("withheld") or 0
        if meta["collected"] + len(bad) + held != meta["total"]:
            problems.append("type %s: collected %d + %d unreadable + %d withheld is not the site's own count %d"
                            % (t, meta["collected"], len(bad), held, meta["total"]))
        if held:
            withheld[t] = {"collected": meta["collected"], "total": meta["total"], "withheld": held}
    accounted = set()
    for url, r in (reconciled.get("pages") or {}).items():
        accounted.add(match_key(url))
        for a in r.get("aliases", []):
            accounted.add(match_key(a))
    dropped = reconciled.get("dropped") or {}
    for bucket in ("dead", "soft_404", "offsite", "robots", "non_content", "unread"):
        for u in dropped.get(bucket, []):
            accounted.add(match_key(u))
    for u in dropped.get("collapsed", {}):
        accounted.add(match_key(u))
    lost = [u for u in (sm.get("urls") or {}) if match_key(u) not in accounted]
    if lost:
        problems.append("%d sitemap URLs are neither in the catalogue nor in any drop bucket (first: %s)"
                        % (len(lost), ", ".join(lost[:3])))
    if sm.get("blocked"):
        # Loud, but not an accounting failure: what a blocked sitemap would have listed is unknowable,
        # so it is a warning the user must see, while the gate keeps to what can be counted.
        warnings.append("%d declared sitemap(s) were blocked, so pages only they list are unknown: %s"
                        % (len(sm["blocked"]), "; ".join("%s (%s)" % (b["sitemap"], b["why"]) for b in sm["blocked"][:3])))
    detail = ("every content type matches the site's own count and every sitemap URL is accounted for"
              if not problems else "; ".join(problems))
    if not is_wp and not problems:
        detail = "no content-system counts to check; every sitemap URL is accounted for"
    if dropped.get("unread"):
        detail += "; %d URLs found but not read (max_pages %s)" % (len(dropped["unread"]), site.get("max_pages"))
    gates.append({"name": "enumeration accounting", "pass": not problems, "detail": detail})

    # ---- gate 2: response integrity --------------------------------------------------------------
    truncated, unclosed = [], 0
    for url in (reconciled.get("pages") or {}):
        meta = fx.cached_meta(url)
        if not meta:
            continue
        sha, status, ctype, kept = meta
        if status != 200 or not sha or "html" not in (ctype or "").lower():
            continue
        path = fx.raw_path(sha, ctype)
        if not os.path.exists(path):
            continue
        body = open(path, "rb").read()
        import json as _json
        headers = _json.loads(kept) if kept else {}
        clen = headers.get("content-length")
        if clen and "content-encoding" not in headers and str(clen).isdigit():
            if len(body) < int(clen):
                truncated.append(url)
        if b"</html" not in body[-4096:].lower():
            unclosed += 1
    if unclosed:
        warnings.append("%d documents without a closing </html> (some servers truncate their own responses)" % unclosed)
    gates.append({"name": "response integrity", "pass": not truncated,
                  "detail": ("every saved page is as long as the server said it was" if not truncated else
                             "%d pages arrived shorter than their declared length (first: %s)"
                             % (len(truncated), ", ".join(truncated[:3])))})

    # ---- gate 3: extraction coverage, PER TYPE ---------------------------------------------------
    per_type = {}
    for row in rows:
        d = per_type.setdefault(row["type"] or "(untyped)", {"rows": 0, "ok": 0, "stub": 0, "flagged": 0, "failed": 0})
        d["rows"] += 1
        status = row["body_status"] if row["body_status"] in ("ok", "stub", "flagged") else "failed"
        d[status] += 1
    covered_total = sum(d["ok"] + d["stub"] + d["flagged"] for d in per_type.values())
    overall = covered_total / max(1, len(rows))
    problems = []
    if overall < settings.GATE_OVERALL:
        problems.append("overall %.1f%% of pages yielded text, below %.0f%%" % (overall * 100, settings.GATE_OVERALL * 100))
    for t, d in sorted(per_type.items()):
        d["coverage"] = round((d["ok"] + d["stub"] + d["flagged"]) / max(1, d["rows"]), 4)
        if d["coverage"] < settings.GATE_PER_TYPE:
            problems.append("type %s: %.1f%% (%d of %d had no readable text), below %.0f%%"
                            % (t, d["coverage"] * 100, d["failed"], d["rows"], settings.GATE_PER_TYPE * 100))
    gates.append({"name": "extraction coverage", "pass": not problems,
                  "detail": ("%.1f%% of pages yielded readable text, and every type is above %.0f%%"
                             % (overall * 100, settings.GATE_PER_TYPE * 100)) if not problems else "; ".join(problems)})

    # ---- gate 4: the honest cross-check — ranking pages missing from the catalogue -----------------
    cat_keys = {match_key(row["url"]) for row in rows}
    for u in dropped.get("collapsed", {}):
        cat_keys.add(match_key(u))
    gaps = [p["url"] for p in traffic.get("top_pages") or []
            if own_host(p["url"], site["host"]) and match_key(p["url"]) not in cat_keys]
    tmeta = traffic.get("meta") or {}
    if tmeta.get("skipped"):
        detail = "not checked: " + tmeta["skipped"]
    elif tmeta.get("demo"):
        # demo traffic names made-up pages, so a "gap" here is fiction; say so instead of failing
        gaps, detail = [], "not checked: the traffic is demo data (no DataForSEO credentials)"
    elif gaps:
        detail = "%d pages that rank in search are missing from the catalogue (first: %s)" % (len(gaps), ", ".join(gaps[:3]))
    else:
        detail = "every own-site page that ranks in search is in the catalogue"
    gates.append({"name": "traffic cross-check", "pass": not gaps, "detail": detail})

    st = dict(reconciled.get("stats") or {})
    st["archive_unchecked"] = len(archive.get("unchecked") or [])
    st["archive_dead"] = len(archive.get("dead") or [])
    if archive.get("error"):
        warnings.append("web archive: " + archive["error"])
    if archive.get("unchecked"):
        warnings.append("%d archive-remembered URLs were not checked live (cap %d); they are not in the catalogue"
                        % (len(archive["unchecked"]), settings.ARCHIVE_LIVENESS_CAP))
    if fetch.get("page_blocked"):
        warnings.append("%d pages answered 403 while the rest of the site served; recorded as unread" % fetch["page_blocked"])
    if fetch.get("site_blocked"):
        warnings.append(fetch["site_blocked"])
    if fetch.get("circuit_broken"):
        warnings.append("the reading pass stopped after %d failures in a row" % settings.CIRCUIT_BREAK)
    if wp.get("blocked"):
        warnings.append("the content system refused part of its listing: %s" % "; ".join(wp["blocked"][:2]))

    return {
        "confidence": _confidence(is_wp, unavailable, fetch),
        "gates": gates,
        "coverage_by_type": per_type,
        "coverage_overall": round(overall, 4),
        "provenance": st,
        "withheld": withheld,
        "unknown": {t: m.get("reason", "") for t, m in unavailable.items()},
        "gaps": gaps,
        "traffic": tmeta,
        "warnings": warnings,
        "found_urls": found_urls,
        "read_urls": read_urls,
        "wordpress": is_wp,
        "sitemaps": {"parsed": len(sm.get("sitemaps_parsed") or []), "blocked": sm.get("blocked") or [],
                     "not_sitemaps": len(sm.get("not_sitemaps") or [])},
    }
