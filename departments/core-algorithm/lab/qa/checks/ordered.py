"""Independent checks for 0.16.0-ordered (matrix rows R73, R82, R80): cases 54 to 56 and the sequence scenes.ordered.
Reads the record, the pack files, the three case files and the bytes of the kind file (for its sha256); never imports
the lab's code, never reads results/ and writes nothing.

How it reads. The record keeps lives: one State from its packs, taken through named steps, with a snapshot after each
(see tools/scenes/ordered.py). This file holds its own script of every life (what was done at each step and what each
run did: its status, its steps, what is pending, what stopped it, which rows it named) and its own bookkeeper (`Books`):
what a State holds, worked out from the pack files and from what the script says ran. With the two it REBUILDS, step
by step, everything the record says and compares it whole, as JSON text (1 is not true and not 1.0):

  what was done   every row handed in, every proposal measured again, every stamp, equal to the script's
  what came back  the block's status, goals or affected goals, and the stamp's row made from the receipt it answers
  each run        its goal, scope, the goal's truth before and after, status, work state, steps, pending, waits, stop,
                  branch, stop reasons, cost, the packs loaded, every receipt (made again here, hash included), what
                  it needs made and its proof (argued again here from the plan), the rows its trace names, and the
                  trace's own chain; no key may be missing or added
  each snapshot   scope, budget, slots, grants, questions out, journal, what every fact reads and the row stored for it
  each case       the same for its one look, and its derived state and views

What the lab's extensions compute (the scrub of a text, the three tests on a cut proposal, the soundness of the tier
packs) is computed here a second time from this file's own reading of the sources. The scrub by code is a declared
action kind: the record's list of handlers must name `scrub_text` with the file kinds/scrub_text.py and that file's
sha256, read here from the file. Nothing in cases 54 to 56 or in the sequence is left unread. Every line of a trace is checked against the books as they stood (what it says was observed,
refined, matched, admitted, missing, refused, selected, made, stopped or closed), and the trace's hash chain is checked;
only the order and the number of the lines of a search rest on the chain alone.

S79 runs the same claims on forged copies: a list of hand-made forgeries (records and pack files, one change each;
some rewrite a line of a trace and chain the trace again), and one leaf in every STRIDE of cases 54 to 56 and of every
life, changed in place. Each must make its claim fail. `sweep` changes every leaf; the unit tests run it once."""
import hashlib
import json
import re

FULL = {'compute': 10, 'money': 10, 'attention': 3}
SENTENCE = 'LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'
PACKS = ['120_feedback', '121_scrub_simulated', '122_scrub_by_code', '123_team_rail', '124_cut_desk', '125_fan_in_rules',
         '126_tier_internal', '127_tier_portfolio', '128_tier_project', '129_tier_external']
STRIDE = 37   # S79 changes one leaf in this many; `sweep` with stride 1 changes them all

J = lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
same = lambda a, b: J(a) == J(b)
digest = lambda v: hashlib.sha256(J(v).encode()).hexdigest()
copy = lambda v: json.loads(json.dumps(v))


# ---------------------------------------------------------------------------------------------- this file's own sanitizer and adapter
MARKS = (('<HOME>', r'/(?:Users|home)/[^/\s]+'), ('<EMAIL>', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'), ('<OPAQUE>', r'[A-Za-z0-9+/=_-]{40,}'))


def _scrub(text):
    """The clean text, the number of redactions, the ASCII letters and digits left."""
    n = 0
    for mark, pattern in MARKS:
        text, k = re.subn(pattern, mark, text)
        n += k
    return text, n, len(re.findall(r'[A-Za-z0-9]', re.sub(r'<[A-Z]+>', '', text)))


CUT_SOURCE = 'adapter:ordered/cut@1'
NEVER_CUT = ('proto-000-text', 'boundary-enforcement-preamble', 'policy-coverage-markers', 'coverage-evidence-requirements')
QUESTIONS = {'baseline_cited': 'the proposal cites a measured baseline: where it was measured, which metric, what value',
             'samples_ge_100': 'the baseline rests on at least 100 samples',
             'guardrails_hold': 'the override count has not risen, triage accuracy is 90 or more, and nothing on the do-not-cut list is touched'}


def _cut_rows(p):
    """This file's own reading of a cut proposal: row name -> the whole row the adapter must have made."""
    whole = lambda v: type(v) is int and v >= 0
    text = lambda v: type(v) is str and v.strip() != ''
    part = lambda d, k: d.get(k) if type(d.get(k)) is dict else {}
    b, g, t = part(p, 'baseline'), part(p, 'guardrails'), p.get('touches')
    o = part(g, 'override_count_total')
    named = type(t) is list and len(t) > 0 and all(type(x) is str and re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', x) is not None for x in t)
    touched = sorted(set(x for x in t if x in NEVER_CUT)) if named else None
    measured = {'baseline_cited': {'source': b.get('source'), 'metric': b.get('metric'), 'value': b.get('value')},
                'samples_ge_100': {'samples': b.get('samples'), 'floor': 100},
                'guardrails_hold': {'override_count_before': o.get('before'), 'override_count_now': o.get('now'), 'triage_correct_pct': g.get('triage_correct_pct'),
                                    'triage_floor': 90, 'touches_do_not_cut': touched}}
    holds = {'baseline_cited': text(b.get('source')) and text(b.get('metric')) and whole(b.get('value')),
             'samples_ge_100': whole(b.get('samples')) and b['samples'] >= 100,
             'guardrails_hold': whole(o.get('before')) and whole(o.get('now')) and o['now'] <= o['before'] and whole(g.get('triage_correct_pct')) and g['triage_correct_pct'] >= 90 and touched == []}
    out = {}
    for name in measured:
        row, truth = p['cut'] + '_' + name, 'TRUE' if holds[name] else 'FALSE'
        verdict = {'row': row, 'truth': truth, 'floors': {k: v for k, v in measured[name].items() if k.endswith('floor')}}   # the version names the verdict, not the numbers
        out[row] = {'predicate': row, 'truth': truth, 'verified': True, 'source': CUT_SOURCE, 'version': 'cut-' + digest(verdict)[:12],
                    'checked': p.get('id'), 'question': QUESTIONS[name], 'measured': measured[name]}
    return out


# ---------------------------------------------------------------------------------------------- this file's own bookkeeper
class Books:
    """What a State holds, from the pack files and from what is done to it. Planning is not done here: which steps a run
    took comes from the script; what those steps make, cost and leave behind is worked out here."""

    def __init__(self, files, names):
        self.files, self.scope, self.goals, self.rows, self.rules, self.methods = files, 'orgA/fulfillment', [], {}, {}, {}
        self.slots, self.grants, self.budget, self.loaded, self.journal, self.asks = {}, set(), dict(FULL), [], [], {}
        for n in names:
            self.apply(n)

    def apply(self, name):
        p = self.files[name]
        if 'scope' in p:
            self.scope = p['scope']
        if 'goals' in p:
            self.goals = list(p['goals'])
        for row in p.get('evidence', []):
            self.take(row)
        for r in p.get('rules', []):
            if r.get('approved') is True:
                self.rules[r['head']] = r
        for m in p.get('methods', []):
            if m['id'] in self.methods:
                raise ValueError('one step under two packs')   # the kernel refuses such a State
            self.methods[m['id']] = m
        self.slots.update(p.get('providers', {}))
        self.grants = (self.grants | set(p.get('grants', []))) - set(p.get('revoke_grants', []))
        self.budget.update(p.get('budget', {}))
        self.loaded.append({'pack': p['id'], 'sha256': digest(p)})

    def take(self, row):
        """A row handed in by a pack, an event or a stamp -> 'unverified', 'stands' (a decision is on the fact) or 'kept'."""
        scope = row.get('scope', self.scope)
        key = scope + '|' + row['predicate']
        if row.get('verified') is not True:
            return 'unverified'
        if self.rows.get(key, {}).get('final') and not row.get('final'):
            self.journal.append({'status': 'DECISION_STANDS', 'scope': scope, 'predicate': row['predicate']})
            return 'stands'
        self.rows[key] = dict(row, scope=scope)
        return 'kept'

    def row(self, p):
        return self.rows.get(self.scope + '|' + p)

    def read(self, p, seen=()):
        """The row a fact reads as, or None: a row counts only while every row it rests on is there, TRUE, at the version it cites."""
        row = self.row(p)
        if row is None or p in seen:
            return None
        for dep in row.get('depends_on', []):
            other = self.read(dep['predicate'], seen + (p,))
            if other is None or other['truth'] != 'TRUE' or J(other.get('version')) != J(dep.get('version')):
                return None
        return row

    def truth(self, p):
        row = self.read(p)
        return row['truth'] if row else 'UNKNOWN'

    def rests_on(self, p, changed, seen=()):
        if p == changed:
            return True
        if p in seen:
            return False
        seen = seen + (p,)
        rule = self.rules.get(p)
        if rule and any(self.rests_on(c, changed, seen) for branch in rule['branches'] for c in branch):
            return True
        if any(self.rests_on(q, changed, seen) for m in self.methods.values() if m['effect'] == p for q in m.get('requires', [])):
            return True
        return any(d.get('predicate') == changed for d in (self.row(p) or {}).get('depends_on', []))

    def cost(self, steps):
        return {dim: sum(self.methods[mid].get('cost', {}).get(dim, 0) for mid in steps) for dim in self.budget}

    def argue(self, p, plan, alternative=None):
        """What a plan needs made and why its goal will hold, as a run words it (`needs`, `proof`): a fact that reads TRUE is observed; a rule's
        head holds by one alternative, each of its conditions argued in turn; anything else is made by the plan's step for it, on that step's prerequisites."""
        row = self.read(p)
        if row and row['truth'] == 'TRUE':
            return [], [f'{p} observed TRUE ({row.get("source")})']
        rule = self.rules.get(p)
        if rule:
            for i, branch in enumerate(rule['branches']):
                parts = [self.argue(c, plan) for c in branch] if alternative in (None, i + 1) else [None]
                if all(part is not None for part in parts):
                    needs, proof = [], [f'{p} ⇐ {rule["id"]}: alternative {i + 1}']
                    for n, why in parts:
                        needs, proof = needs + n, proof + why
                    return list(dict.fromkeys(needs)), proof
            return None
        made = [mid for mid in plan if self.methods[mid]['effect'] == p]
        if not made:
            return None
        needs, proof = [p], [f'{made[0]} would establish {p}']
        for q in self.methods[made[0]].get('requires', []):
            part = self.argue(q, plan)
            if part is None:
                return None
            needs, proof = needs + part[0], proof + part[1]
        return list(dict.fromkeys(needs)), proof

    def admission(self, steps):
        """The gate's line for these steps as the books stand: over budget, a grant not held, a provider without a slot."""
        why, cost, use = set(), self.cost(steps), {}
        if any(cost[dim] > self.budget[dim] for dim in cost):
            why.add('RESOURCE_REQUIRED')
        for mid in steps:
            m = self.methods[mid]
            if m.get('grant') and m['grant'] not in self.grants:
                why.add('AUTHORITY_REQUIRED')
            if m.get('provider'):
                use[m['provider']] = use.get(m['provider'], 0) + 1
        if any(self.slots.get(provider, 0) < n for provider, n in use.items()):
            why.add('PROVIDER_REQUIRED')
        return {'methods': steps, 'accepted': not why, 'blockers': sorted(why), 'cost': cost}

    def told(self, op, d):
        """Is this line of a run's search true of the books as they stand? Each kind of line says one thing, and it is checked whole."""
        p = d.get('predicate')
        row, makers = self.read(p) if type(p) is str else None, [m for m in self.methods.values() if m['effect'] == p and m.get('approved', True)]
        if op == 'RETAIN':
            return row is not None and row['truth'] == 'TRUE' and same(d, {'predicate': p, 'source': row.get('source'), 'version': row.get('version')})
        if op == 'REFINE':
            rule = self.rules.get(p)
            return rule is not None and same(d, {'predicate': p, 'rule': rule['id'], 'alternatives': len(rule['branches'])})
        if op == 'METHOD_MATCH':
            return same(d, {'predicate': p, 'method': d.get('method')}) and d.get('method') in [m['id'] for m in makers]
        if op == 'METHOD_ABSENT':
            return same(d, {'predicate': p}) and row is not None and row['truth'] == 'FALSE' and not row.get('final') and not makers
        if op == 'QUERY_EVIDENCE':
            return same(d, {'predicate': p}) and (row is None or row['truth'] == 'UNKNOWN') and (p in self.rules or not makers)
        if op == 'REFUSED':
            return row is not None and row['truth'] == 'FALSE' and row.get('final') is True and same(d, {'predicate': p, 'source': row.get('source')})
        if op == 'ADMISSION':
            return type(d.get('methods')) is list and all(mid in self.methods for mid in d['methods']) and same(d, self.admission(d['methods']))
        return op in ('GOAL_ACCEPTED', 'BLOCK', 'ASK_CLOSED', 'TERMINAL')   # read whole elsewhere; any other kind of line has no place in a search

    def step(self, mid):
        """One step runs: its row is made, it is paid, and the receipt the kernel must have issued is returned."""
        m = self.methods[mid]
        deps = [{'predicate': q, 'version': (self.read(q) or {}).get('version')} for q in m.get('requires', [])]
        made = {'predicate': m['effect'], 'truth': 'TRUE', 'verified': True, 'evidence_kind': 'SIMULATED_LOCAL', 'depends_on': deps}
        rec = {'method': mid, 'scope': self.scope, 'action': m['action'], 'status': 'LOCAL_ONLY'}
        if m['action'] == 'simulate_fact':
            self.take(dict(made, source='LOCAL_MODEL:' + mid, version='local-sim-1'))
            rec['model_effect'] = m['effect']
        elif m['action'] == 'scrub_text':
            clean, n, left = _scrub(self.read(m['scrubs'])['text'])
            if left < 10:
                raise ValueError('the sanitizer refuses these words')
            self.take(dict(made, source='LOCAL_SCRUB:' + mid, version='scrub-' + digest(clean)[:12], clean_text=clean, redactions=n))
            rec.update(model_effect=m['effect'], redactions=n, clean_sha256=digest(clean))
        elif m['action'] == 'ask':
            rec.update(ask={'predicate': m['effect'], 'question': m['question'], 'to': m['ask_to'], 'asked_in': digest({'packs': self.loaded, 'runs': self.journal})}, parked=True)
        else:
            raise ValueError('a kind this file does not know')
        rec['sha256'] = digest(rec)
        if m['action'] == 'ask':
            self.asks[self.scope + '|' + m['effect']] = {'method': mid, 'receipt': rec['sha256'], 'issued': rec}
        for dim, v in m.get('cost', {}).items():
            self.budget[dim] -= v
        self.slots[m['provider']] -= 1
        return rec

    def close(self):
        """The end of an executed run: a question whose fact holds a decision leaves the books. -> the lines the run's trace must carry."""
        lines = []
        for key in [k for k in self.asks if k.startswith(self.scope + '|')]:
            seen = self.read(key.split('|', 1)[1]) or {}
            if seen.get('final'):
                lines.append({'ask': key, 'receipt': self.asks[key]['receipt'], 'truth': seen['truth'], 'source': seen.get('source')})
                del self.asks[key]
        return lines

    def snap(self, facts):
        return {'scope': self.scope, 'budget': self.budget, 'providers': self.slots, 'grants': sorted(self.grants),
                'open_asks': {k: v for k, v in self.asks.items() if k.startswith(self.scope + '|') and not (self.read(k.split('|', 1)[1]) or {}).get('final')},
                'journal': [j['status'] for j in self.journal], 'reads': {p: self.truth(p) for p in facts}, 'rows': {p: self.row(p) for p in facts}}


# ---------------------------------------------------------------------------------------------- one run, one step, one life, one case
WORK = {'LOCAL_MODEL_EFFECTS_RECORDED': 'completed', 'SUPPORTED_BY_EVIDENCE': 'completed', 'STEP_STOPPED': 'stopped', 'WAITING': 'waiting'}
RUN_KEYS = {'goal', 'scope', 'goal_truth_before', 'work_state', 'actions', 'needs', 'cost', 'proof', 'model_receipts', 'candidates', 'selected_branch', 'stop_reasons',
            'provenance', 'status', 'pareto_options', 'trace', 'trace_root_sha256', 'claim'}
NAMED = ('METHOD_ABSENT', 'QUERY_EVIDENCE', 'REFUSED')


def _run(books, r, want, bad, chain, case=False):
    """One recorded run against the books before it and the script's line for it; the books then take what it did."""
    status, steps = want['status'], want['actions']
    work = WORK.get(status, 'blocked')
    blocked = work == 'blocked'
    plan = steps + want.get('pending', [])
    keys = RUN_KEYS | {k for k in ('pending', 'waits', 'stopped') if k in want} | (set() if blocked else {'goal_truth_after'}) | ({'learning', 'learning_record'} if case else set())
    if set(r) != keys:
        bad('keys ' + str(sorted(set(r) ^ keys)))
    pins = {'goal': want['goal'], 'scope': books.scope, 'goal_truth_before': books.truth(want['goal']), 'status': status, 'work_state': work, 'actions': steps,
            'selected_branch': want['branch'], 'stop_reasons': want.get('why', []), 'candidates': [], 'provenance': books.loaded, 'claim': SENTENCE,
            'cost': None if blocked else books.cost(steps)}
    pins.update({k: want[k] for k in ('pending', 'waits', 'stopped') if k in want})
    pins['needs'], pins['proof'] = ([], []) if blocked else (books.argue(want['goal'], plan, int(want['branch'].rsplit('/OR', 1)[1]) if want['branch'] else None) or (None, None))
    full = None if blocked else books.cost(plan)
    stop_reads = books.truth(books.methods[want['stopped']['method']]['effect']) if 'stopped' in want else None
    t = r['trace']
    chose = [i for i, e in enumerate(t) if e['operation'] == 'SELECT'][:1]
    search, acting = (t[:chose[0]], t[chose[0]:]) if chose else (t, [])
    told = all(books.told(e['operation'], e['data']) for e in search)   # every line of the search, against the books as they stood before any step ran
    receipts, gates = [], []
    for mid in steps:   # the steps run here, in the books: the gate's line for each, then its receipt
        gates.append(books.admission([mid]))
        receipts.append(books.step(mid))
    if 'stopped' in want:
        gates.append(books.admission([want['stopped']['method']]))   # the step that stopped had passed the gate
    pins['model_receipts'] = receipts
    if not blocked:
        pins['goal_truth_after'] = 'MODEL_DERIVABLE_NOT_EXTERNAL_PROOF' if status == 'LOCAL_MODEL_EFFECTS_RECORDED' else books.truth(want['goal'])
    closed = books.close()
    rows = lambda op: [e['data'] for e in t if e['operation'] == op]
    chosen = rows('SELECT')
    pins['pareto_options'] = 0 if blocked else (chosen[0].get('pareto_options') if len(chosen) == 1 else None)
    if case:
        pins.update(learning=[], learning_record={'source_trace': r.get('trace_root_sha256'), 'learning_sha256': digest([])})
    for k, v in pins.items():
        if k not in r or not same(r[k], v):
            bad(k)
    trace = {'first': (t[0]['operation'], t[0]['data']) == ('GOAL_ACCEPTED', {'goal': want['goal'], 'scope': books.scope}),
             'last': (t[-1]['operation'], t[-1]['data']) == ('TERMINAL', {'status': status, 'work_state': work}) and r['trace_root_sha256'] == t[-1]['sha256'],
             'chain': chain is None or chain(t) is True,
             'search': told,
             'steps': all(e['operation'] in ('SELECT', 'ADMISSION', 'LOCAL_EFFECT', 'STEP_STOPPED', 'ASK_CLOSED', 'TERMINAL') for e in acting)
             and same([e['data'] for e in acting if e['operation'] == 'ADMISSION'], gates),
             'receipts': same([x['receipt'] for x in rows('LOCAL_EFFECT')], receipts),
             'plan': (same(rows('BLOCK'), [{'reason': status, 'all_reasons': want.get('why', [])}]) and chosen == []) if blocked
             else (len(chosen) == 1 and same(chosen[0].get('actions'), plan) and same(chosen[0].get('full_cost'), full) and rows('BLOCK') == []),
             'stop': same(rows('STEP_STOPPED'), [dict(want['stopped'], effect_reads=stop_reads)] if 'stopped' in want else []),
             'skipped': rows('STEP_ALREADY_TRUE') == [],
             'closed': same(rows('ASK_CLOSED'), closed),
             'named': all(sorted(set(x.get('predicate') for x in rows(op))) == want.get('named', {}).get(op, []) for op in NAMED),
             'gate': 'gate' not in want or same([[a['methods'], a['accepted'], a['blockers']] for a in rows('ADMISSION')], want['gate'])}
    for k, ok in trace.items():
        if not ok:
            bad('trace ' + k)
    books.journal.append({'goal': want['goal'], 'scope': books.scope, 'status': status, 'trace_root_sha256': r['trace_root_sha256']})


def _runs(books, block, head, want, bad, chain, case=False):
    """A block the kernel returned for a look or an event that reached the goals: its head whole, then its runs, one per goal."""
    if set(block) != set(head) | {'runs'} or not all(same(block[k], v) for k, v in head.items()):
        bad('head')
    goals = head.get('goals', head.get('affected'))
    if [w['goal'] for w in want] != goals or len(block['runs']) != len(want):
        bad('goals')
    for r, w in zip(block['runs'], want):
        _run(books, r, w, lambda what, g=w['goal']: bad(g + ': ' + what), chain, case)


def _handed(books, row, does, result, want, bad, chain):
    """A row handed in as an event: ignored, kept under another scope, or taken and the goals that rest on it looked at again."""
    took = books.take(row)
    quiet = 'UNVERIFIED_EVENT_IGNORED' if took == 'unverified' else 'DECISION_STANDS' if took == 'stands' else 'OUT_OF_SCOPE' if row.get('scope', books.scope) != books.scope else None
    if quiet:
        if want != quiet or not same(result, {'status': quiet, 'affected': [], 'runs': []}):
            bad('result')
    elif type(want) is not list:
        bad('result')
    else:
        _runs(books, result, {'status': 'RECONCILED', 'event': row, 'affected': [g for g in books.goals if books.rests_on(g, row['predicate'])]}, want, bad, chain)


def _life(life, files, spec, chain=None):
    """One recorded life against its script -> [(step, what is wrong)]; empty when the record is what the pack files and the script give."""
    packs, facts, steps = spec
    out = []
    try:
        if set(life) != {'packs', 'start', 'steps'} or not same(life['packs'], packs) or list(life['steps']) != [s[0] for s in steps]:
            out.append(('life', 'shape'))
        books = Books(files, packs)
        if not same(life['start'], books.snap(facts)):
            out.append(('start', 'snapshot'))
        for name, does, want in steps:
            rec = life['steps'][name]
            bad = lambda what, name=name: out.append((name, what))
            if set(rec) != {'does', 'result', 'after'}:
                bad('keys')
            if does[0] == 'look':
                if not same(rec['does'], {'look': 'executed'}):
                    bad('does')
                _runs(books, rec['result'], {'status': 'EVALUATED', 'goals': books.goals}, want, bad, chain)
            elif does[0] == 'event':
                if not same(rec['does'], {'event': does[1]}):
                    bad('does')
                _handed(books, does[1], rec['does'], rec['result'], want, bad, chain)
            elif does[0] == 'measured':
                part, edit = EDITS[does[1]]
                proposal = copy([p for p in files['124_cut_desk']['proposals'] if p['cut'] == 'hook_chain'][0])
                edit(proposal)
                row = _cut_rows(proposal)['hook_chain_' + part]
                if not same(rec['does'], {'proposal': proposal, 'event': row}):
                    bad('does')
                _handed(books, row, rec['does'], rec['result'], want, bad, chain)
            elif does[0] == 'answer':
                _, step, at, truth, by = does
                if not same(rec['does'], {'answer': {'step': step, 'run': at, 'truth': truth, 'by': by}}):
                    bad('does')
                receipt = life['steps'][step]['result']['runs'][at]['model_receipts'][0]
                fact = receipt['ask']['predicate']
                if not same(books.asks.get(books.scope + '|' + fact, {}).get('issued'), receipt) or receipt['ask']['to'] != by:
                    bad('no such question is out')
                keeps = books.read(fact) if truth == 'TRUE' and books.truth(fact) == 'TRUE' else None
                row = {'predicate': fact, 'truth': truth, 'verified': True, 'final': True, 'source': 'STAMP:' + by,
                       'version': keeps['version'] if keeps else 'ask-' + receipt['sha256'][:12], 'answers': receipt['sha256'], 'scope': books.scope}
                _handed(books, row, rec['does'], rec['result'], want, bad, chain)
            else:   # apply
                if not same(rec['does'], {'apply': does[1]}) or rec['result'] is not None:
                    bad('does')
                books.apply(does[1])
            if not same(rec['after'], books.snap(facts)):
                bad('snapshot')
    except Exception as e:
        out.append(('life', 'cannot be read: ' + type(e).__name__))
    return out


CASE_KEYS = {'id', 'title', 'description', 'area', 'packs', 'pack_digest', 'scope', 'run', 'outcome', 'derived_state', 'four_views'}


def _case(c, files, case_file, spec, chain=None):
    """One recorded case against its file, its packs and its script: the one look, then the State it left, whole."""
    packs, want = spec
    out = []
    bad = lambda what: out.append(('case', what))
    try:
        if set(c) != CASE_KEYS or set(case_file) != {'id', 'title', 'description', 'packs', 'execute', 'area', 'expected'}:
            bad('keys')
        if not same([c[k] for k in ('id', 'title', 'description', 'area', 'packs')], [case_file[k] for k in ('id', 'title', 'description', 'area', 'packs')]) \
                or not same(case_file['packs'], packs) or case_file['execute'] is not True or case_file['expected'] != want[0]['status']:
            bad('file')
        books = Books(files, packs)
        if c['pack_digest'] != digest([files[n] for n in packs]) or not same(c['scope'], books.scope):
            bad('packs')
        _runs(books, c['run'], {'status': 'EVALUATED', 'goals': books.goals}, want, bad, chain, case=True)
        if not same(c['outcome'], c['run']['runs'][0]):
            bad('outcome')
        if not same(c['derived_state'], {'facts': books.rows, 'rule_ids': [r['id'] for r in books.rules.values()], 'candidate_count': 0,
                                         'budget_after': books.budget, 'historical_events': books.journal}):
            bad('derived state')
        if not same(c['four_views'], {'world': [{'predicate': k, 'truth': v['truth'], 'source': v.get('source')} for k, v in books.rows.items()],
                                      'knowledge': list(books.rules.values()), 'design': c['outcome']['actions'], 'run': c['outcome']['trace']}):
            bad('views')
    except Exception as e:
        bad('cannot be read: ' + type(e).__name__)
    return out


# ---------------------------------------------------------------------------------------------- the script: what each run did
def done(goal, steps, branch=''):
    return {'goal': goal, 'status': 'LOCAL_MODEL_EFFECTS_RECORDED', 'actions': steps, 'branch': branch}


def held(goal, branch=''):
    return {'goal': goal, 'status': 'SUPPORTED_BY_EVIDENCE', 'actions': [], 'branch': branch}


def halted(goal, pending, reason):
    return {'goal': goal, 'status': 'STEP_STOPPED', 'actions': [], 'pending': pending, 'stopped': {'method': pending[0], 'reason': reason}, 'branch': ''}


def asks(goal, ask, pending, branch):
    return {'goal': goal, 'status': 'WAITING', 'actions': [ask], 'pending': pending, 'waits': [ask], 'branch': branch}


def stuck(goal, status, why, **named):
    return {'goal': goal, 'status': status, 'actions': [], 'branch': None, 'why': why, 'named': named}


LOOK = ('look',)

# R73. The words, the refused words, and the reason the sanitizer must give for them (from this file's own scrub).
WORDS = ['feedback_given', 'scrubbed', 'written_locally', 'feedback_sent']
SCRUB, WRITE, PUSH, CAPTURED, SENT = 'scrub@1', 'write-local@1', 'push@1', 'written_locally', 'feedback_sent'
CODE = 'scrub-text@1'   # the scrub done by code (pack 122): a method of its own, so an id of its own
KIND, KIND_FILE = 'scrub_text', 'kinds/scrub_text.py'
BAD = '/Users/someone ' + '0123456789abcdef' * 3
GOOD = 'The feedback command prints nothing when the folder is read-only. Seen in /Users/%s/work/app; reply to %s@example.org.'
REFUSAL = 'Handler refused: sanitizer error: nothing useful is left after redaction (%d letters and digits, 10 needed)' % _scrub(BAD)[2]   # the handler's own refusal, in its words
MARKER = {'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': False, 'source': 'hand-written', 'version': 'none'}
NO_SCRUB = [stuck(CAPTURED, 'METHOD_ABSENT', ['METHOD_ABSENT'], METHOD_ABSENT=['scrubbed']), stuck(SENT, 'METHOD_ABSENT', ['METHOD_ABSENT'], METHOD_ABSENT=['scrubbed'])]
REFUSED = [halted(CAPTURED, [CODE, WRITE], REFUSAL), halted(SENT, [CODE, WRITE, PUSH], REFUSAL)]
THROUGH = [done(CAPTURED, [SCRUB, WRITE]), done(SENT, [PUSH])]   # the capture, then the send: scrub, write, push (case 54: the scrub simulated)
BY_CODE = [done(CAPTURED, [CODE, WRITE]), done(SENT, [PUSH])]    # the same with the scrub done by code
NO_RAIL = stuck(SENT, 'PROVIDER_REQUIRED', ['PROVIDER_REQUIRED'])


def words(version, text):
    return {'predicate': 'feedback_given', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/user-typed', 'version': version, 'text': text}


# R82. The hook chain proposal measured again with one thing changed: the part whose row is handed in, and the change.
PARTS = [c + '_' + p for c in ('hook_chain', 'boot_load') for p in ('baseline_cited', 'samples_ge_100', 'guardrails_hold', 'cut_approved', 'cut_shipped')]
DESK = ['124_cut_desk']
EDITS = {'no_baseline': ('baseline_cited', lambda p: p.update(baseline={'samples': p['baseline']['samples']})),
         'small_sample': ('samples_ge_100', lambda p: p['baseline'].update(samples=42)),
         'guardrail_broken': ('guardrails_hold', lambda p: p['guardrails']['override_count_total'].update(now=17)),
         'never_cut_touched': ('guardrails_hold', lambda p: p['touches'].append('proto-000-text')),
         'more_samples': ('samples_ge_100', lambda p: p['baseline'].update(samples=213)),
         'guardrail_back': ('guardrails_hold', lambda p: p['guardrails']['override_count_total'].update(now=13))}
HOOK, BOOT = 'hook_chain_cut_landed', 'boot_load_cut_landed'
ASK_HOOK, SHIP_HOOK, ASK_BOOT, SHIP_BOOT = 'ask-hook-chain-cut-approval@1', 'ship-hook-chain-cut@1', 'ask-boot-load-cut-approval@1', 'ship-boot-load-cut@1'
VIA_HOOK, VIA_BOOT = 'R-HOOK-CHAIN-LANDED@1/OR1', 'R-BOOT-LOAD-LANDED@1/OR1'
BOTH_ASK = [asks(HOOK, ASK_HOOK, [SHIP_HOOK], VIA_HOOK), asks(BOOT, ASK_BOOT, [SHIP_BOOT], VIA_BOOT)]
missing = lambda part: [stuck(HOOK, 'METHOD_ABSENT', ['METHOD_ABSENT'], METHOD_ABSENT=['hook_chain_' + part])]

# R80. One rule set under each tier pack.
FACTS = ['tier_internal', 'tier_portfolio', 'tier_project', 'tier_external', 'notice_shown', 'opted_in', 'batch_confirmed', 'signals_sent']
RULES, FAN_IN = '125_fan_in_rules', 'fan_in_done'
TIER = {'internal': '126_tier_internal', 'portfolio': '127_tier_portfolio', 'project': '128_tier_project', 'external': '129_tier_external'}
others = lambda own: sorted('tier_' + t for t in TIER if t != own)
via = lambda n: 'R-FAN-IN@1/OR%d' % n
ASK_CLIENT, SEND_PROJECT, SEND_INTERNAL, DENIED = 'ask-batch-confirm@1', 'send-project@1', 'send-internal@1', ['AUTHORITY_REQUIRED']
OPT_IN = ('event', {'predicate': 'opted_in', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/consent-ledger', 'version': 'consent-1'})
YES = ('answer', 'opted_in', 0, 'TRUE', 'client')
foreign = lambda **more: dict({'predicate': 'tier_internal', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/not-the-registry', 'version': 'handed-in-1'}, **more)
no_opt_in = lambda own: [stuck(FAN_IN, 'QUERY_EVIDENCE', ['METHOD_ABSENT', 'QUERY_EVIDENCE'], METHOD_ABSENT=others(own), QUERY_EVIDENCE=['opted_in'])]
closed = lambda own: {'METHOD_ABSENT': others(own)}   # the other tiers' alternatives are shut by their tier rows
PROJECT_ASKS = [dict(asks(FAN_IN, ASK_CLIENT, [SEND_PROJECT], via(3)), named=closed('project'), gate=[[[ASK_CLIENT, SEND_PROJECT], True, []], [[ASK_CLIENT], True, []]])]
PROJECT_SENDS = [dict(done(FAN_IN, [SEND_PROJECT], via(3)), named=closed('project'), gate=[[[SEND_PROJECT], True, []], [[SEND_PROJECT], True, []]])]
PROJECT = [('look', LOOK, no_opt_in('project')), ('opted_in', OPT_IN, PROJECT_ASKS), ('confirmed', YES, PROJECT_SENDS)]   # the internal send is never a candidate
SHUT = {'METHOD_ABSENT': ['tier_external', 'tier_portfolio']}   # with a foreign internal row only two alternatives are shut by a tier row; the internal one is shut by authority
# The fan-in and consent columns of the Privacy charter's tier table, as this file reads them: the rule's alternatives, and each step's effect, prerequisites, grant, kind and asked party.
FAN_IN_RULE = [['tier_internal', 'signals_sent'], ['tier_portfolio', 'notice_shown', 'signals_sent'], ['tier_project', 'opted_in', 'batch_confirmed', 'signals_sent'], ['tier_external', 'opted_in', 'signals_sent']]
FAN_IN_STEPS = {'send-internal@1': ['signals_sent', ['tier_internal'], 'fan-in:internal', 'simulate_fact', None],
                'send-portfolio@1': ['signals_sent', ['tier_portfolio', 'notice_shown'], 'fan-in:portfolio', 'simulate_fact', None],
                'send-project@1': ['signals_sent', ['tier_project', 'opted_in', 'batch_confirmed'], 'fan-in:project', 'simulate_fact', None],
                'send-external@1': ['signals_sent', ['tier_external', 'opted_in'], 'fan-in:external', 'simulate_fact', None],
                'show-notice@1': ['notice_shown', ['tier_portfolio'], 'notice:portfolio', 'simulate_fact', None],
                'ask-batch-confirm@1': ['batch_confirmed', ['tier_project', 'opted_in'], 'ask:client', 'ask', 'client']}
PORTFOLIO = [dict(done(FAN_IN, ['show-notice@1', 'send-portfolio@1'], via(2)), named=closed('portfolio'))]

CASES = {'54_ordered_effects': (['120_feedback', '121_scrub_simulated', '123_team_rail'], THROUGH),
         '55_data_before_cuts': (DESK, BOTH_ASK),
         '56_tier_rules': ([RULES, TIER['portfolio']], PORTFOLIO)}
LIVES = {
    'effects.no_scrub_step': (['120_feedback', '123_team_rail'], WORDS, [('look', LOOK, NO_SCRUB)]),
    'effects.fail_closed': (['120_feedback', '122_scrub_by_code', '123_team_rail'], WORDS, [
        ('refused', ('event', words('words-2', BAD)), REFUSED), ('unverified_marker', ('event', MARKER), 'UNVERIFIED_EVENT_IGNORED'), ('again', LOOK, REFUSED),
        ('sent', ('event', words('words-3', GOOD % ('someone', 'someone'))), BY_CODE), ('repeat', LOOK, [held(CAPTURED), held(SENT)]),
        ('second', ('event', words('words-4', GOOD % ('another', 'another'))), BY_CODE)]),
    'effects.rail_down': (['120_feedback', '122_scrub_by_code'], WORDS, [
        ('captured', LOOK, [done(CAPTURED, [CODE, WRITE]), NO_RAIL]), ('again', LOOK, [held(CAPTURED), NO_RAIL]),
        ('rail_back', ('apply', '123_team_rail'), None), ('retry', LOOK, [held(CAPTURED), done(SENT, [PUSH])])]),
    'cuts.missing.no_baseline': (DESK, PARTS, [('measured', ('measured', 'no_baseline'), missing('baseline_cited'))]),
    'cuts.missing.small_sample': (DESK, PARTS, [('measured', ('measured', 'small_sample'), missing('samples_ge_100'))]),
    'cuts.missing.guardrail_broken': (DESK, PARTS, [('measured', ('measured', 'guardrail_broken'), missing('guardrails_hold'))]),
    'cuts.missing.never_cut_touched': (DESK, PARTS, [('measured', ('measured', 'never_cut_touched'), missing('guardrails_hold'))]),
    'cuts.own_question': (DESK, PARTS, [
        ('first', LOOK, BOTH_ASK), ('yes_hook_chain', ('answer', 'first', 0, 'TRUE', 'founder'), [done(HOOK, [SHIP_HOOK], VIA_HOOK)]),
        ('no_boot_load', ('answer', 'first', 1, 'FALSE', 'founder'), [stuck(BOOT, 'REFUSED', ['REFUSED'], REFUSED=['boot_load_cut_approved'])]),
        ('measured_again', ('measured', 'more_samples'), [held(HOOK, VIA_HOOK)]), ('guardrail_broke', ('measured', 'guardrail_broken'), missing('guardrails_hold')),
        ('guardrail_back', ('measured', 'guardrail_back'), [held(HOOK, VIA_HOOK)])]),
    'cuts.yes_without_data': (DESK, PARTS, [
        ('asked', LOOK, BOTH_ASK), ('sample_shrank', ('measured', 'small_sample'), missing('samples_ge_100')),
        ('yes_hook_chain', ('answer', 'asked', 0, 'TRUE', 'founder'), missing('samples_ge_100'))]),
    'tiers.internal': ([RULES, TIER['internal']], FACTS, [('look', LOOK, [dict(done(FAN_IN, [SEND_INTERNAL], via(1)), named=closed('internal'))])]),
    'tiers.portfolio': ([RULES, TIER['portfolio']], FACTS, [('look', LOOK, PORTFOLIO)]),
    'tiers.project': ([RULES, TIER['project']], FACTS, PROJECT),
    'tiers.project_refused': ([RULES, TIER['project']], FACTS, [
        ('opted_in', OPT_IN, PROJECT_ASKS),
        ('refused', ('answer', 'opted_in', 0, 'FALSE', 'client'), [stuck(FAN_IN, 'REFUSED', ['METHOD_ABSENT', 'REFUSED'], METHOD_ABSENT=others('project'), REFUSED=['batch_confirmed'])])]),
    'tiers.external': ([RULES, TIER['external']], FACTS, [
        ('look', LOOK, no_opt_in('external')), ('opted_in', OPT_IN, [dict(done(FAN_IN, ['send-external@1'], via(4)), named=closed('external'))])]),
    'tiers.old_grant': ([RULES, TIER['internal'], TIER['project']], FACTS, PROJECT),   # the same script as the plain project State, line for line
    'tiers.foreign_row': ([RULES, TIER['project']], FACTS, [
        ('unverified_row', ('event', foreign(verified=False)), 'UNVERIFIED_EVENT_IGNORED'),
        ('row_from_another_scope', ('event', foreign(scope='internal/fan-in')), 'OUT_OF_SCOPE'),
        ('row_in_scope', ('event', foreign()), [dict(stuck(FAN_IN, 'QUERY_EVIDENCE', ['AUTHORITY_REQUIRED', 'METHOD_ABSENT', 'QUERY_EVIDENCE'], QUERY_EVIDENCE=['opted_in'], **SHUT),
                                                     gate=[[[SEND_INTERNAL], False, DENIED]])]),
        ('opted_in', OPT_IN, [dict(asks(FAN_IN, ASK_CLIENT, [SEND_PROJECT], via(1)), named=SHUT,
                                   gate=[[[SEND_INTERNAL], False, DENIED], [[ASK_CLIENT, SEND_PROJECT], True, []], [[ASK_CLIENT, SEND_INTERNAL], False, DENIED],
                                         [[ASK_CLIENT, SEND_PROJECT], True, []], [[ASK_CLIENT], True, []]])]),
        ('confirmed', YES, [dict(done(FAN_IN, [SEND_PROJECT], via(1)), named=SHUT,
                                 gate=[[[SEND_INTERNAL], False, DENIED], [[SEND_PROJECT], True, []], [[SEND_INTERNAL], False, DENIED], [[SEND_PROJECT], True, []], [[SEND_PROJECT], True, []]])])]),
}


# ---------------------------------------------------------------------------------------------- what the pack files must be
def _method(p, mid):
    return [m for m in p.get('methods', []) if m['id'] == mid][0]


def _shape_effects(f):
    """R73 in the pack files: the order is in the prerequisites, the capture is a goal of its own, each scrub is one step in a pack of its own, the rail is a pack.
    The two scrubs are two methods, so each has an id of its own (a method id names one method in the whole lab). The ids are held to the letter: at the same
    cost the kernel's rule for equal plans goes by the order of the step names, and `scrub-text@1` stands before `scrub@1` there."""
    a, sim, code, rail = (f[n] for n in PACKS[:4])
    out = []
    if [m['id'] for p in (a, sim) for m in p['methods']] != [PUSH, WRITE, SCRUB] or [m['id'] for m in code['methods']] != [CODE] or not CODE < SCRUB:
        out.append('the three steps are authored send, write, and each scrub in a pack of its own: the simulated one as scrub@1, the one by code as scrub-text@1')
    if not same([_method(a, PUSH)['requires'], _method(a, WRITE)['requires'], sim['methods'][0]['requires'], code['methods'][0]['requires']],
                [['written_locally', 'scrubbed', 'feedback_given'], ['scrubbed', 'feedback_given'], ['feedback_given'], ['feedback_given']]):
        out.append('the write requires the scrub and the words, the send the write, the scrub and the words')
    if [(m['effect'], m['provider'], m['action']) for m in (_method(a, PUSH), _method(a, WRITE), sim['methods'][0])] != [
            ('feedback_sent', 'team-rail', 'simulate_fact'), ('written_locally', 'local-disk', 'simulate_fact'), ('scrubbed', 'sanitizer', 'simulate_fact')] \
            or (code['methods'][0]['effect'], code['methods'][0]['provider'], code['methods'][0]['action'], code['methods'][0].get('scrubs')) != ('scrubbed', 'sanitizer', 'scrub_text', 'feedback_given'):
        out.append('each step makes its own row on its own provider; pack 122 hands the scrub to code')
    if a.get('goals') != [CAPTURED, SENT] or 'team-rail' in a.get('providers', {}) or not same(rail, {'schema': 'sutra-extension/2', 'id': '123_team_rail', 'providers': {'team-rail': 2}}):
        out.append('the capture is a standing goal ahead of the send, and the rail is a pack of its own')
    marks = {e['predicate']: e for e in a['evidence']}
    if [(marks[p]['truth'], marks[p]['source']) for p in WORDS[1:]] != [('FALSE', 'fixture/marker-absent')] * 3 or marks['feedback_given']['truth'] != 'TRUE' or len(a['evidence']) != 4 \
            or set(a) != {'schema', 'id', 'scope', 'goals', 'evidence', 'methods', 'providers', 'grants'} or set(sim) != {'schema', 'id', 'methods', 'grants'} or set(code) != set(sim):
        out.append('the three markers start as absent and nothing else is authored')
    steps = a['methods'] + sim['methods'] + code['methods']
    if a.get('scope') != 'sutra/feedback' or not same(a['providers'], {'local-disk': 2, 'sanitizer': 2}) or not same([a['grants'], sim['grants'], code['grants']], [['action:' + PUSH, 'action:' + WRITE], ['action:' + SCRUB], ['action:' + CODE]]) \
            or any(m.get('grant') != 'action:' + m['id'] or not same(m.get('cost'), {'compute': 1, 'money': 0, 'attention': 0}) or m.get('approved') is not True for m in steps):
        out.append('each step has its own grant, costs one unit of compute and is approved; the feedback pack gives the disk and the sanitizer two slots each')
    return out


def _shape_cuts(f):
    """R82 in pack 124: the three locks of each cut (the rule, the ask's prerequisites, the ship's) and the adapter's rows, made again here."""
    p = f['124_cut_desk']
    out = []
    rules = {r['head']: r for r in p['rules']}
    stored = {e['predicate']: e for e in p['evidence'] if e.get('source') == CUT_SOURCE}
    want = {}
    for proposal in p['proposals']:
        want.update(_cut_rows(proposal))
    if len(p['proposals']) != 2 or len(want) != 6 or not same(stored, want) or any(r['truth'] != 'TRUE' for r in want.values()):
        out.append('the six adapter rows are what their proposals give, all TRUE')
    if not same([e for e in p['evidence'] if e.get('source') != CUT_SOURCE],
                [{'predicate': c + '_cut_shipped', 'truth': 'FALSE', 'verified': True, 'source': 'fixture/not-shipped', 'version': '1'} for c in ('hook_chain', 'boot_load')]):
        out.append('beside the adapter rows the pack says only that nothing is shipped')
    for c in ('hook_chain', 'boot_load'):
        slug = c.replace('_', '-')
        parts = [c + '_baseline_cited', c + '_samples_ge_100', c + '_guardrails_hold']
        ship, ask = _method(p, 'ship-' + slug + '-cut@1'), _method(p, 'ask-' + slug + '-cut-approval@1')
        if not same(rules.get(c + '_cut_admissible', {}).get('branches'), [parts]) or not same(rules.get(c + '_cut_landed', {}).get('branches'), [[c + '_cut_admissible', c + '_cut_approved', c + '_cut_shipped']]) \
                or any(rules[h].get('approved') is not True for h in (c + '_cut_admissible', c + '_cut_landed')):
            out.append(c + ': admissible is the three parts; landed is admissible, approved and shipped')
        if (ship['effect'], ship['action']) != (c + '_cut_shipped', 'simulate_fact') or not same(ship['requires'], parts + [c + '_cut_approved']):
            out.append(c + ': the ship requires the three parts and the approval')
        if (ask['effect'], ask['action'], ask.get('ask_to')) != (c + '_cut_approved', 'ask', 'founder') or not same(ask['requires'], parts) or not same(ask['cost'], {'compute': 0, 'money': 0, 'attention': 1}):
            out.append(c + ': the ask requires the three parts, goes to the founder and costs attention')
    if len(p['rules']) != 4 or len(p['methods']) != 4 or p.get('goals') != [HOOK, BOOT]:
        out.append('two cuts: four rules, four steps, two goals')
    if set(p) != {'schema', 'id', 'scope', 'goals', 'rules', 'methods', 'providers', 'grants', 'evidence', 'proposals'} or p.get('scope') != 'sutra/speed' \
            or not same(p['providers'], {'local-provider': 4, 'founder-channel': 3}) or sorted(p['grants']) != sorted('action:' + m['id'] for m in p['methods']) \
            or any(m.get('grant') != 'action:' + m['id'] or m.get('approved') is not True or m.get('provider') != ('founder-channel' if m.get('action') == 'ask' else 'local-provider')
                   or (m.get('action') != 'ask' and not same(m.get('cost'), {'compute': 1, 'money': 0, 'attention': 0})) for m in p['methods']):
        out.append('the desk holds its scope, its slots and one grant per step, and nothing else')
    return out


def _shape_tiers(f):
    """R80 in packs 125 to 129, from a closed list: what a rule set may hold, what a tier pack may hold, and who holds each step's grant."""
    rules, packs = f[RULES], [f[n] for n in TIER.values()]
    out = []
    if set(rules) - {'schema', 'id', 'goals', 'rules', 'methods'}:
        out.append('the rule set holds more than goals, rules and methods')
    if len(rules.get('rules', [])) != 1 or rules['rules'][0].get('head') != FAN_IN or rules['rules'][0].get('approved') is not True or rules.get('goals') != [FAN_IN]:
        return out + ['the rule set holds one approved rule, the goal\'s']
    tiers = [branch[0] for branch in rules['rules'][0]['branches']]
    if tiers != ['tier_' + t for t in TIER]:
        out.append('one alternative per tier, each opening with its tier row')
    owner = {}
    for p in packs:
        rows = {e['predicate']: e for e in p.get('evidence', [])}
        if set(p) - {'schema', 'id', 'scope', 'evidence', 'grants', 'providers'}:
            out.append(p['id'] + ' holds more than a scope, rows, grants and slots')
        if any('scope' in e for e in rows.values()) or len(rows) != len(p.get('evidence', [])):
            out.append(p['id'] + ' gives a row a scope of its own, or a row twice')
        if set(tiers) - set(rows) or any(e.get('verified') is not True for e in rows.values()) or sorted(e['truth'] for e in rows.values()) != ['FALSE'] * (len(rows) - 1) + ['TRUE']:
            out.append(p['id'] + ' does not hold every tier row and, beside them, only rows that say FALSE: all verified, one TRUE')
            continue
        own = [t for t in tiers if rows[t]['truth'] == 'TRUE']
        if len(own) != 1 or own[0] in owner:
            out.append(p['id'] + ' is not the one pack of one tier')
            continue
        owner[own[0]] = p['id']
    if set(owner) != set(tiers) or len({p.get('scope') for p in packs}) != len(packs) or any(type(p.get('scope')) is not str for p in packs):
        out.append('every tier has its pack and every pack a scope of its own')
    if not same(rules['rules'][0]['branches'], FAN_IN_RULE) or not same({m['id']: [m.get('effect'), m.get('requires'), m.get('grant'), m.get('action'), m.get('ask_to')] for m in rules['methods']}, FAN_IN_STEPS):
        out.append('the rule and its six steps are not the fan-in and consent columns of the tier table')
    needs = {t: set() for t in tiers}
    for m in rules.get('methods', []):
        own = [q for q in m.get('requires', []) if q in tiers]
        if len(own) != 1 or m.get('effect') in tiers or type(m.get('grant')) is not str:
            out.append(m.get('id', '?') + ' does not require exactly one tier row, or makes one')
            continue
        needs[own[0]].add(m['grant'])
        if [p['id'] for p in packs if m['grant'] in p.get('grants', [])] != [owner.get(own[0])]:
            out.append(m['id'] + ': its grant is not held by its tier\'s pack alone')
    if any(set(f[owner[t]].get('grants', [])) != needs[t] for t in owner):
        out.append('a tier pack holds a grant no step of its tier needs')
    return out


def _scene(mine, handler):
    """The shape of the whole sequence, the scrub's handler, and the looks the record holds twice. The handler: `scrub_text` is a declared kind, so the record's
    list of handlers names it, with the kind file as its file and that file's sha256 (`handler`: read from kinds/scrub_text.py by this module)."""
    o = mine['scenes']['ordered']
    out = []
    have = sorted(['effects.' + n for n in o['effects']] + ['cuts.missing.' + n for n in o['cuts']['missing']]
                  + ['cuts.' + n for n in o['cuts'] if n != 'missing'] + ['tiers.' + n for n in o['tiers']])
    if set(o) != {'effects', 'cuts', 'tiers'} or have != sorted(LIVES):
        out.append('lives')
    if not same(mine['action_handlers'].get(KIND), {'module': 'kinds.' + KIND, 'file': KIND_FILE, 'sha256': handler}):
        out.append('handler')
    case = lambda cid: [c for c in mine['cases'] if c['id'] == cid][0]
    bare = lambda run: [{k: v for k, v in r.items() if k not in ('learning', 'learning_record')} for r in run['runs']]
    if not same(bare(case('55_data_before_cuts')['run']), o['cuts']['own_question']['steps']['first']['result']['runs']) \
            or not same(bare(case('56_tier_rules')['run']), o['tiers']['portfolio']['steps']['look']['result']['runs']):
        out.append('the looks recorded twice')
    return out


def _judge(mine, files, case_files, handler, chain, only=None):
    """Everything this file claims, target by target: target -> what is wrong with it (an empty list: it holds)."""
    out = {}

    def guard(name, fn):
        if only is None or name in only:
            try:
                out[name] = fn()
            except Exception as e:
                out[name] = ['cannot be read: ' + type(e).__name__]
    for name, fn in (('shape:effects', _shape_effects), ('shape:cuts', _shape_cuts), ('shape:tiers', _shape_tiers)):
        guard(name, lambda fn=fn: fn(files))
    for cid, spec in CASES.items():
        guard('case:' + cid, lambda cid=cid, spec=spec: _case([c for c in mine['cases'] if c['id'] == cid][0], files, case_files[cid], spec, chain))
    for key, spec in LIVES.items():
        guard('life:' + key, lambda key=key, spec=spec: _life(_at(mine['scenes']['ordered'], key), files, spec, chain))
    guard('scene', lambda: _scene(mine, handler))
    return out


def _at(o, key):
    for k in key.split('.'):
        o = o[k]
    return o


CLAIMS = {   # check id -> the claims of the passage it carries, and the targets they rest on
    'S70_the_order_comes_from_the_prerequisites': ('C1', ['shape:effects', 'case:54_ordered_effects']),
    'S71_no_scrub_or_a_refused_scrub_writes_and_sends_nothing': ('C2 C3', ['shape:effects', 'life:effects.no_scrub_step', 'life:effects.fail_closed']),
    'S72_safe_words_are_captured_then_sent_and_the_capture_does_not_wait_for_the_rail': ('C4 C5', ['shape:effects', 'life:effects.fail_closed', 'life:effects.rail_down', 'scene']),
    'S73_cut_rows_follow_from_what_was_measured': ('C6', ['shape:cuts', 'case:55_data_before_cuts'] + ['life:cuts.missing.' + n for n in ('no_baseline', 'small_sample', 'guardrail_broken', 'never_cut_touched')]),
    'S74_each_cut_asks_its_own_question_and_ships_only_on_its_yes': ('C7 C8', ['shape:cuts', 'case:55_data_before_cuts', 'life:cuts.own_question', 'scene']),
    'S75_a_false_part_stops_a_cut_and_a_part_measured_again_leaves_a_landed_cut_alone': ('C9 C10', ['shape:cuts', 'life:cuts.own_question', 'life:cuts.yes_without_data']
                                                                                         + ['life:cuts.missing.' + n for n in ('no_baseline', 'small_sample', 'guardrail_broken', 'never_cut_touched')]),
    'S76_one_rule_set_gives_each_tier_its_own_way': ('C11', ['shape:tiers', 'case:56_tier_rules', 'scene'] + ['life:tiers.' + n for n in ('internal', 'portfolio', 'project', 'project_refused', 'external')]),
    'S77_tier_packs_hold_only_their_own_rows_and_grants': ('C12', ['shape:tiers']),
    'S78_one_lock_alone_opens_nothing': ('C13', ['shape:tiers', 'life:tiers.project', 'life:tiers.old_grant', 'life:tiers.foreign_row']),
}


# ---------------------------------------------------------------------------------------------- forgeries
def _leaves(o, traces=False):
    """Every leaf of a recorded target as (holder, key), in the record's own order. Trace rows are left out unless asked for (they need the chain function)."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == 'trace' and not traces:
                continue
            if isinstance(v, (dict, list)) and v:
                yield from _leaves(v, traces)
            else:
                yield o, k
    else:
        for i, v in enumerate(o):
            if isinstance(v, (dict, list)) and v:
                yield from _leaves(v, traces)
            else:
                yield o, i


def _forged(v):
    """Another value for a leaf, and where it is a number or a flag, the same value written as another JSON type."""
    if type(v) is bool:
        return [not v, int(v)]
    if type(v) is int:
        return [v + 1, float(v)]
    if type(v) is str:
        return [v + '~']
    return ['~']   # null, an empty list, an empty object


def _objects(o, traces=False):
    """Every object (JSON dict) of a recorded target, the target first; the same parts are left out as in `_leaves`."""
    if isinstance(o, dict):
        yield o
    for k, v in (o.items() if isinstance(o, dict) else enumerate(o)):
        if isinstance(v, (dict, list)) and (k != 'trace' or traces):
            yield from _objects(v, traces)


def sweep(mine, files, case_files, handler, chain=None, stride=1, traces=False, keys=False):
    """Change leaves of cases 54 to 56 and of every life in place, one at a time, and judge the target each belongs to.
    -> (how many forgeries were made, the ones that passed). With `traces` (and a chain function) the leaves of trace rows are changed too.
    With `keys` every leaf is also taken out of its object, and every object is given one more key."""
    made, passed = 0, []
    targets = [('case:' + cid, [c for c in mine['cases'] if c['id'] == cid][0]) for cid in CASES] + [('life:' + key, _at(mine['scenes']['ordered'], key)) for key in LIVES]
    judged = lambda name: bool(_judge(mine, files, case_files, handler, chain, only={name})[name])
    count = 0
    for name, target in targets:
        for holder, key in list(_leaves(target, traces)):
            count += 1
            if count % stride:
                continue
            kept = holder[key]
            for value in _forged(kept):
                holder[key] = value
                made += 1
                try:
                    if not judged(name):
                        passed.append((name, 'changed', str(key), J(kept)[:60], J(value)[:60]))
                finally:
                    holder[key] = kept
            if keys and isinstance(holder, dict):
                order = list(holder.items())
                del holder[key]
                made += 1
                try:
                    if not judged(name):
                        passed.append((name, 'taken out', str(key), J(kept)[:60]))
                finally:
                    holder.clear()
                    holder.update(order)
        if keys:
            for holder in list(_objects(target, traces)):
                holder['~'] = 0
                made += 1
                try:
                    if not judged(name):
                        passed.append((name, 'one more key', sorted(holder)[:4]))
                finally:
                    del holder['~']
    return made, passed


def _rechain(life):
    """Chain every trace of a life again, as a forger would after rewriting a row, and name each run by its new root."""
    for rec in life['steps'].values():
        for r in (rec['result'] or {}).get('runs', []):
            prev = 'GENESIS'
            for i, row in enumerate(r['trace']):
                row.update(seq=i + 1, prev_sha256=prev)
                row['sha256'] = digest({k: v for k, v in row.items() if k != 'sha256'})
                prev = row['sha256']
            r['trace_root_sha256'] = prev


def _handmade():
    """One change each: ('life' | 'case', its name, the change to that record), ('packs', None, the change to the pack files), or
    ('rechained', a life, a change to a row of one of its traces): there the traces are chained again, so only what a row says can give it away."""
    step = lambda name: (lambda L: L['steps'][name])
    run = lambda name, i=0: (lambda L: L['steps'][name]['result']['runs'][i])
    event = lambda name: (lambda L: L['steps'][name]['result']['event'])
    after = lambda name: (lambda L: L['steps'][name]['after'])
    life = lambda key, at, change: ('life', key, lambda L: change(at(L)))
    case = lambda cid, change: ('case', cid, change)
    packs = lambda change: ('packs', None, change)
    line = lambda r, op: [e for e in r['trace'] if e['operation'] == op][0]['data']
    method = _method
    fc, rd, own, late, pj = 'effects.fail_closed', 'effects.rail_down', 'cuts.own_question', 'cuts.yes_without_data', 'tiers.project'
    return [
        # ---- R73
        case('54_ordered_effects', lambda c: c['outcome'].update(actions=[WRITE, SCRUB])),
        case('54_ordered_effects', lambda c: c['run']['runs'][0]['model_receipts'].reverse()),
        case('54_ordered_effects', lambda c: c['run']['runs'][1].update(actions=[], status='SUPPORTED_BY_EVIDENCE')),
        case('54_ordered_effects', lambda c: c['run']['runs'][1].update(learning=[{'kind': 'REUSE_COMPOSITION', 'status': 'PROMOTED'}])),
        case('54_ordered_effects', lambda c: c['run']['runs'][1]['learning_record'].update(source_trace='0' * 64)),
        case('54_ordered_effects', lambda c: c['derived_state']['facts']['sutra/feedback|written_locally']['depends_on'][0].update(version='another')),
        case('54_ordered_effects', lambda c: c['derived_state']['facts']['sutra/feedback|feedback_sent']['depends_on'].pop()),
        case('54_ordered_effects', lambda c: c['derived_state']['facts']['sutra/feedback|feedback_sent'].update(truth='FALSE')),
        case('54_ordered_effects', lambda c: c['derived_state']['facts']['sutra/feedback|scrubbed'].update(verified=False)),
        case('54_ordered_effects', lambda c: c['derived_state']['budget_after'].update(compute=10)),
        case('54_ordered_effects', lambda c: c['derived_state']['budget_after'].update(compute=7.0)),
        case('54_ordered_effects', lambda c: c['derived_state']['historical_events'].pop()),
        case('54_ordered_effects', lambda c: c['four_views']['world'][3].update(truth='FALSE')),
        case('54_ordered_effects', lambda c: c.update(packs=['120_feedback', '121_scrub_simulated'])),
        packs(lambda p: p['120_feedback']['methods'].reverse()),
        packs(lambda p: method(p['120_feedback'], WRITE).update(requires=['feedback_given'])),
        packs(lambda p: method(p['120_feedback'], WRITE).update(requires=['scrubbed'])),
        packs(lambda p: method(p['120_feedback'], PUSH).update(requires=['written_locally', 'scrubbed'])),
        packs(lambda p: method(p['120_feedback'], PUSH).update(requires=['written_locally', 'scrubbed', 'feedback_given', 'never_made'])),
        packs(lambda p: p['120_feedback'].update(goals=[SENT])),
        packs(lambda p: p['120_feedback']['providers'].update({'team-rail': 2})),
        packs(lambda p: p['122_scrub_by_code']['methods'][0].update(id=SCRUB)),            # the scrub by code under the simulated scrub's name: one id, two methods
        packs(lambda p: p['121_scrub_simulated']['methods'][0].update(id='a-scrub@1')),    # the simulated scrub named ahead of the one by code: in a State that holds both it would be the one taken
        packs(lambda p: p['121_scrub_simulated']['methods'][0].update(cost={'compute': 0, 'money': 0, 'attention': 0})),   # or priced below it
        packs(lambda p: p['122_scrub_by_code']['methods'][0].update(action='simulate_fact')),
        packs(lambda p: p['122_scrub_by_code']['methods'][0].pop('scrubs')),
        packs(lambda p: p['122_scrub_by_code'].update(grants=['action:' + SCRUB])),
        packs(lambda p: p['121_scrub_simulated']['methods'].append(dict(method(p['120_feedback'], WRITE), id='write-raw@1', requires=['feedback_given']))),
        life('effects.no_scrub_step', run('look'), lambda r: r.update(status='PLAN_READY')),
        life('effects.no_scrub_step', run('look', 1), lambda r: r['trace'][-2]['data'].update(reason='QUERY_EVIDENCE')),
        life('effects.no_scrub_step', after('look'), lambda a: a['reads'].update(written_locally='TRUE')),
        life('effects.no_scrub_step', after('look'), lambda a: a['providers'].update({'team-rail': 1})),
        life('effects.no_scrub_step', after('look'), lambda a: a['rows']['feedback_sent'].update(truth='TRUE', source='LOCAL_MODEL:push@1')),
        life(fc, run('refused'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', work_state='completed')),
        life(fc, run('refused'), lambda r: r.update(model_receipts=[{'method': WRITE}], actions=[WRITE])),
        life(fc, run('refused'), lambda r: r.update(pending=[CODE])),
        life(fc, run('refused'), lambda r: r.update(pending=[SCRUB, WRITE])),                                      # stopped at the simulated scrub, which this State does not hold
        life(fc, run('refused'), lambda r: r['stopped'].update(method=SCRUB)),
        life(fc, run('refused'), lambda r: r['stopped'].update(reason='Handler failed: RuntimeError')),             # a fault of the handler, not its refusal
        life(fc, run('refused'), lambda r: r['stopped'].update(reason=REFUSAL[len('Handler refused: '):])),         # the sanitizer's words without the kernel's
        life(fc, run('again', 1), lambda r: r['stopped'].update(reason='Handler refused: A decision stands on this effect')),
        life(fc, run('refused', 1), lambda r: r['stopped'].update(reason='Handler failed: KeyError')),
        life(fc, run('refused'), lambda r: r['stopped'].update(method=PUSH)),
        life(fc, run('refused'), lambda r: r.update(cost={'compute': 1, 'money': 0, 'attention': 0})),
        life(fc, step('refused'), lambda s: s['does']['event'].update(text='Words that the sanitizer would have let through.')),
        life(fc, event('refused'), lambda e: e.update(text='Words that the sanitizer would have let through.')),
        life(fc, after('refused'), lambda a: a['reads'].update(written_locally='TRUE')),
        life(fc, after('refused'), lambda a: a['rows']['scrubbed'].update(truth='TRUE')),
        life(fc, after('refused'), lambda a: a['budget'].update(compute=9)),
        life(fc, after('refused'), lambda a: a['providers'].update({'sanitizer': 1})),
        life(fc, after('again'), lambda a: a['rows']['feedback_sent'].update(source='LOCAL_MODEL:push@1')),
        life(fc, after('again'), lambda a: a.update(journal=['STEP_STOPPED', 'STEP_STOPPED'])),
        life(fc, run('again'), lambda r: r.update(status='WAITING')),
        life(fc, step('unverified_marker'), lambda s: s['result'].update(status='RECONCILED', affected=[SENT])),
        life(fc, step('unverified_marker'), lambda s: s['does']['event'].update(verified=True)),
        life(fc, after('unverified_marker'), lambda a: a['reads'].update(scrubbed='TRUE')),
        life(fc, after('sent'), lambda a: a['rows']['scrubbed'].update(clean_text=GOOD % ('someone', 'someone'))),
        life(fc, after('sent'), lambda a: a['rows']['scrubbed'].update(version='local-sim-1')),
        life(fc, after('sent'), lambda a: a['rows']['written_locally']['depends_on'][0].update(version='scrub-000000000000')),
        life(fc, after('sent'), lambda a: a['rows']['feedback_sent']['depends_on'].reverse()),
        life(fc, after('sent'), lambda a: a['reads'].update(feedback_sent='FALSE')),
        life(fc, after('sent'), lambda a: a['reads'].update(feedback_sent='FALSE', written_locally='FALSE')),
        life(fc, after('sent'), lambda a: a['budget'].update(compute=10)),
        life(fc, run('sent'), lambda r: r.update(actions=[WRITE, CODE])),
        life(fc, run('sent'), lambda r: r.update(actions=[SCRUB, WRITE])),                                         # the simulated scrub's name on the step the code ran
        life(fc, run('sent'), lambda r: r['model_receipts'][0].update(method=SCRUB)),
        life(fc, run('sent'), lambda r: r['model_receipts'][0].update(redactions=0)),
        life(fc, run('sent'), lambda r: r['model_receipts'][0].update(redactions=2.0)),
        life(fc, run('sent'), lambda r: r['model_receipts'][0].update(action='simulate_fact')),
        life(fc, run('sent', 1), lambda r: r.update(actions=[], model_receipts=[], status='SUPPORTED_BY_EVIDENCE')),
        life(fc, event('sent'), lambda e: e.update(verified=False)),
        life(fc, step('sent'), lambda s: s['result'].update(affected=[CAPTURED])),
        life(fc, step('sent'), lambda s: s['result'].update(status='OUT_OF_SCOPE')),
        life(fc, run('repeat'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', actions=[PUSH])),
        life(fc, after('repeat'), lambda a: a['providers'].update({'team-rail': 0})),
        life(fc, after('repeat'), lambda a: a['reads'].update(feedback_sent='UNKNOWN')),
        life(fc, run('second'), lambda r: r.update(actions=[CODE], skipped=[WRITE])),
        life(fc, run('second', 1), lambda r: r.update(actions=[], model_receipts=[], status='SUPPORTED_BY_EVIDENCE')),
        life(fc, after('second'), lambda a: a['rows']['written_locally']['depends_on'][1].update(version='words-3')),
        life(fc, after('second'), lambda a: a['providers'].update({'local-disk': 1})),
        life(rd, run('captured'), lambda r: r.update(actions=[], model_receipts=[], status='PROVIDER_REQUIRED', work_state='blocked')),
        life(rd, run('captured', 1), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', work_state='completed', actions=[PUSH])),
        life(rd, after('captured'), lambda a: a['reads'].update(written_locally='FALSE')),
        life(rd, after('captured'), lambda a: a['reads'].update(feedback_sent='TRUE')),
        life(rd, after('captured'), lambda a: a['providers'].update({'team-rail': 1})),
        life(rd, after('again'), lambda a: a['budget'].update(compute=6)),
        life(rd, step('rail_back'), lambda s: s['does'].update(apply='121_scrub_simulated')),
        life(rd, after('rail_back'), lambda a: a['reads'].update(feedback_sent='TRUE')),
        life(rd, run('retry', 1), lambda r: r.update(actions=[WRITE, PUSH])),
        life(rd, run('retry'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', actions=[WRITE])),
        life(rd, after('retry'), lambda a: a['rows']['written_locally'].update(version='local-sim-2')),
        life(rd, after('retry'), lambda a: a['rows']['feedback_sent']['depends_on'][0].update(version='local-sim-2')),
        # ---- R82
        packs(lambda p: p['124_cut_desk']['evidence'][1].update(truth='FALSE')),
        packs(lambda p: p['124_cut_desk']['proposals'][0]['baseline'].update(samples=42)),
        packs(lambda p: p['124_cut_desk']['proposals'][1]['guardrails'].update(triage_correct_pct=89)),
        packs(lambda p: p['124_cut_desk']['proposals'][1].update(touches=['boot-context-files', 'policy-coverage-markers'])),
        packs(lambda p: p['124_cut_desk']['evidence'][0].update(version='cut-000000000000')),
        packs(lambda p: p['124_cut_desk']['evidence'][2]['measured'].update(override_count_now=13)),
        packs(lambda p: p['124_cut_desk']['rules'][1].update(branches=[['hook_chain_cut_approved', 'hook_chain_cut_shipped']])),
        packs(lambda p: p['124_cut_desk']['rules'][1]['branches'][0].reverse()),
        packs(lambda p: p['124_cut_desk']['rules'][0]['branches'][0].pop()),
        packs(lambda p: method(p['124_cut_desk'], ASK_HOOK).update(requires=[])),
        packs(lambda p: method(p['124_cut_desk'], SHIP_HOOK).update(requires=['hook_chain_cut_approved'])),
        packs(lambda p: method(p['124_cut_desk'], ASK_BOOT).update(ask_to='operations')),
        case('55_data_before_cuts', lambda c: c['outcome'].update(actions=[ASK_HOOK, SHIP_HOOK], pending=[])),
        case('55_data_before_cuts', lambda c: c['outcome']['model_receipts'][0]['ask'].update(to='operations')),
        case('55_data_before_cuts', lambda c: c['outcome'].update(status='LOCAL_MODEL_EFFECTS_RECORDED')),
        case('55_data_before_cuts', lambda c: c['outcome'].update(cost={'compute': 0, 'money': 0, 'attention': 2})),
        case('55_data_before_cuts', lambda c: c['derived_state']['budget_after'].update(attention=3)),
        case('55_data_before_cuts', lambda c: c['derived_state']['facts']['sutra/speed|boot_load_samples_ge_100']['measured'].update(samples=13)),
        case('55_data_before_cuts', lambda c: c['run']['runs'][1].update(learning=[{'kind': 'REUSE_COMPOSITION', 'status': 'PROMOTED'}])),
        case('55_data_before_cuts', lambda c: c['run']['runs'][1]['model_receipts'][0]['ask'].update(predicate='hook_chain_cut_approved')),
        life('cuts.missing.small_sample', step('measured'), lambda s: s['does']['event'].update(truth='TRUE')),
        life('cuts.missing.small_sample', step('measured'), lambda s: s['does']['event']['measured'].update(samples=420)),
        life('cuts.missing.small_sample', event('measured'), lambda e: e.update(truth='TRUE')),
        life('cuts.missing.small_sample', run('measured'), lambda r: r.update(status='WAITING', work_state='waiting')),
        life('cuts.missing.small_sample', after('measured'), lambda a: a['reads'].update(hook_chain_cut_shipped='TRUE')),
        life('cuts.missing.small_sample', after('measured'), lambda a: a['rows']['hook_chain_samples_ge_100'].update(truth='TRUE')),
        life('cuts.missing.no_baseline', step('measured'), lambda s: s['does']['proposal'].update(baseline={'source': 'holding/LATENCY-LOG.jsonl', 'metric': 'm', 'value': 1, 'samples': 212})),
        life('cuts.missing.no_baseline', after('measured'), lambda a: a.update(open_asks={'sutra/speed|hook_chain_cut_approved': {}})),
        life('cuts.missing.no_baseline', after('measured'), lambda a: a['budget'].update(attention=2)),
        life('cuts.missing.guardrail_broken', run('measured'), lambda r: [e for e in r['trace'] if e['operation'] == 'METHOD_ABSENT'][0]['data'].update(predicate='hook_chain_samples_ge_100')),
        life('cuts.missing.never_cut_touched', step('measured'), lambda s: s['does']['proposal']['touches'].pop()),
        life('cuts.missing.never_cut_touched', step('measured'), lambda s: s['does']['event']['measured'].update(touches_do_not_cut=[])),
        life('cuts.missing.never_cut_touched', run('measured'), lambda r: r.update(status='WAITING', work_state='waiting', actions=[ASK_HOOK])),
        life(own, run('first'), lambda r: r['model_receipts'][0]['ask'].update(to='operations')),
        life(own, run('first', 1), lambda r: r['model_receipts'][0]['ask'].update(predicate='hook_chain_cut_approved')),
        life(own, after('first'), lambda a: a['budget'].update(attention=2)),
        life(own, after('first'), lambda a: a['reads'].update(hook_chain_cut_shipped='TRUE')),
        life(own, after('first'), lambda a: a['open_asks'].pop('sutra/speed|boot_load_cut_approved')),
        life(own, event('yes_hook_chain'), lambda e: e.update(answers='0' * 64)),
        life(own, event('yes_hook_chain'), lambda e: e.update(source='STAMP:operations')),
        life(own, event('yes_hook_chain'), lambda e: e.update(predicate='boot_load_cut_approved')),
        life(own, event('yes_hook_chain'), lambda e: e.update(final=1)),
        life(own, step('yes_hook_chain'), lambda s: s['result'].update(affected=[HOOK, BOOT])),
        life(own, step('yes_hook_chain'), lambda s: s['does']['answer'].update(run=1)),
        life(own, run('yes_hook_chain'), lambda r: r.update(actions=[], model_receipts=[])),
        life(own, after('yes_hook_chain'), lambda a: a.update(open_asks={})),
        life(own, after('yes_hook_chain'), lambda a: a['reads'].update(boot_load_cut_shipped='TRUE')),
        life(own, after('yes_hook_chain'), lambda a: a['reads'].update(boot_load_cut_approved='TRUE')),
        life(own, event('no_boot_load'), lambda e: e.update(predicate='hook_chain_cut_approved')),
        life(own, event('no_boot_load'), lambda e: e.update(verified=False)),
        life(own, event('no_boot_load'), lambda e: e.update(final=1)),
        life(own, event('no_boot_load'), lambda e: e.update(final=False)),
        life(own, event('no_boot_load'), lambda e: e.update(truth='TRUE')),
        life(own, run('no_boot_load'), lambda r: r.update(status='WAITING', work_state='waiting')),
        life(own, after('no_boot_load'), lambda a: a['budget'].update(compute=8)),
        life(own, after('no_boot_load'), lambda a: a['reads'].update(boot_load_cut_shipped='TRUE')),
        life(own, run('measured_again'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', actions=[SHIP_HOOK])),
        life(own, step('measured_again'), lambda s: s['does']['event'].update(version='cut-000000000000')),
        life(own, step('measured_again'), lambda s: s['does']['event']['measured'].update(samples=212)),
        life(own, after('measured_again'), lambda a: a['budget'].update(compute=8)),
        life(own, after('measured_again'), lambda a: a['providers'].update({'local-provider': 2})),
        life(own, after('measured_again'), lambda a: a['rows']['hook_chain_samples_ge_100']['measured'].update(samples=212)),
        life(own, step('guardrail_broke'), lambda s: s['result'].update(status='OUT_OF_SCOPE')),
        life(own, step('guardrail_broke'), lambda s: s['result'].update(affected=[])),
        life(own, event('guardrail_broke'), lambda e: e.update(verified=1)),
        life(own, run('guardrail_broke'), lambda r: r.update(status='SUPPORTED_BY_EVIDENCE', work_state='completed', stop_reasons=[])),
        life(own, after('guardrail_broke'), lambda a: a['reads'].update(hook_chain_cut_shipped='TRUE')),
        life(own, run('guardrail_back'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', actions=[SHIP_HOOK])),
        life(own, after('guardrail_back'), lambda a: a['reads'].update(hook_chain_cut_shipped='UNKNOWN')),
        life(late, event('yes_hook_chain'), lambda e: e.update(source='STAMP:operations')),
        life(late, event('yes_hook_chain'), lambda e: e.update(predicate='boot_load_cut_approved')),
        life(late, event('yes_hook_chain'), lambda e: e.update(verified=False)),
        life(late, event('yes_hook_chain'), lambda e: e.update(final=1)),
        life(late, event('yes_hook_chain'), lambda e: e.update(truth='FALSE')),
        life(late, step('yes_hook_chain'), lambda s: s['result'].update(status='UNVERIFIED_EVENT_IGNORED')),
        life(late, step('yes_hook_chain'), lambda s: s['result'].update(affected=[])),
        life(late, step('sample_shrank'), lambda s: s['result'].update(status='OUT_OF_SCOPE')),
        life(late, run('yes_hook_chain'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', work_state='completed', actions=[SHIP_HOOK])),
        life(late, after('yes_hook_chain'), lambda a: a['reads'].update(hook_chain_cut_shipped='TRUE')),
        life(late, after('yes_hook_chain'), lambda a: a['budget'].update(compute=9)),
        # ---- R80
        life(pj, run('look'), lambda r: r.update(status='WAITING', work_state='waiting', actions=[ASK_CLIENT])),
        life(pj, run('opted_in'), lambda r: r.update(actions=[SEND_INTERNAL], pending=[])),
        life(pj, run('opted_in'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED')),
        life(pj, event('opted_in'), lambda e: e.update(verified=False)),
        life(pj, after('opted_in'), lambda a: a['reads'].update(signals_sent='TRUE')),
        life(pj, event('confirmed'), lambda e: e.update(truth='FALSE')),
        life(pj, event('confirmed'), lambda e: e.update(final=False)),
        life(pj, event('confirmed'), lambda e: e.update(verified=False)),
        life(pj, event('confirmed'), lambda e: e.update(answers='0' * 64)),
        life(pj, event('confirmed'), lambda e: e.update(predicate='opted_in')),
        life(pj, event('confirmed'), lambda e: e.update(source='STAMP:founder')),
        life(pj, step('confirmed'), lambda s: s['result'].update(status='UNVERIFIED_EVENT_IGNORED')),
        life(pj, step('confirmed'), lambda s: s['does']['answer'].update(by='founder')),
        life(pj, run('confirmed'), lambda r: r.update(actions=[SEND_INTERNAL])),
        life(pj, run('confirmed'), lambda r: [e for e in r['trace'] if e['operation'] == 'ASK_CLOSED'][0]['data'].update(truth='FALSE')),
        life(pj, after('confirmed'), lambda a: a['grants'].append('fan-in:internal')),
        life('tiers.project_refused', event('refused'), lambda e: e.update(truth='TRUE')),
        life('tiers.project_refused', run('refused'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', work_state='completed', actions=[SEND_PROJECT])),
        life('tiers.project_refused', after('refused'), lambda a: a['reads'].update(signals_sent='TRUE')),
        life('tiers.internal', run('look'), lambda r: r['provenance'][0].update(sha256='0' * 64)),
        life('tiers.internal', after('look'), lambda a: a['reads'].update(tier_project='TRUE')),
        life('tiers.internal', after('look'), lambda a: a['reads'].update(signals_sent='FALSE')),
        life('tiers.internal', after('look'), lambda a: a.update(grants=['fan-in:external', 'fan-in:internal', 'fan-in:project'])),
        life('tiers.portfolio', run('look'), lambda r: r.update(actions=['send-portfolio@1'])),
        life('tiers.portfolio', run('look'), lambda r: r.update(selected_branch='R-FAN-IN@1/OR1')),
        life('tiers.portfolio', after('look'), lambda a: a['reads'].update(notice_shown='FALSE')),
        life('tiers.external', run('look'), lambda r: r.update(status='LOCAL_MODEL_EFFECTS_RECORDED', actions=['send-external@1'])),
        life('tiers.external', after('look'), lambda a: a['reads'].update(signals_sent='TRUE')),
        life('tiers.external', after('look'), lambda a: a.update(grants=['fan-in:internal'])),
        life('tiers.external', event('opted_in'), lambda e: e.update(verified=False)),
        life('tiers.external', event('opted_in'), lambda e: e.update(source='hand-written')),
        life('tiers.external', step('opted_in'), lambda s: s['result'].update(status='UNVERIFIED_EVENT_IGNORED')),
        life('tiers.external', run('opted_in'), lambda r: r.update(actions=[SEND_INTERNAL])),
        life('tiers.external', after('opted_in'), lambda a: a['reads'].update(signals_sent='FALSE')),
        case('56_tier_rules', lambda c: c['outcome'].update(actions=[SEND_INTERNAL])),
        case('56_tier_rules', lambda c: c.update(packs=[RULES, TIER['internal']])),
        case('56_tier_rules', lambda c: c['derived_state']['budget_after'].update(compute=10)),
        case('56_tier_rules', lambda c: c['derived_state']['facts']['portfolio/fan-in|notice_shown'].update(truth='FALSE')),
        packs(lambda p: method(p[RULES], SEND_PROJECT).update(requires=['opted_in', 'batch_confirmed'])),
        packs(lambda p: method(p[RULES], SEND_PROJECT).update(requires=['tier_project', 'opted_in'])),
        packs(lambda p: method(p[RULES], ASK_CLIENT).update(requires=['tier_project'])),
        packs(lambda p: p[RULES]['rules'][0]['branches'][2].remove('opted_in')),
        packs(lambda p: p[RULES]['rules'][0]['branches'][3].remove('opted_in')),
        packs(lambda p: p[RULES]['rules'][0]['branches'][1].remove('notice_shown')),
        packs(lambda p: p[RULES]['rules'][0]['branches'][2].remove('batch_confirmed')),
        packs(lambda p: method(p[RULES], 'send-portfolio@1').update(requires=['tier_portfolio'])),
        packs(lambda p: method(p[RULES], 'send-external@1').update(requires=['tier_external'])),
        packs(lambda p: method(p[RULES], ASK_CLIENT).update(ask_to='founder')),
        packs(lambda p: method(p['120_feedback'], PUSH).update(grant='action:write-local@1')),
        packs(lambda p: method(p['120_feedback'], WRITE).update(cost={'compute': 0, 'money': 0, 'attention': 0})),
        packs(lambda p: p['120_feedback']['evidence'].append({'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/self', 'version': '1'})),
        packs(lambda p: p['124_cut_desk']['providers'].update({'founder-channel': 0})),
        packs(lambda p: method(p['124_cut_desk'], SHIP_BOOT).update(requires=['boot_load_baseline_cited', 'boot_load_samples_ge_100', 'boot_load_cut_approved'])),
        packs(lambda p: p[TIER['project']]['grants'].append('fan-in:internal')),
        packs(lambda p: method(p[RULES], SEND_INTERNAL).update(requires=[])),
        packs(lambda p: method(p[RULES], SEND_PROJECT)['requires'].append('tier_internal')),
        packs(lambda p: [e.update(truth='TRUE') for e in p[TIER['project']]['evidence'] if e['predicate'] == 'tier_internal']),
        packs(lambda p: p[TIER['external']]['evidence'].pop(0)),
        packs(lambda p: p[RULES]['methods'].append(dict(method(p[RULES], 'show-notice@1'), id='become-internal@1', effect='tier_internal'))),
        packs(lambda p: p[TIER['portfolio']].update(scope=p[TIER['internal']]['scope'])),
        packs(lambda p: p[TIER['internal']]['grants'].append('notice:portfolio')),
        packs(lambda p: p[RULES].update(grants=['fan-in:internal'])),
        packs(lambda p: p[RULES].update(scope='everyone/fan-in')),
        packs(lambda p: p[RULES].update(evidence=[{'predicate': 'tier_internal', 'truth': 'TRUE', 'verified': True, 'source': 'x', 'version': '1'}])),
        packs(lambda p: p[RULES].update(providers={'client-channel': 9})),
        packs(lambda p: p[RULES]['rules'].append(dict(p[RULES]['rules'][0], id='R-CONFIRMED@1', head='batch_confirmed', branches=[['tier_project']]))),
        packs(lambda p: p[TIER['project']].update(methods=[dict(method(p[RULES], 'show-notice@1'), id='confirm-self@1', effect='batch_confirmed', requires=['tier_project'], grant='fan-in:project')])),
        packs(lambda p: p[TIER['external']].update(rules=[dict(p[RULES]['rules'][0], id='R-FAN-IN@2', replaces='R-FAN-IN@1', branches=[['tier_external', 'signals_sent']])])),
        packs(lambda p: p[TIER['project']]['evidence'].append({'predicate': 'batch_confirmed', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/self', 'version': '1'})),
        packs(lambda p: p[TIER['external']]['evidence'].append({'predicate': 'opted_in', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/self', 'version': '1'})),
        packs(lambda p: p[TIER['internal']]['evidence'][1].update(scope='project/fan-in')),
        packs(lambda p: [e.update(verified=False) for e in p[TIER['portfolio']]['evidence'] if e['predicate'] == 'tier_internal']),
        life('tiers.old_grant', after('look'), lambda a: a['grants'].remove('fan-in:internal')),
        life('tiers.old_grant', run('opted_in'), lambda r: r.update(actions=[SEND_INTERNAL], pending=[], status='LOCAL_MODEL_EFFECTS_RECORDED')),
        life('tiers.old_grant', run('look'), lambda r: r['provenance'].pop(1)),
        life('tiers.old_grant', after('look'), lambda a: a['reads'].update(tier_internal='TRUE')),
        life('tiers.old_grant', run('confirmed'), lambda r: r.update(actions=[SEND_INTERNAL])),
        life('tiers.foreign_row', step('unverified_row'), lambda s: s['result'].update(status='RECONCILED')),
        life('tiers.foreign_row', step('row_from_another_scope'), lambda s: s['result'].update(status='RECONCILED', affected=[FAN_IN])),
        life('tiers.foreign_row', after('row_from_another_scope'), lambda a: a['reads'].update(tier_internal='TRUE')),
        life('tiers.foreign_row', after('row_from_another_scope'), lambda a: a['rows']['tier_internal'].update(truth='TRUE')),
        life('tiers.foreign_row', event('row_in_scope'), lambda e: e.update(truth='FALSE')),
        life('tiers.foreign_row', event('row_in_scope'), lambda e: e.update(verified=1)),
        life('tiers.foreign_row', event('row_in_scope'), lambda e: e.update(scope='internal/fan-in')),
        life('tiers.foreign_row', after('row_in_scope'), lambda a: a['reads'].update(tier_internal='FALSE')),
        life('tiers.foreign_row', after('row_in_scope'), lambda a: a['grants'].append('fan-in:internal')),
        life('tiers.foreign_row', after('row_in_scope'), lambda a: a['budget'].update(compute=9)),
        life('tiers.foreign_row', run('opted_in'), lambda r: r.update(actions=[SEND_INTERNAL], pending=[])),
        life('tiers.foreign_row', run('opted_in'), lambda r: [e['data'].update(accepted=True, blockers=[]) for e in r['trace'] if e['operation'] == 'ADMISSION']),
        life('tiers.foreign_row', run('confirmed'), lambda r: r.update(actions=[SEND_INTERNAL])),
        life('tiers.foreign_row', after('confirmed'), lambda a: a['rows']['signals_sent'].update(source='LOCAL_MODEL:send-internal@1')),
        # ---- a row of a trace rewritten and the trace chained again
        ('rechained', fc, lambda L: line(run('repeat')(L), 'RETAIN').update(source='fixture/elsewhere')),
        ('rechained', fc, lambda L: line(run('sent')(L), 'METHOD_MATCH').update(method=PUSH)),
        ('rechained', rd, lambda L: line(run('captured', 1)(L), 'ADMISSION').update(accepted=True, blockers=[])),
        ('rechained', rd, lambda L: line(run('retry', 1)(L), 'ADMISSION').update(cost={'compute': 0, 'money': 0, 'attention': 0})),
        ('rechained', 'tiers.internal', lambda L: line(run('look')(L), 'REFINE').update(alternatives=1)),
        ('rechained', 'tiers.portfolio', lambda L: line(run('look')(L), 'METHOD_MATCH').update(method=SEND_INTERNAL)),
        ('rechained', 'tiers.external', lambda L: line(run('look')(L), 'QUERY_EVIDENCE').update(predicate='tier_internal')),
        ('rechained', 'tiers.portfolio', lambda L: line(run('look')(L), 'RETAIN').update(version='2')),
        ('rechained', 'cuts.missing.small_sample', lambda L: line(run('measured')(L), 'METHOD_ABSENT').update(predicate='hook_chain_cut_approved')),
        ('rechained', 'cuts.missing.small_sample', lambda L: run('measured')(L)['trace'].insert(1, {'operation': 'NOTE', 'data': {'text': 'approved by phone'}})),
        ('rechained', 'cuts.missing.no_baseline', lambda L: run('measured')(L)['trace'].insert(1, {'operation': 'RETAIN', 'data': {'predicate': 'hook_chain_cut_approved', 'source': 'STAMP:founder', 'version': 'ask-1'}})),
    ]


IDS = list(CLAIMS) + ['S79_ordered_claims_fail_on_forged_records']


def checks(data, ROOT, sha, check_chain):
    """The ten rows of this module, S70 to S79. It never raises: whatever goes wrong while a record is read is a failed row that says so."""
    try:
        return _rows(data, ROOT, check_chain, IDS)
    except Exception as e:
        return [(i, False, 'the checks of this version could not be made: ' + type(e).__name__) for i in IDS]


def _rows(data, ROOT, check_chain, ids):
    try:
        files = {n: json.loads((ROOT / 'scenarios' / (n + '.json')).read_text()) for n in PACKS}
        case_files = {cid: json.loads((ROOT / 'cases' / (cid + '.json')).read_text()) for cid in CASES}
        handler = hashlib.sha256((ROOT / 'kinds' / 'scrub_text.py').read_bytes()).hexdigest()   # the kind file, by its bytes: the record's list of handlers must hold this sha256
        mine = {'cases': [c for c in data['cases'] if c['id'] in CASES], 'scenes': {'ordered': data['scenes']['ordered']}, 'action_handlers': data['action_handlers']}
    except Exception as e:
        return [(i, False, 'the record or a pack file of this version cannot be read: ' + type(e).__name__) for i in ids]
    verdict = _judge(mine, files, case_files, handler, check_chain)
    wrong = lambda targets: [(t, verdict[t][:3]) for t in targets if verdict[t]]
    out = [(cid, not wrong(targets), claims + (' ' + str(wrong(targets)) if wrong(targets) else '')) for cid, (claims, targets) in CLAIMS.items()]

    # The same claims on forged copies. A hand-made forgery changes a copy of one record or of the pack files; the sample changes one leaf in place.
    left = []
    forgeries = _handmade()
    for i, (kind, name, change) in enumerate(forgeries):
        try:
            if kind == 'packs':
                forged = copy(files)
                change(forged)   # judged by the shape of the packs alone: a run's own record of its packs' hashes would refuse any changed pack, and proves nothing about what a pack must say
                caught = any(_judge(mine, forged, case_files, handler, None, only={'shape:effects', 'shape:cuts', 'shape:tiers'}).values())
            elif kind == 'case':
                forged = copy([c for c in mine['cases'] if c['id'] == name][0])
                change(forged)
                caught = bool(_case(forged, files, case_files[name], CASES[name]))
            elif kind == 'rechained':
                forged = copy(_at(mine['scenes']['ordered'], name))
                change(forged)
                _rechain(forged)
                wrong = _life(forged, files, LIVES[name], check_chain)   # judged with the chain: it holds again, so the row itself must be what is refused
                caught = bool(wrong) and not any(what.endswith('trace chain') for _, what in wrong)
            else:
                forged = copy(_at(mine['scenes']['ordered'], name))
                change(forged)
                caught = bool(_life(forged, files, LIVES[name]))
        except Exception:
            caught = False   # a forgery that cannot be made proves nothing
        if not caught:
            left.append(('handmade', i, kind, name))
    # The sequence as a whole and the scrub's handler: a life taken out, and the entry of `scrub_text` in the record's list of handlers forged or gone.
    whole = [lambda m: m['scenes']['ordered']['effects'].pop('rail_down'),
             lambda m: m['action_handlers'][KIND].update(sha256='0' * 64),
             lambda m: m['action_handlers'][KIND].update(file='extensions/ordered_effects.py'),
             lambda m: m['action_handlers'][KIND].update(module='extensions.ordered_effects'),
             lambda m: m['action_handlers'].pop(KIND)]
    for i, change in enumerate(whole):
        try:
            forged = copy(mine)
            change(forged)
            caught = bool(_judge(forged, files, case_files, handler, None, only={'scene'})['scene'])
        except Exception:
            caught = False
        if not caught:
            left.append(('whole record', i, 'scene', None))
    try:
        made, passed = sweep(mine, files, case_files, handler, None, STRIDE)
    except Exception as e:
        made, passed = 0, [('the sample of leaves could not be made', type(e).__name__)]
    honest = not any(verdict.values())
    count = len(forgeries) + len(whole)
    out.append((ids[-1], honest and not left and not passed and made > 0,
                f'{count} hand-made and {made} sampled forgeries; not caught: {left + passed[:5]}' if (left or passed) else f'{count} hand-made and {made} sampled forgeries, all caught'))
    return out
