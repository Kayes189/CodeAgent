"""Traceability report: link supplied requirements to components, diagrams,
files and tests. Only explicitly supplied requirements are mapped; missing
or inconsistent mappings are flagged, never invented.
"""
from __future__ import annotations


def build_traceability(preprocessed: dict, generated_files: list[str] | None = None) -> dict:
    arch = preprocessed.get("architecture", {})
    views = preprocessed.get("views", {})
    requirements = arch.get("requirements", [])
    diagrams = views.get("diagrams", [])
    generated_files = generated_files or []

    diagram_names = {d["name"] for d in diagrams}
    rows = []
    issues = []
    for req in requirements:
        rid = req.get("Requirement ID", "?")
        diagram_field = req.get("Diagram(s)", "")
        component_field = req.get("Component(s)", "")
        artifact_field = req.get("Artifact filename(s)", "")

        referenced_diagrams = [d.strip() for d in diagram_field.split(",") if d.strip()]
        matched_diagrams = [d for d in referenced_diagrams if d in diagram_names]
        missing_diagrams = [d for d in referenced_diagrams if d not in diagram_names]

        components = [c.strip() for c in component_field.split(",") if c.strip()]
        artifacts = [a.strip() for a in artifact_field.split(",") if a.strip()]

        matched_files = [f for f in generated_files
                         if any(a and a.split("/")[-1] in f for a in artifacts)]
        matched_tests = [f for f in generated_files if "test" in f.lower()]

        row = {
            "requirement_id": rid,
            "short_text": req.get("Short Text", ""),
            "components": components,
            "diagrams_referenced": referenced_diagrams,
            "diagrams_matched": matched_diagrams,
            "artifacts": artifacts,
            "generated_files_matched": matched_files,
            "tests_matched": matched_tests,
            "rationale": req.get("Rationale", ""),
            "status": "mapped" if (matched_diagrams or matched_files) else "incomplete",
        }
        rows.append(row)
        if missing_diagrams:
            issues.append(f"{rid}: references diagram(s) not present in views: {missing_diagrams}")
        if not matched_files and generated_files:
            issues.append(f"{rid}: no generated file matched its artifact(s) {artifacts}")

    # Diagram coverage: which diagrams are referenced by at least one requirement.
    referenced = {d for r in rows for d in r["diagrams_matched"]}
    unreferenced = sorted(diagram_names - referenced)

    return {
        "requirement_count": len(requirements),
        "diagram_count": len(diagrams),
        "rows": rows,
        "unreferenced_diagrams": unreferenced,
        "issues": issues,
        "note": ("Only explicitly supplied requirements are mapped. Inconsistencies and "
                 "incomplete mappings are listed in 'issues'; no requirements were invented."),
    }


def render_markdown(report: dict) -> str:
    lines = ["# Traceability Report", "",
             f"Requirements: {report['requirement_count']} | Diagrams: {report['diagram_count']}", "",
             "| Requirement | Components | Diagrams | Generated files | Tests | Status |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in report["rows"]:
        lines.append("| {id} | {comp} | {diag} | {files} | {tests} | {status} |".format(
            id=r["requirement_id"],
            comp=", ".join(r["components"]) or "—",
            diag=", ".join(r["diagrams_matched"]) or "—",
            files=", ".join(r["generated_files_matched"]) or "—",
            tests=", ".join(r["tests_matched"][:3]) or "—",
            status=r["status"],
        ))
    lines += ["", "## Issues / incomplete mappings"]
    if report["issues"]:
        lines += [f"- {i}" for i in report["issues"]]
    else:
        lines.append("- None detected.")
    if report["unreferenced_diagrams"]:
        lines += ["", "## Diagrams not referenced by any requirement",
                  ", ".join(report["unreferenced_diagrams"])]
    lines += ["", report["note"]]
    return "\n".join(lines)
