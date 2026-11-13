"""Preprocessing: turn the two input Markdown files into structured JSON.

Input 1: Architecture_Documentation.md
    -> sections, requirement tables (FR/NFR/ASR traceability), embedded
       code artifacts (openapi / proto / sql / k8s / csv).
Input 2: Architecture_View.md
    -> PlantUML diagram blocks with name, 4+1 view and diagram type.

The JSON is written next to the run output as `preprocessed_input.json`
and injected into the agent's first user message, as recommended by the
task specification.
"""
from __future__ import annotations

import re
from pathlib import Path

from .uml import extract_elements

_REQ_ID = re.compile(r"^(FR|NFR|ASR)-\d+$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UML_START = re.compile(r"^@startuml\s*(\S+)?")
_UML_END = re.compile(r"^@enduml")

# filename hints for embedded artifact blocks
_ARTIFACT_HINTS = {
    "yml": "yaml",
    "yaml": "yaml",
    "proto": "proto",
    "sql": "sql",
    "csv": "csv",
    "json": "json",
    "markdown": "markdown",
}


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_architecture_document(text: str) -> dict:
    """Extract sections, requirement rows and embedded artifacts."""
    sections: list[dict] = []
    requirements: list[dict] = []
    artifacts: list[dict] = []

    current_section = {"title": "(preamble)", "level": 0, "lines": []}
    sections.append(current_section)

    in_fence = False
    fence_lang = ""
    fence_lines: list[str] = []
    table_header: list[str] | None = None

    for line in text.splitlines():
        if in_fence:
            if line.strip().startswith("```"):
                in_fence = False
                lang = fence_lang.lower()
                artifacts.append({
                    "language": lang,
                    "kind": _ARTIFACT_HINTS.get(lang, lang or "text"),
                    "content": "\n".join(fence_lines),
                })
                fence_lines = []
            else:
                fence_lines.append(line)
            continue

        m = _FENCE.match(line.strip())
        if m:
            in_fence = True
            fence_lang = m.group(1)
            fence_lines = []
            table_header = None
            continue

        h = _HEADING.match(line)
        if h:
            current_section = {"title": h.group(2).strip(), "level": len(h.group(1)), "lines": []}
            sections.append(current_section)
            table_header = None
            continue

        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = _split_table_row(stripped)
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue  # separator row
            if table_header is None:
                table_header = cells
            elif cells and _REQ_ID.match(cells[0]):
                row = dict(zip(table_header, cells))
                requirements.append(row)
            current_section["lines"].append(line)
            continue

        table_header = None
        current_section["lines"].append(line)

    # Drop empty sections, join bodies.
    out_sections = []
    for s in sections:
        body = "\n".join(s["lines"]).strip()
        if body or s["title"] != "(preamble)":
            out_sections.append({"title": s["title"], "level": s["level"], "body": body})

    return {
        "sections": out_sections,
        "requirements": requirements,
        "artifacts": artifacts,
    }


def parse_architecture_views(text: str) -> dict:
    """Extract PlantUML blocks with view/type classification."""
    diagrams = []
    current_view = "UnknownView"
    in_fence = False
    uml_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not in_fence:
            h = _HEADING.match(stripped)
            if h and h.group(2).endswith("View"):
                current_view = h.group(2).strip()
            if stripped.startswith("```"):
                in_fence = True
                uml_lines = []
            continue
        if stripped.startswith("```"):
            in_fence = False
            block = "\n".join(uml_lines)
            if "@startuml" in block:
                start = _UML_START.search(block)
                name = start.group(1) if start and start.group(1) else f"diagram_{len(diagrams) + 1}"
                dtype = _type_from_name(name) or _diagram_type(block)
                diagrams.append({
                    "name": name,
                    "view": current_view,
                    "type": dtype,
                    "plantuml": block,
                    "elements": extract_elements(block, dtype),
                })
            uml_lines = []
        else:
            uml_lines.append(line)

    return {"diagrams": diagrams, "diagram_count": len(diagrams)}


def _type_from_name(name: str) -> str | None:
    lower = name.lower()
    for key in (
        "usecase", "class", "object", "state", "activity", "sequence",
        "collaboration", "package", "component", "deployment", "container",
    ):
        if key in lower:
            return key
    return None


def _diagram_type(block: str) -> str:
    if re.search(r"^\s*usecase\s", block, re.M) or "actor " in block:
        return "usecase"
    if re.search(r"^\s*class\s+\w+", block, re.M):
        return "class"
    if re.search(r"^\s*state\s+\w+", block, re.M):
        return "state"
    if re.search(r"^\s*participant\s", block, re.M):
        if "->>" in block:
            return "sequence"
        return "collaboration"
    if re.search(r"^\s*package\s", block, re.M):
        return "package"
    if re.search(r"^\s*artifact\s", block, re.M):
        return "component/container"
    if re.search(r"^\s*node\s", block, re.M):
        return "deployment"
    if re.search(r"^\s*start\s*$", block, re.M):
        return "activity"
    return "unknown"


def preprocess_inputs(doc_path: str | Path, view_path: str | Path) -> dict:
    doc_text = Path(doc_path).read_text(encoding="utf-8", errors="replace")
    view_text = Path(view_path).read_text(encoding="utf-8", errors="replace")
    return {
        "source_files": {
            "architecture_documentation": str(doc_path),
            "architecture_view": str(view_path),
        },
        "architecture": parse_architecture_document(doc_text),
        "views": parse_architecture_views(view_text),
    }
