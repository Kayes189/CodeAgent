"""Tool system: unified tool interface + workspace sandbox.

Design follows the Claude Code tool system (see README "References"):
every tool shares one registry / schema / execution pipeline, and every
file operation passes a permission gate before touching the disk.

Safety model (defense in depth, simplified):
  1. All paths are confined to the output workspace (no traversal, no
     absolute escapes, no reparse-point tricks).
  2. Writes are size-capped; reads are line-capped.
  3. Tool results are truncated so the model context cannot explode.
  4. Unknown tools / malformed arguments return errors instead of raising.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MAX_WRITE_BYTES = 512 * 1024      # 512 KiB per file
MAX_READ_LINES = 2000
MAX_RESULT_CHARS = 16_000
MAX_LIST_ENTRIES = 500
MAX_SEARCH_MATCHES = 100
COMMAND_TIMEOUT = 120             # seconds

# Approved command programs for run_command (no shell, no arbitrary binaries).
# Only test/validation tooling is permitted; generated programs need explicit
# user permission via the allow_generated flag.
APPROVED_PROGRAMS = {
    "python", "python3", "py", "pytest", "pip",
}
# Argument patterns that are always rejected (destructive / network / escape).
_FORBIDDEN_ARG = re.compile(
    r"(rm\s+-rf|del\s+/|rmdir|format\s+|shutdown|curl\s+|wget\s+|Invoke-WebRequest|"
    r"\.\.[\\/]|--upload|publish|push\s+origin)", re.IGNORECASE
)


class ToolError(Exception):
    """Raised for invalid tool input or sandbox violations."""


def truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[..., str]
    is_write: bool = False

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Workspace:
    """A sandboxed directory tree. All tool paths resolve inside it."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        if not isinstance(rel, str) or not rel.strip():
            raise ToolError("Path must be a non-empty string.")
        rel = rel.strip().replace("\\", "/")
        if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
            raise ToolError(f"Absolute paths are not allowed: {rel!r}. Use a path relative to the output directory.")
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise ToolError(f"Path escapes the output directory: {rel!r}") from None
        return candidate


class ToolRegistry:
    def __init__(self, workspace: Workspace):
        self.ws = workspace
        # User permission gate for executing generated programs (GUI checkbox
        # / CLI flag). The model must ALSO pass allow_generated=true.
        self.generated_permission = False
        self._tools: dict[str, Tool] = {}
        self._register_defaults()

    # ------------------------------------------------------------------
    def _register_defaults(self) -> None:
        self.register(Tool(
            name="write_file",
            description=(
                "Create or overwrite a text file inside the output directory. "
                "Parent directories are created automatically. Use for source code, "
                "README, manifests, Dockerfile, tests, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the output directory, e.g. src/app.py"},
                    "content": {"type": "string", "description": "Full file content (UTF-8 text)."},
                },
                "required": ["path", "content"],
            },
            handler=self._write_file,
            is_write=True,
        ))
        self.register(Tool(
            name="read_file",
            description="Read a text file from the output directory (max 2000 lines).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the output directory."},
                },
                "required": ["path"],
            },
            handler=self._read_file,
        ))
        self.register(Tool(
            name="list_files",
            description="List files and directories under a relative path in the output directory ('' = root).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path; empty string lists the root."},
                },
                "required": [],
            },
            handler=self._list_files,
        ))
        self.register(Tool(
            name="search_files",
            description=(
                "Search generated project files for a regular expression. Returns matching "
                "file paths and line snippets (max 100 matches). Use to inspect code before editing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression to search for."},
                    "path": {"type": "string", "description": "Relative directory to search; '' = whole project."},
                },
                "required": ["pattern"],
            },
            handler=self._search_files,
        ))
        self.register(Tool(
            name="run_command",
            description=(
                "Run an APPROVED validation command inside the output directory (e.g. "
                "'python -m pytest tests -q'). Only python/pytest/pip are allowed; no shell, "
                "no arbitrary binaries, no network/destructive commands, 120s timeout. "
                "Running a generated program requires allow_generated=true (user permission)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command line, e.g. 'python -m pytest tests -q'."},
                    "allow_generated": {"type": "boolean", "description": "Set true only with user permission to run a generated program."},
                },
                "required": ["command"],
            },
            handler=self._run_command,
            is_write=True,
        ))
        self.register(Tool(
            name="finish",
            description=(
                "Call this when the project is complete. Provide a short summary of what was generated. "
                "Do not call any other tool after finish."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Short summary of the generated project."},
                },
                "required": ["summary"],
            },
            handler=self._finish,
        ))

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool {name!r}. Available: {', '.join(self._tools)}"
        if not isinstance(arguments, dict):
            return "ERROR: tool arguments must be a JSON object."
        try:
            result = tool.handler(**arguments)
        except ToolError as e:
            return f"ERROR: {e}"
        except TypeError as e:
            return f"ERROR: invalid arguments for {name}: {e}"
        except OSError as e:
            return f"ERROR: filesystem error: {e}"
        return truncate(result)

    # ------------------------------------------------------------------
    def _write_file(self, path: str, content: str) -> str:
        if not isinstance(content, str):
            raise ToolError("content must be a string.")
        data = content.encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            raise ToolError(f"File too large ({len(data)} bytes); limit is {MAX_WRITE_BYTES} bytes.")
        target = self.ws.resolve(path)
        if target.is_dir():
            raise ToolError(f"{path!r} is a directory.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"OK: wrote {len(data)} bytes to {path}"

    def _read_file(self, path: str) -> str:
        target = self.ws.resolve(path)
        if not target.is_file():
            raise ToolError(f"File not found: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > MAX_READ_LINES:
            text = "\n".join(lines[:MAX_READ_LINES]) + f"\n... [truncated at {MAX_READ_LINES} lines]"
        return text

    def _list_files(self, path: str = "") -> str:
        target = self.ws.resolve(path or ".")
        if not target.exists():
            raise ToolError(f"Directory not found: {path or '.'}")
        if not target.is_dir():
            raise ToolError(f"Not a directory: {path}")
        entries = []
        for p in sorted(target.rglob("*")):
            if len(entries) >= MAX_LIST_ENTRIES:
                entries.append("... [listing truncated]")
                break
            rel = p.relative_to(self.ws.root).as_posix()
            entries.append(rel + ("/" if p.is_dir() else ""))
        return "\n".join(entries) if entries else "(empty directory)"

    def _search_files(self, pattern: str, path: str = "") -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"Invalid regular expression: {e}")
        base = self.ws.resolve(path or ".")
        if not base.exists():
            raise ToolError(f"Directory not found: {path or '.'}")
        matches = []
        files = [base] if base.is_file() else sorted(base.rglob("*"))
        for p in files:
            if not p.is_file() or p.suffix.lower() in {".png", ".jpg", ".exe", ".zip", ".pyc"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    rel = p.relative_to(self.ws.root).as_posix()
                    matches.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                    if len(matches) >= MAX_SEARCH_MATCHES:
                        matches.append("... [search truncated at 100 matches]")
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "(no matches)"

    def _run_command(self, command: str, allow_generated: bool = False) -> str:
        if not isinstance(command, str) or not command.strip():
            raise ToolError("command must be a non-empty string.")
        if _FORBIDDEN_ARG.search(command):
            raise ToolError("Command contains a forbidden (destructive/network/escape) pattern.")
        try:
            parts = shlex.split(command, posix=False)
        except ValueError as e:
            raise ToolError(f"Cannot parse command: {e}")
        if not parts:
            raise ToolError("Empty command.")
        program = Path(parts[0]).name.lower().removesuffix(".exe")
        if program not in APPROVED_PROGRAMS:
            raise ToolError(
                f"Program {program!r} is not approved. Allowed: {', '.join(sorted(APPROVED_PROGRAMS))}."
            )
        # pytest invocations are approved validation, not "running a generated
        # program". Other .py scripts need BOTH the model's allow_generated
        # flag AND explicit user permission (registry.generated_permission).
        is_pytest = program == "pytest" or ("-m" in parts[1:] and "pytest" in parts[1:])
        script_args = [a for a in parts[1:] if a.endswith(".py")]
        if script_args and not is_pytest and not (allow_generated and self.generated_permission):
            raise ToolError(
                "Running a generated program requires allow_generated=true AND explicit "
                "user permission (enable 'Permit running generated programs' in the GUI)."
            )
        # Resolve python to a real interpreter. In a frozen exe sys.executable
        # is the app itself, so fall back to a PATH lookup.
        if program in {"python", "python3", "py"}:
            if getattr(sys, "frozen", False):
                import shutil
                found = shutil.which("python") or shutil.which("python3")
                if not found:
                    raise ToolError(
                        "No Python interpreter found on this machine; cannot run tests "
                        "from the packaged exe. Run tests from the source distribution."
                    )
                parts[0] = found
            else:
                parts[0] = sys.executable
        # Reject any path argument that escapes the workspace.
        for a in parts[1:]:
            if a.startswith("-"):
                continue
            if ".." in a or a.startswith("/") or (len(a) > 1 and a[1] == ":"):
                raise ToolError(f"Argument {a!r} may escape the workspace; use relative paths.")
        try:
            proc = subprocess.run(
                parts, cwd=str(self.ws.root), shell=False,
                capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command timed out after {COMMAND_TIMEOUT}s.")
        except OSError as e:
            raise ToolError(f"Failed to start command: {e}")
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return f"exit_code={proc.returncode}\n{truncate(out, 8000)}"

    def _finish(self, summary: str) -> str:
        return f"FINISH: {summary}"


def tool_result_message(tool_call_id: str, result: str) -> dict:
    """Build the OpenAI-style tool result message."""
    return {"role": "tool", "tool_call_id": tool_call_id, "content": result}
