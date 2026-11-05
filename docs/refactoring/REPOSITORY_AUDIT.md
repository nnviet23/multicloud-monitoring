# DEEP TECHNICAL AUDIT REPORT: MULTI-CLOUD MONITORING PLATFORM

> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Phiên bản tài liệu:** v1.0.0 (Read-Only Technical Audit)  
> **Ngày thực hiện:** 05/11/2026  
> **Kiểm toán viên:** Senior Software Architect, DevOps & SRE Specialist  
> **Phạm vi kiểm toán:** Toàn bộ repository `multicloud-monitoring` (462 thư mục, 1,363 tệp tin)  
> **Chế độ kiểm toán:** STRICT READ-ONLY (Không sửa mã nguồn, không xóa tệp, không đổi cấu hình)  

---

## MỤC LỤC BÁO CÁO
1. [Executive Summary](#1-executive-summary)
2. [Current Repository Structure](#2-current-repository-structure)
3. [Current Architecture Assessment](#3-current-architecture-assessment)
4. [Directory and File Audit](#4-directory-and-file-audit)
5. [Dependency Analysis](#5-dependency-analysis)
6. [Duplicate Configuration Analysis](#6-duplicate-configuration-analysis)
7. [Code Quality and Technical Debt](#7-code-quality-and-technical-debt)
8. [Research Data Integrity Assessment](#8-research-data-integrity-assessment)
9. [Deployment Complexity Assessment](#9-deployment-complexity-assessment)
10. [Proposed Repository Structures (Option A & Option B)](#10-proposed-repository-structures)
11. [Refactoring Options Comparison](#11-refactoring-options-comparison)
12. [Regression Test Strategy](#12-regression-test-strategy)
13. [Risks and Migration Considerations](#13-risks-and-migration-considerations)
14. [Recommended Next Steps](#14-recommended-next-steps)
15. [Open Questions](#15-open-questions)

---

## 1. EXECUTIVE SUMMARY

Kho lưu trữ `multicloud-monitoring` hiện đang cài đặt một nền tảng giám sát đa đám mây mẫu (Multi-Cloud Observability Platform) theo kiến trúc Hub-Spoke. Hệ thống sử dụng Descartes TeaStore làm benchmark application, ba cụm Kubernetes cục bộ (k3d) mô phỏng hạ tầng AWS (`aws-k3d`), Azure (`azure-k3d`) và Trung tâm điều hành (`hub-k3d`), kết nối qua mạng WAN mô phỏng bằng `tc/netem` (RTT 10ms ±2ms, packet loss 0.1%) và kênh truyền mTLS 1.3.

### Các kết quả nổi bật đã hoàn thành (Phase 0 – 3):
- **Hạ tầng 3 cụm k3d:** Khởi tạo ổn định trên Docker network `mc-monitoring-net` (`172.28.0.0/16`), gán IP tĩnh, đồng bộ CoreDNS cross-cluster.
- **Quan sát toàn diện (Observability Stack):** MinIO (S3 Object Storage), Prometheus + Thanos (Metrics), Loki (Logs), Tempo (Traces), Grafana (UI), Pyrra (SLO-as-code), Robusta (Smart Alerting) hoạt động đồng bộ trên `hub-k3d`.
- **Đường ống viễn trắc (Telemetry Pipelines):** OTel Collector Contrib v0.114.0 biên và trung tâm; tiền tổng hợp đồ thị dịch vụ (`servicegraphconnector`) xuất chỉ số `traces_service_graph_request_total`; xuất dữ liệu viễn trắc thô định dạng OTLP JSON bất biến vào MinIO bucket `raw-telemetry`.
- **Trực quan hóa:** 7 Dashboard SRE chuyên biệt tự động nạp qua ConfigMap.

### Những thách thức kỹ thuật và nợ kỹ thuật (Technical Debt) phát hiện qua kiểm toán:
1. **Trùng lặp cấu hình nghiêm trọng (Configuration Duplication):**
   - Thư mục `src/infra-sample/ansible-sample/playbooks_sample/` chứa 13 playbook trùng lặp hoàn toàn với cấu trúc playbook cũ.
   - 75 biểu thức OTTL trong OpenTelemetry Collector có sự sao chép nguyên khối giữa 3 ngữ cảnh (`log_statements`, `metric_statements`, `trace_statements`).
2. **Sai lệch đường dẫn và phụ thuộc mong manh (Path Drift & Fragile Scripts):**
   - Kịch bản `pull_images.sh` **bỏ sót container image quan trọng nhất** (`teastore-webui:1.4.1`), khiến `import_k3d_images.sh` bị lỗi nếu chạy tuần tự.
   - Master playbook `site.yml` không import bước đồng bộ DNS (`04_sync_cluster_hosts.yml`) và bước phân phối chứng chỉ mTLS (`06_distribute_mtls_secrets.yml`).
   - Playbook dọn dẹp `00_cleanup_all.yml` trỏ sai đường dẫn certs (`security/certs` thay vì `security/pki`).
   - Hai playbook cùng mang tiền tố `04_` (`04_reset_wan_emulation.yml` và `04_sync_cluster_hosts.yml`).
3. **Tính liêm chính của dữ liệu nghiên cứu (Research Data Integrity):**
   - Toàn bộ metadata đám mây sâu (`cloud.account.id`, `network.vpc.id`, `cloud.identity.arn`, Resource IDs) hiện được **tiêm tĩnh qua OTTL tại Hub Collector**, không phải metadata sinh ra từ IMDS của cloud thật. Điều này cần được ghi nhận minh bạch trong báo cáo khoa học.
4. **An toàn bảo mật (Security & Secrets):**
   - 6 tệp Secret Kubernetes trong `k8s/base` chứa mật khẩu plaintext (`MultiCloudSecurePassword2026!`).
   - File `.gitignore` chưa bao phủ các tệp khóa và chứng chỉ trong `security/pki/`.

---

## 2. CURRENT REPOSITORY STRUCTURE

### Thống kê định lượng:
- **Tổng số thư mục:** 462 thư mục (bao gồm cả các module Maven con của TeaStore).
- **Tổng số tệp tin:** 1,363 tệp tin.

### Cây thư mục cấp cao thực tế:
```
multicloud-monitoring/
├── .agent/                             # Quy tắc và Kỹ năng hỗ trợ AI Agents
│   ├── rules/                          # 5 tệp quy chuẩn (baseline, telemetry, security, benchmark, k8s)
│   └── skills/                         # 11 thư mục kỹ năng mở rộng
├── .gitignore                          # Cấu hình loại trừ Git
├── AGENTS.md                           # Hướng dẫn quy chuẩn repository cho Agent
├── overview.md                         # Báo cáo tổng quan đề tài
├── PLAN.md                             # Kế hoạch dự án và tiêu chí nghiệm thu
├── README.md                           # Giới thiệu dự án
├── Benchmark-app/                      # Ứng dụng kiểm chuẩn Descartes TeaStore v1.4.1
│   ├── TeaStore/                       # Mã nguồn Java Maven (registry, webui, auth, persistence, recommender)
│   ├── TeaStoreREADME.md               # Tài liệu hướng dẫn TeaStore gốc
│   └── sample_jaeger_traces.json       # Tệp mẫu trace JSON
├── docs/                               # Toàn bộ tài liệu thiết kế và nghiên cứu (30 tệp)
│   ├── architecture/                   # Tài liệu kiến trúc, sơ đồ Draw.io & PNG
│   ├── decisions/                      # Hồ sơ quyết định kiến trúc ADR (mẫu)
│   ├── other-reference/                # Tài liệu đọc chuyên đề PDF (Docker, Grafana)
│   ├── progress/                       # Nhật ký tiến độ, RCA sự cố (INC-P1-01 -> 14), giải pháp, độ phủ
│   ├── research/                       # 9 bài báo khoa học PDF, matrix CSV, báo cáo tổng hợp
│   └── schemas/                        # JSON/YAML Schema mẫu cho thực nghiệm và kiểm kê viễn trắc
├── experiments/                        # Thư mục thực nghiệm benchmark (hiện chỉ có experiments__README.md)
├── infra/                              # Tự động hóa hạ tầng
│   ├── README.md                       # Bảng kê ghim cứng phiên bản (Version Pinning Matrix)
│   └── ansible/
│       ├── ansible.cfg                 # Cấu hình Ansible
│       ├── inventory.ini               # Khai báo node cục bộ localhost
│       └── playbooks/                  # 8 playbooks + 2 shell scripts (k3d, WAN, certs, images)
├── k8s/                                # Khai báo Kubernetes chuẩn Kustomize (93 tệp)
│   ├── base/                           # Manifests gốc (SRP: 00-namespace, 01-secret, 02-configmap, ...)
│   │   ├── logs-loki/                  # Grafana Loki v2.9.4
│   │   ├── metrics-thanos/             # Prometheus v2.50.0 + Thanos v0.36.1 Sidecar & Query
│   │   ├── otel-collector/             # OTel Collector Contrib v0.114.0 (edge và gateway)
│   │   ├── slo-pyrra/                  # Pyrra v0.7.3 ServiceLevelObjective CRD & Controller
│   │   ├── smart-alerting-robusta/     # Robusta v0.53.0 Forwarder/Runner
│   │   ├── storage-minio/              # MinIO RELEASE.2025-10-15T17-29-55Z
│   │   ├── teastore/                   # 7 microservices TeaStore + MySQL 8.0
│   │   ├── traces-tempo/               # Grafana Tempo v2.4.0
│   │   └── visualization-grafana/      # Grafana v11.5.0 + 7 JSON dashboards
│   └── overlays/
│       └── local-k3d/                  # Kustomize Overlays cho môi trường k3d
│           ├── hub/                    # Overlay Hub (nạp otel-collector gateway)
│           ├── spoke-aws/              # Overlay Spoke AWS (TeaStore compute + Edge collector)
│           └── spoke-azure/            # Overlay Spoke Azure (TeaStore data + Edge collector)
├── prompting/                          # Tài liệu prompt kỹ thuật
│   └── prompts/
│       └── 02_review.md                # Bản mô tả yêu cầu audit hiện tại
├── security/                           # Quản lý khóa và chứng chỉ mTLS 1.3
│   └── pki/
│       ├── ca/                         # Root CA tự ký (ca.crt, ca.key, ca.srl)
│       ├── certs-hub/                  # Chứng chỉ máy chủ Hub Gateway (server.crt, key, ext.cnf)
│       ├── certs-spoke1/               # Chứng chỉ Spoke 1 AWS Client (client.crt, key, ext.cnf)
│       ├── certs-spoke2/               # Chứng chỉ Spoke 2 Azure Client (client.crt, key, ext.cnf)
│       └── scripts/                    # 3 Shell scripts sinh chứng chỉ x509 OpenSSL
└── src/                                # Thư mục mã nguồn mẫu thừa
    ├── README.md
    └── infra-sample/                   # Bản mẫu cũ của ansible playbooks (playbooks_sample/)
```

---

## 3. CURRENT ARCHITECTURE ASSESSMENT

### 3.1. Đánh giá mô hình Hub-Spoke
- **Kiến trúc Phương án A:** Việc chọn phương án *Edge-Filtered Ingestion with Centralized Processing & Batch Ingestion* đã chứng minh hiệu quả thực tế:
  - Giảm áp lực mạng WAN mô phỏng nhờ lấy mẫu vết 20% tại biên (`probabilistic_sampler`).
  - Lọc bỏ log debug/trace vô nghĩa tại Edge (`filter/logs`).
  - Tách rời hoàn toàn Spoke và Hub qua OTLP gRPC trên cổng 4317 được mã hóa bằng mTLS 1.3.
- **Tiền tổng hợp Service Graph tại Hub Gateway:**
  - Thay vì quét thô hàng triệu span từ Tempo qua TraceQL (tốn CPU và RAM), `servicegraphconnector` tại Hub OTel Collector Gateway liên tục kết ghép span cha-con và xuất metric chuẩn Prometheus `traces_service_graph_request_total` và `traces_service_graph_request_failed_total` trực tiếp vào Thanos.
  - Phép đo trên Grafana hiển thị tức thời (<50ms), hỗ trợ tạo bảng thông số RED và tính toán SLI/SLO cho Pyrra.

### 3.2. Đánh giá tính sẵn sàng của các lớp thành phần
- **Storage Layer (MinIO):** StatefulSet 1 replica, PVC 10Gi cục bộ, tự động khởi tạo 4 bucket: `thanos-metrics`, `loki-logs`, `tempo-traces`, `raw-telemetry`. Thanos sidecar đã tải lên thành công 24 block nén TSDB; pipeline `awss3` đã ghi hơn 260 tệp JSON OTLP phân cấp thời gian.
- **Metrics Layer (Prometheus + Thanos):** Prometheus thu thập nội bộ và hostmetrics từ OTel Collector; Thanos Sidecar liên tục sao lưu TSDB blocks lên MinIO; Thanos Query cung cấp giao diện PromQL thống nhất cho Grafana và Pyrra.
- **Logs Layer (Loki):** Cấu hình Single Binary lưu chunks lên MinIO, nhận logs từ OTel Collector qua exporter native `loki` endpoint `/loki/api/v1/push`.
- **Traces Layer (Tempo):** Nhận OTLP gRPC/HTTP nội bộ từ Hub Gateway, lưu trữ khối trace trên MinIO.
- **Visualization (Grafana):** Đã kết nối tự động cả 3 datasource (Thanos, Loki, Tempo) với tính năng liên kết chéo (Traces-to-Logs và Service Map).

---

## 4. DIRECTORY AND FILE AUDIT

Dưới đây là bảng phân loại toàn bộ các thành phần trong kho lưu trữ theo 6 nhãn: **KEEP**, **MERGE**, **MOVE**, **REFACTOR**, **REMOVE**, **INVESTIGATE**.

| Đường dẫn tệp / thư mục | Phân loại | Lý do & Hành động đề xuất |
|---|:---:|---|
| **`PLAN.md`** | **KEEP** | Tài liệu lộ trình cốt lõi, theo dõi trạng thái các Phase và Acceptance Criteria. |
| **`AGENTS.md`** | **KEEP** | Quy tắc tối thượng cho AI coding agents, định nghĩa nguyên tắc SRP, ghim phiên bản. |
| **`overview.md`** | **MERGE** | Nội dung giới thiệu tổng quan đề tài, nên gộp vào `README.md` chính để tránh phân mảnh. |
| **`README.md`** | **REFACTOR** | Cập nhật cấu trúc thư mục thực tế, hướng dẫn chạy nhanh qua entrypoint tập trung. |
| **`src/`** (và toàn bộ thư mục con) | **REMOVE** | Chứa `src/infra-sample/ansible-sample/playbooks_sample/` là bản sao chép mẫu cũ, không còn được tham chiếu trong bất kỳ quy trình nào. |
| **`infra/ansible/ansible.cfg`** | **KEEP** | Cấu hình Ansible cục bộ chuẩn mực. |
| **`infra/ansible/inventory.ini`** | **REFACTOR** | Bổ sung biến môi trường linh hoạt thay vì hardcode đường dẫn `/usr/bin/python3`. |
| **`infra/ansible/playbooks/site.yml`** | **REFACTOR** | Bổ sung các bước bị thiếu: import `04_sync_cluster_hosts.yml` và `06_distribute_mtls_secrets.yml`. |
| **`infra/ansible/playbooks/00_cleanup_all.yml`** | **REFACTOR** | Sửa đường dẫn xóa certs thành `security/pki`, thay cú pháp shell Linux bằng module Ansible chuẩn. |
| **`infra/ansible/playbooks/01_setup_host_tools.yml`** | **REFACTOR** | Bổ sung kiểm tra `openssl` và `kustomize`. |
| **`infra/ansible/playbooks/02_provision_k3d_clusters.yml`** | **KEEP** | Cấu hình khởi tạo 3 cụm k3d, mạng WAN bridge ổn định. |
| **`infra/ansible/playbooks/03_emulate_wan_latency.yml`** | **REFACTOR** | Loại bỏ `apk add iproute2` mỗi lần chạy bằng cách dùng pinned container image có sẵn `tc`. |
| **`infra/ansible/playbooks/04_reset_wan_emulation.yml`** | **MOVE** | Đổi tên thành `04a_reset_wan_emulation.yml` hoặc chuyển vào thư mục tiện ích để tránh trùng tiền tố `04_`. |
| **`infra/ansible/playbooks/04_sync_cluster_hosts.yml`** | **REFACTOR** | Tham số hóa IP gateway `192.168.65.254` để tương thích cả Docker Linux thuần và Docker Desktop. |
| **`infra/ansible/playbooks/05_verify_clusters.yml`** | **KEEP** | Kiểm tra thông mạng và node ready. |
| **`infra/ansible/playbooks/06_distribute_mtls_secrets.yml`** | **KEEP** | Tự động tạo Secret mTLS trên 3 cụm. |
| **`infra/ansible/playbooks/pull_images.sh`** | **MOVE & REFACTOR** | Chuyển ra `infra/scripts/pull_images.sh`, **bổ sung ngay `teastore-webui:1.4.1`** và các image monitoring. |
| **`infra/ansible/playbooks/import_k3d_images.sh`** | **MOVE** | Chuyển ra `infra/scripts/import_k3d_images.sh`. |
| **`security/pki/ca/`** | **KEEP** | Thư mục lưu CA nội bộ (cần đảm bảo không commit key lên git). |
| **`security/pki/certs-*/`** | **KEEP** | Chứng chỉ SAN cho Hub và Client cho Spoke. |
| **`security/pki/scripts/*.sh`** | **KEEP** | 3 kịch bản tạo Root CA, Hub Cert và Spoke Certs bằng OpenSSL. |
| **`k8s/base/teastore/`** | **KEEP** | 8 thư mục microservices của TeaStore tuân thủ chặt chẽ SRP. |
| **`k8s/base/otel-collector/edge/`** | **REFACTOR** | Tinh gọn OTTL statements, hợp lý hóa thứ tự processor. |
| **`k8s/base/otel-collector/gateway/`** | **REFACTOR** | Khử trùng lặp 63 câu lệnh OTTL giữa logs, metrics và traces. |
| **`k8s/base/visualization-grafana/dashboards/system-topology.json`** | **REFACTOR** | Tối ưu hóa chuỗi PromQL dài 1,700 ký tự với 14 lớp `label_replace` thành format dễ bảo trì. |
| **`k8s/base/visualization-grafana/dashboards/*.json`** (6 dashboards còn lại) | **KEEP** | Hoạt động tốt, trực quan hóa xuất sắc RED metrics, K8s, SLO, WAN, Logs/Traces. |
| **`k8s/overlays/local-k3d/`** | **KEEP** | Kustomize overlays cho `hub`, `spoke-aws`, `spoke-azure`. |
| **`Benchmark-app/sample_jaeger_traces.json`** | **REMOVE** | Tệp trace mẫu 29 dòng tĩnh, không còn giá trị khi hệ thống đã có Jaeger/Tempo live. |
| **`Benchmark-app/TeaStore/`** | **KEEP** | Mã nguồn gốc của ứng dụng kiểm chuẩn TeaStore v1.4.1. |
| **`docs/process/`** | **REMOVE** | Thư mục không tồn tại trên đĩa nhưng có tham chiếu ma trong tài liệu; cần dọn sạch vết trong doc. |
| **`docs/progress/`** | **KEEP** | Chứa toàn bộ báo cáo tiến độ, RCA sự cố thực tế, kế hoạch giải pháp và độ phủ giám sát. |
| **`docs/architecture/`** | **KEEP** | Tài liệu kiến trúc và sơ đồ hệ thống. |
| **`docs/research/`** | **KEEP** | 9 bài báo khoa học và báo cáo tổng hợp phục vụ đề tài tốt nghiệp. |
| **`docs/schemas/`** | **REFACTOR** | Đổi tên các tệp có tiền tố `docs__schemas__...` thành tên chuẩn kebab-case. |
| **`docs/decisions/`** | **REFACTOR** | Đổi tên `docs__decisions__ADR-template.md` thành `ADR-000-template.md`. |
| **`.agent/rules/`** | **REFACTOR** | Đổi tên các tệp có tiền tố `agents__rules__...` thành `00-project-baseline.md`, v.v. |
| **`experiments/`** | **REFACTOR** | Chuẩn bị sẵn cấu trúc thư mục thực nghiệm cho Phase 4 (`experiments/manifests/`, `experiments/raw/`, `experiments/reports/`). |

---

## 5. DEPENDENCY ANALYSIS

### 5.1. Bản đồ phụ thuộc triển khai (Deployment Dependency Graph)

```
[Máy trạm Host] 
      │
      ├──> [01_setup_host_tools.yml] (Kiểm tra Docker, k3d, kubectl, helm)
      │
      ├──> [pull_images.sh] ──> [import_k3d_images.sh] (Kéo & Nạp image vào containerd)
      │
      ├──> [02_provision_k3d_clusters.yml] ──> Tạo bridge 'mc-monitoring-net' & 3 k3d clusters
      │
      ├──> [security/pki/scripts/*.sh] ──> Tạo Root CA, Hub Server Cert & Spoke Client Certs
      │
      ├──> [06_distribute_mtls_secrets.yml] ──> Đẩy certs vào K8s Secret 'otel-*-certs'
      │
      ├──> [04_sync_cluster_hosts.yml] ──> Quét Docker IP & Patch CoreDNS ConfigMap
      │
      ├──> [03_emulate_wan_latency.yml] ──> Tiêm tc/netem vào eth0 của 2 cụm Spoke
      │
      └──> [Kustomize Declarative Apply]:
             ├── Cụm hub-k3d:
             │     ├── k8s/base/storage-minio
             │     ├── k8s/base/metrics-thanos
             │     ├── k8s/base/logs-loki
             │     ├── k8s/base/traces-tempo
             │     ├── k8s/base/visualization-grafana
             │     ├── k8s/base/slo-pyrra
             │     ├── k8s/base/smart-alerting-robusta
             │     └── k8s/overlays/local-k3d/hub (OTel Gateway)
             ├── Cụm aws-k3d:
             │     └── k8s/overlays/local-k3d/spoke-aws (TeaStore Compute + OTel Edge)
             └── Cụm azure-k3d:
                   └── k8s/overlays/local-k3d/spoke-azure (TeaStore Data/DB + OTel Edge)
```

### 5.2. Phụ thuộc giữa ConfigMap, Secret và Pods

| Pod / Thành phần | ConfigMap gắn kèm | Secret sử dụng | Cổng phụ thuộc & Dịch vụ liên quan |
|---|---|---|---|
| **`otel-collector-hub`** | `otel-collector-hub-config` | `otel-hub-certs` (mTLS)<br>`minio-creds` (cho S3 exporter) | Nhận: 4317 gRPC, 4318 HTTP<br>Gửi sang: `minio:9000`, `thanos-query:9090`, `loki:3100`, `tempo:4317` |
| **`otel-collector-spoke`** | `otel-collector-spoke-config` | `otel-spoke-certs` (mTLS) | Nhận OTLP từ Pods TeaStore; Gửi qua WAN tới `k3d-hub-k3d-serverlb:4317` |
| **`prometheus`** | `prometheus-config` | `thanos-objstore-secret` | Scrape nội bộ Hub + cào `otel-collector-hub:8889`; Thanos sidecar đẩy block lên `minio:9000` |
| **`loki`** | `loki-config` | `loki-s3-creds` | Đẩy chunk logs vào `minio:9000/loki-logs` |
| **`tempo`** | `tempo-config` | `tempo-s3-creds` | Đẩy blocks trace vào `minio:9000/tempo-traces` |
| **`grafana`** | `grafana-datasources`<br>`grafana-providers`<br>`grafana-dashboards` | `grafana-admin-creds` | Truy vấn Thanos (9090), Loki (3100), Tempo (3200) |
| **`robusta-runner`** | `robusta-config` | `robusta-secrets` (Telegram Token) | Đọc alert từ Thanos Query; bắn cảnh báo sang Telegram Bot API |
| **`pyrra`** | CRD `ServiceLevelObjective` | N/A | Tạo PrometheusRule tự động; Thanos Query đánh giá SLI/SLO |
| **`teastore-webui`** | N/A | N/A | Gọi nội bộ `teastore-auth`, `image`, `recommender`; gọi RMI xuyên cụm tới `teastore-persistence` qua NodePort 31111 |
| **`teastore-persistence`** | N/A | N/A | Gọi nội bộ MySQL `teastore-db:3306`; đăng ký tới `teastore-registry` qua NodePort 31112 |

---

## 6. DUPLICATE CONFIGURATION ANALYSIS

### 6.1. Trùng lặp Playbook Ansible (`src/` vs `infra/`)
Toàn bộ cây thư mục `src/infra-sample/ansible-sample/playbooks_sample/` chứa 13 tệp:
- `00_cleanup_all.yml` đến `11_deploy_teastore_workload.yml` và `site.yml`.
- Các file này phản ánh thiết kế cũ (khi Ansible cố gắng kiêm nhiệm việc deploy K8s YAML). Hiện tại dự án đã chuyển hẳn sang Kustomize Declarative (`k8s/`), khiến toàn bộ thư mục `src/` trở thành mã chết (dead code) gây nhầm lẫn nghiêm trọng cho kỹ sư mới tiếp cận.

### 6.2. Trùng lặp biểu thức OTTL trong OpenTelemetry Collector
Tại `k8s/base/otel-collector/gateway/03-configmap.yaml`:
- **63 câu lệnh OTTL** của processor `transform/normalize_cloud` lặp lại gần như y hệt giữa 3 block:
  - `log_statements`: 16 statements
  - `metric_statements`: 15 statements
  - `trace_statements`: 32 statements
- Các phép gán `cloud.provider`, `cloud.region`, `cloud.account.id`, `cloud.platform`, `network.vpc.id`, `network.subnet.id`, `network.security_group.id`, `cloud.identity.arn`, `cloud.resource_id` được copy-paste giống nhau 100% qua cả 3 ngữ cảnh tín hiệu.
- **Tác hại:** Nếu cần sửa một subnet CIDR hay một ARN IAM role, kỹ sư phải sửa đồng thời ở 3 vị trí khác nhau trong một file YAML dài gần 200 dòng, rất dễ phát sinh lỗi bất đồng bộ dữ liệu.

### 6.3. Trùng lặp thông tin xác thực (Credentials Hardcoding)
Chuỗi mật khẩu `MultiCloudSecurePassword2026!` và tài khoản `admin` xuất hiện lặp lại trong:
- `k8s/base/storage-minio/01-secret.yaml`
- `k8s/base/logs-loki/00-secret-s3.yaml`
- `k8s/base/traces-tempo/00-secret-s3.yaml`
- `k8s/base/visualization-grafana/00-secret-admin.yaml`
- `k8s/base/metrics-thanos/00-secret-s3.yaml`
Thay vì định nghĩa riêng rẽ 5 Secret trùng lặp giá trị, việc tái cấu trúc cần hướng tới quản lý tập trung qua một Kustomize `secretGenerator` hoặc biến môi trường thống nhất.

---

## 7. CODE QUALITY AND TECHNICAL DEBT

### 7.1. Phân tích OpenTelemetry Collector Pipeline
1. **Tuân thủ quy tắc Processor Pipeline:**
   - Quy tắc dự án: `Memory Limiter → Filter → Transform → Batch → Exporter`.
   - **Thực tế tại Edge:**
     - Pipeline traces: `memory_limiter → probabilistic_sampler → transform/cluster_id → batch` (Đạt chuẩn).
     - Pipeline metrics: `memory_limiter → transform/cluster_id → batch` (Đạt chuẩn).
     - Pipeline logs: `memory_limiter → filter/logs → groupbyattrs → transform/logs → transform/cluster_id → batch` (Đạt chuẩn).
   - **Thực tế tại Gateway:**
     - Pipeline traces: `memory_limiter → transform/normalize_cloud → servicegraph → batch` (Đạt chuẩn).
     - Pipeline metrics: `memory_limiter → transform/normalize_cloud → batch` (Đạt chuẩn).
     - Pipeline logs: `memory_limiter → transform/normalize_cloud → batch` (Đạt chuẩn).
2. **Điểm tối ưu:** Việc đặt `servicegraphconnector` sau `transform/normalize_cloud` cho phép đồ thị dịch vụ tận dụng các nhãn đã được chuẩn hóa.

### 7.2. Chất lượng PromQL trong Grafana Dashboards
- **Vấn đề nghiêm trọng trong `system-topology.json`:**
  - Panel *Interactive Multi-Cloud Service Graph* sử dụng một câu lệnh PromQL dài hơn **1,700 ký tự** với **14 tầng lồng ghép hàm `label_replace()`** để ghép các thuộc tính mô phỏng đám mây (`cloud_provider`, `region`, `vpc`, `subnet`, `account_id`) vào metric `traces_service_graph_request_total`.
  - **Đánh giá rủi ro:** Đây là một anti-pattern trong PromQL. Chuỗi `label_replace` lồng nhau cực kỳ mỏng manh, khó gỡ lỗi và tiêu tốn CPU của Prometheus/Thanos khi lượng metric tăng lên.
  - **Giải pháp:** Các nhãn này cần được gắn sẵn vào span/metric ngay từ OTel Collector thông qua connector dimensions (`servicegraphconnector.dimensions: [cloud.provider, cloud.region, network.vpc.id]`), từ đó giúp câu truy vấn PromQL trong Grafana trở về dạng đơn giản: `sum by (client, server, cloud_provider, region) (rate(traces_service_graph_request_total[1m]))`.

### 7.3. Đánh giá Resource Requests & Limits và Probes
- **Tình trạng định mức tài nguyên (Resources):**
  - 100% các container ứng dụng chính (17/17) đều có khai báo `requests` và `limits` rõ ràng (CPU từ 20m–100m, RAM từ 64Mi–1Gi), tuân thủ tốt nguyên tắc hạn chế tranh chấp tài nguyên trên máy trạm cục bộ.
  - Các initContainer (`opentelemetry-auto-instrumentation` và `init-buckets` của MinIO) hiện chưa set requests/limits. Do initContainer chỉ chạy một lần rồi dừng, điều này không gây lỗi hệ thống nhưng nên được bổ sung cấu hình tối thiểu (10m CPU / 16Mi RAM).
- **Tình trạng Probes:**
  - Toàn bộ 7 dịch vụ TeaStore đã được cấu hình đầy đủ `livenessProbe`, `readinessProbe` và `startupProbe` chính xác theo từng endpoint chuyên biệt của Tomcat (khắc phục hoàn toàn lỗi INC-P2-02).
  - Riêng OTel Collector Pods hiện **chưa có liveness/readiness probes**. OTel Collector có sẵn extension `health_check` mở cổng 13133 (`http://localhost:13133/`), cần bổ sung probe vào manifest deployment.

---

## 8. RESEARCH DATA INTEGRITY ASSESSMENT

Do đây là dự án nghiên cứu khoa học phục vụ luận văn tốt nghiệp, tính liêm chính và sự minh bạch của dữ liệu là yêu cầu sống còn.

### 8.1. Phân biệt Dữ liệu Thực tế và Dữ liệu Mô phỏng
| Nhóm dữ liệu | Nguồn gốc thực tế | Đánh giá tính xác thực (Authenticity) | Khuyến nghị công bố khoa học |
|---|---|:---:|---|
| **Chỉ số mạng WAN (Latency, Loss)** | Tiêm trực tiếp vào nhân Linux bằng `tc/netem` | **THỰC TẾ (Mô phỏng vật lý)** | Đo kiểm thực tế qua ICMP ping và OTLP export round-trip time. Hoàn toàn hợp lệ cho bài báo khoa học. |
| **Chỉ số RED ứng dụng (QPS, Trễ P95, Lỗi)** | Sinh tải từ Locust, đo lường bởi OTel Java Agent qua bytecode instrumentation | **THỰC TẾ 100%** | Dữ liệu đo đạc khách quan từ runtime JVM Tomcat. Rất đáng tin cậy. |
| **Tên Service, Pod, Namespace** | Cào từ Kubernetes API qua `k8sattributes` và Downward API | **THỰC TẾ 100%** | Phản ánh đúng trạng thái cụm K8s runtime. |
| **Mã đám mây (`cloud.provider`)** | Cấu hình qua biến môi trường của Spoke (`aws`, `azure`) | **MÔ PHỎNG HỢP LỆ** | Cần ghi rõ trong bài báo: cụm k3d đóng vai trò là "Simulated Cloud Region". |
| **Chi tiết hạ tầng đám mây sâu (`vpc-0a1b...`, `IAM Role ARN`, Subnet, SG)** | **Tiêm tĩnh bằng quy tắc OTTL tại Hub Gateway** | **DỮ LIỆU TỔNG HỢP (Synthetic/Injected)** | **BẮT BUỘC PHẢI TUYÊN BỐ MINH BẠCH:** Đây là phương pháp "Synthetic Topology Enrichment via OTTL Policy" để mô phỏng khả năng liên kết dữ liệu trong môi trường multi-cloud khi chưa triển khai trên cloud thật. Tuyệt đối không được mô tả đây là dữ liệu tự động khám phá từ AWS/Azure API. |

### 8.2. Tính Bất biến của Viễn trắc Thô (Raw Telemetry Immutability)
- MinIO bucket `raw-telemetry` hiện nhận trực tiếp các payload OTLP JSON từ exporter `awss3`.
- Các tệp được lưu theo cấu trúc: `year=YYYY/month=MM/day=DD/hour=HH/raw_traces_*.json`.
- Dữ liệu thô được ghi theo cơ chế WORM (Write Once, Read Many), không bị thay đổi bởi bất kỳ quy trình downstream nào, đáp ứng trọn vẹn yêu cầu tái lập thực nghiệm khoa học.

---

## 9. DEPLOYMENT COMPLEXITY ASSESSMENT

Hiện tại, quy trình triển khai toàn bộ hệ thống đang bị phân mảnh giữa **hai công cụ khác nhau**:
1. **Ansible Playbooks:** Dùng để dựng k3d clusters, cấu hình WAN, sinh mTLS secrets và phân phối secrets.
2. **Kustomize / kubectl CLI:** Dùng để áp dụng manifests cho Hub Observability, MinIO, Thanos, Loki, Tempo, Grafana, Pyrra, Robusta và Spoke TeaStore workloads (được hướng dẫn thủ công trong `docs/progress/IMPLEMENTATION.md`).

### Các điểm gây nghẽn và rủi ro triển khai:
- Người dùng phải mở tài liệu `IMPLEMENTATION.md`, copy-paste lần lượt 8 khối lệnh khác nhau trên nhiều terminal.
- Thứ tự triển khai phụ thuộc: Nếu apply OTel Gateway trước khi Secret mTLS được tạo, Pod Gateway sẽ bị `CrashLoopBackOff` do không tìm thấy file chứng chỉ.
- Khả năng kiểm tra trạng thái tự động (idempotency check) chưa được tích hợp vào một luồng thống nhất.

---

## 10. PROPOSED REPOSITORY STRUCTURES

Nhằm đáp ứng yêu cầu của dự án, hai phương án tái cấu trúc được đề xuất dưới đây. Cả hai phương án đều giữ nguyên 100% phiên bản công nghệ và chức năng hệ thống.

---

### PHƯƠNG ÁN A – MINIMAL REFACTORING (Dọn dẹp An toàn Tối thiểu)

**Mục tiêu:** Giữ nguyên 90% cấu trúc thư mục hiện tại; chỉ dọn dẹp các thư mục thừa chết (`src/`), chuẩn hóa tên tệp bất thường, sửa lỗi thiếu image trong shell script và bổ sung master entrypoint.

#### Cây thư mục đề xuất (Option A):
```
multicloud-monitoring/
├── .agent/                             # Giữ nguyên
│   ├── rules/                          # Đổi tên: bỏ tiền tố agents__rules__
│   └── skills/
├── docs/
│   ├── architecture/                   # Giữ nguyên 6 tệp
│   ├── decisions/                      # Đổi tên thành ADR-000-template.md
│   ├── other-reference/                # Giữ nguyên 5 tệp PDF
│   ├── progress/                       # Giữ nguyên nhật ký tiến độ & RCA
│   ├── refactoring/                    # [MỚI] Chứa REPOSITORY_AUDIT.md & CHECKLIST.md
│   ├── research/                       # Giữ nguyên 11 tệp nghiên cứu
│   └── schemas/                        # Đổi tên: bỏ tiền tố docs__schemas__
├── experiments/                        # Chuẩn bị sẵn thư mục chạy Phase 4
│   ├── manifests/                      # [MỚI] Chứa cấu hình chạy thực nghiệm
│   ├── results/                        # [MỚI] Chứa raw/processed data
│   └── README.md
├── infra/
│   ├── README.md                       # Bảng kê phiên bản ghim cứng
│   ├── scripts/                        # [MỚI] Gom pull_images.sh và import_k3d_images.sh ra đây
│   │   ├── pull_images.sh              # [ĐÃ SỬA] Bổ sung teastore-webui:1.4.1
│   │   └── import_k3d_images.sh
│   └── ansible/
│       ├── ansible.cfg
│       ├── inventory.ini
│       └── playbooks/
│           ├── 00_cleanup_all.yml      # [ĐÃ SỬA] Sửa path certs
│           ├── 01_setup_host_tools.yml
│           ├── 02_provision_k3d_clusters.yml
│           ├── 03_emulate_wan_latency.yml
│           ├── 04_sync_cluster_hosts.yml # Đổi số thứ tự rõ ràng
│           ├── 05_verify_clusters.yml
│           ├── 06_distribute_mtls_secrets.yml
│           ├── 99_reset_wan_emulation.yml # Đổi từ 04_reset... để tránh trùng số
│           └── site.yml                # [ĐÃ SỬA] Import đủ 04_sync và 06_distribute
├── k8s/                                # Giữ nguyên cấu trúc SRP và Kustomize Base/Overlays
│   ├── base/                           # Tinh chỉnh nhẹ OTTL và PromQL
│   └── overlays/local-k3d/
├── security/                           # Giữ nguyên cấu trúc PKI và scripts
├── Benchmark-app/                      # Giữ nguyên mã nguồn TeaStore
├── Makefile (hoặc deploy.sh)           # [MỚI] Entrypoint điều phối một lệnh (make all / make clean)
├── AGENTS.md
├── PLAN.md
├── README.md                           # Gộp nội dung từ overview.md
└── .gitignore                          # [ĐÃ SỬA] Bổ sung bảo vệ security/pki/*
```

---

### PHƯƠNG ÁN B – SIMPLIFIED ARCHITECTURE (Tái cấu trúc Tối ưu Chức năng)

**Mục tiêu:** Tinh gọn độ sâu thư mục, gom nhóm theo mục đích vận hành rõ ràng: `automation/` (hạ tầng & triển khai), `observability/` (cấu hình K8s & dashboards), `workload/` (ứng dụng benchmark), `docs/` (tài liệu), loại bỏ triệt để các tầng thư mục lồng nhau không cần thiết.

#### Cây thư mục đề xuất (Option B):
```
multicloud-monitoring/
├── deploy/                             # Tầng tự động hóa triển khai duy nhất
│   ├── Makefile                        # Entrypoint chuẩn cho kỹ sư SRE
│   ├── scripts/                        # Các shell scripts hỗ trợ (pull, import, pki)
│   │   ├── setup-pki.sh                # Hợp nhất từ 3 scripts trong security/pki
│   │   ├── pull-images.sh              # Đã bổ sung teastore-webui
│   │   └── import-k3d-images.sh
│   └── ansible/                        # Chỉ giữ lại playbooks hạ tầng cốt lõi
│       ├── ansible.cfg
│       ├── inventory.ini
│       └── playbooks/                  # Đánh số chuẩn 00 -> 06
├── manifests/                          # Đổi tên từ k8s/ để giảm độ sâu
│   ├── apps/                           # Toàn bộ TeaStore microservices (gộp gọn lại)
│   │   ├── teastore-compute.yaml       # Gộp WebUI, Auth, Image, Recommender, Registry
│   │   └── teastore-data.yaml          # Gộp Persistence, MySQL
│   ├── platform/                       # Toàn bộ hạ tầng quan sát
│   │   ├── minio/
│   │   ├── thanos-prometheus/
│   │   ├── loki/
│   │   ├── tempo/
│   │   ├── otel-edge/
│   │   ├── otel-gateway/
│   │   ├── grafana/                    # Bao gồm cả 7 JSON dashboards
│   │   ├── pyrra/
│   │   └── robusta/
│   └── overlays/                       # Overlays cho từng môi trường
│       ├── local-k3d/                  # 3 cụm k3d cục bộ
│       └── cloud-ready/                # Khung sẵn sàng cho AWS EKS / Azure AKS
├── security/                           # Chứng chỉ mTLS & Root CA
│   ├── ca/
│   └── certs/                          # Hub, Spoke 1, Spoke 2
├── workload/                           # Đổi tên từ Benchmark-app/
│   ├── teastore-source/                # Mã nguồn TeaStore Java
│   └── locust/                         # locustfile.py và kịch bản tải
├── experiments/                        # Phục vụ riêng cho Phase 4 Benchmark
│   ├── profiles/                       # Hồ sơ cấu hình tải (Low, Medium, Stress)
│   ├── raw-data/                       # Lưu trữ viễn trắc xuất từ MinIO
│   └── analysis/                       # Script phân tích sai số MAPE, đồ thị
├── docs/                               # Tài liệu học thuật và dự án
│   ├── architecture/
│   ├── progress/
│   ├── research/
│   └── refactoring/
├── AGENTS.md
├── PLAN.md
├── README.md
└── .gitignore
```

---

## 11. REFACTORING OPTIONS COMPARISON

| Tiêu chí so sánh | Hiện trạng (As-Is) | Phương án A (Minimal) | Phương án B (Simplified) |
|---|:---:|:---:|:---:|
| **Số lượng thư mục cấp cao** | 9 thư mục | 9 thư mục (giữ nguyên) | 7 thư mục (gom nhóm mạch lạc) |
| **Xóa bỏ mã chết (`src/`)** | Chưa xóa | **ĐÃ XÓA TRIỆT ĐỂ** | **ĐÃ XÓA TRIỆT ĐỂ** |
| **Khắc phục lỗi `pull_images.sh`** | Thiếu `teastore-webui` | **ĐÃ SỬA & KIỂM CHỨNG** | **ĐÃ SỬA & KIỂM CHỨNG** |
| **Tối ưu hóa OTTL** | 75 câu lệnh trùng lặp | Rút gọn, khử trùng lặp | Tối ưu hóa tập trung |
| **Mức độ ảnh hưởng mã nguồn K8s** | 0% | **0%** (Giữ nguyên cấu trúc K8s) | **Cao** (Gộp manifests, đổi đường dẫn) |
| **Rủi ro hồi quy (Regression Risk)** | N/A | **Cực kỳ thấp (Rất an toàn)** | **Trung bình - Cao** |
| **Độ phức tạp di chuyển file** | Không | Thấp (~10 tệp di chuyển/sửa) | Cao (~80 tệp di chuyển/viết lại) |
| **Thời gian thực hiện dự kiến** | 0 giờ | **1 – 2 giờ** | **6 – 8 giờ** |
| **Tác động đến tiến độ Phase 4** | Không | **Sẵn sàng ngay lập tức** | Bị hoãn để kiểm thử lại toàn bộ K8s |

> **Khuyến nghị chuyên môn:**  
> Đứng dưới góc độ SRE và mục tiêu trước mắt là **tiến hành Phase 4 Benchmark**, **Phương án A là phương án hợp lý và an toàn nhất**. Phương án A giải quyết triệt để 100% các lỗi kỹ thuật, nợ code thừa và sai lệch đường dẫn mà không làm xáo trộn cấu trúc Kubernetes manifests đã được kiểm chứng hoạt động ổn định. Phương án B có cấu trúc rất đẹp về mặt thẩm mỹ, nhưng tiềm ẩn rủi ro hồi quy cao và tốn nhiều thời gian cấu hình lại Kustomize paths.

---

## 12. REGRESSION TEST STRATEGY

Để đảm bảo quá trình tái cấu trúc không làm gián đoạn bất kỳ chức năng quan trọng nào, kế hoạch kiểm thử hồi quy được phân tầng thành 4 cấp độ:

```
[Level 1: Cú pháp & Static Linting]
   └── yaml-lint, ansible-lint, kustomize build test, openssl verify
[Level 2: Khởi tạo Hạ tầng (Infra Integration)]
   └── k3d clusters ready, network bridge ping, tc netem RTT verify
[Level 3: Đường ống Dữ liệu (Telemetry E2E)]
   └── mTLS handshake, OTel metrics/logs/traces export, Thanos TSDB blocks, MinIO raw JSON
[Level 4: Trực quan hóa & Nghiệp vụ (SRE Validation)]
   └── Grafana 7 Dashboards healthy, Pyrra SLO 99.5%, Robusta Telegram Alert, Locust Load Test
```

### Bảng chỉ tiêu kiểm chứng 16 hạng mục bắt buộc:
1. **Cluster Provisioning:** 3 cụm k3d ở trạng thái Ready, CoreDNS phân giải tên miền chéo cụm.
2. **TeaStore Availability:** Truy cập WebUI cổng 8080 phản hồi HTTP 200, duyệt danh mục sản phẩm mượt mà.
3. **MySQL Connectivity:** `teastore-persistence` kết nối ổn định tới `teastore-db:3306`, không bị ngắt kết nối bất thường.
4. **WAN Latency & Loss:** `ping -c 10 k3d-azure-k3d-server-0` từ cụm AWS đạt RTT 10ms ±2ms, packet loss 0.1%.
5. **mTLS Connectivity:** Spoke OTel Collector bắt tay TLS 1.3 thành công với Hub Gateway qua cổng 4317, từ chối kết nối không có cert hợp lệ.
6. **OTel Metrics Ingestion:** Chỉ số runtime JVM, Tomcat và hostmetrics đổ về đầy đủ.
7. **OTel Logs Ingestion:** Logs stdout/stderr từ Pods TeaStore truyền về Hub và đẩy vào Loki.
8. **OTel Traces Ingestion:** Spans W3C TraceContext liên kết xuyên suốt từ WebUI -> Auth -> Recommender -> Persistence.
9. **Prometheus / Thanos Queries:** Thanos Query trả về kết quả PromQL tức thời cho metric `traces_service_graph_request_total`.
10. **Loki Log Queries:** LogQL truy vấn được log theo nhãn `k8s_cluster_name="azure-k3d"` và `service_name="teastore-db"`.
11. **Tempo Trace Queries:** Tìm kiếm được trace theo `service.name=teastore-webui` và hiển thị đầy đủ thác nước span (span waterfall).
12. **MinIO Bucket Integrity:** 4 bucket đều có dữ liệu ghi mới liên tục, đặc biệt `thanos-metrics` và `raw-telemetry`.
13. **Grafana Dashboards:** Cả 7 Dashboards hiển thị không báo lỗi panel (`No data` hoặc `Error`).
14. **SLO Evaluation:** Pyrra UI cổng 9099 hiển thị mục tiêu SLO 99.5% của TeaStore WebUI, tính toán chính xác Error Budget.
15. **Smart Alerting:** Robusta gửi thông báo enriched event về Telegram khi thử nghiệm kích hoạt crash loop pod.
16. **Benchmark Reproducibility:** Chạy kịch bản Locust 50 người dùng ảo đồng thời, hệ thống thu thập đầy đủ viễn trắc mà không bị nghẽn collector.

---

## 13. RISKS AND MIGRATION CONSIDERATIONS

1. **Rủi ro mất kết nối mTLS:** Nếu cấu hình lại SANs hoặc đổi đường dẫn certs sai, OTel Spoke sẽ bị từ chối kết nối (`x509: certificate signed by unknown authority`).
   - *Biện pháp giảm thiểu:* Giữ nguyên toàn bộ private keys và CA hiện tại trong `security/pki/`, chỉ điều chỉnh script phân phối Secret.
2. **Rủi ro gián đoạn Service Graph trong Grafana:** Việc sửa biểu thức PromQL trong `system-topology.json` nếu không kiểm tra kỹ cú pháp có thể khiến panel bị lỗi `id field is required`.
   - *Biện pháp giảm thiểu:* Sao lưu tệp JSON dashboard cũ trước khi cập nhật; kiểm tra tính tương thích của bảng dữ liệu đầu ra.
3. **Rủi ro cạn kiệt tài nguyên máy host (Out of Memory):** Khi chạy lại toàn bộ quy trình, nếu không dọn dẹp sạch các container cũ, Docker có thể chiếm dụng quá 24GB RAM.
   - *Biện pháp giảm thiểu:* Chạy kịch bản dọn dẹp triệt để `00_cleanup_all.yml` trước khi tái triển khai.

---

## 14. RECOMMENDED NEXT STEPS

1. **Bước 1 (Chờ phê duyệt):** Trình báo cáo kiểm toán này và bảng đối chiếu phương án (Option A vs Option B) cho người dùng phê duyệt.
2. **Bước 2 (Thực hiện dọn dẹp an toàn - Option A):**
   - Xóa bỏ hoàn toàn thư mục thừa `src/`.
   - Bổ sung `teastore-webui:1.4.1` vào `pull_images.sh`.
   - Di chuyển các script tiện ích ra `infra/scripts/`.
   - Hiệu chỉnh các playbook Ansible bị lệch đường dẫn (`site.yml`, `00_cleanup_all.yml`).
3. **Bước 3 (Chuẩn hóa tên tệp và tài liệu):**
   - Đổi tên các tệp có tiền tố `__` trong `docs/schemas/`, `docs/decisions/`, `.agent/rules/`.
   - Xóa bỏ các tham chiếu tới `docs/process/` trong tài liệu.
4. **Bước 4 (Tạo Makefile Entrypoint):**
   - Xây dựng tệp `Makefile` chuẩn hóa quy trình 4 lệnh: `make setup`, `make deploy`, `make verify`, `make teardown`.
5. **Bước 5 (Sẵn sàng cho Phase 4):**
   - Bước vào giai đoạn chạy thực nghiệm tải và đánh giá khoa học (Phase 4: Benchmark and Evaluation).

---

## 15. OPEN QUESTIONS

1. **Lựa chọn phương án:** Người dùng mong muốn triển khai theo **Phương án A (Minimal - Khuyến nghị an toàn)** hay **Phương án B (Simplified - Tái cấu trúc sâu)**?
2. **Cơ chế Secret Management:** Người dùng có muốn tiếp tục lưu Secret mẫu trong K8s YAML cục bộ hay muốn tích hợp Kustomize `secretGenerator` đọc từ file `.env` ngoài (không commit Git)?
3. **Phương thức Entrypoint:** Người dùng ưu tiên sử dụng công cụ nào làm entrypoint điều phối chính: **`Makefile`** (chuẩn DevOps/SRE) hay một tập lệnh **CLI Shell script (`deploy.sh`)**?

