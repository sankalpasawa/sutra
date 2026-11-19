"""GmailClient interface, the fixture-backed MockClient, the retry wrapper and the client factory.

Everything above this interface (parse, store, rules, audit, retry) is shared by mock and live, so mock
tests exercise the same code that runs live (architecture D-1).
"""
import copy
import json
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeVar

import errors
from errors import PulseError, TransientError, HistoryExpired, MessageGone

T = TypeVar("T")
METADATA_HEADERS = ["From", "To", "Cc", "Subject"]


class GmailClient(Protocol):
    """Bound to one mailbox at construction."""

    def get_profile(self) -> dict: ...

    def list_messages(self, query: str | None, page_token: str | None, max_results: int) -> dict: ...

    def get_message(self, msg_id: str, fmt: Literal["metadata", "full"]) -> dict: ...

    def list_history(self, start_id: str, page_token: str | None, max_results: int) -> dict: ...


class MockClient:
    """Serves fixtures/inbox.json in Gmail API response shape. Scenario overrides come from scenarios.json.

    Gmail search syntax in `query` is recorded but not evaluated: every list returns the whole fixture inbox.
    """

    def __init__(self, mailbox: str, fixtures_dir: Path, scenario: str = "default"):
        self.mailbox = mailbox
        fixtures_dir = Path(fixtures_dir)
        self.inbox = json.loads((fixtures_dir / "inbox.json").read_text(encoding="utf-8"))
        scenarios = json.loads((fixtures_dir / "scenarios.json").read_text(encoding="utf-8"))
        self.scenario = scenarios[scenario]
        self.page_size = int(self.inbox.get("page_size", 100))
        self.calls = []
        fail = self.scenario.get("fail")
        self._fail_method = fail["method"] if fail else None
        self._fail_statuses = list(fail["statuses"]) if fail and isinstance(fail["statuses"], list) else None
        self._fail_always = (int(fail["statuses"].split(":", 1)[1])
                             if fail and isinstance(fail["statuses"], str) else None)

    def _enter(self, method: str, **args) -> None:
        self.calls.append((method, args))
        s = self.scenario
        if "raise" in s:
            raise RuntimeError("mock scenario raised an unexpected error")
        if "auth_error" in s:
            raise errors.map_refresh_error(s["auth_error"])
        if "http_error" in s:
            raise errors.map_http_error(s["http_error"]["status"], s["http_error"].get("reason", ""))
        if self._fail_method in ("*", method):
            if self._fail_always is not None:
                raise TransientError(self._fail_always)
            if self._fail_statuses:
                raise TransientError(self._fail_statuses.pop(0))

    def call_names(self) -> list:
        return [c[0] for c in self.calls]

    def get_profile(self) -> dict:
        self._enter("get_profile")
        prof = dict(self.inbox["profile"])
        if "profile_email" in self.scenario:
            prof["emailAddress"] = self.scenario["profile_email"]
        return prof

    def _page(self, ids: list, page_token, max_results: int):
        start = int(page_token or 0)
        n = max(1, min(max_results, self.page_size))
        chunk = ids[start:start + n]
        nxt = str(start + n) if start + n < len(ids) else None
        return chunk, nxt

    def list_messages(self, query, page_token, max_results):
        self._enter("list_messages", query=query, page_token=page_token, max_results=max_results)
        ids = [m["id"] for m in self.inbox["messages"]]
        chunk, nxt = self._page(ids, page_token, max_results)
        by_id = {m["id"]: m for m in self.inbox["messages"]}
        out = {"messages": [{"id": i, "threadId": by_id[i]["threadId"]} for i in chunk],
               "resultSizeEstimate": len(chunk)}
        if nxt:
            out["nextPageToken"] = nxt
        return out

    def get_message(self, msg_id, fmt):
        self._enter("get_message", msg_id=msg_id, fmt=fmt)
        msg = next((m for m in self.inbox["messages"] if m["id"] == msg_id), None)
        if msg is None:
            raise MessageGone()  # same as a live 404 on messages.get
        msg = copy.deepcopy(msg)
        if fmt == "metadata":
            wanted = {h.lower() for h in METADATA_HEADERS}
            p = msg["payload"]
            msg["payload"] = {"mimeType": p.get("mimeType", ""),
                              "headers": [h for h in p.get("headers", []) if h["name"].lower() in wanted]}
        return msg

    def list_history(self, start_id, page_token, max_results):
        self._enter("list_history", start_id=start_id, page_token=page_token, max_results=max_results)
        if self.scenario.get("history_status") == 404:
            raise HistoryExpired()
        ids = self.scenario.get("history_added", self.inbox["history"]["added"])
        chunk, nxt = self._page(ids, page_token, max_results)
        by_id = {m["id"]: m for m in self.inbox["messages"]}
        # Ids not in the inbox stand for messages deleted since they were added (scenario history_deleted).
        out = {"history": [{"id": str(1600 + n), "messagesAdded": [{"message": {
                   "id": i, "threadId": by_id.get(i, {}).get("threadId", "thr-gone"),
                   "labelIds": by_id.get(i, {}).get("labelIds", [])}}]}
                           for n, i in enumerate(chunk)],
               "historyId": self.inbox["profile"]["historyId"]}
        if nxt:
            out["nextPageToken"] = nxt
        return out


def with_retry(fn: Callable[[], T], sleep: Callable[[float], None], attempts: int = 5,
               base: float = 1.0, cap: float = 32.0) -> T:
    """Retry TransientError (429 / 5xx / network): delays base, 2*base, ... capped at cap; no jitter (spec R-11)."""
    last = None
    for n in range(1, attempts + 1):
        try:
            return fn()
        except TransientError as e:
            last = e
            if n < attempts:
                sleep(min(base * 2 ** (n - 1), cap))
    if last.kind == "network":
        raise PulseError("network_error",
                         f"Could not reach Google after {attempts} attempts. Check this machine's network "
                         "connection (and any proxy or firewall), then try again.")
    if last.status == 429:
        raise PulseError("rate_limited",
                         f"Gmail kept rate-limiting this request (HTTP 429) after {attempts} attempts. Try again later.")
    raise PulseError("server_error",
                     f"Gmail kept failing with HTTP {last.status} after {attempts} attempts. Try again later.")


def make_client(cfg, mailbox: str) -> GmailClient:
    if cfg.mock:
        from config import FIXTURES
        return MockClient(mailbox, FIXTURES, cfg.scenario)
    import live_client  # stdlib-only module; it imports Google libraries itself, lazily
    return live_client.LiveClient(mailbox, cfg.sa_key_path)
