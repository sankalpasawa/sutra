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
fault outside expect_refused(). Waves 0 and 1 ran in warn mode for the app and strictly for the tests; since 'A1 interface:
refuse' MODE is 'refuse', and a test that is about warn mode pins it with monkeypatch.

Packages import it as `import layer_schema as S` and use exactly A1's names. After wave 0 every change is additive
('A1 interface:' commits); the JSON Schema files under schemas/layers/ are generated from here (`python layer_schema.py
--write`) and never edited by hand.

THE TEMPLATES (amendment A3). A template is an interface is a base class, at seven levels: the user journey, the department
kind, the function, the engine and workflow, the step, the artifact and the ask. The section "A3: the templates at every
level" types the ones A1 and A2 left as prose; template_checks.py holds the rules a type cannot say.
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
RUNGS = ('P', 'C0', 'C1', 'C2')                                        # == engine_runtime.RUNGS
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
MODE = 'refuse'        # 'warn' | 'refuse'. A code constant, never an environment variable; tests change it with monkeypatch.
                       # 'A1 interface: refuse' (the integrator's commit at the end of wave 1, the full gate showing no fault at
                       # all) set it: a write that does not fit the interface raises SchemaFault, after its row.
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
                         'items': items(ref('identity.done_item'), DONE_ITEMS_MAX), 'cycle_id': nullable(text(80)),
                         # a j2_identity ask that puts Adaptation's doubt to the owner (M3.9, W1-IDENTITY): doubt is Adaptation's words, shown
                         # the words the owner was asked (the doubt put in plain words), line the board post of the line request it
                         # doubted, answered the board post of the request that carried the owner's answer (true when it carried none)
                         'doubt': obj({'engine': text(40), 'doubt': text(600), 'shown': text(600), 'fallback': text(600),
                                       'line': nullable(integer(0)), 'answered': any_of(integer(0), boolean())})},
                        required=('id', 'kind', 'status')),
})

# Root's records (A1.6, A1.7)
DEFS.update({
    'root.pins': obj({layer: ref('impl') for layer in LAYER_NAMES}, open=False),
    # a born engine template, as R.born_template writes it to the records home's _library/<slug>.json (W1-ROOT checks it
    # before the file is written). It is the child of engine.library (A3.5): that template with a required made_by
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

# Adaptation's records (A1.9), typed as their writers write them (W1-ADAPT binds them): an idea parked by R.adapt_park and
# noted by R._note_idea (the engine it was built as, or that Priority would not price it), and a step's ladder entry, written by
# R._save_entry from R.entry, R.move, the keeper's trial and the owner's hold. Open objects: a key a later writer adds passes.
# reflected, question and why are a model's words, so their bounds are wide (the same reason as act.conflict's why).
DEFS.update({
    'adaptation.idea': obj({'id': text(40, 1), 'words': nullable(text(100000)), 'reflected': text(8000), 'question': nullable(text(2000)),
                            'shapes': items(text(2000), 3), 'state': enum('parked', 'built'), 'at': text(40),
                            'engine': nullable(text(80)), 'priced': text(40), 'why': text(2000)},
                           required=('id', 'reflected', 'shapes', 'state', 'at')),
    # since is null on a department record that has no created stamp; trial is the next rung run beside the incumbent, counted
    # (R.adapt_trial, the keeper's table trial and R._trial); evidence is the numbers a move rested on (a step's rows counted),
    # or null; by is who moved it and why, in the keeper's words
    'adaptation.ladder': obj({'engine': text(80, 1), 'step': text(80, 1), 'rung': enum(*RUNGS), 'form': nullable(text(40)),
                              'since': nullable(text(40)), 'since_row': integer(0), 'held': boolean(), 'pending': nullable(text(80)),
                              'trial': nullable(obj({'rung': enum(*RUNGS), 'form': nullable(text(40)), 'runs': integer(0),
                                                     'agree': integer(0), 'norule': integer(0), 'state': enum('running', 'done'),
                                                     'started': text(40)})),
                              'history': items(obj({'at': nullable(text(40)), 'from': nullable(enum(*RUNGS)), 'to': enum(*RUNGS),
                                                    'by': text(400), 'evidence': ANYTHING}, required=('to', 'by')))},
                             required=('engine', 'step', 'rung', 'held', 'history')),
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
    # answer, doubt, fallback and go_on are Identity's (M3.9, W1-IDENTITY): the owner's answer to Adaptation's doubt (or the fallback
    # 'just do it' took), the doubt and the fallback it was put with, and go_on, which tells Adaptation to go on to Priority with
    # the doubt named, as for a confidence from 0.6 to under 0.8, and not to doubt again
    'act.line_request': obj({'word': const('line'), 'words': nullable(text(100000)), 'objective': text(2000),
                             'faults': items(text(600)), 'answer': text(2000), 'doubt': text(600), 'fallback': text(600),
                             'go_on': boolean(),
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
    # W1-ADAPT adds coverage (M5.1) and, on each Root review, the checks that ran (M7.3); W2-ADAPT adds round and rounds
    'view.adaptation': obj({
        'proposal': nullable(obj({'workflow': items(text(80)), 'source': nullable(text(40)), 'at': _AT})),
        'root_checks': items(obj({'summary': nullable(text(4000)), 'at': _AT, 'passed': boolean(),
                                  'checks': items(obj({'check': text(60), 'says': text(300), 'passed': boolean(), 'why': text(600)},
                                                      required=('check', 'says', 'passed', 'why')))})),
        'coverage': nullable(obj({'items': items(ref('id.item')), 'uncovered': items(ref('id.item')), 'by': enum('adaptation', 'default')},
                                 required=('items', 'uncovered', 'by'))),
        'rounds': items(obj({}))},
        required=('proposal', 'root_checks', 'rounds')),
    'view.priority': obj({
        'bargains': items(obj({'said': enum('said yes', 'asked for less', 'said no'), 'summary': nullable(text(4000)), 'at': _AT})),
        'envelopes': items(obj({'engine': text(80), 'calls': integer(0), 'usd': number(0), 'calls_limit': integer(0),
                                'usd_limit': number(0), 'share': number(0, 1)})),
        # from W1-PRIORITY (M5.3): what Priority priced and answered, newest first, from prices.jsonl; not required, so a
        # view written before it still validates
        'prices': items(obj({'at': _AT, 'proposal': enum('line', 'round', 'engine', 'cost'),
                             'answer': enum('accept', 'counter', 'reject'), 'said': enum('said yes', 'asked for less', 'said no'),
                             'estimate': obj({'calls': integer(0), 'usd': number(0)}, required=('calls', 'usd')),
                             'room': obj({'calls': integer(), 'usd': number()}, required=('calls', 'usd')), 'why': text(600)},
                            required=('at', 'proposal', 'answer', 'said', 'estimate', 'room', 'why'))),
        # from W2-PRIORITY (M9.2): the goal's ceiling, as the record keeps it, or null before the first registration; not required
        'ceiling': nullable(ref('priority.ceiling')),
        # from W2-PRIORITY (M9.6): what each round of the goal has spent, oldest first, from the runs the ledger links by run_ref;
        # not required
        'spend_by_round': items(obj({'round': integer(1), 'calls': integer(0), 'usd': number(0)}, required=('round', 'calls', 'usd')))},
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
    # W1-AUDIT adds latest and each reading's artifact, v, read, why_not_read and verdicts (M8.3, A1.17): optional, since a
    # reading from before the journal is only its summary and its time; latest.findings are the findings the newest reading
    # filed, so a low or medium one, which asks the owner nothing, is still shown
    'view.audit': obj({
        'readings': items(obj({'summary': nullable(text(4000)), 'at': _AT, 'artifact': ref('name'), 'v': integer(1),
                               'read': boolean(), 'why_not_read': nullable(text(300)),
                               'verdicts': map_of(enum(*ITEM_VERDICTS), keys=ITEM_RE)})),
        'findings': items(obj({'text': nullable(text(4000)), 'at': _AT})),
        'spot_checks': items(obj({})),
        'latest': nullable(obj({'artifact': ref('name'), 'v': integer(1), 'at': _AT,
                                'items': items(obj({'id': ref('id.item'), 'verdict': enum(*ITEM_VERDICTS), 'method': enum('code', 'model'),
                                                    'evidence': text(1000), 'claim': text(600)},
                                                   required=('id', 'verdict', 'method', 'evidence', 'claim'))),
                                'findings': items(ref('audit.finding'))},
                               required=('artifact', 'v', 'at', 'items')))},
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


# ---- the tables (A1.4; contents A1.5 to A1.17) -----------------------------------------------------------------------
#: every department key, its owning layer and its definition (A1.6). LEGACY_KEYS: keys no layer claims that older
#: records may still carry; none today.
DEPARTMENT_KEYS = {key: (owner, 'department.' + key) for key, owner, _ in _DEPARTMENT}
LEGACY_KEYS = ()

#: the records each layer owns: {layer: {kind: {def, store, writer}}}
RECORDS = {
    'root': {
        'department': {'def': 'department', 'store': 'dept.json', 'writer': 'W.create, W.save_dept'},
        'registration': {'def': 'workflow.registration', 'store': 'dept.json workflows[n]', 'writer': 'j2_runtime.registered'},
        'pins': {'def': 'root.pins', 'store': 'dept.json layers', 'writer': 'W.create (W1-ROOT), the migration'},
        'engine': {'def': 'engine.template', 'store': "the records home's _library/<slug>.json", 'writer': 'R.born_template'},
    },
    'identity': {
        'done_item': {'def': 'identity.done_item', 'store': 'dept.json done_items[n]', 'writer': 'W.done_items, W.apply_done_items'},
        'rule': {'def': 'identity.rule', 'store': 'dept.json rules[n]', 'writer': 'W.rule_row, through identity_apply'},
        'ask': {'def': 'identity.ask', 'store': 'asks.json', 'writer': 'W._put_ask (whoever files it: only Identity puts a decision to the owner)'},
    },
    'adaptation': {
        'proposal': {'def': 'act.line', 'store': 'board.jsonl propose/line', 'writer': 'R.adapt_line_offer, R.adapt_line_counter'},
        'idea': {'def': 'adaptation.idea', 'store': 'ideas.json', 'writer': 'R.adapt_park'},
        'ladder': {'def': 'adaptation.ladder', 'store': 'ladder.json', 'writer': 'R._save_entry'},
        'round': {'def': 'adaptation.round', 'store': 'rounds.jsonl', 'writer': 'W.append_row (W2-ADAPT, M9.1)'},
    },
    'priority': {
        'envelope': {'def': 'envelope', 'store': 'dept.json envelopes[name]', 'writer': 'W.create, W.set_envelope, W.add_engine, R.priority_grant'},
        'price': {'def': 'priority.price', 'store': 'prices.jsonl', 'writer': 'W.append_row (W1-PRIORITY, M5.3)'},
        'ceiling': {'def': 'priority.ceiling', 'store': 'dept.json ceiling', 'writer': 'priority/v1 (W2-PRIORITY, M9.2)'},
    },
    'coordination': {
        'table': {'def': 'coordination.table', 'store': 'coordination.json', 'writer': 'R.born, R._put_table (from R.set_line and R.grow_line)'},
        'slot': {'def': 'coordination.slot', 'store': 'coordination.json timetable[n]', 'writer': 'R.timetable_row'},
        'question': {'def': 'coordination.question', 'store': 'questions.json', 'writer': 'W3-BOARD (M4.9)'},
    },
    'audit': {
        'finding': {'def': 'act.finding', 'store': 'board.jsonl inform/finding, and the finding ask', 'writer': 'R.audit_file'},
        'reading': {'def': 'audit.reading', 'store': 'readings.jsonl', 'writer': 'W.append_row (W1-AUDIT, M8.3)'},
        'spot_check': {'def': 'audit.spot_check', 'store': 'spot_checks.jsonl', 'writer': 'W.append_row (W3-BOARD, M8.7)'},
    },
}

#: what each layer hears (A1.8 to A1.12): every handler of its recipe on main, and the in-process born rows (via call).
#: Every version must handle every row; a package adds its own rows when it builds a handler ('A1 interface:').
HEARS = {
    'root': [],
    'identity': [
        {'act': 'request', 'word': 'front', 'from': ('Owner', 'Root'), 'via': 'board', 'payload': 'act.words', 'handler': 'Hear the owner at the front door'},
        {'act': 'request', 'word': 'request', 'from': ('Owner', 'Root'), 'via': 'board', 'payload': 'act.words', 'handler': 'Take a request'},
        {'act': 'request', 'word': 'verdict', 'from': ('Coordination',), 'via': 'board', 'payload': 'act.verdict', 'handler': 'Give a verdict'},
        {'act': 'propose', 'word': 'rung', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.any', 'handler': 'Rule on a rung'},
        {'act': 'accept-proposal', 'word': ANY, 'from': ('Owner', 'Root'), 'via': 'board', 'payload': 'act.stamp', 'handler': 'Take a stamp'},
        {'act': 'reject-proposal', 'word': ANY, 'from': ('Owner', 'Root'), 'via': 'board', 'payload': 'act.stamp', 'handler': 'Take a no'},
        {'act': 'inform', 'word': 'finding', 'from': ('Audit',), 'via': 'board', 'payload': 'act.finding', 'handler': 'Hear a finding'},
        {'act': 'inform', 'word': 'alarm', 'from': ('Coordination',), 'via': 'board', 'payload': 'act.any', 'handler': 'Hear an alarm'},
        {'act': 'inform', 'word': 'idea', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.any', 'handler': 'Hear where an idea went'},
        {'act': 'inform', 'word': 'lost', 'from': ('Coordination',), 'via': 'board', 'payload': 'act.any', 'handler': 'Hear a lost request'},
        {'act': 'propose', 'word': 'engine', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.any', 'handler': 'an engine proposed'},
        {'act': 'propose', 'word': 'line', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.line', 'handler': 'a line proposed'},
        {'act': 'inform', 'word': 'conflict', 'from': ('Adaptation', 'Coordination'), 'via': 'board', 'payload': 'act.conflict', 'handler': 'Close a conflict'},
        {'act': 'inform', 'word': 'doubt', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.doubt', 'handler': 'Hear a doubt'},
        {'act': 'inform', 'word': 'reading', 'from': ('Audit',), 'via': 'board', 'payload': 'act.reading', 'handler': 'Hear a reading'},
        {'act': 'inform', 'word': 'round', 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.round', 'handler': 'File a granted round'},
    ],
    'adaptation': [
        {'act': 'accept-proposal', 'word': 'trial', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Start a trial'},
        {'act': 'reject-proposal', 'word': 'trial', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Drop a trial'},
        {'act': 'inform', 'word': 'rung', 'from': ('Identity',), 'via': 'board', 'payload': 'act.any', 'handler': 'Hear the ruling'},
        {'act': 'request', 'word': 'idea', 'from': ('Identity',), 'via': 'board', 'payload': 'act.any', 'handler': 'Hear an idea'},
        {'act': 'accept-proposal', 'word': 'engine', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Priority priced an engine: room'},
        {'act': 'reject-proposal', 'word': 'engine', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Priority priced an engine: no room'},
        {'act': 'request', 'word': 'line', 'from': ('Identity',), 'via': 'board', 'payload': 'act.line_request', 'handler': 'Shape the line'},
        {'act': 'accept-proposal', 'word': 'line', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Priority said yes to the line'},
        {'act': 'reject-proposal', 'word': 'line', 'from': ('Priority',), 'via': 'board', 'payload': 'act.any', 'handler': 'Priority said no to the line'},
        {'act': 'propose', 'word': 'line', 'from': ('Priority',), 'via': 'board', 'payload': 'act.line', 'handler': 'Priority asked for less on the line'},
    ],
    'priority': [
        {'act': 'propose', 'word': ANY, 'from': ('Adaptation',), 'via': 'board', 'payload': 'act.any', 'handler': 'Answer a proposal'},
        {'act': 'inform', 'word': 'born', 'from': ('Root', 'Identity'), 'via': 'call', 'payload': 'act.born', 'handler': 'An engine is born'},
    ],
    'coordination': [
        {'act': 'agree', 'word': 'verdict', 'from': ('Identity',), 'via': 'board', 'payload': 'act.verdict', 'handler': 'Hear a verdict'},
        {'act': 'refuse', 'word': 'verdict', 'from': ('Identity',), 'via': 'board', 'payload': 'act.verdict', 'handler': 'Hear a no'},
        {'act': 'inform', 'word': 'born', 'from': ('Root', 'Identity'), 'via': 'call', 'payload': 'act.born', 'handler': 'An engine is born'},
    ],
    'audit': [],          # it starts on a version of the deliverable, never on a post
}

#: what each actor sends, to whom, with which words (A1.13): derived from every post() call site of engine_runtime and
#: j2_runtime (test_layer_schema scans them with ast), keyed by the engine_defs actor names plus Engine. A site whose word
#: is not a literal has an (any) row, and so does an edge the definitions allow that no site posts on today; the union of
#: the rows' destinations is engine_defs' edges, in their order. Only Identity has Owner among its destinations.
_IDENTITY_TELLS = ('answer', 'broken', 'department', 'done_items', 'facts', 'filed', 'goal', 'idea', 'instructions', 'line',
                   'live', 'lost', 'plan', 'question', 'request', 'started', 'stopped', 'waits')
_IDENTITY_ASKS = ('blocked', 'conflict', 'done_items', 'engine', 'finding', 'instructions', 'line', 'publish', 'request', 'rule',
                  'rung', 'setup', 'step')
SENDS = {
    'Owner': [
        {'act': 'request', 'words': ('front', 'request'), 'to': ('Identity',), 'payload': 'act.words'},
        {'act': 'accept-proposal', 'words': ANY, 'to': ('Identity',), 'payload': 'act.stamp'},     # the word is the ask's kind
        {'act': 'reject-proposal', 'words': ANY, 'to': ('Identity',), 'payload': 'act.stamp'},
        {'act': 'cancel', 'words': ANY, 'to': ('Identity',), 'payload': 'act.any'},
    ],
    'Root': [
        {'act': 'request', 'words': ('request',), 'to': ('Identity',), 'payload': 'act.words'},
        {'act': 'accept-proposal', 'words': ANY, 'to': ('Identity',), 'payload': 'act.stamp'},
        {'act': 'reject-proposal', 'words': ANY, 'to': ('Identity',), 'payload': 'act.stamp'},
        {'act': 'cancel', 'words': ANY, 'to': ('Identity',), 'payload': 'act.any'},
    ],
    'Identity': [
        {'act': 'agree', 'words': ANY, 'to': ('Owner', 'Adaptation'), 'payload': 'act.any'},
        {'act': 'agree', 'words': ('verdict',), 'to': ('Coordination',), 'payload': 'act.verdict'},
        {'act': 'refuse', 'words': ('request',), 'to': ('Owner',), 'payload': 'act.tell'},
        {'act': 'refuse', 'words': ANY, 'to': ('Adaptation',), 'payload': 'act.any'},
        {'act': 'refuse', 'words': ('verdict',), 'to': ('Coordination',), 'payload': 'act.verdict'},
        {'act': 'request', 'words': _IDENTITY_ASKS, 'to': ('Owner',), 'payload': 'act.ask'},
        {'act': 'request', 'words': ('line',), 'to': ('Adaptation',), 'payload': 'act.line_request'},
        {'act': 'request', 'words': ('idea',), 'to': ('Adaptation',), 'payload': 'act.any'},
        {'act': 'request', 'words': ('next',), 'to': ('Adaptation',), 'payload': 'act.next'},      # W2-IDENTITY, M8.5
        {'act': 'inform', 'words': _IDENTITY_TELLS, 'to': ('Owner',), 'payload': 'act.tell'},
        {'act': 'inform', 'words': ANY, 'to': ('Owner',), 'payload': 'act.tell'},    # _reconcile_j1_tells posts the tell Setup stored
        {'act': 'inform', 'words': ('rung',), 'to': ('Adaptation',), 'payload': 'act.any'},
        # born on the board names only which record it means, and its handler refuses what that record does not hold
        # (_born_on_board, M4.1's fix): the payload is the handler's to judge, so only its word is typed here; the item
        # the word carries in place, by call, is act.born
        {'act': 'inform', 'words': ('born',), 'to': ('Priority',), 'payload': 'act.any'},
        {'act': 'inform', 'words': ANY, 'to': ('Audit',), 'payload': 'act.any'},
        {'act': 'inform', 'words': ('born',), 'to': ('Coordination',), 'payload': 'act.any'},
        {'act': 'failure', 'words': ANY, 'to': ('Owner',), 'payload': 'act.tell'},
    ],
    'Adaptation': [
        {'act': 'propose', 'words': ('line',), 'to': ('Priority', 'Identity'), 'payload': 'act.line'},
        {'act': 'propose', 'words': ('engine', 'trial'), 'to': ('Priority',), 'payload': 'act.any'},
        {'act': 'propose', 'words': ('engine', 'rung'), 'to': ('Identity',), 'payload': 'act.any'},
        {'act': 'inform', 'words': ('idea',), 'to': ('Identity',), 'payload': 'act.any'},
        {'act': 'inform', 'words': ('conflict',), 'to': ('Identity',), 'payload': 'act.conflict'},
        {'act': 'inform', 'words': ('doubt',), 'to': ('Identity',), 'payload': 'act.doubt'},      # W1-ADAPT, M6.4
    ],
    'Priority': [
        # Priority answers with the word of the proposal it answers (priority_post), and asks for less on any of them
        {'act': 'accept-proposal', 'words': ANY, 'to': ('Adaptation',), 'payload': 'act.any'},
        {'act': 'reject-proposal', 'words': ANY, 'to': ('Adaptation',), 'payload': 'act.any'},
        {'act': 'propose', 'words': ('line',), 'to': ('Adaptation',), 'payload': 'act.line'},
        {'act': 'propose', 'words': ANY, 'to': ('Adaptation',), 'payload': 'act.any'},
    ],
    'Audit': [
        {'act': 'inform', 'words': ('finding',), 'to': ('Identity',), 'payload': 'act.finding'},
        # a reading (M8.3): posted only once Identity's recipe has a handler for it, which W2-IDENTITY adds (A1-14)
        {'act': 'inform', 'words': ('reading',), 'to': ('Identity',), 'payload': 'act.reading'},
    ],
    'Coordination': [
        {'act': 'request', 'words': ('verdict',), 'to': ('Identity', 'Priority'), 'payload': 'act.verdict'},
        {'act': 'inform', 'words': ('alarm', 'lost'), 'to': ('Identity',), 'payload': 'act.any'},
        {'act': 'inform', 'words': ('conflict',), 'to': ('Identity',), 'payload': 'act.conflict'},
    ],
    'Engine': [],           # W3-BOARD adds request/question (M4.9)
}

#: the in-process calls between layers (A1.13): a decision that runs another layer's handler in place, not as a post.
#: test_layer_schema scans engine_runtime for every _ask_rule site whose step is another layer's and finds it here.
CALLS = (
    {'from': 'Root', 'to': 'Coordination', 'what': 'coord.table', 'site': '_registered'},
    {'from': 'Root', 'to': 'Priority', 'what': 'priority.grant', 'site': '_registered'},
    {'from': 'Identity', 'to': 'Coordination', 'what': 'coord.table', 'site': 'engine_added'},
    {'from': 'Identity', 'to': 'Priority', 'what': 'priority.grant', 'site': 'engine_added'},
    {'from': 'Root', 'to': 'Identity', 'what': '_blocked', 'site': '_j2_settle'},
    # beyond A1.13's table, from the M3 fix wave: Identity's budget point asks Priority to give the five their limits
    {'from': 'Identity', 'to': 'Priority', 'what': 'priority.grant', 'site': '_priority_limits'},
)

#: each layer's verdict enums (A1.7 to A1.12)
VERDICTS = {
    'root': {'converse': ('ask', 'clear'), 'route': ('organic', 'template'), 'check': ('approved', 'sent back', 'blocked')},
    'identity': {'take': ('go', 'ask', 'refuse'), 'gate': ('admit', 'wait', 'refuse'), 'ruling': ('run', 'drop', 'ask'),
                 'journey': ('task', 'query', 'directive', 'feedback', 'new-idea'), 'rule': ('always', 'ask', 'refuse', 'goal'),
                 'scope': ('standing', 'one-time'), 'weigh': ('format', 'content', 'tone', 'scope', 'accuracy'),
                 'confidence': ('high', 'moderate', 'low', 'unknown'), 'enough': (True, False), 'missing': STANDARD},
    'adaptation': {'source': SOURCES, 'move': ('down', 'trial', 'propose', 'end-trial')},
    'priority': {'answer': ('accept', 'counter', 'reject'), 'envelope': ('admit', 'wait')},
    'coordination': {'gate': ('admit', 'wait', 'refuse'), 'slot': SLOT_STATES},
    'audit': {'ok': (True, False), 'severity': SEVERITIES, 'item': ITEM_VERDICTS},
}

#: each layer's covering checks, by name, with what each holds (A1.7 to A1.12); a check two or more layers name is shared.
#: The bodies are engine_runtime's CHECK registry until a layer moves one into its own CHECK dict.
SHARED_CHECKS = {
    'facts_are_closed': 'every fact a step read by code is one of a closed set',
    'said_what_it_did': 'the step says what it did',
    'gate_answer_is_known': "a gate's answer is admit, wait or refuse",
}
CHECKS = {
    'root': {'setup_converse_is_valid': 'one question to the owner, or clear',
             'department_is_shaped': 'a name, a kind the Library has, a goal, and done-when items each with how and level',
             'department_is_made': 'the department exists under Root, on the runtime, and has its goal',
             'filed_has_files': 'what was filed holds its files and their verdict'},
    'identity': {'answer_names_its_source': 'an answer, its source, and how sure it is',
                 'enough_is_shaped': "enough is a yes or a no; what is missing is named by the standard's points; a no asks one question",
                 'feedback_says_what_changes': 'feedback says what kind of change it is and what to correct now',
                 'gate_verdict_is_known': "a gate's verdict is admit, wait or refuse",
                 'journey_is_known': "the words are one of canon's five journeys",
                 'rule_is_tagged': 'a rule is one line, tagged, with its scope',
                 'ruling_is_known': 'a ruling is run, drop or ask',
                 'done_is_read': 'the goal is reached only from a reading: the version was read, every item is met, none is to confirm and no high finding is open',
                 'verdict_is_known': 'a verdict is go, ask or refuse, and an ask or a no says why'},
    'adaptation': {'counted_the_rows': 'every step is counted from its own rows',
                   'idea_has_shapes': 'an idea is reflected back with the shapes it could take',
                   'line_is_engines': 'a shaped line is one to six engines that code finds nothing wrong with',
                   'moves_name_their_rows': 'each move is of a known kind and names the rows it rests on'},
    'priority': {'answer_has_its_price': 'said yes, asked for less or said no, each with its price; an ask for less names what it keeps',
                 'price_is_observed': 'a yes, or an ask for less, is held to the facts Priority read: what it keeps costs no more than '
                                      'the room left; a no, or a smaller yes, always stands',
                 'round_within_ceiling': "a yes to a round is held to the goal's ceiling: the round, the calls and the money all inside "
                                         'it; a no always stands'},
    'coordination': {'chain_under_its_limit': 'a start is let through only while the chain is under its limit',
                     'names_who_goes_first': 'it names an engine of the department',
                     'one_run_at_a_time': 'a start is let through only while no other run runs'},
    'audit': {'findings_name_where_and_what': 'each finding names where it is and what it claims',
              'has_a_verdict': 'a mechanical check gives a verdict with its notes',
              'picked_a_sample': 'it says whether it sampled, and which pages',
              'reading_is_s30': 'each done-when item has its reading: a verdict, the claim and the evidence behind it; each finding says where and what'},
}

#: samples every implementation's check must judge as main's bodies do (A1.21), each checked against the body on main;
#: only samples whose verdict needs no department in the context are kept (enough_is_shaped's yes reads the record's gaps)
CONTRACT_SAMPLES = {
    'verdict_is_known': {'good': [{'verdict': 'go', 'why': 'inside the goal'}, {'verdict': 'ask', 'why': 'it reaches outside'}],
                         'bad': [{'verdict': 'maybe', 'why': 'x'}]},
    'ruling_is_known': {'good': [{'ruling': 'drop', 'why': 'the goal does not need it'}], 'bad': [{'ruling': 'perhaps', 'why': 'x'}]},
    'done_is_read': {'good': [{'done': False, 'why': 'D2 is not met'},
                              {'done': True, 'reading': 'r-1a2b3c4d', 'read': True, 'met': ['D1', 'D2'], 'not_met': [], 'to_confirm': [],
                               'unread': [], 'high': False, 'why': 'every done-when item is met'}],
                      'bad': [{'done': 'yes'}, {'done': False, 'why': ''},
                              {'done': True, 'read': True, 'met': ['D1'], 'not_met': [], 'to_confirm': [], 'unread': [], 'high': False, 'why': 'x'},
                              {'done': True, 'reading': 'r-1a2b3c4d', 'read': False, 'met': ['D1'], 'not_met': [], 'to_confirm': [], 'unread': [],
                               'high': False, 'why': 'x'},
                              {'done': True, 'reading': 'r-1a2b3c4d', 'read': True, 'met': ['D1'], 'not_met': ['D2'], 'to_confirm': [],
                               'unread': [], 'high': False, 'why': 'x'},
                              {'done': True, 'reading': 'r-1a2b3c4d', 'read': True, 'met': ['D1'], 'not_met': [], 'to_confirm': ['D2'],
                               'unread': [], 'high': False, 'why': 'x'},
                              {'done': True, 'reading': 'r-1a2b3c4d', 'read': True, 'met': ['D1', 'D2'], 'not_met': [], 'to_confirm': [],
                               'unread': [], 'high': True, 'why': 'x'}]},
    'answer_has_its_price': {'good': [{'answer': 'accept', 'why': 'fits today: 9 calls of 30'}],
                             'bad': [{'answer': 'accept', 'why': ''}, {'answer': 'grant', 'why': 'x'}]},
    'price_is_observed': {'good': [{'answer': 'counter', 'why': 'room for two today: 0.08 USD for these of the 0.30 USD left',
                                    'keep': ['Plan', 'Write']},
                                   {'answer': 'reject', 'why': 'no room today: the first costs 0.08 USD against 0.00 USD left'}],
                          'bad': [{'answer': 'counter', 'why': 'room for two today', 'keep': []}, {'answer': 'accept', 'why': ''},
                                  {'answer': 'grant', 'why': 'x'}]},
    'round_within_ceiling': {'good': [{'answer': 'accept', 'why': 'inside the ceiling: round 3 of 6, about 11 calls and 0.40 USD of the 44 '
                                                                 'calls and 1.58 USD left'},
                                      {'answer': 'reject', 'why': 'no room in the ceiling: round 7 against a ceiling of 6 rounds'}],
                             'bad': [{'answer': 'counter', 'why': 'room for two rounds'}, {'answer': 'accept', 'why': ''},
                                     {'answer': 'grant', 'why': 'x'}]},
    'findings_name_where_and_what': {'good': [{'ok': True, 'findings': []}],
                                     'bad': [{'ok': False, 'findings': [{'claim': 'x'}]}, {'ok': False, 'findings': 'none'}]},
    'reading_is_s30': {'good': [{'items': [{'id': 'D1', 'verdict': 'met', 'claim': 'every page is checked and live',
                                            'evidence': 'the live site passed its check'}], 'findings': []},
                                {'items': [], 'findings': [], 'read': False}],
                       'bad': [{'items': [{'id': 'D1', 'verdict': 'fine', 'claim': 'x', 'evidence': 'y'}], 'findings': []},
                               {'items': [{'id': 'D1', 'verdict': 'met', 'claim': 'x', 'evidence': ''}], 'findings': []},
                               {'items': [{'id': 'D1', 'verdict': 'met', 'claim': 'x', 'evidence': 'y'}], 'findings': [{'claim': 'x'}]},
                               {'items': 'none', 'findings': []}]},
    'enough_is_shaped': {'good': [],
                         'bad': [{'enough': 'yes', 'missing': []}, {'enough': False, 'missing': ['colour'], 'question': 'x?'}]},
}

#: the step outputs code outside the layer reads (functions_view's ties and turns): every version returns these keys
OUTPUTS = {'coord.pick': ('answer',), 'coord.tie': ('answer', 'why')}

#: each layer's settings: {name: {def, default, changed_by, says}}
SETTINGS = {
    'root': {},
    'identity': {'windows': {'def': 'setting.windows', 'default': {'Plan': 15, 'Write': 30, 'Check': 5, 'Publish': 10},
                             'changed_by': 'set at birth and when an engine is added; no way for the owner to change it in A1',
                             'says': "each engine's window, in minutes, before Coordination raises an alarm"}},
    'adaptation': {'make': {'def': 'setting.make', 'default': False,
                            'changed_by': 'the build flag J2_ADAPT_MAKE, in Beta only; not a switch of the interface',
                            'says': 'Adaptation makes a line when no template fits'}},
    'priority': {'envelope': {'def': 'envelope', 'default': {'calls': 30, 'usd': 6.0, 'work_calls': 8},
                              'changed_by': "POST /envelope (W.set_envelope), from Priority's card",
                              'says': "each engine's limit a day: calls and money; a work engine is given work_calls times the calls"}},
    'coordination': {'order': {'def': 'setting.order', 'default': ['posts', 'line', 'functions'],
                               'changed_by': 'shown, not changed in A1', 'says': 'who goes first when several are ready'}},
    'audit': {'spot_every_s': {'def': 'setting.spot_every_s', 'default': 86400, 'changed_by': 'not changed in A1; used from wave 3 (M8.7)',
                               'says': 'how often Audit drops in unannounced: once a day, at a random minute'}},
}

#: each prompt group's lead line (A1.16 rule 1), the first paragraph of its file; Root's has no file
GROUPS = {
    'root': {'setup': 'How Root sets up a department the owner asks for: what it asks, and the department it shapes.'},
    'identity': {'goal': 'What Identity is for, and the rules it keeps.',
                 'completeness': 'When the department has enough to work; what to ask if not.',
                 'take': 'How to judge a request: go, ask or refuse.'},
    'adaptation': {'goal': 'What Adaptation is for, and the rules it keeps.',
                   'sense': 'How Adaptation reads an idea the owner floats: what it asks, and the shapes it could take.',
                   'decide': "How Adaptation chooses its next move from what the department's own rows say.",
                   'make': 'How Adaptation shapes the workflows a goal needs when none is in place.'},
    'priority': {'goal': 'What Priority is for, and the rules it keeps.',
                 'bargain': 'How Priority answers a proposal: said yes, asked for less, or said no.'},
    'coordination': {'goal': 'What Coordination is for, and the rules it keeps.',
                     'tie': 'How Coordination says who goes first when several functions are ready at once.'},
    'audit': {'goal': 'What Audit is for, and the rules it keeps.',
              'judge': 'How Audit reads what went live against what was asked.'},
}

#: each layer's prompt slots (A1.16): {layer: {group: {part: {fields, inputs, returns, read_by}}}}. The split rule was run
#: once over function-prompts/*.md and over p_setup_converse and p_setup_shape, and its result is written here as
#: literals; no .md file is read at runtime. fields: the owner's fields and their DEFS; inputs: the names code fills;
#: returns: the answer contract, byte for byte, or None; read_by: the step id that reads the part (a tuple when several
#: do), or None. A part whose first line holds an input, and whose words before its contract hold inputs too, has no
#: owner field by the split rule (close, shape, make.line, bargain.line, refused, setup.shape): its words stay in LAYOUT.
PROMPTS = {
    'root': {
        'setup': {
            'converse': {'fields': {'task': 'field.task'},
                         'inputs': ('examples', 'library', 'existing', 'conversation'),
                         'returns': 'Return ONLY a JSON object: {"verdict": "ask" | "clear", "question": "your one question, or an empty string when clear"}.',
                         'read_by': 'setup.converse'},
            'shape': {'fields': {}, 'inputs': ('org', 'words', 'named', 'kinds', 'use_cases', 'existing'),
                      'returns': 'Return ONLY a JSON object: {"name": "...", "kind": "one of the kinds above", "goal": "...", '
                                 '"purpose": "one line", "second": "...", "done_items": [{"text": "...", "how": "code" | "model" | '
                                 '"person", "level": "target" | "outcome", "confirm": "..."}]}.',
                      'read_by': 'setup.shape'},
        },
    },
    'identity': {
        'goal': {
            'does': {'fields': {'text': 'field.text'}, 'inputs': (), 'returns': None, 'read_by': None},
            'skills': {'fields': {'items': 'field.items'}, 'inputs': (), 'returns': None, 'read_by': None},
            'close': {'fields': {}, 'inputs': ('dept', 'goal', 'done', 'rules', 'plan', 'against'),
                      'returns': 'Return ONLY a JSON object: {"ruling": "run" | "drop" | "ask", "why": "one line, naming the rule or the goal"}.',
                      'read_by': 'identity.close'},
        },
        'completeness': {
            'thin': {'fields': {'task': 'field.task'}, 'inputs': (), 'returns': None, 'read_by': None},
            'enough': {'fields': {'task': 'field.task'}, 'inputs': ('words', 'asked', 'goal', 'items', 'rules', 'owner', 'budget', 'confirm'),
                       'returns': 'Return ONLY a JSON object: {"enough": bool, "missing": ["goal" | "items" | "rules" | "owner" | "budget" | '
                                  '"invented"], "question": "one question, or an empty string when enough", "why": "one line"}.',
                       'read_by': 'identity.enough'},
        },
        'take': {
            'recognise': {'fields': {'task': 'field.task'}, 'inputs': ('goal', 'words', 'facts'),
                          'returns': 'Return ONLY a JSON object: {"journey": "task" | "query" | "directive" | "feedback" | "new-idea", '
                                     '"why": "one line"}.',
                          'read_by': 'identity.recognise'},
            'take': {'fields': {'task': 'field.task', 'guidance': 'field.guidance'}, 'inputs': ('goal', 'rules', 'words', 'facts', 'completeness'),
                     'returns': 'Return ONLY a JSON object: {"verdict": "go" | "ask" | "refuse", "why": "one line", "unsure": [str], '
                                '"rule": {"line": str, "tag": "always" | "refuse" | "ask"} | null, "thin": bool}.',
                     'read_by': 'identity.take'},
            'answer': {'fields': {'task': 'field.task'}, 'inputs': ('question', 'record'),
                       'returns': 'Return ONLY a JSON object: {"answer": str, "source": "which line of the record", "confidence": "high" | '
                                  '"moderate" | "low" | "unknown"}.',
                       'read_by': 'identity.answer'},
            'rule': {'fields': {'task': 'field.task', 'guidance': 'field.guidance'}, 'inputs': ('goal', 'rules', 'words'),
                     'returns': 'Return ONLY a JSON object: {"tag": "always" | "ask" | "refuse" | "goal", "line": str, "scope": "standing" | '
                                '"one-time"}.',
                     'read_by': 'identity.rule'},
            'weigh': {'fields': {'task': 'field.task'}, 'inputs': ('pages', 'words'),
                      'returns': 'Return ONLY a JSON object: {"about": "the page\'s slug, or null", "what": "format" | "content" | "tone" | '
                                 '"scope" | "accuracy", "now": "the correction to make now, one line", "future": "a rule to carry forward '
                                 'to work like this, one line, or null"}.',
                      'read_by': 'identity.weigh'},
            'gate': {'fields': {'task': 'field.task'}, 'inputs': ('rules', 'engine'),
                     'returns': 'Return ONLY a JSON object: {"verdict": "admit" | "wait" | "refuse", "why": "one line"}.',
                     'read_by': ('identity.gate', 'identity.wait_engine', 'identity.judge')},
        },
    },
    'adaptation': {
        'goal': {
            'does': {'fields': {'text': 'field.text'}, 'inputs': (), 'returns': None, 'read_by': None},
            'skills': {'fields': {'items': 'field.items'}, 'inputs': (), 'returns': None, 'read_by': None},
        },
        'sense': {
            'shape': {'fields': {}, 'inputs': ('needs', 'goal', 'idea', 'library'),
                      'returns': 'Return ONLY a JSON object: {"reflected": str, "question": str, "shapes": [str, str, str], "pick": str or '
                                 'null, "engine": {"name": str, "does": str, "needs": [str]} or null}.',
                      'read_by': 'adapt.shape'},
        },
        'decide': {
            'note': {'fields': {'text': 'field.note'}, 'inputs': (), 'returns': None, 'read_by': None},   # NOT_READ: no run reads it
        },
        'make': {
            'line': {'fields': {}, 'inputs': ('dept', 'words', 'items', 'taken', 'out', 'rules', 'refused'),   # items: W1-ADAPT, M5.1
                     'returns': 'Return ONLY a JSON object: {"engines": [{"name": str, "does": str, "reads": str, "writes": str, '
                                '"internet": bool}]}.',
                     'read_by': 'adapt.line'},
            'refused': {'fields': {}, 'inputs': ('faults',), 'returns': None, 'read_by': None},   # feeds make.line's refused input
            # A1-SHAPE (W1-ADAPT, M6.4): adapt.line reads this part, not make.line, when the make setting is on and no template fits
            'shape': {'fields': {'task': 'field.task', 'guidance': 'field.guidance'},
                      'inputs': ('dept', 'words', 'items', 'practices', 'rules', 'taken', 'out', 'refused'),
                      'returns': 'Return ONLY a JSON object: {"engines": [{"name": str, "does": str, "reads": str, "writes": str, '
                                 '"covers": ["D1"], "level": 1 | 2, "confidence": number, "doubt": str, "internet": bool}]}, or '
                                 '{"cannot": {"engine": str, "items": ["D1"], "why": str}} when an engine the kind requires cannot '
                                 'serve an item.',
                      'read_by': 'adapt.line'},
        },
    },
    'priority': {
        'goal': {
            'does': {'fields': {'text': 'field.text'}, 'inputs': (), 'returns': None, 'read_by': None},
            'skills': {'fields': {'items': 'field.items'}, 'inputs': (), 'returns': None, 'read_by': None},
        },
        'bargain': {
            'line': {'fields': {}, 'inputs': ('source', 'engines', 'calls', 'usd', 'room', 'limit', 'estimate', 'remaining'),
                     'returns': 'Return ONLY a JSON object: {"answer": "accept" | "counter" | "reject", "why": "one line", "keep": [names]}.',
                     'read_by': 'priority.bargain'},
            'engine': {'fields': {'task': 'field.task'}, 'inputs': ('engine', 'does', 'needs', 'calls', 'usd', 'room'),
                       'returns': 'Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line"}.',
                       'read_by': 'priority.bargain'},
            'cost': {'fields': {'task': 'field.task'}, 'inputs': ('word', 'step', 'cost', 'room'),
                     'returns': 'Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line"}.',
                     'read_by': 'priority.bargain'},
            # added by W2-PRIORITY (M9.2, A1-ROUND): a round Adaptation proposes on the line, held to the goal's ceiling
            'round': {'fields': {'task': 'field.task'}, 'inputs': ('round', 'correction', 'estimate', 'room', 'ceiling', 'remaining'),
                      'returns': 'Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line, in money and room only"}.',
                      'read_by': 'priority.bargain'},
        },
    },
    'coordination': {
        'goal': {
            'does': {'fields': {'text': 'field.text'}, 'inputs': (), 'returns': None, 'read_by': None},
            'skills': {'fields': {'items': 'field.items'}, 'inputs': (), 'returns': None, 'read_by': None},
        },
        'tie': {
            'tie': {'fields': {'task': 'field.task'}, 'inputs': ('ready', 'what', 'order', 'waiting'),
                    'returns': 'Return ONLY a JSON object: {"answer": "one of the ready names", "why": "one line"}.',
                    'read_by': 'coord.tie'},
        },
    },
    'audit': {
        'goal': {
            'does': {'fields': {'text': 'field.text'}, 'inputs': (), 'returns': None, 'read_by': None},
            'skills': {'fields': {'items': 'field.items'}, 'inputs': (), 'returns': None, 'read_by': None},
        },
        'judge': {
            'judge': {'fields': {'task': 'field.task', 'guidance': 'field.guidance'}, 'inputs': ('brief', 'filed', 'pages'),
                      'returns': 'Return ONLY a JSON object: {"ok": bool, "findings": [{"page": str, "claim": str, "severity": "high" | '
                                 '"low"}]}.',
                      'read_by': 'audit.judge'},
            # added by W1-AUDIT (M8.3, A1-ITEMS): one reading per done-when item, in the S-30 shape
            'items': {'fields': {'task': 'field.task', 'guidance': 'field.guidance'},
                      'inputs': ('brief', 'filed', 'deliverable', 'items', 'measured'),
                      'returns': 'Return ONLY a JSON object: {"items": [{"id": "D1", "verdict": "met" | "not_met" | "to_confirm", '
                                 '"claim": "what is or is not true, one line", "evidence": "what in the work shows it, one line"}], '
                                 '"findings": [{"where": str, "claim": str, "severity": "high" | "medium" | "low", "item": "D1" or null}]}.',
                      'read_by': 'audit.items'},
        },
    },
}

#: the prompt parts later steps added to PROMPTS (A1.16, 'Parts added by later steps'): a layer's WORDS and LAYOUT hold
#: them, and no .md file of the bundle does, so the extractor and the bundle's tests leave them out. A package adds its own.
ADDED_PARTS = (('adaptation', 'make', 'shape'), ('priority', 'bargain', 'round'))

#: each layer's pane view (A1.17), plus the engine card
VIEWS = {'identity': 'view.identity', 'adaptation': 'view.adaptation', 'priority': 'view.priority',
         'coordination': 'view.coordination', 'audit': 'view.audit', 'engine_card': 'view.engine_card'}

#: the department files checked where they are written (A1.20: website_dept._write is the sink), and the journals checked
#: row by row (W.append_row)
SINK = {'dept.json': 'department', 'asks.json': 'identity.ask', 'coordination.json': 'coordination.table',
        'instructions.json': 'instructions'}
SINK_JOURNALS = {'readings.jsonl': 'audit.reading', 'prices.jsonl': 'priority.price', 'rounds.jsonl': 'adaptation.round',
                 'spot_checks.jsonl': 'audit.spot_check'}

#: what each layer is, as its page says it (functions_view.PAGES' vsm, line, holds, hands_to, keeps and v1, copied here
#: verbatim; W1-CORE makes functions_view read them from here), with the names this module holds for it
_PAGES = {
    'root': {
        'vsm': "Root: the organisation's own department",
        'line': 'Makes each department and its five functions from the Library, writes the record its workflow is held to, '
                'and checks every plan against the workflow standards before it runs. It never creates or starts an engine.',
        'holds': "The department's record: its kind, its line and artifacts, its registered workflows and the version each "
                 'function runs.',
        'hands_to': "Identity: the owner's words for a department, and a plan it could not register. Coordination and "
                    'Priority: a registered plan.',
        'keeps': 'Makes the department and its five functions, never an engine; engines come from Adaptation. Every plan '
                 'meets the standards before it runs.',
        'v1': "Setup sets up a department from the Library's templates; the owner stamps it.",
    },
    'identity': {
        'vsm': 'VSM S5: identity and policy',
        'line': "The department's voice and conscience. It hears you, checks that the identity is good enough, gates every "
                'effect by rule, closes conflicts, and says when the goal is reached.',
        'holds': "Goal, done-when, rules (go, ask, never, always), budget, owner and parent, and each engine's window.",
        'hands_to': 'Adaptation: a request for a line, and the next thing to correct. Coordination: verdicts on gates. '
                    'You: it is the only function that speaks to you.',
        'keeps': 'Never makes anything; the maker is an engine. Asks only when a rule says ask. Approvals only tighten. '
                 'Never invents a goal or a rule, and asks one question at a time.',
        'v1': 'Your words become the Brief, one question when the words are thin, the ask before the first publish, and a tell.',
    },
    'adaptation': {
        'vsm': 'VSM S4: outside and future',
        'line': 'Decides how the department gets there. It proposes the workflows the goal needs, from the Library, fitted, '
                'or made fresh, and after each reading it proposes the next round, until the goal holds.',
        'holds': 'Its proposals on the board, the ideas it parked, the ladder of every step, and its rounds.',
        'hands_to': 'Priority: every proposal and every round. Identity: conflicts, and a round Priority said yes to, to file. '
                    'Root: the line Priority said yes to, for its check.',
        'keeps': 'Senses and proposes; never applies. Every proposal passes Priority first. May leave out an engine its '
                 'template does not mark required. Engines come from Adaptation, never from Root.',
        'v1': 'Two to five workflows from the Library or shaped for the goal; no loop and no Make module yet.',
    },
    'priority': {
        'vsm': 'VSM S3: inside and now',
        'line': 'Prices every proposal against the room actually left and holds the budget. It says yes, asks for less, or '
                'says no. Who goes first is never its call.',
        'holds': 'One limit per engine (calls and money a day) and the bargain threads.',
        'hands_to': 'Adaptation: said yes, asked for less, or said no. Identity: through Adaptation\'s conflict, when a limit is hit.',
        'keeps': "Prices and holds the budget; who goes first is Coordination's call. Never starts a run and never says no "
                 'over method. Never changes the goal or speaks to you.',
        'v1': 'The limit on every start, as built. Nothing else.',
    },
    'coordination': {
        'vsm': 'VSM S2: timetables and standards',
        'line': 'Keeps the timetable: a slot for each engine, who goes first, one run at a time, hand-offs, a chain that '
                'stops at its limit, and an alarm past a window. It judges nothing about content.',
        'holds': "Its table: the order, the line and who may post to whom; the run rows and each thread's bounds.",
        'hands_to': 'Identity: alarms, lost requests and verdict asks. Priority: verdict asks.',
        'keeps': 'No model call inside a tick; a missed slot runs once, and each slot runs once. The engine starts itself in '
                 'its slot. Never changes limits, scope or quality calls.',
        'v1': 'As built.',
    },
    'audit': {
        'vsm': 'VSM S3*: sporadic direct inspection',
        'line': 'The second pair of eyes. It reads what the department actually filed, item by item against done-when, '
                'with code checks first, and it also drops in unannounced. Its findings go to Identity.',
        'holds': 'Its readings and its findings.',
        'hands_to': 'Identity only: readings and findings.',
        'keeps': 'The checker is never the writer; it never touches a workflow or a version. A check is a check, never a '
                 'score. It reads what the department did, never only its goal.',
        'v1': 'As built: read the live site against the words.',
    },
}
LAYERS = {
    layer: dict(_PAGES[layer], **{
        'title': TITLE[layer],
        'keys': tuple(k for k, (owner, _) in DEPARTMENT_KEYS.items() if owner == layer),
        'records': tuple(RECORDS[layer]),
        'verdicts': tuple(VERDICTS[layer]),
        'checks': tuple(CHECKS[layer]),
        'settings': tuple(SETTINGS[layer]),
        'prompts': tuple(PROMPTS[layer]),
        'view': VIEWS.get(layer),
        'options': tuple(k for k, o in OPTION_KINDS.items() if o['layer'] == layer),
        'recipe': 'Setup' if layer == 'root' else 'v1.json',
    })
    for layer in LAYER_NAMES
}


# ---- A3: the templates at every level (PRD amendment A3) --------------------------------------------------------------
# A template is an interface is a base class, at every level: fixed, never run by itself, written only in code. What fills
# it is a child: a module or a data file that conforms. This section types the levels A1 and A2 left as prose. Every name
# here is additive ('A3 interface:' commits): nothing above is renamed, and nothing in the runtime reads a definition
# below, so the definitions describe what the runtime already enforces and a test keeps the two equal. A bound is written
# against the shipped files and never narrower than one of them.

# the step (L4, A3.3): the shape law. engine_runtime.validate stays the definition law (names that ship, ids used once,
# a unit that starts and ends with code); this one says what a step may hold, and has no registry in it
NATURES = ('transform', 'check', 'decide', 'make')                     # == engine_runtime.NATURES
GATE_ANSWERS = ('admit', 'wait', 'refuse')                             # == VERDICTS['identity']['gate'], and what a gate's check accepts
MODEL_TOOLS = ('WebSearch', 'WebFetch')                                # == website_dept.MODEL_TOOLS
STEP_KINDS = ('code', 'ai', 'person', 'gate', 'rule')
#: every key a step's body is handed in its context, as a recorded run saw them: peek is on Coordination's rule context and
#: on every gate's; table, rs and done are Coordination's; ready is the tie's; run and spend are an engine run's. item is the
#: fan-out item (the body's third argument on main; reserved here as A3.3 names it)
STEP_CTX = ('ref', 'dept', 'engine', 'def', 'slot', 'inp', 'post', 'run', 'bag', 'how', 'spend', 'table', 'rs', 'done', 'ready',
            'item', 'peek')
#: every key of a line of steps.jsonl, from the three writers (run_step, a gate's decision, the owner's mark): ask is on the
#: row of a step that waits for the owner
STEP_ROW = ('id', 'run', 'engine', 'step', 'item', 'mode', 'slot', 'impl', 'asked_rung', 'rung', 'miss', 'by', 'agent', 'applied',
            'read', 'facts', 'in_sig', 'usd', 'calls', 'def_version', 'started', 'status', 'why', 'ask', 'answer', 'out_hash',
            'out_shape', 'check', 'trial', 'ended', 'ms')


def _law(law, schema):
    """A step field's place in the law of inheritance (A2): fixed, a child version keeps the parent's value; free, a child
    may change it. The classification is read from DEFS['step'] by template_checks.step_law, so the law has one source."""
    return dict(schema, **{'x-law': law})


def step_kind(step, group='steps'):
    """The one kind a step has (ST-3): 'gate' or 'rule' by the list the recipe holds it in ('gates', 'rules'); else 'person'
    when it is born on the person's rung, 'ai' when it has a prompt, and 'code' when it has neither. `group` is 'steps' for
    a handler's steps too."""
    if group == 'gates':
        return 'gate'
    if group == 'rules':
        return 'rule'
    if group != 'steps':
        raise ValueError("a recipe holds a step in gates, rules or steps, not in %s" % group)
    step = step if isinstance(step, dict) else {}
    return 'person' if step.get('born') == 'P' else 'ai' if step.get('prompt') else 'code'


DEFS['step'] = obj({
    'id': _law('fixed', word(r'^[a-z][a-z0-9]*\.[a-z0-9_.]+$', 60)),            # '<engine prefix>.<name>', unique across all engines
    'name': _law('free', say(160, 1)),
    'nature': _law('fixed', enum(*NATURES)),
    'born': _law('free', enum(*RUNGS)),
    'ceiling': _law('free', enum('C0', 'C1', 'C2')),
    'below': _law('free', enum('P', 'C0', 'C1')),
    'check': _law('fixed', text(60, 1)),                                        # a name in CHECKS[layer], SHARED_CHECKS, or the legacy CHECK
    'code': _law('free', text(60, 1)),
    'prompt': _law('free', text(60, 1)),
    'draft': _law('free', text(60, 1)),                                         # the answer when no model is there
    'out': _law('fixed', map_of(any_of(text(20), items(text(40), 12, 1)))),     # {key: 'str'|'list'|'bool'|'dict'} or {key: [enum values]}
    'answer': _law('fixed', text(40, 1)),                                       # the key whose value a table can answer (rung C2 as a table)
    'facts': _law('free', items(text(40), 12)),
    'stringency': _law('fixed', enum('high', 'low')),
    'only_if': _law('fixed', text(120, 1)),                                     # '<step id>.<key>' or '<step id>.<key>=<value>'
    'each': _law('fixed', text(60, 1)),                                         # fan out over the items another step listed
    'side_by_side': _law('free', integer(1, 16)),
    'files': _law('fixed', boolean()),
    'may_end': _law('fixed', boolean()),                                        # 'not needed' ends the run ok
    'by_hand': _law('fixed', text(600, 1)),                                     # the ask's text when the step falls to the person
    'tools': _law('free', items(enum(*MODEL_TOOLS))),
    'timeout_s': _law('free', number(0)),
    'or': _law('fixed', ANYTHING),                                              # the alternative answers a step may give (cannot)
}, required=('id', 'name', 'nature', 'born', 'check'), open=False)

# the row a run writes (R.step_rows): mode is slot for an ordinary step, gate for a gate's decision (Coordination's rules are
# written that way too, never as a mode of their own) and mark for the owner's mark. Open: every other key of STEP_ROW passes,
# and a mark row has run None
DEFS['step.row'] = obj({'id': text(40, 1), 'engine': text(80, 1), 'step': text(60, 1), 'mode': enum('slot', 'gate', 'mark'),
                        'rung': nullable(enum(*RUNGS)), 'status': text(20, 1), 'check': nullable(ref('check.verdict')),
                        'impl': nullable(ref('impl')), 'usd': number(0), 'calls': integer(0), 'started': text(40), 'ended': text(40)},
                       required=('id', 'engine', 'step', 'status'))

# an engine's start: what makes it run. $deliverable is the department's last artifact, whatever its kind (Adaptation's and
# Audit's start); engine_runtime.start_faults stays the law (a version trigger names what it is a version of, a post trigger
# needs a handler, a timer names its period, a blocker is a gate)
DEFS['engine.start'] = obj({
    'on': items(obj({'kind': enum('version', 'post', 'timer'), 'of': any_of(ref('name'), const('$deliverable')), 'checked': boolean(),
                     'every_s': number(1)}, required=('kind',)), min_items=1),
    'unless': items(text(60)),                                                  # gate ids
}, required=('on',), open=False)

# the department kind (L1, A3.5): a department made of a kind is an instance of it, not a child. required is inside line, which
# a type cannot say: template_checks.kind_faults reads the two fields together, as engine_runtime.validate does
DEFS['kind'] = obj({
    'line': items(ref('name')), 'required': items(ref('name')), 'artifacts': items(ref('name'), 32, 1),
    'goal': text(2000, 1), 'done': text(200), 'done_words': items(text(80), 2, 2),
    'rules': items(obj({'tag': enum(*RULE_TAGS), 'line': text(2000, 1)}, required=('tag', 'line'))),
    'say': text(200), 'use_case': text(400, 1), 'functions_template': word(r'^[a-z][a-z-]*$', 40),
}, required=('line', 'artifacts', 'goal', 'rules', 'use_case', 'functions_template'), open=False)

# the engine and workflow (L3, A3.5): a shipped Library template. engine.template (A1.7) is its born child, the same with a
# required made_by (the engine Adaptation made on the owner's stamp), and is not changed. Open: Setup's converse_instruction
# and clarification_questions pass
DEFS['engine.library'] = obj({
    'id': word(r'^engine/[a-z0-9][a-z0-9-]*$', 80), 'name': text(40, 1), 'version': integer(1), 'use_case': text(400, 1),
    'description': text(400), 'skills': items(text(200)), 'reads': ref('name'), 'writes': ref('name'),
    'start': ref('engine.start'), 'steps': items(ref('step')), 'kind': const('work'),
    'instruction': text(4000), 'needs': items(text(40)),
}, required=('id', 'name', 'version', 'use_case', 'kind', 'description', 'reads', 'writes', 'start', 'steps'))

# the artifact (L5, A3.5): the Default template and the ten shipped ones are the base and its children; a template an app
# brings is a child of kind app (which also names its screen and what it reads). Open: a key a later template adds passes
DEFS['artifact.template'] = obj({
    'id': word(r'^artifact/[a-z0-9-]+$', 60), 'name': ref('name'),
    'kind': enum('text', 'plan', 'pages', 'build', 'site', 'record', 'app'), 'use_case': text(400, 1), 'files': items(text(80), 16),
    'checks': items(text(60)), 'written_by': items(text(60)), 'counts_after': enum('filing', 'stamp'), 'put_back': boolean(),
    'operations': items(ref('name')), 'made_from': items(text(80)), 'version': integer(1),
    'screen': text(200), 'reads': items(ref('name')), 'form': text(60),         # an app template brings screen and reads; W2-CHECKS adds form
}, required=('id', 'name', 'kind', 'use_case', 'files', 'counts_after'))

# the user journey (L0, A3.6): a journey is a JSON file under journeys/ that conforms to DEFS['journey']. It carries everything
# the site's own data file lists (the tag, today, the earlier rows kept as was, the site's status words and Code column), and
# no row leaves it but by the owner's mark. A state is never in a definition: ROW_STATES and READ_STATES exist for the status
# document and the read model only, and the site's claim is kept as site_status and site_says so a drift can be seen, never to
# decide a state
JOURNEY_KINDS = ('person', 'system', 'function')
LANE_KINDS = ('person', 'root', 'function', 'engine')
STEP_ACTS = ('say', 'ask', 'tell', 'stamp', 'file', 'read', 'run', 'check', 'post', 'decide')
BIND_KINDS = ('act', 'step', 'event', 'api', 'ui', 'person')
OUTCOME_KINDS = ('tell', 'ask', 'file', 'hold', 'refuse', 'block', 'retry', 'none')
OUTCOME_VOICES = ('Identity', 'Root', 'Coordination', 'none')
SITE_STATUS = ('built', 'wanted', 'today', 'open', 'directed', 'partly', 'not_built', 'to_build', 'none')
DISPOSITIONS = ('keep', 'change', 'drop')
ROW_STATES = ('proven', 'partly', 'failing', 'unproven', 'wanted', 'dropped', 'fault')     # derived, never in a definition
READ_STATES = ROW_STATES + ('unknown',)                                                     # what the read model says before a run
JOURNEY_STATES = ROW_STATES + ('declared',)                                                 # a declared journey has no computed state
RULING_STATUS = ('RULED', 'OPEN', 'PARKED')
JOURNEY_ID = r'^(J[1-9][0-9]?|S[1-9]|U[1-9]|F(?:I|A|P|C|AU)[1-9])$'
SUB_ID = r'^J[1-9][0-9]?\.[a-z]$'
STEP_N = r'^([0-9]|[1-9][0-9])[a-e]?$'                       # 0a and 0b are the earlier rows of J2; 4a to 4e are J3's branches
EDGE_ID = r'^(J[1-9][0-9]?|F(?:I|A|P|C|AU)[1-9])\.[1-9][0-9]?$'
LANE_ID = r'^[a-z][a-z0-9_]{0,15}$'
BACKLOG_ID = r'^BL-[1-9][0-9]?[a-z]?$'                       # BL-2b
SAME_AS = r'^J[1-9][0-9]?/(step/[1-9][0-9]?[a-e]?|edge/J[1-9][0-9]?\.[1-9][0-9]?)$'
SYMBOL = r'^([A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_$][A-Za-z0-9_$]*$'              # a name, or module.name
TEST_REF = (r'^(js:[A-Za-z0-9_.-]+\.js#[A-Za-z0-9_.-]+|'
            r'[A-Za-z0-9_.-]+\.py::([A-Za-z_][A-Za-z0-9_]*::)?[A-Za-z_][A-Za-z0-9_]*)$')   # file.py::test, file.py::Class::test, js:file.js#W45
STEP_REF = r'^J[1-9][0-9]?:[1-9][0-9]?[a-e]?$'                                  # 'J2:6' = step 6 of J2
RULING_ID = r'^(S|Q|MK|D|A1|A2|A3)-?[A-Za-z0-9]{1,4}$'

DEFS['journey.lane'] = obj({'id': word(LANE_ID, 16), 'label': say(40, 1), 'kind': enum(*LANE_KINDS),
                            'function': nullable(enum(*FUNCTION_LAYERS))}, required=('id', 'label', 'kind'), open=False)
DEFS['journey.bind'] = obj({'kind': enum(*BIND_KINDS), 'src': enum(*ACTORS), 'act': enum(*ACTS), 'word': text(40), 'dst': enum(*ACTORS),
                            'id': text(60), 'action': text(60), 'method': enum('GET', 'POST'), 'path': text(120), 'symbol': text(80),
                            'what': text(200), 'optional': boolean()}, required=('kind',), open=False)
DEFS['journey.branch'] = obj({'label': say(40, 1), 'to': text(20, 1)}, required=('label', 'to'), open=False)
DEFS['journey.step'] = obj({'n': word(STEP_N, 3), 'lane': word(LANE_ID, 16), 'short': say(60, 1), 'text': say(1500, 1),
                            'site_function': say(200), 'site_status': enum(*SITE_STATUS), 'site_says': say(120), 'site_code': say(600),
                            'act': enum(*STEP_ACTS), 'binds': items(ref('journey.bind'), 8), 'code': items(word(SYMBOL, 80), 12),
                            'tests': items(word(TEST_REF, 200), 12), 'branches': items(ref('journey.branch'), 6),
                            'child': nullable(word(JOURNEY_ID, 6)), 'read': boolean(), 'backlog': nullable(word(BACKLOG_ID, 6)),
                            'same_as': nullable(word(SAME_AS, 24))},
                           required=('n', 'lane', 'short', 'text'), open=False)
DEFS['journey.outcome'] = obj({'kind': enum(*OUTCOME_KINDS), 'voice': enum(*OUTCOME_VOICES), 'golden': nullable(text(200))},
                              required=('kind',), open=False)
DEFS['journey.edge'] = obj({'id': word(EDGE_ID, 8), 'at': text(20, 1), 'short': say(60, 1), 'trigger': say(400, 1),
                            'site': obj({'status': enum(*SITE_STATUS), 'text': say(1500)}, required=('status',), open=False),
                            'code_does': say(1500), 'outcome': ref('journey.outcome'), 'binds': items(ref('journey.bind'), 8),
                            'code': items(word(SYMBOL, 80), 12), 'tests': items(word(TEST_REF, 200), 12),
                            'backlog': nullable(word(BACKLOG_ID, 6)), 'disposition': nullable(enum(*DISPOSITIONS)),
                            'rulings': items(word(RULING_ID, 8), 8), 'read': boolean(), 'truncated': boolean(),
                            'reword': nullable(say(700)), 'same_as': nullable(word(SAME_AS, 24))},
                           required=('id', 'at', 'short', 'trigger', 'site'), open=False)
DEFS['journey.sub'] = obj({'id': word(SUB_ID, 6), 'title': say(80, 1), 'owner': say(80), 'step': word(STEP_N, 3), 'text': say(800),
                           'drawn': say(120)}, required=('id', 'title', 'step'), open=False)
DEFS['journey.ruling'] = obj({'id': word(RULING_ID, 8), 'status': enum(*RULING_STATUS), 'date': nullable(iso()), 'text': say(700)},
                             required=('id', 'status', 'text'), open=False)
DEFS['journey.quote'] = obj({'date': nullable(iso()), 'on': text(20), 'text': say(1500, 1)}, required=('text',), open=False)
DEFS['journey.scenario'] = obj({'id': text(40, 1), 'lane': text(40, 1), 'test': word(TEST_REF, 200), 'walks': items(word(STEP_N, 3), 20),
                                'says': say(300)}, required=('id', 'lane', 'test'), open=False)
DEFS['journey.backlog'] = obj({'id': word(BACKLOG_ID, 6), 'row': text(20, 1), 'smallest': say(700, 1), 'decision': text(40),
                               'package': text(160, 1)}, required=('id', 'row', 'smallest', 'package'), open=False)
DEFS['journey.direction'] = obj({'id': text(8, 1), 'direction': say(500, 1), 'built': say(800), 'gap': say(500),
                                 'mark': nullable(enum(*DISPOSITIONS))}, required=('id', 'direction'), open=False)
DEFS['journey.build_row'] = obj({'id': text(8, 1), 'when': enum('v1', 'later'), 'change': say(800, 1), 'where': say(300),
                                 'owner': text(40), 'size': enum('S', 'M', 'L'), 'tests': items(word(TEST_REF, 200), 6),
                                 'backlog': nullable(word(BACKLOG_ID, 6))}, required=('id', 'change'), open=False)
# the site's earlier rows of a journey (J2's thirteen steps and twenty edges): history, kept in the site's words, with no state
DEFS['journey.was'] = obj({'title': say(120, 1), 'lanes': items(word(LANE_ID, 16), 10), 'steps': items(ref('journey.step'), 24),
                           'edges': items(ref('journey.edge'), 30)}, required=('title', 'steps', 'edges'), open=False)
DEFS['journey'] = obj({'schema_version': integer(1), 'id': word(JOURNEY_ID, 6), 'title': say(120, 1), 'kind': enum(*JOURNEY_KINDS),
                       'inside': nullable(word(JOURNEY_ID, 6)), 'bound_to': nullable(enum(*FUNCTION_LAYERS)),
                       'serves': items(word(STEP_REF, 8), 6), 'site_serves': nullable(say(40)), 'declared': boolean(),
                       'goal': say(300, 1), 'lead': say(1500), 'ends_when': say(400), 'flag': nullable(text(40)), 'tag': say(200),
                       'today': obj({'text': say(1500, 1), 'sources': text(200)}, required=('text',), open=False), 'was': ref('journey.was'),
                       'site': obj({'page': text(200), 'data_version': text(8), 'as_of': iso()}, open=False),
                       'helper': obj({'site': text(20), 'screen': text(20), 'code': text(20)}, open=False),
                       'lanes': items(ref('journey.lane'), 10), 'steps': items(ref('journey.step'), 24),
                       'edges': items(ref('journey.edge'), 24), 'sub': items(ref('journey.sub'), 10),
                       'children': items(word(JOURNEY_ID, 6), 10), 'directions': items(ref('journey.direction'), 12),
                       'build_rows': items(ref('journey.build_row'), 12), 'rulings': items(ref('journey.ruling'), 24),
                       'decisions': items(text(12), 24), 'quotes': items(ref('journey.quote'), 12),
                       'scenarios': items(ref('journey.scenario'), 12), 'invariants': items(text(60), 8),
                       'backlog': items(ref('journey.backlog'), 24), 'site_ids': items(text(32, 1), 100, unique=True)},
                      required=('schema_version', 'id', 'title', 'kind', 'goal', 'lanes', 'steps', 'edges', 'site_ids'), open=False)
DEFS['journey.file'] = obj({'journeys': items(ref('journey'), 8, 1)}, required=('journeys',), open=False)   # a function's file holds a list

# a row's computed state and a journey's, as the status document and the read model say them: one document per journey
# (journeys/status/<id>.json) with the hash of its own definition, so two packages never conflict on one file
DEFS['journey.row_status'] = obj({'state': enum(*(READ_STATES + ('declared',))), 'proven_by': items(text(200)), 'failing': items(text(200)),
                                  'site': nullable(enum(*SITE_STATUS)), 'drift': boolean()}, required=('state',), open=False)
DEFS['journey.status'] = obj({'schema_version': integer(1), 'id': word(JOURNEY_ID, 6), 'definitions_sha': text(64, 1),
                              'state': enum(*(JOURNEY_STATES + ('unknown',))), 'counts': map_of(integer(0)),
                              'tests': map_of(enum('passed', 'failed', 'missing')), 'rows': map_of(ref('journey.row_status')),
                              'drift': items(obj({'row': text(40, 1), 'site': enum(*SITE_STATUS), 'state': enum(*(READ_STATES + ('declared',)))},
                                                 required=('row', 'site', 'state'), open=False))},
                             required=('schema_version', 'id', 'definitions_sha', 'state', 'counts', 'tests', 'rows'), open=False)

#: the ledger's actions: the dotted words j2_runtime writes on a row of the cycle's ledger (an action of note(...) or of the
#: activity feed, and the reason code check.failed that run.failed and workflow.blocked carry). The interface names them,
#: j2_runtime owns them (A1.22): a journey's event bind names one of these, and a test keeps the list equal to j2_runtime's
#: literals, so a package that adds a ledger action adds it here in the same commit
LEDGER_ACTIONS = ('proposal.requested', 'proposal.created', 'proposal.granted', 'proposal.countered', 'proposal.refused',
                  'proposal.accepted', 'workflow.validated', 'workflow.registered', 'workflow.blocked', 'timetable.written',
                  'envelope.granted', 'envelope.held', 'slot.assigned', 'run.started', 'run.completed', 'run.failed',
                  'artifact.filed', 'audit.finding_filed', 'audit.not_read', 'identity.assessed', 'identity.questioned',
                  'identity.ruled', 'conflict.raised', 'ask.created', 'ask.answered', 'goal.reached', 'cycle.stopped',
                  'cycle.resumed', 'cycle.reopened', 'goal.revised', 'check.failed')
#: Identity's five recognitions of a request (task, query, directive, feedback, new idea): a verdict of its covering, not the
#: user journeys. The key `journeys` of engine_defs/website.json and the check journey_is_known name them and are not renamed
RECOGNITIONS = VERDICTS['identity']['journey']

# the levels (A3.1) as data, so the generated JSON Schema, describe() and a screen can read them: each level's name, the base
# class that is its template (a DEFS name, or a table of this module), where its children are, the one sentence a child keeps
# and the ids of the rules that hold it (A3.1 lists each rule with its case and its failing example). L2's base is the layer
# interface extended by the function template (FUNCTION_TEMPLATE, below)
TEMPLATE_LEVELS = (
    {'level': 'L0', 'name': 'user journey', 'base': 'journey', 'children': 'journeys/*.json',
     'keeps': 'A journey may add steps, edges, sub-journeys, tests, rulings and quotes. It may not drop, move or re-word a row the '
              "site lists (a row leaves only by the owner's mark drop), and it carries no status, which is computed. Every row either "
              'binds to code and passing tests, or says it is wanted and names its smallest behaviour.',
     'rules': ('JC-1', 'JC-2', 'JC-3', 'JC-4', 'JC-5', 'JC-6', 'JC-7', 'JC-8', 'JC-9', 'JC-10', 'JC-11', 'JC-12')},
    {'level': 'L1', 'name': 'department kind', 'base': 'kind', 'children': 'engine_defs/website.json kinds',
     'keeps': 'A kind names its line of work engines, the ones required inside the line, its artifacts, a goal, rules (each tagged), '
              'a use case, and a functions_template that every function has.',
     'rules': ('K-1', 'K-2')},
    {'level': 'L2', 'name': 'function', 'base': 'FUNCTION_TEMPLATE', 'children': 'layers/<layer>/v<N>.py; function-templates/<function>/*.json',
     'keeps': "A version places the interface's role phrase, its 'is not' and 'never' lines and the working agreement (its layout "
              'holds all eight inputs), supplies every typed word within its limits and uses no banned word. A use-case template adds '
              "floor lines and keeps the Default's checks.",
     'rules': ('FT-1', 'FT-2', 'FT-3', 'FT-4', 'FT-5', 'FT-6', 'FT-7', 'FT-8', 'FT-9', 'FT-10')},
    {'level': 'L3', 'name': 'engine and workflow', 'base': 'engine.library', 'children': 'engine-templates/*.json; the _library of born templates',
     'keeps': 'A template names an id, a name, a use case, what it reads and writes (artifacts that have templates), a start (trigger '
              'kinds that exist, blockers that are gates) and steps that conform to the step template. A born template adds made_by.',
     'rules': ('E-1', 'E-2', 'E-3', 'E-4')},
    {'level': 'L4', 'name': 'step', 'base': 'step', 'children': 'layers/<layer>/v<N>.json; engine-templates/*.json',
     'keeps': 'A step has an identity (id, name), a nature, a born rung, a registered check and a body: code, or a prompt with its '
              'plain draft and the shape of its answer, or by_hand. A unit starts and ends with a step by code. Ids are unique. Only the '
              'free fields change between versions.',
     'rules': ('ST-1', 'ST-2', 'ST-3', 'ST-4', 'ST-5', 'ST-6', 'ST-7', 'ST-8', 'ST-9')},
    {'level': 'L5', 'name': 'artifact', 'base': 'artifact.template', 'children': 'artifact-templates/*.json',
     'keeps': 'A template names an id, a name, a kind, a use case, files, checks that exist in artifacts.CHECKS, counts_after (filing '
              'or stamp) and operations that are engines.',
     'rules': ('AR-1', 'AR-2')},
    {'level': 'L6', 'name': 'ask', 'base': 'identity.ask', 'children': 'ASK_FORMS: one form for each kind of ask',
     'keeps': 'An ask has a kind from the list, at most three options each of a known kind, is filed only by Identity to the owner, '
              'and has a status from the list.',
     'rules': ('AS-1', 'AS-2')},
)

#: the form of each kind of ask (L6, A3.5): who files it (always Identity: only Identity speaks to the owner), the kinds of way
#: out its writers attach to it (OPTION_KINDS; an ask carries at most OPTIONS_MAX of them, and an ask whose options are empty is
#: stamped yes or no), and the lead it says first, in the writer's own words (None for the rest). Checked against the writers
#: (website_dept.options_ask, _put_ask, decide_ask; engine_runtime._blocked; adaptation's cannot_options): widened to what they
#: attach, never narrowed. blocked is the plan's card (words, leave, stop); conflict also carries root_setup, which adaptation's
#: cannot_options attaches to the conflict it files, and raise, which W2-IDENTITY's options ask adds (M5.4); envelope is M5.4's
_ASK_OPTIONS = {'blocked': ('words', 'leave', 'stop'), 'conflict': ('words', 'root_setup', 'leave', 'stop', 'raise'),
                'envelope': ('raise', 'leave', 'stop')}
_ASK_LEADS = {'publish': 'Publish: go live for the first time', 'rule': 'A rule, as understood',
              'request': 'Your words reach outside the site'}
ASK_FORMS = {kind: {'by': 'identity', 'options': _ASK_OPTIONS.get(kind, ()), 'lead': _ASK_LEADS.get(kind)} for kind in ASK_KINDS}

# the function template (L2, A3.4.2). Each part of a function is one of three things. A constant is a boundary no field changes:
# what the function is not, what it never does, who it hands on to, and the working agreement all five keep; a tighter boundary
# is a rule, never a field, and an owner cannot loosen one (approvals only tighten, S-08). A word is behaviour, typed in the
# `goal` group of S.PROMPTS (A3-FUNCTIONS adds the parts goal.done and goal.role_*, and the layout of the compiled role block).
# What is derived is written once, in the tables above, so it cannot drift. These constants are addressed to the agent: the owner
# is "the owner", never "You", and where a word sits beside an answer shape it is the contract's (accept, counter, reject; go,
# ask, refuse); the one thing the owner reads, goal.done, keeps the screen's list of banned words
ROLE_INPUTS = ('agreement', 'is', 'is_not', 'may', 'never', 'procedure', 'patterns', 'hands_on')   # the inputs of goal.role_block
ROLE_BLOCK_MAX = 3600                              # characters of the compiled block
TEMPLATE_BANNED = r"\b(charters?|ceo|requesters?|grant(?:s|ed)?|counter(?:s|ed)?|refus\w*|internal systems?)\b"     # re.I; the screen's words
TEMPLATE_BANNED_AGENT = r"\b(charters?|ceo|requesters?|internal systems?)\b"                                       # re.I; the words only the agent reads
TEMPLATE_NEVER_SAY = {'priority': r"order|what runs next"}       # re.I; a substring, as test_priority_never_orders has it (S-05)

#: what team.md's working rules say that the interface cannot: the base text every function keeps. Its first line is true of
#: Identity too, which is the one function that speaks to the owner
DEPARTMENT_AGREEMENT = (
    'Only Identity speaks to the owner; any other function that needs something from the owner tells Identity.',
    "The department's goal and its done-when are the reference for every decision you make.",
    'Disagree with a reason tied to the goal, the limits or the rules, and move when someone gives a better reason.',
    'If two functions cannot settle a disagreement in four exchanges, it goes to Identity with both positions.',
    (
        "A fact only the owner knows is Identity's question to the owner; until it is answered the item is to be "
        'confirmed, and it is not met.'
    ),
    (
        'The work is finished only when Audit has read every done-when item and none is unmet or to be confirmed; a limit '
        'reached ends in an ask to the owner through Identity, never in silence.'
    ),
)

#: per layer (the five functions and Root): role (a label), is_not, never (the lines no version drops), hands_on (who it hands
#: on to, FT-10), in_card (whether the role block is sent in its card; Root's Setup prompts use no card, so its template is
#: interface-only) and, for Adaptation, reserved (the site's parts that are placeholders: recorded, not built)
FUNCTION_TEMPLATE = {
    'identity': {
        'role': 'keeps the goal, the done-when and the rules, and closes conflicts',
        'is_not': (
            'It does not design workflows, give out limits, schedule work, do the work or read results. It rules only '
            'when a proposal touches a rule, when Priority and Adaptation cannot agree, when Audit reports something that '
            'matters, or when the department may be done.'
        ),
        'never': (
            'invent a new goal or a new rule',
            'choose tools or the steps of the work',
            'raise a limit',
            'say which workflow runs first',
            'rewrite a proposal to make it acceptable',
            'ask the owner only because functions disagree',
            'make anything itself: the maker is an engine',
            'loosen a rule: approvals only tighten',
        ),
        'hands_on': (
            'Adaptation: a request for a line, and the next thing to correct. Coordination: verdicts on gates. The owner: '
            'questions, tells and asks, since Identity is the only function that speaks to the owner.'
        ),
        'in_card': True,
    },
    'adaptation': {
        'role': 'senses the gap to the goal and proposes how to close it',
        'is_not': (
            'It designs; it does not approve its own proposal. Priority gives the limits, Identity holds the rules, '
            'Coordination keeps the order and Audit judges the results.'
        ),
        'never': (
            'give itself resources',
            "say a plan passed Root's check",
            'schedule a run',
            'say its own result is right',
            'ask the owner directly: only Identity does',
            'hide a capability or a permission a plan depends on',
            'widen the scope to make a proposal look more valuable',
            'apply a change itself: every proposal passes Priority first',
        ),
        'hands_on': (
            'Priority: every proposal and every round. Identity: conflicts, and a round Priority accepted, to file. Root: '
            'the line Priority accepted, for its check.'
        ),
        'in_card': True,
        'reserved': ('crystallize', 'grow', 'learn', 'compass'),     # the site's parts that are placeholders: recorded, not built
    },
    'priority': {
        'role': 'the budget bargain and the limit of each engine',
        'is_not': (
            'It does not choose strategy, design workflows, decide who goes first, judge the quality of content or read '
            'the rules. A proposal can be attractive and still not affordable, or cheap and still beside the goal; '
            'whether it fits the goal is for Identity and Adaptation.'
        ),
        'never': (
            'say which accepted workflow runs first',
            'reject a proposal because it dislikes a method that fits the limit',
            'give a limit that is not declared, or no limit at all',
            "change the department's goal",
            'ask the owner directly: only Identity does',
            'turn a question of money into a question of policy',
            'start a run',
        ),
        'hands_on': (
            "Adaptation: accept, counter or reject, with the price. Identity: through Adaptation's conflict, when a limit "
            'is hit.'
        ),
        'in_card': True,
    },
    'coordination': {
        'role': 'order, dependencies, hand-offs and keeping work apart',
        'is_not': 'It does not give limits, decide the goal, design workflows or judge the quality of results.',
        'never': (
            'raise a limit',
            'decide that an expensive workflow is not worth it',
            'settle a question of rules',
            'change the steps of a workflow',
            'say a result is right',
            'ask the owner directly: only Identity does',
            'start a run: the engine starts itself in its slot',
        ),
        'hands_on': 'Identity: alarms, lost requests and verdict asks. Priority: verdict asks.',
        'in_card': True,
    },
    'audit': {
        'role': 'an independent check on the evidence',
        'is_not': (
            'It does not design the workflow, repair the result, give limits, schedule rework or decide policy. Its job '
            'is to make a difference visible, with the evidence.'
        ),
        'never': (
            'touch a workflow or a version',
            "approve a proposed workflow because it can picture auditing its output: Root's check registers it",
            'turn a check into a score',
        ),
        'hands_on': 'Identity only: readings and findings.',
        'in_card': True,
    },
    'root': {
        'role': 'makes departments and checks plans',
        'is_not': (
            "It never creates or starts an engine: engines come from Adaptation. It does not do a department's work or "
            'speak for its functions.'
        ),
        'never': (
            'create or start an engine: engines come from Adaptation',
            'register a plan that does not meet the standards',
            "let a department's rules loosen its own",
        ),
        'hands_on': (
            "Identity: the owner's words for a department, and a plan it could not register. Coordination and Priority: a "
            'registered plan.'
        ),
        'in_card': False,                  # Root's Setup prompts use no card: its template is interface-only
    },
}

#: every part of a function the site lists or the prototype's role file has, and its home: (part, the site's field when it
#: has a literal name, else None; kind, 'word' (behaviour, typed in S.PROMPTS), 'constant' (here), 'derived' (written once in
#: another table) or 'version' (the layer's recipe); home). A word's home is (group, part) in S.PROMPTS[layer]; a constant's
#: is (table, key) here; a derived part's is the table of this module, or, in lower case, the folder that holds it
TEMPLATE_PARTS = (
    ('goal', 'goal', 'word', ('goal', 'does')),
    ('skills', None, 'word', ('goal', 'skills')),
    ('done', 'done', 'word', ('goal', 'done')),
    ('role', None, 'constant', ('FUNCTION_TEMPLATE', 'role')),
    ('is', None, 'word', ('goal', 'role_is')),
    ('is_not', None, 'constant', ('FUNCTION_TEMPLATE', 'is_not')),
    ('may', 'choices', 'word', ('goal', 'role_may')),
    ('never', 'keeps', 'constant', ('FUNCTION_TEMPLATE', 'never')),
    ('procedure', None, 'word', ('goal', 'role_procedure')),
    ('patterns', None, 'word', ('goal', 'role_patterns')),
    ('hands_on', 'hands_to', 'constant', ('FUNCTION_TEMPLATE', 'hands_on')),
    ('agreement', None, 'constant', ('DEPARTMENT_AGREEMENT', None)),
    ('hears', 'hears', 'derived', ('HEARS', None)),
    ('writes', 'writes', 'derived', ('SENDS', None)),
    ('checks', 'checks', 'derived', ('CHECKS', None)),
    ('envelope', 'envelope', 'derived', ('SETTINGS', 'envelope')),
    ('settings', 'settings', 'derived', ('SETTINGS', None)),
    ('formats', None, 'derived', ('RECORDS', None)),
    ('recipe', None, 'version', ('LAYERS', 'recipe')),
    ('journeys', None, 'derived', ('journeys', 'functions')),
)


# ---- reading the tables ----------------------------------------------------------------------------------------------
def _layer(name):
    """A layer's name from its name or its title ('identity', 'Identity', 'Setup' -> 'root'); None for any other."""
    if name in LAYER_NAMES:
        return name
    return ENGINE_LAYER.get(name) or {v: k for k, v in TITLE.items()}.get(name)


def edges():
    """Who may post what to whom, {src: {act: [dst, ...]}}, from SENDS: equal to engine_defs' edges for the actors it
    names, in their order."""
    out = {}
    for actor in ACTORS:
        for row in SENDS.get(actor) or []:
            dsts = out.setdefault(actor, {}).setdefault(row['act'], [])
            for dst in row['to']:
                if dst not in dsts:
                    dsts.append(dst)
    return out


def hears(layer):
    return [dict(r) for r in HEARS.get(_layer(layer) or layer, [])]


def sends(layer):
    actor = TITLE.get(_layer(layer) or '', layer)
    return [dict(r) for r in SENDS.get(actor, [])]


def calls():
    return CALLS


def owner_of_key(key):
    return (DEPARTMENT_KEYS.get(key) or (None,))[0]


# ---- public functions (A1.4) -----------------------------------------------------------------------------------------
def _same_json(a, b):
    return _canon(a) == _canon(b)


def _available():
    """The implementations the registry can find, {layer: [impl id]}: layers.available() once the registry has it
    (W1-CORE), else every layers/<layer>/v<N>.py on disk; with no layer package at all, the default pins, which are
    what every department runs until there is one."""
    if not (HERE / 'layers').is_dir():
        return {layer: [impl] for layer, impl in DEFAULT_PINS.items()}
    try:
        import layers
        if callable(getattr(layers, 'available', None)):
            return layers.available()
    except ImportError:
        pass
    out = {}
    for layer in LAYER_NAMES:
        for p in sorted((HERE / 'layers' / layer).glob('v[1-9]*.py')):
            if re.fullmatch(r'v[1-9][0-9]*', p.stem):
                out.setdefault(layer, []).append('%s/%s' % (layer, p.stem))
    return out


def _kinds():
    import website_dept as W                       # lazy: website_dept imports this module
    return W.KINDS


def _workflow_schema():
    """Root's standards in code (workflow_schema.py, W1-ROOT), or None until that module is on main."""
    try:
        import workflow_schema
    except ModuleNotFoundError as exc:
        if exc.name != 'workflow_schema':
            raise
        return None
    return workflow_schema


def _write_ctx(ref):
    """What the 'write' stage reads beside the record: Coordination's line and the engines the owner added."""
    if not ref:
        return {}
    try:
        import engine_runtime as R
        t = R.coordination(ref)
        return {'line': list(t.get('line') or []), 'grown': list(t.get('grown') or [])}
    except Exception:  # noqa: BLE001 -- a context it cannot read is an empty one; the standards say what they lack
        return {}


def check_department(d, ref=None, before=None, by=None):
    """A department record about to be saved, checked against the interface (A1.6, A1.20): only the keys whose value
    changed against `before` (the stored record), so one legacy fault never blocks a later save; the semantic rules of
    a key run only when it changed. Stamps schema_version. A fault on a NEVER_REFUSE key (the owner's Stop) is a row
    only; with `by`, a changed key another layer owns is a row (OWNERSHIP_MODE warn). Returns the record."""
    if not isinstance(d, dict):
        report('department', ['$: is not an object'], ref=ref, owner='root')
        return d
    before = before if isinstance(before, dict) else {}
    d['schema_version'] = SCHEMA_VERSION
    changed = [k for k in d if k not in before or not _same_json(before[k], d[k])]
    hard, soft = [], []
    for k in ('kind', 'ref', 'name'):
        if k not in d:
            hard.append('$.%s: is missing' % k)
    for k in changed:
        sink = soft if k in NEVER_REFUSE else hard
        if k not in DEPARTMENT_KEYS:
            if k not in LEGACY_KEYS:
                sink.append('$.%s: is not a field here' % k)
            continue
        if k == 'workflows' and isinstance(d[k], list):
            continue                                  # entry by entry, below
        sink.extend(faults(DEFS[DEPARTMENT_KEYS[k][1]], d[k], '$.' + k))
    if 'workflows' in changed and isinstance(d.get('workflows'), list):
        old = before.get('workflows') if isinstance(before.get('workflows'), list) else []
        fresh = [i for i, w in enumerate(d['workflows']) if i >= len(old) or not _same_json(old[i], w)]
        for i in fresh:
            hard.extend(faults(DEFS['workflow.registration'], d['workflows'][i], '$.workflows[%d]' % i))
        last = len(d['workflows']) - 1
        if last in fresh and isinstance(d['workflows'][last], dict):
            reg = d['workflows'][last]
            ctx = _write_ctx(ref) if _workflow_schema() is not None else {}
            for row in validate_workflow(as_workflow(reg.get('engines') or [], reg.get('source'), d), 'write', d, ctx):
                if not row.get('passed'):
                    hard.append('$.workflows[%d]: %s: %s' % (last, row.get('check'), row.get('why')))
    # the semantic rules, each only when one of its keys changed
    if 'kind' in changed and d.get('kind') not in _kinds():
        hard.append('$.kind: %s is no kind in the definitions' % d.get('kind'))
    if ('done_items' in changed or 'to_be_confirmed' in changed) and isinstance(d.get('done_items'), list):
        ids = [i.get('id') for i in d['done_items'] if isinstance(i, dict)]
        if ids != ['D%d' % (n + 1) for n in range(len(ids))]:
            hard.append('$.done_items: the ids do not run D1 to D%d in order' % len(ids))
        for c in d.get('to_be_confirmed') or []:
            if isinstance(c, dict) and c.get('item') not in ids:
                hard.append('$.to_be_confirmed: %s names no done-when item' % c.get('item'))
    if 'layers' in changed and isinstance(d.get('layers'), dict):
        found = _available()
        for layer, impl in d['layers'].items():
            if impl not in found.get(layer, []):
                hard.append('$.layers.%s: %s is no implementation the registry can find' % (layer, impl))
    own = []
    who = _layer(by) if by else None
    if by:
        for k in changed:
            owner = owner_of_key(k)
            if owner and owner != who and k != 'schema_version':     # the stamp is the interface's own, whoever saves
                own.append("$.%s: is %s's, and %s wrote it" % (k, TITLE[owner], TITLE.get(who, by)))
    report('department', soft, ref=ref, owner='root', never_refuse=True)
    report('department', own, ref=ref, owner=who or 'root', never_refuse=OWNERSHIP_MODE != 'refuse')
    report('department', hard, ref=ref, owner='root')
    return d


def validate_record(layer, kind, value):
    """`value` as the record `kind` of `layer` (RECORDS); an unknown pair is a fault."""
    r = (RECORDS.get(layer) or {}).get(kind)
    if not r:
        return ['$: %s keeps no record named %s' % (TITLE.get(layer, layer), kind)]
    return validate(r['def'], value)


def check_record(layer, kind, value, ref=None):
    r = (RECORDS.get(layer) or {}).get(kind)
    report(r['def'] if r else '%s.%s' % (layer, kind), validate_record(layer, kind, value), ref=ref, owner=layer if layer in LAYER_NAMES else None)
    return value


def _actor(name):
    """The actor a sender or a receiver is: Owner, Root or a function by its title; any other name is a work engine."""
    name = str(name or '')
    return name if name in ACTORS and name != 'Engine' else 'Engine'


def validate_act(src, dst, act, payload):
    """One post against the interface (A1.13): the sender maps to an actor and every destination is in edges(); when
    the actor's rows for that act list words, the payload's word is one of them (an (any) row takes any); and the
    payload fits the row's definition. Priority's words never order."""
    if act not in ACTS:
        return ['$: %r is not an act' % (act,)]
    a = _actor(src)
    dsts = [dst] if isinstance(dst, str) else list(dst or [])
    out = [] if dsts else ['$: the post names nobody']
    allowed = (edges().get(a) or {}).get(act)
    if allowed is None:
        return out + ['$: %s sends no %s' % (a, act)]
    for x in dsts:
        if _actor(x) not in allowed:
            out.append('$: %s may not %s %s' % (a, act, x))
    rows = [r for r in SENDS.get(a) or [] if r['act'] == act and all(_actor(x) in r['to'] for x in dsts)]
    if not rows:
        return out or ['$: no row says %s may %s %s' % (a, act, ', '.join(map(str, dsts)))]
    if not isinstance(payload, dict):
        return out + ['$: the payload is not an object']
    w = payload.get('word')
    row = next((r for r in rows if r['words'] != ANY and w in r['words']), None) or next((r for r in rows if r['words'] == ANY), None)
    if row is None:
        words = sorted({x for r in rows for x in r['words']})
        return out + ['$.word: %s does not %s with the word %r; its words are %s' % (a, act, w, ', '.join(words))]
    if a == 'Priority' and 'order' in str(w or '').lower():
        out.append('$.word: Priority prices and holds; it never orders')
    return out + faults(DEFS[row['payload']], payload)


def check_act(src, dst, act, payload, ref=None):
    """validate_act's faults through report(): in warn mode a bad post is a row and goes through; in refuse mode it
    raises. post() calls it after may_post and before the append."""
    got = validate_act(src, dst, act, payload)
    if got:
        report('act', ['%s %s to %s: %s' % (src, act, ', '.join(dst) if isinstance(dst, (list, tuple)) else dst, f) for f in got],
               ref=ref, owner=_layer(src) or 'identity')
    return payload


def as_workflow(engines, source, dept=None):
    """Today's engine lists (names, or the dicts a proposal carries: name, does, reads, writes, internet, covers) as a
    DEFS['workflow'] value (A1.14): reads and writes looked up in the definitions for a name, the deliverable the last
    engine's writes, and each engine's covers inverted into covers. When no engine names any covers, every done-when
    item is the last engine's and covers_by is 'default', so a line made before M5.1 still has its items covered."""
    import engine_runtime as R                     # lazy: the definitions are the runtime's
    lib = R.defs()['engines']
    rows = []
    for e in engines or []:
        mine = e if isinstance(e, dict) else {'name': e}
        name = mine.get('name')
        base = lib.get(name) or {}
        row = {'name': name, 'reads': mine.get('reads') or base.get('reads'), 'writes': mine.get('writes') or base.get('writes')}
        does = mine.get('does') or base.get('description')
        if does:
            row['does'] = does
        if mine.get('internet') is not None:
            row['internet'] = bool(mine['internet'])
        if isinstance(mine.get('covers'), list):
            row['covers'] = list(mine['covers'])
        if source in SOURCES:
            row['made_by'] = source
        rows.append({k: v for k, v in row.items() if v is not None})
    covers = {}
    for row in rows:
        for item in row.get('covers') or []:
            covers.setdefault(item, []).append(row['name'])
    by = 'adaptation'
    if not covers and rows:
        by = 'default'
        for i in (dept or {}).get('done_items') or []:
            if isinstance(i, dict) and i.get('id'):
                covers[i['id']] = [rows[-1]['name']]
    wf = {'schema_version': SCHEMA_VERSION, 'source': source, 'engines': rows,
          'deliverable': rows[-1].get('writes') if rows else None, 'covers': covers, 'covers_by': by}
    if (dept or {}).get('kind'):
        wf['kind'] = dept['kind']
    return wf


def validate_workflow(wf, stage='shape', dept=None, ctx=None):
    """[{check, passed, why}] (A1.14): the shape row first (the workflow fits DEFS['workflow']), then, at a stage, the rows
    of Root's standards that apply to it, in WORKFLOW_STANDARDS order, from workflow_schema.run (W1-ROOT); until that
    module is on main, the shape row only."""
    f = validate('workflow', wf)
    rows = [{'check': 'workflow_meets_standards', 'passed': not f,
             'why': '; '.join(f[:3]) if f else 'the workflow fits the workflow schema'}]
    mod = _workflow_schema()
    if mod is not None and stage != 'shape':
        rows += [dict(r) for r in mod.run(wf, stage, dept, ctx or {}) or []]
    return rows


def workflow_faults(wf, stage='shape', dept=None, ctx=None):
    return ['%s: %s' % (r['check'], r['why']) for r in validate_workflow(wf, stage, dept, ctx) if not r['passed']]


def validate_field(layer, group, part, field, value):  # noqa: F811 -- A1.4 names the argument field
    """An owner's value for one prompt field (A1.16): the field's type, no '{{' or '}}', and no 'Return ONLY'."""
    p = ((PROMPTS.get(layer) or {}).get(group) or {}).get(part)
    if p is None:
        return ['$: %s has no part %s.%s' % (TITLE.get(layer, layer), group, part)]
    name = p['fields'].get(field)
    if name is None:
        return ['$: %s.%s has no field %s the owner may change' % (group, part, field)]
    return validate(name, value)


def validate_instructions(doc):
    """{ref}/instructions.json (A1.16): its shape, and every value as its field types it."""
    out = validate('instructions', doc)
    if out or not isinstance(doc, dict):
        return out
    for layer, groups in (doc.get('values') or {}).items():
        for group, parts in (groups or {}).items():
            for part, fields in (parts or {}).items():
                for name, entry in (fields or {}).items():
                    out += ['$.values.%s.%s.%s.%s%s' % (layer, group, part, name, f[1:] if f.startswith('$') else ': ' + f)
                            for f in validate_field(layer, group, part, name, (entry or {}).get('value'))]
    return out


def validate_view(layer, view):
    """A pane's read model against VIEWS[layer] (A1.17); layer may be 'engine_card'."""
    name = VIEWS.get(layer) or VIEWS.get(_layer(layer) or '')
    if name is None:
        return ['$: %s has no view' % layer]
    return validate(name, view)


def first_input(kind):
    """The kind's first artifact: the Brief, or the Request for Root; None for a kind the definitions lack."""
    arts = ((_kinds().get(kind) or {}).get('artifacts') or [None])
    return arts[0]


def deliverable(d):
    """What the department's work leads to: the last engine's writes in its newest registered workflow (names looked
    up in the definitions); with no registration, the kind's last artifact when its kind has a line (website Live site,
    default Result); else None."""
    d = d or {}
    wf = d.get('workflows') or []
    names = (wf[-1] or {}).get('engines') if wf and isinstance(wf[-1], dict) else None
    if names:
        import engine_runtime as R
        return (R.defs()['engines'].get(names[-1]) or {}).get('writes')
    k = _kinds().get(d.get('kind')) or {}
    return (k.get('artifacts') or [None])[-1] if k.get('line') else None


def describe():
    """The whole interface as JSON: what GET /layers serves and the README points at (schemas/layers/interface.v1.json)."""
    out = {
        'schema_version': SCHEMA_VERSION, 'layer_names': LAYER_NAMES, 'title': TITLE, 'engine_layer': ENGINE_LAYER,
        'actors': ACTORS, 'acts': ACTS, 'default_pins': DEFAULT_PINS, 'per_department': PER_DEPARTMENT,
        'constants': {'impl_re': IMPL_RE, 'item_re': ITEM_RE, 'finding_re': FINDING_RE, 'name_re': NAME_RE, 'bounds': BOUNDS,
                      'chain_limit': CHAIN_LIMIT, 'repairs': REPAIRS, 'options_max': OPTIONS_MAX, 'done_items_max': DONE_ITEMS_MAX,
                      'standard': STANDARD, 'done_how': DONE_HOW, 'done_levels': DONE_LEVELS, 'rule_tags': RULE_TAGS,
                      'sources': SOURCES, 'severities': SEVERITIES, 'item_verdicts': ITEM_VERDICTS, 'confidence': CONFIDENCE,
                      'raise_cap': RAISE_CAP, 'rounds_default': ROUNDS_DEFAULT, 'question_statuses': QUESTION_STATUSES,
                      'never_refuse': NEVER_REFUSE, 'ask_kinds': ASK_KINDS, 'ask_statuses': ASK_STATUSES, 'stages': STAGES,
                      'table_fields': TABLE_FIELDS, 'slot_fields': SLOT_FIELDS, 'left_out_fields': LEFT_OUT_FIELDS,
                      'coordination_fields': COORDINATION_FIELDS, 'timetable_row': TIMETABLE_ROW,
                      'engine_card_fields': ENGINE_CARD_FIELDS, 'engine_five_row': ENGINE_FIVE_ROW, 'born_fields': BORN_FIELDS},
        'layers': LAYERS, 'records': RECORDS, 'department_keys': DEPARTMENT_KEYS, 'legacy_keys': LEGACY_KEYS,
        'hears': HEARS, 'sends': SENDS, 'edges': edges(), 'calls': CALLS, 'verdicts': VERDICTS, 'checks': CHECKS,
        'shared_checks': SHARED_CHECKS, 'contract_samples': CONTRACT_SAMPLES, 'outputs': OUTPUTS, 'settings': SETTINGS,
        'groups': GROUPS, 'prompts': PROMPTS, 'option_kinds': OPTION_KINDS,
        'workflow_standards': [{'id': i, 'says': s, 'sources': src, 'stages': st} for i, s, src, st in WORKFLOW_STANDARDS],
        'views': VIEWS, 'sink': SINK, 'sink_journals': SINK_JOURNALS, 'defs': DEFS,
        # the templates at every level (A3): the levels, the ask forms, the step's constants, the ledger's words and Identity's five
        'template_levels': TEMPLATE_LEVELS, 'ask_forms': ASK_FORMS, 'ledger_actions': LEDGER_ACTIONS, 'recognitions': RECOGNITIONS,
        'steps': {'kinds': STEP_KINDS, 'natures': NATURES, 'rungs': RUNGS, 'gate_answers': GATE_ANSWERS, 'model_tools': MODEL_TOOLS,
                  'ctx': STEP_CTX, 'row': STEP_ROW},
        'function_template': {'by_layer': FUNCTION_TEMPLATE, 'agreement': DEPARTMENT_AGREEMENT, 'parts': TEMPLATE_PARTS,
                              'role_inputs': ROLE_INPUTS, 'role_block_max': ROLE_BLOCK_MAX, 'banned': TEMPLATE_BANNED,
                              'banned_agent': TEMPLATE_BANNED_AGENT, 'never_say': TEMPLATE_NEVER_SAY},
    }
    return json.loads(json.dumps(out, ensure_ascii=False))


# ---- migrations (A1.21): read time only; a read never writes, and the next write writes the record back ---------------
def _m0_to_1(name, doc):
    """Before A1 to schema version 1. A department gains schema_version and layers (DEFAULT_PINS), and done_items from
    its done line when it has none (D1, its how from the kind, level outcome, as W.done_items does). Coordination's
    table takes Coordination as the writer of any table whose `by` is neither born nor Coordination, keeping its why."""
    doc['schema_version'] = 1
    if name == 'department':
        doc.setdefault('layers', dict(DEFAULT_PINS))
        if 'done_items' not in doc:
            import website_dept as W
            kind = doc.get('kind')
            text = ' '.join(str(doc.get('done') or '').split())[:300] or (W.KINDS.get(kind) or {}).get('done') or ''
            doc['done_items'] = [{'id': 'D1', 'text': text, 'how': W.KIND_DONE_HOW.get(kind, 'model'), 'level': 'outcome'}] if text else []
    elif name == 'coordination.table':
        if 'by' in doc and doc['by'] not in ('born', 'Coordination'):
            doc['by'] = 'Coordination'
    return doc


MIGRATIONS = {0: _m0_to_1}


def migrate(name, doc):
    """A record read as the current schema version: a copy, migrated step by step; unknown keys are kept; never writes."""
    if not isinstance(doc, dict):
        return doc
    out = copy.deepcopy(doc)
    v = out.get('schema_version')
    v = v if isinstance(v, int) and not isinstance(v, bool) else 0
    while v < SCHEMA_VERSION:
        out = MIGRATIONS[v](name, out)
        v += 1
    return out


# ---- the JSON Schema files (A1.30): generated from here, never edited by hand ------------------------------------------
SCHEMA_FOLDER = HERE / 'schemas' / 'layers'
_ID = 'https://sutra.asawa.co/schemas/layers/'


def _refs(schema, out):
    """Every DEFS name a schema reaches through $ref, transitively."""
    if isinstance(schema, dict):
        r = schema.get('$ref')
        if isinstance(r, str):
            name = r.rsplit('/', 1)[-1]
            if name in DEFS and name not in out:
                out.add(name)
                _refs(DEFS[name], out)
        for v in schema.values():
            _refs(v, out)
    elif isinstance(schema, list):
        for v in schema:
            _refs(v, out)
    return out


def _closure(names):
    got = set(names)
    for n in list(names):
        _refs(DEFS[n], got)
    return {n: DEFS[n] for n in sorted(got)}


def _file(name, title, description, defs, main=None, **more):
    out = {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': _ID + name, 'title': title,
           'description': description + ' Generated from layer_schema.py (schema version %d); never edited by hand: run '
                                        '`python layer_schema.py --write`.' % SCHEMA_VERSION,
           '$defs': _closure(defs)}
    if main:
        out['$ref'] = '#/$defs/' + main
    out.update(more)
    return json.loads(json.dumps(out, ensure_ascii=False))


def json_schemas():
    """{file name: JSON Schema} for schemas/layers/: the interface's definitions as draft 2020-12 documents, each holding
    the definitions it reaches under $defs (the department's keys with x-owner), and interface.v1.json, describe()."""
    record_defs = sorted({r['def'] for kinds in RECORDS.values() for r in kinds.values()} |
                         {'priority.estimate', 'priority.price', 'priority.ceiling', 'audit.reading', 'audit.reading_item',
                          'audit.finding', 'adaptation.round', 'coordination.question', 'audit.spot_check', 'engine.template'})
    return {
        'department.schema.json': _file(
            'department.schema.json', 'A department record (dept.json)',
            "The department's one record, as the interface types it: each key's owning layer is in x-owner, and only the "
            'keys a save changes are checked (PRD A1.6, A1.20).', ['department'], 'department'),
        'workflow.schema.json': _file(
            'workflow.schema.json', 'A department workflow',
            'The one workflow schema every department workflow conforms to (a Library line, a fitted one, one Adaptation '
            'shapes or makes), its engines, its checks against the standards and its registration (PRD A1.14).',
            ['workflow', 'workflow.engine', 'workflow.check', 'workflow.registration'], 'workflow',
            **{'x-standards': [{'id': i, 'says': s, 'sources': list(src), 'stages': list(st)} for i, s, src, st in WORKFLOW_STANDARDS]}),
        'records.schema.json': _file(
            'records.schema.json', "The layers' records",
            "Every record a layer owns: asks, done-when items, rules, Coordination's table and slots, prices, the ceiling, "
            'readings, findings, rounds, questions between engines, spot checks and born engine templates (PRD A1.6 to A1.13b).',
            record_defs, **{'x-records': RECORDS}),
        'acts.schema.json': _file(
            'acts.schema.json', "The board's acts",
            "Every board act's payload, and who may post what to whom (x-edges) with the words each sends (x-sends) "
            '(PRD A1.13).', sorted(n for n in DEFS if n.startswith('act.')), **{'x-edges': edges(), 'x-sends': SENDS}),
        'instructions.schema.json': _file(
            'instructions.schema.json', "The owner's instructions (instructions.json)",
            "The owner's typed values for the prompt fields, by layer, group, part and field (x-fields: each part's fields "
            'and their types) (PRD A1.16).', ['instructions'] + sorted(n for n in DEFS if n.startswith('field.')), 'instructions',
            **{'x-fields': {layer: {group: {part: p['fields'] for part, p in parts.items()} for group, parts in groups.items()}
                            for layer, groups in PROMPTS.items()}}),
        'views.schema.json': _file(
            'views.schema.json', "The panes' read models",
            'What each pane renders, as the screens read it: Identity, Adaptation, Priority, Coordination and Audit, and the '
            'engine card (PRD A1.17).', sorted(VIEWS.values()), **{'x-views': VIEWS}),
        'templates.schema.json': _file(
            'templates.schema.json', 'The templates of the levels below the journey',
            "The step with its row and its start, the department kind, the Library's engine template and the artifact template, "
            'the base classes of levels L1, L3, L4 and L5 (x-levels holds all seven levels, x-steps the constants of the step and '
            'x-ask-forms the form of each kind of ask) (PRD A3.1, A3.3, A3.5).',
            ['step', 'step.row', 'engine.start', 'engine.library', 'kind', 'artifact.template'],
            **{'x-levels': TEMPLATE_LEVELS, 'x-ask-forms': ASK_FORMS,
               'x-steps': {'kinds': STEP_KINDS, 'natures': NATURES, 'rungs': RUNGS, 'gate_answers': GATE_ANSWERS,
                           'model_tools': MODEL_TOOLS, 'ctx': STEP_CTX, 'row': STEP_ROW}}),
        'journeys.schema.json': _file(
            'journeys.schema.json', 'A user journey',
            'The user-journey template (level L0): a journey file under journeys/, its parts (lane, step, edge, bind, outcome, '
            'sub-journey, ruling, quote, scenario, backlog entry, direction, build row, the earlier rows kept as was) and the status '
            'document that is computed for each journey; x-ledger-actions are the ledger words an event bind may name (PRD A3.6).',
            sorted(n for n in DEFS if n == 'journey' or n.startswith('journey.')), 'journey',
            **{'x-ledger-actions': LEDGER_ACTIONS, 'x-recognitions': RECOGNITIONS}),
        'interface.v1.json': describe(),
    }


def _dump(doc):
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def write_json_schemas(folder=None):
    """Write json_schemas() under schemas/layers/ (or `folder`); returns the paths written."""
    folder = Path(folder) if folder else SCHEMA_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name, doc in json_schemas().items():
        p = folder / name
        p.write_text(_dump(doc), encoding='utf-8')
        out.append(str(p))
    return out


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        for path in write_json_schemas():
            print(path)
    else:
        print('usage: python layer_schema.py --write    (regenerates schemas/layers/*.json from this file)')
        sys.exit(2)
