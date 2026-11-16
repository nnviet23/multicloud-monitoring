# Multi-Cloud Observability & Monitoring Platform

> **Đề tài tốt nghiệp:** Nghiên cứu và Xây dựng Nền tảng Giám sát Đa Đám Mây (Multi-Cloud Monitoring Platform) theo Kiến trúc Hub-Spoke.  
> **Ứng dụng kiểm chuẩn:** [Descartes TeaStore](https://github.com/DescartesResearch/TeaStore) Microservices Benchmark (v1.4.1).  
> **Kiến trúc cơ sở:** Phương án A — Thu thập lọc tại biên (Edge-Filtered Ingestion), tiền xử lý và lưu trữ tập trung tại Hub với mTLS 1.3 qua mạng WAN mô phỏng, tích hợp AI Anomaly Detection & Intelligent Alerting (Robusta).

---

## 1. Giới Thiệu & Mục Tiêu Nghiên Cứu

Hệ thống giải quyết bài toán phân mảnh viễn trắc (telemetry fragmentation), chi phí truyền tải mạng WAN (egress cost) và an toàn dữ liệu xuyên biên giới đám mây bằng cách xây dựng một kiến trúc quan sát 3 trụ cột (Metrics, Logs, Traces) chuẩn hoá theo OpenTelemetry:
- **Chuẩn hóa Timestamp xuyên Vùng:** Áp dụng hợp đồng thời gian 4 lớp (`event`, `observed`, `received`, `normalized` UTC).
- **Mô hình Phụ thuộc Đám mây Sâu 360°:** Khám phá và biểu diễn 6 trục phụ thuộc (IAM Role ARN, Resource IDs, VPC/VNet, Subnets, Security Groups, Host Nodes).
- **Tiền tổng hợp Đồ thị Dịch vụ (Pre-aggregated Service Graph):** Tổng hợp quan hệ gọi L7 qua `servicegraphconnector` ngay tại Hub Ingestion đẩy vào Thanos TSDB, cung cấp truy vấn PromQL tức thời cho Grafana Node Graph.
- **Tính Bất biến & Tái lập Khoa học:** Lưu trữ toàn bộ viễn trắc OTLP thô bất biến trong MinIO S3 (`s3://raw-telemetry/`).
- **AI Anomaly Detection & Cross-Cloud Trace RCA:** Module học máy phát hiện bất thường tự động (`ai-engine/`) kết hợp với phân tích nguyên nhân gốc rễ và kiểm thử hỗn loạn (`tests/chaos/`).

---

## 2. Ngăn Xếp Công Nghệ (Pinned Tech Stack Matrix)

Toàn bộ phiên bản công nghệ được **ghim cứng (pinned version)** theo chuẩn tại [infra/README.md](infra/README.md):

| Lớp kiến trúc | Thành phần | Phiên bản ghim cứng | Vai trò kỹ thuật |
|---|---|---|---|
| **OS & Host Runtime** | Ubuntu / Docker Engine | `26.04` / `29.8.2` | Nền tảng điều phối container máy trạm |
| **Simulated Clusters** | k3s / k3d | `v1.31.2+k3s1` / `v5.6.0` | 4 cụm K8s siêu nhẹ (`hub-k3d`, `aws-k3d`, `azure-k3d`, `gcp-k3d`) |
| **Automation** | Ansible Core / Kustomize | `2.15.8` / `v5.3.0` | Tự động hóa hạ tầng và cấu hình declarative |
| **Telemetry Agents** | OTel Java Agent / Contrib | `v2.10.0` / `0.114.0` | Bytecode auto-instrumentation & Edge/Gateway collector |
| **Time-Series Metrics** | Prometheus / Thanos | `v2.50.0` / `v0.36.1` | TSDB metrics & lưu trữ phân tán dài hạn |
| **Logs & Traces** | Grafana Loki / Tempo | `2.9.4` / `2.4.0` | Lưu trữ khối log streams và W3C trace waterfall |
| **Object Storage** | MinIO | `RELEASE.2025-10-15T17-29-55Z` | S3-compatible backend storage cho Thanos, Loki, Tempo, Raw |
| **Visualization** | Grafana | `11.5.0` | 8 bộ Dashboard SRE chuyên biệt (Executive, Topology, RED, USE, WAN, Deepdive, SLO, Cost) |
| **SLO & Alerting** | Pyrra / Robusta | `v0.7.3` / `0.53.0` | Quản trị SLO-as-code & Cảnh báo thông minh sang Telegram |
| **AI Anomaly Engine** | PyTorch / Autoencoders | `2.x` / GRU+TCN | Phát hiện bất thường viễn trắc đa đám mây & suy diễn RCA |
| **Benchmark App** | Descartes TeaStore | `1.4.1` / MySQL `8.0.36` | 7 microservices giả lập thương mại điện tử |

---

## 3. Phân Bổ Mô Hình Cụm Hub - Spoke

- **Spoke 1 — `aws-k3d` (Mô phỏng AWS EKS — us-east-1; Edge Gateway, Storefront & Media):**  
  `nginx-api-gateway` (LoadBalancer 8080, reverse proxy + rate limit), `teastore-webui` (ClusterIP, chỉ đi qua gateway), `teastore-image`, `teastore-registry` (NodePort 31112), và OTel Spoke Edge Collector.
- **Spoke 2 — `azure-k3d` (Mô phỏng Azure AKS — southasia; Enterprise IAM & Core Transactional Data):**  
  `teastore-auth` (NodePort 31114), `teastore-persistence` (NodePort 31111), `teastore-db` (MySQL 8.0), và OTel Spoke Edge Collector.
- **Spoke 3 — `gcp-k3d` (Mô phỏng GCP GKE — asia-southeast1; AI/ML Recommendation Platform):**  
  `teastore-recommender` (NodePort 31113) và OTel Spoke Edge Collector.
- **Gọi chéo cloud:** service ngoài AWS đăng ký vào registry AWS bằng `HOST_NAME=k3d-<cloud>-k3d-server-0` + NodePort (overlay `k8s/overlays/local-k3d/spoke-*`), nên mọi request WebUI → Auth/Persistence/Recommender đều đi qua WAN mô phỏng.
- **Hub — `hub-k3d` (Trung tâm Quan sát & Lưu trữ):**  
  OTel Hub Gateway (LoadBalancer 4317 mTLS), MinIO (9000/9001), Prometheus + Thanos (9090), Loki (3100), Tempo (3200), Grafana (3000), Pyrra (9099), Robusta Runner, và AI Anomaly Detection Plane.
- **Mạng WAN mô phỏng (`mc-monitoring-net`):**  
  Mạng cầu Docker `172.28.0.0/16`, tiêm suy hao bằng Linux `tc/netem`: RTT 10ms ±2ms, packet loss 0.1%.

---

## 4. Hướng Dẫn Triển Khai Nhanh

Chi tiết từng bước triển khai xem tại tài liệu hướng dẫn: [IMPLEMENTATION.md](docs/progress/IMPLEMENTATION.md).

### 4.1. Khởi tạo bằng Makefile trung tâm

```bash
# 1. Kiểm tra môi trường host, kéo images và nạp vào k3d
make setup

# 2. Khởi tạo 3 cụm k3d, mạng WAN bridge, sinh certs mTLS và đồng bộ DNS
make infra

# 3. Triển khai toàn bộ ứng dụng và hạ tầng giám sát
make deploy

# 4. Kiểm tra sức khỏe toàn diện hệ thống
make verify

# 5. Dọn dẹp sạch sẽ toàn bộ môi trường khi kết thúc
make teardown
```

---

## 5. Bảng Ma Trận Cổng Dịch Vụ & Truy Cập Web GUI

| Dịch vụ | URL Truy cập | Tài khoản / Mật khẩu | Mục đích sử dụng |
|---|---|---|---|
| **TeaStore WebUI** | `http://localhost:8080/tools.descartes.teastore.webui/` | Anonymous | Giao diện mua sắm kiểm chuẩn tải |
| **Grafana Dashboards** | `http://localhost:3000` | `admin` / `MultiCloudSecurePassword2026!` | 8 Dashboard SRE chuẩn hóa (Executive, Topology, RED, USE, WAN, Logs/Traces, SLO, Cost) |
| **MinIO Console** | `http://localhost:9001` | `admin` / `MultiCloudSecurePassword2026!` | Quản lý 4 bucket S3 object storage |
| **Thanos Query UI** | `http://localhost:9090` | Không yêu cầu | Truy vấn chỉ số PromQL đa cụm |
| **Pyrra SLO UI** | `http://localhost:9099` | Không yêu cầu | Theo dõi Error Budget & SLI/SLO 99.5% |

---

### 5.1. Danh Mục 8 Grafana Dashboards SRE

Hệ thống được cấu hình sẵn 8 Dashboard chuyên sâu tự động nạp qua provisioning (`k8s/base/visualization-grafana/dashboards/`):

1. **`01. Executive Overview` (`mc-executive-overview.json`):**
   - **Vai trò:** Bảng điều khiển cấp quản lý tổng quan sức khỏe toàn bộ hệ sinh thái đa đám mây.
   - **Panel trọng tâm:** Tổng lưu lượng truy cập đa đám mây, độ trễ liên đám mây WAN P95 (AWS us-east-1 ↔ Azure southasia), tỷ lệ vi phạm SLO và Ma trận sức khỏe hạm đội cụm đa đám mây (Cloud Cluster Fleet Health Matrix với bảng gom nhóm thống nhất `k8s_cluster_name, cloud_provider` qua phép biến đổi `merge`).
2. **`02. Topology & Cloud Context` (`system-topology.json`):**
   - **Vai trò:** Biểu diễn đồ thị kiến trúc mạng và ánh xạ phụ thuộc đám mây sâu 360°.
   - **Panel trọng tâm:** Ma trận định tuyến mạng và Subnet L3/L4 liên đám mây, bảng kiểm kê phụ thuộc đám mây sâu (IAM Role ARN, VPC/VNet ID, Security Group, Subnet), phân phối độ trễ gọi dịch vụ (P50/P90/P99), và Bảng tổng hợp sức khỏe tài nguyên Node và kết nối mạng Kernel theo cụm (`k8s_cluster_name, cloud_provider`).
3. **`03. Application & JVM (RED)` (`red-metrics.json`):**
   - **Vai trò:** Giám sát hiệu năng ứng dụng theo phương pháp RED (Rate, Errors, Duration) và runtime JVM.
   - **Panel trọng tâm:** Request Rate, Error Rate, Latency Duration Percentiles (P50, P90, P99), độ trễ và lỗi gọi cơ sở dữ liệu/RMI Backend tách riêng với trục Y kép (`custom.axisPlacement: right`), Saturation tài nguyên máy chủ (%wa CPU & active TCP sockets), bão hòa JVM runtime (Heap used MB, Threads, GC pause ms), và Điểm bất thường AIOps kèm phân rã nguyên nhân gốc rễ (RCA Trace Latency Decomposition: $T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$).
4. **`04. Compute & OS Kernel (USE)` (`k8s-infrastructure.json`):**
   - **Vai trò:** Giám sát hạ tầng máy chủ và nhân hệ điều hành Linux theo phương pháp USE (Utilization, Saturation, Errors).
   - **Panel trọng tâm:** 3 đồng hồ đo tài nguyên cấp phát (CPU Usage 400%, Node Memory 9.59 GB, Host Disk Space 1007 GB), phân rã CPU (User/System/Idle/Wait), System Load Average (1m/5m/15m) vs Cores, Memory breakdown, Swap & Paging Activity (`system_paging_faults_total` và `system_paging_operations_total` hỗ trợ trục Y kép `faults/s` vs `ops/s`), Disk Throughput (Bps) & IOPS (trục Y kép), Disk Saturation (Latency ms & Queue length), bảng Filesystem & Inode Usage gom nhóm đồng nhất `k8s_cluster_name, cloud_provider, mountpoint`, và TCP Connection Saturation theo trạng thái.
5. **`05. Network & WAN Transport` (`wan-telemetry.json`):**
   - **Vai trò:** Giám sát liên kết mạng đường truyền WAN mô phỏng đa vùng đám mây.
   - **Panel trọng tâm:** Độ trễ mạng liên đám mây (P50, P95 ms), băng thông đường truyền WAN bridge (`mc-monitoring-net`), tỷ lệ gói tin rớt mạng thực tế và lỗi truyền tải (Drops vs Errors trục Y kép), và Tốc độ truyền gói tin kèm bão hòa socket TCP đa cụm (Packet Rates `pps` vs Active Sockets `short` cấu hình trục Y kép).
6. **`06. Logs, Traces & Database` (`logs-traces-deepdive.json`):**
   - **Vai trò:** Phân tích sâu dòng nhật ký viễn trắc phân tán kết hợp dấu vết trace và cơ sở dữ liệu.
   - **Panel trọng tâm:** Khối lượng log stream theo từng vi dịch vụ `{{service_name}} ({{job}})`, tốc độ phát sinh log Warning/Error, log bất thường hạ tầng & kết nối cơ sở dữ liệu, phân phối độ trễ Trace Spans & Service Bottlenecks (P99/P90/P50), truy vấn log stream chi tiết qua Loki LogQL, và liên kết ngược TraceID trực tiếp sang Tempo.
7. **`07. SLO & Error Budget` (`slo-governance.json`):**
   - **Vai trò:** Quản trị độ tin cậy dịch vụ theo chuẩn SRE SLO-as-code (Pyrra integration).
   - **Panel trọng tâm:** Tỷ lệ sẵn sàng khả dụng hiện tại (SLI vs SLO Target 99.5%), Ngân sách lỗi còn lại (Remaining Error Budget %), Xu hướng tốc độ đốt ngân sách đa cửa sổ thời gian (Multi-Window Burn Rate Trend 5m vs 30m), và Bảng phân bổ mức tiêu thụ ngân sách lỗi theo từng vi dịch vụ.
8. **`08. Telemetry & Cost Governance` (`mc-cost-telemetry.json`):**
   - **Vai trò:** Quản trị chi phí và tối ưu hóa khối lượng viễn trắc (FinOps & Observability Cost Control).
   - **Panel trọng tâm:** Tốc độ nạp viễn trắc theo cụm (Metrics points/s vs Logs lines/s hỗ trợ trục Y kép), Thác nước cắt giảm khối lượng trace (Trace Volume Reduction Waterfall: Lọc nhiễu tại Edge Spoke và Tail-Sampling tại Hub Central Gateway), Bảng soi Top 10 metric có độ biến động nhãn cao nhất (High-Cardinality Metrics Inspector), Tốc độ nạp log qua Loki, và Sức khỏe bộ đệm OTel Collector (Memory RSS bytes vs Dropped Points/s trên trục Y kép).

---

## 6. AI Anomaly Detection & Chaos Testing

Chi tiết kiến trúc và kiểm thử hỗn loạn:
- **Kiến trúc AI Engine:** Xem tại [ai-engine/README.md](ai-engine/README.md) và [docs/architecture/ai_engine_architecture.md](docs/architecture/ai_engine_architecture.md).
- **Chaos Testing & Fault Scenarios:** Xem tại [tests/chaos/README.md](tests/chaos/README.md) về các kịch bản tiêm lỗi DB bottleneck, JVM memory leak, HTTP 5xx và WAN degradation với cơ chế tự động dọn dẹp và tự động nhận diện ngữ cảnh cụm (`kubectl config get-contexts -o name`).
