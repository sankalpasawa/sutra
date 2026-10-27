"""owner_words.py -- the bargain in the owner's words, for every read a screen prints (PRD M1.7; the screen word rules).

The record keeps its own words, the inside ones: a handler's name ('Priority granted the line'), a step's name ('Grant,
refuse or counter'), a function's goal ('grants each engine its envelope'), a run's line ('granted the line Plan ->
Write'), the ledger's default summaries ('Refused.') and what Identity tells the owner ('Root's check refused the
plan'). The owner's ruling is that the screen says said yes, asked for less and said no, never grant, counter or refuse.
So every read a function's pane prints passes its words through here on the way out: functions_view's five and each
function's page, and website_api's /steps, /map, /status and /engine reads, which feed the cards under the page (the
steps, gates, Moves, Stamped by rule, Runs), and its /chat read, which feeds each function's Chat tab and the owner's
own chat (what Identity told the owner, the asks it put, each function's thinking). Nothing here writes: the record
keeps its words, the screen gets the owner's. The words are put right where they are composed too (engine_runtime's
tells, the asks' answers through engine_runtime._answers, the step names in the definitions): this table keeps a
record written before that, and anything a definition still says, in the owner's words on the way out.

Phrases only, longest first, so a sentence keeps its grammar, and never a bare verb: the owner's own words (the goal,
done-when, the rules, the requests) are never passed through here, nor are they where a function carries them on (a
turn the record marks quoted, the words an ask's or a run's line ends with: kept), and a rule's tag (go, ask, refuse,
always), a data value, is left as it is: the badge that prints it says 'never' for refuse, and a sentence that lists the
tags says 'never' too ('tagged go, ask, never or always'). One line is read whole: Coordination's who-may-post note, which
carried the act's own id ('Identity may refuse to Owner'), is said again the way the runtime says it now (MAY_NOTE).

One more kind of line is read word by word, and only where it is composed: a sentence a model wrote in its own words (plainly,
said_plainly). The agent is taught accept, counter and reject, so its why may use them, or grant and refuse, as the verbs and as the
nouns they are ('the full grant would go past the room'): each is said by what it is where it stands, a word the owner said (a department
for grant proposals, a shop's counter, refuse collection) stays as they said it, and a sentence the pass cannot say with its grammar
whole, or a word of the bargain that is left in it, is told not to be plain, so that its composer says the answer in words of its own and
never posts the garble. That sentence is said once in the owner's words where its function composes it (Priority's, in priority_post),
so the post, the record, the ledger's line and every read of them agree; a record written before that is said again on the way out by
the same function, not by a table of a pane's own.
"""
import functools
import re
import types

# The bargain in the owner's words wherever a definition's name, a run's line or a ledger row's summary carries the inside
# word. A step's name, the default summaries j2_runtime writes (J.on_post, J.refused, the owner's answer), the lines the
# functions' runs say (engine_runtime's priority_answer, adapt_*, identity_*), what Identity tells the owner (_j2_settle,
# identity_closed, identity_drop), the text of the ask it puts to the owner and a step's check notes all pass through
# here. Phrases first, longest first, then the plain verbs.
BARGAIN_WORDS = (("Send the granted line to Root's check", "Send the line Priority said yes to, to Root's check"),
                 ("File a granted round", "File a round Priority said yes to"),
                 ("Take the refusal to Identity", "Take Priority's no to Identity"),
                 ("Take the counter, or take it to Identity", "Take Priority's ask for less, or take it to Identity"),
                 ("Grant, refuse or counter", "Say yes, ask for less, or say no"),
                 ("grants each engine its envelope", "gives each engine its limit"),
                 ("granted an envelope to each engine", "gave each engine its limit"),
                 ("granted an envelope to each function", "gave each function its limit"),
                 ("Granted within the envelope.", "Said yes within the limit."),
                 # Root's check, and what Identity tells the owner of it (round 2, gap 4): a plan sent back, never refused
                 ("Root's check refused the workflow", "Root's check sent the plan back"),
                 ("Root's check refused the plan", "Root's check sent the plan back"),
                 ("Root's check refused it", "Root's check sent it back"),
                 ("waits for the workflow to be granted and registered", "waits for Priority's yes and Root's check"),
                 ("passed, asked or refused", "passed, asked or stopped"),
                 # the conflict Identity puts to the owner, and the owner's no (identity_closed, identity_drop); every ask's
                 # answers, as an ask filed before engine_runtime._answers said them (the line, the engine, the outside-the
                 # -site, the instructions and the conflict asks, and Root's Setup by hand), so the text and the buttons agree
                 (", Refuse to drop it.", ", or say no to drop it."), (", Refuse to ", ", or say no to "),
                 ("; Refuse to ", ", or say no to "), (", or refuse and ", ", or say no and "),
                 ("or you refuse it", "or you say no to it"),
                 ("Priority did not grant", "Priority did not say yes to"), ("did not grant", "did not say yes to"),
                 ("on your refusal", "because you said no"), ("on the owner's refusal", "because the owner said no"),
                 ("your refusal", "your no"),
                 ("Take a refusal", "Take a no"), ("Drop what was refused", "Drop what was turned down"),
                 ("Hear a refusal", "Hear a no"), ("Note the refusal", "Note the no"),
                 ("The owner refused it.", "The owner said no."), ("refused by the owner", "turned down by the owner"),
                 ("the owner's refusal", "the owner's no"),
                 ("took Priority's counter", "took Priority's ask for less"), ("take Priority's counter", "take Priority's ask for less"),
                 ("Priority's counter", "Priority's ask for less"), ("Priority's refusal", "Priority's no"),
                 ("Priority's grant's stamp", "Priority's yes"), ("Priority's grant", "Priority's yes"),
                 ("Priority granted", "Priority said yes to"), ("Priority refused", "Priority said no to"),
                 ("Priority countered (", "Priority asked for less ("), ("Priority countered", "Priority asked for less on"),
                 ("countered the line", "asked for less on the line"), ("granted the line", "said yes to the line"),
                 ("refused the line", "said no to the line"), ("granted a trial", "said yes to a trial"),
                 ("refused a trial", "said no to a trial"), ("refused the ask", "said no to the ask"), ("refused: ", "said no: "),
                 ("a stamp or a refusal", "a stamp or a no"), ("or a refusal", "or a no"),
                 # what a step's check said, on its card: a decision's words, never the bargain's inside ones
                 ("the answer is accept, reject or counter", "the answer is say yes, ask for less or say no"),
                 ("the verdict is one of admit, wait, refuse", "the verdict is let through, wait or stop"),
                 ("the verdict is one of go, ask, refuse", "the verdict is go, ask or stop"),
                 # the same checks as the interface lists them (layer_schema.CHECKS), on a function's page (A1 C8)
                 ("a gate's verdict is admit, wait or refuse", "a gate's verdict is let through, wait or stop"),
                 ("a verdict is go, ask or refuse", "a verdict is go, ask or stop"),
                 # what an instruction file is for, as its Settings row says it (identity's take: the verdict on a request)
                 ("a request: go, ask or refuse", "a request: go, ask or stop"),
                 # the words in use as a field of Identity's take shows them (K2: a typed value is on its Settings at rest)
                 ("refuse: it breaks a rule", "stop: it breaks a rule"),
                 # the five points of Identity's standard as its completeness row shows them: the rule tags in the words the
                 # badge prints (the pane says 'never' for the refuse tag; the tag itself, a data value, stays 'refuse')
                 ("go, ask, refuse or always", "go, ask, never or always"),
                 ("Countered.", "Asked for less."), ("Refused.", "Said no."),
                 # Priority's role words, as its Settings shows them (A3.4.5): the agent is told the contract's words, accept,
                 # counter and reject, beside the shape of its answer; the owner reads the same lines in the screen's
                 ("accept a proposal, counter it with a smaller limit or scope, or reject it, always",
                  "say yes to a proposal, ask for less with a smaller limit or scope, or say no to it, always"),
                 ("one answer: accept, with its limit; counter, with a smaller limit or scope; or reject, with a reason",
                  "one answer: say yes, with its limit; ask for less, with a smaller limit or scope; or say no, with a reason"))


# Coordination's who-may-post check as a record written before it said the act in the owner's words kept it, the act's
# own id on its card: 'Identity may refuse to Owner', 'Owner may reject-proposal to Identity', 'Audit may not post inform
# to Identity' (engine_runtime.coord_edge). Read again, the note says the act the way coord_edge says it now (ACT_SAYS).
# Only a note that names who posts and to whom, as Coordination's table names them (the owner, Root and the five), is
# read whole: a line of any other kind ('You may request to see the page') is never taken for one.
POSTERS = r"(?:Owner|Root|Identity|Adaptation|Priority|Coordination|Audit)"
MAY_NOTE = re.compile(r"^(?P<src>%s) may (?P<not>not post )?(?P<act>[a-z-]+) to (?P<dst>%s(?:, %s)*|nobody)$" % (POSTERS, POSTERS, POSTERS))


def _may_note(line):
    """A who-may-post note in the act's own id, said again in the owner's words; None for every other line."""
    m = MAY_NOTE.match(line)
    if not m:
        return None
    import engine_runtime as R                     # the act's words are the runtime's (ACT_SAYS), said once there
    if m.group("act") not in R.ACT_SAYS:
        return None
    dst = [] if m.group("dst") == "nobody" else [x.strip() for x in m.group("dst").split(",")]
    return R._may_note(m.group("src"), dst, m.group("act"), "may not" if m.group("not") else "may")


@functools.lru_cache(maxsize=1)
def standard_lead():
    """A pattern for Root's standards named by their id where a note leads with one ('reads_known: Site 2 reads ...'): the
    ids of layer_schema.WORKFLOW_STANDARDS, a word and a colon. The record keeps the id (a step's notes name the standard a
    fault breaks, and the pane lists each check by id beside what it says); the owner reads the fault, which stands as a
    sentence of its own."""
    import layer_schema as S                       # lazy: the interface is not needed to say a bargain's words
    return re.compile(r"(?<![\w-])(?:%s): ?" % "|".join(re.escape(i) for i, _, _, _ in S.WORKFLOW_STANDARDS))


#: each phrase of BARGAIN_WORDS to be said, with the pattern that finds it where it begins a word ('granted the line' is not found in
#: 're-granted the line', which is read word by word, with its 'again'); a phrase that begins with a mark ('; Refuse to ') is found as it is
_PHRASES = tuple((inside, re.compile(r"(?<![\w-])" * inside[:1].isalnum() + re.escape(inside)), said) for inside, said in BARGAIN_WORDS)


def plain(line):
    """One line in the owner's words; '' for nothing."""
    line = str(line or "")
    said = _may_note(line)
    if said is not None:
        return said
    for inside, rx, said in _PHRASES:
        if inside in line:
            line = rx.sub(lambda m, said=said: said, line)
    return standard_lead().sub("", line)


#: The bargain's inside words as a model uses them in a sentence of its own, and what the screen says in their place (said yes,
#: asked for less, said no; never grant, counter or refuse). plain() says phrases and never a bare verb, so a sentence a model
#: wrote is read again word by word, by family: grant (g), reject (r), refuse (f) and counter (c), each in its verb forms (the
#: base, the third person, the past and the -ing) and its noun forms. Where a word stands says what it is (_is_noun): the verb is
#: said as the act ('say yes to'), the noun as the answer ('yes', 'no', 'ask for less'), a participle before a noun as the answer it
#: names ('the said-yes line'). Every form is spelt out, so the sentence keeps its grammar.
_FORMS = ('base', 's', 'ed', 'ing')
_VERBS = types.MappingProxyType({'g': ('say yes to', 'says yes to', 'said yes to', 'saying yes to'),
                                 'r': ('say no to', 'says no to', 'said no to', 'saying no to'),
                                 'f': ('say no to', 'says no to', 'said no to', 'saying no to'),
                                 'c': ('ask for less', 'asks for less', 'asked for less', 'asking for less')})
_NOUNS = types.MappingProxyType({'g': ('yes', 'yeses'), 'r': ('no', 'nos'), 'f': ('no', 'nos'), 'c': ('ask for less', 'asks for less')})
_BEFORE_A_NOUN = types.MappingProxyType({'g': 'said-yes', 'r': 'said-no', 'f': 'said-no', 'c': 'asked-for-less'})
#: a participle that nothing is done by or to ('the offer is rejected', 'Not granted', 'granted by Priority') is the answer it was given
_GIVEN = types.MappingProxyType({'g': 'given a yes', 'r': 'given a no', 'f': 'given a no', 'c': 'met with an ask for less'})
#: 'refuse to grant' is 'decline to say yes to': a refusal to do something, said without the word
_DECLINES = ('decline', 'declines', 'declined', 'declining')
_VERB_FORMS = types.MappingProxyType({'g': ('grant', 'grants', 'granted', 'granting'), 'r': ('reject', 'rejects', 'rejected', 'rejecting'),
                                      'f': ('refuse', 'refuses', 'refused', 'refusing'), 'c': ('counter', 'counters', 'countered', 'countering')})
#: the nouns of the same family, singular and plural: the answer a word names ('the refusal stands', 'a counter-offer of two')
_NOUN_FORMS = types.MappingProxyType({'r': (('rejection', 'rejections'),), 'f': (('refusal', 'refusals'),),
                                      'c': (('counter-offer', 'counter-offers'), ('counteroffer', 'counteroffers'), ('counter-proposal', 'counter-proposals'),
                                            ('counterproposal', 'counterproposals'), ('counter-bid', 'counter-bids'), ('counterbid', 'counterbids'))})
_FORM_OF = {w: (fam, form) for fam, ws in _VERB_FORMS.items() for w, form in zip(ws, _FORMS)}
_FORM_OF.update({w: (fam, form) for fam, pairs in _NOUN_FORMS.items() for one, many in pairs for w, form in ((one, 'n'), (many, 'ns'))})
_FORM_OF['grantable'] = ('g', 'able')
INSIDE = types.MappingProxyType({**{w: _VERBS[fam][_FORMS.index(form)] for w, (fam, form) in _FORM_OF.items() if form in _FORMS},
                                 **{w: _NOUNS[fam][form == 'ns'] for w, (fam, form) in _FORM_OF.items() if form in ('n', 'ns')},
                                 'grantable': 'fit for a yes'})
#: a word with the prefix a model puts on it ('ungranted', 're-granted') is read as the word, with the 'not' or the 'again' it carries
_INSIDE_RE = re.compile(r'(?<![\w-])(?P<pre>(?:un|re|non)-?)?(?P<w>%s)(?![\w-])' % '|'.join(re.escape(w) for w in sorted(_FORM_OF, key=len, reverse=True)), re.I)
#: 'the granting of' is 'the saying yes to': the gerund that is a noun takes its 'of' with it
_GERUND_OF = re.compile(r"(?<![\w-])(?P<det>the|a|an|this|that|its|their|any|each|no|full|whole|partial)(?P<sp>\s+)(?P<w>granting|rejecting|refusing|countering)\s+of(?![\w-])", re.I)

#: what stands before and after a word says whether it is a noun or a verb. A determiner, an adjective of size, a number or a
#: possessive before it is a noun's; a pronoun, a name, 'to' or a modal before it is a verb's; 'of', 'is' and the like after it are a noun's,
#: and a determiner, a name or a number after it are a verb's object.
_DETERMINERS = frozenset('a an the this that these those its their his her my your our any each every no some another such all both either neither which whose what'.split())
_ADJECTIVES = frozenset('full whole partial small smaller large larger big bigger first second third last next new final further extra single total half same other '
                        'real clear simple blanket outright more less least most fewer many few several little part'.split())
_NUMBERS = frozenset('zero one two three four five six seven eight nine ten eleven twelve dozen'.split())
#: before 'grants' these make it the verb: one thing doing it (each grants, it grants, an offer that grants)
_ONE_DOING = frozenset('a an each every another this that one either neither it he she which who'.split())
_RELATIVE = frozenset(('that', 'which', 'who'))
_DOERS = frozenset("i we you they who to will would can could shall should may might must not never cannot don't doesn't didn't won't wouldn't can't couldn't shouldn't "
                   "also still then just always simply even instead priority adaptation identity root coordination audit owner".split())
_NOUN_AFTER = frozenset('of is are was were would will for fits fit does did has have had can could should may might must left made stands stand exceeds exceed '
                        'goes go went cost costs happen happens remain remains hold holds cover covers rise rises'.split())
#: before a participle these make it the passive ('is granted', 'been refused', 'neither granted nor refused'): nothing did it that the sentence names
_BE = frozenset('is are was were be been being am get gets got getting remain remains remained stay stays seem seems neither nor either'.split())
_OBJECT_STARTS = frozenset('a an the this that these those its their his her my your our any each every all both some no none nothing anything everything '
                           'something it them him me us you one another more less only half most much many few other'.split()) | _NUMBERS
#: after 'say yes to' these make it 'say yes': a word that begins no object (a preposition, a conjunction, a verb that follows its
#: subject, an adverb). 'by' is not one: 'said yes to by Priority' is the passive, with its 'to'.
_NOT_AN_OBJECT = frozenset('in on at with within without from into under over after before until while once though although unless whereas because since as when '
                           'if given so but and or nor yet then than also too again already anyway instead now today tomorrow here there earlier later twice '
                           'fully completely entirely outright altogether partly partially for of is are was were be been being am would will can could '
                           'should may might must shall has have had do does did'.split())
_TO_DROPPED = re.compile(r'\b(say|says|said|saying)\s+(yes|no)\s+to(?=\s*(?:$|[.,;:!?)\]}\u2013\u2014]|-(?=\s)|(?:%s)(?![\w-])))' % '|'.join(sorted(_NOT_AN_OBJECT)), re.I)
_PREV = re.compile(r"(?:(?P<w>[\w\x00'-]*[\w\x00'])|(?P<p>[^\w\s]))\s*$")
_NEXT = re.compile(r"\s*(?:(?P<w>[\w\x00][\w\x00'-]*)|(?P<p>[^\w\s]))")

#: 'order' as a verb, which the screen keeps off as it keeps off grant (Priority prices and holds and never orders), said as
#: 'ask for'. Only where it is a verb for certain: after a subject that did the ordering, or a modal; 'orders' (more than one,
#: or it does) as the asks Priority gives or the asking itself. 'order' as the word for a line's order ('in order', 'the order of
#: the line', 'Priority order: Plan, Write', 'ordered by cost') is the ordinary word, and is left.
_ORDER_RE = re.compile(r"(?<![\w-])(?P<w>orders|ordered|order)(?![\w-])", re.I)
_ORDERING_BEFORE = frozenset("i we you they to will would shall should must can could may might not never cannot don't doesn't didn't won't".split())
_ORDERED_SO = frozenset('by in from alphabetically first last ascending descending'.split())

#: what is left of the bargain's inside words after the pass is not plain: a form it does not know (grantee, counterpart)
_LEFT_IN = re.compile(r"[\w'-]*(?:grant|counter|refus|reject)[\w'-]*|(?<![\w-])orders(?![\w-])", re.I)


def owner_tokens(owners):
    """The words the owner said, as a set to look a word up in: the text lowercased and split into its words. `owners` is a text
    (engine_runtime._owners_words), a set of words already, or a list of texts; nothing is nothing."""
    if isinstance(owners, (set, frozenset)):
        return frozenset(owners)
    if isinstance(owners, str):
        owners = (owners,)
    return frozenset(w for text in owners or () for w in re.findall(r"[a-z][a-z'-]*", str(text or '').lower()))


def _owners_own(word, owners):
    """A word the owner said is theirs (the grant of a grant proposal, a shop's counter, refuse collection), whether the sentence
    has it in the singular or the plural, and is never said again, as Identity's net leaves it (engine_runtime.plain_faults)."""
    w = word.lower()
    return bool(owners) and (w in owners or w + 's' in owners or (w.endswith('s') and w[:-1] in owners))


def _around(text, m):
    """The word before a match, the word before that, and the word after it, each as (lowercase, as written); (None, None) for the
    edge of the text or a mark of punctuation, which says only that no word stands there."""
    chunk = text[max(0, m.start() - 80):m.start()]
    before = _PREV.search(chunk)
    before2 = _PREV.search(chunk[:before.start()]) if before and before.group('w') else None
    after = _NEXT.match(text, m.end())
    pick = lambda g: ((g.group('w').lower(), g.group('w')) if g and g.group('w') else (None, None))   # noqa: E731
    return pick(before), pick(before2), pick(after)


def _starts_object(word):
    """Whether the next word begins what a verb is done to: a determiner, a pronoun, a number, a name (a capital, or a workflow's name
    kept apart) -- as against a preposition, an auxiliary, an adverb or the end."""
    low, raw = word
    return bool(low) and (raw[0] == '\x00' or raw[0].isupper() or raw[0].isdigit() or low in _OBJECT_STARTS)


def _is_noun(form, before, after):
    """Whether grant, grants (or reject, counter, order) is a noun here, from the word before and the word after: 'a partial grant
    of two', 'no grants left' are nouns; 'I grant none', 'an offer that grants Plan', 'each grants one run' are verbs."""
    (pw, praw), (nw, _) = before, after
    obj = _starts_object(after)
    if form == 's' and pw in _ONE_DOING:
        return False
    if pw in _RELATIVE and obj:
        return False
    if pw and (pw in _DETERMINERS or pw in _NUMBERS or pw[0].isdigit() or pw.endswith("'s") or pw.endswith("s'")):
        return True
    if pw in _ADJECTIVES:
        return not obj
    if pw in _DOERS or (praw and (praw[0] == '\x00' or praw[0].isupper())):
        return False
    if nw in _NOUN_AFTER:
        return True
    if obj:
        return False
    return form == 's' and pw is None and nw is None      # 'Grants: none' is the count; 'the agent refuses.' is the verb, and so is a base form


def _before_a_noun(before, after):
    """Whether a participle stands before the noun it describes ('the granted line'), not after what it was done to ('the line
    was granted')."""
    (pw, _), (nw, _) = before, after
    return bool(pw) and bool(nw) and nw not in _NOT_AN_OBJECT and nw not in ('by', 'to') and (
        (pw in _DETERMINERS and pw not in _RELATIVE) or pw in _NUMBERS or pw in _ADJECTIVES or pw.endswith("'s") or pw.endswith("s'"))


def _passive(before, before2, after):
    """Whether a participle is the passive with nothing named that did it, or only 'by' what did: 'is rejected', 'has not been
    granted', 'Not granted', 'granted by Priority'."""
    (pw, _), (p2, _), (nw, _) = before, before2, after
    return nw == 'by' or pw in _BE or (pw == 'not' and (p2 is None or p2 in _BE))


def _as(word, out):
    """The replacement in the case of the word: a capital stays a capital, all capitals stay all capitals."""
    return out.upper() if len(word) > 1 and word.isupper() else (out[:1].upper() + out[1:] if word[:1].isupper() else out)


def _inside(m, text, owners, faults):
    """One inside word, said as the owner says it, by what it is where it stands. A form this cannot say plainly is said as near as
    it can and noted in `faults`: the sentence is not plain."""
    word = m.group(0)
    if _owners_own(word, owners):
        return word
    pre, (fam, form) = (m.group('pre') or '').lower().rstrip('-'), _FORM_OF[m.group('w').lower()]
    before, before2, after = _around(text, m)
    nw, kind = after[0], 'verb'
    if form == 'n' and fam == 'f' and nw == 'to':
        out, kind = 'declining', 'noun'                    # a refusal to grant: declining to say yes to
    elif form in ('n', 'ns'):
        out, kind = _NOUNS[fam][form == 'ns'], 'noun'
    elif form == 'able':
        out, kind = 'fit-for-a-yes' if _before_a_noun(before, after) else 'fit for a yes', 'noun'
    elif form in ('base', 's') and not pre and _is_noun(form, before, after):
        out, kind = _NOUNS[fam][form == 's'], 'noun'
    elif form == 'ed' and (_before_a_noun(before, after) or (pre == 'un' and nw and nw not in _NOT_AN_OBJECT and nw not in ('by', 'to') and not _starts_object(after))):
        out, kind = _BEFORE_A_NOUN[fam], 'noun'                # the granted line; ungranted lines (which this cannot say: see pre, below)
    elif form == 'ed' and _passive(before, before2, after):
        out, kind = _GIVEN[fam], 'passive'
        if nw == 'to' and fam != 'c':
            faults.append(word)                            # 'granted to Plan' gives, and is not 'given a yes to Plan'
    else:
        out = _VERBS[fam][_FORMS.index(form)]
        if nw == 'to' and fam == 'f' and not pre:
            out = _DECLINES[_FORMS.index(form)]            # refused to grant: declined to say yes to
        elif nw == 'to' and fam != 'c':
            faults.append(word)
            out = out[:-3]
        elif fam == 'c' and _starts_object(after):
            out += ' on'
    if pre == 're' and kind in ('verb', 'passive'):        # said yes again to the line; said yes again
        core, tail = (out[:-3], out[-3:]) if out.endswith((' to', ' on')) else (out, '')
        out = core + ' again' + (tail if nw and nw not in _NOT_AN_OBJECT else '')
    elif pre == 'un' and form == 'ed' and kind in ('verb', 'passive'):
        out = 'not ' + out
    elif pre:
        faults.append(word)                                # a prefix this does not read: non-granted, ungranted lines, regrantable
        out = 'not-' + out if pre == 'un' and kind == 'noun' else out
    return _as(word, out)


def _ordered(m, text, owners):
    """'order' as a verb or as the asks Priority gives, said as 'ask for' and 'asks'; as the line's order, as it is."""
    word = m.group('w')
    if _owners_own(word, owners):
        return word
    low, (before, _, after) = word.lower(), _around(text, m)
    (pw, _), (nw, _) = before, after
    if low == 'order':
        out = 'ask for' if pw in _ORDERING_BEFORE and nw != 'by' else None
    elif low == 'orders':
        out = 'sorts' if nw == 'by' else ('asks' if nw is None or _is_noun('s', before, after) else 'asks for')
    elif nw in _ORDERED_SO:
        out = None                                          # ordered by cost
    elif nw == 'to' and pw not in _DETERMINERS and pw not in _ADJECTIVES:
        out = 'asked'                                       # ordered to wait
    elif pw in ('priority', 'it', 'he', 'she', 'which', 'that') or (_starts_object(after) and pw not in _DETERMINERS and pw not in _ADJECTIVES):
        out = 'asked for'
    else:
        out = None
    return word if out is None else _as(word, out)


def plainly(text, keep=(), owners=()):
    """A sentence a model wrote, in the owner's words, and whether it is plain: (the sentence, True) when the pass could say every
    inside word in it as the owner does, (the sentence as near as it came, False) when a form is left that it cannot say with its
    grammar whole (a grantee, 'granted to Plan', 'ungranted lines') or a word of the bargain is still in it. The one who composes
    the sentence puts a sentence of its own in place of one that is not plain (Priority's, from the answer and the room), so a
    garbled line is never posted.
    `keep`: the names in the sentence that are a workflow's or an engine's and stay as they are, though they are an inside word (a
    workflow called Grant, or Order, is not said yes to). `owners`: the words the owner said (owner_tokens), kept as they said them,
    as Identity's net keeps them: a department for grant proposals reads back 'grant proposal', a shop its counter, a council its
    refuse collection."""
    owners, held, text = owner_tokens(owners), {}, str(text or '')
    for name in sorted({str(n) for n in keep or () if n}, key=len, reverse=True):
        mark = '\x00%d\x00' % len(held)
        text, n = re.subn(r'(?<![\w-])%s(?![\w-])' % re.escape(name), mark, text)
        if n:
            held[mark] = name
    faults = []
    text = plain(text)
    text = _GERUND_OF.sub(lambda m: m.group('det') + m.group('sp') + _VERBS[_FORM_OF[m.group('w').lower()][0]][3] + (' on' if m.group('w').lower() == 'countering' else ''), text)
    text = _INSIDE_RE.sub(lambda m: _inside(m, text, owners, faults), text)
    text = _TO_DROPPED.sub(r'\1 \2', text)
    text = _ORDER_RE.sub(lambda m: _ordered(m, text, owners), text)
    text = re.sub(r'\b([Aa])(?= ask(?:ed)?\b)', r'\1n', text)
    plain_now = not faults and not [w for w in _LEFT_IN.findall(text) if not _owners_own(w, owners)]
    for mark, name in held.items():
        text = text.replace(mark, name)
    return text, plain_now


def said_plainly(text, keep=(), owners=()):
    """A sentence a model wrote, in the owner's words: the phrases of BARGAIN_WORDS, then the inside words (INSIDE) said again by what
    each is where it stands, 'I reject this; I would counter with two' as 'I say no to this; I would ask for less with two', 'a partial
    grant of two' as 'a partial yes of two', 'no grants left' as 'no yeses left'. 'Order' as a verb (Priority never orders) is 'ask for'. A
    capital stays a capital. Said twice it says the same, so a sentence composed in the owner's words and read again on its way
    out is not changed by the second reading. Only for a sentence a model wrote, or a line made of one: the owner's own words, and any
    data value (a rule's tag, an answer's id), are not its. What it cannot say plainly it says as near as it can (plainly says whether
    that is plain); see there for `keep` and `owners`."""
    return plainly(text, keep, owners)[0]


def _keep(value):
    """A line that is there stays a line, said plainly; a missing one stays missing (None is not '')."""
    return plain(value) if isinstance(value, str) else value


def kept(line, words):
    """A line that ends with the owner's own words (the record says which: an ask's or a run's `words`), said plainly up
    to them, the words as the owner said them; any other line said plainly. A missing line stays missing."""
    if not isinstance(line, str):
        return line
    if isinstance(words, str) and words and line.endswith(words):
        return plain(line[:-len(words)]) + words
    return plain(line)


def runs(rows):
    """Run rows as a screen prints them: each one's line ('what') in the owner's words, the owner's own words at its end
    (the run's `words`: 'took the owner's words: ...') as they said them, the rest as the record keeps it."""
    return [dict(r, what=kept(r.get("what"), r.get("words"))) if isinstance(r, dict) else r for r in rows or []]


def _shown(value):
    """The words of a field in use as one line of a Settings row, said in the owner's words: a list as its items, a text with
    its lines run together. The value itself is the owner's to change and stays as it is (the row's `value`)."""
    return plain(" ".join(("; ".join(str(x) for x in value) if isinstance(value, list) else str(value or "")).split()))


#: A part whose name is an inside word, as its Settings row calls it: Adaptation's 'refused' is the line it is sent when Root's
#: check sent the plan back; the parts of a function's role (A3.4.2) are code names (role_may), said as what they are. The part
#: keeps its name (the row's `part` is what a change names); the row prints the label.
PART_SAYS = {"refused": "sent back", "done": "when it is done", "role_is": "what it is", "role_may": "what it may do",
             "role_procedure": "how it decides", "role_patterns": "what it avoids", "role_block": "its role, as the agent is sent it"}


def _instruction_part(p):
    if not isinstance(p, dict):
        return p
    out = dict(p, fields=[dict(f, shown=_shown(f.get("value"))) if isinstance(f, dict) else f for f in p.get("fields") or []])
    if p.get("part") in PART_SAYS:
        out["label"] = PART_SAYS[p["part"]]
    return out


def _instruction_row(r):
    """One row of a function's instructions: a file of the first design (its line said plainly) or a group of the interface's
    typed fields (its line, each part's label and each field's words in use as `shown`)."""
    if not isinstance(r, dict):
        return r
    out = dict(r, lead=_keep(r.get("lead")))
    if isinstance(r.get("parts"), list):
        out["parts"] = [_instruction_part(p) for p in r["parts"]]
    return out


def steps(view):
    """An engine or a function as its steps (engine_runtime.steps_view), as its card prints it: the description, each
    step's name, the handler it sits under, its last check notes and who moved its rung, what it hears, the names of
    the steps that hold its start, and the line that says what each of its instruction files is for (its Settings), in
    the owner's words; and each typed field's words in use, said again as `shown` (the row prints that; the field's
    `value` is the owner's to change and stays). Ids, rungs, checks and numbers are left as they are, and so is an
    instruction file's own text, which is the file the owner changes."""
    if not view:
        return view
    out = dict(view, description=_keep(view.get("description")), hears=[plain(h) for h in view.get("hears") or []])
    rows = []
    for s in view.get("steps") or []:
        s = dict(s, name=_keep(s.get("name")), under=_keep(s.get("under")))
        if isinstance(s.get("last"), dict):
            s["last"] = dict(s["last"], notes=[plain(x) for x in s["last"].get("notes") or []] or s["last"].get("notes"))
        s["history"] = [dict(h, by=_keep(h.get("by"))) for h in s.get("history") or []]
        rows.append(s)
    out["steps"] = rows
    if isinstance(view.get("instructions"), list):
        out["instructions"] = [_instruction_row(r) for r in view["instructions"]]
    start = view.get("start")
    if isinstance(start, dict):
        out["start"] = dict(start, on=[plain(x) for x in start.get("on") or []],
                            unless=[dict(u, name=_keep(u.get("name"))) for u in start.get("unless") or []])
    return out


def asks(rows):
    """Asks as a screen prints them: the text Identity wrote in the owner's words. An ask that carries the owner's own
    words at the end of its text (an outside-the-site ask: the lead, then the words) keeps those words as they said
    them; ids, kinds and the rest stay as the record keeps them."""
    out = []
    for a in rows or []:
        if not isinstance(a, dict) or not isinstance(a.get("text"), str):
            out.append(a)
            continue
        out.append(dict(a, text=kept(a["text"], a.get("words"))))
    return out


def status(view):
    """The department's status read (website_dept.status): what runs now, the asks and what waits on them, in the
    owner's words."""
    if not view:
        return view
    out = dict(view, running=runs(view.get("running")))
    for k in ("asks", "escalated"):
        if k in view:
            out[k] = asks(view.get(k))
    if "waits" in view:
        out["waits"] = [dict(w, why=_keep(w.get("why"))) if isinstance(w, dict) else w for w in view.get("waits") or []]
    return out


def _turn(t):
    """One turn of a chat: what a function said, and its thinking, in the owner's words; the owner's own turns stay as
    they said them, and so does a function's turn whose line is the owner's words it carries on (quoted: Identity
    handing the request to Adaptation, Adaptation proposing it to Priority; engine_runtime.TURN)."""
    if not isinstance(t, dict) or t.get("src") == "Owner" or t.get("quoted"):
        return t
    return dict(t, line=_keep(t.get("line")))


def fn_chat(view):
    """One function's chat (engine_runtime.fn_chat_view), as its Chat tab prints it: each line a function said and each
    line of its thinking (a step's name and its rung, a gate and its verdict) in the owner's words (PRD M1.7)."""
    if not view:
        return view
    return dict(view, turns=[_turn(t) for t in view.get("turns") or []])


def chat(view):
    """The owner's own chat (engine_runtime.chat_view), on a department or on Root: what Identity told the owner, and the
    asks it put to them and the questions it answered there, in the owner's words (PRD M1.7)."""
    if not view:
        return view
    out = dict(view, turns=[_turn(t) for t in view.get("turns") or []])
    for k in ("asks", "answered"):
        if k in view:
            out[k] = asks(view.get(k))
    return out


def engine(view):
    """One engine's card (website_dept.engine_view): its runs' lines, and its last one's, in the owner's words."""
    if not view:
        return view
    out = dict(view)
    if "runs" in out:
        out["runs"] = runs(out["runs"])
    if isinstance(out.get("last"), dict):
        out["last"] = dict(out["last"], what=kept(out["last"].get("what"), out["last"].get("words")))
    return out


def map_view(view):
    """The department's map read (website_dept.map_view), as the Map and the function cards print it: the last line of
    each function and engine, the recent runs (Identity's 'Stamped by rule'), what runs now and the day's timeline, in
    the owner's words. The goal, done-when, rules and the owner's requests are the owner's own words and stay."""
    if not view:
        return view
    out = dict(view)
    out["systems"] = [dict(s, last=kept(s.get("last"), s.get("words"))) for s in view.get("systems") or []]
    out["engines"] = [engine(e) for e in view.get("engines") or []]
    out["recent"] = runs(view.get("recent"))
    out["status"] = status(view.get("status"))
    health = view.get("health")
    if isinstance(health, dict):
        out["health"] = dict(health, timeline=runs(health.get("timeline")))
    return out
