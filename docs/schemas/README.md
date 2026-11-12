# Hệ Thống Đặc Tả Schema & Hợp Đồng Dữ Liệu Giám Sát (Resource Monitoring Schemas & Data Contracts)

> **Tài liệu:** `docs/schemas/README.md`  
> **Phiên bản:** v4.2.0 (OTel SemConv Two-Tier & Evolution Edition)  
> **Chuẩn quy chiếu:** [OpenTelemetry Semantic Conventions Specification](https://github.com/open-telemetry/semantic-conventions) (Schemas `1.21.0` $\rightarrow$ `1.45.0`)  
> **Mục đích:** Cung cấp hướng dẫn tra cứu kiến trúc phân tầng Schema, bản đồ tiến hóa tên gọi OTel, hợp đồng dữ liệu vi dịch vụ và các hồ sơ giám sát thực thể trong hệ thống Multi-Cloud Monitoring.

---

## 1. Kiến Trúc 2 Tầng: Categories (OTel SemConv) vs Profiles (Entity Composition)

Nhằm đảm bảo sự tách biệt rõ ràng giữa **từ điển ngữ nghĩa đo lường cấp thấp** và **hồ sơ quản trị tài nguyên cấp cao**, hệ thống Schema của đồ án được phân bổ thành 2 tầng độc lập:

```text
docs/schemas/
├── README.md                                  # [Trang chủ] Hướng dẫn tra cứu & Bản đồ phân tầng
├── RESOURCE_MONITORING_SCHEMAS.md             # Tài liệu tổng hợp Kiến trúc, RCA Tree & Join Keys
├── telemetry-field-inventory.csv              # Master Telemetry Data Contract (Bảng kiểm kê 52+ trường)
├── experiment-manifest.example.yaml           # Mẫu manifest thực nghiệm Phase 4
│
├── categories/                                # [TẦNG 1] 8 Danh mục Ngữ nghĩa Nguyên tử (Atomic OTel SemConv)
│   ├── README.md                              # Mục lục & Bảng đối chiếu Namespaces
│   ├── cat-01-os-system.md                    # OS Kernel, CPU State, Memory, Paging/Swap, Load Avg
│   ├── cat-02-storage-filesystem.md           # Block Disk I/O, POSIX Filesystem, S3/MinIO Buckets
│   ├── cat-03-network-transport.md            # L3/L4 Network Interfaces, TCP Sockets, WAN Netem, mTLS 1.3
│   ├── cat-04-cloud-context.md                # Cloud Providers (AWS/Azure), Entra ID, VPC/VNet, Subnet, IAM ARN
│   ├── cat-05-k8s-containers.md               # Kubernetes Hierarchy (Cluster->Node->Namespace->Pod->Container)
│   ├── cat-06-jvm-runtime.md                  # JVM Heap/Non-Heap, G1 GC Pause Stalls, Thread Pool
│   ├── cat-07-http-rpc-apm.md                 # HTTP/REST Status, Java RMI :1099, RED Method, Service Graph
│   └── cat-08-database-mysql.md               # MySQL JDBC Client Spans, SQL Statement, Error/Connection Logs
│
└── profiles/                                  # [TẦNG 2] 4 Hồ sơ Giám sát Thực thể (Entity Monitoring Profiles)
    ├── README.md                              # Ma trận lắp ghép (Entity Composition Matrix)
    ├── webapp-monitoring-schema.yaml          # Entity 1: TeaStore Web Microservices
    ├── instance-monitoring-schema.yaml        # Entity 2: Kubernetes Worker Nodes (EKS / AKS NodePools)
    ├── database-monitoring-schema.yaml        # Entity 3: MySQL 8.0 Relational Database (teastore-db)
    └── wan-network-monitoring-schema.yaml     # Entity 4: Inter-Cloud WAN Bridge & Central Hub Ingestion
```

---

## 2. Bản Đồ Tiến Hóa Lược Đồ (OTel Telemetry Schema Evolution v1.21 -> v1.45)

Để giải quyết vấn đề phân mảnh giữa các phiên bản Agent và Exporter, hệ thống áp dụng kỹ thuật **Dual SemConv Fallback** dựa trên bản đồ tiến hóa của OpenTelemetry Specification:

| Telemetry Signal | Tên Cũ (OTel SemConv v1.21.0 - v1.23.0) | Tên Mới Chuẩn Hóa (OTel SemConv v1.24.0 - v1.45.0) | Điểm Thay Đổi Chính & Cơ Chế Fallback Trong Đồ Án |
| :--- | :--- | :--- | :--- |
| **JVM Memory Used** | `process.runtime.jvm.memory.usage` | `jvm.memory.used` | Đổi prefix `process.runtime.jvm` $\rightarrow$ `jvm` (v1.22), đổi `usage` $\rightarrow$ `used` (v1.24). Đồ án dùng `jvm_memory_used_bytes or process_runtime_jvm_memory_usage_bytes`. |
| **JVM GC Duration** | `process.runtime.jvm.gc.duration` | `jvm.gc.duration` | Rút gọn prefix (v1.22). Đồ án dùng `jvm_gc_duration_seconds_sum or process_runtime_jvm_gc_duration_seconds_sum`. |
| **JVM Threads Count** | `process.runtime.jvm.threads.count` | `jvm.thread.count` | Đổi sang danh từ số ít (v1.22). Đồ án dùng `jvm_thread_count or process_runtime_jvm_threads_count`. |
| **Peer Service Name** | `peer.service` | `service.peer.name` | Chuẩn hóa không gian tên `service.peer` (v1.39). OTTL gán đồng thời cả hai thuộc tính để tương thích `servicegraphconnector`. |
| **SQL Statement Text**| `db.statement` | `db.query.text` | Chuẩn hóa cho cả SQL và NoSQL (v1.26). AI RCA kiểm tra fallback `span.get("db.query.text") or span.get("db.statement")`. |
| **HTTP Status Code** | `http.status_code` | `http.response.status_code` | Tách biệt status code phản hồi HTTP (v1.21). Trace filter kiểm tra cả 2 trường. |

---

## 3. Khóa Liên Kết Đa Tầng (Multi-Layer Join Keys)

Để thực hiện tương quan dữ liệu 360° (Logs $\longleftrightarrow$ Metrics $\longleftrightarrow$ Traces) mà không bị va chạm định danh trên Central Hub, toàn bộ hệ thống sử dụng **Khóa phức hợp (Compound Keys)**:

$$\text{Entity Key} = \langle \texttt{k8s.cluster.name}, \ \texttt{k8s.namespace.name}, \ \texttt{service.name}, \ \texttt{k8s.pod.uid} \rangle$$

- **Truy vấn PromQL:** `system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster"}`
- **Truy vấn LogQL:** `{k8s_cluster_name="aws-k3d", service_name="teastore-webui"} |= "error"`
- **Truy vấn TraceQL:** `{ .k8s.cluster.name = "aws-k3d" && .service.name = "teastore-webui" && status = error }`

---

## 4. Hướng Dẫn Sử Dụng Chi Tiết

- Xem tài liệu tổng hợp kiến trúc và cây quyết định RCA tại: [RESOURCE_MONITORING_SCHEMAS.md](RESOURCE_MONITORING_SCHEMAS.md).
- Tra cứu danh mục 8 bộ SemConv nguyên tử tại: [categories/README.md](categories/README.md).
- Tra cứu 4 hồ sơ giám sát thực thể tại: [profiles/README.md](profiles/README.md).
- Tra cứu bảng kiểm kê toàn bộ thuộc tính và số đo tại: [telemetry-field-inventory.csv](telemetry-field-inventory.csv).
