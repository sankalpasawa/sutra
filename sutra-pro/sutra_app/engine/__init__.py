"""The department runtime: J2's engine, one process per run, speaking to the server only through files (D4, D9, D14).

This file imports nothing on purpose. The host sets the environment (`EngineSettings.to_env()`, the `J2_*_DIR` paths) and
calls `llm.configure(...)` BEFORE the vendored `j2` module is imported, because J2 reads its flags and `llm.MOCK` at
import time. Modules written for the first work package (E0):

    port       the model seam: CallTag, Allowance, PortSpec, CompletionRequest/Result, ModelPort, the ModelError family
    llm        J2's `llm` API over a ModelPort: ask, tagged, bind_atom, configure, ScriptedPort (J2's mock mode)
    hooks      EngineHooks, NullHooks, EventHooks and the turn/call records the function-node layer reads
    events     the eight run-event builders, EventWriter (events.jsonl, trace.jsonl) and EventUsageSink
    spec       TaskSpec (task.json), EngineSettings and how the three settings layers are merged
    paths      where a department's and a run's files live, the `.env` loader, pid_alive
    features   FEATURES: engine.md section 8 as data

Later packages add the vendored J2 modules (E1), the views (E2), the host process (E3), the FastAPI routes (E4) and the
function-node layer `fnodes/` (E6, E8).
"""
