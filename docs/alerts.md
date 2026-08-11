# Alert và Runbook

Mỗi alert dưới đây dựa trên triệu chứng người dùng hoặc mức vi phạm SLO, không phụ thuộc vào tên hàm, class hay implementation nội bộ. Khi nhận alert, owner xác nhận tác động trước, sau đó dùng luồng metrics → traces → logs để khoanh vùng nguyên nhân.

## Alert 1

- **Tên:** `high_latency_p95`
- **Severity:** `warning`
- **SLI/SLO liên quan:** `latency_p95_ms`; P95 phải dưới hoặc bằng 3.000 ms, target 99,5% trong cửa sổ 28 ngày.
- **Điều kiện kích hoạt:** `latency_p95 > 3000ms for 5 minutes`.
- **Ảnh hưởng tới người dùng:** Phần lớn request vẫn có thể thành công, nhưng nhóm người dùng ở tail latency phải chờ lâu hơn 3 giây, dễ timeout hoặc gửi lại request.
- **Ba bước kiểm tra đầu tiên:**
  1. Kiểm tra panel Latency trong 60 phút gần nhất, xác nhận P95 vượt 3.000 ms liên tục 5 phút và so sánh với traffic/error rate cùng thời điểm.
  2. Mở các trace chậm trong khoảng cảnh báo, xem waterfall và xác định observation nào chiếm phần lớn thời gian.
  3. Tìm log bằng correlation ID/session ID của trace chậm; kiểm tra incident đang bật, lỗi dependency, timeout và thay đổi triển khai gần nhất.
- **Mitigation tạm thời:** Giảm concurrency hoặc rate-limit lưu lượng tăng đột biến; vô hiệu hóa tính năng/incident gây chậm; chuyển sang đường xử lý hoặc dependency ổn định nếu có.
- **Owner:** `on-call-engineer`
- **Tự kiểm:** Alert chỉ dựa trên latency người dùng cảm nhận được; không chứa tên hàm hay component nội bộ. Sau mitigation, xác nhận P95 trở về ≤ 3.000 ms trong ít nhất 5 phút và lưu trace/log làm evidence.

## Alert 2

- **Tên:** `elevated_error_rate`
- **Severity:** `critical`
- **SLI/SLO liên quan:** `error_rate_pct`; error rate phải dưới hoặc bằng 2%, target 99% trong cửa sổ 28 ngày.
- **Điều kiện kích hoạt:** `error_rate_pct > 5 for 3 minutes`.
- **Ảnh hưởng tới người dùng:** Hơn 5% request thất bại; người dùng có thể không nhận được câu trả lời, gặp HTTP 5xx hoặc phải thử lại nhiều lần.
- **Ba bước kiểm tra đầu tiên:**
  1. Xác nhận error rate vượt 5% liên tục 3 phút, kiểm tra mẫu số request và bảng breakdown theo `error_type` để loại trừ cảnh báo do lưu lượng quá thấp.
  2. Chọn loại lỗi chiếm tỷ trọng lớn nhất, mở các trace lỗi tương ứng và ghi lại trace ID, session ID cùng thời điểm xảy ra.
  3. Tra log theo correlation ID của trace, kiểm tra exception, dependency, incident đang bật và thay đổi cấu hình/triển khai gần nhất.
- **Mitigation tạm thời:** Rollback thay đổi gần nhất nếu tương quan rõ; tắt incident hoặc tính năng gây lỗi; chuyển sang fallback và giới hạn retry để tránh khuếch đại sự cố.
- **Owner:** `on-call-engineer`
- **Tự kiểm:** Alert phản ánh request thất bại mà người dùng trực tiếp thấy. Sau mitigation, xác nhận error rate xuống ≤ 2% và các request kiểm tra trả thành công trước khi đóng incident.

## Alert 3

- **Tên:** `cost_budget_exceeded`
- **Severity:** `warning`
- **SLI/SLO liên quan:** `daily_cost_usd`; tổng chi phí phải dưới hoặc bằng 2,50 USD mỗi ngày, target 100%.
- **Điều kiện kích hoạt:** `daily_cost_usd > 2.5`.
- **Ảnh hưởng tới người dùng:** Chi phí vượt ngân sách có thể buộc nhóm hạn chế lưu lượng, giảm quota hoặc tạm dừng tính năng, từ đó làm giảm khả năng sử dụng dịch vụ.
- **Ba bước kiểm tra đầu tiên:**
  1. Xác nhận tổng chi phí trong đúng ngày và múi giờ báo cáo, sau đó so sánh với traffic để phân biệt tăng do lưu lượng hay tăng chi phí trên mỗi request.
  2. Kiểm tra `avg_cost_usd`, token input/output và các trace có cost cao nhất; đối chiếu model, feature và session liên quan.
  3. Kiểm tra cost spike, retry bất thường, prompt/context quá dài và thay đổi model hoặc cấu hình gần nhất.
- **Mitigation tạm thời:** Tắt cost spike/incident; giới hạn token và retry; rate-limit workload không thiết yếu hoặc chuyển sang model có chi phí thấp hơn khi không làm vi phạm quality SLO.
- **Owner:** `team-lead`
- **Tự kiểm:** Alert dựa trên tác động ngân sách dịch vụ, không dựa trên tên implementation. Sau mitigation, xác nhận tốc độ tăng chi phí đã giảm và dự báo cuối ngày không tiếp tục vượt xa ngân sách.

## Câu hỏi phản biện CP2

Alert kỹ thuật nên dựa trên triệu chứng người dùng thấy vì latency cao, request thất bại hoặc dịch vụ bị giới hạn bởi ngân sách phản ánh trực tiếp mức độ ảnh hưởng. Symptom-based alert giữ nguyên ý nghĩa khi implementation được refactor hoặc thay dependency, đồng thời giảm cảnh báo nhiễu từ những lỗi nội bộ không tác động tới người dùng. Tên hàm hoặc component vẫn hữu ích trong trace và log để tìm root cause, nhưng không nên là điều kiện paging chính.
