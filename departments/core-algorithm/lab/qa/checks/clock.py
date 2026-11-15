"""Independent checks for 0.13.0-time (S110 to S119). Reads the record, the pack files, the case files, the kernel's text and added.json;
never loads the lab's code.

Time is evidence a clock adapter states at a tick; the kernel has no word of it. Checked here without the kernel and without the adapter.
The module keeps books of its own (`Books`) and a script of its own (`SCRIPT`: the eighteen walks, step by step, with every row a step
brings). From the pack files and that script alone the books make every walk again: each pack the clock states (its name, its rows, cut
into several packs past ROWS rows, a revoke for each grant past its box, an allowance at a new period), each run (planned, gated, acted
and hashed line by line the way the kernel does it for the built-in kind `simulate_fact`), each event, each refusal in the adapter's own
words, each tick's report and what stood after each step, down to a digest of the whole books. The four time cases are made again the same
way, whole, from their case files.

S110 holds the record to that: every walk and every time case equals, field for field, what the books make (so any one field of them
changed, a run moved to another step, a step taken out or put in twice, shows), every clock pack is the pack its scenario file holds, and
no other scenario file carries a row in the clock's names. S111 to S117 are pins: they say what the record must show for the claims C1 to
C13 of the passage, in fixed words (the order ships on day 2 and stops on day 4; the grant ends past day 15; ...), and they pin the rows
the walks bring. S118 holds the kernel. S119 shows that each check is live: every forgery listed below is refused by the check it is
listed for, and each of S110 to S118 refuses one that the other eight pass. For S111 to S117 that forgery is a world made again from end
to end (a pack file, a case file or a step of the script changed and everything made again from it by these books, which S110 passes):
only the pins can tell.

The books replay the built-in kind `simulate_fact` only. A walk or a time case with a step of another kind, a constructor or the learner
switched on fails every check here rather than passing unread."""
import json, hashlib, re

CLOCK = 'adapter:clock@1'
MARK = 'clock@'
ROWS = 64   # at most this many rows in one clock pack
WORDS = ('clock', 'tick', 'window', 'deadline', 'expire', 'allowance', 'overdue', 'in-time', 'moment', 'until:', 'as_of')   # the adapter's words: the kernel's text holds none of them, in any letter case
RANK = ('SEMANTICS_MISSING', 'SEMANTICS_UNAPPROVED', 'EVIDENCE_CONFLICT', 'REFUSED', 'QUERY_EVIDENCE', 'AUTHORITY_REQUIRED', 'PROVIDER_REQUIRED', 'RESOURCE_REQUIRED', 'METHOD_ABSENT', 'CYCLE_LIMIT')
SAID = 'LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'   # the kernel's sentence on every run
NO_KERNEL, NO_MOMENT, BACK, NO_LABEL = ('A tick is made on a kernel, and execute is true or false', 'A moment is a whole number that is not negative',
                                        'Time does not go back: the moment is ', 'A label is text without the mark of the clock')   # the adapter's four refusals
R, S, X, A = 'LOCAL_MODEL_EFFECTS_RECORDED', 'SUPPORTED_BY_EVIDENCE', 'RESOURCE_REQUIRED', 'AUTHORITY_REQUIRED'
SHIP, LEND, G = 'ship-replacement@1', 'disburse-loan@1', 'action:disburse-loan@1'
Q, L = 'orgA/fulfillment', 'orgA/lending'
IDS = ('S110_the_recorded_walks_and_the_time_cases_are_what_the_books_of_the_check_make_field_for_field',
       'S111_the_moment_of_a_run_is_the_latest_clock_pack_in_its_provenance',
       'S112_a_timed_fact_expires_by_resting_and_what_was_made_on_it_lapses',
       'S113_a_closed_window_is_a_decision_and_what_needs_it_is_refused',
       'S114_no_row_moves_the_moment_or_stops_the_clock_and_a_refused_tick_changes_nothing',
       'S115_a_time_boxed_grant_ends_and_what_was_done_under_it_stands',
       'S116_late_is_overdue_as_the_look_begins_and_never_a_status_word',
       'S117_an_allowance_comes_back_when_a_new_period_begins',
       'S118_the_kernel_is_the_pinned_kernel_without_a_word_of_time_and_the_clock_is_no_action_kind',
       'S119_time_checks_fail_on_forged_records_each_on_a_forgery_of_its_own')
CLAIMS = IDS[:9]


def text(v):   # a value as JSON text, the way the kernel compares two versions: 1 and 1.0 are two
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def fresh(v):   # plain data of its own
    return json.loads(json.dumps(v))


def whole(v):
    return type(v) is int and 0 <= v < 10 ** 18


def plain_number(s):
    return isinstance(s, str) and s.isascii() and s.isdigit() and len(s) <= 18 and str(int(s)) == s


def closes(name):   # the last moment a window name stands for, or None when the name is not a window
    return int(name[6:]) if isinstance(name, str) and name.startswith('until:') and plain_number(name[6:]) else None


def named(pid):   # the moment a pack name says when the name is one of the clock's: <label>clock@<n>, or <label>clock@<n>.<i> for a later pack at that moment
    n, dot, i = pid.rpartition(MARK)[2].partition('.') if isinstance(pid, str) and MARK in pid else ('', '', '')
    return int(n) if plain_number(n) and (not dot or (plain_number(i) and i != '0')) else None


def boxed(name):   # (the last moment, the grant) of the name `box:<n>:<grant>`; a box cannot be boxed
    n, sep, grant = name[4:].partition(':') if name.startswith('box:') else ('', '', '')
    return (int(n), grant) if sep and grant and not grant.startswith('box:') and plain_number(n) else None


def allowed(name):   # (the dimension, the amount, the period) of the name `allowance:<dimension>:<amount>:<every>`, every at least 1
    parts = name[10:].rsplit(':', 2) if name.startswith('allowance:') else []
    return (parts[0], int(parts[1]), int(parts[2])) if len(parts) == 3 and parts[0] and plain_number(parts[1]) and plain_number(parts[2]) and int(parts[2]) >= 1 else None


class Refusal(Exception):
    """A tick the clock refuses, in the adapter's own words."""


class Books:
    """The check's own books of one State: kept from pack files and the rows a script brings, with the kernel's rules for a row, a
    reading, a plan, a gate, a step and a run's hash chain, and the adapter's rules for the clock's packs, all in this module's words."""

    def __init__(self, sha):
        self.sha = sha
        self.scope, self.goals, self.rows, self.rules, self.proposed, self.methods = Q, [], {}, {}, {}, {}
        self.providers, self.grants, self.budget, self.preference = {}, set(), {'compute': 10, 'money': 10, 'attention': 3}, ['compute', 'money', 'attention']
        self.loaded, self.journal = [], []

    # ---- rows and packs
    def observe(self, row):   # a verified row is stored under its scope, unless a decision stands there that it cannot replace (the journal says so)
        scope = row.get('scope', self.scope)
        if not row.get('verified', False):
            return False
        key = scope + '|' + row['predicate']
        if self.rows.get(key, {}).get('final') and not row.get('final'):
            self.journal.append({'status': 'DECISION_STANDS', 'scope': scope, 'predicate': row['predicate']})
            return False
        self.rows[key] = dict(row, scope=scope)
        return True

    def load(self, pack):
        if pack.get('constructors') or pack.get('learning') or any(m.get('action') != 'simulate_fact' or m['id'] in self.methods for m in pack.get('methods', [])):
            raise ValueError('a pack these books do not replay')
        self.scope = pack.get('scope', self.scope)
        self.goals = list(pack['goals']) if 'goals' in pack else self.goals
        for row in pack.get('evidence', []):
            self.observe(row)
        for r in pack.get('rules', []):
            if r.get('approved', False):
                self.rules[r['head']] = dict(r)
            else:
                self.proposed[r['head']] = dict(r, status='PROPOSED_ONLY')
        self.methods.update({m['id']: dict(m) for m in pack.get('methods', [])})
        self.providers.update(pack.get('providers', {}))
        self.grants = (self.grants | set(pack.get('grants', []))) - set(pack.get('revoke_grants', []))
        self.budget.update(pack.get('budget', {}))
        self.preference = list(pack['preference']) if 'preference' in pack else self.preference
        self.loaded.append({'pack': pack['id'], 'sha256': self.sha(pack)})

    def fact(self, pred, seen=()):   # the stored row when it is believed: every row it rests on reads TRUE at the version it names
        row = self.rows.get(self.scope + '|' + pred)
        if row is None or pred in seen:
            return {'truth': 'UNKNOWN'}
        for dep in row.get('depends_on', []):
            other = self.fact(dep['predicate'], seen + (pred,))
            if other.get('truth') != 'TRUE' or text(other.get('version')) != text(dep.get('version')):
                return {'truth': 'UNKNOWN'}
        return row

    # ---- a plan
    def expand(self, pred, log, path=(), depth=0, root=False):   # the ways to make a fact hold, and what blocks the others
        if pred in path or depth >= 20:
            log('CYCLE_LIMIT', predicate=pred)
            return [], ['CYCLE_LIMIT']
        seen = self.fact(pred)
        way = lambda actions=(), needs=(), proof=(), branch='': {'actions': list(actions), 'needs': list(needs), 'proof': list(proof), 'branch': branch}
        both = lambda a, b: way(dict.fromkeys(a['actions'] + b['actions']), dict.fromkeys(a['needs'] + b['needs']), a['proof'] + b['proof'], a['branch'] or b['branch'])
        if seen['truth'] == 'TRUE':
            log('RETAIN', predicate=pred, source=seen.get('source'), version=seen.get('version'))
            return [way(proof=[pred + ' observed TRUE (' + str(seen.get('source')) + ')'])], []
        if seen['truth'] == 'FALSE' and seen.get('final'):
            log('REFUSED', predicate=pred, source=seen.get('source'))
            return [], ['REFUSED']
        rule = self.rules.get(pred)
        if rule:
            log('REFINE', predicate=pred, rule=rule['id'], alternatives=len(rule['branches']))
            ways, blocks = [], []
            for i, parts in enumerate(rule['branches']):
                some = [way(proof=[pred + ' ⇐ ' + rule['id'] + ': alternative ' + str(i + 1)], branch=rule['id'] + '/OR' + str(i + 1))]
                for part in parts:
                    below, why = self.expand(part, log, path + (pred,), depth + 1)
                    blocks += why
                    some = [both(a, b) for a in some for b in below]
                    if not some:
                        break
                ways += some
            if seen['truth'] == 'FALSE' and any(not w['actions'] for w in ways):
                log('EVIDENCE_CONFLICT', predicate=pred)
                return [], blocks + ['EVIDENCE_CONFLICT']
            return ways, blocks
        if root and pred not in {m['effect'] for m in self.methods.values()}:
            kind = 'SEMANTICS_UNAPPROVED' if pred in self.proposed else 'SEMANTICS_MISSING'
            log(kind, predicate=pred)
            return [], [kind]
        makers = [m for m in self.methods.values() if m['effect'] == pred and m.get('approved', True)]
        if not makers:
            reason = 'QUERY_EVIDENCE' if seen['truth'] == 'UNKNOWN' else 'METHOD_ABSENT'
            log(reason, predicate=pred)
            return [], [reason]
        ways, blocks = [], []
        for m in makers:
            log('METHOD_MATCH', predicate=pred, method=m['id'])
            some = [way(needs=[pred], proof=[m['id'] + ' would establish ' + pred])]
            for need in m.get('requires', []):
                below, why = self.expand(need, log, path + (pred,), depth + 1)
                blocks += why
                some = [both(a, b) for a in some for b in below]
                if not some:
                    break
            for w in some:
                if m['id'] not in w['actions']:
                    w['actions'].append(m['id'])
                ways.append(w)
        return ways, blocks

    def cost(self, actions):
        return {d: sum(self.methods[a].get('cost', {}).get(d, 0) for a in actions) for d in self.budget}

    def gate(self, actions, log):   # what stands between a plan and its steps: the budget, the grants, the providers
        cost, why, use = self.cost(actions), [], {}
        why += ['RESOURCE_REQUIRED' for d, v in cost.items() if v > self.budget[d]]
        for a in actions:
            m = self.methods[a]
            if m.get('grant') and m['grant'] not in self.grants:
                why.append('AUTHORITY_REQUIRED')
            if m.get('provider'):
                use[m['provider']] = use.get(m['provider'], 0) + 1
        why += ['PROVIDER_REQUIRED' for p, n in use.items() if self.providers.get(p, 0) < n]
        log('ADMISSION', methods=list(actions), accepted=not why, blockers=sorted(set(why)), cost=cost)
        return sorted(set(why))

    def holds(self, goal):   # the goal holds on the evidence: some way to it has nothing left to do
        return any(not w['actions'] for w in self.expand(goal, lambda op, **data: None, root=True)[0])

    # ---- a run
    def resolve(self, goal, execute):
        trace = []

        def log(op, **data):
            line = {'seq': len(trace) + 1, 'prev_sha256': trace[-1]['sha256'] if trace else 'GENESIS', 'operation': op, 'data': data}
            line['sha256'] = self.sha(line)
            trace.append(line)

        log('GOAL_ACCEPTED', goal=goal, scope=self.scope)
        ways, blockers = self.expand(goal, log, root=True)
        open_ways = []
        for w in ways:
            why = self.gate(w['actions'], log)
            blockers = blockers + why
            if not why:
                open_ways.append(w)
        run = {'goal': goal, 'scope': self.scope, 'goal_truth_before': self.fact(goal)['truth'], 'work_state': 'blocked', 'actions': [], 'needs': [], 'cost': None, 'proof': [],
               'model_receipts': [], 'candidates': [], 'selected_branch': None, 'stop_reasons': sorted(set(blockers)), 'provenance': [dict(e) for e in self.loaded]}
        if open_ways:
            price = lambda w: self.cost(w['actions'])
            cheaper = lambda a, b: all(a[d] <= b[d] for d in a) and any(a[d] < b[d] for d in a)
            best = [w for w in open_ways if not any(cheaper(price(o), price(w)) for o in open_ways)]
            pick = min(best, key=lambda w: tuple(price(w)[d] for d in self.preference) + (0, tuple(w['actions'])))
            plan = list(pick['actions'])
            log('SELECT', actions=plan, full_cost=price(pick), pareto_options=len(best))
            run.update(status='PLAN_READY', work_state='ready', actions=plan, needs=pick['needs'], cost=price(pick), proof=pick['proof'], selected_branch=pick['branch'], stop_reasons=[], pareto_options=len(best))
            if execute:
                receipts = self.act(plan, log)
                ran = [x['method'] for x in receipts]
                skipped = [e['data']['method'] for e in trace if e['operation'] == 'STEP_ALREADY_TRUE']
                stops = [e['data'] for e in trace if e['operation'] == 'STEP_STOPPED']
                run.update(model_receipts=receipts, status=R if ran else S, work_state='completed', actions=ran, cost=self.cost(ran))
                if skipped:
                    run['skipped'] = skipped
                if stops:
                    run.update(status='STEP_STOPPED', work_state='stopped', pending=plan[plan.index(stops[0]['method']):], goal_truth_after=self.fact(goal)['truth'],
                               stopped={'method': stops[0]['method'], 'reason': stops[0]['reason']})
                else:
                    run['goal_truth_after'] = 'MODEL_DERIVABLE_NOT_EXTERNAL_PROOF' if ran else self.fact(goal)['truth']
        else:
            status = ([x for x in RANK if x in blockers] + ['METHOD_ABSENT'])[0]
            log('BLOCK', reason=status, all_reasons=sorted(set(blockers)))
            run.update(status=status, pareto_options=0)
        log('TERMINAL', status=run['status'], work_state=run['work_state'])
        run.update(trace=trace, trace_root_sha256=trace[-1]['sha256'], claim=SAID)
        self.journal.append({'goal': goal, 'scope': self.scope, 'status': run['status'], 'trace_root_sha256': run['trace_root_sha256']})
        return run

    def act(self, plan, log):   # the steps of a plan in order: each is gated again, makes its row, leaves its receipt and is paid; a step that cannot run ends the run
        receipts = []
        for mid in plan:
            m = self.methods[mid]
            seen = self.fact(m['effect'])
            if seen['truth'] == 'TRUE':
                log('STEP_ALREADY_TRUE', method=mid, effect=m['effect'], source=seen.get('source'), version=seen.get('version'))
                continue
            why = self.gate([mid], log)
            missing = [p for p in m.get('requires', []) if self.fact(p)['truth'] != 'TRUE']
            if why:
                stop = 'Gate changed before effect: ' + ' '.join(why)
            elif missing:
                stop = 'Prerequisite not true before effect: ' + ' '.join(missing)
            elif not self.observe({'predicate': m['effect'], 'truth': 'TRUE', 'verified': True, 'source': 'LOCAL_MODEL:' + mid, 'version': 'local-sim-1', 'evidence_kind': 'SIMULATED_LOCAL',
                                   'depends_on': [{'predicate': p, 'version': self.fact(p).get('version')} for p in m.get('requires', [])]}):
                stop = 'Handler refused: A decision stands on this effect'
            else:
                stop = None
            if stop:
                log('STEP_STOPPED', method=mid, reason=stop, effect_reads=self.fact(m['effect'])['truth'])
                break
            receipt = {'method': mid, 'scope': self.scope, 'action': 'simulate_fact', 'status': 'LOCAL_ONLY', 'model_effect': m['effect']}
            receipt['sha256'] = self.sha(receipt)
            log('LOCAL_EFFECT', receipt=receipt)
            for d, v in m.get('cost', {}).items():
                self.budget[d] -= v
            if m.get('provider'):
                self.providers[m['provider']] -= 1
            receipts.append(receipt)
        return receipts

    def look(self, execute):
        return {'status': 'EVALUATED' if self.goals else 'NO_STANDING_GOAL', 'goals': list(self.goals), 'runs': [self.resolve(g, execute) for g in self.goals]}

    def event(self, row, execute):   # a row arrives: stored or turned away, and the standing goals it touches are looked at
        if not self.observe(row):
            return {'status': 'DECISION_STANDS' if row.get('verified') else 'UNVERIFIED_EVENT_IGNORED', 'affected': [], 'runs': []}
        if row.get('scope', self.scope) != self.scope:
            return {'status': 'OUT_OF_SCOPE', 'affected': [], 'runs': []}
        changed = row['predicate']

        def touches(p, seen):
            if p == changed:
                return True
            if p in seen:
                return False
            seen = seen | {p}
            rule = self.rules.get(p)
            if rule and any(touches(part, seen) for parts in rule['branches'] for part in parts):
                return True
            if any(touches(need, seen) for m in self.methods.values() if m['effect'] == p for need in m.get('requires', [])):
                return True
            stored = self.rows.get(self.scope + '|' + p)
            return bool(stored and any(dep.get('predicate') == changed for dep in stored.get('depends_on', [])))

        affected = [g for g in self.goals if touches(g, frozenset())]
        return {'status': 'RECONCILED', 'event': row, 'affected': affected, 'runs': [self.resolve(g, execute) for g in affected]}

    # ---- the clock
    def moment(self):
        seen = [m for m in (named(e['pack']) for e in self.loaded) if m is not None]
        return max(seen) if seen else None

    def says(self, at, label):   # the packs the clock states at this moment on these books; a moment or a label it refuses is a Refusal in its words
        before = self.moment()
        if not whole(at):
            raise Refusal(NO_MOMENT)
        if before is not None and at < before:
            raise Refusal(BACK + str(before))
        if not isinstance(label, str) or MARK in label:
            raise Refusal(NO_LABEL)
        rows = []
        for scope in [self.scope] + sorted({key.split('|', 1)[0] for key in self.rows} - {self.scope}):
            rows.append({'predicate': 'now', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': CLOCK, 'version': at, 'at': at, 'scope': scope})
            names = set()
            for key, stored in self.rows.items():
                if key.startswith(scope + '|'):
                    names |= {key[len(scope) + 1:]} | {dep['predicate'] for dep in stored.get('depends_on', [])}
            names |= {need for m in self.methods.values() for need in m.get('requires', [])} | {part for r in self.rules.values() for parts in r['branches'] for part in parts}
            for w in sorted((n for n in names if closes(n) is not None), key=closes):
                rows.append({'predicate': w, 'truth': 'TRUE', 'verified': True, 'source': CLOCK, 'version': 'window', 'scope': scope} if at <= closes(w) else
                            {'predicate': w, 'truth': 'FALSE', 'verified': True, 'final': True, 'source': CLOCK, 'version': 'closed', 'scope': scope})
        if len(rows) > ROWS:   # more than one pack: what closes is stated first
            rows = [r for r in rows if r['truth'] == 'FALSE'] + [r for r in rows if r['truth'] != 'FALSE']
        taken, names, i = {e['pack'] for e in self.loaded}, [], 0
        while len(names) * ROWS < len(rows):
            name = label + MARK + str(at) + ('.' + str(i) if i else '')
            names += [name] if name not in taken else []
            i += 1
        packs = [{'schema': 'sutra-extension/2', 'id': name, 'evidence': rows[j * ROWS:(j + 1) * ROWS]} for j, name in enumerate(names)]
        last = {}
        for n, grant in filter(None, map(boxed, self.grants)):
            last[grant] = max(n, last.get(grant, -1))
        gone = sorted(g for g, n in last.items() if n < at and g in self.grants)
        top = {}
        for dim, amount, every in filter(None, map(allowed, self.grants - set(gone))):
            if dim in self.budget and (before is None or at // every > before // every):
                top[dim] = max(amount, top.get(dim, 0))
        if gone:
            packs[0]['revoke_grants'] = gone
        if top:
            packs[0]['budget'] = top
        return packs

    def late(self):   # overdue as a look begins: a due row that no longer reads TRUE, under a goal that does not hold
        return [g for g in self.goals if self.scope + '|in-time:' + g in self.rows and self.fact('in-time:' + g)['truth'] != 'TRUE' and not self.holds(g)]

    def tick(self, at, execute, label):
        if type(execute) is not bool:
            raise Refusal(NO_KERNEL)
        packs = self.says(at, label)

        def lands(row):   # would this row change what is stored? Not when it is stored already, and not when a decision stands there that it cannot replace
            stored = self.rows.get(row['scope'] + '|' + row['predicate'])
            return text(stored) != text(row) and not (stored is not None and stored.get('final') and not row.get('final'))

        new = self.moment() != at or 'revoke_grants' in packs[0] or any(lands(row) for p in packs for row in p['evidence'])
        for p in (packs if new else []):
            self.load(p)
        time = {'as_of': self.moment(), 'late': self.late()}
        out = self.look(execute)
        out['time'] = time
        if new:
            out['clock_pack'] = packs[0]
            if len(packs) > 1:
                out['more_clock_packs'] = packs[1:]
        return out

    def stood(self, watch):   # what stands after a step
        return {'moment': self.moment(), 'scope': self.scope, 'budget': dict(self.budget), 'grants': sorted(self.grants), 'loaded': [e['pack'] for e in self.loaded],
                'reads': {p: self.fact(p)['truth'] for p in watch}, 'stored': {p: self.rows.get(self.scope + '|' + p) for p in watch},
                'turned_away': len([j for j in self.journal if j.get('status') == 'DECISION_STANDS']),
                'books': self.sha({'e': self.rows, 'g': sorted(self.grants), 'b': self.budget, 'p': self.providers, 'l': self.loaded, 'j': self.journal, 'a': {}})}


# ---- the script: the eighteen walks as this module expects them, step by step, with every row a step brings
def row(predicate, truth, version, source, **more):
    return dict({'predicate': predicate, 'truth': truth, 'verified': True, 'source': source, 'version': version}, **more)


def hand(predicate, truth, version, **more):
    return row(predicate, truth, version, 'fixture/written-by-hand', **more)


def resting(r, *moments):   # the row, resting on the windows that stay open until these moments
    return dict(r, depends_on=[{'predicate': 'until:' + str(n), 'version': 'window'} for n in moments])


def T(key, now, execute=False):
    return {'key': key, 'kind': 'tick', 'now': now, 'execute': execute}


def N(key, now, **how):   # a tick that must be refused
    return dict({'key': key, 'kind': 'refused', 'now': now}, **how)


def E(key, r, execute=False):
    return {'key': key, 'kind': 'event', 'row': r, 'execute': execute}


def P(key, name):
    return {'key': key, 'kind': 'pack', 'pack': name}


def LOOK(key, execute=False):
    return {'key': key, 'kind': 'look', 'execute': execute}


ORDER = ['00_goal', '01_domain', '02_methods', '04_admission', '160_timed_approval']
GATES = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']
APPROVAL = lambda version: resting(row('customer_approved', 'TRUE', version, 'fixture/customer-approval'), 3)
W_ORDER = ['now', 'customer_approved', 'replacement_delivered', 'until:3', 'until:5', 'in-time:order_complete']
W_LOAN = ['now', 'loan_disbursed', 'bureau_report_clean', 'until:7', 'until:30', 'until:60', 'in-time:loan_disbursed']
W_PULLS = ['now', 'report_pulled_a', 'report_pulled_b', 'report_pulled_c']
W_DUE = ['now', 'customer_approved', 'replacement_delivered', 'until:5', 'in-time:order_complete']
FAR = 'until:999999999999999999'
SCRIPT = [
    ('order', ORDER, '160_', W_ORDER,
     [T('day_2', 2, True), T('day_2_again', 2, True), N('day_1', 1), E('now_by_hand', hand('now', 'TRUE', 9, at=9)),
      T('day_4', 4, True), E('reopen', hand('until:3', 'TRUE', 'window'), True), P('day_2_pack_again', '160_clock@2'),
      E('late_approval', APPROVAL('approval-v2'), True), P('original_pack_again', '160_timed_approval'), {'key': 'late_by_observe', 'kind': 'observe', 'row': APPROVAL('approval-v3')},
      LOOK('after_the_late_rows', True), T('day_6', 6)]),
    ('late_order', ORDER, '160_', W_ORDER, [T('day_6', 6, True)]),
    ('allowance', GATES + ['15_low_budget', '161_allowance'], '161_', ['now', 'customer_approved', 'replacement_delivered'], [T('day_1', 1, True)]),
    ('loan', ['162_loan'], '162_', W_LOAN,
     [T('day_5', 5, True), E('box_by_hand', hand('box:20:' + G, 'TRUE', '1'), True), T('day_15', 15, True), T('day_16', 16, True),
      T('day_31', 31, True), P('renewal', '162_renewal'), T('day_31_renewed', 31, True)]),
    ('loan_late', ['162_loan'], '162_', W_LOAN, [T('day_16', 16, True)]),
    ('two_boxes', ['162_loan', '162_second_box'], '162_two_boxes_', W_LOAN,
     [T('day_16', 16), T('day_20', 20), T('day_21', 21), P('sanction_again', '162_sanction_again'), LOOK('admitted_until_the_next_tick'), T('day_21_again', 21)]),
    ('pulls', ['163_bureau_pulls'], '163_', W_PULLS,
     [T('day_0', 0, True), T('day_0_again', 0, True), T('day_1', 1, True), P('day_0_pack_again', '163_clock@0'), N('day_0_once_more', 0)]),
    ('weekly', ['163_weekly_pulls'], '163_weekly_', W_PULLS,
     [T('day_6', 6, True), T('day_7', 7, True), T('day_13', 13, True), E('now_by_hand_says_day_0', hand('now', 'TRUE', 0, final=True, at=0)),
      T('day_13_again', 13, True), P('to_the_branch', '163_branch'), T('day_13_in_the_branch', 13, True), P('back_to_lending', '163_lending'), T('day_14', 14, True)]),
    ('due', GATES + ['164_due_by'], '164_', W_DUE, [T('day_6_dry', 6), T('day_6', 6, True), T('day_7', 7)]),
    ('two_goals', GATES + ['164_due_by', '165_two_goals'], '165_', W_DUE, [T('day_6', 6, True)]),
    ('called_late', ['00_goal', '01_domain', '02_methods', '04_admission', '164_called_late'], '164_called_', ['now', 'customer_approved', 'in-time:order_complete'], [T('day_1', 1)]),
    ('two_scopes', ORDER, '166_', ['now', 'customer_approved', 'replacement_delivered', 'until:3', 'until:5', 'until:7', 'until:30'],
     [T('day_2', 2), T('day_3', 3), P('to_the_loan', '162_loan'), T('day_6', 6), P('back_to_the_order', '00_goal'), LOOK('after', True)]),
    ('offer', ['167_offer'], '167_', ['now', 'offer_approved', 'offer_shipped', 'offer_open', 'until:3', 'until:4'],
     [LOOK('before_any_tick'), T('day_2', 2), T('day_4', 4), T('day_5', 5)]),
    ('same_moment', ORDER, '168_', ['now', 'customer_approved', 'stock_reserved', 'until:3', 'until:5', 'until:8'],
     [T('day_2', 2), T('day_2_again', 2), P('hold_arrives', '168_stock_hold'), T('day_2_new', 2), T('day_2_once_more', 2)]),
    ('planted', ORDER, '169_', ['now', 'customer_approved', 'until:3', 'until:5', FAR],
     [T('day_2', 2), E('decision_on_now', hand('now', 'TRUE', 99, final=True, at=99)), E('decision_on_a_window', hand(FAR, 'FALSE', 'closed', final=True)), T('day_4', 4, True), T('day_4_again', 4),
      E('day_5_word_for_word', row('now', 'TRUE', 5, CLOCK, final=True, at=5, scope=Q)), T('day_5', 5)]),
    ('refusals', ORDER, '160_', W_ORDER,
     [T('day_2', 2), N('half_a_day', 2.5), N('two_as_a_fraction', 2.0), N('below_zero', -1), N('true_for_a_moment', True), N('text_for_a_moment', '3'), N('no_moment', None),
      N('too_far', 10 ** 18), N('a_label_with_the_mark', 3, label='day clock@1 '), N('a_label_that_is_no_text', 3, label=5), N('execute_as_text', 3, execute='yes'),
      N('execute_as_a_number', 3, execute=1), T('day_3', 3)]),
    ('withdrawn', ORDER, '160_', W_ORDER,
     [T('day_2', 2), E('approval_withdrawn', row('customer_approved', 'FALSE', 'approval-withdrawn', 'fixture/customer-approval')), T('day_6', 6), E('late_approval', APPROVAL('approval-v2'), True)]),
    ('crowd', ORDER + ['169_shipping_pass'], '169_crowd_', ['now', 'fleet_ready', 'until:3', 'until:5', 'until:6', 'until:74'],
     [T('day_2', 2), E('seventy_windows', resting(row('fleet_ready', 'TRUE', '1', 'fixture/depot'), *range(5, 75))), T('day_4', 4), T('day_6', 6)]),
]
WALKS = [w[0] for w in SCRIPT]
CASES = {'67_late_order': ('late_order', 'day_6', 'QUERY_EVIDENCE', 6), '67a_order_in_time': ('order', 'day_2', R, 2), '68_allowance': ('allowance', 'day_1', R, 1),
         '69_permission_ran_out': ('loan_late', 'day_16', A, 16)}   # a time case -> the walk whose first tick it is, its status, its moment
USED = ('02_methods', '04_gates', '24_budget') + tuple(CASES)   # the cases these checks read


def walk_of(spec, read, sha):
    """One walk made by the check's own books from its pack files and its script: (the walk as the record must hold it, the packs its ticks stated)."""
    name, files, label, watch, steps = spec
    b = Books(sha)
    for n in files:
        b.load(read(n))
    start, done, stated = b.stood(watch), [], []
    for asked in steps:
        kind = asked['kind']
        if kind == 'tick':
            result = b.tick(asked['now'], asked['execute'], label)
            stated += [result['clock_pack']] + result.get('more_clock_packs', []) if 'clock_pack' in result else []
        elif kind == 'refused':
            try:
                b.tick(asked['now'], asked.get('execute', True), asked.get('label', label))
                result = {'refused': None}
            except Refusal as e:
                result = {'refused': str(e)}
        elif kind == 'event':
            result = b.event(asked['row'], asked['execute'])
        elif kind == 'observe':
            result = {'stored': b.observe(asked['row'])}
        elif kind == 'pack':
            b.load(read(asked['pack']))
            result = {'applied': asked['pack']}
        else:
            result = b.look(asked['execute'])
        done.append(dict(asked, result=result, after=b.stood(watch)))   # nothing kept here is changed later: the books replace a row, they never write into one
    return fresh({'packs': list(files), 'label': label, 'watch': list(watch), 'start': start, 'steps': done}), fresh(stated)


def case_of(spec, read, sha):
    """One recorded case made by the check's own books from its case file and its pack files, whole: the run, the books after it and the four views."""
    b = Books(sha)
    packs = [read(n) for n in spec['packs']]
    for p in packs:
        b.load(p)
    run = b.look(spec['execute'])
    for r in run['runs']:
        r.update(learning=[], learning_record={'source_trace': r['trace_root_sha256'], 'learning_sha256': sha([])})   # the learner is off: these books refuse a pack that switches it on
    outcome = run['runs'][0] if run['runs'] else None
    return fresh({'id': spec['id'], 'title': spec['title'], 'description': spec['description'], 'area': spec['area'], 'packs': spec['packs'], 'pack_digest': sha(packs), 'scope': b.scope,
                  'run': run, 'outcome': outcome,
                  'derived_state': {'facts': b.rows, 'rule_ids': [r['id'] for r in b.rules.values()], 'candidate_count': 0, 'budget_after': b.budget, 'historical_events': b.journal},
                  'four_views': {'world': [{'predicate': k, 'truth': v['truth'], 'source': v.get('source')} for k, v in b.rows.items()], 'knowledge': list(b.rules.values()),
                                 'design': outcome['actions'] if outcome else [], 'run': outcome['trace'] if outcome else []}})


def world(ROOT, sha, forged=None, script=None):
    """Everything the books make from the files of the lab (`forged`: file -> text, or None for a file taken out, stands in for files; only
    the forgeries of S119 hand one in) and a script: the walks, the time cases, the packs the ticks stated, and the readers the checks use."""
    forged, files = {} if forged is None else forged, {}

    def raw(rel):   # a file of the lab as bytes, or the text a forgery put in its place
        if rel in forged:
            if forged[rel] is None:
                raise ValueError('no such file')
            return forged[rel].encode('utf-8')
        return (ROOT / rel).read_bytes()

    def read(name):   # a scenario file, read once
        if name not in files:
            files[name] = json.loads(raw('scenarios/' + name + '.json').decode('utf-8'))
        return files[name]

    def names(folder):   # the JSON files of a folder of the lab, by name without the suffix
        there = {f.stem for f in (ROOT / folder).glob('*.json')} | {rel[len(folder) + 1:-5] for rel in forged if rel.startswith(folder + '/') and rel.endswith('.json')}
        return sorted(n for n in there if forged.get(folder + '/' + n + '.json', '') is not None)

    walks, stated = {}, []
    for spec in (SCRIPT if script is None else script):
        walks[spec[0]], said = walk_of(spec, read, sha)
        stated += said
    cases = {cid: case_of(json.loads(raw('cases/' + cid + '.json').decode('utf-8')), read, sha) for cid in CASES}
    return {'walks': walks, 'cases': cases, 'stated': stated, 'raw': raw, 'read': read, 'names': names, 'files': files, 'sha': {name: sha(made) for name, made in list(walks.items()) + list(cases.items())}}


def claims(data, ROOT, sha, check_chain, forged=None, script=None, made=None):
    """The nine checks S110 to S118 on a record: {id: holds}. `made` is a world already made from the same files and script (the forgeries
    that change the record alone reuse one). It raises when the record or a file cannot be read; `checks` turns that into failed rows."""
    same = lambda a, b: sha(a) == sha(b)
    made = made or world(ROOT, sha, forged, script)
    raw, read, names = made['raw'], made['read'], made['names']
    W = data['scenes']['clock']['walks']
    by = {c['id']: c for c in data['cases']}
    if sorted(W) != sorted(WALKS) or not same(sorted(data['scenes']['clock']), ['walks']):
        return {cid: False for cid in CLAIMS}
    step = lambda walk, key: [st for st in W[walk]['steps'] if st['key'] == key][0]
    res = lambda walk, key: step(walk, key)['result']
    after = lambda walk, key: step(walk, key)['after']
    runs = lambda walk, key: res(walk, key)['runs']
    brief = lambda r: (r['status'], r['actions'], [x['method'] for x in r['model_receipts']], r['stop_reasons'])
    briefs = lambda walk, key: [brief(r) for r in runs(walk, key)]
    keys = lambda walk: [st['key'] for st in W[walk]['steps']]
    reads = lambda walk, key, *facts: [after(walk, key)['reads'][p] for p in facts]
    packs_of = lambda st: ([st['result']['clock_pack']] + st['result'].get('more_clock_packs', [])) if 'clock_pack' in st['result'] else []
    ticks = [st for name in WALKS for st in W[name]['steps'] if st['kind'] == 'tick']
    stated = [p for st in ticks for p in packs_of(st)]
    said = lambda walk: [(st['key'], [p['id'] for p in packs_of(st)]) for st in W[walk]['steps'] if st['kind'] in ('tick', 'refused')]
    blocked = ('QUERY_EVIDENCE', [], [], ['METHOD_ABSENT', 'QUERY_EVIDENCE'])
    refused = ('REFUSED', [], [], ['REFUSED'])
    no_grant = (A, [], [], [A])
    is_clock_row = lambda e: e.get('predicate') == 'now' or closes(e.get('predicate')) is not None or e.get('source') == CLOCK
    shaped = lambda p: (set(p) <= {'schema', 'id', 'evidence', 'revoke_grants', 'budget'} and 0 < len(p['evidence']) <= ROWS
                        and all(e.get('source') == CLOCK and e.get('verified') is True and ((e.get('predicate') == 'now' and same(e.get('at'), named(p['id'])) and e.get('final') is True)
                                                                                           or closes(e.get('predicate')) is not None) for e in p['evidence']))
    every_file = names('scenarios')
    mine = [n for n in every_file if re.match(r'16[0-9]_', n) and named(n) is not None]   # the clock packs among this version's scenario files (160 to 169)
    moment_of = lambda r: max(m for m in (named(p['pack']) for p in r['provenance']) if m is not None)
    first = lambda walk: W[walk]['steps'][0]
    case_is_tick = lambda cid, walk, key, status, at: (   # a time case is the first tick of its walk: the walk's packs and the pack that tick stated, the same run, the same moment
        first(walk)['key'] == key and first(walk)['kind'] == 'tick' and by[cid]['packs'] == W[walk]['packs'] + [p['id'] for p in packs_of(first(walk))] and len(packs_of(first(walk))) == 1
        and by[cid]['outcome']['status'] == status == runs(walk, key)[0]['status'] and by[cid]['outcome']['trace_root_sha256'] == runs(walk, key)[0]['trace_root_sha256']
        and same(by[cid]['outcome']['provenance'], runs(walk, key)[0]['provenance']) and same(by[cid]['outcome']['model_receipts'], runs(walk, key)[0]['model_receipts'])
        and moment_of(by[cid]['outcome']) == at == res(walk, key)['time']['as_of'] and by[cid]['run']['status'] == 'EVALUATED' and same(by[cid]['run']['runs'], [by[cid]['outcome']]))
    kernel, book = raw('kernel/core.py'), json.loads(raw('added.json').decode('utf-8'))
    kinds_run = lambda: [x['action'] for st in (s for name in WALKS for s in W[name]['steps']) for r in st['result'].get('runs', []) for x in r['model_receipts']] + [x['action'] for cid in CASES for x in by[cid]['outcome']['model_receipts']]
    offer, approval, hold = read('167_offer'), dict(read('160_timed_approval')['evidence'][0], scope=Q), dict(read('168_stock_hold')['evidence'][0], scope=Q)
    window_3 = [{'predicate': 'until:3', 'version': 'window'}]
    crowd = lambda key: [e['predicate'] for e in packs_of(step('crowd', key))[0]['evidence']]   # the first pack the crowd's tick stated

    def holds(check):   # one check on its own: a record it cannot read fails that check, not its neighbours
        try:
            return check() is True
        except Exception:
            return False

    told = {
        # The whole record of this version, made again. Every walk and every time case equals what the books make from the pack files, the
        # case files and the script; every pack a tick stated is the pack its scenario file holds; the clock packs among this version's
        # scenario files are exactly the ones the walks' ticks stated; every scenario file of the lab that is named like a clock pack has
        # the shape of one (the clock's rows by its source, at most ROWS of them, a revoke line, a budget line, never `grants`); and no
        # other scenario file of the lab carries a row in the clock's names.
        IDS[0]: lambda: (all(sha(W[name]) == made['sha'][name] for name in WALKS)
        and all(sha(by[cid]) == made['sha'][cid] for cid in CASES)
        and all(same(read(p['id']), p) for p in made['stated']) and sorted({p['id'] for p in made['stated']}) == mine
        and all(shaped(read(n)) for n in every_file if named(n) is not None)
        and not any(is_clock_row(e) for n in every_file if named(n) is None for e in read(n).get('evidence', []))),
        # C8: the moment of a run is the latest clock pack in its own provenance, however the run was started: a tick's report says that
        # moment, and so does what stood after it; a look or an event after a tick carries the tick's pack; each time case is the first
        # tick of its walk (packs, run, moment); the same look at two moments has one trace root and two provenances.
        IDS[1]: lambda: (all(st['result']['time']['as_of'] == st['after']['moment'] == st['now'] and all(moment_of(r) == st['now'] for r in st['result']['runs']) for st in ticks)
        and all(case_is_tick(cid, *how) for cid, how in CASES.items())
        and (runs('two_scopes', 'day_2')[0]['trace_root_sha256'] == runs('two_scopes', 'day_3')[0]['trace_root_sha256'] and not same(runs('two_scopes', 'day_2')[0]['provenance'], runs('two_scopes', 'day_3')[0]['provenance'])
             and [res('two_scopes', k)['time']['as_of'] for k in ('day_2', 'day_3')] == [2, 3] and [step('two_scopes', k)['execute'] for k in ('day_2', 'day_3')] == [False, False])
        and [moment_of(runs(*at)[0]) for at in (('order', 'late_approval'), ('order', 'after_the_late_rows'), ('two_scopes', 'after'), ('two_boxes', 'admitted_until_the_next_tick'))] == [4, 4, 6, 21]
        and [runs(*at)[0]['provenance'][-1]['pack'] for at in (('order', 'day_6'), ('late_order', 'day_6'), ('loan', 'day_31_renewed'), ('crowd', 'day_4'))] == ['160_clock@6', '160_clock@6', '162_clock@31.1', '169_crowd_clock@4.1']),
        # C1, C2, C13: the approval is believed up to its window and not after, its stored row is never touched, what was shipped on it
        # lapses with it, an approval that arrives after its window closed is not believed (by event, in its own pack applied again, handed
        # to observe, and when no other row names the window any more), a hold whose window was never published is not believed until the
        # next tick, and a tick made in another scope closes the windows of the scope the State left. Case 67 and its twin 67a differ in
        # their clock pack alone: on day 2 the order ships, on day 6 it stops.
        IDS[2]: lambda: (briefs('order', 'day_2') == [(R, [SHIP], [SHIP], [])] and reads('order', 'day_2', *W_ORDER) == ['TRUE'] * 6
        and briefs('order', 'day_4') == [blocked] and reads('order', 'day_4', *W_ORDER) == ['TRUE', 'UNKNOWN', 'UNKNOWN', 'FALSE', 'TRUE', 'TRUE']
        and [step('order', k)['execute'] for k in ('day_2', 'day_4')] == [True, True]
        and all(same(after('order', k)['stored']['customer_approved'], approval) for k in keys('order')[:keys('order').index('late_approval')]) and same(W['order']['start']['stored']['customer_approved'], approval)
        and same(approval['depends_on'], window_3) and same(step('order', 'late_approval')['row'], resting(row('customer_approved', 'TRUE', 'approval-v2', 'fixture/customer-approval'), 3))
        and (res('order', 'late_approval')['status'], res('order', 'late_approval')['affected'], briefs('order', 'late_approval')) == ('RECONCILED', ['order_complete'], [blocked])
        and (after('order', 'late_approval')['stored']['customer_approved']['version'], reads('order', 'late_approval', 'customer_approved')) == ('approval-v2', ['UNKNOWN'])
        and (step('order', 'original_pack_again')['pack'], after('order', 'original_pack_again')['stored']['customer_approved']['version'], reads('order', 'original_pack_again', 'customer_approved')) == ('160_timed_approval', 'approval-v1', ['UNKNOWN'])
        and same(step('order', 'late_by_observe')['row'], resting(row('customer_approved', 'TRUE', 'approval-v3', 'fixture/customer-approval'), 3)) and same(res('order', 'late_by_observe'), {'stored': True})
        and (after('order', 'late_by_observe')['stored']['customer_approved']['version'], reads('order', 'late_by_observe', 'customer_approved'), briefs('order', 'after_the_late_rows'), step('order', 'after_the_late_rows')['execute']) == ('approval-v3', ['UNKNOWN'], [blocked], True)
        and briefs('late_order', 'day_6') == [blocked]
        and by['67_late_order']['outcome']['trace_root_sha256'] == by['02_methods']['outcome']['trace_root_sha256']   # the chain has no word of time: the late order's run is case 02's run, and its twin on day 2 is case 04's, receipt and all
        and (by['67a_order_in_time']['outcome']['trace_root_sha256'], sha(by['67a_order_in_time']['outcome']['model_receipts'])) == (by['04_gates']['outcome']['trace_root_sha256'], sha(by['04_gates']['outcome']['model_receipts']))
        and (by['67_late_order']['packs'][:-1], by['67_late_order']['packs'][-1], by['67a_order_in_time']['packs'][-1]) == (by['67a_order_in_time']['packs'][:-1], '160_clock@6', '160_clock@2')
        and (brief(by['67_late_order']['outcome']), brief(by['67a_order_in_time']['outcome'])) == (blocked, (R, [SHIP], [SHIP], []))
        and (by['67_late_order']['derived_state']['facts'][Q + '|until:3']['truth'], by['67a_order_in_time']['derived_state']['facts'][Q + '|until:3']['truth']) == ('FALSE', 'TRUE')
        and same(by['67_late_order']['derived_state']['facts'][Q + '|customer_approved'], approval)
        and [reads('same_moment', k, 'stock_reserved', 'until:8') for k in ('hold_arrives', 'day_2_new')] == [['UNKNOWN', 'UNKNOWN'], ['TRUE', 'TRUE']]
        and all(same(after('same_moment', k)['stored']['stock_reserved'], hold) for k in ('hold_arrives', 'day_2_new', 'day_2_once_more')) and same(hold['depends_on'], [{'predicate': 'until:8', 'version': 'window'}])
        and [(e['scope'], e['predicate'], e['truth']) for e in res('two_scopes', 'day_6')['clock_pack']['evidence']]
        == [(L, 'now', 'TRUE'), (L, 'until:7', 'TRUE'), (L, 'until:30', 'TRUE'), (Q, 'now', 'TRUE'), (Q, 'until:3', 'FALSE'), (Q, 'until:5', 'FALSE')]
        and (after('two_scopes', 'back_to_the_order')['scope'], reads('two_scopes', 'back_to_the_order', 'customer_approved', 'until:3')) == (Q, ['UNKNOWN', 'FALSE'])
        and briefs('two_scopes', 'after') == [blocked] and step('two_scopes', 'after')['execute'] is True
        and same(step('withdrawn', 'approval_withdrawn')['row'], row('customer_approved', 'FALSE', 'approval-withdrawn', 'fixture/customer-approval'))
        and [e['predicate'] for e in res('withdrawn', 'day_6')['clock_pack']['evidence']] == ['now', 'until:3', 'until:5']   # no row names the window any more: it is still the clock's row, and it closes at its time
        and same(step('withdrawn', 'late_approval')['row'], step('order', 'late_approval')['row'])
        and (res('withdrawn', 'late_approval')['status'], reads('withdrawn', 'late_approval', 'customer_approved', 'until:3'), briefs('withdrawn', 'late_approval')) == ('RECONCILED', ['UNKNOWN', 'FALSE'], [blocked])),
        # C4, C12: a closed window is the clock's decision; an ordinary row that says it is open and the clock's own earlier pack applied
        # again reopen nothing; a rule that names a window holds inside it and is refused past it, and so is a step that names one, each
        # at its own window, while the decision beside them still reads as decided; a step whose effect is the window is never planned
        # once the clock has closed it (before the first tick it is: a stated limit, on the record).
        IDS[3]: lambda: (same(step('order', 'reopen')['row'], hand('until:3', 'TRUE', 'window')) and step('order', 'reopen')['execute'] is True
        and same(res('order', 'reopen'), {'status': 'DECISION_STANDS', 'affected': [], 'runs': []})
        and same(after('order', 'reopen')['stored']['until:3'], {'predicate': 'until:3', 'truth': 'FALSE', 'verified': True, 'final': True, 'source': CLOCK, 'version': 'closed', 'scope': Q})
        and (step('order', 'day_2_pack_again')['pack'], reads('order', 'day_2_pack_again', 'until:3', 'customer_approved'), after('order', 'day_2_pack_again')['moment']) == ('160_clock@2', ['FALSE', 'UNKNOWN'], 4)
        and after('order', 'day_2_pack_again')['turned_away'] == after('order', 'reopen')['turned_away'] + 1 == after('order', 'day_4')['turned_away'] + 2
        and same(offer['rules'][0]['branches'], [['offer_approved', 'until:3']]) and same([(m['id'], m['effect'], m['requires']) for m in offer['methods']], [('ship-offer@1', 'offer_shipped', ['offer_approved', 'until:4']), ('reopen-offer@1', 'until:3', [])])
        and same(offer['goals'], ['offer_shipped', 'offer_open']) and 'action:reopen-offer@1' in offer['grants']
        and briefs('offer', 'before_any_tick') == [('QUERY_EVIDENCE', [], [], ['QUERY_EVIDENCE']), ('PLAN_READY', ['reopen-offer@1'], [], [])]
        and briefs('offer', 'day_2') == [('PLAN_READY', ['ship-offer@1'], [], []), ('PLAN_READY', [], [], [])]
        and briefs('offer', 'day_4') == [('PLAN_READY', ['ship-offer@1'], [], []), refused] and briefs('offer', 'day_5') == [refused, refused]
        and [e['predicate'] for e in res('offer', 'day_2')['clock_pack']['evidence']] == ['now', 'until:3', 'until:4']
        and (reads('offer', 'day_5', 'offer_approved', 'until:3', 'until:4'), after('offer', 'day_5')['stored']['offer_approved'].get('final')) == (['TRUE', 'FALSE', 'FALSE'], True)),
        # C5, C9: a tick is refused for an earlier moment, a moment that is not a whole number below 10**18, a label that is not text or
        # holds the clock's mark and an execute that is not true or false, each in the adapter's words, and what stood after it is what
        # stood before it, digest and all; a second tick at the same moment states nothing and something new there gets a pack with a
        # name of its own; an ordinary `now` row is turned away; a decision written by hand on `now` or on a window no moment can pass
        # does not stop the clock; and a row that names seventy windows does not either: the tick states them in two packs, what closes first.
        IDS[4]: lambda: ([(st['key'], st['now'], st.get('label', 0), st.get('execute', 0), st['result']['refused']) for name in WALKS for st in W[name]['steps'] if st['kind'] == 'refused']
        == [('day_1', 1, 0, 0, BACK + '2'), ('day_0_once_more', 0, 0, 0, BACK + '1'), ('half_a_day', 2.5, 0, 0, NO_MOMENT), ('two_as_a_fraction', 2.0, 0, 0, NO_MOMENT), ('below_zero', -1, 0, 0, NO_MOMENT),
            ('true_for_a_moment', True, 0, 0, NO_MOMENT), ('text_for_a_moment', '3', 0, 0, NO_MOMENT), ('no_moment', None, 0, 0, NO_MOMENT), ('too_far', 10 ** 18, 0, 0, NO_MOMENT),
            ('a_label_with_the_mark', 3, 'day clock@1 ', 0, NO_LABEL), ('a_label_that_is_no_text', 3, 5, 0, NO_LABEL), ('execute_as_text', 3, 0, 'yes', NO_KERNEL), ('execute_as_a_number', 3, 0, 1, NO_KERNEL)]
        and same([st['now'] for st in W['refusals']['steps'][1:5]], [2.5, 2.0, -1, True])   # as JSON: 2.0 is not 2 and true is not 1
        and all(same(st['after'], W[name]['steps'][i - 1]['after']) for name in WALKS for i, st in enumerate(W[name]['steps']) if st['kind'] == 'refused')
        and said('refusals') == [('day_2', ['160_clock@2'])] + [(k, []) for k in keys('refusals')[1:-1]] + [('day_3', ['160_clock@3'])] and after('refusals', 'day_3')['moment'] == 3
        and said('order')[:3] == [('day_2', ['160_clock@2']), ('day_2_again', []), ('day_1', [])] and after('order', 'day_2_again')['loaded'] == after('order', 'day_2')['loaded']
        and said('same_moment') == [('day_2', ['168_clock@2']), ('day_2_again', []), ('day_2_new', ['168_clock@2.1']), ('day_2_once_more', [])]   # something new at a stated moment gets a pack with a name of its own
        and [e['predicate'] for e in res('same_moment', 'day_2_new')['clock_pack']['evidence']] == ['now', 'until:3', 'until:5', 'until:8']
        and same(step('order', 'now_by_hand')['row'], hand('now', 'TRUE', 9, at=9))
        and (res('order', 'now_by_hand')['status'], after('order', 'now_by_hand')['moment'], after('order', 'now_by_hand')['stored']['now']['source'], after('order', 'now_by_hand')['stored']['now']['at']) == ('DECISION_STANDS', 2, CLOCK, 2)
        and (after('pulls', 'day_0_pack_again')['moment'], after('pulls', 'day_0_pack_again')['stored']['now']['at']) == (1, 0)   # the earlier pack applied again: its `now` row is stored until the next tick, the moment does not go back
        and same([step('planted', k)['row'] for k in ('decision_on_now', 'decision_on_a_window')], [hand('now', 'TRUE', 99, final=True, at=99), hand(FAR, 'FALSE', 'closed', final=True)])
        and [res('planted', k)['status'] for k in ('decision_on_now', 'decision_on_a_window')] == ['RECONCILED', 'RECONCILED']
        and (after('planted', 'decision_on_now')['stored']['now']['source'], after('planted', 'decision_on_now')['stored']['now']['at'], after('planted', 'decision_on_a_window')['moment']) == ('fixture/written-by-hand', 99, 2)
        and (res('planted', 'day_4')['clock_pack']['id'], after('planted', 'day_4')['moment'], after('planted', 'day_4')['stored']['now']['source'], after('planted', 'day_4')['stored']['now']['at']) == ('169_clock@4', 4, CLOCK, 4)
        and (after('planted', 'day_4')['turned_away'], after('planted', 'day_4')['stored'][FAR]['source'], reads('planted', 'day_4', 'customer_approved'), briefs('planted', 'day_4')) == (1, 'fixture/written-by-hand', ['UNKNOWN'], [blocked])
        and said('planted') == [('day_2', ['169_clock@2']), ('day_4', ['169_clock@4']), ('day_4_again', []), ('day_5', ['169_clock@5'])]   # a row the kernel turns away is nothing new; a new moment is, whatever the rows say
        and same(step('planted', 'day_5_word_for_word')['row'], row('now', 'TRUE', 5, CLOCK, final=True, at=5, scope=Q)) and same(res('planted', 'day_5')['clock_pack']['evidence'][0], step('planted', 'day_5_word_for_word')['row'])
        and (res('planted', 'day_5_word_for_word')['status'], after('planted', 'day_5_word_for_word')['stored']['now']['at'], after('planted', 'day_5_word_for_word')['moment'], after('planted', 'day_5')['moment'], after('planted', 'day_5')['loaded'][-1]) == ('RECONCILED', 5, 4, 5, '169_clock@5')
        and same(step('crowd', 'seventy_windows')['row'], resting(row('fleet_ready', 'TRUE', '1', 'fixture/depot'), *range(5, 75))) and res('crowd', 'seventy_windows')['status'] == 'RECONCILED'
        and said('crowd') == [('day_2', ['169_crowd_clock@2']), ('day_4', ['169_crowd_clock@4', '169_crowd_clock@4.1']), ('day_6', ['169_crowd_clock@6', '169_crowd_clock@6.1'])]
        and crowd('day_4') == ['until:3', 'now'] + ['until:' + str(n) for n in range(5, 67)] and crowd('day_6') == ['until:3', 'until:5', 'now'] + ['until:' + str(n) for n in range(6, 67)]
        and [[e['predicate'] for e in res('crowd', k)['more_clock_packs'][0]['evidence']] for k in ('day_4', 'day_6')] == [['until:' + str(n) for n in range(67, 75)]] * 2
        and [reads('crowd', k, 'fleet_ready', 'until:5', 'until:74') for k in ('seventy_windows', 'day_4', 'day_6')] == [['UNKNOWN', 'TRUE', 'UNKNOWN'], ['TRUE', 'TRUE', 'TRUE'], ['UNKNOWN', 'FALSE', 'TRUE']]
        and (after('crowd', 'day_6')['moment'], after('crowd', 'day_6')['loaded'][-2:]) == (6, ['169_crowd_clock@6', '169_crowd_clock@6.1'])
        and same(read('169_shipping_pass')['grants'], ['box:5:action:ship-replacement@1'])   # the revoke goes with the first of the two packs
        and (res('crowd', 'day_4')['clock_pack'].get('revoke_grants'), res('crowd', 'day_6')['clock_pack'].get('revoke_grants'), 'revoke_grants' in res('crowd', 'day_6')['more_clock_packs'][0]) == (None, ['action:ship-replacement@1'], False)),
        # C6: inside its box the grant admits, on its last day too; a row written by hand that names a longer box changes no grant; past the
        # box the clock's pack takes the grant away and a run that still needs it asks for authority; what was done under it stands; of
        # two boxes the later one counts; given again with no fresh box the grant admits until the next tick, whose pack carries the
        # revoke alone; no clock pack ever gives a grant.
        IDS[5]: lambda: (same(read('162_loan')['grants'], [G, 'box:15:' + G]) and same(read('162_second_box'), {'schema': 'sutra-extension/2', 'id': '162_second_box', 'grants': ['box:20:' + G]})
        and same(read('162_sanction_again')['grants'], [G])
        and (briefs('loan', 'day_5'), after('loan', 'day_5')['grants'], 'revoke_grants' in res('loan', 'day_5')['clock_pack']) == ([(R, [LEND], [LEND], [])], [G, 'box:15:' + G], False)
        and same(step('loan', 'box_by_hand')['row'], hand('box:20:' + G, 'TRUE', '1')) and (res('loan', 'box_by_hand')['status'], after('loan', 'box_by_hand')['grants']) == ('RECONCILED', [G, 'box:15:' + G])
        and (briefs('loan', 'day_15'), res('loan', 'day_15')['clock_pack'].get('revoke_grants'), after('loan', 'day_15')['grants']) == ([(S, [], [], [])], None, [G, 'box:15:' + G])   # the last day of a box counts
        and (briefs('loan', 'day_16'), res('loan', 'day_16')['clock_pack'].get('revoke_grants'), after('loan', 'day_16')['grants'], reads('loan', 'day_16', 'loan_disbursed')) == ([(S, [], [], [])], [G], ['box:15:' + G], ['TRUE'])
        and (briefs('loan_late', 'day_16'), after('loan_late', 'day_16')['grants'], res('loan_late', 'day_16')['clock_pack'].get('revoke_grants')) == ([no_grant], ['box:15:' + G], [G])
        and by['69_permission_ran_out']['outcome']['stop_reasons'] == [A] and by['69_permission_ran_out']['outcome']['provenance'][-1]['pack'] == '162_clock@16'
        and [(k, briefs('two_boxes', k), res('two_boxes', k).get('clock_pack', {}).get('revoke_grants')) for k in keys('two_boxes') if step('two_boxes', k)['kind'] != 'pack']
        == [('day_16', [('PLAN_READY', [LEND], [], [])], None), ('day_20', [('PLAN_READY', [LEND], [], [])], None), ('day_21', [no_grant], [G]),
            ('admitted_until_the_next_tick', [('PLAN_READY', [LEND], [], [])], None), ('day_21_again', [no_grant], [G])]
        and (step('two_boxes', 'sanction_again')['pack'], said('two_boxes')[-1], G in after('two_boxes', 'sanction_again')['grants'], G in after('two_boxes', 'day_21_again')['grants']) == ('162_sanction_again', ('day_21_again', ['162_two_boxes_clock@21.1']), True, False)
        and not any('grants' in p for p in stated)),
        # C7: a tick reports late exactly the goals whose due row no longer reads TRUE and that do not hold as the look begins; the look
        # that completes a goal past its due-by says so, also when an earlier run of that look made it hold; a goal met in time is not
        # late while it holds and is late once what it was made on has lapsed; a due row that reads FALSE is not in time either; a goal
        # with no due row is never late; no run and no look made without a tick carries a word of it.
        IDS[6]: lambda: (same(read('164_due_by')['evidence'], [resting(row('in-time:order_complete', 'TRUE', 'due-by-1', 'fixture/owner-due-by'), 5)])
        and same(read('160_timed_approval')['evidence'][1], resting(row('in-time:order_complete', 'TRUE', '1', 'fixture/owner-due-by'), 5))
        and same(read('162_loan')['evidence'][1], resting(row('in-time:loan_disbursed', 'TRUE', '1', 'fixture/owner-due-by'), 7))
        and same(read('164_called_late')['evidence'], [row('in-time:order_complete', 'FALSE', '1', 'fixture/owner-due-by')])
        and same([[step('due', k)['execute'], runs('due', k)[0]['status'], runs('due', k)[0]['actions'], res('due', k)['time'], 'clock_pack' in res('due', k)] for k in keys('due')],
                 [[False, 'PLAN_READY', [SHIP], {'as_of': 6, 'late': ['order_complete']}, True], [True, R, [SHIP], {'as_of': 6, 'late': ['order_complete']}, False], [False, 'PLAN_READY', [], {'as_of': 7, 'late': []}, True]])
        and same(res('two_goals', 'day_6')['time'], {'as_of': 6, 'late': ['order_complete']}) and [(r['goal'], brief(r)) for r in runs('two_goals', 'day_6')] == [('replacement_delivered', (R, [SHIP], [SHIP], [])), ('order_complete', (S, [], [], []))]
        and same([res('order', k)['time'] for k in ('day_2', 'day_4', 'day_6')], [{'as_of': 2, 'late': []}, {'as_of': 4, 'late': []}, {'as_of': 6, 'late': ['order_complete']}])
        and same(res('late_order', 'day_6')['time'], {'as_of': 6, 'late': ['order_complete']})
        and same([res('loan', k)['time']['late'] for k in ('day_5', 'day_15', 'day_16', 'day_31', 'day_31_renewed')], [[], [], [], ['loan_disbursed'], ['loan_disbursed']])
        and reads('loan', 'day_16', 'in-time:loan_disbursed') == ['UNKNOWN']   # past its due-by and not late: the loan was disbursed in time and still holds
        and same(res('loan_late', 'day_16')['time'], {'as_of': 16, 'late': ['loan_disbursed']})
        and (same(res('called_late', 'day_1')['time'], {'as_of': 1, 'late': ['order_complete']}) and briefs('called_late', 'day_1') == [blocked] and reads('called_late', 'day_1', 'in-time:order_complete') == ['FALSE'])
        and same(res('allowance', 'day_1')['time'], {'as_of': 1, 'late': []})   # no due row: never late
        and not any('time' in st['result'] for name in WALKS for st in W[name]['steps'] if st['kind'] != 'tick')   # late is the tick's read: a look, an event or a pack reports none
        and not any('time' in r or 'late' in r or any('LATE' in e['operation'] for e in r['trace']) or not set(r['stop_reasons']) <= set(RANK) for name in WALKS for st in W[name]['steps'] for r in st['result'].get('runs', []))),
        # C10: the allowance is given by the State's first clock pack and at each new period, never at a second look, never inside a
        # period, not for a `now` row written by hand and not at the first tick in another scope; a larger allowance on the same
        # dimension sets the level, one for a dimension the budget does not have gives nothing, and one the clock's pack takes away
        # (its box has ended) gives nothing more; the clock's own earlier pack applied again sets its level again (a stated limit).
        IDS[7]: lambda: (same(read('161_allowance')['grants'], ['allowance:compute:2:1', 'allowance:money:2:1']) and 'allowance:pulls:2:1' in read('163_bureau_pulls')['grants']
        and same(read('163_weekly_pulls')['grants'][3:], ['allowance:pulls:1:7', 'box:13:allowance:pulls:1:7', 'allowance:pulls:0:7', 'allowance:energy:5:7']) and read('163_weekly_pulls')['budget']['pulls'] == 0
        and [[r['status'] for r in runs('pulls', k)] for k in ('day_0', 'day_0_again', 'day_1')] == [[R, R, X], [S, S, X], [S, S, R]]
        and same([res('pulls', k).get('clock_pack', {}).get('budget') for k in ('day_0', 'day_0_again', 'day_1')], [{'pulls': 2}, None, {'pulls': 2}])
        and same([after('pulls', k)['budget']['pulls'] for k in keys('pulls')], [0, 0, 1, 2, 2])
        and by['24_budget']['outcome']['status'] == X and brief(by['68_allowance']['outcome']) == (R, [SHIP], [SHIP], []) and by['68_allowance']['packs'][:-2] == by['24_budget']['packs']
        and same(res('allowance', 'day_1')['clock_pack'].get('budget'), {'compute': 2, 'money': 2}) and same(by['68_allowance']['derived_state']['budget_after'], {'compute': 0, 'money': 0, 'attention': 0})
        and same(after('allowance', 'day_1')['budget'], {'compute': 0, 'money': 0, 'attention': 0})
        and by['68_allowance']['outcome']['trace_root_sha256'] == by['04_gates']['outcome']['trace_root_sha256']
        and same(by['68_allowance']['derived_state']['facts'][Q + '|replacement_delivered'], {'predicate': 'replacement_delivered', 'truth': 'TRUE', 'verified': True, 'source': 'LOCAL_MODEL:' + SHIP, 'version': 'local-sim-1',
                 'evidence_kind': 'SIMULATED_LOCAL', 'depends_on': [{'predicate': 'substitute_stock', 'version': '1'}, {'predicate': 'customer_approved', 'version': 'approval-v1'}], 'scope': Q})
        and same(step('weekly', 'now_by_hand_says_day_0')['row'], hand('now', 'TRUE', 0, final=True, at=0)) and [step('weekly', k)['pack'] for k in ('to_the_branch', 'back_to_lending')] == ['163_branch', '163_lending']
        and same([[k, [r['status'] for r in runs('weekly', k)], res('weekly', k)['clock_pack'].get('budget'), res('weekly', k)['clock_pack'].get('revoke_grants'), after('weekly', k)['budget']['pulls']]
                  for k in keys('weekly') if step('weekly', k)['kind'] == 'tick'],
                 [['day_6', [R, X, X], {'pulls': 1}, None, 0], ['day_7', [S, R, X], {'pulls': 1}, None, 0], ['day_13', [S, S, X], None, None, 0], ['day_13_again', [S, S, X], None, None, 0],
                  ['day_13_in_the_branch', [X, X, X], None, None, 0], ['day_14', [S, S, X], {'pulls': 0}, ['allowance:pulls:1:7'], 0]])
        and (after('weekly', 'now_by_hand_says_day_0')['stored']['now']['at'], after('weekly', 'now_by_hand_says_day_0')['moment'], after('weekly', 'day_13_in_the_branch')['scope'], 'energy' in after('weekly', 'day_14')['budget']) == (0, 13, 'orgA/branch', False)),
        # C11: the kernel's file is the one added.json pinned before any version was added as files, and its text holds none of the
        # adapter's words in any letter case; the record holds no handler of the clock's; and every step of the time walks and cases
        # ran under the built-in kind `simulate_fact`.
        IDS[8]: lambda: (data['kernel_sha256'] == book['pinned']['kernel_sha256'] == hashlib.sha256(kernel).hexdigest()
        and not any(w in kernel.decode('utf-8').lower() for w in WORDS)
        and not any(h['file'] == 'extensions/clock.py' or h['module'] == 'extensions.clock' for h in data['action_handlers'].values())
        and len(kinds_run()) >= 12 and set(kinds_run()) == {'simulate_fact'}),
    }
    return {cid: holds(check) for cid, check in told.items()}


# ---- forgeries. Each gets a copy of the record `d`, a dict `f` in which it may put the text of a file of the lab (file -> text, None
# takes the file out), a reader of the lab's files as they are, and `remake`, which makes the walks, the time cases and the clock packs
# again from the files in `f` and a script (the default one when none is given) and puts them into `d` and `f`: a world made again.
def in_file(rel, edit):   # one JSON file of the lab with one thing changed, the record left as it is
    def change(d, f, text_of, remake):
        x = json.loads(text_of(rel))
        edit(x)
        f[rel] = json.dumps(x)
    return change


def again(rel=None, edit=None, steps=None):   # a world made again: a JSON file changed, or the steps of the script changed, and everything made again from it
    def change(d, f, text_of, remake):
        if rel:
            x = json.loads(text_of(rel))
            edit(x)
            f[rel] = json.dumps(x)
        script = fresh_script()
        if steps:
            steps({name: st for name, _, _, _, st in script})
        remake(script)
    return change


def fresh_script():   # the script as data of its own (a forgery changes its copy)
    return [(name, list(files), label, list(watch), fresh(steps)) for name, files, label, watch, steps in SCRIPT]


def other_kernel(words):   # a kernel with a word of time in it, pinned and recorded as if it were the lab's: only its text can tell
    def change(d, f, text_of, remake):
        src = text_of('kernel/core.py') + words
        h = hashlib.sha256(src.encode('utf-8')).hexdigest()
        book = json.loads(text_of('added.json'))
        book['pinned']['kernel_sha256'] = h
        f.update({'kernel/core.py': src, 'added.json': json.dumps(book)})
        d['kernel_sha256'] = h
        d['action_handlers']['simulate_fact'] = dict(d['action_handlers']['simulate_fact'], sha256=h)
    return change


step_of = lambda d, walk, key: [st for st in d['scenes']['clock']['walks'][walk]['steps'] if st['key'] == key][0]
res_of = lambda d, walk, key: step_of(d, walk, key)['result']
after_of = lambda d, walk, key: step_of(d, walk, key)['after']
case_at = lambda d, cid: [c for c in d['cases'] if c['id'] == cid][0]
keyed = lambda steps, key: [st for st in steps if st['key'] == key][0]


def moved(d, to, frm):   # the first run of one step put under another, with that step's own provenance: the same chain at another moment
    run = fresh(res_of(d, *frm)['runs'][0])
    run['provenance'] = fresh(res_of(d, *to)['runs'][0]['provenance'])
    res_of(d, *to)['runs'][0] = run


def traded(d, a, b):   # two runs trade their steps, each taking the other's provenance
    ra, rb = fresh(res_of(d, *a)['runs'][0]), fresh(res_of(d, *b)['runs'][0])
    ra['provenance'], rb['provenance'] = rb['provenance'], ra['provenance']
    res_of(d, *a)['runs'][0], res_of(d, *b)['runs'][0] = rb, ra


def swap(d, walk, a, b):   # two looks trade their reports
    res_of(d, walk, a)['time'], res_of(d, walk, b)['time'] = res_of(d, walk, b)['time'], res_of(d, walk, a)['time']


FORGERIES = [
    # S110: the record against what the books make. A change of the record alone is refused here, wherever it is made.
    ('S110', lambda d, f, t, m: moved(d, ('order', 'day_6'), ('same_moment', 'day_2'))),                # the review's swap (a): the dry look of day 2, which plans on the approval, put under the tick of day 6 with day 6's provenance
    ('S110', lambda d, f, t, m: traded(d, ('order', 'day_6'), ('same_moment', 'day_2'))),               # (b): two run records trade their moments
    ('S110', lambda d, f, t, m: moved(d, ('two_scopes', 'day_6'), ('loan_late', 'day_16'))),            # (c): a run that asks for authority put inside the box
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_4').update(runs=res_of(d, 'order', 'day_6')['runs'])),   # the run of day 6 put under the tick of day 4 as it is: the same chain, the provenance of another moment
    ('S110', lambda d, f, t, m: step_of(d, 'order', 'day_4')['after'].update(books='0' * 64)),          # the digest of the books after a step
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_2')['runs'][0].update(needs=['x'])),            # a field of a run that its trace does not carry
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_2')['runs'][0].update(note='x')),               # a key added to a run
    ('S110', lambda d, f, t, m: res_of(d, 'loan', 'day_5')['runs'][0]['trace'][3]['data'].update(cost={'compute': 0, 'money': 0, 'attention': 0})),   # a gate row's own fields
    ('S110', lambda d, f, t, m: step_of(d, 'due', 'day_6_dry').update(execute=True)),                   # a dry look recorded as executed
    ('S110', lambda d, f, t, m: step_of(d, 'withdrawn', 'day_2').update(execute=True)),
    ('S110', lambda d, f, t, m: res_of(d, 'planted', 'decision_on_now').update(affected=['order_complete'])),   # an event said to touch a goal that no run looked at
    ('S110', lambda d, f, t, m: d['scenes']['clock']['walks']['two_scopes']['steps'].append(fresh(d['scenes']['clock']['walks']['two_scopes']['steps'][-1]))),   # a step that stands twice
    ('S110', lambda d, f, t, m: res_of(d, 'withdrawn', 'late_approval')['runs'].append(fresh(res_of(d, 'withdrawn', 'late_approval')['runs'][0]))),              # a run that stands twice
    ('S110', lambda d, f, t, m: d['scenes']['clock']['walks']['offer']['steps'].pop(0)),                # a step taken out
    ('S110', lambda d, f, t, m: d['scenes']['clock'].update(note='x')),
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_4')['clock_pack']['evidence'][1].pop('final')),
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_4')['clock_pack']['evidence'][0].update(scope='orgB/other')),   # a row stated into another scope
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_4')['clock_pack'].update(id='clock@4')),        # a name without the walk's label
    ('S110', lambda d, f, t, m: res_of(d, 'order', 'day_4')['clock_pack']['evidence'].append({'predicate': 'customer_approved', 'truth': 'TRUE', 'verified': True, 'source': CLOCK, 'version': 'approval-v1', 'scope': Q})),   # another source's row stated again
    ('S110', lambda d, f, t, m: res_of(d, 'two_scopes', 'day_6')['clock_pack']['evidence'].pop()),      # a window of the scope the State left, left open
    ('S110', lambda d, f, t, m: res_of(d, 'pulls', 'day_1')['clock_pack']['budget'].update(compute=10)),   # a dimension with no allowance filled up
    ('S110', lambda d, f, t, m: res_of(d, 'crowd', 'day_4')['more_clock_packs'][0]['evidence'].pop()),  # a window of the crowd left unstated
    ('S110', lambda d, f, t, m: res_of(d, 'crowd', 'day_4')['clock_pack']['evidence'].reverse()),       # what closes not stated first
    ('S110', lambda d, f, t, m: case_at(d, '67_late_order').update(scope='x')),                        # the time cases, field by field: what the base's checks do not read
    ('S110', lambda d, f, t, m: case_at(d, '67_late_order')['run'].update(goals=[])),
    ('S110', lambda d, f, t, m: case_at(d, '67_late_order')['derived_state'].update(rule_ids=['x'])),
    ('S110', lambda d, f, t, m: case_at(d, '67_late_order')['four_views']['world'][0].update(truth='TRUE')),
    ('S110', lambda d, f, t, m: case_at(d, '67a_order_in_time')['four_views']['knowledge'][0].update(approved=False)),
    ('S110', lambda d, f, t, m: case_at(d, '69_permission_ran_out').update(title='x')),
    ('S110', lambda d, f, t, m: case_at(d, '68_allowance')['derived_state']['facts'][Q + '|replacement_delivered'].update(version='x')),   # the stored row of the step that ran
    ('S110', lambda d, f, t, m: case_at(d, '69_permission_ran_out')['outcome'].update(goal_truth_before='TRUE')),
    ('S110', in_file('scenarios/160_clock@4.json', lambda x: x['evidence'][1].update(truth='TRUE', version='window'))),   # the scenario file of a clock pack changed: the tick's pack is no longer the file's
    ('S110', in_file('scenarios/160_timed_approval.json', lambda x: x['evidence'].append({'predicate': 'until:9', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/written-by-hand', 'version': 'window'}))),   # a pack that is not the clock's carrying a window row
    ('S110', in_file('scenarios/04_admission.json', lambda x: x.update(evidence=[{'predicate': 'now', 'truth': 'TRUE', 'verified': True, 'final': True, 'source': 'fixture/written-by-hand', 'version': 9, 'at': 9}]))),   # any scenario file of the lab, not only this version's
    ('S110', lambda d, f, t, m: f.update({'scenarios/170_clock@3.json': json.dumps({'schema': 'sutra-extension/2', 'id': '170_clock@3', 'evidence': [], 'grants': [G]})})),   # a later pack named like the clock's that gives a grant
    ('S110', lambda d, f, t, m: f.update({'scenarios/160_clock@9.json': t('scenarios/160_clock@6.json').replace('160_clock@6', '160_clock@9')})),   # a clock pack among this version's files that no tick stated
    # S111: the moment of a run
    ('S111', again('cases/67_late_order.json', lambda x: x.update(packs=x['packs'][:-1] + ['160_clock@4']))),                     # the late order's case on the clock pack of another day: the same run, another moment
    ('S111', again(steps=lambda s: keyed(s['two_scopes'], 'day_3').update(now=4))),                                               # the second of the two looks made past the window: not the same look any more
    ('S111', lambda d, f, t, m: res_of(d, 'late_order', 'day_6')['time'].update(as_of=2)),                                         # a report that says another moment than the run's own provenance
    ('S111', lambda d, f, t, m: [r['provenance'].pop() for r in res_of(d, 'late_order', 'day_6')['runs']]),                        # the clock pack dropped from a run's provenance
    ('S111', lambda d, f, t, m: case_at(d, '69_permission_ran_out')['outcome'].update(status='PLAN_READY')),
    # S112: a timed fact
    ('S112', again(steps=lambda s: keyed(s['order'], 'late_approval').update(row=resting(row('customer_approved', 'TRUE', 'approval-v2', 'fixture/customer-approval'), 9)))),   # the approval that arrives late said to count until day 9
    ('S112', again('scenarios/168_stock_hold.json', lambda x: x['evidence'][0]['depends_on'][0].update(predicate='until:5'))),     # the hold on a window the clock had published already: believed on arrival
    ('S112', again('scenarios/160_timed_approval.json', lambda x: x['evidence'][0]['depends_on'][0].update(predicate='until:9'))),   # the approval's pack said to count until day 9
    ('S112', lambda d, f, t, m: after_of(d, 'order', 'day_4')['reads'].update(replacement_delivered='TRUE')),                      # what was shipped on the lapsed approval still believed
    ('S112', lambda d, f, t, m: after_of(d, 'order', 'late_approval')['reads'].update(customer_approved='TRUE')),                  # the approval that arrived late believed
    ('S112', lambda d, f, t, m: after_of(d, 'two_scopes', 'back_to_the_order')['reads'].update(customer_approved='TRUE')),         # the approval believed again in the scope the State came back to
    # S113: a closed window
    ('S113', again('scenarios/167_offer.json', lambda x: x['rules'][0].update(branches=[['offer_approved', 'until:4']]))),         # the rule on the step's window: it would hold a day longer
    ('S113', again(steps=lambda s: keyed(s['order'], 'reopen')['row'].update(truth='FALSE', version='closed'))),                   # the row that 'reopens' says the window is closed: it shows nothing
    ('S113', again('scenarios/167_offer.json', lambda x: x['methods'].pop())),                                                     # the offer's pack without the step whose effect is the window
    ('S113', lambda d, f, t, m: res_of(d, 'order', 'reopen').update(status='RECONCILED')),
    ('S113', lambda d, f, t, m: after_of(d, 'order', 'day_2_pack_again')['reads'].update({'until:3': 'TRUE'})),
    ('S113', lambda d, f, t, m: res_of(d, 'offer', 'day_5')['runs'][0].update(stop_reasons=['QUERY_EVIDENCE'])),
    # S114: the moment and the clock
    ('S114', again(steps=lambda s: keyed(s['order'], 'day_1').update(now=2))),                                                     # the tick 'back' made at the same moment: it is no refusal
    ('S114', again(steps=lambda s: keyed(s['order'], 'now_by_hand')['row'].update(at=2, version=2))),                              # the `now` row by hand names the moment itself: it shows nothing
    ('S114', again(steps=lambda s: keyed(s['refusals'], 'half_a_day').update(now=3))),                                             # the tick that must be refused for its moment made at a whole one
    ('S114', again(steps=lambda s: keyed(s['crowd'], 'seventy_windows').update(row=resting(row('fleet_ready', 'TRUE', '1', 'fixture/depot'), *range(5, 65))))),   # sixty windows: they fit one pack, nothing is cut
    ('S114', lambda d, f, t, m: res_of(d, 'order', 'day_1').update(refused='x')),                                                  # a refusal in other words
    ('S114', lambda d, f, t, m: step_of(d, 'order', 'day_1').update(now=None)),
    ('S114', lambda d, f, t, m: after_of(d, 'order', 'day_1').update(books='0' * 64)),                                             # a refused tick that changed the books
    ('S114', lambda d, f, t, m: after_of(d, 'order', 'now_by_hand').update(moment=9)),                                             # a row written by hand said to move the moment
    ('S114', lambda d, f, t, m: after_of(d, 'planted', 'day_4').update(moment=2)),                                                 # the clock said to have stopped
    # S115: a time-boxed grant
    ('S115', again('scenarios/162_second_box.json', lambda x: x.update(grants=['box:16:' + G]))),                                  # the second box said to end on day 16
    ('S115', again('scenarios/162_sanction_again.json', lambda x: x.update(grants=[G, 'box:45:' + G]))),                           # the grant given again with a fresh box: the next tick has nothing to take away
    ('S115', lambda d, f, t, m: after_of(d, 'loan', 'day_16')['grants'].append(G)),
    ('S115', lambda d, f, t, m: after_of(d, 'loan', 'day_16')['reads'].update(loan_disbursed='UNKNOWN')),                          # what was done under the grant said to lapse with it
    ('S115', lambda d, f, t, m: after_of(d, 'loan', 'box_by_hand')['grants'].append('box:20:' + G)),                               # a row written by hand said to have given a box
    ('S115', lambda d, f, t, m: res_of(d, 'loan', 'day_15')['clock_pack'].update(revoke_grants=[G])),                              # a grant taken away on the last day of its box
    # S116: late
    ('S116', again('scenarios/164_due_by.json', lambda x: x['evidence'][0]['depends_on'][0].update(predicate='until:9'))),         # the due-by's pack said to run until day 9
    ('S116', again('scenarios/164_called_late.json', lambda x: x['evidence'][0].update(truth='TRUE'))),                            # the due row its owner states as passed, said to be in time
    ('S116', again('scenarios/164_due_by.json', lambda x: x['evidence'][0].update(source='fixture/reviewed'))),                    # a due row from another source than the pack file names
    ('S116', lambda d, f, t, m: swap(d, 'order', 'day_2', 'day_6')),                                                               # two looks trade their reports
    ('S116', lambda d, f, t, m: res_of(d, 'due', 'day_6')['time'].update(late=[])),                                                # the look that ships it late, reported in time
    ('S116', lambda d, f, t, m: res_of(d, 'two_goals', 'day_6')['time'].update(late=[])),                                          # the order that an earlier run of the look completed, reported in time
    ('S116', lambda d, f, t, m: res_of(d, 'loan', 'day_16')['time'].update(late=['loan_disbursed'])),
    ('S116', lambda d, f, t, m: res_of(d, 'two_scopes', 'after').update(time={'as_of': 6, 'late': []})),                           # a look made without a tick that claims a report
    # S117: an allowance
    ('S117', again('scenarios/163_weekly_pulls.json', lambda x: x['grants'].remove('box:13:allowance:pulls:1:7'))),                # the weekly allowance without its box: it comes back on day 14
    ('S117', again('scenarios/161_allowance.json', lambda x: x.update(grants=['allowance:compute:3:1', 'allowance:money:3:1']))),   # the allowance's pack said to give three a day
    ('S117', again('scenarios/163_weekly_pulls.json', lambda x: x['grants'].remove('allowance:energy:5:7'))),
    ('S117', lambda d, f, t, m: after_of(d, 'pulls', 'day_0')['budget'].update(pulls=2)),
    ('S117', lambda d, f, t, m: res_of(d, 'weekly', 'day_13')['clock_pack'].update(budget={'pulls': 1})),                          # an allowance given inside its period
    ('S117', lambda d, f, t, m: case_at(d, '68_allowance')['derived_state']['budget_after'].update(compute=2)),
    # S118: the kernel and the kinds
    ('S118', other_kernel('# the moment\n')),
    ('S118', other_kernel('# TICK: the Clock reads the Deadline, Moment by Moment\n')),                                            # the adapter's words in capitals
    ('S118', lambda d, f, t, m: d.update(kernel_sha256='0' * 64)),
    ('S118', in_file('added.json', lambda x: x['pinned'].update(kernel_sha256='0' * 64))),
    ('S118', lambda d, f, t, m: d['action_handlers'].update(clock=dict(d['action_handlers']['ask'], module='extensions.clock', file='extensions/clock.py'))),   # the clock recorded as an action kind
]


def refusers(data, ROOT, sha, check_chain, change, base=None):
    """The checks that refuse one forgery: the ids of S110 to S118 that do not hold on a copy of the record with one thing changed (the parts
    the checks read are copied, the rest is shared). None when the forgery could not be made; all nine when the forged record cannot be read."""
    try:
        d = dict(data, cases=[fresh(c) if c['id'] in USED else c for c in data['cases']], scenes=dict(data['scenes'], clock=fresh(data['scenes']['clock'])), action_handlers=dict(data['action_handlers']))
        f, state = {}, {}

        def remake(script):   # the walks, the time cases and the clock packs made again from the files in `f` and this script
            for _ in (1, 2):   # a second time when a walk or a case loaded a clock pack as a file and the ticks now state another pack under that name
                made = world(ROOT, sha, f, script)
                old = {'scenarios/' + n + '.json' for n in made['names']('scenarios') if re.match(r'16[0-9]_', n) and named(n) is not None}
                f.update({rel: None for rel in old})
                f.update({'scenarios/' + p['id'] + '.json': json.dumps(p) for p in made['stated']})
                if not any(p['id'] in made['files'] and text(made['files'][p['id']]) != text(p) for p in made['stated']):
                    break
            d['scenes']['clock'] = {'walks': made['walks']}
            d['cases'] = [made['cases'].get(c['id'], c) for c in d['cases']]
            state.update(script=script, made=made)

        change(d, f, lambda rel: (ROOT / rel).read_bytes().decode('utf-8'), remake)
    except Exception:
        return None
    try:
        got = claims(d, ROOT, sha, check_chain, f, state.get('script'), state.get('made') or (base if not f else None))
    except Exception:
        return list(CLAIMS)
    return [cid for cid in CLAIMS if got.get(cid) is not True]


def survey(data, ROOT, sha, check_chain):
    """What S110 to S118 say on the record ({id: holds}), and for each forgery in turn the checks that refuse it (None in place of the
    list when the nine do not all hold: the forgeries show that checks which hold are live, so on such a record there is nothing to show)."""
    base = world(ROOT, sha)
    told = claims(data, ROOT, sha, check_chain, made=base)
    return told, [refusers(data, ROOT, sha, check_chain, change, base) for _, change in FORGERIES] if all(told.values()) else None


def verdict(told, seen):
    """The ten rows of a survey. S119 holds when every forgery was refused by the check it is listed for and each of the nine refused one alone."""
    rows = [(cid, told.get(cid) is True, '') for cid in CLAIMS]
    if seen is None:
        return rows + [(IDS[9], False, 'S110 to S118 do not all hold on this record, so the forgeries were not run')]
    number = lambda cid: cid.split('_')[0]
    wrong = {i: None if by is None else [number(c) for c in by] for i, ((target, _), by) in enumerate(zip(FORGERIES, seen)) if by is None or target not in [number(c) for c in by]}   # not made, accepted, or refused by other checks only
    alone = {number(by[0]) for by in seen if by is not None and len(by) == 1}
    bare = sorted({number(cid) for cid in CLAIMS} - alone)   # a check without a forgery that it alone refuses
    live = not wrong and not bare
    return rows + [(IDS[9], live, '' if live else str({'not refused by its own check': wrong, 'checks without a forgery of their own': bare})[:1500])]


def checks(data, ROOT, sha, check_chain):
    try:
        return verdict(*survey(data, ROOT, sha, check_chain))
    except Exception as e:
        return [(cid, False, 'the time record or a file it rests on cannot be read: ' + type(e).__name__) for cid in IDS]
