import json

from codeagent.context import compact
from codeagent.traceability import build_traceability, render_markdown
from codeagent.validation import validate_project


def test_compact_summarises_old_write_args():
    big = "x" * 5000
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {
                "name": "write_file",
                "arguments": json.dumps({"path": "a.py", "content": big})}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "OK: wrote 5000 bytes"},
    ]
    # add recent filler so the old turn is outside the keep window
    for i in range(10):
        messages.append({"role": "user", "content": f"recent {i}"})
    out, changed = compact(messages, budget=1000, keep_recent=4)
    assert changed
    args = json.loads(out[1]["tool_calls"][0]["function"]["arguments"])
    assert args["path"] == "a.py"
    assert "compacted" in args["content"]
    assert out[1]["tool_calls"][0]["id"] == "c1"  # pairing preserved


def test_compact_noop_under_budget():
    messages = [{"role": "user", "content": "hi"}]
    out, changed = compact(messages, budget=100000)
    assert not changed


def test_traceability_maps_and_flags():
    pre = {
        "architecture": {"requirements": [
            {"Requirement ID": "FR-1", "Short Text": "Play", "Diagram(s)": "UseCaseDiagram",
             "Component(s)": "GameComponent", "Artifact filename(s)": "openapi.yaml", "Rationale": "x"},
            {"Requirement ID": "NFR-9", "Short Text": "Ghost", "Diagram(s)": "MissingDiagram",
             "Component(s)": "X", "Artifact filename(s)": "none.yaml", "Rationale": "y"},
        ]},
        "views": {"diagrams": [{"name": "UseCaseDiagram"}]},
    }
    report = build_traceability(pre, generated_files=["openapi.yaml", "tests/test_game.py"])
    assert report["requirement_count"] == 2
    fr = report["rows"][0]
    assert fr["diagrams_matched"] == ["UseCaseDiagram"]
    assert "openapi.yaml" in fr["generated_files_matched"]
    assert any("MissingDiagram" in i for i in report["issues"])
    md = render_markdown(report)
    assert "FR-1" in md and "Issues" in md


def test_validation_detects_missing_deliverables(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n")
    report = validate_project(tmp_path)
    assert report["valid"] is False
    assert "README.md" in report["missing_required"]


def test_validation_passes_complete(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    (tmp_path / "requirements.txt").write_text("pytest")
    (tmp_path / "app.py").write_text("print(1)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_a():\n    assert True\n")
    report = validate_project(tmp_path)
    assert report["valid"] is True


def test_validation_detects_syntax_error(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    (tmp_path / "requirements.txt").write_text("pytest")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    report = validate_project(tmp_path)
    assert report["syntax_errors"]
    assert report["valid"] is False
