"""The Interface library: closed models, the registry and the one write gate.

Every structure that is stored, sent over SSE, returned by an API or asked of a model is an instance of a class defined
here. Importing a module registers its classes (`@record` or `REGISTRY.register_payload`); import
`sutra_app.library.all` for the full registry. This package imports nothing from the engine, the connectors, the
orchestrator or the UI; they import it.

    types      scalars, id patterns, FUNCTIONS, Violation, DomainEvent, the id helpers (atom_sid, function_atom_id,
               overhead_atom_id, function_node_id)
    base       Value, Record, canonical_json, unbounded_fields and aliased_fields (the checks of design rules 3 and 7)
    registry   ModelRegistry, REGISTRY, record, transport_schema, reply_schema, is_transport_safe
    gate       Gate, GATE, Checked, GateError, the shipped cross rules
    replies    ReplyParser, ReplyInvalid, normalise_enums, extract_json, close_json
    export     python -m sutra_app.library.export [--check]
"""
