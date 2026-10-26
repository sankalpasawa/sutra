"""layers/root/v1.py -- Root, version 1: the implementation behind the interface's root entries (PRD A1.18, W1-ROOT).

Its recipe is the Library's Setup template (engine-templates/setup.json), which A1 does not move, named here by
RECIPE_TEMPLATE. Every code, prompt, draft and check name Setup's steps use is provided here, by reference to the body
in engine_runtime that has not moved (the strangler, A1-D5): a body moves into this file only when it is changed.

What Root's words are, typed (A1.16): WORDS holds the default of each owner field and LAYOUT the template that arranges
them, for the two parts Setup's agent reads, root.setup.converse (the owner's task, the examples and the conversation so
far) and root.setup.shape (the department's name, kind, goal and done-when items). Root's answer contracts are the
interface's (layer_schema.PROMPTS), compiled in verbatim; the owner cannot change them. The words are the inline
builders' (p_setup_converse and p_setup_shape) byte for byte, which test_fixtures/root-prompts.snapshot.json proves.

standards() is what GET /layers shows of Root's standards (S18, read only); apply_option() applies the one option Root
applies in wave 1, root_setup. Root has no pane of its own: Adaptation's view carries Root's check.
"""
from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'root'
VERSION = 1
IMPLEMENTS = 1
RECIPE_TEMPLATE = 'Setup'

#: Setup's instruction to its converse agent when the Library's template says none of its own (the template's
#: converse_instruction, when set, is read in its place: engine_runtime.p_setup_converse)
CONVERSE = ("You are Sutra, the helper of the organisation. The owner wants a department. Ask what you need to know, one question at a "
            "time, until you can confidently create it: what it is for, for whom, and what it must deliver first. Ask only what "
            "the owner has not already said; never ask the same thing twice; one short question, no list. When you could create "
            "the department from what was said, say clear. Three or four questions are plenty: after that, say clear and decide.")

# Setup's steps, by reference: setup.read, setup.converse, setup.say, setup.shape, setup.make, setup.file
CODE = {'setup_read': ref_to('setup_read'), 'setup_say': ref_to('setup_say'), 'setup_make': ref_to('setup_make'),
        'setup_file': ref_to('setup_file')}
PROMPT = {'setup_converse': ref_to('p_setup_converse'), 'setup_shape': ref_to('p_setup_shape')}
DRAFT = {'setup_converse_draft': ref_to('d_setup_converse'), 'setup_shape_draft': ref_to('d_setup_shape')}
CHECK = {'facts_are_closed': ref_to('c_facts_are_closed'), 'said_what_it_did': ref_to('c_said_what_it_did'),
         'setup_converse_is_valid': ref_to('c_setup_converse_is_valid'), 'department_is_shaped': ref_to('c_department_is_shaped'),
         'department_is_made': ref_to('c_department_is_made'), 'filed_has_files': ref_to('c_filed_has_files')}

WORDS = {'setup': {'converse': {'task': CONVERSE}, 'shape': {}}}
LAYOUT = {'setup': {
    'converse': ("{task}\n\n"
                 "QUESTIONS OF THE KIND YOU MAY ASK (examples, not a list to walk): {{examples}}\n"
                 "WHAT THE LIBRARY CAN BUILD: {{library}}\n"
                 "DEPARTMENTS THIS ORGANISATION ALREADY HAS: {{existing}}\n\n"
                 "THE CONVERSATION SO FAR:\n{{conversation}}\n\n"
                 "{returns}"),
    'shape': ("The owner of {{org}} asks Root for a department. Shape it: a short name (the organisation's name and what it is, like "
              "\"{{org}} Website\"; a NEW department takes a name none of the existing ones has, say \"{{org}} Website 2\" or what sets it apart; "
              "when the owner gave the department a name, that name is its name, exactly as given), "
              "its kind from the Library (the kind whose use case fits the words; default when none does), and its goal in one or two "
              "sentences in the owner's own words.\n"
              "THE OWNER'S WORDS: {{words}}\nTHE NAME THE OWNER GAVE: {{named}}\nKINDS IN THE LIBRARY: {{kinds}}\nEACH KIND'S USE CASE: {{use_cases}}\n"
              "DEPARTMENTS THIS ROOT ALREADY HAS: {{existing}}\n\n"
              "If the words describe MORE THAN ONE department, shape only the first: its goal covers only that one, and `second` "
              "holds, in the owner's words, what the other department is for. Otherwise `second` is an empty string.\n"
              "Draft its done-when as items: each one line that must be true when the department is done, from the owner's words "
              "and nothing else, with how it is checked (code: a program can check it on what was made; model: an AI reads what "
              "was made; person: only the owner can say) and its level (target: something the work must have; outcome: something "
              "it must achieve). An item that rests on a fact the owner did not give says why in confirm; else confirm is \"\".\n"
              "{returns}"),
}}


def standards():
    """Root's standards as GET /layers shows them (S18, read only): [{id, says, sources, stages}], in the order they run."""
    return [{'id': sid, 'says': says, 'sources': list(sources), 'stages': list(stages)} for sid, says, sources, stages in S.WORKFLOW_STANDARDS]


def apply_option(ref, ask, option):
    """The owner chose 'set the department up again, done its own way' (root_setup, option.words {words}): the words go to
    the organisation's Root department as one request, '<the words>, done its own way', which Root's Identity takes as it
    takes the owner's words at the front door, for the owner's stamp. That request is all: no key of any department
    changes, no ask is touched and no engine is made (Root never creates or starts an engine, S-10). Returns
    {root, request, text}."""
    option = option if isinstance(option, dict) else {}
    words = " ".join(str(((option.get('params') or {}).get('words')) or ((ask or {}).get('chosen') or {}).get('words') or '').split())
    if not words:
        raise ValueError("say what the department is for")
    d = W.dept(ref)
    if not d:
        raise ValueError("no department at %s" % ref)
    root = ref if d.get('kind') == 'root' else d.get('root')
    if not root or not W.dept(root):
        raise ValueError("%s has no Root to set it up again" % (d.get('name') or ref))
    text = "%s, done its own way" % words.rstrip('. ')
    rq, _ = R.request(root, text, about=None if root == ref else ref)
    return {'root': root, 'request': rq['id'], 'text': text}
