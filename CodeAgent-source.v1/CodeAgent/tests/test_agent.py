import json
import threading

import pytest

from codeagent.agent import Agent
from codeagent.cost import CostManager
from codeagent.llm import LLMResponse, ToolCall
from codeagent.tools import ToolRegistry, Workspace


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, tools=None, max_tokens=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)),
                           "tools": tools, "max_tokens": max_tokens})
        if not self.responses:
            return LLMResponse(content="No more scripted responses.")
        return self.responses.pop(0)


def _tc(name, args, cid="c1"):
    return ToolCall(id=cid, name=name, arguments=args)


def _usage():
    return {"prompt_tokens": 100, "completion_tokens": 20}


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(Workspace(tmp_path / "out"))


def _complete_project_files(registry):
    registry.execute("write_file", {"path": "README.md", "content": "# Demo"})
    registry.execute("write_file", {"path": "requirements.txt", "content": "pytest"})
    registry.execute("write_file", {"path": "app.py", "content": "print('hi')\n"})
    registry.execute("write_file", {"path": "tests/test_app.py", "content": "def test_x():\n    assert True\n"})


def test_full_loop_completes_with_validation(registry, sample_inputs, tmp_path):
    doc, view = sample_inputs
    _complete_project_files(registry)
    client = ScriptedClient([
        LLMResponse(content=None, tool_calls=[_tc("finish", {"summary": "Done."})],
                    finish_reason="tool_calls", usage=_usage()),
    ])
    events = []
    agent = Agent(client, registry, cost_manager=CostManager(0.80),
                  on_event=lambda k, t: events.append((k, t)))
    result = agent.run(doc, view)
    assert result.status == "completed"
    assert result.validation["valid"] is True
    assert (tmp_path / "out" / "usage_report.json").exists()
    assert (tmp_path / "out" / "traceability_report.md").exists()
    assert any(k == "usage" for k, _ in events)


def test_finish_rejected_when_incomplete(registry, sample_inputs):
    doc, view = sample_inputs
    # No files written -> validation fails -> finish rejected, then model stops.
    client = ScriptedClient([
        LLMResponse(content=None, tool_calls=[_tc("finish", {"summary": "premature"})],
                    finish_reason="tool_calls", usage=_usage()),
        LLMResponse(content="I will fix it.", usage=_usage()),
    ])
    agent = Agent(client, registry, cost_manager=CostManager(0.80))
    result = agent.run(doc, view)
    # finish was rejected; loop continued; second response had no tools -> completed
    tool_msgs = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
    assert any("finish rejected" in m["content"] for m in tool_msgs)


def test_budget_exceeded_preserves_files(registry, sample_inputs, tmp_path):
    doc, view = sample_inputs
    registry.execute("write_file", {"path": "partial.py", "content": "x = 1\n"})
    cm = CostManager(budget_usd=0.0000001)  # essentially zero
    client = ScriptedClient([LLMResponse(content="should not run")])
    agent = Agent(client, registry, cost_manager=cm)
    result = agent.run(doc, view)
    assert result.status == "budget_exceeded"
    assert client.calls == []  # no API call made
    assert (tmp_path / "out" / "partial.py").exists()  # files preserved
    assert (tmp_path / "out" / "usage_report.json").exists()


def test_max_tokens_capped_by_budget(registry, sample_inputs):
    doc, view = sample_inputs
    _complete_project_files(registry)
    cm = CostManager(budget_usd=0.80)
    cm.total_cost_usd = 0.76
    client = ScriptedClient([
        LLMResponse(content=None, tool_calls=[_tc("finish", {"summary": "ok"})],
                    finish_reason="tool_calls", usage=_usage()),
    ])
    agent = Agent(client, registry, cost_manager=cm, max_output_tokens=8000)
    agent.run(doc, view)
    assert client.calls[0]["max_tokens"] < 8000


def test_cancellation(registry, sample_inputs):
    doc, view = sample_inputs
    cancel = threading.Event()
    cancel.set()
    client = ScriptedClient([LLMResponse(content="x")])
    agent = Agent(client, registry, cancel_event=cancel)
    result = agent.run(doc, view)
    assert result.status == "stopped"
    assert client.calls == []


def test_missing_input(registry, tmp_path):
    agent = Agent(ScriptedClient([]), registry)
    result = agent.run(tmp_path / "no.md", tmp_path / "no2.md")
    assert result.status == "error"
    assert "Cannot read input" in result.error


def test_llm_error_reported(registry, sample_inputs):
    from codeagent.llm import LLMError

    class Broken:
        def chat(self, *a, **k):
            raise LLMError("HTTP 401: bad key")

    doc, view = sample_inputs
    agent = Agent(Broken(), registry, cost_manager=CostManager(0.80))
    result = agent.run(doc, view)
    assert result.status == "error"
    assert "401" in result.error


def test_max_iterations(registry, sample_inputs):
    doc, view = sample_inputs
    endless = [LLMResponse(content=None, tool_calls=[_tc("list_files", {"path": ""})],
                           finish_reason="tool_calls", usage=_usage()) for _ in range(10)]
    agent = Agent(ScriptedClient(endless), registry, max_iterations=3)
    result = agent.run(doc, view)
    assert result.status == "max_iterations"
    assert result.iterations == 3


def test_cost_accumulates_in_result(registry, sample_inputs):
    doc, view = sample_inputs
    _complete_project_files(registry)
    client = ScriptedClient([
        LLMResponse(content=None, tool_calls=[_tc("finish", {"summary": "ok"})],
                    finish_reason="tool_calls",
                    usage={"prompt_tokens": 1000, "completion_tokens": 500}),
    ])
    agent = Agent(client, registry, cost_manager=CostManager(0.80))
    result = agent.run(doc, view)
    assert result.cost_usd > 0
    assert result.usage["output_tokens"] == 500
