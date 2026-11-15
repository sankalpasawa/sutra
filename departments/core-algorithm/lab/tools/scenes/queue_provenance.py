"""R91, recorded: the decision rows of the loan desk's day (the look itself is case 58), what the escalated decision reads
like once it is answered, and the rows of a run whose step stopped after the gate (the look is case 30_stop).
Two States from the same pack: on the first the credit head says no, on the second yes.
The books are read before each look, the look is the kernel's, and the projection is handed both: it runs nothing."""
LOOKS = 2   # answered_no and answered_yes: what the kernel returned for each answer
RUNS = 2    # one run in each; the decision rows, the books and the refusal are no runs (the day's own look is case 58, not kept here)


def scene(lab):
    from extensions.queue_provenance import books, decisions
    State, Kernel, pack, answer = lab['State'], lab['Kernel'], lab['pack'], lab['answer']
    lines = lambda b: {key: b[key] for key in ('grants', 'providers', 'budget')}

    def looked(*names):
        s = State.from_packs([pack(n) for n in names])
        k = Kernel(s)
        before = books(s)
        result = k.run_standing(execute=True)
        return s, k, before, result, decisions(result['runs'], before)

    s, k, before, result, rows = looked('132_loan_desk')
    asked = next(x for r in result['runs'] for x in r['model_receipts'] if x.get('parked'))
    after = books(s)
    try:   # the books as the look left them, handed in as if the look had started from them: they do not explain its trace
        decisions(result['runs'], after)
        refused = None
    except ValueError as e:
        refused = str(e)
    no = answer(k, asked, 'FALSE', 'credit-head', execute=True)
    s2, k2, _, result2, _ = looked('132_loan_desk')
    after2 = books(s2)
    yes = answer(k2, next(x for r in result2['runs'] for x in r['model_receipts'] if x.get('parked')), 'TRUE', 'credit-head', execute=True)
    stopped = looked('30_build_goal', '31_build_theory', '82_components_without_constructor')[4]
    return {'decisions': rows, 'books_before': lines(before), 'books_after': lines(after), 'wrong_books_refused': refused,
            'answered_no': no, 'decisions_after_no': decisions(no['runs'], after),
            'answered_yes': yes, 'decisions_after_yes': decisions(yes['runs'], after2),
            'decisions_of_a_stopped_step': stopped}
