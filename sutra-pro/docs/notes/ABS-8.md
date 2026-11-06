# ABS-8 as built

`Router.choice_source` (session id -> persisted choice, None by default) is read by `_plan` when no pin was given, so the org chat agent (`AsyncConnector` sets `RouteContext.session_id`), one-shot and chat calls follow the chat's choice. A choice that cannot run falls back to the policy order and the Router emits `connector.choice_unavailable {session_id, wanted, reason, used}`; a failing source never breaks a call.
`orchestrator/chat_choice.py` was NOT created: the logic is two small riders (`wiring` sets `router.choice_source = ChatChoices(db).get`; `tasks._run_spec` sets `RunSpec.connector` from the department chat's `pinned` when the settings connector is not the offline stub). The spec's `runs.py` rider is not needed (the spec is built in `tasks.py`; `runs.py` only passes it to the engine). J2 files are not touched.
A pinned run uses that one provider only (the Router's restrict mode); there is no fallback inside such a run.
Tests: `tests/orchestrator/test_chat_choice.py`.
