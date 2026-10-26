"""layers/identity/v1.py -- Identity, version 1: the implementation behind the interface's identity entries (PRD A1.18).

Its recipe is v1.json beside it: the Identity engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here: by reference (ref_to), a late-bound delegate
to the body engine_runtime holds today, so the behaviour is exactly what ran before, or as a body of its own where this
version adds to it (A1.19: a name a layer changes is copied here and changed here): the handler Hear a doubt (identity_doubt,
PRD M3.9) and the two steps that tell it the owner's answer (identity_read and identity_file, which hand every other
word on to the body engine_runtime holds). WORDS and LAYOUT hold the words of every part of Identity's prompts (I2), so none
is read from the .md bundle. view() returns the pane's read model by reference (I3).
"""
import re

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'identity'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'

#: the steps of v1.json that run code (the gates' rules and every handler's code steps), by the body they name
CODE = {
    'identity_gate': ref_to('identity_gate'),
    'identity_wait_engine': ref_to('identity_wait_engine'),
    'hear': ref_to('hear'),
    'identity_route': ref_to('identity_route'),
    'identity_hand': ref_to('identity_hand'),
    'identity_verdict': ref_to('identity_verdict'),
    'identity_rung': ref_to('identity_rung'),
    'identity_apply': ref_to('identity_apply'),
    'identity_drop': ref_to('identity_drop'),
    'identity_finding': ref_to('identity_finding'),
    'identity_alarm': ref_to('identity_alarm'),
    'identity_idea': ref_to('identity_idea'),
    'identity_lost': ref_to('identity_lost'),
    'identity_engine': ref_to('identity_engine'),
    'identity_line': ref_to('identity_line'),
    'identity_closed': ref_to('identity_closed'),
}
#: the prompts its soft steps send, and the plain drafts they fall to offline
PROMPT = {
    'identity_gate_soft': ref_to('p_identity_gate'),
    'identity_recognise': ref_to('p_identity_recognise'),
    'identity_take': ref_to('p_identity_take'),
    'identity_enough': ref_to('p_identity_enough'),
    'identity_answer': ref_to('p_identity_answer'),
    'identity_rule': ref_to('p_identity_rule'),
    'identity_weigh': ref_to('p_identity_weigh'),
    'identity_close': ref_to('p_identity_close'),
}
DRAFT = {
    'identity_gate_draft': ref_to('d_identity_gate'),
    'identity_recognise_draft': ref_to('d_identity_recognise'),
    'identity_take_draft': ref_to('d_identity_take'),
    'identity_enough_draft': ref_to('d_identity_enough'),
    'identity_answer_draft': ref_to('d_identity_answer'),
    'identity_rule_draft': ref_to('d_identity_rule'),
    'identity_weigh_draft': ref_to('d_identity_weigh'),
    'identity_close_draft': ref_to('d_identity_close'),
}
#: its covering checks, the shared ones included (S.SHARED_CHECKS)
CHECK = {
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),
    'facts_are_closed': ref_to('c_facts_are_closed'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
    'journey_is_known': ref_to('c_journey_is_known'),
    'verdict_is_known': ref_to('c_verdict_is_known'),
    'enough_is_shaped': ref_to('c_enough_is_shaped'),
    'answer_names_its_source': ref_to('c_answer_names_its_source'),
    'rule_is_tagged': ref_to('c_rule_is_tagged'),
    'feedback_says_what_changes': ref_to('c_feedback_says_what_changes'),
    'gate_verdict_is_known': ref_to('c_gate_verdict_is_known'),
    'ruling_is_known': ref_to('c_ruling_is_known'),
}

# ---- Identity's words (I2, A1.16): the default value of every field of its prompt parts, and the layout that arranges them,
# as `python -m layers.prompts --extract identity` splits them from the .md files by the rule of A1.16 -- the proof, in
# test_layer_prompts and test_layer_identity, is that each part compiles back to the .md part byte for byte. The answer
# contract (S.PROMPTS[...]['returns']) is the interface's and is not here; an owner's change is a typed value over these.
WORDS = {
    'goal': {
        'does': {
            'text': 'holds the goal and the rules, judges every effect, and is the one the owner speaks with',
        },
        'skills': {
            'items': [
                'recognise a task, a query, a directive, feedback or a new idea',
                'judge a request against the goal',
                'gate an effect by rule',
                'put a question to the owner',
            ],
        },
        'close': {},
    },
    'completeness': {
        'thin': {
            'task': 'thin: true when the request names nothing to build from (no subject, no purpose).',
        },
        'enough': {
            'task': (
                "Read who the department is against Identity's standard, and say whether it is enough to start "
                'work on. The standard has five points, and only five:\n'
                'goal: the goal names what the department makes and for whom.\n'
                'items: done-when is a list of items, and each item says how it is checked.\n'
                'rules: every rule is tagged go, ask, refuse or always.\n'
                'owner, budget: the department has an owner and a budget.\n'
                'invented: nothing is invented; a fact the owner did not give is marked to confirm, never stated.'
            ),
        },
    },
    'take': {
        'recognise': {
            'task': (
                'Recognise what kind of words the owner has given. There are five kinds, and only five:\n'
                'task: "do X for me". query: "tell me Y". directive: "from now on, do Z", a standing change to how '
                'the department works or to its goal. feedback: "that was wrong", about work already made. '
                'new-idea: "I want a new capability", something the department cannot do today.'
            ),
        },
        'take': {
            'task': 'Judge one request from the owner.',
            'guidance': (
                'go: do it. ask: it reaches outside what the department makes (money, a message to someone, a '
                'change to the goal), so the owner stamps first. refuse: it breaks a rule. Reading the web is not '
                'outside: the department can read any page.\n'
                'unsure: facts the request says the owner is not sure of, in a few words each; [] when none.\n'
                'rule: a standing rule the request states (always or never, from now on) with its tag; null when '
                'it is one piece of work.'
            ),
        },
        'answer': {
            'task': (
                "Answer the owner's question from the record below, and from nothing else. If the record does not "
                'hold the answer, say so.'
            ),
        },
        'rule': {
            'task': 'The owner has given a directive. Restate it as one rule, in one line, in plain words.',
            'guidance': (
                'tag goal: the directive changes what the department is for. scope one-time: the owner means this '
                'once.'
            ),
        },
        'weigh': {
            'task': 'The owner has given feedback on work the department made. Read what it changes.',
        },
        'gate': {
            'task': 'An engine asks whether it may start.',
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
        'close': (
            'You are Identity of the department "{{dept}}". Adaptation proposed a plan and it did not close '
            'with Priority. Close it against the goal and the rules ONLY; do not invent a rule.\n'
            'THE GOAL: {{goal}}\n'
            'DONE WHEN: {{done}}\n'
            'THE RULES: {{rules}}\n'
            'THE PLAN: {{plan}}\n'
            'WHAT WAS SAID AGAINST IT: {{against}}\n'
            '\n'
            'run: the goal cannot be met without this plan and no rule forbids it. drop: a rule forbids it, or '
            'the goal does not need it. ask: the goal and the rules do not settle it, so the owner must.\n'
            '{returns}'
        ),
    },
    'completeness': {
        'thin': '{task}',
        'enough': (
            '{task}\n'
            "THE OWNER'S WORDS: {{words}}\n"
            'WHAT ROOT ASKED, AND WHAT THE OWNER SAID: {{asked}}\n'
            'THE GOAL: {{goal}}\n'
            'DONE WHEN: {{items}}\n'
            'THE RULES: {{rules}}\n'
            'THE OWNER: {{owner}}\n'
            'THE BUDGET: {{budget}}\n'
            'TO CONFIRM: {{confirm}}\n'
            '\n'
            'Ask only for what is missing, in one plain question to the owner, the most important first. Never '
            "ask what the owner's words or Root's questions already answered.\n"
            '{returns}'
        ),
    },
    'take': {
        'recognise': (
            '{task}\n'
            'THE GOAL: {{goal}}\n'
            'THE WORDS: {{words}}\n'
            'READ BY CODE: {{facts}}\n'
            '\n'
            '{returns}'
        ),
        'take': (
            '{task}\n'
            'THE GOAL: {{goal}}\n'
            'THE RULES: {{rules}}\n'
            'THE REQUEST: {{words}}\n'
            'READ BY CODE: {{facts}}\n'
            '\n'
            '{returns}\n'
            '{guidance}\n'
            '{{completeness}}'
        ),
        'answer': (
            '{task}\n'
            'THE QUESTION: {{question}}\n'
            'THE RECORD:\n'
            '- {{record}}\n'
            '\n'
            '{returns}'
        ),
        'rule': (
            '{task}\n'
            'THE GOAL: {{goal}}\n'
            'THE RULES TODAY: {{rules}}\n'
            'THE DIRECTIVE: {{words}}\n'
            '\n'
            '{returns} {guidance}'
        ),
        'weigh': (
            '{task}\n'
            'THE PAGES: {{pages}}\n'
            'THE FEEDBACK: {{words}}\n'
            '\n'
            '{returns}'
        ),
        'gate': (
            '{task}\n'
            'THE RULES: {{rules}}\n'
            'THE ENGINE: {{engine}}\n'
            '\n'
            '{returns}'
        ),
    },
}

# ---- Hear a doubt (PRD M3.9; J2B-7, J2B-8) -----------------------------------------------------------------------------
# Adaptation shaped a plan it is not sure of and posts inform/doubt, which ends the bargain, nothing registered. Identity
# decides what happens next, in code. In the department's cycle it puts the doubt to the owner once, as one question built
# here (J2B-8: it shows no number and names no internal part), and the owner's answer, or 'just do it', which takes the
# fallback, goes back to Adaptation as a new line request that carries it. One question a line request and S.REPAIRS a
# cycle; past either, Identity tells Adaptation to go on to Priority with the doubt named (a line request marked go_on),
# and a doubt that comes back after that is a blocked plan with a way out, never a loop (rule 8: what Identity cannot
# settle goes to the owner).
#: what the plan goes on with when a doubt names no fallback, or one that would reach outside the site or that the owner
#: cannot be told in plain words; and what the question says of a doubt it cannot put in the owner's words
FALLBACK = "I go ahead with the plan as it stands, and nothing in it reaches outside the site"
SOMETHING = "one thing in the plan rests on something only you can say."
QUESTION = 'Before I set up the work for %s: %s Unless you say, %s. Answer in your own words, or say "just do it".'


def _said(text, n):
    return " ".join(str(text or "").split())[:n]


#: What the owner may not read in a doubt or a fallback a model wrote (J2B-8: it shows no number and names no internal part): the
#: confidence, as the word or as a figure (0.45, .45, 45%, 45 percent), the parts by name (Adaptation, Priority, Coordination, Audit)
#: and the app's own words for its insides (engine, envelope, workflow, charter, refuse). A figure of the owner's own work (three
#: pages, Class 8.5) is theirs, and so is a search engine; neither is matched.
INSIDE = re.compile(r"(?i:confiden)|(?<![\w.])0?\.\d+(?![\w.])|(?i:\d+\s*(?:%|per\s?cent))|\b(?:Adaptation|Priority|Coordination|Audit)\b|"
                    r"(?i:\b(?:engines?|envelopes?|workflows?|charter|internal system|refus\w*)\b)")
SEARCH_ENGINE = re.compile(r"\bsearch engines?\b", re.I)


def inside(text):
    """What in `text` the owner may not read of the app's inside (INSIDE), as the words that match; [] when it is clean."""
    return [m.group(0) for m in INSIDE.finditer(SEARCH_ENGINE.sub("", str(text or "")))]


def _plain_or(ref, text, otherwise):
    """`text` as the owner may read it (M3.6, J2B-8): as it is, or said again in the owner's words; `otherwise` when it still
    breaks the plain-words rule (a doubt a model wrote may say 'grant' or 'counter', as a card or a tell may not) or shows
    the confidence or a part of the app (inside())."""
    line, _, how = R._plain_one(text, R._owners_words(ref, {}), "")
    return otherwise if how == "template" or inside(line) else line


def fallback_of(ref, payload):
    """What the plan does when the owner says nothing more: the doubt's own fallback, unless it says nothing, reaches
    outside the site (the fallback never does) or cannot be told to the owner in plain words."""
    f = _said(payload.get("fallback"), 600).rstrip(".")
    return FALLBACK if not f or R.LEAVES.search(f) else _plain_or(ref, f, FALLBACK)


def question(name, doubt, fallback):
    """J2B-8, built by code from the doubt and its fallback: the owner reads no number and no part of the app."""
    doubt = _said(doubt, 600)
    return QUESTION % (name, doubt + ("" if doubt[-1:] in (".", "?", "!") else "."), fallback.rstrip("."))


def _line_request_of(ref):
    """The last line request Identity made of Adaptation, as a board post, or None."""
    return next((q for q in reversed(R.board(ref)) if q["src"] == "Identity" and q["dst"] == ["Adaptation"] and q["msg_type"] == "request"
                 and (q.get("payload") or {}).get("word") == "line"), None)


def _line(ref, words, **more):
    """A line request, as engine_runtime._line_request makes it, with what a doubt adds."""
    return dict({"word": "line", "words": words, "objective": "propose the workflows the goal needs",
                 "output": "the engines, each with what it does, reads and writes", "may_read": ["Brief"],
                 "boundaries": "nothing runs before Priority grants it and Root registers it", "for": None, "faults": []}, **more)


def identity_doubt(ctx, step, item):
    """Adaptation's doubt (inform/doubt): asked of the owner once, or Adaptation told to go on with it named."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    pl = p.get("payload") or {}
    doubt, engine, fallback = _said(pl.get("doubt"), 600), _said(pl.get("engine"), 40), fallback_of(ref, pl)
    if not doubt:
        return {"said": "heard a doubt with nothing in it; nothing to ask"}
    cj = R._j2()
    cycle = ((cj._state(ref) or {}).get("cycle_id") if cj and cj.active(ref) else None)
    line = _line_request_of(ref)
    asked = [a for a in W.asks(ref) if cycle and a.get("kind") == "j2_identity" and a.get("missing") == "plan" and a.get("cycle_id") == cycle]
    here = [a for a in asked if line and (a.get("doubt") or {}).get("line") == line["n"]]
    if any(a["status"] == "pending" for a in here):
        return {"said": "heard a doubt the owner is asked about already; waiting for the answer"}
    if cj and cj.waiting_on_owner(ref):
        # one open question at a time: the plan is shaped again when that is answered, and the doubt comes with it if it stands
        return {"said": "the owner has another question open; the doubt waits for the plan to be shaped again"}
    if cycle and not here and len(asked) < S.REPAIRS:
        return _ask_the_owner(ctx, cycle, doubt, engine, fallback, line)
    return _go_on(ctx, doubt, fallback, line)


def _ask_the_owner(ctx, cycle, doubt, engine, fallback, line):
    """The doubt as one question of Identity's, an ask that takes words and holds the cycle at step 2 until it is answered."""
    ref, d = ctx["ref"], ctx["dept"]
    cj = R._j2()
    shown = _plain_or(ref, doubt, SOMETHING)
    said = R.plain_card(ref, {"text": question(d.get("name"), shown, fallback),
                              "why": "the plan rests on something only you can say"}, "question")
    with W._lock(ref):
        ask = dict(W.j2_identity_ask(said["text"], cycle, "plan", said["why"], ["plan"], False),
                   doubt={"engine": engine, "doubt": doubt, "shown": shown, "fallback": fallback, "line": line["n"] if line else None})
        W._put_ask(ref, ask)
        cj.note(ref, 2, "Identity", "User", "identity.questioned", "waiting", said["text"], "identity-doubt-" + ask["id"],
                {"missing": ["plan"], "why": said["why"], "standard": False})
        cj._move(ref, "waiting", step=2, open_ask=ask["id"])
    # the line names its card, and the chat leaves the question to the card, which says it once (M0.6)
    R._tell(ref, d, {"src": "Root" if d.get("root") else R.OWNER}, "inform", {"word": "question", "done": said["text"], "card": ask["id"]})
    return {"said": "asked the owner what Adaptation doubts%s: %s" % (" of " + engine if engine else "", doubt[:160]), "asked": ask["id"]}


def _go_on(ctx, doubt, fallback, line):
    """Past the bound: Adaptation goes on to Priority with the doubt named. A doubt that comes back after Adaptation was
    told so is the owner's, as a blocked plan with its ways out."""
    ref, d = ctx["ref"], ctx["dept"]
    who = {"src": "Root" if d.get("root") else R.OWNER}
    if line and (line.get("payload") or {}).get("go_on"):
        shown = _plain_or(ref, doubt, SOMETHING)
        R._blocked(ref, d, who, "The plan cannot go on as it is: it rests on something nobody has settled. %s Say what to do, or choose a way "
                   "forward on this card." % shown, "The plan has a doubt left.", "Adaptation, still unsure of the plan", shown)
        return {"said": "the doubt came back after Adaptation was told to go on; put to the owner as a blocked plan: " + doubt[:160]}
    words = R._brief_text(ref).strip() or str((line or {}).get("payload", {}).get("words") or d.get("goal") or "")
    R.post(ref, "Identity", "Adaptation", "request", _line(ref, words, go_on=True, doubt=doubt, fallback=fallback))
    shown = _plain_or(ref, doubt, SOMETHING)
    R._tell(ref, d, who, "inform", {"word": "line", "done": "I have asked what I can, so the plan goes on as it stands, with one doubt left open: %s "
                                    "Unless you say otherwise, %s. Priority and Root check it before anything runs." % (
                                        shown if shown[-1:] in (".", "?", "!") else shown + ".", fallback.rstrip("."))})
    return {"said": "told Adaptation to go on to Priority with the doubt named: " + doubt[:160], "went_on": True}


def _doubt_asked(ctx):
    """The doubt of Adaptation's that the words in this post answer, as the ask holds it: the one a box answer names, else the
    one the cycle waits on when they were said in the chat. None for any other words."""
    ref, aid = ctx["ref"], (ctx["post"].get("payload") or {}).get("answers")
    cj = R._j2()
    if not cj or not cj.enabled():
        return None
    if not aid:
        q = cj.open_question(ref) or {}
        aid = q.get("id") if q.get("missing") == "plan" else None
    return next((a for a in W.asks(ref) if aid and a["id"] == aid and a.get("kind") == "j2_identity" and a.get("missing") == "plan"), None)


def identity_read(ctx, step, item):
    """Read what was said (the body engine_runtime holds), and mark the words that answer Adaptation's doubt: they are no
    new request to recognise and no word on the identity's standard, which was met before the plan was shaped."""
    got = R.identity_read(ctx, step, item)
    ask = _doubt_asked(ctx)
    if ask:
        got.update({"doubt": ask["id"], "answers": None, "assess": False, "later": False, "filled": []})
    return got


def identity_file(ctx, step, item):
    """File what was decided: the answer to a doubt goes back to Adaptation (doubt_answered); any other word, to the body
    engine_runtime holds."""
    got = ctx["bag"]["identity.read"]
    if got.get("doubt"):
        return doubt_answered(ctx, got)
    return R.identity_file(ctx, step, item)


def doubt_answered(ctx, got):
    """The owner's answer to Adaptation's doubt, or 'just do it', which takes the fallback: it joins the Brief with the
    question it answers and goes to Adaptation as a new line request that carries it (the cycle goes back to step 2)."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    words, hurry = got["words"], bool(got.get("hurry"))
    ask = R._j2().took(ref, got["doubt"], words, at=R._words_at(ref, p)) or {}
    meta = ask.get("doubt") or {}
    if meta.get("answered"):
        return {"said": "took words for a doubt that was answered already"}
    doubt, fallback = meta.get("doubt") or "", meta.get("fallback") or FALLBACK
    shown = meta.get("shown") or _plain_or(ref, doubt, SOMETHING)             # the Brief says what the owner was asked, as they read it
    answer = ("going with this: " + fallback.rstrip(".")) if hurry else words
    row = R._file_words(ref, d, "To Identity's question (%s): %s" % (shown.rstrip("?."), answer), "the owner's answer")
    sent = R.post(ref, "Identity", "Adaptation", "request",
                  _line(ref, R._brief_text(ref).strip() or d.get("goal") or words, doubt=doubt, answer=answer[:2000]))   # the Brief keeps all
    with W._lock(ref):
        ask = next((a for a in W.asks(ref) if a["id"] == got["doubt"]), ask)
        ask["doubt"] = dict(meta, answered=(sent or {}).get("n") or True)
        W._put_ask(ref, ask)
    R._tell(ref, d, p, "inform", {"word": "line", "done": ("Just doing it: %s. Adaptation shapes the plan from that; Priority and Root check it "
                                                           "before anything runs." % fallback.rstrip(".")) if hurry else
                                  "Thank you. Adaptation shapes the plan afresh with your answer; Priority and Root check it before anything runs."},
            thread=p["thread"])
    return {"said": "took the owner's %s to Adaptation's doubt and asked Adaptation to shape the plan again: %s" % (
        "'just do it'" if hurry else "answer", answer[:160]), "filed": row["v"]}


#: the bodies of this version's own, in the table beside the references
CODE.update({'identity_read': identity_read, 'identity_file': identity_file, 'identity_doubt': identity_doubt})


def view(ref, d, events, asks):
    """Identity's pane (S.VIEWS['identity'], A1.17; M3.7): functions_view's read model of the record, by reference. It
    reads _identity_part and not _j2_part, which reads the layers' views and would come back here."""
    return FV._identity_part(ref, d, events)
