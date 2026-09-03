"""registry.py — the tool list. Costs and gates live HERE, not in the model's head.

The description on each tool is what the model reads to pick it, so each one carries
a RULE, not just a definition. That is the only lever that makes it choose correctly.

`gate` is read by the loop, never by the model:
    auto            just run it (free, read-only, reversible)
    ask_before      stop and ask, with the cost stated (costs money or a lot of time)
    always_approve  stop every time (irreversible)

`owner` on an input: "locked" means the app fills it and the model cannot; "agent"
means the model decides. Identity is always locked. Details are always free.

`module` is the tool's module path relative to this package ("tools.index_site").
loop.py resolves it against the package, so the name never depends on sys.path.
"""

# The three tools that drive the interface. The model sees them as ordinary tools.
UI_TOOLS = [
    {
        "name": "log_step",
        "description": (
            "Tell the user, in ONE short human sentence, what you are about to do. "
            "Call this before anything that takes more than a few seconds. "
            "Write like a colleague ('Reading your site index'), never like code."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "input_schema": {"type": "object", "properties": {
            "message": {"type": "string", "description": "One short sentence, present tense."}
        }, "required": ["message"]},
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question and WAIT for their answer. Use only when the answer "
            "changes what happens next and you cannot work it out yourself. Give 2-4 options, "
            "mark one recommended, and always say WHY you are asking. Do not ask about things "
            "that are free, reversible, or that you could reasonably decide."
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
            "Show the user something you made and wait for them to approve or edit it. "
            "Call this at the end of each stage: after topics, after research, after the "
            "blueprint, after the draft. Returns the artifact, which may have been edited."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": True,
        "input_schema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Artifact filename, e.g. research.json"},
            "view": {"type": "string", "enum": ["topic_list", "research_brief", "blueprint", "article"]},
            "prompt": {"type": "string", "description": "One line asking them to review it."},
        }, "required": ["path", "view", "prompt"]},
    },
    {
        "name": "save_memory",
        "description": (
            "Save a lasting rule the user has stated. Use ONLY when they say something that "
            "should apply to FUTURE articles, not just this one. Never save a one-off "
            "instruction. Tell them you saved it."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "input_schema": {"type": "object", "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["rule", "preference"]},
        }, "required": ["text"]},
    },
]

# The work tools. Each wraps one engine.
WORK_TOOLS = [
    {
        "name": "index_site",
        "description": (
            "Crawl this company's website and catalogue every page: what it covers, how long "
            "it is, and what it ranks for. Run this ONCE at setup. Everything else depends on "
            "it, so if there is no site index yet, run this FIRST before anything else."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 5, "module": "tools.index_site",
        "input_schema": {"type": "object", "properties": {
            "domain": {"type": "string", "description": "The site to index, e.g. example.com"},
            "max_pages": {"type": "integer", "description": "Cap. Default 300."},
        }, "required": ["domain"]},
        "locked": [],
    },
    {
        "name": "learn_voice",
        "description": (
            "Read the site's own pages and work out how this company writes and what it sells: "
            "tone, sentence style, vocabulary, who they talk to, and what they offer. Run ONCE "
            "at setup, after index_site. Every article is written in this voice."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 4, "module": "tools.learn_voice",
        "input_schema": {"type": "object", "properties": {
            "sample_pages": {"type": "integer", "description": "How many pages to read. Default 8."},
        }},
        "locked": [],
    },
    {
        "name": "suggest_topics",
        "description": (
            "Study ONE competitor's best-performing pages and propose six topics this company "
            "could own, each with a distinct angle the competitor has not taken. Rotates through "
            "the competitor list so ideas stay varied. Use when the user has not named a topic."
        ),
        "gate": "ask_before", "cost_credits": 3, "pauses": False,
        "est_minutes": 4, "module": "tools.suggest_topics",
        "input_schema": {"type": "object", "properties": {
            "competitor": {"type": "string", "description": "Optional. Leave empty to rotate."},
        }},
        "locked": [],
    },
    {
        "name": "run_research",
        "description": (
            "Full research for one topic: the best primary keyword with real search volume and "
            "difficulty, the People Also Ask questions, the top ten ranking pages, what they all "
            "cover, and the gap this company could fill. Costs credits. Run once per article, "
            "after the topic is settled."
        ),
        "gate": "ask_before", "cost_credits": 8, "pauses": False,
        "est_minutes": 12, "module": "tools.run_research",
        "input_schema": {"type": "object", "properties": {
            "topic": {"type": "string"},
            "intent": {"type": "string", "enum": ["commercial", "informational", "mixed"],
                       "description": "What kind of reader we want. Default mixed."},
        }, "required": ["topic"]},
        "locked": [],
    },
    {
        "name": "build_blueprint",
        "description": (
            "Turn approved research into an article structure: sections, what each covers, "
            "roughly how long, and which existing pages on the site it should link to. Run "
            "after the user has approved the research brief."
        ),
        "gate": "auto", "cost_credits": 0, "pauses": False,
        "est_minutes": 3, "module": "tools.build_blueprint",
        "input_schema": {"type": "object", "properties": {
            "target_words": {"type": "integer", "description": "Total length. Default 1500."},
        }},
        "locked": [],
    },
    {
        "name": "write_article",
        "description": (
            "Write the full draft from an approved blueprint, in the company's own voice, with "
            "internal links and sources. Takes a while. Run only after the blueprint is approved."
        ),
        "gate": "ask_before", "cost_credits": 0, "pauses": False,
        "est_minutes": 15, "module": "tools.write_article",
        "input_schema": {"type": "object", "properties": {}},
        "locked": [],
    },
]

ALL = UI_TOOLS + WORK_TOOLS
BY_NAME = {t["name"]: t for t in ALL}


def for_model():
    """What the model sees. Costs, gates and modules are stripped — they are ours."""
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


def label(name):
    """A human line for the log when the model did not call log_step first."""
    return {
        "index_site": "Reading the website",
        "learn_voice": "Learning how you write",
        "suggest_topics": "Studying a competitor for topic ideas",
        "run_research": "Researching the topic",
        "build_blueprint": "Building the article structure",
        "write_article": "Writing the draft",
    }.get(name, name.replace("_", " ").capitalize())
