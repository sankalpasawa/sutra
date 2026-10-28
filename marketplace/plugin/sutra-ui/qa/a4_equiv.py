"""The equivalence proof of PRD amendment A4 (A4.3.7): the pydantic port against the oracle, on the same inputs.

    python qa/a4_equiv.py --check [--only NAMES] [--fuzz N] [--seed S]   P1 (same verdict), P2 (same sentences), P4 (every keyword hit)
    python qa/a4_equiv.py --record DIR [pytest files]                    what the suite validates, to DIR/<definition>.jsonl
    python qa/a4_equiv.py --write-golden [DIR]                           the golden corpus and CORPUS.sha (A4-PORT P0 writes it from the oracle)
    python qa/a4_equiv.py --bench [--only NAMES]                         the port against the oracle on each definition's good sample (P6)
    python qa/a4_equiv.py --mixins                                       fields that are byte-identical in three or more definitions (R5)

Four sources of input: the samples (the good and the failing example of every definition), mutants of a good value, the writers'
output (recorded by qa/a4_record.py) and seeded fuzz. The oracle is layer_schema as it stands (`oracle`); A4-PORT re-points it to
layer_models.legacy, the frozen literal definitions. The port is whatever `port_classes()` finds: the 130 definitions of layer_models. No allow-list of differences exists, and none is added."""
import argparse
import copy
import hashlib
import json
import random
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
for _p in (str(UI), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import layer_schema as S                                                    # noqa: E402

SEED = 20261027
GOLDEN_DIR = UI / 'test_fixtures' / 'models' / 'corpus' / 'golden'
KINDS = [None, True, 0, 7, -1, 2.5, 3.0, '', 'x', 'D1', [], [1], {}, {'a': 1}, 'a' * 5000, '\x01', 'a\nb', '{{x}}', 'Return ONLY',
         'abc\n', float('nan')]
CANDS = ['x', 'Plan', 'D1', 'F1', 'identity/v1', 'r-0123abcd', 'Q-1', '2026-10-27', 'engine/a-b', 'go', 'abc def', 'a_b:c.d',
         'pending', 'publish', 'ask', 'library', 'run it', 'Write', 'accept', 'words', 'adaptation',
         'ab.cd', 'BL-1', 'J1', 'J1.a', 'J1.1', 'J1/step/1', 'J1:2', 'S1', 'RULED', 'a.py::t', 'js:a.js#W1', 'FI1', '1', '4a']


# ---- the two sides --------------------------------------------------------------------------------------------------------
def oracle(name, value):
    """The sentences of the oracle: the frozen walker over the frozen literal definitions (layer_models.legacy)."""
    import layer_models.legacy as L
    return L.oracle(name, value)


def port_classes():
    """{definition name: class or annotation} of the port: the 130 definitions of layer_models, over the trial's six for a name
    nobody registered (none, once the port is complete)."""
    import a4_trial
    import layer_models
    reg = layer_models.load()
    found = dict(a4_trial.EXPORTED, **reg.DEF_CLASS, **reg.DEF_TYPE)
    return {n: t for n, t in found.items() if n in S.DEFS}               # a family such as identity.ask.form is not a definition


_ADAPTERS = {}


def port(name, value):
    """The sentences of the port; an exception is a difference, never a crash."""
    from layer_models.faults import sentences
    from pydantic import TypeAdapter
    try:
        ad = _ADAPTERS.get(name)
        if ad is None:
            ad = _ADAPTERS[name] = TypeAdapter(port_classes()[name])
        return sentences(ad, value)
    except Exception as e:                                                  # noqa: BLE001
        return ['EXCEPTION %s: %s' % (type(e).__name__, str(e)[:120])]


# ---- source 1: the samples ------------------------------------------------------------------------------------------------
def seeds():
    """{definition name: [value, ...]}: the good and the failing example of every definition and every department key."""
    import test_layer_schema as T
    out = {}
    for name, pair in T.SAMPLES.items():
        out[name] = [copy.deepcopy(v) for v in pair]
    for key in T.DEPARTMENT:
        out['department.' + key] = [copy.deepcopy(T.DEPARTMENT[key]), copy.deepcopy(T.DEPARTMENT_BAD[key])]
    return out


# ---- source 2: mutants ----------------------------------------------------------------------------------------------------
class _Nothing:
    pass


NONE = _Nothing()


def node(schema):
    if '$ref' in schema:
        return node(S.DEFS[schema['$ref'].rsplit('/', 1)[-1]])
    return schema


def good(sch, full=False, depth=0, alt=False):
    """A value that fits the legacy schema `sch` (found, not proved: the oracle is asked), or NONE."""
    sch = node(sch)
    if depth > 6:
        return NONE
    if 'enum' in sch:
        return sch['enum'][0]
    if 'const' in sch:
        return sch['const']
    if 'anyOf' in sch:
        for b in (reversed(sch['anyOf']) if alt else sch['anyOf']):      # alt: the last shape that fits, so every shape is tried
            g = good(b, full, depth + 1, alt)
            if g is not NONE:
                return g
        return NONE
    t = sch.get('type')
    if t == 'string':
        for c in CANDS:
            if not S.faults(sch, c):
                return c
        return NONE
    if t == 'integer':
        lo = sch.get('minimum', 0)
        return max(lo, 1) if sch.get('maximum', 10 ** 9) >= max(lo, 1) else lo
    if t == 'number':
        return sch.get('minimum', 0) if sch.get('minimum', 0) else 0.5
    if t == 'boolean':
        return True
    if t == 'null':
        return None
    if t == 'array':
        out = []
        for _ in range(max(sch.get('minItems', 0), 1 if full else 0)):
            g = good(sch['items'], full, depth + 1, alt) if 'items' in sch else 1
            if g is NONE:
                return NONE
            out.append(g)
        return NONE if sch.get('uniqueItems') and len(out) > 1 else out
    if t == 'object':
        out, props = {}, sch.get('properties')
        if props is not None:
            for k in (list(props) if full else list(sch.get('required') or [])):
                g = good(props[k], full, depth + 1, alt)
                if g is not NONE:
                    out[k] = g
        elif isinstance(sch.get('additionalProperties'), dict) and full:
            g = good(sch['additionalProperties'], full, depth + 1, alt)
            key = next((c for c in CANDS + ['D1'] if not S.faults({'propertyNames': sch.get('propertyNames') or {}, 'type': 'object'}, {c: 1})), 'D1')
            if g is not NONE:
                out[key] = g
        return out
    return 1


def paths(v, p=()):
    yield p
    if isinstance(v, dict):
        for k in list(v):
            yield from paths(v[k], p + (k,))
    elif isinstance(v, (list, tuple)):
        for i in range(len(v)):
            yield from paths(v[i], p + (i,))


def at(v, p):
    for s in p:
        v = v[s]
    return v


def put(v, p, new):
    if not p:
        return new
    v = copy.deepcopy(v)
    cur = v
    for s in p[:-1]:
        cur = cur[s]
    cur[p[-1]] = new
    return v


def drop(v, p):
    v = copy.deepcopy(v)
    cur = v
    for s in p[:-1]:
        cur = cur[s]
    del cur[p[-1]]
    return v


def mutants(v, rng=None):
    """The grid of A4.3.7 from one good value: every path set to each of 21 values of the wrong kind; an extra key, a key that is not
    a word, the keys reversed, each key dropped; a list doubled, padded to 30, emptied, given a null, turned into a tuple; each
    string given a line break, a control character, '{{', '}}', 'Return ONLY', 400 and 5,000 characters, emptied; each number set
    to -1, 0, 2, 99, 100, 1e9, 0.5, 1.0."""
    yield v
    for p in list(paths(v)):
        cur = at(v, p)
        for k in KINDS:
            yield put(v, p, copy.deepcopy(k))
        if isinstance(cur, dict):
            yield put(v, p, dict(cur, zzextra=1))
            yield put(v, p, dict(cur, **{'bad key!': 1}))
            yield put(v, p, dict(reversed(list(cur.items()))))
            for k in list(cur):
                yield drop(v, p + (k,))
        if isinstance(cur, list):
            yield put(v, p, cur + cur)
            yield put(v, p, cur + [cur[0]] * 30 if cur else [1] * 30)
            yield put(v, p, cur + [cur[0]] * 70 if cur else [1] * 70)
            yield put(v, p, [])
            yield put(v, p, tuple(cur))
            if cur:
                yield put(v, p, cur + [None])
        if isinstance(cur, str):
            for suf in ('\n', '\x01', '{{', '}}', 'Return ONLY', 'z' * 400, 'z' * 5000):
                yield put(v, p, cur + suf)
            yield put(v, p, '')
        if isinstance(cur, (int, float)) and not isinstance(cur, bool):
            for n in (-1, 0, 2, 99, 100, 1e9, 0.5, 1.0):
                yield put(v, p, n)


# ---- source 4: fuzz -------------------------------------------------------------------------------------------------------
def _random_json(rng, depth=0):
    r = rng.random()
    if depth > 2 or r < 0.5:
        return copy.deepcopy(rng.choice(KINDS + [rng.randint(-5, 200), rng.random() * 100, rng.choice(CANDS), 'k' * rng.randint(0, 60)]))
    if r < 0.75:
        return [_random_json(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {rng.choice(CANDS + ['id', 'name']): _random_json(rng, depth + 1) for _ in range(rng.randint(0, 3))}


def fuzz(v, rng, n):
    """Seeded: one or two paths of `v` replaced by a random JSON value."""
    ps = list(paths(v))
    for _ in range(n):
        try:
            out = put(v, rng.choice(ps), _random_json(rng))
            if rng.random() < 0.5:
                out = put(out, rng.choice(list(paths(out))), _random_json(rng))
            yield out
        except (TypeError, KeyError, IndexError):
            continue


def bases(name, extra=()):
    """The good values a definition's inputs are made from: its good sample and the ones found by asking the oracle."""
    sch = S.DEFS[name]
    found = []
    for cand in list(extra) + [good(sch, False), good(sch, True), good(sch, True, alt=True)]:
        if cand is not NONE and not oracle(name, cand) and cand not in found:
            found.append(cand)
    return found


def inputs(name, seed_values, rng, fuzz_n):
    """Every input of a definition, in a fixed order, each once."""
    seen = set()
    good_ones = bases(name, [v for v in seed_values[:1]])
    for base in good_ones:
        stream = [mutants(base), fuzz(base, rng, fuzz_n)]
        for s in stream:
            for m in s:
                key = repr(m)
                if key not in seen:
                    seen.add(key)
                    yield m
    for v in seed_values:
        key = repr(v)
        if key not in seen:
            seen.add(key)
            yield v


# ---- the keywords (P4) ----------------------------------------------------------------------------------------------------
KEYWORDS = ('type', 'enum', 'const', 'minLength', 'maxLength', 'pattern', 'range', 'items', 'unique', 'required', 'closed',
            'keys', 'anyOf', 'x-say', 'x-field')


def uses(name):
    """The keyword kinds a definition has, following its $refs (but not into a shape of an any-of that is itself a definition)."""
    found, seen = set(), set()

    def walk(s):
        if not isinstance(s, dict):
            return
        if '$ref' in s:
            n = s['$ref'].rsplit('/', 1)[-1]
            if n not in seen:
                seen.add(n)
                walk(S.DEFS.get(n))
        if 'type' in s:
            found.add('type')
        for k, kind in (('enum', 'enum'), ('const', 'const'), ('maxLength', 'maxLength'), ('pattern', 'pattern'),
                        ('maxItems', 'items'), ('uniqueItems', 'unique'), ('anyOf', 'anyOf'), ('x-say', 'x-say'),
                        ('x-field', 'x-field')):
            if s.get(k):
                found.add(kind)
        if s.get('minLength'):
            found.add('minLength')
        if s.get('minItems'):
            found.add('items')
        if 'minimum' in s or 'maximum' in s:
            found.add('range')
        if s.get('required'):
            found.add('required')
        if s.get('additionalProperties') is False:
            found.add('closed')
        if (s.get('propertyNames') or {}).get('pattern'):
            found.add('keys')
        for v in (s.get('properties') or {}).values():
            walk(v)
        walk(s.get('items'))
        if isinstance(s.get('additionalProperties'), dict):
            walk(s['additionalProperties'])
        for i, b in enumerate(s.get('anyOf') or []):
            if i == 0 and '$ref' not in b:   # a shape that is a definition is proved on its own; the walker shows only a failing
                walk(b)                      # anyOf's first shape's first fault, so what is inside any other shape cannot show
    walk(S.DEFS[name])
    return found


def hit(sentence):
    """The keyword kinds a sentence shows."""
    t = sentence.split(': ', 1)[-1]
    if t in ('is not a string', 'is not a whole number', 'is not a number', 'is not true or false', 'is not a list', 'is not an object', 'is not null'):
        return {'type'}
    if t.startswith('is not one of'):
        return {'enum'}
    if t == 'is not a field here':
        return {'closed'}
    if t.startswith('is not '):
        return {'const'}
    if t.startswith('shorter than'):
        return {'minLength'}
    if t.startswith('longer than'):
        return {'maxLength'}
    if t.startswith('does not match'):
        return {'pattern'}
    if t.startswith('below') or t.startswith('above'):
        return {'range'}
    if t.startswith('fewer than') or t.startswith('more than'):
        return {'items'}
    if t == 'holds an item twice':
        return {'unique'}
    if t == 'is missing':
        return {'required'}
    if t.startswith('the key does not match'):
        return {'keys'}
    if t.startswith('fits none'):                       # the shape's own fault is the keyword that rejected
        return {'anyOf'} | hit(t[t.index('(') + 1:-1])
    if t == 'holds a control character':
        return {'x-say', 'x-field'}
    if t.startswith('holds'):
        return {'x-field'}
    return set()


# ---- the differential -----------------------------------------------------------------------------------------------------
def compare(name, oracle_fn, port_fn, values, show=10):
    """Run both sides on every value. Returns {'inputs', 'rejected', 'verdict', 'sentences', 'hits', 'first'}: the counts of the
    differences in accept/reject and in the list of sentences (in order), the keyword kinds the rejections hit and the first
    `show` differences, each with both lists."""
    rep = {'inputs': 0, 'rejected': 0, 'verdict': 0, 'sentences': 0, 'hits': {}, 'first': []}
    for v in values:
        a, b = oracle_fn(name, v), port_fn(name, v)
        rep['inputs'] += 1
        rep['rejected'] += bool(a)
        for s in a:
            for k in hit(s):
                rep['hits'][k] = rep['hits'].get(k, 0) + 1
        if bool(a) != bool(b):
            rep['verdict'] += 1
        if a != b:
            rep['sentences'] += 1
            if len(rep['first']) < show:
                rep['first'].append({'value': json.dumps(v, default=str)[:300], 'oracle': a, 'port': b})
    return rep


def missed(name, rep):
    """P4: the keyword kinds the definition has and no rejecting input hit."""
    return sorted(uses(name) - set(rep['hits']))


def check(only=None, fuzz_n=500, seed=SEED, out=sys.stdout):
    """P1, P2 and P4 over the definitions the port has (all of them, or `only`). Returns {name: report}."""
    have = port_classes()
    seed_values = seeds()
    reports = {}
    for name in sorted(have):
        if only and name not in only:
            continue
        rng = random.Random(seed)
        rep = compare(name, oracle, port, inputs(name, seed_values.get(name, []), rng, fuzz_n))
        rep['missed'] = missed(name, rep)
        reports[name] = rep
        print('%-24s inputs %6d  rejected by the oracle %6d  verdict differences %d  sentence differences %d  keywords not hit %s'
              % (name, rep['inputs'], rep['rejected'], rep['verdict'], rep['sentences'], rep['missed'] or '-'), file=out)
        for f in rep['first']:
            print('  value  :', f['value'], file=out)
            print('  oracle :', f['oracle'], file=out)
            print('  port   :', f['port'], file=out)
    print('TOTAL inputs %d  rejected %d  differences %d' % (sum(r['inputs'] for r in reports.values()),
          sum(r['rejected'] for r in reports.values()), sum(r['sentences'] for r in reports.values())), file=out)
    return reports


# ---- the golden corpus ----------------------------------------------------------------------------------------------------
def template(sentence):
    """A sentence with its place and its numbers and quoted parts taken out: one template per kind of fault."""
    t = sentence.split(': ', 1)[-1]
    t = re.sub(r'\(.*\)', '(_)', t)
    t = re.sub(r"'[^']*'", "'_'", t)
    t = re.sub(r'^(is not one of|is not|does not match|the key does not match) .*$', r'\1 _', t)
    return re.sub(r'\d+(\.\d+)?', 'N', t)


def golden_lines(name, seed_values, seed=SEED, cap=150, seeded=30):
    """At most `cap` lines of JSON for a definition: each distinct sentence template once, then `seeded` values chosen by seed."""
    rng = random.Random(seed)
    pool = list(inputs(name, seed_values, rng, 0))
    lines, seen, chosen = [], set(), set()
    for i, v in enumerate(pool):
        a = oracle(name, v)
        fresh = {template(s) for s in a} - seen
        if fresh and len(lines) < cap - seeded:
            seen |= fresh
            chosen.add(i)
            lines.append(i)
    rest = [i for i in range(len(pool)) if i not in chosen]
    pick = sorted(random.Random(seed).sample(rest, min(seeded, len(rest))))
    out = []
    for i in lines + pick:
        out.append(json.dumps({'value': pool[i], 'faults': oracle(name, pool[i])}, sort_keys=True, ensure_ascii=False, default=str))
    return out[:cap]


def write_golden(out_dir=GOLDEN_DIR, names=None, seed=SEED):
    """Writes one file per definition and CORPUS.sha beside them; returns the sha256 of the files in definition order."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_values = seeds()
    h = hashlib.sha256()
    for name in (names or sorted(S.DEFS)):
        body = '\n'.join(golden_lines(name, seed_values.get(name, []), seed)) + '\n'
        (out_dir / (name + '.jsonl')).write_text(body, encoding='utf-8')
        h.update(name.encode('utf-8') + b'\n' + body.encode('utf-8'))
    sha = h.hexdigest()
    (out_dir / 'CORPUS.sha').write_text(sha + '\n', encoding='utf-8')
    return sha


# ---- the benchmark and the mixin finder -----------------------------------------------------------------------------------
def bench(only=None, n=2000, out=sys.stdout):
    """Median microseconds of one validation of a definition's good sample, oracle and port. Returns {name: (oracle, port)}."""
    from layer_models.faults import sentences  # noqa: F401
    from pydantic import TypeAdapter
    seed_values = seeds()
    res = {}
    for name in sorted(port_classes()):
        if only and name not in only:
            continue
        good_ones = bases(name, seed_values.get(name, [])[:1])
        if not good_ones:
            continue
        v = good_ones[-1]
        ad = TypeAdapter(port_classes()[name])

        def med(f):
            t = []
            for _ in range(n):
                s = time.perf_counter()
                f()
                t.append(time.perf_counter() - s)
            return statistics.median(t) * 1e6
        d = S.DEFS[name]
        res[name] = (med(lambda: S.faults(d, v)), med(lambda: ad.validate_python(v)))
        print('%-24s oracle %7.1f us  port %7.1f us  ratio %.2f' % (name, res[name][0], res[name][1], res[name][1] / res[name][0]), file=out)
    if res:
        o, p = sum(a for a, _ in res.values()), sum(b for _, b in res.values())
        print('ALL                      oracle %7.1f us  port %7.1f us  ratio %.2f' % (o, p, p / o), file=out)
    return res


def mixins(minimum=3):
    """[(field name, schema, [definitions])]: a field that is byte-identical in `minimum` or more definitions, most shared first."""
    seen = {}
    for dname, d in S.DEFS.items():
        if not isinstance(d, dict):
            continue
        for fname, sch in (d.get('properties') or {}).items():
            seen.setdefault((fname, json.dumps(sch, sort_keys=True)), []).append(dname)
    rows = [(f, json.loads(s), sorted(ds)) for (f, s), ds in seen.items() if len(ds) >= minimum]
    rows.sort(key=lambda r: (-len(r[2]), r[0]))
    return rows


# ---- the command line -----------------------------------------------------------------------------------------------------
RECORD_FILES = ['test_layer_schema.py', 'test_j2.py', 'test_j2_api.py', 'test_j1.py', 'test_dept_api.py', 'test_org2_api.py',
                'test_function_templates.py']


def record(dest, files=None):
    """Runs pytest on the lanes with the recorder plugin; the values land in dest/<definition>.jsonl."""
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'a4_record', '--a4-record-dir', str(dest)]
    env = dict(__import__('os').environ, PYTHONPATH=str(HERE) + ':' + str(UI))
    return subprocess.run(cmd + list(files or RECORD_FILES), cwd=str(UI), env=env).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--record', metavar='DIR')
    ap.add_argument('--write-golden', nargs='?', const=str(GOLDEN_DIR), metavar='DIR')
    ap.add_argument('--bench', action='store_true')
    ap.add_argument('--mixins', action='store_true')
    ap.add_argument('--only', default='', help='comma-separated definition names')
    ap.add_argument('--fuzz', type=int, default=500)
    ap.add_argument('--seed', type=int, default=SEED)
    ap.add_argument('files', nargs='*', help='with --record: the pytest files to run')
    a = ap.parse_args(argv)
    only = [n for n in a.only.split(',') if n]
    rc = 0
    if a.check:
        reports = check(only, a.fuzz, a.seed)
        rc |= 1 if any(r['sentences'] or r['verdict'] or r['missed'] for r in reports.values()) else 0
    if a.record:
        rc |= record(a.record, a.files)
    if a.write_golden:
        print('CORPUS_SHA', write_golden(a.write_golden, only or None, a.seed))
    if a.bench:
        res = bench(only)
        rc |= 1 if any(b > o for o, b in res.values()) else 0                  # P6: no definition slower than the oracle
    if a.mixins:
        for f, sch, ds in mixins():
            print('%-16s in %2d: %s  %s' % (f, len(ds), json.dumps(sch, sort_keys=True)[:80], ', '.join(ds[:6])))
    return rc


if __name__ == '__main__':
    sys.exit(main())
