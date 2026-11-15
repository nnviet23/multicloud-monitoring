# Accuracy Measurement

## 1. Mục tiêu và phạm vi

Accuracy experiment đánh giá mức độ telemetry metrics được phát từ workload generator có thể được quan sát ở Hub và đối chiếu với ground truth.

Cần phân biệt ba khái niệm:

1. **Generator send status:** generator báo số lần gửi thành công/thất bại theo logic của nó.
2. **Hub/Prometheus observation:** metrics được OTel Hub xuất và Prometheus scrape.
3. **Measurement result:** collector truy vấn dữ liệu quan sát được và tính các chỉ số.

Ba khái niệm này không tương đương. Generator gửi thành công không tự chứng minh Hub đã nhận; Job hoàn tất cũng không chứng minh toàn bộ datapoint đã được scrape.

## 2. Execution flow

Theo source được kiểm tra trong audit:

1. `common/config.py` nạp và kiểm tra cấu hình.
2. `common/result_writer.py` tạo experiment ID.
3. `workloads/ground_truth.py` tạo ground truth xác định theo scenario, source ID và seed.
4. `workloads/run_experiment.py` render Kubernetes Job từ `k8s/job-template.yaml`.
5. Job chạy `workloads/generator.py` trong spoke.
6. Generator gửi OTLP HTTP metrics tới OTel Spoke endpoint.
7. Spoke chuyển tiếp OTLP tới OTel Hub.
8. Hub Prometheus exporter xuất metrics tại `:8889`.
9. Prometheus scrape Hub exporter theo cấu hình.
10. `workloads/collect.py` truy vấn endpoint tương thích Prometheus/Thanos Query và thu thập snapshot.
11. `run_experiment.py` tính Accuracy và ghi kết quả.

Đường đi metrics được audit mô tả là:

`Generator → OTel Spoke → OTLP → OTel Hub → Prometheus exporter :8889 → Prometheus scrape → Thanos Query → local collector`

Không mô tả luồng này là Prometheus Remote Write → Thanos Receive; các thành phần đó không có bằng chứng cấu hình trong phạm vi audit.

## 3. Ground truth

Ground truth được tạo xác định theo:

- scenario;
- source ID;
- seed.

Theo implementation được audit, số datapoint theo scenario là:

| Scenario | Số datapoint |
|---|---:|
| `small` | 1,000 |
| `medium` | 10,000 |
| `large` | 50,000 |
| `stress` | 100,000 |

Timestamp trong ground truth là timestamp tổng hợp dựa trên mốc `2020-01-01 UTC` cộng offset theo sequence. Đây **không phải thời gian gửi thực tế** và không được dùng trực tiếp để tính end-to-end latency.

## 4. Metrics được generator phát

| Metric | Kiểu/ý nghĩa | Vai trò |
|---|---|---|
| `measurement_datapoints_total` | Cumulative counter | Đếm datapoint theo semantics của generator |
| `measurement_run_expected_total` | Counter expected | Thể hiện số lượng expected theo implementation |
| `measurement_last_sequence_id` | Gauge | Sequence cuối |
| `measurement_last_value` | Gauge | Giá trị cuối |

Các attributes dùng để phân biệt run/source gồm `experiment_id`, `source_id` và `test`; resource attributes có thể được chuyển thành Prometheus labels ở Hub exporter.

## 5. Chỉ số Accuracy

### 5.1 Completeness

Theo logic được audit:

\[
Completeness(\%) =
\frac{\min(counter_{final}, expected)}{expected}\times 100
\]

Đây là tỷ lệ dựa trên counter cuối cùng. Nó không xác nhận từng sequence đã được nhận đúng một lần.

### 5.2 Loss

\[
Loss(\%) = \max(0,\ 100 - Completeness(\%))
\]

Loss được suy ra từ completeness, không phải phép đối chiếu độc lập từng datapoint.

### 5.3 Correctness

Implementation so sánh sequence cuối cùng quan sát được với sequence cuối kỳ vọng, đồng thời so sánh giá trị cuối cùng với tolerance trong code.

Điều này chỉ kiểm tra **final sequence/final value**. Nếu dữ liệu ở giữa bị mất hoặc trùng nhưng giá trị cuối vẫn đúng, phép kiểm tra cuối này có thể không phát hiện.

### 5.4 Duplication

Theo audit, duplication được suy ra từ:
- counter vượt expected;
- các dòng trùng khớp chính xác trong `received_samples.csv`.

Do Prometheus scrape tạo snapshot, cùng một giá trị xuất hiện ở nhiều thời điểm không tự động có nghĩa là duplicate delivery. Chỉ số này không phải cơ chế phát hiện duplicate datapoint hoàn chỉnh.

## 6. Giới hạn của scrape model

Prometheus scrape lấy snapshot theo chu kỳ (Hub measurement scrape được cấu hình 5 giây trong tài liệu audit). Vì vậy:

- Một OTLP datapoint có thể được gửi và xử lý giữa hai lần scrape nhưng không có sample riêng tương ứng.
- Counter có thể phản ánh mức tăng tổng giữa hai lần scrape, nhưng không chứa danh tính từng datapoint.
- Gauge phản ánh giá trị tại thời điểm scrape.
- Nhiều physical series có thể xuất hiện nếu label identity thay đổi.
- Query window rộng hơn không khôi phục được các datapoint chưa từng được scrape.

Vì vậy, nên gọi kết quả hiện tại là counter-based completeness/last-value correctness, không gọi là full per-datapoint delivery accuracy.

## 7. Rủi ro cardinality: `telemetry.hub.received_time`

Audit phát hiện Hub transform gắn `telemetry.hub.received_time` bằng thời gian hiện tại vào resource attributes; exporter bật `resource_to_telemetry_conversion`.

Nếu thuộc tính này được chuyển thành Prometheus label, giá trị thay đổi liên tục có thể làm mỗi lần scrape tạo ra label set khác, dẫn đến time-series cardinality tăng nhanh. Điều này có thể làm tăng bộ nhớ/TSDB churn và gây nhập nhằng khi collector truy vấn nhiều series.

Trước khi chạy benchmark dài:
- xác minh attribute này có thực sự trở thành label trong output exporter;
- không dùng timestamp biến thiên làm label identity;
- cân nhắc chuyển receive time thành datapoint attribute hoặc một cơ chế đo latency phù hợp;
- đánh giá lại cách collector gộp nhiều series và xử lý counter reset.

Không kết luận cardinality đã tăng tới một mức cụ thể nếu chưa có số liệu runtime tương ứng.

## 8. Generator và Job semantics

Theo source được audit:
- Generator không retry khi HTTP send thất bại.
- Lỗi gửi được ghi vào summary.
- Job có thể exit code 0 dù có một số lần gửi thất bại.

Do đó phải kiểm tra generator summary và collector summary, không chỉ kiểm tra Job status.

## 9. Output artifacts

Kết quả được ghi tại:

`results/accuracy/<experiment_id>/`

| File | Nội dung |
|---|---|
| `metadata.json` | Metadata run |
| `ground_truth.csv` | Expected datapoints |
| `received_samples.csv` | Snapshot/query results |
| `collect_summary.json` | Polling, counter, endpoint và lỗi |
| `accuracy.json` | Accuracy theo source và tổng hợp |

## 10. Cách báo cáo kết quả

Mỗi kết quả cần nêu:
- experiment ID, scenario, seed, source;
- expected count và semantics của expected;
- generator sent success/failure;
- counter cuối được query;
- completeness/loss;
- final sequence/value comparison;
- duplication heuristic được dùng;
- scrape interval và query window;
- missing series, timeout, counter reset, cardinality concern;
- trạng thái bằng chứng và thời điểm chạy.

**Không khẳng định đã đo được per-datapoint delivery correctness bằng phương pháp hiện tại.**
