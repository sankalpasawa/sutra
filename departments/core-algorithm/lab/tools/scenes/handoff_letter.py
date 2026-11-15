"""Recorded sequence of 0.18.0-handoff: a collections letter handed to a model and checked against the loan book, with tries.
scene(lab) -> the dict kept in the record under scenes.handoff_letter. Every pack loaded here is a scenario file.

Nothing real is called. The hand and the checker are stand-ins that read and write two files in the run's own folder (a temporary
folder that is gone when the scene returns; no path of it is recorded):
  loan_book.json   the lender's book for one loan (loan, borrower, amount overdue). Only the checker reads it.
  letter.txt       what the hand wrote. Its first line names the hand-over it answers: `for hand-over <sha256 of the receipt>`.
draft() is the hand: it is given a receipt and writes the letter. It never reads the book. On a later try it reads, in its receipt,
what the check of the try before said. check() is the checker: it reads both files and nothing else and states its rows. Its row on
the letter names the receipt the letter cites (`checks`), rests on the book's row at the version it read (`depends_on`), and carries
as its version a digest of the two files. The rows enter through the journal's event door (extensions/journal.py), whose header
names this one checker: each row that differs from the stored one is one journal entry and one executed look.

  tries   The desk and the hand-off method (packs 210 and 211). A first look: the book has not been read, nothing is handed over.
          The checker reads the book: the letter is handed to the model (try 1) and the run waits. A stamp for the hand-off, the
          hand's own row and a decision are each refused at the door. A second look waits and pays nothing. The model writes 2400;
          the check fails; the same look hands the letter over again (try 2), and that receipt says what the check of try 1 found.
          The process ends; the next one restarts from the kept journal and finds the same hand-over out. A late copy of the first
          draft is checked: it names the first receipt, so the look waits and no try is used. The model reads what it was told and
          writes 240: the check passes, the hand-off is closed as confirmed and the letter is queued. Then the book changes (a part
          payment: 180): the letter no longer counts as drafted, it is handed over again as a new hand-over, and the check of the
          old letter against the new book, which names the old receipt, uses no try of it.
  spent   The same desk and a hand that does not read what it is told. Three wrong letters, three failed checks: after the third
          the model's provider has no slot left and the look stops as PROVIDER_REQUIRED, dry or executed. A second method that
          hands the same letter to a person is handed in (pack 214): the kernel takes it, as try 4, and its receipt tells the
          officer what the three checks said. The officer's letter passes: closed as confirmed, queued.

A step is {entry, result}: the number of the journal entry it sealed and what the kernel returned for it. A snapshot is
{budget, providers, open_handoffs, letter_drafted, letter_queued}."""
import hashlib, json, re, tempfile
from pathlib import Path

LOOKS = 16   # the looks scene(lab) records (a dict that holds a list under `runs`: a look at the goals, or one row let in): tries 9, spent 7
RUNS = 16    # the runs in them (a dict with `trace` and `trace_root_sha256`): one in every look

HAND, CHECKER, OFFICER = 'model:letter-drafter', 'checker:loan-book', 'person:collections-officer'
BOOK, LETTER = 'loan_book.json', 'letter.txt'
_sha = lambda data: hashlib.sha256(data).hexdigest()


def keep_book(folder, overdue):
    """The lender's loan book for one loan, as a file in the run's folder."""
    (Path(folder) / BOOK).write_bytes(json.dumps({'loan': 'L-17', 'borrower': 'A. Rao', 'overdue': overdue}, sort_keys=True).encode('utf-8'))


def draft(folder, receipt, believes, reads_before=True, note=''):
    """The hand, a stand-in for a model or a person. It is given the receipt of a hand-over and writes the letter into the run's
    folder; it never reads the loan book. On a first try it writes the amount it believes. On a later try it reads, in its receipt,
    what the check of the try before said and writes the amount that check named, unless it does not read what it is told.
    Returns the amount it wrote."""
    told = [t['checked']['why'] for t in receipt['handoff']['before'] if t['checked'] and 'why' in t['checked']]
    named = re.findall(r'the loan book says ([0-9]+)', told[-1]) if told and reads_before else []
    amount = int(named[-1]) if named else believes
    text = f"for hand-over {receipt['sha256']}\nDear A. Rao, your loan L-17 is overdue by {amount}. Please pay within 14 days.{note}\n"
    (Path(folder) / LETTER).write_bytes(text.encode('utf-8'))
    return amount


def check(folder):
    """The checker, a stand-in. It reads the loan book and the letter in the run's folder, and nothing else, and states its rows:
    the book's row first (its version is a digest of the book file), then, when there is a letter, the letter's row: TRUE when the
    letter names the borrower, the loan and exactly the amount the book says is overdue, else FALSE with what it found (`why`,
    one text). That row names the receipt the letter cites (`checks`; null when it cites none), rests on the book's row at the
    version read (`depends_on`), and its version is a digest of both files."""
    book_bytes = (Path(folder) / BOOK).read_bytes()
    book, book_version = json.loads(book_bytes), 'book-' + _sha(book_bytes)[:16]
    rows = [{'predicate': 'loan_on_book', 'truth': 'TRUE', 'verified': True, 'source': CHECKER, 'version': book_version}]
    if (Path(folder) / LETTER).is_file():
        letter_bytes = (Path(folder) / LETTER).read_bytes()
        text = letter_bytes.decode('utf-8')
        first, _, rest = text.partition('\n')
        cites = first[len('for hand-over '):] if first.startswith('for hand-over ') else None
        body = text if cites is None else rest   # a letter that cites no hand-over is read whole
        amounts, why = re.findall(r'overdue by ([0-9]+)', body), []
        if book['borrower'] not in body:
            why.append(f"the letter does not name the borrower {book['borrower']}")
        if book['loan'] not in body:
            why.append(f"the letter does not name the loan {book['loan']}")
        if amounts != [str(book['overdue'])]:
            why.append(f"the letter says an overdue amount of {' and '.join(amounts) or 'nothing'}; the loan book says {book['overdue']}")
        row = {'predicate': 'letter_drafted', 'truth': 'FALSE' if why else 'TRUE', 'verified': True, 'source': CHECKER,
               'version': 'letter-' + _sha(letter_bytes + b'\n' + book_bytes)[:16], 'depends_on': [{'predicate': 'loan_on_book', 'version': book_version}],
               'checks': cites}
        if why:
            row['why'] = '; '.join(why)
        rows.append(row)
    return rows


def scene(lab):
    import sys
    from extensions import journal as J
    pack = lab['pack']
    open_handoffs = sys.modules['kinds.handoff'].open_handoffs   # the kind file is loaded by the lab's tools before any sequence runs
    KINDS = ['simulate_fact', 'handoff']
    PACKS = ['210_letters_desk', '211_hand_to_model']

    def reads(s, fact):
        seen = s.fact(fact)
        return {key: seen.get(key) for key in ('truth', 'source', 'final', 'version', 'checks')}

    def snap(run):
        s = run.state
        return {'budget': dict(s.budget), 'providers': dict(s.providers), 'open_handoffs': open_handoffs(s),
                'letter_drafted': reads(s, 'letter_drafted'), 'letter_queued': reads(s, 'letter_queued')}

    def step(run, kind, body):
        e = run.add(kind, body)
        return {'entry': e['seq'], 'result': run.detail[e['seq']]}

    def let_in(run, rows):   # the checker's rows through the journal's event door: a row that differs from the stored one is one entry and one executed look
        return [step(run, 'event', {'row': r, 'execute': True}) for r in rows if run.state.evidence.get(run.state.key(r['predicate'])) != dict(r, scope=run.state.scope)]

    def refused(do):
        try:
            do()
        except ValueError as why:
            return str(why)
        return None

    handed = lambda steps: steps[-1]['result']['runs'][0]['model_receipts'][-1]   # the receipt of the hand-over a look issued

    def begin(name):
        run = J.start(KINDS, [CHECKER], name=name)
        for n in PACKS:
            run.add('pack', {'pack': pack(n)})
        return run

    # ---- tries: two tries of the model, a restart in between, then the book changes
    with tempfile.TemporaryDirectory() as tmp:
        keep, run = J.Keep(), begin('collections-letter')
        before_the_book = step(run, 'look', {'execute': True})
        keep_book(tmp, 240)
        first = let_in(run, check(tmp))
        r1 = handed(first)
        own_row = {'predicate': 'letter_drafted', 'truth': 'TRUE', 'verified': True, 'source': HAND, 'version': 'the-hands-own-word', 'checks': r1['sha256']}
        at_the_door = {'a_stamp_from_the_hand': refused(lambda: run.add('answer', {'receipt': r1, 'truth': 'TRUE', 'source': HAND, 'execute': True})),
                       'a_stamp_from_the_checker': refused(lambda: run.add('answer', {'receipt': r1, 'truth': 'TRUE', 'source': CHECKER, 'execute': True})),
                       'the_hands_own_row': refused(lambda: run.add('event', {'row': own_row, 'execute': True})),
                       'a_decision_under_the_checkers_name': refused(lambda: run.add('event', {'row': dict(own_row, source=CHECKER, final=True), 'execute': True}))}
        after_first = snap(run)
        second_look = step(run, 'look', {'execute': True})
        after_second_look = snap(run)
        wrote_1 = draft(tmp, r1, believes=2400)
        failed = let_in(run, check(tmp))
        r2 = handed(failed)
        after_failed = snap(run)
        head_kept = J.save(run, keep)
        del run

        run = J.restart(keep)   # a new process: all it has is the kept text and the kept head
        restarted = {'head': dict(run.base), 'cut': run.cut, 'notice': run.notice, 'after': snap(run)}
        look_after_restart = step(run, 'look', {'execute': True})
        draft(tmp, r1, believes=2400, note=' (a late copy of the first draft)')
        late_copy = let_in(run, check(tmp))
        after_late_copy = snap(run)
        wrote_2 = draft(tmp, r2, believes=2400)
        passed = let_in(run, check(tmp))
        after_passed = snap(run)
        keep_book(tmp, 180)
        book_changed = let_in(run, check(tmp))
        tries = {'packs': PACKS, 'kinds': KINDS, 'checkers': [CHECKER],
                 'before_the_book': before_the_book, 'handed_over': first, 'at_the_door': at_the_door, 'after_handed_over': after_first,
                 'second_look': second_look, 'after_second_look': after_second_look,
                 'wrote_1': wrote_1, 'failed_check': failed, 'after_failed_check': after_failed, 'head_kept': head_kept,
                 'restarted': restarted, 'look_after_restart': look_after_restart, 'late_copy': late_copy, 'after_late_copy': after_late_copy,
                 'wrote_2': wrote_2, 'passing_check': passed, 'after_passing_check': after_passed,
                 'book_changed': book_changed, 'after_book_changed': snap(run), 'head': J.save(run, keep)}

    # ---- spent: a hand that does not read what it is told, then the next hand
    with tempfile.TemporaryDirectory() as tmp:
        run = begin('collections-letter-spent')
        keep_book(tmp, 240)
        first = let_in(run, check(tmp))
        receipt, wrong = handed(first), []
        for believes in (2400, 24, 204):
            draft(tmp, receipt, believes=believes, reads_before=False)
            steps = let_in(run, check(tmp))
            wrong.append({'wrote': believes, 'check': steps, 'after': snap(run)})
            if steps[-1]['result']['runs'][0]['model_receipts']:
                receipt = handed(steps)
        dry = step(run, 'look', {'execute': False})
        run.add('pack', {'pack': pack('214_hand_to_officer')})
        officer = step(run, 'look', {'execute': True})
        after_officer = snap(run)
        wrote = draft(tmp, handed([officer]), believes=0)
        passed = let_in(run, check(tmp))
        spent = {'packs': PACKS, 'handed_over': first, 'wrong_letters': wrong, 'dry_look': dry, 'next_hand': '214_hand_to_officer',
                 'officer': officer, 'after_officer': after_officer, 'officer_wrote': wrote, 'passing_check': passed, 'after': snap(run), 'head': run.head()}
    return {'tries': tries, 'spent': spent}
