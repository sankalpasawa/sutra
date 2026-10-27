"""layers/identity/tighten.py -- a department's rule can only tighten an inherited one (PRD A3.7.4, BL-2; ruling S-08).

Pure functions and no import of the runtime: the same rules and the same line give the same answer, and a layer module or a
test reads them without loading the app. Identity calls them in two places (engine_runtime._rule_ask, before a rule is
asked for, and identity_apply's rule branch, before it is written).

    normalise(line)               a rule's line as it is compared: case folded, its leading always / never / do not / don't
                                  and its punctuation taken off, its white space collapsed
    rank(tag, line)               how strict a rule is: go 0, ask 1, refuse 2; an `always` rule 2 only when its line is a
                                  prohibition; None when the rule cannot be ranked (a positive `always`, `goal`, an unknown tag)
    rule_faults(inherited, line, tag)
                                  one plain sentence for each inherited rule that says the same thing more strictly

WHAT THIS DOES NOT DO (BL-2b). It compares by the normalised line, not by meaning: a looser rule worded differently is not
caught, a positive `always` rule is never compared with a `go` rule, and Root's own born rules are `always` and `go`, so today
the check reaches a rule an ancestor stamped. A stricter law (a model reading of looseness) is a later amendment.
"""
import re

#: how strict a tag is, among the three that order. `always` ranks by its line (see rank); `goal` and any other tag are not ranked
RANKS = {'go': 0, 'ask': 1, 'refuse': 2}
#: what a rule's tag makes the department do, in the words Identity uses with the owner (engine_runtime.RULE_SAYS): the owner is
#: never shown a tag
SAYS = {'go': 'it may do this', 'ask': 'it asks you first', 'refuse': 'it never does this', 'always': 'it always does this'}

_APOSTROPHES = '’‘ʼ`'
_LEAD = re.compile(r"^(?:always|never|do\s+not|don't)\b")
_PROHIBITION = re.compile(r"^(?:never|do\s+not|don't)\b")


def _fold(line):
    """The line in lower case, its white space collapsed, its curly apostrophes straight, and nothing before its first word."""
    text = ' '.join(str(line or '').casefold().split())
    for mark in _APOSTROPHES:
        text = text.replace(mark, "'")
    return re.sub(r'^\W+', '', text)


def normalise(line):
    """The line as rules are compared: case folded; a leading `always`, `never`, `do not` or `don't` taken off; the
    punctuation taken off; the white space collapsed. 'Never publish prices.' and 'publish  PRICES' are the same line."""
    text = _LEAD.sub('', _fold(line), count=1)
    return ' '.join(re.sub(r'[^\w\s]', ' ', text).split())


def prohibition(line):
    """The line forbids something: it starts with never, do not or don't."""
    return bool(_PROHIBITION.match(_fold(line)))


def rank(tag, line):
    """How strict the rule is: `go` 0, `ask` 1, `refuse` 2; an `always` rule 2 when its line is a prohibition ('Never ...'),
    otherwise None, as is `goal` or a tag that is not one of the store's. A rule with no rank is never compared."""
    if tag in RANKS:
        return RANKS[tag]
    if tag == 'always' and prohibition(line):
        return RANKS['refuse']
    return None


def _quoted(rule):
    """An inherited rule as a sentence names it: its line, and what it makes the department do. The words follow the rank the
    rule was compared at, not its raw tag: a prohibition tagged `always` ranks as `refuse`, so it is glossed as one ('it never
    does this'), never as 'it always does this' beside a line that says never."""
    line = ' '.join(str(rule.get('line') or '').split()).rstrip('.')
    tag = rule.get('tag')
    says = SAYS['refuse'] if rank(tag, rule.get('line')) == RANKS['refuse'] else SAYS.get(tag, 'it holds')
    return '%s (%s)' % (line, says)


def rule_faults(inherited, line, tag):
    """One plain sentence for each inherited rule whose normalised line is the new rule's and which is stricter than it, naming
    that rule; [] when the new rule loosens nothing. A rule that cannot be ranked, on either side, is never compared. The
    sentences are the owner's to read, so they say what the rule makes the department do and never its tag."""
    mine, key = rank(tag, line), normalise(line)
    if mine is None or not key:
        return []
    out = []
    for rule in inherited or []:
        if not isinstance(rule, dict):
            continue
        theirs = rank(rule.get('tag'), rule.get('line'))
        if theirs is None or theirs <= mine or normalise(rule.get('line')) != key:
            continue
        out.append('The rule above says: %s.' % _quoted(rule))
    return out
