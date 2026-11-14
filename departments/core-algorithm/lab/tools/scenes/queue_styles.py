"""R101, recorded: one complaint, one goal, and what each word of the router does to it.
Standing looks, each on a fresh State (so each starts from the same books): before the router has spoken; routed to each
of the two declared styles; and each of those again under the declaration that a third card replaces it with.
Then the router names a style the declaration does not list: the row arrives as an event, nobody reads it, and the look
that follows is the look before the router spoke.
Then the router says the complaint is unmatched (the look is case 59): the charter owner is asked. On one State the
owner says no (it stays: a new style is to be declared here), the campaign card and the replaced declaration are
applied, and the router names the new style. On a second State the owner says yes (a new home)."""
LOOKS = 11  # seven standing looks (unrouted, by_the_book, incident, the two older styles under the new declaration, unlisted, unmatched),
            # two events of the router (unlisted_named, new_style) and the owner's two answers (answered_no, answered_yes)
RUNS = 10   # one run in each of them, except unlisted_named: no goal reads that row, so it holds no run


def scene(lab):
    State, Kernel, pack, answer = lab['State'], lab['Kernel'], lab['pack'], lab['answer']
    desk = ['133_complaint_desk', '134_style_run_the_book', '135_style_incident']
    snap = lambda s: {'budget': dict(s.budget), 'providers': dict(s.providers)}
    names = lambda style: {'predicate': 'styled_' + style, 'truth': 'TRUE', 'verified': True, 'source': 'router/credit-ops', 'version': 'r2'}   # the router's row, as an event

    def fresh(*more):
        s = State.from_packs([pack(n) for n in desk + list(more)])
        return s, Kernel(s)

    out = {}
    for name, more in (('unrouted', []), ('by_the_book', ['136_routed_by_the_book']), ('incident', ['137_routed_incident']),
                       ('old_style_under_new', ['136_routed_by_the_book', '139_style_campaign']),
                       ('other_old_style_under_new', ['137_routed_incident', '139_style_campaign'])):
        s, k = fresh(*more)
        out[name] = k.run_standing(execute=True)
        out['after_' + name] = snap(s)

    s, k = fresh()
    out['unlisted_named'] = k.on_event(names('campaign'), execute=True)
    out['unlisted'] = k.run_standing(execute=True)
    out['after_unlisted'] = snap(s)

    s, k = fresh('138_routed_unmatched')
    out['unmatched'] = k.run_standing(execute=True)
    out['after_unmatched'] = snap(s)
    out['answered_no'] = answer(k, out['unmatched']['runs'][0]['model_receipts'][-1], 'FALSE', 'charter-owner', execute=True)
    out['after_no'] = snap(s)
    s.apply(pack('139_style_campaign'))
    out['new_style'] = k.on_event(names('campaign'), execute=True)
    out['after_new_style'] = snap(s)

    s, k = fresh('138_routed_unmatched')
    first = k.run_standing(execute=True)
    out['answered_yes'] = answer(k, first['runs'][0]['model_receipts'][-1], 'TRUE', 'charter-owner', execute=True)
    out['after_yes'] = snap(s)
    return out
