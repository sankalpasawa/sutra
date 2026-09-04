"""suggest_topics.py — study ONE competitor, propose six topics we could own.

One competitor per run, not all of them. Reading every rival every time produces the same
safe middle-of-the-road list, so the competitor list rotates: whoever was used longest ago
goes next. Different rival, different ideas.

Every topic has to be sparked by a keyword the competitor actually ranks for. That is the
whole point of paying for the data. A topic with no source keyword is just a guess with
extra steps.
"""
from .. import store
from .. import llm
from . import _shared as sh

try:
    from . import dfs
except ImportError:  # dfs.py is a separate module and may not be installed yet
    dfs = None

RIVAL_KEYWORD_LIMIT = 100    # how many of the competitor's ranking keywords we pull
RIVAL_SHOWN = 60             # how many of those the model sees, best positions first
WANT_TOPICS = 6


def _load_competitors():
    """knowledge/competitors.json is {competitors: [{domain, why, last_used}]}; a bare list or plain
    strings (older saves) are read too."""
    raw = store.knowledge("competitors.json") or []
    if isinstance(raw, dict):
        raw = raw.get("competitors") or []
    rows = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            rows.append({"domain": item.strip(), "last_used": None})
        elif isinstance(item, dict) and item.get("domain"):
            rows.append({"domain": item["domain"].strip(),
                         "last_used": item.get("last_used"),
                         "why": item.get("why", "")})
    return rows


def _derive_competitors(ctx, say):
    """No list on file, so work one out from what we know we sell. Saved, so this only
    ever happens once."""
    voice = sh.brand_voice()
    if not voice:
        return []
    say("Working out who you compete with", "No competitor list on file yet")
    prompt = sh.fill(sh.load_prompt("derive_competitors"), voice=sh.voice_block(voice))
    try:
        data = llm.json_call(prompt)
    except Exception as e:
        say("Could not derive competitors", str(e)[:160])
        return []
    rows = []
    for item in (data.get("competitors") or [])[:4]:
        domain = (item.get("domain") or "").strip().lower()
        domain = domain.replace("https://", "").replace("http://", "").strip("/")
        if domain:
            rows.append({"domain": domain, "why": item.get("why", ""), "last_used": None})
    if rows:
        store.save_knowledge("competitors.json", {"competitors": rows})
        say("Saved " + sh.plural(len(rows), "competitor"), ", ".join(r["domain"] for r in rows))
    return rows


def _pick(rows, asked_for):
    """Rotation: never used beats used long ago beats used recently."""
    if asked_for:
        wanted = asked_for.strip().lower().replace("https://", "").replace("http://", "").strip("/")
        for r in rows:
            if r["domain"].lower() == wanted:
                return r
        row = {"domain": wanted, "last_used": None}
        rows.append(row)
        return row
    return sorted(rows, key=lambda r: (r.get("last_used") or ""))[0]


def _rival_lines(keywords):
    lines = []
    for k in keywords:
        term = k.get("keyword", "")
        if not term:
            continue
        pos, vol = k.get("position"), k.get("volume")
        bits = []
        if pos is not None:
            bits.append("position %s" % pos)
        if vol is not None:
            bits.append("%s/mo" % vol)
        if k.get("url"):
            bits.append(k["url"])
        lines.append("%s (%s)" % (term, ", ".join(bits)) if bits else term)
    return lines


def run(ctx, competitor=None):
    say = sh.reporter(ctx, "suggest_topics")
    rows = _load_competitors()
    if not rows and not competitor:
        # derive from the brand pack rather than asking. Found live 2026-09-04: this tool asked
        # the user to name a competitor on every first run, which is a question the agent can
        # answer itself from what it already knows the company sells.
        rows = _derive_competitors(ctx, say)
    if not rows and not competitor:
        return {"summary": "Could not work out who you compete with.",
                "error": ("No competitor list on file, and the brand pack has no voice profile "
                          "to derive one from, so learn_brand has probably not run. Run setup "
                          "first, or name a competitor domain and I will use that.")}

    mode = sh.dfs_mode(dfs)
    if mode == "off":
        return {"summary": "No competitor keyword data available.",
                "error": ("DataForSEO is not connected, so there are no real ranking keywords "
                          "to spark topics from. Add the login in Connections.")}

    chosen = _pick(rows, competitor)   # a named competitor is honoured even with an empty list
    domain = chosen["domain"]
    say("Studying %s" % domain,
        "Rotating through the competitor list" if not competitor else "You asked for this one")
    if mode == "demo":
        say("Using demo keyword data", "No DataForSEO login, so these numbers are not real")

    try:
        keywords = dfs.ranked_keywords(domain, limit=RIVAL_KEYWORD_LIMIT) or []
    except Exception as e:
        return {"summary": "Could not read %s." % domain,
                "error": "DataForSEO failed on ranked_keywords: %s" % str(e)[:300]}

    if not keywords:
        return {"summary": "%s has no ranking keywords on file." % domain,
                "error": ("DataForSEO returned nothing for %s. The domain may be wrong, or it "
                          "may not rank for anything measurable. Try another competitor." % domain)}

    keywords.sort(key=lambda k: (k.get("position") or 999, -(k.get("volume") or 0)))
    say("Read " + sh.plural(len(keywords), "of their ranking keywords",
                            "of their ranking keywords"),
        "Top page: %s" % (keywords[0].get("url") or keywords[0].get("keyword", "")))

    index = sh.site_index()
    covered = sh.covered_topics(index)
    say("Checked what you already cover",
        sh.plural(len(index.get("pages", [])), "page") + " in your site index" if covered
        else "No site index yet, so overlap is unchecked")

    prompt = sh.fill(
        sh.load_prompt("suggest_topics"),
        company=sh.company()["brand"],
        competitor=domain,
        voice=sh.voice_block(),
        rival_keywords=sh.bullets(_rival_lines(keywords[:RIVAL_SHOWN])),
        own_pages=sh.bullets(covered, empty="(no site index, so assume nothing is covered)"),
    )
    try:
        data = llm.json_call(prompt)
    except Exception as e:
        return {"summary": "Topic ideas failed.",
                "error": "The model did not return usable topics: %s" % str(e)[:300]}

    topics = []
    for i, t in enumerate(data.get("topics") or [], start=1):
        if not isinstance(t, dict) or not t.get("topic"):
            continue
        topics.append({
            "id": t.get("id") or "t%d" % i,
            "topic": t["topic"],
            "sparked_by": t.get("sparked_by", ""),
            "angle": t.get("angle", ""),
            "why_us": t.get("why_us", ""),
            "est_volume": t.get("est_volume"),
            "est_difficulty": t.get("est_difficulty"),
        })
    topics = topics[:WANT_TOPICS]

    if not topics:
        return {"summary": "No usable topics came back.",
                "error": "The model replied but no entry had a topic in it. Worth retrying."}

    # Stamp the rotation only once the run actually used this competitor.
    chosen["last_used"] = store.now()
    store.save_knowledge("competitors.json", {"competitors": rows})

    store.save_artifact(ctx["chat_id"], ctx["run_id"], "topics.json", {
        "competitor": domain,
        "competitor_keywords_read": len(keywords),
        "topics": topics,
        "demo_data": mode == "demo",
        "generated_at": store.now(),
    })
    say("Wrote " + sh.plural(len(topics), "topic"), topics[0]["topic"])
    summary = "%d topics from %s" % (len(topics), domain)
    if mode == "demo":
        summary += " (demo data, no DataForSEO login, so the numbers are not real)"
    return {"summary": summary, "artifact": "topics.json"}
