"""Agent controller — the heart of the system.

Claude-Code-style loop: call model -> execute tools -> feed results back.
Around the tiny decision core sits the runtime armor:

  * CostManager   — pre-request estimate + dynamic max_tokens cap +
                    post-request actual-usage accounting (budget guard).
  * ContextManager— compact summaries for old source-code tool arguments.
  * ToolRegistry  — permission-gated, sandboxed tool execution.
  * Validation    — finish is accepted only when the project validates.
  * Traceability  — requirements -> diagrams -> files -> tests report.
  * Logging       — full transcript + usage report saved to the workspace.

Files written before a budget stop are always preserved.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .context import compact
from .cost import BudgetExceededError, CostManager
from .llm import LLMError, LLMResponse
from .preprocess import preprocess_inputs
from .prompts import SYSTEM_PROMPT, build_user_message
from .tools import ToolRegistry, tool_result_message
from .traceability import build_traceability, render_markdown
from .validation import validate_project

EventHook = Callable[[str, str], None]

MAX_FINISH_REJECTIONS = 3


@dataclass
class AgentResult:
    status: str = "error"  # completed|stopped|max_iterations|budget_exceeded|error
    summary: str = ""
    iterations: int = 0
    tool_calls: int = 0
    files_written: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    error: str = ""
    validation: dict = field(default_factory=dict)


class Agent:
    def __init__(
        self,
        client,
        registry: ToolRegistry,
        cost_manager: CostManager | None = None,
        max_iterations: int = 60,
        on_event: EventHook | None = None,
        cancel_event: threading.Event | None = None,
        max_output_tokens: int = 8192,
    ):
        self.client = client
        self.registry = registry
        self.cost = cost_manager or CostManager()
        self.max_iterations = max_iterations
        self.max_output_tokens = max_output_tokens
        self.on_event = on_event or (lambda kind, text: None)
        self.cancel = cancel_event or threading.Event()
        self.messages: list[dict] = []
        self.result = AgentResult()
        self._finish_rejections = 0

    # ------------------------------------------------------------------
    def run(self, doc_path: str | Path, view_path: str | Path, extra_instruction: str = "") -> AgentResult:
        self.on_event("status", "Preprocessing input documents...")
        try:
            preprocessed = preprocess_inputs(doc_path, view_path)
        except OSError as e:
            self.result.error = f"Cannot read input files: {e}"
            self.on_event("error", self.result.error)
            return self._finalize(0)

        ws_root = self.registry.ws.root
        self._write_json(ws_root / "preprocessed_input.json", preprocessed)
        self.on_event(
            "status",
            f"Preprocessed: {len(preprocessed['architecture']['requirements'])} requirement rows, "
            f"{preprocessed['views']['diagram_count']} diagram blocks.",
        )

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(preprocessed, extra_instruction)},
        ]
        tools = self.registry.schemas()

        for i in range(1, self.max_iterations + 1):
            if self.cancel.is_set():
                self.result.status = "stopped"
                self.result.summary = "Cancelled by user. Generated files were preserved."
                self.on_event("status", "Stopped by user.")
                return self._finalize(i - 1)

            self.result.iterations = i
            self.messages, compacted = compact(self.messages)
            if compacted:
                self.on_event("status", "Context compacted (old source-code arguments summarised).")

            # --- PRE-request cost guard -------------------------------
            input_chars = len(json.dumps(self.messages, ensure_ascii=False))
            try:
                max_tokens = self.cost.pre_request_check(input_chars, self.max_output_tokens)
            except BudgetExceededError as e:
                self.result.status = "budget_exceeded"
                self.result.summary = str(e) + " Files generated so far were preserved."
                self.on_event("error", self.result.summary)
                return self._finalize(i - 1)

            est = self.cost.estimate_request_cost(input_chars, max_tokens)
            self.on_event(
                "status",
                f"Iteration {i}/{self.max_iterations}: calling deepseek-v4-pro "
                f"(max_tokens={max_tokens}, est. cost ${est:.4f}, remaining ${self.cost.remaining_usd:.4f}).",
            )
            try:
                resp = self.client.chat(self.messages, tools, max_tokens=max_tokens)
            except LLMError as e:
                self.result.error = str(e)
                self.on_event("error", f"API error: {e}")
                return self._finalize(i)

            # --- POST-request accounting ------------------------------
            request_cost = self.cost.record_response(resp.usage)
            self._emit_usage(request_cost)
            self.messages.append(self._assistant_message(resp))

            if not resp.has_tool_calls:
                text = (resp.content or "").strip()
                if text:
                    self.on_event("assistant", text)
                self.result.status = "completed"
                self.result.summary = text or "Model finished without a finish call."
                return self._finalize(i)

            finished = False
            for tc in resp.tool_calls:
                if self.cancel.is_set():
                    self.messages.append(tool_result_message(tc.id, "ERROR: cancelled by user."))
                    continue
                self.result.tool_calls += 1
                args_preview = json.dumps(tc.arguments, ensure_ascii=False)
                if len(args_preview) > 300:
                    args_preview = args_preview[:300] + "..."
                self.on_event("tool", f"{tc.name}({args_preview})")

                if tc.name == "finish":
                    result = self._handle_finish(tc.arguments)
                    if result.startswith("FINISH:"):
                        finished = True
                        self.result.summary = result[len("FINISH:"):].strip()
                else:
                    result = self.registry.execute(tc.name, tc.arguments)
                    if tc.name == "write_file" and result.startswith("OK:") and isinstance(tc.arguments.get("path"), str):
                        self.result.files_written.append(tc.arguments["path"])

                self.on_event("tool_result", result if len(result) <= 400 else result[:400] + "...")
                self.messages.append(tool_result_message(tc.id, result))

            if finished:
                self.result.status = "completed"
                return self._finalize(i)

        self.result.status = "max_iterations"
        self.result.summary = f"Reached the iteration budget ({self.max_iterations}) before finish."
        self.on_event("error", self.result.summary)
        return self._finalize(self.max_iterations)

    # ------------------------------------------------------------------
    def _handle_finish(self, arguments: dict) -> str:
        """Accept finish only when the generated project actually validates."""
        report = validate_project(self.registry.ws.root)
        self.result.validation = report
        summary = arguments.get("summary", "") if isinstance(arguments, dict) else ""
        if report["valid"] or self._finish_rejections >= MAX_FINISH_REJECTIONS:
            if not report["valid"]:
                self.on_event("error", "Finish accepted with unresolved validation issues: " + "; ".join(report["issues"]))
            return f"FINISH: {summary}"
        self._finish_rejections += 1
        issues = "; ".join(report["issues"])
        self.on_event("error", f"Finish rejected — validation failed: {issues}")
        return (
            "ERROR: finish rejected. The project is not complete/valid yet. "
            f"Issues: {issues}. Fix them with write_file/run_command, then call finish again."
        )

    def _emit_usage(self, request_cost: float) -> None:
        payload = {
            "total_cost_usd": round(self.cost.total_cost_usd, 6),
            "remaining_usd": round(self.cost.remaining_usd, 6),
            "budget_usd": self.cost.budget_usd,
            "last_request_cost_usd": round(request_cost, 6),
            "totals": self.cost.totals.as_dict(),
        }
        self.on_event("usage", json.dumps(payload, ensure_ascii=False))

    def _finalize(self, iterations: int) -> AgentResult:
        self.result.iterations = iterations
        self.result.usage = self.cost.totals.as_dict()
        self.result.cost_usd = round(self.cost.total_cost_usd, 6)
        ws_root = self.registry.ws.root

        # Reports are always written, even on budget stop / error / cancel.
        self._write_json(ws_root / "usage_report.json", self.cost.report())
        self.result.validation = self.result.validation or validate_project(ws_root)
        self._write_json(ws_root / "validation_report.json", self.result.validation)
        trace = build_traceability(self._preprocessed_cache(), self.result.files_written)
        self._write_json(ws_root / "traceability_report.json", trace)
        try:
            (ws_root / "traceability_report.md").write_text(render_markdown(trace), encoding="utf-8")
        except OSError:
            pass
        self._write_json(ws_root / "agent_run_log.json", {
            "result": {
                "status": self.result.status, "summary": self.result.summary,
                "iterations": self.result.iterations, "tool_calls": self.result.tool_calls,
                "files_written": self.result.files_written, "usage": self.result.usage,
                "cost_usd": self.result.cost_usd, "error": self.result.error,
                "validation": self.result.validation,
            },
            "messages": self.messages,
        })
        self.on_event(
            "status",
            f"Run finished: {self.result.status} | {self.result.iterations} iterations | "
            f"{len(self.result.files_written)} files | cost ${self.result.cost_usd:.4f}.",
        )
        self._emit_usage(0.0)
        return self.result

    def _preprocessed_cache(self) -> dict:
        try:
            return json.loads((self.registry.ws.root / "preprocessed_input.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"architecture": {"requirements": []}, "views": {"diagrams": []}}

    @staticmethod
    def _write_json(path: Path, data) -> None:
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _assistant_message(resp: LLMResponse) -> dict:
        msg: dict = {"role": "assistant", "content": resp.content or ""}
        # Preserve reasoning_content for thinking-mode multi-turn continuity.
        if resp.reasoning_content:
            msg["reasoning_content"] = resp.reasoning_content
        if resp.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                for tc in resp.tool_calls
            ]
        return msg
