# 0.16.0-ordered: packs 120 to 129 (matrix rows R73, R82, R80). Authoring code, handed pack, fact, rule and method.
from extensions.ordered_cuts import cut_facts
from extensions.ordered_tiers import tier_faults

STEP = {'compute': 1, 'money': 0, 'attention': 0}
ASK = {'compute': 0, 'money': 0, 'attention': 1}

# R73, ordered side effects: a person's words are scrubbed, written locally, then sent. The order is in what each step requires:
# the write requires the scrub (never write raw because the scrub broke), the send requires the write (local capture before any
# network attempt) and the scrub (scrub before fan-out). Every step also requires the words themselves, so each row made is about
# one message: the next message is scrubbed, written and sent again, also when it scrubs to the same clean text.
# The capture is a standing goal of its own, ahead of the send: when the send cannot run the words are still scrubbed and written.
# The steps are authored out of order on purpose: send, write, and the scrub in a pack of its own. Pack 121 simulates the scrub
# like any other step (scrub@1); pack 122 hands the scrub to code outside the kernel (the kind scrub_text, kinds/scrub_text.py,
# which runs the sanitizer of extensions/ordered_effects.py and can refuse the words). The two are two methods, so each has an
# id of its own: a method id names one method in the whole lab. A State is given pack 121 or pack 122. One that holds both has
# two steps for one row at one cost, and the kernel's rule for equal plans (the order of the step names) takes scrub-text@1.
# Pack 120 gives the team rail no slot: the rail is another pack (123), and without it the send has no provider.
ABSENT = 'fixture/marker-absent'
WORDS = 'feedback_given'
pack('120_feedback', scope='sutra/feedback', goals=['written_locally', 'feedback_sent'],
     evidence=[dict(fact(WORDS, 'TRUE', source='fixture/user-typed', version='words-1'),
                    text='The start command refuses a folder that only holds a settings directory. Seen in /Users/someone/work/app; write to someone@example.org.'),
               fact('scrubbed', 'FALSE', source=ABSENT), fact('written_locally', 'FALSE', source=ABSENT), fact('feedback_sent', 'FALSE', source=ABSENT)],
     methods=[method('push@1', 'feedback_sent', ['written_locally', 'scrubbed', WORDS], provider='team-rail', cost=STEP),
              method('write-local@1', 'written_locally', ['scrubbed', WORDS], provider='local-disk', cost=STEP)],
     providers={'local-disk': 2, 'sanitizer': 2}, grants=['action:push@1', 'action:write-local@1'])
pack('121_scrub_simulated', methods=[method('scrub@1', 'scrubbed', [WORDS], provider='sanitizer', cost=STEP)], grants=['action:scrub@1'])
pack('122_scrub_by_code', methods=[method('scrub-text@1', 'scrubbed', [WORDS], provider='sanitizer', cost=STEP, action='scrub_text', scrubs=WORDS)], grants=['action:scrub-text@1'])
pack('123_team_rail', providers={'team-rail': 2})

# R82, data before cuts: a cut lands when it is admissible (a cited baseline, at least 100 samples, guardrails holding: three adapter
# rows), approved (its own question to the founder) and shipped. Three locks carry "data before cuts", and each is read by a test:
# the rule (a cut is not landed without its three parts, whatever else is true), the ask's prerequisites (nobody is asked about a
# cut without its data) and the ship's prerequisites (a yes never stands in for the data). Two cuts on one desk, each with its own
# rules, question and step; the proposals the rows were read from are kept beside them.
HOOK = {'id': 'cut-proposal-hook-chain', 'cut': 'hook_chain', 'sink': 'hook chain overhead per tool call',
        'baseline': {'source': 'holding/LATENCY-LOG.jsonl', 'metric': 'hook_chain_overhead_p95_ms', 'value': 640, 'samples': 212},
        'target': {'metric': 'hook_chain_overhead_p95_ms', 'value': 300},
        'guardrails': {'override_count_total': {'before': 14, 'now': 14}, 'triage_correct_pct': 96}, 'touches': ['hook-pretool-chain']}
BOOT = {'id': 'cut-proposal-boot-load', 'cut': 'boot_load', 'sink': 'boot load before the first output',
        'baseline': {'source': 'holding/LATENCY-LOG.jsonl', 'metric': 'boot_load_p50_ms', 'value': 15200, 'samples': 131},
        'target': {'metric': 'boot_load_p50_ms', 'value': 8000},
        'guardrails': {'override_count_total': {'before': 14, 'now': 14}, 'triage_correct_pct': 96}, 'touches': ['boot-context-files']}


def _cut(c, what):
    slug = c.replace('_', '-')
    parts = [f'{c}_baseline_cited', f'{c}_samples_ge_100', f'{c}_guardrails_hold']
    return {'rules': [rule(f'R-{slug.upper()}-ADMISSIBLE@1', f'{c}_cut_admissible', [parts], source='reviewed/speed-charter'),
                      rule(f'R-{slug.upper()}-LANDED@1', f'{c}_cut_landed', [[f'{c}_cut_admissible', f'{c}_cut_approved', f'{c}_cut_shipped']], source='reviewed/speed-charter')],
            'methods': [method(f'ship-{slug}-cut@1', f'{c}_cut_shipped', parts + [f'{c}_cut_approved'], cost=STEP),
                        method(f'ask-{slug}-cut-approval@1', f'{c}_cut_approved', parts, provider='founder-channel', cost=ASK, action='ask',
                               question=f'Approve this one cut, {what}? Its baseline, its sample and its guardrails are on file.', ask_to='founder')],
            'grants': [f'action:ship-{slug}-cut@1', f'action:ask-{slug}-cut-approval@1']}


_a, _b = _cut('hook_chain', 'the hook chain overhead cut'), _cut('boot_load', 'the boot load cut')
pack('124_cut_desk', scope='sutra/speed', goals=['hook_chain_cut_landed', 'boot_load_cut_landed'], rules=_a['rules'] + _b['rules'],
     methods=_a['methods'] + _b['methods'], providers={'local-provider': 4, 'founder-channel': 3}, grants=_a['grants'] + _b['grants'],
     evidence=cut_facts(HOOK) + cut_facts(BOOT) + [fact('hook_chain_cut_shipped', 'FALSE', source='fixture/not-shipped'),
                                                   fact('boot_load_cut_shipped', 'FALSE', source='fixture/not-shipped')],
     proposals=[HOOK, BOOT])   # the proposals the rows were read from; the kernel ignores this field, the verifier reads it

# R80, per-tier rules: one rule set (pack 125) for the fan-in of captured signals to the team (the fan-in and consent columns of the
# Privacy charter's tiered contract), one alternative per tier, the tier as an evidence row. Internal installs send; a portfolio
# install shows its notice first; a client project needs its opt-in on file and then asks the client about the batch in hand; an
# install of the external fleet sends nothing until an opt-in is on file. The rule set holds goals, rules and methods and nothing
# else; each tier pack holds its scope, the four tier rows (one TRUE), what has not happened yet, and its own grants. tier_faults
# refuses a set in which one tier could use another tier's way.
TIERS = ['tier_internal', 'tier_portfolio', 'tier_project', 'tier_external']
FAN_IN = {'goals': ['fan_in_done'],
          'rules': [rule('R-FAN-IN@1', 'fan_in_done', [['tier_internal', 'signals_sent'], ['tier_portfolio', 'notice_shown', 'signals_sent'],
                                                       ['tier_project', 'opted_in', 'batch_confirmed', 'signals_sent'], ['tier_external', 'opted_in', 'signals_sent']],
                         source='reviewed/privacy-tiered-contract')],
          'methods': [method('send-internal@1', 'signals_sent', ['tier_internal'], grant='fan-in:internal', cost=STEP),
                      method('send-portfolio@1', 'signals_sent', ['tier_portfolio', 'notice_shown'], grant='fan-in:portfolio', cost=STEP),
                      method('send-project@1', 'signals_sent', ['tier_project', 'opted_in', 'batch_confirmed'], grant='fan-in:project', cost=STEP),
                      method('send-external@1', 'signals_sent', ['tier_external', 'opted_in'], grant='fan-in:external', cost=STEP),
                      method('show-notice@1', 'notice_shown', ['tier_portfolio'], grant='notice:portfolio', cost=STEP),
                      method('ask-batch-confirm@1', 'batch_confirmed', ['tier_project', 'opted_in'], provider='client-channel', grant='ask:client', cost=ASK, action='ask',
                             question='May this batch of signals go to the Sutra team?', ask_to='client')]}


def _tier(own, scope, grants, more=(), providers=None):
    return {'scope': scope, 'evidence': [fact(t, 'TRUE' if t == own else 'FALSE', source='fixture/client-registry') for t in TIERS]
            + [fact('signals_sent', 'FALSE', source='fixture/nothing-sent')] + list(more), 'grants': grants, 'providers': providers or {'local-provider': 3}}


TIER_PACKS = {'126_tier_internal': _tier('tier_internal', 'internal/fan-in', ['fan-in:internal']),
              '127_tier_portfolio': _tier('tier_portfolio', 'portfolio/fan-in', ['fan-in:portfolio', 'notice:portfolio'], [fact('notice_shown', 'FALSE', source='fixture/no-banner-yet')]),
              '128_tier_project': _tier('tier_project', 'project/fan-in', ['fan-in:project', 'ask:client'], providers={'local-provider': 3, 'client-channel': 1}),
              '129_tier_external': _tier('tier_external', 'fleet/fan-in', ['fan-in:external'])}
_faults = tier_faults(dict(FAN_IN, id='125_fan_in_rules'), [dict(p, id=n) for n, p in TIER_PACKS.items()], 'fan_in_done')
if _faults:
    raise ValueError('These tier packs let one tier use the way of another: ' + '; '.join(_faults))
pack('125_fan_in_rules', **FAN_IN)
for _n, _p in TIER_PACKS.items():
    pack(_n, **_p)
