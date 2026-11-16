"""The learn feature's reading of checks, of several records at once and of who settled a fact (0.20.0-learn; made under
ruling R35 of the program: one new part, where the parts the lab had could not say it).

The reader (extensions/reader.py) and the Learner (extensions/reflection.py) read runs: what ran, what stopped, what was
asked and answered, one record at a time. This module reads what they pass over: the rows the State was handed, by the
journal's event door and in the evidence of packs, with the words they carry, the packs that say who settles a fact, and
several records side by side. Like the reader it is a function of the kept text and its head. It imports the record
adapter (extensions/journal_record.py) and nothing else of the lab: no kernel, no State, not the journal's writer, not the
reader. It keeps nothing between two calls and changes nothing. What it reads is as true as the journals it was given: it
does not replay.

  records   a list of records, each a list of one or more (text, head) as the record adapter takes it: one journal, or a
            chain. A record is named by its first journal (the first 12 characters of that journal's header hash). A journal
            that stands in two records of the list is refused: every record is counted once. (One that stands twice in one
            record is refused by the record adapter: a journal does not continue itself.) Two journals with one header (the
            same kinds, checkers and name, and no journal before) have one name, so they are one journal here and are
            refused too: the sessions of a desk need a name each.
  least     how many times make a repeat, and in how many records a thing must stand to be one thing: a whole number,
            2 or more. The number is the caller's; this module holds none of its own.
  scope     a row is read in its own scope, else in the State's: the scope the last pack of the record named, else the
            scope a new State starts in (FIRST_SCOPE, the kernel's). Only a pack moves the State's scope, and a journal
            that continues another starts from that State, so every run of the record is run in that scope too.
  a row     a row the State was handed, with what came of it (`door`): RECONCILED, the event door took it in the State's
            scope; OUT_OF_SCOPE, the event door kept it for the scope it names, which is not the State's, and ran nothing on
            it; PACK, a row of a pack's evidence, kept; DECISION_STANDS, turned away, at the event door or in a pack, because
            a decision stands on its fact in its scope. A decision stands from a row of a pack that is one (`final`) or an
            answer to a question (the stamp is one); only another decision replaces it. A row of a pack that is not verified
            is not kept and is not read; an answer is read as an answer, not as a row.
  the plan  the methods the State held when the row came: the methods of the packs handed in before it, in the same record. A
            pack's own methods are not before its own rows: the State takes a pack's evidence before its methods. A fact is
            GIVEN to someone by every method of the plan that makes it: an ask gives it to the party its question is put to
            (`ask_to`), a hand-over to the checker it names (`verified_by`), a step of any other kind to that step, whose
            receipt makes it (no row the State is handed is a step's).
  out       a try of a hand-over is out, as the hand-over kind keeps it in its books, from the run whose receipt handed it
            over until a new try of its fact goes out or a HANDOFF_CLOSED line of the kind names its receipt: read from
            the receipts and the kind's own lines in the record. A check, failed or passed, does not end it: the kind
            reads the last row on the fact, so a later row of the checker on that receipt is a check too.
  a check   a row the State keeps (RECONCILED, OUT_OF_SCOPE or PACK) on the fact of a try that is out, in that try's scope,
            that names the try's receipt under `checks`, comes from the checker the try names, reads TRUE or FALSE and is
            no decision: the row the hand-over kind reads as the check of that try (kinds/handoff.py, `_said`) whenever
            it looks at the fact, until another row on the fact replaces it. What a try's check said is its last check row.
  as written  a check is read from the row as the State was handed it, not from what the State reads of it: a row whose
            `depends_on` no longer holds reads UNKNOWN in the State and is still read here as it says.
  words     a row's `why` when it is one text, else null. Words are quoted and compared whole, never judged.

What it proposes, each a plain dict {kind, record, ..., support, at, status} (one thing of several records carries `records`
and `record_ids` in place of `record`): `at` cites every row it rests on by journal, entry number and entry hash (a row of
a pack also by its place in the pack's evidence, `evidence`, from 0; a run by its run id), `support` is how many that is,
`status` is always PROPOSED_ONLY.

  CHECK_FAILED, CHECK_PASSED   one for every check row, FALSE or TRUE. It carries the fact, the checker, the step and the
                     try it checked, the hand, the receipt and the checker's words.
  CHECK_FAILED_AGAIN   in one record, the check rows of one fact of one scope by one checker read FALSE `least` times or more: every
                     one, each with its words; `same_words` is true when every one carries words that are one text and
                     all are the same text, else false. It counts rows: a row handed in twice is two.
  HANDED_OUT_AGAIN   in one record, the work on one fact of one scope was handed over `least` times or more, counted by fact,
                     whatever step handed it over: each hand-over with the try number its receipt carries, its step,
                     its hand, its receipt and what its last check row said (null where none came).
  BLOCKED_AGAIN      in one record, `least` or more runs of one goal of one scope in a row were blocked with the same status word,
                     with no other run of that goal between them; a run of the goal that is not blocked, or blocked for
                     another reason, ends the row, and the latter starts the next.
  STATED_BY_ANOTHER  a row on a fact the plan gives to someone, from a source the plan does not give it to: no
                     asked party and no checker the plan names for that fact.
  STATED_WITHOUT_A_CHECK   a row on a fact a hand-over of the plan gives to its checker, from a checker the plan gives it
                     to, that is no check row: no try was out (`out` is null), or the try that is out is not one it checks:
                     it names another receipt or none, it comes from another checker than that try names, a decision
                     turned it away, or it is a decision itself (`out` names that try's receipt, `names` what the row
                     names). A row of the try's own checker that reads UNKNOWN on that try's receipt is not read. `last_check`
                     is the last check row on the fact before it, or null: a row that states a confirmed fact again shows as one.
  IN_SEVERAL_RECORDS   one thing seen in `least` records or more, counted by record (`records`) and named by every row:
                     a blocked run (by its status word), a stopped step (by step and reason), a failed check (by fact,
                     checker and words, when its words are one text), an answer (by party, question and truth), a pack (by its sha256), a try that
                     handed work out again (by fact), a row stated by another source (by fact, whom the plan gives it
                     to and the source), a row its checker stated without a check (by fact and checker). `records` is how many
                     records, `record_ids` names them.

Per record, in the order the records are given: the check rows and the stated rows in the order the State was handed them
(entry by entry, the rows of a pack in their order), then the repeats in the order of their first row: journal of the
chain, then entry. Then the things of several records, in the order they were first seen. The same records and number give
the same list. A record that is not a list of one or more (text, head) is refused in this module's words (NO_RECORD); one
the adapter refuses, in its words; one that is whole and still does not hold what is read from it, in this module's words
(NOT_READ): a ValueError each time. No record at all is no refusal."""
from __future__ import annotations
import hashlib, json
from extensions import journal_record as R

KINDS = ('CHECK_FAILED', 'CHECK_PASSED', 'CHECK_FAILED_AGAIN', 'HANDED_OUT_AGAIN', 'BLOCKED_AGAIN', 'STATED_BY_ANOTHER',
         'STATED_WITHOUT_A_CHECK', 'IN_SEVERAL_RECORDS')
KEPT = ('RECONCILED', 'OUT_OF_SCOPE', 'PACK')   # what came of a row the State keeps: the kind reads it when it looks at its fact
DOORS = KEPT + ('DECISION_STANDS',)            # every row that is read: kept, or turned away because a decision stands
FIRST_SCOPE = 'orgA/fulfillment'   # the scope a new State starts in (kernel/core.py, State.scope); a unit test holds the two equal
NOT_READ = 'A record does not hold what the learn feature reads from it'
NO_RECORD = 'A record is a list of one or more (text, head)'
TWICE = 'A journal stands in two records: every record is counted once'


def _sha(v) -> str:
    """The sha256 of a value as canonical JSON (the record adapter's form: sorted keys, no spaces, characters as they are)."""
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _proposal(kind: str, record: str, fields: dict, at: list) -> dict:
    return dict({'kind': kind, 'record': record}, **fields, support=len(at), at=at, status='PROPOSED_ONLY')


def _given(methods: dict, fact: str) -> list:
    """Whom the plan gives a fact to: [[how, party, step]] in the order of the methods; how is `asked` (the party is the
    ask's `ask_to`), `checker` (the hand-over's `verified_by`) or `step` (the party is the step itself)."""
    out = []
    for m in methods.values():
        if m['effect'] == fact:
            how = {'ask': 'asked', 'handoff': 'checker'}.get(m.get('action'), 'step')
            out.append([how, m['ask_to'] if how == 'asked' else m['verified_by'] if how == 'checker' else m['id'], m['id']])
    return out


def _one(kept: list, least: int):
    """One record read in entry order: what it proposes alone, and its things for the reading across records."""
    records = R.record(kept)
    record, order = records[0]['journal'], {j['journal']: n for n, j in enumerate(records)}
    methods, scope, decided = {}, FIRST_SCOPE, set()   # the plan; the State's scope (what the last pack named); (scope, fact) where a decision stands
    issued, out, last_check = {}, {}, {}   # receipt -> the try; (scope, fact) -> the receipt out; (scope, fact) -> the last check row
    failed, tries, runs = {}, {}, {}       # (scope, fact, checker) -> failed checks; (scope, fact) -> receipts; (scope, goal) -> runs
    found, things = [], []                 # proposals in entry order; (key, what, citation) for the reading across records

    def read(row, door, at):
        """One row the State was handed, with what came of it."""
        key, source, words = (row.get('scope', scope), row['predicate']), row['source'], row['why'] if type(row.get('why')) is str else None
        tried = issued.get(out.get(key))
        mine = tried is not None and row.get('checks') == out[key] and source == tried['checker']   # names the try out, from its checker
        if mine and door in KEPT and not row.get('final') and row['truth'] in ('TRUE', 'FALSE'):
            item = _proposal('CHECK_PASSED' if row['truth'] == 'TRUE' else 'CHECK_FAILED', record,
                             {'scope': key[0], 'fact': key[1], 'checker': source, 'step': tried['step'], 'try': tried['try'], 'to': tried['to'],
                              'receipt': out[key], 'words': words}, [at])
            found.append(item)
            tried['checked'] = {'truth': row['truth'], 'words': words, 'at': at}   # the kind reads the last row: a later check of this try replaces it
            last_check[key] = {'truth': row['truth'], 'at': at}   # the try stays out: only a new try or the kind's HANDOFF_CLOSED ends it
            if row['truth'] == 'FALSE':
                failed.setdefault((key[0], key[1], source), []).append(item)
                if type(words) is str:   # words that are not one text say no reason that two records could share
                    things.append((('check_failed', key[1], source, words), {'what': 'check_failed', 'fact': key[1], 'checker': source, 'words': words}, at))
            return
        given = _given(methods, key[1])
        if given and source not in [g[1] for g in given if g[0] != 'step']:
            found.append(_proposal('STATED_BY_ANOTHER', record, {'scope': key[0], 'fact': key[1], 'given': given, 'source': source,
                                                                 'truth': row['truth'], 'door': door, 'words': words}, [at]))
            things.append((('stated_by_another', key[1], json.dumps(given), source),
                           {'what': 'stated_by_another', 'fact': key[1], 'given': given, 'source': source}, at))
        elif source in [g[1] for g in given if g[0] == 'checker'] and not (mine and row['truth'] == 'UNKNOWN'):
            found.append(_proposal('STATED_WITHOUT_A_CHECK', record, {'scope': key[0], 'fact': key[1], 'checker': source, 'truth': row['truth'],
                                                                       'door': door, 'names': row.get('checks'), 'out': out.get(key),
                                                                       'last_check': last_check.get(key), 'words': words}, [at]))
            things.append((('stated_without_a_check', key[1], source),
                           {'what': 'stated_without_a_check', 'fact': key[1], 'checker': source}, at))

    for j in records:
        for e in j['entries']:
            at = {'journal': j['journal'], 'entry': e['seq'], 'sha256': e['sha256']}
            body, result = e['body'], e['result']
            if e['kind'] == 'pack':   # as the State takes a pack: its scope, then its evidence row by row, then its methods
                pack = body['pack']
                scope = pack['scope'] if type(pack.get('scope')) is str else scope
                for i, row in enumerate(pack.get('evidence', [])):
                    if row.get('verified') is True:   # a row that is not verified the State does not keep
                        key = (row.get('scope', scope), row['predicate'])
                        door = 'DECISION_STANDS' if key in decided and not row.get('final') else 'PACK'
                        if door == 'PACK' and row.get('final'):
                            decided.add(key)
                        read(row, door, dict(at, evidence=i))
                for m in pack.get('methods', []):
                    methods.setdefault(m['id'], m)
                sha = _sha(pack)
                things.append((('pack', sha), {'what': 'pack', 'pack': pack.get('id'), 'pack_sha256': sha}, at))
            elif e['kind'] == 'event' and result['status'] in DOORS:
                read(body['row'], result['status'], at)
            elif e['kind'] == 'answer':
                ask = body['receipt']['ask']
                decided.add((body['receipt']['scope'], ask['predicate']))   # the stamp is a decision on the fact, in the scope it was asked in
                things.append((('answer', ask['to'], ask['question'], body['truth']),
                               {'what': 'answer', 'to': ask['to'], 'question': ask['question'], 'truth': body['truth']}, at))
            for i, b in enumerate(result.get('briefs', [])):
                run = dict(at, run=f"{j['journal']}:{e['seq']}.{i}")
                runs.setdefault((b['scope'], b['goal']), []).append((b, run))
                if b['work_state'] == 'blocked':
                    things.append((('blocked', b['status']), {'what': 'blocked', 'reason': b['status']}, run))
                if 'stopped' in b:
                    things.append((('stopped', b['stopped']['method'], b['stopped']['reason']),
                                   {'what': 'stopped', 'step': b['stopped']['method'], 'reason': b['stopped']['reason']}, run))
                for x in b['receipts']:
                    h = x.get('handoff')
                    if type(h) is dict:
                        key = (x['scope'], h['predicate'])
                        issued[x['sha256']] = {'step': x['method'], 'to': h['to'], 'checker': h['verified_by'], 'try': h['try'], 'at': run, 'checked': None}
                        out[key] = x['sha256']
                        tries.setdefault(key, []).append(x['sha256'])
                        if len(tries[key]) > 1:
                            things.append((('handed_out_again', key[1]), {'what': 'handed_out_again', 'fact': key[1]}, run))
                for line in b.get('settled', []):
                    if line['operation'] == 'HANDOFF_CLOSED':
                        key = next((k for k, receipt in out.items() if receipt == line['data']['receipt']), None)
                        if key is not None:
                            del out[key]
    repeats = []
    for (sc, fact, checker), items in failed.items():
        if len(items) >= least:
            said = [i['words'] for i in items]
            repeats.append((items[0]['at'][0], _proposal('CHECK_FAILED_AGAIN', record, {
                'scope': sc, 'fact': fact, 'checker': checker, 'times': len(items), 'words': said,
                'same_words': all(type(w) is str for w in said) and len(set(said)) == 1},
                [i['at'][0] for i in items])))
    for (sc, fact), receipts in tries.items():
        if len(receipts) >= least:
            each = [{'try': issued[r]['try'], 'step': issued[r]['step'], 'to': issued[r]['to'], 'receipt': r, 'checked': issued[r]['checked']} for r in receipts]
            repeats.append((issued[receipts[0]]['at'], _proposal('HANDED_OUT_AGAIN', record, {
                'scope': sc, 'fact': fact, 'times': len(receipts), 'tries': each}, [issued[r]['at'] for r in receipts])))
    for (sc, goal), seen in runs.items():
        stretch = []
        for b, run in seen + [(None, None)]:
            if b is not None and b['work_state'] == 'blocked' and (not stretch or stretch[0][0]['status'] == b['status']):
                stretch.append((b, run))
                continue
            if len(stretch) >= least:
                repeats.append((stretch[0][1], _proposal('BLOCKED_AGAIN', record, {
                    'scope': sc, 'goal': goal, 'reason': stretch[0][0]['status'], 'times': len(stretch)}, [r for _, r in stretch])))
            stretch = [(b, run)] if b is not None and b['work_state'] == 'blocked' else []
    found += [p for _, p in sorted(repeats, key=lambda x: (order[x[0]['journal']], x[0]['entry']))]   # by the first row: journal of the chain, then entry
    return record, [j['journal'] for j in records], found, things


def proposals(records: list, least: int) -> list:
    """What the records say together: every record's own proposals, in the order the records are given, then the things
    that stand in `least` records or more. The same records and number give the same list."""
    if type(least) is not int or least < 2:
        raise ValueError('A repeat is two times or more: `least` is a whole number, 2 or more')
    if type(records) is not list:
        raise ValueError('The learn feature reads a list of records')
    if any(type(kept) is not list or not kept or any(type(p) not in (list, tuple) or len(p) != 2 for p in kept) for kept in records):
        raise ValueError(NO_RECORD)
    out, groups, seen = [], {}, set()
    for kept in records:
        try:
            record, journals, found, things = _one(kept, least)
        except (KeyError, TypeError, AttributeError):
            raise ValueError(NOT_READ) from None
        if seen & set(journals):
            raise ValueError(TWICE)
        seen |= set(journals)
        out += found
        for key, what, at in things:
            g = groups.setdefault(json.dumps(key), {'what': what, 'records': [], 'at': []})
            if record not in g['records']:
                g['records'].append(record)
            g['at'].append(at)
    for g in groups.values():
        if len(g['records']) >= least:
            out.append(dict({'kind': 'IN_SEVERAL_RECORDS'}, **g['what'], records=len(g['records']), record_ids=g['records'], support=len(g['at']), at=g['at'],
                            status='PROPOSED_ONLY'))
    return out
