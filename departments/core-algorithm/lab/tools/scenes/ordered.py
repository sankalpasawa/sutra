"""Recorded sequences of 0.16.0-ordered (matrix rows R73, R82, R80): what one look cannot show.
scene(lab) -> the dict kept in the record under scenes.ordered. Every pack loaded here is a scenario file, and every
State is built by the kernel's own State.from_packs: the scrub by code is the declared kind `scrub_text`
(kinds/scrub_text.py), which every State knows.

The record is a set of lives. A life is one State built from its packs and taken through named steps, and it is kept
in one shape: `packs`, the snapshot at the `start`, and for each step what was done (`does`), what the kernel returned
(`result`) and the snapshot `after` it. A step is one of five things:

  look      the standing goals are looked at and run (`does`: {"look": "executed"})
  event     a row is handed in (`does`: {"event": the row}); `result` is the kernel's answer, also when it ignores the row
  measured  a cut proposal is measured again and the adapter's row for one part is handed in (`does`: the proposal and the row)
  answer    the stamp on the question that a named step's run asked (`does`: {"answer": {step, run, truth, by}})
  apply     one more scenario pack is applied to the living State (`does`: {"apply": the pack}; no `result`)

A snapshot is what the State held at that point: its scope, budget, provider slots, grants, the questions still out,
the journal's statuses, what each named fact reads and the row stored for it. The independent checks rebuild every
snapshot from the pack files and the receipts before it and compare it whole.

  effects  R73. `no_scrub_step`: pack 120 and the rail, no scrub: nothing is offered. `fail_closed`: the scrub done by
           code (pack 122): words the sanitizer cannot make safe stop both goals at the scrub; an unverified marker is
           ignored; a second look stops the same way; words it can make safe are scrubbed and written, then sent; one
           more look does nothing; a second message that scrubs to the same clean text is scrubbed, written and sent
           again. `rail_down`: no rail pack: the words are scrubbed and written and the send is blocked; a second
           look pays nothing; the rail pack is applied and the next look sends, alone.
  cuts     R82. `missing`: four lives, each a cut with one measured part false. `own_question`: two cuts, each with its
           own question: a yes ships one, a no refuses the other; the sample measured again (and still enough) leaves
           the landed cut alone; a guardrail that breaks blocks the standing goal, and holds again. `yes_without_data`:
           a yes that arrives after the sample shrank ships nothing.
  tiers    R80. The same rule set under each of the four tier packs (`project_refused`: the client's no);
           `old_grant`: a project State that still holds the internal grant; `foreign_row`: a project State handed
           an internal tier row (unverified, from another scope, then verified in its own scope).

How many looks and runs the sequence records. A look is every `result` that is not empty: what the kernel returned
for one look at the standing goals, for one row handed in (also a row it ignored: such a look holds no run) or for
one stamp. An `apply` step has no result and is no look. A run is one goal resolved inside a look.
  effects  10 looks, 18 runs   (no_scrub_step 1 and 2; fail_closed 6 and 10; rail_down 3 and 6)
  cuts     13 looks, 15 runs   (the four lives of missing 1 and 1 each; own_question 6 and 7; yes_without_data 3 and 4)
  tiers    17 looks, 15 runs   (internal 1 and 1; portfolio 1 and 1; project 3 and 3; project_refused 2 and 2;
                                external 2 and 2; old_grant 3 and 3; foreign_row 5 and 3)"""
import copy

LOOKS = 40
RUNS = 48


def scene(lab):
    State, Kernel, pack, answer, open_asks = (lab[x] for x in ('State', 'Kernel', 'pack', 'answer', 'open_asks'))
    from extensions.ordered_cuts import cut_facts

    def snap(s, facts):
        return {'scope': s.scope, 'budget': dict(s.budget), 'providers': dict(s.providers), 'grants': sorted(s.grants), 'open_asks': open_asks(s),
                'journal': [j['status'] for j in s.event_journal], 'reads': {p: s.fact(p)['truth'] for p in facts},
                'rows': {p: copy.deepcopy(s.evidence.get(s.scope + '|' + p)) for p in facts}}

    def life(packs, facts, steps):
        s = State.from_packs([pack(n) for n in packs])
        k = Kernel(s)
        out = {'packs': list(packs), 'start': snap(s, facts), 'steps': {}}
        for name, kind, arg in steps:
            if kind == 'look':
                does, result = {'look': 'executed'}, k.run_standing(execute=True)
            elif kind == 'event':
                does, result = {'event': copy.deepcopy(arg)}, k.on_event(arg, execute=True)
            elif kind == 'measured':
                proposal, part = arg
                row = next(r for r in cut_facts(proposal) if r['predicate'] == proposal['cut'] + '_' + part)
                does, result = {'proposal': copy.deepcopy(proposal), 'event': copy.deepcopy(row)}, k.on_event(row, execute=True)
            elif kind == 'answer':
                step, run, truth, by = arg
                receipt = out['steps'][step]['result']['runs'][run]['model_receipts'][0]
                does, result = {'answer': {'step': step, 'run': run, 'truth': truth, 'by': by}}, answer(k, receipt, truth, by, execute=True)
            else:   # apply
                s.apply(pack(arg))
                does, result = {'apply': arg}, None
            out['steps'][name] = {'does': does, 'result': result, 'after': snap(s, facts)}
        return out

    look = ('look', 'look', None)

    # ---- R73: ordered side effects
    WORDS = ('feedback_given', 'scrubbed', 'written_locally', 'feedback_sent')
    words = lambda version, text: {'predicate': 'feedback_given', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/user-typed', 'version': version, 'text': text}
    bad = '/Users/someone ' + '0123456789abcdef' * 3   # only a path and a long opaque string
    good = 'The feedback command prints nothing when the folder is read-only. Seen in /Users/%s/work/app; reply to %s@example.org.'
    marker = {'predicate': 'scrubbed', 'truth': 'TRUE', 'verified': False, 'source': 'hand-written', 'version': 'none'}
    effects = {'no_scrub_step': life(['120_feedback', '123_team_rail'], WORDS, [look]),
               'fail_closed': life(['120_feedback', '122_scrub_by_code', '123_team_rail'], WORDS,
                                   [('refused', 'event', words('words-2', bad)), ('unverified_marker', 'event', marker), ('again',) + look[1:],
                                    ('sent', 'event', words('words-3', good % ('someone', 'someone'))), ('repeat',) + look[1:],
                                    ('second', 'event', words('words-4', good % ('another', 'another')))]),   # another sender, the same clean text
               'rail_down': life(['120_feedback', '122_scrub_by_code'], WORDS,
                                 [('captured',) + look[1:], ('again',) + look[1:], ('rail_back', 'apply', '123_team_rail'), ('retry',) + look[1:]])}

    # ---- R82: data before cuts
    DESK = ['124_cut_desk']
    PARTS = [f'{c}_{p}' for c in ('hook_chain', 'boot_load') for p in ('baseline_cited', 'samples_ge_100', 'guardrails_hold', 'cut_approved', 'cut_shipped')]
    hook = next(p for p in pack('124_cut_desk')['proposals'] if p['cut'] == 'hook_chain')
    EDITS = {'no_baseline': ('baseline_cited', lambda p: p.update(baseline={'samples': p['baseline']['samples']})),
             'small_sample': ('samples_ge_100', lambda p: p['baseline'].update(samples=42)),
             'guardrail_broken': ('guardrails_hold', lambda p: p['guardrails']['override_count_total'].update(now=17)),
             'never_cut_touched': ('guardrails_hold', lambda p: p['touches'].append('proto-000-text')),
             'more_samples': ('samples_ge_100', lambda p: p['baseline'].update(samples=213)),
             'guardrail_back': ('guardrails_hold', lambda p: p['guardrails']['override_count_total'].update(now=13))}

    def measured(name):   # the hook chain proposal measured again with one thing changed, and the part whose row is handed in
        part, edit = EDITS[name]
        proposal = copy.deepcopy(hook)
        edit(proposal)
        return proposal, part

    cuts = {'missing': {name: life(DESK, PARTS, [('measured', 'measured', measured(name))]) for name in ('no_baseline', 'small_sample', 'guardrail_broken', 'never_cut_touched')},
            'own_question': life(DESK, PARTS, [('first',) + look[1:], ('yes_hook_chain', 'answer', ('first', 0, 'TRUE', 'founder')), ('no_boot_load', 'answer', ('first', 1, 'FALSE', 'founder')),
                                               ('measured_again', 'measured', measured('more_samples')), ('guardrail_broke', 'measured', measured('guardrail_broken')),
                                               ('guardrail_back', 'measured', measured('guardrail_back'))]),
            'yes_without_data': life(DESK, PARTS, [('asked',) + look[1:], ('sample_shrank', 'measured', measured('small_sample')),
                                                   ('yes_hook_chain', 'answer', ('asked', 0, 'TRUE', 'founder'))])}

    # ---- R80: per-tier rules
    RULES = '125_fan_in_rules'
    TIER = {'internal': '126_tier_internal', 'portfolio': '127_tier_portfolio', 'project': '128_tier_project', 'external': '129_tier_external'}
    FACTS = ('tier_internal', 'tier_portfolio', 'tier_project', 'tier_external', 'notice_shown', 'opted_in', 'batch_confirmed', 'signals_sent')
    opt_in = ('opted_in', 'event', {'predicate': 'opted_in', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/consent-ledger', 'version': 'consent-1'})
    yes = ('confirmed', 'answer', ('opted_in', 0, 'TRUE', 'client'))
    foreign = lambda **more: dict({'predicate': 'tier_internal', 'truth': 'TRUE', 'verified': True, 'source': 'fixture/not-the-registry', 'version': 'handed-in-1'}, **more)
    tiers = {'internal': life([RULES, TIER['internal']], FACTS, [look]),
             'portfolio': life([RULES, TIER['portfolio']], FACTS, [look]),
             'project': life([RULES, TIER['project']], FACTS, [look, opt_in, yes]),
             'project_refused': life([RULES, TIER['project']], FACTS, [opt_in, ('refused', 'answer', ('opted_in', 0, 'FALSE', 'client'))]),
             'external': life([RULES, TIER['external']], FACTS, [look, opt_in]),
             'old_grant': life([RULES, TIER['internal'], TIER['project']], FACTS, [look, opt_in, yes]),   # was internal, is a project now: the internal grant is still held
             'foreign_row': life([RULES, TIER['project']], FACTS, [('unverified_row', 'event', foreign(verified=False)), ('row_from_another_scope', 'event', foreign(scope='internal/fan-in')),
                                                                  ('row_in_scope', 'event', foreign()), opt_in, yes])}
    return {'effects': effects, 'cuts': cuts, 'tiers': tiers}
