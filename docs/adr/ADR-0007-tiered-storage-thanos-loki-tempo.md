# ADR-0007: Multi-Cloud Observability Storage Engine: Thanos, Loki, Tempo & MinIO S3

## Status
Implemented (Đã triển khai)

## Context
Thu thập dữ liệu viễn trắc đa đám mây (metrics, logs, traces) từ nhiều cụm tạo ra khối lượng dữ liệu khổng lồ theo thời gian. Việc lưu trữ trực tiếp toàn bộ dữ liệu trên các ổ đĩa cục bộ (Local Persistent Volumes / SSD) gặp phải các rào cản nghiêm trọng:
1. **Chi phí lưu trữ đắt đỏ (Storage Cost Spikes):** Ổ cứng thể rắn tốc độ cao (SSD/NVMe) có chi phí đắt hơn từ 5 đến 10 lần so với lưu trữ đối tượng (Object Storage như S3/MinIO).
2. **Thiếu khả năng truy vấn hợp nhất đa cụm (Siloed Querying):** Prometheus truyền thống chỉ lưu trữ trên một cụm duy nhất, không thể cung cấp góc nhìn toàn cảnh (Global View) tổng hợp số liệu từ cả `aws-k3d`, `azure-k3d` và `hub-k3d`.
3. **Hiệu năng suy giảm khi truy vấn dài hạn:** Khi người dùng truy vấn biểu đồ xu hướng trong 3 tháng hoặc 1 năm, Prometheus phải quét hàng triệu điểm dữ liệu thô (raw samples), dẫn đến hiện tượng quá tải bộ nhớ và treo trình duyệt.

## Decision
Chúng tôi quyết định chuẩn hóa toàn bộ ngăn xếp lưu trữ viễn trắc (Observability Storage Stack) theo mô hình **Phân tầng Lưu trữ (Tiered Storage Architecture)** kết hợp các thành phần mã nguồn mở hàng đầu:

### 1. Kiến trúc Metrics Hợp nhất với Thanos & MinIO
Triển khai hệ thống Metrics & Thanos trên cụm `hub-k3d` bao gồm các vai trò chuyên biệt:
- **`prometheus + thanos-sidecar`:** Prometheus thu thập metrics từ Hub OTel Gateway trên cổng `:8889` (`prometheus` exporter), lưu trữ tầng nóng TSDB cục bộ với thời gian ngắn chỉ **2 giờ (`2h`)** và tự động đóng gói, đẩy các khối TSDB 2 giờ lên tầng lưu trữ đối tượng MinIO S3 thông qua `thanos-sidecar` (cũng hỗ trợ nhận luồng mở rộng qua `thanos-receive` ở Phase 5).
- **MinIO S3 Object Storage:** Đóng vai trò tầng lưu trữ nguội và dài hạn (Cold/Warm Storage Tier) với các bucket chuyên biệt:
  - `thanos-metrics` (trước đây gọi là `thanos-data`): Lưu trữ toàn bộ khối metrics của Thanos.
  - `loki-data`: Lưu trữ các chunks nhật ký của Grafana Loki.
  - `tempo-traces`: Lưu trữ các khối traces của Grafana Tempo.
  - `raw-telemetry`: Lưu trữ dữ liệu viễn trắc thô bất biến phục vụ tái hiện thí nghiệm benchmark.
- **Thanos Store Gateway (`thanos-store`):** Đóng vai trò proxy cho phép Thanos Query đọc trực tiếp các khối dữ liệu lịch sử từ bucket `thanos-metrics` trên MinIO.
- **Thanos Compactor (`thanos-compact`):** Tự động hợp nhất các khối dữ liệu và áp dụng chính sách giảm độ phân giải (Downsampling) định kỳ:
  - **Dữ liệu thô (Raw Resolution):** Giữ lại trong **30 ngày (`30d`)**.
  - **Giảm độ phân giải 5 phút (5m Downsampling):** Tự động tổng hợp cho các khối dữ liệu sau **40 giờ (`40h`)**, thời hạn lưu trữ **90 ngày (`90d`)**.
  - **Giảm độ phân giải 1 giờ (1h Downsampling):** Tự động tổng hợp cho các khối dữ liệu sau **10 ngày (`10d`)**, thời hạn lưu trữ **365 ngày (`365d`)** (1 năm).
- **Thanos Query (`thanos-query`):** Điểm truy vấn tập trung duy nhất (Single Global Query Endpoint) cho Grafana, tự động hợp nhất và khử trùng lặp (deduplication) dữ liệu metrics từ cả tầng nóng (`thanos-sidecar`) và tầng lạnh (`thanos-store`).

### 2. Quản lý Logs Tập trung với Grafana Loki
- Triển khai **Grafana Loki** chế độ Single-Binary trên `hub-k3d`.
- Toàn bộ log thu thập từ OTel Collector được chuyển tiếp vào Loki qua OTLP HTTP / Push API.
- Tách bạch cấu trúc lưu trữ: Metadata index lưu trong TSDB cục bộ, log data chunks đẩy thẳng lên MinIO bucket `loki-data`.
- Áp dụng thời hạn lưu trữ log cục bộ trên lab k3d là **72 giờ (`72h`)** để tối ưu hóa không gian lưu trữ của máy trạm (có thể mở rộng lên 7–30 ngày trên môi trường cloud).

### 3. Phân tích Dấu vết Phân tán với Grafana Tempo
- Triển khai **Grafana Tempo** để nhận và lập chỉ mục các distributed traces.
- Lưu trữ các trace blocks trực tiếp trên MinIO bucket `tempo-traces`.
- Thời hạn lưu trữ traces cục bộ trên lab k3d là **24 giờ (`24h`)**.
- Cho phép liên kết ngữ cảnh 3 chiều: Metrics -> Traces (qua TraceID) -> Logs (qua SpanID).

### 4. Tự động hóa Bảng điều khiển Grafana bằng Sidecar
- Triển khai **Grafana** trên `hub-k3d` tích hợp container `k8s-sidecar`:
  - Tự động theo dõi các ConfigMaps có nhãn `grafana_dashboard: "1"` để nạp các dashboard SRE (TeaStore Overview, OTel Collector Health, Thanos Performance, SLO Tracking) mà không cần cấu hình thủ công qua giao diện.

## Consequences
### Tích cực (Positive)
- **Tiết kiệm tới 70% chi phí lưu trữ:** Việc chuyển đổi phần lớn dữ liệu từ SSD sang Object Storage (MinIO S3) và downsampling giúp duy trì khả năng truy vấn trong 365 ngày mà không làm đầy đĩa cứng.
- **Góc nhìn tập trung duy nhất (Global Observability):** Một bảng điều khiển Grafana duy nhất trên Hub có thể truy vấn liền mạch toàn bộ dữ liệu từ 3 đám mây.
- **Hiệu năng truy vấn vượt trội:** Nhờ cơ chế downsampling 5m và 1h của Thanos Compactor, các biểu đồ khoảng thời gian 30–90 ngày tải trong vòng chưa tới 1 giây.

### Tiêu cực & Thách thức (Trade-offs)
- Kiến trúc lưu trữ gồm nhiều thành phần phân tán (Thanos Receive, Store, Compactor, Query, MinIO) đòi hỏi cấu hình chuẩn xác và hiểu biết sâu về hệ sinh thái Thanos.
- Thanos Compactor không được chạy ở chế độ đa replica (Single-Replica only) để tránh xung đột ghi đè khối dữ liệu trên S3.

## Alternatives considered
1. **Lưu trữ toàn bộ dữ liệu trên Prometheus TSDB cục bộ:** Đòi hỏi ổ đĩa SSD dung lượng rất lớn, không hỗ trợ downsampling tự động, và không thể cung cấp góc nhìn toàn cục đa cụm.
2. **Sử dụng giải pháp thương mại SaaS (Datadog / New Relic):** Chi phí cấp phép bản quyền và lưu trữ viễn trắc vượt xa ngân sách của dự án nghiên cứu.
3. **Cortex / Mimir thay vì Thanos:** Mimir có kiến trúc phân tán mạnh mẽ nhưng đòi hỏi nhiều microservices hơn và tiêu tốn nhiều RAM hơn Thanos (~1.5GB vs ~500MB), không phù hợp với giới hạn 8–10 GB RAM của máy trạm.

## References
- Thanos Architecture & Components Documentation (Receive, Store Gateway, Compactor, Query)
- MinIO Object Storage for Kubernetes
- Grafana Loki: LogQL & Object Storage Storage Architecture
- Grafana Tempo: Distributed Tracing at Scale
