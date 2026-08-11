# Official challenge investigation

## Released challenge

- Cohort: `K3`
- Challenge ID: `day13-k3-observability-v1`
- Affected feature: `refund`
- Official latency threshold: `2000 ms`
- Official runtime used the released queries only; `config/challenge.json` was read and not changed.

## Metrics → trace → logs

The clean baseline recorded P95 latency of **536 ms** in
[`baseline-metrics.json`](baseline-metrics.json). The five most recent released
challenge requests recorded P95/P99 latency of **3089 ms**, above the official
2000 ms threshold, in
[`challenge-request-metrics.json`](challenge-request-metrics.json).

The slow request has correlation ID `req-31aabd39` and trace ID
`6bb38e58439286544d8960d265f696c8`. Its real Langfuse waterfall is stored in
[`trace-waterfall.json`](trace-waterfall.json):

- `retrieval`: **2.501 s**
- `prompt_resolution`: 0.437 s
- `llm_generation`: 0.151 s
- `agent_execution`: 3.092 s

The matching records in [`challenge-log.json`](challenge-log.json) use the same
correlation ID. In particular, `retrieval_completed` records `tool_name`
`mock_rag` with `latency_ms: 2500`, while `response_sent` records total agent
latency of 3089 ms.

## Root cause

The abnormal latency is localized to retrieval/RAG: it accounts for about 2.5
seconds of the 3.1-second agent execution while generation stays near 0.15
seconds. This conclusion follows the P95 change, trace span timings, and the
correlated retrieval log—not merely the incident name in the released config.

## Production action and prevention

- Immediate mitigation: disable the affected retrieval incident/dependency path,
  which was done after evidence collection; `/health` returned all incidents as
  `false` afterward.
- Production fix: investigate the vector-store query/dependency latency, set a
  bounded retrieval timeout, and use a safe fallback when the retrieval budget
  is exhausted. The starter's incident simulator remains unchanged.
- Preventive monitoring: keep the `high_p95_latency` SLO alert and runbook,
  investigate a slow trace first, then use correlation ID to verify the matching
  structured log before declaring a root cause.
