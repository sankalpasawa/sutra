"""registry.py — the tool list. What each tool does, when it runs, what it needs.

The description on each tool is what the model reads to pick it, so each one carries a
RULE (when to run it, what must come first), not just a definition. That is the only
lever that makes it choose correctly.

No credit gates. Every tool runs when the model calls it; paid steps do their own
DataForSEO balance pre-flight and say plainly when they skipped a paid call. The user is
still in control through the checkpoints: `show_artifact` stops and waits at the brand
pack, the topics, the research brief, the blueprint and the draft.

`gate` is kept for the loop (all "auto" now). `module` is the tool's module path relative
to this package; loop.py resolves it against the package, never against sys.path.

`plain` is what the Tools screen shows the user: one sentence each for what it does,
when it runs, what it needs and how long it takes. Written for a person, not a model.
"""

UI_TOOLS = [
    {
        "name": "log_step",
        "description": (
            "Tell the user, in ONE short human sentence, what you are about to do. Call this "
            "before anything that takes more than a few seconds. Write like a colleague "
            "('Reading your site now'), never like code, and never name a tool."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "input_schema": {"type": "object", "properties": {
            "message": {"type": "string", "description": "One short sentence, present tense."}
        }, "required": ["message"]},
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user ONE question and WAIT. Use only when the answer changes what happens "
            "next and you cannot work it out yourself or from Knowledge. Give 2-4 options, mark "
            "one recommended, say WHY you are asking in one line. Never ask about things that "
            "are free, reversible, or already answered in Knowledge. Never ask two things at once."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": True,
        "input_schema": {"type": "object", "properties": {
            "question": {"type": "string"},
            "why": {"type": "string", "description": "One line on why this answer matters."},
            "options": {"type": "array", "items": {"type": "object", "properties": {
                "label": {"type": "string"}, "note": {"type": "string"},
                "recommended": {"type": "boolean"}}}},
        }, "required": ["question", "why"]},
    },
    {
        "name": "show_artifact",
        "description": (
            "Show the user something you made and wait for them to approve or edit it. The five "
            "checkpoints: the brand pack after setup (view brand_pack, path brand), the topics "
            "(topic_list, topics.json), the research brief (research_brief, research.json), the "
            "blueprint (blueprint, blueprint.json) and the draft (article, draft.md). Returns the "
            "artifact, which may have been edited."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": True,
        "input_schema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Artifact filename, e.g. research.json; 'brand' for the brand pack"},
            "view": {"type": "string", "enum": ["brand_pack", "topic_list", "research_brief", "blueprint", "article"]},
            "prompt": {"type": "string", "description": "One line asking them to review it."},
        }, "required": ["path", "view", "prompt"]},
    },
    {
        "name": "save_memory",
        "description": (
            "Save a lasting rule the user has stated. Use ONLY when they say something that "
            "should apply to FUTURE articles, not just this one ('never open with a question'). "
            "Never save a one-off instruction. Tell them you saved it. Saved rules reach every "
            "step that shapes or writes prose."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "input_schema": {"type": "object", "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["rule", "preference"]},
        }, "required": ["text"]},
    },
]

WORK_TOOLS = [
    {
        "name": "index_site",
        "description": (
            "Catalogue the company's whole website: every page, its full text with headings, "
            "and what each page ranks for. Finds pages from the CMS, the sitemaps, the web "
            "archive and a crawl, and checks its own coverage. Run ONCE at setup, FIRST, as soon "
            "as you know the domain. Takes a while on a big site; it reports progress."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 15, "module": "tools.index_site",
        "input_schema": {"type": "object", "properties": {
            "domain": {"type": "string", "description": "The site, e.g. example.com"},
            "max_pages": {"type": "integer", "description": "Cap on pages read. Default 3000."},
        }, "required": ["domain"]},
        "plain": {
            "does": "Reads the whole website and saves every page's text, headings and rankings.",
            "when": "Once, at setup, as soon as you give the website.",
            "needs": "The website address. DataForSEO for the rankings (optional).",
            "takes": "A few minutes for a small site, longer for thousands of pages.",
        },
    },
    {
        "name": "build_page_index",
        "description": (
            "Embed every page's title and text so later steps can find the company's own pages "
            "by MEANING: internal links, related pages, reuse checks. Run ONCE at setup, right "
            "after index_site. Needs a Voyage key in Connections; if there is none, say so and "
            "carry on without it (links then fall back to weaker matching)."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 8, "module": "tools.build_page_index",
        "input_schema": {"type": "object", "properties": {
            "rebuild": {"type": "boolean", "description": "Throw the old index away first. Default false."},
        }},
        "plain": {
            "does": "Turns every page into numbers that capture its meaning, so the agent can find the right page to link to.",
            "when": "Once, after the site is read. Again only if the site changes a lot.",
            "needs": "A Voyage key (free tier is enough).",
            "takes": "About a minute per thousand pages.",
        },
    },
    {
        "name": "learn_brand",
        "description": (
            "Build the brand pack from the company's own pages: how they write, what they sell, "
            "who they write for, their real numbers and customer stories, the words they never "
            "use, the pages a call to action may link to, and the one-page writer brief every "
            "article is written from. Run ONCE at setup, after index_site (and build_page_index "
            "if there is a key). Then show_artifact the brand pack so the user confirms the "
            "flagged rows."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 20, "module": "tools.learn_brand",
        "input_schema": {"type": "object", "properties": {
            "redo": {"type": "boolean", "description": "Rebuild files that already exist. Default false."},
            "only": {"type": "string", "description": "Rebuild one builder only, e.g. persona."},
        }},
        "plain": {
            "does": "Learns the brand from its own site: voice, style, products, readers, numbers, stories, and writes the brief the writer follows.",
            "when": "Once, after the site is read. Rebuild a piece when the site changes.",
            "needs": "The site catalogue.",
            "takes": "Ten to twenty minutes. It reads a lot of pages.",
        },
    },
    {
        "name": "suggest_topics",
        "description": (
            "Propose six topics this company could own, each with an angle competitors have not "
            "taken, from one competitor's best pages and what this site already covers. Use when "
            "the user has not named a topic. Then show_artifact the list so they pick one."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 4, "module": "tools.suggest_topics",
        "input_schema": {"type": "object", "properties": {
            "competitor": {"type": "string", "description": "Optional. Leave empty to rotate."},
        }},
        "plain": {
            "does": "Suggests six article topics with an angle no competitor has taken.",
            "when": "When you have not decided what to write about.",
            "needs": "The site catalogue and a competitor list.",
            "takes": "A few minutes.",
        },
    },
    {
        "name": "run_research",
        "description": (
            "Research one topic the way the content machine does: state what the topic is and is "
            "not about, buy real keyword numbers, pick the primary keyword with the world check, "
            "read the live search results and the pages that win, gather evidence cards with "
            "verbatim quotes and sources, fill the gaps, find the company's own pages that belong "
            "in this article, and write the brief. Run once per article after the topic is "
            "settled. Then show_artifact the research brief."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 20, "module": "tools.run_research",
        "input_schema": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "The working title."},
            "angle": {"type": "string", "description": "The angle, if the user gave one."},
        }, "required": ["topic"]},
        "plain": {
            "does": "Researches one topic: real keyword numbers, who ranks, what they cover, the gap, evidence with sources, and which of your pages belong in it.",
            "when": "Once per article, after the topic is chosen.",
            "needs": "DataForSEO with balance for the keyword numbers. The page index for your own pages.",
            "takes": "Fifteen to thirty minutes.",
        },
    },
    {
        "name": "build_blueprint",
        "description": (
            "Turn the approved research into the article's structure: keep only the evidence that "
            "serves the spine, group it into sections and sub-sections with headings, attach the "
            "internal and external links, the FAQ and the keyword set. Run after the user approves "
            "the research brief. Then show_artifact the blueprint."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 8, "module": "tools.build_blueprint",
        "input_schema": {"type": "object", "properties": {}},
        "plain": {
            "does": "Builds the article plan: sections, sub-sections, which facts go where, which pages to link.",
            "when": "After you approve the research.",
            "needs": "The research and the evidence cards.",
            "takes": "Five to ten minutes.",
        },
    },
    {
        "name": "write_article",
        "description": (
            "Write the article from the approved blueprint the way the write phase does: plan and "
            "verify sources, shape it for its format, place brand facts, buy section keywords, "
            "write each section from its own facts in the writer brief's voice, then edit for "
            "length, coherence, readability and AI tells, lay in internal links by meaning, and "
            "assemble with sources. Takes a long time. Run only after the blueprint is approved. "
            "Then show_artifact the draft."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 45, "module": "tools.write_article",
        "input_schema": {"type": "object", "properties": {}},
        "plain": {
            "does": "Writes the whole article from the plan, edits it in several passes, adds links to your own pages and lists the sources.",
            "when": "After you approve the plan.",
            "needs": "The plan, the writer brief and the page index for links.",
            "takes": "Thirty minutes to an hour.",
        },
    },
]

ALL = UI_TOOLS + WORK_TOOLS
BY_NAME = {t["name"]: t for t in ALL}


def for_model():
    """What the model sees. Gates, costs, modules and the plain text are stripped."""
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in ALL]


def get(name):
    return BY_NAME.get(name)


def pauses(name):
    t = get(name)
    return bool(t and t.get("pauses"))


def gate(name):
    t = get(name)
    return t.get("gate", "auto") if t else "auto"


def cost(name):
    t = get(name)
    return t.get("cost_credits", 0) if t else 0


def est_minutes(name):
    t = get(name)
    return t.get("est_minutes", 0) if t else 0


LABELS = {
    "index_site": "Reading the website",
    "build_page_index": "Indexing the pages by meaning",
    "learn_brand": "Learning the brand",
    "suggest_topics": "Finding topic ideas",
    "run_research": "Researching the topic",
    "build_blueprint": "Building the article plan",
    "write_article": "Writing the article",
}


def label(name):
    """A human line for the log when the model did not call log_step first."""
    return LABELS.get(name, name.replace("_", " ").capitalize())


def for_screen():
    """The Tools screen: one row per work tool, in plain words."""
    return [{"name": t["name"], "label": label(t["name"]), "est_minutes": t.get("est_minutes", 0),
             **(t.get("plain") or {})} for t in WORK_TOOLS]
