# Multi-Cloud Observability & Monitoring Platform

> **Đề tài tốt nghiệp:** Nghiên cứu và Xây dựng Nền tảng Giám sát Đa Đám Mây (Multi-Cloud Monitoring Platform) theo Kiến trúc Hub-Spoke.  
> **Ứng dụng kiểm chuẩn:** [Descartes TeaStore](https://github.com/DescartesResearch/TeaStore) Microservices Benchmark (v1.4.1).  
> **Kiến trúc cơ sở:** Phương án A — Thu thập lọc tại biên (Edge-Filtered Ingestion), tiền xử lý và lưu trữ tập trung tại Hub với mTLS 1.3 qua mạng WAN mô phỏng.

---

## 1. Giới Thiệu & Mục Tiêu Nghiên Cứu

Hệ thống giải quyết bài toán phân mảnh viễn trắc (telemetry fragmentation), chi phí truyền tải mạng WAN (egress cost) và an toàn dữ liệu xuyên biên giới đám mây bằng cách xây dựng một kiến trúc quan sát 3 trụ cột (Metrics, Logs, Traces) chuẩn hoá theo OpenTelemetry:
- **Chuẩn hóa Timestamp xuyên Vùng:** Áp dụng hợp đồng thời gian 4 lớp (`event`, `observed`, `received`, `normalized` UTC).
- **Mô hình Phụ thuộc Đám mây Sâu 360°:** Khám phá và biểu diễn 6 trục phụ thuộc (IAM Role ARN, Resource IDs, VPC/VNet, Subnets, Security Groups, Host Nodes).
- **Tiền tổng hợp Đồ thị Dịch vụ (Pre-aggregated Service Graph):** Tổng hợp quan hệ gọi L7 qua `servicegraphconnector` ngay tại Hub Ingestion đẩy vào Thanos TSDB, cung cấp truy vấn PromQL tức thời cho Grafana Node Graph.
- **Tính Bất biến & Tái lập Khoa học:** Lưu trữ toàn bộ viễn trắc OTLP thô bất biến trong MinIO S3 (`s3://raw-telemetry/`).

---

## 2. Ngăn Xếp Công Nghệ (Pinned Tech Stack Matrix)

Toàn bộ phiên bản công nghệ được **ghim cứng (pinned version)** theo chuẩn tại [infra/README.md](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/infra/README.md):

| Lớp kiến trúc | Thành phần | Phiên bản ghim cứng | Vai trò kỹ thuật |
|---|---|---|---|
| **OS & Host Runtime** | Ubuntu / Docker Engine | `26.04` / `29.8.2` | Nền tảng điều phối container máy trạm |
| **Simulated Clusters** | k3s / k3d | `v1.31.2+k3s1` / `v5.6.0` | 3 cụm K8s siêu nhẹ (`hub-k3d`, `aws-k3d`, `azure-k3d`) |
| **Automation** | Ansible Core / Kustomize | `2.15.8` / `v5.3.0` | Tự động hóa hạ tầng và cấu hình declarative |
| **Telemetry Agents** | OTel Java Agent / Contrib | `v2.10.0` / `0.114.0` | Bytecode auto-instrumentation & Edge/Gateway collector |
| **Time-Series Metrics** | Prometheus / Thanos | `v2.50.0` / `v0.36.1` | TSDB metrics & lưu trữ phân tán dài hạn |
| **Logs & Traces** | Grafana Loki / Tempo | `2.9.4` / `2.4.0` | Lưu trữ khối log streams và W3C trace waterfall |
| **Object Storage** | MinIO | `RELEASE.2025-10-15T17-29-55Z` | S3-compatible backend storage cho Thanos, Loki, Tempo, Raw |
| **Visualization** | Grafana | `11.5.0` | 7 bộ Dashboard SRE chuyên biệt |
| **SLO & Alerting** | Pyrra / Robusta | `v0.7.3` / `0.53.0` | Quản trị SLO-as-code & Cảnh báo thông minh sang Telegram |
| **Benchmark App** | Descartes TeaStore | `1.4.1` / MySQL `8.0.36` | 7 microservices giả lập thương mại điện tử |

---

## 3. Phân Bổ Mô Hình Cụm Hub - Spoke

- **Spoke 1 — `aws-k3d` (Mô phỏng AWS EKS — us-east-1):**  
  Đảm nhận tầng tính toán người dùng (Compute Layer): `teastore-webui` (LoadBalancer 8080), `teastore-auth`, `teastore-image`, `teastore-recommender`, `teastore-registry` (NodePort 31112), và OTel Spoke Edge Collector.
- **Spoke 2 — `azure-k3d` (Mô phỏng Azure AKS — southasia):**  
  Đảm nhận tầng dữ liệu và lưu trữ (Data Layer): `teastore-persistence` (NodePort 31111), `teastore-db` (MySQL 8.0), và OTel Spoke Edge Collector.
- **Hub — `hub-k3d` (Trung tâm Quan sát & Lưu trữ):**  
  OTel Hub Gateway (LoadBalancer 4317 mTLS), MinIO (9000/9001), Prometheus + Thanos (9090), Loki (3100), Tempo (3200), Grafana (3000), Pyrra (9099), Robusta Runner.
- **Mạng WAN mô phỏng (`mc-monitoring-net`):**  
  Mạng cầu Docker `172.28.0.0/16`, tiêm suy hao bằng Linux `tc/netem`: RTT 10ms ±2ms, packet loss 0.1%.

---

## 4. Hướng Dẫn Triển Khai Nhanh

Chi tiết từng bước triển khai xem tại tài liệu hướng dẫn: [IMPLEMENTATION.md](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/docs/progress/IMPLEMENTATION.md).

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
| **Grafana Dashboards** | `http://localhost:3000` | `admin` / `MultiCloudSecurePassword2026!` | 7 Dashboard SRE (RED, Topology, SLO, WAN) |
| **MinIO Console** | `http://localhost:9001` | `admin` / `MultiCloudSecurePassword2026!` | Quản lý 4 bucket S3 object storage |
| **Thanos Query UI** | `http://localhost:9090` | Không yêu cầu | Truy vấn chỉ số PromQL đa cụm |
| **Pyrra SLO UI** | `http://localhost:9099` | Không yêu cầu | Theo dõi Error Budget & SLI/SLO 99.5% |

---

## 6. Thành Viên Tham Gia Nghiên Cứu

| Họ và Tên | Mã số Sinh viên | Trách nhiệm chuyên môn |
|---|:---:|---|
| **Huỳnh Hữu Dũng** | 23127352 | Thiết kế hạ tầng khóa công khai PKI, bảo mật kênh truyền mTLS 1.3 cho OTLP streams |
| **Đinh Tuấn Duy** | 23127356 | Khảo sát mô hình viễn trắc, phát hiện bất thường, phân tích nguyên nhân gốc rễ (RCA) |
| **Nguyễn Nam Việt** | 23127517 | Tự động hóa hạ tầng Ansible/k3d, mô phỏng WAN, triển khai kho lưu trữ viễn trắc (MinIO, Thanos, Loki, Tempo, Grafana) |

---

## 7. Giấy Phép
Dự án được phân phối dưới giấy phép mã nguồn mở MIT License.
