"""The shared scalars of the A5 models (A5.4): the ids, the stamp and the department ref, written once.

`TS` is the interface's own stamp (`common.ISO`, the head of W.now(): a date and, after it, whatever the clock says). `REF` is the
department-ref rule `website_dept.ddir` enforces on every path; department.py bounds a ref by length only, so the pattern lives here.
Nothing here imports the app."""
import re

from .common import ISO, WORD
from .faults import faults_error

TS = ISO
MID_RE = r'^m-[0-9a-f]{12}$'
GID_RE = r'^g-[0-9a-f]{12}$'
REF_RE = r'^[A-Za-z0-9_.-]{1,80}$'
CONV_RE = r'^shc-[0-9a-z]{6,40}$'                 # shadow_conversations.ID_RE
KIND_RE = r'^[a-z][a-z0-9-]*$'
OPEN_REF_RE = r'^[A-Za-z0-9._:-]{1,80}$'

#: a node id: a kind prefix and the id the kind is known by
NODE_RES = {'shadow': r'^shadow:now$', 'conversation': r'^conv:shc-[0-9a-z]{6,40}$', 'goal': r'^goal:g-[0-9a-f]{12}$',
            'task': r'^task:m-[0-9a-f]{12}$', 'task_chat': r'^tchat:m-[0-9a-f]{12}$', 'worker': r'^worker:m-[0-9a-f]{12}$',
            'department': r'^dept:[A-Za-z0-9_.-]{1,80}$'}
NODE_ID_RE = '^(' + '|'.join(r[1:-1] for r in NODE_RES.values()) + ')$'

MID = WORD(MID_RE, 14)
GID = WORD(GID_RE, 14)
REF = WORD(REF_RE, 80)
KIND = WORD(KIND_RE, 40)
NODE_ID = WORD(NODE_ID_RE, 90)
OPEN_REF = WORD(OPEN_REF_RE, 80)


#: the sentences of the cross-field rules of the A5 models (the validators), as patterns: `qa/a4_equiv.py` sets them aside, because a
#: JSON Schema cannot say them and the walker over the generated schema is the oracle for everything else
RULE_RES = []


def rule(template):
    """Registers a rule's sentence (`%s` stands for a value in it) and returns the template."""
    RULE_RES.append(re.compile('^' + re.escape(template).replace('%s', '.+') + '$'))
    return template


def is_rule(sentence):
    """Is this one of the sentences of the cross-field rules? (a sentence is 'path: words'.)"""
    words = sentence.split(': ', 1)[-1]
    wrapped = re.match(r'^fits none of its shapes \((.*)\)$', words)          # a rule met inside a nullable member
    words = wrapped.group(1) if wrapped else words
    return any(r.match(words) for r in RULE_RES)


def fail(*sentences):
    """The sentences of a cross-field rule, at the model's own place."""
    return faults_error(list(sentences))
