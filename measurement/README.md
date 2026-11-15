# Multi-Cloud Monitoring — Measurement

Tài liệu này chỉ mô tả **measurement framework** của dự án: cách tổ chức, chạy, kiểm tra và diễn giải hai nhóm thực nghiệm **Accuracy** và **Performance** trên hai spoke mô phỏng AWS/Azure và Hub tập trung.

> **Phạm vi:** README này không phải README tổng quan toàn bộ nền tảng Multi-Cloud Monitoring. Các trạng thái runtime được nhắc đến bên dưới dựa trên báo cáo audit ngày 15/11/2026; cần xác minh lại trước mỗi đợt thực nghiệm.

## 1. Measurement framework làm gì?

Framework có hai nhánh:

| Nhánh | Câu hỏi cần trả lời | Trạng thái theo audit 15/11/2026 |
|---|---|---|
| **Accuracy** | Telemetry metrics phát từ workload có được quan sát ở Hub với mức độ đầy đủ và giá trị cuối đúng như kỳ vọng không? | Đã có luồng thực nghiệm và kết quả lịch sử; cần diễn giải đúng giới hạn scrape/counter |
| **Performance** | Chi phí tài nguyên và khả năng xử lý telemetry của Collector/pipeline thay đổi thế nào theo tải? | Các run Performance được audit thiếu toàn bộ metric mục tiêu; chưa có kết quả hợp lệ để kết luận |

## 2. Data flow phục vụ measurement

```text
Measurement Generator (AWS spoke)       Measurement Generator (Azure spoke)
              |                                        |
              v                                        v
       OTel Spoke Collector                      OTel Spoke Collector
              |                                        |
              +---------------- OTLP -----------------+
                                   |
                                   v
                           OTel Hub Collector
                                   |
                         Prometheus exporter :8889
                                   |
                           Prometheus scrape
                                   |
                            Thanos Query API
                                   |
                       Local measurement collector
                                   |
                    Accuracy / Performance results
```

Đây là luồng logic được mô tả từ source/config đã audit. Prometheus scrape là cơ chế lấy mẫu theo chu kỳ, không bảo đảm lưu lại từng OTLP datapoint. Endpoint và trạng thái runtime cần đối chiếu lại trước khi chạy.

## 3. Bắt đầu trong WSL

```bash
cd /mnt/e/file_VSCode/đo_an_tot_nghiep/multicloud-monitoring/measurement
source .venv/bin/activate
```

Các Kubernetes context được ghi nhận trong WSL tại thời điểm audit:

- `k3d-aws-k3d`
- `k3d-azure-k3d`
- `k3d-hub-k3d`

Không giả định các context này tồn tại trong PowerShell hoặc kubeconfig khác.

## 4. Accuracy

### Build/import image

```bash
bash scripts/build_import.sh small
```

Đảm bảo image tag truyền cho experiment trùng với tag đã build/import.

### Chạy experiment

```bash
python -m workloads.run_experiment \
  --scenario small \
  --sources aws,azure \
  --seed 0 \
  --image measurement:small
```

Đọc `python -m workloads.run_experiment --help` trong repository để xác nhận các tùy chọn đúng với phiên bản code hiện tại.

### Kết quả

Theo `result_writer.py` được kiểm tra trong audit, kết quả nằm tại:

`results/accuracy/<experiment_id>/`

Các file chính:

| File | Nội dung |
|---|---|
| `metadata.json` | Cấu hình run, scenario, seed, context và trạng thái |
| `ground_truth.csv` | Dữ liệu kỳ vọng do generator tạo |
| `received_samples.csv` | Dữ liệu/snapshot thu thập được |
| `collect_summary.json` | Trạng thái polling, counter, endpoint và lỗi |
| `accuracy.json` | Kết quả Accuracy theo source và tổng hợp |

### Giới hạn cần nhớ

Accuracy hiện dựa vào counter completeness và so sánh sequence/value cuối cùng. Nó **không chứng minh delivery correctness của mọi datapoint**. Generator không retry theo audit; Job có thể kết thúc thành công dù một số lần gửi thất bại. Xem [Accuracy methodology](docs/accuracy.md).

## 5. Performance

Performance framework có sampler, source adapters và bước tổng hợp thống kê. Tuy nhiên, audit ngày 15/11/2026 ghi nhận các run lịch sử được kiểm tra thiếu toàn bộ 15 metrics mục tiêu, không có gauge/rate/counter hợp lệ để so sánh.

Các phụ thuộc đang cần xử lý/xác minh:
- OTel internal metrics endpoint `:8888` chưa được xác minh hoạt động.
- Context trong `configs/performance.yaml` không khớp context WSL được ghi nhận.
- Node cAdvisor còn placeholder `REPLACE_WITH_NODE`.
- Workload endpoint localhost chỉ hoạt động khi port-forward tương ứng đang tồn tại.

Vì vậy, **không sử dụng các kết quả Performance lịch sử bị thiếu metrics để đưa ra kết luận hiệu năng**. Xem [Performance methodology](docs/performance.md).

## 6. Cảnh báo về Prometheus cardinality

Hub transform được audit có thêm `telemetry.hub.received_time` với giá trị thời gian hiện tại vào resource attributes; Prometheus exporter bật `resource_to_telemetry_conversion`. Nếu attribute này trở thành Prometheus label, giá trị thay đổi liên tục có thể tạo ra time series mới liên tục.

Đây là rủi ro cardinality quan trọng cần được xác minh và xử lý trước khi chạy benchmark dài hoặc diễn giải kết quả counter.

## 7. Tài liệu chi tiết

- [Accuracy](docs/accuracy.md): mục tiêu, flow, metrics, công thức, giới hạn và cách diễn giải.
- [Performance](docs/performance.md): metrics dự kiến, cách lấy mẫu, thống kê, lỗi hiện tại và điều kiện để kết quả hợp lệ.
- [Experiment protocol](docs/experiment-protocol.md): checklist trước/sau mỗi run và quy tắc kết luận.

## 8. Quy ước trạng thái kết quả

- `VERIFIED`: có bằng chứng runtime/implementation trực tiếp, kèm thời điểm.
- `CONFIGURED`: có trong source/config/manifest nhưng chưa xác minh hoạt động.
- `HISTORICAL`: chỉ được xác minh ở thời điểm trước đó.
- `UNVERIFIED`: chưa đủ bằng chứng.
- `PLANNED`: dự kiến nhưng chưa triển khai/kiểm chứng.
- `UNAVAILABLE`: thiếu endpoint/metric/cơ chế cần thiết.

Không coi metric bị thiếu là giá trị 0. Không coi Kubernetes Job `Complete` là bằng chứng tất cả telemetry đã được nhận.
