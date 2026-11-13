from pathlib import Path

import pytest

from codeagent.preprocess import (
    parse_architecture_document, parse_architecture_views, preprocess_inputs,
)
from codeagent.uml import extract_elements

from conftest import SAMPLE_DOC, SAMPLE_VIEW


def test_requirements_extracted():
    data = parse_architecture_document(SAMPLE_DOC)
    assert [r["Requirement ID"] for r in data["requirements"]] == ["FR-1", "NFR-1", "ASR-1"]


def test_artifacts_extracted():
    data = parse_architecture_document(SAMPLE_DOC)
    kinds = [a["kind"] for a in data["artifacts"]]
    assert "yaml" in kinds and "sql" in kinds


def test_diagrams_and_elements():
    data = parse_architecture_views(SAMPLE_VIEW)
    assert data["diagram_count"] == 3
    by = {d["name"]: d for d in data["diagrams"]}
    assert by["UseCaseDiagram"]["elements"]["actors"] == ["End User"]
    assert "Play Game" in by["UseCaseDiagram"]["elements"]["usecases"]
    cls = by["ClassDiagram"]["elements"]["classes"]
    game = next(c for c in cls if c["name"] == "Game")
    assert any(a["name"] == "score" for a in game["attributes"])
    assert any(m["name"] == "play" for m in game["methods"])
    assert by["SequenceDiagram1"]["elements"]["messages"][0]["label"] == "play()"


def test_state_transitions():
    block = "@startuml StateDiagram\nstate Playing\nstate Paused\n[*] --> Playing\nPlaying --> Paused : pause()\n@enduml"
    el = extract_elements(block, "state")
    assert "Playing" in el["states"]
    assert any(t["trigger"] == "pause()" for t in el["transitions"])


def test_deployment_and_container():
    block = "@startuml DeploymentDiagram\nnode GameServer\nnode QuestionServer\n@enduml"
    assert "GameServer" in extract_elements(block, "deployment")["nodes"]
    block2 = "@startuml ContainerDiagram\nartifact GameContainer\n@enduml"
    assert "GameContainer" in extract_elements(block2, "container")["containers"]


def test_preprocess_end_to_end(sample_inputs):
    doc, view = sample_inputs
    data = preprocess_inputs(doc, view)
    assert len(data["architecture"]["requirements"]) == 3
    assert data["views"]["diagram_count"] == 3


def test_real_task_inputs():
    base = Path(__file__).resolve().parents[2]
    doc = base / "Architecture_Documentation.md"
    view = base / "Architecture_View.md"
    if not (doc.exists() and view.exists()):
        pytest.skip("coursework inputs not present")
    data = preprocess_inputs(doc, view)
    ids = {r["Requirement ID"] for r in data["architecture"]["requirements"]}
    assert {"FR-1", "NFR-1", "ASR-1"} <= ids
    # The view file contains 13 PlantUML blocks covering 11 diagram types.
    assert data["views"]["diagram_count"] == 13
    types = {d["type"] for d in data["views"]["diagrams"]}
    assert {"usecase", "class", "state", "activity", "sequence",
            "package", "deployment", "container"} <= types
    # actors / classes / nodes extracted from real diagrams
    all_elements = [d["elements"] for d in data["views"]["diagrams"]]
    assert any("actors" in e for e in all_elements)
    assert any("classes" in e for e in all_elements)
    assert any("nodes" in e for e in all_elements)
