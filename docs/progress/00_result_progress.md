# Báo Cáo Tiến Độ Triển Khai & Tổng Quan Xử Lý Sự Cố (Implementation Progress & Incident Overview)

> **Tài liệu:** `docs/progress/00_result_progress.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Cập nhật lần cuối:** 2026-11-04  
> **Quy chuẩn:** Báo cáo tiến độ các Phase, tổng quan các lỗi phát sinh, trạng thái giải quyết và kết quả kiểm thử thực tế.

---

## 1. Tổng Quan Tiến Độ Các Phase Triển Khai (Phase Status Summary)

| Phase | Mô tả mục tiêu (Phase Objective) | Trạng thái (Status) | Tỷ lệ hoàn thành | Kiểm thử nghiệm thu (Verification) |
|---|---|---|---|---|
| **Phase 0** | Baseline & Kiến trúc hệ thống, Tech Stack Versioning, SRP Manifests | **Hoàn thành** | 100% | `docs/architecture/`, `infra/README.md`, `.agent/rules/` |
| **Phase 1** | Hạ tầng 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`), mạng WAN mô phỏng `netem`, PKI mTLS 1.3 | **Hoàn thành** | 100% | 3 cụm Kubernetes hoạt động, RTT WAN 10ms ±2ms, chứng chỉ mTLS hợp lệ |
| **Phase 2** | Triển khai TeaStore Compute (`aws-k3d`), Data (`azure-k3d`), OTel Java Agent v2.10, Edge OTel Collector | **Hoàn thành** | 100% | 7 service TeaStore `Running`, WebUI truy cập được, mTLS streaming OTLP sang Hub |
| **Phase 3** | Hub Observability: MinIO Object Storage, Prometheus + Thanos, Loki, Tempo, Grafana, Pyrra, Robusta | **Hoàn thành** | 100% | MinIO 4 buckets, Thanos Query PromQL, Tempo Traces, Loki Logs, Grafana Topology & RED Dashboards |
| **Phase 3.5** | Full-Stack Infrastructure Observability (OS, Kernel, Storage, Network USE) & Nâng cấp toàn diện Bộ 7 Grafana Dashboards | **Hoàn thành** | 100% | OTel Collector 7 Hostmetrics scrapers, 7 Grafana SRE Dashboards (USE Method, 4 Golden Signals, Dynamic Topo, Log Anomaly) |
| **Phase 3.6** | Unified Resource Monitoring Schemas (Web App & Compute Instance), JVM Runtime Completeness & Cross-Layer RCA Tree | **Hoàn thành** | 100% | `RESOURCE_MONITORING_SCHEMAS.md`, `webapp-monitoring-schema.yaml`, `instance-monitoring-schema.yaml`, JVM Heap/Threads Panel 6 trên `red-metrics.json` |
| **Phase 4** | Workload Testing (Locust), AI/ML Sampling & Anomaly Detection, SLO Validation | *Chờ thực hiện* | 0% | Lên lịch sau khi nghiệm thu Phase 3.6 |

---

## 2. Bảng Tổng Quan Các Lỗi Phát Sinh & Kết Quả Xử Lý (Incident Overview & Resolution)

Dưới đây là danh mục toàn bộ sự cố kỹ thuật ghi nhận trong quá trình triển khai thực tế từ Phase 1 đến Phase 3 và trạng thái khắc phục:

| Mã sự cố (ID) | Phase | Thành phần bị ảnh hưởng | Tóm tắt sự cố (Incident Summary) | Mức độ | Trạng thái (Status) | Kết quả giải quyết (Resolution Outcome) |
|---|---|---|---|---|---|---|
| **INC-P1-01** | Phase 1 | Cluster Management | Context `kubectl` không nhận diện được cụm k3d từ Windows host | Medium | **Đã giải quyết** | Đồng bộ hóa `kubeconfig` từ WSL2 sang `%USERPROFILE%\.kube\config`, điều khiển liền mạch cả 3 cụm. |
| **INC-P2-01** | Phase 2 | TeaStore Services | Pod TeaStore bị `OOMKilled` (Exit 137) liên tục do `JAVA_TOOL_OPTIONS` | High | **Đã giải quyết** | Chuyển khai báo Java Agent từ `JAVA_TOOL_OPTIONS` sang `CATALINA_OPTS`, tránh nạp agent vào script tiện ích Tomcat. |
| **INC-P2-02** | Phase 2 | TeaStore Pods | Liveness/Readiness probes trả về HTTP 404 gây restart pod liên tục | High | **Đã giải quyết** | Chuẩn hóa URI probe theo từng service (`/ready/isready`, `/image/finished`, `/train/isready`, `/categories`, `/status`). |
| **INC-P3-01** | Phase 3 | MinIO Storage | Image pull access denied cho image MinIO release cũ trên Docker Hub | High | **Đã giải quyết** | Kéo official hardened MinIO image, ghim tag cục bộ, nạp trực tiếp vào containerd của k3d và cấu hình initContainer tự tạo buckets. |
| **INC-P3-02** | Phase 3 | Loki Logging | Exporter OTLP HTTP sang Loki bị lỗi HTTP 404 Not Found | Medium | **Đã giải quyết** | Chuyển sang exporter `loki` native của OTel Collector Contrib đẩy trực tiếp vào `/loki/api/v1/push`. |
| **INC-P3-03** | Phase 3 | Pyrra SLO | Probe `/api/v1/healthz` của Pyrra trả về HTTP 404 | Low | **Đã giải quyết** | Cập nhật readiness probe trỏ về root path `/`. |
| **INC-P3-04** | Phase 3 | Robusta Alerting | Robusta Runner crash do thiếu biến môi trường, quyền RBAC và cấu hình repo | Medium | **Đã giải quyết** | Thiết lập `PLAYBOOKS_CONFIG_FILE_PATH`, gán quyền RBAC `cluster-admin` và gắn secret Telegram sink. |
| **INC-P3-05** | Phase 3 | Thanos / MinIO | Bucket `thanos-metrics` trong MinIO rỗng do lỗi `hard link: operation not permitted` | Critical | **Đã giải quyết** | Thiết lập `securityContext` đồng nhất UID `65534` (`nobody`) cho Prometheus và Thanos Sidecar. Đã tải lên thành công 24 block nén TSDB vào MinIO. |
| **INC-P3-06** | Phase 3 | Metrics Aggregation | Query `system_memory_usage_bytes` chỉ thấy nhãn `cluster="hub-k3d"`, mất Spoke | High | **Đã giải quyết** | Bật `resource_to_telemetry_conversion: enabled: true`, map `cluster` qua OTTL và bật `honor_labels: true` trong Prometheus scrape config. Thấy đầy đủ `aws-k3d` và `azure-k3d`. |
| **INC-P3-07** | Phase 3 | Grafana Visualization | Panel Topology báo lỗi `Error: id field is required for nodes data frame` | High | **Đã giải quyết** | Tái cấu trúc truy vấn PromQL dạng bảng tức thời (`instant: true`, `format: "table"`) sử dụng `label_join` và `label_replace` sinh đủ `id`, `source`, `target`. Sơ đồ Topology hiển thị hoàn chỉnh. |
| **INC-P3-08** | Phase 3 | Loki / MySQL Logs | MySQL log cảnh báo `Aborted connection` và `telemetry.hub.received_time: null` | Medium | **Đã giải quyết** | Xác nhận log MySQL là cảnh báo bình thường của TCP probe L4 từ Kubelet. Sửa OTTL sang `UnixMilli(Now())` loại bỏ hoàn toàn giá trị `null`. |
| **INC-P3-09** | Phase 3 | Metrics Aggregation | Phân mảnh nhãn cụm giữa `cluster` và `k8s_cluster_name` khi query | Medium | **Đã giải quyết** | Chuẩn hóa toàn bộ hệ thống sử dụng duy nhất nhãn chuẩn `k8s_cluster_name` và `cloud_provider` cho cả 3 cụm. |
| **INC-P3-10** | Phase 3 | Object Storage | Bucket `raw-telemetry` trong MinIO rỗng do thiếu pipeline dump thô | Medium | **Đã giải quyết** | Tích hợp exporter `awss3` vào OTel Hub Collector, lưu tự động dữ liệu JSON thô theo cây thời gian `year=2026/month=11/...`. |
| **INC-P3-11** | Phase 3 | Visualization | Thiếu hệ thống Dashboard toàn diện theo chuẩn SRE (mới có 2 dashboard) | Medium | **Đã giải quyết** | Nâng cấp Rich Node Graph (QPS, P95, Cloud, IP) và triển khai trọn vẹn bộ 7 Dashboards SRE vào Grafana. |
| **INC-P3-12** | Phase 3 | Telemetry Normalization | Thiếu định danh Region (`cloud.region`) và xuất hiện node `unknown` trong Service Graph | Medium | **Đã giải quyết** | Thiết lập `cloud.region` (`us-east-1` cho AWS, `southasia` cho Azure) và áp dụng OTTL Peer Service Enrichment xóa bỏ triệt để `unknown_service`. |
| **INC-P3-13** | Phase 3 | Cloud Dependencies | Thiếu chiều sâu phụ thuộc đám mây của tài nguyên (IAM, ARN ID, Resource ID, VPC, Subnet) | High | **Đã giải quyết** | Xây dựng mô hình 6 Trục Phụ Thuộc Đám Mây Sâu trong `docs/progress/03_resource_monitor.md` và inject đầy đủ qua bộ xử lý OTTL Hub Collector. |
| **INC-P3-14** | Phase 3 | Grafana Visualization | Panel Topology chỉ hiển thị mainstat/title, thiếu thuộc tính phụ thuộc đám mây sâu và subnet | High | **Đã giải quyết** | Nâng cấp toàn diện `system-topology.json` (v3): Interactive Node Graph với đầy đủ subtitle, mainStat, secondaryStat, và 10+ trường `detail__*` (IAM Role, ARN, Subnet, VPC, SG, KMS); bổ sung Bảng Ma trận kết nối mạng L3/L4 và Bảng Kiểm kê 360° Phụ thuộc tài nguyên. |
| **INC-P3-15** | Phase 3.5 | Observability & Dashboards | Thiếu hụt chỉ số hạ tầng sâu (OS/Kernel/Storage/USE) và bộ Dashboards chưa chuẩn 4 Golden Signals / USE Method | High | **Đã giải quyết** | Kích hoạt trọn bộ 7 OTel hostmetrics scrapers (cpu, load, memory, paging, disk, filesystem, network) trên cả Edge và Hub; nâng cấp toàn diện bộ 7 Dashboards SRE (k8s-infrastructure 10 panels/4 rows, wan-telemetry 8 panels, red-metrics 4 Golden Signals, logs-traces-deepdive anomaly & persistence stream, topology dynamic metrics & node health table, executive fleet matrix). |
| **INC-P3-16** | Phase 3.6 | Resource Schemas & JVM Completeness | Thiếu chuẩn đặc tả giám sát thống nhất cho từng loại tài nguyên (Web App vs Compute Instance) và thiếu JVM Runtime Saturation trên RED Dashboard | Medium | **Đã giải quyết** | Ban hành tài liệu đặc tả `RESOURCE_MONITORING_SCHEMAS.md`, khởi tạo 2 tệp YAML Schemas chuẩn máy đọc được (`webapp-monitoring-schema.yaml`, `instance-monitoring-schema.yaml`), và bổ sung Panel 6 (JVM Memory Heap & Thread Count) vào `red-metrics.json`. |

---

## 3. Trạng Thái Vận Hành Thực Tế Hiện Tại (Live Verification Status)

Toàn bộ các thành phần hạ tầng và giám sát trên cả 3 cụm Kubernetes hiện đang ở trạng thái **100% Khỏe mạnh (Healthy)**:

```
[hub-k3d] (Central Aggregator)
  ├── minio-0                    1/1 Running   (API: :9000, Console: :9001 - 4 buckets initialized)
  ├── otel-collector-hub         1/1 Running   (OTLP mTLS :4317/:4318, Prom exporter :8889)
  ├── prometheus-0               2/2 Running   (Prometheus Scraper + Thanos Sidecar)
  ├── thanos-query               1/1 Running   (PromQL Federated Engine :9090)
  ├── tempo-0                    1/1 Running   (Distributed Tracing TSDB :3200, S3: tempo-traces)
  ├── loki-0                     1/1 Running   (Chunk-based Log TSDB :3100, S3: loki-data)
  ├── grafana                    1/1 Running   (Web UI :3000, Dashboards Topology & RED Metrics)
  ├── pyrra                      1/1 Running   (SLO Multi-Burn-Rate Controller :9099)
  └── robusta-runner             1/1 Running   (Automated K8s RCA & Alert Forwarder)

[aws-k3d] (Spoke 1 - Compute)
  ├── otel-collector-spoke       1/1 Running   (Hostmetrics, Filelog, 20% Sampling, mTLS to Hub)
  ├── teastore-registry          1/1 Running   (RMI Registry :1099, NodePort :31112)
  ├── teastore-webui             1/1 Running   (Tomcat WebUI :8080)
  ├── teastore-auth              1/1 Running   (Authentication service)
  ├── teastore-image             1/1 Running   (Image service)
  └── teastore-recommender       1/1 Running   (Recommender service)

[azure-k3d] (Spoke 2 - Persistence)
  ├── otel-collector-spoke       1/1 Running   (Hostmetrics, Filelog, 20% Sampling, mTLS to Hub)
  ├── teastore-persistence       1/1 Running   (Database abstraction layer, NodePort :31111)
  └── teastore-db                1/1 Running   (MySQL 8.0 Relational DB :3306)
```

### Các bằng chứng nghiệm thu đã xác thực:
1. **MinIO Object Storage**: Lệnh `mc ls local/thanos-metrics` xác nhận 24 block TSDB nén của Thanos đã được đẩy lên lưu trữ an toàn.
2. **Prometheus / Thanos Multi-Cluster Metrics**: Query PromQL `count by (k8s_cluster_name) (system_memory_usage_bytes)` trả về đầy đủ series độc lập cho `aws-k3d` và `azure-k3d`, đồng thời các target nội bộ Hub nhận diện chính xác `hub-k3d`.
3. **Grafana Topology Dashboard**: Panel `Cross-Cloud Multi-Cluster Service Graph Topology` hiển thị trực quan các mối quan hệ `user -> teastore-webui -> teastore-registry`, `teastore-persistence -> teadb` mà không gặp bất kỳ lỗi dữ liệu nào.
4. **Loki Logs Normalization**: Log dòng log MySQL và WebUI được chuẩn hóa với thuộc tính định danh cụm (`cloud.provider`, `k8s.cluster.name`) và tem thời gian nhận tại Hub `telemetry.hub.received_time` hợp lệ dạng số nguyên Epoch milliseconds.
5. **Raw Telemetry Data Lake**: Lệnh `mc ls -r local/raw-telemetry` xác nhận hơn 260 tệp dữ liệu thô (JSON OTLP batches của metrics, logs, traces) được ghi liên tục theo cây thời gian `year=2026/month=11/day=04/...` sẵn sàng phục vụ AI offline và thẩm định benchmark.
6. **Bộ 7 Dashboards SRE Hoàn Thiện**: Gọi Grafana API `/api/search` xác thực toàn bộ 7 Dashboards chuẩn mực ngành (`mc-executive-overview`, `mc-system-topology`, `mc-red-metrics`, `mc-k8s-infrastructure`, `mc-slo-governance`, `mc-wan-telemetry`, `mc-logs-traces-deepdive`) đã được provisioned và hiển thị trực quan.
7. **Mô Hình Phụ Thuộc Đám Mây Sâu (Deep Cloud Dependencies)**: Toàn bộ telemetry (Traces, Logs, Metrics thô) đều mang đầy đủ bộ nhận diện hạ tầng sâu: IAM Role ARN (`cloud.identity.arn`), Tài nguyên ARN (`cloud.resource_id`), ID tài khoản (`cloud.account.id`), Mạng VPC/VNet (`network.vpc.id`, `network.vnet.id`), Subnet CIDR và Security Group, loại bỏ hoàn toàn tình trạng `unknown_service`.
8. **Trực Quan Hóa Đột Phá Trên Grafana Topology**: Dashboard `mc-system-topology` phiên bản v3 được xác thực qua Grafana API với 5 panel chuyên sâu:
   - Node Graph tương tác: Click vào Node xem chi tiết 10+ trường phụ thuộc sâu (IAM Role, ARN, Resource ID, Subnet, Security Group, Storage, KMS). Click vào Edge xem thông số WAN (10ms RTT, loss 0.1%, mTLS 1.3).
   - Bảng Ma trận kết nối mạng L3/L4 (Cross-Cloud Network Routing & Subnet Matrix): Ánh xạ rõ nét từng tuyến IP nguồn, IP đích, Subnet CIDR (10.0.1.0/24 vs 10.1.2.0/24), Security Group và QPS thực tế.
   - Bảng Kiểm kê phụ thuộc 360° (Deep Cloud Dependencies 360° Inventory) của từng workload.
9. **Nâng Cấp Toàn Diện Bộ 7 Dashboards SRE & USE Method (Phase 3.5)**:
   - `k8s-infrastructure.json`: Mở rộng từ 4 lên 10 panels phân tầng theo 4 Rows chuẩn phương pháp USE (Compute & Load Avg, Memory & Paging, Disk I/O & Inode Saturation, Network Interface & TCP Sockets).
   - `wan-telemetry.json`: Nâng cấp lên 8 panels tích hợp packet drops thực tế (`system_network_dropped_total`), packet rate và socket saturation.
   - `system-topology.json`: Loại bỏ chuỗi tĩnh giả lập, đồng bộ hóa Node Graph với dữ liệu động thực tế và bổ sung Panel 6 (Cluster Node Resource & Network Health Summary Table).
   - `red-metrics.json`: Hoàn thiện 4 Golden Signals với độ bão hòa hệ thống (Saturation) và trễ Database/RMI Backend Call Latency.
   - `logs-traces-deepdive.json`: Tích hợp bộ đếm lỗi hạ tầng bất thường (regex anomaly filter) và luồng log chuyên sâu tầng Database Persistence tại `azure-k3d`.
   - `mc-executive-overview.json`: Bảng Fleet Health Matrix đa chiều tổng hợp Memory, CPU Load 1m, Network Drops, Disk IOPS.
10. **Chuẩn Hóa Bộ Unified Resource Monitoring Schemas (Phase 3.6)**:
    - Ban hành đặc tả kiến trúc `docs/schemas/RESOURCE_MONITORING_SCHEMAS.md` phân định rõ 3 tầng phụ thuộc (Application, System, Cloud) và cơ chế thu thập tương ứng (IMDS vs K8s API vs IaC/OTTL Enrichment).
    - Tạo 2 tệp Schema chuẩn máy đọc được `docs/schemas/webapp-monitoring-schema.yaml` và `docs/schemas/instance-monitoring-schema.yaml`.
    - Bổ sung Panel 6 (Application Runtime Saturation: JVM Memory Heap Usage & Thread Count) vào `red-metrics.json` với cơ chế trục Y kép (Dual Y-Axis).

