# Library: the Interface library (closed models, registry, write gate)

_Section of docs/DESIGN.md · architect: library · 2026-11-04 · status: proposed; the settlements S2-models, S3-web and S4-fnodes (docs/design/settlements/, binding) are applied in place, and a paragraph, table row or code block they changed carries the settlement id in square brackets (grep for S2-models-, S3-web- or S4-fnodes-). Respects D3 (closed pydantic v2), D4 (engine vendored and adapted in place), D5 (SQLite + files), D6, D8. Proposals DL1 to DL10 are in section 16; the consolidator assigns the D-numbers (from D13)._

**Tags.** `GEN:n` /private/tmp/claude-501/arch/gen.py line n (box "Interface library (Python models)" = GEN:109-117) · `DRW` draw.io page 3 (list: Identity, Adaptation, Priority, Coordination, Audit, Departments, Goal, Evaluation) · `DEC` docs/DECISIONS.md · `J2:n` J2_Prototype/j2.py · `JM:n` j2_artifact_models.py · `JR:n` j2_rules.py · `JS:n` j2_schema.py · `JT:n` j2_template_lib.py · `JZ:n` j2_realization.py · `AS` docs/atom-schema.md/.json · `MAP` docs/map-schema.md · `RS` docs/realization-schema.json · `ROLE:x` agents/j2/x.md · `SA:n` plugin bin/sutra-atom · `HK:n` plugin hooks/atom-cards-stop-check.sh · `ADR-n` plugin os/canon/decisions. `[U]` = could not be verified.
**The function-node spec is final** (`docs/design/function-nodes-spec.json`; the one design built on it is `docs/design/function-nodes.md`, which wins where it names a superseded id); section 8.4 is the interface it plugs into. [S2-models-08] [S4-fnodes-01]

**Notation.** `S(a,b)` = str of a..b chars after strip · `int≥k` · `[T]≤n` = list of at most n · `T?` = `T` or `None` · `Ts` = int ≥ 0, epoch seconds (SA:276) · in tables `a/b/c` inside `Literal[...]` is a choice. Every class is frozen, strict and `extra="forbid"` (3.1). `V:` lines are model validators; a validator reports every violation it finds, not only the first. The core mechanics (strict models, family registry, gate, parser, transport schema, org chart and chart change, atom lifecycle, goal, evaluation, function replies, node, edge, workflow) and `carry_links`/`check_graph` were prototyped and run on pydantic 2.14.2 / Python 3.11 in a scratch directory; every rejection listed in section 14 was observed there or on J2's own code, unless marked `[U]` or tagged with a settlement id (such rows were added or changed after the prototype run and count as `[U]` until their test runs). Not prototyped: `atom_view`, `to_j2/from_j2`, the template port, `gate_record`, the router, `FunctionSpecs` (their tests are written to J2 parity).

## 1. Purpose and scope

The library is the one place where the app's structures are defined, validated, versioned and registered. Anything stored, pushed over SSE, returned by an API or asked of a model is an instance of a class here (GEN:109-117, D3).

In scope:
- the closed base classes; the registry (register, lookup by name and version, JSON-schema export); the **one write gate** every store uses;
- the models of the draw.io list (Identity, Adaptation, Priority, Coordination, Audit, Departments, Goal, Evaluation) plus Org chart, Chart change and the Workflow / Step / Template bases (DRW, GEN:109-117);
- the Atom (the plugin's behaviour: goal, constraints, context, work, verify, lifecycle, ledger row) and the Node family (a Node base with five function-node children), with the code names `FunctionNode` (children `IdentityNode`, `AdaptationNode`, `PriorityNode`, `CoordinationNode`, `AuditNode`), `Atom` and `AtomView`; the function-node spec's AgentNode, WorkAtom and BuilderAtom are prose names for these (docs/design/function-nodes.md section 2.1) [S4-fnodes-01];
- the port of J2's artifact models and rules ("pydantic shape + rules", GEN:151) with the pure helpers J2 keeps beside them;
- a catalogue that maps every J2 run-folder file to a model, and the hook that checks it on `save()`.

Out of scope (other sections own them, but what they persist must subclass `Record` and register): SQL execution and HTTP routes (stores, server); the connector layer (`ModelConnector`, usage and cost records, call log); chat sessions and messages (the orchestrator owns `chat_session`, `chat_message`, `usage_record` and `work_task`; the library owns only J2's `run_message` line and `MessageMeta`, section 10) [S2-models-15]; SSE envelopes; engine control flow (turn routing, bargain, retries); the UI. The library does no I/O except `export` and `write_generic` (both write under `docs/schemas/`, which is never read at runtime [S3-web-08]) and the function-spec loader (reads one JSON file). It makes no model call and reads no clock (callers pass `now`).

## 2. Module map (under `sutra_app/library/` unless noted; tests are listed in section 14)

| Path | Responsibility | WP |
|---|---|---|
| `__init__.py` | docstring only; importing a module registers its classes | L1 |
| `types.py` `base.py` | scalars, id patterns, `FUNCTIONS`, `Violation`, the atom id helpers `atom_sid`, `function_atom_id`, `overhead_atom_id`; `Value`, `Record`, `evolve`, `canonical_json` [S2-models-10] [S4-fnodes-07] | L1 |
| `registry.py` | `ModelRegistry`, `REGISTRY`, `transport_schema`, `reply_schema`, `is_transport_safe` | L1 |
| `gate.py` | `Gate`, `Checked`, `GateError`, `GateContext`, `CrossRule`, shipped cross rules | L1 |
| `replies.py` | `ReplyParser`, `ReplyInvalid`, `normalise_enums` (tolerant in, closed out); `extract_json`, `close_json` (the one copy: `engine/llm.py` re-exports them, `connectors/jsonio.py` imports them) [S2-models-12] | L1 |
| `export.py` | `python -m sutra_app.library.export [--check]` writes or diffs `docs/schemas/` | L1 |
| `org_chart.py` | `OrgNode`, `OrgEdge`, `OrgChart`, `NewNode`, the five ops (`SplitOp.moves` is a list of `ChildMove`), `ChartChangeRequest`, `ChartChange`, `derive_kind`, `apply_change`, `slug_id`, `carry_links`, `seed_chart` [S2-models-04] | L2 |
| `goal.py` `department.py` `evaluation.py` | `Question`, goal drafts, `SiteGoal`/`DocGoal`; `Department` (id, home_dir, ts_created); `Finding`, `RubricResult`, evaluation kinds [S2-models-14] | L3 |
| `chat.py` | `MessageMeta` (the closed key set of J2 chat meta, open values), `RunMessage` (payload `run_message`: J2's chat.jsonl line) [S2-models-15] | L3 |
| `atom.py` | `AtomDraft`, `Atom`, `Check`, `Verify`, `Seen`, lifecycle (`open_atom`, `close_atom`, `abandon_atom`), `atom_display_state`, `LedgerRow`, `ledger_row`, `ledger_row_from_view`, `Card`, `AtomView`, `atom_view`; the 26 `CheckTemplate` names [S2-models-06] [S4-fnodes-02] [S4-fnodes-03] [S4-fnodes-08] [S4-fnodes-09] | L4 |
| `workflow.py` `functions.py` | `Resources`, `Envelope`, `Step` (`AIStep`, `CodeStep`, `AssignmentStep`), `Workflow` (`TaskWorkflow`, `DeptWorkflow` with `Proposed` and `Registered`), `to_j2/from_j2`; the five function reply families, `Conflict`, `Lesson`, `Certainty`, `certainty_zone` | L5 |
| `node.py` | `Node` base, `StructuralNode`, `FunctionNode` + 5 children, `GraphEdge`, `HANDOFFS`, `check_graph`, `FunctionSpec(s)` (`TaskKind`, `CheckRef`, `AtomTemplate`), `load_function_specs`, `new_function_node`, `refresh_function_nodes` [S3-web-04] [S4-fnodes-02] [S4-fnodes-14] | L6 |
| `specs/function_specs.json` | the seed `FunctionSpecs` of the five functions (templates with named checks, `yields`, `work_hint`) and the default path of `load_function_specs()` [S2-models-05] [S4-fnodes-02] | L10 |
| `artifacts/{__init__,models,rules,render}.py` `templates.py` | port of `j2_artifact_models`, `j2_rules` (+`RuleSpec`), renderers; the `Template` bases and checks | L7 |
| `records.py` `api.py` `all.py`, `docs/schemas/*.json` | J2 file to family catalogue and `gate_record`; schema router at `/api/schemas` (GETs open, POST validate behind the write guard, ORCH error envelope) [S3-web-03] [S3-web-15]; imports every module (`wire` inside `try/except ModuleNotFoundError` until L9 lands); generated schemas | L8 |
| `wire.py` | J2 wire documents: map/1, board/1, story/1, agent/1, artifacts/1, artifacts-tree/1, realization/1, run summary (with its budget `{start, granted, used, raises}` read from summary.json) [S2-models-14] | L9 |

What the other sections import (the contract; everything else is internal; import `sutra_app.library.all` for the full registry):
| Consumer | Imports | For |
|---|---|---|
| stores (SQLite, files) | `GATE`, `Checked`, `GateError`; `OrgChart`, `apply_change`, `carry_links`; `Atom`, `open_atom`, `close_atom`, `abandon_atom`, `ledger_row`, `ledger_row_from_view`, `atom_display_state`; `Node` family, `GraphEdge`, `check_graph`, `refresh_function_nodes` [S4-fnodes-08] [S4-fnodes-09] [S4-fnodes-14] | every write goes through `GATE.check`; the library computes, the store commits |
| chat agent (orchestrator) | `OrgChart`, `ChartChangeRequest`, `ChartChange`, `TaskWorkflow` and `AssignmentStep`, `MessageMeta`, `REGISTRY.transport_schema`, `ReplyParser`, `FunctionSpecs` [S2-models-13] [S2-models-15] | read the chart, ask for a change, build workflows (flow steps 1 to 3) |
| connector layer | `REGISTRY.transport_schema(family, kind=...)` as the `schema` argument of `call_json` (GEN:170); `ReplyParser` on the returned text; `extract_json`, `close_json` (`connectors/jsonio.py` imports them) [S2-models-12] | structured JSON from Claude or Codex; the connector knows no model class |
| engine (vendored J2) | `gate_record`; `extract_json`, `close_json` (`engine/llm.py` re-exports them); the function reply families, `ReplyParser`, `RegisteredWorkflow`; for the function-node layer: `FunctionSpecs`, the `Atom` lifecycle with `Seen`, `atom_sid`, `function_atom_id`, `overhead_atom_id` [S2-models-12] [S4-fnodes-03] [S4-fnodes-07] | validate J2's dicts on `save()`; one copy of `extract_json`/`close_json`; the library owns the artifact models, rules, template checks and `certainty_zone`, and the engine keeps its vendored copies of them as the runtime copy, bound to the library by `test_lib_engine_parity.py` until the switch of S2-models-12 |
| server and UI | `api.py` router, `AtomView` and the wire documents, `DomainEvent` | schema endpoints (GETs open, POST validate guarded), J2 views unchanged, SSE payloads [S3-web-03] |

Import direction: the library imports nothing from engine, connectors, orchestrator or ui; they import the library and define none of its models. [S2-models-12]

## 3. Foundations

### 3.1 Tiers and rules
```
Value    closed object without identity fields (nested parts)
Record   Value + kind + schema_version: a stored or sent document; kind is the discriminator inside a FAMILY (a registry name)
Payload  a Value registered under (name, version) with no identity fields (J2 artifact sections, J2 wire documents)
```
```python
class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True,
                              validate_by_name=True, validate_by_alias=True, serialize_by_alias=True)
class Record(Value):
    FAMILY: ClassVar[str]; VERSION: ClassVar[int] = 1; ABSTRACT: ClassVar[bool] = False
    kind: str                  # a concrete class narrows it to Literal[...] with a default (one or several kinds)
    schema_version: int = 1    # V: == VERSION
    def evolve(self, **changes) -> Self   # model_validate({**dump, **changes}); the ONLY update path (model_copy(update=) skips validation)
    def canonical_json(self) -> str       # dump(mode="json"), sort_keys, separators (",",":"), ensure_ascii=False
```
Rules, each tested:
1. No coercion: `"1"`, `1.0`, `true` for an int and `"true"` for a bool are rejected.
2. JSON-native types only (`str int float bool list dict[str,X] Literal None`); never `Enum`, `tuple`, `set`, `datetime`, `UUID` (strict mode refuses them from parsed JSON).
3. Every `str` and `list` is bounded. The numbers in this section (lengths, 500 nodes, depth 6, 1 MiB) are my design parameters, not J2 or plugin facts `[U]`; each is one constant per class.
4. `ABSTRACT = True` is read from the class body (`cls.__dict__`), never inherited (an inherited flag silently unregistered every child in a prototype).
5. Frozen blocks attribute assignment but not `list.append`; stores never mutate fields, and the gate re-validates the serialised form at every write.
6. Needs pydantic ≥ 2.11 (`validate_by_name`, `serialize_by_alias`); pyproject says ≥ 2.8 and must be raised (installed: 2.14.2).
7. A field alias is allowed only where J2's wire key is a Python keyword (`pass`, `from`).

### 3.2 `types.py`
```
Ts = int≥0 · NodeId = ^[a-z][a-z0-9_-]{1,39}$ (no dot: dots belong to function node ids "<dept>.<function>")
FUNCTIONS = ("identity","adaptation","priority","coordination","audit") (J2:100) · FunctionName = Literal[...]
WorkflowId = ^W-\d+$ · AtomId = ^(a-[a-z0-9]{1,16}-\d{2,6}|W-\d+\.a\d+)$ (plugin SA:253 / J2:6679) · ChangeId = ^chg-\d{4,9}$ · Ref = ^\$[a-z][a-z0-9_]{0,15}$ · Target = a NodeId or a Ref
FindingId = ^F-[A-Za-z0-9-]{1,20}$ · EdgeId = "<kind>:<from_id>><to_id>" · JsonObject = dict[str, JsonValue]
function_node_id(dept_id, function) -> "<dept_id>.<function>"   # the ONE place that knows the scheme: FunctionIds, FunctionNode and check_graph call it, so another scheme is a one-line change
atom_sid(run_id, node_id) -> the first 10 hex digits of sha1("<run_id>:<node_id>") · function_atom_id(sid, n) -> "a-" + sid + "-" + n   # n with at least two digits; the only code that builds a function atom id; Atom.session_id holds the sid  [S2-models-10]
overhead_atom_id(owner_ref: str) -> AtomId = function_atom_id(atom_sid(owner_ref, "overhead"), 1)   # owner_ref = the run id or "req-<id>"; the accounting key of a call made outside a function turn; no atoms row, not a third scheme  [S4-fnodes-07]
"W-<n>.a<k>" names a J2 workflow atom, "a-<sid>-<nn>" a function-node atom; no third scheme; the app key of a J2 atom is "<run_id>:<id>" (J2 restarts at W-1 in every run)  [S2-models-10]
Violation(Value): path: str · code: str · message: S(1,300)     # path = pydantic loc joined by ".", union tag first
DomainEvent(Value): type: Literal[chart.changed, atom.transitioned, node.state] · subject_id: str · data: JsonObject · ts: Ts      # section 13
```

### 3.3 Registry (`registry.py`)
```python
class RegistryError(Exception): ...
class ModelRegistry:
    def register(self, cls) -> cls          # @record; one entry per kind in get_args(cls.model_fields["kind"].annotation); skips ABSTRACT
    def register_payload(self, name: str, version: int, cls, *, rules: Sequence[RuleSpec] = ()) -> cls
    def upgrade(self, family: str, from_version: int)   # decorator: fn(payload: dict) -> dict, result is from_version+1; chained on read
    def freeze(self) -> None                # after imports: further register() raises RegistryError("frozen")
    def families(self) -> list[str]; def versions(self, family) -> list[int]; def kinds(self, family, version=None) -> dict[str, type]
    def adapter(self, family, version=None) -> TypeAdapter   # one class: itself; several: Annotated[Union[...], Field(discriminator="kind")]
    def json_schema(self, family, version=None) -> dict      # adapter.json_schema(by_alias=True): 2020-12; families give oneOf + discriminator
    def transport_schema(self, family, kind=None, version=None) -> dict   # 3.5; one concrete class only
    def verify_refs(self) -> list[Violation]                 # every FunctionSpec task_kind (reply_family, each "|" alternative of reply_kind) is registered; every template check name is a CheckTemplate member with a matching argument count (8.4)  [S2-models-06] [S4-fnodes-02]
REGISTRY = ModelRegistry(); record = REGISTRY.register
```
- The same `(family, version, kind)` with a different class raises `RegistryError("duplicate")`.
- Adding a kind to a family is additive (no version bump). Removing or renaming a field, narrowing a type, adding a required field, or tightening a validator so that old data fails is **breaking**: add a class with `VERSION+1`, keep the old class for reading, register an `upgrade`.
- `export` writes `docs/schemas/<family>.v<N>.json` (sorted keys, indent 2) and `docs/schemas/index.json` (`{family: {version: [kinds]}}`). `test_lib_schema_drift` fails on any difference, so a breaking change without a version bump cannot merge.
- J2 wire documents keep J2's `schema: "name/N"` string: `AtomView` is registered as payload `atom_view` v1 and carries `schema: Literal["atom/1"]` (family `atom` is the Atom record).

### 3.4 The write gate (`gate.py`)
```python
class GateError(Exception): family: str; stage: Literal["unknown","size","shape","cross","round_trip"]; violations: list[Violation]
class Checked(Generic[T]):                       # __slots__; constructible only inside gate.py (module-private token), else TypeError
    model: T; family: str; version: int; kind: str; json: str; sha256: str   # json = canonical_json; sha256 of its UTF-8 bytes
class GateContext(Protocol): def get(self, family: str, id: str) -> Value | None
class CrossRule(Protocol): name: str; family: str; kind: str | None; def __call__(self, model, ctx: GateContext) -> list[Violation]
class Gate:
    def __init__(self, registry=REGISTRY, cross_rules: Sequence[CrossRule] = ())
    def check(self, family, payload: Mapping|str|bytes|Value, *, version=None, ctx: GateContext|None = None) -> Checked
GATE = Gate(REGISTRY, SHIPPED_CROSS_RULES)
```
`check`, in order:
1. A `Value` instance is dumped to JSON first, so `model_construct` cannot bypass validation.
2. Unknown family or version: `GateError(unknown)`. Payload over `MAX_PAYLOAD_BYTES = 1_048_576`: `size`.
3. A payload older than the latest `schema_version` runs the `upgrade` chain; no chain: `shape`, code `schema_version`.
4. Strict validation through the family adapter, class validators included: `shape`, every error a `Violation`.
5. Cross rules for the family and kind, only when `ctx` is given: `cross`.
6. Canonical JSON and sha256; then `adapter.validate_json(text) == model`, else `round_trip` (a model whose dump is not valid input is a bug found at its first write).
7. Return `Checked`. The gate writes nothing.

**Stores accept only `Checked`** (`def put(self, c: Checked[OrgChart])`). The SQL `body` column is always `Checked.json`; indexed columns are projections the store computes from `Checked.model`, never from raw input. Stores that must use it (the stores section owns their code): org charts and changes, nodes and edges, chat sessions and messages, atoms and the atom ledger, the usage ledger, department records and J2 run files (through `gate_record`, section 10), template-library files. J2 run files keep J2's own formatting (D5): the gate validates and the canonical text is discarded.
Shipped cross rules: `atom.supersedes_abandoned` (`ctx.get("atom", supersedes).state == "abandoned"`, SA:237-241) · `edge.endpoints_exist` (`ctx.get("node", from_id)` and `to_id`) · `node.department_exists` (`ctx.get("node", department_id)` is a department) · `department.in_chart` (`ctx.get("org_chart", "chart")` holds a department with that id).

### 3.5 Model replies and transport schemas (`replies.py`, `registry.py`)
Principle (DL4): **model output is untrusted and parsed tolerantly; everything stored is closed.**
```python
class ReplyInvalid(Exception): code: Literal["not_json","not_object","shape"]; violations: list[Violation]; retry_text: str
@dataclass(frozen=True) class ParsedReply: model: Value; dropped_keys: list[str]; normalised: list[str]
class ReplyParser:
    def parse(self, family, text: str, *, kind=None, version=None) -> ParsedReply
```
1. Extract the JSON with J2's own `extract_json` and `close_json`, ported into `replies.py` (llm.py:268-295): a fenced block, else the text from the first `{` to the last `}`, and once more with an unfinished string and brackets closed (a reply cut short). This is the one copy: `engine/llm.py` re-exports it and `connectors/jsonio.py` imports it, and the verbatim J2 cases are tested once, in `test_lib_replies.py`. [S2-models-12]
2. Nothing parseable: `ReplyInvalid("not_json")`; JSON that is not an object: `not_object`.
3. `normalise_enums`: every `Literal[str]` field is read case-insensitively and written back in the model's casing (port of `JM:510-529`, which handled only `priority` and `type`).
4. Drop keys the class does not declare, at any depth, and list them in `dropped_keys` (J2 reads replies with `.get`, so extra keys never failed a turn; the engine records a `reply_extra_keys` event).
5. Strict validation. Failure: `ReplyInvalid("shape", violations, retry_text)` with `retry_text = "THE VALIDATOR REJECTED: " + "; ".join(f"{path}: {message}")` (J2 wording, `J2:5972`; `JM:502-507`). The retry budget stays in the engine (J2 gives a builder 3 attempts).

`transport_schema(model)` is the port of `JM:415-457`: draft-07, `$defs` to `definitions`, every object `additionalProperties:false`, all properties required except the class's `TRANSPORT_OPTIONAL` set (artifact payloads: J2's `OPTIONAL_FIELDS`, JM:39-42), no length/pattern/format/default/title, `anyOf [X,null]` folded to a type list. Four changes (the first three observed in the prototype, the first two matter together: `anyOf` needs distinguishable members; the fourth found by running a copy of J2's `_clean` on pydantic 2.14.2) [S2-models-04]:
- **`const` becomes a one-value `enum`**. J2 dropped it: a single-value `Literal` lost its constraint (`act: Literal["GRANT"]` became plain `string`).
- **Unions become `anyOf`**: `oneOf` is rewritten as `anyOf` and `discriminator` is dropped (J2's `_clean` already keeps a non-null `anyOf`); the one-value `enum` on each member's `kind` or `op` keeps the choice unambiguous. A whole family is never sent: the caller names one class (a request class such as `ChartChangeRequest` has a union only inside it). Whether the real CLIs accept `anyOf` of objects is `[U]` until `test_chart_change_request_native` runs (section 17, risk 2); fallback: `ChartOpFlat`, see S2-models-04. [S2-models-04]
- **Recursion is refused** (`transport_recursion`, a `$ref` cycle in `definitions`).
- **A free-key dict is refused** (`transport_dict`, `RegistryError`): a dict with `additionalProperties` given as a schema and no `properties` becomes, in J2's `_clean`, the object `{additionalProperties:false, required:[]}`, which accepts no key (observed); `is_transport_safe` reports it. A model-facing class uses a list of pairs instead (`SplitOp.moves`, section 4). [S2-models-04]

`reply_schema(model, extra_fields)` is ported as is (`JM:460-482`, `reason` first). `is_transport_safe(schema) -> list[str]` is the checker the tests run on every reply class. The connector's `call_json(prompt, tools, schema, timeout)` (GEN:170) receives `REGISTRY.transport_schema(family, kind=...)` as `schema`; whatever object or text comes back is passed to `ReplyParser` (an object is first dumped to JSON), so the connector never knows a model class.

### 3.6 Cross-cutting
- **Errors**: `GateError`, `ChartChangeInvalid`, `ReplyInvalid` carry `violations: list[Violation]`; `RegistryError` is a programming error. HTTP: 422 with violations for the first three, 413 for `size`, 500 for `RegistryError`; bodies use the orchestrator's `{error:{code,message,details}}` envelope (section 13) [S3-web-15]. No bare `ValueError` leaves the library.
- **Logging**: `logging.getLogger("sutra.library")`; DEBUG for dropped keys; WARNING for `log`-mode record rejections; payload bodies are never logged above DEBUG (they hold user text).
- **Config**: `SUTRA_RECORDS=strict|log` (default `log`, read by `gate_record`); `SUTRA_SCHEMA_DIR` (export target, default `docs/schemas`); `SUTRA_TEMPLATES_DIR` (9.2). Nothing else.
- **Security**: every string and list is bounded; payload ≤ 1 MiB; no `eval`, no pickle; ids are slugs (no path separator), so they are safe in file names and URLs; `..` is refused in envelope paths; the ported rules `css_safe` and `html_no_page_tags` keep agent HTML and CSS contained (JR:24-25); a `Violation.message` echoes at most 200 characters of input.
- **Performance**: a 500-node chart validates in O(n·depth); `apply_change` is O(ops·n); adapters are built once and cached.
- **Concurrency**: models are immutable and the functions are pure; the registry is frozen after import. A run is its own process (D9): each process rebuilds the registry on import, and nothing is shared except files and the database. Atomicity of a chart change and "one open atom per node" belong to the store (SQLite write lock, unique index, section 11).

## 4. Org chart and chart changes (`org_chart.py`)

One global chart (owner rule). A chart is a document with a `revision`; a change is a record that produces the next revision. Departments carry their five function nodes by construction.
```
FunctionIds(Value): identity, adaptation, priority, coordination, audit: str      V: five different; for_department(d) -> function_node_id(d, f) for each f
OrgNode(Value): id: NodeId · kind: Literal[root,department,division] · name: S(1,80) · purpose: S(0,300)="" · functions: FunctionIds? · added_in: int≥1 = 1
  V: department => functions == FunctionIds.for_department(id) (always its five); other kinds => functions None
OrgEdge(Value): parent: NodeId · child: NodeId                       # a "contains" edge; the chart is one tree
OrgChart(Record) FAMILY "org_chart", kind "org_chart": revision: int≥1 = 1 · nodes: [OrgNode] 1..500 · edges: [OrgEdge]≤500 · updated_ts: Ts = 0
  before-validator sorts edges by (parent, child), so canonical JSON and sha are stable; nodes keep their order, new nodes are appended in change order
  V1 ids unique · V2 exactly one root (any NodeId), no parent · V3 edge endpoints exist, every non-root has exactly one parent edge
  V4 parent kinds: department under root; division under department or division · V5 no cycle, depth ≤ 6 · V6 function node ids unique across the chart
  helpers: node(id) parent_of(id) children_of(id) subtree(id) department_of(id)           seed_chart(root_id="root", ts=0): revision 1, only the root
```
```
NewNode(Value): ref: Ref · kind: Literal[department,division] · name: S(1,80) · purpose: S(0,300)="" · parent: Target     # Target: an existing NodeId or a Ref added earlier in the same change
AddOp: op="add" · node: NewNode                 MoveOp: op="move" · node: Target · to_parent: Target
RenameOp: op="rename" · node: Target · name: S(1,80)? · purpose: S(0,300)?        V: at least one of name, purpose
MergeOp: op="merge" · into: Target · sources: [Target] 1..4                        SplitOp: op="split" · node: Target · parts: [NewNode] 1..3 · moves: [ChildMove]≤20   # [S2-models-04]
ChildMove(Value): child: Target · to: Target       # replaces the old dict move_children: a free-key dict cannot be a transport field (3.5)  [S2-models-04]
ChartOp = Annotated[Union[AddOp, MoveOp, RenameOp, MergeOp, SplitOp], Field(discriminator="op")]
derive_kind(ops) -> "reuse" if no ops; "add" if every op is an AddOp; else "rearrange"
ChartChangeRequest(Value) (what the chat agent asks the model for; the model never sees ids it must invent): reason: S(1,400) · reuses: [NodeId]≤10 · ops: [ChartOp]≤8
ChartChange(Record, ChartChangeRequest) FAMILY "chart_change", kind: Literal[reuse,add,rearrange]: + id: ChangeId · task_id: S(1,64) (the request id "req-<message id>", S2-models-08 glossary) · base_revision: int≥1 · ts: Ts = 0
  V: kind == derive_kind(ops) (the model's word is never trusted: code sets kind) · reuse => reuses non-empty · each Ref is added once and used only after it is added
ChartChangeResult(Value): chart: OrgChart · ids: dict[Ref, NodeId] · aliases: dict[removed_id, kept_id] · added, moved, merged: [NodeId] · new_function_nodes: [str]
LinkPlan(Value): keep: dict[NodeId, SessionId] · move: dict[SessionId, NodeId] · archive: dict[SessionId, NodeId]
class ChartChangeInvalid(Exception): violations: list[Violation]
apply_change(chart, change, *, new_id: Callable[[kind, name, taken], NodeId] = slug_id) -> ChartChangeResult   # pure; raises ChartChangeInvalid with ALL violations, not the first
slug_id(kind, name, taken) -> NodeId: lowercase slug of the name, "-2", "-3" ... until free; a name that slugs to a Windows device name (con, prn, aux, nul, com1-9, lpt1-9) starts from the kind ("department-con"), because the id is the team's folder (the orchestrator may inject its own generator)
carry_links(links: Mapping[NodeId, SessionId], result) -> LinkPlan        resolve_alias(aliases, node_id) -> NodeId   # follows chains (a merged-away target may itself be merged)
```
Ops run in order on a working copy, so a later op can use a `Ref` an earlier op added (an add and a move in one change is a `rearrange`).
| Rule | Violation code |
|---|---|
| C1 `base_revision != chart.revision`: another request changed the chart, read it again [S2-models-08] | `stale_base` |
| C2 reuse: every id in `reuses` exists; chart and revision unchanged; the attempt is still logged | `unknown_node` |
| C3 add: the parent resolves; its kind is legal (V4); the name is unique among siblings, case and space blind (a clash means "reuse it"); the id comes from `new_id`, so it cannot collide | `unknown_node` `bad_parent_kind` `duplicate_name` |
| C4 move: division only; target not inside the node; target kind legal; no name clash | `move_not_division` `cycle` `bad_parent_kind` `duplicate_name` |
| C5 rename: not the root; no sibling clash | `unknown_node` `duplicate_name` |
| C6 merge: divisions only; sources distinct and not the target; target not inside a source; the sources' children move to the target; sources are removed and recorded in `aliases` | `merge_not_division` `bad_merge` `cycle` |
| C7 split: division only; parts are divisions under the node's own parent; moved children are current children; the targets in `moves` are a part or the node [S2-models-04] | `split_not_division` `bad_split_part` `not_a_child` `bad_target` |
| C8 the result must satisfy V1 to V6 (so a department keeps its five function nodes) | `invariant` |
| C9 a rearrange loses no id except merged sources and never changes a department's function ids | `ids_lost` `functions_changed` |
| C10 an added department gets `functions` filled by code; its five ids go to `new_function_nodes` so the graph store creates the function nodes in the same transaction | n/a |
| C11 chat links: `carry_links` is the only rule (keep, move, archive) and the store executes the plan (orchestrator `ChatStore.apply_links`). A surviving node keeps its session (`keep`); a merged-away node's session moves to the target if the target has none (`move`), else it is archived under the target (`archive`); aliases are followed through chains, in the old chart's node order; no session is ever dropped (prototype: 3 sessions in, 3 placed). In the app every live node has a session, so a merge gives `keep` for the survivor and `archive` for each merged-away node; `move` is tested with a link map that lacks the target [S2-models-11] | n/a |
| C12 refs: a Ref used before it is added, added twice, or a `kind` that disagrees with the ops is rejected by the `ChartChange` model itself, before `apply_change` runs | `value_error` |

Revision grows by 1 for add and rearrange, not for reuse. A department cannot be moved or merged: it owns five agentic nodes, a goal and runs, so only a new design decision may change that (DL5). Example, the first request on an empty chart (the model sends only `reason`, `reuses`, `ops`; code adds `kind`, `id`, `task_id`, `base_revision`, `ts`) [S2-models-08]:
```json
{"kind":"add","schema_version":1,"id":"chg-0001","task_id":"req-17","base_revision":1,"reason":"the brief needs sales and support","reuses":[],"ts":1,
 "ops":[{"op":"add","node":{"ref":"$sales","kind":"department","name":"Sales","purpose":"","parent":"root"}},
        {"op":"add","node":{"ref":"$leads","kind":"division","name":"Leads","purpose":"","parent":"$sales"}}]}
```
Result: `ids {"$sales":"sales","$leads":"leads"}`, revision 2, `new_function_nodes` the five `sales.<function>` ids. The same change with `"base_revision":1` when the chart is at revision 2 gives `[{"path":"","code":"stale_base","message":"change is based on revision 1, chart is at 2: read the chart again"}]`; with `"kind":"rearrange"` it is rejected by the model (`kind is add for these ops, not rearrange`). A department node without `functions` makes `OrgChart` fail with `value_error: a department must carry its five function nodes` at `nodes.1`. A transport schema for `ChartChangeRequest` was 2.3 KB in the prototype (`test_lib_chart_transport.py` pins it under 4 KB). [S2-models-04]

## 5. Goal, Department, Evaluation

```
Question(Value): question: S(1,400) · options: [S(1,300)]≤4 = []                                   (J2:4027-4029)
TbcAnswer(Value): item: int≥1 · fact: S(1,300)      ToBeConfirmed(Value): criterion: S(1,400) · fact: S(1,300)   (stored form, J2:4155-4165)
GoalDraft(Value) (what Identity returns, CHARTER_FMT J2:3544-3557): statement: S(1,600) · audience: str = "" · standards, rules: [S(1,300)]≤30
  · done_when: [S(1,400)] 1..40 · core: [bool] · to_be_confirmed: [TbcAnswer] · dropped_from_brief: [str] · facts: [S(1,300)]≤60
  V: core empty or one flag per done_when item · done_when items differ · to_be_confirmed.item <= len(done_when)
SiteGoalDraft(GoalDraft): kind "site" · site_name: S(1,120) · business_type: str = "" · visitor_needs: [str]
DocGoalDraft(GoalDraft): kind "doc" · product_name: S(1,120) · users, problem: str = "" · features, constraints, success_measures: [str]
  · user_groups: [{name: S(1,120), actions: [S]}]                                                 (PRD_CHARTER_FMT J2:2258-2263)
SiteGoal(Record, SiteGoalDraft) / DocGoal(Record, DocGoalDraft) FAMILY "goal", kinds site/doc: the stored charter; to_be_confirmed becomes [ToBeConfirmed]
  + charter_items, core_items, dropped_by_requester, requester_answers: [str] · dropped_reasons: [{criterion, reason}] · confirmed_facts: [ToBeConfirmed]   (code-written keys, J2:3781-3783, 4114-4119, 4448, 4479)
  V: to_be_confirmed.criterion is in done_when · dropped_by_requester items were once charter items
Department(Record) FAMILY "department": id: NodeId (= the OrgNode id) · home_dir: S(1,200) ("departments/<id>", relative to the data dir) · ts_created: Ts      # [S2-models-14]
  Name and purpose are read from the chart (their one owner is OrgChart), the charter is the run folder's goal.json (family goal), runs are the tasks table, the budget is the run summary (wire.py, L9: {start, granted, used, raises}).   # [S2-models-14]
```
`Evaluation` is a judgement of a subject against a Goal (DRW "Evaluation"); `FAMILY "evaluation"`; the vocabulary is J2's.
```
Finding(Value) (the stored audit row, J2:8864-8909): id: FindingId · item: int≥0? · criterion: str · verdict: Literal[PASS,PASS_WITH_WARNING,NEEDS_REVISION,BLOCKED_BY_EVIDENCE,POLICY_CONCERN,TO_BE_CONFIRMED]
  · severity: Literal[low,medium,high,critical]? · confidence: Literal[low,medium,high]? · note: S(0,1000) · needs_requester_fact: str? · passed: bool (alias "pass") · audit_id: str?
  V: PASS and PASS_WITH_WARNING need a non-empty note (audit.md, J2:9068) · passed is true exactly for those two verdicts
RubricResult(Value): id: ^[RD]-\d+$ · verdict: Literal[PASS,PASS_WITH_WARNING,NEEDS_REVISION] · note: str · passed: bool (alias "pass")
ConditionResult(Value): id: ^[A-Z]\d+$ · met: bool · evidence: str · severity: Literal[warn]?
ResultEvaluation kind "result" (= the J2 audit entry, J2:8959-8962): cycle, version: int≥1 · results: [Finding]≥1 · extra_issues: [Finding] · rubric: [RubricResult]
  · conditions: [ConditionResult] · mechanical: JsonObject (opaque, owned by j2_check) · screenshot: str? · all_pass: bool · accepted: [str]
  V: finding ids unique · all_pass == (all results passed, all rubric passed, no unmet non-warn condition): the stored flag may not lie
RecheckEvaluation kind "recheck" (J2:7928-7935): trigger: str · doc: str · version: int · t: str · results: [{atom, check, pass, evidence}]
PlanEvaluation kind "plan" (confidence judge: ROLE:confidence-judge, JZ:24-50, 276-306): workflow: S · round: int 0..3 · score: float 0..1 · passed: bool
  · answers: dict[QuestionId, {answer: Literal[yes,no,n/a], note: str}] · weakest: Literal[inputs,method,done_test,factors,zone_fit,size,fits]     V: passed == (score >= 0.80)
RunReview kind "run" (REVIEW_FMT J2:9310-9312): verdict: S · agents: dict[str, {score: int 1..5, note: str}] · went_well, problems, learnings: [S]
```

## 6. The five function models (`functions.py`)

Each function has a **family** named after it. Each turn J2 asks of it is a **kind**, one class, because a transport schema is per class (3.5). Every reply class carries `say: str = ""` and `reason: str = ""` (J2 builders put `reason` first) and a `next` limited as shown (J2 `next_field`). Fields and rules come from the J2 reply formats cited per row. Other J2 turns (`question`, `send_confirm`, `ruling_budget`, `limit`) reuse these shapes; adding a kind is additive.

| Family kind | Fields (beyond say, reason) | Validators |
|---|---|---|
| identity `intake` (J2:4027-4032; ROLE:identity) | enough: bool · questions: [Question]≤4 · goal: SiteGoalDraft or DocGoalDraft? · to_requester, to_agents: S(0,600) · next: Requester/Adaptation | enough => goal, no questions, next Adaptation; not enough => 1..4 questions, no goal, next Requester (J2:4042-4045) |
| identity `ruling` (J2:4206-4213) | clause: S(1,300) · facts: [S] · resolved: bool · ruling: S? (one of the two parties, or "split" for a proposal) · workflows: [S] · instruction: S · user_question: Question? | resolved => ruling set; not resolved => user_question with ≥ 2 options and no ruling; split => workflows non-empty |
| identity `heard` (J2:4396-4402, DECISION_FMT J2:1508) | clause · decision: Literal[continue,drop,ship,stop]? · add: int≥0? · drop_items: [int≥1] · confirmed, still_to_be_confirmed: [TbcAnswer] · instruction_to_adaptation: S? · next: Audit/Adaptation | ranges only (J2 applies `add` unless the decision is ship, J2:4484) |
| identity `done` (J2:4892-4896, 1504-1506) | clause · done, needs_requester: bool · requester_questions: [S] · instruction_to_adaptation: S? · needs_decision: bool · budget_needed: int≥0? · next: Requester/Adaptation | next is Requester exactly when done or needs_requester |
| identity `approval` (J2:4317) / `approval_ask` (J2:4329) | approved: bool · budget_increase: int≥0? / clause · decision: Literal[DENY,ASK] · user_question: Question? | ranges only (J2 uses `budget_increase` only when approved; its mock sends ASK with no question, J2:4334-4335) |
| adaptation `propose` (J2:5396-5402; ROLE:adaptation) | act: Literal[PROPOSE,POLICY_QUESTION,DISPUTE] · workflows: [ProposedWorkflow]≤20 · left_out: [{item: int≥1, reason: S}] · question: S? · dispute: {with: Audit/Coordination, about, reason}? · playbook_used, playbook_changes, lesson_used: S? · certainty_assessment: Certainty? · analysis: {options: [S], chosen: S, why: S, assumptions: [S]}? · deferred: [{item: S, until: S}] · realization fields (9.4) · next: Priority/Identity/Audit/Coordination | PROPOSE => workflows non-empty; POLICY_QUESTION => question; DISPUTE => dispute; certainty zone analyze => analysis; zone experiment => 1..3 workflows whose `certainty` is experiment, each with hypothesis, signal, fails_if, limit (JZ:94-135) |
| adaptation `respond` (J2:6285-6288) | act: Literal[ACCEPT,REVISE,PARK] · workflows: [ProposedWorkflow] · next: Priority/Identity | REVISE => workflows non-empty; ACCEPT and PARK => empty |
| adaptation `atom_verdict` (J2:8802-8806) | verdict: Literal[CHECK_WRONG,BUILD_WRONG] · atom: AtomId · verification: [Check] · affordable: bool? · build_wrong_reason: S? | CHECK_WRONG => verification; BUILD_WRONG => affordable and reason |
| adaptation `lesson` (J2:9287-9300) | lessons: [{problem: S, cause: S = "", fix: S}]≤10 | stored `Lesson`: + id `L-<run>-<n>`, run, cycle, versions [int,int], workflows [WorkflowId], t, output?, test?, mock? |
| priority `price` (J2:6470-6471, 5190-5191, 6476-6481) | decision: Literal[GRANT,COUNTER,REFUSE] · workflows: [ProposedWorkflow with envelope] · next: Adaptation/Identity | REFUSE => no workflows; GRANT and COUNTER => ≥ 1, each with `envelope.money_limit ≥ 1` (J2:6397) |
| priority `envelope_check` (J2:6920-6921) | decision: Literal[HOLD,REQUEST_APPROVAL] · next: Coordination/Identity | HOLD <=> next Coordination |
| coordination `schedule` (J2:6838-6841, 6854-6855; ROLE:coordination) | rule: S(1,300) · order: [WorkflowId] · holds: [{id, missing: S(1,300)}] · next: Priority/Adaptation | order and hold ids unique; rule non-empty (ordering without a stated rule is a failure pattern, ROLE:coordination); next Adaptation only when every ordered workflow is held |
| audit `report` (J2:9062-9072, 9128-9136; ROLE:audit) | read: S? (documents) · findings: [FindingRow] · rubric: [{id, verdict, evidence}] · next: Identity | row ids unique; a PASS row needs evidence; `FindingRow` = id, item: int?, criterion, verdict (5 values), severity, confidence, evidence, needs_requester_fact |

```
Envelope(Value): money_limit: int≥0 · model_call_limit: int≥0 = 2 · time_limit_minutes: int≥0 = 10 · retry_limit: int≥0 = 1 · stop_loss: S(0,300)    (J2:5190, 166)
  ROLE:priority also lists proposal_id and valid_until; J2 code has neither, so they are omitted [U].
Certainty(Value): zone: Literal[operate,analyze,experiment,stabilize] · rationale: S · signals: {broken, reaction, facts_given, known_pattern, open_choices: {answer: Literal[yes,no,unknown], evidence: str}} (all five)
  V: zone == certainty_zone(signals) ("your signals give X by the Certainty rule, but zone says Y", JZ:103-107)
certainty_zone(signals) -> zone: the pure rule ported from JZ:77-92; the library owns the definition and the engine keeps `j2_realization.certainty_zone` as the runtime copy, bound to this one by `test_lib_engine_parity.py` (all signal combinations agree) [S2-models-12]
Conflict(Record) FAMILY "conflict" (J2:4936-4941, 4256): id "C-n" · cycle · topic: Literal[proposal,finding,hold] · between: [FunctionName, FunctionName] · about, subject: str · detail: str?
  · attempts: [{n, who, msg: int?, text, position, agree}] · status: Literal[open,escalated,settled] · escalated: bool · resolved_by: Literal[agents,identity,identity_after_user]?
  · identity: [{say, clause, resolved, ruling, after_user}] · escalated_to_user: bool · user_question: Question? · user_answer, winner, outcome, escalated_because: str?
```
Example reply (valid): `{"kind":"price","decision":"COUNTER","workflows":[{"kind":"proposed","id":"P-1","name":"Scaffold","goal_gap":"no page","outputs":["#hero"],"completion_check":"hero exists","envelope":{"money_limit":10},"steps":[...]}],"next":"Adaptation"}`; the same with `"decision":"REFUSE"` is rejected (`REFUSE funds nothing: workflows must be empty`).

## 7. Atom: the plugin's work atom (`atom.py`)

The plugin declares GOAL / CONSTRAINTS / CONTEXT / WORK and "Verify is the teeth" (SA:13-14). One atom per mutating step, closed or abandoned before the next opens (SA:172-174). Retries keep the atom and raise `attempt`, at most 3 (ADR-038 §5, ADR-029 D4, J2:326). J2's stored atom adds `expected_output` and a list of checks (J2:307, 5126-5131). One class carries both. In the app the unit is one function turn, with work `llm`, `bash` or `manual`; J2's re-asks inside the turn are its attempts, and the turn's helper calls are charged to its atom (S2-models-06, docs/design/function-nodes.md section 5). [S4-fnodes-03]
```
Constraint(Value): text: S(1,300) · check: S(0,300)? (SA:262)
Work(Value): dispatch_kind: Literal[llm,skill,bash,manual] · ref: S(0,200)? · agent: S(0,80)? · steps: S(0,2000) = "" · how_kind: Literal[AI,code] = "AI"     (SA:183,269; J2:5126 how{kind,agent,steps})
ExpectedItem(Value): text: S(1,300) · kind: Literal[section,element,facts,file,test,tap,behavior] · target: S(1,300) or [S(1,300)]≤20 · count: int≥1 = 1 · steps: [S(1,300)]≤8   (J2:5128-5129)
  V: a behavior step starts with set, click, scroll-to, wait (≤ 3 per item), expect-visible, expect-hidden, expect-text, expect-number, expect-changed, expect-style-changed or expect-class (J2:5145-5154)
CheckTemplate = Literal[file-exists,grep-count,named-test, element-count,facts-present,tap-targets,behavior-steps,heading-present,section-not-empty,ids-unique,lld-slice,deed-send,
                        reply-valid,turn-posted,charter-stamp,workable,audience-split,atom-rules,judge-gate,price-kept,within-budget,order-registered,finding-per-item,pass-needs-proof,code-measure-wins,answer-recorded]   # [S4-fnodes-02]
  (the first twelve: plugin templates SA:185 and bin/verify-templates, J2 check types J2:321-323, AS check table; the last 14: the engine's verify registry, one pure function each, docs/design/function-nodes.md section 4; the library only lists the names)
CheckResult(Value): attempt: int 1..3 · exit_code: int · evidence: S(0,2000) · ts: Ts      # 0 = pass; 1 = a registry check failed; 127 = runner or CLI missing, or an unknown registry name; 97 = pinned test changed (SA:325)  [S4-fnodes-02]
Check(Value): template · args: [S(1,500)]≤8 · text: S(0,300) · expect: int or bool? · relevance: S(0,300)? (None = not given) · relevance_source: Literal[declared,default] = declared
  · target_sha256: ^[0-9a-f]{64}$? · results: [CheckResult]≤3
Verify(Value): checks: [Check]≤12           AtomEdge(Value): atom: AtomId · why: S(1,300)           Refusal(Value): code: S(1,40) · message: S(1,600)
AtomDraft(Value): goal: S(0,600) = "" · constraints: [Constraint]≤20 · context: [S(1,200)]≤40 (references only, J2:5135) · work: Work · model, effort: S? · touches, outputs: [S(1,300)]≤40
  · expected: [ExpectedItem]≤20 · verify: Verify · depends_on: [AtomEdge]≤40 · supersedes: AtomId?
OutputItem(Value): verb: Literal[make,do] · name: S · form: S(1,40) (open list, AS:42-55) · ref: S(1,300)
Atom(Record, AtomDraft) FAMILY "atom", kind "atom": id: AtomId · node_id: S(1,60) · department_id: NodeId? · workflow_id: WorkflowId? · task_id: S(1,64)? (the orchestrator task, tsk_...)  [S2-models-06] · session_id: S(1,64)? (the plugin's `sid`; for a function atom the sid of `atom_sid`)  [S2-models-10]
  · state: Literal[open,closed,refused,abandoned] = open · attempt: int 0..3 = 0 · closed_by: Literal[verify,manual-override]? · reason: S(1,600)? · refusal: Refusal? · abandon_code: Literal[verify_failed,run_ended,replaced,manual]? (only when abandoned)  [S4-fnodes-08]
  · produced: [OutputItem]≤40 · notes: S(0,600) · details: dict (keys only from selectors, ids, section, anchor, elements, scope, channel, mode, sent; AS:18-20) · ts_open: Ts · ts_closed: Ts?
```
Validators. The plugin's open-time rules are model rules for every atom that is not `refused`; one function, `open_rules(draft, other_open, abandoned_ids) -> Refusal?`, backs both (the two context-dependent rules, `atom_still_open` and `bad_supersedes`, run only in `open_atom`):
- V1 goal non-empty and not banal: `^(works|done|ok|fix|fixed|good|passes|it runs|no errors)$`, case blind (SA:36, 182). V2 at least one check (SA:184).
- V3 `grep-count` has exactly 3 args and min ≥ 1 (SA:188-192); `file-exists` and `named-test` have ≥ 1 arg; `named-test` needs `target_sha256` (SA:243-248). Relevance: a check that gives none is given `declared: <template> on <args[0]>` with `relevance_source=default` at open (SA:204); one given but blank is refused `relevance_empty` (SA:198-200); a stored non-refused check always has a non-empty relevance. Registry checks (the 14 names added to `CheckTemplate`) [S4-fnodes-02]: `reply-valid` takes exactly 2 args `[family, kind]` (kind may list alternatives joined by `|`); `answer-recorded` takes exactly 1 arg `[question message id]`; the other twelve take none; none needs `target_sha256`; V4 ignores them; the default relevance of a registry check is its own text, and `Check.text` carries the plain sentence the UI shows (docs/design/function-nodes.md section 4).
- V4 envelope: if `touches` or `outputs` exist, every `file-exists` path and the `grep-count` file lie inside them; a directory entry (trailing `/`) covers only paths strictly under it; any `..` is refused (SA:206-235).
- V5 per state. `open`: no `closed_by`, `ts_closed`, `refusal`, `reason`. `closed`: `closed_by == verify`, `ts_closed`, `attempt ≥ 1`, every check's last result exit 0. `abandoned`: non-empty `reason`, `closed_by == manual-override`, `ts_closed`, `abandon_code` (default `manual`); no other state carries an `abandon_code` [S4-fnodes-08]. `refused`: `refusal`, `attempt == 0`, `ts_closed`, no `closed_by`; its goal may be empty and checks missing, because it records what was refused.
- V6 every check has exactly `attempt` results (a close attempt appends one result to every check). A V1 to V4 failure reads `value_error: <code>: <message>`.

Lifecycle: pure functions; callers pass `now`; the check runner executes the templates and hands back one `CheckResult` per check (the plugin runs `bin/verify-templates/*.sh`, J2 runs its code checks).
```python
Transition(Value): outcome: Literal[opened,closed,verify_failed,refused,abandoned] · atom: Atom · card: Card · events: [DomainEvent] · refusal: Refusal?
Seen(Value): work: Literal[llm,bash,manual]? · model: S(1,80)? · note: S(0,200) = ""       # what the layer saw while the work ran  [S4-fnodes-03]
open_atom(draft, *, id, node_id, now, department_id=None, workflow_id=None, task_id=None, session_id=None, other_open=None, abandoned_ids=()) -> Transition  # opened, or a stored refused atom  [S2-models-06]
close_atom(atom, results: Sequence[CheckResult], now, *, pins_now: Mapping[int, str] = {}, seen: Seen | None = None) -> Transition   # [S4-fnodes-03]
abandon_atom(atom, reason, now, *, code="manual", seen=None) -> Transition        ledger_row(atom) -> LedgerRow        card(transition) -> Card   # [S4-fnodes-03] [S4-fnodes-08]
atom_display_state(atom) -> Literal[open,verify_failed,closed,refused,abandoned]   # "verify_failed" iff state is abandoned and abandon_code is "verify_failed"; every other state is itself (open is always open)  [S4-fnodes-08]
ledger_row_from_view(view: AtomView, node_id: str, department_id: str | None, *, now: Ts = 0) -> LedgerRow   # a J2 atom/1 (builder) row for the Atom log; ts = now, the caller's clock  [S4-fnodes-09]
atom_view(atom, workflow: Mapping | None = None, edges=(), ended=False) -> AtomView   # port of JS:68-96; `workflow` is a mapping with name and status, so atom.py never imports workflow.py
# run_views, link_views, validate_views: ports of JS:133-206
```
| Step | Rule | Outcome |
|---|---|---|
| open | another atom of this node is open (`atom_still_open`) · goal missing or banal · no check (`verify_missing`) · `bad_args` · `vacuous_check` · `relevance_empty` · `pin_missing` · `dotdot` · `outside_envelope` · `bad_supersedes` (target not abandoned). Plugin order, first wins (SA:172-248) | `refused` atom stored, card "ATOM REFUSED" (HK:4-5, 60) |
| close | `not_open` · `attempts_exhausted` (three used: the worker stops, ADR-029 D4) · `bad_results` (one result per check) · envelope drift (`outside_envelope`, `dotdot`, SA:292-319) | `refused`, atom unchanged, `Transition.refusal` set |
| close | pinned `named-test` changed: result exit 97 (SA:321-329) · runner or CLI missing: the runner reports exit 127 · any non-zero exit (SA:335-342): attempt + 1, atom stays open | `verify_failed` |
| close | every check exit 0: `closed`, `closed_by=verify` (SA:359-370) | `closed` + ledger row |
| abandon | needs `open` and a non-blank reason (`reason_missing`, `not_open`; SA:373-391); `code` defaults to `manual`, the layer passes `verify_failed`, `run_ended` or `replaced` [S4-fnodes-08] | `abandoned` / `refused` |

- A failed try with tries left leaves the atom `open` (display state `open`). When the tries are used up and J2 has no recovery, the layer abandons the atom with `abandon_code` `verify_failed`; `atom_display_state` reports `verify_failed` (ADR-029 D4, ADR-011 five-set). The mapping of (state, `abandon_code`) to the five display words is the table of docs/design/function-nodes.md section 6.2; the card, the Atom log, the chip counts and `AtomOut.state` all use this one function. [S4-fnodes-08]
- `verify_failed` is derived, never a stored state (ADR-038 §5: "open to closed or abandoned"): a failed try is a transition outcome, a final failure is stored `abandoned` with its code. [S4-fnodes-08]
- `Seen`: when `seen.work` is set and differs from `atom.work.dispatch_kind`, the returned atom has `work.dispatch_kind = seen.work` and `notes = (notes + " declared <old>, did <new>").strip()`; `seen.model` fills `Atom.model` when empty. Nothing else about the atom changes after open. [S4-fnodes-03]
- `ledger_row_from_view`: `status = view.status` (closed, verify_failed, abandoned); `verify = {template: the type before ":" in the first verification method, exit_code: 0 for closed, else 1}`; `attempt = view.attempt or 0`; model, effort and touches empty; reason from `view.details` or notes; `ts = now`. [S4-fnodes-09]
- `refused` is stored only for an open-time refusal. The plugin prints REFUSED and writes nothing (SA:39); the app keeps it so the node and the owner's page show it (DL6).
- Not modelled: the plugin's skill ladder (SA:344-357) and dispatch markers.

`LedgerRow(Record)` FAMILY "atom_ledger_row" (the plugin's `atom-ledger-v0.3`, SA:361-366, 384-387, plus `node_id` and `department_id`; refused rows are a declared addition to atom-ledger-v0.3 [S2-models-10], and so are verify_failed rows): atom_id · node_id · department_id? · session_id? · goal · status: Literal[closed,verify_failed,abandoned,refused] · verify: {template, exit_code}? · attempt: int 0..3 · model, effort: S? · touches: [S] · relevance: S? · relevance_source? · reason: S? · ts: Ts. V: closed => verify with exit 0; verify_failed => verify {template, exit_code != 0} (the last failing check) and a reason; abandoned and refused => a reason and no verify. `ledger_row(atom)` picks verify_failed from `abandon_code`. [S4-fnodes-08]
`Card(Value)`: label: Literal["WORK ATOM OPEN","WORK ATOM CLOSED","VERIFY FAILED","WORK ATOM ABANDONED","ATOM REFUSED"] (SA:98-143; HK:60-78) · goal · rows: [{label, text}] with the plugin's row names (Goal, Done when, Done by, Limits, Using, Ref, Result, Proof, Output, Recorded, Why, Next, Reason). The card is built inside the transition and is never optional (SA:15-19). A failed close gives VERIFY FAILED; the abandon after it gives WORK ATOM ABANDONED with the rows Reason and Why (the failing evidence). [S4-fnodes-08]

`AtomView` (payload `atom_view` v1; the J2 wire document, so the J2 UI is unchanged, D6): `schema: Literal["atom/1"]` · id · workflow · name · owner: str? · status · attempt: int? · goal: str? · how: {kind, agent, steps}? · constraints: [str] · context: [str] · defined_output: [dict] · verification: [{check: Literal[exists,valid,"meets the defined output",receipt], applies_to: str?, method: str, met: bool?, evidence: str?}] · output: [OutputItem] · depends_on, used_by: [AtomEdge] · notes: str · details: dict · stale, rechecked (optional, board/1). Source: ASJ:1-193.
| From `Atom` | To `AtomView` |
|---|---|
| state `closed` / `abandoned` | status `closed` / `abandoned` |
| state `abandoned` with `abandon_code` `verify_failed` | status `verify_failed` [S4-fnodes-08] |
| state `open`; or `open` with attempt 3 and a failing last result | `open`; `verify_failed` (JS:61-62; J2's own derivation for J2-format atoms, `atom_display_state` never reads the attempt) [S4-fnodes-08] |
| state `refused` | `abandoned`, with `details.refusal` (the view enum is closed by D6; J2-format documents only, the app's own surfaces keep `refused` through `atom_display_state`) [S4-fnodes-08] |
| workflow, name, owner, how, constraints | `workflow_id` or `id` before the dot (JS:70); workflow name; `work.agent`; `{kind: how_kind, agent, steps}`; constraint texts |
| verification | one row per `CheckResult`, all attempts (JS:73-78) |

## 8. Nodes and graph edges (`node.py`)

### 8.1 Node family (FAMILY "node")
```
Node(Record) ABSTRACT: id: ^[a-z][a-z0-9_-]{1,39}(\.[a-z]+)?$ · label: S(1,80) · department_id: NodeId? · state: Literal[idle,running,waiting,waiting_on_you,fault,filed,done_unchecked,left_open,not_made] = idle · detail: S(0,300) = ""
  · version: int≥1 = 1 · chat_session_id: S(1,64)? · edge_ids: [EdgeId]≤200 (stored edges only) · ts_created, ts_updated: Ts      # [S2-models-03] [S2-models-02]
StructuralNode(Node) kinds root, department, division, step (nodes that mirror the chart, and task steps): parent_id: NodeId? · task_id: S(1,64)? · step_ref: S(1,40)?      # [S2-models-02]
  V: step => task_id and step_ref, where step_ref is "task", "W-<n>" or "team:<role>"; other kinds => neither · root, department and division: state is idle, running, waiting_on_you or fault; step: any of the nine      # [S2-models-02] [S2-models-03]
FunctionNode(Node) ABSTRACT, the agentic node: kind · goal: S(1,600) · task: S(1,200) · context: [S(1,200)]≤40 · open_atom: AtomId? · atom_count: int≥0 = 0 · wait_on: S? · stats: {calls: int≥0, seconds: float≥0, tokens: {input, output: int≥0}} · spec_version: int≥1 = 1      # [S4-fnodes-14]
  V: department_id set and id == "<department_id>.<kind>" · state is one of idle, running, waiting, waiting_on_you, fault · waiting => wait_on      # [S4-fnodes-14]
IdentityNode / AdaptationNode / PriorityNode / CoordinationNode / AuditNode: kind = the function name; FUNCTION ClassVar = that name
```
`state` is J2's map/1 vocabulary (docs/map-schema.md Statuses, nine words; MAP:55-60: working => running, blocked => fault, `waiting_on_you` only while a question to the Requester is open); a function node uses the five function states. [S2-models-03] `FunctionNode` follows the owner's four words: **goal** (the standing sentence of the spec, always equal to the `FunctionSpec` goal of its `spec_version`), **task** (the standing TASK line of the spec, a string; the live unit is the department's task and `Atom.task_id`, not a node field), **context** (the names of the slice the function reads, = `FunctionSpec.reads`), **work atoms** (the node holds its `open_atom` id and an `atom_count`; the atoms table is the list, so a node never grows without bound). goal, task, context and `spec_version` are set by `new_function_node` and refreshed by `refresh_function_nodes` at startup when the spec version rises, never by an event; `state`, `detail`, `wait_on` and `stats` come from the node event. [S2-models-08] [S3-web-04] [S4-fnodes-14] Ids are the library's: a chart node keeps its chart id, a function node is `<dept>.<fn>`, a step node is `s-` plus the first 10 hex digits of sha1(`<task_id>:<step_ref>`). [S2-models-02] `FunctionNode` is the spec's AgentNode and its five children are the spec's Identity, Adaptation, Priority, Coordination and Audit; there is no BuilderAtom class: a builder's atom is J2's dict, gated by `gate_record`, shown through `AtomView`. [S4-fnodes-01]

### 8.2 Graph edges and mirror checks
```
GraphEdge(Record) FAMILY "edge", kinds contains, has_function, has_step, handoff, step, speaks_to, depends_on: id (== "<kind>:<from_id>><to_id>") · from_id, to_id: S(1,80) · label: S(0,200) · n: int≥0? · version: int≥1      # [S2-models-02]
  · status: Literal[filed,running,waiting,waiting_on_you,fault,not_made,idle] (MAP:68-78) · source: {file, workflow?, field, value}?
  V: from_id != to_id · contains, has_function and has_step need no `source` and are never stored (derived on read); every other kind needs `source` ("no line without a record", MAP:84-86) · a handoff between two function nodes of one department must be in HANDOFFS      # [S2-models-02]
  # reads and rework are event names, not edge kinds: a read is a depends_on edge labelled "reads", a rework a depends_on edge labelled "revises"      [S2-models-02]
HANDOFFS = {identity: (requester,adaptation,priority,coordination,audit), adaptation: (priority,identity,audit,coordination), priority: (adaptation,identity,coordination),
            coordination: (priority,adaptation,identity,audit), audit: (identity,)}; a workflow agent W-n => (coordination,)     (J2:103-107, changed by S3-web-04)
  # coordination -> audit is the code hand-off at queue empty (j2.py:6834, 6891); audit -> identity only (j2.py:8969 _pick allowed=(identity,)). The wire hands_to is this table without "requester".      [S3-web-04]
check_graph(chart, nodes, edges) -> list[Violation]      # edges = the stored edges plus the edges the store derives: contains from chart.edges, has_function from department_id, has_step from parent_id      [S2-models-02]
  G1 every chart node has a StructuralNode with the same id and kind · G2 every department's five function nodes exist with the chart's ids and this department_id
  G3 no node names a missing department · G4 edge endpoints exist; the derived `contains` edges equal the chart's edges · G5 node.edge_ids and the stored edges agree both ways      # [S2-models-02]
  # no G6: "one open atom per node" is enforced by the unique index one_open_atom_per_node (section 11), not here      [S2-models-03]
```
### 8.3 What the library does not decide
Chat transcripts and sessions (`chat_session_id` is only the link: one session per node, a moved node keeps it, GEN:107, 122), the graph store's SQL, and live updates (events, section 13). A division's session is a lens: it keeps notes only, and its transcript is read through the department session. [S4-fnodes-06]

### 8.4 Function-node plug-in (interface; the final spec is applied)
The function-node design supplies **data**, not classes: `FunctionSpecs`, validated here and held in `specs/function_specs.json` (WP L10). The names are settled: the spec's AgentNode = `FunctionNode` with the children `IdentityNode`, `AdaptationNode`, `PriorityNode`, `CoordinationNode`, `AuditNode`; WorkAtom = `Atom` (family `atom`; `work-atom/0.3` is only the schema string on the wire and in the DB); BuilderAtom is not a class (builders keep J2 dicts and the `atom/1` view); org_node_id = `department_id`; session_id = `chat_session_id`; reads / writes / never / stages / routes / reply_model / checks = `FunctionSpec.reads`, `writes`, `may_not`, `stages`, `HANDOFFS`, `TaskKind.reply_family` + `reply_kind`, `AtomTemplate.checks`; AgentNode.atoms = `open_atom` + `atom_count`; AgentNode.state = `Node.state` (one source: the engine's J2 lanes); WorkAtom.author = `Atom.node_id`; WorkAtom.usage = the `usage_ledger` rows keyed by `atom_id`. When the spec moves, only `FunctionSpec` fields, `load_function_specs` and the L10 data change. [S2-models-08] [S4-fnodes-01]
```
TaskKind(Value): kind: S(1,40) · summary: S(1,200) · reply_family: S · reply_kind: S ("a|b" lists alternatives)      # [S2-models-06]
CheckRef(Value): name: CheckTemplate (a registry name) · args: [S(1,500)]≤8      # [S4-fnodes-02]
AtomTemplate(Value): name: S(1,60) · goal: S(1,600) (may hold {function} {kind} {step_label} {task}) · work: Work · work_hint: Literal[llm,bash,manual] = "llm" · checks: [CheckRef]≤6 · touches: [S(1,300)]      # [S2-models-06] [S4-fnodes-02] [S4-fnodes-03]
FunctionSpec(Value): function: FunctionName · role: S(1,200) (the TASK line) · goal: S(1,600) · yields: S(1,60) · stages: [S(1,40)]≤8 · reads, writes: [S(1,80)]≤20 · may_not: [S(1,200)]≤20 · task_kinds: [TaskKind]≤20 · atom_templates: [AtomTemplate]≤10 · version: int≥1      # [S2-models-06] [S3-web-04] [S4-fnodes-02]
FunctionSpecs(Record) FAMILY "function_specs": specs: dict[FunctionName, FunctionSpec] (all five; key == spec.function)
load_function_specs(path=<specs/function_specs.json>) -> FunctionSpecs      # the default path is the L10 data file  [S2-models-05]
new_function_node(dept_id, function, specs, now) -> FunctionNode      # goal = spec.goal, task = spec.role, context = spec.reads, spec_version = spec.version, state idle  [S4-fnodes-14]
refresh_function_nodes(specs, nodes) -> list[FunctionNode]      # pure: the nodes whose spec_version is lower, with goal, task, context and spec_version replaced; the orchestrator calls it at startup and stores the result through the gate  [S4-fnodes-14]
```
- `stages` are the J2 steps the function acts in (for example `J2.b`). Every `FunctionSpec` holds an `AtomTemplate` named `generic` (goal "The {function} answers the hand-off {kind} with a reply that follows its rules", no named check) that serves any task kind without its own template. A template lists named checks only; declare adds the floors: `reply-valid` when the `TaskKind` names a reply family and kind, `turn-posted` always for llm and bash work, none for manual. [S2-models-06] [S4-fnodes-02]
- `work_hint` is the work kind the template predicts; declare writes it to `Work.dispatch_kind` (how_kind AI for llm, else code; docs/design/function-nodes.md 2.3). Seeds: priority/envelope `bash`; identity/"the owner's question" (template `answer`) `manual`; coordination/schedule `llm`, with the declare rule "bash iff `workflows.json` has no registered or held workflow". [S4-fnodes-03]
- `yields` is the WORK ATOM YIELDS line of the card: identity "charter, rule, question", adaptation "proposal with its checks", priority "GRANT, COUNTER, REFUSE", coordination "rule, order, holds", audit "one finding per item". The seed templates (goal, work hint and named checks per task kind) are the table of docs/design/function-nodes.md section 3. [S4-fnodes-02]
- `verify_refs` also checks that every `CheckRef` name is a `CheckTemplate` member with a matching argument count and that every `reply_family` / `reply_kind` alternative is registered. [S2-models-06] [S4-fnodes-02]
- `writes` is recorded on the spec and checked by the engine layer in warn-and-log mode (`layer.touches_miss`); no library rule enforces it. [S4-fnodes-04]
- Package data: `specs/function_specs.json` is read at runtime, so a built wheel must carry it, but `[tool.setuptools.package-data]` in the chassis `pyproject.toml` has no glob for `library/specs/*.json` (S3-web-08 checked the globs against the module maps, and none named this file). `tests/test_packaging.py` fails on a data file no glob matches, and no work package may own `pyproject.toml` (a protected chassis file), so the chassis owner adds that glob by hand. [S3-web-08]

Seed values (the first content of `specs/function_specs.json`; role, reads and writes from the `agents/j2/*.md` front matter and `j2_ui.html:940-942`; task kinds from the J2 turn dispatchers) [S2-models-05] [S3-web-04]:
| function | role (the TASK line) | goal (the J2 role sentence) | reads | writes | J2 task kinds |
|---|---|---|---|---|---|
| identity | J2.a charter, J2.d rulings, J2.h workable? | charter guardian and conflict closer | charter, proposals, findings, alarms, recorded rules | identity decisions, questions to the Requester, done verdicts | intake, stage_decision, resolve, approval, audit, requester_answered, ruling_budget, limit, send_confirm, question (J2:3539-3542) |
| adaptation | J2.b proposes, disputes, saves lessons | sense the goal gap and propose how to close it | charter, record, results, findings, constraints, capability catalogue | proposals and revisions | propose, respond, dispute, atom_failed, change (J2:5196-5203) |
| priority | J2.c prices, checks run limits | resource bargain and envelope authority | proposals, available resources, current envelopes, reported spend | grants, counters, refusals, envelope changes | price, dispute, envelope, ruling (J2:6333-6339) |
| coordination | J2.f schedules, holds the write lock | ordering, dependencies, handoffs, collision prevention | registered workflows, envelopes, triggers, dependencies, locks, schedule | schedule decisions, holds, handoffs, alarms | schedule, dispute (J2:6804-6806) |
| audit | J2.g checks the site | independent evidence-based check | charter, registered workflow, run record, result artifact, sources | findings | audit, dispute (J2:8942-8943) |

The identity row has no `envelope decisions` in `reads`: the code strips envelopes from Identity's state (FN-24, j2.py:3053-3090). An `alarm` appears in two role files and GEN:133, but J2 code has no alarm record `[U]`, and the final spec lists alarms without defining a record, so the library defines none. [S3-web-04] [S2-models-08]

## 9. Workflow, Step, Template, artifacts and rules

### 9.1 Workflow and Step (`workflow.py`)
Two levels, because the owner's graph has both (GEN:65-70, 121). A **task workflow** is what the chat agent builds across departments: its steps are the `step` nodes of the workflow graph, each given to one department. A **department workflow** is what Adaptation proposes and the validator registers inside one department: J2's workflow dicts (J2:5120-5131, 6672-6678), whose steps are work atoms. `to_j2(w) -> dict` and `from_j2(d) -> ProposedWorkflow` cover the department level and round-trip J2's own `EXAMPLE_WORKFLOW` (J2:292-305; J2 `atoms` are the `steps`).
```
Resources(Value): money, calls, time_minutes: int≥0 = 0                 FailureAction = Literal[rollback,escalate,pause,abort,continue] (ADR-011)
Step(Value) ABSTRACT: id: S(1,20) ("a1" in J2) · name: S(1,120) · depends_on: [S(1,20)]≤20 · on_failure: FailureAction?
  AIStep kind "ai": atom: AtomDraft, work.how_kind == AI, dispatch llm or skill       CodeStep kind "code": atom: AtomDraft, work.how_kind == code, dispatch bash or manual
    (J2 how.kind is AI or code; a send deed is a code step, AS:69-75)
  AssignmentStep kind "assignment": dept: NodeId · scope: NodeId? (a division) · brief: S(1,2000) · follows: ^tsk_[0-9a-f]{12}$? (an earlier task it continues) · depends_on: [S(1,20)]≤4 · id: S(1,20), the chat agent's refs a1 to a5 are accepted      # [S2-models-13]
Workflow(Record) FAMILY "workflow" ABSTRACT: name: S(1,120) · steps: [AIStep or CodeStep or AssignmentStep] 1..12 (discriminator `kind`)
  · failure_policy: FailureAction = escalate (ADR-011 names the set, not the default: my choice, DL8)        V: step ids unique · a step's depends_on names an earlier step
TaskWorkflow kind "task": id: S(1,64) (the request id "req-<message id>")                                    V: assignment steps only      # [S2-models-13] [S2-models-08]
DeptWorkflow(Workflow) ABSTRACT: goal_gap: S(1,400) · expected_outcome: S(0,400) · outputs: [S(1,200)] 1..20 · completion_check: S(1,400) · dependencies: [S(1,40)]≤20
  · parts: [S(1,80)] (rate-card items) · covers: [int≥1] · fixes: [S(1,40)] · revises: S(1,40)? · estimated_resources: Resources · output: Literal[website,prd,hld,lld] = website
  · role-file fields, optional (ROLE:adaptation:20-37, absent from J2's reply format): inputs, capabilities, risks: [S]≤10 · trigger: S? · authority_touched: Literal[local,cross_department,external]?
  V: atom steps only (J2 today: exactly one, id "a1")
ProposedWorkflow kind "proposed": id: S(1,40) · envelope: Envelope? · plan fields, optional (RS:56-84): stage, certainty, done_test, delivers, informs, inputs_from, hold, research, approach, certainty_signals, experiment
RegisteredWorkflow kind "registered" (J2:6672-6678 and later keys): id: WorkflowId · proposal_id: str? · covers_text: [str] · purpose: str · cost, estimate: int≥0 · envelope: Envelope · charged: bool
  · calls_used, retries_used: int≥0 · status: Literal[registered,held,running,done,failed,unfunded] · cycle: int≥1 · atoms: [AtomId] · lld_sections: [str] · section: str · agent: str · stage, change, kept: str?
  · last_check, send_error: str? · hold_override, approval_asked, style_guide: bool · version: int? · artifact: str?
```
`name`, `goal_gap`, `outputs`, `completion_check` are required non-empty (J2 `REQUIRED`, J2:6611). Keys the engine sets after registration that are missing here fail the golden-run test (section 14), which is how the list stays complete. A task step node is keyed by `task_id` and `step_ref` `task` (S2-models-02); the `TaskWorkflow` is the validated plan and is not stored. The chat agent's reply classes stay flat and orchestrator-owned (`ChatDecision`, `AssignmentDraft`, `AssignmentPlan`; transport-safe, no union): `AssignmentPlan.to_task_workflow(request_id)` builds the `TaskWorkflow`, and `TurnRunner` passes it through `GATE.check("workflow")` before any task is created. [S2-models-13]

### 9.2 Template bases (`templates.py`)
- Port of `JT:72-372` and the spec-to-model helpers `JT:373-486, 487-654`: `FieldSpec`, `ObjectSpec`, `MadeBy`, `Context`, `Template` (closed; `kind` generic or specialised; at most 25 fields; allowed types string, integer, boolean, `list[string]`, `list[Obj]`, `Obj`), `GenericTemplate`, `SpecialisedTemplate`, and the pure checks `shape_problems`, `rule_problems`, `resolve`, `keeps_problems`, `generic_ref`, `from_model`, `generic`, `build_model`, `transport`, `validate`. Family "template" (kinds generic, specialised). The library owns this definition; the engine keeps its vendored `j2_template_lib.py` as the runtime copy, bound to the library by `test_lib_engine_parity.py` until the switch of S2-models-12. [S2-models-12]
- Stays with the engine port: the router, library-directory I/O, codegen and prompts (`JT:706` onward).
- `generic()` already builds a generic from the section model and `RULES` (JT:429-441). The library keeps `generic_file`, `write_generic` and `generic_drift` (JT:444-483); the files go to `SUTRA_TEMPLATES_DIR` (default `docs/schemas/templates/<artifact>/generic.json`) instead of J2's `templates/`, and `test_lib_templates` fails on drift. These files are generated documentation and are never read at runtime; the runtime copy of the generic templates is `sutra_app/engine/templates/**` (package data). [S3-web-08]

### 9.3 Artifact models and rules as data (`artifacts/`)
- `models.py` is `j2_artifact_models.py` with one change: `Artifact` derives from `Value` (strict, frozen). Checked on pydantic 2.14: all 19 section models and the three document models accept J2-style payloads; `required: "true"` is now rejected. The library owns these definitions (and the rules below); the engine keeps its vendored `j2_artifact_models.py` and `j2_rules.py` (lax coercion, J2 behaviour) as the runtime copy, bound to the library by `test_lib_engine_parity.py` until the switch of S2-models-12. [S2-models-12]
- Registration (payloads; version = the digit in `TEMPLATE`):
```python
for kind, sections in SECTION_MODELS.items():        # prd 6, hld 6, lld 5, design 1, website 1 = 19
    for section, cls in sections.items():
        REGISTRY.register_payload(f"artifact.{kind}.{slug(section)}", 1, cls)   # artifact.prd.problem, artifact.design.style-guide, artifact.website.section
for kind in ("prd", "hld", "lld"):
    REGISTRY.register_payload(f"artifact.{kind}", 1, DOC_MODELS[kind])          # design and website documents are their section models
```
- `SECTION_MODELS`, `DOC_MODELS`, `SECTION_CONDITIONS`, `model_for` (JM:378-412) move to `artifacts/__init__.py`. `OPTIONAL_FIELDS` (JM:39-42) stays the transport-optional set, so J2's schema shas stay comparable. `render.py` holds `render_section`, `style_from_design`, `normalise` and `errors_of` unchanged (JM:502-631).
- `rules.py` is `j2_rules.py`: the same 12 rule functions and `run_rules/run_specs/failures` (they never raise; `pass` is True, False or None). `RULES` becomes `dict[(kind, section), list[RuleSpec]]`, validated at import, so a typo fails the import.
- `RuleSpec(Value)`: rule: Literal[the 12 names] · name: S(1,200) · from_: S (alias "from") · path: S or [S] · prefix, target, anchor_path, html_path, fail_text, missing_text: S? · values: [S]? · required_target: bool = False. V: the keys each rule type needs (`RULE_NEEDS`, JT:51-54); single-path types take one path; a `ref_exists` target starts with `this.`, `prd.`, `hld.` or `lld.` (JT:301). Whether a path resolves is a `Template` check (`resolve`), not a `RuleSpec` check.
- `register_payload(..., rules=)` attaches a list; a specialised template carries its own list in exactly this shape (JR:3-8).

### 9.4 Realization plan
`RealizationFields` (RS:13-100) sit on `adaptation.propose`: `factors` [{name, source: Literal[brief,general,research,budget], quote: str?, citation: str?, why, stages}] · `unplaced` [{name, why}] · `stages` [{id, thinking, tiers, goal, done_test, method: str?, owns_factors, inputs_from}] · `open_facts` [{fact, workflow, blocking, handling}] · `not_ready` [{workflow, score: 0..1, weakest, stop_reason, route: Literal[identity,priority,left_out]}]. Stage ids come from `agents/j2/stages.json` (35 ids), loaded once. V: source brief => non-empty quote; research => `citation` matches `^research\.md#R-\d+$`; budget => `stages` empty; a workflow with `research` has empty `delivers`, a stage other than `build`, and `min_sources ≥ 3` (RS:27-30, 71-83). `plan_faults` (R1 to R6, cycles) stays in the engine (JZ:149).

## 10. Registry index and the J2 record catalogue (`records.py`)

Families registered in v1 (kinds): `org_chart` · `chart_change` (reuse, add, rearrange) · `goal` (site, doc) · `department` · `evaluation` (result, recheck, plan, run) · `identity` (intake, ruling, heard, done, approval, approval_ask) · `adaptation` (propose, respond, atom_verdict, lesson) · `priority` (price, envelope_check) · `coordination` (schedule) · `audit` (report) · `conflict` · `atom` · `atom_ledger_row` · `node` (root, department, division, step, identity, adaptation, priority, coordination, audit) · `edge` (contains, has_function, has_step, handoff, step, speaks_to, depends_on) · `workflow` (task, proposed, registered) · `template` (generic, specialised) · `function_specs` · payloads `artifact.*` (22), `atom_view` and `run_message`. [S2-models-02] [S2-models-13] [S2-models-15]

`gate_record(name, data, *, mode) -> Checked | None` is called by the vendored engine's `J2Run.save(name, data)` (J2:3046) and, per line, by `post()` (J2:3008-3040). `RECORD_FAMILIES` (file => family):
- goal.json => goal · workflows.json => workflow:registered (array) · atoms.json => atom_view (`{schema, atoms[], warnings[]}`) · audits.json => evaluation:result/recheck (array) · conflicts.json => conflict (array) · conditions*.json => [ConditionResult] · style.json => artifact.design.style-guide · memory/lessons.jsonl => lesson
- receipts.jsonl => receipt (atom, attempt, type, check, target, pass, evidence `[U]`)
- realization.json, map.json, board.json, story, agent, artifacts, artifacts-tree, summary.json => `wire.py` (L9)
- chat.jsonl => `run_message` (`chat.py`, L3; it was `chat_message`, which is now the orchestrator's stored server message) · calls.jsonl => connector section [S2-models-15]

`mode="log"` records a `record_rejected` event and lets J2's write go on (during the port); `mode="strict"` raises `RecordRejected` (after the golden-run test passes; `SUTRA_RECORDS=strict`). In strict mode a file not in the catalogue is rejected.
Chat message meta (`MessageMeta` in `chat.py`, used by `RunMessage` and by the orchestrator's stored `chat_message`) is a closed key set with open values. [S2-models-15] J2 attaches meta by keyword at `post/_say/_reply/_ask_user`; keys found by an AST scan of j2.py on 2026-11-04: warning to_user change next done test redirect relay requester_only audience rejected checks mechanical override act pause shaped reader affected agree keep template_route realization handoff gaps conflict auto gaps_title to options_only decision artifact workflow proposal accept envelope version attempt register schedule human_output section workflow_cost stamp charged cycle exchange atom audit workable playbook lessons; base keys: id t who text step calls board_read. `test_lib_records` re-runs the scan and fails if the engine uses a key that `MessageMeta` (`chat.py`) omits. [S2-models-15]

## 11. Data

Schema export: `docs/schemas/<family>.v<N>.json` and `index.json`, for example `{"atom":{"1":["atom"]},"node":{"1":["root","department","division","step","identity","adaptation","priority","coordination","audit"]}}`. Reference DDL for the stores section (it may rename, not drop a column or a rule); `body` is always `Checked.json`. `org_charts` and `chart_changes` are created by the orchestrator (orchestrator.md 4.1); this file defines their bodies only: `Checked[OrgChart]` and `Checked[ChartChange]`. The statements below for nodes, edges, atoms and atom_ledger stay as reference. [S2-models-01]
```sql
CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, department_id TEXT, state TEXT NOT NULL, version INTEGER NOT NULL, chat_session_id TEXT, body TEXT NOT NULL, sha256 TEXT NOT NULL, ts INTEGER NOT NULL);
CREATE TABLE edges (id TEXT PRIMARY KEY, kind TEXT NOT NULL, from_id TEXT NOT NULL, to_id TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL);   -- stored kinds only (handoff, step, speaks_to, depends_on); contains, has_function and has_step are derived on read  [S2-models-02]
CREATE TABLE atoms (id TEXT PRIMARY KEY, node_id TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('open','closed','refused','abandoned')), attempt INTEGER NOT NULL,
                    body TEXT NOT NULL, sha256 TEXT NOT NULL, ts_open INTEGER NOT NULL, ts_closed INTEGER);
CREATE UNIQUE INDEX one_open_atom_per_node ON atoms(node_id) WHERE state = 'open';   -- SA:172-180; per node because each node has one session
CREATE TABLE atom_ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, atom_id TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, ts INTEGER NOT NULL);   -- append-only (SA:42)
```
Example `atoms.body` of a closed atom after two attempts, as the gate emits it (keys sorted in the file; shown wrapped, defaults omitted; the id has the function-atom form `a-<sid>-<nn>`, S2-models-10):
```json
{"kind":"atom","schema_version":1,"id":"a-3f9a1c2b7d-01","node_id":"sales.adaptation","goal":"Visitors can open the contact form","state":"closed","attempt":2,"closed_by":"verify",
 "work":{"dispatch_kind":"llm","agent":"Builder","steps":"Create #contact","how_kind":"AI"},"touches":["site/"],"ts_open":100,"ts_closed":120,
 "verify":{"checks":[{"template":"file-exists","args":["site/index.html"],"relevance":"declared: file-exists on site/index.html","relevance_source":"default",
   "results":[{"attempt":1,"exit_code":1,"evidence":"missing","ts":110},{"attempt":2,"exit_code":0,"evidence":"present","ts":120}]}]}}
```
- Its ledger row: `{"kind":"atom_ledger_row","schema_version":1,"atom_id":"a-3f9a1c2b7d-01","node_id":"sales.adaptation","status":"closed","verify":{"template":"file-exists","exit_code":0},"attempt":2,"touches":["site/"],"relevance":"declared: file-exists on site/index.html","relevance_source":"default","ts":120}`.
- A refused open (`goal: "done"`): the stored atom has `"state":"refused","attempt":0,"ts_closed":<now>,"refusal":{"code":"goal_banal","message":"goal is banal ('done'): state the observable outcome"}`, and its ledger row `"status":"refused"` with that message as `reason`.
- A function node (valid): `{"kind":"priority","id":"sales.priority","label":"Priority","department_id":"sales","goal":"Price every proposal against the room that is left","task":"J2.c prices, checks run limits","state":"idle"}`; with `"id":"sales.audit"` it is rejected (`a function node id is '<department id>.<function>'`), and so is `"state":"filed"` (a function node uses the five function states). [S4-fnodes-14] [S2-models-03]

## 12. Flows

**F1 Write through the gate.**
1. A store method receives a model or dict. 2. `GATE.check(family, payload, ctx=store_ctx)`. 3. On `GateError` nothing is written: an API returns 422 with the violations in the error envelope (section 13) [S3-web-15], an agent gets the violations as retry text. 4. The store opens its transaction, writes `Checked.json` and the projections, commits. A crash between 2 and 4 loses only the unwritten change.

**F2 Chart change.**
1. Chat flow step 1: the chat agent reads the chart (revision r). 2. Per request it asks the connector for a `ChartChangeRequest` (reason, reuses, ops) with `transport_schema(ChartChangeRequest)`; the model decides reuse, add or rearrange by what it puts in `ops`. 3. `ReplyParser` parses it; code builds the `ChartChange` (`kind = derive_kind(ops)`, id, task_id = the request id, base_revision r, ts) [S2-models-08] and calls `GATE.check("chart_change")` (shape). 4. The chart store takes the SQLite write lock, loads the current chart, runs `apply_change(chart, change, new_id=...)`.
5. `ChartChangeInvalid`: all violations go back to the agent as retry text and the attempt is stored `rejected` (at most 3 tries, J2 pattern); `stale_base`: re-read and redo.
6. Success: `GATE.check("org_chart", result.chart)`; then one transaction appends `org_charts`, marks the change `applied`, creates `new_function_nodes` and structural nodes, executes the `carry_links` plan on chat sessions (`ChatStore.apply_links`), commits; the store publishes `chart.changed`. [S2-models-11]
Failures: model call fails or JSON invalid (`not_json`): no change, the agent tells the user. Two requests racing: the second sees `stale_base`. Crash: the transaction rolls back and the chart is unchanged.

**F3 Atom.**
1. The engine layer declares an `AtomDraft` from the `FunctionSpec` template of the turn (never from the model). 2. `open_atom`: a stored `refused` atom (card, `atom.transitioned`) or `opened`. 3. The work runs (connector, engine). 4. The layer's check runner returns one `CheckResult` per check; `close_atom` gives `closed` (ledger row) or, for a failed try, the outcome `verify_failed` with the atom still `open`. 5. When the tries are used up and J2 has no recovery, the layer calls `abandon_atom(atom, reason, now, code="verify_failed")` (ADR-029 D4); `atom_display_state` then reports `verify_failed`. [S2-models-06] [S4-fnodes-08]
Failures: runner or CLI missing: exit 127 is recorded as a failed attempt. The run crashes mid-attempt: results are appended only inside `close_atom`, so the atom stays `open` with `attempt` unchanged (V6 holds); the server abandons it when it recovers the stale run (`run_ended`) and the next `turn_started` of the node abandons a stale open atom first (`replaced`). Two nodes opening at once: the unique index rejects the second, which becomes a `refused` atom `atom_still_open`. [S2-models-06] [S4-fnodes-08]

**F4 Model reply.** 1. The connector returns text. 2. `ReplyParser.parse`. 3. `ReplyInvalid`: the engine retries with `retry_text` within the envelope's retry limit, then the function reports failure to Coordination (J2 builder rule). `dropped_keys`: a `reply_extra_keys` event. A connector failure never reaches the library.
**F5 Schema change.** Change a class; run `python -m sutra_app.library.export`; review the diff in `docs/schemas/`. A breaking diff needs `VERSION+1` and an `upgrade`, else `test_lib_schema_drift` fails.
**F6 J2 record save.** `J2Run.save(name, data)` calls `gate_record(name, data, mode)`, then J2's unchanged write. In `log` mode a rejection is an event; in `strict` mode it stops the run with the violations.

## 13. Endpoints and events

Router `api.py`, mounted by the server; `POST /api/schemas/validate` takes the write guard like every non-GET route (it stores nothing, the rule is by method): the header `X-Sutra-Token` checked by `Services.require_token`, handed to the router factory as a required `write_guard` argument, as for the connectors' router; GETs carry no token. Every error uses the orchestrator's envelope `{error:{code,message,details}}`; the prefix `/api/library` is J2's template library, which is why these routes live under `/api/schemas`. [S3-web-03] [S3-web-15]
- `GET /api/schemas` => `{"families":[{"family":"atom","versions":[1],"kinds":["atom"]}]}`
- `GET /api/schemas/{family}/{version}` => the JSON Schema, or 404 `{"error":{"code":"unknown_schema",...}}`
- `POST /api/schemas/validate` body `{"family","version"?,"payload"}` => 200 `{"ok":true,"sha256"}` or 422 `{"error":{"code":"validation",...,"details":{"violations":[{path,code,message}]}}}`; 401 without the header; payload over 1 MiB => 413 in the same envelope.

Events: `DomainEvent` (types.py) fixes three payload shapes. The atom lifecycle returns `atom.transitioned` events in `Transition.events`; the stores build `chart.changed` (from a `ChartChangeResult`) and `node.state`. `chart.changed` data = `{revision, change_id, kind, added, moved, merged}`; `atom.transitioned` = `{atom_id, node_id, outcome, state}`; `node.state` = `{node_id, state}`. The store publishes them after commit; the server section maps them onto SSE (D10).

## 14. Tests (default suite: no model call, no network; files are prefixed `test_lib_` so basenames stay unique)

| File | Asserts |
|---|---|
| `test_lib_base.py` | config of Value and Record; rules 1 to 5 of 3.1; `evolve` re-validates; `kind` and `schema_version` literals; ABSTRACT not inherited |
| `test_lib_registry.py` | register, lookup, versions; duplicate; frozen; union adapter and discriminator; `upgrade` chain; export is deterministic |
| `test_lib_gate.py` | `Checked` unforgeable; canonical JSON and sha stable across key order; round trip; stages unknown, size, shape, cross (toy families and a toy cross rule); older `schema_version`; a `model_construct` instance cannot bypass |
| `test_lib_replies.py` | fences, `not_json`, `not_object`, enum case, dropped keys recorded, `retry_text` wording; the verbatim J2 cases of `extract_json` and `close_json`, tested once for the one copy that `engine/llm.py` re-exports and `connectors/jsonio.py` imports [S2-models-12] |
| `test_lib_transport.py` | toy classes only: `const` becomes `enum`; a union becomes `anyOf` with no `oneOf` or `discriminator`; recursion refused; a free-key dict raises `transport_dict` [S2-models-04]; optional fields; draft-07 shape (the real classes are checked in L5 and L7) |
| `test_lib_atom_ids.py` | `atom_sid` and `function_atom_id` results match `AtomId`; the sid is the first 10 hex digits of sha1 of `<run_id>:<node_id>`; no collision in 10000 ids; `overhead_atom_id` matches `AtomId`, repeats for one owner and differs between owners [S2-models-10] [S4-fnodes-07] [S4-fnodes-11] |
| `test_lib_org_chart.py` `test_lib_chart_change.py` | tables below; a 300-step seeded random walk keeps ids, aliases and function ids (285 of 300 steps applied in the prototype); `carry_links` loses no session; `apply_change` is pure |
| `test_lib_chart_transport.py` | `transport_schema(ChartChangeRequest)`: draft-07, no `oneOf` or `discriminator`, the `ops` items are `anyOf` of five closed objects each with a one-value `op` enum, every object has `additionalProperties` false, size under 4 KB, `is_transport_safe` true; a model with a free-key dict raises `transport_dict` [S2-models-04] |
| `test_lib_goal.py` `_department.py` `_evaluation.py` | tables below; J2 charter fixtures (`mock_charter`, J2:1689) validate; `_department` covers the three fields id, home_dir, ts_created [S2-models-14] |
| `test_lib_chat.py` | `MessageMeta` accepts every key of section 10 with open values and rejects an unknown key; `RunMessage` accepts J2 chat.jsonl lines (base keys id, t, who, text, step, calls, board_read plus the meta keys at top level) [S2-models-15] |
| `test_lib_atom.py` `_atom_lifecycle.py` `_atom_view.py` | tables below; sequences open-fail-fail-fail-abandon (code `verify_failed`) and open-fail-close; exits 1, 127 and 97; ledger rows (closed, verify_failed, abandoned, refused); `Atom.task_id`; the argument rules of the 14 registry checks; `Seen` (a differing `work` replaces `dispatch_kind` and the notes get "declared bash, did llm"; `model` fills an empty one); `atom_view` equals J2's `atom_view` on fixtures built once from J2 dicts; `ledger_row_from_view`: each terminal J2 status gives a valid `LedgerRow` [S2-models-06] [S4-fnodes-02] [S4-fnodes-03] [S4-fnodes-09] [S4-fnodes-11] |
| `test_lib_atom_display.py` | each stored state and `abandon_code` gives the table of docs/design/function-nodes.md section 6.2; an open atom at attempt 3 is `open`; abandon with code `verify_failed` gives a `verify_failed` `LedgerRow` whose `verify.exit_code` is not 0; an abandoned atom with another code gives `abandoned` [S4-fnodes-08] [S4-fnodes-11] |
| `test_lib_functions.py` `_workflow.py` | a valid sample per kind built from the cited J2 formats; invalid table; every reply class passes `is_transport_safe`; `to_j2`/`from_j2` round trip on `EXAMPLE_WORKFLOW` |
| `test_lib_node.py` | node family union; ids; the nine states per kind (a function node only the first five; root, department and division only idle, running, waiting_on_you, fault); `StructuralNode` `task_id` and `step_ref`; `check_graph` G1 to G5 on stored plus derived edges; `HANDOFFS` equals J2 `ROUTES` except coordination (adds the code hand-off to audit) and audit (identity only); the `FunctionNode` shape; `new_function_node` and `refresh_function_nodes`; the `FunctionSpecs` model validates a toy spec; `verify_refs` flags a missing reply kind (toy registry) [S2-models-02] [S2-models-03] [S3-web-04] [S4-fnodes-14] |
| `test_lib_function_specs.py` (L10) | `specs/function_specs.json` loads; `verify_refs` against the full registry; every `CheckRef` name is a `CheckTemplate` member and its argument count matches; every template opens without refusal for a sample `TurnInfo` of its kind; the `generic` template exists and names no check; `may_not` ≤ 20; `yields` is non-empty; every goal template is non-banal after filling; the seed `work_hint` values (priority/envelope `bash`, identity/answer `manual`, coordination/schedule `llm`) [S2-models-06] [S4-fnodes-02] [S4-fnodes-03] [S4-fnodes-11] |
| `test_lib_artifacts.py` `_rules.py` `_templates.py` | the 19 sections and 3 documents accept J2 fixtures and reject the table; transport schemas equal J2's for the 19 sections (shas from a one-time run of J2's `schema_sha` on a copy); `run_rules` parity with J2 on every `RULES` entry; `RuleSpec` rejects what `rule_problems` rejects; template checks and `generic_drift` parity |
| `test_lib_records.py` | catalogue complete; `gate_record` modes; the shipped cross rules against the real families; the seed `FunctionSpecs` (`specs/function_specs.json`) verify against the full registry; AST scan of the engine for chat meta keys against `MessageMeta` [S2-models-15]; golden run: every JSON file of one mock-mode engine run validates (skipped until the engine package exists) |
| `test_lib_api.py` `_schema_drift.py` `_write_paths.py` | router shapes at `/api/schemas` with the ORCH error envelope, and 401 on `POST /api/schemas/validate` without the header [S3-web-03] [S3-web-15]; `docs/schemas/` equals a fresh export; AST: the files listed in `tests/library/write_paths.txt` (one path per line: `sutra_app/orchestrator/{chart,chats,atoms,usage,graph,tasks,departments,nodes}.py`) must exist, and every public `put*/insert*/append*/save*/upsert*/post*/record*/apply*` method in them has a `Checked[...]` parameter unless it is in `tests/library/write_allowlist.txt` (the verb list is wide because the orchestrator's write methods are `ChartStore.apply`, `GraphStore.put_node`, `ChatStore.post`, `AtomStore.upsert` and `UsageStore.record`) [S2-models-01] |
| `test_lib_engine_parity.py` (skipped when `sutra_app.engine` is not importable) | per artifact model the `transport_schema` sha equals the engine's after the declared library changes (`const` as `enum`, `anyOf`, no recursion); the valid/invalid verdict agrees on the shared corpus except the entries of `tests/library/parity_allowlist.json` (for example `required: "true"`); `run_rules` gives identical results on every `RULES` entry; `certainty_zone` agrees on all signal combinations; `extract_json` and `close_json` are the same objects in `engine.llm` and `connectors.jsonio` [S2-models-12] |
| `test_lib_live_transport.py` (marker `live`, only with `SUTRA_LIVE=1`) | runs the real `claude -p --json-schema` with `transport_schema("priority", kind="price")` and parses the reply with `ReplyParser`; proves the corrected schema (`const` as `enum`) is accepted `[U]` until run; `test_chart_change_request_native`: 5 trials per CLI through `ClaudeConnector.call_json` and `CodexConnector.call_json` with `transport_schema(ChartChangeRequest)`, a six-node chart and the request "merge Leads into Quotes and add a Support team"; it passes when `how == "native"` and the reply validates in at least 4 of 5 trials on each CLI, and it settles union or flat (section 17, risk 2) [S2-models-04] |

Invalid inputs each model must reject (observed in the prototype or on J2's own code unless marked `[U]` or tagged with a settlement id, which counts as `[U]` until its test runs):

| Model | Invalid input | Rejected with |
|---|---|---|
| any Value | unknown key `"colour"` | `extra_forbidden` |
| any int / bool | `"1"`, `1.0`, `true` for an int; `"true"` for a bool | `int_type`; `bool_type` |
| any family | `kind` not registered | `union_tag_invalid` (family) or `literal_error` (one class) |
| Record | `schema_version: 2` on a v1 class; version 0 with no `upgrade` | `value_error` (shape); `schema_version` (shape) |
| registry | same (family, version, kind) with another class; register after freeze | `RegistryError` duplicate; frozen |
| gate | unknown family; payload over 1 MiB; hand-built `Checked(...)`; failing cross rule | stage `unknown`; `size`; `TypeError`; `cross` |
| parser | text `I cannot do that`; text `[1,2]`; `"decision":"MAYBE"` | `not_json`; `not_object`; `shape` with `retry_text` |
| transport | a recursive class | `transport_recursion` (a union is not an error: it becomes `anyOf`) |
| transport | a free-key dict | `transport_dict` [S2-models-04] |
| OrgChart | department without `functions`; function ids not `<dept>.<fn>`; one function missing | `value_error`; `value_error`; `missing` (path `functions.audit`) |
| OrgChart | division carrying `functions`; two roots; no root | `value_error` (each) |
| OrgChart | duplicate id; node without a parent edge; node with two parents | `value_error` (each) |
| OrgChart | cycle (`aa`<->`bb`); edge to a missing node; division under root; department under division | `value_error` (each) |
| OrgChart | extra key; `revision: 0`; `revision: "1"`; id `Sales`; `kind: "org"` | `extra_forbidden`; `greater_than_equal`; `int_type`; `string_pattern_mismatch`; `literal_error` |
| ChartChange (model) | `kind` add but a move op; `reuse` without `reuses`; a Ref used before it is added; a Ref added twice; rename with neither name nor purpose; 9 ops; ref `sales` without `$` | `value_error` (five); `too_long`; `string_pattern_mismatch` |
| ChartChange (apply) | stale `base_revision`; new division named ` LEADS ` beside `Leads` | `stale_base`; `duplicate_name` |
| ChartChange (apply) | department under department; parent id `ghost-1`; reuse of `ghost-1` | `bad_parent_kind`; `unknown_node`; `unknown_node` |
| ChartChange (apply) | move a division into itself or its subtree; move a department; merge a department | `cycle`; `move_not_division`; `merge_not_division` |
| ChartChange (apply) | merge into own descendant; merge self; duplicate sources; two bad ops in one change | `cycle`; `bad_merge`; `bad_merge`; both reported (`unknown_node`, `merge_not_division`) |
| ChartChange (apply) | split part under another parent; moved child not a child; target outside parts; rename root; division moved under root | `bad_split_part`; `not_a_child`; `bad_target`; `unknown_node`; `bad_parent_kind` |
| GoalDraft | `core` length differs from `done_when`; `done_when: []`; duplicate items; `site_name: ""` | `value_error`; `too_short`; `value_error`; `string_too_short` |
| Department | the dropped keys `name`, `goal`, `budget`, `run_ids`; an empty `home_dir` | `extra_forbidden`; `string_too_short` [S2-models-14] |
| Finding, ResultEvaluation | PASS with empty note; `pass` contradicts verdict; `all_pass` lies; duplicate finding ids; verdict `OK` | `value_error` (four); `literal_error` |
| price | REFUSE with workflows; COUNTER with none; `money_limit: 0` | `value_error` (each) |
| envelope_check | HOLD with next Identity | `value_error` |
| schedule | `order` repeats an id; empty `rule` | `value_error`; `string_too_short` |
| intake | enough with next Requester; not enough without questions; 5 questions | `value_error`; `value_error`; `too_long` |
| Atom | closed without passing last results; abandoned with blank reason; refused with attempt 1; open with `ts_closed` | `value_error`; `string_too_short`; `value_error`; `value_error` |
| Atom | open with no checks; open with goal `done`; results count differs from `attempt`; `attempt: 4` | `value_error` (`verify_missing`); `value_error` (`goal_banal`); `value_error`; `less_than_equal` |
| Atom | id `atom-1`; state `done`; extra key; template `lint` | `string_pattern_mismatch`; `literal_error`; `extra_forbidden`; `literal_error` |
| Atom | `abandon_code` on an open atom; `abandon_code: "crash"` | `value_error`; `literal_error` [S4-fnodes-08] |
| Check | `reply-valid` with one arg; `answer-recorded` with no arg; `turn-posted` with an arg; an unknown registry name | `value_error` (three); `literal_error` [S4-fnodes-02] |
| LedgerRow | `verify_failed` with exit 0 or without a reason; `closed` with exit 1; `abandoned` with a `verify` | `value_error` (each) [S4-fnodes-08] |
| open_atom | goal `done`; empty goal; other atom open; `grep-count` min 0; blank relevance; `..` in a path; path `site` with `touches: ["site/"]`; `named-test` without pin; supersedes a live atom | refused: `goal_banal`; `goal_missing`; `atom_still_open`; `vacuous_check`; `relevance_empty`; `dotdot`; `outside_envelope`; `pin_missing`; `bad_supersedes` |
| close_atom | closing a closed or abandoned atom; a 4th attempt; blank abandon reason | refused: `not_open`; `attempts_exhausted`; `reason_missing` |
| close_atom | pinned test changed; runner missing (exit 127) | `verify_failed` with exit 97; `verify_failed` with exit 127 |
| FunctionNode | id not `<dept>.<kind>`; no department; state `filed` on a function node; waiting without `wait_on` | `value_error` (each) [S2-models-03] [S4-fnodes-14] |
| StructuralNode | step node without `task_id` or `step_ref`; `step_ref` not `task`, `W-<n>` or `team:<role>`; a department with `step_ref`; state `filed` on a department | `value_error` (each) [S2-models-02] [S2-models-03] |
| Node | unknown kind `treasury` | `union_tag_invalid` |
| GraphEdge | handoff audit->priority in one department; an edge of a stored kind without `source`; from equals to | `value_error` (each) [S2-models-02] |
| check_graph | a department's audit node missing; a chart node without its structural node; `contains` edges differ from the chart; `edge_ids` out of step | `G2`; `G1`; `G4`; `G5` |
| Workflow | no steps; no outputs; `covers: [0]`; empty `completion_check`; duplicate step ids; step depends on a later step; AI step with bash dispatch; task workflow with an AI step; department workflow with an assignment step; step kind `human`; `failure_policy: "retry"` | `too_short`; `too_short`; `greater_than_equal`; `string_too_short`; `value_error` (five); `union_tag_invalid`; `literal_error` |
| AssignmentStep | `follows: "T-9"`; 5 entries in `depends_on` | `string_pattern_mismatch`; `too_long` [S2-models-13] |
| artifact sections | `required: "true"`; extra key; website section without html or head; `goals: "G1"` | `bool_type`; `extra_forbidden`; `value_error`; `list_type` |
| artifact rules | first goal id `G2`; palette colour `blue`; anchor `hero` | `run_rules` pass False with J2's evidence text |
| RuleSpec | unknown rule type; `ids_sequential` without `prefix`; `ref_exists` target `foo.x` | `value_error` (J2's `rule_problems` wording); a path outside the template is a `Template` error |

## 15. Work packages (one per file group; no file in two packages; `scripts/py` = the main checkout's venv Python, which also works inside a worktree)

| Id | Title | Owns | Depends | Acceptance |
|---|---|---|---|---|
| L1 | Foundations, registry, gate, replies, schema export, id helpers (overhead_atom_id) [S2-models-10] [S4-fnodes-07] | `sutra_app/library/{__init__,types,base,registry,gate,replies,export}.py`, `tests/library/{conftest,test_lib_base,test_lib_registry,test_lib_gate,test_lib_replies,test_lib_transport,test_lib_atom_ids}.py` | none | `scripts/py -m pytest tests/library/test_lib_base.py tests/library/test_lib_registry.py tests/library/test_lib_gate.py tests/library/test_lib_replies.py tests/library/test_lib_transport.py tests/library/test_lib_atom_ids.py -q` |
| L2 | Org chart and chart changes [S2-models-04] | `sutra_app/library/org_chart.py`, `tests/library/{factories_org,test_lib_org_chart,test_lib_chart_change,test_lib_chart_transport}.py` | L1 | `scripts/py -m pytest tests/library/test_lib_org_chart.py tests/library/test_lib_chart_change.py tests/library/test_lib_chart_transport.py -q` |
| L3 | Goal, Department, Evaluation, chat message meta [S2-models-15] | `sutra_app/library/{goal,department,evaluation,chat}.py`, `tests/library/test_lib_{goal,department,evaluation,chat}.py` | L1 | `scripts/py -m pytest tests/library/test_lib_goal.py tests/library/test_lib_department.py tests/library/test_lib_evaluation.py tests/library/test_lib_chat.py -q` |
| L4 | Atom, lifecycle, ledger row, cards, atom/1 view, display state (abandon_code, Seen, 14 check names, verify_failed log row, ledger_row_from_view) [S2-models-06] [S4-fnodes-08] | `sutra_app/library/atom.py`, `tests/library/{factories_atom,test_lib_atom,test_lib_atom_lifecycle,test_lib_atom_view,test_lib_atom_display}.py`, `tests/library/fixtures/atom/` | L1 | `scripts/py -m pytest tests/library/test_lib_atom.py tests/library/test_lib_atom_lifecycle.py tests/library/test_lib_atom_view.py tests/library/test_lib_atom_display.py -q` |
| L5 | Workflow, Step and the five function models | `sutra_app/library/{workflow,functions}.py`, `tests/library/{test_lib_workflow,test_lib_functions}.py` | L1 L3 L4 | `scripts/py -m pytest tests/library/test_lib_workflow.py tests/library/test_lib_functions.py -q` |
| L6 | Node family, graph edges, function-spec plug-in (FunctionNode: goal, task string, context, open_atom, atom_count, wait_on, stats, spec_version; refresh_function_nodes; HANDOFFS table of S3-web-04) [S3-web-04] [S4-fnodes-14] | `sutra_app/library/node.py`, `tests/library/{factories_node,test_lib_node}.py` | L1 L2 L4 | `scripts/py -m pytest tests/library/test_lib_node.py -q` |
| L7 | Artifact models, rules as data, templates [J2 SYNC 2026-11-04: baseline 33aeeda, read docs/design/j2-sync.md] | `sutra_app/library/artifacts/*`, `sutra_app/library/templates.py`, `tests/library/test_lib_{artifacts,rules,templates}.py`, `tests/library/fixtures/artifacts/` | L1 | `scripts/py -m pytest tests/library/test_lib_artifacts.py tests/library/test_lib_rules.py tests/library/test_lib_templates.py -q` |
| L8 | Integration: J2 record catalogue and gate hook, schema API at /api/schemas (guarded POST, ORCH error envelope), generated schemas [S2-models-01] [S2-models-12] [S3-web-03] [S3-web-15] [J2 SYNC 2026-11-04: baseline 33aeeda, read docs/design/j2-sync.md] | `sutra_app/library/{records,api,all}.py`, `docs/schemas/`, `tests/library/test_lib_{records,api,schema_drift,write_paths,live_transport,engine_parity}.py`, `tests/library/{write_allowlist.txt,write_paths.txt,parity_allowlist.json}` | L1 to L7, L10 | `scripts/py -m sutra_app.library.export --check`; `scripts/py -m pytest tests/library -q`; `scripts/py -m pytest tests/library/test_lib_engine_parity.py -q` |
| L9 | J2 wire documents (after the engine package exists) | `sutra_app/library/wire.py`, `tests/library/test_lib_wire.py` | L1 L4 L5 | `scripts/py -m pytest tests/library/test_lib_wire.py tests/library/test_lib_records.py -q` |
| L10 | Function specs: seed data (templates with named checks, yields, work hints) and its tests [S2-models-05] [S4-fnodes-02] | `sutra_app/library/specs/function_specs.json`, `tests/library/test_lib_function_specs.py` | L1 L4 L5 L6 | `scripts/py -m pytest tests/library/test_lib_function_specs.py -q` |

Each package also owns its hand-over note `docs/notes/<id>.md` (a rule of `scripts/plan_tools.py`, which also forbids owning a protected chassis file such as `pyproject.toml`). The parity test skips itself while `sutra_app.engine` is not importable, and the live test file skips itself without `SUTRA_LIVE=1`; the on-request command (D8, never part of an acceptance run) is `SUTRA_LIVE=1 scripts/py -m pytest tests/library/test_lib_live_transport.py -q`. [S2-models-12] [S2-models-04]

Order: L1 first; then L2, L3, L4, L7 in parallel; then L5 and L6; then L10; then L8; L9 last. The whole library gate is `scripts/gate.sh tests/library`. [S2-models-05]

## 16. Decision proposals and what the diagram shows

| Id | Decision | Why | Rejected | Diagram |
|---|---|---|---|---|
| DL1 | Every structure is a closed pydantic class in three tiers (Value, Record, Payload): strict, frozen, `extra="forbid"`, bounded, JSON-native types, `evolve` as the only update | The owner asked for hardened closed models checked at every write (GEN:116-117); J2's artifact models are lax and not frozen (JM:48-52) | lax coercion; mutable models with `validate_assignment` (in-place list edits slip through); dataclasses or TypedDict | badge on the "Interface library" box, label "closed · strict · frozen" |
| DL2 | One registry keyed (family, version) with `kind` as discriminator; schemas exported to `docs/schemas/` and diffed in tests; a breaking change is a new version with an `upgrade` | Lookup by name and version is required; drift must be visible; J2 already versions its schemas (`atom/1`, `map/1`, `board/1`) | version-less schemas; schemas generated only at run time | same box, label "registry · name/version · schema export" |
| DL3 | One write gate: stores take only `Checked` (strict validation, cross rules, canonical JSON, sha256, round trip), enforced by an AST test | "Checked at every write" must not depend on each store remembering; one gate is one place to test | validation inside each store; pydantic validation without cross rules | the arrow "validates records" (GEN:222), label "Gate.check at every write" |
| DL4 | Model output is parsed tolerantly (fences, enum case, unknown keys dropped and recorded) and then validated strictly; the transport schema is generated from the same class, with `const` kept as a one-value `enum` and a union rewritten as `anyOf` | J2 reads replies with `.get` so extra keys never failed a turn (fidelity, D4); J2's transport dropped `const` (observed), which would make a union unreadable | rejecting unknown keys in raw model text; sending `oneOf` with a discriminator to `--json-schema` | connector layer, line "asks for structured JSON": add "schema from the model class" |
| DL5 | The org chart is one tree document with a revision. A change is one record, `ChartChange`, whose kind (reuse, add, rearrange) is derived from its ops and checked, never trusted. The model proposes ops with `$ref` placeholders and code assigns the ids. Rearrange = move or rename a division, merge or split divisions, possibly with adds. Ids are never reused; a merged-away id becomes an alias. A department is added with its five function node ids derived from one function, and cannot be moved or merged. Chat links are keyed by node id and carried by `carry_links` | Owner rules: one chart, reuse/add/rearrange on need, a moved node keeps its chat (GEN:122); a model that invents ids collides and loops, one request class gives the agent one schema | one chart per workflow (owner rule); three change classes the model must choose between; patch-style diffs that cannot prove "keeps ids"; moving departments (it would move five agentic nodes and their runs) | "One global org chart" box (GEN:84-107): badge on Rearrange, label "ids kept · 5 function nodes per department" |
| DL6 | Atom states are `open`, `closed`, `refused`, `abandoned`. `verify_failed` is derived, never stored: a failed try is a transition outcome and a final failure is stored `abandoned` with `abandon_code` `verify_failed` (`atom_display_state` reports it). `refused` is stored only for an open-time refusal and is also ledgered. One open atom per node. FN-3 and FN-16 (nothing is written) are superseded by S4-fnodes-05: a refusal is stored, ledgered and carded. [S4-fnodes-05] [S4-fnodes-08] | The plugin's transitions are open, close, refuse, abandon and ADR-038 says "open to closed or abandoned" (SA:14, HK:4-5); the owner lists four states | storing `verify_failed` as a state (against ADR-038; the plugin leaves the atom open); dropping `refused` | function cards (GEN:129-139), label "work atom: open · closed · refused · abandoned" |
| DL7 | `Node` is an abstract base with `StructuralNode` and `FunctionNode`; five concrete function children; function specifics enter as data (`FunctionSpecs`); a node holds its open atom id and an atom count, the atoms table is the list [S2-models-03]; edges are separate `GraphEdge` records; `check_graph` proves the graph mirrors the chart | Owner: a function is an agentic node with goal, task, context, atoms; the spec is final (docs/design/function-nodes-spec.json) [S2-models-08]; "nodes mirror the org chart" (GEN:121) | one Node class with a `function` string (no per-function reply binding); embedding atoms in nodes | "Workflow graph store" box (GEN:121), label "check_graph: mirrors the chart" |
| DL8 | `Workflow` and `Step` become abstract bases at two levels: a `TaskWorkflow` of `AssignmentStep`s (the chat agent's plan across departments, the graph's step nodes) and a `DeptWorkflow` (`Proposed`, `Registered`) of `AIStep`/`CodeStep`s that carry work atoms. `Template` is ported as is. `failure_policy` uses ADR-011's five-set with default `escalate` | The owner names Workflow, Step, Template as base classes (GEN:114) and draws steps as graph nodes (GEN:67); J2 has only Template and keeps workflows as dicts; the Native `primitives/workflow.md` and `step.md` are not in the plugin mirror `[U]` | keeping workflow dicts; a Step child per verb (J2 says atoms are not split by verb, AS:52-54); one level only | same box, badge on the line "Base classes: Workflow · Step · Template" |
| DL9 | J2 artifact models and rules are ported into the library, strict and frozen, registered as payloads `artifact.<kind>.<section>`; rules stay data (`RuleSpec`) checked at import. The library owns the definitions; `extract_json` and `close_json` have one copy (`replies.py`) used by `engine/llm.py` and `connectors/jsonio.py`; the engine keeps its vendored `j2_artifact_models.py`, `j2_rules.py`, `j2_template_lib.py` and `certainty_zone` as the runtime copy, bound to the library by `test_lib_engine_parity.py` until the switch of S2-models-12 [S2-models-12] | "Artifact models + rules as data" (GEN:115); observed to run on pydantic 2.14 | rewriting them; two permanent copies with only a drift test; the engine importing the strict models at once [S2-models-12] | chip "Artifact schemas · pydantic shape + rules" (GEN:151): badge |
| DL10 | J2 run files are checked on `save()` through a file-to-family catalogue, `log` mode first, `strict` after a golden-run test; chat meta is a closed key set with open values | D4 keeps the engine's dict code; hardening must not break J2 behaviour; late-set keys must be found by a test, not by a crash | rewriting J2Run state as models; unchecked saves | box "Department records" (GEN:140), label "records checked on save" |

## 17. Risks

1. **Function-node names.** Settled in S2-models-08 and S4-fnodes-01; the final spec (`docs/design/function-nodes-spec.json`, built into `docs/design/function-nodes.md`) is applied. If the spec moves, only the `FunctionSpec` fields, `load_function_specs` and the L10 data change. [S2-models-08] [S4-fnodes-01]
2. **Strictness against real model output.** Closed classes may reject replies J2 accepted. Mitigated by the tolerant parser, per-class transport schemas and `retry_text`. Only the `live` test `test_lib_live_transport.py` proves the Claude CLI honours `const` as `enum` and `anyOf` of objects `[U]`. Decision: union. Live check `test_chart_change_request_native` (`SUTRA_LIVE=1`): 5 trials per CLI via `ClaudeConnector.call_json` and `CodexConnector.call_json` with `transport_schema(ChartChangeRequest)` and a six-node chart; pass = `how` native and a valid reply in at least 4 of 5 on each CLI. On failure set `CHART_OPS_TRANSPORT = "flat"` in `org_chart.py` and add `ChartOpFlat` (op plus optional fields; `flat_to_ops` raises `bad_op` on a missing or surplus field). Until then the net is the connector's prompted path on a structured-output error (remembered per schema sha for the process, so at most one wasted call) and `ReplyParser`, which validates with the same union either way. [S2-models-04]
3. **J2 record fidelity.** Closed models for vendored dicts may miss keys set late (workflow, goal, conflict, chat meta). `log` mode, the golden-run test and the AST key scan are the safety net. `Evaluation.mechanical` and `Atom.details` stay open blobs on purpose.
4. **Frozen is shallow.** Lists can be edited in place; the gate re-validates at every write and the AST test checks write paths.
5. **pydantic pin.** ≥ 2.11 is needed; pyproject says ≥ 2.8.
6. *Removed [S2-models-10]:* the two atom id forms (`a-<sid>-<nn>` for a function atom, `W-n.aK` for a J2 workflow atom) are settled, one class of atom each, no third scheme.
7. *Removed [S2-models-10]:* refused atoms are stored, ledgered and carded as a declared addition to atom-ledger-v0.3 (DL6).
8. *Removed [S2-models-11]:* the chat section accepts archived sessions under a node (`ChatStore.apply_links`, C11).
9. **Native `workflow.md` and `step.md` are unavailable**: `Step.on_failure` and the default policy are unverified `[U]`; a per-step timeout is omitted.
10. **Import order.** `templates.py` imports `artifacts` (its models and `RULES`), never the reverse; `all.py` imports artifacts before templates. The library imports nothing from engine, connectors, orchestrator or ui. [S2-models-12]
11. **J2 "could not run"** (neither failed nor verified, AS:36) is stored here as exit 127 and consumes an attempt (plugin behaviour, SA:335-337), so the atom/1 view may show `verify_failed` earlier than J2 would.
12. **Size.** About 60 classes; import cost is small, but `export` and the drift test must stay in the default suite so schemas never go stale.

## 18. Reconciliation with sibling sections (state at about 00:50, for the consolidator)

Settled by docs/design/settlements/S2-models.md (S2-models-01 to 15). The orchestrator, engine and connectors import library models and define none of them. The web-layer points are settled in S3-web.md (S3-web-03, 04, 08, 15) and the function-node points in S4-fnodes.md (S4-fnodes-01 to 14), which wins where it names a superseded id; the bracketed ids in this file mark where each landed. [S2-models-01]
