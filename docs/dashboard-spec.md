# Yêu cầu dashboard

Contract có thể kiểm tra bằng máy nằm tại `config/dashboard.yaml`. Hướng dẫn dựng và kiểm tra runtime nằm tại [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).

## Cấu hình chung

- Tên dashboard: **Day 13 AI Observability**.
- Nguồn dữ liệu runtime: endpoint `GET /metrics` (`http://localhost:8000/metrics`).
- Khoảng thời gian mặc định: **1 giờ gần nhất**.
- Tần suất làm mới: **30 giây**.
- Công cụ sử dụng: **mô tả bằng spec**. Có thể hiện thực tương đương bằng Grafana hoặc Langfuse nếu giữ nguyên tên panel, đơn vị và threshold.
- Số panel ở lớp chính: **6 panel**.

## Đặc tả 6 panel

| # | Tên panel | Field từ `/metrics` | Kiểu hiển thị | Đơn vị | Khoảng thời gian | Threshold/SLO line |
|---|---|---|---|---|---|---|
| 1 | Latency P50/P95/P99 | `latency_p50`, `latency_p95`, `latency_p99` | Line chart hoặc ba Single Value | ms | 1 giờ | P95 ≤ 3.000 ms |
| 2 | Request Traffic | `traffic` | Counter tổng request; có thể bổ sung QPS hoặc request/phút từ các lần lấy mẫu | requests | 1 giờ | Traffic ≥ 1 request/phút |
| 3 | Error Rate & Breakdown | `error_rate_pct`, `error_breakdown` | Single Value cho tỷ lệ lỗi và bảng breakdown theo `error_type` | % và errors | 1 giờ | Error rate ≤ 2% |
| 4 | Total & Average Cost | `total_cost_usd`, `avg_cost_usd` | Single Value hoặc line chart so với ngân sách | USD | 1 giờ | Tổng chi phí ≤ 2,50 USD |
| 5 | Input/Output Tokens | `tokens_in_total`, `tokens_out_total` | Hai Single Value hoặc stacked line chart | tokens | 1 giờ | Tổng input và output ≤ 50.000 tokens |
| 6 | Average Quality Score | `quality_avg` | Gauge hoặc Single Value | score (0–1) | 1 giờ | Quality trung bình ≥ 0,75 |

## Ý nghĩa và cách đọc panel

### 1. Latency P50/P95/P99

P50 thể hiện trải nghiệm điển hình, còn P95 và P99 thể hiện tail latency. Đường SLO chính đặt tại P95 = 3.000 ms; panel chuyển sang trạng thái cảnh báo khi P95 vượt ngưỡng.

### 2. Request Traffic

`traffic` là tổng số request mà tiến trình API đã ghi nhận. Khi dashboard lấy mẫu định kỳ, chênh lệch giữa hai mẫu có thể được quy đổi thành request/phút hoặc QPS.

### 3. Error Rate & Breakdown

`error_rate_pct` thể hiện tỷ lệ request lỗi. `error_breakdown` được trình bày dạng bảng gồm loại lỗi và số lần xuất hiện để hỗ trợ tìm nguyên nhân chính. Nếu endpoint hiện tại chưa trả `error_rate_pct`, dashboard có thể tính tỷ lệ từ số lỗi trong `error_breakdown` và traffic, hoặc dùng phép tính tương ứng từ `data/logs.jsonl`.

### 4. Total & Average Cost

`total_cost_usd` được so sánh với ngân sách 2,50 USD. `avg_cost_usd` giúp phát hiện trường hợp chi phí trung bình trên mỗi request tăng dù traffic không đổi.

### 5. Input/Output Tokens

Hiển thị riêng `tokens_in_total` và `tokens_out_total` để nhận biết phần nào tạo ra mức tiêu thụ lớn. SLO line tổng hợp đặt tại 50.000 tokens.

### 6. Average Quality Score

`quality_avg` sử dụng thang điểm từ 0 đến 1. Giá trị dưới 0,75 được đánh dấu cảnh báo vì không đạt quality objective.

## Lưu ý về cửa sổ thời gian

Endpoint `/metrics` hiện trả snapshot cộng dồn trong bộ nhớ kể từ khi tiến trình API khởi động, không tự lưu chuỗi thời gian. Khi hiện thực dashboard 1 giờ, công cụ cần lấy mẫu mỗi 30 giây và chỉ hiển thị các mẫu trong 60 phút gần nhất. `data/logs.jsonl` vẫn là nguồn chuẩn của contract trong `config/dashboard.yaml` khi cần tính chính xác theo cửa sổ thời gian.

## Kiểm tra dữ liệu và contract

Xem snapshot hiện tại:

```bash
curl http://localhost:8000/metrics | python -m json.tool
```

Kiểm tra contract trước khi chụp evidence:

```bash
python scripts/validate_dashboard.py
```

Screenshot evidence phải nhìn rõ tên panel, khoảng thời gian 1 giờ, đơn vị và threshold/SLO line.
