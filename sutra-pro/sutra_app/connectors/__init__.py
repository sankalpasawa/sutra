"""The connector layer: every model call goes through here (D7, D27-D38).

Built by the work packages CN-1 to CN-9, in this order of dependence:

    errors     ConnectorError tree on the engine's ModelError (code, kind, retryable, fallback_ok, user_message)
    models     the shared pydantic models (Usage, TurnResult, RouteContext, ConnectorConfig, ...)
    env        PASS_NAMES, the one environment allowlist of the project, and child_env
    process    ProcessRunner: own process group, stdin writer, line reader, deadlines, cancel ladder
    jsonio     reply parsing and validation, repair prompt, prune_nulls (extract_json/close_json are the library's)
    schema     to_json_schema, strict_schema (Codex), minimal_validate, example_from_schema

`Router`, `build_router` and `make_port` come from later packages (router.py, factory.py, engine_port.py). They are
resolved on first use, so this package imports with only the modules that exist, and `from sutra_app.connectors import
Router` works as soon as router.py is merged, with no change here.
"""
from importlib import import_module
from importlib.util import find_spec

from .errors import (
    ERROR_CLASSES, AccountBlockedError, CallCancelledError, CallTimeoutError, ConnectorError, CliMissingError,
    CrashedError, EmptyReplyError, EnvelopeExceededError, FlagUnsupportedError, InvalidJsonError, InvalidRequestError,
    ModelNotFoundError, NoProviderError, NotSignedInError, OverloadedError, PolicyInvalidError, ProtocolError,
    ProviderError, QuotaError, RateLimitedError, ReplyTruncatedError, ServerError, SessionLostError, StructuredError,
    error_for_code,
)

_ERRORS = [
    "ConnectorError", "NoProviderError", "CliMissingError", "FlagUnsupportedError", "NotSignedInError",
    "AccountBlockedError", "QuotaError", "RateLimitedError", "OverloadedError", "ServerError", "CallTimeoutError",
    "CrashedError", "ProtocolError", "ProviderError", "ModelNotFoundError", "SessionLostError", "EmptyReplyError",
    "StructuredError", "InvalidJsonError", "ReplyTruncatedError", "InvalidRequestError", "EnvelopeExceededError",
    "CallCancelledError", "PolicyInvalidError", "ERROR_CLASSES", "error_for_code",
]

# name -> the module (of this package) that defines it
_LATER = {"Router": "router", "build_router": "factory", "make_port": "engine_port"}


def __getattr__(name: str):
    module = _LATER.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if find_spec(f"{__name__}.{module}") is None:
        raise AttributeError(f"{name} is defined in {__name__}.{module}, which is not part of this build yet")
    value = getattr(import_module(f"{__name__}.{module}"), name)
    globals()[name] = value
    return value


__all__ = _ERRORS + [n for n, m in _LATER.items() if find_spec(f"{__name__}.{m}") is not None]
