import io
import json
import urllib.error

import pytest

from codeagent.llm import (
    AuthenticationError, DeepSeekClient, LLMError, RateLimitError,
)


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _payload(content=None, tool_calls=None, finish="stop", usage=None):
    msg = {"content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5}}


@pytest.fixture
def client():
    return DeepSeekClient("sk-test", max_retries=1)


def test_rejects_other_model():
    with pytest.raises(LLMError):
        DeepSeekClient("sk", model="deepseek-chat")


def test_rejects_other_endpoint():
    with pytest.raises(LLMError):
        DeepSeekClient("sk", base_url="https://api.openai.com")


def test_payload_disables_thinking_by_default(client, monkeypatch):
    captured = {}

    def fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return FakeResponse(_payload(content="OK"))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    client.chat([{"role": "user", "content": "hi"}], max_tokens=100)
    assert captured["body"]["model"] == "deepseek-v4-pro"
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["max_tokens"] == 100
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["auth"] == "Bearer sk-test"


def test_thinking_enabled_payload(monkeypatch):
    c = DeepSeekClient("sk", thinking_enabled=True)
    captured = {}
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: (captured.update(body=json.loads(req.data.decode())),
                                                   FakeResponse(_payload(content="x")))[1])
    c.chat([])
    assert captured["body"]["thinking"] == {"type": "enabled"}


def test_tool_calls_parsed(client, monkeypatch):
    p = _payload(tool_calls=[{"id": "c1", "function": {"name": "write_file",
                 "arguments": '{"path":"a.txt","content":"x"}'}}], finish="tool_calls")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResponse(p))
    resp = client.chat([], tools=[{"type": "function"}])
    assert resp.has_tool_calls
    assert resp.tool_calls[0].arguments == {"path": "a.txt", "content": "x"}


def test_reasoning_content_preserved(client, monkeypatch):
    p = _payload(content="answer")
    p["choices"][0]["message"]["reasoning_content"] = "thought steps"
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResponse(p))
    resp = client.chat([])
    assert resp.reasoning_content == "thought steps"


def test_usage_cache_fields_passed_through(client, monkeypatch):
    p = _payload(content="x", usage={"prompt_tokens": 100, "prompt_cache_hit_tokens": 60,
                                     "prompt_cache_miss_tokens": 40, "completion_tokens": 20})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResponse(p))
    resp = client.chat([])
    assert resp.usage["prompt_cache_hit_tokens"] == 60


def test_401_raises_auth_no_retry(client, monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    with pytest.raises(AuthenticationError):
        client.chat([])
    assert calls["n"] == 1


def test_429_retries_then_rate_limit_error(client, monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(RateLimitError):
        client.chat([])
    assert calls["n"] == 2  # initial + 1 retry


def test_500_retries_then_succeeds(client, monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 500, "Err", {}, io.BytesIO(b""))
        return FakeResponse(_payload(content="ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert client.chat([]).content == "ok"
    assert calls["n"] == 2


def test_network_error_retries(client, monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection reset")
        return FakeResponse(_payload(content="ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert client.chat([]).content == "ok"


def test_no_key_raises_auth():
    c = DeepSeekClient("")
    with pytest.raises(AuthenticationError):
        c.chat([])


def test_connection_test(client, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: FakeResponse(_payload(content="OK")))
    info = client.test_connection()
    assert info["ok"] is True
    assert info["model"] == "deepseek-v4-pro"
