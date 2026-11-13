import pytest

from codeagent.cost import (
    BudgetExceededError, CostManager, cost_for_tokens, estimate_tokens_from_chars,
)


def test_cost_formula_peak_pricing():
    # 1M cached + 1M uncached + 1M output at peak prices
    cost = cost_for_tokens(1_000_000, 1_000_000, 1_000_000, {
        "cached_input_per_million": 0.044,
        "uncached_input_per_million": 1.32,
        "output_per_million": 3.96,
    })
    assert abs(cost - (0.044 + 1.32 + 3.96)) < 1e-9


def test_record_with_cache_breakdown():
    cm = CostManager(budget_usd=0.80)
    cm.record_response({"prompt_tokens": 1000, "prompt_cache_hit_tokens": 600,
                        "prompt_cache_miss_tokens": 400, "completion_tokens": 200})
    assert cm.totals.cached_input_tokens == 600
    assert cm.totals.uncached_input_tokens == 400
    assert cm.totals.output_tokens == 200
    expected = (600 * 0.044 + 400 * 1.32 + 200 * 3.96) / 1e6
    assert abs(cm.total_cost_usd - expected) < 1e-9


def test_no_cache_info_all_uncached():
    cm = CostManager()
    cm.record_response({"prompt_tokens": 1000, "completion_tokens": 100})
    assert cm.totals.cached_input_tokens == 0
    assert cm.totals.uncached_input_tokens == 1000


def test_cache_hit_only_derives_miss():
    cm = CostManager()
    cm.record_response({"prompt_tokens": 1000, "prompt_cache_hit_tokens": 700,
                        "completion_tokens": 50})
    assert cm.totals.uncached_input_tokens == 300


def test_cumulative_cost():
    cm = CostManager()
    cm.record_response({"prompt_tokens": 1000, "completion_tokens": 100})
    first = cm.total_cost_usd
    cm.record_response({"prompt_tokens": 1000, "completion_tokens": 100})
    assert abs(cm.total_cost_usd - 2 * first) < 1e-9
    assert cm.totals.requests == 2


def test_pre_request_blocks_when_budget_exhausted():
    cm = CostManager(budget_usd=0.000001)
    with pytest.raises(BudgetExceededError):
        cm.pre_request_check(input_chars=100000, requested_max_tokens=8000)


def test_dynamic_max_tokens_cap():
    cm = CostManager(budget_usd=0.80)
    # Spend most of the budget (leave room above the safety margin).
    cm.total_cost_usd = 0.76
    capped = cm.pre_request_check(input_chars=100, requested_max_tokens=8000)
    assert capped < 8000
    assert capped >= 0


def test_affordable_output_zero_when_no_room():
    cm = CostManager(budget_usd=0.80)
    cm.total_cost_usd = 0.80
    assert cm.affordable_output_tokens(100, 8000) == 0


def test_estimate_conservative():
    cm = CostManager()
    est = cm.estimate_request_cost(3000, 1000)
    # all input treated uncached
    in_tok = estimate_tokens_from_chars(3000)
    expected = (in_tok * 1.32 + 1000 * 3.96) / 1e6
    assert abs(est - expected) < 1e-9


def test_report_structure():
    cm = CostManager(budget_usd=0.80)
    cm.record_response({"prompt_tokens": 100, "completion_tokens": 10})
    r = cm.report()
    assert r["budget_usd"] == 0.80
    assert r["under_budget"] is True
    assert r["controls"]["pre_request_estimate"] is True
    assert r["controls"]["post_request_actual_usage"] is True
    assert len(r["per_request"]) == 1


def test_remaining_never_negative():
    cm = CostManager(budget_usd=0.01)
    cm.record_response({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
    assert cm.remaining_usd == 0.0
