"""links_pass.py — Writer step 8: LINKS. Internal links, read-more pointers, curated external links.

Reads:  the article after the slop pass ({intro, sections:[{heading, prose}], close}), the structure
        (each section's job), the card index (the cited sources), the Voyage page index
        (knowledge/content-index, tools/_index.py) and the page bodies (knowledge/content-database.jsonl).
Writes: the article with links laid in (links, citation_keep) and the report: placed (with sim/rr),
        failed, rejected, competitor urls blocked, dead links dropped, integrity per block.

Three pools, three judges, everything else code:
  1. INLINE: candidates per SECTION. Query = "<heading> — <job>", ONE batched voyage.embed, the title +
     best-body-chunk blend from _index.score, filters (own domain, ascii title, no %, skip paths), rerank
     ALL top-N with voyage.rerank on the page text, sort by rr then sim, keep LINK_PER_SECTION, attach
     excerpts. A page the article already cites is injected at 1.0. The judge (inline-links.md) sees every
     section at once. CODE: one link per section, never the same url twice, cap 5, the allowance scales
     with length (max(MIN_INTERNAL_LINKS, words / WORDS_PER_INTERNAL_LINK)).
  2. READ-MORE: top 5 cosine matches of the article's fingerprint against the title index, with the page
     opening; read-more.md; the pointer line is validated (a digit or an em dash rejects it); smoothing is
     applied only when the old sentence appears once and its tags and numbers are identical.
  3. EXTERNAL: the article's cited cards, own domain removed, direct competitors (knowledge/competitors.json)
     removed unless the article is a comparison; external-links.md picks at most EXTERNAL_LINKS_MAX.
Then: liveness (only 404/410/connect failure = dead; bot blocks kept), tolerant anchor insertion, THE
INTEGRITY DIFF (undo every declared insertion and the text must equal the pre-links article exactly,
both sides unlinked; undeclared drift reverts that block), and citation thinning (citation-places.md).

If the page index is missing, inline and read-more are skipped with a clear note; external curation
still runs.
"""
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from .. import llm, store
from ..tools import _index, _shared as sh, voyage
from ..write import _common as C
from ..write import tags

_MDLINK = re.compile(r"\[([^\]\[]+)\]\((https?://[^)\s]+)\)")
DEFAULT_PRODUCT_PATHS = ("/pricing", "/product", "/products", "/features", "/tools", "/calculator",
                         "/templates", "/glossary", "/demo", "/signup", "/platform", "/solutions")
SKIP_PATHS = ("/login", "/signup", "/contact", "/about", "/careers", "/terms", "/privacy", "/cdn-cgi")
READ_MORE_BAD = ("/pricing", "/login", "/signup", "/contact", "/about", "/careers", "/terms", "/privacy")


# ---------------------------------------------------------------- inputs
def product_paths():
    """The paths that mark a page as a product surface: brand/cta-pages.md's urls plus a generic default."""
    paths = set(DEFAULT_PRODUCT_PATHS)
    for u in re.findall(r"https?://[^\s)\]>\"']+", sh.brand_file("cta-pages.md") or ""):
        try:
            p = "/" + u.split("/", 3)[3].strip("/").split("?")[0]
        except IndexError:
            continue
        if len(p) > 1:
            paths.add(p.lower().rstrip("/"))
    return tuple(sorted(paths))


def own_domain(order):
    dom = (C.company().get("domain") or "").lower()
    if not dom:
        host = Counter(u.split("/")[2] for u in order if "://" in u).most_common(1)
        dom = host[0][0].lower() if host else ""
    return dom[4:] if dom.startswith("www.") else dom


def competitor_domains():
    d = store.knowledge("competitors.json") or {}
    rows = d.get("competitors") if isinstance(d, dict) else d
    out = set()
    for r in rows or []:
        dom = (r.get("domain") if isinstance(r, dict) else str(r)) or ""
        dom = dom.lower().strip()
        for pre in ("https://", "http://"):
            if dom.startswith(pre):
                dom = dom[len(pre):]
        dom = dom.split("/")[0]
        if dom.startswith("www."):
            dom = dom[4:]
        if dom:
            out.add(dom)
    return out


def article_text(w):
    parts = [("intro", w.get("intro") or "")]
    parts += [(s["heading"], s["prose"]) for s in w.get("sections") or []]
    parts.append(("close", w.get("close") or ""))
    return parts


def _render_article(parts):
    return "\n\n".join("## %s\n\n%s" % (h, t) for h, t in parts)


def _is_product(u, paths):
    return any(p in u.lower() for p in paths)


def _rank_of(c):
    rr = c.get("rr")
    return float(rr) if rr is not None else float(c.get("sim") or 0.0)


# ---------------------------------------------------------------- judge 4: where a source is marked
def citation_places(w, idx, cap, say=lambda *a: None):
    """Choose WHERE each over-cited source keeps its marker. Returns ({card_id: {kept place numbers}}, n_over).
    Occurrences are NUMBERED on the way out and matched by number on the way back; anything invalid falls
    back to keeping the first `cap`. Nothing is deleted: only the markers a reader sees are thinned."""
    places = {}
    for name, text in article_text(w):
        for sent in re.split(r"(?<=[.!?])\s+", text or ""):
            for cid in tags.ids(sent):
                places.setdefault(cid, []).append((name, " ".join(sent.split())[:110]))
    over = {c: p for c, p in places.items() if len(p) > cap}
    if not over:
        return {}, 0
    blocks = []
    for cid, ps in sorted(over.items(), key=lambda kv: -len(kv[1])):
        gloss = ((idx.get(cid) or {}).get("gloss") or "")[:90]
        lines = ["SOURCE %d — %s" % (cid, gloss), "  marked in %d places, keep at most %d:" % (len(ps), cap)]
        lines += ['   %d. "%s"   (in: %s)' % (i, s, b[:44]) for i, (b, s) in enumerate(ps, 1)]
        blocks.append("\n".join(lines))
    try:
        reply = llm.json_call(C.prompt("citation-places", max=cap, occurrences="\n\n".join(blocks))) or {}
    except Exception:       # noqa: BLE001
        reply = {}
    keep = {}
    srcs = reply.get("sources")
    for r in (srcs if isinstance(srcs, list) else []):
        if not isinstance(r, dict):
            continue
        try:
            cid = int(r.get("source"))
        except (TypeError, ValueError):
            continue
        if cid not in over:
            continue
        want = [i for i in (r.get("keep") or []) if isinstance(i, int) and 1 <= i <= len(over[cid])]
        keep[cid] = set(sorted(want)[:cap]) if want else set(range(1, cap + 1))
    for cid in over:
        keep.setdefault(cid, set(range(1, cap + 1)))
    return keep, len(over)


# ---------------------------------------------------------------- retrieval
def section_candidates(w, jobs, own, paths, say=lambda *a: None, per=None):
    """Per-SECTION shortlist of pages to link to. Returns {section heading: [candidate, ...]}."""
    import numpy as np
    per = per or C.LINK_PER_SECTION
    heads = [s_["heading"] for s_ in w.get("sections") or []]
    if not heads:
        return {}
    queries = [("%s — %s" % (h, jobs.get(h, ""))).strip(" —") for h in heads]
    Q = np.nan_to_num(np.asarray(voyage.embed(queries, "query"), dtype=np.float32))   # ONE call for all sections
    blend, T, B, meta, order = _index.score(Q, C.LINK_ALPHA)
    if B is None:
        say("No page-text index", "matching on titles only, which is weaker")
    bodies = sh.page_bodies()
    out, rerank_jobs = {}, []
    for qi, h in enumerate(heads):
        dense = []
        for i in np.argsort(-blend[qi]):
            u = order[i]
            t = meta.get(u, "")
            if not t or not t.isascii() or "%" in u or own not in u or any(b in u for b in SKIP_PATHS):
                continue
            dense.append({"url": u, "title": t, "sim": round(float(blend[qi][i]), 3),
                          "title_sim": round(float(T[qi][i]), 3),
                          "body_sim": round(float(B[qi][i]), 3) if B is not None else None,
                          "rr": None, "kind": "product" if _is_product(u, paths) else "article"})
            if len(dense) >= C.LINK_N_RETRIEVE:
                break
        out[h] = dense
        rerank_jobs.append((h, queries[qi], dense))

    def _rr(job):
        h, q, dense = job
        docs = [(bodies.get(c["url"].rstrip("/")) or c["title"])[:C.LINK_RERANK_DOC_CHARS] for c in dense]
        if not docs:
            return h, dense
        try:
            for i, s in voyage.rerank(q, docs, len(docs)):       # ALL of them: two scales must not be mixed
                dense[i]["rr"] = round(float(s), 3)
        except Exception:       # noqa: BLE001 — a rerank hiccup must not lose the whole section
            pass
        return h, dense

    with ThreadPoolExecutor(max_workers=6) as ex:
        for h, dense in ex.map(_rr, rerank_jobs):
            ranked = sorted(dense, key=_rank_of, reverse=True)[:per]
            kept = [c for c in ranked if _rank_of(c) >= C.LINK_MIN_SCORE]
            for c in kept:
                c["excerpt"] = " ".join((bodies.get(c["url"].rstrip("/")) or "").split())[:C.LINK_EXCERPT_CHARS]
            out[h] = kept
    return out


def read_more_candidates(w, own, exclude):
    """Top-5 site pages by meaning against the TITLE index. The article's fingerprint is the query."""
    import numpy as np
    loaded = _index.load_title()
    if loaded is None:
        return []
    V, meta, order = loaded
    fingerprint = " · ".join([w.get("h1") or ""] + [s["heading"] for s in w.get("sections") or []])
    q = np.nan_to_num(np.asarray(voyage.embed([fingerprint], "query")[0], dtype=np.float32))
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        sims = np.nan_to_num(V @ q)
    bodies = sh.page_bodies()
    out = []
    for i in np.argsort(-sims):
        u = order[i]
        t = meta.get(u, "")
        if u in exclude or "%" in u or not t or not t.isascii() or len(t) < 15:
            continue
        if own not in u or any(b in u for b in READ_MORE_BAD) or u.rstrip("/").count("/") <= 2:
            continue
        exc = " ".join((bodies.get(u.rstrip("/")) or "").split())[:2500]
        if not exc:
            continue                                   # a page with no text cannot be judged
        out.append({"url": u, "title": t, "sim": round(float(sims[i]), 3), "excerpt": exc})
        if len(out) == 5:
            break
    return out


# ---------------------------------------------------------------- insertion + guards
_SMART = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}


def _plain(t):
    """Typography-insensitive form for MATCHING only, never for output."""
    for a, b in _SMART.items():
        t = t.replace(a, b)
    return " ".join(t.split())


def _mask_links(text):
    return _MDLINK.sub(lambda m: "\x00" * len(m.group(0)), text)


def insert_anchor(prose, anchor, url):
    """Lay [...](url) over the first occurrence of the anchor WORDS not already inside a link.
    Tolerant matching: case, hyphens and spacing may differ, and any short run of non-alphanumerics may
    sit between the words (so "RICE, ICE, MoSCoW, the Eisenhower Matrix" matches), but the linked text is
    always the article's own span, untouched."""
    parts = [re.escape(p) for p in re.split(r"[^0-9A-Za-z%$]+", anchor) if p]
    if not parts:
        return None
    rx = re.compile(r"[^0-9A-Za-z]{1,4}".join(parts), re.I)
    m = rx.search(_mask_links(prose))
    if not m:
        return None
    found = prose[m.start():m.end()]
    return prose[:m.start()] + "[%s](%s)" % (found, url) + prose[m.end():]


def _unlink(text):
    return _MDLINK.sub(lambda m: m.group(1), text)


def valid_pointer(p, rm_urls):
    """A read-more pointer is navigation, not content: no digit, no em dash, no double hyphen."""
    if not (isinstance(p, dict) and p.get("url") in rm_urls and p.get("line")):
        return False
    stripped = re.sub(r"\(https?[^)]*\)", "", p["line"])
    return not re.search(r"\d", stripped) and "—" not in p["line"] and "--" not in stripped


def place_links(w, inline, pointers, kept, cand_by):
    """Insert every chosen link, then prove nothing else changed. Returns (article, placed, failed, integrity)."""
    out = C.deep(w)
    sec_by_head = {s["heading"]: s for s in out.get("sections") or []}
    placed, failed = [], []

    def _prose_of(name):
        if name == "intro":
            return out.get("intro") or ""
        if name == "close":
            return out.get("close") or ""
        return (sec_by_head.get(name) or {}).get("prose", "")

    def _set_prose(name, text):
        if name == "intro":
            out["intro"] = text
        elif name == "close":
            out["close"] = text
        elif name in sec_by_head:
            sec_by_head[name]["prose"] = text

    for l in inline:
        prose = _prose_of(l.get("section") or "")
        new = insert_anchor(prose, l["anchor"], l["url"]) if prose else None
        if new is None:
            failed.append(dict(l, kind="inline", judge_why=l.get("why"), why="anchor not found verbatim"))
        else:
            _set_prose(l["section"], new)
            c = cand_by.get((l.get("section") or "", l.get("url") or "")) or {}
            placed.append({"kind": "inline", **l, "sim": c.get("sim"), "rr": c.get("rr"),
                           "title_sim": c.get("title_sim"), "body_sim": c.get("body_sim")})

    head_by_plain = {_plain(h): h for h in list(sec_by_head) + ["intro", "close"]}
    for p in pointers:
        name = p.get("after_section") or ""
        prose = _prose_of(name)
        if not prose:
            name = head_by_plain.get(_plain(name), name)
            prose = _prose_of(name)
            if prose:
                p["after_section"] = name
        if not prose:
            failed.append(dict(p, kind="read-more", judge_why=p.get("why"), why="section not found"))
            continue
        adjustments = []
        for key in ("adjust_before", "adjust_after"):
            adj = p.get(key)
            if isinstance(adj, dict) and adj.get("old") and adj.get("new"):
                if (prose.count(adj["old"]) == 1 and tags.ids(adj["old"]) == tags.ids(adj["new"])
                        and sorted(re.findall(r"\d[\d,\.]*", adj["old"])) == sorted(re.findall(r"\d[\d,\.]*", adj["new"]))):
                    prose = prose.replace(adj["old"], adj["new"])
                    adjustments.append({key: adj})
                else:
                    failed.append({"kind": "read-more-adjust", "why": "sentence not found once, or touched a number/tag", **adj})
        prose = prose.rstrip() + "\n\n" + p["line"].strip()
        _set_prose(name, prose)
        placed.append({"kind": "read-more", "after_section": name, "line": p["line"].strip(), "url": p["url"],
                       "why": p.get("why"), "adjustments": adjustments})

    for k in kept:
        ph = k.get("anchor_phrase")
        if not ph:
            continue
        for name in ["intro"] + [s["heading"] for s in out.get("sections") or []] + ["close"]:
            prose = _prose_of(name)
            new = insert_anchor(prose, ph, k["url"]) if ph in _mask_links(prose) else None
            if new is not None:
                _set_prose(name, new)
                placed.append({"kind": "external-anchor", "section": name, "anchor": ph, "url": k["url"]})
                break
        else:
            k["anchor_phrase"] = None

    # THE INTEGRITY DIFF: undo everything declared -> must equal the pre-links text exactly. Both sides
    # are unlinked, because the article may arrive carrying the wrapper's CTA link. A link the article
    # ARRIVED with must still be there.
    integrity = []
    for name, before in dict(article_text(w)).items():
        after = _prose_of(name)
        reverted = _unlink(after)
        for pl in placed:
            if pl["kind"] == "read-more" and pl["after_section"] == name:
                reverted = reverted.replace("\n\n" + _unlink(pl["line"]), "")
                for adj in pl["adjustments"]:
                    a = list(adj.values())[0]
                    reverted = reverted.replace(a["new"], a["old"])
        ok = " ".join(reverted.split()) == " ".join(_unlink(before).split())
        lost = {u for _, u in _MDLINK.findall(before)} - {u for _, u in _MDLINK.findall(after)}
        if lost:
            ok = False
        if not ok:
            _set_prose(name, before)
        integrity.append(dict({"block": name, "ok": ok}, **({"lost_links": sorted(lost)} if lost else {})))
    return out, placed, failed, integrity


# ---------------------------------------------------------------- the step
def run(w, st, idx, say=lambda *a: None):
    brand = C.company()
    paths = product_paths()
    have_index = bool(_index.status().get("built")) and voyage.available()
    order_urls = []
    if have_index:
        loaded = _index.load_title()
        order_urls = loaded[2] if loaded else []
    own = own_domain(order_urls)

    # cards' urls + which cards each supports (the external pool)
    url_cards = defaultdict(list)
    used_ids = set()
    for _h, t in article_text(w):
        used_ids |= tags.id_set(t)
    for cid in used_ids:
        c = idx.get(cid)
        if c:
            for u in (c.get("source_urls") or [])[:1]:
                url_cards[u].append(c)

    words = sum(len((s_.get("prose") or "").split()) for s_ in (w.get("sections") or []))
    want = max(C.MIN_INTERNAL_LINKS, round(words / C.WORDS_PER_INTERNAL_LINK))
    jobs = {s_.get("headline") or "": (s_.get("job") or "")[:220] for s_ in (st.get("sections") or [])}
    notes = []

    # ---- JUDGE 1: inline internal links, SECTION BY SECTION -------------------
    inline, j1, per_sec, cand_by = [], {}, {}, {}
    if have_index:
        say("Finding pages on your site for every section", "%d sections" % len(w.get("sections") or []))
        per_sec = section_candidates(w, jobs, own, paths, say)
        for name, txt in article_text(w):
            for cid in tags.id_set(txt):
                c = idx.get(cid)
                for u in (c.get("source_urls") or [])[:1] if c else []:
                    if "://" in u and own and own in u.split("/")[2].lower() and name in per_sec:
                        if not any(x["url"] == u for x in per_sec[name]):
                            per_sec[name].insert(0, {"url": u, "title": "", "sim": 1.0, "title_sim": None, "body_sim": None,
                                                     "rr": 1.0, "excerpt": " ".join((sh.page_bodies().get(u.rstrip("/")) or "").split())[:C.LINK_EXCERPT_CHARS],
                                                     "why_here": "this article already cites this page",
                                                     "kind": "product" if _is_product(u, paths) else "article"})
        cand_by = {(h, c["url"]): c for h, cs in per_sec.items() for c in cs}
        blocks, cand_urls = [], set()
        for s_ in w.get("sections") or []:
            h = s_["heading"]
            cs = per_sec.get(h) or []
            cand_urls |= {c["url"] for c in cs}
            blocks.append(
                "SECTION: %s\nWHAT IT MUST DELIVER: %s\nITS TEXT:\n%s\nPAGES SHORTLISTED FOR THIS SECTION:\n"
                % (h, jobs.get(h, "(not recorded)"), (s_.get("prose") or "")[:2600])
                + ("\n\n".join(
                    "  - [%s] %s · %s\n    MATCH SCORE: %.2f%s\n    WHAT IS ACTUALLY ON THAT PAGE: %s"
                    % (c["kind"].upper(), c["url"], c["title"] or "(no title)", _rank_of(c),
                       (" (%s)" % c["why_here"]) if c.get("why_here") else "",
                       c.get("excerpt") or "(page text unavailable — judge on the title alone, and be stricter)")
                    for c in cs) or "  (none)"))
        say("Choosing the internal links", "%d candidate pages, aiming for about %d links over %d words" % (len(cand_urls), want, words))
        try:
            j1 = llm.json_call(C.prompt("inline-links", brand=brand["brand"], how_many=want,
                                        how_many_low=max(C.MIN_INTERNAL_LINKS, want - 2), words="{:,}".format(words),
                                        sections="\n\n────────────────────────────────────────\n\n".join(blocks))) or {}
        except Exception as e:      # noqa: BLE001
            j1 = {}
            notes.append("the internal-link judge failed: %s" % str(e)[:80])
        raw = [l for l in (j1.get("links") or [])
               if isinstance(l, dict) and l.get("url") in cand_urls and l.get("anchor") and l.get("section")]
        inline = choose_inline(raw)
    else:
        notes.append("internal links and read-more pointers skipped: the page index is not built"
                     + ("" if voyage.available() else " (and no Voyage key is connected)"))
        say("Internal links skipped", notes[-1])

    # ---- JUDGE 2: read-more pointers ----------------------------------------
    pointers, j2 = [], {}
    if have_index:
        rm_c = read_more_candidates(w, own, exclude={l["url"] for l in inline})
        if rm_c:
            try:
                j2 = llm.json_call(C.prompt("read-more", brand=brand["brand"], article=_render_article(article_text(w)),
                                            candidates="\n\n".join("  - %s · %s\n    THE PAGE'S OPENING: %s" % (c["url"], c["title"], c["excerpt"][:2200])
                                                                   for c in rm_c) or "  (none)",
                                            memory=C.sh.memory_block())) or {}
            except Exception:       # noqa: BLE001
                j2 = {}
        rm_urls = {c["url"] for c in rm_c}
        pointers = [p for p in (j2.get("pointers") or []) if valid_pointer(p, rm_urls)][:2]

    # ---- JUDGE 3: external curation -----------------------------------------
    comp = competitor_domains()
    is_comparison = "comparison" in (st.get("format_archetype") or "")
    ext, dropped_comp = [], []
    for u, cs in url_cards.items():
        if "://" not in u:
            continue
        host = u.split("/")[2].lower()
        host = host[4:] if host.startswith("www.") else host
        if own and own in host:
            continue
        if any(host == d or host.endswith("." + d) for d in comp) and not is_comparison:
            dropped_comp.append(u)
            continue
        claims = [("★ " if re.search(r"\d\d", c.get("verbatim") or "") else "") + (c.get("gloss") or "")[:90] for c in cs[:3]]
        ext.append({"url": u, "host": host, "n": len(cs), "claims": claims})
    ext.sort(key=lambda x: -x["n"])
    j3 = {}
    if ext:
        say("Choosing which sources become visible links", "%d cited sources, keeping at most %d" % (len(ext), C.EXTERNAL_LINKS_MAX))
        try:
            j3 = llm.json_call(C.prompt("external-links", brand=brand["brand"], total=len(ext), max=C.EXTERNAL_LINKS_MAX,
                                        candidates="\n".join("  - %s · %s\n    supports %d claim(s): %s" % (e["host"], e["url"], e["n"], " | ".join(e["claims"]))
                                                             for e in ext[:120]) or "  (none)")) or {}
        except Exception:       # noqa: BLE001
            j3 = {}
    ext_urls = {e["url"] for e in ext}
    kept = [k for k in (j3.get("kept") or []) if isinstance(k, dict) and k.get("url") in ext_urls][:C.EXTERNAL_LINKS_MAX]

    # ---- CODE: every chosen link must be ALIVE before anything is inserted ----
    chosen = list(dict.fromkeys([l["url"] for l in inline] + [p["url"] for p in pointers] + [k["url"] for k in kept]))
    with ThreadPoolExecutor(max_workers=8) as ex:
        alive = dict(zip(chosen, ex.map(C.alive, chosen)))
    dead = [u for u, ok in alive.items() if not ok]
    inline = [l for l in inline if alive.get(l["url"])]
    pointers = [p for p in pointers if alive.get(p["url"])]
    kept = [k for k in kept if alive.get(k["url"])]
    if dead:
        say("Dropped links whose page is gone", "%d" % len(dead))

    out, placed, failed, integrity = place_links(w, inline, pointers, kept, cand_by)
    clean = all(i["ok"] for i in integrity)

    cite_keep, n_over = citation_places(out, idx, C.CITATION_MAX_REPEATS, say)
    if n_over:
        say("Thinned the citation markers", "%d source(s) were marked more than %d times" % (n_over, C.CITATION_MAX_REPEATS))
    out["citation_keep"] = {str(c): sorted(v) for c, v in cite_keep.items()}
    out["links"] = {"inline": [p for p in placed if p["kind"] == "inline"],
                    "read_more": [p for p in placed if p["kind"] == "read-more"], "external_kept": kept}
    report = {"own_domain": own, "comparison_article": is_comparison, "page_index": have_index, "notes": notes,
              "citations_thinned": [{"card": c, "kept": len(v)} for c, v in sorted(cite_keep.items())],
              "citation_cap": C.CITATION_MAX_REPEATS, "external_kept": kept, "placed": placed, "failed": failed,
              "inline_rejected": j1.get("rejected") or [], "read_more_rejected": j2.get("rejected") or [],
              "external_rejected": j3.get("rejected_examples") or [], "competitor_urls_blocked": dropped_comp,
              "dead_links_dropped": dead, "integrity": integrity, "integrity_clean": clean,
              "wanted_inline": want, "words": words}
    anchored = [p for p in placed if p["kind"] == "external-anchor"]
    say("Links laid in", "%d internal, %d read-more, %d of %d sources kept as visible links (%d named in the prose); %s"
        % (len(out["links"]["inline"]), len(out["links"]["read_more"]), len(kept), len(ext), len(anchored),
           "nothing else changed" if clean else "a block drifted and was put back"))
    if kept and not anchored:
        say("No kept source became a link in the prose", "the reader sees them only as citation numbers")
    return {"article": out, "report": report}


def choose_inline(raw):
    """CODE: one link per section, never the same url twice, best-reasoned first, capped."""
    inline, seen_sec, seen_url = [], set(), set()
    for l in raw:
        if l["section"] in seen_sec or l["url"] in seen_url:
            continue
        seen_sec.add(l["section"]); seen_url.add(l["url"])
        inline.append(l)
    return inline[:C.INLINE_LINKS_CAP]
