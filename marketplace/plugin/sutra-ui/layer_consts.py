"""layer_consts.py -- the constants and tables the interface's definitions read (PRD amendment A4, A4.3.1).

They were the top of layer_schema.py; they are here, text unchanged, so that layer_models (the definitions as pydantic classes)
can read them without importing layer_schema, and layer_schema does `from layer_consts import *`, so every name is still
`layer_schema.<name>`. This module imports nothing: no pydantic, nothing of the app, not layer_schema or layer_models.

What stays in layer_schema.py is what a test patches or W3-PROOF freezes: SCHEMA_VERSION, INTERFACE_SHA, MODE, OWNERSHIP_MODE,
NEVER_REFUSE, REFUSED, ANY and HERE.
"""

LAYER_NAMES = ('root', 'identity', 'adaptation', 'priority', 'coordination', 'audit')
FUNCTION_LAYERS = LAYER_NAMES[1:]
TITLE = {'root': 'Root', 'identity': 'Identity', 'adaptation': 'Adaptation', 'priority': 'Priority',
         'coordination': 'Coordination', 'audit': 'Audit'}
ENGINE_LAYER = {'Identity': 'identity', 'Adaptation': 'adaptation', 'Priority': 'priority',
                'Coordination': 'coordination', 'Audit': 'audit', 'Setup': 'root'}
ACTORS = ('Owner', 'Root', 'Identity', 'Adaptation', 'Priority', 'Coordination', 'Audit', 'Engine')
#   the engine_defs edge keys, plus Engine: any work engine of the line
ACTS = ('request', 'agree', 'refuse', 'propose', 'accept-proposal', 'reject-proposal', 'inform',
        'failure', 'not-understood', 'cancel')                               # == engine_runtime.ACTS
DEFAULT_PINS = {'root': 'root/v1', 'identity': 'identity/v1', 'adaptation': 'adaptation/v1',
                'priority': 'priority/v1', 'coordination': 'coordination/v1', 'audit': 'audit/v1'}
#   the release's choice of implementation per layer: what a department is born with, and what a pin of its record that cannot
#   run falls back to (W3-PINS: a record's own pin wins over it, so a department born earlier keeps the version it was born
#   with until it is re-pinned); changing it is not a schema change, but it needs the contract and the gate (A1.21)
PER_DEPARTMENT = True    # W3-PINS: a department runs the versions its record pins (recipes and bodies together); False runs DEFAULT_PINS for all
IMPL_RE = r'^(root|identity|adaptation|priority|coordination|audit)/v[1-9][0-9]*$'
ITEM_RE, FINDING_RE = r'^D[1-9][0-9]?$', r'^F[1-9][0-9]{0,2}$'
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9 &'.-]{0,39}$"                      # an engine or artifact name
BOUNDS = {'hops': 4, 'seconds': 900, 'usd': 0.5}                       # == engine_runtime.BOUNDS
CHAIN_LIMIT = 12                                                       # == website_dept.CHAIN_LIMIT
REPAIRS = 2                                                            # == j2_runtime.REPAIRS
OPTIONS_MAX = 3                                                        # == website_dept.OPTIONS_MAX
DONE_ITEMS_MAX = 12                                                    # == website_dept.DONE_ITEMS_MAX
RUNGS = ('P', 'C0', 'C1', 'C2')                                        # == engine_runtime.RUNGS
STANDARD = ('goal', 'items', 'rules', 'owner', 'budget', 'invented')   # == engine_runtime.STANDARD (MK-1)
DONE_HOW, DONE_LEVELS = ('code', 'model', 'person'), ('target', 'outcome')    # the coverings' enums (MK-2), never the store's
RULE_TAGS = ('go', 'ask', 'refuse', 'always')                                # the covering's enum, never the store's
SOURCES = ('library', 'shaped', 'fitted', 'made')     # library and shaped are written today; fitted (M5.2) and made (M6) are reserved
#: the workflow classes (A2.8): a source is a class, and this is what each extends, {child source: parent source}; None is a source
#: that extends the workflow interface itself. A child source is held to every standard its parent source is, which
#: test_layer_inherit.py proves over WORKFLOW_STANDARDS: a standard that lists the parent lists the child.
WORKFLOW_FAMILY = {'library': None, 'fitted': 'library', 'shaped': None, 'made': 'shaped'}
SEVERITIES = ('high', 'medium', 'low')
ITEM_VERDICTS = ('met', 'not_met', 'to_confirm')
CONFIDENCE = {'ask_below': 0.6, 'show_below': 0.8}                     # J2B-7 (M6.4, wave 1)
RAISE_CAP, ROUNDS_DEFAULT = 2.0, 6                                     # Q6 (M5.4, M9.2, wave 2)
QUESTION_STATUSES = ('open', 'answered', 'unanswered', 'refused')      # board/1 (M4.9, wave 3)

# ---- the enums and tables the definitions read (A1.8, A1.14, A1.15) ---------------------------------------------------
#: every status an asks.json row takes, from its writers: _put_ask's callers, choose_option, decide_ask, _blocked
#: (replaced), _reopen (chosen) and j2_runtime's answer (stamped)
ASK_STATUSES = ('pending', 'stamped', 'refused', 'answered', 'chosen', 'replaced')
#: every kind an asks.json row takes, A1.8's list completed from the writers: model (_held_back), step (_person) and
#: request (identity_file's 'reaches outside' ask)
ASK_KINDS = ('publish', 'setup', 'engine', 'envelope', 'alarm', 'finding', 'hole', 'rule', 'goal', 'rung', 'trial',
             'conflict', 'line', 'j2_identity', 'done_items', 'instructions', 'blocked', 'model', 'step', 'request')

#: the ways out an ask offers (A1.15): which layer applies each, its params (a DEFS name, or None), what it says, and
#: the wave it is built in (0: built before A1, M3.5)
OPTION_KINDS = {
    'words': {'layer': 'identity', 'params': None, 'says': 'change the plan in my words', 'from_wave': 0},
    'leave': {'layer': 'identity', 'params': None, 'says': 'leave an item out of done-when', 'from_wave': 0},
    'stop': {'layer': 'identity', 'params': None, 'says': 'stop here', 'from_wave': 0},
    'raise': {'layer': 'priority', 'params': 'option.raise', 'says': 'add budget, up to twice where it started', 'from_wave': 2},
    'root_setup': {'layer': 'root', 'params': 'option.words', 'says': 'set the department up again, done its own way', 'from_wave': 1},
    'pin': {'layer': 'root', 'params': 'option.pin', 'says': 'run another version of one function', 'from_wave': 3},
}

#: Root's standards (A1.14; MK-4 taken): (id, says, sources, stages). The says text is what S11 and S18 show. Their code
#: is workflow_schema.py (W1-ROOT); until it is on main, validate_workflow returns the shape rows only.
WORKFLOW_STANDARDS = (
    ('names_an_engine', 'the workflow names its engines', SOURCES, ('proposal', 'registration', 'write', 'grow', 'birth')),
    ('engines_known', 'each engine is one the Library has', ('library', 'fitted'), ('birth', 'registration', 'write', 'grow')),
    ('each_engine_named', 'every engine has a name', ('shaped', 'made'), ('proposal', 'registration', 'grow')),
    ('names_unique', "no name is used twice, and none is a function's, Root's or Owner's", SOURCES,
     ('proposal', 'registration', 'grow')),
    ('names_new', 'no name is one the Library already has', ('shaped', 'made'), ('proposal', 'registration')),
    ('first_reads_input', "the first engine reads the kind's first artifact", SOURCES, ('proposal', 'birth', 'registration')),
    ('reads_known', "each engine reads the kind's first artifact or what one before it wrote", SOURCES,
     ('proposal', 'birth', 'registration', 'grow')),
    ('one_output', 'each engine writes something not yet written', SOURCES, ('proposal', 'birth', 'registration', 'grow')),
    ('items_covered', 'every done-when item is covered by an engine', SOURCES, ('registration', 'proposal')),
    ('required_kept', 'no engine the kind requires is left out', SOURCES, ('proposal', 'birth', 'registration')),
    ('size_in_range', 'one engine or more; more than six says why', SOURCES, ('proposal', 'registration')),
    ('check_exists', "each engine's output has a check", SOURCES, ('registration', 'grow')),
    ('fits_room', "Priority priced it and it fits today's room", SOURCES, ('registration',)),
    ('line_is_registered', "Coordination's line is a registered plan plus the engines the owner added", SOURCES, ('write',)),
)
STAGES = ('birth', 'proposal', 'registration', 'grow', 'write')

#: the field tuples the code names once (engine_runtime M4, functions_view M4.5 and M4.7); the definitions below are
#: built from them, and test_layer_schema keeps them equal to the code's
TABLE_FIELDS = ('order', 'functions', 'line', 'edges', 'left_out', 'grown', 'registered', 'timetable', 'by', 'since', 'why')
LEFT_OUT_FIELDS = ('engine', 'in_line', 'since')
SLOT_FIELDS = ('engine', 'on', 'of', 'checked', 'every_s', 'window_min', 'since')
COORDINATION_FIELDS = ('line', 'registered', 'timetable', 'left_out', 'holds', 'handoffs', 'chain', 'alarms', 'ties', 'questions')
TIMETABLE_ROW = ('engine', 'on', 'starts', 'window_min', 'since', 'state', 'word', 'why', 'at', 'last')
ENGINE_CARD_FIELDS = ('engine', 'head', 'motor', 'five')
ENGINE_FIVE_ROW = ('fn', 'state', 'says', 'at', 'share')
BORN_FIELDS = ('engines', 'version', 'full', 'grow', 'before')     # == engine_runtime.BORN_FIELDS
SLOT_STATES = ('running', 'turn', 'waits', 'ran', 'stopped')         # == functions_view.TT_WORDS' keys

NATURES = ('transform', 'check', 'decide', 'make')                     # == engine_runtime.NATURES
GATE_ANSWERS = ('admit', 'wait', 'refuse')                             # == VERDICTS['identity']['gate'], and what a gate's check accepts
MODEL_TOOLS = ('WebSearch', 'WebFetch')                                # == website_dept.MODEL_TOOLS
STEP_KINDS = ('code', 'ai', 'person', 'gate', 'rule')
#: every key a step's body is handed in its context, as a recorded run saw them: peek is on Coordination's rule context and
#: on every gate's; table, rs and done are Coordination's; ready is the tie's; run and spend are an engine run's. item is the
#: fan-out item (the body's third argument on main; reserved here as A3.3 names it)
STEP_CTX = ('ref', 'dept', 'engine', 'def', 'slot', 'inp', 'post', 'run', 'bag', 'how', 'spend', 'table', 'rs', 'done', 'ready',
            'item', 'peek')
#: every key of a line of steps.jsonl, from the three writers (run_step, a gate's decision, the owner's mark): ask is on the
#: row of a step that waits for the owner
STEP_ROW = ('id', 'run', 'engine', 'step', 'item', 'mode', 'slot', 'impl', 'asked_rung', 'rung', 'miss', 'by', 'agent', 'applied',
            'read', 'facts', 'in_sig', 'usd', 'calls', 'def_version', 'started', 'status', 'why', 'ask', 'answer', 'out_hash',
            'out_shape', 'check', 'trial', 'ended', 'ms')

JOURNEY_KINDS = ('person', 'system', 'function')
LANE_KINDS = ('person', 'root', 'function', 'engine')
STEP_ACTS = ('say', 'ask', 'tell', 'stamp', 'file', 'read', 'run', 'check', 'post', 'decide')
BIND_KINDS = ('act', 'step', 'event', 'api', 'ui', 'person')
OUTCOME_KINDS = ('tell', 'ask', 'file', 'hold', 'refuse', 'block', 'retry', 'none')
OUTCOME_VOICES = ('Identity', 'Root', 'Coordination', 'none')
SITE_STATUS = ('built', 'wanted', 'today', 'open', 'directed', 'partly', 'not_built', 'to_build', 'none')
DISPOSITIONS = ('keep', 'change', 'drop')
ROW_STATES = ('proven', 'partly', 'failing', 'unproven', 'wanted', 'dropped', 'fault')     # derived, never in a definition
READ_STATES = ROW_STATES + ('unknown',)                                                     # what the read model says before a run
JOURNEY_STATES = ROW_STATES + ('declared',)                                                 # a declared journey has no computed state
RULING_STATUS = ('RULED', 'OPEN', 'PARKED')
JOURNEY_ID = r'^(J[1-9][0-9]?|S[1-9]|U[1-9]|F(?:I|A|P|C|AU)[1-9])$'
SUB_ID = r'^J[1-9][0-9]?\.[a-z]$'
STEP_N = r'^([0-9]|[1-9][0-9])[a-e]?$'                       # 0a and 0b are the earlier rows of J2; 4a to 4e are J3's branches
EDGE_ID = r'^(J[1-9][0-9]?|F(?:I|A|P|C|AU)[1-9])\.[1-9][0-9]?$'
LANE_ID = r'^[a-z][a-z0-9_]{0,15}$'
BACKLOG_ID = r'^BL-[1-9][0-9]?[a-z]?$'                       # BL-2b
SAME_AS = r'^J[1-9][0-9]?/(step/[1-9][0-9]?[a-e]?|edge/J[1-9][0-9]?\.[1-9][0-9]?)$'
SYMBOL = r'^([A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_$][A-Za-z0-9_$]*$'              # a name, or module.name
TEST_REF = (r'^(js:[A-Za-z0-9_.-]+\.js#[A-Za-z0-9_.-]+|'
            r'[A-Za-z0-9_.-]+\.py::([A-Za-z_][A-Za-z0-9_]*::)?[A-Za-z_][A-Za-z0-9_]*)$')   # file.py::test, file.py::Class::test, js:file.js#W45
STEP_REF = r'^J[1-9][0-9]?:[1-9][0-9]?[a-e]?$'                                  # 'J2:6' = step 6 of J2
RULING_ID = r'^(S|Q|MK|D|A1|A2|A3)-?[A-Za-z0-9]{1,4}$'

#: the ledger's actions: the dotted words j2_runtime writes on a row of the cycle's ledger (an action of note(...) or of the
#: activity feed, and the reason code check.failed that run.failed and workflow.blocked carry). The interface names them,
#: j2_runtime owns them (A1.22): a journey's event bind names one of these, and a test keeps the list equal to j2_runtime's
#: literals, so a package that adds a ledger action adds it here in the same commit
LEDGER_ACTIONS = ('proposal.requested', 'proposal.created', 'proposal.granted', 'proposal.countered', 'proposal.refused',
                  'proposal.accepted', 'workflow.validated', 'workflow.registered', 'workflow.blocked', 'timetable.written',
                  'envelope.granted', 'envelope.held', 'slot.assigned', 'run.started', 'run.completed', 'run.failed',
                  'artifact.filed', 'audit.finding_filed', 'audit.not_read', 'identity.assessed', 'identity.questioned',
                  'identity.ruled', 'conflict.raised', 'ask.created', 'ask.answered', 'goal.reached', 'cycle.stopped',
                  'cycle.resumed', 'cycle.reopened', 'goal.revised', 'check.failed')


__all__ = [
    'LAYER_NAMES',
    'FUNCTION_LAYERS',
    'TITLE',
    'ENGINE_LAYER',
    'ACTORS',
    'ACTS',
    'DEFAULT_PINS',
    'PER_DEPARTMENT',
    'IMPL_RE',
    'ITEM_RE',
    'FINDING_RE',
    'NAME_RE',
    'BOUNDS',
    'CHAIN_LIMIT',
    'REPAIRS',
    'OPTIONS_MAX',
    'DONE_ITEMS_MAX',
    'RUNGS',
    'STANDARD',
    'DONE_HOW',
    'DONE_LEVELS',
    'RULE_TAGS',
    'SOURCES',
    'WORKFLOW_FAMILY',
    'SEVERITIES',
    'ITEM_VERDICTS',
    'CONFIDENCE',
    'RAISE_CAP',
    'ROUNDS_DEFAULT',
    'QUESTION_STATUSES',
    'ASK_STATUSES',
    'ASK_KINDS',
    'OPTION_KINDS',
    'WORKFLOW_STANDARDS',
    'STAGES',
    'TABLE_FIELDS',
    'LEFT_OUT_FIELDS',
    'SLOT_FIELDS',
    'COORDINATION_FIELDS',
    'TIMETABLE_ROW',
    'ENGINE_CARD_FIELDS',
    'ENGINE_FIVE_ROW',
    'BORN_FIELDS',
    'SLOT_STATES',
    'NATURES',
    'GATE_ANSWERS',
    'MODEL_TOOLS',
    'STEP_KINDS',
    'STEP_CTX',
    'STEP_ROW',
    'JOURNEY_KINDS',
    'LANE_KINDS',
    'STEP_ACTS',
    'BIND_KINDS',
    'OUTCOME_KINDS',
    'OUTCOME_VOICES',
    'SITE_STATUS',
    'DISPOSITIONS',
    'ROW_STATES',
    'READ_STATES',
    'JOURNEY_STATES',
    'RULING_STATUS',
    'JOURNEY_ID',
    'SUB_ID',
    'STEP_N',
    'EDGE_ID',
    'LANE_ID',
    'BACKLOG_ID',
    'SAME_AS',
    'SYMBOL',
    'TEST_REF',
    'STEP_REF',
    'RULING_ID',
    'LEDGER_ACTIONS',
]
