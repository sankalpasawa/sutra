"""A spec is data; a class is made from it here, and nothing else is ever run (A4.5.4, A4.5.8).

A field comes only from the vocabulary of spec.py, through the annotation objects of types.py. The class is made on a core base,
so it inherits that base's validation, and is held to the class rules when it is made (rules.check_class). No spec text is ever
evaluated, imported or looked up by name: a name is a dictionary key, nothing more.

    compile_all(specs, core, reuse=None) -> Registry      the whole set, bases and nests first
    compile_one(spec, scope) -> class                      one model, on the classes `scope` already holds

A model that cannot be made (a rule, a loosening child, a base that failed) is left out of the registry and marked needs_a_look
with the first sentence; nothing is deleted."""
import hashlib
import json
from typing import Annotated, Any, Union

from pydantic import AliasChoices, Field, TypeAdapter, ValidationError

from . import owner_rules
from .faults import explain, faults_error, type_error
from .owner_base import ID_PATTERN
from .registry import Registry
from .spec import NAMED_PATTERNS
from .types import AnyOf, Bool, Enum, Int, Items, Num, Ref, Str

_MODULE = 'layer_models.owner'


class Dispatch:
    """A family (R8): an abstract base, the field that picks a child, and the children that are on. A value with a tag that is no
    child's reads 'is not one of circle, square' at the tag; a value with none, 'is missing'. The adapters are built here, once."""

    def __init__(self, disc, children):
        self.disc = disc
        self.tags = list(children)
        self.adapters = {t: TypeAdapter(c) for t, c in children.items()}

    def bounds(self):
        return {'discriminator': self.disc, 'tags': list(self.tags)}

    def __get_pydantic_core_schema__(self, source, handler):
        from pydantic_core import core_schema
        disc, tags, adapters = self.disc, self.tags, self.adapters

        def chk(v):
            if not isinstance(v, dict):
                raise type_error('is not an object')
            if disc not in v:
                raise faults_error([], [([disc], 'is missing')])
            tag = v[disc]
            ad = adapters.get(tag) if isinstance(tag, str) else None
            if ad is None:
                raise faults_error([], [([disc], 'is not one of %s' % ', '.join(tags))])
            try:
                return ad.validate_python(v)
            except ValidationError as e:
                raise faults_error([], explain(e.errors(include_url=False), v))
        return core_schema.no_info_plain_validator_function(chk)

    def __get_pydantic_json_schema__(self, cs, handler):
        return {'oneOf': [ad.json_schema() for ad in self.adapters.values()]}


class _Scope:
    """What compile_one needs of a registry being built: the core, the classes made so far and the specs."""

    def __init__(self, core, specs, classes=None):
        self.core, self.specs = core, specs
        self.classes = {} if classes is None else classes
        self._families = {}

    def base_of(self, ref):
        """The class a 'core:...' or 'x:...' reference names, or None."""
        if ref.startswith('core:'):
            return self.core.get(ref)
        fk = owner_rules.ref_key(ref, self.specs)
        return self.classes.get(owner_rules.ek(fk)) if fk else None

    def family(self, fk):
        """The dispatch of an abstract base that names a discriminator: its children that are on and made, by tag. None for a
        model that is not a family. Built once for each key."""
        spec = self.specs[fk]
        if not (spec.get('abstract') and spec.get('discriminator')):
            return None
        if fk not in self._families:
            kids = {}
            for ck in owner_rules.children_of(self.specs, fk):
                cls = self.classes.get(owner_rules.ek(ck))
                tag = _tag_of(self.specs[ck], spec['discriminator'])
                if cls is not None and tag is not None and not self.specs[ck].get('abstract') and owner_rules.effective_on(self.specs, ck):
                    kids[tag] = cls
            self._families[fk] = Dispatch(spec['discriminator'], kids)
        return self._families[fk]


def annotation(f):
    """A field spec -> its annotation. Only the eight kinds exist; anything else is a ValueError (the spec shape has refused it)."""
    t = f['type']
    if t == 'text':
        return Annotated[str, Str(f.get('max_len') or 200, f.get('min_len') or 0, pattern=NAMED_PATTERNS.get(f.get('pattern')), say=True)]
    if t == 'long_text':
        return Annotated[str, Str(f.get('max_len') or 20000, 0, say=True)]
    if t == 'whole':
        return Annotated[int, Int(f.get('minimum'), f.get('maximum'))]
    if t == 'number':
        return Annotated[float, Num(f.get('minimum'), f.get('maximum'))]
    if t == 'yesno':
        return Annotated[bool, Bool()]
    if t == 'choice':
        return Annotated[Any, Enum(*f['choices'])]
    if t == 'words':
        return Annotated[list[Annotated[str, Str(80, 1, say=True)]], Items(f.get('max_items') or 20, 0, bool(f.get('unique')))]
    if t == 'date':
        return Annotated[str, Str(10, 10, pattern=NAMED_PATTERNS['date'])]
    raise ValueError('no such kind of field: %s' % t)


def _link_annotation(l, scope):
    """A link -> its annotation. A nest is the target's class (a family's dispatch when the target is abstract); a refer is the
    target's id."""
    to = l['to']
    many, mx, need = bool(l.get('many')), l.get('max') or 50, bool(l.get('required'))
    if l['mode'] == 'refer':
        tk = owner_rules.ref_key(to, scope.specs)
        ref = Annotated[str, Ref(owner_rules.ek(tk) if tk else to, Str(40, 1, pattern=ID_PATTERN, word=True))]
        return Annotated[list[ref], Items(mx, 1 if need else 0)] if many else ref
    tgt = scope.base_of(to)
    if tgt is None:
        raise ValueError('%s is not available' % to)
    tk = None if to.startswith('core:') else owner_rules.ref_key(to, scope.specs)
    fam = scope.family(tk) if tk else None
    one = Annotated[Any, fam] if fam is not None else tgt
    return Annotated[list[one], Items(mx, 1 if need else 0)] if many else one


def compile_one(spec, scope):
    """The class of one spec. On the class of the version before it (R10), else on its base. TypeError from the class rules
    (a field that loosens its base) is for the caller."""
    ann, attrs, tags = {}, {}, spec.get('base') or ''
    base = None
    if spec['version'] > 1:
        base = scope.base_of(spec['parent'])
    if base is None:
        base = scope.base_of(tags)
    if base is None:
        raise ValueError('%s cannot be built on' % tags)
    for f in spec.get('fields') or []:
        a = annotation(f)
        if f.get('nullable'):
            a = Annotated[Union[a, None], AnyOf()]
        kw = {}
        if f.get('aliases'):
            kw['validation_alias'] = AliasChoices(f['name'], *f['aliases'])
        ann[f['name']] = a
        attrs[f['name']] = Field(**kw) if f.get('required') and not f.get('retired') else Field(default=None, **kw)
    for l in spec.get('links') or []:
        if l.get('enabled') is False:
            continue
        ann[l['name']] = _link_annotation(l, scope)
        attrs[l['name']] = Field() if l.get('required') else Field(default=None)
    ns = dict(attrs, __annotations__=ann, __module__=_MODULE, __def__='x.' + spec['name'], __version__=spec['version'],
              __abstract__=bool(spec.get('abstract')))
    return type(base)('X_%s_v%d' % (spec['name'], spec['version']), (base,), ns)


def sha(obj):
    """The sha256 of an object as canonical JSON."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')).hexdigest()


def _deps(spec, specs):
    """The file keys a spec needs made first: its parent, its base, the models it nests (and a family's children)."""
    out = []
    for ref in (spec.get('parent'), spec.get('base')):
        k = owner_rules.ref_key(ref, specs)
        if k:
            out.append(k)
    for l in spec.get('links') or []:
        if l.get('mode') == 'nest' and l.get('enabled') is not False:
            k = owner_rules.ref_key(l.get('to'), specs)
            if k:
                out.append(k)
                out += owner_rules.children_of(specs, k) if specs[k].get('abstract') else []
    return out


def _order(specs):
    """Dependencies first. A key in a circle comes out anyway (the rules have marked it) so every key is visited once."""
    seen, out = set(), []

    def visit(k, trail):
        if k in seen or k in trail:
            return
        for d in _deps(specs[k], specs):
            visit(d, trail | {k})
        seen.add(k)
        out.append(k)
    for k in sorted(specs, key=lambda x: (specs[x]['version'], x)):
        visit(k, frozenset())
    return out


def _tag_of(spec, disc):
    f = next((x for x in spec.get('fields') or [] if x['name'] == disc), None)
    return f['choices'][0] if f and f.get('choices') else None


def compile_all(specs, core, reuse=None):
    """Make the whole set. `reuse` is a Registry whose classes are kept for a spec that has not changed and whose dependencies are
    the very classes they were made on, so an edit rebuilds the model it touches and what stands on it, no more."""
    faults = {k: list(v) for k, v in owner_rules.check(specs, core).items()}
    bad = {k[2:] for k in faults}
    scope = _Scope(core, specs)
    why = {}
    for fk in _order(specs):
        spec, key = specs[fk], owner_rules.ek(fk)
        dead = [d for d in _deps(spec, specs) if d in bad or owner_rules.ek(d) not in scope.classes]
        if fk in bad or dead:
            bad.add(fk)
            if fk not in {k[2:] for k in faults}:
                faults[key] = [('BASE_BROKEN', '%s stands on %s, which needs a look' % (spec['label'], owner_rules.label(specs, dead[0]) if dead else 'a model'))]
            continue
        deps = _deps(spec, specs)
        sig = (sha(spec), id(scope.base_of(spec.get('base') or '')), tuple((id(scope.classes.get(owner_rules.ek(d))), owner_rules.effective_on(specs, d)) for d in deps))
        old = reuse.classes.get(key) if reuse is not None else None
        if old is not None and old.__dict__.get('_sig') == sig:
            scope.classes[key] = old
        else:
            try:
                cls = compile_one(spec, scope)
            except TypeError as e:
                bad.add(fk)
                faults[key] = [('LOOSENS_BASE', p) for p in str(e).split(': ', 1)[-1].split('; ')]
                continue
            except ValueError as e:
                bad.add(fk)
                faults[key] = [('LINK_TARGET', str(e))]
                continue
            cls._sig = sig
            scope.classes[key] = cls
    state = {}
    for fk in specs:
        key = owner_rules.ek(fk)
        if key in faults:
            state[key] = 'needs_a_look'
            why[key] = faults[key][0][1]
        elif not owner_rules.effective_on(specs, fk):
            state[key] = 'off'
        else:
            state[key] = 'on'
    adapters, fam_ad = {}, {}
    for key, cls in scope.classes.items():
        fam = scope.family(key[2:])
        if fam is not None:
            fam_ad[key] = TypeAdapter(Annotated[Any, fam])
        elif not cls.__dict__.get('__abstract__'):
            adapters[key] = TypeAdapter(cls)
    return Registry(core=core, classes=scope.classes, adapters=adapters, specs=specs, state=state, why=why, families=fam_ad,
                    faults={k: v for k, v in faults.items()})
