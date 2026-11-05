# Hạ Tầng Giám Sát Đa Đám Mây — Phiên Bản Công Nghệ (Infrastructure Tech Stack Version Matrix)

> **Tài liệu:** `infra/README.md`  
> **Nguyên tắc bất biến:** **Tuyệt đối không sử dụng nhãn `latest`** trong bất kỳ manifest, cấu hình Dockerfile, container image hay playbook nào. Toàn bộ phiên bản phải được ghim cứng (**version pinning**) để đảm bảo tính tái lập (reproducibility), ổn định và dễ bảo trì lâu dài.

---

## 1. Bảng Danh Mục Phiên Bản Chi Tiết (Version Pinning Matrix)

| Lớp kiến trúc (Layer) | Thành phần công nghệ (Component) | Phiên bản ghim cứng (Pinned Version) | Docker Image / Package Identifier | Mục đích & Ghi chú |
|---|---|---|---|---|
| **Host Operating System** | Linux Ubuntu | `26.04` (Noble/Future LTS) | Host OS Platform | Hệ điều hành máy trạm thực thi |
| **Host Runtime** | Docker Engine | `29.8.2` | Docker Engine Community 29.8.2 | Container runtime trên máy trạm |
| **Desktop Suite** | Docker Desktop | `v4.95.0` | Docker Desktop v4.95.0 | Bộ công cụ giao diện & VM Docker |
| **Cluster Engine** | k3s (Kubernetes) | `v1.31.2+k3s1` | `rancher/k3s:v1.31.2-k3s1` | Kubernetes siêu nhẹ chạy trên k3d (đồng bộ từ sample) |
| **Cluster CLI** | k3d | `v5.6.0` | `k3d version v5.6.0` | Công cụ quản lý k3s trong Docker |
| **IaC Automation** | Ansible Core | `2.15.8` | `ansible-core==2.15.8` | Tự động hóa cài đặt & cấu hình k3d |
| **Declarative Config** | Kustomize | `v5.3.0` | `registry.k8s.io/kustomize/kustomize:v5.3.0` | Quản lý manifests base & overlays |
| **Telemetry Agent** | OTel Java Agent | `v2.10.0` | `ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.10.0` | Auto-instrumentation Java cho TeaStore |
| **Telemetry Edge** | OTel Collector Contrib (Spoke) | `0.114.0` | `otel/opentelemetry-collector-contrib:0.114.0` | Collector tại biên lọc & sampling 20% |
| **Telemetry Hub** | OTel Collector Contrib (Hub) | `0.114.0` | `otel/opentelemetry-collector-contrib:0.114.0` | Gateway chuẩn hóa UTC, Cloud Semconv & ServiceGraph |
| **Network & Ingress** | Traefik | `v2.11.0` | `traefik:v2.11.0` | Ingress Controller hỗ trợ mTLS 1.3 |
| **Metrics Collector** | Prometheus | `v2.50.0` | `prom/prometheus:v2.50.0` | Local scraping & Remote Write engine |
| **Metrics Long-Term** | Thanos | `v0.36.1` | `quay.io/thanos/thanos:v0.36.1` | Receive, Query, Store, Compact, Ruler |
| **Logs Backend** | Grafana Loki | `v2.9.4` | `grafana/loki:2.9.4` | Chunk-based Log TSDB không index full-text |
| **Traces Backend** | Grafana Tempo | `v2.4.0` | `grafana/tempo:2.4.0` | Parquet block Trace TSDB & TraceQL |
| **Object Storage** | MinIO Server | `RELEASE.2025-10-15T17-29-55Z` | `minio/minio:RELEASE.2025-10-15T17-29-55Z` | S3-compatible storage (bản mới nhất được hỗ trợ) |
| **Object Storage CLI** | MinIO Client (`mc`) | `RELEASE.2025-10-15T17-29-55Z` | `minio/mc:RELEASE.2025-10-15T17-29-55Z` | Khởi tạo 3 buckets tự động qua Job |
| **Visualization** | Grafana | `11.5.0` | `grafana/grafana:11.5.0` | UI hiển thị dashboards tập trung |
| **SLO Management** | Pyrra | `v0.7.3` | `ghcr.io/pyrra-dev/pyrra:v0.7.3` | Quản lý SLO Multi-Burn-Rate |
| **Alert Automation** | Robusta Runner | `0.53.0` | `robustadev/robusta-runner:0.53.0` | Khảo sát ngữ cảnh pod lỗi tự động |
| **Alert Forwarder** | Robusta Forwarder | `0.53.0` | `robustadev/robusta-forwarder:0.53.0` | Lắng nghe sự kiện K8s API Server |
| **Benchmark App** | TeaStore WebUI/Services | `1.4.1` | `descartesresearch/teastore-webui:1.4.1` | Pinned tag chính thức (loại bỏ :latest từ sample) |
| **Database** | MySQL Server | `8.0.36` | `mysql:8.0.36` | Cơ sở dữ liệu quan hệ cho Persistence |
| **Load Testing** | Locust | `2.24.0` | `locustio/locust:2.24.0` | Bộ sinh tải phân tán kịch bản Python |
| **Network Emulation** | Linux iproute2 (`tc`) | `6.1.0` | `iproute2=6.1.0-1` | Tiêm suy hao mạng WAN trễ & mất gói |
| **Security / PKI** | OpenSSL | `4.0.3` | `openssl=4.0.3` | Sinh Root CA và chứng chỉ x509 SAN |

---

## 2. Quy Định Quản Lý Phiên Bản (Version Governance Policy)

1. **Cấm Sử Dụng Tag Trôi Nổi (No Floating Tags):**
   - Nghiêm cấm đặt `image: <name>:latest` hoặc `image: <name>:stable` trong bất kỳ file YAML nào.
   - Luôn sử dụng thẻ phiên bản cụ thể (ví dụ: `image: grafana/tempo:2.4.0`).
2. **Quy Trình Nâng Cấp Phiên Bản (Upgrade Workflow):**
   - Khi cần nâng cấp bất kỳ thành phần nào (ví dụ OTel Collector từ `0.96.0` lên `0.98.0`), bắt buộc phải:
     1. Cập nhật bảng kê trong tệp này (`infra/README.md`).
     2. Ghi rõ lý do nâng cấp và tác động tương thích vào hồ sơ quyết định kiến trúc (`docs/decisions/`).
     3. Kiểm tra tính tương thích của API và Schema OTel Semantic Conventions trước khi triển khai thực tế.
3. **Mã Nguồn Mở & Khả Năng Tái Lập (Reproducibility):**
   - Mọi thực nghiệm benchmark tại `experiments/` đều lưu kèm mã hash digest của từng Docker image để đảm bảo kết quả đo đạc khoa học có thể tái hiện chính xác 100% trong tương lai.

---

## 3. Kế Hoạch Kịch Bản Dọn Dẹp Nhanh Hạ Tầng (Quick Teardown / Cleanup Workflow)

Để phục vụ việc gỡ nhanh toàn bộ cụm k3d và tài nguyên mạng Docker khi muốn dọn dẹp hoặc cài đặt lại từ đầu mà không để lại rác tiến trình, playbook dọn dẹp `00_cleanup_all.yml` (hoặc `teardown.yml`) trong `infra/ansible/playbooks/` được thiết kế thực hiện tuần tự các tác vụ:
1. **Xóa tất cả các cụm k3d:** Thực thi `k3d cluster delete --all` một cách an toàn (graceful termination).
2. **Cưỡng chế xóa container k3d còn sót:** Quét và xóa các container `k3d-*` nếu daemon chưa dừng kịp.
3. **Xóa mạng Docker bridge:** Gỡ bỏ mạng `mc-monitoring-net` (hoặc `multi-cloud-wan`).
4. **Dọn dẹp Docker Volumes:** Thực thi `docker volume prune -f` để giải phóng dung lượng đĩa của MinIO và MySQL.
5. **Dọn dẹp thư mục chứng chỉ mTLS tạm thời:** Thu hồi và xóa các certs/keys sinh trong phiên làm việc.
*(Kịch bản này đã được thiết kế sẵn và sẽ được đưa vào thực thi ở bước triển khai).*

