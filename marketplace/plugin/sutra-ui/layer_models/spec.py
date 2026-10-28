"""The spec of an owner-defined model (A4.5.2): data that says what a model holds. A spec is itself a core definition, so a hand-edited
models.json is checked like any record, and its JSON Schema is generated like the others (schemas/models/).

The vocabulary is closed: eight kinds of field, three named patterns, two kinds of link, and bounds that are numbers. Nothing in a
spec is ever run; compile.py turns it into annotation objects of types.py and nothing else (A4.5.8)."""
import json
import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import ConfigDict, Field, TypeAdapter, model_validator

from .base import Closed
from .faults import faults_error
from .types import AnyOf, Anything, Bool, Const, Enum, Int, Items, MapOf, Num, Str

NAME = r'^[a-z][a-z0-9_]{1,30}$'
FIELD_NAME = r'^[a-z][a-z0-9_]{0,30}$'
#: a base or a target: 'core:record', 'x:client/v1', 'x:client' (a link to the latest)
BASE_REF = r'^(core:[a-z][a-z0-9_.]{0,40}|x:[a-z][a-z0-9_]{1,30}(/v[0-9]{1,2})?)$'
EXACT_REF = r'^x:[a-z][a-z0-9_]{1,30}/v[0-9]{1,2}$'
FILE_KEY = r'^[a-z][a-z0-9_]{1,30}/v[0-9]{1,2}$'

VOCABULARY = ('text', 'long_text', 'whole', 'number', 'yesno', 'choice', 'words', 'date')
#: the owner's word for each kind of field
VOCABULARY_WORDS = {'text': 'text', 'long_text': 'long text', 'whole': 'whole number', 'number': 'number', 'yesno': 'yes or no',
                    'choice': 'one of', 'words': 'list of words', 'date': 'date'}
NAMED_PATTERNS = {'slug': r'^[a-z0-9][a-z0-9-]*$', 'code': r'^[A-Z0-9][A-Z0-9_-]*$', 'date': r'^\d{4}-\d\d-\d\d'}
LIMITS = {'models': 60, 'versions': 20, 'fields': 40, 'links': 10, 'nest_depth': 4, 'spec_bytes': 64 * 1024,
          'file_bytes': 2 * 1024 * 1024, 'request_bytes': 128 * 1024, 'pending': 20, 'choices': 12, 'sample_depth': 32}
#: the core models an owner may hold as a value (none may be extended) and the ones an owner may build on
NESTABLE_CORE = ('envelope', 'identity.done_item', 'option')
EXTENSIBLE_CORE = ('record', 'artifact.template', 'engine.library', 'kind', 'journey')


def T(n, m=0, **k):
    return Annotated[str, Str(n, m, **k)]


def L(of, mx=None, mn=0, uq=False):
    return Annotated[list[of], Items(mx, mn, uq)]


def NL(of):
    return Annotated[Union[of, None], AnyOf()]


BOUND = Annotated[int, Int(-10 ** 9, 10 ** 9)]
_WORD = T(40, 1, pattern=NAME, word=True)
_FNAME = T(31, 1, pattern=FIELD_NAME, word=True)


class _Field(Closed):
    """What every kind of field has. A field is required, or it may be missing; there is no default (A4.5.2)."""
    __abstract__ = True
    name: _FNAME
    label: T(60, 1, say=True)
    about: Optional[T(200, 0, say=True)] = None
    required: Optional[Annotated[bool, Bool()]] = None
    nullable: Optional[Annotated[bool, Bool()]] = None
    retired: Optional[Annotated[bool, Bool()]] = None
    aliases: Optional[L(_FNAME, 3, 0, True)] = None


class TextField(_Field):
    __abstract__ = False
    type: Literal['text']
    max_len: Optional[Annotated[int, Int(1, 2000)]] = None
    min_len: Optional[Annotated[int, Int(0, 2000)]] = None
    pattern: Optional[Annotated[Any, Enum(*NAMED_PATTERNS)]] = None


class LongTextField(_Field):
    __abstract__ = False
    type: Literal['long_text']
    max_len: Optional[Annotated[int, Int(1, 20000)]] = None


class WholeField(_Field):
    __abstract__ = False
    type: Literal['whole']
    minimum: Optional[BOUND] = None
    maximum: Optional[BOUND] = None


class NumberField(_Field):
    __abstract__ = False
    type: Literal['number']
    minimum: Optional[Annotated[float, Num(-10 ** 9, 10 ** 9)]] = None
    maximum: Optional[Annotated[float, Num(-10 ** 9, 10 ** 9)]] = None


class YesNoField(_Field):
    __abstract__ = False
    type: Literal['yesno']


class ChoiceField(_Field):
    __abstract__ = False
    type: Literal['choice']
    choices: L(T(40, 1, say=True), LIMITS['choices'], 1, True)


class WordsField(_Field):
    __abstract__ = False
    type: Literal['words']
    max_items: Optional[Annotated[int, Int(1, 100)]] = None
    unique: Optional[Annotated[bool, Bool()]] = None


class DateField(_Field):
    __abstract__ = False
    type: Literal['date']


FieldSpec = Annotated[Union[TextField, LongTextField, WholeField, NumberField, YesNoField, ChoiceField, WordsField, DateField],
                      Field(discriminator='type')]


class LinkSpec(Closed):
    """A nest (the target's value sits inside this one) or a refer (the target's id)."""
    __abstract__ = False
    name: _FNAME
    label: T(60, 1, say=True)
    mode: Literal['nest', 'refer']
    to: T(60, 1, pattern=BASE_REF, word=True)
    many: Optional[Annotated[bool, Bool()]] = None
    required: Optional[Annotated[bool, Bool()]] = None
    max: Optional[Annotated[int, Int(1, 100)]] = None
    enabled: Optional[Annotated[bool, Bool()]] = None


class ModelSpec(Closed):
    """One entry of models.json, keyed 'name/vN'."""
    __abstract__ = False
    __def__ = 'model.spec'
    schema_version: Optional[Annotated[Any, Const(1)]] = None
    name: T(31, 2, pattern=NAME, word=True)
    version: Annotated[int, Int(1, LIMITS['versions'])]
    parent: Optional[T(60, 1, pattern=EXACT_REF, word=True)] = None
    label: T(60, 1, say=True)
    about: Optional[T(300, 0, say=True)] = None
    base: T(60, 1, pattern=BASE_REF, word=True)
    abstract: Optional[Annotated[bool, Bool()]] = None
    discriminator: Optional[T(31, 1, pattern=FIELD_NAME, word=True)] = None
    enabled: Optional[Annotated[bool, Bool()]] = None
    fields: L(FieldSpec, LIMITS['fields'])
    links: Optional[L(LinkSpec, LIMITS['links'])] = None
    base_sha: Optional[T(64, 64, pattern=r'^[0-9a-f]{64}$')] = None
    created: Optional[T(40, 0)] = None
    updated: Optional[T(40, 0)] = None
    by: Optional[T(60, 0, say=True)] = None

    @model_validator(mode='after')
    def _a_later_version_names_its_parent(self):
        if self.version > 1 and not self.parent:
            raise faults_error([], [(['parent'], 'is missing: version %d builds on version %d' % (self.version, self.version - 1))])
        return self


class _Cap:
    """The file's own limits: at most 60 models, and no spec over 64 KB. The sentences sit at the entry they are about."""

    def __get_pydantic_core_schema__(self, source, handler):
        from pydantic_core import core_schema
        inner = handler(source)
        top, size = LIMITS['models'], LIMITS['spec_bytes']

        def wrap(v, h):
            if isinstance(v, dict):
                at = [([k], 'a model is at most %d KB' % (size // 1024)) for k, s in v.items() if len(json.dumps(s, default=str)) > size]
                own = ['a file holds at most %d models' % top] if len(v) > top else []
                if at or own:
                    raise faults_error(own, at)
            return h(v)
        return core_schema.no_info_wrap_validator_function(wrap, inner)

    def __get_pydantic_json_schema__(self, cs, handler):
        return handler(cs)


class ModelFile(Closed):
    """models.json as a whole."""
    __abstract__ = False
    __def__ = 'model.file'
    schema_version: Annotated[Any, Const(1)]
    rev: Annotated[int, Int(0, 10 ** 9)]
    models: Annotated[dict[str, ModelSpec], MapOf(FILE_KEY), _Cap()]


class HistoryRow(Closed):
    """One line of history.jsonl. `class` is a keyword, so the field is `klass` and answers to `class`."""
    __abstract__ = False
    __def__ = 'model.history'
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    rev: Annotated[int, Int(0, 10 ** 9)]
    at: T(40, 1)
    by: T(60, 1, say=True)
    op: Annotated[Any, Enum('create', 'edit', 'enable', 'disable', 'revert', 'stamp', 'rebase', 'base_changed')]
    key: T(80, 1)
    says: T(400, 0, say=True)
    klass: Optional[Annotated[Any, Enum('tightens', 'same', 'widens', 'mixed')]] = Field(default=None, alias='class')
    before_sha: Optional[T(64, 0)] = None
    after_sha: Optional[T(64, 0)] = None
    spec: Annotated[Any, Anything()] = None


_ADAPTERS = {}


def adapter(cls):
    """One TypeAdapter for each spec class, built on first use and kept."""
    ad = _ADAPTERS.get(cls)
    if ad is None:
        ad = _ADAPTERS[cls] = TypeAdapter(cls)
    return ad


def check(cls, value):
    """The faults of `value` as one of the spec classes: [] when it fits."""
    from .faults import sentences
    return sentences(adapter(cls), value)


def key_of(spec):
    """The file key of a spec: 'client/v1'."""
    return '%s/v%d' % (spec['name'], spec['version'])
