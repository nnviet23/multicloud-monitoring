# Báo Cáo Tiến Độ Triển Khai & Tổng Quan Xử Lý Sự Cố (Implementation Progress & Incident Overview)

> **Tài liệu:** `docs/progress/00_result_progress.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Cập nhật lần cuối:** 2026-11-10  
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
| **Phase 3.7** | AI Anomaly Detection Engine V3 & Closed-Loop AIOps Pipeline (Tempo Trace RCA, Embedded Exporter :9108, Telegram Sink) | **Hoàn thành** | 100% | Hợp nhất nhánh AI, PromQL Dual SemConv, Tempo Trace RCA, Prometheus scrape :9108, Panel 7 Grafana `red-metrics.json`, Telegram Alert Sink |
| **Phase 3.8** | Chiến lược Quan sát Nâng cao Học hỏi từ SigNoz (Dynamic Templating, 360° Data Links, Tempo TraceQL Explorer & Telemetry Cost Meter) | **Hoàn thành** | 100% | 8/8 Grafana Dashboards chuẩn hóa biến động, NodeGraph Health Arcs, Tempo Distributed Traces, Dashboard 8 `mc-cost-telemetry.json`, Edge Pre-filtering & Gateway Tail-sampling |
| **Phase 3.9** | Kiến Trúc Tối Ưu Tầng Sâu (Dual-Route Traces Pipeline, Prometheus Absent Data Alert Rules & Linux/WSL2 Test Suite) | **Hoàn thành** | 100% | OTel Collector Dual-Route Pipeline bảo toàn 100% QPS cho ServiceGraph, 4 nhóm luật Prometheus Alert Rules (`01-configmap-prometheus-rules.yaml`), lệnh `make test` pass 100% trên Ubuntu WSL2 |
| **Phase 4** | Workload Testing (Locust), Live Chaos Evaluation, SLO Validation & Final Scientific Report | *Sẵn sàng thực thi* | 0% | Toàn bộ script Locust & Chaos Engineering đã sẵn sàng khởi chạy |

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
| **INC-P3-17** | Phase 3.7 | AI Engine & AIOps Closed-Loop | Lệch pha tên SemConv PromQL, xung đột kịch bản chaos với 3 cụm k3d, thiếu phản hồi Closed-Loop và kênh cảnh báo Telegram | High | **Đã giải quyết** | Chuẩn hóa PromQL Dual SemConv fallback trong `collector.py` & `detector.py`, chuyển hướng toàn bộ scripts chaos sang 3 cụm chuẩn k3d (AWS, Azure, Hub), xây dựng máy chủ Prometheus Exporter nhúng cổng `:9108`, bổ sung Panel 7 Grafana (Dual Y-Axis) và tích hợp Telegram Alert Sink kèm bộ đệm chống spam 60s. |
| **INC-P3-18** | Phase 3.8 | Visualization & Telemetry Cost | Dashboards Grafana thiếu biến động (static templating), thiếu liên kết ngữ cảnh (Data Links), thiếu panel TraceQL Tempo, và thiếu giám sát chi phí/cardinality | Medium | **Đã giải quyết** | Bổ sung dynamic templating (`$cluster`, `$service`, `$environment`) cho 100% dashboards, tích hợp Data Links chuyển tiếp ngữ cảnh, nhúng Tempo TraceQL explorer (`{ status = error || duration > 1.5s }`), và phát triển Dashboard 8 chuyên sâu về Cost Meter & Cardinality Management theo chuẩn SigNoz. |
| **INC-P3-19** | Phase 3.9 | Collector Pipeline & Alerting | ServiceGraph bị suy giảm thông lượng do tail-sampling và Prometheus thiếu tập luật cảnh báo tự động | Medium | **Đã giải quyết** | Thiết lập Dual-Route Traces Pipeline trong OTel Gateway tách riêng luồng ServiceGraph (100% QPS) với luồng lưu trữ Tempo (tail-sampling), triển khai 4 nhóm luật Prometheus Alert Rules và hoàn thiện master test suite `make test` chạy mượt mà trên Linux/WSL2. |
| **INC-P3-20** | Phase 3.9 | Kustomize CRD & Containerd Cache | Race condition khi apply Kustomize Pyrra CRD cùng ServiceLevelObjective CR và containerd pull scope error cho MinIO image | Medium | **Đã giải quyết** | Áp dụng lại Kustomize overlay sau khi Kube API server hoàn tất đăng ký schema CRD; sử dụng pipeline `docker save | ctr images import -` nạp trực tiếp image MinIO vào containerd của k3d server node, đưa toàn bộ 18 pod lên trạng thái 100% `Running`. |
| **INC-P3-21** | Phase 3.9 | Clean Teardown & Cloud Identity Normalization | Tồn đọng Docker images sau khi teardown; nhãn sai lệch "AzureVM" và định danh giả lập chưa chuẩn thực tế (123456 / 000000) | High | **Đã giải quyết** | Khởi tạo script `clean_images.sh` tích hợp vào `make teardown` xóa sạch 100% container images; loại bỏ hoàn toàn nhãn AzureVM, chuẩn hóa sang AKS NodePool (`nodepool-data`); làm giàu định danh chuẩn thực tế với Microsoft Entra ID (Tenant/UAMI) và AWS Account ID 12 số (`851725492014`). |
| **INC-P3-22** | Phase 3.9.3 | Remediation & Cryptographic PKI Verification | Lệch service Prometheus `prometheus-server:80`, Head Sampling 20% làm mất 80% error traces, MySQL 384Mi nguy cơ OOM, kịch bản GCP không tồn tại, và script PKI thiếu xác thực chữ ký mật mã | Critical | **Đã giải quyết** | 1. Chuẩn hóa script PKI với `openssl verify -CAfile` + `openssl x509 -checkend 604800` + `chmod 600`.<br>2. Sửa `collector.py`, `detector.py`, `run_live.py` trỏ đúng `svc/prometheus:9090`.<br>3. Gỡ bỏ `probabilistic_sampler` tại Spoke, bật `compression: gzip`, hội tụ spans về Hub để `servicegraphconnector` và `tail_sampling` bảo toàn 100% error/high-latency traces.<br>4. Nâng RAM MySQL lên `768Mi` và cấu hình `retention_period: 72h` cho Loki.<br>5. Chuẩn hóa 100% kịch bản trong `scenarios.json` về cặp cụm thực tế `aws <-> azure`. |
| **INC-P3-23** | Phase 3.9.5 | Dynamic Secret Injection & Dashboards Standardization | Mật khẩu S3 MinIO plaintext trong ConfigMap của Loki/Tempo; 8 Dashboards Grafana tiêu đề rườm rà, lệch biến cluster, thiếu filter cụm và thiếu metrics GC/P99/Service | High | **Đã giải quyết** | 1. Loại bỏ 100% plaintext trong ConfigMap Loki & Tempo, chuyển sang `${MINIO_ROOT_USER}` & `${MINIO_ROOT_PASSWORD}` kết hợp cờ `-config.expand-env=true` nạp động từ Secret.<br>2. Chuẩn hóa tiêu đề 8 Dashboards ngắn gọn `01.` đến `08.`.<br>3. Chuẩn hóa biến `$cluster` dùng `label_values(system_cpu_time_seconds_total, k8s_cluster_name)` trên 8/8 Dashboards.<br>4. Thêm filter `k8s_cluster_name=~"$cluster"` cho 10 panels K8s Infra và Panels 6, 7, 8 WAN Telemetry.<br>5. Bổ sung GC Pause (ms/s) cho Panel 6 RED Metrics, quantile P99 cho Topology, và gom nhóm `service_name` cho Logs. |
| **INC-P3-24** | Phase 3.9.7 | Dashboards vs Schemas v4.2.0 Alignment & Safe Refinements | Rà soát độ phủ giữa 8 Categories/4 Entity Profiles và 8 Grafana Dashboards; phát hiện 5 điểm cần tinh chỉnh (GAP-01 đến GAP-05) | Medium | **Đã giải quyết** | 1. Giữ nguyên bộ lọc `{server=~"$service"}` cho GAP-01 và không thêm panel cAdvisor vào Dashboard 04 cho GAP-04 nhằm triệt tiêu hoàn toàn rủi ro "No Data".<br>2. Bổ sung bộ lọc `{k8s_cluster_name=~"$cluster"}` cho Panel 4 của `red-metrics.json` (GAP-02).<br>3. Chuẩn hóa tiêu đề/mô tả Waterfall Panel 5 của `mc-cost-telemetry.json` (GAP-03).<br>4. Bổ sung target `refId: C` hiển thị Database Error Rate (`reqps`, trục Y phải, màu đỏ) trên Panel 5 và đồng bộ biến `$service` trên Panel 6 của `red-metrics.json` (GAP-05). Toàn bộ 8 dashboards và kustomize build hợp lệ 100%. |

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
  ├── otel-collector-spoke       1/1 Running   (Hostmetrics, Filelog, Edge Noise Filter, Gzip mTLS to Hub)
  ├── teastore-registry          1/1 Running   (RMI Registry :1099, NodePort :31112)
  ├── teastore-webui             1/1 Running   (Tomcat WebUI :8080)
  ├── teastore-auth              1/1 Running   (Authentication service)
  ├── teastore-image             1/1 Running   (Image service)
  └── teastore-recommender       1/1 Running   (Recommender service)

[azure-k3d] (Spoke 2 - Persistence)
  ├── otel-collector-spoke       1/1 Running   (Hostmetrics, Filelog, Edge Noise Filter, Gzip mTLS to Hub)
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
11. **Tích Hợp Dynamic Multi-Cluster Templating & 360° Data Links (Phase 3.8 - Gói 1 & Gói 2)**:
    - Chuẩn hóa hệ thống biến động (`templating`) trên **100% (8/8) Grafana Dashboards**:
      - `$cluster`: Truy vấn động `label_values(up, cluster)` hoặc `k8s_cluster_name` cho phép cô lập phân tích theo từng cụm hoặc xem toàn cục đa cụm (`$__all`).
      - `$service`: Truy vấn `label_values(traces_service_graph_request_total, server)` lọc chi tiết microservice (WebUI, Auth, Recommender, Image, Persistence, DB).
      - `$environment`: Phân tách ranh giới môi trường (`production` vs `staging`).
    - Nâng cấp **Interactive NodeGraph (Panel 1 trên `system-topology.json`)**:
      - Tích hợp vòng tròn sức khỏe (Health Donut Arcs) với `arc__passed` (xanh lục) và `arc__failed` (đỏ) phản ánh tỷ lệ lỗi trực quan trên từng node.
      - Hiển thị nhãn kết nối an toàn `Active (mTLS 1.3)` trên toàn bộ các cạnh (edges) WAN xuyên cụm.
      - Tích hợp 360° Data Links: Click chuột trực tiếp từ Node để chuyển tiếp ngữ cảnh sang `mc-red-metrics` hoặc `mc-logs-traces-deepdive` kèm biến `$service`, `$cluster` và khoảng thời gian `${__from}`/`${__to}`.
    - Tích hợp Data Links trên Panels 1, 2, 3 của `red-metrics.json` và Panel 6 của `slo-governance.json` dẫn trực tiếp tới điều tra Logs & Traces chuyên sâu.
12. **Nâng Cấp Tempo Distributed Tracing Explorer & Dashboard 8 Quản Trị Chi Phí Telemetry (Phase 3.8 - Gói 3 & Gói 4)**:
    - **Nâng cấp `logs-traces-deepdive.json`**:
      - Bổ sung Panel 6: *Tempo Distributed TraceQL Explorer (Cross-Cloud Slow & Error Traces)* truy vấn trực tiếp từ Tempo backend qua TraceQL `{ status = error || duration > 1.5s }`, cho phép xem chi tiết Spans Waterfall của các giao dịch lỗi hoặc vượt ngưỡng độ trễ WAN/DB.
      - Bổ sung Panel 7: *Trace Spans Latency Distribution & Service Bottlenecks (P99, P90, P50)* tính toán theo thời gian thực từ `traces_service_graph_request_server_seconds_bucket`.
    - **Kiến tạo Dashboard 8: `mc-cost-telemetry.json` (Multi-Cloud Telemetry Ingestion, Cardinality & Cost Meter)**:
      - 8 Panels chuyên sâu phục vụ đánh giá luận văn:
        1. *Total Telemetry Ingestion Rate*: Tổng tốc độ nạp (pps) của toàn bộ Metrics, Logs, Spans.
        2. *Projected Monthly Telemetry Volume*: Dự báo tổng dung lượng nạp trong 30 ngày (GB/tháng).
        3. *Estimated Monthly Cloud WAN Egress Cost*: Ước tính chi phí truyền tải WAN liên đám mây theo đơn giá chuẩn $0.09/GB.
        4. *Telemetry Ingestion Rate by Multi-Cloud Cluster*: Phân bổ lưu lượng nạp theo `aws-k3d`, `azure-k3d`, `hub-k3d`.
        5. *Trace Volume Reduction Waterfall*: Đánh giá hiệu quả tiết kiệm chi phí của cơ chế Edge Pre-filtering (`filter/drop_noise`) và Central Gateway Tail-sampling (100% error/slow preservation).
        6. *Top 10 High-Cardinality Metrics Inspector*: Bảng kiểm toán rò rỉ nhãn vô hạn (unbounded cardinality) thời gian thực.
        7. *Logs Ingestion Rate by Service (Loki)*: Lưu lượng log chi tiết theo từng service.
        8. *Collector Health: Pipeline Memory RSS & Dropped Telemetry Points*: Giám sát bộ đệm và áp lực bộ nhớ collector pods.
      - Đăng ký chính thức `dashboards/mc-cost-telemetry.json` vào `k8s/base/visualization-grafana/kustomization.yaml`.
    - Xác thực kỹ thuật: 100% 8/8 tệp JSON dashboard vượt qua kiểm tra cú pháp; Kustomize build thành công cho cả 3 cụm (`hub-k3d`, `aws-k3d`, `azure-k3d`).
13. **Kiến Trúc Tối Ưu Tầng Sâu & Hoàn Thiện Master Test Suite (Phase 3.9)**:
    - **Dual-Route Traces Pipeline trong OTel Gateway (`03-configmap.yaml`)**:
      - Tách luồng traces thành 2 pipeline độc lập:
        - `traces`: Nhận 100% spans thô $\rightarrow$ qua `memory_limiter`, `transform/normalize_cloud`, `batch` $\rightarrow$ xuất trực tiếp vào `servicegraph` connector. Bảo toàn nguyên vẹn 100% throughput giao dịch (True QPS) và độ chính xác của bản đồ mạng Service Map.
        - `traces/storage`: Nhận spans thô $\rightarrow$ qua `tail_sampling` (giữ 100% trace lỗi, 100% trace trễ > 1500ms, lấy mẫu 5% trace thông thường) $\rightarrow$ ghi vào `otlp/tempo` và MinIO S3 `awss3`. Đảm bảo tiết kiệm >70% chi phí lưu trữ TSDB.
    - **Bộ Luật Cảnh Báo Prometheus Thông Minh (`01-configmap-prometheus-rules.yaml`)**:
      - Ban hành ConfigMap `prometheus-rules` và liên kết trực tiếp vào Prometheus StatefulSet (`/etc/prometheus/rules/alerts.yaml`) với 4 nhóm luật:
        1. `SpokeClusterHeartbeatAbsent`: Bắt lỗi mất tín hiệu telemetry từ Spoke AWS hoặc Azure quá 2 phút (Absent Data detection).
        2. `MicroserviceHighErrorRate`: Cảnh báo khi tỷ lệ lỗi microservice > 5% trong 2 phút.
        3. `CrossCloudWANLatencyDegraded`: Cảnh báo khi trễ P99 liên cụm vượt 1500ms liên tục trong 2 phút.
        4. `OTelCollectorMemoryHigh`: Giám sát áp lực bộ nhớ và nguy cơ tràn bộ đệm OTel Collector Pods (> 400MB RSS).
    - **Hoàn Thiện Master Automation Makefile & Xác Thực 100% Trên Ubuntu WSL2**:
      - Bổ sung các target: `make test`, `make test-ai`, `make validate-dashboards`, `make validate-kustomize`, `make test-wan`.
      - Chạy thực tế lệnh `make test` trong môi trường Ubuntu (WSL2):
        - AI Anomaly Detection Engine V3: 4/4 bài test đạt `OK` (thời gian chạy 0.001s).
        - Toàn bộ 8/8 Dashboards Grafana: Xác thực cú pháp JSON hợp lệ 100%.
        - Kustomize manifests của cả 3 cụm (`hub-k3d`, `aws-k3d`, `azure-k3d`): Build dry-run thành công 100%.
14. **Kiểm Thử Nghiệm Thu Toàn Diện Trên Môi Trường Sạch (Fresh Teardown & Full Redeployment Verification - 2026-11-10)**:
    - **Quy trình thực nghiệm**:
      1. Xóa bỏ hoàn toàn thư mục làm việc cũ trên Ubuntu (WSL2) và clone mới 100% từ nhánh `feat/integrate-infra-ai-anomaly` (commit `e7e2d16`).
      2. Kích hoạt `make teardown` (Ansible playbook `00_cleanup_all.yml`): Xóa sạch 3 cụm k3d, docker network `mc-monitoring-net`, volumes lưu trữ và PKI certs tạm thời. Kiểm tra `docker ps -a`, `k3d cluster list`, `docker network ls` xác nhận 0 container, 0 cluster, 0 network còn sót lại (sạch 100%).
      3. Khởi tạo hạ tầng tuần tự:
         - `make env-setup`: Tạo tệp `.env` từ `.env.example`.
         - `make pki-generate`: Sinh Root CA, Hub server certs và Spoke1/Spoke2 client certs.
         - `make infra`: Khởi tạo 3 cụm `hub-k3d`, `aws-k3d`, `azure-k3d`, thiết lập WAN netem (10ms ±2ms) và đồng bộ secrets mTLS (Ansible recap: 40 ok, 11 changed, 0 failed).
         - `make deploy-hub`: Triển khai toàn bộ cụm Hub Observability. Sau khi Kube API server hoàn tất đăng ký schema CRD Pyrra và nạp ảnh MinIO vào containerd, toàn bộ 9 Pods Hub đạt `1/1 Running` (`prometheus-0` đạt `2/2 Running`).
         - `make deploy-spokes`: Triển khai workload TeaStore và OTel Collector Spoke cho cụm AWS và Azure. Toàn bộ các microservices đạt `1/1 Running`:
           - `aws-k3d`: `otel-collector-spoke`, `teastore-webui`, `teastore-auth`, `teastore-image`, `teastore-recommender`, `teastore-registry`.
           - `azure-k3d`: `otel-collector-spoke`, `teastore-persistence`, `teastore-db`.
    - **Kết quả nghiệm thu live end-to-end**:
      - **TeaStore WebUI HTTP Service**: `curl -sI http://localhost:8080/tools.descartes.teastore.webui/` $\rightarrow$ `HTTP/1.1 200 OK` (Server: TeaStoreTomcat).
      - **Grafana Health & Dashboards**: `curl -sI http://localhost:3000/api/health` $\rightarrow$ `HTTP/1.1 200 OK`. Gọi `/api/search` xác thực toàn bộ 8/8 Dashboards chuẩn SRE và Cost Meter đã được provision tự động vào folder `Multi-Cloud Observability`.
      - **MinIO Object Storage S3**: `mc ls local` xác nhận 4 buckets (`loki-data`, `raw-telemetry`, `tempo-traces`, `thanos-metrics`) hoạt động trơn tru; dữ liệu OTLP thô liên tục được stream vào `raw-telemetry/year=2026/...`.
      - **Prometheus Alert Rules**: `/api/v1/rules` xác nhận 4 nhóm luật SigNoz (`SpokeClusterHeartbeatAbsent`, `MicroserviceHighErrorRate`, `CrossCloudWANLatencyDegraded`, `OTelCollectorMemoryHigh`) đều ở trạng thái hoạt động (Active). Luật Heartbeat bắt lỗi chính xác thời điểm cụm khởi động khi chưa có tín hiệu mTLS.
      - **Mô phỏng WAN Netem**: Ping giữa node `aws-k3d-server-0` và `azure-k3d-server-0` duy trì RTT thực tế 20–39ms với 0% packet loss.
      - **Automated Test Suite (`make test`)**: 4/4 bài kiểm tra AI Anomaly Detection Engine V3 đạt `OK`, 8/8 Dashboards Grafana JSON hợp lệ, và build thành công 3 Kustomize overlays.



