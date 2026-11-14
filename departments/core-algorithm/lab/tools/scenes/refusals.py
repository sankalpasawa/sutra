"""Recorded sequences of 0.15.0-refusals (matrix rows R49, R103, R37): what one look cannot show.
Every pack loaded here is a scenario file, so the verifier checks each run below like any other."""
LOOKS = 11   # the looks scene(lab) records (a dict that holds a list under `runs`): desk 4 (the later allow, the look, the re-screening, the look under the later pack), yes 2, no 4, narrowing 1
RUNS = 22    # the runs in them (a dict with `trace` and `trace_root_sha256`): desk 8 + 8, yes 1 + 1, no 1 + 1 + 1, narrowing 1; the two later allows and the re-screening start none


def scene(lab):
    from extensions.refusals_classes import screened
    from extensions.refusals_narrowing import relaxations
    State, Kernel, pack, answer, open_asks = lab['State'], lab['Kernel'], lab['pack'], lab['answer'], lab['open_asks']
    DESK = ['110_ops_desk', '111_requested_actions']
    TEAM = ['112_servicing_team', '113_servicing_standing_rules']
    PRACTICE = TEAM + ['114_practice_money_movement']
    LOOSE = PRACTICE + ['115_servicing_loosens']

    def start(names):
        s = State.from_packs([pack(n) for n in names])
        return s, Kernel(s)

    def snap(s):   # the books after a step of the sequence, and what the State turned away
        return {'budget': dict(s.budget), 'providers': dict(s.providers), 'open_asks': open_asks(s),
                'turned_away': [j for j in s.event_journal if j.get('status') == 'DECISION_STANDS']}

    def allow(fact, source):   # an ordinary row that says yes
        return {'predicate': fact, 'truth': 'TRUE', 'verified': True, 'source': source, 'version': 'allow-1'}

    # R49. An allow that arrives later does not open a refused class: the row is turned away, and the eight looks end as in case 51.
    s, k = start(DESK)
    desk = {'packs': DESK, 'allow_later': k.on_event(allow('may:privilege_escalation', 'team:lendco/platform'), execute=True),
            'look': k.run_standing(execute=True), 'after': snap(s)}
    # The export ran on the reading of its request. The reading of another request for the same step arrives: it is another fact,
    # no step requires it, and nothing runs or is paid again.
    desk['rescreened'] = k.on_event(screened('export-due-list@1', {'kind': 'command', 'text': 'sudo python3 reports/due_list.py --month 2026-11'}), execute=True)
    desk['after_rescreened'] = snap(s)
    # Nor does a team's later pack that brings its own method for the refused permission, with its grant and a bigger budget; the check names that pack.
    LATER = DESK + ['119_platform_allows_itself']
    s, k = start(LATER)
    desk['later_pack'] = {'packs': LATER, 'relaxed': relaxations([pack(n) for n in DESK], pack(LATER[-1])), 'look': k.run_standing(execute=True), 'after': snap(s)}

    # R103, with the practice pick. The look asks the owner and waits; the owner says yes; the refund is paid and reconciled by another holder.
    s, k = start(PRACTICE)
    look = k.run_standing(execute=True)
    yes = {'packs': PRACTICE, 'look': look, 'after_look': snap(s),
           'answered_yes': answer(k, look['runs'][0]['model_receipts'][-1], 'TRUE', 'owner', execute=True), 'after_yes': snap(s)}

    # The same team, and the owner says no. Nothing is paid by any route; a later allow of the route the owner refused is turned away.
    s, k = start(PRACTICE)
    look = k.run_standing(execute=True)
    no = {'packs': PRACTICE, 'look': look,
          'answered_no': answer(k, look['runs'][0]['model_receipts'][-1], 'FALSE', 'owner', execute=True),
          'allow_later': k.on_event(allow('third_party_payout_allowed', 'team:lendco/servicing'), execute=True),
          'look_again': k.run_standing(execute=True), 'after': snap(s)}

    # R37. What the check says of the two child packs, and what the kernel does with the one that loosens: it applies it.
    narrowing = {'practice': {'parents': TEAM, 'child': PRACTICE[-1], 'relaxed': relaxations([pack(n) for n in TEAM], pack(PRACTICE[-1]))},
                 'loosened': {'parents': PRACTICE, 'child': LOOSE[-1], 'relaxed': relaxations([pack(n) for n in PRACTICE], pack(LOOSE[-1]))}}
    s, k = start(LOOSE)
    narrowing['loosened'].update(packs=LOOSE, look=k.run_standing(execute=True), after=snap(s))
    return {'desk': desk, 'yes': yes, 'no': no, 'narrowing': narrowing}
