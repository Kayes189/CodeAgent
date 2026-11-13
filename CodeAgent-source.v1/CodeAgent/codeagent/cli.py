"""Command-line interface (DeepSeek V4-Pro only).

Usage:
    codeagent gui                                    # desktop GUI (default)
    codeagent run --doc A.md --view B.md --out DIR   # headless generation
    codeagent preprocess --doc A.md --view B.md -o out.json
    codeagent test-connection                        # live API check (tiny cost)

API key: secure store (DPAPI), env CODEAGENT_API_KEY, or --api-key.
The endpoint and model are fixed to https://api.deepseek.com / deepseek-v4-pro.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_settings


def _print_event(kind: str, text: str) -> None:
    if kind == "usage":
        try:
            u = json.loads(text)
            t = u["totals"]
            print(f"[cost] ${u['total_cost_usd']:.4f} spent / ${u['budget_usd']:.2f} budget "
                  f"| in={t['total_input_tokens']} out={t['output_tokens']} tokens", flush=True)
        except (ValueError, KeyError):
            pass
        return
    prefix = {"status": "[*]", "tool": "[tool]", "tool_result": "   ->",
              "assistant": "[model]", "error": "[!]"}.get(kind, "[?]")
    print(f"{prefix} {text}", flush=True)


def cmd_run(args: argparse.Namespace) -> int:
    from .agent import Agent
    from .cost import CostManager
    from .llm import DeepSeekClient
    from .tools import ToolRegistry, Workspace

    s = load_settings()
    if args.api_key:
        s.api_key = args.api_key
    if args.budget is not None:
        s.budget_usd = args.budget
    problems = s.validate()
    if problems:
        print("Configuration problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        print("Set the key via `codeagent gui`, env CODEAGENT_API_KEY or --api-key.", file=sys.stderr)
        return 2

    try:
        client = DeepSeekClient(s.api_key, timeout=s.request_timeout,
                                temperature=s.temperature, thinking_enabled=s.thinking_enabled)
        registry = ToolRegistry(Workspace(args.out))
        registry.generated_permission = bool(args.allow_generated)
    except (OSError, ValueError) as e:
        print(f"Invalid output directory: {e}", file=sys.stderr)
        return 2

    cost = CostManager(budget_usd=s.budget_usd, pricing=s.pricing)
    agent = Agent(client, registry, cost_manager=cost,
                  max_iterations=args.max_iterations, on_event=_print_event)
    result = agent.run(args.doc, args.view, args.instruction or "")
    print(f"\nStatus: {result.status}\nSummary: {result.summary}")
    print(f"Files: {len(result.files_written)} | iterations: {result.iterations} "
          f"| cost: ${result.cost_usd:.4f} | usage: {result.usage}")
    return 0 if result.status == "completed" else 1


def cmd_preprocess(args: argparse.Namespace) -> int:
    from .preprocess import preprocess_inputs

    data = preprocess_inputs(args.doc, args.view)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


def cmd_test_connection(args: argparse.Namespace) -> int:
    from .llm import DeepSeekClient, LLMError

    s = load_settings()
    if args.api_key:
        s.api_key = args.api_key
    if not s.api_key:
        print("No API key configured.", file=sys.stderr)
        return 2
    try:
        client = DeepSeekClient(s.api_key, timeout=60)
        info = client.test_connection()
        print(f"Connection OK. Model: {info['model']} | reply: {info['reply']!r} | usage: {info['usage']}")
        return 0
    except LLMError as e:
        print(f"Connection FAILED: {e}", file=sys.stderr)
        return 1


def cmd_gui(_args: argparse.Namespace) -> int:
    from .gui import main

    main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codeagent",
                                     description="Simplified Claude-Code-style coding agent (DeepSeek V4-Pro).")
    parser.add_argument("--version", action="version", version=f"codeagent {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_gui = sub.add_parser("gui", help="Launch the desktop GUI (default).")
    p_gui.set_defaults(func=cmd_gui)

    p_run = sub.add_parser("run", help="Run the generation task headlessly.")
    p_run.add_argument("--doc", required=True)
    p_run.add_argument("--view", required=True)
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--instruction", default="")
    p_run.add_argument("--api-key", default="")
    p_run.add_argument("--budget", type=float, default=None, help="Budget in USD (default 0.80)")
    p_run.add_argument("--max-iterations", type=int, default=60)
    p_run.add_argument("--allow-generated", action="store_true",
                       help="Permit run_command to execute generated programs")
    p_run.set_defaults(func=cmd_run)

    p_pre = sub.add_parser("preprocess", help="Only preprocess inputs to structured JSON.")
    p_pre.add_argument("--doc", required=True)
    p_pre.add_argument("--view", required=True)
    p_pre.add_argument("-o", "--output", default="")
    p_pre.set_defaults(func=cmd_preprocess)

    p_test = sub.add_parser("test-connection", help="Live API connection test (tiny cost).")
    p_test.add_argument("--api-key", default="")
    p_test.set_defaults(func=cmd_test_connection)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return cmd_gui(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
