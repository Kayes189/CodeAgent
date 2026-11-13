# Research Notes — Implementation Mechanisms of Claude-Code-style Agents

This document records what was studied from the three repositories named in
the assignment, which engineering mechanisms were adopted, and **where each
lives in this source tree**. It does not claim access to proprietary Claude
Code internals; findings are based on the public repositories and their
documentation only.

## Sources studied

| Repository | What it is | How it was used |
| --- | --- | --- |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | Official product repo (README, docs, plugins, changelog). The runnable tool is distributed via npm/installer; the repo documents the product surface and tool/permission model. | Confirmed the agentic-coding workflow, tool-based design and permission philosophy. |
| [Windy3f3f3f3f/how-claude-code-works](https://github.com/Windy3f3f3f3f/how-claude-code-works) | Community architecture analysis (21 chapters) of a leaked source snapshot: agent loop, context engineering, tool system, 7-layer permission defense, etc. | Primary reference for the loop, context compression stages and defense-in-depth ideas. |
| [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code) | Clean-room Rust reimplementation of the Claude Code harness (with a Python reference workspace). | Confirmed harness structure: provider client, tool registry, turn loop, path-scope security. |

> Note: the assignment's links contain typos (`clawcode`, `howclaudecodeworks`,
> `claudecode`); the canonical URLs above were verified to resolve.

## Mechanisms adopted and where they live

### 1. Agent loop (the core)
Claude Code's engine is a `while` loop: call the model → if it requests tools,
execute them → feed results back → repeat. No state machine, no preset
pipeline; the decision core is tiny and everything else is runtime armor.
- **Implemented in:** `codeagent/agent.py` (`Agent.run`).
- Iteration budget, cancellation, and a `finish` gate that only accepts
  completion after validation.

### 2. Tool registry (uniform interface)
Every tool shares one registry, one JSON-schema contract and one execution
pipeline, so tools are interchangeable and equally gated.
- **Implemented in:** `codeagent/tools.py` (`Tool`, `ToolRegistry`).
- Tools: `write_file`, `read_file`, `list_files`, `search_files`,
  `run_command`, `finish`.

### 3. Tool execution + permission checks (defense in depth)
Claude Code layers workspace trust, rules, command analysis, tool-level
validation, sandboxing and user confirmation. This project implements the
file-system + command subset:
- Path confinement to the output workspace; traversal/absolute/symlink
  escapes rejected (`Workspace.resolve`).
- Write-size and read-length caps; result truncation.
- `run_command`: approved-program allowlist, **no `shell=True`**, forbidden
  destructive/network patterns, workspace-bound arguments, 120s timeout, and
  a **two-key gate** for running generated programs (model `allow_generated`
  flag **and** explicit user permission).
- **Implemented in:** `codeagent/tools.py`.

### 4. Context management
Claude Code uses a multi-stage compression pipeline. This project implements
a compact-summary stage: old `write_file` arguments (full source code) are
replaced with short summaries while file paths and recent turns are kept, and
old tool results are trimmed. Tool-call id pairing is preserved (API
requirement).
- **Implemented in:** `codeagent/context.py` (`compact`).

### 5. Error handling / silent recovery
Transient HTTP errors (429/5xx) and network failures are retried with
exponential backoff; auth errors are surfaced immediately; malformed
tool-call arguments degrade to `{}` rather than crashing.
- **Implemented in:** `codeagent/llm.py` (`DeepSeekClient.chat`, `_parse`).

### 6. Autonomous coding workflow
Plan → inspect requirements → write files → read/search → run approved tests
→ correct → review → finish. The system prompt encodes this workflow and the
`finish` validation gate enforces "done means actually done".
- **Implemented in:** `codeagent/prompts.py`, `codeagent/agent.py`
  (`_handle_finish`), `codeagent/validation.py`.

### 7. Cost guard (assignment-specific addition)
Not a Claude Code mechanism, but required by the professor: pre-request cost
estimation + dynamic `max_tokens` cap + post-request actual-usage accounting
at conservative peak pricing, with a hard stop before the budget is exceeded.
- **Implemented in:** `codeagent/cost.py` (`CostManager`), wired into
  `Agent.run`.

## What was deliberately NOT implemented (scope honesty)
Streaming output, sub-agents / agent teams, MCP integration, hooks, the full
4-stage compression pipeline, ML permission classifiers, and OS-level
process sandboxing. These are production-scale features beyond a simplified
coursework agent; the simplified equivalents above cover the required
behaviour.
