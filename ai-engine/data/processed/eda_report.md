# Multi-Cloud Observability Baseline Telemetry Profile (4-Hour Normal Dataset)

> **Báo cáo phân tích dữ liệu khám phá (EDA - Exploratory Data Analysis)**
> **Thời gian tạo:** 2026-10-25 20:44:59

## 1. Tổng quan Tập dữ liệu

- **Tổng số mẫu**: `1,440` mẫu (Chính xác 4.0 giờ).
- **Thời gian bắt đầu**: `2026-10-24T08:09:40Z`
- **Thời gian kết thúc**: `2026-10-24T12:09:30Z`
- **Chu kỳ lấy mẫu**: `10 giây/mẫu` (Độ liên tục: 100%, không bị gián đoạn hay mất gói).
- **Workload**: TeaStore Microservices trải rộng trên 2 cụm Kubernetes (`aws-k3d` cho Web/Logic và `azure-k3d` cho Database/Persistence) qua cầu mạng WAN mô phỏng (`10ms` RTT).

## 2. Phân tích Tiến trình 4 Giai đoạn Phụ tải (Hourly Progression)

| Giai đoạn | QPS Trung bình (Min - Max) | Latency P95 TB (Max) | WebUI CPU % (Max) | Cluster RAM % (Max) |
| :--- | :--- | :--- | :--- | :--- |
| **Hour 1 (Warmup)** | 84.1 (5.7 - 141.6) | 76.1ms (87.0ms) | 7.3% (55.4%) | 59.9% (73.8%) |
| **Hour 2 (Normal)** | 142.8 (76.8 - 209.6) | 80.8ms (97.4ms) | 9.3% (16.7%) | 59.7% (70.0%) |
| **Hour 3 (Peak)** | 216.9 (150.8 - 260.0) | 82.0ms (90.3ms) | 11.8% (16.5%) | 60.0% (72.4%) |
| **Hour 4 (Cooldown)** | 144.1 (50.3 - 252.0) | 80.3ms (85.8ms) | 7.9% (15.8%) | 60.6% (73.6%) |

## 3. Ma trận Tương quan Giữa các Chỉ số Vàng (Pearson Correlation)

| Chỉ số | Throughput QPS | Latency P95 | WebUI CPU % | Image CPU % | Persistence CPU % | WAN Traffic |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **throughput_qps** | 1.00 | 0.40 | 0.52 | 0.71 | 0.84 | 0.92 |
| **latency_p95** | 0.40 | 1.00 | -0.05 | 0.26 | 0.35 | 0.38 |
| **webui_cpu_pct** | 0.52 | -0.05 | 1.00 | 0.61 | 0.63 | 0.47 |
| **image_cpu_pct** | 0.71 | 0.26 | 0.61 | 1.00 | 0.78 | 0.65 |
| **persistence_cpu_pct** | 0.84 | 0.35 | 0.63 | 0.78 | 1.00 | 0.76 |
| **wan_network_io_kbs** | 0.92 | 0.38 | 0.47 | 0.65 | 0.76 | 1.00 |

## 4. Đề xuất Kiến trúc Đặc trưng (Feature Engineering) cho Mô hình AI

### A. Nhóm 14 Đặc trưng Cốt lõi (Input Vector $X \in \mathbb{R}^{14}$)
1. `throughput_qps`: Lưu lượng truy cập hệ thống.
2. `latency_p95`: Độ trễ phản hồi mức 95th percentile.
3. `app_cpu_pct`: Mức sử dụng CPU trung bình toàn cụm.
4. `max_pod_cpu_pct`: Điểm nóng CPU Pod nặng nhất (phát hiện nghẽn cổ chai).
5. `app_ram_pct`: Mức tiêu thụ Heap RAM trung bình toàn cụm.
6. `max_pod_ram_pct`: Điểm nóng RAM Pod cao nhất.
7. `jvm_threads_live`: Số luồng thực thi trong JVM.
8. `jvm_gc_pause_rate`: Thời gian dừng thu gom rác Garbage Collection.
9. `webui_cpu_pct`: CPU của Frontend WebUI trên AWS.
10. `webui_ram_pct`: RAM của Frontend WebUI trên AWS.
11. `persistence_cpu_pct`: CPU của tầng Persistence/Database trên Azure.
12. `persistence_ram_pct`: RAM của tầng Persistence/Database trên Azure.
13. `image_cpu_pct`: CPU của dịch vụ xử lý hình ảnh sản phẩm.
14. `wan_network_io_kbs`: Lưu lượng truyền tải qua cầu nối WAN giữa AWS và Azure.

### B. Nhóm Chỉ số Canh gác (Guards / Post-check)
- `error_rate_5xx` và `wan_network_errors`: Luôn bằng 0 trong tập bình thường. Sẽ được dùng trong quy tắc kết hợp (Rule-based post-check) khi có lỗi mạng hoặc sập container.

### C. Nhóm Loại bỏ để Chống Đa cộng tuyến (Multicollinearity)
- `latency_p50`, `latency_p99`: Loại bỏ vì tương quan quá cao (>0.95) với `latency_p95`.
- `registry_cpu_pct`, `registry_ram_pct`: Loại bỏ vì Service Registry hầu như không đổi tải.
