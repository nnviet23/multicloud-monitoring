# Hướng Dẫn Cài Đặt & Triển Khai Toàn Diện Hệ Thống (End-to-End Implementation Guide)

> **Tài liệu:** `docs/progress/IMPLEMENTATION.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Phiên bản tài liệu:** v1.0.0  
> **Cập nhật lần cuối:** 2026-11-04  

---

## 1. Tổng Quan Kiến Trúc & Danh Mục Công Nghệ (Overview & Tech Stack)

### 1.1. Mục tiêu hệ thống
Dự án xây dựng một nền tảng giám sát đa đám mây (Multi-Cloud Observability Platform) theo mô hình **Hub-Spoke** có khả năng tái lập (reproducible), chịu lỗi và bảo mật cao:
* **Spoke 1 (`aws-k3d`):** Cụm Kubernetes đóng vai trò mô phỏng vùng đám mây AWS, triển khai các dịch vụ tính toán (Compute Layer) của ứng dụng benchmark TeaStore và bộ sinh tải Locust.
* **Spoke 2 (`azure-k3d`):** Cụm Kubernetes đóng vai trò mô phỏng vùng đám mây Azure, triển khai tầng cơ sở dữ liệu và lưu trữ bền vững (Persistence & Database Layer - MySQL).
* **Simulated WAN:** Cầu nối mạng Docker Bridge (`mc-monitoring-net: 172.28.0.0/16`) được tiêm suy hao mạng WAN qua Linux `tc netem` (RTT Latency 10ms, Jitter 2ms, Packet Loss 0.1%).
* **Central Hub (`hub-k3d`):** Cụm Kubernetes trung tâm tiếp nhận toàn bộ dữ liệu Telemetry (Metrics, Logs, Traces) qua kết nối bảo mật mTLS 1.3, chuẩn hóa theo OpenTelemetry Semantic Conventions và lưu trữ lâu dài.

### 1.2. Giới thiệu Ứng dụng Benchmark — TeaStore
* **Tên ứng dụng:** Descartes TeaStore — Microservice Reference Application.
* **Tác giả:** Descartes Research Group (Đại học Würzburg, CHLB Đức).
* **Kho lưu trữ GitHub gốc:** [https://github.com/DescartesResearch/TeaStore](https://github.com/DescartesResearch/TeaStore)
* **Kiến trúc microservice:**
  * `teastore-registry`: Dịch vụ định danh và đăng ký dịch vụ nội bộ (RMI Registry).
  * `teastore-webui`: Giao diện web người dùng chạy trên Apache Tomcat.
  * `teastore-auth`: Dịch vụ xác thực và quản lý phiên người dùng.
  * `teastore-image`: Dịch vụ lưu trữ và xử lý hình ảnh sản phẩm.
  * `teastore-recommender`: Dịch vụ gợi ý sản phẩm dựa trên học máy (Collaborative Filtering).
  * `teastore-persistence`: Dịch vụ tầng trung gian thao tác dữ liệu (Hibernate JPA).
  * `teastore-db`: Cơ sở dữ liệu quan hệ MySQL 8.0 lưu trữ người dùng và sản phẩm.

### 1.3. Bảng Danh Mục Phiên Bản Công Nghệ Ghim Cứng (Pinned Tech Stack)

> **Nguyên tắc bất biến:** Tuyệt đối không dùng nhãn `latest`. Toàn bộ phiên bản được ghim cứng theo `infra/README.md`.

| Thành phần (Component) | Phiên bản ghim cứng | Image / Identifier | Vai trò & Mục đích |
|---|---|---|---|
| **Host OS** | Ubuntu `24.04` / `26.04` | Ubuntu Noble/LTS | Hệ điều hành máy chủ/máy trạm thực thi |
| **Container Engine** | Docker Engine `29.8.2` | Community Edition | Nền tảng containerization trên host |
| **Kubernetes CLI** | `kubectl` | `v1.31.2` | Công cụ giao tiếp Kubernetes API Server |
| **Cluster Engine** | k3s trong k3d `v5.6.0` | `rancher/k3s:v1.31.2-k3s1` | Kubernetes siêu nhẹ tối ưu tài nguyên RAM |
| **IaC Automation** | Ansible Core `2.15.8` | `ansible-core==2.15.8` | Tự động hóa cài đặt, cấu hình WAN và cụm |
| **K8s Config Management**| Kustomize `v5.3.0` | `kustomize/kustomize:v5.3.0` | Quản lý manifests theo mô hình Base vs Overlays |
| **Telemetry Agent** | OTel Java Agent `v2.10.0` | `autoinstrumentation-java:2.10.0` | Tự động đo đạc bytecode Java trong TeaStore |
| **Telemetry Edge/Hub** | OTel Collector Contrib `0.114.0` | `otel/opentelemetry-collector-contrib:0.114.0` | Lọc, lấy mẫu 20%, chuẩn hóa và xuất telemetry |
| **Metrics Storage** | Prometheus `v2.50.0` + Thanos `v0.36.1`| `prom/prometheus:v2.50.0` / `quay.io/thanos/thanos:v0.36.1` | TSDB metric ngắn hạn và lưu trữ S3 dài hạn |
| **Logs Storage** | Grafana Loki `v2.9.4` | `grafana/loki:2.9.4` | Lưu trữ và lập chỉ mục metadata logs dạng chunks |
| **Traces Storage** | Grafana Tempo `v2.4.0` | `grafana/tempo:2.4.0` | Lưu trữ trace phân tán dạng block Parquet trên S3 |
| **Object Storage** | MinIO Server | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | Kho lưu trữ đối tượng tương thích chuẩn AWS S3 |
| **Visualization** | Grafana `11.5.0` | `grafana/grafana:11.5.0` | Giao diện đồ thị, Topology và RED dashboards |
| **SLO Management** | Pyrra `v0.7.3` | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Quản trị độ tin cậy và ngân sách lỗi Multi-Burn-Rate |
| **Smart Alerting** | Robusta Runner `0.53.0` | `robustadev/robusta-runner:0.53.0` | Khảo sát ngữ cảnh pod lỗi và gửi Telegram |
| **Load Testing** | Locust `2.24.0` | `locustio/locust:2.24.0` | Bộ sinh tải phân tán bằng kịch bản Python |
| **Security / PKI** | OpenSSL `4.0.3` | `openssl=4.0.3` | Sinh Root CA và chứng chỉ x509 mTLS 1.3 |

---

## 2. Yêu Cầu Tiền Đề & Những Thứ Người Dùng Cần Tự Chuẩn Bị (Prerequisites & Self-Setup)

Trước khi thực hiện lệnh triển khai, bạn cần đảm bảo máy tính đáp ứng các điều kiện sau:

### 2.1. Yêu cầu phần cứng và hệ điều hành
* **RAM:** Tối thiểu 16 GB RAM (Khuyến nghị 24 GB – 32 GB để chạy đồng thời 3 cụm Kubernetes và bộ lưu trữ TSDB).
* **CPU:** Tối thiểu 4 Cores / 8 Threads (Khuyến nghị 8 Cores trở lên).
* **Dung lượng đĩa trống:** Tối thiểu 40 GB dung lượng SSD trống.
* **Hệ điều hành:**
  * **Linux (Ưu tiên số 1):** Ubuntu 24.04 LTS hoặc 26.04 LTS.
  * **Windows:** Windows 10/11 Pro/Enterprise với **WSL2** (cài đặt distro Ubuntu 24.04).

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
4. **Ansible & Python:**
   * Python 3.10 trở lên và `ansible-core==2.15.8`:
     ```bash
     pip install ansible-core==2.15.8
     ansible --version
     ```

### 2.3. Cấu hình Telegram Bot cho Robusta Smart Alerting (Tự thiết lập)
Để hệ thống tự động bắn cảnh báo kèm nguyên nhân gốc rễ (RCA) về điện thoại của bạn qua Telegram khi có sự cố pod:
1. Mở ứng dụng Telegram, tìm kiếm bot chính thức **`@BotFather`**.
2. Gửi lệnh `/newbot`, đặt tên cho Bot và nhận chuỗi mã bí mật **`TELEGRAM_BOT_TOKEN`** (ví dụ: `7123456789:AAH...`).
3. Mở khung chat với bot bạn vừa tạo, bấm `/start`.
4. Tìm kiếm bot **`@userinfobot`** trên Telegram, bấm `/start` để lấy số định danh cá nhân **`TELEGRAM_CHAT_ID`** (ví dụ: `123456789`).
5. Cập nhật thông tin vào file cấu hình `k8s/base/smart-alerting-robusta/01-secret-telegram.yaml`:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: robusta-telegram-creds
     namespace: monitoring
   type: Opaque
   stringData:
     bot-token: "YOUR_TELEGRAM_BOT_TOKEN_HERE"
     chat-id: "YOUR_TELEGRAM_CHAT_ID_HERE"
   ```

---

## 3. Quy Trình Triển Khai Chi Tiết Từng Bước (Step-by-Step Implementation)

### Bước 1: Clone kho lưu trữ về máy
Mở Terminal trên Linux hoặc trong WSL2:
```bash
git clone https://github.com/your-username/multicloud-monitoring.git
cd multicloud-monitoring
```

### Bước 2: Chuẩn bị môi trường & cài đặt công cụ Host
Thực thi playbook kiểm tra và cài đặt công cụ cần thiết trên host:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host_tools.yml
```

### Bước 3: Khởi tạo 3 cụm k3d đa đám mây
Khởi tạo tự động 3 cụm Kubernetes độc lập gắn kết chung vào bridge network `mc-monitoring-net` (`172.28.0.0/16`):
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_provision_k3d_clusters.yml
```
*Sau bước này, lệnh `k3d cluster list` sẽ hiển thị 3 cụm: `hub-k3d`, `aws-k3d`, `azure-k3d`.*

### Bước 4: Thiết lập suy hao mạng mô phỏng WAN (WAN Emulation)
Tiêm trễ mạng 10ms, dao động jitter 2ms, mất gói tin 0.1% lên bridge container:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_emulate_wan_latency.yml
```

### Bước 5: Sinh chứng chỉ bảo mật PKI & Phân phối Secret mTLS 1.3
Khởi tạo Root CA và các chứng chỉ SAN cho Gateway và Spoke Collectors, tự động mount vào cả 3 cụm:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/06_distribute_mtls_secrets.yml
```

### Bước 6: Đồng bộ hóa cấu hình máy chủ giữa các cụm
Cấu hình địa chỉ IP DNS của cụm Hub vào Spoke để Spoke Collector phân giải được domain `k3d-hub-k3d-server-0`:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/04_sync_cluster_hosts.yml
```

### Bước 7: Triển khai các thành phần Kubernetes qua Kustomize

#### 7.1. Triển khai Cụm Trung Tâm (Central Hub `hub-k3d`):
```bash
# 1. Triển khai MinIO Object Storage
kubectl --context=k3d-hub-k3d apply -k k8s/base/storage-minio

# 2. Triển khai Prometheus & Thanos Query Engine
kubectl --context=k3d-hub-k3d apply -k k8s/base/metrics-thanos

# 3. Triển khai Grafana Tempo (Traces TSDB)
kubectl --context=k3d-hub-k3d apply -k k8s/base/traces-tempo

# 4. Triển khai Grafana Loki (Logs TSDB)
kubectl --context=k3d-hub-k3d apply -k k8s/base/logs-loki

# 5. Triển khai Grafana UI & Provisioned Dashboards
kubectl --context=k3d-hub-k3d apply -k k8s/base/visualization-grafana

# 6. Triển khai Pyrra SLO-as-Code Controller
kubectl --context=k3d-hub-k3d apply -k k8s/base/slo-pyrra

# 7. Triển khai Robusta Smart Alerting
kubectl --context=k3d-hub-k3d apply -k k8s/base/smart-alerting-robusta

# 8. Triển khai OpenTelemetry Gateway Hub Ingestion
kubectl --context=k3d-hub-k3d apply -k k8s/base/otel-collector/gateway
```

#### 7.2. Triển khai Cụm Spoke AWS (`aws-k3d` - Compute Layer):
```bash
kubectl --context=k3d-aws-k3d apply -k k8s/overlays/local-k3d/spoke-aws
```
*Tự động triển khai: `teastore-registry`, `teastore-webui`, `teastore-auth`, `teastore-image`, `teastore-recommender` và `otel-collector-spoke`.*

#### 7.3. Triển khai Cụm Spoke Azure (`azure-k3d` - Persistence Layer):
```bash
kubectl --context=k3d-azure-k3d apply -k k8s/overlays/local-k3d/spoke-azure
```
*Tự động triển khai: `teastore-db` (MySQL 8.0), `teastore-persistence` và `otel-collector-spoke`.*

### Bước 8: Kiểm tra xác nhận trạng thái toàn hệ thống
Thực thi playbook kiểm thử nghiệm thu tổng thể:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/05_verify_clusters.yml
```
Kiểm tra nhanh qua `kubectl`:
```bash
kubectl --context=k3d-hub-k3d get pods -A
kubectl --context=k3d-aws-k3d get pods -A
kubectl --context=k3d-azure-k3d get pods -A
```
*Toàn bộ các Pod phải hiển thị trạng thái `Running`.*

---

## 4. Hướng Dẫn Truy Cập Giao Diện GUI Web & Quản Trị Tài Nguyên (Access & Credentials Guide)

Sau khi hoàn tất quá trình triển khai, toàn bộ các cổng dịch vụ đã được ánh xạ trực tiếp ra máy host (`localhost`). Bạn có thể mở trình duyệt web và truy cập theo danh mục dưới đây:

### 4.1. Bảng Tra Cứu Toàn Bộ Giao Diện Web (Web Portals Matrix)

| Dịch vụ (Service) | Cụm K8s | URL Truy Cập Trình Duyệt | Tài khoản (Username) | Mật khẩu (Password) | Chức năng chính |
|---|---|---|---|---|---|
| **Grafana UI** | `hub-k3d` | [http://localhost:3000](http://localhost:3000) | `admin` | `MultiCloudSecurePassword2026!` | Xem Dashboard Topology, RED Metrics, Logs & Traces |
| **MinIO Console** | `hub-k3d` | [http://localhost:9001](http://localhost:9001) | `admin` | `MultiCloudSecurePassword2026!` | Giao diện quản trị Object Storage, xem 4 S3 buckets |
| **MinIO S3 API** | `hub-k3d` | [http://localhost:9000](http://localhost:9000) | `admin` | `MultiCloudSecurePassword2026!` | Endpoint S3 API cho Prometheus, Loki, Tempo |
| **TeaStore WebUI** | `aws-k3d` | [http://localhost:8080/tools.descartes.teastore.webui/](http://localhost:8080/tools.descartes.teastore.webui/) | *(Không yêu cầu)* | *(Không yêu cầu)* | Web bán trà trực tuyến, dùng để tương tác sinh tải |
| **Thanos Query UI** | `hub-k3d` | `http://localhost:9090` *(xem lệnh mở cổng bên dưới)* | *(Không yêu cầu)* | *(Không yêu cầu)* | Giao diện PromQL federated query toàn hệ thống |
| **Pyrra SLO UI** | `hub-k3d` | `http://localhost:9099` *(xem lệnh mở cổng bên dưới)* | *(Không yêu cầu)* | *(Không yêu cầu)* | Giao diện theo dõi SLO và ngân sách lỗi Error Budget |
| **Locust Load UI** | `aws-k3d` | [http://localhost:8089](http://localhost:8089) | *(Không yêu cầu)* | *(Không yêu cầu)* | Giao diện sinh tải người dùng ảo cho TeaStore |

---

### 4.2. Lệnh Port-Forward Nhanh Cho Các Giao Diện Nội Bộ
Một số dịch vụ nội bộ chạy trong mạng Cluster IP để đảm bảo an ninh, nếu bạn muốn mở giao diện trực quan của chúng, hãy chạy các lệnh sau trong terminal riêng:

1. **Mở Thanos Query Web UI (Cổng 9090):**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/thanos-query 9090:9090
   ```
   *Truy cập tại: [http://localhost:9090](http://localhost:9090)*

2. **Mở Pyrra SLO Management UI (Cổng 9099):**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/pyrra 9099:9099
   ```
   *Truy cập tại: [http://localhost:9099](http://localhost:9099)*

---

## 5. Quy Trình Dọn Dẹp & Xóa Sạch Hệ Thống Khi Cần Gỡ Bỏ (Teardown & Cleanup)

Khi cần reset hoàn toàn môi trường về trạng thái ban đầu để kiểm thử lại từ đầu hoặc giải phóng dung lượng RAM/Disk:

### Lệnh gỡ bỏ tự động toàn diện qua Ansible:
```bash
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/00_cleanup_all.yml
```
Playbook này sẽ tự động:
1. Xóa bỏ hoàn toàn 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`).
2. Xóa các container phụ trợ và mạng docker bridge `mc-monitoring-net`.
3. Xóa các tệp chứng chỉ x509 tạm thời.
4. Trả lại tài nguyên CPU và RAM sạch sẽ cho máy host.

