# Performance Measurement

## 1. Mục tiêu

Performance experiment hướng tới đo chi phí và khả năng xử lý telemetry của các Collector/pipeline trong môi trường multi-cloud mô phỏng.

Các nhóm đại lượng dự kiến gồm:
- CPU;
- memory;
- process uptime;
- accepted/sent/failed telemetry points;
- throughput/rate;
- queue size (nếu exporter queue được cấu hình);
- container CPU, memory và network.

Việc một metric xuất hiện trong YAML hoặc source không chứng minh metric đó có thể được thu thập trong runtime.

## 2. Cấu trúc xử lý

Theo code được audit, Performance gồm hai phần chính:

1. **Optional workload generator:** phát telemetry liên tục theo cấu hình workload.
2. **Sampler:** lấy mẫu các target theo interval, gọi source adapters và lưu raw samples.
3. **Summarizer:** tính thống kê gauge, rate và counter từ dữ liệu thu thập.

Tên module được audit gồm `performance/run.py`, `performance/sampler.py`, `performance/sources.py`, `performance/summarize.py` và `experiments/performance.py`. Cần đối chiếu lại CLI help nếu interface thay đổi.

## 3. Metric groups

### 3.1 OTel Collector internal metrics

| Metric | Ý nghĩa | Phép xử lý dự kiến |
|---|---|---|
| `otelcol_process_cpu_seconds` | CPU time của process | Rate từ counter delta |
| `otelcol_process_memory_rss` | Resident memory | Gauge |
| `otelcol_process_uptime` | Uptime | Gauge |
| `otelcol_receiver_accepted_metric_points` | Metric points được receiver chấp nhận | Rate |
| `accepted_log_records` | Log records được chấp nhận | Rate |
| `accepted_spans` | Spans được chấp nhận | Rate |
| `otelcol_exporter_sent_metric_points` | Metric points exporter gửi thành công | Rate |
| `otelcol_exporter_send_failed_metric_points` | Metric points gửi thất bại | Rate |
| `otelcol_exporter_queue_size` | Queue occupancy | Gauge; chỉ có ý nghĩa nếu queue tồn tại |

Audit ghi nhận sampler lấy OTel internal metrics qua endpoint `:8888`, nhưng endpoint này chưa được xác minh hoạt động. Cấu hình Prometheus target tới `:8888` không đủ chứng minh Collector đang expose internal telemetry.

### 3.2 Container/cAdvisor metrics

| Metric | Ý nghĩa | Phép xử lý |
|---|---|---|
| `container_cpu_usage_seconds_total` | CPU time container | Rate |
| `container_memory_working_set_bytes` | Working set memory | Gauge |
| `container_network_transmit_bytes_total` | Network transmitted bytes | Rate |
| `container_network_receive_bytes_total` | Network received bytes | Rate |

Audit ghi nhận target node trong `performance.yaml` còn placeholder `REPLACE_WITH_NODE`; Prometheus scrape config cũng không có cAdvisor target. Vì vậy không coi các metric này là đã thu thập được.

## 4. Cách tính thống kê

Theo `summarize.py` được kiểm tra:

- **Gauge:** mean, median, population standard deviation, min, max và các percentile được triển khai.
- **Rate:** tính từ counter delta giữa các timestamp liên tiếp; code có xử lý counter reset.
- **Counter:** lưu first, last và total increase.

Đây là mô tả thuật toán trong code. Tính đúng của phép thống kê không bù được việc đầu vào bị thiếu hoặc endpoint không hoạt động.

## 5. Kết quả audit hiện tại

Audit ngày 15/11/2026 kiểm tra các kết quả Performance lịch sử và ghi nhận:
- hai target spoke có `missing_counts` cho toàn bộ 15 metrics;
- không có gauges, rates hoặc counters hợp lệ được tính;
- OTel internal endpoint `:8888` không truy cập được theo discovery snapshot;
- context trong cấu hình Performance không khớp context WSL được ghi nhận;
- node cAdvisor vẫn là placeholder;
- workload endpoints localhost phụ thuộc port-forward đang hoạt động.

Vì vậy, các run được kiểm tra **không đủ điều kiện làm benchmark**. Không sử dụng chúng để kết luận CPU, memory, throughput, network overhead hoặc so sánh AWS/Azure.

Đây là kết luận đối với các artifacts lịch sử được audit, không phải khẳng định rằng mọi lần chạy trong tương lai đều thất bại.

## 6. Điều kiện để một Performance run hợp lệ

Trước khi chạy:
1. OTel internal metrics phải được bật và endpoint xác minh được.
2. Mỗi target phải có context, namespace, pod/deployment và port chính xác.
3. Node name phải là tên node thực, không còn placeholder.
4. cAdvisor endpoint phải được xác minh nếu dùng container metrics.
5. Workload endpoint phải truy cập được từ nơi generator chạy.
6. Sampler phải thu được sample có timestamp/value hợp lệ.
7. Metric labels phải định danh đúng cluster/source/instance.
8. Thử một run ngắn để kiểm tra missing count trước chiến dịch đo chính.

Trong khi chạy:
- ghi raw sample;
- ghi missing count theo metric và target;
- ghi lỗi endpoint/timeout;
- không chuyển missing thành 0;
- lưu config, interval, duration, warmup và tải generator.

Sau khi chạy:
- kiểm tra raw samples;
- xác nhận số sample hợp lệ;
- kiểm tra counter reset và timestamp ordering;
- chỉ summarize các metric có đủ dữ liệu;
- đánh dấu run `PARTIAL`, `FAILED` hoặc `UNAVAILABLE` khi thiếu dữ liệu bắt buộc.

## 7. Output artifacts

Theo audit, Performance output nằm dưới:

`results/performance/<run_id>/`

| File | Nội dung |
|---|---|
| `metadata.json` | Cấu hình run, target và generator summary |
| `raw_samples.csv` | Dữ liệu dài theo metric/target/timestamp |
| `summary.json` | Thống kê gauge/rate/counter |

Cần kiểm tra thư mục thực tế và writer code nếu cấu trúc output được thay đổi.

## 8. Cách báo cáo

Một bảng kết quả Performance nên có:
- target/source;
- metric;
- unit;
- số sample hợp lệ;
- missing count;
- mean/median/p95/p99 hoặc rate tương ứng;
- interval và duration;
- trạng thái endpoint;
- trạng thái run;
- giới hạn đo.

Nếu `valid_samples = 0`, ghi `UNAVAILABLE`/`MISSING`, không ghi `0 CPU`, `0 memory` hoặc `0 throughput`.
