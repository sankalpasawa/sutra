"""0.16.0-ordered (matrix rows R73, R82, R80): ordered side effects, data before cuts, per-tier rules.
One test per claim of the README passage (C1 to C13), each with its refusal paths and with the State compared before and after
where something is refused; the known limits the passage states are pinned where they show. Further tests cover what the claims
lean on: the declared kind of the scrub and the two scrub steps, the sanitizer's words, the three locks of a cut, the closed list
of the tier packs. The last two tie the record to the sequence and to the independent checks, and change every recorded leaf of
this version once."""
# Added when the findings of the confirming review were settled (no code of the version changed, and no line of this file: lines were
# only added): the tests named `test_known_limit_...`, which pin limits the passage states exactly as they are today (the first of them
# an e-mail address the sanitizer leaves in the text it calls clean), and assertions that hold what a changed copy of the version's
# code would break (each one stands beside the claim it belongs to).
from pathlib import Path
import unittest, sys, json, copy, time, hashlib, importlib.util
import re
def ours(cid, low, high):   # a check of the base (built in; the add-on base and its first case) or of this version: in a lab where other versions are laid, their checks stand beside these and may refuse the same forged record
    n = int(re.match(r'S(\d+)', cid).group(1)); return n != 202 and (n < 60 or 200 <= n <= 219 or low <= n <= high)   # S202, the pin of what earlier versions recorded, is left out: once a later version has pinned this version's record, a forged copy of it fails that pin, as it should
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, ACTIONS, Stop, digest
from tools.run_all import pack, scenes, undeclared, MORE, KINDS   # importing the lab's tools loads the kind files: scrub_text is registered from kinds/scrub_text.py
from tools.make_packs import fact, rule, method
from extensions.asks import answer, open_asks
from extensions import ordered_effects as fx
from extensions.ordered_cuts import cut_facts, SOURCE as CUT_SOURCE, DO_NOT_CUT
from extensions.ordered_tiers import tier_faults
from extensions.ordered_tiers import RULE_SET_HOLDS, TIER_PACK_HOLDS   # the two closed lists, held to the letter below

OPAQUE = '0123456789abcdef' * 3   # a long opaque string, as a hash would be
BAD = '/Users/someone ' + OPAQUE   # only a path and a hash: nothing is left once they are redacted
GOOD = 'The feedback command prints nothing when the folder is read-only. Seen in /Users/someone/work/app; reply to someone@example.org.'
SCRUB, WRITE, PUSH = 'scrub@1', 'write-local@1', 'push@1'
CODE = 'scrub-text@1'   # the scrub done by code (pack 122): a method of its own, so an id of its own
REFUSAL = 'Handler refused: sanitizer error: nothing useful is left after redaction (0 letters and digits, 10 needed)'   # the handler's own refusal, in its words, as the kernel records it
DONE, HELD = 'LOCAL_MODEL_EFFECTS_RECORDED', 'SUPPORTED_BY_EVIDENCE'
ZERO = {'compute': 0, 'money': 0, 'attention': 0}
OPT_IN = {'predicate': 'opted_in', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/consent-ledger', 'version': 'consent-1'}
HOOK_Q, BOOT_Q = 'sutra/speed|hook_chain_cut_approved', 'sutra/speed|boot_load_cut_approved'


def load(*names):
    return [pack(n) for n in names]


def looks(s, execute=True):
    return Kernel(s).run_standing(execute=execute)['runs']


def rows(run, op):
    return [e['data'] for e in run['trace'] if e['operation'] == op]


def held(s):
    """What a refusal must leave alone: the evidence, the budget, the provider slots, the grants, the books of the kinds, the scope and the goals."""
    return (digest(s.evidence), dict(s.budget), dict(s.providers), sorted(s.grants), digest(s.active_work), s.scope, list(s.goals))


def words(version, text):
    return {'predicate': 'feedback_given', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/user-typed', 'version': version, 'text': text}


def verifier():
    spec = importlib.util.spec_from_file_location('independent_verify_for_ordered', ROOT / 'qa' / 'independent_verify.py')
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    return v


def check_module():
    """The independent check of this version, loaded the way the verifier loads it: from its file, into a namespace of its own."""
    ns = {}
    exec(compile((ROOT / 'qa' / 'checks' / 'ordered.py').read_text(), 'qa/checks/ordered.py', 'exec'), ns)
    return ns


class OrderedEffects(unittest.TestCase):
    """R73: scrub, write locally, send; the capture is a standing goal of its own."""
    SIM = ('120_feedback', '121_scrub_simulated', '123_team_rail')   # case 54
    CODE = ('120_feedback', '122_scrub_by_code', '123_team_rail')
    DOWN = ('120_feedback', '122_scrub_by_code')                     # no rail pack: the send has no provider

    def test_the_order_comes_from_the_prerequisites_not_from_the_authoring_order(self):   # C1
        packs = load(*self.SIM)
        self.assertEqual([m['id'] for p in packs for m in p.get('methods', [])], [PUSH, WRITE, SCRUB])   # authored: send, write, scrub
        self.assertEqual({m['id']: m['requires'] for p in packs for m in p.get('methods', [])},
                         {PUSH: ['written_locally', 'scrubbed', 'feedback_given'], WRITE: ['scrubbed', 'feedback_given'], SCRUB: ['feedback_given']})
        self.assertEqual((packs[0]['goals'], 'team-rail' in packs[0]['providers'], packs[2]['providers']), (['written_locally', 'feedback_sent'], False, {'team-rail': 2}))
        s = State.from_packs(packs)
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in looks(s, False)],
                         [('written_locally', 'PLAN_READY', [SCRUB, WRITE]), ('feedback_sent', 'PLAN_READY', [SCRUB, WRITE, PUSH])])
        ran = looks(s)
        self.assertEqual([(r['goal'], r['status'], r['actions'], [x['method'] for x in r['model_receipts']]) for r in ran],
                         [('written_locally', DONE, [SCRUB, WRITE], [SCRUB, WRITE]), ('feedback_sent', DONE, [PUSH], [PUSH])])
        for mid in (SCRUB, WRITE, PUSH):   # each row made cites the version of the rows its step required, the words among them
            m = s.methods[mid]
            self.assertEqual(s.fact(m['effect'])['depends_on'], [{'predicate': q, 'version': s.fact(q)['version']} for q in m['requires']], mid)
            self.assertIn('feedback_given', m['requires'])
        self.assertEqual(s.budget, {'compute': 7, 'money': 10, 'attention': 3})
        turned = copy.deepcopy(packs)   # the goals the other way round: the steps still run scrub, write, send, now inside one run
        turned[0]['goals'].reverse()
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in looks(State.from_packs(turned))],
                         [('feedback_sent', DONE, [SCRUB, WRITE, PUSH]), ('written_locally', HELD, [])])
        # The same steps with one prerequisite moved (the local write first, as the brief of this row words it): the order moves with it,
        # and so does what a refused scrub leaves behind. The raw words are written though the scrub stops: that is why the write requires the scrub.
        moved = copy.deepcopy(load(*self.CODE))
        by = {m['id']: m for p in moved for m in p.get('methods', [])}
        by[WRITE]['requires'] = ['feedback_given']
        by[CODE]['requires'] = ['written_locally', 'feedback_given']
        w = State.from_packs(moved)
        self.assertEqual([r['actions'] for r in looks(w, False)], [[WRITE], [WRITE, CODE, PUSH]])
        raw = Kernel(w).on_event(words('words-2', BAD), execute=True)['runs']
        self.assertEqual([(r['status'], r['actions'], r.get('pending'), r.get('stopped')) for r in raw],
                         [(DONE, [WRITE], None, None), ('STEP_STOPPED', [], [CODE, PUSH], {'method': CODE, 'reason': REFUSAL})])
        self.assertEqual([w.fact(p)['truth'] for p in ('written_locally', 'scrubbed', 'feedback_sent')], ['TRUE', 'FALSE', 'FALSE'])

    def test_without_a_scrub_step_nothing_is_offered(self):   # C2
        s = State.from_packs(load('120_feedback', '123_team_rail'))
        before = held(s)
        for execute in (False, True):
            ran = looks(s, execute)
            self.assertEqual([(r['goal'], r['status'], r['work_state'], r['actions'], r['model_receipts'], rows(r, 'METHOD_ABSENT')) for r in ran],
                             [(g, 'METHOD_ABSENT', 'blocked', [], [], [{'predicate': 'scrubbed'}]) for g in ('written_locally', 'feedback_sent')])
        self.assertEqual(held(s), before)

    def test_a_sanitizer_error_stops_both_goals_before_anything_is_written_or_sent(self):   # C3
        s = State.from_packs(load(*self.CODE))
        k = Kernel(s)
        self.assertEqual([r['status'] for r in k.on_event(words('words-2', BAD))['runs']], ['PLAN_READY', 'PLAN_READY'])   # the dry look cannot tell: the sanitizer has not run
        before = held(s)
        stop = {'method': CODE, 'reason': REFUSAL}   # the handler refused in its own words: the kernel's Stop, raised with one text
        want = [('written_locally', 'STEP_STOPPED', 'stopped', [], [], [CODE, WRITE], stop, ZERO), ('feedback_sent', 'STEP_STOPPED', 'stopped', [], [], [CODE, WRITE, PUSH], stop, ZERO)]
        shape = lambda ran: [(r['goal'], r['status'], r['work_state'], r['actions'], r['model_receipts'], r['pending'], r['stopped'], r['cost']) for r in ran]
        ran = k.run_standing(execute=True)['runs']
        self.assertEqual((shape(ran), held(s)), (want, before))   # nothing written, nothing sent, nothing paid
        self.assertEqual([rows(r, 'STEP_STOPPED') for r in ran], [[dict(stop, effect_reads='FALSE')]] * 2)   # one line in each run's record: the step, the reason, and what its effect still reads
        self.assertEqual([(s.fact(p)['truth'], s.fact(p)['source']) for p in ('scrubbed', 'written_locally', 'feedback_sent')], [('FALSE', 'fixture/marker-absent')] * 3)
        self.assertEqual([(j['status'], j['trace_root_sha256']) for j in s.event_journal[-2:]], [('STEP_STOPPED', r['trace_root_sha256']) for r in ran])
        marker = k.on_event({'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': False, 'source': 'hand-written', 'version': 'none'}, execute=True)
        self.assertEqual((marker['status'], marker['runs'], held(s)), ('UNVERIFIED_EVENT_IGNORED', [], before))   # a marker nobody verified opens nothing
        self.assertEqual((shape(k.run_standing(execute=True)['runs']), held(s)), (want, before))               # a second look stops the same way
        twin = Kernel(State.from_packs(load(*self.CODE))).on_event(words('words-2', BAD), execute=True)['runs']
        self.assertEqual([r['trace_root_sha256'] for r in twin], [r['trace_root_sha256'] for r in ran])           # the same stop, the same record
        for text in ('   ', None):   # words that are no text at all stop the same way, with their own reason
            t = State.from_packs(load(*self.CODE))
            empty = Kernel(t).on_event(dict(words('words-2', text)), execute=True)['runs']
            self.assertEqual(([r['stopped'] for r in empty], t.fact('scrubbed')['truth'], t.budget['compute']),
                             ([{'method': CODE, 'reason': 'Handler refused: sanitizer error: no text to scrub'}] * 2, 'FALSE', 10))
        # A known limit, pinned: the kernel does not know who may hand in a marker. A VERIFIED row that says scrubbed is taken, and the refused words are written and sent.
        trusted = k.on_event({'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': True, 'source': 'hand-written', 'version': 'none'}, execute=True)['runs']
        self.assertEqual([r['actions'] for r in trusted], [[WRITE], [PUSH]])

    def test_words_that_can_be_made_safe_are_captured_then_sent_and_so_is_the_next_message(self):   # C4
        s = State.from_packs(load(*self.CODE))
        k = Kernel(s)
        k.on_event(words('words-2', BAD), execute=True)   # refused first, as in the recorded sequence
        ran = k.on_event(words('words-3', GOOD), execute=True)['runs']
        clean, n = fx.scrub(GOOD)
        self.assertEqual((clean, n), ('The feedback command prints nothing when the folder is read-only. Seen in <HOME>/work/app; reply to <EMAIL>.', 2))
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in ran], [('written_locally', DONE, [CODE, WRITE]), ('feedback_sent', DONE, [PUSH])])
        row, version = s.fact('scrubbed'), 'scrub-' + digest(clean)[:12]
        given = {'predicate': 'feedback_given', 'version': 'words-3'}
        self.assertEqual((row['clean_text'], row['version'], row['source'], row['depends_on']), (clean, version, 'LOCAL_SCRUB:scrub-text@1', [given]))
        self.assertEqual(row, {'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': True, 'source': 'LOCAL_SCRUB:scrub-text@1', 'version': version, 'evidence_kind': 'SIMULATED_LOCAL',   # the row whole, against
                               'depends_on': [given], 'clean_text': clean, 'redactions': 2, 'scope': 'sutra/feedback'})                                                              # literals: no field is left unread
        self.assertEqual((s.fact('written_locally')['depends_on'], s.fact('feedback_sent')['depends_on']),
                         ([{'predicate': 'scrubbed', 'version': version}, given], [{'predicate': 'written_locally', 'version': 'local-sim-1'}, {'predicate': 'scrubbed', 'version': version}, given]))
        first = ran[0]['model_receipts'][0]
        self.assertEqual({k: v for k, v in first.items() if k != 'sha256'},   # the receipt whole: what the handler returned, rebuilt as plain data, under the kernel's own four fields
                         {'method': CODE, 'scope': 'sutra/feedback', 'action': 'scrub_text', 'status': 'LOCAL_ONLY', 'model_effect': 'scrubbed', 'redactions': 2, 'clean_sha256': digest(clean)})
        self.assertEqual((type(first['redactions']), first['sha256']), (int, digest({k: v for k, v in first.items() if k != 'sha256'})))
        paid = held(s)
        again = k.run_standing(execute=True)['runs']
        self.assertEqual(([(r['status'], r['actions'], r['model_receipts']) for r in again], held(s)), ([(HELD, [], [])] * 2, paid))   # one more look does and pays nothing
        # The next message scrubs to the SAME clean text (another sender, the same sentence). It is another message: all three steps run again.
        other = GOOD.replace('someone', 'another')
        self.assertEqual((fx.scrub(other)[0], other == GOOD), (clean, False))
        nxt = k.on_event(words('words-4', other), execute=True)['runs']
        self.assertEqual(([r['actions'] for r in nxt], [r.get('skipped') for r in nxt], s.fact('scrubbed')['version'], s.fact('written_locally')['depends_on'][1], s.fact('feedback_sent')['depends_on'][2], s.budget['compute']),
                         ([[CODE, WRITE], [PUSH]], [None, None], version, {'predicate': 'feedback_given', 'version': 'words-4'}, {'predicate': 'feedback_given', 'version': 'words-4'}, 4))
        c = State.from_packs(load(*self.SIM))   # the State of case 54, where the scrub is simulated and every row made has the same version: a second message is still written and sent
        kc = Kernel(c)
        kc.run_standing(execute=True)
        second = kc.on_event(words('words-2', 'A second, different message about another fault.'), execute=True)['runs']
        self.assertEqual([(r['status'], r['actions'], r.get('skipped')) for r in second], [(DONE, [SCRUB, WRITE], None), (DONE, [PUSH], None)])
        same = kc.on_event(words('words-2', 'Other words, handed in under the version already on file.'), execute=True)['runs']
        self.assertEqual([(r['status'], r['actions']) for r in same], [(HELD, []), (HELD, [])])   # a known limit, pinned: a message is told apart by the version of its row

    def test_the_capture_does_not_wait_for_the_send(self):   # C5
        s = State.from_packs(load(*self.DOWN))
        k = Kernel(s)
        first = k.run_standing(execute=True)['runs']
        self.assertEqual([(r['goal'], r['status'], r['actions'], r['stop_reasons']) for r in first],
                         [('written_locally', DONE, [CODE, WRITE], []), ('feedback_sent', 'PROVIDER_REQUIRED', [], ['PROVIDER_REQUIRED'])])
        self.assertEqual(([s.fact(p)['truth'] for p in ('scrubbed', 'written_locally', 'feedback_sent')], s.budget['compute'], s.providers), (['TRUE', 'TRUE', 'FALSE'], 8, {'local-disk': 1, 'sanitizer': 1}))
        written, kept = s.fact('written_locally'), held(s)
        again = k.run_standing(execute=True)['runs']
        self.assertEqual(([(r['status'], r['actions'], r['model_receipts']) for r in again], held(s)), ([(HELD, [], []), ('PROVIDER_REQUIRED', [], [])], kept))   # the words stay written; nothing is paid for looking
        s.apply(pack('123_team_rail'))   # the rail is there again
        retry = k.run_standing(execute=True)['runs']
        self.assertEqual([(r['status'], r['actions']) for r in retry], [(HELD, []), (DONE, [PUSH])])   # the send alone: the retry of what was written
        self.assertEqual((s.fact('written_locally'), s.fact('feedback_sent')['depends_on'][0], s.budget['compute'], s.providers['team-rail']),
                         (written, {'predicate': 'written_locally', 'version': written['version']}, 7, 1))
        sim = load('120_feedback', '121_scrub_simulated')   # the same with the simulated scrub, in either order of the goals
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in looks(State.from_packs(sim))], [('written_locally', DONE, [SCRUB, WRITE]), ('feedback_sent', 'PROVIDER_REQUIRED', [])])
        turned = copy.deepcopy(sim)
        turned[0]['goals'].reverse()
        self.assertEqual([(r['goal'], r['status'], r['actions']) for r in looks(State.from_packs(turned))], [('feedback_sent', 'PROVIDER_REQUIRED', []), ('written_locally', DONE, [SCRUB, WRITE])])
        only = copy.deepcopy(sim)   # what the standing goal is for: with the send as the only goal the plan is admitted whole, and nothing is written when the rail has no slot
        only[0]['goals'] = ['feedback_sent']
        o = State.from_packs(only)
        self.assertEqual(([(r['status'], r['actions']) for r in looks(o)], o.fact('written_locally')['truth']), ([('PROVIDER_REQUIRED', [])], 'FALSE'))
        # A known limit, pinned: one State holds one message. Words that arrive while an earlier message is written and unsent are captured in its place
        # (the deployed script keeps both files and sends both at the next call).
        d = State.from_packs(load(*self.DOWN))
        kd = Kernel(d)
        kd.run_standing(execute=True)
        earlier = d.fact('scrubbed')['clean_text']
        nxt = kd.on_event(words('words-2', 'A later message, typed while the rail was still down.'), execute=True)['runs']
        self.assertEqual(([(r['status'], r['actions']) for r in nxt], d.fact('scrubbed')['clean_text'] == earlier, d.fact('written_locally')['depends_on'][1]['version']),
                         ([(DONE, [CODE, WRITE]), ('PROVIDER_REQUIRED', [])], False, 'words-2'))
        # So the earlier words are lost: when the rail is back one send runs, on the later message. The earlier message, written and never sent, is nowhere in the State:
        # neither its clean text nor its raw words (the row of the words was replaced, and the scrubbed row with it).
        d.apply(pack('123_team_rail'))
        back = kd.run_standing(execute=True)['runs']
        self.assertEqual(([(r['goal'], r['status'], r['actions']) for r in back], d.fact('feedback_sent')['depends_on'][2], earlier in json.dumps(d.evidence), 'someone' in json.dumps(d.evidence), d.providers['team-rail']),
                         ([('written_locally', HELD, []), ('feedback_sent', DONE, [PUSH])], {'predicate': 'feedback_given', 'version': 'words-2'}, False, False, 1))

    def test_the_scrub_kind_is_declared_by_its_file_and_each_scrub_is_a_step_of_its_own(self):
        # The kind arrives as its own file, kinds/scrub_text.py, which registers it with the kernel's register: every State knows it, with the registered handler and hook.
        kind = ACTIONS['scrub_text']
        self.assertEqual(('scrub_text' in KINDS, undeclared(), sorted(kind), kind['run'].__module__, kind['run'].__name__, Path(sys.modules['kinds.scrub_text'].__file__)),
                         (True, [], ['check', 'run'], 'kinds.scrub_text', 'scrub_step', ROOT / 'kinds' / 'scrub_text.py'))
        for s in (State(), State.from_packs(load(*self.CODE)), State.from_packs(load(*self.SIM))):
            self.assertEqual((sorted(s.actions['scrub_text']), s.actions['scrub_text']['run'] is kind['run'], s.actions['scrub_text']['check'] is kind['check']), (['check', 'run'], True, True))
        self.assertFalse(hasattr(fx, 'with_scrub') or hasattr(fx, 'scrub_step') or hasattr(fx, 'register'))   # the extension holds the sanitizer only: no handler, no registry, no State of its own
        # The two scrubs are two methods for one row, so each has an id of its own: a method id names one method in the whole lab.
        sim, code = pack('121_scrub_simulated')['methods'][0], pack('122_scrub_by_code')['methods'][0]
        self.assertEqual((sim['id'], code['id'], sim['action'], code['action'], code['scrubs'], sim['cost'] == code['cost'], CODE < SCRUB), (SCRUB, CODE, 'simulate_fact', 'scrub_text', 'feedback_given', True, True))
        self.assertEqual({k: (sim.get(k), code.get(k)) for k in set(sim) | set(code) if sim.get(k) != code.get(k)},
                         {'id': (SCRUB, CODE), 'grant': ('action:' + SCRUB, 'action:' + CODE), 'action': ('simulate_fact', 'scrub_text'), 'scrubs': (None, 'feedback_given')})
        # A known limit, pinned: a State may hold both scrub packs. Then two plans make the same row at the same cost, and the kernel's rule for equal plans (the order of
        # the step names) takes the scrub by code, in either order of loading: words the sanitizer refuses stop there, at every look, and the simulated scrub never runs.
        stop = {'method': CODE, 'reason': REFUSAL}
        for names in (('120_feedback', '121_scrub_simulated', '122_scrub_by_code', '123_team_rail'), ('120_feedback', '122_scrub_by_code', '121_scrub_simulated', '123_team_rail')):
            w = State.from_packs(load(*names))
            self.assertEqual((sorted(m for m in w.methods if w.methods[m]['effect'] == 'scrubbed'), [r['actions'] for r in looks(w, False)]), ([CODE, SCRUB], [[CODE, WRITE], [CODE, WRITE, PUSH]]))
            k = Kernel(w)
            before = None
            for ran in (k.on_event(words('words-2', BAD), execute=True)['runs'], k.run_standing(execute=True)['runs']):
                self.assertEqual([(r['status'], r['actions'], r['stopped']) for r in ran], [('STEP_STOPPED', [], stop)] * 2)
                self.assertEqual(([w.fact(p)['truth'] for p in ('scrubbed', 'written_locally', 'feedback_sent')], w.budget['compute']), (['FALSE'] * 3, 10))
                before = before or held(w)
                self.assertEqual(held(w), before)
            self.assertEqual([r['actions'] for r in k.on_event(words('words-3', GOOD), execute=True)['runs']], [[CODE, WRITE], [PUSH]])
        # What keeps the simulated scrub out of such a State is that order and the equal cost, nothing else: named ahead of the scrub by code, or priced below it
        # (both in memory here), the simulated scrub is the one taken and the words the sanitizer refuses are written and sent. So a State is given pack 121 or pack 122.
        for change in (lambda p: (p['methods'][0].update(id='a-scrub@1', grant='action:a-scrub@1'), p.update(grants=['action:a-scrub@1'])),
                       lambda p: p['methods'][0].update(cost=dict(ZERO))):
            other = copy.deepcopy(pack('121_scrub_simulated'))
            change(other)
            w = State.from_packs([pack('120_feedback'), other, pack('122_scrub_by_code'), pack('123_team_rail')])
            ran = Kernel(w).on_event(words('words-2', BAD), execute=True)['runs']
            self.assertEqual(([(r['status'], r['actions']) for r in ran], w.fact('feedback_sent')['truth']), ([(DONE, [other['methods'][0]['id'], WRITE]), (DONE, [PUSH])], 'TRUE'))
        # The kind's own check, run when a pack is applied: a scrub names the row it reads, and that row is one of its prerequisites.
        w = State.from_packs(load('120_feedback'))
        before = (held(w), list(w.methods), copy.deepcopy(w.loaded))
        bad = copy.deepcopy(pack('122_scrub_by_code'))
        del bad['methods'][0]['scrubs']
        with self.assertRaises(ValueError):   # a scrub that does not name the row it reads
            w.apply(bad)
        bad['methods'][0]['scrubs'] = 'written_locally'
        with self.assertRaises(ValueError):   # or names a row that is not one of its prerequisites
            w.apply(bad)
        self.assertEqual((held(w), list(w.methods), w.loaded), before)
        # The handler reads the row its step names under `scrubs`, whichever of its prerequisites that is: here a note beside the words (both packs changed in memory).
        noted = copy.deepcopy(load(*self.CODE))
        noted[0]['evidence'].append(dict(words('note-1', 'A note beside the words, kept in /home/another/notes for later reading.'), predicate='note_given'))
        noted[1]['methods'][0].update(requires=['feedback_given', 'note_given'], scrubs='note_given')
        w = State.from_packs(noted)
        self.assertEqual(([r['actions'] for r in looks(w)], w.fact('scrubbed')['clean_text'], w.fact('scrubbed')['redactions'], w.fact('scrubbed')['depends_on']),
                         ([[CODE, WRITE], [PUSH]], 'A note beside the words, kept in <HOME>/notes for later reading.', 1,
                          [{'predicate': 'feedback_given', 'version': 'words-1'}, {'predicate': 'note_given', 'version': 'note-1'}]))

    def test_the_sanitizer_redacts_in_the_deployed_order_and_refuses_what_says_nothing(self):
        for text in (None, '', '   ', 42, '/Users/someone', OPAQUE + ' ' + OPAQUE, 'someone@example.org', 'Ten letter', '<TODO> Ten letter', 'привет, мир: это просто слова'):
            with self.assertRaises(fx.SanitizerError, msg=repr(text)):
                fx.scrub(text)
        self.assertEqual(fx.scrub('Ten letters'), ('Ten letters', 0))                    # ten letters and digits are enough, nine are not
        self.assertEqual(fx.scrub('привет Ten letters'), ('привет Ten letters', 0))     # only ASCII letters and digits count, as in the deployed script
        self.assertEqual(fx.scrub('See /home/someone/notes and the text beside it'), ('See <HOME>/notes and the text beside it', 1))
        self.assertEqual(fx.scrub('Seen in /Users/someone and the folder beside it is read-only.'), ('Seen in <HOME> and the folder beside it is read-only.', 1))   # a home path ends at the first space: the words after it stay
        self.assertEqual(fx.scrub('a' * 39 + ' and ten more letters'), ('a' * 39 + ' and ten more letters', 0))   # 39 characters are not yet an opaque string
        self.assertEqual(fx.scrub('a' * 40 + ' and ten more letters'), ('<OPAQUE> and ten more letters', 1))      # 40 are
        # The order of the detectors shows where a path or an address holds a long name: path first, then address, then the opaque string.
        self.assertEqual(fx.scrub('/Users/' + 'a' * 45 + '/notes and the text beside it'), ('<HOME>/notes and the text beside it', 1))
        self.assertEqual(fx.scrub('a' * 45 + '@example.org wrote ten letters'), ('<EMAIL> wrote ten letters', 1))
        self.assertEqual(fx.scrub('x@y.org, a.b+c@d-e.co.uk and not@this wrote ten letters'), ('<EMAIL>, <EMAIL> and not@this wrote ten letters', 2))
        started = time.perf_counter()   # a long text with no address in it is read once, not once per character (which would take many seconds here)
        clean, n = fx.scrub('ten letters ' + 'a.' * 20000)
        self.assertEqual((n, len(clean)), (0, 40012))
        self.assertLess(time.perf_counter() - started, 2)
        # A decision that stands on the effect: the step refuses instead of writing over it (the kernel's Stop, with one text), and through the kernel both goals are refused.
        s = State.from_packs(load(*self.CODE))
        s.observe({'predicate': 'scrubbed', 'truth': 'FALSE', 'verified': True, 'final': True, 'source': 'owner', 'version': 'no-1'})
        before = held(s)
        scrub_step = ACTIONS['scrub_text']['run']
        with self.assertRaises(Stop) as refused:
            scrub_step(s, s.methods[CODE], CODE, [{'predicate': 'feedback_given', 'version': 'words-1'}])
        self.assertEqual((refused.exception.args, held(s)), (('A decision stands on this effect',), before))   # the handler wrote no row; the journal says a decision turned one away
        self.assertEqual(s.event_journal[-1], {'status': 'DECISION_STANDS', 'scope': 'sutra/feedback', 'predicate': 'scrubbed'})
        self.assertEqual(([(r['status'], r['actions']) for r in looks(s)], held(s)), ([('REFUSED', []), ('REFUSED', [])], before))
        # The handler's refusal of the words is the same class, raised with one text: that is why the kernel records it in the handler's words.
        t = State.from_packs(load(*self.CODE))
        t.observe(words('words-2', BAD))
        before = held(t)
        with self.assertRaises(Stop) as refused:
            scrub_step(t, t.methods[CODE], CODE, [{'predicate': 'feedback_given', 'version': 'words-2'}])
        self.assertEqual((refused.exception.args, held(t)), (('sanitizer error: nothing useful is left after redaction (0 letters and digits, 10 needed)',), before))

    def test_known_limit_an_address_joined_to_the_one_before_it_stays_in_the_text_called_clean(self):
        """The FIRST of the passage's known limits, pinned as it is today; its repair is the first thing owed to the next version.
        The e-mail detector of extensions/ordered_effects.py begins a match only where the character before it is not one an address may hold (a look-behind,
        put there so that a long text is read once). After one address it therefore cannot begin the next one when nothing but such characters stands between
        the two: the second address stays in the text the scrub calls clean, and the State writes and sends it as scrubbed. The check module scrubs with its
        own copy of the sanitizer, which has no look-behind and redacts both: the two readings of one scrub disagree on such words."""
        own = check_module()['_scrub']   # the check module's own copy: -> (the clean text, the redactions, the letters and digits left)
        say = 'Reply to anna@example.org%sben@example.org about the start command.'
        for glue in ('-', '+', '_', '%2C', '9', '.9'):   # joined by a digit or by one of _ % + -, or by a dot before one of these (a list written with - or +, or URL-encoded: %2C)
            # half one: the extension leaves the second address in the text it calls clean, and counts one redaction
            self.assertEqual(fx.scrub(say % glue), ('Reply to <EMAIL>' + glue + 'ben@example.org about the start command.', 1), glue)
            # half two: the check module's copy redacts both
            self.assertEqual(own(say % glue)[:2], ('Reply to <EMAIL><EMAIL> about the start command.', 2), glue)
        for glue in (', ', ' ', ';', '/', ' and '):   # with a space or any other character between them the two readings agree: both addresses are redacted
            self.assertEqual((fx.scrub(say % glue), own(say % glue)[:2]), (('Reply to <EMAIL>' + glue + '<EMAIL> about the start command.', 2),) * 2, glue)
        for glue in ('.', 'x'):   # joined by a dot and letters, or by letters alone, the first match takes them in and what is left is no address to either reading
            self.assertEqual((fx.scrub(say % glue), own(say % glue)[:2]), (('Reply to <EMAIL>@example.org about the start command.', 1),) * 2, glue)
        s = State.from_packs(load(*self.CODE))   # through the kernel: such words are scrubbed, written and sent, with the second address in the row called scrubbed
        ran = Kernel(s).on_event(words('words-2', say % '-'), execute=True)['runs']
        row, receipt = s.fact('scrubbed'), ran[0]['model_receipts'][0]
        self.assertEqual(([(r['status'], r['actions']) for r in ran], row['clean_text'], row['redactions'], receipt['redactions'], receipt['clean_sha256'], s.fact('feedback_sent')['truth']),
                         ([(DONE, [CODE, WRITE]), (DONE, [PUSH])], 'Reply to <EMAIL>-ben@example.org about the start command.', 1, 1, digest(row['clean_text']), 'TRUE'))
        # What follows for this version's own checks: their bookkeeper scrubs with that copy, so an honest life made with such words (made here in memory and kept the
        # way tools/scenes/ordered.py keeps a life: its packs, a snapshot at the start, and for its one step what was done, what came back and a snapshot after it) is
        # refused at that step: the receipt, the version the send's search cites and the stored row are not what the bookkeeper rebuilds. The recorded words do not trigger it.
        check, chain = check_module(), verifier().check_chain
        files = {n: pack(n) for n in check['PACKS']}

        def judged(text):
            s = State.from_packs(load(*self.CODE))
            snap = lambda: {'scope': s.scope, 'budget': dict(s.budget), 'providers': dict(s.providers), 'grants': sorted(s.grants), 'open_asks': open_asks(s),
                            'journal': [j['status'] for j in s.event_journal], 'reads': {p: s.fact(p)['truth'] for p in check['WORDS']},
                            'rows': {p: copy.deepcopy(s.evidence.get(s.scope + '|' + p)) for p in check['WORDS']}}
            row = words('words-2', text)
            life = {'packs': list(self.CODE), 'start': snap(), 'steps': {}}
            life['steps']['sent'] = {'does': {'event': copy.deepcopy(row)}, 'result': Kernel(s).on_event(row, execute=True), 'after': snap()}
            return check['_life'](json.loads(json.dumps(life)), files, (list(self.CODE), check['WORDS'], [('sent', ('event', row), check['BY_CODE'])]), chain)
        self.assertEqual((judged(GOOD), judged(say % ', ')), ([], []))   # honest lives the check accepts: words like the recorded ones, and two addresses with a comma between them
        self.assertEqual(judged(say % '-'), [('sent', 'written_locally: model_receipts'), ('sent', 'written_locally: trace receipts'), ('sent', 'feedback_sent: trace search'), ('sent', 'snapshot')])

    def test_known_limit_a_state_captures_two_messages(self):
        """A known limit, pinned as it is today: pack 120 gives the sanitizer and the disk two slots each and a slot never comes back, so one State scrubs and
        writes two messages in its life. The third is not captured, whether or not a send ever ran: both goals are blocked for a provider, nothing is paid, and
        its words sit on file unscrubbed. The capture does not wait for the send; it does wait for a slot at the sanitizer and at the disk."""
        self.assertEqual((pack('120_feedback')['providers'], pack('123_team_rail')['providers']), ({'local-disk': 2, 'sanitizer': 2}, {'team-rail': 2}))
        say = lambda v: words(v, 'The start command prints nothing in a read-only folder, message ' + v + '.')
        shape = lambda ran: [(r['goal'], r['status'], r['actions'], r['stop_reasons']) for r in ran]
        no_slot = lambda goal: (goal, 'PROVIDER_REQUIRED', [], ['PROVIDER_REQUIRED'])
        blocked = [no_slot('written_locally'), no_slot('feedback_sent')]
        markers = lambda s: [s.fact(p)['truth'] for p in ('scrubbed', 'written_locally', 'feedback_sent')]
        for names, scrub_step, rail, left, reads in ((self.CODE, CODE, True, 4, ['UNKNOWN'] * 3), (self.SIM, SCRUB, True, 4, ['UNKNOWN'] * 3), (self.DOWN, CODE, False, 6, ['UNKNOWN', 'UNKNOWN', 'FALSE'])):
            s = State.from_packs(load(*names))
            k = Kernel(s)
            captured = [('written_locally', DONE, [scrub_step, WRITE], []), ('feedback_sent', DONE, [PUSH], []) if rail else no_slot('feedback_sent')]
            for v in ('a', 'b'):   # two messages are scrubbed and written (and sent, where there is a rail)
                self.assertEqual(shape(k.on_event(say(v), execute=True)['runs']), captured, (names, v))
            paid = (dict(s.budget), dict(s.providers))
            self.assertEqual((s.budget['compute'], s.providers['sanitizer'], s.providers['local-disk']), (left, 0, 0), names)
            third = k.on_event(say('c'), execute=True)['runs']   # the third is not captured: the markers of the second no longer read, and nothing takes their place
            self.assertEqual((shape(third), [r['model_receipts'] for r in third], (dict(s.budget), dict(s.providers)), markers(s)), (blocked, [[], []], paid, reads), names)
            on_file = s.fact('feedback_given')   # its words are the row on file, as they were typed: nothing scrubbed them and nothing wrote them
            self.assertEqual((on_file['version'], on_file['truth'], on_file['text']), ('c', 'TRUE', say('c')['text']), names)
            before = held(s)
            self.assertEqual((shape(k.run_standing(execute=True)['runs']), held(s)), (blocked, before), names)   # a later look finds the same: no slot comes back
        for provider in ('sanitizer', 'local-disk'):   # the same from the first look, in a State given no slot there (in memory): both goals blocked, unpaid, nothing scrubbed or written
            packs = copy.deepcopy(load(*self.CODE))
            packs[0]['providers'][provider] = 0
            s = State.from_packs(packs)
            before = held(s)
            self.assertEqual((shape(looks(s)), held(s), markers(s)), (blocked, before, ['FALSE'] * 3), provider)


class DataBeforeCuts(unittest.TestCase):
    """R82: a cut needs its baseline, its sample, its guardrails and its own approval."""
    DESK = ('124_cut_desk',)

    def _hook(self, edit=None):
        p = copy.deepcopy(pack('124_cut_desk')['proposals'][0])
        if edit:
            edit(p)
        return p

    def _row(self, part, edit=None):
        return [r for r in cut_facts(self._hook(edit)) if r['predicate'] == 'hook_chain_' + part][0]

    def test_the_adapter_turns_a_proposal_into_three_rows_that_follow_from_what_was_measured(self):   # C6
        p = pack('124_cut_desk')
        self.assertEqual([r for r in p['evidence'] if r['source'] == CUT_SOURCE], cut_facts(p['proposals'][0]) + cut_facts(p['proposals'][1]))
        truth = lambda edit=None: ''.join(r['truth'][0] for r in cut_facts(self._hook(edit)))   # baseline cited, samples, guardrails: T or F each
        self.assertEqual(truth(), 'TTT')
        base, over, guard = (lambda **kw: (lambda q: q['baseline'].update(**kw))), (lambda **kw: (lambda q: q['guardrails']['override_count_total'].update(**kw))), (lambda **kw: (lambda q: q['guardrails'].update(**kw)))
        touch = lambda *names: (lambda q: q.update(touches=list(names)))
        table = [(base(samples=100), 'TTT'), (base(samples=99), 'TFT'), (base(samples='212'), 'TFT'), (base(samples=True), 'TFT'), (base(samples=-5), 'TFT'), (base(samples=212.0), 'TFT'),
                 (base(source=' '), 'FTT'), (base(value=640.5), 'FTT'), (base(value=-1), 'FTT'), (base(value=True), 'FTT'), (base(value=0), 'TTT'),
                 (lambda q: q['baseline'].pop('metric'), 'FTT'), (lambda q: q.pop('baseline'), 'FFT'), (lambda q: q.update(baseline='a guess'), 'FFT'),
                 (over(now=15), 'TTF'), (over(now=13), 'TTT'), (over(before=-2, now=-3), 'TTF'), (over(now=14.0), 'TTF'), (over(now='14'), 'TTF'), (over(before=14.5), 'TTF'),
                 (guard(triage_correct_pct=90), 'TTT'), (guard(triage_correct_pct=89), 'TTF'), (guard(triage_correct_pct=96.5), 'TTF'), (guard(triage_correct_pct='96'), 'TTF'),
                 (guard(triage_correct_pct=True), 'TTF'), (guard(triage_correct_pct=-1), 'TTF'), (lambda q: q['guardrails'].pop('override_count_total'), 'TTF'), (lambda q: q.pop('guardrails'), 'TTF'),
                 (touch('hook-pretool-chain', 'another-thing'), 'TTT'), (lambda q: q.pop('touches'), 'TTF'), (touch(), 'TTF'), (lambda q: q.update(touches='hook-pretool-chain'), 'TTF'),
                 (touch(['proto-000-text']), 'TTF'), (touch(' proto-000-text'), 'TTF'), (touch('hook-pretool-chain', 'proto-000-text '), 'TTF'), (touch('PROTO-000-TEXT'), 'TTF'),
                 (touch('hook-pretool-chain', 7), 'TTF'), (touch('hook-pretool-chain', None), 'TTF')]
        table += [(touch('hook-pretool-chain', name), 'TTF') for name in DO_NOT_CUT] + [(touch(name), 'TTF') for name in DO_NOT_CUT]   # each of the four things that are never cut
        self.assertEqual(len(DO_NOT_CUT), 4)
        for edit, want in table:
            self.assertEqual(truth(edit), want, cut_facts(self._hook(edit)))
        self.assertEqual(self._row('guardrails_hold', touch('hook-pretool-chain', 'policy-coverage-markers', 'proto-000-text'))['measured']['touches_do_not_cut'], ['policy-coverage-markers', 'proto-000-text'])
        self.assertEqual(self._row('guardrails_hold', touch('hook-pretool-chain', 'proto-000-text', 'proto-000-text', 'policy-coverage-markers'))['measured']['touches_do_not_cut'],
                         ['policy-coverage-markers', 'proto-000-text'])   # a never-cut name the proposal lists twice is named once
        self.assertEqual(truth(base(source='a guess', metric='feels slow', value=0)), 'TTT')   # a known limit, pinned: cited means a source, a metric and a value are named, not that the source is the charter's data
        for bad in ({}, {'cut': ''}, {'cut': 'two words'}, {'cut': 7}, None):   # a proposal that does not name its cut is refused: the rows would have no name
            with self.assertRaises(ValueError):
                cut_facts(bad)
        # The version of a row names its verdict (the row, its truth, the floors it was tested against), not its numbers.
        first = cut_facts(self._hook())
        named = lambda name, floors: 'cut-' + digest({'row': name, 'truth': 'TRUE', 'floors': floors})[:12]
        self.assertEqual((CUT_SOURCE, first), ('adapter:ordered/cut@1', [   # the three rows whole, against literals: the source, the proposal checked, the question asked and what was measured
            {'predicate': 'hook_chain_baseline_cited', 'truth': 'TRUE', 'verified': True, 'source': 'adapter:ordered/cut@1', 'version': named('hook_chain_baseline_cited', {}), 'checked': 'cut-proposal-hook-chain',
             'question': 'the proposal cites a measured baseline: where it was measured, which metric, what value',
             'measured': {'source': 'holding/LATENCY-LOG.jsonl', 'metric': 'hook_chain_overhead_p95_ms', 'value': 640}},
            {'predicate': 'hook_chain_samples_ge_100', 'truth': 'TRUE', 'verified': True, 'source': 'adapter:ordered/cut@1', 'version': named('hook_chain_samples_ge_100', {'floor': 100}), 'checked': 'cut-proposal-hook-chain',
             'question': 'the baseline rests on at least 100 samples', 'measured': {'samples': 212, 'floor': 100}},
            {'predicate': 'hook_chain_guardrails_hold', 'truth': 'TRUE', 'verified': True, 'source': 'adapter:ordered/cut@1', 'version': named('hook_chain_guardrails_hold', {'triage_floor': 90}), 'checked': 'cut-proposal-hook-chain',
             'question': 'the override count has not risen, triage accuracy is 90 or more, and nothing on the do-not-cut list is touched',
             'measured': {'override_count_before': 14, 'override_count_now': 14, 'triage_correct_pct': 96, 'triage_floor': 90, 'touches_do_not_cut': []}}]))
        more = cut_facts(self._hook(lambda q: (q['baseline'].update(samples=213, value=300), q['guardrails']['override_count_total'].update(now=13), q['guardrails'].update(triage_correct_pct=91))))
        shrunk = cut_facts(self._hook(base(samples=42)))
        self.assertEqual(([r['version'] for r in more] == [r['version'] for r in first], [r['measured'] == f['measured'] for r, f in zip(more, first)]), (True, [False, False, False]))
        self.assertEqual([a['version'] == b['version'] for a, b in zip(first, shrunk)], [True, False, True])
        for r in first + more + shrunk:
            floors = {k: v for k, v in r['measured'].items() if k.endswith('floor')}
            self.assertEqual((r['verified'], r['source'], r['version']), (True, CUT_SOURCE, 'cut-' + digest({'row': r['predicate'], 'truth': r['truth'], 'floors': floors})[:12]))
        self.assertEqual(([sorted(k for k in r['measured'] if k.endswith('floor')) for r in first], len({r['version'] for r in first + shrunk})), ([[], ['floor'], ['triage_floor']], 4))
        s = State.from_packs(load(*self.DESK))   # the rows the State holds are the adapter's rows
        self.assertEqual([{k: v for k, v in s.fact(r['predicate']).items() if k != 'scope'} for r in first], first)

    def test_a_cut_with_its_data_asks_once_and_ships_only_on_its_own_yes(self):   # C7, C8
        s = State.from_packs(load(*self.DESK))
        k = Kernel(s)
        first = k.run_standing(execute=True)['runs']
        self.assertEqual([(r['status'], r['actions'], r['pending']) for r in first],
                         [('WAITING', ['ask-hook-chain-cut-approval@1'], ['ship-hook-chain-cut@1']), ('WAITING', ['ask-boot-load-cut-approval@1'], ['ship-boot-load-cut@1'])])
        hook, boot = (r['model_receipts'][0] for r in first)
        self.assertEqual((hook['ask']['to'], hook['ask']['predicate'], boot['ask']['predicate'], s.budget['attention']), ('founder', 'hook_chain_cut_approved', 'boot_load_cut_approved', 1))
        self.assertEqual([s.fact(p)['truth'] for p in ('hook_chain_cut_shipped', 'boot_load_cut_shipped')], ['FALSE', 'FALSE'])
        asked = held(s)
        again = k.run_standing(execute=True)['runs']   # asked once: a second look asks nobody and pays nothing
        self.assertEqual(([r['status'] for r in again], [r['model_receipts'] for r in again], held(s)), (['WAITING', 'WAITING'], [[], []], asked))
        waits = k.on_event(self._row('samples_ge_100', lambda q: q['baseline'].update(samples=213)), execute=True)['runs'][0]   # a part measured again while the question is out: still one question
        self.assertEqual((waits['status'], waits['model_receipts'], s.budget['attention'], list(open_asks(s))), ('WAITING', [], 1, [HOOK_Q, BOOT_Q]))
        yes = answer(k, hook, 'TRUE', 'founder', execute=True)
        self.assertEqual((yes['affected'], [r['actions'] for r in yes['runs']]), (['hook_chain_cut_landed'], [['ship-hook-chain-cut@1']]))
        self.assertEqual((list(open_asks(s)), s.fact('boot_load_cut_approved')['truth'], s.fact('boot_load_cut_shipped')['truth'], s.fact('hook_chain_cut_shipped')['truth']),
                         ([BOOT_Q], 'UNKNOWN', 'FALSE', 'TRUE'))
        before = held(s)
        for stamp in (lambda: answer(k, hook, 'TRUE', 'founder', execute=True),                                                            # the yes for one cut cannot be used again
                      lambda: answer(k, dict(hook, ask=dict(hook['ask'], predicate='boot_load_cut_approved')), 'TRUE', 'founder', execute=True),   # nor turned towards the other cut's question
                      lambda: answer(k, boot, 'TRUE', 'operations', execute=True)):                                                        # and only the founder answers
            with self.assertRaises(ValueError):
                stamp()
        self.assertEqual(held(s), before)
        no = answer(k, boot, 'FALSE', 'founder', execute=True)['runs'][0]
        self.assertEqual((no['status'], no['actions'], no['model_receipts'], s.fact('boot_load_cut_shipped')['truth'], open_asks(s)), ('REFUSED', [], [], 'FALSE', {}))
        paid = (dict(s.budget), dict(s.providers))
        self.assertEqual(([r['status'] for r in k.run_standing(execute=True)['runs']], (dict(s.budget), dict(s.providers))), ([HELD, 'REFUSED'], paid))
        # A known limit, pinned: the kernel does not know who may hand in an approval. A VERIFIED row that says approved ships the cut with the founder's question still out.
        t = State.from_packs(load(*self.DESK))
        kt = Kernel(t)
        kt.run_standing(execute=True)
        handed = kt.on_event({'predicate': 'hook_chain_cut_approved', 'truth': 'TRUE', 'verified': True, 'source': 'hand-written', 'version': 'none'}, execute=True)['runs'][0]
        self.assertEqual((handed['actions'], list(open_asks(t))), (['ship-hook-chain-cut@1'], [HOOK_Q, BOOT_Q]))

    def test_a_false_part_is_named_and_nothing_is_asked_or_shipped(self):   # C9
        edits = {'baseline_cited': lambda q: q.update(baseline={'samples': 212}), 'samples_ge_100': lambda q: q['baseline'].update(samples=42),
                 'guardrails_hold': lambda q: q['guardrails']['override_count_total'].update(now=17)}
        cases = list(edits.items()) + [('guardrails_hold', lambda q: q['touches'].append('proto-000-text'))]   # a cut that touches what is never cut
        for part, edit in cases:
            s = State.from_packs(load(*self.DESK))
            k = Kernel(s)
            before = (dict(s.budget), dict(s.providers))
            r = k.on_event(self._row(part, edit), execute=True)['runs'][0]
            self.assertEqual((r['status'], r['actions'], r['model_receipts'], rows(r, 'METHOD_ABSENT'), open_asks(s), (dict(s.budget), dict(s.providers)), s.fact('hook_chain_cut_shipped')['truth']),
                             ('METHOD_ABSENT', [], [], [{'predicate': 'hook_chain_' + part}], {}, before, 'FALSE'), part)
            both = k.run_standing(execute=True)['runs']   # the other cut, whose data is whole, still asks its own question
            self.assertEqual(([x['status'] for x in both], list(open_asks(s))), (['METHOD_ABSENT', 'WAITING'], [BOOT_Q]), part)
        bare = copy.deepcopy(pack('124_cut_desk'))   # a row that is not there at all is unknown, not false: the look asks for the evidence
        bare['evidence'] = [e for e in bare['evidence'] if e['predicate'] != 'hook_chain_baseline_cited']
        r = looks(State.from_packs([bare]))[0]
        self.assertEqual((r['status'], rows(r, 'QUERY_EVIDENCE'), r['model_receipts']), ('QUERY_EVIDENCE', [{'predicate': 'hook_chain_baseline_cited'}], []))
        s = State.from_packs(load(*self.DESK))   # a yes does not stand in for the data
        k = Kernel(s)
        asked = k.run_standing(execute=True)['runs'][0]
        k.on_event(self._row('samples_ge_100', edits['samples_ge_100']), execute=True)
        spent = (dict(s.budget), dict(s.providers))
        yes = answer(k, asked['model_receipts'][0], 'TRUE', 'founder', execute=True)['runs'][0]
        self.assertEqual((yes['status'], yes['model_receipts'], rows(yes, 'METHOD_ABSENT'), s.fact('hook_chain_cut_approved')['truth'], s.fact('hook_chain_cut_shipped')['truth'], (dict(s.budget), dict(s.providers))),
                         ('METHOD_ABSENT', [], [{'predicate': 'hook_chain_samples_ge_100'}], 'TRUE', 'FALSE', spent))
        back = k.on_event(self._row('samples_ge_100'), execute=True)['runs'][0]   # a known limit, pinned: the yes is a decision and stands, so when the sample is back the cut ships on it
        self.assertEqual((back['status'], back['actions']), (DONE, ['ship-hook-chain-cut@1']))
        broke = k.on_event(self._row('guardrails_hold', edits['guardrails_hold']), execute=True)['runs'][0]   # after the cut landed, a broken guardrail blocks the standing goal
        self.assertEqual((broke['status'], rows(broke, 'METHOD_ABSENT'), broke['model_receipts'], s.fact('hook_chain_cut_shipped')['truth']),
                         ('METHOD_ABSENT', [{'predicate': 'hook_chain_guardrails_hold'}], [], 'UNKNOWN'))
        # A known limit, pinned: a look names the first part of a rule that is not true, not all of them (three false parts, then two: one name each time).
        for edit, parts, named in ((lambda q: (q.update(baseline={'samples': 42}), q['guardrails']['override_count_total'].update(now=17)), 'FFF', 'baseline_cited'),
                                   (lambda q: (q['baseline'].update(samples=42), q['guardrails']['override_count_total'].update(now=17)), 'TFF', 'samples_ge_100')):
            s = State.from_packs(load(*self.DESK))
            k = Kernel(s)
            measured = cut_facts(self._hook(edit))
            for row in measured:
                k.on_event(row, execute=True)
            r = k.run_standing(execute=True)['runs'][0]
            self.assertEqual((''.join(x['truth'][0] for x in measured), r['status'], rows(r, 'METHOD_ABSENT'), r['model_receipts']), (parts, 'METHOD_ABSENT', [{'predicate': 'hook_chain_' + named}], []))
        # A known limit, pinned: the kernel does not know who may hand in a measured part. A VERIFIED row from any source, over the adapter's FALSE row, opens the question to the founder.
        t = State.from_packs(load(*self.DESK))
        kt = Kernel(t)
        small = kt.on_event(self._row('samples_ge_100', lambda q: q['baseline'].update(samples=3)), execute=True)['runs'][0]
        self.assertEqual((small['status'], rows(small, 'METHOD_ABSENT'), open_asks(t)), ('METHOD_ABSENT', [{'predicate': 'hook_chain_samples_ge_100'}], {}))
        handed = kt.on_event({'predicate': 'hook_chain_samples_ge_100', 'truth': 'TRUE', 'verified': True, 'source': 'hand-written', 'version': 'none'}, execute=True)['runs'][0]
        self.assertEqual((handed['status'], handed['actions'], list(open_asks(t)), t.fact('hook_chain_samples_ge_100')['source'], t.budget['attention']),
                         ('WAITING', ['ask-hook-chain-cut-approval@1'], [HOOK_Q], 'hand-written', 2))

    def test_a_part_measured_again_with_the_same_verdict_leaves_a_landed_cut_alone(self):   # C10
        s = State.from_packs(load(*self.DESK))
        k = Kernel(s)
        answer(k, k.run_standing(execute=True)['runs'][0]['model_receipts'][0], 'TRUE', 'founder', execute=True)
        shipped, paid = s.fact('hook_chain_cut_shipped'), (dict(s.budget), dict(s.providers))
        self.assertEqual((shipped['truth'], paid), ('TRUE', ({'compute': 9, 'money': 10, 'attention': 1}, {'local-provider': 3, 'founder-channel': 1})))
        again = [('samples_ge_100', lambda q, n=n: q['baseline'].update(samples=n)) for n in (213, 214, 215, 216)]
        again += [('baseline_cited', lambda q: q['baseline'].update(value=300)), ('guardrails_hold', lambda q: q['guardrails']['override_count_total'].update(now=13))]
        for part, edit in again:   # other numbers, the same verdict: the cut is not shipped again, nothing is paid, nobody is asked
            r = k.on_event(self._row(part, edit), execute=True)['runs'][0]
            self.assertEqual((r['status'], r['actions'], r['model_receipts'], (dict(s.budget), dict(s.providers)), s.fact('hook_chain_cut_shipped'), open_asks(s)),
                             (HELD, [], [], paid, shipped, {BOOT_Q: open_asks(s)[BOOT_Q]}), part)
        self.assertEqual((s.fact('hook_chain_samples_ge_100')['measured']['samples'], s.fact('hook_chain_baseline_cited')['measured']['value']), (216, 300))   # the new numbers are kept
        broke = k.on_event(self._row('guardrails_hold', lambda q: q['guardrails']['override_count_total'].update(now=17)), execute=True)['runs'][0]
        self.assertEqual((broke['status'], s.fact('hook_chain_cut_shipped')['truth'], (dict(s.budget), dict(s.providers))), ('METHOD_ABSENT', 'UNKNOWN', paid))   # a verdict that changes is a new version
        self.assertEqual(s.evidence['sutra/speed|hook_chain_cut_shipped'], shipped)   # a known limit, pinned: a landed cut is not reverted when a guardrail breaks: its row stays on file as it was, and only stops being read
        holds = k.on_event(self._row('guardrails_hold', lambda q: q['guardrails']['override_count_total'].update(now=12)), execute=True)['runs'][0]
        self.assertEqual((holds['status'], holds['actions'], s.fact('hook_chain_cut_shipped'), (dict(s.budget), dict(s.providers))), (HELD, [], shipped, paid))   # it holds again: landed again, not shipped twice

    def test_data_before_cuts_rests_on_three_locks_and_each_one_holds_alone(self):
        p = pack('124_cut_desk')
        heads, by = {r['head']: r['branches'] for r in p['rules']}, {m['id']: m for m in p['methods']}
        for c, slug in (('hook_chain', 'hook-chain'), ('boot_load', 'boot-load')):
            parts = [c + '_baseline_cited', c + '_samples_ge_100', c + '_guardrails_hold']
            ship, ask = by[f'ship-{slug}-cut@1'], by[f'ask-{slug}-cut-approval@1']
            self.assertEqual((heads[c + '_cut_admissible'], heads[c + '_cut_landed']), ([parts], [[c + '_cut_admissible', c + '_cut_approved', c + '_cut_shipped']]))
            self.assertEqual((ship['requires'], ask['requires'], ask['action'], ask['ask_to'], ask['cost']['attention']), (parts + [c + '_cut_approved'], parts, 'ask', 'founder', 1))
        small = self._row('samples_ge_100', lambda q: q['baseline'].update(samples=42))

        def desk(rule=True, steps=True):   # the desk with one lock or both taken away
            d = copy.deepcopy(p)
            if not rule:
                for r in d['rules']:
                    r['branches'] = [[x for x in r['branches'][0] if not x.endswith('_cut_admissible')]]
            if not steps:
                for m in d['methods']:
                    m['requires'] = [x for x in m['requires'] if x.endswith('_cut_approved')]
            return State.from_packs([d])
        def look_with_a_small_sample(rule, steps):   # the small sample is handed in, then the hook chain cut is looked at
            s = desk(rule, steps)
            k = Kernel(s)
            k.on_event(small, execute=True)
            r = k.run_standing(execute=True)['runs'][0]
            return r['status'], [x['method'] for x in r['model_receipts']], HOOK_Q in open_asks(s)
        for rule, steps in ((True, True), (True, False), (False, True)):   # both locks, the rule alone, the steps' prerequisites alone: a cut without its sample is not asked about
            self.assertEqual(look_with_a_small_sample(rule, steps), ('METHOD_ABSENT', [], False), (rule, steps))
        self.assertEqual(look_with_a_small_sample(False, False), ('WAITING', ['ask-hook-chain-cut-approval@1'], True))   # with neither, the founder is asked about a cut whose sample is too small


class TierRules(unittest.TestCase):
    """R80: one rule set, the tier as an evidence row, each tier's grants in its own pack."""
    RULES = '125_fan_in_rules'
    TIER = {'internal': '126_tier_internal', 'portfolio': '127_tier_portfolio', 'project': '128_tier_project', 'external': '129_tier_external'}
    BATCH_2 = {'predicate': 'signals_sent', 'truth': 'FALSE', 'verified': True, 'source': 'fixture/new-batch', 'version': 'batch-2'}

    def _state(self, *tiers):
        return State.from_packs(load(self.RULES, *[self.TIER[t] for t in tiers]))

    def _row(self, **more):
        return dict({'predicate': 'tier_internal', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/not-the-registry', 'version': 'handed-in-1'}, **more)

    def test_one_rule_set_gives_each_tier_its_own_done_when_and_steps(self):   # C11
        want = {'internal': ('R-FAN-IN@1/OR1', DONE, ['send-internal@1']), 'portfolio': ('R-FAN-IN@1/OR2', DONE, ['show-notice@1', 'send-portfolio@1']),
                'project': (None, 'QUERY_EVIDENCE', []), 'external': (None, 'QUERY_EVIDENCE', [])}
        one = digest(self._state('internal').rules), digest(self._state('internal').methods)
        for name, (branch, status, actions) in want.items():
            s = self._state(name)
            self.assertEqual((digest(s.rules), digest(s.methods)), one, name)   # the same rule set under every tier
            r = looks(s)[0]
            self.assertEqual((r['status'], r['actions'], r['selected_branch']), (status, actions, branch), name)
            self.assertTrue(all('tier_' + name in s.methods[mid]['requires'] and s.methods[mid]['grant'] in s.grants for mid in actions), name)   # only its own steps, on its own grants
        s = self._state('project')   # the opt-in first, then the question about the batch in hand, then the send
        k = Kernel(s)
        before = held(s)
        r = k.run_standing(execute=True)['runs'][0]
        self.assertEqual((rows(r, 'QUERY_EVIDENCE'), r['model_receipts'], held(s), open_asks(s)), ([{'predicate': 'opted_in'}], [], before, {}))   # no opt-in on file: nobody is asked
        asked = k.on_event(OPT_IN, execute=True)['runs'][0]
        self.assertEqual((asked['status'], asked['actions'], asked['pending'], asked['selected_branch'], asked['model_receipts'][0]['ask']['to'], s.fact('signals_sent')['truth']),
                         ('WAITING', ['ask-batch-confirm@1'], ['send-project@1'], 'R-FAN-IN@1/OR3', 'client', 'FALSE'))
        with self.assertRaises(ValueError):   # only the client answers
            answer(k, asked['model_receipts'][0], 'TRUE', 'founder', execute=True)
        yes = answer(k, asked['model_receipts'][0], 'TRUE', 'client', execute=True)['runs'][0]
        self.assertEqual((yes['actions'], yes['selected_branch'], s.fact('signals_sent')['truth']), (['send-project@1'], 'R-FAN-IN@1/OR3', 'TRUE'))
        later = k.on_event(self.BATCH_2, execute=True)['runs'][0]   # a known limit, pinned: one State is one batch. The yes is a decision and stands, so a later batch goes out unasked
        self.assertEqual((later['status'], later['actions'], open_asks(s)), (DONE, ['send-project@1'], {}))
        s = self._state('project')   # the client's no is final: nothing is sent
        k = Kernel(s)
        no = answer(k, k.on_event(OPT_IN, execute=True)['runs'][0]['model_receipts'][0], 'FALSE', 'client', execute=True)['runs'][0]
        self.assertEqual((no['status'], no['model_receipts'], s.fact('signals_sent')['truth']), ('REFUSED', [], 'FALSE'))
        later = k.on_event(self.BATCH_2, execute=True)['runs'][0]   # the same limit: the no refuses every later batch
        self.assertEqual((later['status'], later['actions']), ('REFUSED', []))
        s = self._state('external')   # off by default: nothing leaves until an opt-in is on file
        k = Kernel(s)
        before = held(s)
        r = k.run_standing(execute=True)['runs'][0]
        self.assertEqual((r['status'], rows(r, 'QUERY_EVIDENCE'), r['model_receipts'], held(s)), ('QUERY_EVIDENCE', [{'predicate': 'opted_in'}], [], before))
        self.assertEqual((k.on_event(dict(OPT_IN, verified=False), execute=True)['status'], held(s)), ('UNVERIFIED_EVENT_IGNORED', before))   # an opt-in nobody verified opens nothing
        opted = k.on_event(OPT_IN, execute=True)['runs'][0]
        self.assertEqual((opted['actions'], opted['selected_branch'], s.fact('signals_sent')['truth']), (['send-external@1'], 'R-FAN-IN@1/OR4', 'TRUE'))

    def test_tier_packs_hold_only_their_own_rows_and_grants(self):   # C12
        rules, packs = pack(self.RULES), [pack(n) for n in self.TIER.values()]
        shape = check_module()['_shape_tiers']   # the independent check's own reading of the same five packs
        files = lambda r, ps: dict({p['id']: p for p in ps}, **{r['id']: r})
        self.assertEqual((tier_faults(rules, packs, 'fan_in_done'), shape(files(rules, packs))), ([], []))
        self.assertEqual([p['providers'] for p in packs], [{'local-provider': 3}, {'local-provider': 3}, {'local-provider': 3, 'client-channel': 1}, {'local-provider': 3}])   # each tier pack's slots, to the number
        self.assertEqual([m['id'] for m in rules['methods'] if m['effect'] == 'opted_in'], [])   # a known limit, pinned: both opt-ins are rows that are handed in; no step asks for one or makes one
        self.assertEqual(rules['rules'][0]['branches'], [['tier_internal', 'signals_sent'], ['tier_portfolio', 'notice_shown', 'signals_sent'],   # each condition of a tier sits in its alternative
                                                         ['tier_project', 'opted_in', 'batch_confirmed', 'signals_sent'], ['tier_external', 'opted_in', 'signals_sent']])
        self.assertEqual({m['id']: (m['requires'], m['grant']) for m in rules['methods']},                                                     # and in the prerequisites of its steps
                         {'send-internal@1': (['tier_internal'], 'fan-in:internal'), 'send-portfolio@1': (['tier_portfolio', 'notice_shown'], 'fan-in:portfolio'),
                          'send-project@1': (['tier_project', 'opted_in', 'batch_confirmed'], 'fan-in:project'), 'send-external@1': (['tier_external', 'opted_in'], 'fan-in:external'),
                          'show-notice@1': (['tier_portfolio'], 'notice:portfolio'), 'ask-batch-confirm@1': (['tier_project', 'opted_in'], 'ask:client')})
        by = lambda r, mid: [m for m in r['methods'] if m['id'] == mid][0]
        row = lambda p, t='TRUE', **kw: dict({'predicate': p, 'truth': t, 'verified': True, 'source': 'fixture/test', 'version': '1'}, **kw)
        own_step = lambda r: dict(by(r, 'show-notice@1'), id='confirm-self@1', effect='batch_confirmed', requires=['tier_project'], grant='fan-in:project', cost=ZERO)
        own_rule = lambda r: dict(r['rules'][0], id='R-FAN-IN@2', replaces='R-FAN-IN@1', branches=[['tier_external', 'signals_sent']])
        broken = [(lambda r, ps: ps[2]['grants'].append('fan-in:internal'), 'is held by'),                                    # the project pack is handed the internal grant
                  (lambda r, ps: by(r, 'send-internal@1')['requires'].remove('tier_internal'), 'requires 0 tier rows'),      # a step that no tier row guards
                  (lambda r, ps: by(r, 'send-project@1')['requires'].append('tier_internal'), 'requires 2 tier rows'),
                  (lambda r, ps: by(r, 'send-internal@1').pop('grant'), 'is held by'),                                       # a step with no grant at all
                  (lambda r, ps: [e.update(truth='TRUE') for e in ps[2]['evidence'] if e['predicate'] == 'tier_internal'], 'exactly one TRUE'),   # a pack that is two tiers at once
                  (lambda r, ps: ps[3]['evidence'].pop(0), 'does not set every tier row'),
                  (lambda r, ps: [e.update(verified=False) for e in ps[1]['evidence'] if e['predicate'] == 'tier_internal'], 'does not set every tier row'),
                  (lambda r, ps: r['methods'].append(dict(by(r, 'show-notice@1'), id='become-internal@1', effect='tier_internal')), 'never made'),
                  (lambda r, ps: ps[1].update(scope=ps[0]['scope']), 'every tier pack names a scope'),
                  (lambda r, ps: ps[1].pop('scope'), 'every tier pack names a scope'),                                                 # a tier pack that names no scope at all
                  (lambda r, ps: ps[0]['grants'].append('notice:other'), 'which no step of its tier needs'),
                  (lambda r, ps: r['rules'][0]['branches'].append(['tier_internal', 'signals_sent']), 'open with the same tier row'),
                  # the closed list: what a rule set holds reaches every tier
                  (lambda r, ps: r.update(grants=['fan-in:internal']), "carries ['grants']"),
                  (lambda r, ps: r.update(scope='everyone/fan-in'), "carries ['scope']"),
                  (lambda r, ps: r.update(evidence=[row('tier_internal')]), "carries ['evidence']"),
                  (lambda r, ps: r.update(providers={'client-channel': 9}), "carries ['providers']"),
                  (lambda r, ps: r['rules'].append(dict(r['rules'][0], id='R-CONFIRMED@1', head='batch_confirmed', branches=[['tier_project']])), 'holds one approved rule'),
                  (lambda r, ps: r['rules'][0].update(approved=False), 'holds one approved rule'),
                  (lambda r, ps: r.update(goals=['fan_in_done', 'signals_sent']), 'as its one goal'),
                  # and a tier pack brings no step, no rule and no fact of its own
                  (lambda r, ps: ps[2].update(methods=[own_step(r)]), "carries ['methods']"),
                  (lambda r, ps: ps[3].update(rules=[own_rule(r)]), "carries ['rules']"),
                  (lambda r, ps: ps[2].update(budget={'attention': 9}), "carries ['budget']"),
                  (lambda r, ps: ps[2].update(goals=['signals_sent']), "carries ['goals']"),
                  (lambda r, ps: ps[2]['evidence'].append(row('batch_confirmed')), 'says only what has not happened yet'),
                  (lambda r, ps: ps[3]['evidence'].append(row('opted_in')), 'says only what has not happened yet'),
                  (lambda r, ps: ps[0]['evidence'][1].update(scope='project/fan-in'), 'gives a row a scope'),
                  (lambda r, ps: ps[1]['evidence'].append(row('signals_sent', 'FALSE')), 'states a fact twice'),
                  (lambda r, ps: ps[1]['evidence'].append(row('batch_confirmed', 'FALSE', verified=False)), 'says only what has not happened yet')]
        for change, word in broken:
            r, ps = copy.deepcopy(rules), copy.deepcopy(packs)
            change(r, ps)
            faults = tier_faults(r, ps, 'fan_in_done')
            self.assertTrue(any(word in line for line in faults), (word, faults))
            self.assertTrue(shape(files(r, ps)), word)   # the extension and the independent check refuse the same sets
        for change, word in ((lambda r, ps: ps.pop(3), 'no pack is the pack of tier_external'),
                             (lambda r, ps: ps.append(dict(ps[0], id='126_again', scope='another/fan-in')), 'are both the pack of tier_internal')):
            r, ps = copy.deepcopy(rules), copy.deepcopy(packs)
            change(r, ps)
            self.assertTrue(any(word in line for line in tier_faults(r, ps, 'fan_in_done')), word)
        self.assertEqual(tier_faults({'id': 'x', 'rules': []}, packs, 'fan_in_done'), ['x holds one approved rule, the rule for fan_in_done, and no other'])
        # What the closed list is for. Each of these sets passes the kernel's own checks, and each opens a way its tier does not have.
        leaky = dict(copy.deepcopy(rules), grants=['fan-in:internal'])   # the rule set hands out the internal grant
        s = State.from_packs([leaky, pack(self.TIER['project'])])
        k = Kernel(s)
        k.run_standing(execute=True)
        self.assertEqual(k.on_event(self._row(), execute=True)['runs'][0]['actions'], ['send-internal@1'])   # one handed-in row then opens the internal way
        confirming = dict(copy.deepcopy(pack(self.TIER['project'])), methods=[own_step(rules)])           # the project pack confirms for the client
        s = State.from_packs([rules, confirming])
        r = Kernel(s).on_event(OPT_IN, execute=True)['runs'][0]
        self.assertEqual((r['actions'], open_asks(s)), (['confirm-self@1', 'send-project@1'], {}))            # nobody is asked
        ruling = dict(copy.deepcopy(pack(self.TIER['external'])), rules=[own_rule(rules)], methods=[dict(by(rules, 'send-external@1'), id='send-anyway@1', requires=['tier_external'])])
        s = State.from_packs([rules, ruling])                                                               # the external pack rewrites its own done-when
        self.assertEqual((looks(s)[0]['actions'], s.fact('opted_in')['truth']), (['send-anyway@1'], 'UNKNOWN'))   # it sends with no opt-in on file
        # The pack file refuses to author a faulty set: it raises before any of the five tier packs is written.
        source = (ROOT / 'tools' / 'packs' / 'ordered.py').read_text()
        for old, new in (("['fan-in:project', 'ask:client']", "['fan-in:project', 'ask:client', 'fan-in:internal']"),
                         ("FAN_IN = {'goals': ['fan_in_done'],", "FAN_IN = {'goals': ['fan_in_done'], 'grants': ['fan-in:internal'],")):
            faulty = source.replace(old, new)
            self.assertNotEqual(faulty, source)
            written = []
            with self.assertRaises(ValueError):
                exec(compile(faulty, 'ordered.py', 'exec'), {'pack': lambda name, **fields: written.append(name), 'fact': fact, 'rule': rule, 'method': method})
            self.assertEqual(written, ['120_feedback', '121_scrub_simulated', '122_scrub_by_code', '123_team_rail', '124_cut_desk'])
        # The two closed lists, to the letter, and held against every key the kernel reads in a pack (and one it does not read): whatever is not on a list is a fault,
        # named by its key, and the independent check refuses the same sets.
        holds_rules, holds_tier = {'schema', 'id', 'goals', 'rules', 'methods'}, {'schema', 'id', 'scope', 'evidence', 'grants', 'providers'}
        self.assertEqual((RULE_SET_HOLDS, TIER_PACK_HOLDS), (holds_rules, holds_tier))
        reads = {'goals': ['fan_in_done'], 'grants': [], 'revoke_grants': [], 'scope': 'somewhere/else', 'evidence': [], 'rules': [], 'methods': [], 'constructors': [], 'providers': {},
                 'budget': {}, 'preference': ['compute', 'money', 'attention'], 'a_key_of_a_later_kernel': 1}
        for key, value in reads.items():
            if key not in holds_rules:
                r, ps = dict(copy.deepcopy(rules), **{key: value}), copy.deepcopy(packs)
                self.assertEqual(([line.split(':')[0] for line in tier_faults(r, ps, 'fan_in_done')], bool(shape(files(r, ps)))), (["125_fan_in_rules carries ['%s']" % key], True), key)
            if key not in holds_tier:
                r, ps = copy.deepcopy(rules), copy.deepcopy(packs)
                ps[2][key] = value
                self.assertEqual(([line.split(':')[0] for line in tier_faults(r, ps, 'fan_in_done')], bool(shape(files(r, ps)))), (["128_tier_project carries ['%s']" % key], True), key)
        # A known limit, pinned: tier_faults judges the five packs it is given, not a sixth pack loaded with them. A sixth pack that hands out the internal grant leaves
        # the five without a fault, and a project State that holds it and is then handed an internal tier row runs the internal send.
        sixth = {'schema': 'sutra-extension/2', 'id': 'a_sixth_pack', 'grants': ['fan-in:internal']}
        s = State.from_packs([rules, pack(self.TIER['project']), sixth])
        k = Kernel(s)
        first = k.run_standing(execute=True)['runs'][0]
        handed = k.on_event(self._row(), execute=True)['runs'][0]
        self.assertEqual((tier_faults(rules, packs, 'fan_in_done'), first['status'], first['actions'], handed['status'], handed['actions'], s.fact('signals_sent')['source']),
                         ([], 'QUERY_EVIDENCE', [], DONE, ['send-internal@1'], 'LOCAL_MODEL:send-internal@1'))

    def test_one_lock_alone_opens_nothing(self):   # C13
        shape = lambda r: (r['status'], r['actions'], r.get('pending'), r.get('waits'), [x['method'] for x in r['model_receipts']], r['cost'])
        internal = lambda r: [a for a in rows(r, 'ADMISSION') if 'send-internal@1' in a['methods']]

        def way(k):   # a project State's whole way from the opt-in on: the question to the client, then the send on the yes
            out = [k.on_event(OPT_IN, execute=True)['runs'][0]]
            return out + [answer(k, out[0]['model_receipts'][0], 'TRUE', 'client', execute=True)['runs'][0]]
        k = Kernel(self._state('project'))
        plain = [k.run_standing(execute=True)['runs'][0]] + way(k)
        self.assertEqual([(r['status'], r['actions']) for r in plain], [('QUERY_EVIDENCE', []), ('WAITING', ['ask-batch-confirm@1']), (DONE, ['send-project@1'])])
        s = self._state('internal', 'project')   # it was an internal install and is a project now: the internal grant is still held
        self.assertEqual((s.scope, 'fan-in:internal' in s.grants, s.fact('tier_internal')['truth']), ('project/fan-in', True, 'FALSE'))
        k = Kernel(s)
        old = [k.run_standing(execute=True)['runs'][0]] + way(k)
        self.assertEqual(([shape(r) for r in old], [r['selected_branch'] for r in old], [internal(r) for r in old]),
                         ([shape(r) for r in plain], [r['selected_branch'] for r in plain], [[], [], []]))   # the internal send was never a candidate
        s = self._state('project')
        k = Kernel(s)
        before = held(s)
        self.assertEqual((k.on_event(self._row(verified=False), execute=True)['status'], held(s)), ('UNVERIFIED_EVENT_IGNORED', before))   # an unverified row changes nothing
        elsewhere = k.on_event(self._row(scope='internal/fan-in'), execute=True)   # the registry's row of another tenant: stored under its own scope and not read here
        rest = {key: v for key, v in s.evidence.items() if key != 'internal/fan-in|tier_internal'}
        self.assertEqual((elsewhere['status'], elsewhere['runs'], s.evidence['internal/fan-in|tier_internal']['truth'], s.fact('tier_internal')['truth'], digest(rest), held(s)[1:]),
                         ('OUT_OF_SCOPE', [], 'TRUE', 'FALSE', before[0], before[1:]))   # every other row and all the books are as they were
        got = k.on_event(self._row(), execute=True)['runs'][0]   # a verified internal row in its own scope, and no internal grant
        self.assertEqual((s.fact('tier_internal')['truth'], shape(got), rows(got, 'QUERY_EVIDENCE')[0], s.fact('signals_sent')['truth'], held(s)[1:]),
                         ('TRUE', shape(plain[0]), {'predicate': 'opted_in'}, 'FALSE', before[1:]))
        after = way(k)
        self.assertEqual(([shape(r) for r in after], s.fact('signals_sent')['source']), ([shape(r) for r in plain[1:]], 'LOCAL_MODEL:send-project@1'))   # the same steps, receipts and costs as a plain project State
        for r in [got] + after:   # the internal send is a candidate now, and is refused for authority every time
            self.assertTrue(internal(r) and all(a['accepted'] is False and a['blockers'] == ['AUTHORITY_REQUIRED'] for a in internal(r)))
        self.assertEqual([r['selected_branch'] for r in after], ['R-FAN-IN@1/OR1'] * 2)   # a known limit, pinned: the run names the first alternative that can be met, here the foreign one
        both = self._state('internal', 'project')   # a known limit, pinned: with the row AND the grant the State acts as the other tier
        self.assertEqual(Kernel(both).on_event(self._row(), execute=True)['runs'][0]['actions'], ['send-internal@1'])


class OrderedRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'results' / 'actual_run_records.json').read_text())
        cls.v, cls.check = verifier(), check_module()
        cls.files = {n: json.loads((ROOT / 'scenarios' / (n + '.json')).read_text()) for n in cls.check['PACKS']}
        cls.case_files = {cid: json.loads((ROOT / 'cases' / (cid + '.json')).read_text()) for cid in cls.check['CASES']}
        cls.handler = hashlib.sha256((ROOT / 'kinds' / 'scrub_text.py').read_bytes()).hexdigest()

    def test_the_record_holds_the_cases_and_the_sequence_and_the_checks_fail_on_forgeries(self):
        data = self.data
        self.assertTrue({'54_ordered_effects', '55_data_before_cuts', '56_tier_rules'} <= {c['id'] for c in MORE})
        self.assertEqual(json.loads(json.dumps(scenes()['ordered'])), data['scenes']['ordered'])   # made again here: the same runs, the same trace roots
        # The scrub's kind is a declared kind: the record lists its handler by file and sha256, and lists the sanitizer's file among the added files.
        self.assertEqual(data['action_handlers']['scrub_text'], {'module': 'kinds.scrub_text', 'file': 'kinds/scrub_text.py', 'sha256': self.handler})
        self.assertEqual((data['added']['files']['kinds/scrub_text.py'], data['added']['files']['extensions/ordered_effects.py']),
                         (self.handler, hashlib.sha256((ROOT / 'extensions' / 'ordered_effects.py').read_bytes()).hexdigest()))
        by_code = [x for r in self.v.runs_under(data['scenes']['ordered']) for x in r['model_receipts'] if x['action'] == 'scrub_text']
        self.assertEqual((len(by_code), {x['method'] for x in by_code}, [x for c in data['cases'] for r in self.v.runs_under(c) for x in r['model_receipts'] if x['action'] == 'scrub_text']),
                         (3, {CODE}, []))   # three steps of the sequence ran under it; no case does (case 54 simulates the scrub)
        result = {t['id']: t for t in self.v.inspect(data)['checks']}
        self.assertEqual([result[i]['pass'] for i in ('S41_action_handlers_recorded_by_sha', 'S204_every_receipt_names_an_action_kind_the_record_holds_a_handler_for')], [True, True])
        mine = sorted(i for i in result if 'S70' <= i[:3] <= 'S79')
        self.assertEqual((len(mine), [i for i in mine if not result[i]['pass']], mine[:9]), (10, [], list(self.check['CLAIMS'])))
        failing = lambda d: [cid[:3] for cid, ok, _ in self.check['checks'](d, ROOT, self.v.sha, self.v.check_chain) if not ok]
        step = lambda d, part, life, name: d['scenes']['ordered'][part][life]['steps'][name]
        case = lambda d, cid: [c for c in d['cases'] if c['id'].startswith(cid)][0]
        forged = [   # forged records, one field each; the first eleven are the ones the two refuters passed through the earlier checks
            (lambda d: step(d, 'tiers', 'project', 'confirmed')['result']['event'].update(truth='FALSE'), 'S76'),      # the client said no and the batch was sent
            (lambda d: step(d, 'tiers', 'external', 'opted_in')['result']['event'].update(verified=False), 'S76'),    # an unverified opt-in opened the send
            (lambda d: step(d, 'cuts', 'own_question', 'no_boot_load')['result']['event'].update(final=1), 'S74'),    # 1 for true
            (lambda d: step(d, 'cuts', 'yes_without_data', 'yes_hook_chain')['result']['event'].update(source='STAMP:operations'), 'S75'),
            (lambda d: step(d, 'tiers', 'foreign_row', 'row_in_scope')['result']['event'].update(truth='FALSE'), 'S78'),
            (lambda d: step(d, 'effects', 'fail_closed', 'sent')['after']['reads'].update(feedback_sent='FALSE'), 'S72'),
            (lambda d: step(d, 'effects', 'no_scrub_step', 'look')['after']['providers'].update({'team-rail': 1}), 'S71'),
            (lambda d: step(d, 'tiers', 'external', 'look')['after'].update(grants=['fan-in:internal']), 'S76'),
            (lambda d: case(d, '54')['derived_state']['facts']['sutra/feedback|feedback_sent'].update(truth='FALSE'), 'S70'),
            (lambda d: case(d, '55')['derived_state']['budget_after'].update(attention=3), 'S74'),
            (lambda d: case(d, '55')['run']['runs'][1].update(learning=[{'kind': 'REUSE_COMPOSITION', 'status': 'PROMOTED'}]), 'S74'),
            (lambda d: step(d, 'effects', 'rail_down', 'captured')['after']['reads'].update(written_locally='FALSE'), 'S72'),
            (lambda d: step(d, 'cuts', 'own_question', 'measured_again')['result']['runs'][0].update(status=DONE, actions=['ship-hook-chain-cut@1']), 'S75'),
            (lambda d: step(d, 'effects', 'fail_closed', 'refused')['result']['runs'][0]['stopped'].update(reason='Handler failed: RuntimeError'), 'S71'),   # a fault of the handler in place of its refusal
            (lambda d: step(d, 'effects', 'fail_closed', 'sent')['result']['runs'][0]['model_receipts'][0].update(action='simulate_fact'), 'S72'),         # the step of the code under the simulated kind
            (lambda d: d['action_handlers']['scrub_text'].update(sha256='0' * 64), 'S72'),                                                                  # the scrub's handler: another file's hash,
            (lambda d: d['action_handlers']['scrub_text'].update(file='extensions/ordered_effects.py'), 'S72'),                                             # another file,
            (lambda d: d['action_handlers'].pop('scrub_text'), 'S72'),                                                                                      # or not in the record's list at all
            (lambda d: d['scenes'].pop('ordered'), 'S79')]
        for i, (change, expect) in enumerate(forged):
            d = json.loads(json.dumps(data))
            change(d)
            self.assertIn(expect, failing(d), i)
        self.assertEqual(failing(data), [])

    def test_every_recorded_leaf_of_this_version_is_read_by_a_check(self):
        mine = {'cases': [c for c in self.data['cases'] if c['id'] in self.check['CASES']], 'scenes': {'ordered': self.data['scenes']['ordered']}, 'action_handlers': self.data['action_handlers']}
        kept = json.dumps(mine)
        # Every leaf of cases 54 to 56 and of every life, in place, one at a time: changed, written as another JSON type, and taken out; and one more key put on every object.
        made, passed = self.check['sweep'](mine, self.files, self.case_files, self.handler, None, 1, keys=True)
        self.assertEqual((made > 15000, passed), (True, []))
        made, passed = self.check['sweep'](mine, self.files, self.case_files, self.handler, self.v.check_chain, 23, True)   # and one leaf in 23 with the rows of every trace among them
        self.assertEqual((made > 500, passed), (True, []))
        made, passed = self.check['sweep'](mine, self.files, self.case_files, self.handler, None, 23, True)   # the same without the chain: what a line of a trace says is still read,
        self.assertEqual((made > 500, {p[2] for p in passed} <= {'seq', 'prev_sha256', 'sha256'}, json.dumps(mine)), (True, True, kept))   # only the chain's own fields pass; the record is as it was

    def test_the_scene_file_states_the_looks_and_runs_the_record_holds(self):
        """The scene file states, once each at its top level, how many looks and runs the sequence records (`LOOKS`, `RUNS`), and its own words give them part by part.
        Counted here by shape in the record (a look: an object that holds a list under `runs`; a run: an object with `trace` and `trace_root_sha256`)."""
        def count(o):
            inside = [count(x) for x in (o.values() if isinstance(o, dict) else o)] if isinstance(o, (dict, list)) else []
            return (sum(n for n, _ in inside) + (isinstance(o, dict) and type(o.get('runs')) is list), sum(n for _, n in inside) + (isinstance(o, dict) and 'trace' in o and 'trace_root_sha256' in o))
        stated, sequence = (ROOT / 'tools' / 'scenes' / 'ordered.py').read_text(), self.data['scenes']['ordered']
        self.assertEqual(([re.findall(r'^%s = (\d+)$' % name, stated, re.M) for name in ('LOOKS', 'RUNS')], count(sequence), {part: count(lives) for part, lives in sequence.items()}),
                         ([['40'], ['48']], (40, 48), {'effects': (10, 18), 'cuts': (13, 15), 'tiers': (17, 15)}))
        for words_of_the_file in ('effects  10 looks, 18 runs', 'cuts     13 looks, 15 runs', 'tiers    17 looks, 15 runs'):
            self.assertIn(words_of_the_file, stated)

    def test_known_limit_what_of_a_trace_rests_on_the_chain_alone(self):
        """A known limit, pinned as it is today (the passage states it; reading every row of a trace whole is owed to the next version).
        The checks read a trace line by line for what each line must say, not row by row for all it says. A forger who rewrites a trace in the places of the first
        half, chains it again and seals the sequence again (a seal holds no secret) passes every check of the base and of this version (where another version is laid beside it, a check of that version may refuse it: numbers' S105 and S109 do). No status, step, receipt, snapshot or stored
        row can be forged this way: those are rebuilt from the pack files and the script. The second half: the same kind of change where the checks do read."""
        sha, chain, at = self.v.sha, self.v.check_chain, self.check['_at']
        of = lambda r, kind: [e for e in r['trace'] if e['operation'] == kind]

        def rechain(r):   # what a forger does after rewriting a trace: chain it again and name the run by its new root
            prev = 'GENESIS'
            for i, row in enumerate(r['trace']):
                row.update(seq=i + 1, prev_sha256=prev)
                row['sha256'] = prev = sha({k: v for k, v in row.items() if k != 'sha256'})
            r['trace_root_sha256'] = prev

        def effects_first(r):   # every effect line put before every gate line that follows the chosen plan
            cut = r['trace'].index(of(r, 'SELECT')[0])
            r['trace'][:] = r['trace'][:cut + 1] + of(r, 'LOCAL_EFFECT') + [e for e in r['trace'][cut + 1:] if e['operation'] == 'ADMISSION'] + r['trace'][-1:]
        d = json.loads(json.dumps(self.data))
        run = lambda key, step, i=0: at(d['scenes']['ordered'], key)['steps'][step]['result']['runs'][i]
        a = run('tiers.internal', 'look')                                                # one look of the internal tier:
        of(a, 'SELECT')[0]['data'].update(approved_by='founder', pareto_options=9)       # the line of the chosen plan says who approved it and counts nine options,
        a['pareto_options'] = 9                                                          # and the run's own count is forged with it (the checks hold the one to the other and plan nothing)
        of(a, 'LOCAL_EFFECT')[0]['data']['external_effect'] = 'sent for real'            # the line of an effect says more than its receipt
        a['trace'][3]['note'] = 'approved by phone'                                      # a row carries one more key
        a['trace'].insert(1, {'operation': 'TERMINAL', 'data': {'status': 'REFUSED', 'work_state': 'blocked'}})                  # a second closing line, before the search,
        a['trace'].insert(2, {'operation': 'GOAL_ACCEPTED', 'data': {'goal': 'feedback_sent_to_everyone', 'scope': 'world'}})     # and a second goal, of another scope
        b = run('effects.fail_closed', 'sent')                                           # the capture of a message: both effect lines before both gate lines
        effects_first(b)
        c = run('effects.fail_closed', 'second')                                         # the search of another run: a line taken out, a line doubled, two lines changing places
        del c['trace'][4]
        c['trace'].insert(2, json.loads(json.dumps(c['trace'][2])))
        c['trace'][1], c['trace'][2] = c['trace'][2], c['trace'][1]
        case = [x for x in d['cases'] if x['id'] == '54_ordered_effects'][0]              # and a recorded case, whose new root is then written wherever the case names it
        e = case['run']['runs'][0]
        of(e, 'SELECT')[0]['data'].update(note='approved by phone', pareto_options=9)
        e['pareto_options'] = 9
        of(e, 'LOCAL_EFFECT')[1]['data']['external'] = True
        effects_first(e)
        for r in (a, b, c, e):
            rechain(r)
        e['learning_record']['source_trace'] = case['derived_state']['historical_events'][0]['trace_root_sha256'] = e['trace_root_sha256']
        case['outcome'], case['four_views']['run'] = json.loads(json.dumps(e)), json.loads(json.dumps(e['trace']))
        d['added']['scenes']['ordered'] = sha(d['scenes']['ordered'])                    # the sequence sealed again
        kinds = lambda r: [x['operation'] for x in r['trace']]
        self.assertEqual((kinds(a)[:3], kinds(b)[6:11], kinds(c)[:6], kinds(e)[6:11]),
                         (['GOAL_ACCEPTED', 'TERMINAL', 'GOAL_ACCEPTED'], ['SELECT', 'LOCAL_EFFECT', 'LOCAL_EFFECT', 'ADMISSION', 'ADMISSION'],
                          ['GOAL_ACCEPTED', 'METHOD_MATCH', 'METHOD_MATCH', 'METHOD_MATCH', 'RETAIN', 'ADMISSION'], ['SELECT', 'LOCAL_EFFECT', 'LOCAL_EFFECT', 'ADMISSION', 'ADMISSION']))
        verdict = self.v.inspect(d)
        self.assertEqual(([t['id'] for t in verdict['checks'] if not t['pass'] and ours(t['id'], 70, 79)], d != self.data), ([], True))   # no check of the base or of this version refuses the forged record (a check another version brings may)

        # The second half: where the checks do read, one such change is refused though the trace is chained again. Judged the way S79 judges a rechained forgery:
        # the life against its script, with the chain; the chain holds, so it is what a line says that gives it away.
        def refused(key, step, change, i=0):
            life = json.loads(json.dumps(at(self.data['scenes']['ordered'], key)))
            r = life['steps'][step]['result']['runs'][i]
            change(r)
            rechain(r)
            wrong = self.check['_life'](life, self.files, self.check['LIVES'][key], chain)
            return bool(wrong) and not any(what.endswith('trace chain') for _, what in wrong)
        look = ('tiers.internal', 'look')
        read = [look + (lambda r: r.update(pareto_options=9),),                                                                    # the run's count without its line,
                look + (lambda r: of(r, 'SELECT')[0]['data'].update(pareto_options=9),),                                            # the line's count without the run's
                look + (lambda r: of(r, 'SELECT')[0]['data'].update(actions=['send-external@1']),),                                 # another plan on the line of the chosen plan,
                look + (lambda r: of(r, 'SELECT')[0]['data'].update(full_cost={'compute': 0, 'money': 0, 'attention': 0}),),        # or another cost
                look + (lambda r: of(r, 'LOCAL_EFFECT')[0]['data']['receipt'].update(status='EXTERNAL'),),                          # another receipt on the line of an effect
                look + (lambda r: r['trace'].insert(1, {'operation': 'BLOCK', 'data': {'reason': 'REFUSED', 'all_reasons': ['REFUSED']}}),),   # a line that blocks a run that ran
                look + (lambda r: r['trace'].insert(1, {'operation': 'NOTE', 'data': {'text': 'approved by phone'}}),),             # a kind of line no search has
                look + (lambda r: r['trace'].insert(len(r['trace']) - 1, {'operation': 'GOAL_ACCEPTED', 'data': {'goal': 'fan_in_done', 'scope': 'internal/fan-in'}}),),   # a goal accepted after the plan was chosen
                look + (lambda r: [r['trace'].remove(e) for e in of(r, 'METHOD_ABSENT')],),                                         # the lines that name the other tiers' rows, all taken out
                look + (lambda r: r['trace'].remove(of(r, 'ADMISSION')[-1]),),                                                      # the gate line of the step that ran
                look + (lambda r: r['trace'].append(r['trace'].pop(0)),),                                                           # the first line put last
                look + (lambda r: of(r, 'RETAIN')[0]['data'].update(note='seen by phone'),),                                        # one more key on a line of the search that is read whole,
                ('effects.fail_closed', 'refused', lambda r: of(r, 'STEP_STOPPED')[0]['data'].update(note='tried twice')),          # on the line of a stop,
                ('tiers.project', 'confirmed', lambda r: of(r, 'ASK_CLOSED')[0]['data'].update(note='by phone')),                   # on the line that closes a question,
                ('effects.rail_down', 'captured', lambda r: of(r, 'BLOCK')[0]['data'].update(note='for now'), 1),                   # or on the line that blocks a run
                ('tiers.foreign_row', 'opted_in', lambda r: r['trace'].remove(of(r, 'ADMISSION')[0]))]                              # a gate line taken out of a search whose gate lines the script lists
        self.assertEqual([refused(*x) for x in read], [True] * len(read))
        # One more of the first half, alone: the refused gate line of the send, taken out of the search of the run that had no rail. Checks S70 to S78 pass. S79 fails for a reason
        # of its own: one of its hand-made forgeries rewrites that very line, and a forgery that cannot be made on the record it is handed is counted as not caught.
        d = json.loads(json.dumps(self.data))
        r = run('effects.rail_down', 'captured', 1)
        r['trace'].remove(of(r, 'ADMISSION')[0])
        rechain(r)
        d['added']['scenes']['ordered'] = sha(d['scenes']['ordered'])
        got = {cid[:3]: (ok, detail) for cid, ok, detail in self.check['checks'](d, ROOT, sha, chain)}
        self.assertEqual(([cid for cid in got if not got[cid][0]], got['S79'][1].split('; ')[1]), (['S79'], "not caught: [('handmade', 265, 'rechained', 'effects.rail_down')]"))


if __name__ == '__main__':
    unittest.main()
