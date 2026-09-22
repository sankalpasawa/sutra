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

Between the brief and the research conversation the run STOPS ONCE and asks the person how long
the article should be. That is the only stop of its kind in a run, and it sits there because the
band exists by then and the four researchers have not started: they are the longest and most
expensive part of a run, so this is the last cheap moment to ask. Answering it starts them.

Before step 0b there is the credit pre-flight. If the numbers cannot be bought, the run refuses at
the top rather than starting and quietly filling itself with placeholders (see _preflight).

Two rules run through all of it. Nothing invented: every number comes from DataForSEO, every fact
is a card with a quote and a source. Code counts, the model judges: the filters, the substring
checks, the caps and the completeness boxes are all code.
"""
from .. import store
from ..prompts import store as pstore
from ..research import _common as _c
from ..research import (assemble, cannibalisation, curate, dossier, evidence, expand, gap_check,
                        keywords, ownpage, persona, render, seeds, serp, spine, topic_gate, winners,
                        world)
from ..write import _common as write_common
from . import _shared as sh
from . import dfs


def _plural(n, word, many=None):
    return sh.plural(n, word, many)


def _cost(*steps):
    return round(sum(float((s or {}).get("cost") or 0.0) for s in steps), 4)


def _format_pick(text):
    """A person's format_choice, as either the archetype slug or one of its 8 plain names ("Listicle"),
    normalised to the slug. None when it names neither."""
    s = str(text or "").strip()
    if s in write_common.ARCHETYPES:
        return s
    low = s.lower()
    for a in write_common.ARCHETYPES:
        if pstore.format_title(a).lower() == low:
            return a
    return None


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


# ---- the one length question --------------------------------------------------------------------
# The whole record of the question and its answer for this run: _work/ask-words.json. It holds what
# was asked, what was measured, what the person said, AND the run's own inputs.
#
# THE INPUTS MATTER. loop._resume_words re-enters this tool with `{"word_target": N}` and nothing
# else, so on the way back there is no topic, no angle and no placeholder flag in the call. Without
# them recorded here the resumed run would refuse itself with "No topic given" and the person would
# watch twenty minutes of research vanish because they answered a question. Written BEFORE the tool
# returns the question, never after.
ASK_FILE = "ask-words"


def _ask_block(keyword, band, suggested):
    """The two lines a person reads, in their words, with the numbers in them.

    No band means nothing could be measured (no login, a refused SERP, a model reply with no band
    in it). Say that plainly rather than dressing a default up as a measurement.
    """
    lo, hi = (band or {}).get("min"), (band or {}).get("max")
    n = "{:,}".format(suggested)
    if lo and hi and lo != hi:
        question = ('The pages ranking for "%s" run %s to %s words. The average is %s.'
                    % (keyword, "{:,}".format(lo), "{:,}".format(hi), n))
    elif lo or hi:
        question = ('The pages ranking for "%s" run about %s words.'
                    % (keyword, "{:,}".format(lo or hi)))
    else:
        question = ('I could not measure how long the pages ranking for "%s" run, so %s words is a '
                    "starting point, not a measurement." % (keyword, n))
    why = ("I will write to %s words, and the research team will take about fifteen minutes. "
           "Type a different number if you want a different length." % n)
    return question, why


def _record_question(ctx, topic, angle_given, placeholder_numbers, demo, demo_note, keyword, volume,
                     band, suggested, arch, arch_why, topic_on, topic_why):
    """File the question, and the run's inputs with it, then hand loop.py what to put on screen.

    This is the run's one checkpoint (2026-09-16): the length question, the format the winning
    pages imply (with a one-line reason and the 8 plain names to pick a different one from), and
    the on/off-topic verdict, all in one stop. The question/why text still asks only about length —
    it is the one thing this run cannot go ahead without — the rest is shown for the person to read
    and, for the format, to override.
    """
    _c.save_work(ctx, ASK_FILE, {
        "asked_at": store.now(),
        "topic": topic, "angle": angle_given, "placeholder_numbers": bool(placeholder_numbers),
        "demo": bool(demo), "demo_note": demo_note,
        "keyword": keyword, "volume": volume, "band_measured": band or None, "suggested": suggested,
        "format": arch, "format_why": arch_why,
        "topic_on": bool(topic_on), "topic_why": topic_why,
        "answer": None, "answered_at": None, "answer_source": None,
    })
    question, why = _ask_block(keyword, band, suggested)
    return {"question": question, "why": why, "suggested": suggested, "band": band or {},
            "format": arch, "format_label": pstore.format_title(arch), "format_why": arch_why,
            "format_options": [pstore.format_title(a) for a in sorted(write_common.ARCHETYPES)],
            "topic": {"state": "on" if topic_on else "off", "why": topic_why or ""}}


def _record_answer(ctx, asked, words, source):
    """File the answer next to the question. The file, not the run state, is what a later call reads,
    so the number survives a restart of the app between the question and the rest of the research."""
    row = dict(asked or {})
    row["answer"] = words
    row["answered_at"] = store.now()
    row["answer_source"] = source
    _c.save_work(ctx, ASK_FILE, row)
    return row


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

# The research conversation, kept turn by turn while it runs (2026-09-15). "curate" is only written
# when the whole round finishes, so a round that died part way used to take every search it had
# bought with it, and the retry paid for all of them again. This file holds the round so far, with
# the topic and angle it belongs to, and curate.run picks up from it.
CURATE_PARTIAL = "curate-partial"


def _curate(ctx, fresh, topic, angle, spine_ctx, company, say):
    """curate.run, resumable. fresh=True throws any saved round away first (a redo, or the thin
    dossier's second attempt, which must not be the first attempt replayed)."""
    key = {"topic": topic, "angle": angle}
    if fresh:
        _c.save_work(ctx, CURATE_PARTIAL, {})
    saved = _c.load_work(ctx, CURATE_PARTIAL) or {}
    if (saved.get("topic"), saved.get("angle")) != (topic, angle):
        saved = {}
    return curate.run(topic, angle, spine_ctx, company, own_domain=company.get("domain") or "",
                      say=say, resume=saved or None,
                      keep=lambda state: _c.save_work(ctx, CURATE_PARTIAL, dict(state, **key)))


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

    NO LOGIN REFUSES TOO (2026-09-17), for the same reason as an empty balance and the same owner's
    words: a run with no DataForSEO login connected used to run anyway, said so once in passing,
    researched on placeholder numbers, and usually failed the thin-material guard a few steps later
    with no further mention of DataForSEO -- so the real cause was never named again. placeholder_
    numbers=True is still the explicit way to run on demo figures with no login, exactly as it is
    for a low balance.
    """
    if dfs.demo_mode():
        # NO LOGIN REFUSES TOO, UNLESS ASKED FOR (2026-09-17). Found live: a run said "no
        # DataForSEO login" once, researched three times over 26 minutes on placeholder numbers,
        # failed the thin-material guard each time with no further mention of DataForSEO, then sat
        # waiting 17 hours. The owner's own words above already covered this ("why should it even
        # go further if there is no DataForSEO?"); only the empty-balance branch below ever acted
        # on them. dfs.available() and not dfs.demo_mode()'s own DEMO_MODE flag, so a forced demo
        # with real credentials present (tests) still runs, as it always has.
        if not dfs.available() and not placeholder_numbers:
            say("Not enough DataForSEO to start", "No DataForSEO login is connected")
            return ({"summary": "Research did not start: no DataForSEO login is connected.",
                     "error": ("No DataForSEO login is connected, so none of these numbers would "
                               "be real. Say that in one line, then ask: connect DataForSEO in "
                               "Connections, or go ahead on placeholder numbers marked as not real "
                               "(call run_research again with placeholder_numbers set to true).")},
                    False, "")
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
    # ONE LINE, NOT A LECTURE (owner, 2026-09-11: "it could simply have been 'not enough
    # DataForSEO credits'"). This used to hand the agent a 70-word explanation of what DataForSEO
    # buys and why estimates are worse than nothing, and the agent read it back to the person,
    # paragraph and all. It now carries only what the agent needs: the fact, and the two ways on.
    return ({"summary": "Research did not start: not enough DataForSEO credits ($%.2f)." % bal,
             "error": ("Not enough DataForSEO credits: the balance is $%.2f and research needs "
                       "$%.2f. Say that in one line, then ask: top up, or go ahead on placeholder "
                       "numbers marked as not real (call run_research again with "
                       "placeholder_numbers set to true)." % (bal, MIN_CREDITS))}, False, "")


def run(ctx, topic="", angle="", redo=False, placeholder_numbers=False, word_target=None,
       format_choice=None, **_ignored):
    """One topic, researched. Called twice per article: once by the model with the topic, and once
    by loop._resume_words with the checkpoint's answer and nothing else.

    word_target is a word count in the person's own words: given upfront (the model may read one
    off the person's first message and pass it here, see registry.py) it is prefilled and never
    asked about again; given on the way back from the checkpoint, it is their answer to the one
    length question. Either way it is the person's number, never the model's to invent.

    format_choice is the person overriding the checkpoint's routed format with one of the 8 plain
    names or archetype slugs; None (the ordinary case) keeps the router's pick.
    """
    topic = (topic or "").strip()
    angle = (angle or "").strip()
    asked = _c.load_work(ctx, ASK_FILE) or {}
    words_chosen = assemble.as_words(word_target)

    # The way back in from the length question: the call carries a number and nothing else, so the
    # topic, the angle as the person first gave it, and the placeholder flag all come off the file
    # that was written before the question went out.
    resuming = bool(asked.get("asked_at")) and words_chosen is not None
    if not topic:
        topic = str(asked.get("topic") or "").strip()
        angle = angle or str(asked.get("angle") or "").strip()
        if asked.get("placeholder_numbers"):
            placeholder_numbers = True
    if not topic:
        return {"summary": "No topic given.", "error": "run_research needs a topic."}
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "run_research")

    # THE SHEET'S OWN ANGLE, when this run started from an idea. `idea_id` is on the run's state
    # before the model reads anything: the chip on the Asset ideas tab puts it there, and so does
    # accepting the agent's offer in the chat. It is pure provenance, never a match by meaning.
    # The asset engine already judged this idea's angle against what the company can own and what
    # anyone would cite. Re-deriving one from scratch pays for that work twice and throws the
    # first answer away. An angle the caller gave still wins: the person outranks the sheet.
    idea_id = str((store.get_state(chat_id, run_id) or {}).get("idea_id") or "").strip()
    if idea_id and not angle:
        try:
            from ..assets import _common as acm
            row = acm.by_id(idea_id) or {}
        except Exception:   # noqa: BLE001 — a sheet we cannot read must never stop the research
            row = {}
        if str(row.get("angle") or "").strip():
            angle = str(row["angle"]).strip()
            say("Using the angle the sheet already worked out", "%s: %s" % (idea_id, angle[:160]))
    company = sh.company()
    notes = []

    # ---- A NEW TOPIC STARTS FRESH ------------------------------------------------------------------
    # Every step below saves its result under this run and reuses it on the next call. That is right
    # for the way back in from the length question (same topic, the paid work is already done), and it
    # was wrong for everything else. On 2026-09-15 a person was told "white collar vs blue collar" was
    # not ours, said "keep the topic, aim it at hiring teams", and the agent called this again with a
    # new title and angle in the SAME run. Every step -- world, seeds, keywords, the SERP, the pages,
    # the topic gate -- came back from the first call's files in under a second, so the new angle was
    # never researched, and the agent reported the replayed verdict as if Google had been re-read.
    # So the topic and angle a run was researched for are recorded, and a call that asks about a
    # different one redoes every step.
    if not resuming:
        before = _c.load_work(ctx, "input") or {}
        if before and (str(before.get("topic") or ""), str(before.get("angle") or "")) != (topic, angle):
            redo = True
            say("New topic, so the research starts fresh",
                "Was: %s. Now: %s" % (str(before.get("topic") or "")[:80], topic[:80]))
        _c.save_work(ctx, "input", {"topic": topic, "angle": angle})

    # ---- the credit pre-flight, before a single step starts ------------------------------------
    # Skipped on the way back from the length question. Reading the balance is itself a DataForSEO
    # call, the rule in _preflight is that it is read ONCE per run, and the run that asked the
    # question already read it a moment ago. Its verdict is on the ask file, so it is reused.
    if resuming:
        demo, demo_note = bool(asked.get("demo")), str(asked.get("demo_note") or "")
    else:
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
    # THE PAA GOES IN WITH THE PAGES (2026-09-22). A gap has to name a reader who wants it, and
    # this is the only place in the whole run where real readers say what they want in their own
    # words. Both lists, on-angle and off: what people ask is not ours to pre-filter before
    # working out what they want.
    _asked = list(snap.get("paa_on") or []) + list(snap.get("paa_off") or [])
    win, _ = step("winners", lambda: (lambda md: dict(winners.extract(md), md=md))(
        winners.write_up(pages, angle, primary["keyword"], company, paa=_asked)))
    say("Studied the pages that win",
        "%s common headings, %s we can own" % (len(win.get("common_h2s") or []), _plural(len(win.get("gaps_to_own") or []), "gap")))

    # ---- 1a. cannibalisation (never blocks) ------------------------------------------------------
    cann, _ = step("cannibalisation", lambda: {"hit": cannibalisation.check(primary["keyword"])})
    if cann.get("hit"):
        say("You already rank #%s for this keyword" % cann["hit"]["rank"],
            "%s. Building anyway; the new article has to beat that page" % cann["hit"]["url"])

    # ---- 1b. the topic gate — NEVER BLOCKS (2026-09-16). It used to stop the run and refuse to
    # write; now it only warns. One line in the chat, the verdict travels in decisions.json and
    # reaches the Library row, and the run carries on exactly as it would for an on-topic article:
    # no change of angle, no special handling. --------------------------------------------------
    gate, _ = step("topic-gate", lambda: topic_gate.run(topic, angle, snap, win, company, primary=primary["keyword"]))
    angle_before = angle
    if gate.get("relevant"):
        if gate.get("angle"):
            angle = gate["angle"]
        say("Ours to write" if gate.get("why") else "Topic passed the gate",
            (gate.get("why") or "")[:160])
        if gate.get("angle_changed"):
            say("Angle rewritten from the real search results", angle[:200])
    else:
        say("Off topic, writing it anyway", gate.get("why") or "no reason given")
        notes.append("the topic gate judged this off the brand's scope (%s); the article was "
                     "written anyway, and the verdict is on the decisions file and the Library row"
                     % (gate.get("why") or "no reason given"))

    # ---- THE FORMAT PICK, decided once, right after the winners study and the topic gate --------
    # Moved here from the write phase's own "route" step (write/fmt_router.py, deleted 2026-09-16):
    # one AI call, made once, and never re-made while writing. On a resumed run the earlier answer
    # (filed on the ask-words row below) is reused rather than asking the model again.
    if asked.get("format") in write_common.ARCHETYPES:
        arch, arch_why = asked["format"], asked.get("format_why", "")
    else:
        arch, arch_why = winners.route_format(win.get("format", ""), topic, angle, win.get("md", ""))
    say("Format: %s" % pstore.format_title(arch), arch_why or "decided from the pages that win")

    # ---- 7. the verdict and the build spec (after the gate, so the angle it anchors on is the
    # settled one; found live 2026-09-04: with no angle given, the brief said "Anchors missing"
    # a moment before the gate wrote the angle) ------------------------------------------------
    brief, _ = step("brief", lambda: assemble.run(topic, angle, final, snap["md"], win["md"], company))
    if brief.get("incomplete"):
        say("The brief is missing pieces", ", ".join(brief["incomplete"]))
    else:
        say("Brief assembled", "Verdict and build spec written; every box checked")

    # ---- THE ONE LENGTH QUESTION ----------------------------------------------------------------
    # Here, and nowhere else. The band exists (the brief above measured it) and the research
    # conversation has not started, so this is the last moment the run is still cheap.
    #
    # The bug it ends, 2026-09-09: length used to be decided TWICE by two steps that never spoke.
    # The architect budgeted from this band, and then readable re-decided it from a hardcoded 2,100
    # that had never seen the band. Competitors at 3,200 words and competitors at 1,400 both came
    # out as an article cut to 2,100. That is the over-concision the owner had been feeling for
    # weeks and worked out himself. From here on there is one number, a person chose it, and every
    # step downstream reads it off build_spec.word_band.
    measured_band = (brief.get("build_spec") or {}).get("word_band") or {}
    suggested = assemble.suggested_words(brief.get("build_spec"))
    if words_chosen is None:
        words_chosen = assemble.as_words(asked.get("answer"))
    if words_chosen is None and asked.get("asked_at"):
        # Asked once already and still no number: take the suggestion and say so. Asking again
        # would break "one question per article", and re-asking on every re-entry is a loop that
        # never ends, because the thing that would end it is the answer we did not get.
        words_chosen = suggested
        asked = _record_answer(ctx, asked, words_chosen, "the suggestion; the question was put once "
                                                         "and came back without a number")
        notes.append("the length question was put once and came back without a number, so the "
                     "article is written to the measured average of %s words" % "{:,}".format(words_chosen))
    if words_chosen is None:
        ask = _record_question(ctx, topic, angle_before, placeholder_numbers, demo, demo_note,
                               primary["keyword"], primary.get("volume"), measured_band, suggested,
                               arch, arch_why, gate.get("relevant", True), gate.get("why", ""))
        say("Asking how long the article should be, and confirming the format",
            "The pages that rank run %s; suggesting %s words"
            % (("%s to %s" % ("{:,}".format(measured_band["min"]), "{:,}".format(measured_band["max"])))
               if measured_band.get("min") and measured_band.get("max") else "an unmeasured length",
               "{:,}".format(suggested)))
        return {"summary": "Waiting on one answer: how long this article should be, and whether the "
                           "format is right.",
                "ask_words": ask}
    if not asked.get("asked_at"):
        # The number arrived with the call and no question was ever put (a scripted run, a rerun
        # that already knows the answer). Record the same row anyway, with asked_at left null, so
        # the file always says which of the two happened.
        asked = dict(asked, topic=topic, angle=angle_before, asked_at=None,
                     placeholder_numbers=bool(placeholder_numbers), demo=bool(demo),
                     demo_note=demo_note, keyword=primary["keyword"], volume=primary.get("volume"),
                     band_measured=measured_band or None, suggested=suggested,
                     format=arch, format_why=arch_why)
    if asked.get("answer") != words_chosen:
        asked = _record_answer(ctx, asked, words_chosen,
                               "the person" if words_chosen != suggested else "the person, who kept the suggestion")

    # From this line on, `build_spec` is the settled one and `brief["build_spec"]` is the raw
    # measurement. Nothing below reads the raw one, and _work/brief.json keeps it for the record.
    build_spec = assemble.settle_word_band(brief["build_spec"], words_chosen)
    say("Writing to %s words" % "{:,}".format(words_chosen),
        "Your number, not the measured band. Every step from here reads it: the plan's word budget, "
        "each section's length, the blend and the final rewrite")

    # ---- THE DECISIONS FILE, written once, here, and nowhere else -----------------------------
    # format, length and the topic verdict, all settled by this point. Every later step (the plan,
    # the write phase) reads this file through write/_common.decisions() and never re-decides any
    # of the three. format_choice, when given, is the person overriding the routed pick on the
    # ask-words reply; anything else keeps the router's archetype.
    picked_format = _format_pick(format_choice)
    format_final, format_source = (picked_format, "user") if picked_format else (arch, "serp")
    existing_decisions = store.load_artifact(chat_id, run_id, "decisions.json")
    # WRITTEN ONCE. A topic already researched can be asked about again in the same run (a fresh
    # angle mid-conversation, a rerun that already knows the answer) and every step above this line
    # replays from cache in under a second — but the decisions this file records were made the
    # first time, and a second pass over the same ground must not restamp them with a new
    # decided_at or silently redo a person's pick. Only a genuinely new run (no file yet) writes one;
    # an existing one wins, so the fields carried into research.json below stay in step with it.
    if existing_decisions is None:
        word_source = "measured" if (asked.get("answer_source") or "").startswith("the suggestion;") else "user"
        existing_decisions = {
            "format": format_final, "format_source": format_source,
            "word_target": words_chosen, "word_source": word_source,
            "measured_band": measured_band or {},
            "topic": {"state": "on" if gate.get("relevant", True) else "off", "why": gate.get("why") or ""},
            "decided_at": store.now(),
        }
        write_common.save_decisions(ctx, existing_decisions)
    else:
        format_final = existing_decisions.get("format") or format_final

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
    cur, reused_cur = step("curate", lambda: _curate(ctx, redo, topic, angle, spine_ctx, company, say))
    article_brief = curate._article_block(topic, angle, spine_ctx)
    dos = har = None
    if cur.get("turns"):
        dos, _ = step("dossier", lambda: dossier.build(cur, article_brief, say=say))
        # ---- the dossier health gate (8.19) ----------------------------------------------------
        # His conductor refuses a dossier under config.STORM_MIN_WORDS and retries the whole
        # research step ONCE before giving up, because "a dud STORM run poisons everything
        # downstream". Sutra let a 300-word dossier through in silence and built the blueprint, the
        # plan and the article on top of it. Same floor, same single retry, and the refusal says
        # plainly what happened instead of shipping a brief nobody can use.
        words, ok = dossier.healthy(dos)
        for _attempt in range(_c.DOSSIER_RETRIES):
            if ok:
                break
            say("The research came back too thin (%s, under %s)"
                % (_plural(words, "word"), "{:,}".format(_c.DOSSIER_MIN_WORDS)),
                "A healthy dossier runs to thousands of words. Running the interviews again, once")
            cur, _ = _c.cached(ctx, "curate", True,
                               lambda: _curate(ctx, True, topic, angle, spine_ctx, company, say))
            reused_cur = False
            if not cur.get("turns"):
                dos = None
                break
            dos, _ = _c.cached(ctx, "dossier", True, lambda: dossier.build(cur, article_brief, say=say))
            words, ok = dossier.healthy(dos)
        if dos is not None and not ok:
            say("Stopping: the research is too thin to build on",
                "%s after a second attempt, and the floor is %s"
                % (_plural(words, "word"), "{:,}".format(_c.DOSSIER_MIN_WORDS)))
            # NAME THE CAUSE WHEN IT WAS PLACEHOLDERS (2026-09-17). Found live, chained to the
            # _preflight fix above: a run on placeholder numbers (no DataForSEO login, asked for
            # explicitly) hit exactly this guard, and this message used to say only "the write-up
            # came back thin" -- never that the search numbers behind it were never real. Checked
            # here, not read from a credential: dfs.available() is a plain bool, no login value.
            cause = (" This run was on placeholder search numbers because no DataForSEO login is "
                     "connected, which is very likely why the material came back this thin."
                     if demo and not dfs.available() else "")
            return {"summary": "The research did not produce enough material to write from, so the "
                               "run stopped rather than building on it.",
                    "error": (("The research team ran, and the write-up came back at %s. A real "
                              "dossier for a topic like this runs to thousands; anything under %s "
                              "means the research effectively failed even though nothing crashed. I "
                              "tried a second time and got the same result. Everything after this "
                              "step is built on the dossier — the facts, the plan, the article — so "
                              "a thin one quietly turns into an article with almost nothing behind "
                              "it. Run the research again, or give me a narrower topic with more "
                              "written about it."
                              % (_plural(words, "word"), "{:,}".format(_c.DOSSIER_MIN_WORDS))) + cause),
                    "artifact": None}
        if dos is not None:
            har, _ = step("dossier-cards", lambda: dossier.harvest(dos, cur.get("pages"), say=say))
    if har and har.get("cards"):
        ev = {"cards": har["cards"], "pages": cur["pages"], "cost": cur.get("cost") or 0.0,
              "skipped": [], "dropped_verbatims": har.get("dropped_verbatims") or 0,
              "recovered_sources": har.get("recovered_sources") or 0,
              "needs_source": har.get("needs_source") or 0,
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
    fill, _ = step("gap-evidence", lambda: _fill(gap["queries"], company, ev, demo, say,
                                                 angle=angle, spine_ctx=spine_ctx,
                                                 article_brief=article_brief))
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
        "verdict": brief["verdict"], "build_spec": build_spec, "completeness": brief["completeness"],
        "word_target": words_chosen,
        # a display copy of the checkpoint's pick, for the research doc; decisions.json is the source
        "format_archetype": format_final,
        "cannibalisation": cann.get("hit"),
        "topic_gate": {"relevant": bool(gate.get("relevant", True)), "why": gate.get("why", ""),
                       "angle_changed": bool(gate.get("angle_changed")), "why_changed": gate.get("why_changed", "")},
        "persona": per,
        "evidence": {"pages": ev["pages"], "skipped": ev.get("skipped") or [], "cards": len(ev["cards"]),
                     "dropped_verbatims": ev.get("dropped_verbatims", 0),
                     # the offline source recovery: figures traced back to the page that stated them,
                     # and figures that could not be and are marked needs_source instead
                     "recovered_sources": ev.get("recovered_sources", 0),
                     "needs_source": sum(1 for c in cards if c.get("needs_source")),
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
                      "queries": gap["queries"], "filled": fill.get("pages") or [],
                      "fill_rounds": fill.get("rounds") or []},
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


def _fill(queries, company, ev, demo, say, angle="", spine_ctx=None, article_brief=""):
    """The gap fill: a REAL research conversation per gap question, not a keyword lookup.

    12-gap-check/scripts/rerun_storm.py runs STORM's own runner once per gap query
    (`--turns 4 --topk 5 --perspectives 4`), carrying the article's spine file so the fill research
    "stays inside the article's world instead of running blind", and saves each as its own iteration
    beside the main dossier.

    Sutra answered the same gap with ONE keyword search over ten SERP results (2026-09-10). That is
    backwards: the gap check exists to find the holes that matter most — the gaps we can own, the
    thing the article is supposed to be differentiated on — and they were getting the thinnest
    evidence in the whole run. This runs the same machinery step 2 runs, so there is one conversation
    engine in this package and not two: the gap query becomes the research subject, the article's own
    spine and world ride along unchanged, the answers are written up as a dossier, and the cards are
    lifted out of that. A question whose conversation comes back with nothing falls back to the plain
    keyword read, for the same reason step 2 does: some evidence beats none.
    """
    if not queries:
        return {"cards": [], "pages": [], "cost": 0.0, "rounds": []}
    own = company.get("domain") or ""
    seen = {p["url"] for p in (ev.get("pages") or []) if p.get("url")}
    # The facts the main round already carries, so a gap round that lands on the same page does not
    # file the same sentence twice as a second card.
    known = {_c.norm(c.get("verbatim", "")) for c in (ev.get("cards") or [])}
    out = {"cards": [], "pages": [], "cost": 0.0, "rounds": []}
    for q in queries:
        say("Researching the gap: %s" % q["query"][:70],
            "The same four-researcher conversation the main round ran, aimed at this one hole")
        cur = curate.run(q["query"], angle, spine_ctx, company, own_domain=own,
                         max_pages=_c.GAP_FILL_MAX_PAGES, say=say)
        cards, pages, cost = [], [], cur.get("cost") or 0.0
        if cur.get("turns"):
            dos = dossier.build(cur, article_brief or curate._article_block(q["query"], angle, spine_ctx), say=say)
            har = dossier.harvest(dos, cur.get("pages"), say=say)
            cards = har.get("cards") or []
            pages = [{"url": p.get("url"), "title": p.get("title") or "",
                      "word_count": p.get("word_count")} for p in (cur.get("pages") or [])]
            route = "the research conversation"
        if not cards:
            # nothing came back from the interviews: the narrower read, rather than an unfilled gap
            got = evidence.gather([q["query"]], company, own_domain=own, exclude=seen,
                                  max_pages=_c.EVIDENCE_SERP_DEPTH, demo=demo, say=say)
            cards = got.get("cards") or []
            pages = list(got.get("pages") or [])
            cost += got.get("cost") or 0.0
            route = "the plain keyword read (the conversation returned nothing)"
        fresh = []
        for c in cards:
            key = _c.norm(c.get("verbatim", ""))
            if key in known:
                continue
            known.add(key)
            c["origin"] = "gap/" + c.get("origin", "")
            fresh.append(c)
        out["cards"] += fresh
        out["pages"] += [dict(p, query=q["query"]) for p in pages]
        out["cost"] += cost
        out["rounds"].append({"query": q["query"], "route": route, "harvested": len(cards),
                              "cards": len(fresh), "pages": len(pages),
                              "questions": len(cur.get("turns") or [])})
        seen |= {p["url"] for p in pages if p.get("url")}
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
