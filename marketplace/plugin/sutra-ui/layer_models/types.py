"""The interface's scalars and containers as annotation objects (A4.3.2). Each is ONE object that carries both the check and the
JSON Schema it generates, so the two are written once; every failure carries the sentence layer_schema's walker writes today.

    name: Annotated[str, Str(40, 1)]            text(40, 1)
    n:    Annotated[int, Int(0, 99)]            integer(0, 99)
    xs:   Annotated[list[X], Items(12)]         items(X, 12)

`bounds()` returns an object's parameters as a dict (rules.narrows reads it). A check is a plain function: it never builds a
TypeAdapter, a model or a schema per call, so it is safe in a stream producer (A4.7.2)."""
import json
import re
from typing import Any, get_args

from pydantic import TypeAdapter, ValidationError
from pydantic_core import core_schema

from .faults import explain, faults_error, type_error
from . import registry

_CTRL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')     # control characters except tab and newline


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def _same(a, b):
    """Equal as JSON values are: True is never 1, and 1 is 1.0."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _shown(values, n=8):
    vals = [json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for v in values]
    return ', '.join(vals[:n]) + (', ...' if len(vals) > n else '')


def _plain(check):
    return core_schema.no_info_plain_validator_function(check)


# ---- scalars ------------------------------------------------------------------------------------------------------------
class Str:
    """text / say / field / word / iso. Every failure of one value is reported together, in the walker's order."""

    def __init__(self, max_len, min_len=0, pattern=None, say=False, field=None, word=False):
        self.max_len, self.min_len, self.pattern, self.say, self.field, self.word = max_len, min_len, pattern, say, field, word
        self._re = re.compile(pattern) if pattern else None

    def bounds(self):
        return {'max_len': self.max_len, 'min_len': self.min_len, 'pattern': self.pattern, 'say': self.say,
                'field': self.field, 'word': self.word}

    def __get_pydantic_core_schema__(self, source, handler):
        return _plain(self.check)

    def check(self, v):
        if not isinstance(v, str):
            raise type_error('is not a string')
        f = []
        if len(v) < self.min_len and not self.word:
            f.append('shorter than %d' % self.min_len)
        if self.max_len is not None and len(v) > self.max_len:
            f.append('longer than %d' % self.max_len)
        if self._re is not None and not self._re.search(v):
            f.append('does not match %s' % self.pattern)
        if self.say and _CTRL.search(v):
            f.append('holds a control character')
        if self.field:
            if '{{' in v or '}}' in v:
                f.append("holds '{{' or '}}', which only the app may write")
            if 'Return ONLY' in v:
                f.append("holds 'Return ONLY': the answer's shape belongs to the app")
            if _CTRL.search(v.replace('\n', '')):
                f.append('holds a control character')
            if not self.field.get('multiline') and '\n' in v:
                f.append('holds a line break')
        if f:
            raise faults_error(f)
        return v

    def __get_pydantic_json_schema__(self, cs, handler):
        out = {'type': 'string'}
        if not self.word:
            out['minLength'] = self.min_len
        if self.max_len is not None:
            out['maxLength'] = self.max_len
        if self.pattern:
            out['pattern'] = self.pattern
        if self.say:
            out['x-say'] = True
        if self.field is not None:
            out['x-field'] = dict(self.field)
        return out


class Int:
    """integer(lo, hi): a whole number, and 3.0 is one; a bool is not."""
    kind = 'integer'

    def __init__(self, minimum=None, maximum=None):
        self.minimum, self.maximum = minimum, maximum

    def bounds(self):
        return {'minimum': self.minimum, 'maximum': self.maximum}

    def __get_pydantic_core_schema__(self, source, handler):
        return _plain(self.check)

    def _range(self, v):
        f = []
        if self.minimum is not None and v < self.minimum:
            f.append('below %s' % self.minimum)
        if self.maximum is not None and v > self.maximum:
            f.append('above %s' % self.maximum)
        if f:
            raise faults_error(f)
        return v

    def check(self, v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not v.is_integer()):
            raise type_error('is not a whole number')
        return self._range(v)

    def __get_pydantic_json_schema__(self, cs, handler):
        out = {'type': self.kind}
        if self.minimum is not None:
            out['minimum'] = self.minimum
        if self.maximum is not None:
            out['maximum'] = self.maximum
        return out


class Num(Int):
    """number(lo, hi)."""
    kind = 'number'

    def check(self, v):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise type_error('is not a number')
        return self._range(v)


class Bool:
    def bounds(self):
        return {}

    def __get_pydantic_core_schema__(self, source, handler):
        def chk(v):
            if not isinstance(v, bool):
                raise type_error('is not true or false')
            return v
        return _plain(chk)

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'type': 'boolean'}


class Enum:
    """enum(*values): True is never 1; at most 8 values are shown in the sentence."""

    def __init__(self, *values):
        self.values = list(values)

    def bounds(self):
        return {'values': list(self.values)}

    def __get_pydantic_core_schema__(self, source, handler):
        values = self.values

        def chk(v):
            if not any(_same(v, e) for e in values):
                raise type_error('is not one of %s' % _shown(values))
            return v
        return _plain(chk)

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'enum': list(self.values)}


class Const(Enum):
    """const(value)."""

    def __init__(self, value):
        super().__init__(value)
        self.value = value

    def bounds(self):
        return {'value': self.value}

    def __get_pydantic_core_schema__(self, source, handler):
        value = self.value

        def chk(v):
            if not _same(v, value):
                raise type_error('is not %s' % _shown([value]))
            return v
        return _plain(chk)

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'const': self.value}


class Anything:
    """ANYTHING: a field that is named but not typed."""

    def bounds(self):
        return {}

    def __get_pydantic_core_schema__(self, source, handler):
        return core_schema.any_schema()

    def __get_pydantic_json_schema__(self, cs, handler):
        return {}


class Bare:
    """obj({}): an object with no declared field. A plain check, so the dict that comes in is the dict that stays."""

    def bounds(self):
        return {}

    def __get_pydantic_core_schema__(self, source, handler):
        def chk(v):
            if not isinstance(v, dict):
                raise type_error('is not an object')
            return v
        return _plain(chk)

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': True}


# ---- markers: they add a keyword to the file and never reject -------------------------------------------------------------
class DefRef:
    """A named scalar (`name`, `id.item`): the field's schema is {'$ref': '#/$defs/<name>'} and the body is registered once.
    Pydantic cannot be handed a $ref of its own (G9), so the file carries the marker x-defref and schema.export rewrites it."""

    def __init__(self, name, body):
        self.name, self.body = name, body
        registry.ALIASES[name] = body

    def bounds(self):
        return {'name': self.name}

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'x-defref': self.name}


class Owner:
    """The layer that owns a field of the department record: x-owner."""

    def __init__(self, layer):
        self.layer = layer

    def bounds(self):
        return {'layer': self.layer}

    def __get_pydantic_json_schema__(self, cs, handler):
        return dict(handler(cs), **{'x-owner': self.layer})


class Law:
    """A step field's place in the law of inheritance (A2): 'fixed' or 'free': x-law."""

    def __init__(self, law):
        if law not in ('fixed', 'free'):
            raise ValueError("a law is 'fixed' or 'free'")
        self.law = law

    def bounds(self):
        return {'law': self.law}

    def __get_pydantic_json_schema__(self, cs, handler):
        return dict(handler(cs), **{'x-law': self.law})


class Ref:
    """A link by id (R7): the id of `target_def`, typed by `id_type` (a Str). The check and the sentence are the Str's own; the
    file adds x-ref so a reader can tell a link from a plain word."""

    def __init__(self, target_def, id_type):
        self.target_def, self.id_type = target_def, id_type

    def bounds(self):
        return {'target_def': self.target_def, 'id_type': self.id_type.bounds()}

    def __get_pydantic_core_schema__(self, source, handler):
        return self.id_type.__get_pydantic_core_schema__(source, handler)

    def __get_pydantic_json_schema__(self, cs, handler):
        return dict(self.id_type.__get_pydantic_json_schema__(cs, handler), **{'x-ref': self.target_def})


# ---- containers ---------------------------------------------------------------------------------------------------------
class Items:
    """list[X] with the walker's length and uniqueness sentences, reported together with the items' own faults (G3). A tuple is a
    list. The wrapper returns the inner validator's result (G8), never its input."""

    def __init__(self, max_items=None, min_items=0, unique=False):
        self.max_items, self.min_items, self.unique = max_items, min_items, unique

    def bounds(self):
        return {'max_items': self.max_items, 'min_items': self.min_items, 'unique': self.unique}

    def __get_pydantic_core_schema__(self, source, handler):
        inner = handler(source)
        lo, hi, unique = self.min_items, self.max_items, self.unique

        def wrap(v, h):
            if isinstance(v, tuple):
                v = list(v)
            if not isinstance(v, list):
                raise type_error('is not a list')
            own = []
            if len(v) < lo:
                own.append('fewer than %d items' % lo)
            if hi is not None and len(v) > hi:
                own.append('more than %d items' % hi)
            if unique and len({_canon(x) for x in v}) != len(v):
                own.append('holds an item twice')
            child, out = [], v
            try:
                out = h(v)
            except ValidationError as e:
                child = explain(e.errors(include_url=False), v)
            if own or child:
                raise faults_error(own, child)
            return out
        return core_schema.no_info_wrap_validator_function(wrap, inner)

    def __get_pydantic_json_schema__(self, cs, handler):
        out = dict(handler(cs), type='array', minItems=self.min_items)
        if self.max_items is not None:
            out['maxItems'] = self.max_items
        if self.unique:
            out['uniqueItems'] = True
        return out


class MapOf:
    """dict[str, X] whose every key matches `keys` when one is given: the key sentence first for each key, then the values'."""

    def __init__(self, keys=None):
        self.keys = keys
        self._re = re.compile(keys) if keys else None

    def bounds(self):
        return {'keys': self.keys}

    def __get_pydantic_core_schema__(self, source, handler):
        inner = handler(source)
        rx, pattern = self._re, self.keys

        def wrap(v, h):
            if not isinstance(v, dict):
                raise type_error('is not an object')
            own = []
            if rx is not None:
                own = [([k], 'the key does not match %s' % pattern) for k in v if not rx.search(str(k))]
            child, out = [], v
            try:
                out = h(v)
            except ValidationError as e:
                child = explain(e.errors(include_url=False), v)
            if own or child:
                raise faults_error([], own + child)
            return out
        return core_schema.no_info_wrap_validator_function(wrap, inner)

    def __get_pydantic_json_schema__(self, cs, handler):
        out = dict(handler(cs), type='object')
        if self.keys:
            out['propertyNames'] = {'pattern': self.keys}
        return out


class AnyOf:
    """A union of shapes with the walker's sentence: fits none of its shapes (<the first shape's first fault>). The first shape
    that fits answers. A value that fits goes through the union in the core; only a value that fits none is taken through the
    branches again, one adapter each (built once, with the class that holds the field), to find the first shape's first fault."""

    def bounds(self):
        return {}

    def __get_pydantic_core_schema__(self, source, handler):
        inner = handler(source)
        branches = [TypeAdapter(b) for b in get_args(source)]

        def wrap(v, h):
            try:
                return h(v)              # the union itself, in the core: a value some shape takes is taken (the common case, fast)
            except ValidationError:
                pass
            first = None
            for ad in branches:
                try:
                    return ad.validate_python(v)
                except ValidationError as e:
                    if first is None:
                        got = explain(e.errors(include_url=False), v)
                        first = got[0][1] if got else 'no shape'
            raise faults_error(['fits none of its shapes (%s)' % first])
        return core_schema.no_info_wrap_validator_function(wrap, inner)

    def __get_pydantic_json_schema__(self, cs, handler):
        return handler(cs)
