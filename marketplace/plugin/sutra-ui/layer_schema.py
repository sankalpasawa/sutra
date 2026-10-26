"""layer_schema.py -- the interface of Root and the five layers, hard-coded (PRD amendment A1).

The owner, 2026-10-26: "The root should have this identity adaptation, all these layers in a schema format, and any
kind of workflow for the department which is getting created should follow this from a coding perspective ... It should
be hard-coded within the interface schema layer." And: "the functionality of identity or adaptation can change, so we
need that modularization into the layer. But the schema part ... remain[s] the same."

THE ONE RULE OF A1. The interface is everything another layer, the screens, the tests or the owner may rely on, and it
lives only here: the records each layer owns and the department keys it owns, the acts it hears and sends and to whom,
its verdicts and covering checks, its settings, its prompt slots and its pane view, and the one workflow schema every
department workflow conforms to. The implementation (a layer's recipe and step bodies) lives in layers/<layer>/v<N>.*.

THE TYPES are JSON-Schema-shaped dicts (a draft 2020-12 subset) with a validator built in: no third-party import, and
nothing of the app's imported at import time (website_dept imports this module early; anything needed from it, the
runtime or j2_runtime is imported inside the function that needs it).

THE MODES (A1.20). In warn mode a fault is a row on the department's record and an entry in REFUSED, and the write goes
through. In refuse mode the write is refused with SchemaFault after the row is written. The mode is a code constant;
tests change it with monkeypatch, and no environment variable reads it. The conftest fixture fails any test that met a
fault outside expect_refused(), so the app warns while the tests are strict.

Packages import it as `import layer_schema as S` and use exactly A1's names. After wave 0 every change is additive
('A1 interface:' commits); the JSON Schema files under schemas/layers/ are generated from here (`python layer_schema.py
--write`) and never edited by hand.
"""
import contextlib
import copy
import json
import re
import sys
import threading
import time
from pathlib import Path

# ---- constants (A1.3) ----------------------------------------------------------------------------------------------
SCHEMA_VERSION = 1
LAYER_NAMES = ('root', 'identity', 'adaptation', 'priority', 'coordination', 'audit')
FUNCTION_LAYERS = LAYER_NAMES[1:]
TITLE = {'root': 'Root', 'identity': 'Identity', 'adaptation': 'Adaptation', 'priority': 'Priority',
         'coordination': 'Coordination', 'audit': 'Audit'}
ENGINE_LAYER = {'Identity': 'identity', 'Adaptation': 'adaptation', 'Priority': 'priority',
                'Coordination': 'coordination', 'Audit': 'audit', 'Setup': 'root'}
ACTORS = ('Owner', 'Root', 'Identity', 'Adaptation', 'Priority', 'Coordination', 'Audit', 'Engine')
#   the engine_defs edge keys, plus Engine: any work engine of the line
ACTS = ('request', 'agree', 'refuse', 'propose', 'accept-proposal', 'reject-proposal', 'inform',
        'failure', 'not-understood', 'cancel')                               # == engine_runtime.ACTS
DEFAULT_PINS = {'root': 'root/v1', 'identity': 'identity/v1', 'adaptation': 'adaptation/v1',
                'priority': 'priority/v1', 'coordination': 'coordination/v1', 'audit': 'audit/v1'}
#   the release's choice of implementation per layer; changing it is not a schema change, but it
#   needs the contract and the gate (A1.21)
PER_DEPARTMENT = False   # wave 3 (W3-PINS) makes recipes and bodies per department; until then every department runs DEFAULT_PINS
IMPL_RE = r'^(root|identity|adaptation|priority|coordination|audit)/v[1-9][0-9]*$'
ITEM_RE, FINDING_RE = r'^D[1-9][0-9]?$', r'^F[1-9][0-9]{0,2}$'
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9 &'.-]{0,39}$"                      # an engine or artifact name
BOUNDS = {'hops': 4, 'seconds': 900, 'usd': 0.5}                       # == engine_runtime.BOUNDS
CHAIN_LIMIT = 12                                                       # == website_dept.CHAIN_LIMIT
REPAIRS = 2                                                            # == j2_runtime.REPAIRS
OPTIONS_MAX = 3                                                        # == website_dept.OPTIONS_MAX
DONE_ITEMS_MAX = 12                                                    # == website_dept.DONE_ITEMS_MAX
STANDARD = ('goal', 'items', 'rules', 'owner', 'budget', 'invented')   # == engine_runtime.STANDARD (MK-1)
DONE_HOW, DONE_LEVELS = ('code', 'model', 'person'), ('target', 'outcome')    # the coverings' enums (MK-2), never the store's
RULE_TAGS = ('go', 'ask', 'refuse', 'always')                                # the covering's enum, never the store's
SOURCES = ('library', 'shaped', 'fitted', 'made')     # library and shaped are written today; fitted (M5.2) and made (M6) are reserved
SEVERITIES = ('high', 'medium', 'low')
ITEM_VERDICTS = ('met', 'not_met', 'to_confirm')
CONFIDENCE = {'ask_below': 0.6, 'show_below': 0.8}                     # J2B-7 (M6.4, wave 1)
RAISE_CAP, ROUNDS_DEFAULT = 2.0, 6                                     # Q6 (M5.4, M9.2, wave 2)
QUESTION_STATUSES = ('open', 'answered', 'unanswered', 'refused')      # board/1 (M4.9, wave 3)
INTERFACE_SHA = {}                                                     # W3-PROOF sets {1: sha256 of describe()} once nothing else changes it
MODE = 'warn'          # 'warn' | 'refuse'. A code constant, never an environment variable; tests change it with monkeypatch.
                       # The integrator's 'A1 interface: refuse' commit sets 'refuse' at the end of wave 1, once the full gate
                       # shows no fault at all.
OWNERSHIP_MODE = 'warn'          # a key written by a layer that does not own it: a row only, until W3-PROOF (wave 3) makes it 'refuse'
NEVER_REFUSE = ('stopped', 'control')   # department keys whose writes always land (the owner's Stop); a fault is a row only
REFUSED = {'count': 0, 'rows': []}      # every fault this process met: the conftest fixture and SM-13 read it
ANY = '(any)'                           # a SENDS or HEARS row that takes any word (a site whose word is not a literal)

HERE = Path(__file__).resolve().parent


# ---- type constructors (A1.4): each returns a JSON-Schema dict --------------------------------------------------------
def text(max_len, min_len=0):
    """Any text a writer stores, the owner's or a model's words included: no content rule."""
    return {'type': 'string', 'minLength': min_len, 'maxLength': max_len}


def say(max_len, min_len=0):
    """Words the owner reads: text with no control character except newline and tab."""
    return dict(text(max_len, min_len), **{'x-say': True})


def field(max_len, min_len=1, multiline=False):
    """An owner-editable prompt field (A1.16): no '{{' or '}}', no 'Return ONLY', no control character except tab, and a
    newline only when multiline. Only this type refuses the markers: an owner's request holding '}}' is text."""
    return dict(text(max_len, min_len), **{'x-field': {'multiline': bool(multiline)}})


def word(pattern, max_len=40):
    return {'type': 'string', 'pattern': pattern, 'maxLength': max_len}


def enum(*values):
    return {'enum': list(values)}


def const(value):
    return {'const': value}


def boolean():
    return {'type': 'boolean'}


def iso():
    """The head of W.now(): a date and, after it, whatever the clock says."""
    return word(r'^\d{4}-\d\d-\d\d', 40)


def integer(minimum=None, maximum=None):
    out = {'type': 'integer'}
    if minimum is not None:
        out['minimum'] = minimum
    if maximum is not None:
        out['maximum'] = maximum
    return out


def number(minimum=None, maximum=None):
    out = {'type': 'number'}
    if minimum is not None:
        out['minimum'] = minimum
    if maximum is not None:
        out['maximum'] = maximum
    return out


def items(of, max_items=None, min_items=0, unique=False):
    out = {'type': 'array', 'items': of, 'minItems': min_items}
    if max_items is not None:
        out['maxItems'] = max_items
    if unique:
        out['uniqueItems'] = True
    return out


def obj(properties, required=(), open=True):
    """An object: the named fields typed, `required` present; open, an unknown key passes and is kept."""
    return {'type': 'object', 'properties': dict(properties), 'required': list(required), 'additionalProperties': bool(open)}


def map_of(value, keys=None):
    """An object whose every value is `value`, and whose every key matches the pattern `keys` when one is given."""
    out = {'type': 'object', 'additionalProperties': value}
    if keys:
        out['propertyNames'] = {'pattern': keys}
    return out


def nullable(x):
    return {'anyOf': [x, {'type': 'null'}]}


def any_of(*xs):
    return {'anyOf': list(xs)}


def ref(name):
    return {'$ref': '#/$defs/' + name}


ANYTHING = {}                    # a field that is named but not typed: any JSON value


# ---- the validator ---------------------------------------------------------------------------------------------------
_SAY_BAD = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')            # control characters except tab and newline
_FIELD_BAD = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')          # the same; a newline is judged by multiline
_KIND = {'string': 'a string', 'integer': 'a whole number', 'number': 'a number', 'boolean': 'true or false',
         'array': 'a list', 'object': 'an object', 'null': 'null'}


def _is(kind, v):
    if kind == 'string':
        return isinstance(v, str)
    if kind == 'integer':
        return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
    if kind == 'number':
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if kind == 'boolean':
        return isinstance(v, bool)
    if kind == 'array':
        return isinstance(v, (list, tuple))
    if kind == 'object':
        return isinstance(v, dict)
    if kind == 'null':
        return v is None
    return True


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def _same(a, b):
    """Equal as JSON values are: True is never 1, and 1 is 1.0."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _shown(values, n=8):
    vals = [json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for v in values]
    return ', '.join(vals[:n]) + (', ...' if len(vals) > n else '')


def _key(path, k):
    return '%s.%s' % (path, k)


def faults(schema, value, path='$'):
    """What is wrong with `value` against `schema`, one line each, '<path>: <what is wrong>'; [] when it fits. Supports
    exactly: type (a bool is not an integer), enum, const, minLength, maxLength, pattern (re.search), minimum, maximum,
    items, minItems, maxItems, uniqueItems, properties, required, additionalProperties (bool or schema),
    propertyNames.pattern, anyOf, $ref into DEFS, x-say and x-field. Unknown keywords are ignored."""
    out = []
    _walk(schema, value, path, out)
    return out


def _walk(s, v, path, out):
    if not isinstance(s, dict) or not s:
        return
    if '$ref' in s:
        name = str(s['$ref']).rsplit('/', 1)[-1]
        target = DEFS.get(name)
        if target is None:
            out.append('%s: no definition named %s' % (path, name))
            return
        _walk(target, v, path, out)
    if 'anyOf' in s:
        tries = []
        for branch in s['anyOf']:
            got = []
            _walk(branch, v, path, got)
            if not got:
                break
            tries.append(got)
        else:
            first = next((t[0] for t in tries if t), '')
            out.append('%s: fits none of its shapes (%s)' % (path, first.split(': ', 1)[-1] if first else 'no shape'))
            return
    if 'type' in s:
        kinds = s['type'] if isinstance(s['type'], list) else [s['type']]
        if not any(_is(k, v) for k in kinds):
            out.append('%s: is not %s' % (path, ' or '.join(_KIND.get(k, k) for k in kinds)))
            return
    if 'enum' in s and not any(_same(v, e) for e in s['enum']):
        out.append('%s: is not one of %s' % (path, _shown(s['enum'])))
        return
    if 'const' in s and not _same(v, s['const']):
        out.append('%s: is not %s' % (path, _shown([s['const']])))
        return
    if isinstance(v, str):
        if 'minLength' in s and len(v) < s['minLength']:
            out.append('%s: shorter than %d' % (path, s['minLength']))
        if 'maxLength' in s and len(v) > s['maxLength']:
            out.append('%s: longer than %d' % (path, s['maxLength']))
        if 'pattern' in s and not re.search(s['pattern'], v):
            out.append('%s: does not match %s' % (path, s['pattern']))
        if s.get('x-say') and _SAY_BAD.search(v):
            out.append('%s: holds a control character' % path)
        if s.get('x-field'):
            multiline = bool((s['x-field'] or {}).get('multiline')) if isinstance(s['x-field'], dict) else False
            if '{{' in v or '}}' in v:
                out.append("%s: holds '{{' or '}}', which only the app may write" % path)
            if 'Return ONLY' in v:
                out.append("%s: holds 'Return ONLY': the answer's shape belongs to the app" % path)
            if _FIELD_BAD.search(v.replace('\n', '')):
                out.append('%s: holds a control character' % path)
            if not multiline and '\n' in v:
                out.append('%s: holds a line break' % path)
    if _is('number', v):
        if 'minimum' in s and v < s['minimum']:
            out.append('%s: below %s' % (path, s['minimum']))
        if 'maximum' in s and v > s['maximum']:
            out.append('%s: above %s' % (path, s['maximum']))
    if isinstance(v, (list, tuple)):
        if 'minItems' in s and len(v) < s['minItems']:
            out.append('%s: fewer than %d items' % (path, s['minItems']))
        if 'maxItems' in s and len(v) > s['maxItems']:
            out.append('%s: more than %d items' % (path, s['maxItems']))
        if s.get('uniqueItems') and len({_canon(x) for x in v}) != len(v):
            out.append('%s: holds an item twice' % path)
        if 'items' in s:
            for i, x in enumerate(v):
                _walk(s['items'], x, '%s[%d]' % (path, i), out)
    if isinstance(v, dict):
        props = s.get('properties') or {}
        for k in s.get('required') or []:
            if k not in v:
                out.append('%s: is missing' % _key(path, k))
        extra = s.get('additionalProperties', True)
        pattern = (s.get('propertyNames') or {}).get('pattern')
        for k, x in v.items():
            if pattern and not re.search(pattern, str(k)):
                out.append('%s: the key does not match %s' % (_key(path, k), pattern))
            if k in props:
                _walk(props[k], x, _key(path, k), out)
            elif extra is False:
                out.append('%s: is not a field here' % _key(path, k))
            elif isinstance(extra, dict):
                _walk(extra, x, _key(path, k), out)


# ---- faults and errors -----------------------------------------------------------------------------------------------
class SchemaFault(Exception):
    """A write that does not fit the interface, in refuse mode. Not a ValueError: an `except ValueError` path never
    swallows it, and the row and the count it leaves stand even when a caller does."""

    def __init__(self, name, faults):
        self.name = name
        self.faults = list(faults or [])
        super().__init__('%s: %s' % (name, '; '.join(self.faults[:3])))


_GUARD = threading.RLock()
_COLLECT = []                    # the open expect_refused() blocks, innermost last


class Met(list):
    """The faults met inside one expect_refused() block, as lines; `rows` holds the REFUSED rows themselves."""

    def __init__(self, name=None):
        super().__init__()
        self.name = name
        self.rows = []


def _owner_of_def(name):
    head = str(name or '').split('.', 1)[0]
    if head in LAYER_NAMES:
        return head
    return {'department': 'root', 'workflow': 'root', 'engine': 'root', 'instructions': 'identity',
            'option': 'identity'}.get(head, 'root')


def refused(ref, name, faults, owner=None, kept=False):
    """A write met a fault: REFUSED grows, and, with a ref whose department exists, one runs.json row is written by
    W.system_run under the owning layer's title: 'refused a write that does not fit the interface: ...', or, kept,
    'kept a record that does not fit the interface: ...'. Never raises."""
    try:
        owner = owner or _owner_of_def(name)
        row = {'name': name, 'faults': [str(f) for f in faults or []][:12], 'ref': ref, 'owner': owner, 'kept': bool(kept),
               'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
        with _GUARD:
            REFUSED['count'] += 1
            REFUSED['rows'].append(row)
            if len(REFUSED['rows']) > 2000:
                del REFUSED['rows'][:-2000]
            took = next((c for c in reversed(_COLLECT) if c.name in (None, name)), None)
            if took is not None:
                took.extend(row['faults'])
                took.rows.append(row)
        if ref:
            import website_dept as W                      # lazy: website_dept imports this module
            if (W.ddir(ref) / 'dept.json').exists():
                what = ('kept a record that does not fit the interface: ' if kept else
                        'refused a write that does not fit the interface: ') + '%s: %s' % (name, '; '.join(row['faults'][:3]))
                W.system_run(ref, TITLE.get(owner, 'Root'), what[:600])
    except Exception:  # noqa: BLE001 -- the row is a record of the fault, never a second fault
        pass


def report(name, faults, ref=None, owner=None, never_refuse=False):
    """Faults a caller found itself (the sink: a dept.json written past save_dept): the rows of refused(), and in refuse
    mode, unless never_refuse, SchemaFault after them. Returns the faults."""
    faults = [str(f) for f in faults or []]
    if faults:
        hard = MODE == 'refuse' and not never_refuse
        refused(ref, name, faults, owner=owner, kept=not hard)
        if hard:
            raise SchemaFault(name, faults)
    return faults


def validate(name, value):
    """What is wrong with `value` as DEFS[name]: [] when it fits."""
    if name not in DEFS:
        return ['$: no definition named %s' % name]
    return faults(DEFS[name], value)


def check(name, value, ref=None, owner=None, never_refuse=False):
    """`value` checked as DEFS[name] where it is written: its faults go to refused(); SchemaFault only when MODE is
    'refuse' and the write is not never-refuse. Returns the value."""
    report(name, validate(name, value), ref=ref, owner=owner, never_refuse=never_refuse)
    return value


@contextlib.contextmanager
def expect_refused(name=None):
    """For tests: yields the list of faults met inside the block (of DEFS `name`, or of any), and takes them off
    REFUSED on the way out, so the conftest fixture lets them pass. The list fills as the faults are met."""
    met = Met(name)
    with _GUARD:
        _COLLECT.append(met)
    try:
        yield met
    finally:
        with _GUARD:
            if met in _COLLECT:
                _COLLECT.remove(met)
            ids = {id(r) for r in met.rows}
            REFUSED['rows'][:] = [r for r in REFUSED['rows'] if id(r) not in ids]
            REFUSED['count'] -= len(met.rows)


# ---- the enums and tables the definitions read (A1.8, A1.14, A1.15) ---------------------------------------------------
#: every status an asks.json row takes, from its writers: _put_ask's callers, choose_option, decide_ask, _blocked
#: (replaced), _reopen (chosen) and j2_runtime's answer (stamped)
ASK_STATUSES = ('pending', 'stamped', 'refused', 'answered', 'chosen', 'replaced')
#: every kind an asks.json row takes, A1.8's list completed from the writers: model (_held_back), step (_person) and
#: request (identity_file's 'reaches outside' ask)
ASK_KINDS = ('publish', 'setup', 'engine', 'envelope', 'alarm', 'finding', 'hole', 'rule', 'goal', 'rung', 'trial',
             'conflict', 'line', 'j2_identity', 'done_items', 'instructions', 'blocked', 'model', 'step', 'request')

#: the ways out an ask offers (A1.15): which layer applies each, its params (a DEFS name, or None), what it says, and
#: the wave it is built in (0: built before A1, M3.5)
OPTION_KINDS = {
    'words': {'layer': 'identity', 'params': None, 'says': 'change the plan in my words', 'from_wave': 0},
    'leave': {'layer': 'identity', 'params': None, 'says': 'leave an item out of done-when', 'from_wave': 0},
    'stop': {'layer': 'identity', 'params': None, 'says': 'stop here', 'from_wave': 0},
    'raise': {'layer': 'priority', 'params': 'option.raise', 'says': 'add budget, up to twice where it started', 'from_wave': 2},
    'root_setup': {'layer': 'root', 'params': 'option.words', 'says': 'set the department up again, done its own way', 'from_wave': 1},
    'pin': {'layer': 'root', 'params': 'option.pin', 'says': 'run another version of one function', 'from_wave': 3},
}

#: Root's standards (A1.14; MK-4 taken): (id, says, sources, stages). The says text is what S11 and S18 show. Their code
#: is workflow_schema.py (W1-ROOT); until it is on main, validate_workflow returns the shape rows only.
WORKFLOW_STANDARDS = (
    ('names_an_engine', 'the workflow names its engines', SOURCES, ('proposal', 'registration', 'write', 'grow', 'birth')),
    ('engines_known', 'each engine is one the Library has', ('library', 'fitted'), ('birth', 'registration', 'write', 'grow')),
    ('each_engine_named', 'every engine has a name', ('shaped', 'made'), ('proposal', 'registration', 'grow')),
    ('names_unique', "no name is used twice, and none is a function's, Root's or Owner's", SOURCES,
     ('proposal', 'registration', 'grow')),
    ('names_new', 'no name is one the Library already has', ('shaped', 'made'), ('proposal', 'registration')),
    ('first_reads_input', "the first engine reads the kind's first artifact", SOURCES, ('proposal', 'birth', 'registration')),
    ('reads_known', "each engine reads the kind's first artifact or what one before it wrote", SOURCES,
     ('proposal', 'birth', 'registration', 'grow')),
    ('one_output', 'each engine writes something not yet written', SOURCES, ('proposal', 'birth', 'registration', 'grow')),
    ('items_covered', 'every done-when item is covered by an engine', SOURCES, ('registration', 'proposal')),
    ('required_kept', 'no engine the kind requires is left out', SOURCES, ('proposal', 'birth', 'registration')),
    ('size_in_range', 'one engine or more; more than six says why', SOURCES, ('proposal', 'registration')),
    ('check_exists', "each engine's output has a check", SOURCES, ('registration', 'grow')),
    ('fits_room', "Priority priced it and it fits today's room", SOURCES, ('registration',)),
    ('line_is_registered', "Coordination's line is a registered plan plus the engines the owner added", SOURCES, ('write',)),
)
STAGES = ('birth', 'proposal', 'registration', 'grow', 'write')

#: the field tuples the code names once (engine_runtime M4, functions_view M4.5 and M4.7); the definitions below are
#: built from them, and test_layer_schema keeps them equal to the code's
TABLE_FIELDS = ('order', 'functions', 'line', 'edges', 'left_out', 'grown', 'registered', 'timetable', 'by', 'since', 'why')
LEFT_OUT_FIELDS = ('engine', 'in_line', 'since')
SLOT_FIELDS = ('engine', 'on', 'of', 'checked', 'every_s', 'window_min', 'since')
COORDINATION_FIELDS = ('line', 'registered', 'timetable', 'left_out', 'holds', 'handoffs', 'chain', 'alarms', 'ties')
TIMETABLE_ROW = ('engine', 'on', 'starts', 'window_min', 'since', 'state', 'word', 'why', 'at', 'last')
ENGINE_CARD_FIELDS = ('engine', 'head', 'motor', 'five')
ENGINE_FIVE_ROW = ('fn', 'state', 'says', 'at', 'share')
BORN_FIELDS = ('engines', 'version', 'full', 'grow', 'before')     # == engine_runtime.BORN_FIELDS
SLOT_STATES = ('running', 'turn', 'waits', 'ran', 'stopped')         # == functions_view.TT_WORDS' keys


# ---- the definitions (A1.5 to A1.17, A1.13b) ------------------------------------------------------------------------
# Every type is bound to the writer that exists on main (test_layer_writers.py has one test per writer). The store's
# enums are loose where Identity's standard must see a bad value: a rule with no tag, an item whose how is not code,
# model or person, an empty goal (A1.6). Objects are open unless A1 closes them. A bound wider than A1's says so beside it.
DEFS = {}

# common (A1.5)
DEFS.update({
    'name': word(NAME_RE, 40),
    'id.item': word(ITEM_RE, 3),
    'id.finding': word(FINDING_RE, 4),
    'impl': word(IMPL_RE, 24),
    'envelope': obj({'calls': integer(0), 'usd': number(0)}, required=('calls', 'usd')),
    # cost: say(400), wider than A1's 300: _blocked's leave option says the item's text (up to 300) inside its cost
    'option': obj({'id': word(r'^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]{1,40})?$', 64), 'label': say(120, 1), 'cost': say(400),
                   'kind': enum(*OPTION_KINDS), 'params': obj({})}, required=('id', 'label', 'cost')),
    'check.verdict': obj({'ok': boolean(), 'notes': items(text(2000))}, required=('ok', 'notes')),   # every covering check returns this
})

# Identity's records (A1.6, A1.8)
DEFS.update({
    # how and level as said (W.done_items keeps them as the agent said them, lowercased): text(200), wider than A1's 20
    'identity.done_item': obj({'id': ref('id.item'), 'text': text(300, 1), 'how': text(200), 'level': text(200), 'confirm': text(200)},
                              required=('id', 'text'), open=False),
    # W.rule_row: {id, tag, line, since, from, scope?}; a kind's rules are {tag, line}. tag may be absent or null (a rule with no
    # tag is a standard gap, not a store fault); line text(2000), wider than A1's 600: a restated line is a model's words
    'identity.rule': obj({'id': text(80), 'tag': nullable(text(20)), 'line': text(2000), 'since': nullable(text(40)),
                          'from': nullable(text(8000)), 'scope': text(20)}, required=('line',)),
    # open: title, who, why, if_nothing, missing, standard, points, fn, file, ...
    # decided and by are null on a card that waits open again after its choice (_blocked_chosen, M3.5's fix)
    'identity.ask': obj({'id': text(40, 1), 'kind': enum(*ASK_KINDS), 'status': enum(*ASK_STATUSES), 'text': text(4000),
                         'created': text(40), 'decided': nullable(text(40)), 'by': nullable(text(80)), 'engine': nullable(text(60)),
                         'thread': nullable(text(80)),
                         'options': items(ref('option'), OPTIONS_MAX),
                         'chosen': nullable(obj({'id': text(64), 'label': text(120), 'at': text(40), 'by': text(80),
                                                 'words': nullable(text(2000))})),
                         'items': items(ref('identity.done_item'), DONE_ITEMS_MAX), 'cycle_id': nullable(text(80))},
                        required=('id', 'kind', 'status')),
})

# Root's records (A1.6, A1.7)
DEFS.update({
    'root.pins': obj({layer: ref('impl') for layer in LAYER_NAMES}, open=False),
    # a born engine template, as R.born_template writes it to the records home's _library/<slug>.json (W1-ROOT checks it
    # before the file is written)
    'engine.template': obj({'id': word(r'^engine/[a-z0-9][a-z0-9-]*$', 80), 'name': text(40, 1), 'version': integer(1),
                            'use_case': text(300, 1), 'description': text(300), 'instruction': text(4000), 'reads': text(200),
                            'writes': text(40),
                            'made_by': obj({'by': const('Adaptation'), 'dept': text(200), 'at': text(40), 'idea': nullable(text(300))},
                                           required=('by',)),
                            'start': obj({}), 'steps': items(obj({})), 'needs': items(text(40)), 'kind': const('work')},
                           required=('id', 'name', 'use_case', 'made_by')),
})

# the workflow schema (A1.14)
DEFS.update({
    'workflow.engine': obj({'name': ref('name'), 'does': text(300), 'reads': ref('name'), 'writes': ref('name'),
                            'covers': items(ref('id.item'), 12, unique=True), 'internet': boolean(), 'start': obj({}), 'check': text(60),
                            'envelope': ref('envelope'), 'made_by': enum('library', 'fitted', 'shaped', 'made'), 'required': boolean(),
                            'fit': text(300), 'level': enum(1, 2), 'confidence': number(0, 1), 'doubt': text(300)},
                           required=('name', 'reads', 'writes')),
    'workflow': obj({'schema_version': integer(1), 'version': integer(1), 'kind': text(40), 'source': enum(*SOURCES),
                     'engines': items(ref('workflow.engine'), 24), 'deliverable': nullable(ref('name')),
                     'covers': map_of(items(ref('name'), min_items=1), keys=ITEM_RE), 'covers_by': enum('adaptation', 'default'),
                     'left_out': items(ref('name')), 'checks': items(ref('workflow.check')), 'why': text(600), 'at': text(40),
                     'by': text(40)},
                    required=('engines', 'source')),
    'workflow.check': obj({'check': enum(*([s[0] for s in WORKFLOW_STANDARDS] + ['workflow_meets_standards'])), 'passed': boolean(),
                           'why': text(600)}, required=('check', 'passed', 'why')),
    # j2_runtime.registered writes the first five
    'workflow.registration': obj({'version': integer(1), 'engines': items(ref('name'), 24), 'source': enum(*SOURCES),
                                  'registered': text(40), 'by': text(40), 'checks': items(ref('workflow.check')),
                                  'covers': map_of(items(ref('name')), keys=ITEM_RE), 'fit': map_of(text(300)),
                                  'deliverable': nullable(ref('name')), 'left_out': items(ref('name'))},
                                 required=('version', 'engines', 'source', 'registered')),
})

# Coordination's records (A1.11)
DEFS.update({
    'coordination.slot': obj({'engine': ref('name'), 'on': text(80), 'of': ref('name'), 'checked': boolean(), 'every_s': number(0),
                              'window_min': integer(0, 1440), 'since': text(40)}, required=('engine', 'on'), open=False),
    'coordination.left_out': obj({'engine': ref('name'), 'in_line': const(False), 'since': text(40)}, required=('engine',), open=False),
    'coordination.table': obj({'schema_version': integer(1), 'order': items(enum('posts', 'line', 'functions'), 3, 1, True),
                               'functions': items(enum(*TITLE.values())), 'line': items(ref('name'), 24, unique=True), 'edges': obj({}),
                               'left_out': items(ref('coordination.left_out')), 'grown': items(ref('name'), unique=True),
                               'registered': nullable(integer(0)), 'timetable': items(ref('coordination.slot')),
                               'by': enum('born', 'Coordination'), 'since': text(40), 'why': text(300)},
                              required=('order', 'line'), open=False),
})

# Adaptation's open records (A1.9): their writers are bound when W1-ADAPT checks them
DEFS.update({
    'adaptation.idea': obj({}),
    'adaptation.ladder': obj({}),
})

# the records and acts waves 1 to 3 write first (A1.13b), declared as A1 types them
DEFS.update({
    'priority.estimate': obj({'calls': integer(0), 'usd': number(0), 'basis': enum('median', 'prior', 'line'), 'runs': integer(0),
                              'per_engine': map_of(obj({'calls': integer(0), 'usd': number(0), 'basis': enum('median', 'prior'),
                                                        'runs': integer(0)}))}, required=('calls', 'usd')),
    'priority.price': obj({'schema_version': integer(1), 'id': text(40), 'at': text(40), 'cycle_id': nullable(text(80)),
                           'round': nullable(integer(1)), 'thread': text(80), 'proposal': enum('line', 'round', 'engine', 'cost'),
                           'engines': items(ref('name')), 'estimate': ref('priority.estimate'),
                           'room': obj({'calls': integer(), 'usd': number()}), 'remaining': obj({'calls': integer(), 'usd': number()}),
                           'answer': enum('accept', 'counter', 'reject'), 'keep': items(ref('name')), 'why': text(600),
                           'indices': obj({'spend_per_run': map_of(number(0)), 'checks': map_of(enum('ok', 'failed', 'none'))})},
                          required=('at', 'proposal', 'estimate', 'room', 'answer', 'why')),
    'priority.ceiling': obj({'rounds': integer(1, 99), 'calls': integer(0), 'usd': number(0),
                             'start': obj({'rounds': integer(1), 'calls': integer(0), 'usd': number(0)}, required=('rounds', 'calls', 'usd')),
                             'raised': items(obj({'at': text(40), 'by': text(80), 'to': obj({})})), 'at': text(40)},
                            required=('rounds', 'calls', 'usd', 'start')),
    'audit.reading_item': obj({'id': ref('id.item'), 'subject': text(200), 'claim': text(600), 'evidence': text(1000),
                               'method': enum('code', 'model'), 'verdict': enum(*ITEM_VERDICTS), 'severity': enum(*SEVERITIES)},
                              required=('id', 'subject', 'claim', 'evidence', 'method', 'verdict', 'severity')),
    'audit.finding': obj({'id': ref('id.finding'), 'severity': enum(*SEVERITIES), 'claim': text(600), 'where': text(200),
                          'item': nullable(ref('id.item')), 'went_to': nullable(enum('Identity', 'Adaptation', 'you')),
                          'ask': nullable(text(40)), 'at': text(40)}, required=('id', 'severity', 'claim', 'where')),
    'audit.reading': obj({'schema_version': integer(1), 'id': word(r'^r-[0-9a-f]{8}$', 10), 'v': integer(1), 'artifact': ref('name'),
                          'cycle_id': nullable(text(80)), 'round': nullable(integer(1)), 'read': boolean(),
                          'why_not_read': nullable(text(300)), 'items': items(ref('audit.reading_item')),
                          'findings': items(ref('audit.finding')), 'at': text(40)},
                         required=('id', 'v', 'artifact', 'read', 'items', 'at')),
    'adaptation.round': obj({'schema_version': integer(1), 'round': integer(1, 99), 'at': text(40), 'cycle_id': nullable(text(80)),
                             'correction': text(600), 'fixes': items(ref('id.finding')), 'covers': items(ref('id.item')),
                             'estimate': ref('priority.estimate'), 'status': enum('proposed', 'granted', 'refused', 'filed', 'read'),
                             'reading': text(40), 'brief_v': integer(1)}, required=('round', 'correction', 'covers', 'status')),
    'coordination.question': obj({'schema': const('board/1'), 'id': word(r'^Q-[1-9][0-9]*$', 8), 'asked_by': ref('name'), 'to': ref('name'),
                                  'about': text(120), 'question': text(600), 'answer': nullable(text(2000)),
                                  'answered_by': nullable(ref('name')), 'status': enum(*QUESTION_STATUSES), 'reason': nullable(text(300)),
                                  'artifact_update': nullable(obj({})), 'used_by': items(ref('name')), 'cycle': nullable(text(80)),
                                  'slot': text(160), 'attempt': integer(1), 'run': nullable(text(40))},
                                 required=('schema', 'id', 'asked_by', 'to', 'about', 'question', 'status', 'used_by')),
    'audit.spot_check': obj({'schema_version': integer(1), 'id': text(40), 'at': text(40), 'minute': integer(0, 1439),
                             'checks': items(obj({'check': text(80), 'ok': boolean(), 'why': text(300)}, required=('check', 'ok', 'why'))),
                             'findings': items(ref('audit.finding'))}, required=('id', 'at', 'checks', 'findings')),
    'option.raise': obj({'what': enum('envelope', 'ceiling'), 'engine': ref('name'), 'calls': integer(0), 'usd': number(0),
                         'rounds': integer(0)}, required=('what',)),
    'option.words': obj({'words': text(4000, 1)}, required=('words',)),
    'option.pin': obj({'layer': enum(*LAYER_NAMES), 'impl': ref('impl')}, required=('layer', 'impl')),
})

# the board's acts and their payloads (A1.13, A1.13b). Every payload is open: unknown keys pass, and only the fields
# named are typed. Words that may carry a whole Brief (a line request's, a proposal's) are text(100000).
DEFS.update({
    'act.any': obj({'word': text(40)}, required=('word',)),
    'act.words': obj({'word': enum('front', 'request'), 'words': text(8000), 'objective': text(8000), 'output': text(600),
                      'may_read': items(text(60)), 'boundaries': text(8000), 'request': ANYTHING, 'about': ANYTHING,
                      'answers': ANYTHING}, required=('word',)),
    'act.stamp': obj({'word': text(40), 'ask': text(40)}),
    # done: say(8000), wider than A1's 4000: the birth tell names every done-when item, up to twelve of 300
    'act.tell': obj({'word': text(40), 'done': say(8000), 'card': text(40)}, required=('word',)),
    'act.ask': obj({'word': text(40), 'objective': say(4000), 'output': text(600), 'may_read': items(text(60)),
                    'boundaries': text(8000)}, required=('word',)),
    'act.verdict': obj({'word': const('verdict'), 'answer': enum('admit', 'wait', 'refuse'), 'why': nullable(text(600))},
                       required=('word',)),
    'act.line_request': obj({'word': const('line'), 'words': nullable(text(100000)), 'objective': text(2000),
                             'faults': items(text(600)),
                             'practices': obj({'rules': ANYTHING, 'engines': ANYTHING, 'artifacts': ANYTHING, 'required': ANYTHING,
                                               'taken': ANYTHING})}, required=('word',)),
    'act.line': obj({'word': const('line'), 'engines': items(any_of(ref('name'), ref('workflow.engine')), 24),
                     'source': nullable(enum(*SOURCES)), 'words': nullable(text(100000)), 'for': nullable(text(80)),
                     'covers': map_of(items(ref('name')), keys=ITEM_RE), 'doubt': text(600), 'confidence': number(0, 1),
                     'fit': map_of(text(300)), 'keep': items(ref('name')), 'why': text(2000)}, required=('word',)),
    # why: text(2000), wider than A1's 600: a conflict quotes the counter's own why
    'act.conflict': obj({'word': const('conflict'), 'engines': items(any_of(ref('name'), ref('workflow.engine'))),
                         'source': nullable(enum(*SOURCES)), 'words': nullable(text(100000)), 'why': text(2000),
                         'bound': nullable(text(40)), 'for': nullable(text(80)), 'options': items(ref('option'), 3)},
                        required=('word',)),
    # claim: text(2000), wider than A1's 600: a mechanical note is the claim when the judge found nothing
    'act.finding': obj({'word': const('finding'), 'claim': text(2000), 'severity': enum(*SEVERITIES), 'where': text(200),
                        'page': nullable(text(200)), 'item': nullable(ref('id.item')), 'v': integer(1), 'findings': items(obj({}))},
                       required=('word',)),
    # beyond A1.13: the word born, as BORN_FIELDS names it (a plan Root registered, or an engine the owner stamped)
    'act.born': obj({'word': const('born'), 'engines': items(text(80)), 'version': nullable(integer(0)), 'full': boolean(),
                     'grow': text(80), 'before': nullable(text(80))}, required=('word',)),
    'act.doubt': obj({'word': const('doubt'), 'engine': ref('name'), 'doubt': text(600), 'fallback': text(600),
                      'confidence': number(0, 1),
                      'cannot': nullable(obj({'engine': ref('name'), 'items': items(ref('id.item')), 'why': text(600)}))},
                     required=('word', 'engine', 'doubt')),
    'act.reading': obj({'word': const('reading'), 'reading': text(40), 'artifact': ref('name'), 'v': integer(1), 'read': boolean(),
                        'met': items(ref('id.item')), 'not_met': items(ref('id.item')), 'to_confirm': items(ref('id.item')),
                        'findings': items(ref('id.finding')), 'high': boolean()},
                       required=('word', 'reading', 'artifact', 'v', 'read', 'met', 'not_met', 'to_confirm')),
    'act.next': obj({'word': const('next'), 'items': items(ref('id.item'), min_items=1), 'reading': text(40),
                     'findings': items(ref('id.finding')), 'round': integer(1, 99)}, required=('word', 'items', 'reading')),
    'act.round': obj({'word': const('round'), 'round': integer(1, 99), 'correction': text(600), 'fixes': items(ref('id.finding')),
                      'covers': items(ref('id.item')), 'estimate': ref('priority.estimate'), 'why': text(600),
                      'ceiling': ref('priority.ceiling')}, required=('word', 'round')),
    'act.question': obj({'word': const('question'), 'entry': ref('coordination.question')}, required=('word', 'entry')),
    'act.answer': obj({'word': const('answer'), 'entry': ref('coordination.question')}, required=('word', 'entry')),
})

# prompt fields and the owner's values (A1.16)
DEFS.update({
    'field.task': field(1200, multiline=True),
    'field.guidance': field(2000, 0, multiline=True),
    'field.text': field(400),
    'field.note': field(4000, 0, multiline=True),
    'field.items': items(field(160), 12, 1),
    'instructions': obj({'schema_version': const(1),
                         'values': map_of(map_of(map_of(map_of(obj({'value': ANYTHING, 'at': text(40), 'ask': text(40)},
                                                                   required=('value',))))))},
                        required=('schema_version', 'values')),
})

# settings (A1.8 to A1.12)
DEFS.update({
    'setting.windows': map_of(integer(0, 1440)),
    'setting.make': boolean(),
    'setting.order': items(enum('posts', 'line', 'functions'), 3, 1, True),
    'setting.spot_every_s': integer(3600, 604800),
})

# the pane views (A1.17): the read models already merged, typed as they are; later steps add fields, never rename them
_AT = nullable(text(40))
DEFS.update({
    'view.identity': obj({
        'standard': obj({'met': boolean(), 'missing': items(enum(*STANDARD)),
                         'rows': items(obj({'id': enum('goal', 'items', 'rules', 'owner_budget', 'invented'), 'says': text(200),
                                            'state': enum('met', 'not_met', 'to_confirm', 'reading'), 'note': text(4000)},
                                           required=('id', 'says', 'state', 'note')))},
                        required=('met', 'missing', 'rows')),
        'goal': nullable(text(2000)), 'done': nullable(text(4000)),
        'done_items': items(obj({'id': text(8), 'text': nullable(text(300)), 'how': nullable(text(200)), 'level': nullable(text(200)),
                                 'confirm': nullable(text(300))})),
        'rules': items(obj({'tag': nullable(text(20)), 'line': text(2000), 'by': enum('yours', 'the template'), 'since': _AT})),
        'open_question': nullable(obj({'id': ANYTHING, 'text': ANYTHING, 'why': ANYTHING, 'missing': ANYTHING, 'asked': ANYTHING,
                                       'standard': ANYTHING, 'points': ANYTHING})),
        'conflicts': items(obj({'at': _AT, 'who': text(200), 'split': nullable(text(4000)), 'plan': nullable(text(2000)),
                                'ruling': text(20), 'ruled': text(40), 'why': nullable(text(4000)), 'asked_you': boolean()}), 6)},
        required=('standard', 'goal', 'done', 'done_items', 'rules', 'open_question', 'conflicts')),
    'view.adaptation': obj({
        'proposal': nullable(obj({'workflow': items(text(80)), 'source': nullable(text(40)), 'at': _AT})),
        'root_checks': items(obj({'summary': nullable(text(4000)), 'at': _AT, 'passed': boolean()})),
        'rounds': items(obj({}))},
        required=('proposal', 'root_checks', 'rounds')),
    'view.priority': obj({
        'bargains': items(obj({'said': enum('said yes', 'asked for less', 'said no'), 'summary': nullable(text(4000)), 'at': _AT})),
        'envelopes': items(obj({'engine': text(80), 'calls': integer(0), 'usd': number(0), 'calls_limit': integer(0),
                                'usd_limit': number(0), 'share': number(0, 1)}))},
        required=('bargains', 'envelopes')),
    'view.coordination': obj({
        'line': items(text(80)), 'registered': nullable(integer(0)),
        'timetable': items(obj({'engine': text(80), 'on': nullable(text(80)), 'starts': text(200), 'window_min': integer(0),
                                'since': _AT, 'state': enum(*SLOT_STATES), 'word': text(40), 'why': nullable(text(600)), 'at': _AT,
                                'last': nullable(obj({'at': _AT, 'status': nullable(text(20)), 'wrote': nullable(text(120))}))},
                               required=TIMETABLE_ROW, open=False)),
        'left_out': items(obj({'engine': nullable(text(80)), 'since': _AT}, open=False)),
        'holds': items(obj({'engine': text(80), 'why': text(600)}, open=False)),
        'handoffs': items(obj({'art': text(80), 'v': nullable(integer(0)), 'by': nullable(text(80)), 'says': nullable(text(200)),
                               'readers': items(text(80))})),
        'chain': obj({'of': nullable(text(80)), 'used': integer(0), 'limit': integer(0), 'share': number(0, 1)}),
        'alarms': items(obj({'engine': nullable(text(80)), 'text': nullable(text(600)), 'at': _AT})),
        'ties': items(obj({'pick': text(80), 'said': text(200), 'why': nullable(text(600)), 'at': _AT, 'today': boolean()}))},
        required=COORDINATION_FIELDS, open=False),
    'view.engine_card': obj({
        'engine': text(80),
        'head': obj({'state': enum(*(SLOT_STATES + ('left_out', 'quiet'))), 'word': nullable(text(80)), 'why': nullable(text(600)),
                     'at': _AT, 'round': ANYTHING}, required=('state', 'word', 'why', 'at', 'round'), open=False),
        'motor': obj({'slot': nullable(text(80)), 'starts': text(200), 'once': boolean(), 'says': text(80), 'window_min': integer(0),
                      'today': number(0, 1)}, required=('slot', 'starts', 'once', 'says', 'window_min', 'today'), open=False),
        'five': items(obj({'fn': enum(*[TITLE[x] for x in FUNCTION_LAYERS]),
                           'state': enum('ok', 'warn', 'block', 'wait', 'breath', 'off'), 'says': text(300), 'at': _AT,
                           'share': nullable(number(0, 1))}, required=ENGINE_FIVE_ROW, open=False), 5, 5)},
        required=ENGINE_CARD_FIELDS, open=False),
    'view.audit': obj({
        'readings': items(obj({'summary': nullable(text(4000)), 'at': _AT})),
        'findings': items(obj({'text': nullable(text(4000)), 'at': _AT})),
        'spot_checks': items(obj({}))},
        required=('readings', 'findings', 'spot_checks')),
})

# the department record (dept.json) and who owns each key (A1.6): (key, owner, type). Only the keys a save changes are
# checked (A1.20). Three keys are beyond A1.6's table, each with a reader or writer on main: pending_final_tell (Setup
# writes it on the child; _reconcile_j1_tells pops it), ladder (numbers() reads the department's own ladder numbers)
# and bounds (post() reads a department's own thread bounds).
_DEPARTMENT = (
    ('schema_version', 'root', integer(0)),
    ('kind', 'root', text(40)),
    ('ref', 'root', text(200, 1)),
    ('name', 'root', text(200, 1)),
    ('parent', 'root', nullable(text(200))),
    ('created', 'root', iso()),
    ('runtime', 'root', enum(1, 2)),
    ('control', 'root', text(40)),
    ('stopped', 'root', boolean()),
    ('engines', 'root', items(ref('name'), 24, unique=True)),
    ('artifacts', 'root', items(ref('name'), 32, unique=True)),
    ('workflows', 'root', items(ref('workflow.registration'))),
    ('layers', 'root', ref('root.pins')),
    ('org', 'root', obj({})),
    ('root', 'root', nullable(text(200))),
    # template_ref: founding.spawn writes Setup's {id, version} (or None), wider than A1's nullable text
    ('template_ref', 'root', nullable(any_of(text(200), obj({})))),
    ('templates', 'root', map_of(text(80))),
    ('founding', 'root', obj({'operation_id': text(200), 'checkpoints': items(text(40))})),
    ('events', 'root', items(obj({'kind': text(40)}))),
    ('pending_final_tell', 'root', obj({})),
    ('goal', 'identity', text(2000)),
    ('done', 'identity', text(4000)),
    ('done_items', 'identity', items(ref('identity.done_item'), DONE_ITEMS_MAX)),
    ('to_be_confirmed', 'identity', items(obj({'item': ref('id.item'), 'why': text(300)}, required=('item',)))),
    ('rules', 'identity', items(ref('identity.rule'), 64)),
    ('owner', 'identity', text(200)),
    ('windows', 'identity', ref('setting.windows')),
    ('identity_revision', 'identity', integer(1)),
    ('initial_goal_context', 'identity', obj({})),
    ('publish_asks_from', 'identity', integer(0)),
    ('goals', 'identity', items(obj({}))),
    ('looked_up', 'identity', items(text(2000))),
    ('host', 'identity', text(200)),
    ('ladders', 'identity', map_of(obj({}))),
    ('ladder', 'identity', map_of(integer(0))),
    ('bounds', 'identity', obj({'hops': integer(0), 'seconds': number(0), 'usd': number(0)})),
    ('envelopes', 'priority', map_of(ref('envelope'))),          # any name: there is no membership rule
    ('ceiling', 'priority', ref('priority.ceiling')),            # declared in wave 0; written from wave 2 (W2-PRIORITY)
)
DEFS.update({'department.' + key: t for key, _, t in _DEPARTMENT})
DEFS['department'] = obj({key: dict(ref('department.' + key), **{'x-owner': owner}) for key, owner, _ in _DEPARTMENT},
                         required=('kind', 'ref', 'name'), open=False)
