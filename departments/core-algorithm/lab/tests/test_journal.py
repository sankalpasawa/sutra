"""Memory across runs (the journal version, matrix gap 1, rows R07 and R11): the journal, its doors, its head, its keeper,
and the record read back without the kernel. A test named test_cN_... pins claim CN of the README passage; the others
pin the named changes of the ruling and of its two refuters, and what the two refuters of the build found."""
from pathlib import Path
import unittest, sys, json, copy, dataclasses, hashlib, os, random, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, ACTIONS, canonical, digest
from tools.run_all import CASES, pack, scenario, extra_events, ask_events
from extensions import journal as J
from extensions import journal_record as R
from extensions.asks import answer, open_asks
from extensions.reflection import Learner

ASK = ['00_goal', '01_domain', '02_methods', '04_admission', '80_ask_method']     # the packs of case 29: the approval is asked for
ORDER = ['00_goal', '01_domain', '02_methods', '03_approval', '04_admission']     # the packs of case 04: the approval is there
STOP = ['30_build_goal', '31_build_theory', '82_components_without_constructor']  # the packs of case 30: the last step stops
KINDS = ['simulate_fact', 'ask']
CHECKERS = ['fixture/stock-recount', 'fixture/courier']
RECOUNT = {'predicate': 'substitute_stock', 'truth': 'TRUE', 'version': '2', 'verified': True, 'source': 'fixture/stock-recount'}
LOST = {'predicate': 'replacement_delivered', 'truth': 'FALSE', 'version': 'returned-1', 'verified': True, 'source': 'fixture/courier'}
QUESTION = 'orgA/fulfillment|customer_approved'
LOOK = {'execute': True}
CLOSED_RUN = 'This run takes no more entries (its journal is closed and goes on in the journal its last entry names)'
CLOSED_KEPT = 'The journal kept here is closed: nothing is appended to it, and it goes on in the journal its last entry names'
NAMES_ANOTHER = 'The journal is closed and names another journal as the one that continues it'
NOT_CLOSED = 'A journal continues one that is closed: the journal handed in before it does not end on a closing entry'
NO_CITE = 'The header does not cite the head of the journal handed in before it'
NOT_ITS_NEXT = 'The journal handed in before this one names another journal as the one that continues it'
NOT_ONE_RECORD = 'A journal of this record does not continue the one before it'
MOVED = 'The journal moved on since this run was replayed ({}): replay it and try again'
TAKES = 'A keeper takes whole entries that chain onto the head it keeps and end on the head handed in with them'


def deep_call(n, do):   # `do` called n calls further down the stack of this process
    return do() if n <= 0 else deep_call(n - 1, do)


def started(packs=ASK, kinds=KINDS, name='test', look=True):
    run = J.start(kinds, CHECKERS, name=name)
    for n in packs:
        run.add('pack', {'pack': pack(n)})
    if look:
        run.add('look', LOOK)
    return run


def kept(run):
    keep = J.Keep()
    J.save(run, keep)
    return keep


def receipt_of(run, seq=6):
    return run.detail[seq]['runs'][0]['model_receipts'][0]


def yes(receipt, truth='TRUE'):
    return {'receipt': receipt, 'truth': truth, 'source': 'customer', 'execute': True}


def last(run):   # the first run of the last entry, as the kernel returned it
    return run.detail[len(run.journal) - 1]['runs'][0]


def chained(entries):   # what a forger can do without any secret: number the entries and hash the chain again
    out, prev = [], 'GENESIS'
    for n, e in enumerate(entries):
        e = dict(copy.deepcopy(e), seq=n, prev_sha256=prev)
        e['sha256'] = digest({k: e[k] for k in J.COVERED})
        out.append(e)
        prev = e['sha256']
    return out, {'length': len(out), 'sha256': prev}


def mutants(value):
    """A field of the State changed by hand, in every way its type allows. No field is named here: the guard is what a
    change does to the digest, not a list of names."""
    plain_data = lambda v: type(v) in (str, int, list, dict) and not _holds_code(v)
    if type(value) is str:
        yield value + 'x'
    elif type(value) is set:
        yield value | {'mutant'}
        if value:
            yield set(sorted(value)[1:])
    elif type(value) is list:
        yield value + [copy.deepcopy(value[0]) if value else 'mutant']
        if value:
            yield value[1:]
            yield value[::-1] + value[:1] if len(value) > 1 else value + value
    elif type(value) is dict:
        yield dict(value, mutant=copy.copy(next(iter(value.values()))) if value else 'mutant')
        if value:
            first = next(iter(value))
            yield {k: v for k, v in value.items() if k != first}
            if plain_data(value[first]):
                v = value[first]
                yield dict(value, **{first: v + 1 if type(v) is int else v + 'x' if type(v) is str else v + ['x'] if type(v) is list else dict(v, mutant='x')})


def _holds_code(v):
    try:
        json.dumps(v)
        return False
    except (TypeError, ValueError):
        return True


# A journal written by a draft of the build that added the journal (on the 388-line kernel), kept here as text, with
# its head: a pack with one ask, one executed look, the question out. See test_a_journal_kept_from_this_build_still_replays.
KEPT = (
    '{"body":{"checkers":[],"kinds":["ask"],"name":"kept"},"kind":"header","prev_sha256":"GENESIS","result":{"budget":{"attention":3,"compute":10,"money":10},"providers":{},"state":"7df4d56db9ebe155fd3a82c6a91e5a726d711f46dce4cb292e4c22dd5c5e0477"},"seq":0,"sha256":"356aa54521ce4bae0ba61db6708282707e12573b82b959cfddfb7d3cf18a5e5f","stated":{"code":{"extensions.asks":"dcc5807bfe7a95f5ae8d652f854dd1c232fc02ab859924e091adf5dfd1c22357","extensions.journal":"658951608d80e365a9095d7a5e8f6354e7a1716fda6d50a3ab427d5b8c9ac6fe","kernel.core":"3377f09360392d4c21edb4d0c670f0dc030cb1de98a2e6089317000b5e23944f"}}}',
    '{"body":{"pack":{"goals":["approved"],"grants":["may-ask"],"id":"kept","methods":[{"action":"ask","ask_to":"owner","cost":{"attention":1},"effect":"approved","grant":"may-ask","id":"ask@1","provider":"owner","question":"Go?","requires":[]}],"providers":{"owner":1},"schema":"sutra-extension/2"}},"kind":"pack","prev_sha256":"356aa54521ce4bae0ba61db6708282707e12573b82b959cfddfb7d3cf18a5e5f","result":{"budget":{"attention":3,"compute":10,"money":10},"providers":{"owner":1},"state":"b60230f3c70d3deae3d985d881b7cc61960cc86ade79276406afb7033190e848"},"seq":1,"sha256":"aa8854a7155dbaaa91d753c062f8494a9c0c3fe7b7352d85185295987a2190c8"}',
    '{"body":{"execute":true},"kind":"look","prev_sha256":"aa8854a7155dbaaa91d753c062f8494a9c0c3fe7b7352d85185295987a2190c8","result":{"briefs":[{"actions":["ask@1"],"cost":{"attention":1,"compute":0,"money":0},"goal":"approved","receipts":[{"action":"ask","ask":{"asked_in":"f87e74a79ad9e1221c74b62a112c99c56bb71d0b56fcbb45cfdee3191d47d95b","predicate":"approved","question":"Go?","to":"owner"},"method":"ask@1","parked":true,"scope":"orgA/fulfillment","sha256":"1fe71c9bd27349021036af97ef23abf695aa9fc14400aec43c501df0677eca2f","status":"LOCAL_ONLY"}],"scope":"orgA/fulfillment","status":"WAITING","trace_root_sha256":"e44d7d9bfb39a524f72f1ef4867fab09013c4bbd602d0f5a65bc99e98a8bcd49","waits":["ask@1"],"work_state":"waiting"}],"budget":{"attention":2,"compute":10,"money":10},"goals":["approved"],"providers":{"owner":0},"state":"28c3b32a8538c04a20bd9eb03ead47b2ab9b0241558ecee985e0221e31f13c7f","status":"EVALUATED"},"seq":2,"sha256":"c2ca882b8a629c688c7bb1fefeb506a8118ea3109e942874e6cd6e649aeba9db"}')
KEPT_HEAD = {'length': 3, 'sha256': 'c2ca882b8a629c688c7bb1fefeb506a8118ea3109e942874e6cd6e649aeba9db'}


class JournalTests(unittest.TestCase):
    def words(self, do):
        with self.assertRaises(ValueError) as caught:
            do()
        return str(caught.exception)

    # ------------------------------------------------------------------ C1: whole and in order, or refused
    def test_c1_replay_runs_exactly_what_its_head_names_and_ends_on_its_hash(self):
        p1 = started()
        keep, receipt = kept(p1), receipt_of(p1)
        text, head = keep.read()
        entries = J.parse(text)
        self.assertEqual(head, {'length': 7, 'sha256': entries[6]['sha256']})
        self.assertEqual(self.words(lambda: J.replay(entries[:-1], head)), 'The journal ends before its head: 6 entries, the head names 7')
        self.assertEqual(self.words(lambda: J.restart(J.Keep(J.dump(entries[:-1]), head))), 'The journal ends before its head: 6 entries, the head names 7')
        self.assertEqual(self.words(lambda: J.replay(entries, {'length': 7, 'sha256': entries[5]['sha256']})), 'The journal does not end on the hash its head names')
        for bad in (None, {}, {'length': 7}, dict(head, more=1), dict(head, length=True), dict(head, length=7.0), dict(head, length=0), dict(head, sha256=7), [7, head['sha256']]):
            self.assertTrue(self.words(lambda: J.replay(entries, bad)).startswith('No head, no restart'), bad)   # no head, no restart; a head is exact
        self.assertTrue(self.words(lambda: J.restart(J.Keep(text, None))).startswith('No head, no restart'))
        # An entry past the head (the writer died between the entry and the head, or a forger's yes): reported, cut, never run.
        writer = J.restart(keep)
        writer.add('answer', yes(receipt))
        stray = J.Keep(text + J.dump(writer.journal[7:]), head)
        r = J.restart(stray)
        self.assertEqual((r.cut, len(r.journal), list(open_asks(r.state)), dict(r.state.budget), r.state.fact('replacement_delivered')['truth']),
                         (1, 7, [QUESTION], {'compute': 10, 'money': 10, 'attention': 2}, 'FALSE'))
        self.assertEqual(J.replay(J.parse(stray.text), head).cut, 1)
        r.add('look', LOOK)
        J.save(r, stray)                                     # the next save cuts it
        self.assertEqual([e['kind'] for e in J.parse(stray.text)][6:], ['look', 'look'])
        torn = J.Keep(text + '{"body":{"execute', head)      # a writer that died inside an entry: also past the head
        self.assertEqual((J.restart(torn).cut, J.restart(torn).head()), (1, head))
        self.assertEqual(J.load(torn), (entries, head, ['{"body":{"execute']))   # what a restart reads: the entries the head names, the head, and apart from them what stands past it
        self.assertEqual(J.load(J.Keep(text + J.dump(writer.journal[7:]) + 'x', head))[2], [canonical(writer.journal[7]), 'x'])
        self.assertEqual(J.load(keep), (entries, head, []))
        self.assertEqual(self.words(lambda: J.load(J.Keep(J.dump(entries[:-1]), head))), 'The journal ends before its head: 6 entries, the head names 7')
        self.assertEqual((p1.cut, p1.notice, p1.stopped, p1.base, p1.earlier), (0, [], False, head, []))   # a run that was started here and saved

    def test_c1_a_changed_dropped_doubled_or_swapped_entry_is_refused_by_number(self):
        keep = kept(started())
        text, head = keep.read()
        entries = J.parse(text)
        edited = copy.deepcopy(entries)
        edited[5]['body']['pack']['methods'][0]['ask_to'] = 'someone-else'
        for changed, presented, at in ((edited, head, 5), (entries[:3] + entries[4:], {'length': 6, 'sha256': head['sha256']}, 3), (entries[:4] + entries[3:], head, 4),
                                       (entries[:2] + [entries[3], entries[2]] + entries[4:], head, 2), (entries[1:], {'length': 6, 'sha256': head['sha256']}, 0)):
            self.assertEqual(self.words(lambda: J.replay(changed, presented)), f'The journal is broken at entry {at}')
        for line in (text.split('\n')[2].replace('":', '": ', 1), text.split('\n')[2] + ' ', '{"seq":2,"seq":2}', 'not json'):   # not the text this journal writes
            lines = text.split('\n')
            lines[2] = line
            self.assertEqual(self.words(lambda: J.parse('\n'.join(lines))), 'The journal is broken at entry 2')
            self.assertEqual(self.words(lambda: J.restart(J.Keep('\n'.join(lines), head))), 'The journal is broken at entry 2')
        self.assertEqual(self.words(lambda: J.parse(text[:-1])), 'The journal is broken at entry 6')   # the text ends inside an entry
        for entry in ({'seq': 0}, 'text', dict(entries[0], more=1), dict(entries[0], stated={'code': {'kernel.core': 1}}), dict(entries[0], stated={'note': 'x'}),
                      dict(entries[0], stated=dict(entries[0]['stated'], when='now')), dict(entries[0], stated=['code']), dict(entries[0], stated={'code': 'kernel.core'})):
            self.assertEqual(self.words(lambda: J.replay([entry], {'length': 1, 'sha256': entries[0]['sha256']})), 'The journal is broken at entry 0')
        for journal in ('text', tuple(entries), {'entries': entries}, None):
            self.assertEqual(self.words(lambda: J.replay(journal, head)), 'A journal is a list of entries')
        for odd in ({'a', 'b'}, object(), b'bytes', {1: 'a', '1': 'b'}):               # an entry that holds what is no plain data
            self.assertEqual(self.words(lambda: J.replay(entries[:6] + [dict(entries[6], body=odd)], head)), 'The journal is not plain data')

    def test_c1_an_entry_on_a_wrong_link_or_under_a_wrong_number_is_refused_though_its_own_hash_is_true(self):
        """Refuter 2 of the build, finding 4: a chain is the link and the number, not only each entry's own hash."""
        run = started()
        run.add('look', LOOK)
        run.add('look', LOOK)
        keep = kept(run)
        entries = J.parse(keep.text)

        def own(e, **changed):   # an entry changed and hashed again by itself: its own hash is true
            e = dict(copy.deepcopy(e), **changed)
            e['sha256'] = digest({k: e[k] for k in J.COVERED})
            return e
        dry = own(entries[7], body={'execute': False})   # entry 7 said to have been a dry look. Entry 8 is untouched, so the journal still ends on the kept head
        forged = entries[:7] + [dry, entries[8]]
        for read in (lambda: J.replay(forged, keep.head), lambda: J.restart(J.Keep(J.dump(forged), keep.head)), lambda: R.ledger([(J.dump(forged), keep.head)])):
            self.assertEqual(self.words(read), 'The journal is broken at entry 8')
        before = {'length': 8, 'sha256': entries[7]['sha256']}
        for last in (own(entries[8], prev_sha256=entries[6]['sha256']), own(entries[8], prev_sha256='GENESIS'), own(entries[8], seq=9), own(entries[8], seq=8.0), own(entries[8], seq=True)):
            journal, head = entries[:8] + [last], {'length': 9, 'sha256': last['sha256']}   # the last entry, so nothing after it shows the break: the right number on a wrong link, the right link under a wrong number
            for read in (lambda: J.replay(journal, head), lambda: J.restart(J.Keep(J.dump(journal), head)), lambda: R.counts([(J.dump(journal), head)])):
                self.assertEqual(self.words(read), 'The journal is broken at entry 8')
            keeper = J.Keep(J.dump(entries[:8]), before)
            self.assertEqual(self.words(lambda: keeper.append(before, J.dump([last]), head)), TAKES)   # and no keeper takes it
            self.assertEqual(keeper.read(), (J.dump(entries[:8]), before))
        alone = J.replay(entries[:7] + [dry], {'length': 8, 'sha256': dry['sha256']})   # on a chain of its own and under a head of its own the dry look replays: only the head kept outside tells the two journals apart
        self.assertEqual(J.state_digest(alone.state), entries[7]['result']['state'])

    def test_c1_a_line_that_nests_deeper_than_any_entry_is_a_broken_entry_and_a_failure_of_the_process_refuses_nothing(self):
        """Refuter 1 of the build, findings 3 and 4. Two kinds of failure, never mixed: a ValueError refuses the journal,
        by entry number; a RecursionError says the process ran out of stack: it refuses nothing and stops no run."""
        run = started()
        keep = kept(run)
        text, head = keep.read()
        lines, entries = text.split('\n'), J.parse(text)
        self.assertEqual((max(J._depth(line) for line in lines[:-1]), J.DEEPEST, R.DEEPEST), (7, 64, 64))   # what this journal writes nests 7 deep
        for deep in ('[' * 1000 + ']' * 1000, '{"a":' * 1000 + '1' + '}' * 1000, '[' * 5000, '[' * 70 + ']' * 70, '"' + '[' * 1000 + '"'):
            bad = '\n'.join(lines[:3] + [deep] + lines[4:])                              # entry 3 replaced: the first three no reader can take apart; the last two parse, and are no entry
            writer = J.restart(keep)
            writer.add('look', LOOK)
            for read in (lambda: J.restart(J.Keep(bad, head)), lambda: J.replay(J.parse(bad), head), lambda: J.save(writer, J.Keep(bad, head)), lambda: R.ledger([(bad, head)]), lambda: R.counts([(bad, head)])):
                self.assertEqual(self.words(read), 'The journal is broken at entry 3', deep[:12])
            self.assertEqual(self.words(lambda: J.Keep(text, head).append(head, deep + '\n', {'length': 8, 'sha256': '0' * 64})), TAKES)
        texts = ('{}', '[[]]', '{"a":[1,{"b":[]}],"c":"[[[{"}', '"[[["', '[' * 64 + ']' * 64, '{"a":"\\"[["}', '[1,[2],[3,[4]]]', '{"a":{"b":{"c":"}}}"}}}')
        self.assertEqual(([J._depth(t) for t in texts], [R._depth(t) for t in texts]), ([1, 2, 4, 0, 64, 1, 3, 3],) * 2)   # counted outside quoted text, without recursion
        self.assertEqual([J._deeper(json.loads('[' * n + ']' * n)) for n in (1, 63, 64, 65, 200)], [False, False, False, True, True])
        self.assertEqual([J._deeper([[0]] * n) for n in (1000000, 1000001)], [False, True])   # and no entry holds more than a million parts at one level
        nested = []
        for _ in range(1000):
            nested = [nested]
        handed = J.parse(text)
        handed[3]['body']['pack']['nested'] = nested                                     # the same in a list of entries handed to replay
        self.assertEqual(self.words(lambda: J.replay(handed, head)), 'The journal is broken at entry 3')
        self.assertTrue(self.words(lambda: run.add('pack', {'pack': {'schema': 'sutra-extension/2', 'id': 'deep', 'nested': nested}})).startswith('An entry body is plain data'))
        wide = [0]
        for _ in range(21):
            wide = [wide, wide]                                                           # one part handed in in many places: written out, two million of it at one level
        handed = J.parse(text)
        handed[3]['body']['pack']['wide'] = wide
        self.assertEqual(self.words(lambda: J.replay(*chained(handed))), 'The journal is broken at entry 3')   # no entry: it is not written out to find that
        seventy = []
        for _ in range(70):
            seventy = [seventy]
        r = J.restart(kept(started(ORDER, ['simulate_fact'], look=False)))               # and an entry that deep is never sealed, so no line this journal wrote is refused for its depth
        r.state.actions['simulate_fact'] = dict(r.state.actions['simulate_fact'], settle=lambda s, result, log: log('NOTE', nested=seventy))
        self.assertEqual(self.words(lambda: r.add('look', LOOK)), 'An entry nests at most 64 levels deep: nothing is sealed')
        self.assertEqual((len(r.journal), r.stopped), (6, 'an entry stopped part way'))
        # Near the end of the stack every read either comes out or fails as the process: never in the journal's words.
        limit, seen = sys.getrecursionlimit(), {'done': 0, 'the process': 0}
        for depth in range(limit - 150, limit):
            live = J.restart(keep)
            live.add('look', LOOK)
            for do in (lambda: J.replay(entries, head), lambda: J.restart(keep), lambda: R.ledger([(text, head)]), live.head, lambda: J.save(live, J.Keep(text, head))):
                try:
                    deep_call(depth, do)
                    seen['done'] += 1
                except RecursionError:
                    seen['the process'] += 1
            self.assertEqual((live.stopped, live.head()['length']), (False, 8), depth)  # no run was stopped by it, and from the bottom of the stack its head is quoted
        self.assertTrue(seen['done'] > 100 and seen['the process'] > 100, seen)
        low, high = 0, limit                                                             # how far down this stack goes from here
        while low < high:
            mid = (low + high + 1) // 2
            try:
                deep_call(mid, int)
                low = mid
            except RecursionError:
                high = mid - 1
        for depth, failure in ((64, RecursionError), (65, ValueError)):                  # 30 calls from its end: a line as deep as an entry may be fails as the process, one level deeper as the journal
            bad = '\n'.join(lines[:3] + ['[' * depth + ']' * depth] + lines[4:])
            for read in (lambda: J._line('[' * depth + ']' * depth, 3), lambda: J.parse(bad), lambda: R.entries(bad, head)):
                with self.assertRaises(failure):
                    deep_call(low - 30, read)

    def test_c1_a_tail_torn_inside_a_character_is_past_the_head_reported_and_cut(self):
        """Refuter 2 of the build, finding 6: the journal writes text outside ASCII as it is, so a writer that dies inside
        its write can leave half a character. Only what stands under the head must be text."""
        marks = ['00_goal', '01_domain', '02_methods', '04_admission', '141_ask_with_line_marks']
        with tempfile.TemporaryDirectory() as folder:
            keep, file = J.FileKeep(folder), Path(folder) / 'journal.jsonl'
            head = J.save(started(marks), keep)
            kept_bytes = file.read_bytes()
            self.assertGreater(len(kept_bytes), len(kept_bytes.decode('utf-8')))        # the kept text holds characters of more than one byte
            torn = '{"body":{"question":"May we?\u2028'.encode('utf-8')[:-1]            # the start of one more entry, cut inside the three bytes of U+2028
            with self.assertRaises(UnicodeDecodeError):
                (kept_bytes + torn).decode('utf-8')
            file.write_bytes(kept_bytes + torn)
            r = J.restart(keep)
            self.assertEqual((r.cut, r.head(), J.dump(r.journal).encode('utf-8'), list(open_asks(r.state))), (1, head, kept_bytes, [QUESTION]))   # reported, never run
            r.add('look', {'execute': False})
            after = J.save(r, keep)
            self.assertEqual((after['length'], file.read_bytes()), (8, kept_bytes + J.dump(r.journal[7:]).encode('utf-8')))   # and cut by the next save
            file.write_bytes(file.read_bytes() + b'\xff\xfe\n{"seq":9}\n\xe2\x80')        # two whole lines and a torn third past the head, the first and the last no text at all
            self.assertEqual((J.restart(keep).cut, J.restart(keep).head()), (3, after))
            broken = file.read_bytes()
            file.write_bytes(broken[:40] + b'\xff' + broken[41:])                         # under the head it must be text
            self.assertEqual(self.words(lambda: J.restart(keep)), 'The journal is broken: its text is not UTF-8')
            (Path(folder) / 'journal.head').unlink()                                      # with no head nothing must be text: no head, no restart, and nothing is appended
            file.write_bytes(b'\xff\xfe' + kept_bytes)
            self.assertEqual(self.words(lambda: J.restart(keep)), 'No head, no restart: the head is kept outside the journal, and none is kept here')
            self.assertEqual(self.words(lambda: J.save(started(), keep)), 'A journal stands here without a head: nothing is appended to it and nothing replaces it')

    # ------------------------------------------------------------------ C2 and C3: what was asked, decided and ran comes back
    def test_c2_a_restart_gives_the_look_of_the_process_that_never_stopped(self):
        p1 = started()
        keep, receipt = kept(p1), receipt_of(p1)
        twin = started()
        p2 = J.restart(keep)
        self.assertEqual((p2.base, p2.cut, p2.notice, J.state_digest(p2.state)), (keep.head, 0, [], p1.journal[-1]['result']['state']))
        self.assertEqual(canonical(J.views(p2.state)), canonical(J.views(twin.state)))
        for kind, body in (('look', LOOK), ('answer', yes(receipt)), ('look', LOOK), ('event', {'row': RECOUNT, 'execute': False}), ('look', {'execute': False})):
            a, b = p2.add(kind, body), twin.add(kind, body)
            self.assertEqual(canonical(a), canonical(b))                                                # the entry
            self.assertEqual(canonical(p2.detail[a['seq']]), canonical(twin.detail[b['seq']]))          # and the kernel's whole answer, trace included
        self.assertEqual(J.save(p2, keep), twin.head())                                                 # a restart seals nothing: the same head
        self.assertEqual(keep.text, J.dump(twin.journal))

    def test_c2_the_question_is_still_out_nothing_is_charged_again_and_the_answer_is_taken(self):
        p1 = started()
        keep, receipt = kept(p1), receipt_of(p1)
        self.assertEqual((last(p1)['status'], last(p1)['actions'], dict(p1.state.budget)), ('WAITING', ['ask-customer-approval@1'], {'compute': 10, 'money': 10, 'attention': 2}))
        p2 = J.restart(keep)
        self.assertEqual(canonical(open_asks(p2.state)), canonical({QUESTION: {'method': 'ask-customer-approval@1', 'receipt': receipt['sha256'], 'issued': receipt}}))
        p2.add('look', LOOK)
        r = last(p2)
        self.assertEqual((r['status'], r['actions'], r['model_receipts'], r['pending'], r['cost'], dict(p2.state.budget), dict(p2.state.providers)),
                         ('WAITING', [], [], ['ship-replacement@1'], {'compute': 0, 'money': 0, 'attention': 0}, {'compute': 10, 'money': 10, 'attention': 2}, {'local-provider': 5, 'owner-channel': 1}))
        e = p2.add('answer', yes(receipt))
        self.assertEqual((last(p2)['status'], last(p2)['actions'], dict(p2.state.budget)), ('LOCAL_MODEL_EFFECTS_RECORDED', ['ship-replacement@1'], {'compute': 8, 'money': 8, 'attention': 2}))
        self.assertEqual((e['body']['receipt']['sha256'], e['body']['source']), (receipt['sha256'], receipt['ask']['to']))   # the answer entry names the receipt it answers
        asks = [x for entry in p2.journal for b in entry['result'].get('briefs', []) for x in b['receipts'] if 'ask' in x]
        self.assertEqual([x['sha256'] for x in asks], [receipt['sha256']])   # asked once in the whole record
        # From the packs alone, a new process: the receipt is refused, the customer is asked the very same question again and charged again.
        s = State.from_packs([pack(n) for n in ASK])
        k = Kernel(s)
        self.assertEqual(self.words(lambda: answer(k, receipt, 'TRUE', 'customer', execute=True)), 'No open ask matches this receipt')
        r = k.run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], r['actions'], s.budget['attention'], canonical(r['model_receipts'][0])), ('WAITING', ['ask-customer-approval@1'], 2, canonical(receipt)))

    def test_c2_the_answer_is_a_function_of_the_journal_up_to_its_head_not_of_the_packs_alone(self):
        """The promise, reworded by the panel on the owner's four: the same packs and the same journal up to its head
        give the same answer. The packs alone do not: a receipt is bound to the State's history."""
        p1 = started()                                         # five packs, one executed look
        receipt, first = receipt_of(p1), p1.detail[6]['runs'][0]
        d = started(look=False)
        d.add('look', {'execute': False})                      # the same header and packs, and one dry look more
        self.assertEqual((last(d)['status'], last(d)['model_receipts'], dict(d.state.budget)), ('PLAN_READY', [], {'compute': 10, 'money': 10, 'attention': 3}))
        d.add('look', LOOK)
        other = last(d)['model_receipts'][0]
        self.assertEqual((canonical(last(d)['provenance']), last(d)['status']), (canonical(first['provenance']), 'WAITING'))          # the same packs, the same question
        self.assertEqual(canonical({k: v for k, v in other['ask'].items() if k != 'asked_in'}), canonical({k: v for k, v in receipt['ask'].items() if k != 'asked_in'}))
        self.assertTrue(other['sha256'] != receipt['sha256'] and other['ask']['asked_in'] != receipt['ask']['asked_in'] and last(d)['trace_root_sha256'] != first['trace_root_sha256'])   # another receipt, another trace
        self.assertEqual(self.words(lambda: d.add('answer', yes(receipt))), 'No open ask matches this receipt')                    # which the first receipt does not answer
        d.add('answer', yes(other))
        self.assertEqual(last(d)['status'], 'LOCAL_MODEL_EFFECTS_RECORDED')
        # The same journal up to its head: two processes that hold the same text and head seal the same entries, byte for byte.
        keep = kept(p1)
        a, b = J.restart(keep), J.restart(J.Keep(*json.loads(json.dumps(keep.read()))))
        for kind, body in (('look', {'execute': False}), ('look', LOOK), ('event', {'row': RECOUNT, 'execute': True}), ('answer', yes(receipt, 'FALSE')), ('look', LOOK)):
            ea, eb = a.add(kind, body), b.add(kind, body)
            self.assertEqual((canonical(ea), canonical(a.detail[ea['seq']])), (canonical(eb), canonical(b.detail[eb['seq']])))
        self.assertEqual(a.head(), b.head())

    def test_c3_a_no_and_a_finished_step_survive_a_restart(self):
        p1 = started()
        keep, receipt = kept(p1), receipt_of(p1)
        n2 = J.restart(keep)
        n2.add('answer', yes(receipt, 'FALSE'))
        self.assertEqual((last(n2)['status'], last(n2)['work_state']), ('REFUSED', 'blocked'))
        J.save(n2, keep)
        n3 = J.restart(keep)
        n3.add('look', LOOK)
        self.assertEqual((last(n3)['status'], last(n3)['model_receipts'], dict(n3.state.budget)), ('REFUSED', [], {'compute': 10, 'money': 10, 'attention': 2}))
        self.assertEqual(self.words(lambda: n3.add('answer', yes(receipt))), 'No open ask matches this receipt')   # a later yes is refused
        self.assertEqual(len(n3.journal), 9)
        s = State.from_packs([pack(n) for n in ASK])   # the packs alone: the no is forgotten, and a yes ships
        k = Kernel(s)
        k.run_standing(execute=True)
        self.assertEqual(answer(k, receipt, 'TRUE', 'customer', execute=True)['runs'][0]['status'], 'LOCAL_MODEL_EFFECTS_RECORDED')
        # What ran is not run or paid again.
        o1 = started(ORDER, ['simulate_fact'])
        self.assertEqual((last(o1)['status'], dict(o1.state.budget)), ('LOCAL_MODEL_EFFECTS_RECORDED', {'compute': 8, 'money': 8, 'attention': 3}))
        o2 = J.restart(kept(o1))
        o2.add('look', LOOK)
        self.assertEqual((last(o2)['status'], last(o2)['model_receipts'], dict(o2.state.budget)), ('SUPPORTED_BY_EVIDENCE', [], {'compute': 8, 'money': 8, 'attention': 3}))
        s = State.from_packs([pack(n) for n in ORDER])
        self.assertEqual((Kernel(s).run_standing(execute=True)['runs'][0]['status'], dict(s.budget)), ('LOCAL_MODEL_EFFECTS_RECORDED', {'compute': 8, 'money': 8, 'attention': 3}))   # ships and pays again

    def test_restart_equals_never_stopping_on_random_walks(self):
        """Property: whatever is done through the doors, and wherever the process is restarted through the text, the
        State, the head and the next executed look are those of a twin that never stopped."""
        rng = random.Random(20261114)
        families = ((ASK, KINDS), (ORDER + ['06_notify'], ['simulate_fact']), (['20_enquiry_goal', '21_enquiry_theory', '22_enquiry_methods', '23_enquiry_extra_knowledge', '24_enquiry_privacy'], ['simulate_fact']),
                    (STOP, ['simulate_fact', 'compile_candidate']))
        rows = [RECOUNT, LOST, dict(RECOUNT, predicate='original_stock', version='3'), dict(LOST, predicate='record_stored', version='lost-1'), dict(RECOUNT, predicate='privacy_checked', truth='FALSE', version='4')]
        restarts = entries = 0
        for walk in range(24):
            packs, kinds = families[walk % len(families)]
            live, twin, keep, todo = J.start(kinds, CHECKERS, name=f'walk-{walk}'), J.start(kinds, CHECKERS, name=f'walk-{walk}'), J.Keep(), list(packs)
            for _ in range(rng.randint(6, 16)):
                out = list(open_asks(twin.state).values())
                pick = rng.choice(['pack'] * 3 + ['look'] * 3 + ['event'] * 2 + ['answer'] * 2)
                if pick == 'pack' and todo:
                    kind, body = 'pack', {'pack': pack(todo.pop(0))}
                elif pick == 'event':
                    kind, body = 'event', {'row': dict(rng.choice(rows), version=str(rng.randint(1, 4))), 'execute': rng.random() < 0.7}
                elif pick == 'answer' and out:
                    kind, body = 'answer', yes(out[0]['issued'], rng.choice(['TRUE', 'FALSE']))
                else:
                    kind, body = 'look', {'execute': rng.random() < 0.7}
                self.assertEqual(canonical(live.add(kind, body)), canonical(twin.add(kind, body)))
                entries += 1
                if rng.random() < 0.35:   # the process ends here; the next one has the text and the head
                    J.save(live, keep)
                    live = J.restart(J.Keep(*json.loads(json.dumps(keep.read()))))
                    restarts += 1
                    self.assertEqual(J.state_digest(live.state), J.state_digest(twin.state))
            self.assertEqual((J.save(live, keep), keep.text), (twin.head(), J.dump(twin.journal)))
            self.assertEqual(canonical(live.add('look', LOOK)), canonical(twin.add('look', LOOK)))
            self.assertEqual(canonical(live.detail[len(live.journal) - 1]), canonical(twin.detail[len(twin.journal) - 1]))
            J.save(live, keep)
            got, runs = R.counts([keep.read()]), [r for d in twin.detail.values() for r in d['runs']]   # and the counts read from the text are the kernel's own runs and receipts
            self.assertEqual((sum(g['looked'] for g in got['goals'].values()), sum(s['ran'] for s in got['steps'].values())), (len(runs), sum(len(r['model_receipts']) for r in runs)))
        self.assertGreater(restarts, 40)
        self.assertGreater(entries, 200)

    # ------------------------------------------------------------------ C4: recomputed, not believed
    def test_c4_a_journal_re_chained_by_a_forger_is_refused_where_the_result_does_not_come_out_again(self):
        keep = kept(started())
        entries = J.parse(keep.text)

        def forged(change):
            f = copy.deepcopy(entries)
            change(f)
            return chained(f)
        for change, said, at in ((lambda f: f[6]['result']['budget'].update(attention=3), 'budget', 6),                  # the charge for the question taken back
                                 (lambda f: f[6]['result']['briefs'][0].update(status='PLAN_READY'), 'briefs', 6),       # another status
                                 (lambda f: f[6]['result'].update(state='0' * 64), 'state', 6),                          # a false State digest: only a replay can tell
                                 (lambda f: f[4]['result']['providers'].update({'local-provider': 9}), 'providers', 4),
                                 (lambda f: f[6]['result'].update(note='x'), 'note', 6),
                                 (lambda f: f[0]['result'].update(state='0' * 64), 'state', 0),                          # the header too: what a new State is, is computed again
                                 (lambda f: f[0]['result']['budget'].update(attention=9), 'budget', 0),
                                 (lambda f: f[0]['result']['providers'].update({'local-provider': 1}), 'providers', 0)):
            journal, head = forged(change)
            self.assertEqual(self.words(lambda: J.replay(journal, head)), f'The journal does not replay at entry {at}: the result differs ({said})')
        header = 'The journal does not replay at entry 0: A header holds kinds and checkers (lists of names) and may hold a name and the head it continues'
        for change, said in ((lambda f: f[6]['result'].pop('providers'), 'The journal does not replay at entry 6: the result differs (providers)'),   # a part the result should hold, gone
                             (lambda f: f[6]['result'].pop('briefs'), 'The journal does not replay at entry 6: the result differs (briefs)'),
                             (lambda f: f[0]['body'].update(name=''), header), (lambda f: f[0]['body'].update(checkers=['x', 'x']), header), (lambda f: f[0]['body'].update(continues=7), 'The journal does not replay at entry 0: No head, no restart: a head is {length, sha256} and is kept outside the journal'),
                             (lambda f: f[6].update(kind='resume'), 'The journal is broken at entry 6'),                 # a kind the journal does not have
                             (lambda f: f[6].update(kind=['look']), 'The journal is broken at entry 6'),
                             (lambda f: f[6].update(body=[True]), 'The journal is broken at entry 6'),                   # a body or a result that is no object
                             (lambda f: f[6].update(result='EVALUATED'), 'The journal is broken at entry 6'),
                             (lambda f: f[3].update(kind='header', body={'kinds': KINDS, 'checkers': []}), 'The journal is broken at entry 3'),   # a second header
                             (lambda f: f[0].update(kind='pack', body={'pack': pack('00_goal')}), 'The journal is broken at entry 0')):          # no header
            journal, head = forged(change)
            self.assertEqual(self.words(lambda: J.replay(journal, head)), said)
        journal, head = forged(lambda f: f[6]['result'].update(state='0' * 64))
        self.assertEqual(len(R.ledger([(J.dump(journal), head)])), 7)   # a known limit, pinned: without the kernel a false State digest passes; only replay refuses it
        journal, head = forged(lambda f: f[5]['body']['pack']['methods'][0].update(ask_to='someone-else'))   # who is asked, changed in the pack as handed in
        self.assertEqual(self.words(lambda: J.replay(journal, head)), 'The journal does not replay at entry 5: the result differs (state)')
        journal, head = forged(lambda f: f[6]['body'].update(execute='true'))
        self.assertEqual(self.words(lambda: J.replay(journal, head)), 'The journal does not replay at entry 6: execute is true or false')
        journal, head = forged(lambda f: f[0]['body'].update(schema='journal/2'))
        self.assertTrue(self.words(lambda: J.replay(journal, head)).startswith('The journal does not replay at entry 0: A header holds'))

    def test_c4_an_entry_states_the_books_in_plain_and_they_follow_from_its_own_packs_and_receipts(self):
        run = started(ORDER, ['simulate_fact'])
        run.add('pack', {'pack': pack('140_levels_restated')})
        run.add('event', {'row': LOST, 'execute': True})
        run.add('look', {'execute': False})
        budget, slots, methods = {'compute': 10, 'money': 10, 'attention': 3}, {}, {}
        for e in J.parse(kept(run).text):   # no kernel below this line: the packs and the receipts the entries hold
            if e['kind'] == 'pack':
                budget.update(e['body']['pack'].get('budget', {}))
                slots.update(e['body']['pack'].get('providers', {}))
                methods.update({m['id']: m for m in e['body']['pack'].get('methods', [])})
            for b in e['result'].get('briefs', []):
                for x in b['receipts']:
                    slots[methods[x['method']]['provider']] -= 1
                    for dim, v in methods[x['method']]['cost'].items():
                        budget[dim] -= v
            self.assertEqual((e['result']['budget'], e['result']['providers']), (budget, slots), e['seq'])
        self.assertEqual((budget, slots, dict(run.state.budget), dict(run.state.providers)), ({'compute': 8, 'money': 8, 'attention': 3}, {'local-provider': 3}, budget, slots))

    def test_an_entry_is_enough_to_act_on_without_the_kernel(self):
        """Judge 2: a look or answer entry records the ledger row itself. A stopped run keeps the step and the reason,
        an ask keeps the party and the question, every receipt is kept in full, and a look is reported as its entry."""
        run = started(STOP, ['simulate_fact', 'compile_candidate'])
        e, r = run.journal[-1], last(run)
        b = e['result']['briefs'][0]
        self.assertEqual((b['status'], b['stopped'], b['pending'], len(b['receipts']), b['cost']),
                         ('STEP_STOPPED', {'method': 'construct-enquiry-candidate@1', 'reason': 'Handler refused: No declared constructor'}, ['construct-enquiry-candidate@1'], 3, r['cost']))
        self.assertEqual((canonical(b['receipts']), b['trace_root_sha256'], b['actions']), (canonical(r['model_receipts']), r['trace_root_sha256'], r['actions']))
        self.assertEqual(J.restart(kept(run)).head(), run.head())   # a stop is an outcome: it is sealed and it replays
        asked = started()
        b = asked.journal[-1]['result']['briefs'][0]
        self.assertEqual((b['receipts'][0]['ask']['to'], b['receipts'][0]['ask']['question'], b['waits'], b['pending']),
                         ('customer', 'May we send a replacement for the item that is out of stock?', ['ask-customer-approval@1'], ['ship-replacement@1']))
        e = asked.add('answer', yes(receipt_of(asked)))
        self.assertEqual((e['prev_sha256'], e['seq'], e['sha256']), (asked.journal[6]['sha256'], 7, asked.head()['sha256']))   # the head it rests on, its number, the head after
        self.assertEqual(e['result']['briefs'][0]['settled'], [{'operation': 'ASK_CLOSED', 'data': {'ask': QUESTION, 'receipt': receipt_of(asked)['sha256'], 'truth': 'TRUE', 'source': 'STAMP:customer'}}])
        self.assertEqual(set(e['result']), {'status', 'affected', 'briefs', 'state', 'budget', 'providers'})
        self.assertEqual(set(asked.journal[1]['result']), {'state', 'budget', 'providers'})

    # ------------------------------------------------------------------ C5: one writer
    def test_c5_of_two_runs_from_one_head_the_second_save_is_refused_and_changes_nothing(self):
        p1 = started()
        shared, receipt = kept(p1), receipt_of(p1)
        a, b = J.restart(shared), J.restart(shared)
        a.add('answer', yes(receipt, 'FALSE'))
        first = J.save(a, shared)
        was = shared.read()
        b.add('event', {'row': RECOUNT, 'execute': True})
        self.assertEqual(last(b)['status'], 'WAITING')   # b has not seen the no
        self.assertEqual(self.words(lambda: J.save(b, shared)), 'The journal moved on since this run was replayed (its head names 8 entries now): replay it and try again')
        self.assertEqual(shared.read(), was)
        b = J.restart(shared)                            # the loser replays and tries again
        self.assertEqual(b.base, first)
        b.add('event', {'row': RECOUNT, 'execute': True})
        self.assertEqual(last(b)['status'], 'REFUSED')
        self.assertEqual(J.save(b, shared)['length'], 9)
        self.assertEqual(J.save(b, shared)['length'], 9)                                    # nothing new: nothing is written
        other = J.Keep()                                                                    # a head is returned only for a keeper that holds it, also when nothing is new
        self.assertEqual(self.words(lambda: J.save(b, other)), MOVED.format('it has no head now'))
        self.assertEqual(other.read(), ('', None))
        idle, busy = J.restart(shared), J.restart(shared)
        busy.add('look', LOOK)
        J.save(busy, shared)
        self.assertEqual(self.words(lambda: J.save(idle, shared)), MOVED.format('its head names 10 entries now'))   # and not for a journal that moved on meanwhile
        shared = J.Keep(''.join(line + '\n' for line in shared.text.split('\n')[:9]), b.base)   # as it was kept before that look
        self.assertTrue(self.words(lambda: J.save(started(), shared)).startswith('The journal moved on'))   # a new journal never replaces a kept one
        headless = J.Keep(shared.text, None)
        self.assertEqual(self.words(lambda: J.save(started(), headless)), 'A journal stands here without a head: nothing is appended to it and nothing replaces it')
        self.assertEqual(headless.read(), (shared.text, None))
        lines = shared.text.split('\n')[:-1]                                                # the head is the same, but the kept text is no longer whole up to it
        edited = json.loads(lines[3])
        edited['body']['pack']['methods'][0]['cost']['money'] = 0                           # an entry under the head changed where it is kept, its hash left as it was
        remade = J.parse(shared.text)
        remade[8]['result']['status'] = 'OTHER'                                             # the last entry changed and the chain made again: whole, but not what the head names
        for text, said in (('\n'.join(lines[:8] + lines[7:8]) + '\n', 'The journal is broken at entry 8'), ('\n'.join(lines[:8] + ['{}']) + '\n', 'The journal is broken at entry 8'),
                           (J.dump(chained(remade)[0]), 'The journal does not end on the hash its head names'),
                           ('\n'.join(lines[:8]) + '\n', 'The journal ends before its head: 8 entries, the head names 9'), ('\n'.join(lines[:3] + [canonical(edited)] + lines[4:]) + '\n', 'The journal is broken at entry 3'),
                           ('\n'.join(lines[:8] + [lines[8].replace(shared.head['sha256'], '0' * 64)]) + '\n', 'The journal is broken at entry 8')):
            other = J.Keep(text, shared.head)
            b = J.restart(shared)
            b.add('look', LOOK)
            self.assertEqual(self.words(lambda: J.save(b, other)), said)                   # nothing is appended to it
            self.assertEqual(other.read(), (text, shared.head))

    def test_c5_two_interpreters_one_folder_the_entry_first_then_the_head(self):
        child = ("import sys,json;sys.path.insert(0,sys.argv[1]);from extensions import journal as J;keep=J.FileKeep(sys.argv[2]);run=J.restart(keep);"
                 "r=run.detail[6]['runs'][0]['model_receipts'][0];run.add('answer',{'receipt':r,'truth':'FALSE','source':'customer','execute':True});print(json.dumps(J.save(run,keep)))")
        with tempfile.TemporaryDirectory() as folder:
            keep = J.FileKeep(folder)
            self.assertEqual(self.words(lambda: J.restart(keep)), 'No head, no restart: the head is kept outside the journal, and none is kept here')
            head = J.save(started(), keep)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['journal.head', 'journal.jsonl'])
            self.assertEqual(json.loads((Path(folder) / 'journal.head').read_text()), head)   # the head is a file of its own, outside the text
            mine = J.restart(keep)                                    # this interpreter replays first ...
            other = subprocess.run([sys.executable, '-I', '-B', '-c', child, str(ROOT), folder], capture_output=True, text=True)
            self.assertEqual(other.returncode, 0, other.stderr)       # ... a second interpreter replays the same head, adds the customer's no and saves
            first = json.loads(other.stdout)
            self.assertEqual((first['length'], keep.read()[1]), (8, first))
            was = (Path(folder) / 'journal.jsonl').read_bytes()
            mine.add('look', LOOK)
            self.assertEqual(self.words(lambda: J.save(mine, keep)), 'The journal moved on since this run was replayed (its head names 8 entries now): replay it and try again')
            self.assertEqual(((Path(folder) / 'journal.jsonl').read_bytes(), keep.read()[1]), (was, first))
            mine = J.restart(keep)
            mine.add('look', LOOK)
            self.assertEqual(last(mine)['status'], 'REFUSED')
            (Path(folder) / 'journal.lock').write_bytes(b'')          # another writer is inside its one exclusive step
            self.assertEqual(self.words(lambda: J.save(mine, keep)), 'Another writer holds this journal: replay it and try again')
            (Path(folder) / 'journal.lock').unlink()
            replace = J.os.replace
            def dies(*a):
                raise OSError('the writer died between the entry and the head')
            J.os.replace = dies
            try:
                with self.assertRaises(OSError):
                    J.save(mine, keep)
            finally:
                J.os.replace = replace
            self.assertFalse((Path(folder) / 'journal.lock').exists())
            self.assertEqual((len(J.parse(keep.read()[0])), keep.read()[1]), (9, first))   # the entry is in the text, the head was not moved
            after = J.restart(keep)
            self.assertEqual((after.cut, after.head(), list(after.detail)[-1]), (1, first, 7))   # so it is past the head: reported, never run
            after.add('look', {'execute': False})
            self.assertEqual(J.save(after, keep)['length'], 9)
            self.assertEqual(J.parse(keep.read()[0])[8]['body'], {'execute': False})        # and cut by the next save

    def test_c5_four_interpreters_race_on_one_folder_and_every_save_is_taken_once(self):
        """One writer at a time by construction, under real concurrency: four interpreters, five rounds each. In a round a
        process restarts from the folder, adds one row and saves; when its save is refused it restarts and tries again."""
        child = ("import sys,json,time;sys.path.insert(0,sys.argv[1]);from extensions import journal as J;keep=J.FileKeep(sys.argv[2]);me=sys.argv[3];lost=0\n"
                 "for i in range(5):\n"
                 "    for attempt in range(2000):\n"
                 "        run=J.restart(keep)\n"
                 "        run.add('event',{'row':{'predicate':'substitute_stock','truth':'TRUE','version':me+'-'+str(i),'verified':True,'source':'fixture/stock-recount'},'execute':False})\n"
                 "        try:\n"
                 "            J.save(run,keep);break\n"
                 "        except ValueError as why:\n"
                 "            if 'moved on' not in str(why) and 'Another writer' not in str(why):raise\n"
                 "            lost+=1;time.sleep(0.001*(int(me)+1))\n"
                 "    else:raise SystemExit('no save was taken in 2000 tries')\n"
                 "print(json.dumps(lost))")
        with tempfile.TemporaryDirectory() as folder:
            keep = J.FileKeep(folder)
            J.save(started(), keep)
            mine = J.restart(keep)                                   # this interpreter replays before the race
            racers = [subprocess.Popen([sys.executable, '-I', '-B', '-c', child, str(ROOT), folder, str(n)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in range(4)]
            done = [p.communicate() for p in racers]
            self.assertEqual([p.returncode for p in racers], [0, 0, 0, 0], [err[-300:] for _, err in done])
            after = J.restart(keep)                                  # what is kept is one journal: whole, in order, on its head, and it replays
            rows = [e['body']['row']['version'] for e in after.journal if e['kind'] == 'event']
            self.assertEqual((after.head()['length'], after.cut, sorted(rows), sorted(os.listdir(folder))),
                             (27, 0, sorted(f'{n}-{i}' for n in range(4) for i in range(5)), ['journal.head', 'journal.jsonl']))   # every save taken once, none lost, none doubled
            self.assertTrue(all(type(json.loads(out)) is int for out, _ in done))
            mine.add('look', LOOK)                                   # and the one that replayed before the race is refused like any loser
            self.assertEqual(self.words(lambda: J.save(mine, keep)), 'The journal moved on since this run was replayed (its head names 27 entries now): replay it and try again')

    def test_c5_a_keeper_takes_only_whole_entries_that_end_on_the_head_handed_in(self):
        """A kept head never names text the keeper does not have: what is handed to a keeper is checked against the head
        handed in with it, in memory and in a folder, and a refusal changes nothing that is kept."""
        run = started()
        keep = kept(run)
        was = keep.read()
        run.add('look', LOOK)
        new, head = J.dump(run.journal[7:]), {'length': 8, 'sha256': run.journal[7]['sha256']}
        takes = TAKES

        def own(**changed):   # entry 7 changed and hashed again: it chains onto the kept head and its own hash is true
            e = dict(copy.deepcopy(run.journal[7]), **changed)
            e['sha256'] = digest({k: e[k] for k in J.COVERED})
            return J.dump([e]), {'length': 8, 'sha256': e['sha256']}
        loose = own(prev_sha256='0' * 64)                            # an entry with its own true hash that rests on another journal
        false = (J.dump([dict(run.journal[7], sha256='0' * 64)]), {'length': 8, 'sha256': '0' * 64})   # an entry whose hash is not the hash of what it holds
        bad = ((new, dict(head, length=9), takes), (new, dict(head, sha256=run.journal[6]['sha256']), takes), (new[:-1], head, takes), (new + new, head, takes), ('', head, takes),
               ('not json\n', head, takes), ('{}\n', head, takes), ('', was[1], takes), (*loose, takes), (*false, takes), (J.dump(run.journal[6:7]), {'length': 8, 'sha256': run.journal[6]['sha256']}, takes),
               (*own(kind='resume', body={}, result={}), takes), (*own(body={'execute': True, 'note': 'x'}), takes), (*own(body={'execute': 1}), takes), (*own(body={}), takes),   # what no reader would read: the keeper checks it before it moves the head
               (*own(kind='header', body={'kinds': KINDS, 'checkers': []}), takes), (*own(kind='pack', body={'pack': 'text'}), takes), (*own(extra=1), takes), (*own(result=[]), takes),
               (*own(kind='close', body={'next': 'orders-2'}), takes), (*own(stated={'code': {'kernel.core': 1}}), takes),
               (new, None, 'No head, no restart'), (new, [8, head['sha256']], 'No head, no restart'), (new, dict(head, more=1), 'No head, no restart'))
        with tempfile.TemporaryDirectory() as folder:
            files = J.FileKeep(folder)
            files.append(None, was[0], was[1])                       # the same seven entries, kept in a folder
            for k in (keep, files):
                for lines, at, said in bad:
                    self.assertTrue(self.words(lambda: k.append(was[1], lines, at)).startswith(said), (lines[:20], at))
                    self.assertEqual(k.read(), was)                  # a refused append changes nothing that is kept
                self.assertTrue(self.words(lambda: k.append({'length': 6, 'sha256': run.journal[5]['sha256']}, new, head)).startswith('The journal moved on'))
                k.append(was[1], new, head)
                self.assertEqual(k.read(), (was[0] + new, head))
                self.assertEqual(J.restart(k).head(), head)
            self.assertEqual(sorted(os.listdir(folder)), ['journal.head', 'journal.jsonl'])
            (Path(folder) / 'journal.head').write_bytes(b'[8]')      # what is kept as the head is not a head: no restart, and nothing is appended
            self.assertEqual(self.words(lambda: J.restart(files)), 'No head, no restart: what is kept as the head here is not a head')
            self.assertEqual(self.words(lambda: files.append(head, new, head)), 'No head, no restart: what is kept as the head here is not a head')
            self.assertFalse((Path(folder) / 'journal.lock').exists())
            (Path(folder) / 'journal.head').write_bytes(canonical(head).encode())
            (Path(folder) / 'journal.jsonl').write_bytes(b'\xff\xfe')   # a text that is not UTF-8
            self.assertEqual(self.words(lambda: J.restart(files)), 'The journal is broken: its text is not UTF-8')
        self.assertTrue(self.words(lambda: J.Keep(was[0], {'x': 1}).append({'x': 1}, new, head)).startswith('A keeper takes whole entries'))   # a keeper that was given no head of its own
        by_hand = J.Keep(*was)                                       # a limit, pinned: a keeper checks the chain and the shape of what it is handed, not what an entry did
        by_hand.append(was[1], *own(result=dict(run.journal[7]['result'], status='MADE-UP')))
        self.assertEqual(by_hand.head['length'], 8)
        self.assertEqual(self.words(lambda: J.restart(by_hand)), 'The journal does not replay at entry 7: the result differs (status)')   # only save() hands over a journal that has replayed

    # ------------------------------------------------------------------ C6: the doors
    def test_c6_a_pack_id_passes_the_door_once(self):
        run = started(ORDER, ['simulate_fact'])
        run.add('pack', {'pack': pack('140_levels_restated')})
        run.add('event', {'row': LOST, 'execute': True})
        was = (J.state_digest(run.state), len(run.journal), dict(run.state.budget))
        self.assertEqual(was[2], {'compute': 8, 'money': 8, 'attention': 3})
        self.assertEqual(self.words(lambda: run.add('pack', {'pack': pack('140_levels_restated')})), 'A hand-over passes the door once: a pack with the id "140_levels_restated" was already let in')
        self.assertEqual(self.words(lambda: run.add('pack', {'pack': dict(pack('140_levels_restated'), budget={'money': 99})})), 'A hand-over passes the door once: a pack with the id "140_levels_restated" was already let in')
        self.assertEqual((J.state_digest(run.state), len(run.journal), dict(run.state.budget)), was)
        run.add('look', LOOK)                                         # the refusal changed nothing: the run goes on
        odd, other = {'schema': 'sutra-extension/2', 'id': 'niveau-\u00e9t\u00e9'}, started(ORDER, ['simulate_fact'], look=False)
        other.add('pack', {'pack': odd})
        self.assertEqual(self.words(lambda: other.add('pack', {'pack': odd})), 'A hand-over passes the door once: a pack with the id "niveau-\u00e9t\u00e9" was already let in')   # the id as it is written
        s = State.from_packs([pack(n) for n in ORDER])                # the kernel alone takes it twice
        k = Kernel(s)
        k.run_standing(execute=True)
        s.apply(pack('140_levels_restated'))
        k.on_event(LOST, execute=True)
        s.apply(pack('140_levels_restated'))
        self.assertEqual((dict(s.budget), [p['pack'] for p in s.loaded].count('140_levels_restated')), ({'compute': 10, 'money': 10, 'attention': 3}, 2))
        entries = J.parse(kept(run).text)                             # a journal that holds it twice does not replay
        again = copy.deepcopy(entries[7])
        again['result']['state'] = entries[-1]['result']['state']
        journal, head = chained(entries + [again])
        self.assertEqual(self.words(lambda: J.replay(journal, head)), 'The journal does not replay at entry 10: A hand-over passes the door once: a pack with the id "140_levels_restated" was already let in')

    def test_c6_every_door_takes_exactly_its_keys_and_what_the_kernel_refuses_the_journal_refuses(self):
        run = started()
        receipt, was = receipt_of(run), (J.state_digest(run.state), run.head())
        other = dict(copy.deepcopy(receipt), ask=dict(receipt['ask'], to='someone-else'))
        ran = []

        class Sly(dict):   # an object that only looks like a dict: its code must never run
            def items(self):
                ran.append('items')
                return [('execute', True)]

            def keys(self):
                ran.append('keys')
                return ['execute']

        class Any:   # a kind that says it equals whatever it is compared with: only its type is read
            def __eq__(self, other):
                ran.append('eq')
                return True
            __hash__ = object.__hash__

            def __str__(self):
                return 'any kind'
        exact = 'The {} door takes exactly: {}'
        plain_data = 'An entry body is plain data (text, numbers, true, false, null, lists, objects with text keys), at most 19 levels deep and 100000 items'
        event_door = 'The event door lets in only verified rows that are not decisions, from a checker the header names'
        names = 'A closing entry names the journal that continues this one: its kinds and checkers (lists of names) and, if it has one, its name'
        for kind, body, said in (
                ('look', {'execute': 'false'}, 'execute is true or false'), ('look', {'execute': 1}, 'execute is true or false'), ('look', {'execute': None}, 'execute is true or false'),
                ('look', {'execute': True, 'note': 'x'}, exact.format('look', 'execute')), ('look', {}, exact.format('look', 'execute')),
                ('look', ('execute', True), plain_data), ('look', {1: True}, plain_data), ('look', Sly(execute=True), plain_data), ('look', {'execute': (True,)}, plain_data),
                ('look', {'execute': float('nan')}, plain_data), ('look', 'execute', plain_data), ('look', None, plain_data),
                ('pack', {'pack': [pack('03_approval')]}, 'A pack entry holds a pack'), ('pack', {'pack': pack('03_approval'), 'again': True}, exact.format('pack', 'pack')),
                ('pack', {'pack': {'schema': 'sutra-extension/1', 'id': 'old'}}, 'Invalid extension pack'), ('pack', {'pack': pack('80_ask_method')}, 'A hand-over passes the door once: a pack with the id "80_ask_method" was already let in'),
                ('event', {'row': RECOUNT}, exact.format('event', 'execute, row')), ('event', {'row': [RECOUNT], 'execute': True}, 'An event entry holds one row'),
                ('event', {'row': RECOUNT, 'execute': 'yes'}, 'execute is true or false'),
                ('event', {'row': dict(RECOUNT, source='the-hand'), 'execute': True}, event_door), ('event', {'row': dict(RECOUNT, verified=False), 'execute': True}, event_door),
                ('event', {'row': dict(RECOUNT, verified=1), 'execute': True}, event_door), ('event', {'row': dict(RECOUNT, predicate='customer_approved', final=True), 'execute': True}, event_door),
                ('event', {'row': dict(RECOUNT, truth='MAYBE'), 'execute': True}, 'Invalid observation'),
                ('answer', dict(yes(other), source='someone-else'), 'No open ask matches this receipt'), ('answer', dict(yes(receipt), source='someone-else'), 'The answer does not come from the party that was asked'),
                ('answer', dict(yes(receipt), truth='MAYBE'), 'An answer is TRUE or FALSE, from a named party, to an ask receipt'), ('answer', dict(yes(receipt), execute='yes'), 'execute is true or false'),
                ('answer', {'fact': 'customer_approved', 'truth': 'TRUE', 'source': 'customer', 'execute': True}, exact.format('answer', 'execute, receipt, source, truth')),
                ('answer', dict(yes(receipt), receipt=receipt['sha256']), 'An answer is TRUE or FALSE, from a named party, to an ask receipt'),
                ('resume', {'head': run.head()}, 'Unknown journal entry kind: resume'), (['look'], LOOK, "Unknown journal entry kind: ['look']"),
                ('header', {'kinds': KINDS, 'checkers': []}, 'A journal has one header, entry 0'), ('header', {'kinds': KINDS}, 'A header holds kinds and checkers (lists of names) and may hold a name and the head it continues'),
                ('close', {}, exact.format('close', 'next')), ('close', {'next': {'kinds': KINDS, 'checkers': []}, 'execute': True}, exact.format('close', 'next')),
                ('close', {'next': 'orders-2'}, names), ('close', {'next': {'kinds': KINDS}}, names), ('close', {'next': {'kinds': KINDS, 'checkers': [], 'name': 7}}, names),
                ('close', {'next': ['kinds', 'checkers']}, names), ('close', {'next': {'kinds': KINDS, 'checkers': [], 'name': ''}}, names), ('close', {'next': None}, names),
                ('x' * 60, {}, 'Unknown journal entry kind: ' + 'x' * 40), (Any(), LOOK, 'Unknown journal entry kind: any kind'),
                ('close', {'next': {'kinds': KINDS, 'checkers': [], 'continues': run.head()}}, names), ('close', {'next': {'kinds': [], 'checkers': []}}, names),
                ('close', {'next': {'kinds': ['ask'], 'checkers': []}}, 'A journal that continues another names the same action kinds'),
                ('close', {'next': {'kinds': list(reversed(KINDS)), 'checkers': []}}, 'A journal that continues another names the same action kinds')):
            self.assertEqual(self.words(lambda: run.add(kind, body)), said, (kind, body))
        self.assertEqual((ran, J.state_digest(run.state), run.head()), ([], *was))   # no code of the caller ran, nothing was sealed, nothing changed
        for value in ('false', 'true', 1, 0, None, [True]):                        # what the kernel's own door refuses, the journal's look door refuses
            with self.assertRaises(ValueError):
                Kernel(State.from_packs([pack(n) for n in ASK])).run_standing(execute=value)
            self.assertEqual(self.words(lambda: run.add('look', {'execute': value})), 'execute is true or false')
        run.add('look', {'execute': False})                                          # the run is still usable
        e = run.add('answer', yes(receipt))
        self.assertEqual(canonical(e['body']['receipt']), canonical(receipt))        # the stamp is the receipt the caller presented
        for bad in (dict(kinds=[]), dict(kinds=['simulate_fact', 'simulate_fact']), dict(kinds='ask'), dict(kinds=KINDS, checkers='x'), dict(kinds=KINDS, checkers=[1]), dict(kinds=['no-such-kind']),
                    dict(name=7), dict(name=['restart']), dict(checkers=['fixture/courier', 'fixture/courier']), dict(checkers=['']), dict(kinds=[''])):
            with self.assertRaises(ValueError):
                J.start(**dict({'kinds': KINDS, 'checkers': []}, **bad))
        nest = lambda n: [nest(n - 1)] if n else 0
        nested = lambda n: {'pack': {'schema': 'sutra-extension/2', 'id': f'nest-{n}', 'note': nest(n)}}
        room = started(look=False)
        self.assertEqual(room.add('pack', nested(17))['seq'], 6)                         # a pack may nest as deep in an entry as at the kernel's own door ...
        self.assertEqual(self.words(lambda: room.add('pack', nested(18))), plain_data)   # ... and one level more is refused here, in the journal's words
        State.from_packs([nested(17)['pack']])
        self.assertEqual(self.words(lambda: State.from_packs([nested(18)['pack']])), 'Not a plain JSON object')
        bare = J.start(KINDS)                                                        # the header of a journal that names no checker and has no name
        self.assertEqual((bare.journal[0]['body'], set(bare.journal[0]['result'])), ({'kinds': KINDS, 'checkers': []}, {'state', 'budget', 'providers'}))
        self.assertEqual(self.words(lambda: bare.add('event', {'row': RECOUNT, 'execute': True})), event_door)   # so its event door lets in no row at all
        self.assertEqual(J.start(tuple(KINDS), tuple(CHECKERS), name='').journal[0]['body'], {'kinds': KINDS, 'checkers': CHECKERS})   # tuples are taken as lists, and no name is no name
        self.assertEqual(J.start(KINDS, CHECKERS, name='orders').journal[0]['body'], {'kinds': KINDS, 'checkers': CHECKERS, 'name': 'orders'})

    def test_c6_a_state_changed_outside_the_journal_is_refused_at_the_next_add(self):
        p1 = started()
        keep, receipt = kept(p1), receipt_of(p1)
        refused = 'The State was changed outside the journal after entry 6'
        seen = 0
        for field in dataclasses.fields(State):        # every field of the State, changed by hand in every way its type allows
            for mutant in mutants(getattr(J.restart(keep).state, field.name)):
                r = J.restart(keep)
                setattr(r.state, field.name, mutant)
                self.assertEqual(self.words(lambda: r.add('look', LOOK)), refused, field.name)
                self.assertEqual(self.words(r.head), refused, field.name)
                self.assertEqual(len(r.journal), 7)
                seen += 1
        self.assertGreaterEqual(seen, 2 * len(dataclasses.fields(State)))
        for bypass in (lambda r: r.state.apply(pack('03_approval')), lambda r: r.state.observe(dict(RECOUNT, version='9')), lambda r: Kernel(r.state).resolve('order_complete'),
                       lambda r: Kernel(r.state).run_standing(execute=False), lambda r: Kernel(r.state).on_event(RECOUNT, execute=True),
                       lambda r: answer(Kernel(r.state), receipt, 'TRUE', 'customer', execute=True)):     # the kernel's doors called directly
            r = J.restart(keep)
            bypass(r)
            self.assertEqual(self.words(lambda: r.add('look', LOOK)), refused)
            self.assertEqual(self.words(lambda: J.save(r, keep)), refused)
        r = J.restart(keep)
        r.state.goals.append(object())                 # what no journal can record is a change like any other
        self.assertEqual((self.words(lambda: r.add('look', LOOK)), self.words(r.head), self.words(lambda: J.state_digest(r.state))), (refused, refused, 'The State holds what a journal cannot record'))
        after = J.restart(keep)                        # after a restart the bypass never happened
        self.assertEqual((list(open_asks(after.state)), dict(after.state.budget), after.head()), ([QUESTION], {'compute': 10, 'money': 10, 'attention': 2}, keep.head))

    # ------------------------------------------------------------------ C7: what a head covers
    def test_c7_the_digest_is_over_named_views_and_an_empty_view_is_left_out(self):
        new = J.views(State())
        self.assertEqual(new, {'scope': 'orgA/fulfillment', 'budget': {'compute': 10, 'money': 10, 'attention': 3}, 'preference': ['compute', 'money', 'attention'], 'kinds': list(ACTIONS)})
        self.assertEqual(J.state_digest(State()), digest(new))
        rich = started(['30_build_goal', '31_build_theory', '32_builder_components'], ['simulate_fact', 'compile_candidate', 'ask'])   # the packs of case 15: a candidate is made
        rich.add('pack', {'pack': pack('50_unapproved_semantics')})
        rich.add('pack', {'pack': pack('80_ask_method')})
        rich.add('pack', {'pack': dict(pack('00_goal'), id='goals-again', goals=['customer_approved', 'capability_candidate_created'], scope='orgA/enquiries')})
        rich.add('pack', {'pack': {'schema': 'sutra-extension/2', 'id': 'rule', 'rules': [{'id': 'R@1', 'head': 'x', 'branches': [['y']], 'approved': True}], 'grants': ['action:x']}})
        rich.add('look', LOOK)
        full = J.views(rich.state)
        self.assertEqual(sorted(full), sorted(['scope', 'goals', 'evidence', 'rules', 'proposed', 'methods', 'constructors', 'providers', 'grants', 'budget', 'preference', 'candidates',
                                               'loaded', 'history', 'books', 'kinds']))   # every view has something in it here
        for s in (State(), started(look=False).state, rich.state):
            self.assertTrue(all(v not in ('', [], {}, None) for v in J.views(s).values()))
        # The guard is a mutation test: any field of the State, changed by hand, changes the digest. No field is named.
        for state in (rich.state, started().state, State()):
            for field in dataclasses.fields(State):
                changes = list(mutants(getattr(state, field.name)))
                self.assertTrue(changes, field.name)
                for mutant in changes:
                    other = copy.deepcopy(state, {id(state.actions): state.actions})
                    setattr(other, field.name, mutant)
                    self.assertNotEqual(J.state_digest(other), J.state_digest(state), field.name)
        self.assertEqual(self.words(lambda: J.state_digest(dataclasses.replace(State(), goals=[object()]))), 'The State holds what a journal cannot record')

    def test_c7_the_code_is_stated_beside_the_entry_and_a_head_covers_no_file_hash(self):
        run = started()
        keep = kept(run)
        text, head = keep.read()
        entries = J.parse(text)
        files = {name: hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest() for name in ('kernel.core', 'extensions.asks', 'extensions.journal')}
        self.assertEqual(J.code_now(KINDS), files)                                          # computed here from the loaded modules, taken from no caller
        self.assertEqual(sorted(J.code_now(['simulate_fact'])), ['extensions.journal', 'kernel.core'])
        self.assertEqual([(e['seq'], e['stated']) for e in entries if 'stated' in e], [(0, {'code': files})])   # said once
        covered = canonical([{k: e[k] for k in J.COVERED} for e in entries])
        self.assertTrue(all(sha not in covered for sha in files.values()))                  # no file hash under the head
        self.assertEqual(set(entries[0]['body']), {'kinds', 'checkers', 'name'})            # and no schema name
        self.assertTrue(all(e['sha256'] == digest({k: e[k] for k in J.COVERED}) for e in entries))
        other = copy.deepcopy(entries)
        other[0]['stated']['code']['kernel.core'] = '0' * 64                                # the journal says it was written under another kernel file
        r = J.replay(other, head)
        self.assertEqual((r.head(), r.notice, J.state_digest(r.state)), (head, [{'entry': 0, 'differs': ['kernel.core']}], entries[-1]['result']['state']))   # the same head, a notice, no refusal
        self.assertEqual(r.add('look', LOOK)['stated'], {'code': files})                    # the code that continues says so, once
        self.assertNotIn('stated', r.add('look', LOOK))
        bare = [{k: v for k, v in e.items() if k != 'stated'} for e in entries]             # a journal that states nothing replays too
        self.assertEqual(J.replay(bare, head).notice, [])
        made = Kernel.__init__                                                              # what refuses is a result that does not come out again

        def narrow(self, state):
            made(self, state)
            self.limit = 1
        Kernel.__init__ = narrow
        try:
            said = self.words(lambda: J.replay(entries, head))
        finally:
            Kernel.__init__ = made
        self.assertEqual(said, 'The journal does not replay at entry 6: the result differs (briefs, budget, providers, state)')
        self.assertEqual(J.replay(entries, head).head(), head)

    # ------------------------------------------------------------------ C8: continuing a journal is a write to it; a chain of journals
    def test_c8_a_new_journal_cites_the_head_it_continues_and_the_chain_reads_as_one_record(self):
        j1 = started(ORDER, ['simulate_fact'], name='orders-1')
        keep1, keep2 = J.Keep(), J.Keep()
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, continues=j1)), 'Continuing a journal is a write to it: name where it is kept')
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, keep=keep1)), 'A keeper is named with the journal that is continued; a new journal is kept by save()')
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, continues=keep1, keep=keep1)), 'A journal continues a run that was replayed or started here')
        self.assertEqual(self.words(lambda: J.start(KINDS, CHECKERS, continues=j1, keep=keep1)), 'A journal that continues another names the same action kinds')
        self.assertEqual(self.words(lambda: J.start(['no-such-kind'], CHECKERS, continues=j1, keep=keep1)), 'A journal that continues another names the same action kinds')
        self.assertEqual((j1.stopped, len(j1.journal), keep1.read()), (False, 7, ('', None)))        # each refused before anything was sealed or kept
        j2 = J.start(['simulate_fact'], CHECKERS, name='orders-2', continues=j1, keep=keep1)        # the closing entry, with everything not yet saved before it: one compare-and-append
        close = j1.journal[7]
        self.assertEqual((close['kind'], close['body'], close['result']),
                         ('close', {'next': {'kinds': ['simulate_fact'], 'checkers': CHECKERS, 'name': 'orders-2'}}, {k: j1.journal[6]['result'][k] for k in ('state', 'budget', 'providers')}))
        self.assertEqual((keep1.head, j1.base, j1.closed, j1.stopped), ({'length': 8, 'sha256': close['sha256']}, keep1.head, True, J.CLOSED))
        self.assertEqual((j2.journal[0]['body']['continues'], j2.journal[0]['result']['state'], j2.journal[0]['prev_sha256'], len(j2.journal)), (keep1.head, close['result']['state'], 'GENESIS', 1))
        self.assertEqual(self.words(lambda: j1.add('look', LOOK)), CLOSED_RUN)                       # one writer: the journal that was continued takes no more entries
        j2.add('look', LOOK)
        self.assertEqual((last(j2)['status'], dict(j2.state.budget)), ('SUPPORTED_BY_EVIDENCE', {'compute': 8, 'money': 8, 'attention': 3}))   # it did not start from the packs
        self.assertEqual(self.words(lambda: j2.add('pack', {'pack': pack('03_approval')})), 'A hand-over passes the door once: a pack with the id "03_approval" was already let in')
        j2.add('event', {'row': LOST, 'execute': True})
        self.assertEqual((dict(j2.state.budget), dict(j1.state.budget), j1.head()), ({'compute': 6, 'money': 6, 'attention': 3}, {'compute': 8, 'money': 8, 'attention': 3}, keep1.head))   # on a State of its own
        head2 = J.save(j2, keep2)                                                                # the head is quoted after the whole chain replayed on a shadow run
        r = J.restart(keep2, before=J.restart(keep1))
        self.assertEqual((J.state_digest(r.state), r.head(), dict(r.state.budget)), (J.state_digest(j2.state), head2, {'compute': 6, 'money': 6, 'attention': 3}))
        r.add('look', LOOK)
        self.assertEqual(J.save(r, keep2)['length'], 4)
        self.assertEqual(self.words(lambda: J.restart(keep2)), 'This journal continues another one: hand that journal in first, replayed to the head this header cites')
        open1 = J.Keep(''.join(line + '\n' for line in keep1.text.split('\n')[:7]), {'length': 7, 'sha256': j1.journal[6]['sha256']})   # journal 1 as it was kept before it was closed
        self.assertEqual(self.words(lambda: J.restart(keep2, before=J.restart(open1))), NOT_CLOSED)
        self.assertEqual(self.words(lambda: J.restart(keep2, before=keep1)), NOT_CLOSED)
        self.assertEqual(self.words(lambda: J.restart(keep1, before=J.restart(keep1))), NO_CITE)
        unsaved = J.replay(j1.journal, keep1.head)                                               # a run of journal 1 that is closed but not saved up to that head
        unsaved.base = {'length': 7, 'sha256': j1.journal[6]['sha256']}
        self.assertEqual(self.words(lambda: J.restart(keep2, before=unsaved)), 'The journal before is not saved up to the head this header cites: the entry first, then the head, then the journal that continues it')
        j3 = J.start(['simulate_fact'], CHECKERS, continues=J.restart(keep2, before=J.restart(keep1)), keep=keep2)   # and a third on the second, one that has no name
        self.assertEqual((J.parse(keep2.text)[4]['body'], 'name' in j3.journal[0]['body']), ({'next': {'kinds': ['simulate_fact'], 'checkers': CHECKERS}}, False))
        j3.add('look', LOOK)
        keep3 = kept(j3)
        self.assertEqual(J.restart(keep3, before=J.restart(keep2, before=J.restart(keep1))).head(), keep3.head)
        whole = [keep1.read(), keep2.read(), keep3.read()]
        self.assertEqual([[e['kind'] for e in j['entries']][-1] for j in R.record(whole)], ['close', 'close', 'look'])
        self.assertEqual([len(j['entries']) for j in R.record(whole)], [8, 5, 2])
        self.assertEqual(R.counts(whole)['steps']['orgA/fulfillment|ship-replacement@1']['ran'], 2)
        self.assertEqual([r['what'] for r in R.ledger(whole)].count('handed_in'), 6)             # five packs and one row: a closing entry is no row
        self.assertEqual(self.words(lambda: R.record(whole[1:])), 'This record starts in the middle: its first journal continues another')
        self.assertEqual(self.words(lambda: R.record([whole[0], whole[2]])), NOT_ONE_RECORD)
        self.assertEqual(self.words(lambda: R.record([open1.read(), whole[1]])), NOT_ONE_RECORD)
        two = J.parse(keep2.text)                                                                # the adapter holds each link of the chain by itself: the name, the citation, the State
        for change in (lambda f: f[0]['body'].update(name='orders-2b'), lambda f: f[0]['body']['continues'].update(length=7), lambda f: f[0]['body']['continues'].update(sha256=j1.journal[6]['sha256']),
                       lambda f: f[0]['result'].update(state='0' * 64), lambda f: f[0]['body'].update(checkers=[])):
            forged = copy.deepcopy(two)
            change(forged)
            journal, head = chained(forged)
            self.assertEqual(self.words(lambda: R.record([whole[0], (J.dump(journal), head)])), NOT_ONE_RECORD)
        one = J.parse(keep1.text)                                                                # and the closing entry by its shape and its place
        for change, at in ((lambda f: f[7]['body'].update(next='orders-2'), 7), (lambda f: f[7]['body']['next'].pop('checkers'), 7), (lambda f: f[7]['body'].update(note='x'), 7),
                           (lambda f: f[7]['body'].update(next=['kinds', 'checkers']), 7), (lambda f: f[7]['body']['next'].update(continues=7), 7),
                           (lambda f: f.append(copy.deepcopy(f[6])), 8)):
            forged = copy.deepcopy(one)
            change(forged)
            journal, head = chained(forged)
            self.assertEqual(self.words(lambda: R.ledger([(J.dump(journal), head)])), f'The journal is broken at entry {at}')
        journal, head = chained(one + [copy.deepcopy(one[6])])                                   # an entry after the closing entry: no reader reads it and no replay runs it
        for read in (lambda: J.replay(journal, head), lambda: J.restart(J.Keep(J.dump(journal), head))):
            self.assertEqual(self.words(read), 'The journal is broken at entry 8')
        journal, head = chained(one[:7] + [dict(one[7], body={'next': {'kinds': ['ask'], 'checkers': []}})])   # closed in the name of a journal of other kinds
        self.assertEqual(self.words(lambda: J.replay(journal, head)), 'The journal does not replay at entry 7: A journal that continues another names the same action kinds')

    def test_c8_continuing_a_journal_is_a_write_to_it_so_a_second_writer_and_a_second_continuation_are_refused(self):
        """Refuter 1 of the build, finding 1: the double spend. A level is handed in for one shipment. Three runs replay
        journal 1 from one head. One continues it and ships. Of the other two, one ships in memory and saves, and one
        continues the journal under another name: both are refused, nothing kept changes, and after replaying they
        hold a closed journal that takes no entry, from a run or at its keeper."""
        j1 = started(ORDER, ['simulate_fact'], name='orders-1')
        j1.add('pack', {'pack': {'schema': 'sutra-extension/2', 'id': 'level:one-shipment', 'budget': {'compute': 2, 'money': 2}}})
        keep1 = kept(j1)
        a, b, c = J.restart(keep1), J.restart(keep1), J.restart(keep1)
        ja = J.start(['simulate_fact'], CHECKERS, name='orders-2', continues=a, keep=keep1)
        was = keep1.read()
        self.assertEqual((was[1]['length'], J.parse(was[0])[8]['kind'], a.closed), (9, 'close', True))
        ja.add('event', {'row': LOST, 'execute': True})
        keep_a = kept(ja)
        self.assertEqual((last(ja)['actions'], dict(ja.state.budget)), (['ship-replacement@1'], {'compute': 0, 'money': 0, 'attention': 3}))   # the one shipment the level was handed in for
        b.add('event', {'row': LOST, 'execute': True})                                           # the second run has not seen the closing: it ships too, in memory
        self.assertEqual((last(b)['actions'], dict(b.state.budget)), (['ship-replacement@1'], {'compute': 0, 'money': 0, 'attention': 3}))
        self.assertEqual(self.words(lambda: J.save(b, keep1)), MOVED.format('its head names 9 entries now'))
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, name='orders-2b', continues=c, keep=keep1)), MOVED.format('its head names 9 entries now'))   # a second continuation of the same head
        self.assertEqual((keep1.read(), c.closed, len(c.journal)), (was, True, 9))                 # nothing kept changed; what the loser sealed, it sealed in memory
        self.assertEqual(self.words(lambda: c.add('look', LOOK)), CLOSED_RUN)
        again = J.restart(keep1)                                                                 # the loser replays: the journal is closed
        self.assertEqual((again.closed, again.stopped, again.cut, again.head()), (True, J.CLOSED, 0, was[1]))
        for kind, body in (('event', {'row': LOST, 'execute': True}), ('pack', {'pack': pack('140_levels_restated')}), ('look', LOOK), ('close', {'next': {'kinds': ['simulate_fact'], 'checkers': []}})):
            self.assertEqual(self.words(lambda: again.add(kind, body)), CLOSED_RUN)
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, name='orders-2b', continues=again, keep=keep1)), NAMES_ANOTHER)
        self.assertEqual(self.words(lambda: J.start(['simulate_fact'], [], name='orders-2', continues=again, keep=keep1)), NAMES_ANOTHER)
        self.assertEqual((keep1.read(), J.save(again, keep1)), (was, was[1]))
        stray = dict(copy.deepcopy(ja.journal[1]), seq=9, prev_sha256=was[1]['sha256'])            # by hand, past every door of a run: a whole entry that chains onto the closing entry
        stray.pop('stated', None)
        stray['sha256'] = digest({k: stray[k] for k in J.COVERED})
        with tempfile.TemporaryDirectory() as folder:
            files = J.FileKeep(folder)
            files.append(None, *was)
            for keeper in (keep1, files):
                self.assertEqual(self.words(lambda: keeper.append(was[1], J.dump([stray]), {'length': 10, 'sha256': stray['sha256']})), CLOSED_KEPT)
                self.assertEqual(keeper.read(), was)
            self.assertEqual((J.restart(files).closed, sorted(os.listdir(folder))), (True, ['journal.head', 'journal.jsonl']))
        chain = J.restart(keep_a, before=J.restart(keep1))                                       # what is kept is one record with one shipment after the level
        self.assertEqual((dict(chain.state.budget), R.counts([keep1.read(), keep_a.read()])['steps']['orgA/fulfillment|ship-replacement@1']['ran']), ({'compute': 0, 'money': 0, 'attention': 3}, 2))
        # The journal that is named may be started again from the closed one (the process that closed it may have died before it kept the new header).
        # It is the same header, byte for byte, and where journal 2 is kept already the keeper refuses it. A known limit, pinned: an empty keeper takes it,
        # because where a journal is kept is not in the journal.
        twin = J.start(['simulate_fact'], CHECKERS, name='orders-2', continues=J.restart(keep1), keep=keep1)
        self.assertEqual((canonical(twin.journal[0]), keep1.read()), (canonical(ja.journal[0]), was))
        self.assertEqual(self.words(lambda: J.save(twin, keep_a)), MOVED.format('its head names 2 entries now'))
        self.assertEqual(J.save(twin, J.Keep())['length'], 1)

    def test_c8_a_continuation_that_is_refused_leaves_the_run_before_it_as_it_was(self):
        """Refuter 1 of the build, finding 2: a continuation is replayed on a State of its own, so a journal that is
        refused part way changes nothing a caller still holds, and the honest journal still replays on the same run."""
        j1 = started(ORDER, ['simulate_fact'], name='orders-1')
        keep1 = J.Keep()
        j2 = J.start(['simulate_fact'], CHECKERS, name='orders-2', continues=j1, keep=keep1)
        j2.add('event', {'row': LOST, 'execute': True})
        honest = copy.deepcopy(j2.journal)
        r1 = J.restart(keep1)
        told = lambda: (J.state_digest(r1.state), dict(r1.state.budget), dict(r1.state.providers), r1.head(), r1.stopped, len(r1.journal), r1.base)
        was = told()
        self.assertEqual(was[1:5], ({'compute': 8, 'money': 8, 'attention': 3}, {'local-provider': 4}, keep1.head, J.CLOSED))
        for change, said in ((lambda f: f[1]['result']['budget'].update(money=9), 'The journal does not replay at entry 1: the result differs (budget)'),   # refused after the shipment ran
                             (lambda f: f[1]['body']['row'].update(source='the-hand'), 'The journal does not replay at entry 1: The event door lets in only verified rows that are not decisions, from a checker the header names'),
                             (lambda f: f[0]['result'].update(state='0' * 64), 'The journal does not replay at entry 0: the result differs (state)'),     # the header of a continuing journal is computed again too
                             (lambda f: f[0]['result']['budget'].update(money=10), 'The journal does not replay at entry 0: the result differs (budget)'),
                             (lambda f: f[0]['body'].update(name='orders-2b'), NOT_ITS_NEXT),
                             (lambda f: f[0]['body'].update(checkers=[]), NOT_ITS_NEXT),
                             (lambda f: f[0]['body']['continues'].update(length=7), NO_CITE),
                             (lambda f: f[0]['body'].pop('continues'), NO_CITE)):
            forged = copy.deepcopy(honest)
            change(forged)
            journal, head = chained(forged)
            self.assertEqual(self.words(lambda: J.replay(journal, head, before=r1)), said)
            self.assertEqual(told(), was)                                                        # the run handed in is as it was
        again = J.replay(honest, {'length': 2, 'sha256': honest[1]['sha256']}, before=r1)        # and the honest journal still replays on it
        again.add('look', LOOK)
        self.assertEqual((dict(again.state.budget), told()), ({'compute': 6, 'money': 6, 'attention': 3}, was))   # nor does anything the continuation does later reach it
        self.assertIsNot(again.state.actions, r1.state.actions)                                  # not even through the registry
        r1.state.budget['money'] = 9                                                             # a closed run is held to its State like one that takes entries
        refused = 'The State was changed outside the journal after entry 7'
        self.assertEqual((self.words(r1.head), self.words(lambda: J.replay(honest, {'length': 2, 'sha256': honest[1]['sha256']}, before=r1)), self.words(lambda: J.save(r1, keep1))), (refused,) * 3)

    # ------------------------------------------------------------------ C9: the record read back without the kernel
    def test_c9_ledger_rows_and_counts_are_read_from_the_text_alone_and_cite_their_entries(self):
        run = started(name='ledger')
        receipt = receipt_of(run)
        for kind, body in (('look', LOOK), ('event', {'row': RECOUNT, 'execute': True}), ('answer', yes(receipt)), ('look', LOOK), ('look', LOOK), ('look', {'execute': False})):
            run.add(kind, body)
        keep = kept(run)
        text, head = keep.read()
        entries = J.parse(text)
        journal = entries[0]['sha256'][:12]
        rows = R.ledger([(text, head)])
        self.assertEqual([(r['what'], r['entry']) for r in rows],
                         [('handed_in', n) for n in range(1, 6)] + [('ran', 6), ('asked', 6), ('ran', 7), ('handed_in', 8), ('ran', 8), ('decided', 9), ('ran', 9), ('ran', 10), ('ran', 11), ('ran', 12)])
        self.assertTrue(all(r['journal'] == journal and r['sha256'] == entries[r['entry']]['sha256'] for r in rows))   # every row cites its entry by number and hash
        asked, decided = [r for r in rows if r['what'] == 'asked'][0], [r for r in rows if r['what'] == 'decided'][0]
        self.assertEqual((asked['to'], asked['question'], asked['receipt'], asked['run']), ('customer', receipt['ask']['question'], receipt['sha256'], f'{journal}:6.0'))
        self.assertEqual((decided['truth'], decided['by'], decided['answers'], decided['asked_at']),
                         ('TRUE', 'customer', receipt['sha256'], {'journal': journal, 'entry': 6, 'sha256': entries[6]['sha256'], 'run': f'{journal}:6.0'}))
        shipped = [r for r in rows if r['what'] == 'ran' and r['entry'] == 9][0]
        self.assertEqual((shipped['status'], shipped['actions'], shipped['cost'], shipped['executed'], shipped['trace_root_sha256']),
                         ('LOCAL_MODEL_EFFECTS_RECORDED', ['ship-replacement@1'], {'compute': 2, 'money': 2, 'attention': 0}, True, run.detail[9]['runs'][0]['trace_root_sha256']))
        self.assertEqual(rows[0]['pack_sha256'], digest(pack('00_goal')))
        got = R.counts([(text, head)])
        goal, step = got['goals']['orgA/fulfillment|order_complete'], got['steps']['orgA/fulfillment|ship-replacement@1']
        self.assertEqual((goal['looked'], goal['executed'], goal['statuses']), (7, 6, {'WAITING': 3, 'LOCAL_MODEL_EFFECTS_RECORDED': 1, 'SUPPORTED_BY_EVIDENCE': 2, 'PLAN_READY': 1}))
        self.assertEqual([(a['entry'], a['sha256']) for a in goal['at']], [(n, entries[n]['sha256']) for n in range(6, 13)])
        self.assertEqual((step['ran'], [(a['entry'], a['what']) for a in step['at']]), (1, [(9, 'ran')]))
        self.assertLess(len(goal['trace_roots']), goal['looked'])                       # looks that find the same thing are one trace: counted by entry, never by root
        self.assertEqual(len({run.detail[n]['runs'][0]['trace_root_sha256'] for n in (10, 11)}), 1)
        early = R.counts([(text, {'length': 9, 'sha256': entries[8]['sha256']})])       # the counts as of an earlier head: hand in that head
        self.assertEqual((early['goals']['orgA/fulfillment|order_complete']['looked'], 'orgA/fulfillment|ship-replacement@1' in early['steps']), (3, False))
        stopped = started(STOP, ['simulate_fact', 'compile_candidate'], name='stops')   # a step that stops is counted as stopped, where it stopped
        stopped.add('look', LOOK)
        steps = R.counts([kept(stopped).read()])['steps']
        self.assertEqual((steps['orgA/enquiries|construct-enquiry-candidate@1']['stopped'], [a['entry'] for a in steps['orgA/enquiries|construct-enquiry-candidate@1']['at']],
                          steps['orgA/enquiries|validate-field@1']['ran']), (2, [4, 5], 1))
        again = started('81_made_again'.split(), ['simulate_fact'], name='skips')        # a step that is already true at its turn is counted as skipped
        again.add('event', {'row': {'predicate': 'quote_ready', 'truth': 'FALSE', 'version': '2', 'verified': True, 'source': 'fixture/courier'}, 'execute': True})
        steps = R.counts([kept(again).read()])['steps']
        self.assertEqual({k.split('|')[1]: (v['ran'], v['skipped']) for k, v in steps.items()}, {'prepare-quote@1': (2, 0), 'assume-approval@1': (1, 1), 'ship-quoted@1': (1, 1)})
        for bad_text, bad_head, said in ((text, {'length': 13, 'sha256': entries[11]['sha256']}, 'The journal does not end on the hash its head names'),
                                         (text.replace('WAITING', 'WAITED', 1), head, 'The journal is broken at entry 6'), (text, None, 'No head, no read: a head is {length, sha256} and is kept outside the journal'),
                                         (''.join(line + '\n' for line in text.split('\n')[:5]), head, 'The journal ends before its head: 5 entries, the head names 13')):
            self.assertEqual(self.words(lambda: R.ledger([(bad_text, bad_head)])), said)   # the adapter computes the chain again itself
        for change, at in ((lambda f: f[7].update(kind='credit'), 7), (lambda f: f[7]['body'].update(note='x'), 7), (lambda f: f[6]['body'].update(execute='true'), 6),
                           (lambda f: f[0]['body'].update(schema='journal/2'), 0), (lambda f: f[3].update(kind='header'), 3), (lambda f: f[8].update(body=[RECOUNT]), 8)):
            forged = copy.deepcopy(entries)                                             # re-chained by a forger, so whole and on its head: read only as the journal's own kinds, each with its keys
            change(forged)
            self.assertEqual(self.words(lambda: R.counts([(J.dump(chained(forged)[0]), chained(forged)[1])])), f'The journal is broken at entry {at}')
        forged = copy.deepcopy(entries)
        del forged[6]['result']['briefs'][0]['receipts']                                # a result that does not hold what a row needs is named: a refusal, never a KeyError
        for read in (R.ledger, R.counts):
            self.assertEqual(self.words(lambda: read([(J.dump(chained(forged)[0]), chained(forged)[1])])), f'Entry 6 of journal {journal} does not hold what the record reads from it')
        child = ("import sys,json;sys.path.insert(0,sys.argv[1]);from extensions import journal_record as R;text,head=json.loads(sys.stdin.read());"
                 "print(json.dumps([sorted(m for m in sys.modules if m.split('.')[0] in ('kernel','tools') or m=='extensions.journal'),R.ledger([(text,head)]),R.counts([(text,head)])]))")
        alone = subprocess.run([sys.executable, '-I', '-B', '-c', child, str(ROOT)], input=json.dumps([text, head]), capture_output=True, text=True)
        self.assertEqual(alone.returncode, 0, alone.stderr)
        self.assertEqual(json.loads(alone.stdout), [[], json.loads(json.dumps(rows)), json.loads(json.dumps(got))])   # a second interpreter, with no kernel loaded, reads the same rows

    def test_c9_a_ran_row_says_what_is_pending_and_the_adapter_reads_only_the_text_the_journal_writes(self):
        """Refuter 2 of the build, finding 5: what the adapter gives and refuses, held by unit tests of its own."""
        run = started(name='ledger')
        receipt = receipt_of(run)
        for kind, body in (('look', LOOK), ('answer', yes(receipt)), ('look', LOOK), ('look', LOOK)):
            run.add(kind, body)
        text, head = kept(run).read()
        rows = {r['entry']: r for r in R.ledger([(text, head)]) if r['what'] == 'ran'}
        self.assertEqual((rows[6]['pending'], rows[6]['waits'], rows[6]['executed'], 'settled' in rows[6]), (['ship-replacement@1'], ['ask-customer-approval@1'], True, False))   # the run that asked
        self.assertEqual((rows[7]['pending'], rows[7]['waits'], rows[7]['receipts']), (['ship-replacement@1'], ['ask-customer-approval@1'], []))                                   # the look that waited
        self.assertEqual(rows[8]['settled'], [{'operation': 'ASK_CLOSED', 'data': {'ask': QUESTION, 'receipt': receipt['sha256'], 'truth': 'TRUE', 'source': 'STAMP:customer'}}])     # the run the yes started
        self.assertEqual(('pending' in rows[8], 'waits' in rows[8], rows[8]['receipts']), (False, False, [run.detail[8]['runs'][0]['model_receipts'][0]['sha256']]))
        goal = R.counts([(text, head)])['goals']['orgA/fulfillment|order_complete']
        roots = [run.detail[n]['runs'][0]['trace_root_sha256'] for n in range(6, 11)]
        self.assertEqual(goal['trace_roots'], list(dict.fromkeys(roots)))                # every trace root once, in the order it was first seen
        self.assertEqual((goal['looked'], len(goal['trace_roots']) < 5), (5, True))
        stopped = started(STOP, ['simulate_fact', 'compile_candidate'], name='stops')    # a run that stopped: the step, the reason and what is pending are on its row
        row = [r for r in R.ledger([kept(stopped).read()]) if r['what'] == 'ran'][0]
        self.assertEqual((row['status'], row['stopped'], row['pending'], len(row['receipts'])),
                         ('STEP_STOPPED', {'method': 'construct-enquiry-candidate@1', 'reason': 'Handler refused: No declared constructor'}, ['construct-enquiry-candidate@1'], 3))
        marks = started(['00_goal', '01_domain', '02_methods', '04_admission', '141_ask_with_line_marks'], name='line-marks')   # text outside ASCII is read as the journal wrote it
        mtext, mhead = kept(marks).read()
        asked = [r for r in R.ledger([(mtext, mhead)]) if r['what'] == 'asked'][0]
        self.assertEqual((asked['question'], mtext.isascii()), (pack('141_ask_with_line_marks')['methods'][0]['question'], False))
        self.assertTrue(all(mark in asked['question'] for mark in '\u2028\u2029\x85'))
        escaped = mtext.split('\n')
        escaped[6] = json.dumps(json.loads(escaped[6]), sort_keys=True, separators=(',', ':'))   # the same entry with its characters escaped: not the text this journal writes
        self.assertEqual((json.loads(escaped[6]), self.words(lambda: R.ledger([('\n'.join(escaped), mhead)]))), (json.loads(mtext.split('\n')[6]), 'The journal is broken at entry 6'))
        lines = text.split('\n')
        for at, line in ((2, lines[2].replace('":', '": ', 1)), (4, lines[4] + ' '), (6, lines[6].replace(',', ', ', 1)), (0, ' ' + lines[0])):
            other = '\n'.join(lines[:at] + [line] + lines[at + 1:])
            self.assertEqual(json.loads(line), json.loads(lines[at]))                    # the same entry, written in another way
            for read in (R.ledger, R.counts, R.record):
                self.assertEqual(self.words(lambda: read([(other, head)])), f'The journal is broken at entry {at}')
        entries = J.parse(text)
        for change, at in ((lambda f: f[6].update(result=[]), 6), (lambda f: f[6].update(body=[True]), 6), (lambda f: f[0].update(body=['kinds', 'checkers']), 0), (lambda f: f[6].update(extra=1), 6),
                           (lambda f: f[3].update(kind='header', body={'kinds': KINDS, 'checkers': []}), 3), (lambda f: f[0].update(kind='pack', body={'pack': pack('00_goal')}), 0),
                           (lambda f: f[0]['body'].update(more=1), 0), (lambda f: f[0]['body'].pop('checkers'), 0)):
            forged = copy.deepcopy(entries)                                              # re-chained by a forger: an entry that is no object where it should be one, a key too many, a header out of place
            change(forged)
            journal, forged_head = chained(forged)
            for read in (R.ledger, R.counts):
                self.assertEqual(self.words(lambda: read([(J.dump(journal), forged_head)])), f'The journal is broken at entry {at}')
        bare = J.start(['simulate_fact'])                                                # a journal that is its header and nothing else, with no name and no checker
        btext, bhead = kept(bare).read()
        self.assertEqual((bhead['length'], R.ledger([(btext, bhead)]), R.counts([(btext, bhead)]), [len(j['entries']) for j in R.record([(btext, bhead)])]), (1, [], {'goals': {}, 'steps': {}}, [1]))
        first = {'length': 1, 'sha256': J.parse(text)[0]['sha256']}                      # and any journal read at the head of its header
        self.assertEqual((R.ledger([(text, first)]), R.counts([(text, first)])), ([], {'goals': {}, 'steps': {}}))
        for bad in ({'length': 0, 'sha256': first['sha256']}, {'length': True, 'sha256': first['sha256']}, {'length': 1, 'sha256': 7}, {'length': 1}, dict(first, more=1)):
            self.assertEqual(self.words(lambda: R.ledger([(text, bad)])), 'No head, no read: a head is {length, sha256} and is kept outside the journal')
        self.assertEqual(self.words(lambda: R.ledger([(text.encode(), head)])), 'A journal is read from its text')

    # ------------------------------------------------------------------ named changes of the ruling and its refuters
    def test_a_head_is_quoted_only_for_a_journal_that_replays_on_a_fresh_state(self):
        """Refuter 1, finding 1: six ways the digest guard is silent. A new Kernel for every entry, the checkers read from
        the sealed header, a copy returned by add, and a shadow run before any head is quoted."""
        p1 = started()
        keep = kept(p1)
        r = J.restart(keep)
        self.assertFalse(any(isinstance(v, Kernel) for v in vars(r).values()))            # (a), (b): no Kernel is kept between entries, so none can be bent
        r.state.actions['ask']['plan'] = lambda s, m: None                                # (e): a hook of this run's registry, replaced by hand: code is not data
        e = r.add('look', LOOK)
        self.assertEqual((len(e['result']['briefs'][0]['receipts']), r.state.budget['attention']), (1, 1))   # the customer was asked a second time, in memory
        no_head = 'No head is quoted: The journal does not replay at entry 7: the result differs (briefs, budget, providers, state)'
        self.assertEqual(self.words(r.head), no_head)
        self.assertEqual(self.words(lambda: J.save(r, keep)), no_head)
        self.assertTrue(self.words(lambda: r.add('look', LOOK)).startswith('This run takes no more entries (its journal does not replay)'))
        self.assertEqual((keep.head['length'], J.restart(keep).state.budget['attention']), (7, 2))   # what is kept was never touched
        r = J.restart(keep)                                                               # (c): a checker added to the header by hand
        r.journal[0]['body']['checkers'].append('the-hand')
        r.add('event', {'row': dict(RECOUNT, source='the-hand'), 'execute': True})
        self.assertEqual(self.words(r.head), 'No head is quoted: The journal is broken at entry 0')
        r = J.restart(keep)                                                               # (d): the order of the methods is part of what a look reads
        r.state.methods = dict(reversed(list(r.state.methods.items())))
        self.assertEqual(self.words(lambda: r.add('look', LOOK)), 'The State was changed outside the journal after entry 6')
        r = J.restart(keep)                                                               # (f): add returns a copy
        e = r.add('look', {'execute': False})
        e['result']['briefs'][0]['status'], e['body']['execute'], e['sha256'] = 'FORGED', True, '0' * 64
        self.assertEqual((r.journal[7]['result']['briefs'][0]['status'], r.journal[7]['body'], J.save(r, keep)['sha256']), ('WAITING', {'execute': False}, r.journal[7]['sha256']))
        r = J.restart(keep)                                                               # an entry reached into and edited: no head either
        r.add('look', LOOK)
        r.journal[8]['result']['budget']['attention'] = 3
        self.assertEqual(self.words(r.head), 'No head is quoted: The journal is broken at entry 8')
        r = J.restart(keep)                                                               # also after its head was quoted once: the keeper is never handed it
        r.add('look', LOOK)
        r.add('look', LOOK)
        quoted, was = r.head(), keep.read()
        r.journal[8]['result']['budget']['attention'] = 3
        self.assertEqual(self.words(lambda: J.save(r, keep)), 'No head is quoted: The journal is broken at entry 8')
        self.assertEqual((quoted['length'], keep.read()), (10, was))

    def test_a_look_that_ends_in_a_fault_of_the_process_is_not_sealed(self):
        """Refuter 1, finding 8: a kernel fault, `unsettled`, a RecursionError or a MemoryError is not an outcome of the
        State. It is not sealed; the fault goes to the caller; only a replay continues."""
        keep = kept(started(ORDER, ['simulate_fact'], look=False))

        def raises(exc):
            def run(s, m, mid, deps):
                raise exc
            return run
        for hooks, said in (({'run': raises(RecursionError())}, 'Handler failed: RecursionError'), ({'run': raises(MemoryError())}, 'Handler failed: MemoryError'),
                            ({'run': lambda s, m, mid, deps: s.budget.pop('money') and {}}, 'Kernel fault: KeyError'),
                            ({'settle': lambda s, result, log: 1 / 0}, 'unsettled: simulate_fact')):
            r = J.restart(keep)
            r.state.actions['simulate_fact'] = dict(r.state.actions['simulate_fact'], **hooks)
            with self.assertRaises(J.Unsealed) as caught:
                r.add('look', LOOK)
            self.assertEqual(str(caught.exception), f'The look ended in a fault of the process, not in an outcome ({said}): nothing is sealed, and only a replay of the journal continues')
            self.assertEqual(len(r.journal), 6)
            self.assertTrue(self.words(lambda: r.add('look', {'execute': False})).startswith('This run takes no more entries (a look ended in a fault of the process)'))
            self.assertEqual(J.save(r, keep), keep.head)                                 # what was sealed before the fault is still a journal
        r = J.restart(keep)                                                              # an ordinary failure of a handler is an outcome: sealed in memory like any stop
        r.state.actions['simulate_fact'] = dict(r.state.actions['simulate_fact'], run=raises(KeyError('x')))
        self.assertEqual(r.add('look', LOOK)['result']['briefs'][0]['stopped']['reason'], 'Handler failed: KeyError')
        r = J.restart(keep)                                                              # only a replay continues
        r.add('look', LOOK)
        self.assertEqual(last(r)['status'], 'LOCAL_MODEL_EFFECTS_RECORDED')
        head = J.save(r, keep)
        entries = J.parse(keep.text)
        was = dict(ACTIONS['simulate_fact'])

        def replayed_under(hooks):   # what a replay of this journal ends in when the registry it loads holds these hooks
            ACTIONS['simulate_fact'].update(hooks)
            try:
                J.replay(entries, head)
            except (ValueError, RecursionError, MemoryError) as why:
                return type(why), str(why)
            finally:
                ACTIONS['simulate_fact'].clear()
                ACTIONS['simulate_fact'].update(was)
        # A replay that meets a failure of the process fails as the process: the journal is not refused, and the same replay goes through in a healthy one.
        for exc in (RecursionError, MemoryError):
            self.assertEqual(replayed_under({'run': raises(exc())}), (exc, f'The process failed while entry 6 was replayed (Handler failed: {exc.__name__}): the journal is not refused'))
        self.assertEqual(replayed_under({'settle': lambda s, result, log: deep_call(10 ** 6, int)}),
                         (RecursionError, 'The process failed while entry 6 was replayed (unsettled: simulate_fact): the journal is not refused'))   # also where a kind ran out of stack when it settled
        live = J.restart(keep)
        live.add('look', {'execute': False})
        ACTIONS['simulate_fact']['run'] = raises(RecursionError())
        try:
            for quote in (live.head, lambda: J.save(live, keep)):                        # nor is a run stopped by it, or anything kept
                with self.assertRaises(RecursionError):
                    quote()
        finally:
            ACTIONS['simulate_fact']['run'] = was['run']
        self.assertEqual((live.stopped, keep.head, J.save(live, keep)['length']), (False, head, 8))
        # A fault that is not the process's would come out again at every replay: an entry that ends in one was never sealed, so the journal that holds it is refused.
        self.assertEqual(replayed_under({'run': lambda s, m, mid, deps: s.budget.pop('money') and {}}), (ValueError, 'The journal does not replay at entry 6: the look ends in a fault (Kernel fault: KeyError)'))
        self.assertEqual(replayed_under({'settle': lambda s, result, log: 1 / 0}), (ValueError, 'The journal does not replay at entry 6: the look ends in a fault (unsettled: simulate_fact)'))
        made = Kernel.run_standing                                                       # the kernel's own door failing as the process, under a replay and under an add

        def out_of_stack(self, execute=False):
            raise RecursionError()

        def part_way(self, execute=False):
            self.s.budget['money'] -= 1
            raise RuntimeError('died part way')
        try:
            Kernel.run_standing = out_of_stack
            with self.assertRaises(RecursionError):
                J.replay(entries, head)
            r = J.restart(J.Keep(J.dump(entries[:6]), {'length': 6, 'sha256': entries[5]['sha256']}))
            with self.assertRaises(RecursionError):
                r.add('look', LOOK)
            self.assertEqual((r.stopped, len(r.journal)), (False, 6))                    # it changed nothing, so the run goes on
            Kernel.run_standing = part_way                                               # an entry that stops part way: the State moved and nothing was sealed
            with self.assertRaises(RuntimeError):
                r.add('look', LOOK)
        finally:
            Kernel.run_standing = made
        self.assertEqual((r.stopped, len(r.journal)), ('an entry stopped part way', 6))
        self.assertEqual(self.words(lambda: r.add('look', LOOK)), 'This run takes no more entries (an entry stopped part way): replay the journal to continue')
        self.assertEqual(r.head(), {'length': 6, 'sha256': entries[5]['sha256']})        # what was sealed before it is still a journal: the head is of the journal, not of the State
        self.assertEqual(J.replay(entries, head).head(), head)

    def test_an_entry_taken_deep_in_the_stack_is_sealed_only_when_it_replays(self):
        """Refuter 1, finding 8, as a scan: a look, an answer and an event row, each taken at every depth of the process's
        own stack over the last 150 calls before the recursion limit. Whatever the depth does to the entry, it is sealed
        only when it replays from the bottom of the stack; otherwise the fault goes to the caller, nothing is sealed, and
        what was sealed before it still replays."""
        def deep(n, do):
            return do() if n <= 0 else deep(n - 1, do)
        limit, seen = sys.getrecursionlimit(), {'sealed': 0, 'unsealed': 0, 'to the caller': 0}
        ask = kept(started())
        order = kept(started(ORDER, ['simulate_fact'], look=False))
        receipt = receipt_of(J.restart(ask))
        for keep, kind, body in ((order, 'look', LOOK), (ask, 'answer', yes(receipt)), (ask, 'event', {'row': RECOUNT, 'execute': True})):
            for depth in range(limit - 150, limit):
                run = J.restart(keep)
                try:
                    deep(depth, lambda: run.add(kind, body))
                    seen['sealed'] += 1
                except J.Unsealed:
                    seen['unsealed'] += 1
                except RecursionError:
                    seen['to the caller'] += 1
                at = {'length': len(run.journal), 'sha256': run.journal[-1]['sha256']}
                self.assertIn(at['length'], (keep.head['length'], keep.head['length'] + 1), (kind, depth))
                self.assertEqual(J.replay(run.journal, at).head(), at, (kind, depth))   # from the bottom of the stack: sealed or not, the journal replays
        self.assertTrue(seen['sealed'] > 100 and seen['unsealed'] + seen['to the caller'] > 20, seen)   # the scan crossed the limit: both sides were seen

    def test_save_and_load_round_trip_every_character_through_a_file_and_a_second_interpreter(self):
        """Refuter 1, finding 3: a line mark inside a question, a predicate and a source (U+2028, U+2029, U+0085)."""
        marks = '\u2028\u2029\x85'
        goal, source = 'order' + marks + 'done', 'fixture/desk' + marks
        odd = {'schema': 'sutra-extension/2', 'id': 'odd' + marks, 'goals': [goal], 'providers': {'owner-channel': 1}, 'grants': ['action:ask@1'],
               'evidence': [{'predicate': 'stock' + marks, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': '1'}],
               'methods': [{'id': 'ask@1', 'effect': goal, 'requires': ['stock' + marks], 'provider': 'owner-channel', 'grant': 'action:ask@1', 'cost': {'attention': 1}, 'action': 'ask',
                            'ask_to': 'customer', 'question': 'May we?' + marks + ' Reply "yes" or \\no/. \u00e9\u4e2d\U0001f600'}]}
        run = J.start(KINDS, [source], name='marks' + marks)
        run.add('pack', {'pack': odd})
        run.add('event', {'row': {'predicate': 'stock' + marks, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': '2\r\n\t'}, 'execute': True})
        receipt = last(run)['model_receipts'][0]
        self.assertEqual(receipt['ask']['question'], odd['methods'][0]['question'])
        text = J.dump(run.journal)
        self.assertEqual((len(text.split('\n')) - 1, J.dump(J.parse(text)) == text), (3, True))
        self.assertGreater(len(text.splitlines()), 3)                # a reader that cut at every line mark would cut entries in two
        with self.assertRaises(ValueError):
            [json.loads(line) for line in text.splitlines()]
        child = ("import sys,json;sys.path.insert(0,sys.argv[1]);from extensions import journal as J;from extensions.asks import open_asks;run=J.restart(J.FileKeep(sys.argv[2]));"
                 "print(json.dumps([run.head(),J.state_digest(run.state),[v['issued'] for v in open_asks(run.state).values()]]))")
        with tempfile.TemporaryDirectory() as folder:
            keep = J.FileKeep(folder)
            head = J.save(run, keep)
            self.assertEqual((Path(folder) / 'journal.jsonl').read_bytes(), text.encode('utf-8'))   # every character, as bytes
            self.assertEqual(keep.read(), (text, head))
            again = J.restart(keep)
            self.assertEqual((again.head(), J.state_digest(again.state), J.dump(again.journal)), (head, J.state_digest(run.state), text))
            other = subprocess.run([sys.executable, '-I', '-B', '-c', child, str(ROOT), folder], capture_output=True, text=True)
            self.assertEqual(other.returncode, 0, other.stderr)
            self.assertEqual(json.loads(other.stdout), [head, J.state_digest(run.state), [receipt]])   # a second interpreter replays the saved file to the same head
            again.add('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': 'customer', 'execute': True})
            J.save(again, keep)
            self.assertEqual(J.restart(keep).state.fact(goal)['truth'], 'TRUE')
        with self.assertRaises(ValueError):
            run.add('look', {'execute': True, 'note': '\ud800'})     # text that UTF-8 cannot carry does not pass the door

    def test_a_learner_walked_over_the_journal_equals_the_twin(self):
        """Refuter 1, finding 6: the journal says where the packs fell, so a Learner fed in entry order (apply at every
        pack entry, attach the runs of every other entry) says what the Learner of the never-stopped process said.
        Fed all replayed runs at once, it counts one too many. No reader is built here; this pins what one can rest on."""
        said = lambda runs: [[x.get('observations') for x in r['learning']] for r in runs]
        run, twin, live = started(ORDER, ['simulate_fact'], look=False), Learner(False), []
        for kind, body in (('look', LOOK), ('event', {'row': LOST, 'execute': False}), ('pack', {'pack': pack('05_learning')}), ('look', LOOK)):
            e = run.add(kind, body)
            if kind == 'pack':
                twin.apply(body['pack'])
            else:
                live += twin.attach(copy.deepcopy(run.detail[e['seq']]))['runs']
        again = J.restart(kept(run))
        walked, got = Learner(False), []
        for e in again.journal:
            if e['kind'] == 'pack':
                walked.apply(e['body']['pack'])
            elif e['seq'] in again.detail:
                got += walked.attach(copy.deepcopy(again.detail[e['seq']]))['runs']
        self.assertEqual((said(got), said(got)), (said(live), [[], [], [1]]))
        at_once = Learner.from_packs([e['body']['pack'] for e in again.journal if e['kind'] == 'pack'])
        runs = copy.deepcopy([r for seq in sorted(again.detail) for r in again.detail[seq]['runs']])
        self.assertEqual(said(at_once.attach({'runs': runs})['runs']), [[1], [], [2]])

    def test_a_journal_kept_from_this_build_still_replays(self):
        """Refuter 2, finding 2: 'the restart case written on one lab replays on the next'. KEPT is a journal a draft of
        the build that added the journal wrote, kept as text. Under whatever kernel and journal code run this test it
        must replay to its head, with the question still out and the kept receipt taking the answer. The journal file
        that wrote it is already another than the one that replays it: that is a notice, never a refusal.
        If this fails after a kernel promotion or a change to the journal, a kept journal no longer replays. That is
        the ruling's trigger (carry the State over, or the record pack), not a constant to bring up to date."""
        text = ''.join(line + '\n' for line in KEPT)
        run = J.restart(J.Keep(text, KEPT_HEAD))
        self.assertEqual((run.head(), run.cut, J.dump(run.journal) == text), (KEPT_HEAD, 0, True))
        self.assertTrue(all(n['entry'] == 0 and set(n['differs']) <= {'kernel.core', 'extensions.asks', 'extensions.journal'} for n in run.notice))
        self.assertEqual((len(run.notice), 'extensions.journal' in run.notice[0]['differs']), (1, True))   # stated under another journal file: said, and replayed to the same head
        receipt = J.parse(text)[2]['result']['briefs'][0]['receipts'][0]
        self.assertEqual(canonical([v['issued'] for v in open_asks(run.state).values()]), canonical([receipt]))
        e = run.add('answer', {'receipt': receipt, 'truth': 'TRUE', 'source': 'owner', 'execute': True})
        self.assertEqual((e['result']['status'], [b['status'] for b in e['result']['briefs']], run.state.fact('approved')['truth'], dict(run.state.budget)),
                         ('RECONCILED', ['SUPPORTED_BY_EVIDENCE'], 'TRUE', {'compute': 10, 'money': 10, 'attention': 2}))
        self.assertEqual([r['what'] for r in R.ledger([(text, KEPT_HEAD)])], ['handed_in', 'ran', 'asked'])   # and the adapter reads it without the kernel

    def test_limit_every_handler_runs_again_on_replay(self):
        """A known limit, pinned: replay puts every entry through its door again, so a handler runs once more at every
        restart and at every save. Safe only while an effect is a local model; a kind that acts outside needs a keyed
        outbox, which this version does not build."""
        acts = []
        was = ACTIONS['simulate_fact']['run']

        def counted(s, m, mid, deps):
            acts.append(mid)
            return was(s, m, mid, deps)
        ACTIONS['simulate_fact']['run'] = counted
        try:
            run = started(ORDER, ['simulate_fact'])
            self.assertEqual(acts, ['ship-replacement@1'])                    # one act, live
            keep = kept(run)
            self.assertEqual(len(acts), 2)                                    # the save replayed it on a shadow run
            for _ in range(3):
                J.restart(keep)
            self.assertEqual(len(acts), 5)                                    # and each restart once more
        finally:
            ACTIONS['simulate_fact']['run'] = was
        made, doors = Kernel.__init__, []                                     # what a restart costs, in entries: every entry after the header goes through its door again

        def counted_kernel(self, state):
            doors.append(1)
            made(self, state)
        Kernel.__init__ = counted_kernel
        try:
            r = J.restart(keep)
            self.assertEqual((len(r.journal), len(doors)), (7, 6))            # a restart: six of seven entries, once each
            r.add('look', LOOK)
            J.save(r, keep)
            self.assertEqual(len(doors), 6 + 1 + 7)                           # one more entry: once live, and the save replays all seven that follow the header
        finally:
            Kernel.__init__ = made

    def test_limit_a_body_changed_to_one_that_gives_the_same_result_replays_under_another_head(self):
        """A known limit, pinned: what replay refuses is a result that does not come out again, and nothing else. A
        forger who changes a body to another one that gives the same result needs no kernel: the look that waits runs
        nothing whether it executes or not, no row came from the second checker, and the header's name is in no State.
        Each such journal replays, to the same State, under a head of its own. Only the head kept outside tells them apart."""
        run = started()
        run.add('look', LOOK)                                              # entry 7: the question is out, so this look waits whatever `execute` says
        keep = kept(run)
        entries = J.parse(keep.text)
        for change in (lambda f: f[7]['body'].update(execute=False), lambda f: f[0]['body'].update(name='another'), lambda f: f[0]['body']['checkers'].__setitem__(1, 'fixture/elsewhere')):
            forged = copy.deepcopy(entries)
            change(forged)
            journal, head = chained(forged)
            again = J.replay(journal, head)
            self.assertEqual((J.state_digest(again.state), head['length']), (entries[-1]['result']['state'], keep.head['length']))   # the same State ...
            self.assertNotEqual(head, keep.head)                                                                                      # ... under another head
            self.assertEqual(self.words(lambda: J.replay(journal, keep.head)), 'The journal does not end on the hash its head names')   # which the kept head refuses
        forged = copy.deepcopy(entries)                                    # where the result would differ, the same kind of change is refused
        forged[6]['body']['execute'] = False                               # the look that asked, said to have been a dry look
        self.assertEqual(self.words(lambda: J.replay(*chained(forged))), 'The journal does not replay at entry 6: the result differs (briefs, budget, providers, state)')

    def test_loading_the_journal_registers_no_action_kind_and_changes_no_recorded_case(self):
        child = "import sys;sys.path.insert(0,sys.argv[1]);from kernel.core import ACTIONS;import extensions.asks;was=sorted(ACTIONS);import extensions.journal,extensions.journal_record;print(was==sorted(ACTIONS),sorted(ACTIONS))"
        alone = subprocess.run([sys.executable, '-I', '-B', '-c', child, str(ROOT)], capture_output=True, text=True)
        self.assertEqual(alone.stdout.strip(), "True ['ask', 'simulate_fact']", alone.stderr)
        record = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())
        roots = {c['id']: (c['outcome'] or {}).get('trace_root_sha256') for c in record['cases']}
        for spec in CASES:    # with the journal loaded and used in this process, every recorded case comes out with its recorded trace root
            self.assertEqual((scenario(spec)['outcome'] or {}).get('trace_root_sha256'), roots[spec[0]], spec[0])
        for block, made in (('events', extra_events), ('ask_events', ask_events)):   # and so do the two event records, whole
            self.assertEqual(canonical(json.loads(json.dumps(made()))), canonical(record[block]), block)

    def test_the_recorded_sequences_replay_in_this_process(self):
        """The journal texts kept in the record are journals: each replays here to its recorded head, and each tampered
        one is refused here in the recorded words."""
        scenes = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())['scenes']
        restart, refusals, chain = scenes['journal_restart'], scenes['journal_refusals'], scenes['journal_chain']
        for text, head in ((restart['text'], restart['head']), (restart['text'], restart['head_after_first']), (restart['no']['text'], restart['no']['head']),
                           (restart['one_dry_look_more']['text'], restart['one_dry_look_more']['head']),
                           (restart['line_marks']['text'], restart['line_marks']['head']), (refusals['text'], refusals['head']),
                           (refusals['past_the_head']['text_after_save'], refusals['past_the_head']['head_after_save']), (refusals['second_writer']['text'], refusals['second_writer']['head']),
                           (refusals['pack_twice']['text'], refusals['pack_twice']['head']), (chain['first']['text'], chain['first']['head']),
                           (restart['twin_text'], restart['twin_head']), (refusals['second_writer']['second']['kept_text'], refusals['second_writer']['second']['kept_head']),
                           (chain['first']['text'], chain['first']['head_before_closing']), (chain['late_writer']['kept_text'], chain['late_writer']['kept_head'])):
            run = J.restart(J.Keep(text, head))
            self.assertEqual((run.head(), J.state_digest(run.state), run.notice), (head, J.parse(text)[head['length'] - 1]['result']['state'], []))
        first = J.restart(J.Keep(chain['first']['text'], chain['first']['head']))
        second = J.restart(J.Keep(chain['second']['text'], chain['second']['head']), before=first)
        self.assertEqual((second.head(), first.closed, second.closed), (chain['second']['head'], True, False))
        self.assertEqual(self.words(lambda: first.add('look', LOOK)), chain['late_writer']['entry_refused'])
        self.assertEqual(len(refusals['tampered']), 10)
        for t in refusals['tampered'] + [refusals['pack_twice']['holds_it_twice']]:
            self.assertEqual(self.words(lambda: J.restart(J.Keep(t['text'], t['head']))), t['refused'])
        self.assertEqual(J.restart(J.Keep(refusals['past_the_head']['text'], refusals['past_the_head']['head'])).cut, 1)
        self.assertEqual((restart['twin_head'], restart['twin_text']), (restart['head'], restart['text']))
        for kept_text, head in ((restart['text'], restart['head']), (chain['first']['text'], chain['first']['head']), (chain['second']['text'], chain['second']['head'])):
            self.assertEqual(len(kept_text.split('\n')), head['length'] + 1)                 # a kept text holds what its head names and nothing after it

    # ------------------------------------------------------------------ the confirming round: what its two refuters found, settled without new code
    # Two refuters attacked this build once more, on the promoted base. Every claim on behaviour held. What they found is pinned below as
    # the build behaves today, and the passage says it in words. A fix of any of it is new code: it belongs to a later version and its own
    # review, and the test that pins the behaviour here changes with it.
    def test_c1_what_stands_past_the_head_is_cut_by_the_next_save_that_appends_and_by_no_other(self):
        """The confirming round, refuter 1, finding 4: a save with nothing new to hand over compares the heads and writes
        nothing, so what stands past the head still stands after it. The next save that appends an entry cuts it. It is
        reported at every restart and never run. In memory and in a folder, and in a folder whose tail is torn inside a
        character."""
        text, head = kept(started()).read()
        with tempfile.TemporaryDirectory() as folder:
            files, file = J.FileKeep(folder), Path(folder) / 'journal.jsonl'
            files.append(None, text, head)
            file.write_bytes(file.read_bytes() + b'{"torn')
            for keep, standing in ((J.Keep(text + '{"torn', head), lambda k: k.text), (files, lambda k: file.read_bytes().decode('utf-8'))):
                r = J.restart(keep)
                self.assertEqual((r.cut, len(r.journal), r.head()), (1, 7, head))                # reported, never run
                self.assertEqual((J.save(r, keep), standing(keep)), (head, text + '{"torn'))     # nothing new to hand over: the heads are compared, nothing is written, and it still stands
                self.assertEqual(J.restart(keep).cut, 1)
                r.add('look', {'execute': False})
                self.assertEqual((J.save(r, keep)['length'], standing(keep)), (8, text + J.dump(r.journal[7:])))   # one new entry: this save cuts it
                self.assertEqual(J.restart(keep).cut, 0)
        torn = '{"body":{"question":"May we? '.encode('utf-8')[:-1]            # the start of one more entry, cut inside the three bytes of U+2028
        with tempfile.TemporaryDirectory() as folder:
            files, file = J.FileKeep(folder), Path(folder) / 'journal.jsonl'
            files.append(None, text, head)
            file.write_bytes(file.read_bytes() + torn)
            r = J.restart(files)
            self.assertEqual((r.cut, len(r.journal), r.head()), (1, 7, head))                    # reported, never run
            self.assertEqual((J.save(r, files), file.read_bytes()), (head, text.encode('utf-8') + torn))   # nothing new to hand over: the torn character still stands
            self.assertEqual(J.restart(files).cut, 1)
            r.add('look', {'execute': False})
            self.assertEqual((J.save(r, files)['length'], file.read_bytes()), (8, (text + J.dump(r.journal[7:])).encode('utf-8')))   # one new entry: this save cuts it
            self.assertEqual(J.restart(files).cut, 0)

    def test_limit_a_continuation_the_keeper_refuses_leaves_the_run_handed_in_closed_in_memory(self):
        """The confirming round, refuter 1, finding 2. A known limit, pinned: start() seals the closing entry on the run
        handed in before the save that the keeper may refuse (here another writer holds the folder; a writer that died
        leaves the same lock). Nothing that is kept changes and the State of that run is as it was, but the run is closed
        in memory: it takes no entry and no continuation under another name. Only the same continuation goes on with it,
        or a restart from the keeper, which does not hold what was not saved. And save() of that run keeps the closing
        entry too: the kept journal then ends on an entry that names a journal that was never started. Sealing the closing
        entry only when its save is taken is new code, owed to a later version."""
        def refused(folder):   # the only writer of a kept journal adds one row, does not save it, and continues the journal while the keeper is held
            keep, lock, file = J.FileKeep(folder), Path(folder) / 'journal.lock', Path(folder) / 'journal.jsonl'
            J.save(started(ORDER, ['simulate_fact'], name='one'), keep)
            was = (keep.read(), file.read_bytes())
            r = J.restart(keep)
            r.add('event', {'row': LOST, 'execute': True})
            told = lambda: (J.state_digest(r.state), dict(r.state.budget), dict(r.state.providers), r.base)
            state = told()
            self.assertEqual((len(r.journal), r.stopped, r.closed, state[1], state[3]), (8, False, False, {'compute': 6, 'money': 6, 'attention': 3}, was[0][1]))
            lock.write_bytes(b'')                                    # another writer is inside its one exclusive step
            self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, name='two', continues=r, keep=keep)), 'Another writer holds this journal: replay it and try again')
            lock.unlink()
            self.assertEqual(((keep.read(), file.read_bytes()), told()), (was, state))   # nothing that is kept changed, and the State of the run handed in is as it was
            self.assertEqual((len(r.journal), r.journal[8]['kind'], r.journal[8]['body'], r.stopped, r.closed),
                             (9, 'close', {'next': {'kinds': ['simulate_fact'], 'checkers': CHECKERS, 'name': 'two'}}, J.CLOSED, True))   # but the run went from 8 entries to 9 and is closed, in memory
            self.assertEqual(self.words(lambda: r.add('look', LOOK)), CLOSED_RUN)
            self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, name='three', continues=r, keep=keep)), NAMES_ANOTHER)   # the keeper is free again: still no continuation under another name
            for kinds, checkers in ((['simulate_fact', 'ask'], CHECKERS), (['simulate_fact'], CHECKERS[::-1]), (['simulate_fact'], [])):
                self.assertEqual(self.words(lambda: J.start(kinds, checkers, name='two', continues=r, keep=keep)), NAMES_ANOTHER)   # nor under its name with other kinds or checkers
            self.assertEqual((keep.read(), file.read_bytes()), was)
            return keep, was[0], r
        with tempfile.TemporaryDirectory() as folder:
            keep, was, r = refused(folder)
            again = J.restart(keep)                                  # a restart goes on from what is kept: the row that was not saved is not there
            self.assertEqual((len(again.journal), again.stopped, again.closed, dict(again.state.budget)), (7, False, False, {'compute': 8, 'money': 8, 'attention': 3}))
            two = J.start(['simulate_fact'], CHECKERS, name='two', continues=r, keep=keep)   # the same continuation goes on with the run: the row and the closing entry are kept, and the new header cites that head
            now = keep.read()
            self.assertEqual(([e['kind'] for e in J.parse(now[0])][7:], now[1]['length'], two.journal[0]['body']['continues'], r.base, dict(two.state.budget)),
                             (['event', 'close'], 9, now[1], now[1], {'compute': 6, 'money': 6, 'attention': 3}))
        with tempfile.TemporaryDirectory() as folder:
            keep, was, r = refused(folder)
            saved = J.save(r, keep)                                  # save() of that run, to keep the one row, keeps the closing entry too
            closing = J.parse(keep.read()[0])[-1]
            self.assertEqual((saved['length'], keep.read()[1], closing['kind'], closing['body']), (9, saved, 'close', {'next': {'kinds': ['simulate_fact'], 'checkers': CHECKERS, 'name': 'two'}}))
            back = J.restart(keep)                                   # the kept journal is closed in the name of a journal that was never started
            self.assertEqual((back.closed, back.stopped, self.words(lambda: back.add('look', LOOK))), (True, J.CLOSED, CLOSED_RUN))
            self.assertEqual(self.words(lambda: J.start(['simulate_fact'], CHECKERS, name='three', continues=back, keep=keep)), NAMES_ANOTHER)
            self.assertEqual(J.start(['simulate_fact'], CHECKERS, name='two', continues=back, keep=keep).journal[0]['body']['continues'], saved)   # only a journal of that name goes on from it
            self.assertEqual(sorted(os.listdir(folder)), ['journal.head', 'journal.jsonl'])

    def test_limit_a_look_taken_dry_is_a_ledger_row_worded_ran_with_the_actions_and_cost_of_its_plan(self):
        """The confirming round, refuter 2, finding 4. A known limit, pinned on the recorded journal with one dry look
        more: the dry look is a ledger row worded `ran`, with `executed` false, no receipt, and the actions and the cost
        of its plan, though nothing ran and nothing was charged. The cost over all `ran` rows is therefore more than the
        books say was spent; over the rows with `executed` true it is what the books say. The counts are right: they
        read receipts. A row of its own for a look taken dry is new code, owed to a later version."""
        m = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())['scenes']['journal_restart']['one_dry_look_more']
        text, head = m['text'], m['head']
        entries = J.parse(text)
        self.assertEqual([(e['seq'], e['kind'], e['body']['execute']) for e in entries[6:]], [(6, 'look', False), (7, 'look', True), (8, 'answer', True)])
        ran = [r for r in R.ledger([(text, head)]) if r['what'] == 'ran']
        self.assertEqual([(r['entry'], r['executed'], r['status'], r['work_state'], r['actions'], r['cost'], len(r['receipts'])) for r in ran],
                         [(6, False, 'PLAN_READY', 'ready', ['ask-customer-approval@1', 'ship-replacement@1'], {'compute': 2, 'money': 2, 'attention': 1}, 0),
                          (7, True, 'WAITING', 'waiting', ['ask-customer-approval@1'], {'compute': 0, 'money': 0, 'attention': 1}, 1),
                          (8, True, 'LOCAL_MODEL_EFFECTS_RECORDED', 'completed', ['ship-replacement@1'], {'compute': 2, 'money': 2, 'attention': 0}, 1)])
        self.assertEqual((entries[6]['result']['budget'], entries[6]['result']['providers']), (entries[5]['result']['budget'], entries[5]['result']['providers']))   # the dry look charged nothing and took no slot
        total = lambda rows: {k: sum(r['cost'][k] for r in rows) for k in ('compute', 'money', 'attention')}
        spent = {k: v - entries[-1]['result']['budget'][k] for k, v in {'compute': 10, 'money': 10, 'attention': 3}.items()}
        self.assertEqual((total(ran), spent, total([r for r in ran if r['executed']])),
                         ({'compute': 4, 'money': 4, 'attention': 2}, {'compute': 2, 'money': 2, 'attention': 1}, {'compute': 2, 'money': 2, 'attention': 1}))   # all `ran` rows, the books, the rows that executed
        got = R.counts([(text, head)])
        goal = got['goals']['orgA/fulfillment|order_complete']
        self.assertEqual((goal['looked'], goal['executed'], goal['statuses']), (3, 2, {'PLAN_READY': 1, 'WAITING': 1, 'LOCAL_MODEL_EFFECTS_RECORDED': 1}))
        self.assertEqual({k.split('|')[1]: (v['ran'], [a['entry'] for a in v['at']]) for k, v in got['steps'].items()},
                         {'ask-customer-approval@1': (1, [7]), 'ship-replacement@1': (1, [8])})   # counted by receipt: each step ran once
        d = started(look=False)                                      # and on a journal made here: a look taken dry is a `ran` row that holds what its plan would do
        d.add('look', {'execute': False})
        row = [r for r in R.ledger([kept(d).read()]) if r['what'] == 'ran'][0]
        self.assertEqual((row['executed'], row['status'], row['actions'], row['cost'], row['receipts'], dict(d.state.budget)),
                         (False, 'PLAN_READY', ['ask-customer-approval@1', 'ship-replacement@1'], {'compute': 2, 'money': 2, 'attention': 1}, [], {'compute': 10, 'money': 10, 'attention': 3}))
        w = started()                                                # while the question is out, a look taken dry waits: no action, no cost, no receipt
        w.add('look', {'execute': False})
        w.add('look', LOOK)                                          # a look that executes and waits has no receipt either: only `executed` tells the two rows apart
        self.assertEqual([(r['entry'], r['executed'], r['status'], r['actions'], r['cost'], r['receipts']) for r in R.ledger([kept(w).read()]) if r['what'] == 'ran'][1:],
                         [(7, False, 'WAITING', [], {'compute': 0, 'money': 0, 'attention': 0}, []), (8, True, 'WAITING', [], {'compute': 0, 'money': 0, 'attention': 0}, [])])

    def test_limit_a_kept_head_that_nests_deeper_than_the_stack_ends_in_pythons_error_not_in_the_journals_words(self):
        """The confirming round, refuter 1, finding 3. A known limit, pinned: the depth rule covers kept lines and entries
        handed to replay, not the kept head of the folder keeper, which is read as JSON before any rule. A head text that
        nests as deep as the recursion limit of the process ends in a RecursionError. By this module's rule that says the
        process failed and the call may be made again; here it is the kept head that is at fault, at every depth of the
        stack. A head that nests less deep, or is no head in another way, is refused in the journal's words. The depth
        rule for the kept head is new code, owed to a later version."""
        deep = sys.getrecursionlimit()                               # a thousand levels in the build this was written on
        not_a_head = 'No head, no restart: what is kept as the head here is not a head'
        with tempfile.TemporaryDirectory() as folder:
            keep, file = J.FileKeep(folder), Path(folder) / 'journal.head'
            run = started()
            head = J.save(run, keep)
            good, text = file.read_bytes(), (Path(folder) / 'journal.jsonl').read_bytes()
            run.add('look', LOOK)
            for kept_head in (b'[' * deep + b']' * deep, b'{"length":' + b'[' * deep + b']' * deep + b',"sha256":"x"}'):
                file.write_bytes(kept_head)
                for read in (lambda: J.restart(keep), keep.read, lambda: J.save(run, keep)):
                    with self.assertRaises(RecursionError):
                        read()
                self.assertEqual((sorted(os.listdir(folder)), (Path(folder) / 'journal.jsonl').read_bytes(), run.stopped, len(run.journal)),
                                 (['journal.head', 'journal.jsonl'], text, False, 8))   # no lock is left, nothing is appended, and no run is stopped by it
            for kept_head in (b'[' * 70 + b']' * 70, b'[' * 200 + b']' * 200, b'\xef\xbb\xbf' + good, b'\xff\xfe', good.replace(b'"length":7', b'"length":7.0'), good[:-1] + b',"more":1}'):
                file.write_bytes(kept_head)                          # less deep, with a byte order mark, not UTF-8, a length that is no whole number, a key too many
                self.assertEqual((self.words(lambda: J.restart(keep)), self.words(lambda: J.save(run, keep))), (not_a_head, not_a_head))
            file.write_bytes(good)
            self.assertEqual((J.restart(keep).head(), J.save(run, keep)['length']), (head, 8))   # the journal itself was never at fault

    def test_limit_the_adapter_does_not_look_at_the_shape_of_the_code_statement(self):
        """The confirming round, refuter 1, finding 5. A known limit, pinned: the code statement stands outside an entry's
        hash, so a text in which it is changed still ends on its head. The journal's reader refuses a statement that is
        not {code: {name: text}} as a broken entry, by number. The adapter reads the same text and gives the same rows
        and counts: it never looks at `stated`. The adapter's own check of that shape is new code, owed to a later version."""
        text, head = kept(started(ORDER, ['simulate_fact'], name='one')).read()
        lines = text.split('\n')
        rows, counted = R.ledger([(text, head)]), R.counts([(text, head)])
        self.assertEqual((len(rows), 'stated' in json.loads(lines[2])), (6, False))
        restated = lambda stated: '\n'.join(lines[:2] + [canonical(dict(json.loads(lines[2]), stated=stated))] + lines[3:])   # entry 2 with a code statement beside it, its hash left as it was
        for stated in ({'code': {'x': 1}}, None, {'note': 'x'}, ['code'], {'code': 'kernel.core'}):
            other = restated(stated)
            for read in (lambda: J.restart(J.Keep(other, head)), lambda: J.replay(J.parse(other), head)):
                self.assertEqual(self.words(read), 'The journal is broken at entry 2', stated)
            self.assertEqual((R.ledger([(other, head)]), R.counts([(other, head)]), [len(j['entries']) for j in R.record([(other, head)])]), (rows, counted, [7]), stated)
        well = J.restart(J.Keep(restated({'code': {'x': 'y'}}), head))   # a statement of the right shape, whatever it says, is read by both: it says, it does not prove
        self.assertEqual((well.head(), well.notice, R.ledger([(restated({'code': {'x': 'y'}}), head)])), (head, [{'entry': 2, 'differs': ['extensions.journal', 'kernel.core', 'x']}], rows))

    def test_limit_a_key_added_to_a_part_of_a_recorded_sequence_passes_the_checks_and_is_left_to_the_seal(self):
        """The confirming round, refuter 2, finding 6. A known limit, pinned: the independent checks read the parts of a
        recorded sequence by their keys, so a key added in one of these 58 places (the three sequences, their named parts
        and their recorded steps) fails none of the 74 tests. A key added to what the checks compare whole (a snapshot,
        a head, a ledger row, the counts, what the kernel returned, a body tried at a door) fails one. What the checks
        let pass is left to the seal the record keeps over each sequence, which then no longer fits; a sequence made
        again with its seal would pass. Closed lists of keys for these parts are new code, owed to a later version."""
        places = {'journal_restart': ['', 'first', 'restarted', 'again', 'answered_yes', 'later', 'from_packs_alone', 'no', 'no.answered_no', 'no.look', 'no.from_packs_alone', 'one_dry_look_more',
                                      'one_dry_look_more.dry', 'one_dry_look_more.look', 'one_dry_look_more.answered_yes', 'line_marks', 'line_marks.look'],
                  'journal_refusals': ['', 'look'] + [f'tampered.{n}' for n in range(10)] + ['past_the_head', 'past_the_head.writer', 'past_the_head.look', 'second_writer', 'second_writer.first',
                                       'second_writer.first.step', 'second_writer.second', 'second_writer.second.step', 'second_writer.again', 'second_writer.again.step', 'pack_twice',
                                       'pack_twice.shipped', 'pack_twice.came_back', 'pack_twice.kernel_alone', 'pack_twice.holds_it_twice', 'outside'],
                  'journal_chain': ['', 'first', 'first.look', 'late_writer', 'late_writer.step', 'second', 'second.look', 'second.came_back', 'second.look_again', 'restarted', 'restarted.look', 'refused',
                                    'from_packs_alone']}
        whole = ['journal_restart.after_first', 'journal_restart.head', 'journal_restart.ledger.0', 'journal_restart.counts', 'journal_restart.first.result', 'journal_refusals.after_doors',
                 'journal_refusals.doors.0', 'journal_chain.second.head', 'journal_chain.counts_after_first']
        record = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())
        file, module = ROOT / 'qa' / 'checks' / 'journal.py', {'__name__': 'qa_checks_journal'}
        exec(compile(file.read_text(encoding='utf-8'), str(file), 'exec'), module)   # the check module, loaded as the verifier loads it
        read = {'kernel_sha256': record['kernel_sha256'], 'action_handlers': record['action_handlers'], 'cases': [c for c in record['cases'] if c['id'] == '60_pack_twice'],
                'scenes': {name: record['scenes'][name] for name in places}, 'added': {'files': record['added']['files']}}   # what these checks read of the record

        def with_a_key(place=None):   # (how many tests ran, the tests that fail, the record) with one key added at this place
            d = json.loads(json.dumps(read))
            if place:
                at = d['scenes']
                for k in place.split('.'):
                    at = at[int(k)] if type(at) is list else at[k]
                at['zz_extra'] = 1
            got = module['parts'](d, ROOT, digest)
            return sum(len(each) for each in got.values()), sorted(name for each in got.values() for name, ok in each.items() if not ok), d
        self.assertEqual((with_a_key()[:2], sum(len(parts) for parts in places.values())), ((74, []), 58))
        for name, parts in places.items():
            self.assertEqual(record['added']['scenes'][name], digest(record['scenes'][name]))   # the seal the record keeps over the sequence
            for part in parts:
                ran, failed, d = with_a_key(name + ('.' + part if part else ''))
                self.assertEqual((ran, failed, record['added']['scenes'][name] == digest(d['scenes'][name])), (74, [], False), (name, part))   # no test fails, and the seal no longer fits
        for place in whole:
            self.assertTrue(with_a_key(place)[1], place)                                     # compared whole: one key more fails a test

    def test_c9_the_adapter_imports_nothing_of_the_lab(self):
        """The confirming round, refuter 2, finding 3: this clause of C9 is held by unit tests alone, since it is about a
        file and not about the record. The adapter's import lines, read here: three modules of the standard library, and
        no call that could load another."""
        import ast
        tree = ast.parse((ROOT / 'extensions' / 'journal_record.py').read_text(encoding='utf-8'))
        imported = sorted({a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {'.' * n.level + (n.module or '') for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)})
        self.assertEqual(imported, ['__future__', 'hashlib', 'json', 're'])
        self.assertEqual([n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in ('__import__', 'exec', 'eval', 'compile', 'importlib', 'open')], [])


if __name__ == '__main__':
    unittest.main()
