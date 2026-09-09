"""run_research.py — one topic → the research brief and the evidence cards, the way the content machine did it.

The tool sequences the steps in research/ (one module per step) in the original's order and
nothing else lives here. Every step writes its output under artifacts/_work/<step>.json before the
next reads it, so a crash resumes where it stopped and a paid call is never repeated by accident.

    0b  world          what the topic is and is not about (before a cent is spent)
    1   the brief      seeds → the tight keyword net → the free filter → real numbers + intent →
                       the scorer panel and the judge (the world check) → the live SERP and its snapshot →
                       the winning pages and what they cover → the verdict and the build spec
    1a  cannibalisation  do we already rank top 10 for the primary? a flag, never a block
    1b  the topic gate   is this ours, and what is the real angle (replaces the given one)
    2a  the spine        what the article argues
    2   evidence         cards with verbatim quotes from the pages that rank (the STORM substitute)
    3   gap check        what the brief says matters that the evidence does not cover, and up to
                         three more evidence rounds to fill it
    4   own pages        the company's pages that belong here, found through the page index, plus
                         the reuse verdict
    persona              the one reader this is written for, decided once and reused by the blueprint

Before step 0b there is the credit pre-flight. If the numbers cannot be bought, the run refuses at
the top rather than starting and quietly filling itself with placeholders (see _preflight).

Two rules run through all of it. Nothing invented: every number comes from DataForSEO, every fact
is a card with a quote and a source. Code counts, the model judges: the filters, the substring
checks, the caps and the completeness boxes are all code.
"""
from .. import store
from ..research import _common as _c
from ..research import (assemble, cannibalisation, curate, dossier, evidence, expand, gap_check,
                        keywords, ownpage, persona, render, seeds, serp, spine, topic_gate, winners,
                        world)
from . import _shared as sh
from . import dfs


def _plural(n, word, many=None):
    return sh.plural(n, word, many)


def _cost(*steps):
    return round(sum(float((s or {}).get("cost") or 0.0) for s in steps), 4)


def _compat(research):
    """Older readers of research.json (the first write_article, the library) look for these names.
    Every value is lifted from the fields above it; nothing new is decided here."""
    kw = research.get("keywords") or {}
    pr = kw.get("primary") or {}
    who = (research.get("serp") or {}).get("who_ranks") or []
    research["primary_keyword"] = {"keyword": pr.get("keyword", ""), "volume": pr.get("volume"),
                                   "difficulty": pr.get("kd"), "intent": pr.get("intent")}
    research["secondary_keywords"] = [s.get("keyword") for s in (kw.get("secondary") or []) if s.get("keyword")]
    research["people_also_ask"] = list((research.get("serp") or {}).get("paa") or [])
    research["top_results"] = [{"position": r.get("rank"), "title": r.get("title"), "url": r.get("url"),
                                "description": ""} for r in who]
    research["recommended_angle"] = research.get("angle") or ""
    research["what_they_all_cover"] = list((research.get("winners") or {}).get("common_h2s") or [])
    research["the_gap"] = "; ".join((research.get("winners") or {}).get("gaps_to_own") or [])
    return research


# ---- the credit pre-flight ---------------------------------------------------------------------
# Resolved at import, not inside the guard. Found 2026-09-09: the first version of the same guard
# in front of serp_advanced named a constant that did not exist, so the check threw, was swallowed,
# and the guard failed open without anyone noticing until it was run. A name resolved here breaks
# loudly at import instead, and test_credit_guard asserts it is real.
MIN_CREDITS = _c.MIN_CREDITS

# Every step of this run that costs money, by the name of the _work file it writes. Nothing else
# in run() spends. The evidence pair is either/or: the research conversation ("curate") writes its
# own file, and the plain keyword read ("evidence") only runs when the conversation came back with
# nothing, so a finished run has one of the two and never both.
PAID_STEPS = ("pool", "metrics", "serp", "gap-evidence")
EVIDENCE_STEPS = ("curate", "evidence")


def _paid_work_left(ctx, redo):
    """Is there anything left in this run that has to be bought?

    A resume whose paid steps are all on disk spends nothing, so refusing it would only stand
    between a person and the brief he has already paid for. redo re-runs everything, so it always
    means yes.
    """
    if redo:
        return True
    if any(_c.load_work(ctx, name) is None for name in PAID_STEPS):
        return True
    return all(_c.load_work(ctx, name) is None for name in EVIDENCE_STEPS)


def _read_balance():
    """The DataForSEO balance in dollars, or None when it cannot be read.

    FAILS OPEN, and deliberately in both directions. dfs.balance() already answers None rather
    than raising on a network blip; this wraps it again in case a stub, a future version or a
    changed response shape raises instead, and treats anything that is not a number as unknown.
    None means "unknown, go ahead". The owner's connection drops several times a day, and a blip
    must never be the reason he cannot write. The paid steps report their own failure loudly.
    """
    try:
        bal = dfs.balance()
    except Exception:      # noqa: BLE001 - a broken balance check must never stop a run
        return None
    try:
        return None if bal is None else float(bal)
    except (TypeError, ValueError):
        return None


def _preflight(ctx, redo, placeholder_numbers, say):
    """Refuse at the top when the numbers cannot be bought. Returns (refusal, demo, note).

    refusal is what run() returns when the run must not start, in the shape learn_brand uses when
    there is no measured traffic: a summary, and an error that names what is missing and both ways
    out. demo says every number in this run is a placeholder. note is the line that goes into
    research.json so the file says so too.

    Why it sits at the very top, 2026-09-09. The balance was minus seven cents. The free keyword
    steps ran, the paid calls quietly swapped in demo data (dfs.serp_advanced falls back rather
    than firing calls that would only be refused), and the run carried on for another twenty
    minutes to produce an article built on estimates. The owner: "why should it even go further if
    there is no DataForSEO? It never misfires. It is pointless, a very bad experience."

    Two rules hold here. The balance is read ONCE per run, never per step, because reading it is
    itself an API call. And the check fails OPEN: an unreadable balance proceeds.

    Refusing is the default, not the only answer. A person may want the shape of an article without
    paying for it, so placeholder_numbers=True runs it on demo figures, every one of them flagged.
    That has to be asked for; it is never what happens on its own.
    """
    if dfs.demo_mode():
        say("Using demo search data", "No DataForSEO login, so none of these numbers are real")
        return None, True, "demo data: no DataForSEO login, so no number here is real"
    if not _paid_work_left(ctx, redo):
        return None, False, ""
    bal = _read_balance()
    if bal is None:
        say("Could not read the DataForSEO balance",
            "Going ahead. A paid step says so itself if it cannot pay")
        return None, False, ""
    if bal >= MIN_CREDITS:
        say("Checked the DataForSEO balance", "%.2f dollars available" % bal)
        return None, False, ""
    if placeholder_numbers:
        say("Running on placeholder numbers because you asked for it",
            "The balance is $%.2f, so nothing in this brief is measured" % bal)
        return None, True, ("demo data: you asked for the run with the balance at $%.2f, so no "
                            "number here is real" % bal)
    say("Not enough DataForSEO balance to start", "The balance is $%.2f and a run needs $%.2f"
        % (bal, MIN_CREDITS))
    return ({"summary": "The research did not start: there is not enough DataForSEO balance to "
                        "buy the numbers ($%.2f on the account)." % bal,
             "error": ("Every number in a research brief is bought from DataForSEO: the search "
                       "volumes, the difficulty, the live search results and the pages that win. "
                       "The balance is $%.2f and a run needs at least $%.2f, so not one figure in "
                       "this brief would be measured, and twenty minutes of writing on estimates "
                       "is worse than no writing at all. Top up the DataForSEO account and ask me "
                       "again, or tell me you want it anyway and I will run it on placeholder "
                       "numbers with every one of them marked as not real (call run_research again "
                       "with placeholder_numbers set to true). I will not guess at this."
                       % (bal, MIN_CREDITS))}, False, "")


def run(ctx, topic, angle="", redo=False, placeholder_numbers=False, **_ignored):
    topic = (topic or "").strip()
    angle = (angle or "").strip()
    if not topic:
        return {"summary": "No topic given.", "error": "run_research needs a topic."}
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "run_research")
    company = sh.company()
    notes = []

    # ---- the credit pre-flight, before a single step starts ------------------------------------
    refusal, demo, demo_note = _preflight(ctx, redo, bool(placeholder_numbers), say)
    if refusal:
        return refusal
    if demo_note:
        notes.append(demo_note)

    def step(name, produce):
        out, reused = _c.cached(ctx, name, redo, produce)
        return out, reused

    # ---- 0b. the world statement -----------------------------------------------------------
    w, reused = step("world", lambda: world.run(topic, company))
    say("Drew the line around the subject" + (" (kept from last time)" if reused else ""),
        "Not about: " + w["not_about"][:150])

    # ---- 1. the brief: seeds → net → filter → numbers → judge -----------------------------------
    sd, _ = step("seeds", lambda: seeds.run(topic, angle, w, company))
    say("Chose %s to search from" % _plural(len(sd["seeds"]), "seed"), ", ".join(sd["seeds"][:6]))

    pool, reused = step("pool", lambda: expand.expand(sd["seeds"], company, say=say))
    say("Keyword pool: %s" % _plural(len(pool["pool"]), "phrase") + (" (kept from last time)" if reused else ""),
        "Phrases that contain one of the seeds, from DataForSEO")
    short, _ = step("shortlist", lambda: {"rows": expand.filter_pool(pool["pool"])})
    say("Kept %s worth measuring" % _plural(len(short["rows"]), "phrase"),
        "At least %d searches a month and difficulty %d or under" % (_c.VOL_FLOOR, _c.KD_CEIL))

    met, _ = step("metrics", lambda: keywords.metrics(short["rows"], company))
    say("Measured %s" % _plural(len(met["rows"]), "keyword"), "Real volume, difficulty and intent for each")

    try:
        judged, reused = step("keywords", lambda: keywords.score_and_judge(
            met["rows"], topic, angle, w, sd.get("hygiene", ""), company, say=say))
    except keywords.NoKeywordDemand as e:
        say("No keyword demand", str(e))
        store.save_artifact(chat_id, run_id, "research.json", _compat({
            "topic": topic, "angle": angle, "world": w, "keywords": {}, "serp": {}, "winners": {},
            "verdict": [], "build_spec": {}, "cannibalisation": None, "persona": None,
            "cost_usd": _cost(pool, met), "outcome": "no keyword demand", "why": str(e),
            "demo_data": demo, "generated_at": store.now()}))
        return {"summary": "Nobody searches for this in a way we can measure, so there is nothing to research.",
                "error": "no keyword demand", "artifact": "research.json"}
    except keywords.NoScores as e:
        return {"summary": "The keyword scoring produced nothing to choose from.",
                "error": "Could not pick a primary keyword: %s" % str(e)[:300]}
    final = judged["final"]
    primary = final["primary"]
    say("Primary keyword: %s" % primary["keyword"],
        "%s searches a month, difficulty %s%s" % (primary.get("volume"), primary.get("kd"),
                                                  "; shared with another field" if primary.get("split_world") else ""))

    # ---- 4. the live SERP + the snapshot ---------------------------------------------------------
    sp, _ = step("serp", lambda: serp.fetch(primary["keyword"], company))
    extract = sp["extract"]
    snap, _ = step("snapshot", lambda: serp.snapshot(extract, topic, angle, w, primary["keyword"], company))
    say("Read the first page of Google",
        "%s, %s, AI Overview %s" % (_plural(len(extract.get("top_organic") or []), "result"),
                                    _plural(len(extract.get("paa") or []), "People Also Ask question"),
                                    "present" if extract.get("ai_overview") else "absent"))

    # ---- 5. the winning pages and what they cover -----------------------------------------------
    pages, _ = step("pages", lambda: winners.read_pages(snap["readlist"], demo=demo, say=say))
    win, _ = step("winners", lambda: (lambda md: dict(winners.extract(md), md=md))(
        winners.write_up(pages, angle, primary["keyword"], company)))
    say("Studied the pages that win",
        "%s common headings, %s we can own" % (len(win.get("common_h2s") or []), _plural(len(win.get("gaps_to_own") or []), "gap")))

    # ---- 1a. cannibalisation (never blocks) ------------------------------------------------------
    cann, _ = step("cannibalisation", lambda: {"hit": cannibalisation.check(primary["keyword"])})
    if cann.get("hit"):
        say("You already rank #%s for this keyword" % cann["hit"]["rank"],
            "%s. Building anyway; the new article has to beat that page" % cann["hit"]["url"])

    # ---- 1b. the topic gate --------------------------------------------------------------------
    gate, _ = step("topic-gate", lambda: topic_gate.run(topic, angle, snap, win, company))
    if not gate.get("relevant"):
        say("Not our topic", gate.get("why") or "no reason given")
        store.save_artifact(chat_id, run_id, "research.json", _compat({
            "topic": topic, "angle": angle, "angle_before": angle, "world": w,
            "keywords": final, "serp": _serp_block(extract, snap), "winners": _win_block(win),
            "verdict": [], "build_spec": {}, "cannibalisation": cann.get("hit"),
            "persona": None, "topic_gate": gate, "cost_usd": _cost(pool, met, sp),
            "outcome": "not our topic", "demo_data": demo, "generated_at": store.now()}))
        return {"summary": "This topic is not ours to write: %s" % (gate.get("why") or "no reason given"),
                "error": "not our topic: %s" % (gate.get("why") or "no reason given"), "artifact": "research.json"}
    angle_before = angle
    if gate.get("angle"):
        angle = gate["angle"]
    say("Ours to write" if gate.get("why") else "Topic passed the gate",
        (gate.get("why") or "")[:160])
    if gate.get("angle_changed"):
        say("Angle rewritten from the real search results", angle[:200])

    # ---- 7. the verdict and the build spec (after the gate, so the angle it anchors on is the
    # settled one; found live 2026-09-04: with no angle given, the brief said "Anchors missing"
    # a moment before the gate wrote the angle) ------------------------------------------------
    brief, _ = step("brief", lambda: assemble.run(topic, angle, final, snap["md"], win["md"], company))
    if brief.get("incomplete"):
        say("The brief is missing pieces", ", ".join(brief["incomplete"]))
    else:
        say("Brief assembled", "Verdict and build spec written; every box checked")

    # ---- 2a. the spine ---------------------------------------------------------------------------
    spn, _ = step("spine", lambda: {"spine": spine.run(topic, angle, w, win, company)})
    say("The spine", spn["spine"][:200])

    # ---- the persona, decided once ------------------------------------------------------------
    per, _ = step("persona", lambda: persona.run(topic, angle, company))
    say("Reader: %s" % (per.get("name") or "a practitioner"), (per.get("lens") or "")[:160])

    # ---- 2. the research conversation, then the dossier, then the cards -------------------------
    # A research TEAM, not a keyword lookup: four mixed personas interview an expert, each question
    # grounded in what the last answer said. The dossier is written from what they retrieved, and
    # the cards are lifted out of the dossier, which is what lets one card cite two sources.
    spine_ctx = {"spine": spn["spine"], "about": w["about"], "not_about": w["not_about"]}
    cur, reused_cur = step("curate", lambda: curate.run(
        topic, angle, spine_ctx, company, own_domain=company.get("domain") or "", say=say))
    article_brief = curate._article_block(topic, angle, spine_ctx)
    dos = har = None
    if cur.get("turns"):
        dos, _ = step("dossier", lambda: dossier.build(cur, article_brief, say=say))
        har, _ = step("dossier-cards", lambda: dossier.harvest(dos, say=say))
    if har and har.get("cards"):
        ev = {"cards": har["cards"], "pages": cur["pages"], "cost": cur.get("cost") or 0.0,
              "skipped": [], "dropped_verbatims": har.get("dropped_verbatims") or 0,
              "team": cur.get("team") or [], "turns": cur["turns"], "queries": cur.get("queries") or [],
              "dossier_words": dos.get("words") or 0, "sources": dos.get("sources") or []}
        reused = reused_cur
        say("Evidence: %s from %s"
            % (_plural(len(ev["cards"]), "card"), _plural(len(ev["pages"]), "page"))
            + (" (kept from last time)" if reused else ""),
            "%d questions asked across %d searches; every card is a quote checked against the dossier"
            % (len(cur["turns"]), len(cur.get("queries") or []))
            + ("; %d quotes did not match and were thrown out" % ev["dropped_verbatims"]
               if ev["dropped_verbatims"] else ""))
        store.save_artifact(chat_id, run_id, "dossier.md",
                            (dos.get("md") or "") + "\n\n## Sources\n\n"
                            + dossier.sources_block(dos.get("sources") or []))
        notes.append("evidence gathered the way the original does: %d researchers interviewing an "
                     "expert over %d questions, then a written dossier, then cards lifted from it"
                     % (len(ev["team"]), len(cur["turns"])))
    else:
        # no team came back, or nothing was retrievable: fall back to the plain keyword read rather
        # than shipping a run with no evidence at all, and say which route was taken
        ev_keywords = [primary["keyword"]] + [s["keyword"] for s in final.get("secondary") or []][:_c.EVIDENCE_MAX_SECONDARY]
        ev, reused = step("evidence", lambda: evidence.gather(
            ev_keywords, company, own_domain=company.get("domain") or "", demo=demo, say=say))
        why = (cur.get("skipped") or ("the interviews retrieved nothing usable"
                                      if cur.get("turns") else "no interviews ran"))
        say("Evidence: %s from %s" % (_plural(len(ev["cards"]), "card"), _plural(len(ev["pages"]), "page")),
            "The research team produced no cards (%s), so this is the plain keyword read" % why)
        notes.append("the research conversation produced no cards (%s); evidence is the narrower "
                     "keyword read" % why)

    # ---- 3. gap check ----------------------------------------------------------------------------
    meta = {"title": topic, "angle": angle, "spine": spn["spine"], "about": w["about"], "not_about": w["not_about"]}

    def _gap():
        items = gap_check.checklist(win, (extract.get("ai_overview") or {}).get("text") if extract.get("ai_overview") else "")
        verdicts = gap_check.judge(items, meta, _numbered(ev["cards"]), say=say)
        queries = gap_check.triage(verdicts, meta, _numbered(ev["cards"]))
        return {"items": verdicts, "queries": queries}
    gap, _ = step("gap-check", _gap)
    misses = [v for v in gap["items"] if v["verdict"] in _c.MISS_VERDICTS]
    say("Checked the evidence against what matters",
        "%s of %s covered; %s to fill" % (len(gap["items"]) - len(misses), _plural(len(gap["items"]), "item"),
                                          _plural(len(gap["queries"]), "question")))
    fill, _ = step("gap-evidence", lambda: _fill(gap["queries"], company, ev, demo, say))
    if gap["queries"]:
        say("Filled the gaps with %s" % _plural(len(fill["cards"]), "more card"),
            "; ".join(q["query"][:60] for q in gap["queries"]))

    # ---- 4. own pages through the page index ----------------------------------------------------
    own, _ = step("ownpage", lambda: ownpage.run(topic, angle, company, say=say))
    if own.get("note"):
        notes.append(own["note"])

    # ---- cards.json: evidence first, then own pages, continuous ids -------------------------------
    cards = []
    for c in ev["cards"] + fill["cards"] + own["cards"]:
        c = dict(c)
        c.setdefault("protected", None)
        c.setdefault("relevance", None)
        cards.append(c)
    for i, c in enumerate(cards, 1):
        c["id"] = i
    store.save_artifact(chat_id, run_id, "cards.json", cards)

    research = {
        "topic": topic, "angle": angle, "angle_before": angle_before,
        "world": w, "spine": spn["spine"],
        "keywords": {"primary": primary, "variations": final.get("variations") or [],
                     "secondary": final.get("secondary") or [], "in_body": final.get("in_body") or [],
                     "spokes": (final.get("spoke_candidates") or [])[:_c.MAX_SPOKES], "notes": final.get("notes", "")},
        "serp": _serp_block(extract, snap),
        "winners": _win_block(win),
        "verdict": brief["verdict"], "build_spec": brief["build_spec"], "completeness": brief["completeness"],
        "cannibalisation": cann.get("hit"),
        "topic_gate": {"relevant": True, "why": gate.get("why", ""), "angle_changed": bool(gate.get("angle_changed")),
                       "why_changed": gate.get("why_changed", "")},
        "persona": per,
        "evidence": {"pages": ev["pages"], "skipped": ev.get("skipped") or [], "cards": len(ev["cards"]),
                     "dropped_verbatims": ev.get("dropped_verbatims", 0),
                     # the research conversation, so the brief can show what was actually asked
                     "team": ev.get("team") or [], "questions": len(ev.get("turns") or []),
                     "searches": len(ev.get("queries") or []),
                     "turns": [{"persona": t.get("persona", ""), "question": t.get("question", ""),
                                "queries": t.get("queries") or [], "sources": len(t.get("urls") or []),
                                "answer": (t.get("answer") or "")[:1200]}
                               for t in (ev.get("turns") or [])],
                     "dossier_words": ev.get("dossier_words") or 0,
                     "dossier_sources": ev.get("sources") or []},
        "gap_check": {"items": [{k: v[k] for k in ("id", "type", "item", "verdict", "why") if k in v} for v in gap["items"]],
                      "queries": gap["queries"], "filled": fill.get("pages") or []},
        "reuse": own.get("reuse"),
        "own_pages": own.get("pages") or [],
        "cost_usd": _cost(pool, met, sp, ev, fill),
        "notes": notes, "demo_data": demo, "generated_at": store.now(),
    }
    store.save_artifact(chat_id, run_id, "research.json", _compat(research))

    # The two documents a person reads, plus the trail behind them. Pure assembly: nothing here
    # decides anything, it lays out what the steps already wrote.
    rows = render.trail(chat_id, run_id, store)
    store.save_artifact(chat_id, run_id, "research-doc.md",
                        render.research_doc(research, brief.get("keywords_md") or "",
                                            snap.get("md") or "", win.get("md") or "", rows))
    store.save_artifact(chat_id, run_id, "bundle.md",
                        render.bundle(research, rows, store.list_knowledge("brand") or []))
    say("Research brief saved",
        "%s, %s; %s of working files kept, each one openable"
        % (_plural(len(cards), "card"), "%.2f dollars spent" % research["cost_usd"], len(rows)))

    summary = "Primary '%s' (%s/mo, KD %s). %s: %s evidence, %s own pages. Angle: %s" % (
        primary["keyword"], primary.get("volume"), primary.get("kd"), _plural(len(cards), "card"),
        len(ev["cards"]) + len(fill["cards"]), len(own["cards"]), angle[:140])
    if cann.get("hit"):
        summary += ". You already rank #%s for it via %s" % (cann["hit"]["rank"], cann["hit"]["url"])
    if demo:
        # Two ways a run ends up on demo figures (no login, or a balance too low and you asked for
        # it anyway). The pre-flight decided which, once; this only says it.
        summary += " (%s)" % demo_note.replace("demo data: ", "demo data, ", 1)
    if own.get("note"):
        summary += ". " + own["note"].capitalize()
    return {"summary": summary, "artifact": "research.json", "cost_usd": research["cost_usd"]}


def _numbered(cards):
    out = []
    for i, c in enumerate(cards, 1):
        d = dict(c)
        d["id"] = i
        out.append(d)
    return out


def _fill(queries, company, ev, demo, say):
    """One more evidence round per gap question, skipping pages the first round already read."""
    if not queries:
        return {"cards": [], "pages": [], "cost": 0.0}
    seen = [p["url"] for p in ev.get("pages") or []]
    out = {"cards": [], "pages": [], "cost": 0.0}
    for q in queries:
        got = evidence.gather([q["query"]], company, own_domain=company.get("domain") or "", exclude=seen,
                              max_pages=_c.EVIDENCE_SERP_DEPTH, demo=demo, say=say)
        for c in got["cards"]:
            c["origin"] = "gap/" + c.get("origin", "")
        out["cards"] += got["cards"]
        out["pages"] += [dict(p, query=q["query"]) for p in got["pages"]]
        out["cost"] += got.get("cost") or 0.0
        seen += [p["url"] for p in got["pages"]]
    out["cost"] = round(out["cost"], 6)
    return out


def _serp_block(extract, snap):
    return {"who_ranks": [{"rank": r.get("rank"), "domain": r.get("domain"), "title": r.get("title"), "url": r.get("url")}
                          for r in (extract.get("top_organic") or [])],
            "who_ranks_text": snap.get("who_ranks_text", ""), "open_gap": snap.get("open_gap", ""),
            "featured_snippet": extract.get("featured_snippet"),
            "ai_overview": extract.get("ai_overview"),
            "paa": list(extract.get("paa") or []),
            "paa_on": snap.get("paa_on") or [], "paa_off": snap.get("paa_off") or [],
            "related_on": snap.get("related_on") or [], "related_off": snap.get("related_off") or [],
            "read_list": snap.get("readlist") or [], "features": extract.get("features") or {},
            "snapshot_md": snap.get("md", "")}


def _win_block(win):
    return {"format": win.get("format", ""), "common_h2s": win.get("common_h2s") or [],
            "drift": win.get("drift") or [], "gaps_to_own": win.get("gaps_to_own") or [],
            "md": win.get("md", "")}
