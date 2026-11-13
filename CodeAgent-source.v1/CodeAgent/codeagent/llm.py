"""DeepSeek V4-Pro API client (official OpenAI-compatible endpoint).

Strictly bound to https://api.deepseek.com and model ``deepseek-v4-pro``.
Uses the Chat Completions API with function/tool calling. Non-thinking mode
is the default (``thinking={"type": "disabled"}``); when thinking is enabled,
``reasoning_content`` is preserved on assistant messages.

Features: request/response handling, tool-call parsing, cache-token usage
extraction, exponential-backoff retries, connection testing, and clear
user-visible errors. The client never switches model or provider.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"


class LLMError(Exception):
    """User-visible API error."""


class AuthenticationError(LLMError):
    """Invalid or missing API key (HTTP 401/403)."""


class RateLimitError(LLMError):
    """Rate limited (HTTP 429)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)
    reasoning_content: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DeepSeekClient:
    """Chat client fixed to the official DeepSeek V4-Pro endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEEPSEEK_MODEL,
        timeout: int = 300,
        temperature: float = 0.2,
        max_retries: int = 3,
        thinking_enabled: bool = False,
    ):
        if base_url.rstrip("/") != DEEPSEEK_BASE_URL:
            raise LLMError(f"Only the official DeepSeek endpoint {DEEPSEEK_BASE_URL} is permitted.")
        if model != DEEPSEEK_MODEL:
            raise LLMError(f"Only model {DEEPSEEK_MODEL} is permitted; got {model!r}.")
        self.base_url = DEEPSEEK_BASE_URL
        self.model = DEEPSEEK_MODEL
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries
        self.thinking_enabled = thinking_enabled

    # ------------------------------------------------------------------
    def _payload(self, messages, tools, max_tokens):
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "thinking": {"type": "enabled" if self.thinking_enabled else "disabled"},
        }
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             max_tokens: int | None = None) -> LLMResponse:
        if not self.api_key:
            raise AuthenticationError("No DeepSeek API key configured.")
        body = json.dumps(self._payload(messages, tools, max_tokens)).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        last_error = ""
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._parse(data)
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", errors="replace")[:800]
                except Exception:
                    pass
                last_error = f"HTTP {e.code}: {detail or e.reason}"
                if e.code in (401, 403):
                    raise AuthenticationError(
                        "DeepSeek rejected the API key (HTTP %d). Check the key in the GUI." % e.code
                    ) from e
                if e.code == 429:
                    if attempt < self.max_retries:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                    raise RateLimitError("DeepSeek rate limit reached (HTTP 429). Try again later.") from e
                if e.code in _RETRYABLE_STATUS and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise LLMError(last_error) from e
            except urllib.error.URLError as e:
                last_error = f"Network error: {e.reason}"
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise LLMError(last_error) from e
            except (TimeoutError, OSError) as e:
                last_error = f"Request failed: {e}"
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise LLMError(last_error) from e
        raise LLMError(last_error or "Request failed after retries.")

    def test_connection(self) -> dict:
        """Cheap live call to verify the key/model. Returns usage + ok flag.

        Uses a tiny max_tokens to minimise cost. Raises LLMError on failure.
        """
        resp = self.chat(
            [{"role": "user", "content": "Reply with the single word: OK"}],
            tools=None, max_tokens=8,
        )
        return {"ok": True, "model": self.model, "usage": resp.usage,
                "reply": (resp.content or "").strip()}

    @staticmethod
    def _parse(data: dict) -> LLMResponse:
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected API response shape: {str(data)[:400]}") from e
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            if isinstance(raw_args, dict):
                args = raw_args
            else:
                try:
                    args = json.loads(raw_args)
                except ValueError:
                    args = {}
            tool_calls.append(ToolCall(
                id=tc.get("id") or f"call_{len(tool_calls)}",
                name=fn.get("name") or "", arguments=args,
            ))
        return LLMResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason") or "stop",
            usage=data.get("usage") or {},
            reasoning_content=msg.get("reasoning_content"),
        )


# Backwards-compatible alias used by older imports/tests.
LLMClient = DeepSeekClient
