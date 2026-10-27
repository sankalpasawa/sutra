"""layers/identity/v1.py -- Identity, version 1: the implementation behind the interface's identity entries (PRD A1.18).

Its recipe is v1.json beside it: the Identity engine object, moved byte for byte from engine_defs/website.json in wave 0.
Every code, prompt, draft and check name the recipe uses is provided here: by reference (ref_to), a late-bound delegate
to the body engine_runtime holds today, so the behaviour is exactly what ran before, or as a body of its own where this
version adds to it (A1.19: a name a layer changes is copied here and changed here): the handler Hear a doubt (identity_doubt,
PRD M3.9) and the two steps that tell it the owner's answer (identity_read and identity_file, which hand every other
word on to the body engine_runtime holds). Wave 2 adds to it (A1 W2-IDENTITY): the conflict's own ways out reach the owner as one
card, applied by the layer that owns each (identity_closed, identity_apply; M5.4); Hear a reading, where done is read from
Audit's reading and what it leaves open is weighed three ways (identity_done, identity_weigh_reading; M8.4, M8.5); File a
granted round (identity_round; M9.3); and no end of the pursuit is silent (M9.5). WORDS and LAYOUT hold the words of every part of Identity's prompts (I2), so none
is read from the .md bundle. view() returns the pane's read model by reference (I3).
"""
import re
import uuid

import layers
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

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
WORDS['goal']['done'] = {'text': (
    'every request has a verdict and every effect a gate answer, and the goal is said to be reached '
    "only from Audit's reading of every done-when item"
)}
WORDS['goal']['role_is'] = {'text': (
    "the department's voice and conscience; it keeps the department aligned with its goal, its "
    'done-when, its rules and the boundary of what it may decide, and it is the only function that '
    'speaks to the owner'
)}
WORDS['goal']['role_may'] = {'items': [
    'rule that a proposal fits the goal and the rules, or does not',
    'settle a disagreement between Adaptation and Priority within the goal and the rules',
    'say what an existing rule means',
    'stop an action that is unsafe or that no rule lets through',
    'decide whether a finding that matters needs the work done again',
    "say the goal is reached, when Audit's reading of every done-when item supports it",
    'put one question to the owner, with its ways forward, when the goal and the rules cannot decide',
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Name the goal item or the rule that applies.',
    'Separate what is known from what is assumed.',
    'Decide with the authority you already have when you can.',
    'If the evidence is missing but another function can get it, ask for that evidence before asking the owner.',
    (
        'Ask the owner only when the choice changes the purpose, the risk, a commitment outside the '
        'department, or a trade-off of values.'
    ),
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Becoming a general manager who comments on every message.',
    'Treating a personal preference as a rule.',
    'Escalating without giving the ways forward.',
    'Quietly changing what done-when means.',
    "Doing Adaptation's or Audit's work.",
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})

# ---- Hear a doubt (PRD M3.9; J2B-7, J2B-8) -----------------------------------------------------------------------------
# Adaptation shaped a plan it is not sure of and posts inform/doubt, which ends the bargain, nothing registered. Identity
# decides what happens next, in code. In the department's cycle it puts the doubt to the owner once, as one question built
# here (J2B-8: it shows no number and names no internal part), and the owner's answer, or 'just do it', which takes the
# fallback, goes back to Adaptation as a new line request that carries it. One question a line request and S.REPAIRS a
# cycle; past either, Identity tells Adaptation to go on to Priority with the doubt named (a line request marked go_on),
# and a doubt that comes back after that is a blocked plan with a way out, never a loop (rule 8: what Identity cannot
# settle goes to the owner).
#: what the plan goes on with when a doubt names no fallback, or one that would reach outside the department or that the owner
#: cannot be told in plain words; and what the question says of a doubt it cannot put in the owner's words. A website is the
#: owner's site and any other kind is the department (as engine_runtime.identity_file says them): fallback_default(d) says it for
#: the department it is put to, and FALLBACK is a website's.
FALLBACK_OF = "I go ahead with the plan as it stands, and nothing in it reaches outside the %s"
FALLBACK = FALLBACK_OF % "site"
SOMETHING = "one thing in the plan rests on something only you can say."
QUESTION = 'Before I set up the work for %s: %s Unless you say, %s. Answer in your own words, or say "just do it".'


def _said(text, n):
    return " ".join(str(text or "").split())[:n]


#: What the owner may not read in a doubt or a fallback a model wrote (J2B-8: it shows no number and names no internal part): the
#: confidence, as the word or as a figure (0.45, .45, 45%, 45 percent; one that ends a sentence, '... at 0.45.'; and one said in
#: words, 'sixty percent', 'a 1 in 3 chance', 'zero point four five'), the parts by name (Adaptation, Priority, Coordination,
#: Audit) and the app's own words for its insides (engine, envelope, charter, refuse). A figure of the owner's own work (three
#: pages, Class 8.5, 9.30, v2.1.3, 3 in 4 columns) is theirs, and so are the words their page says (workflow, a search engine):
#: none is matched. A ratio is read as odds only beside a word of chance, so a count of the owner's own is never taken for one.
_NUMBER = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|hundred)"
_RATIO = r"\b%s\s+(?:in|out\s+of)\s+%s\b" % (_NUMBER, _NUMBER)
_CHANCE = r"\b(?:chances?|odds|probab\w*|likel\w*|sure|certain\w*|put\s+(?:it|this|that)\s+at|give\s+(?:it|this|that))\b"
INSIDE = re.compile("|".join((
    r"(?i:confiden)",
    r"(?<![\w.])0?\.\d+(?!\w)(?!\.\d)",             # 0.45 and .45, at the end of a sentence too; not 9.30, 8.5, v2.1.3 or 0.45.3
    r"(?i:\d+\s*(?:%|per\s?cent)|\bper\s?cent\b|\b(?:zero|nought|naught)\s+point\b)",   # 45%, 45 percent, sixty percent, zero point
    r"(?i:%s(?=[^.?!;]{0,40}%s)|%s[^.?!;]{0,40}?%s)" % (_RATIO, _CHANCE, _CHANCE, _RATIO),   # 'a 1 in 3 chance', 'I put it at 2 out of 5'
    r"\b(?:Adaptation|Priority|Coordination|Audit)\b",
    r"(?i:\b(?:engines?|envelopes?|charter|internal system|refus\w*)\b)")))
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


def fallback_default(d):
    """What the plan goes on with when nothing better is said, for the department it is put to: its site when it is a
    website, the department otherwise."""
    return FALLBACK_OF % ("site" if (d or {}).get("kind") == "website" else "department")


def fallback_of(ref, payload):
    """What the plan does when the owner says nothing more: the doubt's own fallback, unless it says nothing, reaches
    outside the department (the fallback never does) or cannot be told to the owner in plain words."""
    f, default = _said(payload.get("fallback"), 600).rstrip("."), fallback_default(W.dept(ref))
    return default if not f or R.LEAVES.search(f) else _plain_or(ref, f, default)


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
    """Read what was said (the body engine_runtime holds), and mark the words that answer Adaptation's doubt, or Identity's
    question on a fact only the owner has (fact_answered): they are no new request to recognise and no word on the identity's
    standard, which was met before the plan was shaped."""
    got = R.identity_read(ctx, step, item)
    ask = _doubt_asked(ctx)
    if ask:
        got.update({"doubt": ask["id"], "answers": None, "assess": False, "later": False, "filled": []})
        return got
    ask = _fact_asked(ctx)
    if ask:
        got.update({"fact": ask["id"], "answers": None, "assess": False, "later": False, "filled": []})
    return got


def identity_file(ctx, step, item):
    """File what was decided: the answer to a doubt goes back to Adaptation (doubt_answered), the answer to a question on a
    fact goes into the Brief (fact_answered); any other word, to the body engine_runtime holds."""
    got = ctx["bag"]["identity.read"]
    if got.get("doubt"):
        return doubt_answered(ctx, got)
    if got.get("fact"):
        return fact_answered(ctx, got)
    return R.identity_file(ctx, step, item)


def earlier_cycle(ref, ask):
    """Whether Identity asked this question under a cycle that has ended: a changed goal starts another (M9.8), and a question of
    the old one is not answered in the new."""
    cj = R._j2()
    now = (cj._state(ref) or {}).get('cycle_id') if cj else None
    return bool(ask and ask.get('cycle_id') and now and ask['cycle_id'] != now)


def set_aside(ctx, ask):
    """The owner's words answer a question of a cycle that has ended: it is closed as replaced if it still waits, nothing in the
    cycle now at work moves, and the owner is told, in plain words, that it was set aside."""
    ref, d, p = ctx['ref'], ctx['dept'], ctx['post']
    if ask['status'] == 'pending':
        W._put_ask(ref, dict(ask, status='replaced', decided=W.now()))
    R._tell(ref, d, p, 'inform', {'word': 'request', 'done': 'That question belonged to the goal before it changed, so I have set it aside. '
                                                            'Say it again if it still matters.'}, thread=p['thread'])
    return {'said': "set aside the owner's words: the question belonged to an earlier cycle; nothing moves"}


def doubt_answered(ctx, got):
    """The owner's answer to Adaptation's doubt, or 'just do it', which takes the fallback: it joins the Brief with the
    question it answers and goes to Adaptation as a new line request that carries it (the cycle goes back to step 2)."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    words, hurry = got["words"], bool(got.get("hurry"))
    old = next((a for a in W.asks(ref) if a["id"] == got["doubt"]), None)
    if earlier_cycle(ref, old):
        return set_aside(ctx, old)
    ask = R._j2().took(ref, got["doubt"], words, at=R._words_at(ref, p)) or {}
    meta = ask.get("doubt") or {}
    if meta.get("answered"):
        return {"said": "took words for a doubt that was answered already"}
    doubt, fallback = meta.get("doubt") or "", meta.get("fallback") or fallback_default(d)
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


# ---- The ways out of a conflict (PRD M5.4) ------------------------------------------------------------------------------
# A conflict Identity cannot settle goes to the owner as one ask. When the one who raised it knew the ways out (Priority at a
# limit: raise it, leave an item out, stop; Adaptation when no plan can be made: set it up again, leave an item out, stop), the
# conflict carries them as options (act.conflict), and the ask carries those: each checked as the interface types an option, at
# most three, each applied by the layer OPTION_KINDS names. A conflict that carries none is put to the owner as it was.


def conflict_options(payload):
    """The ways out a conflict carries, as the ask will hold them (W.option): the ones the interface types as an option, and no
    more than it allows; [] when the conflict carries none."""
    out = []
    for o in (payload or {}).get('options') or []:
        try:
            built = W.option(o['id'], o['label'], o['cost'], o.get('params'))
        except (KeyError, TypeError, AttributeError):
            continue
        if not S.validate('option', built) and len(out) < S.OPTIONS_MAX:
            out.append(built)
    return out


def round_words(pl):
    """The title and the source of the card a conflict about a round puts to the owner (M9.4, M9.5), or None when the conflict is
    not about a round. The plan is registered and runs; what needs the owner's word is the next round. A round that was proposed
    carries its correction, and what stopped it is Priority's (it said no, or did not price it in time); one that was never made
    carries none, and what stopped it is that Adaptation has no new way to put the work right."""
    n = (pl or {}).get('round')
    if not isinstance(n, int) or isinstance(n, bool):
        return None
    return 'The next round needs your word.', 'Priority, pricing the round' if pl.get('correction') else 'Adaptation, correcting the work'


def identity_closed(ctx, step, item):
    """Identity's ruling on a bargain that did not close (step 4): run it, drop it, or one ask to the owner (J2.3). The body
    engine_runtime held, moved here to carry the conflict's own ways out: whenever the ruling puts the conflict to the owner,
    what the owner gets is one card with those ways out when the conflict carries them (conflict_options)."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    got = ctx['bag']['identity.close']
    ruling, why = got.get('ruling'), str(got.get('why') or '').strip().rstrip('.')
    engines, cj = [e for e in pl.get('engines') or [] if isinstance(e, dict) and e.get('name')], R._j2()
    names = ' -> '.join(e['name'] for e in engines)
    who = {'src': 'Root' if d.get('root') else R.OWNER}
    ways = conflict_options(pl)
    if not engines:
        # no plan at all: Adaptation answered that an engine the kind requires cannot serve an item (J2B-4, M6.4), so there is
        # nothing to run, nothing to drop and no plan to stamp (a stamp would send Root a plan that names no engine, and the
        # same card would come back). The owner is put the reason in plain words, on the card every blocked plan has, with the
        # ways out the conflict carries, or the usual three. A conflict about a round is not that: the plan is registered and
        # runs, and the question is the next round (M9.4, M9.5), so its card says so (round_words)
        reason = str(pl.get('why') or 'no plan can be made').strip().rstrip('.')
        if cj:
            cj.ruled(ref, 'ask', reason, engines)
        rnd = round_words(pl)
        if rnd:
            card = R._blocked(ref, d, who, '%s. Say how to put it right, or choose a way forward on this card.' % reason, rnd[0], rnd[1], reason, options=ways)
            W._put_ask(ref, dict(card, round=pl['round']))        # the card knows it is the next round's: its words are a correction (round_words_chosen)
            return {'said': 'the next round cannot go on (%s); put to the owner, with the ways out' % reason}
        R._blocked(ref, d, who, '%s. Say what the department should do, or choose a way forward on this card.' % reason,
                   'No plan can be made as it stands.', 'Adaptation, shaping the plan', reason, options=ways)
        return {'said': 'no plan can be made (%s); put to the owner, with the ways out' % reason}
    if cj:
        cj.ruled(ref, ruling, why, engines)
    if ruling == 'run':
        R._tell(ref, d, who, 'inform', {'word': 'line', 'done': 'Priority did not say yes to the plan %s; I ruled it runs: %s.' % (names, why)})
        return R._j2_settle(ref, d, engines, pl.get('source') or 'shaped', pl.get('words'), "Identity's ruling")
    if ruling == 'drop':
        R._blocked(ref, d, who, "The plan %s is dropped: %s. Say what to change, or raise Priority's limit on its card."
                   % (names, why or str(pl.get('why') or '')), 'The plan is dropped.', "Identity, settling Priority's no",
                   why or str(pl.get('why') or ''), options=ways)
        return {'said': 'dropped the plan: ' + (why or "Priority's no stands")}
    if ways:
        # the conflict says how it can go on, so the owner chooses between those: one card, never a stamp that can only run or drop
        if not any(a.get('kind') == 'blocked' and a.get('status') == 'pending' and a.get('for') == pl.get('for') for a in W.asks(ref)):
            text = ('Adaptation proposes the plan %s. %s. The goal and the rules do not settle it. Choose a way forward on this card.'
                    % (names, str(pl.get('why') or 'Priority did not say yes to it').rstrip('.')))
            ask = R._blocked(ref, d, who, text, 'The plan needs your word.', 'Identity, settling the bargain',
                             why or str(pl.get('why') or ''), options=ways)
            W._put_ask(ref, dict(ask, **{'for': pl.get('for')}))
        return {'said': 'could not close the conflict from the goal and the rules; put it to the owner, with its ways out'}
    text = ('Adaptation proposes the plan %s. %s. The goal and the rules do not settle it. %s'
            % (names, str(pl.get('why') or 'Priority did not say yes to it').rstrip('.'), R._answers('run it as proposed', 'to drop it')))
    # the card quotes Priority's why, which a model may say in the bargain's inside words: it passes the check every card
    # passes (plain_card, M3.6), so the card says what the line it stands for may (found by a verifier 2026-10-26: the
    # Chat's 'Waiting for you' card said grant and counter while its line was plain)
    text = R.plain_card(ref, {'text': text}, 'conflict')['text']
    if not any(a.get('kind') == 'conflict' and a.get('for') == pl.get('for') for a in W.asks(ref)):
        p = R.post(ref, 'Identity', R.OWNER, 'request', {'word': 'conflict', 'objective': text, 'output': 'a stamp or a refusal', 'may_read': ['Brief'],
                                                          'boundaries': 'this one plan'})
        W._put_ask(ref, {'id': 'a-' + uuid.uuid4().hex[:8], 'kind': 'conflict', 'engine': 'Identity', 'engines': engines,
                         'source': pl.get('source') or 'shaped', 'words': pl.get('words'), 'for': pl.get('for'), 'text': text,
                         'status': 'pending', 'created': W.now(), 'thread': p['thread'] if p else None})
    return {'said': 'could not close the conflict from the goal and the rules; put it to the owner'}


def apply_way(ctx, ask, pl):
    """The way out the owner chose on a card, when another layer owns it (S.OPTION_KINDS says which, A1.15): that layer's
    apply_option(ref, ask, option) applies it. Words, leave and stop are Identity's own, applied by the body engine_runtime
    holds. A layer that cannot apply it yet, or refuses it (raise past its cap, a set-up with no words), leaves the card
    waiting as it was, and the owner is told why: a choice nothing applied is no choice. None for a way Identity applies."""
    ref, d = ctx['ref'], ctx['dept']
    oid = str(pl.get('option') or '')
    spec = S.OPTION_KINDS.get(oid.split(':', 1)[0])
    if not spec or spec['layer'] == 'identity':
        return None
    option = next((o for o in ask.get('options') or [] if o.get('id') == oid), None) or {'id': oid}
    module = layers.impl(ref, spec['layer'], d)
    fn = getattr(module, 'apply_option', None)
    try:
        if not callable(fn):
            raise ValueError('%s cannot do that yet' % S.TITLE[spec['layer']])
        got = fn(ref, ask, option)
    except ValueError as exc:
        R._card_waits(ref, d, ask)
        R._tell(ref, d, {'src': 'Root' if d.get('root') else R.OWNER}, 'inform',
                {'word': 'request', 'done': '%s. Nothing changed; choose again on the card.' % str(exc).strip().rstrip('.')})
        return {'said': "could not apply the owner's choice (%s): %s; the card waits" % (oid, exc), 'applied': False}
    return {'said': "applied the owner's choice (%s) through %s" % (oid, S.TITLE[spec['layer']]), 'applied': True, 'result': got}


def round_card(ask):
    """Whether a card is the one for the next round (identity_closed tags it with the round the conflict names): the plan it stands
    beside is registered and runs, and what the card asks for is the next correction."""
    n = (ask or {}).get('round')
    return (ask or {}).get('kind') == 'blocked' and isinstance(n, int) and not isinstance(n, bool)


def words_filed(ref, d, v):
    """The owner's words for the next round are in the Brief as version v: the registered line runs again on them (step 6, as it does
    for a round filed), and the owner is told so. Nothing is shaped afresh, registered or paid for as a round. A department the owner
    stopped keeps its stop: the move waits for Start (j2_runtime._move)."""
    cj = R._j2()
    if cj and cj.active(ref) and not cj.done(ref):
        cj._move(ref, 'running', step=6)
    R._tell(ref, d, _who(d), 'inform', {'word': 'filed', 'link': 'Brief', 'v': v,
                                        'done': 'Thank you. Your words are in the Brief as v%d, and the line runs again with them.' % v})


def round_words_chosen(ctx, ask):
    """The owner chose to say how to put it right on the card for the next round (M9.4): the card says their words go into the Brief and
    the line runs again, and that is all it does. The words are filed as 'Correct this: <words>' with no stamp, unless a rule says
    ask (S-18: then they are put back to the owner first, and the stamp files them, words_filed); the registered line runs again.
    No round is made for them, so none is paid for, and the plan is not shaped afresh (the reopening that is for a plan that is
    blocked, which this plan is not: the registered line is whole)."""
    ref, d = ctx['ref'], ctx['dept']
    words = ' '.join(str((ask.get('chosen') or {}).get('words') or '').split())[:2000]
    rule = rule_asking_first(ref, d, words)
    if rule:
        text = 'Your words for the next round: %s. The rule "%s" says I ask you first. Stamp to have the line put it right.' % (words, str(rule['line']).rstrip('.'))
        p = R.post(ref, 'Identity', R.OWNER, 'request', {'word': 'finding', 'objective': text, 'output': 'a stamp or a refusal', 'may_read': ['Brief'],
                                                         'boundaries': words, 'claim': words})
        W._put_ask(ref, {'id': 'a-' + uuid.uuid4().hex[:8], 'kind': 'finding', 'engine': 'Identity', 'slot': ctx['slot'], 'text': text, 'claim': words,
                         'found': words, 'findings': [], 'rule': rule['line'], 'words_for_round': ask['round'], 'status': 'pending', 'created': W.now(),
                         'thread': p['thread'] if p else None})
        return {'said': 'put the owner\'s words for the next round back to the owner first, as the rule "%s" says to ask' % rule['line']}
    row = R._file_brief(ref, d, 'Correct this: ' + words, "the owner's words on the card for the next round")
    words_filed(ref, d, row['v'])
    return {'said': "filed the owner's words in the Brief as v%d with no stamp; the registered line runs again, and nothing is shaped afresh" % row['v'],
            'filed': row['v']}


def refused_round(ref, cycle):
    """The latest round of this cycle whose last row says refused (rounds.jsonl), or None: a round Priority would not pay for."""
    last = {}
    for r in W.rows(ref, 'rounds.jsonl'):
        if isinstance(r, dict) and isinstance(r.get('round'), int) and r.get('cycle_id') in (None, cycle):
            last[r['round']] = r
    gone = [r for _, r in sorted(last.items()) if r.get('status') == 'refused']
    return gone[-1] if gone else None


def ask_again(ref, d):
    """The owner added room to the goal's ceiling (M9.2, M9.5), so the round it refused is asked for again: request/next to
    Adaptation on the items that round covered still in done-when, from the reading that asked for it, naming the round so that it
    keeps its number, and the cycle goes on pursuing. Once for each time that round was refused. None when no round was refused,
    nothing it covered is left, the goal is reached, or Adaptation hears no next round."""
    cj = R._j2()
    if not (cj and cj.active(ref) and next_is_heard()) or cj.done(ref):
        return None
    cycle = (cj._state(ref) or {}).get('cycle_id')
    row = refused_round(ref, cycle)
    if not row:
        return None
    n, kept = row['round'], {i['id'] for i in W.items_of(d)}
    left = [i for i in row.get('covers') or [] if i in kept]
    read = [r for r in W.rows(ref, 'readings.jsonl') if r.get('read')]
    reading = reading_of(ref, row.get('reading')) or (read[-1] if read else None)
    if not left or not reading:
        return None
    refusals = {r.get('thread') for r in W.rows(ref, 'rounds.jsonl') if r.get('round') == n and r.get('status') == 'refused' and r.get('cycle_id') in (None, cycle)}
    asked = [q for q in R.board(ref) if q['src'] == 'Identity' and q['dst'] == ['Adaptation'] and (q['payload'] or {}).get('word') == 'next'
             and q['payload'].get('round') == n and q['payload'].get('reading') == reading['id']]
    if len(asked) >= len(refusals):
        return None
    sent = R.post(ref, 'Identity', 'Adaptation', 'request',
                  {'word': 'next', 'items': left, 'reading': reading['id'], 'findings': [f for f in row.get('fixes') or [] if isinstance(f, str)], 'round': n,
                   'objective': 'propose the next correction for %s' % ', '.join(left), 'output': 'one priced correction on the registered line',
                   'may_read': ['Brief'], 'boundaries': 'nothing new is registered; only the registered engines run'},
                  about={'art': reading['artifact'], 'v': reading['v']})
    if sent and (cj._state(ref) or {}).get('state') == 'blocked':
        cj._move(ref, 'pursuing', step=8)
    return {'round': n, 'items': left, 'n': sent and sent['n']}


def resume_after_raise(ctx, got):
    """What apply_way gave back, and when the choice added room to the goal's ceiling, the round the ceiling refused asked for again
    (ask_again): the owner who pays for one more round gets it, and not the card they chose from."""
    if not (got.get('applied') and (got.get('result') or {}).get('what') == 'ceiling'):
        return got
    again = ask_again(ctx['ref'], ctx['dept'])
    if not again:
        return got
    return dict(got, said='%s; asked Adaptation for round %d again, on %s' % (got['said'], again['round'], ', '.join(again['items'])), round=again['round'])


def _standing(d):
    """Who the department is, as a change to it is read against what it was: the goal, done-when and the identity's revision."""
    return {'goal': (d or {}).get('goal'), 'done': (d or {}).get('done'), 'revision': int((d or {}).get('identity_revision') or 1)}


def retire_asks(ref, cycle):
    """What Identity asked under the cycle that has just ended is moot under the new one (M9.8): its question on a fact or on
    Adaptation's doubt, a finding put to the owner, a blocked plan's card, a conflict it could not settle. Each still waiting is
    closed as replaced, so none is answered later against a goal that has changed; the new cycle asks its own. The asks of the
    new cycle, and every other kind (a publish, an engine offered, a rule or done-when still to be stamped), stand."""
    with W._lock(ref):
        for a in W.asks(ref):
            owned = a.get('kind') in ('finding', 'blocked', 'conflict') or (a.get('kind') == 'j2_identity' and a.get('missing') in ('fact', 'plan'))
            if a['status'] == 'pending' and owned and a.get('cycle_id') != cycle:
                W._put_ask(ref, dict(a, status='replaced', decided=W.now()))


def reopen_on_change(ctx, ask, before):
    """A stamped change to the goal (a rule tagged goal) or to done-when (a done_items ask) starts the department's cycle again
    (M9.8; Q7: Identity takes the owner's words as a goal rule they stamp): j2_runtime.reopen, then Identity says old to new in
    one line and reads its standard on the new cycle as it does where a cycle starts. What Identity asked under the old cycle is
    retired first (retire_asks), so the new cycle starts with no question of the old goal open. Not when the stamp answers
    Identity's own question (the cycle is still on its first step, asking), when nothing it changed is the goal or done-when,
    or when the department has no cycle that has started. After done, a task is the Brief's (J3 4a, Q8) and starts no cycle."""
    ref = ctx['ref']
    cj = R._j2()
    cur = (cj._state(ref) or {}) if cj else {}
    after = W.dept(ref) or {}
    if (ask.get('answers') or (ask['kind'] == 'rule' and ask.get('tag') != 'goal') or not cur.get('cycle_id')
            or (int(cur.get('step') or 1) <= 1 and cur.get('state') != 'done')
            or (after.get('goal'), after.get('done')) == (before['goal'], before['done'])):
        return None
    if not cj.reopen(ref, was=before):
        return None
    retire_asks(ref, (cj._state(ref) or {}).get('cycle_id'))
    goal = before['goal'] != after.get('goal')
    old, new = (before['goal'], after.get('goal')) if goal else (before['done'], after.get('done'))
    R._tell(ref, after, _who(after), 'inform',
            {'word': 'goal', 'done': '%s changed from \u201c%s\u201d to \u201c%s\u201d. The department starts its work again from the top.'
             % ('The goal' if goal else 'Done-when', str(old or 'nothing').rstrip('.'), str(new or 'nothing').rstrip('.'))})
    R._j2_went_on(ref, ask['id'])
    return cj._state(ref)


def leave_rule_out(ctx, rule):
    """The owner chose to leave a rule out (M9.5, J2.7: a build still breaks it after two rewrites): the rule comes off the
    department's rules, the identity moves a revision, the Brief says so, and the line builds again without it. A rule the
    owner stamped is the owner's to drop; no rule of a parent's is offered here."""
    ref, d = ctx['ref'], ctx['dept']
    line = str(rule.get('line') or '').rstrip('.')
    with W._lock(ref):
        cur = W.dept(ref)
        cur['rules'] = [r for r in cur.get('rules') or [] if r.get('id') != rule.get('id')]
        W.bump_identity(ref, cur)
    cj = R._j2()
    if cj and cj.active(ref):
        cj._move(ref, 'running')
    row = R._file_words(ref, W.dept(ref), 'A rule is left out: %s. Build again without it.' % line, 'a rule the owner left out')
    R._tell(ref, d, _who(d), 'inform', {'word': 'request', 'done': 'The rule is left out: %s. The line builds again without it.' % line, 'v': row['v']})
    return {'said': "left the rule out on the owner's choice: %s" % line, 'filed': row['v']}


def identity_apply(ctx, step, item):
    """Apply what the owner stamped (the body engine_runtime holds), once the ways out another layer owns have been applied
    by it (apply_way, M5.4); a stamp on the correction a round asked (identity_round) files the round (M9.3)."""
    ref, pl = ctx['ref'], ctx['post']['payload']
    ask = next((x for x in W.asks(ref) if x['id'] == pl.get('ask')), None)
    before = _standing(W.dept(ref))
    if ask and ask.get('kind') == 'blocked' and pl.get('option'):
        oid = str(pl['option'])
        rule = next((r for r in ctx['dept'].get('rules') or [] if oid.startswith('leave:') and r.get('id') == oid.split(':', 1)[1]), None)
        if rule:
            return leave_rule_out(ctx, rule)
        if oid == W.WORDS_OPTION and round_card(ask):
            return round_words_chosen(ctx, ask)
        got = apply_way(ctx, ask, pl)
        if got is not None:
            return resume_after_raise(ctx, got)
    out = R.identity_apply(ctx, step, item)
    if ask and ask.get('kind') == 'finding' and ask.get('round') and out.get('filed'):
        round_filed(ref, ctx['dept'], ask['round'], out['filed'], ask.get('correction') or ask.get('claim'))
    if ask and ask.get('kind') == 'finding' and ask.get('words_for_round') and out.get('filed'):
        words_filed(ref, ctx['dept'], out['filed'])             # the owner's words a rule said to ask about, stamped
    if ask and ask.get('kind') in ('rule', 'done_items'):
        reopen_on_change(ctx, ask, before)
    return out


def last_reading(ref, cycle=None):
    """The last reading that was read, of this cycle (any, when none is named), as readings.jsonl holds it, or None."""
    return next((r for r in reversed(W.rows(ref, 'readings.jsonl')) if r.get('read') and cycle in (None, r.get('cycle_id'))), None)


def ways_out(d, why, lead='Say what to change'):
    """The closing words of a card whose ways out R._blocked builds: they name the way that leaves an item out of done-when only
    when the card offers it (never with one item, since done-when is never left empty), so what the card says and what its
    buttons do are the same (M9.5)."""
    item = R._left_out(d, why)
    return '%s, leave %s out of done-when, or stop here.' % (lead, item['id']) if item else '%s, or stop here.' % lead


def open_items(ref, ask, base=None):
    """The done-when items a finding the owner turned down leaves open, in the order done-when lists them: the ones its round
    covers; else the ones its findings name; else the items not met in the reading it came from (the cycle's last reading, when
    the ask does not name one). [] when it names none and every item is met."""
    ids = [i['id'] for i in W.items_of(W.dept(ref))]
    named = [i for i in (base or {}).get('covers') or [] if isinstance(i, str)]
    named = named or [f['item'] for f in ask.get('findings') or [] if isinstance(f, dict) and f.get('item') in ids]
    if named:
        return [i for i in ids if i in named] or named
    cj = R._j2()
    row = reading_of(ref, ask.get('reading')) or last_reading(ref, (cj._state(ref) or {}).get('cycle_id') if cj else None)
    verdicts = R.audit_verdicts((row or {}).get('items'))
    return [i for i in ids if verdicts.get(i) == 'not_met']


def identity_drop(ctx, step, item):
    """Take the owner's no (the body engine_runtime holds). A no to a finding the owner was asked to stamp ends that correction
    (a round's is a round refused), and the pursuit does not end with it in silence: while the department is not done, the owner
    is given the ways out as one card (M9.5), whatever put the finding to them: a round, a reading's item that is not met, a
    finding a rule says to ask about, or a high finding on a reading that met every item."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    ask = next((x for x in W.asks(ref) if x['id'] == pl.get('ask')), None)
    out = R.identity_drop(ctx, step, item)
    if not (ask and ask.get('kind') == 'finding'):
        return out
    n, base = ask.get('round'), None
    what = _said(ask.get('correction') or ask.get('found') or ask.get('claim'), 300).rstrip('.')
    if n:
        rows = round_rows(ref, n)
        base = rows[-1] if rows else None
        if not base or base.get('status') not in ('refused', 'filed', 'read'):
            round_row(ref, base or {'round': n, 'correction': ask.get('correction') or ask.get('claim') or '', 'covers': []}, 'refused')
    cj = R._j2()
    cur = (cj._state(ref) or {}) if cj else {}
    if not (cur.get('cycle_id') and not cj.done(ref)):
        return out
    left = open_items(ref, ask, base)
    why = '%s not met' % ', '.join(left) if left else 'a finding is still open'
    R._blocked(ref, d, _who(d), 'You said no to the correction%s: %s. %s' % (' for round %d' % n if n else '', what, ways_out(d, why)),
               'The correction was turned down.', 'You, on the correction Identity put to you', why)
    return out


# ---- Hear a reading (PRD M8.4) -------------------------------------------------------------------------------------------
# Audit files a reading of one version (readings.jsonl, audit.reading) and tells Identity (inform/reading, act.reading; Audit posts
# it once this handler is in Identity's recipe, A1-14). Identity reads the reading by its id: the goal is reached only when the
# reading says so, which identity_done holds to done_is_read before j2_runtime records it (j2_runtime records and projects and
# never rules, rule 14). 'Found nothing' is no reading of an item (S-30).


def reading_of(ref, rid):
    """The reading a post names, as readings.jsonl holds it, or None."""
    return next((r for r in W.rows(ref, 'readings.jsonl') if rid and r.get('id') == rid), None)


def done_claim(d, row):
    """What a reading says of the goal, as Identity reads it: the department's done-when items by their verdict in the reading,
    and whether the goal holds. Done means the version was read, every item has a verdict and it is met, none is to confirm,
    none is a fact still to be confirmed on the record, and no finding is high."""
    ids = [i['id'] for i in W.items_of(d)]
    verdicts = R.audit_verdicts((row or {}).get('items'))
    out = {'reading': (row or {}).get('id'), 'artifact': (row or {}).get('artifact'), 'v': (row or {}).get('v'),
           'read': bool(row) and row.get('read') is True,
           'met': [i for i in ids if verdicts.get(i) == 'met'], 'not_met': [i for i in ids if verdicts.get(i) == 'not_met'],
           'to_confirm': [i for i in ids if verdicts.get(i) == 'to_confirm'], 'unread': [i for i in ids if i not in verdicts],
           'high': any(f.get('severity') == 'high' for f in (row or {}).get('findings') or [])}
    owed = [c.get('item') for c in d.get('to_be_confirmed') or [] if isinstance(c, dict)]
    why = None
    if not row:
        why = 'no reading by that name is on the record'
    elif not out['read']:
        why = 'the version was not read'
    elif not ids:
        why = 'the department has no done-when items to read'
    elif out['not_met']:
        why = '%s not met' % ', '.join(out['not_met'])
    elif out['to_confirm'] or owed:
        why = '%s still to be confirmed' % ', '.join(out['to_confirm'] or owed)
    elif out['unread']:
        why = '%s not read' % ', '.join(out['unread'])
    elif out['high']:
        why = 'a high finding is open'
    out.update({'done': why is None, 'why': why or 'every done-when item is met, none is to confirm and no high finding is open'})
    return out


def c_done_is_read(ctx, step, item, out):
    """Done is read from a reading, never from no findings (PRD M8.4): a claim that the goal is reached cites the reading, says
    it was read, and has every item met, none to confirm, none unread and no high finding; against the record, the items it
    meets are all the department's. A claim that it is not reached says why."""
    notes, done = [], out.get('done')
    if not isinstance(done, bool):
        notes.append('it does not say whether the goal is reached')
    elif done:
        if not out.get('reading'):
            notes.append('done, and no reading is cited')
        if out.get('read') is not True:
            notes.append('done, on a version that was not read')
        if not out.get('met'):
            notes.append('done, with no item met')
        for key, said in (('not_met', 'an item is not met'), ('to_confirm', 'an item is to be confirmed'), ('unread', 'an item is not read')):
            if out.get(key):
                notes.append('done, but %s: %s' % (said, ', '.join(map(str, out[key]))))
        if out.get('high'):
            notes.append('done, with a high finding open')
        if ctx and ctx.get('dept'):
            # against the record: the claim is read again off the reading it cites, and the items it meets are all the department's
            owed = {i['id'] for i in W.items_of(ctx['dept'])} - set(out.get('met') or [])
            if owed:
                notes.append('done, but %s is not met' % ', '.join(sorted(owed)))
            again = done_claim(ctx['dept'], reading_of(ctx['ref'], out.get('reading'))) if ctx.get('ref') and out.get('reading') else None
            if again and not again['done']:
                notes.append('done, but the reading it cites says otherwise: %s' % again['why'])
    elif not str(out.get('why') or '').strip():
        notes.append('not done, and it does not say why')
    return {'ok': not notes, 'notes': notes or ['done is read from the reading' if done else 'not done: %s' % out.get('why')]}


def identity_done(ctx, step, item):
    """Identity says the goal is reached, from a reading and from nothing else (M8.4): the reading is read by its id, the claim
    is held to done_is_read before anything is written, then j2_runtime records goal.reached citing the reading and the owner
    is told, once. Only a cycle with a plan at work (step 6 on) can be done, and only on a reading of its own cycle and of the
    version now out."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    cj = R._j2()
    row = reading_of(ref, pl.get('reading'))
    got = done_claim(d, row)
    cur = (cj._state(ref) or {}) if cj else {}
    if cj and cj.done(ref):
        return dict(got, said='the goal was reached already; nothing more is declared')
    if got['done']:
        newer = W.latest(ref, got['artifact'], passed=True) if got['artifact'] else None
        if not (cj and cj.active(ref) and int(cur.get('step') or 1) >= 6):
            got.update({'done': False, 'why': 'the department is not in its cycle with a plan at work'})
        elif row.get('cycle_id') not in (None, cur.get('cycle_id')):
            got.update({'done': False, 'why': 'the reading belongs to an earlier cycle'})
        elif newer and int(newer['v']) > int(got['v'] or 0):
            got.update({'done': False, 'why': 'a newer version is out, and its reading decides'})
        else:
            held = c_done_is_read(ctx, step, item, got)
            if not held['ok']:
                got.update({'done': False, 'why': '; '.join(held['notes'])})
    if not got['done']:
        return dict(got, said='the reading does not say the goal holds: %s' % got['why'])
    cj.reached(ref, got['v'], artifact=got['artifact'], reading=got['reading'], findings=len(row.get('findings') or []))
    found = 'noted something that does not block' if row.get('findings') else 'found nothing to put right'
    try:
        R._tell(ref, d, {'src': 'Root' if d.get('root') else R.OWNER}, 'inform',
                {'word': 'goal', 'done': 'The goal is reached: %s. Audit read %s v%s and %s.'
                 % (str(d.get('done') or 'done').rstrip('.'), got['artifact'], got['v'], found), 'link': got['artifact'], 'v': got['v']})
    except Exception:  # noqa: BLE001 -- the goal is reached on the record whether or not the word reached the chat
        pass
    return dict(got, said='declared the goal reached on reading %s: %s' % (got['reading'], got['why']))


# ---- Weigh a reading three ways (PRD M8.5) -------------------------------------------------------------------------------
# What a reading leaves open is routed in code from its verdicts and findings, each piece one way. An item to confirm rests on a
# fact only the owner has: one question. A finding the owner must say yes to is an ask (S-18: only when a rule says ask, or it
# reaches outside what the department makes). Every other item not met is the next thing to correct: a request to Adaptation
# (request/next), posted only once Adaptation's recipe has the handler (A1-14). Until it has, the item goes the way it went before
# rounds, the finding ask that puts it right on the owner's stamp, so a not-met item always leaves a next move (SM-6).
#: the words that say nothing of what a rule is about, so a rule that asks first applies to a finding by what it names
ASK_WORDS = frozenset('about after again ahead always anything before could every first from have into never other outside owner '
                      'reaches should their there these they this those through under until what when where which will with without '
                      'would your page pages site'.split())
#: rounds in a row that meet no new item, after which Identity stops asking the line for another and asks the owner (M9.5)
NO_PROGRESS = 2


def next_is_heard():
    """Whether Adaptation's recipe has a handler for a request of the next round (A1-14: an act is posted only to a receiver
    that hears it)."""
    return R._handler(R.engine_def('Adaptation'), {'msg_type': 'request', 'payload': {'word': 'next'}}) is not None


def rule_asking_first(ref, d, text):
    """The rule that says to ask the owner before this, or None (S-18: Identity asks only when a rule says ask): a rule tagged
    ask applies to words that reach outside what the department makes (R.LEAVES), or that name what the rule is about."""
    ruled = [r for r in R._effective_rules(ref, d) if r.get('tag') == 'ask' and str(r.get('line') or '').strip()]
    if not ruled:
        return None
    if R.LEAVES.search(str(text or '')):
        return ruled[0]
    named = set(re.findall(r'[a-z]{4,}', str(text or '').lower())) - ASK_WORDS
    return next((r for r in ruled if named & (set(re.findall(r'[a-z]{4,}', r['line'].lower())) - ASK_WORDS)), None)


def _met_in(row):
    return {i for i, v in R.audit_verdicts((row or {}).get('items')).items() if v == 'met'}


def stalled(ref, row):
    """Whether the last NO_PROGRESS rounds in a row met no item the reading before them had not met (M9.5), this reading being
    the one after the last of them: counted from the cycle's readings, a version at a time, and the rounds Identity filed."""
    filed = {r['round'] for r in W.rows(ref, 'rounds.jsonl') if r.get('status') in ('filed', 'read')
             and r.get('cycle_id') in (None, row.get('cycle_id'))}
    mine = []
    for r in W.rows(ref, 'readings.jsonl'):
        if r.get('read') and r.get('cycle_id') == row.get('cycle_id'):
            mine = [x for x in mine if (x.get('artifact'), x.get('v')) != (r.get('artifact'), r.get('v'))] + [r]
    n = 0
    for before, after in reversed(list(zip(mine, mine[1:]))):
        if _met_in(after) - _met_in(before):
            break
        n += 1
    return bool(mine) and mine[-1].get('id') == row.get('id') and len(filed) >= NO_PROGRESS and n >= NO_PROGRESS


def mark_rounds_read(ref, row):
    """A reading made after a round was filed is that round read (M9.3): its next status, a row appended to rounds.jsonl
    (granted, filed, read), once, for each round of this cycle that was filed and not yet read."""
    last = {}
    for r in W.rows(ref, 'rounds.jsonl'):
        last[r['round']] = r
    for r in last.values():
        if r.get('status') == 'filed' and r.get('cycle_id') in (None, row.get('cycle_id')) and str(r.get('at') or '') <= str(row.get('at') or ''):
            round_row(ref, r, 'read')


def _claims(row, ids):
    """What the reading says of these items, one line each: 'D2 Every page names its fees: the fees are not on the page'."""
    by = {}
    for r in (row or {}).get('items') or []:
        if r.get('id') in ids and R.VERDICT_RANK.get(r.get('verdict'), -1) >= R.VERDICT_RANK.get((by.get(r['id']) or {}).get('verdict'), -1):
            by[r['id']] = r
    return ['%s %s: %s' % (i, str(by[i].get('subject') or '').rstrip('.'), str(by[i].get('claim') or '').rstrip('.')) for i in ids if i in by]


def _who(d):
    return {'src': 'Root' if d.get('root') else R.OWNER}


def _ask_fact(ctx, row, ids):
    """One question to the owner for the items a reading could not confirm (they rest on a fact only the owner can give): an ask
    that takes words, missing 'fact', one open at a time. None when the same question is open already, or another is open."""
    ref, d = ctx['ref'], ctx['dept']
    cj = R._j2()
    cur = cj._state(ref) or {}
    if any(a.get('kind') == 'j2_identity' and a.get('missing') == 'fact' and a['status'] == 'pending' and set(ids) <= set(a.get('points') or [])
           for a in W.asks(ref)) or cj.waiting_on_owner(ref):
        return None
    said = R.plain_card(ref, {'text': 'I cannot confirm yet: %s. Tell me the facts here and I will put them in.' % '; '.join(_claims(row, ids)),
                              'why': 'it rests on a fact only you can give'}, 'question')
    step = max(6, int(cur.get('step') or 8))
    with W._lock(ref):
        ask = dict(W.j2_identity_ask(said['text'], cur.get('cycle_id'), 'fact', said['why'], list(ids), False), reading=row['id'])
        W._put_ask(ref, ask)
        cj.note(ref, step, 'Identity', 'User', 'identity.questioned', 'waiting', said['text'], 'identity-fact-' + ask['id'],
                {'missing': ['fact'], 'why': said['why'], 'standard': False})
        cj._move(ref, 'waiting', step=step, open_ask=ask['id'])
    R._tell(ref, d, _who(d), 'inform', {'word': 'question', 'done': said['text'], 'card': ask['id']})
    return ask


def _fact_asked(ctx):
    """The question on a fact that the words in this post answer, as the ask holds it: the one a box answer names, else the one
    the cycle waits on when they were said in the chat. None for any other words."""
    ref, aid = ctx['ref'], (ctx['post'].get('payload') or {}).get('answers')
    cj = R._j2()
    if not cj or not cj.enabled():
        return None
    if not aid:
        q = cj.open_question(ref) or {}
        aid = q.get('id') if q.get('missing') == 'fact' else None
    return next((a for a in W.asks(ref) if aid and a['id'] == aid and a.get('kind') == 'j2_identity' and a.get('missing') == 'fact'), None)


def fact_answered(ctx, got):
    """The owner's answer to the question on a fact (M8.5): the question is closed, the answer joins the Brief under it so the
    line builds again with the fact, and the items it was about no longer wait on it. 'Just do it' gives no fact: those items
    stay to be confirmed, so the goal cannot be reached as it stands, and the owner is given the ways out."""
    ref, d, p = ctx['ref'], ctx['dept'], ctx['post']
    cj = R._j2()
    words, hurry = got['words'], bool(got.get('hurry'))
    ask = next(a for a in W.asks(ref) if a['id'] == got['fact'])
    if earlier_cycle(ref, ask):
        return set_aside(ctx, ask)
    ids = [i for i in ask.get('points') or []]
    if ask['status'] == 'pending':
        with W._lock(ref):
            W._put_ask(ref, dict(ask, status='stamped', decided=W.now(), by='the owner', answered=words, words_at=R._words_at(ref, p)))
            cj.note(ref, max(6, int((cj._state(ref) or {}).get('step') or 8)), 'User', 'Identity', 'ask.answered', 'complete',
                    'The owner answered: %s' % words[:200], 'answer-' + ask['id'], {'missing': 'fact'})
    cj._move(ref, 'pursuing', step=8, open_ask=None)
    if hurry:
        why = '%s still to be confirmed' % ', '.join(ids)
        R._blocked(ref, d, _who(d), '%s rests on a fact only you can give, and it stays to be confirmed, so the goal cannot be reached as it stands. %s'
                   % (', '.join(ids), ways_out(d, why, 'Give the fact')), 'A fact is still missing.', 'Identity, reading the work', why)
        return {'said': "took 'just do it' for a fact only the owner has; %s stays to be confirmed, and the owner has the ways out" % ', '.join(ids)}
    items = [dict(i, confirm='') if i['id'] in ids else i for i in W.items_of(W.dept(ref))]
    W.put_done_items(ref, items)
    row = R._file_words(ref, d, "To Identity's question (%s): %s" % (str(ask.get('text') or '').rstrip('?.'), words), "the owner's answer")
    R._tell(ref, d, p, 'inform', {'word': 'request', 'done': 'Thank you. I put it in the Brief, and the line builds again with it.'}, thread=p['thread'])
    return {'said': "took the owner's answer on %s and filed it in the Brief: %s" % (', '.join(ids), words[:160]), 'filed': row['v']}


def _ask_finding(ctx, art, claim, found, findings, rule=None, **more):
    """A finding put to the owner for the stamp that puts it right (the shape identity_finding files): the stamp files 'Correct
    this' in the Brief (identity_apply). `more` is kept on the ask: the reading it came from, or the round it is."""
    ref = ctx['ref']
    text = 'Audit found: %s. Stamp to have it put right.' % found
    p = R.post(ref, 'Identity', R.OWNER, 'request', {'word': 'finding', 'objective': text, 'output': 'a stamp or a refusal',
                                                      'may_read': [art] if art else [], 'boundaries': claim, 'claim': claim})
    return W._put_ask(ref, dict({'id': 'a-' + uuid.uuid4().hex[:8], 'kind': 'finding', 'engine': 'Audit', 'slot': ctx['slot'], 'text': text,
                                  'claim': claim, 'found': found, 'findings': findings, 'status': 'pending', 'created': W.now(),
                                  'thread': p['thread'] if p else None}, **dict(more, **({'rule': rule} if rule else {}))))


def _asked_about(ref, claim):
    """Whether the owner was asked (or has answered) about a finding with this claim already."""
    want = ' '.join(str(claim).lower().split())
    return any(a.get('kind') == 'finding' and (' '.join(str(a.get('claim') or '').lower().split()) == want or
                                               any(' '.join(str(f.get('claim') or '').lower().split()) == want for f in a.get('findings') or [] if isinstance(f, dict)))
               for a in W.asks(ref))


def identity_weigh_reading(ctx, step, item):
    """Weigh what a reading leaves open, three ways (M8.5), in code from its verdicts and findings: an item to confirm is one
    question; a finding that needs the owner's yes is an ask; every other item not met is the next move, to Adaptation, once it
    hears one. Two rounds with no new item met end in an options ask instead (stalled, M9.5)."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    cj = R._j2()
    got = ctx['bag']['identity.done']
    row = reading_of(ref, pl.get('reading'))
    routes = {'question': None, 'asks': [], 'next': None, 'card': None}
    if row and row.get('read'):
        mark_rounds_read(ref, row)
    if got['done']:
        return {'said': 'the goal holds on this reading; nothing is left open', 'routes': routes}
    if not row or not row.get('read'):
        return {'said': 'the version was not read; nothing is weighed and nothing is cleared', 'routes': routes}
    if not (cj and cj.active(ref)):
        return {'said': 'the department is not in its cycle; the reading is kept and nothing is weighed', 'routes': routes}
    if row.get('cycle_id') not in (None, (cj._state(ref) or {}).get('cycle_id')):
        return {'said': 'the reading belongs to an earlier cycle; it is kept and nothing is weighed', 'routes': routes}
    said = []
    if got['to_confirm']:
        ask = _ask_fact(ctx, row, got['to_confirm'])
        routes['question'] = ask and ask['id']
        said.append(('put %s, which it could not confirm, to the owner as one question' if ask else
                     'left %s, which it could not confirm, to the question the owner has open') % ', '.join(got['to_confirm']))
    left = list(got['not_met'])
    if left and stalled(ref, row):
        # the line has tried and met nothing new: no further round is asked for, and the owner has the ways out (no silent end)
        if not any(a.get('kind') == 'blocked' and a['status'] == 'pending' and a.get('reading') == row['id'] for a in W.asks(ref)):
            why = '%s not met' % ', '.join(left)
            card = R._blocked(ref, d, _who(d), 'The last rounds did not get any closer: %s still not met. %s' % (', '.join(left), ways_out(d, why)),
                              'The next rounds are not getting closer.', 'Identity, reading the work', why)
            W._put_ask(ref, dict(card, reading=row['id']))
            routes['card'] = card['id']
        said.append('asked the owner what to do: the rounds met nothing new')
        return {'said': '; '.join(said), 'routes': routes}
    findings = [f for f in row.get('findings') or [] if isinstance(f, dict) and f.get('claim')]
    covered = set()
    if any(q['src'] == 'Identity' and R.OWNER in q['dst'] and (q['payload'] or {}).get('word') == 'facts'
           and q['payload'].get('about_version') == row.get('v') for q in R.board(ref)):
        # the site said it does not know some facts and the owner was asked for them (identity_finding): what code measured as
        # not holding waits on those facts, which are never made up, and the question is its next move
        covered |= {r['id'] for r in row.get('items') or [] if r.get('method') == 'code' and r.get('verdict') == 'not_met'}
        left = [i for i in left if i not in covered]
    for f in findings:
        rule = rule_asking_first(ref, d, f['claim'])
        if not rule:
            continue
        if not _asked_about(ref, f['claim']):
            routes['asks'].append(_ask_finding(ctx, row['artifact'], f['claim'], f['claim'], [f], rule=rule.get('line'), reading=row['id'])['id'])
        covered.add(f.get('item'))
    left = [i for i in left if i not in covered]
    if routes['asks']:
        said.append("put what needs the owner's yes to the owner as an ask")
    if left and next_is_heard():
        if not any(q['src'] == 'Identity' and q['dst'] == ['Adaptation'] and (q['payload'] or {}).get('word') == 'next'
                   and q['payload'].get('reading') == row['id'] for q in R.board(ref)):
            ids = set(left)
            sent = R.post(ref, 'Identity', 'Adaptation', 'request',
                          {'word': 'next', 'items': left, 'reading': row['id'], 'findings': [f['id'] for f in findings if f.get('item') in ids or not f.get('item')],
                           'objective': 'propose the next correction for %s' % ', '.join(left), 'output': 'one priced correction on the registered line',
                           'may_read': ['Brief'], 'boundaries': 'nothing new is registered; only the registered engines run'},
                          about={'art': row['artifact'], 'v': row['v']})
            routes['next'] = sent and sent['n']
        if (cj._state(ref) or {}).get('state') not in ('waiting', 'blocked'):
            cj._move(ref, 'pursuing', step=8)
        said.append('asked Adaptation for the next move on %s' % ', '.join(left))
    elif left:
        # nobody hears a next round yet: the item goes the way it went before rounds, to the owner, to be put right on a stamp
        if not [a for a in W.asks(ref) if a['kind'] == 'finding' and a['status'] == 'pending']:
            lines = _claims(row, left)
            routes['asks'].append(_ask_finding(ctx, row['artifact'], '; '.join(lines), '; '.join(lines), [f for f in findings if f.get('item') in set(left)],
                                                reading=row['id'])['id'])
        said.append('put %s to the owner to be put right: nobody takes a next round yet' % ', '.join(left))
    return {'said': '; '.join(said) or 'weighed the reading; nothing is left to route', 'routes': routes}


def identity_finding(ctx, step, item):
    """Weigh a finding (the body engine_runtime holds), except the high one a reading's next round carries (M8.5): once Adaptation
    hears a next round, a finding of a reading that has an item not met is carried by that round, which Identity asks of
    Adaptation when it weighs the reading, so the owner is not also asked to stamp the same correction. A fact only the owner has,
    and a finding a rule says to ask about, are put to the owner as before."""
    ref, pl = ctx['ref'], ctx['post']['payload'] or {}
    row, cj = reading_of(ref, pl.get('reading')), R._j2()
    if not (row and row.get('read') and cj and cj.active(ref) and next_is_heard()
            and 'not_met' in R.audit_verdicts(row.get('items')).values()):
        return R.identity_finding(ctx, step, item)
    finds = [f for f in pl.get('findings') or [] if isinstance(f, dict) and f.get('claim')]
    keep = [f for f in finds if f.get('kind') == 'hole' or str(f.get('severity') or '').lower() != 'high'
            or rule_asking_first(ref, ctx['dept'], f['claim'])]
    if len(keep) == len(finds):
        return R.identity_finding(ctx, step, item)
    got = R.identity_finding(dict(ctx, post=dict(ctx['post'], payload=dict(pl, findings=keep))), step, item)
    return {'said': 'left %d high finding%s to the reading\'s next round; %s' % (len(finds) - len(keep), '' if len(finds) - len(keep) == 1 else 's', got['said'])}


# ---- File a granted round (PRD M9.3) -------------------------------------------------------------------------------------
# Adaptation proposed a correction round, Priority priced it inside the goal's ceiling, and Adaptation tells Identity it was
# granted (inform/round, act.round). Identity files the correction in the Brief as 'Correct this: ...' with no stamp, unless a rule
# says ask (S-18), and records the round's next status as a row of rounds.jsonl: a status change is a row appended, never one
# rewritten (W.append_row). The line, which only runs what Root registered (SM-3), runs again on the new Brief. Identity files a
# round only when the round's own last row, in this cycle, says granted: every proposal passes Priority first (rule 10), and who
# sends the word is no proof of it.


def round_rows(ref, n):
    """The rows rounds.jsonl holds of round n in the cycle now at work, oldest first: rounds are numbered again in each cycle, so a
    row of an earlier cycle says nothing of this one's round n."""
    cj = R._j2()
    cycle = (cj._state(ref) or {}).get('cycle_id') if cj else None
    return [r for r in W.rows(ref, 'rounds.jsonl') if r.get('round') == n and r.get('cycle_id') in (None, cycle)]


def round_row(ref, base, status, **more):
    """Round `base`'s next status, as a row of its own: what the round's last row held, with the new status and its time."""
    row = {k: v for k, v in base.items() if k not in ('status', 'at')}
    row.update(more)
    row.update({'schema_version': 1, 'status': status, 'at': W.now()})
    return W.append_row(ref, 'rounds.jsonl', row)


def round_filed(ref, d, n, v, correction):
    """The round's correction is in the Brief as version v: the round is filed (with brief_v), the cycle runs the line again at
    step 6 with the round it stands on, and the owner is told what was sent back."""
    rows = round_rows(ref, n)
    cj = R._j2()
    if not rows or rows[-1].get('status') not in ('filed', 'read'):
        cycle = (cj._state(ref) or {}).get('cycle_id') if cj else None
        round_row(ref, rows[-1] if rows else {'round': n, 'cycle_id': cycle, 'correction': correction[:600], 'covers': []}, 'filed', brief_v=v)
    if cj:
        cj._move(ref, 'running', step=6, round=n)
    R._tell(ref, d, _who(d), 'inform', {'word': 'filed', 'link': 'Brief', 'v': v,
                                        'done': 'Round %d: I sent the line back to put right: %s. It is filed in the Brief as v%d.'
                                        % (n, str(correction).rstrip('.'), v)})


def identity_round(ctx, step, item):
    """File a round Priority priced and Adaptation tells Identity of: 'Correct this: <correction>' in the Brief, with no stamp
    unless a rule says ask (S-18: then the correction is an ask the owner stamps, and the stamp files the round)."""
    ref, d, pl = ctx['ref'], ctx['dept'], ctx['post']['payload']
    cj = R._j2()
    n, correction = pl.get('round'), ' '.join(str(pl.get('correction') or '').split())
    if not n or not correction:
        return {'said': 'heard a round with nothing to correct; nothing is filed'}
    rows = round_rows(ref, n)
    if rows and rows[-1].get('status') in ('filed', 'read', 'refused'):
        return {'said': 'round %d is %s already; nothing is filed again' % (n, rows[-1]['status']), 'round': n}
    if not cj or cj.done(ref):
        return {'said': 'the goal is reached already; round %d is not filed' % n, 'round': n}
    if not rows or rows[-1].get('status') != 'granted':
        # every proposal passes Priority first (rule 10): the round is filed on its last row saying granted, in this cycle, and
        # not on the word of the one who sent it
        return {'said': 'round %d has no yes from Priority; nothing is filed' % n, 'round': n}
    rule = rule_asking_first(ref, d, correction)
    if rule:
        if not [a for a in W.asks(ref) if a.get('kind') == 'finding' and a.get('round') == n and a['status'] == 'pending']:
            _ask_finding(ctx, S.deliverable(d), correction, correction, [], rule=rule.get('line'), round=n, correction=correction)
        return {'said': 'put round %d to the owner first, as the rule "%s" says to ask: %s' % (n, rule.get('line'), correction), 'round': n}
    row = R._file_brief(ref, d, 'Correct this: ' + correction, 'round %d, granted' % n, rnd=n)
    round_filed(ref, d, n, row['v'], correction)
    return {'said': 'filed round %d in the Brief as v%d, with no stamp: %s' % (n, row['v'], correction), 'round': n, 'filed': row['v']}


#: the bodies of this version's own, in the table beside the references
CODE.update({'identity_read': identity_read, 'identity_file': identity_file, 'identity_doubt': identity_doubt,
             'identity_closed': identity_closed, 'identity_apply': identity_apply, 'identity_done': identity_done,
             'identity_weigh_reading': identity_weigh_reading, 'identity_finding': identity_finding, 'identity_round': identity_round,
             'identity_drop': identity_drop})
CHECK.update({'done_is_read': c_done_is_read})


def view(ref, d, events, asks):
    """Identity's pane (S.VIEWS['identity'], A1.17; M3.7): functions_view's read model of the record, by reference. It
    reads _identity_part and not _j2_part, which reads the layers' views and would come back here."""
    return FV._identity_part(ref, d, events)
