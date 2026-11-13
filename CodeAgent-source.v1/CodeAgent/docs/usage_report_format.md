# API Usage & Cost Report Format

Every run writes `usage_report.json` to the output directory (even on budget
stop, cancellation or error). Structure:

```json
{
  "budget_usd": 0.80,
  "total_cost_usd": 0.123456,
  "remaining_usd": 0.676544,
  "under_budget": true,
  "pricing_per_million_tokens": {
    "cached_input_per_million": 0.044,
    "uncached_input_per_million": 1.32,
    "output_per_million": 3.96
  },
  "totals": {
    "cached_input_tokens": 0,
    "uncached_input_tokens": 0,
    "total_input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "requests": 0
  },
  "per_request": [
    {
      "request_index": 1,
      "cached_input_tokens": 0,
      "uncached_input_tokens": 0,
      "output_tokens": 0,
      "cost_usd": 0.0,
      "cumulative_cost_usd": 0.0
    }
  ],
  "controls": {
    "pre_request_estimate": true,
    "dynamic_max_tokens_cap": true,
    "post_request_actual_usage": true,
    "conservative_uncached_when_unknown": true,
    "safety_margin_usd": 0.02
  }
}
```

## Cost formula
```
total_cost = (cached_input * 0.044 + uncached_input * 1.32 + output * 3.96) / 1_000_000
```
Pricing values are configurable (settings `pricing`) so they can be updated
if DeepSeek changes its rate card. The defaults are the conservative **peak**
rates verified against the official pricing page.

## Companion reports (same output directory)
- `preprocessed_input.json` — structured agent input.
- `traceability_report.json` / `.md` — requirement → diagram → file → test mapping.
- `validation_report.json` — generated-project validation result.
- `agent_run_log.json` — full transcript + result summary.
