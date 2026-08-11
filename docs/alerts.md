# Alert runbooks

These three rules use user-visible symptoms and the SLOs in `config/slo.yaml`.
They are intentionally small enough to run from the local JSONL dashboard.

## High P95 latency

- Name: `high_p95_latency`
- Severity: critical
- SLI/SLO: `latency_p95_ms`, objective 3000 ms, target 99.5% over 28 days.
- Condition and duration: P95 latency is greater than 3000 ms continuously for 10 minutes.
- User impact: users wait longer for answers and may retry, increasing traffic and cost.
- First three checks:
  1. Confirm the P95/P99 window and request volume in the dashboard.
  2. Open a slow trace and compare retrieval, prompt resolution and generation span durations.
  3. Use the trace correlation ID to find the matching `response_sent` and `request_failed` records.
- Temporary mitigation: disable the affected practice/feature incident, reduce concurrency, and temporarily route traffic to a known-fast retrieval path if available.
- Owner: `ai-platform`

## High error rate

- Name: `high_error_rate`
- Severity: critical
- SLI/SLO: `error_rate_pct`, objective 2%, target 99.0% over 28 days.
- Condition and duration: failed requests exceed 2% continuously for 5 minutes.
- User impact: users receive HTTP 5xx responses or no usable answer.
- First three checks:
  1. Confirm the error-rate denominator and breakdown by `error_type`.
  2. Inspect a failed trace and its `request_failed` record by correlation ID.
  3. Check `/health` and the current incident state for an enabled dependency-failure scenario.
- Temporary mitigation: disable the affected incident, enable the local fallback path, and rate-limit retries while the dependency is recovered.
- Owner: `ai-platform`

## Daily cost budget exceeded

- Name: `daily_cost_budget_exceeded`
- Severity: warning
- SLI/SLO: `daily_cost_usd`, objective 2.50 USD per day, target 100% of daily budgets.
- Condition and duration: rolling daily response cost is above 2.50 USD for 15 minutes.
- User impact: the service risks exhausting its budget and may need throttling, causing delayed or rejected requests.
- First three checks:
  1. Compare total cost with request count and input/output token totals.
  2. Open generation observations to check output-token and model metadata.
  3. Compare the cost timeline with deployments, prompt labels and traffic spikes.
- Temporary mitigation: cap output tokens, reduce concurrency, and route to the configured low-cost fallback until the budget returns to normal.
- Owner: `ai-platform`
