# Hướng Dẫn Cài Đặt & Triển Khai Toàn Diện Hệ Thống Bằng Makefile (Master Implementation Guide)

> **Tài liệu:** `docs/progress/IMPLEMENTATION.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Phiên bản tài liệu:** v2.0.0 (Makefile & Single-Environment Configuration Edition)  
> **Cập nhật lần cuối:** 2026-11-05  

---

## 1. Tổng Quan Kiến Trúc & Danh Mục Công Nghệ (Overview & Tech Stack)

### 1.1. Mục tiêu hệ thống
Dự án xây dựng một nền tảng giám sát đa đám mây (Multi-Cloud Observability Platform) theo mô hình **Hub-Spoke** có khả năng tái lập (reproducible), chịu lỗi và bảo mật cao:
* **Spoke 1 (`aws-k3d`):** Cụm Kubernetes mô phỏng vùng đám mây AWS (`us-east-1`), triển khai tầng tính toán (Compute Layer) của ứng dụng benchmark TeaStore và bộ sinh tải Locust.
* **Spoke 2 (`azure-k3d`):** Cụm Kubernetes mô phỏng vùng đám mây Azure (`southasia`), triển khai tầng cơ sở dữ liệu và lưu trữ bền vững (Persistence & Database Layer - MySQL 8.0).
* **Simulated WAN:** Cầu nối mạng Docker Bridge (`mc-monitoring-net: 172.28.0.0/16`) được tiêm suy hao mạng WAN bằng Linux kernel `tc netem` (RTT Latency 10ms ±2ms, Packet Loss 0.1%).
* **Central Hub (`hub-k3d`):** Cụm Kubernetes trung tâm tiếp nhận toàn bộ dữ liệu viễn trắc (Metrics, Logs, Traces) qua kết nối bảo mật mTLS 1.3, chuẩn hóa theo OpenTelemetry Semantic Conventions, tiền tổng hợp đồ thị dịch vụ (`servicegraphconnector`) và lưu trữ dài hạn.

### 1.2. Giới thiệu Ứng dụng Benchmark — Descartes TeaStore
* **Tên ứng dụng:** Descartes TeaStore — Microservice Reference Application.
* **Tác giả:** Descartes Research Group (Đại học Würzburg, CHLB Đức).
* **Kho lưu trữ GitHub gốc:** [https://github.com/DescartesResearch/TeaStore](https://github.com/DescartesResearch/TeaStore)
* **Kiến trúc microservices:**
  * `teastore-registry`: Dịch vụ định danh và đăng ký dịch vụ nội bộ (RMI Registry, NodePort 31112).
  * `teastore-webui`: Giao diện web người dùng chạy trên Apache Tomcat (LoadBalancer 8080).
  * `teastore-auth`: Dịch vụ xác thực và quản lý phiên người dùng.
  * `teastore-image`: Dịch vụ lưu trữ và xử lý hình ảnh sản phẩm.
  * `teastore-recommender`: Dịch vụ gợi ý sản phẩm dựa trên lọc cộng tác (Collaborative Filtering).
  * `teastore-persistence`: Dịch vụ tầng trung gian thao tác dữ liệu (Hibernate JPA, NodePort 31111).
  * `teastore-db`: Cơ sở dữ liệu quan hệ MySQL 8.0 lưu trữ danh mục sản phẩm và tài khoản.

### 1.3. Bảng Danh Mục Phiên Bản Công Nghệ Ghim Cứng (Pinned Tech Stack)

> **Nguyên tắc bất biến:** Tuyệt đối không dùng nhãn `latest` hoặc floating tag. Toàn bộ phiên bản được ghim cứng theo [infra/README.md](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/infra/README.md).

| Thành phần (Component) | Phiên bản ghim cứng | Image / Identifier | Vai trò & Mục đích |
|---|---|---|---|
| **Host OS** | Ubuntu `24.04` / `26.04` | Ubuntu Noble/LTS | Hệ điều hành máy trạm thực thi |
| **Container Engine** | Docker Engine `29.8.2` | Community Edition | Nền tảng container runtime trên host |
| **Cluster CLI & Engine** | k3d `v5.6.0` / k3s `v1.31.2` | `rancher/k3s:v1.31.2-k3s1` | Kubernetes siêu nhẹ tối ưu tài nguyên RAM |
| **Kubernetes CLI** | `kubectl` | `v1.31.2` | Công cụ giao tiếp với Kubernetes API Server |
| **IaC Automation** | Ansible Core `2.15.8` | `ansible-core==2.15.8` | Tự động hóa cài đặt, cấu hình WAN và cụm |
| **Config Management**| Kustomize `v5.3.0` | `kustomize/kustomize:v5.3.0` | Quản lý manifests theo mô hình Base vs Overlays |
| **Entrypoint Control** | GNU Make | `make 4.3+` | Điều phối toàn bộ vòng đời hệ thống bằng 1 lệnh |
| **Telemetry Agent** | OTel Java Agent `v2.10.0` | `autoinstrumentation-java:2.10.0` | Bytecode auto-instrumentation cho Tomcat TeaStore |
| **Telemetry Pipeline** | OTel Collector Contrib `0.114.0` | `otel/opentelemetry-collector-contrib:0.114.0` | Lọc, lấy mẫu 20%, chuẩn hóa và xuất telemetry |
| **Metrics Storage** | Prometheus `v2.50.0` + Thanos `v0.36.1`| `prom/prometheus:v2.50.0` / `quay.io/thanos/thanos:v0.36.1` | TSDB metric ngắn hạn và lưu trữ S3 dài hạn |
| **Logs Storage** | Grafana Loki `v2.9.4` | `grafana/loki:2.9.4` | Lưu trữ và lập chỉ mục metadata logs dạng chunks |
| **Traces Storage** | Grafana Tempo `v2.4.0` | `grafana/tempo:2.4.0` | Lưu trữ trace phân tán dạng blocks trên S3 |
| **Object Storage** | MinIO Server | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | Kho lưu trữ đối tượng tương thích chuẩn AWS S3 |
| **Visualization** | Grafana `11.5.0` | `grafana/grafana:11.5.0` | 7 bộ Dashboard SRE (RED, Topology, SLO, WAN) |
| **SLO Management** | Pyrra `v0.7.3` | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Quản trị độ tin cậy và ngân sách lỗi Error Budget |
| **Smart Alerting** | Robusta Runner `0.53.0` | `robustadev/robusta-runner:0.53.0` | Bắt sự cố pod, chẩn đoán RCA và gửi Telegram |
| **Security / PKI** | OpenSSL `4.0.3` | `openssl=4.0.3` | Sinh Root CA và chứng chỉ x509 SAN mTLS 1.3 |

---

## 2. Yêu Cầu Tiền Đề & Những Thứ Cần Tự Chuẩn Bị (Prerequisites & Self-Setup)

Trước khi thực hiện lệnh triển khai, bạn cần đảm bảo máy tính đáp ứng các điều kiện sau:

### 2.1. Yêu cầu phần cứng và hệ điều hành
* **RAM:** Tối thiểu 16 GB RAM (Khuyến nghị 24 GB – 32 GB để chạy đồng thời 3 cụm Kubernetes và cụm TSDB).
* **CPU:** Tối thiểu 4 Cores / 8 Threads (Khuyến nghị 8 Cores trở lên).
* **Dung lượng đĩa trống:** Tối thiểu 40 GB dung lượng SSD trống.
* **Hệ điều hành:**
  * **Linux (Ưu tiên số 1):** Ubuntu 24.04 LTS hoặc 26.04 LTS.
  * **Windows:** Windows 10/11 Pro/Enterprise với **WSL2** (Ubuntu 24.04).

### 2.2. Các phần mềm cần tự cài đặt trước trên máy host
1. **Docker Engine:**
   * Cài đặt Docker Engine bản `29.8.2` hoặc Docker Desktop `v4.95.0`.
   * Đảm bảo Docker daemon đang hoạt động và người dùng hiện tại có quyền thực thi Docker không cần `sudo`:
     ```bash
     sudo usermod -aG docker $USER && newgrp docker
     docker ps
     ```
2. **K3d CLI:**
   * Cài đặt k3d phiên bản `v5.6.0`:
     ```bash
     curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | TAG=v5.6.0 bash
     k3d version
     ```
3. **Kubectl & Kustomize:**
   * Cài đặt `kubectl` bản `v1.31.2` và `kustomize` bản `v5.3.0`.
4. **Ansible, Python & Make:**
   * Cài đặt `make`, Python 3.10+ và `ansible-core==2.15.8`:
     ```bash
     sudo apt-get update && sudo apt-get install -y make python3-pip
     pip install ansible-core==2.15.8
     ```

### 2.3. Cấu hình Telegram Bot cho Robusta Smart Alerting (Tự thiết lập)
Để hệ thống tự động bắn cảnh báo kèm chẩn đoán nguyên nhân gốc rễ (RCA) về điện thoại của bạn qua Telegram khi có sự cố:
1. Mở ứng dụng Telegram, tìm kiếm bot chính thức **`@BotFather`**.
2. Gửi lệnh `/newbot`, đặt tên cho Bot và nhận chuỗi mã bí mật **`TELEGRAM_BOT_TOKEN`** (ví dụ: `7123456789:AAH...`).
3. Mở khung chat với bot bạn vừa tạo, bấm `/start`.
4. Tìm kiếm bot **`@userinfobot`** trên Telegram, bấm `/start` để lấy số định danh cá nhân **`TELEGRAM_CHAT_ID`** (ví dụ: `123456789`).
5. Điền trực tiếp hai giá trị này vào file `.env` tại thư mục gốc của dự án.

---

## 3. Quy Trình Triển Khai Bằng Makefile (Makefile Deployment Workflow)

Toàn bộ quy trình triển khai phức tạp trước đây (nhiều playbook và lệnh Kustomize rời rạc) hiện đã được chuẩn hóa thành **5 lệnh Make duy nhất** điều phối từ thư mục gốc:

```
[make setup] ──> [make infra] ──> [make deploy] ──> [make verify] ──> [make teardown]
```

### Bước 1: Clone kho lưu trữ về máy
Mở Terminal trên Linux hoặc trong WSL2:
```bash
git clone https://github.com/nnviet23/multicloud-monitoring.git
cd multicloud-monitoring
git checkout feat/infra-ansible-k3d
```

### Bước 2: Thiết lập môi trường & Tải trước Container Images (`make setup`)
Lệnh này sẽ tự động:
1. Tạo file `.env` từ `.env.example` (nếu chưa có).
2. Đồng bộ file `.env` sang Kustomize overlay của Hub.
3. Tải trước (pre-pull) toàn bộ 17 container images đã ghim phiên bản về máy host để tránh nghẽn mạng khi chạy:

```bash
make setup
```

> **Cấu hình tùy chọn:** Nếu bạn có Telegram Bot Token cho Robusta, hãy mở file `.env` tại thư mục gốc và cập nhật:
> ```ini
> TELEGRAM_BOT_TOKEN=YOUR_REAL_TELEGRAM_BOT_TOKEN
> TELEGRAM_CHAT_ID=YOUR_REAL_TELEGRAM_CHAT_ID
> ```

### Bước 3: Khởi tạo hạ tầng cụm, mạng WAN & Chứng chỉ mTLS (`make infra`)
Lệnh này tự động điều phối:
1. Sinh cặp khóa Root CA và chứng chỉ x509 SAN cho Hub Server và Spoke Clients bằng OpenSSL (`security/pki/scripts/`).
2. Chạy Ansible Master Playbook `infra/ansible/playbooks/site.yml`:
   * Tạo Docker bridge `mc-monitoring-net` (`172.28.0.0/16`).
   * Khởi tạo 3 cụm k3d: `hub-k3d`, `aws-k3d`, `azure-k3d`.
   * Tiêm suy hao mạng WAN bằng `tc netem` (10ms delay, 2ms jitter, 0.1% loss).
   * Quét Docker IP và cập nhật đồng bộ CoreDNS `NodeHosts` giữa 3 cụm.
   * Tự động mount Secret chứng chỉ mTLS vào namespace `monitoring` của cả 3 cụm.
3. Nạp (import) trước các container image từ Docker host vào runtime containerd của 3 cụm k3d:

```bash
make infra
```

### Bước 4: Triển khai toàn bộ ứng dụng & hạ tầng quan sát (`make deploy`)
Lệnh này áp dụng toàn bộ Kustomize Overlays lên cả 3 cụm Kubernetes:
* **Tại `hub-k3d`:** Triển khai MinIO S3, Prometheus, Thanos Query, Loki, Tempo, Grafana, Pyrra, Robusta, và OTel Hub Gateway (mTLS 1.3). Toàn bộ Secret được tự động sinh từ file `.env` duy nhất qua Kustomize `secretGenerator`.
* **Tại `aws-k3d` (Spoke 1):** Triển khai tầng tính toán TeaStore (`webui`, `registry`, `auth`, `image`, `recommender`) và OTel Spoke Edge Collector.
* **Tại `azure-k3d` (Spoke 2):** Triển khai cơ sở dữ liệu MySQL `teastore-db`, tầng lưu trữ `teastore-persistence` và OTel Spoke Edge Collector.

```bash
make deploy
```

> **Triển khai từng cụm độc lập (nếu muốn):**
> * Chỉ deploy Hub: `make deploy-hub`
> * Chỉ deploy 2 Spokes: `make deploy-spokes`

### Bước 5: Kiểm tra xác nhận sức khỏe toàn hệ thống (`make verify`)
Kiểm tra tự động trạng thái Nodes, toàn bộ Pods trên cả 3 cụm và kiểm tra kết nối mạng WAN:

```bash
make verify
```

*Kết quả mong đợi:*
- Cả 3 cụm đều có node ở trạng thái `Ready`.
- 100% Pods trên `hub-k3d` (namespace `monitoring`, `storage`) ở trạng thái `Running` (1/1 hoặc 2/2).
- 100% Pods trên `aws-k3d` và `azure-k3d` (namespace `teastore`, `monitoring`) ở trạng thái `Running`.
- Lệnh ping mạng WAN giữa `k3d-aws-k3d-server-0` và `k3d-azure-k3d-server-0` phản hồi RTT ~10ms.

---

## 4. Bảng Tra Cứu Toàn Bộ Giao Diện Web & Thông Tin Đăng Nhập (Access & Credentials Matrix)

Toàn bộ các cổng dịch vụ đã được ánh xạ tự động ra máy host (`localhost`) qua k3d loadbalancer. Bạn có thể mở trực tiếp trên trình duyệt:

| Dịch vụ (Service) | Cụm K8s | URL Truy Cập Trình Duyệt | Tài khoản | Mật khẩu | Mục đích sử dụng |
|---|---|---|---|---|---|
| **TeaStore WebUI** | `aws-k3d` | [http://localhost:8080/tools.descartes.teastore.webui/](http://localhost:8080/tools.descartes.teastore.webui/) | *(Không)* | *(Không)* | Giao diện mua sắm kiểm chuẩn, duyệt danh mục, đặt hàng |
| **Grafana Dashboards** | `hub-k3d` | [http://localhost:3000](http://localhost:3000) | `admin` | `MultiCloudSecurePassword2026!` | 7 Dashboards SRE: System Topology, RED Metrics, SLO, WAN |
| **MinIO Console** | `hub-k3d` | [http://localhost:9001](http://localhost:9001) | `admin` | `MultiCloudSecurePassword2026!` | Quản lý 4 S3 buckets (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`) |
| **MinIO S3 API** | `hub-k3d` | [http://localhost:9000](http://localhost:9000) | `admin` | `MultiCloudSecurePassword2026!` | S3 API endpoint cho Prometheus Sidecar, Loki, Tempo |
| **Thanos Query UI** | `hub-k3d` | `http://localhost:9090` *(xem lệnh mở bên dưới)* | *(Không)* | *(Không)* | Giao diện PromQL federated query toàn hệ thống |
| **Pyrra SLO UI** | `hub-k3d` | `http://localhost:9099` *(xem lệnh mở bên dưới)* | *(Không)* | *(Không)* | Quản trị ngân sách lỗi Error Budget & SLI/SLO 99.5% |
| **Locust Load UI** | `aws-k3d` | [http://localhost:8089](http://localhost:8089) | *(Không)* | *(Không)* | Giao diện sinh tải người dùng ảo phân tán cho TeaStore |

---

### Mở cổng giao diện nội bộ (Port-Forwarding)
Các thành phần nội bộ được bảo vệ trong ClusterIP, khi cần xem trực quan trên máy host, mở một terminal riêng và chạy:

1. **Mở Thanos Query PromQL UI:**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/thanos-query 9090:9090
   ```
   *Truy cập tại: [http://localhost:9090](http://localhost:9090)*

2. **Mở Pyrra SLO Management UI:**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/pyrra 9099:9099
   ```
   *Truy cập tại: [http://localhost:9099](http://localhost:9099)*

---

## 5. Quy Trình Dọn Dẹp & Xóa Sạch Hệ Thống Khi Cần Gỡ Bỏ (Teardown & Cleanup)

Khi cần giải phóng toàn bộ tài nguyên CPU/RAM hoặc thiết lập lại hệ thống từ đầu:

### Lệnh gỡ bỏ toàn diện (`make teardown`):
```bash
make teardown
```

Lệnh này sẽ tự động:
1. Xóa bỏ an toàn toàn bộ 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`).
2. Cưỡng chế xóa các container k3d còn sót lại.
3. Xóa mạng Docker bridge `mc-monitoring-net`.
4. Dọn dẹp sạch sẽ các Docker volumes của MinIO và MySQL.
5. Thu hồi và xóa các tệp chứng chỉ x509 tạm thời trong `security/pki/certs-*/`.

### Lệnh hoàn nguyên mạng WAN mô phỏng (`make reset-wan`):
Nếu chỉ muốn gỡ bỏ suy hao độ trễ mạng WAN để đưa mạng về tốc độ bình thường mà không xóa cụm:
```bash
make reset-wan
```
