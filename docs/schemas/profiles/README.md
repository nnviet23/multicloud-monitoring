# Entity Monitoring Profiles: 4 Core Infrastructure & Application Profiles

Thư mục này chứa 4 Hồ sơ Giám sát Thực thể (Entity Monitoring Profiles) được chuẩn hóa dưới dạng tệp mã nguồn YAML máy đọc được (Machine-readable YAML).

---

## 1. Nguyên Lý Lắp Ghép Thực Thể (Entity Composition Matrix)

Một thực thể trong môi trường Cloud-Native không tồn tại độc lập mà là sự lắp ghép có chủ đích (composition) từ nhiều Danh mục Ngữ nghĩa Nguyên tử (thuộc `categories/`).

Bảng dưới đây quy định ma trận thành phần cấu tạo nên 4 Thực thể Giám sát chính của Đồ án:

| Entity Profile YAML | Tên Thực Thể | Loại Hình Tài Nguyên | Thành Phần Danh Mục Cấu Thành (Composed Categories) | Consumer Chính |
| :--- | :--- | :--- | :--- | :--- |
| **`webapp-monitoring-schema.yaml`** | **Entity 1: Web Microservices** | Java Web App / REST / RPC | `CAT-04` (Cloud) + `CAT-05` (K8s) + `CAT-06` (JVM) + `CAT-07` (HTTP/RPC APM) | `03. Application & JVM (RED)`, Tempo, Pyrra SLO |
| **`instance-monitoring-schema.yaml`** | **Entity 2: K8s Worker Nodes** | EKS / AKS Node Pools | `CAT-01` (OS) + `CAT-02` (Storage) + `CAT-03` (Network) + `CAT-04` (Cloud) + `CAT-05` (K8s) | `04. Compute & OS Kernel (USE)`, `01. Executive Overview` |
| **`database-monitoring-schema.yaml`** | **Entity 3: MySQL 8.0 Relational DB** | Database Store / Persistence | `CAT-01` (OS Wait) + `CAT-02` (Disk I/O) + `CAT-04` (Cloud) + `CAT-05` (K8s) + `CAT-08` (Database) | `06. Logs, Traces & Database`, `02. Topology` |
| **`wan-network-monitoring-schema.yaml`**| **Entity 4: Inter-Cloud WAN Bridge** | WAN Transport & Ingestion | `CAT-03` (Network/WAN) + `CAT-04` (Cloud) + `CAT-05` (K8s) + `CAT-07` (ServiceGraph) | `05. Network & WAN Transport`, `08. Cost Governance` |

---

## 2. Cấu Trúc Khối Của Một Tệp YAML Profile

Mỗi tệp YAML profile trong thư mục này được cấu trúc theo 4 khối chuẩn mực:
1. **`metadata` & `entity`:** Định danh loại tài nguyên (`kind`), danh mục (`category`), phạm vi triển khai và nhãn định danh.
2. **`attributes`:** Danh sách các thuộc tính ngữ cảnh bắt buộc (`required`), khuyến nghị (`recommended`), kiểu dữ liệu và giá trị mẫu.
3. **`telemetry_signals`:** Danh mục tín hiệu 3 trụ cột (Metrics, Traces, Logs) chi tiết đến từng tên metric TSDB, loại công cụ, và vai trò trong USE/RED.
4. **`operational_rules` & `promql_contracts`:** Ngưỡng cảnh báo định lượng (SLO / Warning / Critical) và biểu thức truy vấn PromQL chuẩn mực phục vụ giám sát và AI suy luận nguyên nhân gốc rễ (RCA).

---

## 3. Danh Mục Các Tệp Hồ Sơ Thực Thể

- [webapp-monitoring-schema.yaml](webapp-monitoring-schema.yaml): Đặc tả vi dịch vụ WebUI, Auth, Image, Recommender, Registry, Persistence.
- [instance-monitoring-schema.yaml](instance-monitoring-schema.yaml): Đặc tả máy chủ Worker Node trên các cụm k3d / EKS / AKS.
- [database-monitoring-schema.yaml](database-monitoring-schema.yaml): Đặc tả cơ sở dữ liệu quan hệ MySQL (`teastore-db`).
- [wan-network-monitoring-schema.yaml](wan-network-monitoring-schema.yaml): Đặc tả đường truyền mạng diện rộng xuyên đám mây và cổng thu nhận dữ liệu trung tâm.

