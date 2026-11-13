"""Application configuration — DeepSeek V4-Pro ONLY.

The assignment mandates the official DeepSeek API and the model
``deepseek-v4-pro``. No other provider or model is permitted, and the
application never silently switches models. The API key is persisted
securely (Windows DPAPI / Credential Manager) via ``secrets_store`` and is
never written to this JSON config in plain text.

Environment overrides: CODEAGENT_API_KEY, CODEAGENT_BUDGET_USD.
The base URL and model are fixed by policy and are not user-editable.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import secrets_store

CONFIG_DIR = Path.home() / ".codeagent"
CONFIG_PATH = CONFIG_DIR / "config.json"

# --- Fixed by the assignment (do not change at runtime) -------------------
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"

# Conservative PEAK pricing (USD per 1,000,000 tokens). Configurable so the
# rate card can be updated if DeepSeek changes prices.
DEFAULT_PRICING = {
    "cached_input_per_million": 0.044,
    "uncached_input_per_million": 1.32,
    "output_per_million": 3.96,
}
DEFAULT_BUDGET_USD = 0.80
HARD_CEILING_USD = 1.00  # professor's absolute ceiling; app budget stays below


@dataclass
class Settings:
    # Fixed identity — validated, never overridden by config/env.
    base_url: str = DEEPSEEK_BASE_URL
    model: str = DEEPSEEK_MODEL
    api_key: str = ""  # loaded from secure store, not from the JSON file
    temperature: float = 0.2
    max_iterations: int = 60
    request_timeout: int = 300
    budget_usd: float = DEFAULT_BUDGET_USD
    thinking_enabled: bool = False  # non-thinking mode by default
    pricing: dict = field(default_factory=lambda: dict(DEFAULT_PRICING))

    def validate(self) -> list[str]:
        problems = []
        if self.base_url != DEEPSEEK_BASE_URL:
            problems.append(f"Base URL must be the official DeepSeek endpoint {DEEPSEEK_BASE_URL}.")
        if self.model != DEEPSEEK_MODEL:
            problems.append(f"Model must be {DEEPSEEK_MODEL}; other models are not permitted.")
        if not self.api_key.strip():
            problems.append("API key is empty.")
        if not 0.0 <= self.temperature <= 2.0:
            problems.append("Temperature must be between 0 and 2.")
        if not 1 <= self.max_iterations <= 500:
            problems.append("Max iterations must be between 1 and 500.")
        if not 0.0 < self.budget_usd <= HARD_CEILING_USD:
            problems.append(f"Budget must be between 0 and ${HARD_CEILING_USD:.2f}.")
        for key in DEFAULT_PRICING:
            val = self.pricing.get(key)
            if not isinstance(val, (int, float)) or val < 0:
                problems.append(f"Pricing '{key}' must be a non-negative number.")
        return problems


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_PATH
    s = Settings()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Only load non-secret, policy-safe fields.
            for fld in ("temperature", "max_iterations", "request_timeout",
                        "budget_usd", "thinking_enabled", "pricing"):
                if fld in data:
                    setattr(s, fld, data[fld])
            if isinstance(data.get("pricing"), dict):
                merged = dict(DEFAULT_PRICING)
                merged.update({k: v for k, v in data["pricing"].items() if k in DEFAULT_PRICING})
                s.pricing = merged
        except (OSError, ValueError):
            pass
    # Enforce fixed identity regardless of any stored value.
    s.base_url = DEEPSEEK_BASE_URL
    s.model = DEEPSEEK_MODEL
    # Secret comes from the secure store, then env override.
    s.api_key = secrets_store.load_key()
    if os.environ.get("CODEAGENT_API_KEY"):
        s.api_key = os.environ["CODEAGENT_API_KEY"]
    if os.environ.get("CODEAGENT_BUDGET_USD"):
        try:
            s.budget_usd = float(os.environ["CODEAGENT_BUDGET_USD"])
        except ValueError:
            pass
    return s


def save_settings(s: Settings, path: Path | None = None) -> Path:
    """Persist non-secret settings; store the API key securely (never in JSON)."""
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    secrets_store.save_key(s.api_key)
    payload = {
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
        "temperature": s.temperature,
        "max_iterations": s.max_iterations,
        "request_timeout": s.request_timeout,
        "budget_usd": s.budget_usd,
        "thinking_enabled": s.thinking_enabled,
        "pricing": s.pricing,
        "_note": "API key is stored securely via Windows DPAPI, not in this file.",
    }
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path
