"""Independent checks for numbers at the evidence door (matrix gap 9, ruling R22): checks S100 to S109.

This module reads the record and the pack files (and the text of kernel/core.py); it never loads the lab's code. The
kernel reads no number, so numbers are read here in this file's own words: its own grammar for a number (digits with one
optional point, or digits/digits), its own exact comparison (cross-multiplied whole numbers), its own digests.
  S100  a number row is exact text, has no field more or less than a number row has, sits under its own scope and
        predicate, and its version is the digest of its reading.
  S101  a comparison row is the verdict redone from the number, the operator and the bound it names, with a version that
        is the digest of that recipe (every number in lowest terms) and depends_on exactly the numbers it compared; a
        row that names the other row of its band has that row beside it, saying the opposite (a row that names none
        is held as a comparison alone); while the kernel still reads a comparison, its
        numbers are the ones on the books; in a recorded case the number and comparison rows are the rows its pack files
        leave on the books, none of them ignored, turned away or replaced by another writer's row, and no method or
        rule of those packs makes one or stands two steps below one without naming it; a row authored alone, against a
        bound written into the comparison, leaves the goal asking for evidence, also after a new reading made that row
        again.
  S102  every comparisons block of the recorded sequence is rebuilt from the evidence after the run and set against the
        run's own trace; the sequence holds twenty runs, thirteen with a block, each on exactly the packs of its part,
        and no run beside the runs of its looks; every run of it says, beside its trace, what its packs and the books
        after it say (no candidate, the facts its steps were to make, the truth of its goal after it and, unless the
        run makes its goal itself, before it); the four looks the sequence takes again are the recorded cases' looks,
        field for field (so a field no check reads, the `proof` and the truth before of a run that makes its own
        goal, is held to its case's copy and to nothing else); its other runs argue what the
        facts their traces retained and the recorded case of the same branch say (`proof`, `selected_branch`); no run
        outside the sequence carries a block; what the record says of the four cases beside their runs (the scope, the
        rules, the viewer's world and knowledge views) is what their pack files and their books say, every run of
        theirs carries its learning bound to its own trace, and the row each of their steps wrote on its effect is
        TRUE, verified, that step's, resting on the step's prerequisites at the versions on the books.
  S103  under the band a finding is filed and paid, and the finding on the books is the step's row, reading TRUE; in
        band nothing runs; the number with no comparison row beside it leaves the goal asking for evidence, at 0.8 and
        at 1.0.
  S104  a new reading is taken whole (one look, one journal row, the look names both rows of the band as made again and
        both read on the books after it, and no other stored row is touched but the finding a look filed) or not at
        all (six refusals, five in the adapter's words and one, of the flag `execute`, in the kernel's own, leave the
        books as they were); the reading that arrived is the number it replaces but for its value, its label and its
        version, and it is the reading the sequence names; a reading handed to the kernel alone, as an event or in a
        pack, leaves the comparisons unread and the look asking for evidence; after every look the finding is the row
        of the look that filed it, and it reads UNKNOWN from the next reading on. Not held here: that each row made
        again is the row it replaces, redone on the new number with the same operator, bound and other row (S101
        holds each such row to its own recipe and to the numbers on the books, no more). That is the unit test's,
        which makes the sequence again and compares it with the record.
  S105  every cost a run states (its own, the SELECT row's, every ADMISSION row's) is what the packs that run loaded
        give the methods named, in every dimension its State had (the three every State starts with and every one a
        pack it loaded adds); every executed step stands right after the accepted ADMISSION row that names it alone;
        the sequence's cost receipts say the same.
  S106  no fraction reaches a cost or a budget; the loan review's amounts; a pack that adds a budget dimension names it.
  S107  the queue is in the order of its impacts, the second review stops on the ceiling alone, the shortfall is the
        dimension, the need and what was left, and one run later, the run cap set again, it stops on the ceiling again.
  S108  the kernel's source carries no word of this version and the record lists no action kind of it.
  S109  the same claims fail on forged records, forged pack files and a forged kernel source, each changing one thing.
Scope: number and comparison rows are held in the books of this version's four cases and of its sequence, and, where a
row carries the adapter's marks (its source, a `compares` recipe, the kind NUMBER or COMPARISON), in the books of every
other recorded case; costs in every run the record holds (the cases, the event record, the ask record and every
recorded sequence, its runs found by their shape as the verifier finds them). Numbers are compared as JSON (1 is not 1.0
and not true). The kernel is not run here: a sequence made again from end to end is told only by the unit test that makes
it again. Three kinds of record pass these checks and are told only by that unit test: the two rows of a band made
again after a reading with another operator or bound than the rows they replace, or without each other's names, their
verdicts kept; the `proof` or the truth before of a run that makes its own goal, changed alike in every copy; a key
added to a dict that is no row (a snapshot, a look, a run that is no case's look, a part of the sequence).
checks() never raises: a record or a pack file it cannot read is ten failed rows."""
import json, math, hashlib

CMP = 'adapter:numbers/compare@1'
DIGITS = set('0123456789')
HOLDS = {'<': lambda x, y: x < y, '<=': lambda x, y: x <= y, '>': lambda x, y: x > y, '>=': lambda x, y: x >= y, '==': lambda x, y: x == y, '!=': lambda x, y: x != y}
OPPOSITE = {'<': '>=', '<=': '>', '>': '<=', '>=': '<', '==': '!=', '!=': '=='}
NUMBER_ROW = {'predicate', 'truth', 'verified', 'source', 'version', 'value', 'unit', 'label', 'evidence_kind'}
COMPARISON_ROW = {'predicate', 'truth', 'verified', 'source', 'version', 'depends_on', 'compares', 'evidence_kind'}
C63, C64, C65, C66 = '63_conformance_finding', '64_conformance_in_band', '65_loan_review_cost', '66_review_queue'
OURS = (C63, C64, C65, C66)
ALONE = ['150_conformance_goal', '151_conformance_theory', '159_one_row_alone', '153_finding_method']   # the packs of the look on a row authored alone
BARE = ['150_conformance_goal', '151_conformance_theory', '152_number_alone', '153_finding_method']     # the packs of the look on the number with no comparison row beside it
LATE, NEXT = '152_number_alone', '158_run_cap_again'   # the pack that brings a reading to a running State, and the pack of the next run of the queue
S = 'sutra/workflows|'
BLOCKS = ('comparisons', 'comparisons_record', 'shortfall')   # what this version's sequence writes into a run
LEARNT = ('learning', 'learning_record')                      # what the code that records a case writes into a run
BASE = {'compute': 10, 'money': 10, 'attention': 3}           # the budget every State starts with
WORDS = ('Fraction', "'value'", 'compares', 'usd', 'impact', 'NUMBER', 'COMPARISON', 'renumber', 'ceiling', 'shortfall')
REFUSED = {'another scope': 'A number for another scope is not taken here', 'not a row the adapter made': 'Not a number row this adapter made',
           'another unit': 'A new reading keeps the unit of the number it replaces', 'in the place of a comparison': 'A number takes the place of a number only',
           'in the place of a row that is no number': 'A number takes the place of a number only', 'execute is not true or false': 'execute is true or false'}   # the readings the second State of the events could not take, each with the words it was refused in: five are the adapter's, the last is the kernel's own (it refuses the flag `execute` on the copy)
RUNS, WITH_A_BLOCK = 20, 13   # the runs of the sequence, and how many of them name a comparison
MOVES = ('value', 'label', 'version')   # what a new reading of a number changes on its row
NAMES = ('S100_numbers_are_exact_text_versioned_by_their_reading', 'S101_every_comparison_is_redone_from_its_numbers',
         'S102_every_comparisons_block_agrees_with_the_books_and_the_trace', 'S103_under_the_band_a_finding_and_in_band_nothing_runs',
         'S104_a_new_number_is_taken_whole_or_not_at_all', 'S105_every_step_cost_is_the_gates_row', 'S106_fractions_of_cost_are_whole_units',
         'S107_a_ranked_queue_under_a_ceiling', 'S108_the_kernel_reads_no_number_and_no_action_kind_is_added')
LAST = 'S109_number_claims_fail_on_forged_records'


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def same(a, b):   # compared as JSON: 1 is not 1.0 and not true
    return sha(a) == sha(b)


def a_name(v):
    return type(v) is str and bool(v)


def num(t):   # exact text as (numerator, denominator), or None for anything else: a float, a sign, an exponent, a space, an underscore, a digit that is not ASCII
    if type(t) is not str or not 0 < len(t) <= 64:
        return None
    marks = [ch for ch in t if ch not in DIGITS]
    if not marks:
        return (int(t), 1)
    a, _, b = t.partition(marks[0])
    if len(marks) > 1 or marks[0] not in './' or not a or not b or (marks[0] == '/' and int(b) == 0):
        return None
    return (int(a), int(b)) if marks[0] == '/' else (int(a + b), 10 ** len(b))


def lowest(q):
    g = math.gcd(q[0], q[1])
    return f'{q[0] // g}/{q[1] // g}'


def marked(row):   # a row that carries one of the adapter's marks: a value, the kind NUMBER or COMPARISON, the adapter's source, a recipe
    return 'value' in row or row.get('evidence_kind') in ('NUMBER', 'COMPARISON') or row.get('source') == CMP or 'compares' in row


def keyed(key, row):   # a stored row sits under its own scope and predicate
    return a_name(row.get('scope')) and a_name(row.get('predicate')) and key == row['scope'] + '|' + row['predicate']


def number_ok(row):   # a number row: exact text, known and verified, resting on nothing, no field more or less, with a version that is the digest of its reading
    q = num(row.get('value'))
    return (q is not None and set(row) - {'scope'} == NUMBER_ROW and row['truth'] == 'TRUE' and row['verified'] is True and row['evidence_kind'] == 'NUMBER' and row['source'] != CMP
            and all(a_name(row[k]) for k in ('predicate', 'source', 'unit', 'label'))
            and row['version'] == 'num-' + sha({'predicate': row['predicate'], 'value': lowest(q), 'unit': row['unit'], 'label': row['label'], 'source': row['source']})[:16])


def canon(c):   # what a comparison's version is the digest of: the number, the operator and the bound, every number in lowest terms (one number spelled two ways is one comparison); the name of a band's other row is no part of it
    one = lambda part: {k: (lowest(num(v)) if k in ('value', 'literal') else v) for k, v in part.items()}
    return {'number': one(c['number']), 'op': c['op'], 'bound': one(c['bound'])}


def comparison_ok(row):   # a comparison row: the verdict redone from its own recipe, a version that is the digest of the recipe, depends_on exactly what it compared
    c = row.get('compares')
    n = c.get('number') if isinstance(c, dict) else None
    b = c.get('bound') if isinstance(c, dict) else None
    if (not isinstance(n, dict) or not isinstance(b, dict) or set(row) - {'scope'} != COMPARISON_ROW or set(c) - {'partner'} != {'number', 'op', 'bound'} or set(n) != {'predicate', 'value', 'version'}
            or set(b) not in ({'predicate', 'value', 'version'}, {'literal'}) or not isinstance(c['op'], str) or c['op'] not in HOLDS):
        return False
    left, right = num(n['value']), num(b['value'] if 'predicate' in b else b['literal'])
    if left is None or right is None:
        return False
    cites = [{'predicate': n['predicate'], 'version': n['version']}] + ([{'predicate': b['predicate'], 'version': b['version']}] if 'predicate' in b else [])
    return (row['source'] == CMP and row['verified'] is True and row['evidence_kind'] == 'COMPARISON' and a_name(row['predicate']) and not same(row['predicate'], n['predicate'])
            and not same(row['predicate'], b.get('predicate')) and ('partner' not in c or (a_name(c['partner']) and c['partner'] != row['predicate']))
            and row['truth'] == ('TRUE' if HOLDS[c['op']](left[0] * right[1], right[0] * left[1]) else 'FALSE')
            and row['version'] == 'cmp-' + sha(canon(c))[:16] and same(row['depends_on'], cites))


def band_ok(row, facts):   # a row of a band: its other row is on the same books, compares the same number with the same bound by the opposite operator and names it back (so, both being redone, they say the opposite); a row that names no other row is no row of a band and holds here
    c = row['compares']
    if 'partner' not in c:
        return True
    other = facts.get(row['scope'] + '|' + c['partner']) or {}
    d = other.get('compares')
    return (isinstance(d, dict) and other.get('source') == CMP and same(d.get('partner'), row['predicate']) and same(d.get('op'), OPPOSITE[c['op']]) and same(d.get('number'), c['number'])
            and same(d.get('bound'), c['bound']))


def kread(facts, key, seen=()):   # the kernel's reading of a stored row, in this file's words: UNKNOWN unless verified and every dependency reads TRUE at the cited version
    row = facts.get(key)
    if row is None or key in seen or row.get('verified') is not True:
        return 'UNKNOWN'
    for dep in row.get('depends_on', []):
        other = row['scope'] + '|' + dep['predicate']
        if other not in facts or not same(facts[other].get('version'), dep.get('version')) or kread(facts, other, seen + (key,)) != 'TRUE':
            return 'UNKNOWN'
    return row['truth']


def from_books(row, facts):   # a comparison the kernel still reads was computed from the numbers that are on the books: the same version and the same value
    c = row['compares']

    def on_books(x):
        other = facts.get(row['scope'] + '|' + str(x.get('predicate')))
        mine = num(x.get('value'))
        return bool(other) and number_ok(other) and same(other['version'], x.get('version')) and mine is not None and lowest(num(other['value'])) == lowest(mine)
    return all(on_books(x) for x in [c['number']] + ([c['bound']] if 'predicate' in c['bound'] else []))


def block_ok(r, facts):   # a run's comparisons block, rebuilt from the evidence after the run and set against the run's own trace
    rows = [(p, facts.get(r['scope'] + '|' + p) or {}) for p in dict.fromkeys(e['data'].get('predicate') for e in r['trace'] if e['operation'] != 'CYCLE_LIMIT') if isinstance(p, str)]   # a CYCLE_LIMIT row names a predicate the kernel did not read
    want = [{'predicate': p, 'number': row['compares'].get('number'), 'operator': row['compares'].get('op'), 'bound': row['compares'].get('bound'), 'verdict': row['truth'], 'source': CMP,
             'version': row.get('version'), 'reads': kread(facts, r['scope'] + '|' + p)} for p, row in rows if row.get('source') == CMP and isinstance(row.get('compares'), dict)]
    held = {e['data']['predicate']: e['data'] for e in r['trace'] if e['operation'] == 'RETAIN'}
    return (same(r.get('comparisons', []), want) and ('comparisons' in r) == bool(want) and ('comparisons_record' in r) == bool(want)
            and (not want or same(r['comparisons_record'], {'source_trace': r['trace_root_sha256'], 'comparisons_sha256': sha(want)}))
            and all(same(held.get(x['predicate']), {'predicate': x['predicate'], 'source': CMP, 'version': x['version']}) if x['reads'] == 'TRUE' else x['predicate'] not in held for x in want))


def step_costs(r, own, dims):
    """What each executed step cost, or None when the run's trace does not say it the way the kernel does: the accepted ADMISSION row directly before its LOCAL_EFFECT row names
    that step alone and carries, in every dimension of `dims` and in no other, the cost the run's own packs give the method (`own`: method -> its pack's row)."""
    out = []
    t = r['trace']
    for i, e in enumerate(t):
        if e['operation'] != 'LOCAL_EFFECT':
            continue
        rec = e['data']['receipt']
        gate = t[i - 1]['data'] if i and t[i - 1]['operation'] == 'ADMISSION' else {}
        if (gate.get('methods') != [rec['method']] or gate.get('accepted') is not True or rec['method'] not in own
                or not same(gate['cost'], {dim: own[rec['method']].get('cost', {}).get(dim, 0) for dim in dims})
                or ('cost' in rec and not same(rec['cost'], gate['cost']))):   # a receipt that states a cost of its own must state the gate's
            return None
        out.append({'method': rec['method'], 'receipt': rec['sha256'], 'cost': gate['cost']})
    return out


def walk(v):   # every run under a part of the record, found by its shape (a dict that carries a trace and a trace root) wherever it sits: in a list, under any key, inside another run. The verifier's own rule for the runs of a recorded sequence
    if isinstance(v, dict):
        if 'trace' in v and 'trace_root_sha256' in v:
            yield v
        for x in v.values():
            yield from walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk(x)


def base_runs(d):   # every run outside the recorded sequences: both copies of a case's run, and the two event records
    for c in d['cases']:
        if c['outcome']:
            yield c['outcome']
        yield from c['run']['runs']
    for block in ('events', 'ask_events'):
        for v in d[block].values():
            if isinstance(v, dict) and isinstance(v.get('runs'), list):
                yield from v['runs']


def claims(d, SCEN, core):
    """Check name -> held, on a record `d`, the pack files `SCEN` (name -> pack) and the text of the kernel's source."""
    by = {c['id']: c for c in d['cases']}
    lk, nx, ba, al, ne = (d['scenes']['numbers'][part] for part in ('looks', 'next_run', 'bare', 'alone', 'events'))
    of = lambda names: {m['id']: m for n in names for m in SCEN[n].get('methods', [])}                 # the methods of the packs a case names
    own = lambda r: {m['id']: m for p in r['provenance'] for m in SCEN[p['pack']].get('methods', [])}  # the methods of the packs a run says it loaded (a pack that is no pack file gives none: the run does not hold)
    conform = by[C63]['packs']   # the events of the sequence run on the packs of case 63
    finding = of(conform)['file-finding@1']
    purse63, slots63 = SCEN['150_conformance_goal']['budget'], SCEN['153_finding_method']['providers']
    taken = [k for k, v in ne.items() if isinstance(v, dict) and 'runs' in v]
    parts = ([(lk[c]['packs'], lk[c]['after']['facts'], lk[c]['look']) for c in OURS] + [(nx['packs'], nx['after']['facts'], nx['look'])]
             + [(x['packs'], x['after']['facts'], x['look']) for x in (ba, al)] + [(x['packs'], x['after_again']['facts'], x['again']) for x in (ba, al)]
             + [(conform + ([LATE] if k == 'pack_event' else []), ne['after_' + k]['facts'], ne[k]) for k in taken])   # every look of the sequence: the packs its State had loaded, the books right after it, the look
    seen = [r for _, _, x in parts for r in x['runs']]
    books = [by[c]['derived_state']['facts'] for c in OURS] + [facts for _, facts, _ in parts] + [ne['after_refused']['facts']]
    others = [c['derived_state']['facts'] for c in d['cases'] if c['id'] not in OURS]   # the books of every other recorded case: a row there is held when it carries the adapter's marks (any writer may store a `value`)
    numbers = ([(key, row) for facts in books for key, row in facts.items() if 'value' in row or row.get('evidence_kind') == 'NUMBER']
               + [(key, row) for facts in others for key, row in facts.items() if row.get('evidence_kind') == 'NUMBER'])
    made = [(key, row, facts) for facts in books + others for key, row in facts.items() if row.get('source') == CMP or 'compares' in row or row.get('evidence_kind') == 'COMPARISON']

    def left_by(names):
        """What a list of pack files leaves on the books before any run (scope|fact -> row), and the places where a row of the adapter's was lost: ignored, turned away, or replaced
        by a row that is not the adapter's. This file's own copy of the kernel's rule for a row: a pack names the scope before its rows; a row that is not verified is ignored; a
        later row takes the place of an earlier one; a decision stands against an ordinary row."""
        scope, rows, lost, used = 'orgA/fulfillment', {}, [], []
        for n in names:
            scope = SCEN[n].get('scope', scope)
            for o in SCEN[n].get('evidence', []):
                at = o.get('scope', scope)
                key = at + '|' + o['predicate']
                if o.get('verified') is True and not (rows.get(key, {}).get('final') is True and o.get('final') is not True):
                    rows[key] = dict(o, scope=at)
                    used += [key] if marked(o) else []
                elif marked(o):
                    lost.append(key)
        return rows, lost + [key for key in used if not marked(rows[key])]

    def as_packed(names, facts):   # the number and comparison rows on the books are exactly the ones the pack files leave there, row for row, and no row of the adapter's in those files was lost
        rows, lost = left_by(names)
        return not lost and same({key: row for key, row in facts.items() if marked(row)}, {key: row for key, row in rows.items() if marked(row)})
    verdicts = [row['predicate'] for row in left_by(conform)[0].values() if row.get('source') == CMP]

    def adapter_only(names):   # in these packs no method makes and no rule derives a number or a comparison, no step requires a rule head that stands over a comparison, and no step stands two steps below a number or a comparison without requiring that row itself
        rows = [row for row in left_by(names)[0].values() if marked(row)]
        theirs, compared = {row['predicate'] for row in rows}, {row['predicate'] for row in rows if row.get('source') == CMP}
        rules = {r['head']: r for n in names for r in SCEN[n].get('rules', []) if r.get('approved')}
        methods = [m for n in names for m in SCEN[n].get('methods', [])]

        def over(p, path=()):
            r = rules.get(p)
            return bool(r) and p not in path and any(x in compared or over(x, path + (p,)) for branch in r['branches'] for x in branch)

        def below(m):   # the row such a step writes cites the first step's effect at the one version a handler gives it, so it would come back when the first step runs again on another number
            needs = m.get('requires', [])
            return any(x in theirs and x not in needs for q in needs for first in methods if first.get('effect') == q for x in first.get('requires', []))
        return not (theirs & set(rules)) and not any(m.get('effect') in theirs or any(over(q) for q in m.get('requires', [])) or below(m) for m in methods)

    def named(c):   # every pack of a case that adds a budget dimension names it in its own preference
        dims, ok = set(BASE), True
        for n in by[c]['packs']:
            added = set(SCEN[n].get('budget', {})) - dims
            ok = ok and added <= set(SCEN[n].get('preference', []))
            dims |= added
        return ok
    shape = lambda r: [(x['predicate'], x['number']['value'], x['operator'], x['bound'].get('value'), x['verdict'], x['reads']) for x in r.get('comparisons', [])]
    o63, o64, kept63 = by[C63]['outcome'], by[C64]['outcome'], by[C63]['derived_state']['facts']
    found63 = kept63.get(S + 'finding_filed') or {}
    strip = lambda r, keys: {k: v for k, v in r.items() if k not in keys}
    filed_on = lambda facts: dict(found63, depends_on=[{'predicate': 'fitness_below_band', 'version': facts[S + 'fitness_below_band']['version']}])   # the row the finding step writes: the row of case 63, resting on the row below the band at the version on these books
    untouched = lambda snap, journal: same(snap['budget'], purse63) and same(snap['providers'], slots63) and same(snap['journal'], journal)   # nothing ran, nothing was paid
    loaded = lambda r, names: [p.get('pack') for p in r['provenance']] == names   # a run says it loaded exactly these packs, in this order (the verifier holds each one's sha256 to its file)
    stood = lambda x: same(strip(x, ('runs', 'cost_receipts')), {'status': 'EVALUATED', 'goals': ['run_judged']}) and len(x['runs']) == 1   # a standing look of the one goal
    arrived = lambda e, old, predicate, value, label: (number_ok(e) and (e['predicate'], e['value'], e['label']) == (predicate, value, label)
                                                       and same(strip(dict(e, scope=old['scope']), MOVES), strip(old, MOVES)))   # a reading that arrived: the number it replaces, but for its value, its label and its version

    def retaken(c):   # the look the sequence takes of a case is the recorded case's look, field for field, on the same packs and with the same books after it
        mine, case = lk[c], by[c]
        slots = {}   # the provider slots after the look: what the case's packs give, less one for every receipt
        for n in case['packs']:
            slots.update(SCEN[n].get('providers', {}))
        for r in case['run']['runs']:
            for x in r['model_receipts']:
                slots[own(r)[x['method']]['provider']] -= 1
        return (mine['packs'] == case['packs'] and same(mine['after']['facts'], case['derived_state']['facts']) and same(mine['after']['budget'], case['derived_state']['budget_after'])
                and same(mine['after']['journal'], len(case['derived_state']['historical_events'])) and same(mine['after']['providers'], slots)
                and same(strip(mine['look'], ('runs', 'cost_receipts')), strip(case['run'], ('runs',)))
                and same([strip(r, BLOCKS) for r in mine['look']['runs']], [strip(r, LEARNT) for r in case['run']['runs']]))

    def viewed(c):   # what the record says of a case beside its runs is what its pack files and its books say: its scope, its rules (their ids, and the viewer's knowledge view), the viewer's world view row for row; and every run of the case carries its learning bound to its own trace
        case, scope, rules = by[c], 'orgA/fulfillment', {}
        for n in case['packs']:
            scope = SCEN[n].get('scope', scope)
            rules.update({r['head']: r for r in SCEN[n].get('rules', []) if r.get('approved')})
        return (same(case['scope'], scope) and same(case['derived_state']['rule_ids'], [r['id'] for r in rules.values()]) and same(case['four_views']['knowledge'], list(rules.values()))
                and same(case['four_views']['world'], [{'predicate': key, 'truth': row['truth'], 'source': row.get('source')} for key, row in case['derived_state']['facts'].items()])
                and all(same(r.get('learning_record'), {'source_trace': r['trace_root_sha256'], 'learning_sha256': sha(r.get('learning'))}) for r in case['run']['runs']))

    def stepped(c):   # the row every step of a case wrote on its effect, as far as the pack files and the books can say it: TRUE and verified, no decision, from that step, resting on the step's prerequisites at the versions on the books, and read TRUE (its version and its kind are the handler's)
        facts = by[c]['derived_state']['facts']
        for r in by[c]['run']['runs']:
            for x in r['model_receipts']:
                m, at = own(r)[x['method']], r['scope'] + '|'
                row = facts.get(at + m['effect']) or {}
                rests = [{'predicate': q, 'version': facts[at + q]['version']} for q in m.get('requires', [])]
                if not (same([row.get(k) for k in ('predicate', 'truth', 'verified', 'scope', 'depends_on')], [m['effect'], 'TRUE', True, r['scope'], rests]) and 'final' not in row
                        and str(row.get('source')).endswith(':' + x['method']) and kread(facts, at + m['effect']) == 'TRUE'):
                    return False
        return True

    def told(r, facts):   # what a run of the sequence says beside its trace, where the pack files and the books after it can say it: no candidate, the facts its steps were to make, and the truth of its goal before and after (the truth before is not read for a run that makes its goal itself)
        makes = [own(r)[a]['effect'] for a in r['actions']]
        reads = kread(facts, r['scope'] + '|' + r['goal'])
        return (r['candidates'] == [] and r['needs'] == makes and (r['goal'] in makes or r['goal_truth_before'] == reads) and ('goal_truth_after' in r) == (r['cost'] is not None)
                and r.get('goal_truth_after', reads) == ('MODEL_DERIVABLE_NOT_EXTERNAL_PROOF' if r['model_receipts'] else reads))

    def argued(r):   # the two things a run of the sequence says that its trace does not carry: its proof, and the branch of the rule it took. Read off the facts its trace retained and off the recorded case that took the same branch
        kept = [e['data'] for e in r['trace'] if e['operation'] == 'RETAIN']
        stands = [kept[-1]['predicate'] + ' observed TRUE (' + str(kept[-1]['source']) + ')'] if kept else None   # the proof line of the fact a run stands on: the fact its trace retained last, with that row's source
        if r['cost'] is None:   # a look with no plan argues nothing
            return r['proof'] == [] and r['selected_branch'] is None
        if r['goal'] != 'run_judged':   # a goal with no rule has no branch; a look that ran nothing stands on the goal's own row (a look that ran is a case's look, held to its case's copy: the proof of such a run is read by no check)
            return r['selected_branch'] == '' and (bool(r['model_receipts']) or r['proof'] == stands)
        like = o64 if 'fitness_in_band' in [x['predicate'] for x in kept] else o63   # the recorded case that took the same branch of the rule: in band (case 64), or by the finding (case 63)
        return same(r['selected_branch'], like['selected_branch']) and same(r['proof'], like['proof'] if r['model_receipts'] or like is o64 else like['proof'][:1] + stands)

    def alone_ok():   # one row authored alone, against a bound written into the comparison: below the bound, and no row says so
        first, again, e = al['look']['runs'][0], al['again']['runs'][0], al['again']['event']
        told = lambda r: [(x['predicate'], x['number']['value'], x['operator'], x['bound'], x['verdict'], x['reads']) for x in r.get('comparisons', [])]
        asks = lambda r: (r['status'], r['stop_reasons'], r['actions'], r['model_receipts'], r['cost']) == ('QUERY_EVIDENCE', ['METHOD_ABSENT', 'QUERY_EVIDENCE'], [], [], None)
        return (al['packs'] == ALONE and stood(al['look']) and asks(first) and told(first) == [('fitness_in_band', '0.85', '>=', {'literal': '0.9'}, 'FALSE', 'FALSE')] and untouched(al['after'], 1)
                and same(al['after']['facts'], left_by(ALONE)[0])   # the books are the pack files' rows: no row says the reading is below the band, and no finding was filed
                and sorted(al['after']['facts']) == [S + 'fitness_band', S + 'fitness_in_band', S + 'run_fitness']
                and (al['again']['status'], al['again']['affected'], len(al['again']['runs']), al['again'].get('remade')) == ('RECONCILED', ['run_judged'], 1, ['fitness_in_band'])
                and arrived(e, al['after']['facts'][S + 'run_fitness'], 'run_fitness', '0.7', 'run-0005') and same(al['after_again']['facts'][S + 'run_fitness'], e)
                and asks(again) and told(again) == [('fitness_in_band', '0.7', '>=', {'literal': '0.9'}, 'FALSE', 'FALSE')] and untouched(al['after_again'], 2)
                and sorted(al['after_again']['facts']) == sorted(al['after']['facts']) and same(al['after_again']['facts'][S + 'fitness_band'], al['after']['facts'][S + 'fitness_band']))

    def bare_ok():   # the number with no comparison row beside it: the goal, the rule, the number and the method of case 63 ask for evidence at 0.8, and again at 1.0
        e = ba['event']
        asks = lambda x: stood(x) and (x['runs'][0]['status'], x['runs'][0]['stop_reasons'], x['runs'][0]['actions'], x['runs'][0]['model_receipts'], x['runs'][0]['cost']) == ('QUERY_EVIDENCE', ['QUERY_EVIDENCE'], [], [], None)
        fitness = [row for row in SCEN['152_run_fitness']['evidence'] if row['predicate'] == 'run_fitness']
        return (ba['packs'] == BARE and [n for n in BARE if n not in conform] == [LATE] and [n for n in conform if n not in BARE] == ['152_run_fitness'] and same(SCEN[LATE].get('evidence'), fitness)
                and len(fitness) == 1 and set(SCEN[LATE]) == {'schema', 'id', 'evidence'}   # the pack of the number alone is the fitness pack of case 63 less its two comparison rows
                and asks(ba['look']) and untouched(ba['after'], 1) and same(ba['after']['facts'], left_by(BARE)[0])
                and sorted(ba['after']['facts']) == [S + 'fitness_band', S + 'run_fitness'] and ba['after']['facts'][S + 'run_fitness']['value'] == '0.8'
                and same(strip(e, ('event',)), {'status': 'RECONCILED', 'affected': [], 'runs': [], 'remade': []}) and arrived(e['event'], ba['after']['facts'][S + 'run_fitness'], 'run_fitness', '1.0', 'run-0002')
                and asks(ba['again']) and untouched(ba['after_again'], 2) and same(ba['after_again']['facts'], dict(ba['after']['facts'], **{S + 'run_fitness': e['event']})))

    def events_ok():   # the events of the sequence: a reading taken whole (one look, one journal row), a reading handed to the kernel alone, readings refused, a reading in a pack
        run = lambda k: ne[k]['runs'][0]
        snap = lambda k: ne['after_' + k]
        facts = lambda k: snap(k)['facts']
        both = ['fitness_in_band', 'fitness_below_band']
        reads = lambda k, names: [kread(facts(k), S + p) for p in names]
        look = lambda k, status, actions: (run(k)['status'], run(k)['actions'], [x['method'] for x in run(k)['model_receipts']]) == (status, actions, actions)

        def only(a, b, names):   # between two snapshots only the rows named may have changed: every other stored row is the same row, and none came or went
            keys = {S + p for p in names}
            return keys <= set(facts(b)) and same({key: row for key, row in facts(a).items() if key not in keys}, {key: row for key, row in facts(b).items() if key not in keys})

        def took(k, before, predicate, value, label):   # a reading taken whole: the number stored, both rows of the band named as made again and read, one look of the one goal, and nothing else on the books touched but the finding when the look filed it. Not held: that each row made again is the row it replaces, redone on the new number (`only` leaves both rows free; the unit test that makes the sequence again holds them)
            e = ne[k]['event']
            return ((ne[k]['status'], ne[k]['affected'], len(ne[k]['runs']), ne[k].get('remade')) == ('RECONCILED', ['run_judged'], 1, both)
                    and arrived(e, facts(before)[S + predicate], predicate, value, label) and same(facts(k)[S + predicate], e) and 'UNKNOWN' not in reads(k, both)
                    and only(before, k, [predicate] + both + (['finding_filed'] if run(k)['model_receipts'] else [])))

        def step(a, b, paid):   # between two snapshots: one more journal row, and the finding's cost and provider slot paid, or nothing paid
            return (same(snap(b)['journal'], snap(a)['journal'] + 1) and same(snap(b)['budget'], {dim: v - (finding['cost'].get(dim, 0) if paid else 0) for dim, v in snap(a)['budget'].items()})
                    and same(snap(b)['providers'], {p: v - (1 if paid and p == finding['provider'] else 0) for p, v in snap(a)['providers'].items()}))

        def opened(k):   # the first look of a State: the look of case 63, field for field; one journal row, the pack's budget and provider slots less one finding, and on the books the rows the pack files leave and the finding
            return (same(snap(k)['journal'], 1) and same(snap(k)['budget'], {dim: v - finding['cost'].get(dim, 0) for dim, v in purse63.items()})
                    and same(snap(k)['providers'], {p: v - (1 if p == finding['provider'] else 0) for p, v in slots63.items()})
                    and same(strip(facts(k), (S + 'finding_filed',)), left_by(conform)[0]) and same(strip(ne[k], ('runs', 'cost_receipts')), {'status': 'EVALUATED', 'goals': ['run_judged']})
                    and same([strip(r, BLOCKS) for r in ne[k]['runs']], [strip(r, LEARNT) for r in by[C63]['run']['runs']]))

        def filed(k):   # a look that filed the finding: the one step ran, and the finding on the books after it is that step's row, resting on the row below the band at the version on the books, and it reads TRUE
            return look(k, 'LOCAL_MODEL_EFFECTS_RECORDED', ['file-finding@1']) and same(facts(k).get(S + 'finding_filed'), filed_on(facts(k))) and reads(k, ['finding_filed']) == ['TRUE']
        held = lambda k: look(k, 'SUPPORTED_BY_EVIDENCE', [])
        stale = lambda k: reads(k, ['finding_filed']) == ['UNKNOWN']   # the finding of an earlier reading is still on the books (`only` holds it to the row it was) and no longer reads
        return (filed('first') and opened('first')
                and took('in_band', 'first', 'run_fitness', '0.95', 'run-0002') and held('in_band') and step('first', 'in_band', False) and stale('in_band')
                and took('below_again', 'in_band', 'run_fitness', '0.7', 'run-0003') and filed('below_again') and step('in_band', 'below_again', True)
                and took('same_again', 'below_again', 'run_fitness', '0.7', 'run-0003') and same(ne['same_again']['event'], ne['below_again']['event']) and held('same_again') and step('below_again', 'same_again', False)
                and same(facts('same_again'), facts('below_again'))
                and took('band_moved', 'same_again', 'fitness_band', '0.6', 'band-v2') and held('band_moved') and step('same_again', 'band_moved', False) and reads('band_moved', ['fitness_in_band']) == ['TRUE'] and stale('band_moved')
                and filed('first_bare') and opened('first_bare')
                and (ne['bare_event']['status'], ne['bare_event']['affected'], len(ne['bare_event']['runs']), 'remade' in ne['bare_event']) == ('RECONCILED', ['run_judged'], 1, False)
                and arrived(ne['bare_event']['event'], facts('first_bare')[S + 'run_fitness'], 'run_fitness', '0.95', 'run-0002') and same(facts('bare_event')[S + 'run_fitness'], dict(ne['bare_event']['event'], scope=S[:-1])) and look('bare_event', 'QUERY_EVIDENCE', []) and step('first_bare', 'bare_event', False)
                and only('first_bare', 'bare_event', ['run_fitness']) and reads('bare_event', both + ['finding_filed']) == ['UNKNOWN'] * 3
                and same(ne['refused'], REFUSED) and same(snap('refused'), snap('bare_event'))
                and took('repaired', 'refused', 'run_fitness', '0.95', 'run-0002') and held('repaired') and step('refused', 'repaired', False) and reads('repaired', ['fitness_in_band']) == ['TRUE'] and stale('repaired')
                and same(strip(ne['pack_event'], ('runs', 'cost_receipts')), {'status': 'EVALUATED', 'goals': ['run_judged']}) and len(ne['pack_event']['runs']) == 1 and look('pack_event', 'QUERY_EVIDENCE', [])
                and step('repaired', 'pack_event', False) and only('repaired', 'pack_event', ['run_fitness']) and same([facts('pack_event')[S + 'run_fitness']], [dict(row, scope=S[:-1]) for row in SCEN[LATE]['evidence']])
                and not same(facts('pack_event')[S + 'run_fitness']['version'], facts('repaired')[S + 'run_fitness']['version']) and reads('pack_event', both + ['finding_filed']) == ['UNKNOWN'] * 3)

    def dims_of(r):   # the dimensions the State of a run had: the three every State starts with and every one a pack it loaded adds
        return sorted(set(BASE).union(*[set(SCEN[p['pack']].get('budget', {})) for p in r['provenance']]))

    def paid_ok(r):   # a run this file cannot read does not hold
        try:
            mine, dims = own(r), dims_of(r)
            priced = lambda acts: {dim: sum(mine[a].get('cost', {}).get(dim, 0) for a in acts) for dim in dims}   # what the packs give these methods, in every dimension the State had
            steps = step_costs(r, mine, dims)
            return (steps is not None and [x['receipt'] for x in steps] == [x['sha256'] for x in r['model_receipts']] and (not steps or [x['method'] for x in steps] == r['actions'])
                    and (same(r['cost'], priced(r['actions'])) if r['cost'] is not None else not steps)
                    and all(same(e['data']['cost'], priced(e['data']['methods'])) for e in r['trace'] if e['operation'] == 'ADMISSION')
                    and all(same(e['data']['full_cost'], priced(e['data']['actions'])) for e in r['trace'] if e['operation'] == 'SELECT'))
        except Exception:
            return False

    def receipt_of(r):   # the cost receipt of a run, made again here
        dims = dims_of(r)
        steps = step_costs(r, own(r), dims)
        return {'steps': steps, 'total': {dim: sum(x['cost'][dim] for x in steps) for dim in dims} if steps else {}, 'source_trace': r['trace_root_sha256'], 'steps_sha256': sha(steps)}
    whole = lambda v: type(v) is int and 0 <= v < 10 ** 18
    used = sorted({n for c in d['cases'] for n in c['packs']} | {n for names, _, _ in parts for n in names})   # every pack a recorded case or a look of the sequence loaded
    amounts = [v for n in used for v in list(SCEN[n].get('budget', {}).values()) + list(SCEN[n].get('providers', {}).values()) + [v for m in SCEN[n].get('methods', []) for v in m.get('cost', {}).values()]]
    c65 = by[C65]
    o65 = c65['outcome']
    review = of(c65['packs'])['review-loan-file@1']['cost']
    purse65 = dict(BASE, **SCEN['155_loan_goal']['budget'])
    c66 = by[C66]
    q = SCEN['157_review_queue']
    queued = of(c66['packs'])
    imp = {g: num(v) for g, v in q['impact'].items()}
    scale = math.prod(v[1] for v in imp.values())
    queue, again, later_run = c66['run']['runs'], lk[C66]['look']['runs'], nx['look']['runs']
    order = sorted(q['goals'], key=lambda g: (-imp[g][0] * (scale // imp[g][1]), g))   # higher impact first; equal impacts by name
    standing = [SCEN[n]['goals'] for n in c66['packs'] if 'goals' in SCEN[n]][-1]   # the goals the State has: those of the last pack that sets them
    start = dict(BASE)
    for n in c66['packs']:
        start.update(SCEN[n].get('budget', {}))
    cost_of = lambda acts: {dim: sum(queued[a].get('cost', {}).get(dim, 0) for a in acts) for dim in start}
    paid = cost_of([x['method'] for x in queue[0]['model_receipts']])
    left = {dim: start[dim] - paid[dim] for dim in start}
    left_later = dict(left, **SCEN[NEXT].get('budget', {}))   # one run later: the pack of the next run sets the run cap again
    stopped = lambda r: [e['data']['methods'] for e in r['trace'] if e['operation'] == 'ADMISSION' and 'RESOURCE_REQUIRED' in e['data']['blockers']]
    short_of = lambda r, budget: [{'methods': acts, 'dimension': dim, 'need': need, 'left': budget[dim]} for acts in stopped(r) for dim, need in cost_of(acts).items() if need > budget[dim]]
    short = short_of(queue[1], left)
    ceilings = q['ceilings']
    later = c66['packs'][c66['packs'].index('157_review_queue') + 1:] + [NEXT]
    handlers = d['action_handlers']
    return {
        NAMES[0]: len(numbers) >= 4 and all(number_ok(row) and keyed(key, row) for key, row in numbers),
        NAMES[1]: len(made) >= 4 and len(verdicts) == 2
        and all(comparison_ok(row) and keyed(key, row) and band_ok(row, facts) and (kread(facts, key) == 'UNKNOWN' or from_books(row, facts)) for key, row, facts in made)
        and all(as_packed(by[c]['packs'], by[c]['derived_state']['facts']) for c in OURS) and as_packed(al['packs'], al['after']['facts']) and as_packed(ba['packs'], ba['after']['facts'])
        and all(ne[k]['facts'][S + p].get('source') == CMP for k in ne if k.startswith('after_') for p in verdicts)
        and all(adapter_only(by[c]['packs']) for c in OURS) and adapter_only(al['packs']) and adapter_only(ba['packs']) and alone_ok(),
        NAMES[2]: all(block_ok(r, facts) for _, facts, x in parts for r in x['runs']) and len(list(walk(d['scenes']['numbers']))) == len(seen)   # the sequence holds no run beside the runs of its looks
        and (len(seen), sum('comparisons' in r for r in seen)) == (RUNS, WITH_A_BLOCK) and all(loaded(r, names) and told(r, facts) and argued(r) for names, facts, x in parts for r in x['runs'])
        and not any(key in r for r in base_runs(d) for key in BLOCKS) and sorted(lk) == sorted(OURS) and all(retaken(c) and viewed(c) and stepped(c) for c in OURS),
        NAMES[3]: (o63['status'], o63['actions'], [x['action'] for x in o63['model_receipts']]) == ('LOCAL_MODEL_EFFECTS_RECORDED', ['file-finding@1'], ['emit_artifact'])
        and same(o63['cost'], {dim: finding['cost'].get(dim, 0) for dim in purse63}) and finding.get('requires') == ['fitness_below_band']
        and same({k: found63.get(k) for k in ('predicate', 'truth', 'verified', 'source', 'scope')}, {'predicate': 'finding_filed', 'truth': 'TRUE', 'verified': True, 'source': 'LOCAL_ARTIFACT:file-finding@1', 'scope': S[:-1]})
        and same(found63, filed_on(kept63)) and kread(kept63, S + 'finding_filed') == 'TRUE'   # the finding on the books is the step's row: it rests on the row below the band, at its version, and it reads TRUE
        and S + 'finding_filed' not in by[C64]['derived_state']['facts']
        and shape(lk[C63]['look']['runs'][0]) == [('fitness_in_band', '0.8', '>=', '0.9', 'FALSE', 'FALSE'), ('fitness_below_band', '0.8', '<', '0.9', 'TRUE', 'TRUE')]
        and (o64['status'], o64['actions'], o64['model_receipts']) == ('SUPPORTED_BY_EVIDENCE', [], []) and same(o64['cost'], {dim: 0 for dim in purse63})
        and shape(lk[C64]['look']['runs'][0]) == [('fitness_in_band', '1.0', '>=', '0.9', 'TRUE', 'TRUE'), ('fitness_below_band', '1.0', '<', '0.9', 'FALSE', 'FALSE')]
        and same(by[C64]['derived_state']['budget_after'], purse63) and bare_ok(),
        NAMES[4]: events_ok(),
        NAMES[5]: all(paid_ok(r) for r in base_runs(d)) and all(paid_ok(r) for r in walk(d['scenes']))
        and all(same(x.get('cost_receipts'), [receipt_of(r) for r in x['runs']]) for _, _, x in parts),
        NAMES[6]: all(whole(v) for v in amounts) and all(named(c) for c in OURS)
        and same(SCEN['155_loan_goal']['budget'], {'usd_cents': 200, 'tokens': 10000}) and same(review, {'usd_cents': 42, 'tokens': 3340})
        and o65['status'] == 'LOCAL_MODEL_EFFECTS_RECORDED' and same(o65['cost'], {dim: review.get(dim, 0) for dim in purse65})
        and same(c65['derived_state']['budget_after'], {dim: purse65[dim] - review.get(dim, 0) for dim in purse65})
        and same([c65['derived_state']['budget_after']['usd_cents'], c65['derived_state']['budget_after']['tokens']], [158, 6660])
        and [same(e['data']['cost'], o65['cost']) for e in o65['trace'] if e['operation'] == 'ADMISSION'] == [True, True],
        NAMES[7]: set(imp) == set(q['goals']) and q['goals'] == order and standing == order and c66['run']['goals'] == order and [r['goal'] for r in queue] == order
        and [r['status'] for r in queue] == ['LOCAL_MODEL_EFFECTS_RECORDED', 'RESOURCE_REQUIRED'] and [('shortfall' in r) for r in seen].count(True) == 2
        and same(again[1].get('shortfall'), short) and [x['dimension'] for x in short] == list(ceilings) and all(cost_of(acts)[cap] <= left[cap] for acts in stopped(queue[1]) for cap in ceilings.values())
        and all(same(m.get('cost', {}).get(cap, 0), m.get('cost', {}).get(top, 0)) for m in queued.values() for top, cap in ceilings.items())
        and not any(top in SCEN[n].get('budget', {}) for top in ceilings for n in later)
        # one run later: the pack of the next run sets every capped dimension again, to the level it had, and no ceiling; the review that ran stands on its evidence; the other stops on the ceiling alone, with the same shortfall
        and nx['packs'] == c66['packs'] + [NEXT] and same(SCEN[NEXT].get('budget'), {cap: q['budget'][cap] for cap in ceilings.values()}) and set(SCEN[NEXT]) == {'schema', 'id', 'budget'}
        and same(strip(nx['look'], ('runs', 'cost_receipts')), strip(c66['run'], ('runs',))) and [r['goal'] for r in later_run] == order
        and [(r['status'], r['actions'], r['model_receipts']) for r in later_run] == [('SUPPORTED_BY_EVIDENCE', [], []), ('RESOURCE_REQUIRED', [], [])]
        and stopped(later_run[1]) == stopped(queue[1]) and same(later_run[1].get('shortfall'), short_of(later_run[1], left_later)) and same(short_of(later_run[1], left_later), short)
        and same(nx['after']['budget'], left_later) and same(nx['after']['journal'], lk[C66]['after']['journal'] + 2) and same(nx['after']['providers'], lk[C66]['after']['providers'])
        and same(nx['after']['facts'], lk[C66]['after']['facts']),
        NAMES[8]: all(word not in core for word in WORDS)
        and not any(str(h.get('file', '')).startswith('extensions/numbers') or str(h.get('module', '')).startswith('extensions.numbers') for h in handlers.values())}


# ---------------------------------------------------------------- forgeries: each changes one thing. A few change a row, its block and the block's digest together; the ones marked
# "made whole" change a run as a forger would: every statement of the thing changed, the chain hashed again, the new root carried to every copy and every block bound to it.
case = lambda d, cid: [c for c in d['cases'] if c['id'] == cid][0]
nev = lambda d, k: d['scenes']['numbers']['events'][k]
lok = lambda d, cid: d['scenes']['numbers']['looks'][cid]
part = lambda d, name: d['scenes']['numbers'][name]
seq = lambda d, cid, i=0: lok(d, cid)['look']['runs'][i]            # a run of the look the sequence takes of a case: the copy that carries the blocks
out = lambda d, cid: case(d, cid)['outcome']
kept = lambda d, cid: case(d, cid)['derived_state']['facts']        # the books of a recorded case
row_at = lambda r, op, i=0: [e for e in r['trace'] if e['operation'] == op][i]['data']


def rehash(r):   # a run's chain hashed again after a change, and the new root carried to the blocks bound to it; returns the root it had
    prev = 'GENESIS'
    for i, e in enumerate(r['trace']):
        e.update(seq=i + 1, prev_sha256=prev)
        e['sha256'] = sha({k: v for k, v in e.items() if k != 'sha256'})
        prev = e['sha256']
    old, r['trace_root_sha256'] = r['trace_root_sha256'], prev
    for block in ('comparisons_record', 'learning_record'):
        if block in r:
            r[block]['source_trace'] = prev
    return old


def recost(r, change):   # every statement of cost in a run changed alike: its own, the SELECT row's, every ADMISSION row's
    for cost in [r['cost']] + [e['data']['full_cost'] for e in r['trace'] if e['operation'] == 'SELECT'] + [e['data']['cost'] for e in r['trace'] if e['operation'] == 'ADMISSION']:
        if cost is not None:
            change(cost)
    return rehash(r)


def receipt_again(x, i=0):   # the cost receipt of a look's run made again from its gate rows, as the adapter makes it
    r = x['runs'][i]
    steps = [{'method': e['data']['receipt']['method'], 'receipt': e['data']['receipt']['sha256'], 'cost': dict(r['trace'][j - 1]['data']['cost'])} for j, e in enumerate(r['trace']) if e['operation'] == 'LOCAL_EFFECT']
    x['cost_receipts'][i] = {'steps': steps, 'total': {dim: sum(s['cost'][dim] for s in steps) for dim in (steps[0]['cost'] if steps else {})}, 'source_trace': r['trace_root_sha256'], 'steps_sha256': sha(steps)}


def recost_case(d, cid, change):   # made whole: the first run of a case in every copy the record keeps (the outcome, the run block, the viewer's trace, the journal row, the look the sequence took again and its cost receipt)
    c = case(d, cid)
    old = [recost(r, change) for r in [c['outcome'], c['run']['runs'][0]] + ([seq(d, cid)] if cid in OURS else [])][0]
    c['four_views']['run'] = json.loads(json.dumps(c['outcome']['trace']))
    for j in c['derived_state']['historical_events']:
        if j.get('trace_root_sha256') == old:
            j['trace_root_sha256'] = c['outcome']['trace_root_sha256']
    if cid in OURS:
        receipt_again(lok(d, cid)['look'])


def recost_event(d, k, change):   # made whole: the run of a look of the events and its cost receipt
    recost(nev(d, k)['runs'][0], change)
    receipt_again(nev(d, k))


def liar(d):   # the first look of the events forged whole: the stored row says TRUE for 0.8 >= 0.9 under the version of a comparison of 0.95, and the run's block and its digest agree with it
    row = nev(d, 'after_first')['facts'][S + 'fitness_in_band']
    row['compares']['number'].update(value='0.95')
    row.update(truth='TRUE', version='cmp-' + sha(canon(row['compares']))[:16])
    r = nev(d, 'first')['runs'][0]
    r['comparisons'][0].update(number=dict(row['compares']['number']), verdict='TRUE', version=row['version'], reads='TRUE')
    r['comparisons_record'].update(comparisons_sha256=sha(r['comparisons']))


def reblock(d, k, change):   # change the comparisons block of a recorded look and make its digest agree
    r = nev(d, k)['runs'][0]
    change(r['comparisons'])
    r['comparisons_record'].update(comparisons_sha256=sha(r['comparisons']))


def liar_stale(d):   # both rows of the band that went stale flipped in the two snapshots that carry them, and the block of the look that saw them: only the verdict redone from each row's own recipe tells
    for k in ('after_bare_event', 'after_refused'):
        for p, truth in (('fitness_in_band', 'TRUE'), ('fitness_below_band', 'FALSE')):
            nev(d, k)['facts'][S + p].update(truth=truth)
    reblock(d, 'bare_event', lambda rows: [x.update(verdict=truth) for x, truth in zip(rows, ('TRUE', 'FALSE'))])


def reversioned(d):   # a comparison that did not hold given another version, on the books and in the block: only the digest of its own recipe tells
    nev(d, 'after_first')['facts'][S + 'fitness_in_band'].update(version='cmp-0000000000000000')
    reblock(d, 'first', lambda rows: rows[0].update(version='cmp-0000000000000000'))


def cheaper(d):   # a step's cost changed everywhere the record states it (both gate rows, every copy of the run, the cost receipt, what was left), the chains left as they were: only the pack files of the case tell
    for r in (out(d, C65), case(d, C65)['run']['runs'][0], seq(d, C65)):
        for i in (0, -1):
            row_at(r, 'ADMISSION', i)['cost'].update(usd_cents=41)
        r['cost'].update(usd_cents=41)
    rec = lok(d, C65)['look']['cost_receipts'][0]
    rec['steps'][0]['cost'].update(usd_cents=41)
    rec['total'].update(usd_cents=41)
    rec.update(steps_sha256=sha(rec['steps']))
    case(d, C65)['derived_state']['budget_after'].update(usd_cents=159)
    lok(d, C65)['after']['budget'].update(usd_cents=159)


def relabelled(d):   # the reading the record says arrived is another reading of the same value than the one on the books
    e = nev(d, 'in_band')['event']
    e.update(label='run-0009')
    e.update(version='num-' + sha({'predicate': e['predicate'], 'value': lowest(num(e['value'])), 'unit': e['unit'], 'label': e['label'], 'source': e['source']})[:16])


def restated(d):   # the row made again on the State with one row authored alone, restated for another number under a version of its own, the block of its look following suit: only the number on the books tells
    al = part(d, 'alone')
    row = al['after_again']['facts'][S + 'fitness_in_band']
    row['compares']['number'].update(value='0.71')
    row.update(version='cmp-' + sha(canon(row['compares']))[:16])
    r = al['again']['runs'][0]
    r['comparisons'][0].update(number=dict(row['compares']['number']), version=row['version'])
    r['comparisons_record'].update(comparisons_sha256=sha(r['comparisons']))


def reordered(d):   # the block of a look in another order than its trace names the comparisons, with a digest that agrees
    r = seq(d, C63)
    r['comparisons'].reverse()
    r['comparisons_record'].update(comparisons_sha256=sha(r['comparisons']))


def on_a_finding(d):   # the look in band says, in its branch and in the first line of its proof alike, that it stood on a finding
    r = nev(d, 'in_band')['runs'][0]
    r.update(selected_branch=out(d, C63)['selected_branch'])
    r['proof'][0] = out(d, C63)['proof'][0]


def relabelled_whole(d):   # made whole: the reading that arrived in band carries another label everywhere the record states it: the event, the row on the books, both comparisons made on it, the block of the look, the row its trace retained, the chain
    e, facts, r = nev(d, 'in_band')['event'], nev(d, 'after_in_band')['facts'], nev(d, 'in_band')['runs'][0]
    e.update(label='run-0009')
    e.update(version='num-' + sha({'predicate': e['predicate'], 'value': lowest(num(e['value'])), 'unit': e['unit'], 'label': e['label'], 'source': e['source']})[:16])
    facts[S + 'run_fitness'] = dict(e)
    for p in ('fitness_in_band', 'fitness_below_band'):
        row = facts[S + p]
        row['compares']['number'].update(version=e['version'])
        row['depends_on'][0].update(version=e['version'])
        row.update(version='cmp-' + sha(canon(row['compares']))[:16])
    for x in r['comparisons']:
        x.update(number=dict(facts[S + x['predicate']]['compares']['number']), version=facts[S + x['predicate']]['version'])
    r['comparisons_record'].update(comparisons_sha256=sha(r['comparisons']))
    row_at(r, 'RETAIN').update(version=facts[S + 'fitness_in_band']['version'])
    rehash(r)
    receipt_again(nev(d, 'in_band'))


def reviewed_false(d):   # made whole in its three copies: the row the big review wrote says FALSE on the books of case 66, after the look the sequence took again, and in the viewer's world view
    for facts in (kept(d, C66), lok(d, C66)['after']['facts']):
        facts['orgA/lending|big_loan_reviewed'].update(truth='FALSE')
    for w in case(d, C66)['four_views']['world']:
        if w['predicate'] == 'orgA/lending|big_loan_reviewed':
            w.update(truth='FALSE')


def unfiled(d):   # the finding of case 63 no longer reads: FALSE and unverified on the books of the case and after the look the sequence took again
    for facts in (kept(d, C63), lok(d, C63)['after']['facts']):
        facts[S + 'finding_filed'].update(truth='FALSE', verified=False)


RECORD_FORGERIES = [
    lambda d: seq(d, C63)['comparisons'][0].update(verdict='TRUE'),
    lambda d: kept(d, C63)[S + 'fitness_in_band'].update(truth='TRUE'),                         # a row that says TRUE for 0.8 >= 0.9
    lambda d: kept(d, C63)[S + 'run_fitness'].update(value='0.95'),                              # another value under the old version
    lambda d: kept(d, C63)[S + 'run_fitness'].update(value=0.8),                                 # a float
    lambda d: kept(d, C63)[S + 'run_fitness'].update(value='8e-1'),                              # an exponent
    lambda d: kept(d, C63)[S + 'fitness_below_band'].pop('depends_on'),                          # a comparison that rests on nothing
    lambda d: kept(d, C63)[S + 'fitness_below_band'].update(version='cmp-0000000000000000'),
    lambda d: kept(d, C63)[S + 'fitness_below_band'].update(source='LOCAL_MODEL:fix-fitness@1'),   # a comparison's predicate made by another source
    lambda d: kept(d, C63)[S + 'fitness_below_band']['compares'].update(op='<='),
    lambda d: kept(d, C63)[S + 'fitness_in_band']['compares']['number'].update(value='0.95'),
    lambda d: seq(d, C63).pop('comparisons'),
    lambda d: seq(d, C63)['comparisons'].pop(0),
    lambda d: seq(d, C63)['comparisons_record'].update(source_trace='0' * 64),
    lambda d: seq(d, C63)['comparisons'][1]['number'].update(value='0.95'),
    lambda d: seq(d, C63)['comparisons'][1].update(reads='UNKNOWN'),
    lambda d: out(d, C63).update(status='SUPPORTED_BY_EVIDENCE'),
    lambda d: out(d, C64).update(actions=['file-finding@1']),
    lambda d: kept(d, C63)[S + 'finding_filed'].update(depends_on=[]),                           # the finding of the case rests on nothing
    lambda d: out(d, '04_gates').update(comparisons=[]),                                         # a block on a run that names no comparison
    lambda d: lok(d, C65)['look']['cost_receipts'][0]['steps'][0]['cost'].update(usd_cents=1),
    lambda d: lok(d, C65)['look'].pop('cost_receipts'),
    lambda d: lok(d, C63)['look']['cost_receipts'].pop(),
    lambda d: row_at(out(d, C65), 'LOCAL_EFFECT')['receipt'].update(cost={'usd_cents': 1}),      # a receipt that states a cost of its own
    lambda d: row_at(out(d, C65), 'ADMISSION', -1)['cost'].update(usd_cents=41),                 # the gate's row
    lambda d: row_at(out(d, C65), 'ADMISSION', -1).update(methods=['review-loan-file@1', 'another@1']),
    lambda d: case(d, C65)['derived_state']['budget_after'].update(usd_cents=200),
    lambda d: out(d, C65)['cost'].update(tokens=3340.0),
    lambda d: seq(d, C66, 1)['shortfall'][0].update(left=60),
    lambda d: seq(d, C66, 1).pop('shortfall'),
    lambda d: seq(d, C65).update(shortfall=[]),                                                  # a shortfall on a look that fitted
    lambda d: case(d, C66)['run'].update(goals=list(reversed(case(d, C66)['run']['goals']))),
    lambda d: case(d, C66)['run']['runs'].reverse(),
    lambda d: nev(d, 'in_band')['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
    lambda d: nev(d, 'in_band')['event'].update(value='0.5'),
    lambda d: nev(d, 'in_band').update(remade=['fitness_in_band']),
    lambda d: nev(d, 'after_in_band').update(journal=nev(d, 'after_in_band')['journal'] + 1),    # a second journal row
    lambda d: nev(d, 'after_in_band')['facts'][S + 'finding_filed'].update(depends_on=[]),      # the earlier finding still stands
    lambda d: nev(d, 'after_below_again')['budget'].update(attention=nev(d, 'after_in_band')['budget']['attention']),   # the second finding was free
    lambda d: nev(d, 'same_again')['runs'][0].update(actions=['file-finding@1']),
    lambda d: nev(d, 'band_moved')['event'].update(predicate='run_fitness'),
    lambda d: nev(d, 'bare_event')['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'),
    lambda d: nev(d, 'bare_event')['runs'][0]['comparisons'][0].update(reads='FALSE'),           # a stale comparison read as if it stood
    lambda d: nev(d, 'after_refused')['facts'][S + 'run_fitness'].update(label='run-0009'),      # a refused reading left a mark
    lambda d: nev(d, 'refused').update({'another scope': ''}),                                   # the reading for another scope was taken after all
    lambda d: nev(d, 'refused').update({'another unit': 'refused'}),                             # another reason than the one the adapter gives
    lambda d: nev(d, 'refused').pop('execute is not true or false'),                             # one of the six refusals is not in the record
    lambda d: nev(d, 'refused').update({'a seventh reading': 'A number takes the place of a number only'}),
    lambda d: kept(d, C63)[S + 'run_fitness'].update(note='reviewed'),                           # a field more than a number row has
    lambda d: nev(d, 'after_in_band')['facts'][S + 'run_fitness'].update(note='reviewed'),
    lambda d: nev(d, 'after_in_band')['facts'][S + 'fitness_in_band'].update(evidence_kind='NUMBER'),
    lambda d: nev(d, 'after_in_band')['facts'][S + 'fitness_in_band'].update(note='reviewed'),   # a field more than a comparison row has
    lambda d: nev(d, 'after_in_band')['facts'].pop(S + 'fitness_below_band'),                    # half a band
    lambda d: nev(d, 'after_in_band')['facts'][S + 'fitness_below_band']['compares'].update(partner='another_row'),
    lambda d: out(d, C64)['cost'].update(compute=0.0),                                           # 0.0 is not 0
    lambda d: nev(d, 'after_in_band').update(journal=float(nev(d, 'after_in_band')['journal'])),   # 2.0 is not 2
    lambda d: nev(d, 'after_first')['budget'].update(compute=5),                                 # the first finding was free
    lambda d: d['events']['initial']['runs'][0].update(comparisons=[]),                          # a block on a run of an older record
    lambda d: lok(d, C63)['look']['cost_receipts'][0].update(source_trace='0' * 64),
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_band'].update(note='reviewed'),        # the band kept as policy: a field more
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_band'].update(evidence_kind='MEASURE'),
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_band'].update(label='band-v9'),        # another label under the old version
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_band'].update(value=0.9),              # a float where the exact text was
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_in_band'].update(depends_on=[]),       # a comparison that rests on nothing would outlive its number
    lambda d: nev(d, 'after_refused').update(facts=json.loads(json.dumps(nev(d, 'after_repaired')['facts']))),   # a refused reading was taken after all
    lambda d: nev(d, 'below_again')['runs'][0]['cost'].update(attention=0),                      # the second finding's run says it cost no attention
    lambda d: row_at(out(d, C65), 'ADMISSION', 0)['cost'].update(usd_cents=41),                  # the plan's admission row, a cent short
    lambda d: kept(d, C63)[S + 'fitness_band'].update(value='0.90'),                             # the same number spelled another way than in the pack file of the case
    lambda d: [nev(d, k)['budget'].update(compute=nev(d, k)['budget']['compute'] + 1) for k in ('after_first', 'after_in_band', 'after_below_again', 'after_same_again', 'after_band_moved')],   # one unit more in every snapshot of the first State
    lambda d: seq(d, C63).update(trace_root_sha256='0' * 64),                                    # the look the sequence took is not the recorded case's look
    lambda d: seq(d, C64).update(status='LOCAL_MODEL_EFFECTS_RECORDED'),
    lambda d: lok(d, C64)['after']['facts'][S + 'run_fitness'].update(label='run-0009'),         # other books after the look than the case's
    lambda d: lok(d, C64)['packs'].reverse(),
    lambda d: lok(d, C66)['after']['budget'].update(dept_usd_cents=60),                          # the ceiling was not charged
    lambda d: lok(d, C66)['after'].update(journal=1),
    lambda d: lok(d, C63)['after']['providers'].update({'local-provider': 2}),                   # the finding took no provider slot
    lambda d: lok(d, C66)['look'].update(goals=list(reversed(lok(d, C66)['look']['goals']))),    # the look says it took the goals in another order
    lambda d: nev(d, 'first').update(status='NO_STANDING_GOAL'),
    lambda d: nev(d, 'after_first')['facts'][S + 'finding_filed'].update(source='fixture/reviewed'),   # the finding on the books is not the step's row
    lambda d: nev(d, 'after_below_again')['facts'][S + 'finding_filed'].update(depends_on=[{'predicate': 'fitness_in_band', 'version': nev(d, 'after_below_again')['facts'][S + 'fitness_in_band']['version']}]),   # the second finding rests on the other row of the band
    lambda d: d['scenes']['numbers']['looks'].pop(C65),
    lambda d: seq(d, C65).update(comparisons=[]),                                                # an empty block on a look of the sequence that names no comparison
    lambda d: lok(d, C65)['after']['facts']['orgA/lending|loan_file_reviewed'].update(version='local-sim-2'),   # a row on the books after the look that the case's books do not have
    lambda d: nev(d, 'after_first')['facts'][S + 'finding_filed'].update(depends_on=[]),         # the first finding rests on nothing
    lambda d: [nev(d, k).update(journal=nev(d, k)['journal'] + 1) for k in ('after_first', 'after_in_band', 'after_below_again', 'after_same_again', 'after_band_moved')],   # one journal row more in every snapshot of the first State
    lambda d: [x['budget' if 'budget' in x else 'budget_after'].update(compute=4) for x in (case(d, C64)['derived_state'], lok(d, C64)['after'])],   # the look in band paid something, in the case and in the sequence
    lambda d: out(d, C65).update(status='PLAN_READY'),                                           # the loan review did not run
    lambda d: [r.update(status='PROVIDER_REQUIRED') for r in (case(d, C66)['run']['runs'][1], seq(d, C66, 1))],   # the second review stopped for another reason, in both copies
    lambda d: [(row_at(r, 'ADMISSION', -1)['cost'].update(money=1), r['cost'].update(money=1)) for r in (out(d, '04_gates'), case(d, '04_gates')['run']['runs'][0])],   # a step of an older case a unit cheaper in its gate row and in both copies of its run: only the pack file tells
    lambda d: d['action_handlers'].update(judge={'module': 'extensions.numbers_lint', 'file': 'extensions/other.py', 'sha256': '0' * 64}),   # a kind whose handler lives in a module of this version
    lambda d: d['action_handlers'].update(compare={'module': 'extensions.numbers', 'file': 'extensions/numbers.py', 'sha256': '0' * 64}),   # a comparison made by a step: an action kind of this version
    lambda d: part(d, 'alone')['look']['runs'][0].update(status='METHOD_ABSENT'),                # the look on the row authored alone stopped under another word
    lambda d: part(d, 'alone')['after']['facts'].update({S + 'fitness_below_band': dict(lok(d, C63)['after']['facts'][S + 'fitness_below_band'])}),   # somebody wrote the other row after all
    lambda d: part(d, 'alone')['after']['budget'].update(attention=1),                           # the look that asked for evidence was paid for
    lambda d: part(d, 'alone')['again'].update(remade=[]),                                       # the one row was not made again
    lambda d: part(d, 'alone')['after_again'].update(journal=1),                                 # the new reading left no look in the journal
    lambda d: part(d, 'alone')['again']['runs'][0]['comparisons'][0]['bound'].update(literal='0.6'),   # the block names another bound than the row on the books
    lambda d: d['scenes']['numbers'].update(spare=dict(seq(d, C63), comparisons=[])),            # a run kept beside the looks of the sequence, where no block would be rebuilt
    lambda d: kept(d, '04_gates').update({'orgA/fulfillment|fitness_in_band': dict(kept(d, C63)[S + 'fitness_in_band'], truth='TRUE', scope='orgA/fulfillment')}),   # a row under the adapter's name in the books of an older case that says TRUE for 0.8 >= 0.9
    lambda d: kept(d, '04_gates').update({'orgA/fulfillment|run_fitness': dict(kept(d, C63)[S + 'run_fitness'], value=0.8, scope='orgA/fulfillment')}),   # a number row with a float in the books of an older case
    lambda d: nev(d, 'after_first')['facts'][S + 'fitness_in_band']['compares'].update(partner='nowhere'),   # a row of the band made to name a row that is not there (its version does not cover the name): only the two rows set side by side tell
    liar, liar_stale, reversioned, cheaper, relabelled, reordered, restated,
    # ---- the second round: what two refuters got past the checks of the first build
    lambda d: recost_case(d, C66, lambda c: c.pop('dept_usd_cents', None)),                      # made whole: the ceiling dropped from every statement of the big review's cost (the record says the gate did not charge it)
    lambda d: recost_case(d, C66, lambda c: c.clear()),                                          # made whole: every statement of the big review's cost emptied
    lambda d: recost_event(d, 'below_again', lambda c: c.clear()),                               # made whole: the second finding cost nothing in any dimension
    lambda d: recost_event(d, 'below_again', lambda c: c.pop('attention', None)),                # made whole: the second finding's cost names no attention
    lambda d: recost_case(d, '04_gates', lambda c: c.pop('attention', None)),                    # made whole, in an older case: a dimension its State had is in no statement of the step's cost
    lambda d: recost_case(d, '09_pareto', lambda c: c.update(money=c['money'] - 1)),             # made whole, a plan that was only offered: a unit cheaper in its own cost, its SELECT row and its gate row
    lambda d: (row_at(nev(d, 'first')['runs'][0], 'ADMISSION', 0)['cost'].update(compute=0), rehash(nev(d, 'first')['runs'][0])),   # the plan's own gate row of a look of the events says another cost than the step's, the chain hashed again
    unfiled,
    lambda d: kept(d, C63)[S + 'finding_filed'].update(source='fixture/reviewed'),               # the finding of the case is not the step's row
    lambda d: nev(d, 'after_band_moved')['facts'][S + 'finding_filed'].update(depends_on=[]),   # after the band moved the finding of the old reading rests on nothing, and so reads again
    lambda d: nev(d, 'after_repaired')['facts'][S + 'finding_filed'].update(depends_on=[]),     # the same after the reading was repaired
    lambda d: nev(d, 'after_band_moved')['facts'].pop(S + 'finding_filed'),                      # the finding of the old reading is gone from the books
    lambda d: nev(d, 'after_first_bare')['facts'][S + 'finding_filed'].update(version='local-sim-2'),   # the finding of the second State under another version
    lambda d: nev(d, 'after_in_band')['facts'][S + 'finding_filed'].update(verified=False),     # the finding that went stale is said to be unverified: it would read UNKNOWN for another reason
    lambda d: nev(d, 'after_first')['facts'][S + 'run_fitness'].update(scope='orgB/elsewhere'),  # a number row that says another scope than the place it is stored in
    lambda d: part(d, 'alone')['after_again']['facts'][S + 'fitness_in_band'].update(predicate='fitness_ok'),   # a comparison row that says another predicate than the place it is stored in
    lambda d: nev(d, 'after_in_band')['facts'][S + 'fitness_band'].update(label='band-v9'),      # a row the reading did not touch changed between two snapshots
    lambda d: nev(d, 'after_bare_event')['facts'].update({S + 'waiver': {'predicate': 'waiver', 'truth': 'TRUE', 'verified': True, 'source': 'owner', 'version': '1', 'scope': S[:-1]}}),   # a row that came from nowhere between two snapshots
    lambda d: [w.update(truth='TRUE') for w in case(d, C63)['four_views']['world'] if w['predicate'] == S + 'fitness_in_band'],   # the viewer's copy of case 63 says TRUE for 0.8 >= 0.9
    lambda d: case(d, C66)['run']['runs'][1]['learning_record'].update(source_trace='0' * 64),   # the learning of the review that stopped on the ceiling is bound to another trace
    lambda d: nev(d, 'in_band')['runs'][0]['provenance'].pop(),                                  # a look of the events says it loaded one pack less
    lambda d: nev(d, 'in_band')['runs'][0].update(goal_truth_after='TRUE'),                      # a look says its goal read TRUE after it; the books hold no row of that goal
    lambda d: part(d, 'alone')['look']['runs'][0].update(needs=['finding_filed']),               # a look that ran nothing says it was to make the finding
    lambda d: nev(d, 'below_again')['runs'][0]['candidates'].append({'id': 'x', 'status': 'PROPOSED_ONLY'}),   # a candidate on a look that constructed nothing
    lambda d: nev(d, 'first_bare')['runs'][0].update(selected_branch='R-CONFORMS@1/OR1'),        # the first look of the second State is not the look of case 63: it says it took the other branch of the rule
    lambda d: nev(d, 'same_again')['runs'][0]['proof'].pop(),                                    # the look that stood on the earlier finding does not say so in its proof
    lambda d: nev(d, 'pack_event')['runs'][0]['proof'].append('fitness_in_band observed TRUE (adapter:numbers/compare@1)'),   # a look that asked for evidence argues from the comparison it could not read
    lambda d: part(d, 'next_run')['look']['runs'][0].update(selected_branch='R-CONFORMS@1/OR1'),   # a goal that has no rule is said to have taken a branch of one
    on_a_finding, relabelled_whole, reviewed_false,
    lambda d: case(d, C64).update(scope='orgB/elsewhere'),                                       # a case said to have run in another scope than its packs name
    lambda d: case(d, C63)['derived_state']['rule_ids'].pop(),                                   # the case's books list no rule
    lambda d: case(d, C63)['four_views']['knowledge'][0].update(branches=[['fitness_in_band']]),   # the viewer's copy of the rule knows no finding
    lambda d: part(d, 'bare')['look']['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'),         # the number alone was enough
    lambda d: part(d, 'bare')['after']['facts'].update({S + 'fitness_in_band': dict(lok(d, C64)['after']['facts'][S + 'fitness_in_band'])}),   # a comparison row beside the number that was to stand alone
    lambda d: part(d, 'bare')['event'].update(affected=['run_judged']),                          # the reading that nothing compares is said to have touched the goal
    lambda d: part(d, 'bare')['after_again']['facts'][S + 'run_fitness'].update(value='0.8'),    # the second reading is not on the books
    lambda d: part(d, 'bare')['after_again']['budget'].update(compute=4),                        # a look that asked for evidence was paid for
    lambda d: nev(d, 'pack_event')['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'),            # after the reading in a pack the look stood on the old verdict
    lambda d: nev(d, 'pack_event')['runs'][0]['comparisons'][0].update(reads='TRUE'),            # a comparison of the old reading read as if it stood
    lambda d: nev(d, 'after_pack_event')['facts'][S + 'run_fitness'].update(label='run-0009'),   # the reading on the books is not the pack's
    lambda d: nev(d, 'after_pack_event')['facts'].update({S + 'run_fitness': dict(nev(d, 'after_repaired')['facts'][S + 'run_fitness'])}),   # the pack's reading never arrived
    lambda d: nev(d, 'after_pack_event').update(journal=nev(d, 'after_repaired')['journal']),    # the look after the pack left no journal row
    lambda d: part(d, 'next_run')['look']['runs'][1]['shortfall'][0].update(left=60),            # one run later the ceiling had room again
    lambda d: part(d, 'next_run')['look']['runs'][1]['shortfall'][0].update(dimension='usd_cents'),   # one run later the review stopped on the run cap
    lambda d: part(d, 'next_run')['after']['budget'].update(usd_cents=158),                      # the run cap was not set again
    lambda d: part(d, 'next_run')['after']['budget'].update(dept_usd_cents=60),                  # the ceiling was set again with the run cap
    lambda d: part(d, 'next_run')['look']['runs'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),   # the big review ran a second time
    lambda d: part(d, 'next_run')['look']['runs'].reverse(),                                     # one run later the queue was taken in another order
    lambda d: part(d, 'next_run')['packs'].pop()]                                                # the next run is said to have loaded no pack of its own

PACK_FORGERIES = [   # the pack files changed, the record left as it is: `p` is name -> pack
    lambda p: p['153_finding_method']['methods'].append({'id': 'fix-fitness@1', 'effect': 'fitness_in_band', 'requires': [], 'provider': 'local-provider', 'grant': 'action:fix-fitness@1',
                                                         'cost': {'compute': 0}, 'action': 'simulate_fact', 'approved': True}),   # a method that makes a comparison's predicate true by itself
    lambda p: p['153_finding_method']['methods'].append({'id': 'measure-fitness@1', 'effect': 'run_fitness', 'requires': [], 'provider': 'local-provider', 'grant': 'action:measure-fitness@1',
                                                         'cost': {'compute': 1}, 'action': 'simulate_fact', 'approved': True}),   # a method that makes a number
    lambda p: p['151_conformance_theory']['rules'].append({'id': 'R-WAIVE@1', 'head': 'fitness_in_band', 'branches': [['waiver_given']], 'approved': True}),   # a rule that derives a comparison
    lambda p: (p['151_conformance_theory']['rules'].append({'id': 'R-BELOW@1', 'head': 'below_band', 'branches': [['fitness_below_band']], 'approved': True}),
               p['153_finding_method']['methods'][0].update(requires=['below_band'])),              # a step that requires a rule head over a comparison
    lambda p: p['152_run_fitness']['evidence'][1].update(truth='TRUE'),                              # the pack file says TRUE for 0.8 >= 0.9
    lambda p: p['154_run_fitness_in_band']['evidence'].pop(),                                        # half a band in the pack file
    lambda p: p['155_loan_goal'].pop('preference'),                                                  # a new budget dimension that no preference names
    lambda p: p['156_loan_review']['methods'][0]['cost'].update(usd_cents=42.0),                     # a fraction-typed cost
    lambda p: p['156_loan_review']['methods'][0]['cost'].update(usd_cents=41),                       # the pack prices the review a cent lower than the gate charged
    lambda p: p['155_loan_goal']['budget'].update(usd_cents=10 ** 18),                               # an amount the kernel does not take
    lambda p: p['153_finding_method']['methods'][0]['cost'].update(attention=2),
    lambda p: p['150_conformance_goal']['budget'].update(compute=6),
    lambda p: p['158_queue_reviews']['methods'][1]['cost'].pop('dept_usd_cents'),                    # a method under the ceiling that does not cost it
    lambda p: p['158_queue_reviews'].update(budget={'dept_usd_cents': 60}),                          # a later pack sets the ceiling again, to the level it had
    lambda p: p['157_review_queue']['budget'].update(usd_cents=50),                                  # a run cap so low that the second review would stop on it too
    lambda p: p['04_admission']['providers'].update({'local-provider': 5.0}),                        # a capacity that is not a whole number, in a pack of an older case
    lambda p: p['157_review_queue']['goals'].reverse(),                                              # the goals out of the order of their impact
    lambda p: p['157_review_queue']['impact'].update(small_loan_reviewed='10'),
    lambda p: p['157_review_queue']['impact'].update(small_loan_reviewed=1),                         # an impact that is not exact text
    lambda p: p['159_one_row_alone']['evidence'][1]['compares']['bound'].update(literal='0.8'),      # the pack file compares against another bound than the row the look read
    lambda p: p['153_finding_method']['methods'][0].update(requires=[]),                             # the finding needs no comparison at all
    # ---- the second round
    lambda p: p['04_admission'].update(budget={'tokens': 5}),                                        # a pack of an older case says its State had a dimension that no gate row of its runs names
    lambda p: p['156_loan_review'].update(budget={'reviews': 3}),                                    # the same in a case of this version
    lambda p: p['152_run_fitness']['evidence'].insert(0, {'predicate': 'fitness_in_band', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': 'owner', 'version': 'waiver-1'}),   # a decision stands where the pack carries a row of the band: the adapter's row would be turned away
    lambda p: p['153_finding_method'].update(evidence=[{'predicate': 'fitness_below_band', 'truth': 'FALSE', 'verified': True, 'source': 'desk', 'version': '1'}]),   # a later pack puts another writer's row in the place of a comparison
    lambda p: p['153_finding_method']['methods'].append({'id': 'tell-owner@1', 'effect': 'owner_told', 'requires': ['finding_filed'], 'provider': 'local-provider', 'grant': 'action:file-finding@1',
                                                         'cost': {'compute': 1}, 'action': 'simulate_fact', 'approved': True}),   # a step two steps below a comparison that does not name it
    lambda p: p['158_queue_reviews'].update(goals=['small_loan_reviewed', 'big_loan_reviewed']),     # a later pack sets the goals again, out of the order of their impact
    lambda p: p['158_run_cap_again']['budget'].update(dept_usd_cents=60),                            # the pack of the next run sets the ceiling again with the run cap
    lambda p: p['158_run_cap_again']['budget'].update(usd_cents=100),                                # the pack of the next run sets another run cap than the queue had
    lambda p: p['152_number_alone']['evidence'].append(dict(p['152_run_fitness']['evidence'][1])),   # the pack of the number alone carries a comparison row
    lambda p: p['152_number_alone']['evidence'][0].update(label='run-0009')]                         # the number alone is not the number of case 63

KERNEL_FORGERIES = [   # the text of kernel/core.py changed: a kernel that carries a word of this version is not the kernel this version was built on
    lambda text: text + "\n# a later line: row.get('value')\n",
    lambda text: 'from fractions import Fraction\n' + text,
    lambda text: text + "\ndef renumber(state, row):pass\n"]


def checks(data, ROOT, sha_of_the_verifier, check_chain):
    """The ten rows of this module: (id, held, detail). It never raises: a record, a pack file or a kernel source it cannot read is ten failed rows that say so."""
    try:
        SCEN = {f.stem: json.loads(f.read_text()) for f in sorted((ROOT / 'scenarios').glob('*.json'))}
        core = (ROOT / 'kernel' / 'core.py').read_text()
        got = claims(data, SCEN, core)
        raw, packs = json.dumps(data), json.dumps(SCEN)
    except Exception as e:
        return [(name, False, 'the record, the pack files or the kernel source cannot be read: ' + type(e).__name__) for name in NAMES + (LAST,)]

    def forged(change, what):   # the claims on a forged copy of the record, of the pack files or of the kernel's source: they must not all hold
        d, p, text = json.loads(raw), json.loads(packs), core
        try:
            if what == 'kernel':
                text = change(text)
            else:
                change(p if what == 'pack' else d)
        except Exception:
            return False   # the forgery could not be made on this record: it shows nothing, and is counted as not refused
        try:
            return not all(claims(d, p, text).values())
        except Exception:
            return True    # a forged record the claims cannot read does not hold
    missed = ([f'record {i}' for i, f in enumerate(RECORD_FORGERIES) if not forged(f, 'record')] + [f'pack {i}' for i, f in enumerate(PACK_FORGERIES) if not forged(f, 'pack')]
              + [f'kernel {i}' for i, f in enumerate(KERNEL_FORGERIES) if not forged(f, 'kernel')])
    return [(name, got[name] is True, '') for name in NAMES] + [(LAST, all(got.values()) and not missed, 'forgeries that no check refused, or that could not be made: ' + ', '.join(missed) if missed else '')]
