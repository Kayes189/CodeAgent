"""Context manager: keep the conversation bounded.

Implements a compact-summary strategy (inspired by Claude Code's compression
pipeline): old write_file tool-call arguments (full source code) are replaced
with short summaries once they age out, while recent turns and all file-path
information are preserved so the agent still knows what exists. Tool results
are also trimmed. This prevents source code from accumulating unnecessarily.
"""
from __future__ import annotations

import json

CONTEXT_CHAR_BUDGET = 300_000
KEEP_RECENT_TURNS = 8


def _message_chars(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False))


def compact(messages: list[dict], budget: int = CONTEXT_CHAR_BUDGET,
            keep_recent: int = KEEP_RECENT_TURNS) -> tuple[list[dict], bool]:
    """Return (possibly compacted messages, changed?).

    Preserves message order and tool_call_id pairing (required by the API).
    Only the *content* of old assistant tool-call arguments and old tool
    results is summarised; ids and structure stay intact.
    """
    if _message_chars(messages) <= budget:
        return messages, False

    # Index of the boundary: keep the last `keep_recent` messages untouched.
    boundary = max(0, len(messages) - keep_recent)
    changed = False
    for i, msg in enumerate(messages):
        if i >= boundary:
            break
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                if fn.get("name") == "write_file":
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except ValueError:
                        args = {}
                    path = args.get("path", "?")
                    content = args.get("content", "")
                    summary = {
                        "path": path,
                        "content": f"[compacted: {len(content)} chars written earlier; "
                                   f"use read_file to view current content]",
                    }
                    fn["arguments"] = json.dumps(summary, ensure_ascii=False)
                    changed = True
        elif role == "tool":
            content = msg.get("content") or ""
            if len(content) > 500:
                msg["content"] = content[:500] + "\n... [old tool output compacted]"
                changed = True
    return messages, changed
