"""The rules an owner's set of models is held to at save and at load (A4.5.5, R6 to R12). They read the specs (dicts, already
shaped as model.spec) and the core, never a class: the comparison of two compiled classes is `classify`.

`check(specs, core)` returns {key: [(code, sentence)]} for every key with a fault, keyed 'x.<name>/v<N>'. The sentences are the
owner's words: they name the model by its label and say what is wrong, and never use the bargain's words (S.TEMPLATE_BANNED)."""
import json
import keyword
import re

from pydantic import BaseModel

from . import rules
from .spec import EXTENSIBLE_CORE, LIMITS, NESTABLE_CORE, key_of

RESERVED = set(dir(BaseModel)) | set(keyword.kwlist) | {'model', 'schema', 'json', 'copy', 'dict', 'id_'}
#: the heads of the core definitions (identity.ask -> identity): a name that begins with one belongs to the app
CORE_HEADS = ('identity', 'adaptation', 'priority', 'coordination', 'audit', 'root', 'act', 'ask', 'edge', 'verdict', 'reading',
              'workflow', 'department', 'view', 'step', 'setting', 'prompt', 'check', 'option', 'envelope', 'journey', 'engine',
              'artifact', 'kind', 'record', 'layer', 'model')
CORE_LABELS = {'record': 'Record', 'artifact.template': 'Artifact template', 'engine.library': 'Engine library',
               'kind': 'Department kind', 'journey': 'Journey', 'envelope': 'Envelope', 'identity.done_item': 'Done item',
               'option': 'Option'}
CORE_SAYS = {'record': 'a record with an id', 'artifact.template': 'what a kind of filed work holds',
             'engine.library': 'what an engine template holds', 'kind': 'what a kind of department holds',
             'journey': 'what a journey holds'}


def core_label(name):
    """The owner's word for a core model: 'Ask' for identity.ask."""
    name = name[5:] if name.startswith('core:') else name
    return CORE_LABELS.get(name) or name.rsplit('.', 1)[-1].replace('_', ' ').capitalize()


def ek(file_key):
    """'client/v1' -> 'x.client/v1'."""
    return 'x.' + file_key


def ref_key(ref, specs):
    """The file key an 'x:<name>[/v<N>]' reference points at (an unversioned one is the highest version), or None."""
    if not isinstance(ref, str) or not ref.startswith('x:'):
        return None
    body = ref[2:]
    if '/v' in body:
        return body if body in specs else None
    best = None
    for k, s in specs.items():
        if s.get('name') == body and (best is None or s['version'] > specs[best]['version']):
            best = k
    return best


def label(specs, fk):
    s = specs.get(fk)
    return (s or {}).get('label') or fk.split('/')[0]


def _label_of(ref, specs):
    if isinstance(ref, str) and ref.startswith('core:'):
        return core_label(ref)
    k = ref_key(ref, specs)
    return label(specs, k) if k else str(ref).replace('x:', '').split('/')[0]


def own_on(s):
    return s.get('enabled') is not False


def effective_on(specs, fk, _seen=None):
    """R9: the model's switch and its base's effective switch are both on. A missing base is off."""
    s = specs.get(fk)
    if s is None or not own_on(s):
        return False
    base = s.get('base') or ''
    if base.startswith('x:'):
        bk = ref_key(base, specs)
        if bk is None or bk == fk or (_seen and bk in _seen):
            return False
        return effective_on(specs, bk, (_seen or set()) | {fk})
    return True


def children_of(specs, fk):
    """The file keys of the models whose base is `fk`."""
    return [k for k, s in specs.items() if ref_key(s.get('base'), specs) == fk and k != fk]


def names(spec, specs=None, creating=False):
    """R11: [(code, sentence)] for a spec's own names. With `creating`, a name already in `specs` (any version) is taken."""
    out, n = [], spec.get('name') or ''
    lab = spec.get('label') or n
    if creating and any(s.get('name') == n for s in (specs or {}).values()):
        out.append(('NAME_TAKEN', 'a model called %s is already there' % lab))
    if n in RESERVED or n.startswith('_') or any(n == h or n.startswith(h + '_') for h in CORE_HEADS):
        out.append(('NAME_RESERVED', 'that name belongs to the app'))
    seen = set()
    taken = [f['name'] for f in spec.get('fields') or []] + [l['name'] for l in spec.get('links') or []]
    for nm in taken:
        if nm in RESERVED or nm.startswith('_'):
            out.append(('FIELD_NAME', '%s is a name the app keeps' % nm))
        elif nm in seen:
            out.append(('FIELD_NAME', '%s is used twice in %s' % (nm, lab)))
        seen.add(nm)
    for f in spec.get('fields') or []:
        for a in f.get('aliases') or []:
            if a in seen and a != f['name']:
                out.append(('FIELD_NAME', '%s is used twice in %s' % (a, lab)))
    return out


def base_ok(spec, specs, core):
    """The base is core and extensible, or a model of the owner's (R12). [(code, sentence)]."""
    base = spec.get('base') or ''
    if base.startswith('core:'):
        name = base[5:]
        if name in EXTENSIBLE_CORE and (base in core or name == 'record'):
            return []
        return [('BASE_UNKNOWN', '%s cannot be built on' % core_label(base))]
    if ref_key(base, specs) is None:
        return [('BASE_UNKNOWN', 'there is no model %s to build on' % base[2:].split('/')[0])]
    return []


def base_off(specs, fk):
    """R9, at a save: the model is to be on and its base is effectively off. A load never asks: a child follows its base."""
    s = specs[fk]
    bk = ref_key(s.get('base'), specs)
    if own_on(s) and bk and not effective_on(specs, bk):
        return [('BASE_OFF', '%s is off; turn it on first' % label(specs, bk))]
    return []


def version_chain(specs):
    """R10: version N names version N-1 as its parent. {file key: [(code, sentence)]}."""
    out = {}
    for fk, s in specs.items():
        v, parent = s['version'], s.get('parent')
        prev = '%s/v%d' % (s['name'], v - 1)
        if v > 1 and (parent != 'x:' + prev or prev not in specs):
            out.setdefault(fk, []).append(('VERSION_PARENT', 'there is no version %d to build version %d on' % (v - 1, v)))
        elif v == 1 and parent:
            out.setdefault(fk, []).append(('VERSION_PARENT', 'version 1 has nothing to build on'))
    return out


def _nest_graph(specs):
    g = {}
    for fk, s in specs.items():
        g[fk] = []
        for l in s.get('links') or []:
            if l.get('mode') == 'nest' and l.get('enabled') is not False:
                t = ref_key(l.get('to'), specs)
                if t:
                    g[fk].append(t)
    return g


def _depth(g, fk, seen=()):
    if fk in seen:
        return 0
    return 1 + max([_depth(g, t, seen + (fk,)) for t in g.get(fk, [])] or [0])


def discriminator_faults(specs, fk):
    """R8: every concrete child of a family has the discriminator as a one-value choice, and no two share the value."""
    s = specs[fk]
    d = s.get('discriminator')
    if not d or not s.get('abstract'):
        return []
    out, seen = [], {}
    for ck in children_of(specs, fk):
        c = specs[ck]
        if c.get('abstract'):
            continue
        f = next((x for x in c.get('fields') or [] if x['name'] == d), None)
        if f is None or f.get('type') != 'choice' or len(f.get('choices') or []) != 1:
            out.append(('DISCRIMINATOR', '%s has no one-value %s' % (c['label'], d)))
            continue
        tag = f['choices'][0]
        if tag in seen:
            out.append(('DISCRIMINATOR', '%s and %s both say %s is %s' % (seen[tag], c['label'], d, tag)))
        seen[tag] = c['label']
    return out


def check(specs, core):
    """Every rule of A4.5.5 over the whole set. {'x.<name>/v<N>': [(code, sentence)]}, only keys with a fault."""
    out = {}

    def add(fk, code_sentences):
        if code_sentences:
            out.setdefault(ek(fk), []).extend(code_sentences)
    g = _nest_graph(specs)
    cyc = rules.nest_cycle(g)
    for fk, s in specs.items():
        lab = s.get('label') or s['name']
        size = len(json.dumps(s, default=str))
        if size > LIMITS['spec_bytes']:
            add(fk, [('TOO_BIG', '%s is more than 64 KB' % lab)])
        if len(s.get('fields') or []) > LIMITS['fields']:
            add(fk, [('TOO_MANY', 'a model holds at most %d fields' % LIMITS['fields'])])
        if len(s.get('links') or []) > LIMITS['links']:
            add(fk, [('TOO_MANY', 'a model holds at most %d links' % LIMITS['links'])])
        add(fk, names(s))
        add(fk, base_ok(s, specs, core))
        for l in s.get('links') or []:
            to = l.get('to') or ''
            if to.startswith('core:'):
                if l.get('mode') != 'nest' or to[5:] not in NESTABLE_CORE:
                    add(fk, [('LINK_TARGET', '%s cannot be held by %s' % (core_label(to), lab))])
                continue
            tk = ref_key(to, specs)
            if tk is None:
                add(fk, [('LINK_TARGET', 'there is no model %s to link to' % to[2:].split('/')[0])])
            elif specs[tk].get('abstract') and not children_of(specs, tk) and l.get('mode') == 'nest':
                add(fk, [('LINK_TARGET', '%s has nothing built on it yet' % label(specs, tk))])
        add(fk, discriminator_faults(specs, fk))
        if _depth(g, fk) > LIMITS['nest_depth']:
            add(fk, [('TOO_DEEP', '%s nests more than %d deep' % (lab, LIMITS['nest_depth']))])
    if cyc:
        add(cyc[0], [('CYCLE', '%s: a circle' % ', '.join(label(specs, k) for k in cyc))])
    for fk, fs in version_chain(specs).items():
        add(fk, fs)
    # a base that is its own ancestor
    for fk in specs:
        seen, cur = {fk}, ref_key(specs[fk].get('base'), specs)
        while cur:
            if cur in seen:
                add(fk, [('CYCLE', '%s builds on itself' % label(specs, fk))])
                break
            seen.add(cur)
            cur = ref_key(specs[cur].get('base'), specs)
    return out


def new_link_faults(old, new, specs):
    """A link added by an edit may not point at a model that is off (R9); one that was already there is only reported."""
    out = []
    had = {l['name'] for l in (old or {}).get('links') or []}
    for l in new.get('links') or []:
        if l['name'] in had:
            continue
        tk = ref_key(l.get('to'), specs)
        if tk and not effective_on(specs, tk):
            out.append(('LINK_TARGET', '%s is off' % label(specs, tk)))
    return out


def compare_specs(old, new):
    """The faults of a revision of a saved spec: a field keeps its type (FIELD_TYPE_FIXED) and is retired, never removed
    (FIELD_DROPPED)."""
    out, nf = [], {f['name']: f for f in new.get('fields') or []}
    renamed = {a: f for f in nf.values() for a in f.get('aliases') or []}
    for f in old.get('fields') or []:
        g = nf.get(f['name']) or renamed.get(f['name'])
        if g is None:
            out.append(('FIELD_DROPPED', 'a field is retired, never removed'))
        elif g.get('type') != f.get('type'):
            out.append(('FIELD_TYPE_FIXED', 'a field keeps its type; make a new model'))
    nl = {l['name'] for l in new.get('links') or []}
    for l in old.get('links') or []:
        if l['name'] not in nl:
            out.append(('FIELD_DROPPED', 'a link is turned off, never removed'))
    return out


def core_locked(key):
    """A key that names a core model: [(code, sentence)]."""
    if isinstance(key, str) and (key.startswith('core:') or (not key.startswith('x.') and key.split('/')[0] in EXTENSIBLE_CORE + NESTABLE_CORE)):
        return [('CORE_LOCKED', '%s is part of the app and cannot be changed' % core_label(key))]
    return []


def classify(old_cls, new_cls):
    """How the new class stands against the old one, by rules.compare: 'same', 'tightens', 'widens' or 'mixed'."""
    return rules.compare(old_cls, new_cls)
