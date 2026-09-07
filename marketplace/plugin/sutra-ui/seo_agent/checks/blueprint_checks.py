"""blueprint_checks.py — catch a bad plan before anyone spends fifteen minutes writing from it.

The blueprint is the cheapest place in the run to be wrong, and every fault in it multiplies.
A section with no brief becomes a padded section. Two overlapping sections become two
paragraphs saying the same thing in different words. A word budget that does not add up
becomes an article half the length that was asked for. All of it is free to catch here and
expensive to catch after the draft exists.

The invented-link check is the one that earns this file. A model asked for internal links
produces plausible URLs whether or not they exist, and a plausible URL is exactly the kind of
mistake that survives a human review and ships as a 404. site_index.json is the only record of
which pages are real, so it is the only thing this file will believe.
"""
from . import ai_writing, artifact, item, norm_url, overlap, primary_keyword, result, site_urls, tokens

DUPLICATE_OVERLAP = 0.6      # above this, two sections are covering the same ground
BUDGET_TOLERANCE = 0.20      # the summed word budget may miss the target by this much
DEFAULT_TARGET_WORDS = 0     # 0 means "no target stated", which skips the budget check


# ---- reading the blueprint -----------------------------------------------------------------

def sections(blueprint):
    s = (blueprint or {}).get("sections")
    return [x for x in s if isinstance(x, dict)] if isinstance(s, list) else []


def section_id(section, index):
    return str(section.get("id") or "s%d" % (index + 1))


def section_where(section, index):
    """Locate a section the way the user sees it, by heading, with the id as the fallback."""
    heading = (section.get("heading") or "").strip()
    sid = section_id(section, index)
    return "%s (%s)" % (heading, sid) if heading else sid


def covers_text(section):
    for key in ("covers", "brief", "summary"):
        v = section.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def section_links(section):
    """Links come as {url, anchor} objects from the blueprint prompt, but a hand-edited
    blueprint often carries bare strings. Both are read rather than one being rejected."""
    raw = section.get("internal_links") or section.get("links") or []
    out = []
    if isinstance(raw, dict):
        raw = [raw]
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            out.append({"url": entry, "anchor": ""})
        elif isinstance(entry, dict) and entry.get("url"):
            out.append({"url": str(entry["url"]), "anchor": str(entry.get("anchor") or "")})
    return out


def section_words(section):
    for key in ("words", "word_budget", "target_words", "length"):
        v = section.get(key)
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
    return 0


def target_words(blueprint, ctx=None):
    """The stated total. Absent, the budget check reports rather than inventing a number."""
    ctx = ctx or {}
    for source in (blueprint or {}, ctx):
        for key in ("target_words", "target_word_count", "total_words"):
            v = (source or {}).get(key)
            if isinstance(v, (int, float)) and v > 0:
                return int(v)
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
    state = artifact(ctx, "state.json")
    if isinstance(state, dict) and isinstance(state.get("target_words"), int):
        return state["target_words"]
    return DEFAULT_TARGET_WORDS


# ---- the checks ------------------------------------------------------------------------------

def check_covers(blueprint):
    """A section with no brief is a section the writer will pad, because nobody told it what
    to say. This is the single most common way a blueprint fails quietly."""
    secs = sections(blueprint)
    if not secs:
        return result("sections_have_covers", "fail", "The blueprint has no sections.", [])
    bad = []
    for i, s in enumerate(secs):
        text = covers_text(s)
        if not text:
            bad.append(item(section_where(s, i), "covers is empty",
                            "Write two or three sentences saying what this section argues, "
                            "and in what order."))
        elif len(text.split()) < 8:
            bad.append(item(section_where(s, i), '"%s"' % text,
                            "Too thin to write from. Name the specific points, not the topic."))
    if any(b["what"] == "covers is empty" for b in bad):
        return result("sections_have_covers", "fail",
                      "%d of %d sections have no brief." % (len(bad), len(secs)), bad)
    if bad:
        return result("sections_have_covers", "warn",
                      "%d of %d briefs are too thin to write from." % (len(bad), len(secs)), bad)
    return result("sections_have_covers", "pass",
                  "All %d sections have a brief." % len(secs), [])


def check_internal_links(blueprint, known_urls, domain):
    """Only a URL in the crawl is real. Everything else is the model being helpful."""
    secs = sections(blueprint)
    all_links = [(i, s, l) for i, s in enumerate(secs) for l in section_links(s)]
    if not all_links:
        return result("internal_links_exist", "pass", "No internal links to check.", [])
    if not known_urls:
        return result("internal_links_exist", "warn",
                      "%d internal links, but there is no site index to check them against. "
                      "Run index_site." % len(all_links), [])
    bad = []
    for i, s, link in all_links:
        if norm_url(link["url"], domain) not in known_urls:
            bad.append(item(section_where(s, i), link["url"],
                            "Not a page on this site. Use a URL from the site index or drop "
                            "the link."))
    if bad:
        return result("internal_links_exist", "fail",
                      "%d of %d internal links point at pages that do not exist."
                      % (len(bad), len(all_links)), bad)
    return result("internal_links_exist", "pass",
                  "All %d internal links exist on the site." % len(all_links), [])


def check_no_duplicate_sections(blueprint, threshold=DUPLICATE_OVERLAP):
    """Two sections covering the same ground is the outline equivalent of saying it twice."""
    secs = sections(blueprint)
    profiles = [(i, s, tokens((s.get("heading") or "") + " " + covers_text(s))) for i, s in enumerate(secs)]
    dupes = []
    for a in range(len(profiles)):
        for b in range(a + 1, len(profiles)):
            score = overlap(profiles[a][2], profiles[b][2])
            if score > threshold:
                dupes.append(item(
                    "%s and %s" % (section_where(profiles[a][1], profiles[a][0]),
                                   section_where(profiles[b][1], profiles[b][0])),
                    "%.0f%% of their words overlap" % (score * 100),
                    "Merge them, or give each a distinct job the other does not do."))
    if dupes:
        return result("no_duplicate_sections", "warn",
                      "%d pair(s) of sections cover much the same ground." % len(dupes), dupes)
    return result("no_duplicate_sections", "pass",
                  "No two sections overlap by more than %.0f%%." % (threshold * 100), [])


def check_word_budget(blueprint, target, tolerance=BUDGET_TOLERANCE):
    secs = sections(blueprint)
    total = sum(section_words(s) for s in secs)
    missing = [item(section_where(s, i), "no word budget", "Give this section a word count.")
               for i, s in enumerate(secs) if section_words(s) <= 0]
    if not target:
        return result("word_budget_matches_target", "pass",
                      "Sections total %d words. No target was stated, so nothing to compare."
                      % total, missing)
    if missing:
        return result("word_budget_matches_target", "warn",
                      "%d sections carry no word budget, so the total of %d cannot be trusted."
                      % (len(missing), total), missing)
    drift = abs(total - target) / float(target)
    if drift > tolerance:
        return result("word_budget_matches_target", "warn",
                      "Sections total %d words against a target of %d, out by %.0f%%."
                      % (total, target, drift * 100),
                      [item("whole blueprint", "%d vs %d words" % (total, target),
                            "Adjust the section budgets until they land within %.0f%% of the "
                            "target." % (tolerance * 100))])
    return result("word_budget_matches_target", "pass",
                  "Sections total %d words against a target of %d." % (total, target), [])


def check_primary_keyword(blueprint, keyword):
    """The keyword has to appear in the plan, or the writer has no reason to use it."""
    if not keyword:
        return result("primary_keyword_placed", "pass",
                      "No primary keyword on record, so there is nothing to place.", [])
    needle = " ".join(keyword.lower().split())
    key_tokens = set(tokens(keyword))
    places = []
    for i, s in enumerate(sections(blueprint)):
        places.append((section_where(s, i), (s.get("heading") or "") + " " + covers_text(s)))
    title = (blueprint or {}).get("title") or ""
    if title:
        places.append(("title", title))

    for where, text in places:
        if needle in " ".join(text.lower().split()):
            return result("primary_keyword_placed", "pass",
                          'The primary keyword "%s" appears in %s.' % (keyword, where), [])
    for where, text in places:
        if key_tokens and key_tokens <= set(tokens(text)):
            return result("primary_keyword_placed", "warn",
                          'The primary keyword "%s" appears only reworded, in %s.'
                          % (keyword, where),
                          [item(where, '"%s"' % text.strip()[:90],
                                "Use the exact phrase once, where it reads naturally.")])
    return result("primary_keyword_placed", "fail",
                  'The primary keyword "%s" is in no heading, brief or title.' % keyword,
                  [item("whole blueprint", '"%s" appears nowhere' % keyword,
                        "Put it in the title and in the first section's brief.")])


# ---- the run ---------------------------------------------------------------------------------

def run(blueprint, previous=None, ctx=None):
    """Every blueprint check, in the order a person would read them: does it have substance,
    is what it points at real, is it repeating itself, does it add up, is it on keyword."""
    ctx = ctx or {}
    blueprint = blueprint or {}
    known_urls, domain = site_urls(ctx)

    results = [
        check_covers(blueprint),
        check_internal_links(blueprint, known_urls, domain),
        check_no_duplicate_sections(blueprint),
        check_word_budget(blueprint, target_words(blueprint, ctx)),
        check_primary_keyword(blueprint, primary_keyword(ctx, blueprint)),
    ]

    # The headings and briefs are prose the reader will meet as headings, so they get the same
    # writing scan the draft gets. Sections are the unit here, so a finding says "section 3".
    plan_text = "\n\n".join(
        ((s.get("heading") or "") + ". " + covers_text(s)).strip()
        for s in sections(blueprint))
    if plan_text.strip():
        from . import brand_voice
        results.append(ai_writing.check(plan_text, brand_voice(ctx), unit_label="section"))
    return results
