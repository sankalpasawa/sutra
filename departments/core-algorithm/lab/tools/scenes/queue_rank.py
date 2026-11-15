"""R31b, recorded: the collections queue looked at as it is listed, then ranked by the extension and looked at again.
Two States from the same pack, so the two looks start from the same books and differ in nothing but the order of the queue.
A snapshot is taken before the ranking, right after it and after ranking a second time: the order of the queue and the
list of packs are all that a ranking changes, and a second ranking changes nothing.
Then three queues that cannot be ranked, each for another reason, each left exactly as it was: a goal with no rule
(the first order goal), a rule that declares no impact (the complaint desk), an impact that is a word (the loan desk)."""
LOOKS = 2   # as_listed and as_ranked: each a look at the four goals of the queue
RUNS = 8    # four runs in each of the two looks; the snapshots, the ranking and the three refusals hold no run


def scene(lab):
    from extensions.queue_rank import rank
    State, Kernel, pack = lab['State'], lab['Kernel'], lab['pack']
    snap = lambda s: {'goals': list(s.goals), 'budget': dict(s.budget), 'providers': dict(s.providers), 'grants': sorted(s.grants), 'loaded': [dict(p) for p in s.loaded]}
    listed = State.from_packs([pack('130_collections_queue')])
    as_listed = Kernel(listed).run_standing(execute=True)
    ranked = State.from_packs([pack('130_collections_queue')])
    before = snap(ranked)
    kept = rank(ranked, '131_queue_ranked')   # the live ranking: it must be the pack the scenario file holds, or the verifier's pack check fails
    after_ranking = snap(ranked)
    rank(ranked, '131_queue_ranked')          # ranking again changes nothing: not even the list of packs
    after_ranking_again = snap(ranked)
    as_ranked = Kernel(ranked).run_standing(execute=True)

    def refusal(*names):
        s = State.from_packs([pack(n) for n in names])
        was = snap(s)
        try:
            rank(s, 'never-applied')
            said = None
        except ValueError as e:
            said = str(e)
        return {'packs': list(names), 'refused': said, 'before': was, 'after': snap(s)}

    return {'as_listed': as_listed, 'after_listed': snap(listed), 'before_ranking': before, 'ranking': kept, 'after_ranking': after_ranking,
            'after_ranking_again': after_ranking_again, 'as_ranked': as_ranked, 'after_ranked': snap(ranked),
            'not_ranked': [refusal('00_goal'), refusal('133_complaint_desk'), refusal('132_loan_desk')]}
