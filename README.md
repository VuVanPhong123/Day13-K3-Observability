# Day 13 — Observability cho hệ thống AI

## Nhóm thực hiện

1. Hà Duy Anh — Logging & PII
2. Đoàn Nhật Nam — Dashboard, SLO & Alert
3. Vũ Văn Phong — Tracing, Prompt Version, Challenge & final integration

Chi tiết đóng góp và evidence nằm trong [`submission/REPORT.md`](submission/REPORT.md).

Trong lab 4 giờ này, bạn sẽ biến một API AI chạy được nhưng khó quan sát thành một hệ thống có thể theo dõi, phát hiện sự cố và giải thích nguyên nhân bằng bằng chứng.

## Sau lab, bạn làm được gì?

- Ghi log JSON có cấu trúc và correlation ID xuyên suốt một request.
- Loại bỏ PII trước khi dữ liệu được ghi vào log.
- Theo dõi latency, error, token, cost và quality proxy.
- Đọc metrics → mở trace → dùng log để chứng minh root cause.
- Thiết kế dashboard, SLO, alert và runbook cơ bản.
- Viết báo cáo incident có trace ID hoặc log cụ thể làm bằng chứng.

## Bạn cần hoàn thành

1. Hoàn thiện các khối `TODO` trong `app/` và `config/`.
2. Tạo tối thiểu 10 traces có metadata trên Langfuse.
3. Tạo hai phiên bản prompt cơ bản theo [hướng dẫn prompt versioning](docs/PROMPT_VERSIONING.md), gắn label và chứng minh trace liên kết đúng phiên bản.
4. Dựng dashboard theo [`config/dashboard.yaml`](config/dashboard.yaml), làm theo [hướng dẫn dashboard](docs/DASHBOARD_SETUP.md) và chạy validator thành công.
5. Điều tra challenge chính thức sau khi Lab Coach release `config/challenge.json`.
6. Hoàn thiện `submission/REPORT.md` và lưu bằng chứng trong `submission/evidence/`.

## Luồng làm bài bắt buộc

| Mốc | Làm gì | Tự kiểm tra | Evidence |
|---|---|---|---|
| Setup | Cài Python, cấu hình Langfuse chung/cloud; Docker local chỉ khi cần | `/health` trả `ok: true` | ảnh health và môi trường không lộ key |
| Logging & PII | Hoàn thiện correlation ID, metadata và redaction | `python scripts/validate_logs.py` đạt ít nhất 80/100 | log có correlation ID và log đã che PII |
| Trace & Prompt Version | Tạo prompt v1/v2, chạy cùng input với hai label | trace có `prompt_name`, `prompt_label`, `prompt_version` | hai trace ID và ảnh đổi label/rollback |
| Dashboard & SLO | Dựng đúng 6 panel từ `data/logs.jsonl` | `python scripts/validate_dashboard.py` báo `6/6 panel` | ảnh dashboard có time range, đơn vị, threshold |
| Challenge | Chỉ chạy sau khi Lab Coach release file chính thức | nối được Metrics → Traces → Logs | root cause, fix và preventive measure |
| Nộp bài | Hoàn thiện report, tests và Git | `python -m pytest -q` | repo URL, commit SHA và `submission/` |

Chi tiết thời gian và tiêu chí qua từng mốc nằm ngay trong [CHECKPOINTS.md](CHECKPOINTS.md); cấu trúc nộp bài nằm trong [SUBMISSION.md](SUBMISSION.md).

Trong lab này, Langfuse dùng cho trace và prompt versioning; nguồn chuẩn của 6 panel dashboard là `data/logs.jsonl`. Chạy Langfuse local không thay đổi dashboard contract.

## 15 phút đầu

1. Làm theo [SETUP.md](SETUP.md).
2. Chạy API: `uvicorn app.main:app --reload --env-file .env`.
3. Ở terminal khác, chạy: `python scripts/load_test.py`.
4. Mở `data/logs.jsonl` và ghi lại những trường còn thiếu.
5. Chạy `python scripts/validate_logs.py` để lấy baseline.
6. Chạy `python scripts/validate_dashboard.py` để hiểu contract của dashboard.

Kết quả đúng ở bước 6 phải có dòng `HỢP LỆ: 6/6 panel`. Lệnh này chỉ kiểm tra contract; ảnh dashboard runtime vẫn phải nộp.

## Practice và challenge chính thức

- Practice luôn dùng được: `python scripts/inject_incident.py --scenario rag_slow`.
- Challenge chính thức chỉ chạy sau khi có `config/challenge.json`.
- Khi được release, chạy:

```bash
python scripts/inject_incident.py
python scripts/load_test.py --challenge --concurrency 5
```

Nếu file chưa được release, script sẽ dừng và yêu cầu chờ Lab Coach. Không tự tạo hoặc sửa `config/challenge.json`.

## Cấu trúc repo

```text
app/          API, agent, logging, metrics, tracing và PII
config/       log schema, dashboard contract, SLO, alert và challenge được release
data/         dữ liệu practice và log sinh ra khi chạy
docs/         hướng dẫn, dashboard spec và biểu mẫu bằng chứng
scripts/      load test, inject incident và kiểm tra log
tests/        public tests
submission/   báo cáo và evidence phải nộp
```

## Tài liệu cần đọc

- [CHECKPOINTS.md](CHECKPOINTS.md): tiến độ và đầu ra từng mốc.
- [RULES.md](RULES.md): quy định của bài lab.
- [SUBMISSION.md](SUBMISSION.md): cấu trúc bài nộp.
- [RUBRIC.md](RUBRIC.md): cách chấm tối đa 100 điểm.
- [docs/GUIDE.md](docs/GUIDE.md): gợi ý khi bị kẹt.
- [docs/PROMPT_VERSIONING.md](docs/PROMPT_VERSIONING.md): version, label và rollback prompt.
- [docs/DASHBOARD_SETUP.md](docs/DASHBOARD_SETUP.md): nguồn dữ liệu và cách kiểm tra dashboard.

## Phân vai nhóm — tối đa 4 vai trò

| Vai trò | Phạm vi chính | Evidence phải bàn giao |
|---|---|---|
| Logging & PII | correlation ID, metadata, JSON log, redaction | log hợp lệ và bằng chứng không lộ PII |
| Tracing & Prompt Version | traces, metadata, prompt v1/v2, label/rollback | trace gắn đúng prompt version |
| Dashboard, SLO & Alert | 6 panel, threshold, SLO, alert và runbook | validator + ảnh dashboard |
| Incident, Report & Demo | chạy challenge, nối metrics → traces → logs | root cause, fix và demo cuối |

Một người có thể giữ hai vai trò khi nhóm ít người; không tách thêm vai trò chỉ để chia nhỏ đầu việc.

## Lưu ý

- App dùng fake LLM nên phần practice không cần API key trả phí.
- Langfuse chung/cloud là cách mặc định; Docker Compose local chỉ là lựa chọn dự phòng trong `SETUP.md`.
- Không có Langfuse key, app vẫn chạy bằng prompt local nhưng bạn không có bằng chứng trace/prompt version để lấy trọn điểm.
- `validate_logs.py` chỉ là kiểm tra kỹ thuật nhanh, không phải điểm cuối cùng.
- Không commit `.env`, API key, `.venv/` hoặc log chứa dữ liệu nhạy cảm.
