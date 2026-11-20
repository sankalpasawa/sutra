"""The node meter (MAN-9, D272): what one node of a project has spent across ALL its calls (calls, dollars, wall time), checked before every call, and the allowance each call may still use. A run with
no node has no meter and sends the allowance it always sent: none."""
import pytest

from sutra_app.engine import llm
from sutra_app.engine.llm import NodeCapReached, NodeMeter
from sutra_app.engine.port import CompletionResult, ModelError, PortInfo, PreflightResult

pytestmark = pytest.mark.usefixtures("clean_env", "llm_reset")


class Port:
    def __init__(self, usd=0.25, fail=None):
        self.requests, self.usd, self.fail = [], usd, fail

    def describe(self):
        return PortInfo(provider="claude", model="sonnet", mock=False)

    def preflight(self):
        return PreflightResult(ok=True, message="ok", providers=[])

    def complete(self, req, on_progress=None):
        self.requests.append(req)
        if self.fail:
            raise self.fail
        return CompletionResult(text="reply", usd=self.usd, provider="claude", model="sonnet")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def ask():
    return llm.ask("sys", "user", None)


def test_with_no_meter_the_allowance_is_none_as_it_always_was():
    port = Port()
    llm.configure(port, mock=False)
    assert ask() == "reply" and port.requests[0].allowance is None


def test_the_calls_cap_is_cumulative_and_the_call_past_it_is_never_made():
    port, meter = Port(), NodeMeter(max_calls=3)
    llm.configure(port, mock=False, meter=meter)
    for _ in range(3):
        ask()
    with pytest.raises(NodeCapReached) as stopped:
        ask()
    assert stopped.value.which == "calls" and len(port.requests) == 3 and meter.reached == "calls" and isinstance(stopped.value, ModelError) and stopped.value.retryable is False
    assert [r.allowance.max_calls for r in port.requests] == [3, 2, 1]                          # what one request may still use shrinks


def test_the_dollar_cap_counts_what_the_provider_reported_and_stops_the_next_call():
    port, meter = Port(usd=0.6), NodeMeter(max_usd=1.0)
    llm.configure(port, mock=False, meter=meter)
    ask()
    ask()                                                                                      # 1.2 spent: over
    with pytest.raises(NodeCapReached) as stopped:
        ask()
    assert stopped.value.which == "usd" and port.requests[1].allowance.max_usd == pytest.approx(0.4) and meter.usd == pytest.approx(1.2)


def test_the_wall_clock_cap_is_a_deadline_on_every_request_and_stops_calls_after_it():
    clock, port = Clock(), Port()
    meter = NodeMeter(wall_s=60, clock=clock)
    llm.configure(port, mock=False, meter=meter)
    ask()
    assert port.requests[0].allowance.deadline == 1060.0
    clock.now = 1061.0
    with pytest.raises(NodeCapReached) as stopped:
        ask()
    assert stopped.value.which == "wall" and len(port.requests) == 1


def test_a_failed_call_counts_as_a_call_and_a_cap_of_none_is_never_checked():
    port, meter = Port(fail=ModelError("boom")), NodeMeter(max_calls=2)
    llm.configure(port, mock=False, meter=meter)
    for _ in range(2):
        with pytest.raises(ModelError):
            ask()
    with pytest.raises(NodeCapReached):
        ask()
    free = NodeMeter()
    llm.configure(Port(), mock=False, meter=free)
    for _ in range(50):
        ask()
    assert free.reached is None and free.allowance().max_calls is None and free.allowance().deadline is None


def test_configure_without_a_meter_clears_the_one_before():
    llm.configure(Port(), mock=False, meter=NodeMeter(max_calls=1))
    llm.configure(Port(), mock=False)
    port = Port()
    llm.configure(port, mock=False)
    ask()
    ask()
    assert len(port.requests) == 2 and port.requests[1].allowance is None
