# layer_models: the interface as pydantic

| Field | Value |
|---|---|
| **status** | Final (PRD amendment A4, [design/PRD-FIVE-FUNCTIONS-A4.md](../design/PRD-FIVE-FUNCTIONS-A4.md)) |
| Public face | `layer_schema.py`, unchanged: `validate`, `check`, `describe`, `json_schemas`, `expect_refused`, `DEFS`, `SchemaFault`, `MODE`. Nothing that calls it changed |
| Frozen | `INTERFACE_SHA[1]` and `CORPUS_SHA`: A4 changes no byte of `describe()` (A4.3.8). Never edit a generated file by hand: run `python layer_schema.py --write` |
| Imports | only pydantic (pinned `==2.13.5`), the standard library, `layer_consts` and itself. Anything that needs the app imports it inside the function |
| Switch | `layer_schema.VALIDATOR`, a code constant (`'models'` or `'walker'`); never an environment variable |

## Layout

One line for each module.

| Module | What it holds |
|---|---|
| `acts.py` | The board's acts and their payloads (A1.13, A1.13b). Every payload is open: unknown keys pass, only the fields named are typed |
| `adaptation.py` | Adaptation's records (A1.9): an idea, a step's ladder and a round |
| `audit.py` | Audit's records (A1.13b): a reading, its items, a finding and a spot check |
| `base.py` | The base classes of every model: SutraModel, Closed, Open and Mixin (A4.4.1) |
| `bus.py` | The revision counter a model edit bumps and the stream reads (A4.7.4): one integer, and the last keys that moved |
| `common.py` | The names, the envelope, the option and the verdict every layer shares (A1.5), and the helpers the other modules write their fields with |
| `compile.py` | A spec is data; a class is made from it here, and nothing else is ever run (A4.5.4, A4.5.8) |
| `coordination.py` | Coordination's records (A1.11): the slot, what is left out, the table and the question between engines |
| `defs.py` | Every definition of the interface, registered (A4.3.1): the classes of the layer modules under the names layer_schema.DEFS has |
| `department.py` | The department record (dept.json) and who owns each key (A1.6). Only the keys a save changes are checked (A1.20) |
| `faults.py` | The sentences: ValidationError.errors() translated into the lines layer_schema.faults() writes (A4.3.3) |
| `fields.py` | The prompt fields and the owner's values (A1.16) |
| `frames.py` | The frames the app sends, as models (A4.7.3): a contract, and the two frames A4 adds |
| `graph.py` | The map of the owner's models (A4.6.4): who extends whom, who holds whom and who points at whom, as nodes, edges and the same |
| `hooks.py` | Where an owner's model is accepted (A4.5.7): five core definitions take a `model` key, and a template's filings are held to it |
| `identity.py` | Identity's records (A1.6, A1.8): the done-when item, the rule and the ask |
| `impact.py` | What a change to a model would touch, read and written nowhere (A4.6.5 `preview`) |
| `journey.py` | The user-journey template (A3.6): a journey file and its parts, and the status document computed for each |
| `legacy.py` | The oracle: the 130 definitions as layer_schema.py wrote them as literals, and the walker that judges a value against one |
| `options.py` | The parameters of the ways out an ask offers (A1.15) |
| `owner_base.py` | The core base of a standalone owner record: an open object with an id. A4-PORT's definitions may register their own `record`; |
| `owner_rules.py` | The rules an owner's set of models is held to at save and at load (A4.5.5, R6 to R12). They read the specs (dicts, already |
| `priority.py` | Priority's records (A1.13b): the estimate, the price and the ceiling |
| `registry.py` | What is registered: definition names to classes (or to the annotation of a non-class definition), the bodies of named |
| `root.py` | Root's records (A1.6, A1.7): the pins and the born engine template |
| `rules.py` | The class rules (A4.4.2), checked on the classes themselves: a core class when it is made (SutraModel.__pydantic_init_subclass__ |
| `schema.py` | The JSON Schema export (A4.3.6): the dict layer_schema.DEFS holds for a class, key for key |
| `settings.py` | The settings (A1.8 to A1.12) |
| `spec.py` | The spec of an owner-defined model (A4.5.2): data that says what a model holds. A spec is itself a core definition, so a hand-edited |
| `store.py` | Where the owner's models are kept, and how they change (A4.5.3, A4.6.3) |
| `stream.py` | Validating a streamed answer as it arrives (A4.7.5), and keeping a large value from holding the loop (STR-6) |
| `templates.py` | The templates of the levels below the journey (A3.3, A3.5): the step with its row and start, the kind, the engine and the artifact |
| `types.py` | The interface's scalars and containers as annotation objects (A4.3.2). Each is ONE object that carries both the check and the |
| `unions.py` | The families of the interface, as discriminated unions (A4.4, rule R8) |
| `views.py` | The pane views (A1.17): the read models already merged; later steps add fields, never rename them |
| `workflow.py` | The one workflow schema (A1.14): its engines, checks and registration |

## The twelve rules

Each rule is held where the last column says, and proved by the tests named (`test_layer_models_rules.py` unless the test says otherwise in its file: `core`, `port`, `owner`).

| Id | Rule | In short | Test | Held in |
|---|---|---|---|---|
| **R1** | Inherit | A child has every field of every base it names | `test_r1_a_child_keeps_every_field_of_its_base` | rules.py |
| **R2** | Narrow, never loosen | a child field is as tight or tighter than the base field | `test_r2_one_loosening_each`, `test_r2_a_tighter_child_is_allowed` | rules.py |
| **R3** | Substitute | what a child takes, its base takes (the proof by run) | `test_r3_a_value_the_child_takes_the_base_takes` | rules.py |
| **R4** | Abstract | an abstract class is never made and is not a leaf of the registry | `test_r4_an_abstract_class_is_never_made` | base.py, registry.py |
| **R5** | Mixins | two bases that disagree on a field are refused; a mixin is never a definition | `test_r5_two_bases_that_disagree_on_a_field_are_refused`, `test_r5_a_mixin_is_never_a_definition` | rules.py |
| **R6** | Nest, never in a circle | the nest graph has no cycle and is at most 4 deep | `test_r6_a_nest_cycle_is_found_and_named`, `test_r6_depth_counts_the_models_on_the_longest_path` | rules.py, owner_rules.py |
| **R7** | Refer by id | a link holds the target's id; a dangling one is reported, not raised | `test_r6_to_r12_each_have_their_failing_example` | owner_rules.py |
| **R8** | Polymorphism by tag | a family is an abstract base, a tag and its children; an unknown tag reads as a list | `test_r8_ask_form_adds_no_rejection`, `test_r6_to_r12_each_have_their_failing_example` | unions.py |
| **R9** | On and off | a model is effectively on when its switch and its base's are on; off is not offered and not broken | `test_r6_to_r12_each_have_their_failing_example` | owner_rules.py, compile.py |
| **R10** | Versions | version N+1 is a child of version N | `test_r10_a_new_version_is_a_child_of_the_last`, `test_r10_a_change_in_place_that_loosens_is_not_in_place` | owner_rules.py, store.py |
| **R11** | Names and the vocabulary | names have a fixed shape and are never reused; the vocabulary is closed | `test_r11_names_and_vocabulary` | owner_rules.py, spec.py |
| **R12** | The core is not the owner's | a spec cannot edit, shadow or reach into the core | `test_r12_the_core_is_not_the_owners` | owner_rules.py, hooks.py |

## Add a definition (core)

1. Write the class in the layer's module (`identity.py`, `root.py` and so on), required fields first in the interface's order, on `Closed` or `Open`; use the annotation objects of `types.py`, which carry both the check and the JSON Schema.
2. Register it in `defs.py` under the name `layer_schema.DEFS` has for it (a class name that clashes with a Python keyword or a `BaseModel` name takes another class name and keeps the definition's name in the registry).
3. Run `python qa/a4_equiv.py --check --only <name>`: the same verdict, the same sentences in the same order, the same JSON Schema as the walker. Add its good and failing example to `CONTRACT_SAMPLES`.
4. A change to the interface after schema version 1 is schema version 2 with a migration (A1.21). `test_x2_the_interface_is_frozen_at_schema_version_1` says so.

## Run the proof

| Command | What it does |
|---|---|
| `python qa/a4_equiv.py --check [--fuzz N] [--only NAMES]` | the port against the oracle on the samples, mutants, the writers' output and seeded fuzz; zero differences or it exits 1 (the nightly size is `--fuzz 5000`) |
| `python qa/a4_equiv.py --record DIR [pytest files]` | record what the suite validates, to `DIR/<definition>.jsonl` |
| `python qa/a4_equiv.py --write-golden [DIR]` | write the golden corpus and `CORPUS.sha` from the oracle |
| `python qa/a4_equiv.py --bench` | the port against the oracle on each definition's good sample |
| `python qa/stream_bench.py --check` | the streaming gate: the streams are not slower, later or heavier |

## Core and the owner's

The core is hard-coded: the modules above, registered in `defs.py`. The owner's models are data (`spec.py`), compiled with `create_model` on a core base (`compile.py`), held to the same twelve rules at save and at load (`owner_rules.py`), and accepted only at the places `hooks.py` names. A spec cannot name a core model as the one it edits.

Where they are kept: `<records home>/_models/models.json` (the models), `history.jsonl` (one line for each change, append only) and `pending.json` (changes that let in more, waiting for the owner's stamp). `store.py` is the only writer; the Models routes are in `models_api.py` and the screens in `static/js/26-models.js`.

## Add an extension point

An extension point is a core definition that takes a `model` key naming an owner-defined child. Add its name and the path to the value to `HOOKS` in `hooks.py`, make the core class `__extensible__` so a spec may name it as a base, and add a failing example to `test_layer_models_hooks.py`. The owner's child is held to the base by R1 to R3, so the extension point never accepts more than the core does.

## Streaming

No stream producer builds an adapter, compiles a model or validates inside its body (A4.7.2). Adapters are built once, `bus.revision()` is the one call a stream makes, and `qa/stream_bench.py --check` keeps it so.
