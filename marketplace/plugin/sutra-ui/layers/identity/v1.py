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
        # ways out the conflict carries, or the usual three
        reason = str(pl.get('why') or 'no plan can be made').strip().rstrip('.')
        if cj:
            cj.ruled(ref, 'ask', reason, engines)
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


def identity_apply(ctx, step, item):
    """Apply what the owner stamped (the body engine_runtime holds), once the ways out another layer owns have been applied
    by it (apply_way, M5.4)."""
    ref, pl = ctx['ref'], ctx['post']['payload']
    ask = next((x for x in W.asks(ref) if x['id'] == pl.get('ask')), None)
    if ask and ask.get('kind') == 'blocked' and pl.get('option'):
        got = apply_way(ctx, ask, pl)
        if got is not None:
            return got
    return R.identity_apply(ctx, step, item)


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


#: the bodies of this version's own, in the table beside the references
CODE.update({'identity_read': identity_read, 'identity_file': identity_file, 'identity_doubt': identity_doubt,
             'identity_closed': identity_closed, 'identity_apply': identity_apply, 'identity_done': identity_done})
CHECK.update({'done_is_read': c_done_is_read})


def view(ref, d, events, asks):
    """Identity's pane (S.VIEWS['identity'], A1.17; M3.7): functions_view's read model of the record, by reference. It
    reads _identity_part and not _j2_part, which reads the layers' views and would come back here."""
    return FV._identity_part(ref, d, events)
