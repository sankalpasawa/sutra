"""The sentences: ValidationError.errors() translated into the lines layer_schema.faults() writes (A4.3.3).

`explain` turns the errors into [(loc, sentence)] in the walker's order; `sentences` joins a path to each. Pydantic's own message
and the input it quotes never reach an owner or a log: nothing here reads `msg` of an error that is not ours, and no code prints
`str(ValidationError)`."""
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

UNMAPPED_SENTENCE = 'does not fit'
#: the error types this module has a sentence for (the classes of the interface raise no other); a type outside the table is
#: answered with UNMAPPED_SENTENCE, and its name is left in UNMAPPED so a gap is never silent (a test fails on a non-empty set)
TABLE = ('sutra_type', 'sutra_faults', 'missing', 'extra_forbidden', 'model_type', 'model_attributes_type', 'dict_type',
         'list_type', 'union_tag_invalid', 'union_tag_not_found')
UNMAPPED = set()


def faults_error(faults, at=()):
    """One error that carries several sentences: `faults` at the error's own place, `at` as [(relative loc, sentence)] below it."""
    return PydanticCustomError('sutra_faults', 'faults', {'faults': list(faults), 'at': [[list(l), s] for l, s in at]})


def type_error(sentence):
    """One error whose whole content is a sentence. The sentence rides in the context, never in the message template, so a
    '{' in a value cannot be taken for a placeholder."""
    return PydanticCustomError('sutra_type', 'type', {'sentence': sentence})


def path(loc):
    """['a', 2, 'b'] -> '$.a[2].b', the walker's form."""
    out = '$'
    for p in loc:
        out += '[%d]' % p if isinstance(p, int) else '.%s' % p
    return out


def _tags(raw):
    """pydantic writes the expected tags as "'circle', 'square'": the words without the quotes."""
    return ', '.join(t.strip().strip("'\"") for t in str(raw).split(', '))


def _rows(errors):
    """[(loc, sentence, arrival)] before sorting."""
    pairs, seq = [], 0
    for e in errors:
        t, loc = e['type'], tuple(e['loc'])
        ctx = e.get('ctx') or {}
        seq += 1
        if t == 'sutra_faults':
            for s in ctx.get('faults', []):
                pairs.append((loc, s, seq))
            for rel, s in ctx.get('at', []):
                pairs.append((loc + tuple(rel), s, seq))
        elif t == 'sutra_type':
            pairs.append((loc, ctx.get('sentence', UNMAPPED_SENTENCE), seq))
        elif t == 'missing':
            pairs.append((loc, 'is missing', seq))
        elif t == 'extra_forbidden':
            pairs.append((loc, 'is not a field here', seq))
        elif t in ('model_type', 'model_attributes_type', 'dict_type'):
            pairs.append((loc, 'is not an object', seq))
        elif t == 'list_type':
            pairs.append((loc, 'is not a list', seq))
        elif t == 'union_tag_invalid':
            pairs.append((loc + (str(ctx.get('discriminator', '')).strip("'\""),), 'is not one of %s' % _tags(ctx.get('expected_tags', '')), seq))
        elif t == 'union_tag_not_found':
            pairs.append((loc + (str(ctx.get('discriminator', '')).strip("'\""),), 'is missing', seq))
        else:
            UNMAPPED.add(t)
            pairs.append((loc, UNMAPPED_SENTENCE, seq))
    return pairs


def explain(errors, value):
    """[(loc tuple, sentence)] in the order the walker writes them: inside an object the missing keys first (in the order they
    arrive), then each key in the order the INPUT has them; inside a list by index; a fault of a container before those of its
    members. A location step that is neither a key nor an index of the input at its depth, and is not the last, is a union
    tag and is dropped."""
    index = {}                                                    # id(dict) -> {key: position}, built once per dict

    def position(d, step):
        m = index.get(id(d))
        if m is None:
            m = index[id(d)] = {k: i for i, k in enumerate(d)}
        return m.get(step)

    rows = []
    for loc, sentence, seq in _rows(errors):
        key, clean, cur, last = [], [], value, len(loc) - 1
        for n, step in enumerate(loc):
            if isinstance(cur, dict) and step in cur:
                key.append((0, position(cur, step)))
                cur = cur[step]
            elif isinstance(cur, (list, tuple)) and isinstance(step, int) and 0 <= step < len(cur):
                key.append((0, step))
                cur = cur[step]
            elif n < last:
                continue                                          # a step the input lacks, not the last: a union tag
            else:
                key.append((-1, seq))                            # a key the input lacks (a missing one) sorts first
                clean.append(step)
                break
            clean.append(step)
        rows.append((key, seq, tuple(clean), sentence))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [(loc, s) for _, _, loc, s in rows]


def sentences_and_unmapped(adapter, value):
    """(sentences, unmapped error types) of `value` against a TypeAdapter: ([], []) when it fits."""
    try:
        adapter.validate_python(value)
        return [], []
    except ValidationError as e:
        errors = e.errors(include_url=False, include_input=False, include_context=True)
        unmapped = sorted({x['type'] for x in errors if x['type'] not in TABLE})
        return ['%s: %s' % (path(loc), s) for loc, s in explain(errors, value)], unmapped


def sentences(adapter, value):
    """The faults of `value` as layer_schema.validate() would give them: ['$.a.b[0]: is missing', ...]; [] when it fits."""
    return sentences_and_unmapped(adapter, value)[0]
