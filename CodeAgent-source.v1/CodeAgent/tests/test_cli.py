import json

import pytest

from codeagent.cli import main
from codeagent.config import Settings


def test_preprocess_command(tmp_path, sample_inputs):
    doc, view = sample_inputs
    out = tmp_path / "pre.json"
    assert main(["preprocess", "--doc", str(doc), "--view", str(view), "-o", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["views"]["diagram_count"] == 3


def test_preprocess_stdout(sample_inputs, capsys):
    doc, view = sample_inputs
    assert main(["preprocess", "--doc", str(doc), "--view", str(view)]) == 0
    assert "UseCaseDiagram" in capsys.readouterr().out


def test_run_requires_config(tmp_path, sample_inputs, monkeypatch):
    doc, view = sample_inputs
    monkeypatch.delenv("CODEAGENT_API_KEY", raising=False)
    monkeypatch.setattr("codeagent.cli.load_settings", lambda: Settings())
    code = main(["run", "--doc", str(doc), "--view", str(view), "--out", str(tmp_path / "out")])
    assert code == 2


def test_run_invalid_output_dir(tmp_path, sample_inputs, monkeypatch):
    doc, view = sample_inputs
    monkeypatch.setattr("codeagent.cli.load_settings", lambda: Settings(api_key="sk-test"))
    bad_out = tmp_path / "afile.txt"
    bad_out.write_text("not a dir")
    code = main(["run", "--doc", str(doc), "--view", str(view), "--out", str(bad_out)])
    assert code == 2


def test_test_connection_no_key(monkeypatch):
    monkeypatch.delenv("CODEAGENT_API_KEY", raising=False)
    monkeypatch.setattr("codeagent.cli.load_settings", lambda: Settings())
    assert main(["test-connection"]) == 2


def test_test_connection_success(monkeypatch, capsys):
    monkeypatch.setattr("codeagent.cli.load_settings", lambda: Settings(api_key="sk-test"))

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def test_connection(self):
            return {"ok": True, "model": "deepseek-v4-pro", "usage": {}, "reply": "OK"}

    monkeypatch.setattr("codeagent.llm.DeepSeekClient", FakeClient)
    assert main(["test-connection"]) == 0
    assert "Connection OK" in capsys.readouterr().out


def test_test_connection_failure(monkeypatch):
    from codeagent.llm import LLMError

    monkeypatch.setattr("codeagent.cli.load_settings", lambda: Settings(api_key="sk-test"))

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def test_connection(self):
            raise LLMError("HTTP 401: bad key")

    monkeypatch.setattr("codeagent.llm.DeepSeekClient", FakeClient)
    assert main(["test-connection"]) == 1


def test_version(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    assert "codeagent" in capsys.readouterr().out
