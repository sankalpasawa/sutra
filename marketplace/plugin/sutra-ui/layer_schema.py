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


DEFS = {}
