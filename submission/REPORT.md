# Báo cáo Day 13 — Observability

## 1. Thông tin nhóm
- Repository URL: https://github.com/VinUni-AI20k/Day13-K3-Observability
- Commit SHA cuối: `0b09edb2f939f95fe17dcdcdc22b91736ee6df96` (implementation commit trước metadata-only finalization).
- Thành viên theo thứ tự:
  1. Hà Duy Anh
  2. Phạm Nhật Nam
  3. Vũ Văn Phong

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: **100/100**; 0 missing required field, 0 missing enrichment và 0 PII leak. Xem [`evidence/validate-logs.txt`](evidence/validate-logs.txt).
- Tổng số traces: **33** trace `agent_execution` được API Langfuse trả về tại lúc thu evidence; 22 trace ID cũng xuất hiện trong structured response logs. Xem [`evidence/langfuse-traces.json`](evidence/langfuse-traces.json) và ảnh [`evidence/langfuse-traces.png`](evidence/langfuse-traces.png).
- Số PII leak còn lại: **0**. Record runtime đã redact nằm tại [`evidence/pii-redaction-log.json`](evidence/pii-redaction-log.json).
- Health evidence: [`evidence/health.png`](evidence/health.png), với tracing enabled và các incident đều tắt.
- Dashboard local: chạy `python scripts/dashboard.py` rồi mở `http://127.0.0.1:8501/`. Snapshot runtime đủ sáu panel nằm tại [`evidence/dashboard-runtime.json`](evidence/dashboard-runtime.json), ảnh runtime tại [`evidence/dashboard.png`](evidence/dashboard.png).

## 3. Logging và tracing

- Evidence correlation ID: [`evidence/correlation-log.json`](evidence/correlation-log.json) ghi request `req-deadbeef`; body response và header `x-request-id` cùng giá trị. Middleware cũng trả `x-response-time-ms`.
- Evidence PII redaction: [`evidence/pii-redaction-log.json`](evidence/pii-redaction-log.json) chứa preview đã thay email, số điện thoại và thẻ bằng marker `[REDACTED_*]`; validator không phát hiện raw PII.
- Evidence trace waterfall: [`evidence/trace-waterfall.json`](evidence/trace-waterfall.json) và ảnh [`evidence/trace-waterfall.png`](evidence/trace-waterfall.png), trace `6bb38e58439286544d8960d265f696c8`.
- Span đáng chú ý: span `retrieval` mất **2.501 s**, `prompt_resolution` khoảng **0.437 s**, còn `llm_generation` khoảng **0.151 s** trong tổng `agent_execution` **3.092 s**. Trace metadata liên kết prompt managed `day13-chat`, label `production`, version `1` và correlation ID `req-31aabd39`.

## 4. Prompt versioning

- Prompt name: `day13-chat`.
- Version/label baseline: **v1** — `baseline`, ban đầu và cuối cùng cũng là `production`.
- Version/label candidate: **v2** — `candidate`; chỉ thêm instruction concise, vẫn giữ `Feature={{feature}}`, `Docs={{docs}}`, `Question={{message}}`.
- Trace ID của mỗi version:
  - Baseline v1: `a351bcb24406b163f8fdce683121d46a` — ảnh [`evidence/trace-baseline.png`](evidence/trace-baseline.png).
  - Candidate v2: `864af8594697818fa6ab45c67deaeb77` — ảnh [`evidence/trace-candidate.png`](evidence/trace-candidate.png).
  - Production promoted to v2: `7a04e55abcd72768f5ebb4584ff3d69a`.
  - Production after rollback to v1: `5d42cdab83fd0903288c6e5df0e59ce6`.
- Bằng chứng prompt versions: [`evidence/prompt-versions.json`](evidence/prompt-versions.json) và ảnh [`evidence/prompt-versions.png`](evidence/prompt-versions.png).
- Bằng chứng đổi label/rollback: [`evidence/prompt-rollback.txt`](evidence/prompt-rollback.txt) và ảnh [`evidence/prompt-rollback.png`](evidence/prompt-rollback.png). Production đã được rollback về **v1**.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: hợp lệ **6/6 panel**. Xem [`evidence/validate-dashboard.txt`](evidence/validate-dashboard.txt) và ảnh [`evidence/validate-dashboard.png`](evidence/validate-dashboard.png).
- Evidence dashboard: [`evidence/dashboard-runtime.json`](evidence/dashboard-runtime.json) dùng đúng `data/logs.jsonl`, time range 60 phút, refresh 30 giây, unit và threshold từ contract; ảnh dashboard: [`evidence/dashboard.png`](evidence/dashboard.png).
- SLO đã chọn và lý do: P95 latency ≤3000 ms, error rate ≤2%, daily cost ≤2.50 USD và quality mean ≥0.75, theo [`config/slo.yaml`](../config/slo.yaml). Chúng tương ứng với sáu signal dashboard và làm rõ user impact.
- Alert rules và runbook: đúng ba alert symptom/SLO-based (`high_p95_latency`, `high_error_rate`, `daily_cost_budget_exceeded`) tại [`config/alert_rules.yaml`](../config/alert_rules.yaml), với runbook cụ thể tại [`docs/alerts.md`](../docs/alerts.md).

## 6. Điều tra challenge

- Challenge ID: `day13-k3-observability-v1`, cohort `K3`, affected feature `refund`, official threshold 2000 ms.
- Triệu chứng từ metrics: clean baseline P95 **536 ms** ([`evidence/baseline-metrics.json`](evidence/baseline-metrics.json)); năm request challenge chính thức có P95/P99 **3089 ms**, vượt threshold ([`evidence/challenge-request-metrics.json`](evidence/challenge-request-metrics.json)).
- Trace ID liên quan: `6bb38e58439286544d8960d265f696c8`.
- Log line/correlation ID liên quan: `req-31aabd39`; `retrieval_completed` có `tool_name=mock_rag`, `latency_ms=2500`, và `response_sent` là 3089 ms trong [`evidence/challenge-log.json`](evidence/challenge-log.json).
- Root cause: retrieval/RAG chậm bất thường. Trace ghi retrieval 2.501 s trong tổng agent execution 3.092 s, còn generation chỉ 0.151 s; log cùng correlation ID xác nhận retrieval là thành phần chậm.
- Fix action: kiểm tra vector-store/dependency, đặt retrieval timeout/budget và fallback an toàn khi vượt budget; không thay đổi cơ chế incident simulation.
- Preventive measure: dùng alert P95 latency, mở trace chậm rồi đối chiếu correlated log trước khi kết luận root cause. Điều tra đầy đủ nằm tại [`evidence/challenge-investigation.md`](evidence/challenge-investigation.md). Incident đã được disable và `/health` trở lại normal.

## 7. Đóng góp cá nhân

Các đóng góp được mô tả theo vai trò lab trên worktree dùng chung; Git history không chứng minh commit/PR riêng cho từng thành viên.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Hà Duy Anh | Logging & PII: correlation ID, structured logging, metadata và PII redaction | N/A - final shared lab commit | Structured logging; correlation ID; PII scrubbing trước khi persist log. |
| Phạm Nhật Nam | Tracing & Prompt Version: Langfuse traces, prompt v1/v2, labels và production promotion/rollback | N/A - final shared lab commit | Tracing/span; prompt versioning; liên kết trace với managed prompt. |
| Vũ Văn Phong | Dashboard, SLO, alerts, challenge investigation và report/evidence integration | N/A - final shared lab commit | Percentile/SLO; Metrics → Traces → Logs; root-cause investigation. |
