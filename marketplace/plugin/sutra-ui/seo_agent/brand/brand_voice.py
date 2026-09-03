"""brand/brand_voice.py — builder 2: how this company sounds, drawn from its own pages.

Port of 1-brand-voice (shortlist.py, read_pages.py, assemble.py, quality_gate.py, run_brand_voice.py).

Step 0  shortlist the voice pages. Code builds the candidate table (top-traffic winners + the
        commercial and positioning pages raw traffic misses); the model picks 20-40; code writes
        brand/page-shortlist.md. An existing shortlist is a curated INPUT and is reused.
Step 1  one evidence row per page (model per page, resumable, thin pages recorded not guessed).
Step 2  assemble brand-voice.md from the evidence: pure assembly against the recipe's Appendix A
        schema and its Step-2 mapping table, both lifted verbatim. The first assembly also drafts
        the one-liner and niche definition into company.json, only where those are still empty.
Step 3  the quality gate: the model judges completeness, depth and specificity; code adds the one
        check a model misses, leftover [BRACKET] placeholders. Fail -> back to step 2, capped.

Reads:  the catalogue, knowledge/top-pages.json, brand/type-roles.json, brand/company.json.
Writes: brand/page-shortlist.md · brand/_work/brand-voice/{evidence.json, gate-round-N.json,
        oneliner-draft.json} · brand/brand-voice.md
"""
import re

from .. import llm
from .. import store
from ..tools import _shared as sh
from . import _common as cm

OUTPUT = "brand-voice.md"
SHORTLIST = "page-shortlist.md"
WORK = "_work/brand-voice/"

# --- shortlist knobs -------------------------------------------------------------------------
SHORTLIST_MIN, SHORTLIST_MAX = 20, 40      # the recipe's page-count band
CAND_TOP_TRAFFIC = 80        # top-traffic candidates shown to the picker
CAND_COMMERCIAL = 300        # commercial candidates shown; ALL shallow ones always make it (the ones raw traffic misses)
THIN_WORDS = 150             # a page body under this = thin; recorded as thin, weighed lightly, never guessed at

# --- read/assemble knobs ---------------------------------------------------------------------
BV_BODY_CAP = 14000          # chars of one page body per evidence prompt
GATE_MAX_ROUNDS = 3          # assemble->gate loop cap (the recipe loops until pass)

_COMMERCIAL_HINT = re.compile(r"pricing|compare|plans|alternatives|-vs-|why-|integrations?|demo|features?", re.I)
_URL_RE = re.compile(r"https?://[^\s)·]+")
_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z /·&-]{2,}\]")
EVIDENCE_FIELDS = [("voice_tone", "Voice & tone"), ("positioning", "Positioning"),
                   ("audience_pain", "Audience & pain"), ("quotable", "Quotable (verbatim)"),
                   ("style_format_cta", "Style · format · CTA"), ("company_dimension", "Company dimension")]


# ---- step 0: shortlist -----------------------------------------------------------------------

def _candidates(co, cat, tmap, say):
    """Top-traffic winners + the commercial/positioning pages raw traffic misses. The model picks
    from what it is shown, so the shown set must contain both halves."""
    ranked = sorted(cat.values(), key=lambda r: cm.traffic_of(r, tmap), reverse=True)
    shown = ranked[:CAND_TOP_TRAFFIC]
    roles = cm.roles()
    ctypes = set(roles.get("commercial_types", [])) if roles else set()
    if roles:
        say("Commercial page types", "classified for this company: %s" % sorted(ctypes))
    else:
        say("Commercial page types", "no type roles on file, so commercial candidates come from URL patterns only")
    primary = (co.get("language_code") or "en")[:2]
    shown_urls = {r["url"] for r in shown}
    # EVERY shallow primary-language commercial-type page is ALWAYS shown: the company's core positioning
    # pages (/pricing/, /why-us/) are shallow and often zero-traffic, and a traffic-ordered cap hid them
    # from the picker twice in the original's runs. Deeper hint-matchers fill the rest.
    core = [r for r in cat.values()
            if r["url"] not in shown_urls and r.get("type") in ctypes and cm.depth1(r["url"])
            and (r.get("lang") or primary)[:2] == primary]
    core_urls = {r["url"] for r in core}
    deep = [r for r in cat.values()
            if r["url"] not in shown_urls and r["url"] not in core_urls
            and (r.get("type") in ctypes or _COMMERCIAL_HINT.search(r["url"]))]
    deep.sort(key=lambda r: -cm.traffic_of(r, tmap))
    shown = shown + core + deep[:max(0, CAND_COMMERCIAL - len(core))]
    home = next((r for r in cat.values() if cm.is_home(r["url"], co["domain"])), None)
    if home and home["url"] not in {r["url"] for r in shown}:
        shown.append(home)
    return shown


def shortlist(co, say, redo=False):
    if cm.exists(SHORTLIST) and not redo:
        say("Kept the page shortlist", "brand/page-shortlist.md exists (a curated shortlist is input); delete it to regenerate")
        return cm.read(SHORTLIST)
    cat = {r["url"]: r for r in cm.ok_pages(co.get("language_code"))}
    if not cat:
        raise RuntimeError("The site index has no pages with readable text, so no voice pages can be picked.")
    tmap = cm.traffic_map()
    cands = _candidates(co, cat, tmap, say)
    table = "\n".join("%s · %d · %s · %s" % (r.get("type") or "", int(cm.traffic_of(r, tmap)), r["url"], (r.get("title") or "")[:70])
                      for r in cands)
    say("Built the candidate table", "%d pages shown to the picker" % len(cands))
    out = llm.json_call(cm.fill(cm.prompt("pick-pages"), brand=co["brand"], niche=co.get("niche_definition") or "",
                                min=SHORTLIST_MIN, max=SHORTLIST_MAX, candidates=table))
    picks = (out or {}).get("picks", []) if isinstance(out, dict) else []
    picks = [p for p in picks if isinstance(p, dict) and p.get("url") in cat]      # never accept an invented URL
    seen, uniq = set(), []
    for p in picks:
        if p["url"] not in seen:
            seen.add(p["url"])
            uniq.append(p)
    picks = uniq
    band_note = ""
    if not (SHORTLIST_MIN <= len(picks) <= SHORTLIST_MAX):
        band_note = "the picker returned %d pages (the recipe's band is %d-%d); review before trusting" % (len(picks), SHORTLIST_MIN, SHORTLIST_MAX)
        say("Shortlist outside the band", band_note)
    lines = ["# Page shortlist — %s" % co["brand"], "",
             "- **Source:** the site catalogue (the page index + traffic data), picked by the",
             "  shortlist step of the brand-voice builder (criteria: top-traffic winners + deliberately-added",
             "  commercial/positioning pages).",
             "- **The number beside each page = estimated monthly organic traffic.**", ""]
    by_bucket = {}
    for p in picks:
        by_bucket.setdefault((str(p.get("bucket") or "?"), str(p.get("bucket_name") or "")), []).append(p)
    for (b, bn), grp in sorted(by_bucket.items()):
        lines.append("## %s. %s" % (b, bn))
        for p in grp:
            try:
                tr = int(float(p.get("traffic") or 0))
            except (TypeError, ValueError):
                tr = 0
            lines.append("- %s  (%d, %s)" % (p["url"], tr, p.get("note") or ""))
        lines.append("")
    lines.append("---\nThese %d pages are read from the site catalogue by the evidence step." % len(picks))
    text = "\n".join(lines) + "\n"
    cm.save(SHORTLIST, text)
    say("Picked the voice pages", "%d pages -> brand/page-shortlist.md" % len(picks))
    return text


def shortlist_urls(text, domain):
    urls = [u.rstrip(".,)") for u in _URL_RE.findall(text or "")]
    d = (domain or "").lower().replace("www.", "")
    out, seen = [], set()
    for u in urls:
        if d and d not in u.lower():
            continue
        k = u.rstrip("/")
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out


# ---- step 1: evidence -------------------------------------------------------------------------

def _extract(co, url, cat):
    row = cat.get(url) or cat.get(url.rstrip("/")) or cat.get(url.rstrip("/") + "/") or {}
    body = row.get("body") or ""
    thin = len(body.split()) < THIN_WORDS           # thin: recorded, weighed lightly, never guessed at
    out = llm.json_call(cm.fill(cm.prompt("extract-evidence"), brand=co["brand"], url=url, body=body[:BV_BODY_CAP]))
    r = dict(out) if isinstance(out, dict) else {}
    r.update(page=cm.slug(url), url=url, thin=thin)
    return r


def evidence(co, urls, say, redo=False):
    name = WORK + "evidence.json"
    done = {}
    if not redo:
        for r in (cm.read(name) or []):
            if isinstance(r, dict) and r.get("url"):
                done[r["url"].rstrip("/")] = r
    cat = {}
    for r in cm.pages():
        cat[r["url"]] = r
        cat[r["url"].rstrip("/")] = r
    todo = [u for u in urls if u.rstrip("/") not in done]
    say("Reading each page into an evidence row", "%d cached, %d to read, %d at a time" % (len(done), len(todo), llm.PARALLEL))
    for url, res, err in cm.parallel(lambda u: _extract(co, u, cat), todo, say, "Reading voice pages"):
        if err:
            say("Could not read a voice page", "%s: %s" % (url, str(err)[:90]))
        else:
            done[url.rstrip("/")] = res
    rows = [done[u.rstrip("/")] for u in urls if u.rstrip("/") in done]
    cm.save(name, rows)
    thin = sum(1 for r in rows if r.get("thin"))
    say("Evidence table", "%d rows (%d thin pages flagged)" % (len(rows), thin))
    return rows


def _evidence_block(rows):
    out = []
    for r in rows:
        out.append("### %s · %s%s" % (r.get("page", ""), r.get("url", ""), "  [THIN PAGE — weigh lightly]" if r.get("thin") else ""))
        for k, label in EVIDENCE_FIELDS:
            v = str(r.get(k) or "").strip()
            if v:
                out.append("- %s: %s" % (label, v))
        out.append("")
    return "\n".join(out)


# ---- step 2: assemble -------------------------------------------------------------------------

def assemble(co, rows, say, redo_notes=""):
    p = cm.fill(cm.prompt("assemble-voice"), brand=co["brand"], niche=co.get("niche_definition") or "",
                oneliner=co.get("brand_oneliner") or "", schema=cm.template("brand-voice-schema"),
                mapping=cm.template("brand-voice-mapping"), evidence=_evidence_block(rows),
                redo_notes=("\nREDO NOTES from the last quality gate (fix these specifically):\n%s\n" % redo_notes) if redo_notes else "")
    draft = cm.strip_fence(llm.text(p))
    cm.save(OUTPUT, draft)
    say("Assembled brand-voice.md", "%d words%s" % (cm.words(draft), " (rebuilt with the gate's notes)" if redo_notes else ""))
    return draft


def draft_oneliner(co, rows, say):
    """The one-liner + niche DRAFT, once, from the same evidence. Merged into company.json only where
    the record is still empty: a value a person already wrote is never overwritten."""
    name = WORK + "oneliner-draft.json"
    if cm.exists(name):
        return cm.read(name)
    one = llm.json_call(cm.fill(cm.prompt("draft-oneliner"), brand=co["brand"], evidence=_evidence_block(rows)[:20000]))
    one = one if isinstance(one, dict) else {}
    cm.save(name, one)
    rec = store.knowledge("brand/company.json") or {}
    for k in ("brand", "domain", "wordpress_url", "location_name", "language_code", "about"):
        rec.setdefault(k, co.get(k) or "")
    filled = []
    for k in ("brand_oneliner", "niche_definition"):
        if not (rec.get(k) or "").strip() and str(one.get(k) or "").strip():
            rec[k] = str(one[k]).strip()
            co[k] = rec[k]
            filled.append(k)
    store.save_knowledge("brand/company.json", rec)
    say("Drafted the one-liner and niche", ("filled %s in the company record" % ", ".join(filled)) if filled
        else "the company record already had both; the draft is kept beside it")
    return one


# ---- step 3: the gate -------------------------------------------------------------------------

def gate(co, draft, round_n, say):
    verdict = llm.json_call(cm.fill(cm.prompt("voice-quality-gate"), brand=co["brand"], draft=draft))
    verdict = dict(verdict) if isinstance(verdict, dict) else {"sections": [], "overall_pass": False, "redo_notes": ""}
    # the deterministic check code owns: no [BRACKET] placeholder may survive (Appendix A's own rule)
    leftovers = sorted({b for b in _PLACEHOLDER.findall(draft) if b != "[BRACKET]"})
    if leftovers:
        verdict["overall_pass"] = False
        verdict["redo_notes"] = (str(verdict.get("redo_notes") or "") +
                                 "\nUnfilled placeholders survive: %s — fill every one." % ", ".join(leftovers))
    cm.save(WORK + "gate-round-%d.json" % round_n, verdict)
    n_fail = sum(1 for s in (verdict.get("sections") or []) if isinstance(s, dict) and not s.get("pass"))
    say("Quality gate, round %d" % round_n, "%s (%d failing sections%s)"
        % ("pass" if verdict.get("overall_pass") else "fail", n_fail, ", placeholders left" if leftovers else ""))
    return verdict


# ---- the builder ------------------------------------------------------------------------------

def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept brand-voice.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT, SHORTLIST], "needs_review": []}
    notes = []
    text = shortlist(co, say, redo=False)          # a curated shortlist is input even on redo
    urls = shortlist_urls(text, co["domain"])
    if not urls:
        raise RuntimeError("The page shortlist names no pages on %s, so there is nothing to learn the voice from." % co["domain"])
    rows = evidence(co, urls, say, redo=redo)
    if not rows:
        raise RuntimeError("No page could be read into an evidence row.")
    draft = assemble(co, rows, say)
    draft_oneliner(co, rows, say)
    for round_n in range(1, GATE_MAX_ROUNDS + 1):
        verdict = gate(co, draft, round_n, say)
        if verdict.get("overall_pass"):
            break
        if round_n == GATE_MAX_ROUNDS:
            notes.append("brand-voice.md: the quality gate still failed after %d rounds; the draft ships with its verdict (brand/_work/brand-voice/gate-round-%d.json)" % (round_n, round_n))
            break
        draft = assemble(co, rows, say, redo_notes=str(verdict.get("redo_notes") or ""))
    n_flags = cm.count_lines(draft, "⚑ HUMAN DECISION")
    if n_flags:
        notes.append("brand-voice.md: %d ⚑ HUMAN DECISION flags to settle" % n_flags)
    return {"files": [OUTPUT, SHORTLIST], "needs_review": notes}


# ---- the flat profile older code reads (brand_voice.json) ---------------------------------------

def _section(text, heading_re):
    """The body under the first heading (any level) matching heading_re, up to the next heading."""
    m = re.search(r"^#{1,4} [^\n]*?(?:%s)[^\n]*$\n(.*?)(?=^#{1,4} |\Z)" % heading_re, text, re.M | re.S | re.I)
    return m.group(1).strip() if m else ""


def profile(co, text=None):
    """{company, summary, traits, avoid, examples, what_they_sell, who_buys}, derived from
    brand-voice.md by code so loop._system_prompt and _shared.voice_block keep working."""
    text = text if text is not None else cm.read(OUTPUT)
    traits = [m.strip() for m in re.findall(r"^### \d\.\s+(.+?)\s*(?:\(Optional\))?\s*$", text, re.M)]
    traits = [t for t in traits if "[" not in t and "…" not in t][:8]
    tone = _section(text, "General Tone")
    summary = " ".join(ln.strip() for ln in tone.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    if not summary:
        summary = " ".join(text.split()[:80])
    avoid = []
    for m in re.finditer(r"\*\*Avoid\*\*:\s*(.+)", text):
        avoid += [a.strip(" .") for a in re.split(r",|;", m.group(1)) if a.strip(" .")]
    for m in re.finditer(r"^-\s*(.+?)\s*→\s*(.+?)(?:\s*\(|$)", text, re.M):
        avoid.append(m.group(2).strip())
    seen, avoid_u = set(), []
    for a in avoid:
        k = a.lower()
        if k not in seen and 1 < len(a) < 80:
            seen.add(k)
            avoid_u.append(a)
    good = _section(text, r"Excellent .*?Voice|✅") or _section(text, r"Voice Examples")
    examples = [q.strip() for q in re.findall(r"[\"“]([^\"”]{20,400})[\"”]", good)][:3]
    who = ""
    m = re.search(r"\*\*Primary Audience\*\*:\s*(.+)", text)
    if m:
        who = m.group(1).strip()
    return {"company": co.get("brand") or "", "summary": summary, "traits": traits, "avoid": avoid_u[:20],
            "examples": examples, "what_they_sell": co.get("brand_oneliner") or "", "who_buys": who,
            "domain": co.get("domain") or "", "source": "brand/brand-voice.md", "learned_at": store.now()}
