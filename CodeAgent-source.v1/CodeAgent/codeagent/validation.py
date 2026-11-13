"""Validation system: check the generated project for required deliverables
and basic correctness. Used by the agent before finish and by tests.
"""
from __future__ import annotations

import ast
from pathlib import Path

REQUIRED_DELIVERABLES = ["README.md", "requirements.txt"]
RECOMMENDED_DELIVERABLES = ["Dockerfile"]


def validate_project(root: str | Path) -> dict:
    root = Path(root)
    files = [p for p in root.rglob("*") if p.is_file()]
    rel = {p.relative_to(root).as_posix() for p in files}

    missing_required = [d for d in REQUIRED_DELIVERABLES if d not in rel]
    missing_recommended = [d for d in RECOMMENDED_DELIVERABLES if d not in rel]

    py_files = [p for p in files if p.suffix == ".py"]
    syntax_errors = []
    for p in py_files:
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            syntax_errors.append(f"{p.relative_to(root).as_posix()}:{e.lineno}: {e.msg}")

    has_tests = any("test" in r.lower() for r in rel)
    has_source = any(r.endswith(".py") and "test" not in r.lower() for r in rel)

    issues = []
    if missing_required:
        issues.append(f"Missing required deliverables: {missing_required}")
    if syntax_errors:
        issues.append(f"Python syntax errors: {syntax_errors}")
    if not has_tests:
        issues.append("No test files found.")
    if not has_source:
        issues.append("No source files found.")

    return {
        "file_count": len(files),
        "python_file_count": len(py_files),
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "syntax_errors": syntax_errors,
        "has_tests": has_tests,
        "has_source": has_source,
        "valid": not missing_required and not syntax_errors and has_tests and has_source,
        "issues": issues,
    }
