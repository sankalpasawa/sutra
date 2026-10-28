"""The names, the envelope, the option and the verdict every layer shares (A1.5), and the helpers the other modules write their fields with."""
from typing import Annotated, Any, Union
import layer_consts as K
from .base import Open
from .types import Str, Int, Num, Bool, Enum, Const, Anything, Bare, DefRef, Items, MapOf, AnyOf

# ---- the helpers every module writes its fields with ----------------------------------------------------------------------
# T(max, min) is text, SAY the words the owner reads, FIELD an owner-editable prompt field, WORD a pattern, I and N the numbers,
# E an enum, C a const, L a list, M a map, NULLABLE and ANYOF the unions. Each is one annotation (types.py) that carries the check
# and the JSON Schema it exports, so a bound is written once.
def T(max_len, min_len=0):
    return Annotated[str, Str(max_len, min_len)]


def SAY(max_len, min_len=0):
    return Annotated[str, Str(max_len, min_len, say=True)]


def FIELD(max_len, min_len=1, multiline=False):
    return Annotated[str, Str(max_len, min_len, field={'multiline': bool(multiline)})]


def WORD(pattern, max_len=40):
    return Annotated[str, Str(max_len, 0, pattern=pattern, word=True)]


def I(lo=None, hi=None):
    return Annotated[int, Int(lo, hi)]


def N(lo=None, hi=None):
    return Annotated[float, Num(lo, hi)]


def E(*values):
    return Annotated[Any, Enum(*values)]


def C(value):
    return Annotated[Any, Const(value)]


def L(of, max_items=None, min_items=0, unique=False):
    return Annotated[list[of], Items(max_items, min_items, unique)]


def M(of, keys=None):
    return Annotated[dict[str, of], MapOf(keys)]


def NULLABLE(of):
    return Annotated[Union[of, None], AnyOf()]


def ANYOF(*of):
    return Annotated[Union[of], AnyOf()]


B = Annotated[bool, Bool()]
ANY = Annotated[Any, Anything()]
BARE = Annotated[dict[str, Any], Bare()]
ISO = WORD(r'^\d{4}-\d\d-\d\d', 40)               # the head of W.now(): a date and, after it, whatever the clock says


def keep_order(names):
    """A class whose properties the interface lists in another order than its fields (the required ones come first, so that a
    missing key is reported in the order `required` lists them): the export puts them back, so DEFS[name]['properties'] reads as
    it always did."""
    names = tuple(names)

    def put_back(schema, cls=None):
        props = schema.get('properties')
        if props:
            schema['properties'] = dict({k: props[k] for k in names if k in props}, **props)
    return put_back


def named(def_name, body):
    """A definition other definitions point at by $ref: the annotation a field uses (the file says {'$ref': ...}), the body being
    what the name itself is checked against."""
    return Annotated[body, DefRef(def_name, body)]


def ref_of(def_name, target):
    """A definition that is only a $ref to another (department.layers is root.pins)."""
    return Annotated[target, DefRef(def_name, target)]



NameBody = WORD(K.NAME_RE)
Name = named('name', NameBody)


IdItemBody = WORD(K.ITEM_RE, 3)
IdItem = named('id.item', IdItemBody)


IdFindingBody = WORD(K.FINDING_RE, 4)
IdFinding = named('id.finding', IdFindingBody)


ImplBody = WORD(K.IMPL_RE, 24)
Impl = named('impl', ImplBody)


class Envelope(Open):
    __def__ = 'envelope'
    calls: I(0)
    usd: N(0)


class Option(Open):
    __def__ = 'option'
    id: WORD('^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]{1,40})?$', 64)
    label: SAY(120, 1)
    cost: SAY(400)
    kind: E(*K.OPTION_KINDS) = None
    params: BARE = None


class CheckVerdict(Open):
    __def__ = 'check.verdict'
    ok: B
    notes: L(T(2000))


DEFINES = {
    'name': NameBody,
    'id.item': IdItemBody,
    'id.finding': IdFindingBody,
    'impl': ImplBody,
    'envelope': Envelope,
    'option': Option,
    'check.verdict': CheckVerdict,
}
__all__ = [
    'CheckVerdict', 'Envelope', 'IdFinding', 'IdFindingBody', 'IdItem', 'IdItemBody', 'Impl', 'ImplBody', 'Name',
    'NameBody', 'Option', 'DEFINES',
]
