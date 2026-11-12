# Báo Cáo Nghiên Cứu & Dịch Ngược Chiến Lược Giám Sát Của SigNoz (SigNoz Observability Strategy & Schemas)

> **Mã tài liệu:** `docs/progress/05_SigNoz_strategy.md`  
> **Chuyên đề:** Nghiên Cứu Kiến Trúc Schema Giám Sát Tài Nguyên (Resource Monitoring Schemas)  
> **Vị trí nghiên cứu:** Principal Observability Architect & Systems Researcher  
> **Đối tượng phân tích:** Mã nguồn SigNoz Backend & Frontend (`docs/other-reference/SigNozSrc/signoz`) kết hợp hệ thống tài liệu chuyên sâu (`docs/other-reference/SigNozDocs`)  
> **Hệ quy chiếu đồ án:** Multi-Cloud Monitoring Platform (Descartes TeaStore Hub-Spoke trên 3 cụm k3d `hub-k3d`, `aws-k3d`, `azure-k3d` kết hợp Closed-Loop AIOps)

---

## 1. Tổng Quan Kiến Trúc Giám Sát Của SigNoz: Tính Chất Cloud-Native & Native-OTel

Khác biệt với các nền tảng APM thế hệ trước vốn sử dụng các agent độc quyền (proprietary agents) và giao thức đóng mã nguồn, **SigNoz** được thiết kế từ đầu theo triết lý **100% Native-OpenTelemetry (Native-OTel)** và **Cloud-Native First**. 

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        KIẾN TRÚC TOÀN CẢNH SIGNOZ (OTEL-NATIVE)                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  [Applications / Pods / VMs]                                                           │
│         │ (OpenTelemetry SDKs - OTLP gRPC :4317 / HTTP :4318)                          │
│         ▼                                                                              │
│  [OpenTelemetry Collector Agent / Gateway]                                             │
│    • Receivers: otlp, hostmetrics, kubeletstats, filelog, prometheus/mysql             │
│    • Processors: memory_limiter ➔ filter ➔ transform (OTTL) ➔ batch                    │
│    • Exporters: otlp (ClickHouse exporter) / signoz exporter                           │
│         │                                                                              │
│         ▼                                                                              │
│  [SigNoz Query-Service & Ingestion Layer]                                              │
│    • pkg/semconv: Semantic Convention Family Evolution & Backward Compatibility        │
│    • pkg/telemetryschema: Schemas for Traces, Metrics, Logs, AI, Audit, Meter         │
│         │                                                                              │
│         ▼                                                                              │
│  [ClickHouse Columnar Storage Engine]                                                  │
│    • signoz_traces (spans, durationNano, serviceName, tagMap, events)                 │
│    • signoz_metrics (time_series_v2, samples_v2, exponential_histograms)               │
│    • signoz_logs (timestamp, body, severity_text, attributes_string/number)           │
│         │                                                                              │
│         ▼                                                                              │
│  [SigNoz Frontend (React/Vite) & Alertmanager / Ruler Engine]                          │
│    • APM Services Graph ➔ Trace RCA ➔ Metric-to-Trace Correlated Dashboards            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1. Bản Chất Native-OpenTelemetry
1. **Không có Agent thu thập độc quyền:** SigNoz không xây dựng agent riêng. Agent chuẩn của SigNoz chính là bản phân phối **OpenTelemetry Collector Contrib** được đóng gói sẵn các cấu hình thu thập tối ưu.
2. **Giao thức Ingestion đồng nhất:** Mọi tín hiệu viễn trắc (Traces, Metrics, Logs) đều đi vào hệ thống qua giao thức chuẩn công nghiệp **OTLP (OpenTelemetry Protocol)** trên cổng gRPC `:4317` hoặc HTTP `:4318`.
3. **Cơ sở dữ liệu ClickHouse tối ưu cho OTel Data Model:** Dữ liệu OTLP (pdata) được ánh xạ trực tiếp sang các bảng cột phân tán trong ClickHouse mà không cần qua bất kỳ tầng chuyển đổi trung gian độc quyền nào.

---

## 2. Chiến Lược Phân Loại Tài Nguyên & Áp Dụng Schema (Resource Categorization & Schema Invocation)

### 2.1. Phân Loại Tài Nguyên (Categorization Taxonomy)
Dựa trên phân tích mã nguồn frontend (`frontend/src/container/`) và tài liệu kiến trúc (`docs/other-reference/SigNozDocs/SigNoz_Docs_Categorized/`), SigNoz không dùng một file tĩnh duy nhất để phân loại mà tổ chức tài nguyên theo **4 Tầng Miền Giám Sát (Observability Domains)** dựa trên tín hiệu viễn trắc và nhãn ngữ cảnh:

| Nhóm Tài Nguyên (Domain) | Thành phần UI / Codebase đại diện | Nhãn ngữ cảnh cốt lõi (OTel Resource Attributes) | Nguồn thu thập viễn trắc |
| :--- | :--- | :--- | :--- |
| **1. APM & Services** | `ServiceApplication`, `TracesExplorer` | `service.name`, `service.namespace`, `deployment.environment` | OpenTelemetry SDK (Java, Go, Python, Node.js) tự động inject |
| **2. Infrastructure** | `InfraMonitoringHostsV2`, `InfraMonitoringK8sV2` | `host.name`, `os.type`, `k8s.cluster.name`, `k8s.node.name`, `k8s.pod.name` | `hostmetricsreceiver`, `kubeletstatsreceiver` |
| **3. Data Stores & Databases** | `20_Database Monitoring`, `Integrations/` | `db.system` (mysql, postgresql, redis, mongodb), `db.name`, `net.peer.name` | `filelogreceiver` (slow logs) + Prometheus Exporters / OTel DB Receivers + Span DB Calls |
| **4. Cloud & Integrations** | `CloudIntegration`, `OneClickIntegrations` | `cloud.provider` (aws, azure, gcp), `cloud.region`, `cloud.account.id` | AWS CloudWatch Metric Streams, Azure Monitor Event Hub, GCP Cloud Monitoring |
| **5. AI / LLM Observability** | `LLMObservability`, `aitelemetryschema` | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.prompt_tokens` | OpenLLMetry / OTel GenAI Semantic Conventions |

### 2.2. SigNoz Có Cần Gọi Tới Một "Schema Được Ghi Rõ Sẵn" Hay Không?
* **Câu trả lời:** **KHÔNG theo kiểu monolithic tĩnh của Datadog (như file `.csv` danh mục cứng), mà dùng "Dynamic Schema" gắn liền với chuẩn OpenTelemetry Data Model.**
* **Cơ chế hoạt động:**
  1. **Schema nạp động (Dynamic Ingestion Schema):** SigNoz chấp nhận mọi nhãn tùy biến gửi kèm trong `Resource` hoặc `Attributes` của Span/Metric/Log. Bảng ClickHouse (`signoz_traces`, `signoz_logs`) lưu trữ các nhãn động trong các cột `Map(LowCardinality(String), String)` hoặc cấu trúc mảng khóa-giá trị song song (`attributes_string_key`, `attributes_string_value`) cho phép mở rộng không giới hạn mà không cần định nghĩa trước schema cột DB (Schema-on-read kết hợp Semi-structured storage).
  2. **Schema định tuyến hạ tầng qua OTel Collector Pipeline:** Thay vì cài đặt plugin riêng, mỗi loại tài nguyên được cấu hình một pipeline YAML độc lập trong OTel Collector (Receiver $\rightarrow$ Processor $\rightarrow$ Exporter). Ví dụ: giám sát MySQL chỉ cần khai báo receiver `mysql` hoặc `filelog/mysql_error` kết hợp parse regex/json mà không cần biên dịch lại agent.
  3. **Mẫu Dashboard & Alert (OOTB Templates):** SigNoz lưu trữ các mẫu dashboard dưới định dạng JSON (dựa trên OTel metric names chuẩn như `system.cpu.time`, `mysql_global_status_threads_connected`). Khi người dùng chọn "Install Integration", hệ thống chỉ nạp template JSON này vào giao diện và hiển thị hướng dẫn cấu hình Collector.

---

## 3. Mức Độ Tuân Thủ OpenTelemetry Semantic Conventions (SemConv Compliance)

SigNoz tuân thủ OpenTelemetry Semantic Conventions ở **mức độ tuyệt đối (100% Native Compliance)**. Phân tích mã nguồn backend tại `pkg/semconv/` cho thấy SigNoz thậm chí đã phát triển một hệ thống quản trị tiến hóa SemConv phức tạp nhất hiện nay:

### 3.1. Dẫn Chứng Mã Nguồn: Cơ Chế SemConv Evolution Engine (`pkg/semconv/`)
Trong tệp `pkg/semconv/semconv.go`, SigNoz định nghĩa cấu trúc `Family` và `Member` để theo dõi toàn bộ lịch sử đổi tên của các thuộc tính Semantic Conventions từ OpenTelemetry Specification:

```go
// Trích xuất từ pkg/semconv/semconv.go
type Family struct {
    current  string
    kind     Kind
    members  []Member
    contexts []telemetrytypes.FieldContext
    signals  []telemetrytypes.Signal
}

// Members trả về tên chuẩn hiện tại trước, tiếp theo là các tên cũ lịch sử (historical spellings)
// theo thứ tự fallback nhằm đảm bảo truy vấn không bị gián đoạn khi OTel đổi chuẩn.
func Members(kind Kind, selector telemetrytypes.FieldKeySelector) []string { ... }
```

### 3.2. Quản Trị Chuyển Đổi Thuộc Tính Qua `overlay.yaml`
Trong tệp `scripts/semconv/overlay.yaml` (dựa trên OTel schema `1.42.0`):
```yaml
# Trích xuất từ scripts/semconv/overlay.yaml
default_enabled: false
families:
  deployment.environment.name:
    enabled: true
    signals: [traces, logs, metrics]
    contexts: [resource, attribute]
  db.system.name:
    enabled: false # Tạm dừng chờ hoàn thiện mapping giá trị domain (mssql -> microsoft.sql_server)
  k8s.pod.cpu.usage:
    enabled: true
    kind: metric
    old: [k8s.pod.cpu.utilization]
  k8s.node.cpu.usage:
    enabled: true
    kind: metric
    old: [k8s.node.cpu.utilization]
  container.cpu.usage:
    enabled: true
    kind: metric
    old: [container.cpu.utilization]
```

* **Ý nghĩa kiến trúc:** Khi cộng đồng OpenTelemetry đổi tên chuẩn từ `k8s.pod.cpu.utilization` sang `k8s.pod.cpu.usage`, hoặc từ `deployment.environment` sang `deployment.environment.name`, SigNoz không bắt người dùng phải viết lại dashboard hay mất dữ liệu cũ. Tầng `semconv` tự động mở rộng truy vấn SQL trên ClickHouse để tìm kiếm cả tên mới lẫn danh sách tên cũ (`old`).

### 3.3. Phương Pháp Luận Thu Thập Telemetry
1. **Đối với Compute / OS (Host & Kubernetes Monitoring):**
   * Tuân thủ triệt để **USE Method (Utilization, Saturation, Errors)** của Brendan Gregg:
     * **Utilization:** `system.cpu.time` (tính toán tỉ lệ non-idle), `system.memory.usage`.
     * **Saturation:** `system.cpu.load_average.15m`, Disk IOWait (`system.cpu.time` state `wait`), Kubernetes Throttling.
     * **Errors / Headroom:** File system disk full (`system.filesystem.usage`), Memory swap exhaustion.
   * Toàn bộ nhãn sử dụng chuẩn: `host.name`, `os.type`, `k8s.cluster.name`, `k8s.pod.name`.
2. **Đối với Database (MySQL, PostgreSQL, ClickHouse):**
   * Áp dụng **Mô hình Viễn Trắc 3 Lớp (Three-Layer Telemetry)**:
     * *Lớp 1 (Metrics):* Bắt buộc thu thập Connection Saturation (`threads_connected`, `max_connections`), Buffer Pool Hit Ratio, Row Lock Waits, Replication Lag.
     * *Lớp 2 (Logs):* Phân tích Slow Query Logs qua regex/json trong OTel `filelogreceiver`, trích xuất `query_time`, `rows_examined`, `rows_sent`.
     * *Lớp 3 (Traces):* Trích xuất các span tương tác DB từ ứng dụng chứa các thuộc tính chuẩn: `db.system=mysql`, `db.name`, `db.statement`, `db.operation`, `net.peer.name`. Điều này cho phép SigNoz liên kết trực tiếp từ một điểm nghẽn HTTP 500/chậm trên Web App tới chính xác câu SQL chạy chậm trong cơ sở dữ liệu.

---

## 4. Bài Học Rút Ra & Áp Dụng Cho Đồ Án TeaStore Multi-Cloud

Hệ thống giám sát của đồ án chúng ta được xây dựng cho mô hình **Hub-Spoke 3 cụm k3d** (`hub-k3d`, `aws-k3d`, `azure-k3d`) chạy benchmark Descartes TeaStore. Việc dịch ngược kiến trúc SigNoz đem lại 4 giá trị thiết kế cốt lõi:

### 4.1. Thay Thế ClickHouse Bằng Bộ Đôi Thanos + Tempo (Tương Đương Kiến Trúc SigNoz)
* *SigNoz:* Dùng ClickHouse cho cả 3 tín hiệu (Traces, Metrics, Logs) nhằm đơn giản hóa lưu trữ.
* *Đồ án của chúng ta:* Áp dụng **Thanos Receive** cho Metrics, **Grafana Tempo** cho Traces và **Grafana Loki** cho Logs, cùng trỏ về **MinIO Object Storage S3**. Kiến trúc này đảm bảo tính tương thích nguyên bản với hệ sinh thái Kubernetes/PromQL, cho phép Pyrra tính toán SLO-as-Code trực tiếp và AI Anomaly Detection Engine V3 truy vấn PromQL linh hoạt.

### 4.2. Topo Service Graph Đa Đám Mây Qua `servicegraphconnector`
* SigNoz xây dựng Service Map dựa trên việc phân tích mối quan hệ giữa `client` span và `server` span trong distributed traces.
* *Ứng dụng vào đồ án:* Tại cụm trung tâm `hub-k3d`, chúng ta đã triển khai bộ kết nối `servicegraphconnector` trong OTel Hub Gateway. Khi các span đi từ `teastore-web` (trên `aws-k3d`) gọi sang `teastore-persistence` / MySQL (trên `azure-k3d`) qua mạng WAN mô phỏng mTLS, connector tự động tạo ra metric topology `traces_service_graph_request_total` nạp thẳng vào Thanos. Nhờ đó, Grafana có thể vẽ sơ đồ kiến trúc động thời gian thực mà không tốn chi phí truyền dữ liệu đồ thị riêng.

### 4.3. Quản Trị Chuẩn Semantic Conventions & Compound Keys Chống Va Chạm
* *Học hỏi từ `pkg/semconv` của SigNoz:* Trong môi trường Multi-Cloud, các tên tài nguyên có thể trùng nhau giữa các cloud (ví dụ: cả AWS và Azure đều có pod tên `teastore-web-xxx` hoặc namespace `default`).
* *Thực thi trong đồ án:* Toàn bộ telemetry đi qua OTel Edge Collector đều được enrich nhãn chuẩn:
  * `deployment.environment.name = "production"`
  * `cloud.provider = "aws"` / `"azure"`
  * `k8s.cluster.name = "aws-k3d"` / `"azure-k3d"`
  * `k8s.pod.uid`
* Toàn bộ câu truy vấn PromQL, LogQL, TraceQL và mô hình Machine Learning (GRU + TCN + Isolation Forest) đều sử dụng **Compound Keys** (ví dụ: `{k8s_cluster_name="aws-k3d", pod=~"teastore-.*"}`) để triệt tiêu hiện tượng va chạm dữ liệu giữa các đám mây.

### 4.4. Chiến Lược Lọc Tại Biên & Lấy Mẫu Phân Tầng (Edge-Filtered Ingestion)
* *SigNoz Ingestion Optimization:* Lọc bỏ span rác ngay tại Collector trước khi đẩy vào ClickHouse.
* *Áp dụng vào đồ án (Phương án A):*
  * Tại Spoke Edge Collector (`aws-k3d`, `azure-k3d`): Triển khai `filter/drop_noise` để loại bỏ các health check probes của Kubernetes (`/isready`, `/finished`) trước khi gói dữ liệu mã hóa mTLS gửi qua mạng WAN, kết hợp Head-based sampling 20% cho các request bình thường.
  * Tại Hub Gateway Collector (`hub-k3d`): Triển khai `tail_sampling` bảo tồn 100% các traces có HTTP status `>= 500` hoặc latency $> 1500\text{ms}$ để cung cấp đầy đủ dữ liệu nguyên vẹn cho động cơ AI Root Cause Analysis ($T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$).
