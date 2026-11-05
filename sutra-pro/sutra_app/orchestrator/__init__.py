"""The orchestrator: the chat agent, the one global org chart, the workflow graph, chats, atoms, usage, tasks and the API.

The server is the only SQLite writer (D16). This package imports the library (models, gate), the engine's contracts
(`sutra_app.engine.spec`, `events`, `paths`) and, from later packages, the connectors; none of them imports it.
Foundation modules (ORCH-1): errors, ids, redact, textutil, db, schema, records, models, services, api.deps.
"""
