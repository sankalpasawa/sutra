"""curate.py — the research conversation. STORM's knowledge curation, ported as plain Python.

The port's first evidence engine searched the article's own ranking keywords and read what came
back. That is a lookup, not research: it can only ever return a sentence that already exists on
one page, and it asks nothing. Measured against the original on the same topic, it issued 7
keyword searches where STORM asked 36 grounded questions across 132 pages.

This is the method, from `11-storm/engine/knowledge_storm/storm_wiki/modules/knowledge_curation.py`
(ConvSimulator / WikiWriter / TopicExpert) and `11-storm/prompts/pick-researchers.md`:

    1. PICK A TEAM. RESEARCHERS personas, deliberately mixed: the builder, the sceptic, the
       evidence one, the practitioner. Never four people who agree.
    2. EACH ONE INTERVIEWS AN EXPERT, for TURNS turns. Every turn:
         a. the persona asks ONE question, seeing the article brief and the conversation so far
         b. that question becomes at most QUERIES_PER_TURN search queries
         c. the queries are searched and the pages read for free
         d. the "expert" answers ONLY from the passages retrieved, citing them by number
       The answer feeds the next question, which is why the questions get sharper as it goes.
    3. THE BREADTH FLOOR. A persona may not say "thank you" before FLOOR_TURNS questions. Rich
       answers make it satisfied after one or two, and that starves the source breadth. The
       original patched this into WikiWriter for the same reason; the note is kept.

What comes back is the dialogue plus every page any persona read. `synthesise()` then writes the
dossier those pages support, and the harvest lifts cards out of THAT rather than out of raw pages,
which is what lets a card be a cross-source claim ("the figure everyone quotes is from a cycle its
own publisher calls superseded") instead of a sentence copied from one page.

Not ported, deliberately: the OpenAI shim (`11-storm/scripts/shim.py`). It exists only because
dspy/litellm speak the OpenAI HTTP API; this package calls the CLI directly.

A SEARCH THAT FAILS IS A SEARCH WE DO WITHOUT (2026-09-15). The conversation issues ~48 live
searches. One of them coming back "40101: Internal SE Server Error" used to raise straight through
pool.map and throw away everything the other researchers had already found. dfs.py now waits and
retries temporary trouble; a search that still fails after that is skipped and counted, the way an
unreadable page already was. If NO search worked at all the round still fails loudly, because an
article with no research behind it must not be written.

AND THE WORK IS KEPT AS IT HAPPENS. `keep` (optional) is called with the whole conversation so far
after every finished turn, and `resume` hands a saved one back, so a round that dies part way picks
up where it stopped instead of paying for the same searches twice. run_research wires both to
_work/curate-partial.json.

Reads: topic, angle, spine, world, company. Returns
{"team": [...], "turns": [...], "pages": [...], "queries": [...], "cost": float, "demo": bool,
 "searches": int, "failed_searches": int}.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .. import llm, store
from ..tools import dfs
from . import _common as _c
from . import web

# Fewer by default (2026-09-17, the Prompts tab's "Researchers" setting): the picker prompt still
# names four jobs (the builder, the sceptic, the evidence one, the practitioner) and combines them
# onto fewer people when N is smaller, or goes deeper on one when N is larger -- see
# pick-researchers.md. RESEARCHERS_RANGE is the Prompts tab's slider; pick_team clamps to it.
RESEARCHERS = 3
RESEARCHERS_RANGE = (1, 6)
TURNS = 4                 # --turns 4, the original's run flag
QUERIES_PER_TURN = 3      # max_search_queries_per_turn
SEARCH_TOP_K = 5          # --topk 5
FLOOR_TURNS = 3           # the breadth floor: no "thank you" before this many questions
MAX_PAGES = 140           # every persona's reading, deduped, capped so one run cannot run away
READ_TIMEOUT = 90.0       # wall clock for one turn's page reads; a slow host never holds the run
TOTAL_TIMEOUT = 900.0     # and for the whole conversation: past this it stops asking and works
                          # with what it has, so a bad day cannot be sixteen timeouts in a row
ANSWER_WORDS = 2500       # per-source word cap inside one answer prompt (the deep-RAG tweak)
INFO_WORDS = 15000        # and the whole prompt's cap, so one answer cannot run away
END = "thank you so much for your help"
FAIL_FAST = 6             # searches failed with none ever working: stop asking, the service is down


def _words(text, limit):
    """Cut to a word count without breaking lines, the way ArticleTextProcessing does."""
    out, n = [], 0
    for line in (text or "").splitlines():
        w = line.split()
        if n + len(w) > limit:
            out.append(" ".join(w[: max(0, limit - n)]))
            break
        out.append(line)
        n += len(w)
    return "\n".join(out)


def _article_block(topic, angle, spine_ctx):
    """The brief every question and every section write sees, so nothing drifts off the article."""
    sc = spine_ctx or {}
    return "\n".join([
        "- Title: %s" % topic,
        "- Distinct angle: %s" % (angle or "(none given yet)"),
        "- The spine (what this argues, for whom, what the reader can do at the end): %s"
        % (sc.get("spine") or "(not written yet)"),
        "- What this is about: %s" % (sc.get("about") or "(not stated)"),
        "- What this is NOT about: %s" % (sc.get("not_about") or "(not stated)"),
    ])


def pick_team(topic, angle, spine_ctx, company, n=None):
    """The research team. Mixed by construction: builder, sceptic, evidence, practitioner.

    n=None reads the person's saved "Researchers" setting (store.research_settings), falling back
    to RESEARCHERS when nothing has been saved -- so an unattended run and a fresh install both get
    the engine's own default, not just what the Prompts tab happens to display. Always clamped to
    RESEARCHERS_RANGE, whatever is asked for.
    """
    if n is None:
        n = store.research_settings().get("researchers")
        if n is None:
            n = RESEARCHERS
    n = max(RESEARCHERS_RANGE[0], min(RESEARCHERS_RANGE[1], n))
    tok = _c.company_tokens(company)
    p = _c.prompt("pick-researchers", TITLE=topic, ANGLE=angle or "(none given yet)",
                  SPINE=(spine_ctx or {}).get("spine") or "(not written yet)",
                  ABOUT=(spine_ctx or {}).get("about") or "",
                  NOT_ABOUT=(spine_ctx or {}).get("not_about") or "",
                  BRAND=tok["brand"], ABOUT_BRAND=tok.get("about_brand") or tok["brand"], N=str(n))
    data = llm.json_call(p) or {}
    team = []
    for r in (data.get("researchers") or [])[:n]:
        if isinstance(r, dict) and (r.get("role") or "").strip():
            team.append({"role": r["role"].strip(), "focus": (r.get("focus") or "").strip()})
    return team


def _ask(topic, article, persona, turns):
    """One question from one persona, seeing the brief and the conversation so far."""
    conv = []
    for t in turns[:-4]:
        conv.append("You: %s\nExpert: Omit the answer here due to space limit." % t["question"])
    for t in turns[-4:]:
        conv.append("You: %s\nExpert: %s" % (t["question"], re.sub(r"\[\d+\]", "", t["answer"])))
    conv = _words("\n".join(conv).strip() or "N/A", 2500)
    floor = ""
    if len(turns) < FLOOR_TURNS:
        floor = ("\nYou have asked only %d question(s) so far. Do NOT end the conversation yet and "
                 "do NOT say thank you. You must ask another substantive question about a different, "
                 "not-yet-covered aspect of this article." % len(turns))
    q = llm.text(_c.prompt("ask-question", TOPIC=topic, ARTICLE=article,
                           PERSONA="%s — %s" % (persona["role"], persona["focus"]),
                           CONV=conv, FLOOR=floor)) or ""
    return q.strip().strip('"').split("\n")[0].strip()


def _queries(topic, question, n=QUERIES_PER_TURN):
    raw = llm.text(_c.prompt("question-to-queries", TOPIC=topic, QUESTION=question, N=str(n))) or ""
    out = []
    for line in raw.splitlines():
        q = line.strip().lstrip("-*0123456789. ").strip().strip('"').strip("'")
        if q and q.lower() not in {x.lower() for x in out}:
            out.append(q)
    return out[:n]


def _search(query, company, top_k=SEARCH_TOP_K):
    """The organic URLs for one query, plus what the call cost."""
    got = dfs.serp_advanced(query, depth=top_k, paa_click_depth=None, ai_overview=False,
                            location_name=company.get("location_name") or "United States",
                            language_code=company.get("language_code") or "en")
    urls = [r.get("url") for r in ((got.get("extract") or {}).get("top_organic") or []) if r.get("url")]
    return urls[:top_k], got.get("cost") or 0.0, bool(got.get("demo"))


def _rank(passages, question, keep):
    """The passages most relevant to the question, best first.

    STORM ranked snippets with a MiniLM cosine (storm_dataclass.py:110). This package already
    ships Voyage for the own-page match, so it is reused here. With no key the order is left
    alone, which is the original's behaviour with its encoder missing.
    """
    if len(passages) <= keep:
        return passages
    try:
        from ..tools import voyage
        if not voyage.available():
            return passages[:keep]
        vecs = voyage.embed([question] + passages)
        q, rest = vecs[0], vecs[1:]
        order = sorted(range(len(passages)), key=lambda i: -float(rest[i] @ q))
        return [passages[i] for i in order[:keep]]
    except Exception:  # noqa: BLE001 — ranking is a nicety; never lose the passages over it
        return passages[:keep]


def _read(urls, pages, say=None):
    """Read what we have not read before. Returns the newly read pages, in order.

    Hard-capped in wall clock. Found 2026-09-05: one unresolvable host held the whole research
    conversation open forever, because every persona's turn waits on its own reads and each read
    only had a per-request timeout. A page that has not arrived by now is a page we do without.
    """
    todo = [u for u in urls if u not in pages]
    if not todo:
        return []
    fresh = []
    pool = ThreadPoolExecutor(max_workers=6)
    try:
        futures = {pool.submit(_safe_fetch, u): u for u in todo}
        deadline = time.time() + READ_TIMEOUT
        for fut in futures:
            left = deadline - time.time()
            try:
                page = fut.result(timeout=max(0.1, left))
            except Exception:  # noqa: BLE001 — a timed-out or failed read is a page we do without
                fut.cancel()
                continue
            if page:
                url = futures[fut]
                page["passages"] = web.passages(page["text"])
                pages[url] = page
                fresh.append(page)
    finally:
        pool.shutdown(wait=False)
    return fresh


def _safe_fetch(url):
    if url.lower().split("?")[0].endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip")):
        return None
    try:
        return web.fetch(url)
    except Exception:  # noqa: BLE001 — an unreadable page is a fact about the page, not a failure
        return None


def _answer(topic, question, sources):
    """The expert's answer, grounded only in the retrieved passages and citing them by number."""
    if not sources:
        return "I cannot answer this question based on the available information. Nothing was retrieved for it."
    info = ""
    for n, (url, passages) in enumerate(sources, start=1):
        block = "\n".join("[%d]: %s" % (n, p) for p in passages)
        info += _words(block, ANSWER_WORDS) + "\n\n"
    info = _words(info, INFO_WORDS)
    try:
        return (llm.text(_c.prompt("answer-question", TOPIC=topic, QUESTION=question, INFO=info)) or "").strip()
    except Exception as e:  # noqa: BLE001
        return "I cannot answer this question based on the available information (%s)." % str(e)[:80]


def _dead(budget):
    """Has every search so far failed, enough of them to call it? Then asking more is pointless."""
    return budget["failed"] >= FAIL_FAST and budget["failed"] == budget["searched"]


def _converse(persona, topic, article, company, pages, budget, say=None, turns=None, on_turn=None):
    """One persona's interview: TURNS questions, each one searched and answered.

    `turns` is the conversation so far when a saved round is resumed; `on_turn` is told after every
    finished turn, so the work can be kept."""
    turns = list(turns or [])
    for _ in range(TURNS - len(turns)):
        if _dead(budget):
            break
        if len(pages) >= budget["max_pages"]:
            break
        if time.time() > budget["deadline"]:
            if say and not budget.get("said_deadline"):
                budget["said_deadline"] = True
                say("Stopping the interviews here", "the research has taken long enough; writing "
                    "up what the team already found")
            break
        q = _ask(topic, article, persona, turns)
        if not q:
            break
        if q.lower().startswith(END) and len(turns) >= FLOOR_TURNS:
            break
        qs = _queries(topic, q)
        urls, cost, demo, failed = [], 0.0, False, 0
        for query in qs:
            try:
                u, c, d = _search(query, company)
            except Exception as e:  # noqa: BLE001 — a failed search is a search we do without
                failed += 1
                with budget["lock"]:
                    budget["searched"] += 1
                    budget["failed"] += 1
                    budget["last_error"] = str(e)[:200]
                continue
            with budget["lock"]:
                budget["searched"] += 1
            urls += u
            cost += c
            demo = demo or d
        with budget["lock"]:
            budget["cost"] += cost
            budget["demo"] = budget["demo"] or demo
            budget["queries"] += qs
        if qs and failed == len(qs):
            # Nothing came back for this question at all, so there is nothing to answer from. It is
            # not kept as a turn: an "I cannot answer" turn would only be saved and replayed.
            if say:
                say("%s's searches failed" % persona["role"],
                    "%d of %d searches for \"%s\" did not come back; moving on"
                    % (failed, len(qs), q[:70]))
            continue
        urls = [u for u in dict.fromkeys(urls)][: budget["max_pages"] - len(pages)]
        fresh = len(_read(urls, pages))
        sources = []
        for u in urls:
            p = pages.get(u)
            if p and p.get("passages"):
                sources.append((u, _rank(p["passages"], q, 4)))
        answer = _answer(topic, q, sources[:SEARCH_TOP_K])
        turns.append({"persona": persona["role"], "question": q, "queries": qs,
                      "urls": [u for u, _ in sources], "answer": answer})
        if on_turn:
            on_turn(persona, turns, False)
        if say:
            say("%s asked: %s" % (persona["role"], q[:70]),
                "%d new page%s read, %d already seen, %d answered from"
                % (fresh, "" if fresh == 1 else "s", len(urls) - fresh, len(sources)))
    if on_turn and not _dead(budget):
        on_turn(persona, turns, True)      # this persona is finished; a resume skips it
    return turns


def run(topic, angle, spine_ctx, company, own_domain="", max_pages=MAX_PAGES, say=None,
        resume=None, keep=None):
    """The whole curation round. Personas run in parallel; each one's turns are sequential.

    resume: a saved round (what `keep` was last given), reused as far as it got. keep: called with
    the round so far after every finished turn."""
    article = _article_block(topic, angle, spine_ctx)
    saved = resume if isinstance(resume, dict) and resume.get("team") else {}
    team = saved.get("team") or pick_team(topic, angle, spine_ctx, company)
    if not team:
        return {"team": [], "turns": [], "pages": [], "queries": [], "cost": 0.0, "demo": False,
                "skipped": "no research team came back, so no interviews ran"}
    prior = {r: list(ts or []) for r, ts in (saved.get("turns") or {}).items()}
    done = set(saved.get("done") or [])
    if say:
        if saved:
            say("Picking the interviews up where they stopped",
                "%d questions already answered, %d of %d researchers finished; those searches are "
                "not bought again" % (sum(len(v) for v in prior.values()), len(done), len(team)))
        else:
            say("Chose %d researchers" % len(team), "; ".join(r["role"] for r in team))

    pages = dict(saved.get("pages") or {})
    budget = {"cost": float(saved.get("cost") or 0.0), "demo": bool(saved.get("demo")),
              "queries": list(saved.get("queries") or []), "max_pages": max_pages,
              "deadline": time.time() + TOTAL_TIMEOUT, "searched": 0, "failed": 0,
              "last_error": "", "lock": threading.Lock()}
    save_lock = threading.Lock()

    def on_turn(persona, rows, finished):
        if not keep:
            return
        with save_lock:                    # one writer at a time, so a later save never loses a turn
            prior[persona["role"]] = list(rows)
            if finished:
                done.add(persona["role"])
            with budget["lock"]:
                state = {"team": team, "turns": dict(prior), "done": sorted(done),
                         "pages": dict(pages), "queries": list(budget["queries"]),
                         "cost": budget["cost"], "demo": budget["demo"]}
            keep(state)

    def converse(r):
        if r["role"] in done:
            return prior.get(r["role"]) or []
        return _converse(r, topic, article, company, pages, budget, say=say,
                         turns=prior.get(r["role"]), on_turn=on_turn)

    with llm.pool(len(team)) as pool:
        results = list(pool.map(converse, team))
    turns = [t for rows in results for t in rows]
    worked = budget["searched"] - budget["failed"]
    if budget["failed"] and worked == 0 and not any(prior.get(r["role"]) for r in team):
        raise RuntimeError("Every research search failed (%d of %d), so there is nothing to write "
                           "from. The last error: %s"
                           % (budget["failed"], budget["searched"], budget["last_error"]))
    own = (own_domain or "").lower().lstrip("www.")
    kept = [dict(p, url=u) for u, p in pages.items()
            if not (own and (u.split("/")[2].lower().lstrip("www.") if "://" in u else "").endswith(own))]
    if say:
        say("Interviews done", "%d questions asked, %d pages read across %d searches%s"
            % (len(turns), len(kept), len(budget["queries"]),
               "; %d of %d searches failed and were skipped" % (budget["failed"], budget["searched"])
               if budget["failed"] else ""))
    return {"team": team, "turns": turns, "pages": kept, "queries": budget["queries"],
            "cost": budget["cost"], "demo": budget["demo"],
            "searches": budget["searched"], "failed_searches": budget["failed"]}
