"""Extract structured UML elements from PlantUML diagram blocks.

Parses actors, classes (attributes/methods), relationships, states and
transitions, activities, sequence interactions, components, packages,
deployment nodes and containers — as required by the assignment. This is a
lightweight line-based parser sufficient for the supplied diagrams; it does
not claim to be a full PlantUML grammar implementation.
"""
from __future__ import annotations

import re

_ACTOR = re.compile(r'^\s*actor\s+(?:"([^"]+)"|(\w+))(?:\s+as\s+(?:"([^"]+)"|(\w+)))?')
_USECASE = re.compile(r'^\s*usecase\s+"([^"]+)"')
_CLASS = re.compile(r'^\s*class\s+(\w+)')
_MEMBER = re.compile(r'^\s*([+\-#~])\s*(\w+)\s*(\([^)]*\))?\s*(?::\s*(.+))?$')
_STATE = re.compile(r'^\s*state\s+"?([\w ]+)"?')
_TRANSITION = re.compile(r'^\s*(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)\s*(?::\s*(.+))?$')
_ACTIVITY = re.compile(r'^\s*:(.+);')
_NODE = re.compile(r'^\s*node\s+"?([\w ]+)"?')
_ARTIFACT = re.compile(r'^\s*artifact\s+"?([\w ]+)"?')
_PACKAGE = re.compile(r'^\s*package\s+"?([\w ]+)"?')
_PARTICIPANT = re.compile(r'^\s*participant\s+"?([\w ]+)"?')
_MSG = re.compile(r'^\s*(\w+)\s*(->>|-->|->)\s*(\w+)\s*:\s*(.+)$')
_REL = re.compile(r'^\s*(\w+)\s+(--\*|--o|--|\.\.>|-->|--\|>|<\|--)\s+(\w+)')


def extract_elements(block: str, diagram_type: str) -> dict:
    lines = block.splitlines()
    out: dict = {
        "actors": [], "usecases": [], "classes": [], "relationships": [],
        "states": [], "transitions": [], "activities": [], "messages": [],
        "participants": [], "components": [], "packages": [], "nodes": [],
        "containers": [],
    }
    current_class = None
    in_class_body = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("@startuml", "@enduml", "'", "left to right")):
            continue

        m = _ACTOR.match(line)
        if m:
            out["actors"].append(m.group(1) or m.group(3) or m.group(2) or m.group(4))
            current_class = None
            continue
        m = _USECASE.match(line)
        if m:
            out["usecases"].append(m.group(1))
            continue

        m = _CLASS.match(line)
        if m:
            current_class = {"name": m.group(1), "attributes": [], "methods": []}
            out["classes"].append(current_class)
            in_class_body = "{" in line
            continue
        if current_class is not None:
            if "{" in line:
                in_class_body = True
                continue
            if "}" in line:
                in_class_body = False
                current_class = None
                continue
            if in_class_body:
                mm = _MEMBER.match(line)
                if mm:
                    name, call, typ = mm.group(2), mm.group(3), mm.group(4)
                    if call is not None:
                        current_class["methods"].append({"name": name, "signature": call, "return": typ})
                    else:
                        current_class["attributes"].append({"name": name, "type": typ})
                continue

        m = _STATE.match(line)
        if m and diagram_type == "state":
            out["states"].append(m.group(1).strip())
            continue
        m = _TRANSITION.match(line)
        if m:
            out["transitions"].append({"from": m.group(1), "to": m.group(2), "trigger": (m.group(3) or "").strip()})
            continue
        m = _ACTIVITY.match(line)
        if m:
            out["activities"].append(m.group(1).strip())
            continue
        m = _PARTICIPANT.match(line)
        if m:
            out["participants"].append(m.group(1).strip())
            continue
        m = _MSG.match(line)
        if m:
            out["messages"].append({"from": m.group(1), "to": m.group(3), "label": m.group(4).strip()})
            continue
        m = _NODE.match(line)
        if m:
            out["nodes"].append(m.group(1).strip())
            continue
        m = _ARTIFACT.match(line)
        if m:
            name = m.group(1).strip()
            if diagram_type == "container":
                out["containers"].append(name)
            else:
                out["components"].append(name)
            continue
        m = _PACKAGE.match(line)
        if m:
            out["packages"].append(m.group(1).strip())
            continue
        m = _REL.match(line)
        if m:
            out["relationships"].append({"from": m.group(1), "type": m.group(2), "to": m.group(3)})
            continue

    # Drop empty buckets for a compact result.
    return {k: v for k, v in out.items() if v}
