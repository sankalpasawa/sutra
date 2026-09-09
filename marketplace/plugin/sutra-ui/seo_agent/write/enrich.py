"""enrich.py — Architect step 2: ENRICH. Go and get the research the structure asked for.

WHAT CHANGED, AND WHY (2026-09-09). This step used to record every needs_research marker as
"research that did not happen" and hand the note to the writer. The owner rejected that outright:
"why the hell does it not do that? It got to do that. Who cares about every marker as research that
did not happen." He is right. A note does not write a section. On his own cost-per-hire article nine
sections asked for extra research and nine got nothing.

So it now does what the original did, per marker:
  1. plan-queries.md  -> up to QUERIES_PER_MARKER web queries, aimed at the section's JOB
  2. search           -> live organic results (DataForSEO), or the model's own list of pages when
                         there is no paid search to spend (see `route`)
  3. read             -> the write phase's own fetcher (browser-assisted, host rate limited)
  4. extract          -> the research engine's harvest, which drops any quote that is not really on
                         the page. Nothing here is invented; a fact that is not on a page it read
                         does not become a card.
  5. place            -> new cards get ids from 9001 and join the destination the ARCHITECT named
                         (the section's opening, or one of its existing sub-headings). This step
                         never invents a heading.

NOTHING NEW WAS BUILT UNDERNEATH. The searching is `research/evidence.plan_pages` (which is the one
place a DataForSEO organic search happens), the reading is `write/_common.fetch` (the write phase's
single door to the network, so tests can close it), and the extraction is
`research/evidence._harvest_page` (the harvest prompt plus its word-for-word check). This file is the
wiring plus the owner's two prompts.

IT LOGS AS IT GOES. One say() line per marker per stage, because a step that goes quiet for two
minutes looks hung and every other step in this app now says what it is doing.

WHAT STILL RUNS, exactly as before, because it protects the article regardless of where the material
came from:
  THE SAFETY NET. The architect may create a sub-heading with no boxes and rely on research to fill
  it. When the research fails, that leaves a heading with nothing under it, so it is removed here and
  recorded.
  THE THIN FLAG. A section that asked for research and did not get it stays in the article thinner
  than it was designed to be. It is recorded in `research_failures` so write_body warns the writer
  not to pad, exactly as the original did for a marker that came back empty.
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from ..research import evidence
from ..tools import dfs
from . import _common as C

# ---- the knobs, all named, all here ---------------------------------------------------------------
QUERIES_PER_MARKER = 3        # web queries planned per needs_research marker (the original's ENRICH_QUERIES_PER_H3)
PAGES_PER_MARKER = 5          # pages that must LOAD before the extractor runs (ENRICH_PAGES_PER_H3)
URLS_PER_QUERY = 6            # candidate urls kept per query before they are interleaved
PAGE_CHARS = 12000            # chars of each loaded page handed to the extractor (ENRICH_PAGE_CHARS)
MIN_PAGE_CHARS = 500          # below this a "page" is a wall, a cookie banner or an error, not a source
MARKER_WORKERS = 4            # markers researched at once; the model calls are gated by llm.PARALLEL anyway
FIRST_CARD_ID = 9001          # enriched cards are numbered from here, as the original numbered them


# ---- the one search-and-read path the two hunting stations share -----------------------------------
# verify_sources imports `route`, `search` and `read_pages` from here rather than growing a second
# copy. One value decided in one place: whether this run can search at all is decided by `route`, and
# both stations report the same sentence about it.

def route():
    """How this run can search: ("dataforseo" | "model", the sentence the report prints).

    DataForSEO is the real search and costs money, so it is used whenever it is connected and funded.
    With no paid search there is still a route: the model names the pages it believes state the
    material, and every one of them has to actually load and actually contain the quote before a card
    survives. It is weaker than a live search and the report says so, but it is not nothing, and it
    never invents a fact.
    """
    if not dfs.available():
        return "model", ("DataForSEO is not connected, so the paid web search was skipped; the pages "
                         "came from the model's own list and only the ones that really loaded were read")
    try:
        bal = dfs.balance()
    except Exception:  # noqa: BLE001 — a broken balance check must not stop a run that can pay
        bal = None
    if bal is not None and bal < C.MIN_DFS_BALANCE:
        return "model", ("the DataForSEO balance is under $%.2f, so the paid web search was skipped; "
                         "the pages came from the model's own list and only the ones that really "
                         "loaded were read" % C.MIN_DFS_BALANCE)
    return "dataforseo", "live DataForSEO organic search"


def _interleave(lists):
    """Rank-interleave candidate urls across queries, deduped, order preserved.

    One query per marker is usually a dead end. Taking the first query's whole page list first means
    a dead end eats every download slot, which is what this stops."""
    out, i = [], 0
    while any(i < len(L) for L in lists):
        for L in lists:
            if i < len(L):
                out.append(L[i])
        i += 1
    seen, res = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def search(queries, route_name, exclude=(), per_query=URLS_PER_QUERY):
    """Candidate page urls for a list of queries, best first, deduped. (urls, cost_usd).

    The DataForSEO route goes through research/evidence.plan_pages, which is the one place in this
    package a live organic search is bought. A DEMO answer is thrown away here: demo SERP rows are
    made-up urls, and researching from them would put invented sources in a real article.
    """
    queries = [str(q).strip() for q in (queries or []) if str(q).strip()]
    if not queries:
        return [], 0.0
    if route_name == "dataforseo":
        company = C.sh.company()
        per, cost = [], 0.0
        for q in queries:
            planned, c, demo = evidence.plan_pages([q], company, exclude=exclude, max_pages=per_query)
            cost += c
            if demo:
                return [], 0.0
            per.append([u for u, _kw in planned])
        return _interleave(per), round(cost, 6)
    try:
        # web=True: this ONE call may search the internet. It is the port of a step the original
        # runs as `claude -p --allowedTools WebSearch`, and it exists to go and find pages. Without
        # it the model can only offer URLs it believes exist; a believed URL fails to load and is
        # discarded, so nothing invented ever survives, but guess-and-check finds far less than a
        # search does. Every other call in this package answers from its prompt and nothing else.
        out = llm.json_call(C.prompt("search-urls", queries="\n".join("- " + q for q in queries),
                                     max=per_query * len(queries)), web=True) or {}
    except Exception:  # noqa: BLE001 — a search that fails is a marker that found nothing, never a crash
        return [], 0.0
    raw = out.get("urls") if isinstance(out, dict) else out
    seen, urls = {str(u).rstrip("/").lower() for u in exclude}, []
    for u in (raw or []):
        u = str(u or "").strip()
        if not u.lower().startswith("http"):
            continue
        k = u.rstrip("/").lower()
        if k in seen:
            continue
        seen.add(k)
        urls.append(u)
    return urls, 0.0


def search_many(queries, route_name, say=lambda *a: None, exclude=(), per_query=URLS_PER_QUERY):
    """Candidate urls for MANY queries at once: ({query: [urls]}, cost_usd, [queries never searched]).

    ONE QUEUED BATCH INSTEAD OF ONE LIVE SEARCH PER QUERY, which is what the original does and what
    the price says to do: $0.0006 a queued search against $0.002 live (tools/dfs.SERP_QUEUED_USD and
    SERP_LIVE_USD, both his measurements). The hunt plans its queries for every claim before it
    searches for any of them, so there is nothing to wait for and no reason to pay live rates — a
    single article's hunt can run to hundreds of searches, and it is the owner's account.

    The third value is the queries that never came back. A query in that list was NOT searched, and
    the difference matters more here than anywhere: a claim whose search failed must be left
    unverified, and a claim whose search returned nothing is a claim with no source. Reading one as
    the other is how a run reports a clean article it never checked.

    The model route has no batch to speak of, so it falls back to one `search` call over all the
    queries at once — which is what it already did — and the result is spread across them.
    """
    queries = [str(q).strip() for q in (queries or []) if str(q).strip()]
    queries = list(dict.fromkeys(queries))
    if not queries:
        return {}, 0.0, []
    if route_name != "dataforseo":
        urls, cost = search(queries, route_name, exclude=exclude, per_query=per_query)
        # The model answers with one list for all the queries, so every query is handed the same
        # list. It is what the single-query path did too; the batch shape just makes it explicit.
        return ({q: list(urls) for q in queries} if urls else {}), cost, ([] if urls else list(queries))
    company = C.sh.company()
    say("Searching for every claim at once",
        "%d searches in one queued batch, about $%.2f — a live search each would be about $%.2f"
        % (len(queries), len(queries) * dfs.SERP_QUEUED_USD, len(queries) * dfs.SERP_LIVE_USD))
    try:
        got = dfs.serp_batch(queries, location_name=company.get("location_name"),
                             language_code=company.get("language_code"),
                             depth=per_query, say=say)
    except Exception as e:  # noqa: BLE001 — a batch that fails is a search that did not happen
        say("The search batch failed", "%s. Nothing was checked against a fresh search."
            % str(e)[:120])
        return {}, 0.0, list(queries)
    if got.get("demo"):
        # Same rule as `search`: demo rows are made-up urls and researching from them would put
        # invented sources in a real article. A demo answer is no answer.
        return {}, 0.0, list(queries)
    skip = {str(u).rstrip("/").lower() for u in exclude}
    out = {}
    for q, urls in (got.get("urls") or {}).items():
        keep = []
        for u in urls or []:
            k = str(u).rstrip("/").lower()
            if k in skip or k.endswith(evidence._SKIP_SUFFIXES):
                continue
            keep.append(u)
        out[q] = keep[:per_query]
    return out, float(got.get("cost") or 0.0), list(got.get("missing") or [])


def read_pages(urls, want, page_chars=PAGE_CHARS):
    """Read urls in order until `want` of them load. Returns [(url, text)].

    Whitespace is collapsed BEFORE the text is cut: raw tag-stripped text is mostly blank space and
    navigation, so a raw slice of a heavy page hands the extractor a menu instead of the article.
    """
    pages = []
    for u in urls:
        if len(pages) >= want:
            break
        t = C.fetch(u)
        if t.startswith("__ERR__") or len(t.strip()) < MIN_PAGE_CHARS:
            continue
        pages.append((u, " ".join(t.split())[:page_chars]))
    return pages


def cards_from(url, text, about, tag="enriched", origin=""):
    """Cards out of one page, through the research engine's harvest.

    _harvest_page owns the anti-fabrication rule: every "verbatim" has to be an exact substring of
    the page text or the card is dropped. That check is the reason this reuses the research engine
    instead of growing its own extractor.
    """
    got, _dropped = evidence._harvest_page({"url": url, "title": "", "text": text}, about)
    out = []
    for c in got:
        c = dict(c)
        c["tag"] = tag
        c["origin"] = origin or ("enrich/" + about[:40])
        out.append(c)
    return out


# ---- the step --------------------------------------------------------------------------------------

def _markers(shaped):
    """Every needs_research request as (section index, topic, destination).

    A marker is {topic, goes_to}: the topic is the research brief, goes_to names where the answer
    belongs. A plain string (the older shape) still works and defaults to the opening.
    """
    out = []
    for si, sec in enumerate(shaped["sections"]):
        for r in (sec.get("needs_research") or []):
            if isinstance(r, str) and r.strip():
                out.append((si, r.strip(), "opening"))
            elif isinstance(r, dict) and str(r.get("topic") or "").strip():
                out.append((si, str(r["topic"]).strip(), str(r.get("goes_to") or "opening").strip()))
    return out


def run(shaped, say=lambda *a: None, ctx=None):
    """Research every marker, place the new cards, then run the safety net.

    ctx is the article context (title, angle, about, not_about, persona) from _common.context. It is
    optional so an older two-argument call still works, but without it the query planner cannot see
    what the article is NOT about, and an enrichment query that drifts pulls real pages from a
    neighbouring field: every card built from them reads plausible and is wrong for this reader.
    """
    ctx = ctx or {}
    brand = C.company()
    markers = _markers(shaped)
    log, enriched, next_id = [], {}, FIRST_CARD_ID
    route_name, route_note = ("model", "") if not markers else route()

    if markers:
        say("Extra research: %s" % C.sh.plural(len(markers), "request"),
            "The structure asked for material it does not have. Searching by %s."
            % ("live search" if route_name == "dataforseo" else "the model's own list of pages"))

    def _one(si, topic, dest):
        """Research ONE marker. Touches no shared state, so several can run at once. Returns
        (log entry, cards). Ids are minted afterwards, in marker order, so runs stay comparable."""
        sec = shaped["sections"][si]
        head = sec.get("headline") or ""
        e = {"section": head, "h3": topic, "goes_to": dest, "route": route_name,
             "queries": [], "pages": [], "cards_kept": 0}
        try:
            # The section's JOB rides in with the heading. A heading is a label and can be vague
            # ("Appendix: full methodology"); the job says what the section actually has to deliver,
            # and this is the step that decides what we go out and buy.
            q = llm.json_call(C.prompt("plan-queries", brand=brand["brand"], about=brand["about"],
                                       title=ctx.get("title") or "(none)", angle=ctx.get("angle") or "(none)",
                                       world_about=C.or_na(ctx, "about"),
                                       world_not_about=C.or_na(ctx, "not_about"),
                                       persona=ctx.get("persona") or "(general professional reader)",
                                       section_headline=head, section_job=sec.get("job") or "(none given)",
                                       h3=topic, n=QUERIES_PER_MARKER)) or {}
            queries = [str(x).strip() for x in (q.get("queries") or []) if str(x).strip()][:QUERIES_PER_MARKER]
            e["queries"] = queries
            if not queries:
                e["status"] = "no queries planned"
                say("No search to run for: %s" % topic[:60], "the query planner returned nothing")
                return e, []
            say("Searching for: %s" % topic[:60], " | ".join(queries))
            urls, cost = search(queries, route_name)
            e["candidates"], e["cost_usd"] = len(urls), cost
            if not urls:
                e["status"] = "search returned nothing"
                say("Nothing came back for: %s" % topic[:60], "no result pages to read")
                return e, []
            pages = read_pages(urls, PAGES_PER_MARKER)
            e["pages"] = [u for u, _t in pages]
            if not pages:
                e["status"] = "no pages loaded"
                say("No page would open for: %s" % topic[:60],
                    "%d candidate(s) tried, none loaded" % len(urls))
                return e, []
            say("Read %s for: %s" % (C.sh.plural(len(pages), "page"), topic[:50]),
                ", ".join(u.split("/")[2] for u, _t in pages if "//" in u)[:200])
            found = []
            for u, t in pages:
                found += cards_from(u, t, topic)
            e["cards_kept"] = len(found)
            e["status"] = "ok" if found else "nothing usable found"
            if found:
                say("Found %s for: %s" % (C.sh.plural(len(found), "new fact"), topic[:50]),
                    "each one quoted word for word from a page that really loaded")
            else:
                say("Nothing usable for: %s" % topic[:60],
                    "the pages loaded but carried no fact this section can cite")
            return e, found
        except Exception as ex:  # noqa: BLE001 — one failed marker must never cost the article
            e["status"] = "error: %s: %s" % (type(ex).__name__, str(ex)[:120])
            say("Research failed for: %s" % topic[:60], e["status"])
            return e, []

    if markers:
        with ThreadPoolExecutor(max_workers=MARKER_WORKERS) as ex:
            results = [f.result() for f in [ex.submit(_one, si, t, d) for si, t, d in markers]]
    else:
        results = []

    # PLACED WHERE THE ARCHITECT SAID. This step does not invent a sub-heading: the research brief is
    # a search query, not a heading (one real example ran 200 characters), and a section deliberately
    # given no sub-headings must not gain one here. The cards join the opening, or an existing
    # sub-heading the architect named.
    for (si, topic, dest), (e, found) in zip(markers, results):
        sec = shaped["sections"][si]
        kept = []
        for c in found:
            enriched[next_id] = dict(c, card_id=next_id, id=next_id)
            kept.append(next_id)
            next_id += 1
        if kept:
            target = None
            if dest.lower() != "opening":
                target = next((h for h in sec.get("h3s") or [] if h.get("h3") == dest), None)
            if target is None:
                sec.setdefault("lead", {"h3": "", "boxes": [], "card_ids": [], "is_lead": True})
                sec["lead"].setdefault("card_ids", []).extend(kept)
                e["placed_in"] = "opening"
            else:
                target.setdefault("card_ids", []).extend(kept)
                e["placed_in"] = dest
            e["card_ids"] = kept
        log.append(e)

    # THE SAFETY NET. A sub-heading the architect created for research that then failed is a heading
    # with nothing under it. It is removed here and recorded. Also catches an empty one made by mistake.
    emptied = []
    for sec in shaped["sections"]:
        keep = []
        for h in sec.get("h3s") or []:
            if h.get("card_ids"):
                keep.append(h)
            else:
                emptied.append({"section": sec["headline"], "h3": h.get("h3", "")})
        sec["h3s"] = keep
    if emptied:
        shaped["empty_subheadings_removed"] = emptied
        say("Removed sub-headings with nothing under them", "%d" % len(emptied))

    # A FAILED MARKER IS LOUD. The section stays in the article thinner than it was designed to be,
    # so write_body is told not to pad it. It never stops the run: the rest of the section is real.
    failed = [{"section": x.get("section"), "h3": x.get("h3"), "status": x.get("status"),
               "queries": x.get("queries") or [], "pages_loaded": len(x.get("pages") or [])}
              for x in log if x.get("status") != "ok"]
    if failed:
        shaped["research_failures"] = failed
    resolved = sum(1 for x in log if x.get("status") == "ok")
    cost = round(sum(float(x.get("cost_usd") or 0.0) for x in log), 6)
    if not markers:
        note = "the structure asked for no extra research, so none was run"
    else:
        note = ("%d request(s), %d resolved, %d came back empty; %d new fact(s) added. Route: %s."
                % (len(markers), resolved, len(failed), len(enriched), route_note))
    shaped["enrichment"] = {"markers": len(markers), "resolved": resolved, "failed": len(failed),
                            "new_cards": len(enriched), "route": route_name if markers else "",
                            "note": note, "cost_usd": cost, "log": log,
                            # kept for the report page, which reads this key
                            "skipped": route_note if (markers and route_name == "model") else ""}
    if markers:
        say("Extra research done", note)
    return {"structure": shaped, "enriched_cards": enriched, "log": log, "note": note}
