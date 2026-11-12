# Báo Cáo Nghiên Cứu & Dịch Ngược Chiến Lược Giám Sát Của Datadog (Datadog Integration Core Architecture & Schemas)

> **Mã tài liệu:** `docs/progress/06_Datadog_strategy.md`  
> **Chuyên đề:** Nghiên Cứu Kiến Trúc Schema Giám Sát Tài Nguyên (Resource Monitoring Schemas)  
> **Vị trí nghiên cứu:** Principal Observability Architect & Systems Researcher  
> **Đối tượng phân tích:** Mã nguồn Datadog Integrations Core (`docs/other-reference/DatadogIntergration/integrations-core`) bao gồm các module `datadog_checks_base`, `datadog_checks_dev`, `manifest_validator`, và các gói integration điển hình (`apache`, `clickhouse`, `container`, `cockroachdb`, `cassandra`...)  
> **Hệ quy chiếu đồ án:** Multi-Cloud Monitoring Platform (Descartes TeaStore Hub-Spoke trên 3 cụm k3d `hub-k3d`, `aws-k3d`, `azure-k3d` kết hợp Closed-Loop AIOps)

---

## 1. Tổng Quan Kiến Trúc Integration Core Của Datadog: Cơ Chế Agent-Based vs. Cloud-Based

Datadog là nền tảng quan sát thương mại (Commercial SaaS APM) áp dụng kiến trúc **Software-Centric kết hợp Agent-First**. Để giám sát hàng trăm loại dịch vụ khác nhau, Datadog duy trì kho mã nguồn mở khổng lồ mang tên `integrations-core`.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   KIẾN TRÚC THU THẬP VIỄN TRẮC CỦA DATADOG                             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  [Datadog Agent (DaemonSet / Host Service)]                                            │
│    ├── Core Agent (Go Daemon): Điều phối, thu nạp DogStatsD (:8125), Forwarder        │
│    ├── Collector / Python Runner (Embedded CPython 3.x):                               │
│    │     └── Nạp các module kiểm tra (Checks) từ `integrations-core`                   │
│    │           └── `AgentCheck` Base Class (datadog_checks_base)                       │
│    │                 ├── `self.gauge()`, `self.count()`, `self.rate()`                 │
│    │                 └── `self.service_check()` (OK, WARNING, CRITICAL)               │
│    ├── Autodiscovery Engine: Lắng nghe Docker/K8s events (Container Labels)            │
│    └── Tracing Agent (ddtrace / OTLP receiver) & Log Agent (File / Journald)          │
│                                                                                        │
│  [Cơ chế Thu Thập Song Song (Dual-Mode Collection)]                                    │
│    ├── 1. Agent-Based: Polling cục bộ qua socket, IPC, JMX, HTTP metrics, SQL queries │
│    └── 2. Cloud-Based (Agentless): AWS CloudWatch Metric Streams, Azure Monitor APIs  │
│                                                                                        │
│  [Datadog Intake Backend & SaaS Cloud]                                                 │
│    • Validate đối chiếu Telemetry Field Inventory (`metadata.csv`)                     │
│    • Tự động kích hoạt Out-Of-The-Box (OOTB) Dashboards & Monitor Alerts               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1. Cơ Chế Agent-Based (Kiểm Tra Chủ Động Tại Nguồn)
* Mỗi integration trong `integrations-core` thực chất là một gói Python độc lập kế thừa từ lớp cơ sở `AgentCheck` (trong `datadog_checks_base/datadog_checks/base/checks/base.py`).
* Agent nhúng một trình thông dịch Python runtime (`CPython`). Định kỳ (mặc định mỗi 15-30 giây), Agent gọi hàm `check(instance)` của integration để:
  * Kết nối tới socket cục bộ, endpoint HTTP `/server-status` (như Apache), hoặc thực thi câu lệnh SQL (như ClickHouse, MySQL).
  * Chuyển đổi trạng thái hệ thống thành các hàm đo lường nội bộ: `self.gauge()`, `self.count()`, `self.monotonic_count()`, `self.service_check()`.
* **Cơ chế Autodiscovery:** Khi ứng dụng chạy trong Kubernetes, Agent lắng nghe Docker socket / K8s API. Dựa vào trường `process_signatures` (trong `manifest.json`) hoặc Pod Annotations (`ad.datadoghq.com/<container-name>.checks`), Agent tự động gắn cấu hình kiểm tra mà không cần khởi động lại.

### 1.2. Cơ Chế Cloud-Based (Agentless / Push-based)
* Đối với các dịch vụ PaaS/Serverless (như AWS RDS, S3, Azure SQL, Lambda), Datadog không bắt buộc cài Agent trên node mà cung cấp tích hợp đám mây: thiết lập vai trò IAM / Azure App Registration để Datadog SaaS định kỳ kéo số liệu từ API đám mây, hoặc cấu hình streaming qua AWS Kinesis Firehose / Azure Event Hubs.

---

## 2. Hệ Thống Archetypes (Categories) Ngầm Của Datadog

Phân tích hàng trăm tệp `manifest.json` trong `integrations-core` cho thấy Datadog quản lý kho integration theo một hệ thống phân loại nghiêm ngặt thông qua nhãn phân loại:
`tile.classifier_tags: ["Category::<Tên Nhóm>", "Supported OS::<Hệ Điều Hành>", "Offering::Integration"]`.

### 2.1. Bảng Tổng Hợp 15 Archetypes (Danh Mục Cốt Lõi) Của Datadog
Từ việc quét toàn bộ `classifier_tags` trong repo, hệ thống chia các dịch vụ thành các nhóm tiêu biểu sau:

| Archetype (Category) | Ví Dụ Integration Tiêu Biểu | Nguồn Dữ Liệu Thu Thập Cốt Lõi | Mục Tiêu Giám Sát Cốt Lõi |
| :--- | :--- | :--- | :--- |
| **1. Cloud** | `amazon_eks`, `azure_active_directory`, `aws_neuron` | Cloud APIs, CloudWatch, Azure Metrics | Chi phí, hạn mức tài nguyên, trạng thái hạ tầng đám mây |
| **2. Containers & Kubernetes** | `container`, `containerd`, `cri`, `crio`, `calico` | cgroups v1/v2, Docker/CRI socket, Kubelet `/stats/summary` | CPU Throttling, OOM Kills, Pod Restarts, Memory Working Set |
| **3. Data Stores / Databases** | `clickhouse`, `cockroachdb`, `cassandra`, `couchbase` | Database internal tables (e.g. `system.metrics`), JMX | Query Latency Digest, Connections, Buffer Hit Ratio, Locks |
| **4. OS & System** | `system_core`, `system_swap`, `disk`, `directory`, `battery` | `/proc`, sysfs, Windows WMI/Perfmon | USE Method: CPU Idle/User/System, Memory Page Faults, Disk I/O |
| **5. Web & Proxies** | `apache`, `haproxy`, `nginx`, `caddy`, `envoy` | Stub status, mod_status, access logs | Request Throughput, Worker Slots, Active Connections, HTTP 5xx |
| **6. Message Queues** | `activemq`, `celery`, `confluent_platform` | JMX, HTTP API, Admin Queues | Message Age, Queue Depth, Consumer Lag, Dropped Messages |
| **7. Network** | `cisco_sdwan`, `cisco_asa`, `cilium`, `cloudgen_firewall` | SNMP, NetFlow/sFlow, eBPF | Packet Drops, Bandwidth Saturation, TCP Queue Length, RTT |
| **8. Security & SIEM** | `carbon_black_cloud`, `bitdefender`, `checkpoint_*` | Syslog, Audit logs, Webhooks | Threat detections, Auth failures, CVE scan results |
| **9. AI / ML** | `anthropic`, `anyscale`, `bentoml`, `crewai` | REST API, SDK Instrumentation | Token usage, Generation Latency, Cost estimation, Model Errors |
| **10. Log Collection** | `apache`, `clickhouse`, `btrfs`, `system_core` | Log files, Syslog, Windows Event Log | Log Parsing, Error Extraction, Structured Facets |
| **11. Orchestration & CICD** | `argocd`, `argo_rollouts`, `control_m` | Prometheus `/metrics`, Webhooks | Sync status, Pipeline duration, Deployment failure rate |
| **12. Tracing / APM** | `aspdotnet`, `ddtrace` integrations | In-process Instrumentation (Bytecode injection) | RED Metrics: Request Rate, Errors, Duration (p50/p95/p99) |
| **13. Developer Tools** | `airbyte`, `airflow`, `ambari` | Health APIs, SQLite/Postgres backend | Task execution time, DAG status, Worker availability |
| **14. Configuration & Deploy** | `consul`, `consul_connect`, `cert_manager` | Raft state, TLS expiry dates | Cluster quorum, Certificate expiration time |
| **15. Automation & Notifications** | `automox`, `brevo`, `adyen` | Webhooks, Transaction Logs | Payment success rate, Automation job outcomes |

### 2.2. Nhận Diện Dịch Vụ: Vai Trò Của `manifest.json` (Phiên Bản `2.0.0`)
Một file `manifest.json` chuẩn mực của Datadog (như `apache/manifest.json`) định nghĩa danh tính và mọi thành phần phụ thuộc của integration:
```json
{
  "manifest_version": "2.0.0",
  "app_uuid": "8dfc1942-7820-49c7-93c8-5a31579ee52a",
  "app_id": "apache",
  "tile": {
    "title": "Apache",
    "description": "Track requests per second, bytes served, worker threads, uptime, and more.",
    "classifier_tags": [
      "Category::Log Collection",
      "Category::SIEM",
      "Category::Web",
      "Supported OS::Linux",
      "Supported OS::Windows",
      "Offering::Integration"
    ]
  },
  "assets": {
    "integration": {
      "source_type_name": "Apache",
      "configuration": { "spec": "assets/configuration/spec.yaml" },
      "metrics": {
        "prefix": "apache.",
        "check": "apache.performance.busy_workers",
        "metadata_path": "metadata.csv"
      },
      "service_checks": { "metadata_path": "assets/service_checks.json" },
      "process_signatures": ["httpd", "apache", "apache2"],
      "auto_install": true
    },
    "dashboards": { "apache": "assets/dashboards/apache_dashboard.json" },
    "monitors": {
      "Idle workers number is low": "assets/monitors/apache_low_idle_workers.json",
      "CPU load is running high": "assets/monitors/high_keep_alive_and_cpu.json"
    }
  }
}
```

---

## 3. Cấu Tạo Của Một Integration Schema: Trọng Tâm `metadata.csv` & Cảnh Báo Tĩnh

Khi cài đặt một Integration, Datadog **BẮT BUỘC** gọi tới một Schema tĩnh đã được ghi rõ sẵn. Không một metric nào được phép gửi về backend nếu chưa được khai báo và kiểm duyệt trong Schema này.

```
┌────────────────────────────────────────────────────────────────────────┐
│               CẤU TRÚC BỘ SCHEMA CHUẨN CỦA 1 INTEGRATION               │
├────────────────────────────────────────────────────────────────────────┤
│  1. manifest.json           ➔ Khai báo UUID, danh mục, quy chuẩn nạp   │
│  2. metadata.csv            ➔ Telemetry Field Inventory (Toàn bộ số đo)│
│  3. assets/configuration/   ➔ spec.yaml (Schema xác thực file conf.yaml│
│  4. assets/monitors/        ➔ Predefined Out-Of-The-Box Alerts (JSON)  │
│  5. assets/dashboards/      ➔ Predefined OOTB Dashboards (JSON)        │
│  6. assets/service_checks/  ➔ Danh mục mã trạng thái dịch vụ (JSON)    │
│  7. datadog_checks/<name>/  ➔ Mã nguồn Python thu thập số đo thực tế   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1. Telemetry Field Inventory (`metadata.csv`)
Tệp `metadata.csv` đóng vai trò là "Hợp đồng Dữ liệu" (Data Contract) duy nhất giữa Agent và Backend. Mỗi hàng quy định chặt chẽ 1 metric:

```csv
metric_name,metric_type,interval,unit_name,per_unit_name,description,orientation,integration,short_name,curated_metric,sample_tags
container.cpu.usage,gauge,,nanocore,,The container total CPU Usage,0,container,cpu_total,,
container.cpu.throttled,gauge,,nanosecond,,The total cpu throttled time,0,container,cpu_throttled,,
container.memory.oom_events,gauge,,,,The number of OOM events triggered by the container,0,container,mem_oom_events,,
container.memory.partial_stall,gauge,,nanosecond,,The total time at least one task in the container was stalled waiting for memory,-1,container,mem_partial_stall,,
```

* **Ý nghĩa các trường trong Schema `metadata.csv`:**
  1. `metric_name`: Tên định danh metric duy nhất, luôn bắt đầu bằng prefix của integration (VD: `container.cpu.usage`, `clickhouse.ReplicasMaxInsertsInQueue`).
  2. `metric_type`: Kiểu dữ liệu toán học (`gauge`, `count`, `rate`).
  3. `unit_name` & `per_unit_name`: Đơn vị vật lý chuẩn hóa (VD: `nanocore`, `nanosecond`, `byte`, `thread`, `request/second`). Datadog tự động scale đồ thị (MB/GB/TB) trên dashboard dựa trên metadata này.
  4. `description`: Diễn giải ngữ nghĩa chi tiết của chỉ số.
  5. `orientation`: Hướng đánh giá trạng thái:
     * `0`: Trung tính (Neutral - VD: `uptime`, `bytes_served`).
     * `1`: Càng cao càng tốt (Positive - VD: `cache_hit_ratio`, `idle_workers`).
     * `-1`: Càng cao càng xấu (Negative - VD: `cpu_partial_stall`, `error_rate`, `throttled_time`). Thuộc tính này giúp UI Datadog tự động tô màu đỏ khi số đo tăng vọt.
  6. `sample_tags`: Danh sách nhãn mẫu đi kèm để kiểm thử cardinality.

### 3.2. Cơ Chế Kiểm Thử Nghiêm Ngặt Bằng Tooling CI (`datadog_checks_dev`)
Phân tích tệp `datadog_checks_dev/datadog_checks/dev/tooling/manifest_validator/v2/validator.py`:
* **`MetricToCheckValidator` & `MetricsMetadataValidator`:** Trình kiểm tra mã nguồn tự động rà soát file Python implementation. Nếu mã nguồn Python gọi `self.gauge('apache.unknown_metric', 10)` mà tên này **chưa có trong `metadata.csv`**, quy trình CI/CD sẽ lập tức đánh gãy bản build (`self.fail()`).
* **`SchemaValidator`:** Gọi trực tiếp Datadog API (`/api/beta/apps/manifest/validate`) để xác thực tính toàn vẹn của JSON Schema.

### 3.3. Định Nghĩa Cảnh Báo Tĩnh (Predefined Out-of-the-Box Monitors)
Trong thư mục `assets/monitors/`, Datadog cung cấp sẵn các mẫu cảnh báo tĩnh (JSON). Ví dụ trong `apache/assets/monitors/apache_low_idle_workers.json`:
* Cấu hình sẵn ngưỡng: `avg(last_5m):avg:apache.performance.idle_workers{*} < 10`.
* Định nghĩa message hướng dẫn vận hành (Runbook link, Troubleshooting tips) gắn kèm Markdown và cú pháp `@webhook-notification`.

---

## 4. Đánh Giá Khác Biệt: Triết Lý Software-Centric (Datadog) vs. Semantic-Centric (OpenTelemetry)

| Tiêu Chí So Sánh | Datadog (Software-Centric) | OpenTelemetry (Semantic-Centric) |
| :--- | :--- | :--- |
| **Triết lý thiết kế** | **Theo nhà sản xuất phần mềm:** Đặt tên metric theo tên ứng dụng/phần mềm cụ thể (`apache.*`, `nginx.*`, `mysql.*`, `container.*`). | **Theo ngữ nghĩa công nghệ chung:** Tiêu chuẩn hóa số đo theo hành vi bản chất (`http.server.request.duration`, `db.client.operation.duration`, `system.cpu.time`). |
| **Tính đồng nhất đa nền tảng** | **Rời rạc:** NGINX có metric `nginx.net.conn_rate`, Apache có `apache.net.request_per_s`, HAProxy có `haproxy.frontend.req_rate`. Không thể viết 1 dashboard chung cho toàn bộ Web Server. | **Hợp nhất:** Tất cả các máy chủ web/HTTP đều emit `http.server.request.duration` và `http.server.active_requests`. Một dashboard áp dụng cho NGINX, Apache, Envoy, Go, Java. |
| **Cơ chế gắn nhãn (Tagging Model)** | **Unified Service Tagging (UST):** Cố định bộ ba `env:<val>`, `service:<val>`, `version:<val>`. Các nhãn khác định dạng phẳng `key:value`. | **Hierarchical Resource Model:** Phân cấp rõ rệt giữa Resource Context (`service.name`, `cloud.provider`, `k8s.pod.name`) và Scope/Telemetry Attributes. |
| **Chi phí mở rộng & Vendor Lock-in** | **Rất cao:** Người dùng bị ràng buộc hoàn toàn vào Datadog Agent, Datadog Intake API và định dạng truy vấn Datadog Query Language. | **Bằng 0:** Hoàn toàn mở, độc lập nhà cung cấp (Vendor-Agnostic), tự do xuất sang Thanos, Tempo, ClickHouse, SigNoz. |
| **Khả năng kiểm soát Schema** | **Cứng nhắc tuyệt đối:** Bắt buộc đăng ký trước qua `metadata.csv`. Không linh hoạt cho các metric thử nghiệm nhanh. | **Động và tiến hóa:** Hỗ trợ Schema-on-Read, quản trị tiến hóa schema qua OTel Schema File (`schema-1.42.0.yaml`). |

---

## 5. Bài Học Kinh Nghiệm & Đề Xuất Cải Tiến Cho Đồ Án TeaStore Multi-Cloud

Trong đồ án của chúng ta, nhóm đã quyết định xây dựng nền tảng trên kiến trúc **OpenTelemetry + Prometheus/Thanos + Tempo + Loki** thay vì sử dụng giải pháp thương mại trả phí của Datadog. Phân tích kiến trúc của Datadog giúp chúng ta củng cố và hoàn thiện các giải pháp kỹ thuật đã triển khai:

### 5.1. Thay Thế Datadog Container Monitoring Bằng USE Method + Linux Pressure Stall Information (PSI)
* *Datadog:* Thu thập các metric chuyên sâu `container.cpu.partial_stall`, `container.memory.partial_stall`, `container.cpu.throttled` (đòi hỏi agent cài đặt quyền root/host privileged).
* *Ứng dụng vào đồ án:* 
  * Sử dụng `kubeletstatsreceiver` và `hostmetricsreceiver` chuẩn trong OTel Edge Collector để thu thập các số đo USE Method:
    * **Utilization:** `container.cpu.usage` và `container.memory.working_set`.
    * **Saturation:** `container.cpu.throttled` và Node Load Average `system.cpu.load_average.15m`.
    * **Errors:** Số lượng Container Restarts (`k8s.pod.restart_count`) và OOM-kills.
  * Trực quan hóa toàn diện trên Grafana Dashboard `mc-cost-telemetry.json` và `slo-governance.json` với độ trễ thấp mà không tiêu tốn phí bản quyền.

### 5.2. Thay Thế Datadog Unified Service Tagging Bằng OTel Compound Enrichment
* *Datadog:* Dùng 3 nhãn cố định `env`, `service`, `version`.
* *Ứng dụng vào đồ án:* Do đồ án chạy đa cụm mô phỏng đa đám mây (`aws-k3d` cho compute, `azure-k3d` cho persistence), mô hình 3 nhãn của Datadog không đủ để phân biệt tài nguyên giữa các đám mây. Chúng ta đã nâng cấp lên mô hình **Canonical Multi-Cloud Attributes**:
  * `cloud.provider` (`aws` / `azure`)
  * `cloud.region` (`us-east-1` / `eastus`)
  * `k8s.cluster.name` (`aws-k3d` / `azure-k3d`)
  * `k8s.pod.uid` (Đảm bảo định danh duy nhất tuyệt đối khi scale hoặc restart pod)
  * `deployment.environment.name` (`production`)
  * Toàn bộ các bộ xử lý OTTL trong OTel Gateway chuẩn hóa các nhãn này thành **Compound Anti-Collision Keys** cho Prometheus/Thanos.

### 5.3. Thay Thế Datadog Database Monitoring Bằng OTel 3-Layer Correlation Cho MySQL
* *Datadog:* Cung cấp gói trả phí "Database Monitoring (DBM)" thu thập hàng nghìn internal counters từ `metadata.csv` (như trong tệp `clickhouse` có 3639 dòng metrics).
* *Ứng dụng vào đồ án:* Với cơ sở dữ liệu `teastore-db` (MySQL trên `azure-k3d`), thay vì kéo hàng ngàn metrics gây bùng nổ cardinality, nhóm tập trung vào **3 Tín Hiệu Cốt Lõi**:
  1. **Connection Saturation:** Tỉ lệ `mysql_global_status_threads_connected / mysql_global_variables_max_connections`.
  2. **InnoDB Buffer Pool:** `mysql_global_status_innodb_buffer_pool_reads / mysql_global_status_innodb_buffer_pool_read_requests` để theo dõi Cache Hit Ratio.
  3. **Trace-to-DB Correlation:** Trích xuất span client OTel từ `teastore-persistence` (`db.system=mysql`, `db.name=teastore`, `net.peer.name=teastore-db`). Khi Locust bơm tải gây nghẽn DB, hệ thống AI Anomaly Engine V3 phân tích vết Tempo Trace RCA để tách bạch chính xác thời gian trễ mạng WAN ($T_{\text{WAN}}$) và thời gian thực thi nội tại của MySQL ($T_{\text{DB}}$).

### 5.4. Xây Dựng Telemetry Field Inventory Chuẩn Hóa Cho Đồ Án
* *Bài học từ `metadata.csv` của Datadog:* Sự chặt chẽ của Datadog trong việc quy định rõ `unit_name`, `orientation`, và `metric_type` giúp tránh được tình trạng ô nhiễm số đo (metric pollution).
* *Khuyến nghị:* Nhóm đồ án duy trì một bảng "Telemetry Contract" trong `docs/progress/` quy định rõ các chỉ số SLO và RED metrics của TeaStore, đơn vị đo lường (ms, req/s, ratio) và hướng giá trị bình thường/bất thường nhằm phục vụ việc huấn luyện các mô hình Machine Learning (GRU Autoencoder & Isolation Forest) đạt độ chính xác cao nhất.

