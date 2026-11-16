# Entity Monitoring Profiles: 4 Core Infrastructure & Application Profiles

Thư mục này chứa 4 Hồ sơ Giám sát Thực thể (Entity Monitoring Profiles) được chuẩn hóa dưới dạng tệp mã nguồn YAML máy đọc được (Machine-readable YAML) theo chuẩn OpenTelemetry Semantic Conventions v1.45.0.

---

## 1. Nguyên Lý Lắp Ghép Thực Thể (Entity Composition Matrix)

Một thực thể trong môi trường Cloud-Native không tồn tại độc lập mà là sự lắp ghép có chủ đích (composition) từ nhiều Danh mục Ngữ nghĩa Nguyên tử (thuộc thư mục `docs/schemas/categories/`).

Bảng dưới đây quy định ma trận thành phần cấu tạo nên 4 Thực thể Giám sát chính của Đồ án:

| Entity Profile YAML | Tên Thực Thể | Loại Hình Tài Nguyên | Thành Phần Danh Mục Cấu Thành (Composed Categories) | Consumer Chính |
| :--- | :--- | :--- | :--- | :--- |
| **`webapp-monitoring-schema.yaml`** | **Entity 1: Web Microservices** | Java Web App / REST / RPC | `CAT-07` (HTTP/RPC APM) + `CAT-06` (JVM) + `CAT-05` (K8s) + `CAT-08` (DB Client) + `CAT-03` (Network) + `CAT-04` (Cloud) | `03. Application & JVM (RED)`, Tempo, Pyrra SLO |
| **`instance-monitoring-schema.yaml`** | **Entity 2: K8s Worker Nodes** | EKS / AKS Node Pools | `CAT-01` (OS Kernel) + `CAT-02` (Storage) + `CAT-03` (Network) + `CAT-04` (Cloud) + `CAT-05` (K8s) | `04. Compute & OS Kernel (USE)`, `01. Executive Overview` |
| **`database-monitoring-schema.yaml`** | **Entity 3: MySQL 8.0 Relational DB** | Database Store / Persistence | `CAT-08` (Database) + `CAT-02` (Storage) + `CAT-01` (OS Wait) + `CAT-03` (Network) + `CAT-05` (K8s) + `CAT-04` (Cloud) | `06. Logs, Traces & Database`, `02. Topology` |
| **`wan-network-monitoring-schema.yaml`**| **Entity 4: Inter-Cloud WAN Bridge** | WAN Transport & Ingestion | `CAT-03` (Network/WAN) + `CAT-02` (Storage/Buffer) + `CAT-04` (Cloud) + `CAT-01` (OS Kernel) + `CAT-05` (K8s) | `05. Network & WAN Transport`, `08. Cost Governance` |

---

## 2. Cấu Trúc Khối Của Một Tệp YAML Profile

Mỗi tệp YAML profile trong thư mục này được cấu trúc theo 10 khối chuẩn mực:

1. **`schema_version`:** Phiên bản ngữ nghĩa của hồ sơ schema (ví dụ: `"1.45.0"`).
2. **`resource_type`:** Mã định danh duy nhất của kiểu tài nguyên giám sát (`webapp`, `instance`, `database`, `wan`).
3. **`target_system`:** Hệ thống hoặc đối tượng mục tiêu được giám sát (ví dụ: `TeaStore Java Microservices (EKS / AKS)`, `Linux Host / K8s Worker Node`, `MySQL 8.0 Persistence Service`, `Multi-Cloud Virtual WAN Overlay`).
4. **`methodology`:** Phương pháp luận giám sát nền tảng được áp dụng (`RED` - Rate/Errors/Duration hoặc `USE` - Utilization/Saturation/Errors).
5. **`included_categories`:** Danh sách 8 Danh mục Ngữ nghĩa Nguyên tử cấu thành thực thể (`CAT-01` đến `CAT-08`).
6. **`identity_attributes`:** Danh sách các thuộc tính ngữ cảnh định danh bắt buộc (`canonical_name`, `prometheus_label`, `cloud_provider`, `k8s.cluster.name`, `k8s.namespace.name`, `service.name`).
7. **`dependencies`:** Mô hình phụ thuộc của thực thể (hạ tầng máy chủ, runtime thực thi, cơ sở dữ liệu hạ nguồn, mạng kết nối).
8. **`telemetry_signals`:** Danh mục tín hiệu 3 trụ cột (Metrics, Traces, Logs) chi tiết đến từng tên metric TSDB, kiểu đo lường OTel, nhãn bắt buộc, và câu truy vấn mẫu.
9. **`slo_targets`:** Các mục tiêu chỉ tiêu mức dịch vụ (Service Level Objectives) định lượng (Availability, P99 Latency, Error Budget).
10. **`correlation_keys`:** Khóa tương quan (Compound Keys) liên kết đa tín hiệu giữa Metrics, Traces, và Logs (như `k8s_cluster_name`, `service_name`, `trace_id`).

### Ghi Chú Về Trường `orientation` (Hướng Đánh Giá Bất Thường - Anomaly Polarity)

Trong phần khai báo `telemetry_signals.metrics` của các tệp Profile YAML, thuộc tính `orientation` mang giá trị số nguyên xác định chiều hướng tác động của tín hiệu khi xảy ra biến động:

- **`orientation: -1` (Lower is better / Bad when increasing):**
  - Tín hiệu thể hiện sự suy thoái, nghẽn tải hoặc lỗi. Khi chỉ số này tăng vọt là dấu hiệu bất thường tiêu cực của hệ thống.
  - *Ví dụ:* Latency / Duration ($T_{\text{response}}$), Failed Requests / Error Rate, CPU Throttling, Memory Saturation, Paging Faults, Packet Drop.
- **`orientation: 0` (Neutral / Workload Volume):**
  - Tín hiệu đo lường khối lượng công việc, lưu lượng hoặc tải đầu vào. Giá trị tăng hay giảm phụ thuộc vào hành vi người dùng, không mặc định là lỗi.
  - *Ví dụ:* Request Rate (QPS), Network Throughput (Bytes In/Out), Active Sockets, Total GC Runs.
- **`orientation: +1` (Higher is better / Good when high):**
  - Tín hiệu phản ánh độ sẵn sàng, tỷ lệ thành công hoặc năng lực tài nguyên còn dư. Giá trị càng cao càng an toàn; sụt giảm đột ngột là dấu hiệu nguy hiểm.
  - *Ví dụ:* Availability / Success Rate (%), Free Memory / Inode Headroom, Free Buffer Queue Capacity.

---

## 3. Danh Mục Các Tệp Hồ Sơ Thực Thể

- [webapp-monitoring-schema.yaml](webapp-monitoring-schema.yaml): Đặc tả vi dịch vụ WebUI, Auth, Image, Recommender, Registry, Persistence.
- [instance-monitoring-schema.yaml](instance-monitoring-schema.yaml): Đặc tả máy chủ Worker Node trên các cụm k3d / EKS / AKS.
- [database-monitoring-schema.yaml](database-monitoring-schema.yaml): Đặc tả cơ sở dữ liệu quan hệ MySQL (`teastore-db`).
- [wan-network-monitoring-schema.yaml](wan-network-monitoring-schema.yaml): Đặc tả đường truyền mạng diện rộng xuyên đám mây và cổng thu nhận dữ liệu trung tâm.
