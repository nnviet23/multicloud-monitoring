# Hướng Dẫn Cài Đặt & Triển Khai Toàn Diện Hệ Thống Bằng Makefile (Master Implementation Guide)

> **Tài liệu:** `docs/progress/IMPLEMENTATION.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability & Closed-Loop AIOps)  
> **Phiên bản:** `v3.0.0` (Unified Multi-Cloud Runtime, AI Engine V3, Robusta & 8 SRE Dashboards Edition)  
> **Nhánh Git:** `feat/integrate-infra-ai-anomaly`  
> **Cập nhật lần cuối:** 15/11/2026  

---

## 1. Tổng Quan Kiến Trúc & Danh Mục Công Nghệ (Overview & Tech Stack)

### 1.1. Mô hình kiến trúc Hub-Spoke 3 Cụm
Dự án xây dựng nền tảng giám sát đa đám mây (Multi-Cloud Observability Platform) theo mô hình **Hub-Spoke** có khả năng tái lập (reproducible), chịu lỗi cao và bảo mật nghiêm ngặt:
* **Spoke 1 (`aws-k3d`):** Cụm Kubernetes mô phỏng vùng đám mây AWS (`us-east-1`), triển khai tầng tính toán (Compute Layer) của ứng dụng benchmark TeaStore và bộ sinh tải Locust.
* **Spoke 2 (`azure-k3d`):** Cụm Kubernetes mô phỏng vùng đám mây Azure (`southasia`), triển khai tầng cơ sở dữ liệu và lưu trữ bền vững (Persistence & Database Layer - MySQL 8.0).
* **Simulated WAN Network:** Cầu nối mạng Docker Bridge (`mc-monitoring-net: 172.28.0.0/16`) được tiêm suy hao mạng WAN mô phỏng liên đám mây bằng Linux kernel `tc netem` (RTT Latency 10ms ±2ms, Packet Loss 0.1%).
* **Central Hub (`hub-k3d`):** Cụm Kubernetes trung tâm tiếp nhận toàn bộ dữ liệu viễn trắc (Metrics, Logs, Traces) qua kênh truyền bảo mật **mTLS 1.3**, chuẩn hóa ngữ nghĩa theo OpenTelemetry Semantic Conventions, tiền tổng hợp đồ thị dịch vụ (`servicegraphconnector`), lưu trữ dài hạn (Thanos/Loki/Tempo/MinIO) và phân tích tương quan thời gian thực.
* **Closed-Loop AIOps Engine:** Động cơ phát hiện bất thường học sâu Ensemble (GRU + TCN Autoencoders + Isolation Forest), tự động phân rã vết thực thi qua Grafana Tempo ($T_{\text{WAN}}$, $T_{\text{self}}$, $T_{\text{DB}}$), xuất metric qua cổng `:9108/metrics` và khớp nối với Robusta Smart Alerting bắn tin chẩn đoán về Telegram.

```
       ┌────────────────────────────────────────────────────────┐
       │                Central Hub (hub-k3d)                   │
       │  MinIO S3 • Prometheus • Thanos • Loki • Tempo        │
       │  Grafana (8 Dashboards) • Pyrra SLO • Robusta Runner   │
       │              OTel Central Gateway (:4317 mTLS)         │
       └──────────────▲──────────────────────────▲──────────────┘
                      │ (mTLS 1.3 WAN)           │ (mTLS 1.3 WAN)
    ┌─────────────────┴────────────┐       ┌─────┴────────────────────────┐
    │     Spoke 1 (aws-k3d)        │       │     Spoke 2 (azure-k3d)      │
    │  TeaStore Compute Services   │  WAN  │  TeaStore Persistence & DB   │
    │  (WebUI, Auth, Image, Rec)   │◄─────►│  (Persistence, MySQL 8.0)    │
    │  OTel Edge Collector (Agent) │       │  OTel Edge Collector (Agent) │
    │  Locust Workload Generator   │       │                              │
    └──────────────────────────────┘       └──────────────────────────────┘
```

---

### 1.2. Ứng dụng Benchmark — Descartes TeaStore
* **Tên ứng dụng:** Descartes TeaStore — Microservice Reference Application.
* **Tác giả:** Descartes Research Group (Đại học Würzburg, CHLB Đức).
* **Kiến trúc phân bổ xuyên đám mây (Cross-Cloud Deployment):**
  * Tại `aws-k3d`:
    * `teastore-registry`: Dịch vụ định danh và đăng ký RMI Registry (NodePort `31112`).
    * `teastore-webui`: Giao diện người dùng Apache Tomcat (NodePort/LoadBalancer `8080`).
    * `teastore-auth`: Dịch vụ xác thực và quản lý phiên người dùng.
    * `teastore-image`: Dịch vụ lưu trữ và xử lý hình ảnh sản phẩm.
    * `teastore-recommender`: Dịch vụ gợi ý sản phẩm dựa trên lọc cộng tác.
  * Tại `azure-k3d`:
    * `teastore-persistence`: Dịch vụ trung gian thao tác dữ liệu (Hibernate JPA, NodePort `31111`).
    * `teastore-db`: Cơ sở dữ liệu quan hệ MySQL 8.0 lưu trữ danh mục sản phẩm và tài khoản.

---

### 1.3. Danh mục 8 Bộ Grafana SRE Dashboards Hoàn Chỉnh
Toàn bộ 8 Dashboard được tự động nạp (provision) vào Grafana tại [k8s/base/visualization-grafana/dashboards/](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/k8s/base/visualization-grafana/dashboards/):

1. **`01. Executive Overview` (`mc-executive-overview.json`):** Tổng quan mức chiến lược, ma trận sức khỏe các cụm đám mây (Fleet Health Matrix).
2. **`02. Topology & Cloud Context` (`system-topology.json`):** Đồ thị cấu trúc mạng, định danh vị trí vùng địa lý, Node health summary.
3. **`03. Application RED Metrics` (`red-metrics.json`):** Rate, Errors, Duration theo chuẩn RED cho toàn bộ microservices TeaStore.
4. **`04. Compute & OS Kernel (USE)` (`k8s-infrastructure.json`):** CPU, Memory, Disk I/O, Paging Faults theo phương pháp USE.
5. **`05. Network & WAN Transport` (`wan-telemetry.json`):** RTT trễ xuyên đám mây, Packet Drops, TCP Socket Saturation trục Y kép.
6. **`06. Logs, Traces & Database Deepdive` (`logs-traces-deepdive.json`):** Khảo sát phân tán Tempo TraceQL, LogQL stream Loki, chẩn đoán SQL DB.
7. **`07. SLO & Error Budget Governance` (`slo-pyrra.json` / `slo-governance.json`):** Quản trị ngân sách lỗi Error Budget, tốc độ đốt (Burn Rate) theo Pyrra.
8. **`08. Telemetry & Cost Governance` (`mc-cost-telemetry.json`):** Đo đạc lưu lượng viễn trắc (Ingestion Rate) 3 cụm, chi phí Egress mạng WAN và độ hiệu quả nén/lọc dữ liệu.

---

### 1.4. Bảng Phiên Bản Công Nghệ Ghim Cứng (Strict Version Pinning)

> **Nguyên tắc bất biến:** Tuyệt đối không dùng nhãn `latest` hoặc floating tag. Toàn bộ phiên bản được ghim cứng theo [infra/README.md](file:///d:/Workstation/HCMUS/Grade4/01_TTDATN_K23/Tuần%203/multicloud-monitoring/infra/README.md).

| Thành phần | Phiên bản ghim cứng | Container Image / Tool Identifier | Ghi chú & Vai trò |
|---|---|---|---|
| **Host OS** | Ubuntu `24.04` / `26.04` | Ubuntu Noble LTS | Máy tính thực thi hoặc máy ảo WSL2 |
| **Container Engine** | Docker Engine `29.8.2` | Community Edition | Nền tảng container runtime trên host |
| **Kubernetes / k3d** | k3d `v5.6.0` / k3s `v1.31.2` | `rancher/k3s:v1.31.2-k3s1` | Kubernetes siêu nhẹ tối ưu RAM |
| **Kubernetes CLI** | `kubectl` `v1.31.2` | `kubectl` client | Công cụ điều khiển cụm K8s |
| **IaC Automation** | Ansible Core `2.15.8`+ | `ansible-core` (Python 3.10+) | Tự động hóa cài đặt, cấu hình WAN và cụm |
| **Manifests Engine** | Kustomize `v5.3.0` | `kustomize` | Quản lý manifests theo Base vs Overlays |
| **Entrypoint Control** | GNU Make `4.3+` | `make` | Điều phối toàn bộ vòng đời hệ thống |
| **Telemetry Agent** | OTel Java Agent `v2.10.0` | `autoinstrumentation-java:2.10.0` | Bytecode auto-instrumentation cho Tomcat |
| **Telemetry Pipeline** | OTel Collector Contrib `0.114.0` | `otel/opentelemetry-collector-contrib:0.114.0` | Edge Filter 20%, Tail-sampling, Gateway Hub |
| **Metrics Storage** | Prometheus `v2.50.0` + Thanos `v0.36.1` | `prom/prometheus:v2.50.0` / `quay.io/thanos/thanos:v0.36.1` | TSDB metric ngắn hạn và lưu trữ S3 dài hạn |
| **Logs Storage** | Grafana Loki `v2.9.4` | `grafana/loki:2.9.4` | Lưu trữ và lập chỉ mục metadata logs |
| **Traces Storage** | Grafana Tempo `v2.4.0` | `grafana/tempo:2.4.0` | Lưu trữ trace phân tán dạng blocks trên S3 |
| **Object Storage** | MinIO Server | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | Kho lưu trữ S3 tương thích AWS S3 API |
| **Visualization** | Grafana `11.5.0` | `grafana/grafana:11.5.0` | 8 bộ Dashboard SRE hoàn chỉnh |
| **SLO Management** | Pyrra `v0.7.3` | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Quản trị ngân sách lỗi Error Budget |
| **Smart Alerting** | Robusta Runner `0.53.0` | `robustadev/robusta-runner:0.53.0` | Bắt alert, chẩn đoán RCA và gửi Telegram |
| **Security / PKI** | OpenSSL `3.0+` | `openssl` | Sinh Root CA và chứng chỉ SAN mTLS 1.3 |

---

## 2. Yêu Cầu Tiền Đề & Chuẩn Bị Môi Trường (Prerequisites)

### 2.1. Cấu hình phần cứng tối thiểu
* **RAM:** Tối thiểu 16 GB RAM (Khuyến nghị 24 GB – 32 GB để chạy mượt 3 cụm Kubernetes, cụm TSDB và sinh tải).
* **CPU:** Tối thiểu 4 Cores / 8 Threads (Khuyến nghị 8 Cores trở lên).
* **Ổ cứng:** Tối thiểu 40 GB dung lượng SSD trống.
* **Môi trường đề xuất:**
  * **Ubuntu Linux trực tiếp:** Ubuntu 24.04 LTS hoặc 26.04 LTS.
  * **Windows:** Windows 10/11 Pro/Enterprise thông qua **WSL2** (Ubuntu 24.04 LTS).

---

### 2.2. Cài đặt các công cụ bắt buộc trên máy trạm
Chạy các lệnh sau trên Terminal Ubuntu / WSL2:

1. **Docker Engine & Docker Compose:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg lsb-release make python3-pip jq
   # Cấp quyền docker cho user hiện tại (tránh gõ sudo)
   sudo usermod -aG docker $USER && newgrp docker
   docker ps
   ```

2. **k3d CLI (`v5.6.0`):**
   ```bash
   curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | TAG=v5.6.0 bash
   k3d version
   ```

3. **Kubectl (`v1.31.2`):**
   ```bash
   curl -LO "https://dl.k8s.io/release/v1.31.2/bin/linux/amd64/kubectl"
   chmod +x kubectl && sudo mv kubectl /usr/local/bin/
   kubectl version --client
   ```

4. **Kustomize (`v5.3.0`):**
   ```bash
   curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" 5.3.0 | bash
   sudo mv kustomize /usr/local/bin/
   kustomize version
   ```

5. **Ansible & Python Dependencies:**
   ```bash
   pip install --break-system-packages ansible-core==2.15.8 pyyaml
   ansible --version
   ```

---

### 2.3. Thiết lập Telegram Bot cho Cảnh báo Tự động (Robusta & AI Engine)
Để nhận thông báo tức thời khi hệ thống phát hiện bất thường:
1. Mở ứng dụng Telegram, tìm bot **`@BotFather`**, gửi lệnh `/newbot` và đặt tên cho Bot. Bạn sẽ nhận được chuỗi **`TELEGRAM_BOT_TOKEN`** (ví dụ: `7123456789:AAH...`).
2. Mở khung chat với bot vừa tạo, bấm **`/start`**.
3. Tìm bot **`@userinfobot`**, bấm **`/start`** để lấy số định danh cá nhân **`TELEGRAM_CHAT_ID`** (ví dụ: `123456789`).
4. Các thông tin này sẽ được điền vào file `.env` ở bước tiếp theo.

---

## 3. Quy Trình Vận Hành Toàn Diện Bằng Makefile (Master Automation Workflow)

Toàn bộ vòng đời từ sinh khóa, dựng hạ tầng, triển khai ứng dụng, xác thực đến kiểm thử tự động được chuẩn hóa qua **Makefile**:

```
[make setup] ──> [make infra] ──> [make deploy] ──> [make verify] ──> [make test]
```

### Bước 1: Lấy mã nguồn dự án
```bash
git clone https://github.com/nnviet23/multicloud-monitoring.git
cd multicloud-monitoring
git checkout feat/integrate-infra-ai-anomaly
```

---

### Bước 2: Chuẩn bị môi trường & Tải trước Container Images (`make setup`)
Lệnh này tự động tạo file `.env`, đồng bộ cấu hình sang Kustomize overlay của Hub và tải trước 17 container images:
```bash
make setup
```

**Cập nhật cấu hình bí mật trong file `.env` tại thư mục gốc:**
Mở file `.env` và cập nhật thông tin Telegram:
```ini
# --- Smart Alerting: Robusta & AI Telegram Integration ---
TELEGRAM_BOT_TOKEN=7123456789:AAH_your_real_bot_token_here
TELEGRAM_CHAT_ID=123456789
TELEGRAM_COOLDOWN_SECONDS=30

# --- Ingestion Lag Tuning for AI Engine ---
THANOS_QUERY_LAG_OFFSET=5.0
```
Sau đó đồng bộ lại `.env` vào Kustomize Hub:
```bash
make env-setup
```

---

### Bước 3: Sinh khóa mTLS & Khởi tạo Hạ tầng 3 Cụm k3d (`make infra`)
Lệnh này thực hiện tự động toàn bộ chuỗi:
1. **Sinh cặp khóa PKI mTLS 1.3** (`security/pki/scripts/`):
   * Root CA: `security/pki/ca/ca.crt`
   * Hub Server Cert: SAN gồm `k3d-hub-k3d-serverlb`, `k3d-hub-k3d-server-0`, `otel-collector-hub`, `localhost`
   * Spoke Client Certs: Cho `aws-k3d` và `azure-k3d`
2. **Chạy Ansible Master Playbook** (`infra/ansible/playbooks/site.yml`):
   * Khởi tạo mạng Docker Bridge `mc-monitoring-net: 172.28.0.0/16`.
   * Khởi tạo 3 cụm k3d: `hub-k3d`, `aws-k3d`, `azure-k3d`.
   * Tiêm suy hao mạng WAN mô phỏng bằng `tc netem` (10ms delay, 2ms jitter, 0.1% loss).
   * Tự động mount Secret `otel-hub-certs` vào cụm Hub và `otel-spoke-certs` vào 2 cụm Spoke.
   * Đồng bộ hóa CoreDNS `NodeHosts` xuyên suốt 3 cụm.
3. **Nạp trước (import) Container Images** từ máy host vào containerd của cả 3 cụm để tăng tốc độ khởi động Pods:

```bash
make infra
```

> **Mẹo - Chỉ sinh lại chứng chỉ mTLS riêng:**
> ```bash
> make pki-generate
> ```

---

### Bước 4: Kiểm tra tính toàn vẹn Manifests (`make validate-kustomize`)
Trước khi triển khai, kiểm tra cú pháp và khả năng render của toàn bộ Base & Overlays:
```bash
make validate-kustomize
```
*Kết quả chuẩn mong đợi:* `All Kustomize manifests build successfully!`

---

### Bước 5: Triển khai Ứng dụng & Hạ tầng Quan sát (`make deploy`)
Áp dụng toàn bộ Kustomize Overlays lên 3 cụm:
* **Cụm Hub (`hub-k3d`):** Triển khai MinIO S3, Prometheus, Thanos Query, Loki, Tempo, Grafana (8 Dashboards), Pyrra SLO, Robusta Runner và OTel Hub Gateway tiếp nhận mTLS.
* **Cụm Spoke AWS (`aws-k3d`):** Triển khai tầng tính toán TeaStore và OTel Edge Collector (tự động nạp metric nội bộ `:8888`).
* **Cụm Spoke Azure (`azure-k3d`):** Triển khai MySQL `teastore-db`, tầng lưu trữ `teastore-persistence` và OTel Edge Collector.

```bash
make deploy
```

> **Tùy chọn triển khai từng cụm riêng biệt:**
> * Chỉ triển khai Hub: `make deploy-hub`
> * Chỉ triển khai 2 cụm Spoke: `make deploy-spokes`

---

### Bước 6: Kiểm tra xác nhận sức khỏe toàn hệ thống (`make verify`)
Kiểm tra trạng thái sẵn sàng của các Nodes, Pods trên 3 cụm và kiểm tra kết nối mạng WAN:
```bash
make verify
```

*Tiêu chí đánh giá hệ thống khỏe mạnh:*
* Tất cả các Node trên cả 3 cụm đều ở trạng thái `Ready`.
* 100% Pods trên `hub-k3d` (namespace `monitoring`, `storage`) ở trạng thái `Running` (1/1 hoặc 2/2).
* 100% Pods trên `aws-k3d` và `azure-k3d` (namespace `teastore`, `monitoring`) ở trạng thái `Running`.
* Lệnh ping giữa container server `k3d-aws-k3d-server-0` và `k3d-azure-k3d-server-0` phản hồi RTT trung bình ~10ms.

---

### Bước 7: Chạy bộ kiểm thử tự động toàn diện (`make test`)
Chạy kiểm tra tự động bao gồm AI Engine live evaluation, xác thực cú pháp JSON 8 Grafana Dashboards và Kustomize dry-run:
```bash
make test
```
*Kết quả chuẩn:* `All automated system verification tests PASSED!`

---

## 4. Ma Trận Truy Cập & Thông Tin Đăng Nhập (Access Matrix)

Toàn bộ các cổng dịch vụ đã được chuyển tiếp tự động ra máy host (`localhost`) qua bộ cân bằng tải k3d:

| Dịch vụ (Service) | Cụm K8s | URL Truy Cập Trình Duyệt | Tài khoản | Mật khẩu mặc định | Mục đích sử dụng |
|---|---|---|---|---|---|
| **TeaStore WebUI** | `aws-k3d` | [http://localhost:8080/tools.descartes.teastore.webui/](http://localhost:8080/tools.descartes.teastore.webui/) | *(Không)* | *(Không)* | Giao diện mua sắm kiểm chuẩn, duyệt danh mục, đặt hàng |
| **Grafana Dashboards** | `hub-k3d` | [http://localhost:3000](http://localhost:3000) | `admin` | `MultiCloudSecurePassword2026!` | 8 Dashboards SRE (Overview, Topology, RED, USE, WAN, Logs/Traces, SLO, Cost) |
| **AI Metrics Exporter** | Host / k3d | [http://localhost:9108/metrics](http://localhost:9108/metrics) | *(Không)* | *(Không)* | Prometheus metrics AI thời gian thực (Likelihood %, Reconstruction MSE, Tempo RCA) |
| **MinIO Console** | `hub-k3d` | [http://localhost:9001](http://localhost:9001) | `admin` | `MultiCloudSecurePassword2026!` | Quản lý 4 S3 buckets (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`) |
| **MinIO S3 API** | `hub-k3d` | [http://localhost:9000](http://localhost:9000) | `admin` | `MultiCloudSecurePassword2026!` | S3 API endpoint cho Thanos Sidecar, Loki, Tempo |
| **Thanos Query UI** | `hub-k3d` | [http://localhost:9090](http://localhost:9090) *(qua port-forward)* | *(Không)* | *(Không)* | Giao diện PromQL federated query toàn hệ thống |
| **Pyrra SLO UI** | `hub-k3d` | [http://localhost:9099](http://localhost:9099) *(qua port-forward)* | *(Không)* | *(Không)* | Quản trị ngân sách lỗi Error Budget & chỉ số SLI/SLO |
| **Locust Web UI** | `aws-k3d` | [http://localhost:8089](http://localhost:8089) | *(Không)* | *(Không)* | Giao diện điều khiển sinh tải người dùng ảo phân tán |

### Mở cổng các giao diện nội bộ (Port-Forwarding)
Khi cần truy cập giao diện Thanos hoặc Pyrra, mở terminal riêng và chạy:

1. **Thanos Query PromQL UI:**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/thanos-query 9090:9090
   ```
2. **Pyrra SLO Management UI:**
   ```bash
   kubectl --context=k3d-hub-k3d -n monitoring port-forward svc/pyrra 9099:9099
   ```

---

## 5. Vận Hành Tải, Kỹ Thuật Hỗn Loạn & Động Cơ AI (Workload, Chaos & Closed-Loop AIOps)

### 5.1. Kích hoạt bộ sinh tải người dùng (Locust Traffic Generator)
Mở một terminal riêng để sinh tải mua sắm liên tục vào TeaStore:
```bash
# Lựa chọn 1: Sinh tải tự động 4 giai đoạn bằng script nhẹ (Zero external dependencies)
python3 tests/locust/traffic_generator.py --duration 1800 --min-users 10 --max-users 40

# Lựa chọn 2: Sinh tải bằng Locust CLI chuẩn
locust -f tests/locust/locustfile.py --headless -u 20 -r 2 --run-time 30m --host http://localhost:8080
```

---

### 5.2. Khởi chạy Động cơ AI Anomaly Detection V3
Mở một terminal riêng để kích hoạt chu trình suy luận AI thời gian thực:
```bash
python3 ai-engine/inference/detector.py --interval 6
```
Động cơ AI sẽ tự động:
1. Thu thập dữ liệu từ Thanos Query (tự động xử lý Ingestion Lag 5s và khử `NaN`).
2. Chuẩn hóa đặc trưng vi mô qua z-score và đưa vào mô hình Deep Ensemble (Universal GRU + TCN Autoencoders).
3. Xuất metric qua cổng `:9108/metrics` (`ai_anomaly_likelihood_percent`, `ai_reconstruction_error`, `ai_rca_component_latency_ms`) kèm đầy đủ 6 nhãn: `k8s_cluster_name`, `cloud_provider`, `service_name`, `entity_type`, `model`, `anomaly_score`.
4. Khi phát hiện bất thường (`ALERT`): Phân rã vết thực thi qua Tempo thành $T_{\text{WAN}}$, $T_{\text{self}}$, $T_{\text{DB}}$ và bắn tin cảnh báo Markdown giàu ngữ cảnh về Telegram Bot.
5. Khi hệ thống hồi phục về `HEALTHY`: Tự động reset cooldown bộ đệm để sẵn sàng nhận diện đợt tiêm lỗi tiếp theo.

---

### 5.3. Tiêm lỗi hỗn loạn thực tế (Live Chaos Engineering)
Hệ thống hỗ trợ các kịch bản tiêm lỗi chuẩn hóa (hoàn toàn nhắm vào 3 cụm thực tế `hub-k3d`, `aws-k3d`, `azure-k3d`):

```bash
# Kịch bản 1: Tiêm suy hao độ trễ mạng WAN xuyên đám mây AWS -> Azure (180ms delay)
python3 tests/chaos/run_live.py --scenarios azure_wan_delay

# Kịch bản 2: Tiêm rò rỉ bộ nhớ Heap JVM và ép GC trong pod TeaStore Persistence
python3 tests/chaos/run_service_faults.py --scenarios memory_leak

# Kịch bản 3: Tiêm nghẽn khóa bảng CSDL MySQL (Database Lock)
python3 tests/chaos/run_service_faults.py --scenarios db_lock

# Kịch bản 4: Tiêm lỗi HTTP 5xx giả lập
python3 tests/chaos/run_service_faults.py --scenarios http_5xx

# Kịch bản 5: Tiêm tải CPU đột biến (CPU Spike)
python3 tests/chaos/run_service_faults.py --scenarios cpu
```

---

## 6. Dọn Dẹp, Hoàn Nguyên & Gỡ Bỏ Hệ Thống (Teardown & Cleanup)

Khi cần reset hoặc giải phóng tài nguyên CPU/RAM trên máy trạm:

1. **Hoàn nguyên mạng WAN mô phỏng về tốc độ chuẩn (`make reset-wan`):**
   Nếu chỉ muốn gỡ bỏ netem delay để mạng trở về tốc độ bình thường mà không xóa cụm:
   ```bash
   make reset-wan
   ```

2. **Gỡ bỏ toàn bộ cụm và tài nguyên (`make teardown`):**
   Xóa an toàn 3 cụm k3d, mạng Docker bridge, volumes và chứng chỉ x509 tạm (vẫn giữ nguyên cache Docker images đã tải về):
   ```bash
   make teardown
   ```

3. **Dọn dẹp triệt để toàn bộ (`make purge-all`):**
   Xóa toàn bộ cụm, tài nguyên k8s và xóa sạch toàn bộ container images của dự án khỏi máy host:
   ```bash
   make purge-all
   ```

4. **Dọn dẹp riêng container images (`make clean-images`):**
   ```bash
   make clean-images
   ```
