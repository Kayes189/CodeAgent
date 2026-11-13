"""Strict API cost management.

Implements BOTH pre-request and post-request controls so spending stays
below the application budget (default $0.80, professor ceiling $1.00):

Post-request: read actual usage from each API response, track cached /
uncached input and output tokens, accumulate cost at conservative peak
pricing.

Pre-request: estimate the next request's cost, dynamically cap max_tokens
to the affordable output budget, and REFUSE the request if even the input
alone would exceed the remaining budget.

Pricing is configurable. When cache breakdown is unavailable, ALL input
tokens are treated as uncached (conservative).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Conservative peak pricing, USD per 1,000,000 tokens.
DEFAULT_PRICING = {
    "cached_input_per_million": 0.044,
    "uncached_input_per_million": 1.32,
    "output_per_million": 3.96,
}

# Rough chars-per-token heuristic for pre-request estimation (conservative:
# assume fewer chars per token => more tokens => higher estimated cost).
CHARS_PER_TOKEN = 3.0
# Safety margin kept untouched so estimation error cannot breach the budget.
SAFETY_MARGIN_USD = 0.02


@dataclass
class UsageTotals:
    cached_input_tokens: int = 0
    uncached_input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    @property
    def total_input_tokens(self) -> int:
        return self.cached_input_tokens + self.uncached_input_tokens

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "total_input_tokens": self.total_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
        }


def cost_for_tokens(cached: int, uncached: int, output: int, pricing: dict) -> float:
    return (
        cached * pricing["cached_input_per_million"]
        + uncached * pricing["uncached_input_per_million"]
        + output * pricing["output_per_million"]
    ) / 1_000_000


def estimate_tokens_from_chars(num_chars: int) -> int:
    return max(1, int(num_chars / CHARS_PER_TOKEN) + 1)


class BudgetExceededError(Exception):
    """Raised when a request cannot be afforded within the remaining budget."""


class CostManager:
    def __init__(self, budget_usd: float = 0.80, pricing: dict | None = None):
        self.budget_usd = float(budget_usd)
        self.pricing = dict(pricing or DEFAULT_PRICING)
        self.totals = UsageTotals()
        self.total_cost_usd = 0.0
        self.history: list[dict] = []

    # -- post-request accounting --------------------------------------
    def record_response(self, usage: dict) -> float:
        """Accumulate actual usage from an API response; return its cost."""
        cached = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
        miss = usage.get("prompt_cache_miss_tokens", None)
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)

        if miss is not None:
            uncached = int(miss)
        elif cached and prompt:
            uncached = max(0, prompt - cached)
        else:
            # No cache info -> treat ALL input as uncached (conservative).
            uncached = prompt
            cached = 0

        cost = cost_for_tokens(cached, uncached, completion, self.pricing)
        self.totals.cached_input_tokens += cached
        self.totals.uncached_input_tokens += uncached
        self.totals.output_tokens += completion
        self.totals.requests += 1
        self.total_cost_usd += cost
        self.history.append({
            "request_index": self.totals.requests,
            "cached_input_tokens": cached,
            "uncached_input_tokens": uncached,
            "output_tokens": completion,
            "cost_usd": round(cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 6),
        })
        return cost

    # -- pre-request guard --------------------------------------------
    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.total_cost_usd)

    def estimate_request_cost(self, input_chars: int, max_output_tokens: int) -> float:
        in_tokens = estimate_tokens_from_chars(input_chars)
        # Conservative: assume all input uncached for the estimate.
        return cost_for_tokens(0, in_tokens, max_output_tokens, self.pricing)

    def affordable_output_tokens(self, input_chars: int, requested_max: int) -> int:
        """Cap max_tokens so input + output fits the remaining budget."""
        in_tokens = estimate_tokens_from_chars(input_chars)
        input_cost = cost_for_tokens(0, in_tokens, 0, self.pricing)
        available = self.remaining_usd - SAFETY_MARGIN_USD - input_cost
        if available <= 0:
            return 0
        out_price = self.pricing["output_per_million"] / 1_000_000
        affordable = int(available / out_price) if out_price > 0 else requested_max
        return max(0, min(requested_max, affordable))

    def pre_request_check(self, input_chars: int, requested_max_tokens: int) -> int:
        """Return the max_tokens to use, or raise BudgetExceededError.

        Refuses the request when even the input alone cannot be afforded.
        """
        in_tokens = estimate_tokens_from_chars(input_chars)
        input_cost = cost_for_tokens(0, in_tokens, 0, self.pricing)
        if input_cost + SAFETY_MARGIN_USD > self.remaining_usd:
            raise BudgetExceededError(
                f"Remaining budget ${self.remaining_usd:.4f} cannot cover the estimated "
                f"input cost ${input_cost:.4f}. Stopping to stay under ${self.budget_usd:.2f}."
            )
        capped = self.affordable_output_tokens(input_chars, requested_max_tokens)
        if capped <= 0:
            raise BudgetExceededError(
                f"Remaining budget ${self.remaining_usd:.4f} leaves no room for output tokens. "
                "Stopping to stay under the budget."
            )
        return capped

    # -- reporting ----------------------------------------------------
    def report(self) -> dict:
        return {
            "budget_usd": round(self.budget_usd, 4),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "remaining_usd": round(self.remaining_usd, 6),
            "under_budget": self.total_cost_usd <= self.budget_usd,
            "pricing_per_million_tokens": dict(self.pricing),
            "totals": self.totals.as_dict(),
            "per_request": self.history,
            "controls": {
                "pre_request_estimate": True,
                "dynamic_max_tokens_cap": True,
                "post_request_actual_usage": True,
                "conservative_uncached_when_unknown": True,
                "safety_margin_usd": SAFETY_MARGIN_USD,
            },
        }
